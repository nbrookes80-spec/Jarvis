# Google Workspace and local Gemma

Two additions to Jarvis: the local Gemma 4 model, and Google Calendar, Gmail,
Drive/Docs, Sheets and Contacts.

## Local Gemma 4 (private mode)

Gemma runs on this computer through the `gemma4` snap's OpenVINO server
(`127.0.0.1:8336`). Nothing is sent anywhere.

| Say | What happens |
|---|---|
| `private on` / `private off` | Every unmatched question goes to Gemma only. Claude is never contacted, not even for the keyword check. |
| `private <question>` | One question to Gemma only. |
| `gemma <question>` | Same, with conversation memory. `gemma status`, `gemma reset`. |
| (automatic) | If Claude cannot be reached, Gemma answers before the slower Ollama model does. |

If Gemma is not running, private mode says so and does **not** fall back to Claude.
On this CPU-only laptop expect seconds to a minute per answer. Gemma has no internet,
so it cannot look up current facts. Start in private mode with `JARVIS_PRIVATE=1`.

## Google Workspace: one-time setup

Jarvis cannot create the Google Cloud project for you; it needs your own Google
account's approval. About 10 minutes:

1. Go to <https://console.cloud.google.com/> and create a project (for example `jarvis`).
2. **APIs & Services > Library**: enable Google Calendar API, Gmail API, Google Drive API,
   Google Docs API, Google Sheets API and People API.
3. **APIs & Services > OAuth consent screen**: choose *External*, fill in the app name and
   your email, and add your own Google address as a **test user**.
4. **Credentials > Create credentials > OAuth client ID**, application type **Desktop app**.
   Download the JSON file.
5. Save it as `~/.config/jarvis/google/client_secret.json`:

   ```
   mkdir -p ~/.config/jarvis/google && chmod 700 ~/.config/jarvis/google
   mv ~/Downloads/client_secret_*.json ~/.config/jarvis/google/client_secret.json
   chmod 600 ~/.config/jarvis/google/client_secret.json
   ```
6. In Jarvis say `gws login`, approve in the browser. Google shows an
   "unverified app" warning because it is your own app; continue past it.
7. `gws status` should say signed in.

**Sign-in expiry.** While the consent screen is in *Testing*, Google expires the
sign-in after 7 days and you must run `gws login` again. To stop that, set the
publishing status to *In production* on the consent screen. For a personal app used
only by you, no verification is needed; the unverified-app warning stays.

## Commands

```
gws status | login | logout
gcal today | tomorrow | week | next
gcal add dentist tomorrow at 3pm for 30 minutes
email unread | inbox | search <words> | read 2 | summarize 2
email draft name@example.com | Subject | Message text
email drafts | send 1
gdrive search <words> | read 1
gdrive doc Meeting notes | text of the document
gsheet read <sheet id> [A1:F20]
gsheet add <sheet id> Sheet1!A:C | one, two, three
gcontacts <name>
```

The older `gmail` (SMTP sender) and `google` (web search) commands are untouched; the Workspace ones are `gws` and `email`.

Numbers ("read 2", "send 1") refer to the last list shown.

## Safety rules built in

- **Every write is read back and needs a yes**: calendar add, draft, send, new doc, sheet row.
  Anything other than yes cancels. Sending is a separate step from drafting.
- **Mail stays local.** `email summarize` is written by Gemma on this computer. Mail, documents
  and sheet contents are only shown or summarised, never obeyed: text inside an email cannot
  make Jarvis do anything.
- **Permissions requested** (scopes): calendar events; Gmail read and compose; Drive read-only
  plus files Jarvis creates; Sheets; contacts read-only. It cannot delete mail or files.
- **Token** is stored at `~/.config/jarvis/google/token.json`, mode 600. `gws logout`
  deletes it; to revoke access completely use <https://myaccount.google.com/permissions>.
- Mail bodies and documents are printed but not read aloud, so they are not spoken in the room.
