# -*- coding: utf-8 -*-
"""A free, open-source language model running locally through Ollama.

No account, no API key, no per-use cost, and nothing leaves the machine
(except Wikipedia lookups for `research`). Default model: Qwen3 8B
(Apache-2.0), chosen as the strongest writer that fits a 16 GB, CPU-only
machine. On CPU expect a few words per second, so it suits drafts and
research write-ups rather than quick spoken answers.

  JARVIS_LOCAL_MODEL=qwen3:8b     any model pulled into Ollama
  JARVIS_OLLAMA_URL=http://127.0.0.1:11434
  JARVIS_DOCS_DIR=~/Documents/Jarvis   where `draft` saves documents

Ollama itself is installed by scripts/install-local-llm.sh.
"""
import datetime
import json
import os
import re
import shutil
import subprocess
import time

import requests

OLLAMA_URL = os.environ.get('JARVIS_OLLAMA_URL', 'http://127.0.0.1:11434')
DEFAULT_MODEL = os.environ.get('JARVIS_LOCAL_MODEL', 'qwen3:8b')
DOCS_DIR = os.path.expanduser(os.environ.get('JARVIS_DOCS_DIR', '~/Documents/Jarvis'))
OLLAMA_BIN_CANDIDATES = [
    os.path.expanduser('~/.local/ollama/bin/ollama'),
    os.path.expanduser('~/.local/bin/ollama'),
    '/usr/local/bin/ollama', '/usr/bin/ollama',
]

SYSTEM = (
    "You are Jarvis, a helpful assistant running locally on the user's computer. "
    "Write clear, well-organised prose in British English. If you are not sure "
    "of a fact, say so rather than guessing."
)
SYSTEM_RESEARCH = (
    "You are Jarvis, a careful research and writing assistant. Base factual "
    "claims on the numbered sources you are given and cite them inline as [1], "
    "[2]. If the sources do not cover something, say so rather than inventing it."
)


class LocalLLMError(Exception):
    """Message is fit to show the user."""


def ollama_binary():
    found = shutil.which('ollama')
    if found:
        return found
    for path in OLLAMA_BIN_CANDIDATES:
        if os.access(path, os.X_OK):
            return path
    return None


def server_up():
    try:
        requests.get(OLLAMA_URL + '/api/version', timeout=2)
        return True
    except requests.RequestException:
        return False


def ensure_server(wait=15):
    """Start `ollama serve` in the background if it is not already running."""
    if server_up():
        return
    exe = ollama_binary()
    if exe is None:
        raise LocalLLMError("The local model isn't installed. Run scripts/install-local-llm.sh.")
    log = open(os.path.expanduser('~/.local/share/jarvis-ollama.log'), 'ab')
    subprocess.Popen([exe, 'serve'], stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                     start_new_session=True)
    deadline = time.time() + wait
    while time.time() < deadline:
        if server_up():
            return
        time.sleep(0.5)
    raise LocalLLMError('The local model server did not start; see ~/.local/share/jarvis-ollama.log.')


def installed_models():
    ensure_server()
    tags = requests.get(OLLAMA_URL + '/api/tags', timeout=10).json().get('models', [])
    return [t['name'] for t in tags]


class LocalLLM(object):

    def __init__(self, model=DEFAULT_MODEL):
        self.model = model
        self.history = []

    def reset(self):
        self.history = []

    def chat(self, prompt, on_text=None, keep_history=True, think=False, timeout=900,
             system=SYSTEM):
        """Send prompt; stream the reply through on_text(chunk); return full text."""
        ensure_server()
        if self.model not in installed_models() and \
                self.model + ':latest' not in installed_models():
            raise LocalLLMError("The model %s isn't downloaded yet. Run: "
                                "scripts/install-local-llm.sh" % self.model)
        messages = [{'role': 'system', 'content': system}]
        if keep_history:
            messages += self.history[-12:]
        messages.append({'role': 'user', 'content': prompt})
        body = {'model': self.model, 'messages': messages, 'stream': True,
                # Qwen3 "thinking" doubles the wait on a CPU for little gain
                # in plain writing; Ollama ignores the flag for other models.
                'think': think,
                'options': {'num_ctx': 8192}}
        parts = []
        try:
            with requests.post(OLLAMA_URL + '/api/chat', json=body, stream=True,
                               timeout=(10, timeout)) as r:
                if r.status_code != 200:
                    raise LocalLLMError('Local model error: %s' % r.text[:200])
                for line in r.iter_lines():
                    if not line:
                        continue
                    msg = json.loads(line)
                    chunk = msg.get('message', {}).get('content', '')
                    if chunk:
                        parts.append(chunk)
                        if on_text:
                            on_text(chunk)
                    if msg.get('done'):
                        break
        except requests.RequestException as e:
            raise LocalLLMError('Lost contact with the local model: %s' % e)
        text = strip_think(''.join(parts))
        if keep_history:
            self.history += [{'role': 'user', 'content': prompt},
                             {'role': 'assistant', 'content': text}]
        return text


