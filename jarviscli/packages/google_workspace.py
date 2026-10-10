# -*- coding: utf-8 -*-
"""Google Workspace for Jarvis: Calendar, Gmail, Drive and Docs, Sheets, Contacts.

Setup (once): doc/GOOGLE_WORKSPACE.md. In short, create an OAuth "Desktop app"
client in Google Cloud, save its JSON as ~/.config/jarvis/google/client_secret.json,
then run `gws login` and approve access in the browser.

Design rules:
  * Nothing here writes without the plugin asking for a yes first.
  * Tokens live in ~/.config/jarvis/google/token.json, readable only by you.
  * Mail, documents and sheets are untrusted text. They are only ever shown or
    summarised; nothing in them is executed or treated as an instruction.
  * The Google libraries are imported lazily, so Jarvis starts without them.

  JARVIS_GOOGLE_DIR=~/.config/jarvis/google
"""
import base64
import datetime
import html
import os
import re
from email.message import EmailMessage

from dateutil import parser as dateparser

CONFIG_DIR = os.path.expanduser(os.environ.get('JARVIS_GOOGLE_DIR', '~/.config/jarvis/google'))
CLIENT_SECRET = os.path.join(CONFIG_DIR, 'client_secret.json')
TOKEN = os.path.join(CONFIG_DIR, 'token.json')

SCOPES = [
    'https://www.googleapis.com/auth/calendar.events',      # read and write events
    'https://www.googleapis.com/auth/gmail.readonly',       # read and search mail
    'https://www.googleapis.com/auth/gmail.compose',        # create drafts, send a draft
    'https://www.googleapis.com/auth/drive.readonly',       # search and read files
    'https://www.googleapis.com/auth/drive.file',           # files Jarvis itself creates
    'https://www.googleapis.com/auth/spreadsheets',         # read and write sheets
    'https://www.googleapis.com/auth/contacts.readonly',    # look up contacts
]

MAX_TEXT = 4000         # characters of any one body, document or sheet shown
WEEKDAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
INSTALL_HINT = ('The Google libraries are not installed. Run: '
                '~/jarvis-claude/env/bin/pip install google-api-python-client '
                'google-auth-oauthlib google-auth-httplib2')


class GoogleError(RuntimeError):
    """A failure with a message fit for the user."""


# ------------------------------------------------------------------ sign-in

def is_configured():
    return os.path.exists(CLIENT_SECRET)


def is_signed_in():
    return os.path.exists(TOKEN)


def _save_token(creds):
    os.makedirs(CONFIG_DIR, mode=0o700, exist_ok=True)
    fd = os.open(TOKEN, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as f:
        f.write(creds.to_json())
    os.chmod(TOKEN, 0o600)


def login():
    """Open the browser consent screen and store the token."""
    if not is_configured():
        raise GoogleError('No client_secret.json in %s. See doc/GOOGLE_WORKSPACE.md.' % CONFIG_DIR)
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        raise GoogleError(INSTALL_HINT)
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES)
    creds = flow.run_local_server(port=0, prompt='consent')
    _save_token(creds)


def logout():
    """Forget the local token. Access can also be revoked at
    https://myaccount.google.com/permissions"""
    if is_signed_in():
        os.remove(TOKEN)


