# -*- coding: utf-8 -*-
"""Local Gemma 4 and private mode (packages/gemma.py). Nothing leaves this computer.

  gemma <question>        ask the local model (keeps conversation context)
  gemma status | reset
  private <question>      ask Gemma once, never Claude
  private on | off        send every unmatched question to Gemma, never Claude
"""
from colorama import Fore

from packages import gemma
from plugin import plugin


def _answer(jarvis, question):
    try:
        jarvis.say('Thinking locally...', Fore.GREEN, speak=False)
        jarvis.say(gemma.ask(question), Fore.CYAN)
    except gemma.GemmaError as e:
        jarvis.say(str(e), Fore.RED)


@plugin("gemma")
def gemma_cmd(jarvis, s):
    """Ask the local Gemma 4 model. Try: gemma status | gemma reset | gemma <question>"""
    s = s.strip()
    if not s or s == 'status':
        jarvis.say('model:   %s' % gemma.MODEL, Fore.GREEN)
        jarvis.say('server:  %s (%s)' % (gemma.URL, 'running' if gemma.available() else 'not reachable'),
                   Fore.GREEN)
        jarvis.say('private: %s' % ('on' if gemma.private_mode() else 'off'), Fore.GREEN)
        return
    if s == 'reset':
        gemma.reset()
        jarvis.say('Gemma conversation cleared.', Fore.GREEN)
        return
    _answer(jarvis, s)


@plugin("private")
def private(jarvis, s):
    """Keep questions on this computer. Try: private on | private off | private <question>"""
    s = s.strip()
    word = s.lower()
    if word == 'on':
        gemma.set_private(True)
        jarvis.say('Private mode on. Questions stay on this computer and go to Gemma.', Fore.GREEN)
    elif word == 'off':
        gemma.set_private(False)
        jarvis.say('Private mode off. Questions go to Claude again.', Fore.GREEN)
    elif not s or word == 'status':
        jarvis.say('Private mode is %s.' % ('on' if gemma.private_mode() else 'off'), Fore.GREEN)
    else:
        _answer(jarvis, s)
