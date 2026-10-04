# -*- coding: utf-8 -*-
"""Free, offline AI through a local open-source model (packages/local_llm.py).

  local <question>          ask the local model (keeps conversation context)
  local status | reset      model, server and download state / forget context
  local model <name>        switch to another model pulled into Ollama
  research <topic>          research brief from Wikipedia sources, with citations
  draft <description>       write a document; saved as Markdown in ~/Documents/Jarvis
"""
from colorama import Fore

from packages import local_llm
from plugin import plugin

_llm = local_llm.LocalLLM()


def _stream_to(jarvis):
    """Print the reply as it is generated: on a CPU it takes a while."""
    buffer = []

    def on_text(chunk):
        buffer.append(chunk)
        text = ''.join(buffer)
        if '\n' in text:
            head, _, tail = text.rpartition('\n')
            print(Fore.CYAN + local_llm.strip_think(head) + Fore.RESET, flush=True)
            buffer[:] = [tail]

    def flush():
        tail = ''.join(buffer).strip()
        if tail:
            print(Fore.CYAN + tail + Fore.RESET, flush=True)
    return on_text, flush


def _run(jarvis, prompt, keep_history=True, system=local_llm.SYSTEM):
    on_text, flush = _stream_to(jarvis)
    try:
        text = _llm.chat(prompt, on_text=on_text, keep_history=keep_history, system=system)
    except local_llm.LocalLLMError as e:
        jarvis.say(str(e), Fore.RED)
        return None
    flush()
    return text


@plugin("local")
def local(jarvis, s):
    """Ask the free local AI model. Try: local status | local reset | local <question>"""
    s = s.strip()
    if not s or s == 'status':
        exe = local_llm.ollama_binary()
        jarvis.say('model:   %s' % _llm.model, Fore.GREEN)
        jarvis.say('ollama:  %s' % (exe or 'not installed (scripts/install-local-llm.sh)'), Fore.GREEN)
        if exe:
            try:
                models = local_llm.installed_models()
                jarvis.say('models:  %s' % (', '.join(models) or 'none downloaded'), Fore.GREEN)
            except local_llm.LocalLLMError as e:
                jarvis.say('server:  %s' % e, Fore.YELLOW)
        return
    if s == 'reset':
        _llm.reset()
        jarvis.say('Local conversation cleared.', Fore.GREEN)
        return
    if s.startswith('model'):
        name = s[len('model'):].strip()
        if name:
            _llm.model = name
            _llm.reset()
        jarvis.say('Local model: %s' % _llm.model, Fore.GREEN)
        return
    _run(jarvis, s)


@plugin("research")
def research(jarvis, s):
    """Research brief on a topic, written by the local model from Wikipedia sources."""
    topic = s.strip()
    if not topic:
        jarvis.say('What should I research?', Fore.YELLOW)
        return
    jarvis.say('Looking up sources on %s...' % topic, Fore.GREEN, speak=False)
    sources = local_llm.wikipedia_sources(topic)
    jarvis.say('Found %d source%s. Writing (this takes a few minutes on this computer)...'
               % (len(sources), '' if len(sources) == 1 else 's'), Fore.GREEN, speak=False)
    text = _run(jarvis, local_llm.research_prompt(topic, sources), keep_history=False,
                system=local_llm.SYSTEM_RESEARCH)
    if text:
        path = local_llm.save_document('research ' + topic, text)
        jarvis.say('Saved to %s' % path, Fore.GREEN)


@plugin("draft")
def draft(jarvis, s):
    """Write a document with the local model, e.g. draft a cover letter for a library job."""
    request = s.strip()
    if not request:
        jarvis.say('What should I write?', Fore.YELLOW)
        return
    jarvis.say('Writing (this takes a few minutes on this computer)...', Fore.GREEN, speak=False)
    text = _run(jarvis, local_llm.draft_prompt(request), keep_history=False)
    if text:
        first = text.strip().splitlines()[0].lstrip('# ').strip() if text.strip() else request
        path = local_llm.save_document(first or request, text)
        jarvis.say('Saved to %s' % path, Fore.GREEN)