def _credentials():
    try:
        from google.auth.exceptions import RefreshError
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError:
        raise GoogleError(INSTALL_HINT)
    if not is_signed_in():
        raise GoogleError('Not signed in to Google. Say "gws login".')
    creds = Credentials.from_authorized_user_file(TOKEN, SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError:
                raise GoogleError('Your Google sign-in expired. Say "gws login" again.')
            _save_token(creds)
        else:
            raise GoogleError('Your Google sign-in is no longer valid. Say "gws login" again.')
    return creds


def _service(name, version):
    try:
        from googleapiclient.discovery import build
    except ImportError:
        raise GoogleError(INSTALL_HINT)
    return build(name, version, credentials=_credentials(), cache_discovery=False)


def _execute(request):
    """Run a Google API request, turning HTTP failures into readable errors."""
    try:
        return request.execute()
    except GoogleError:
        raise
    except Exception as e:      # googleapiclient.errors.HttpError and network errors
        status = getattr(getattr(e, 'resp', None), 'status', None)
        if status == 403:
            raise GoogleError('Google refused that (403). The API may be switched off in your '
                              'Google Cloud project, or the permission was not granted.')
        if status == 404:
            raise GoogleError('Google could not find that item.')
        raise GoogleError('Google request failed: %s' % e)


# ----------------------------------------------------------------- calendar

def parse_when(text, now=None):
    """'tomorrow 3pm', 'friday at 2:30pm', '12 oct 9am' -> aware local datetime.
    A date with no time means 09:00; a time with no date means today."""
    now = (now or datetime.datetime.now().astimezone())
    words = re.sub(r'\b(at|on|the)\b', ' ', text.lower()).split()
    day = now.date()
    rest = []
    for w in words:
        if w == 'today':
            day = now.date()
        elif w == 'tomorrow':
            day = now.date() + datetime.timedelta(days=1)
        elif w.rstrip(',') in WEEKDAYS or (w in [d[:3] for d in WEEKDAYS]):
            idx = [d[:3] for d in WEEKDAYS].index(w.rstrip(',')[:3])
            ahead = (idx - now.weekday()) % 7 or 7
            day = now.date() + datetime.timedelta(days=ahead)
        elif w != 'next':
            rest.append(w)
    base = datetime.datetime.combine(day, datetime.time(9, 0))
    try:
        parsed = dateparser.parse(' '.join(rest), default=base) if rest else base
    except (ValueError, OverflowError):
        raise GoogleError('I could not understand the date "%s".' % text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=now.tzinfo)
    return parsed


def split_event_request(text):
    """'dentist tomorrow at 3pm for 30 minutes' -> ('dentist', 'tomorrow at 3pm', 30)"""
    minutes = 60
    m = re.search(r'\s+for\s+(\d+)\s*(h|hr|hrs|hours?|m|min|mins|minutes?)\b\s*$', text, re.I)
    if m:
        minutes = int(m.group(1)) * (60 if m.group(2).lower().startswith('h') else 1)
        text = text[:m.start()]
    marker = re.compile(r'\b(at|on|today|tomorrow|next|%s|%s)\b' % (
        '|'.join(WEEKDAYS), '|'.join(d[:3] for d in WEEKDAYS)), re.I)
    m = marker.search(text)
    if not m or not text[:m.start()].strip():
        raise GoogleError('Say it like: add dentist tomorrow at 3pm for 30 minutes.')
    return text[:m.start()].strip(), text[m.start():].strip(), minutes


def _event_time(e):
    start = e.get('start', {})
    if 'dateTime' in start:
        return dateparser.parse(start['dateTime']).strftime('%a %d %b %H:%M')
    return dateparser.parse(start.get('date', '1970-01-01')).strftime('%a %d %b') + ' all day'


def events_between(start, end, limit=15):
    data = _execute(_service('calendar', 'v3').events().list(
        calendarId='primary', timeMin=start.isoformat(), timeMax=end.isoformat(),
        singleEvents=True, orderBy='startTime', maxResults=limit))
    return ['%s  %s' % (_event_time(e), e.get('summary', '(no title)')) for e in data.get('items', [])]


def events_on(day_offset=0, days=1, now=None):
    now = now or datetime.datetime.now().astimezone()
    start = datetime.datetime.combine(now.date() + datetime.timedelta(days=day_offset),
                                      datetime.time.min).replace(tzinfo=now.tzinfo)
    return events_between(start, start + datetime.timedelta(days=days))


def upcoming(limit=5):
    now = datetime.datetime.now().astimezone()
    return events_between(now, now + datetime.timedelta(days=60), limit)


def add_event(title, start, minutes=60):
    body = {'summary': title,
            'start': {'dateTime': start.isoformat()},
            'end': {'dateTime': (start + datetime.timedelta(minutes=minutes)).isoformat()},
            'reminders': {'useDefault': True}}
    return _execute(_service('calendar', 'v3').events().insert(calendarId='primary', body=body))


# -------------------------------------------------------------------- gmail

def _header(msg, name):
    for h in msg.get('payload', {}).get('headers', []):
        if h['name'].lower() == name.lower():
            return h['value']
    return ''


def _strip_html(text):
    text = re.sub(r'(?is)<(script|style).*?</\1>', ' ', text)
    text = re.sub(r'(?s)<[^>]+>', ' ', text)
    return re.sub(r'[ \t]+', ' ', html.unescape(text))


def _body_text(payload):
    """Plain text of a message, preferring text/plain over HTML."""
    plain, rich = [], []

    def walk(part):
        mime = part.get('mimeType', '')
        data = part.get('body', {}).get('data')
        if data and mime in ('text/plain', 'text/html'):
            raw = base64.urlsafe_b64decode(data + '=' * (-len(data) % 4)).decode('utf-8', 'replace')
            (plain if mime == 'text/plain' else rich).append(raw)
        for sub in part.get('parts', []) or []:
            walk(sub)
    walk(payload)
    text = '\n'.join(plain) if plain else _strip_html('\n'.join(rich))
    return re.sub(r'\n{3,}', '\n\n', text).strip()


def search_mail(query, limit=5):
    svc = _service('gmail', 'v1')
    refs = _execute(svc.users().messages().list(userId='me', q=query, maxResults=limit)).get('messages', [])
    out = []
    for ref in refs:
        m = _execute(svc.users().messages().get(
            userId='me', id=ref['id'], format='metadata',
            metadataHeaders=['From', 'Subject', 'Date']))
        out.append({'id': ref['id'], 'from': _header(m, 'From'), 'subject': _header(m, 'Subject'),
                    'date': _header(m, 'Date'), 'snippet': html.unescape(m.get('snippet', ''))})
    return out


def read_mail(message_id):
    m = _execute(_service('gmail', 'v1').users().messages().get(
        userId='me', id=message_id, format='full'))
    return {'from': _header(m, 'From'), 'to': _header(m, 'To'), 'subject': _header(m, 'Subject'),
            'date': _header(m, 'Date'), 'body': _body_text(m.get('payload', {}))[:MAX_TEXT]}


def _clean_header(value):
    """No line breaks in a header value: stops header injection via a pasted address."""
    return re.sub(r'[\r\n]+', ' ', value).strip()


def create_draft(to, subject, body):
    msg = EmailMessage()
    msg['To'] = _clean_header(to)
    msg['Subject'] = _clean_header(subject)
    msg.set_content(body)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return _execute(_service('gmail', 'v1').users().drafts().create(
        userId='me', body={'message': {'raw': raw}}))


def list_drafts(limit=5):
    svc = _service('gmail', 'v1')
    out = []
    for d in _execute(svc.users().drafts().list(userId='me', maxResults=limit)).get('drafts', []):
        full = _execute(svc.users().drafts().get(userId='me', id=d['id'], format='metadata'))
        msg = full.get('message', {})
        out.append({'id': d['id'], 'to': _header(msg, 'To'), 'subject': _header(msg, 'Subject')})
    return out


def send_draft(draft_id):
    return _execute(_service('gmail', 'v1').users().drafts().send(userId='me', body={'id': draft_id}))


# -------------------------------------------------------------------- drive

EXPORTS = {
    'application/vnd.google-apps.document': 'text/plain',
    'application/vnd.google-apps.presentation': 'text/plain',
    'application/vnd.google-apps.spreadsheet': 'text/csv',
}


def drive_search(text, limit=5):
    safe = text.replace('\\', '\\\\').replace("'", "\\'")
    data = _execute(_service('drive', 'v3').files().list(
        q="fullText contains '%s' and trashed = false" % safe, pageSize=limit,
        orderBy='modifiedTime desc', fields='files(id,name,mimeType,modifiedTime)'))
    return data.get('files', [])


def drive_read(file_id):
    svc = _service('drive', 'v3')
    meta = _execute(svc.files().get(fileId=file_id, fields='id,name,mimeType,size'))
    mime = meta.get('mimeType', '')
    if mime in EXPORTS:
        raw = _execute(svc.files().export(fileId=file_id, mimeType=EXPORTS[mime]))
    elif mime.startswith('text/'):
        raw = _execute(svc.files().get_media(fileId=file_id))
    else:
        raise GoogleError('"%s" is not a text file I can read (%s).' % (meta.get('name'), mime))
    text = raw.decode('utf-8', 'replace') if isinstance(raw, bytes) else str(raw)
    return meta.get('name', ''), text[:MAX_TEXT]


def create_doc(title, body):
    svc = _service('docs', 'v1')
    doc = _execute(svc.documents().create(body={'title': title}))
    if body:
        _execute(svc.documents().batchUpdate(documentId=doc['documentId'], body={
            'requests': [{'insertText': {'location': {'index': 1}, 'text': body}}]}))
    return 'https://docs.google.com/document/d/%s/edit' % doc['documentId']


# ------------------------------------------------------------------- sheets

def read_sheet(sheet_id, cell_range='A1:F20'):
    data = _execute(_service('sheets', 'v4').spreadsheets().values().get(
        spreadsheetId=sheet_id, range=cell_range))
    return data.get('values', [])


def append_row(sheet_id, cell_range, values):
    return _execute(_service('sheets', 'v4').spreadsheets().values().append(
        spreadsheetId=sheet_id, range=cell_range, valueInputOption='USER_ENTERED',
        body={'values': [values]}))


# ----------------------------------------------------------------- contacts

def search_contacts(query, limit=5):
    svc = _service('people', 'v1')
    mask = 'names,emailAddresses,phoneNumbers'
    # The People API asks for an empty warm-up search before the first real one.
    _execute(svc.people().searchContacts(query='', readMask=mask))
    data = _execute(svc.people().searchContacts(query=query, readMask=mask, pageSize=limit))
    out = []
    for r in data.get('results', []):
        p = r.get('person', {})
        out.append({'name': (p.get('names') or [{}])[0].get('displayName', '(no name)'),
                    'email': ', '.join(e['value'] for e in p.get('emailAddresses', [])),
                    'phone': ', '.join(n['value'] for n in p.get('phoneNumbers', []))})
    return out