def strip_think(text):
    return re.sub(r'<think>.*?</think>\s*', '', text, flags=re.S).strip()


# ------------------------------------------------------------------ research

WIKI_API = 'https://en.wikipedia.org/w/api.php'
# Wikipedia rejects anonymous default user agents (the `wikipedia` package
# gets an HTML error page back, hence a JSON decode error); identify ourselves.
WIKI_HEADERS = {'User-Agent': 'Jarvis-assistant/1.0 (https://github.com/nbrookes80-spec/Jarvis)'}


def wikipedia_sources(topic, limit=3, chars=2500):
    """[(title, url, extract)] for the top Wikipedia matches; [] if offline."""
    try:
        hits = requests.get(WIKI_API, headers=WIKI_HEADERS, timeout=15, params={
            'action': 'query', 'list': 'search', 'srsearch': topic, 'srlimit': limit,
            'format': 'json'}).json()['query']['search']
        if not hits:
            return []
    except (requests.RequestException, ValueError, KeyError):
        return []
    sources = []
    for h in hits:
        # Full-text extracts come back one page per request (exlimit is 1).
        try:
            pages = requests.get(WIKI_API, headers=WIKI_HEADERS, timeout=15, params={
                'action': 'query', 'prop': 'extracts|info', 'explaintext': 1,
                'inprop': 'url', 'titles': h['title'], 'redirects': 1,
                'format': 'json'}).json()['query']['pages']
        except (requests.RequestException, ValueError, KeyError):
            continue
        for page in pages.values():
            if page.get('extract'):
                sources.append((page['title'], page.get('fullurl', ''), page['extract'][:chars]))
    return sources


def research_prompt(topic, sources):
    if not sources:
        return ("Write a concise research brief on: %s\n\nNo sources could be fetched, so "
                "answer from general knowledge and state clearly that it is unverified." % topic)
    blocks = '\n\n'.join('[%d] %s (%s)\n%s' % (i + 1, t, u, x)
                         for i, (t, u, x) in enumerate(sources))
    return ("Sources:\n\n%s\n\nUsing these sources, write a research brief on: %s\n"
            "Structure: a two-sentence summary, then key points with inline citations, "
            "then open questions the sources leave unanswered. End with a 'Sources' list."
            % (blocks, topic))


# ------------------------------------------------------------------ documents

def save_document(title, body):
    os.makedirs(DOCS_DIR, exist_ok=True)
    slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')[:60] or 'document'
    stamp = datetime.datetime.now().strftime('%Y-%m-%d-%H%M')
    path = os.path.join(DOCS_DIR, '%s-%s.md' % (stamp, slug))
    with open(path, 'w') as f:
        f.write(body.rstrip() + '\n')
    return path


def draft_prompt(request):
    return ("Write the following document in Markdown, with a title line starting "
            "with '# ', clear headings and complete paragraphs. Do not add commentary "
            "before or after the document.\n\nRequest: %s" % request)


_default = None


def ask(question, on_text=None):
    """One-call entry point for other parts of Jarvis (e.g. the unmatched-input
    fallback): answer with the local model, keeping conversation context.
    Raises LocalLLMError with a user-facing message if it isn't available."""
    global _default
    if _default is None:
        _default = LocalLLM()
    return _default.chat(question, on_text=on_text)


def available():
    """Cheap check (no model load): Ollama installed and the model downloaded."""
    if ollama_binary() is None:
        return False
    try:
        return any(m.split(':latest')[0] == DEFAULT_MODEL.split(':latest')[0]
                   for m in installed_models())
    except (LocalLLMError, requests.RequestException, ValueError):
        return False
