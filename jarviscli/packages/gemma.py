# -*- coding: utf-8 -*-
"""Local Gemma 4, served on this computer by the OpenVINO Model Server.

Nothing leaves the machine. The `gemma4` snap runs the server (127.0.0.1:8336)
and speaks the OpenAI chat-completions dialect under /v3. Jarvis uses it:

  * as the "private mode" brain: `private <question>` or `private on`;
    in private mode no question is sent to Claude at all (not even the
    keyword-router check),
  * as the answer when Claude cannot be reached (offline, not signed in,
    spend cap used up), ahead of the slower Ollama model,
  * directly, with `gemma <question>`.

  JARVIS_GEMMA_URL=http://127.0.0.1:8336/v3
  JARVIS_GEMMA_MODEL=gemma4-e4b-ov
  JARVIS_PRIVATE=1                    start in private mode

On this CPU-only laptop expect a few seconds to a minute per answer.
"""
import os
import threading

import requests

URL = os.environ.get('JARVIS_GEMMA_URL', 'http://127.0.0.1:8336/v3').rstrip('/')
MODEL = os.environ.get('JARVIS_GEMMA_MODEL', 'gemma4-e4b-ov')
MAX_TURNS = 8           # question/answer pairs kept for follow-ups
MAX_TOKENS = 400

SYSTEM = (
    "You are Jarvis, a voice assistant on the user's Linux desktop. Your replies "
    "are read aloud, so answer in one to three short, natural sentences, with no "
    "markdown, lists, tables, code blocks or URLs unless the user asks for them. "
    "You run locally and have no internet access, so if a question needs current "
    "facts, say you cannot look that up right now."
)


class GemmaError(RuntimeError):
    """A failure with a message fit for the user."""


_private = os.environ.get('JARVIS_PRIVATE', '0').strip().lower() in ('1', 'true', 'yes', 'on')


def private_mode():
    return _private


def set_private(value):
    global _private
    _private = bool(value)
    return _private


def available(timeout=1.5):
    """True when the server answers and lists the configured model."""
    try:
        r = requests.get(URL + '/models', timeout=timeout)
        r.raise_for_status()
        return any(m.get('id') == MODEL for m in r.json().get('data', []))
    except (requests.RequestException, ValueError):
        return False


class Gemma(object):
    """One short conversation with the local model."""

    def __init__(self, model=None):
        self.model = model or MODEL
        self.history = []
        self._lock = threading.Lock()

    def reset(self):
        with self._lock:
            self.history = []

    def chat(self, prompt, keep_history=True, system=SYSTEM, max_tokens=MAX_TOKENS,
             timeout=240):
        with self._lock:
            messages = [{'role': 'system', 'content': system}]
            if keep_history:
                messages += self.history
            messages.append({'role': 'user', 'content': prompt})
            try:
                r = requests.post(
                    URL + '/chat/completions', timeout=timeout,
                    json={'model': self.model, 'messages': messages, 'stream': False,
                          'max_tokens': max_tokens, 'temperature': 0.4})
                r.raise_for_status()
                text = r.json()['choices'][0]['message']['content'].strip()
            except requests.ConnectionError:
                raise GemmaError('The local Gemma server is not running (the gemma4 snap).')
            except requests.Timeout:
                raise GemmaError('Gemma took too long to answer.')
            except (requests.RequestException, KeyError, IndexError, ValueError) as e:
                raise GemmaError('Gemma returned an error: %s' % e)
            if keep_history:
                self.history += [{'role': 'user', 'content': prompt},
                                 {'role': 'assistant', 'content': text}]
                del self.history[:-2 * MAX_TURNS]
            return text


_gemma = Gemma()


def ask(question, keep_history=True, system=SYSTEM, max_tokens=MAX_TOKENS):
    """Answer with the shared conversation. Raises GemmaError."""
    return _gemma.chat(question, keep_history=keep_history, system=system,
                       max_tokens=max_tokens)


def reset():
    _gemma.reset()
