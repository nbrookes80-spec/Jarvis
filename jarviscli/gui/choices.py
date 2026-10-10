# -*- coding: utf-8 -*-
"""Buttons for the answers a plugin is waiting for.

Plugins ask with input(), so the reply is free text. For the common shapes the
window offers buttons instead, and a click sends the same reply as typing it:

  * yes/no questions ("Save the file? [y/n]")       -> Yes, No
  * a numbered menu printed just before the prompt    -> one button per item
  * a range in the prompt ("Pick a column (1-7)")     -> the numbers

Anything else gets no buttons and is typed as before. Pure functions, so the
rules can be tested without GTK.
"""
import re

MAX_BUTTONS = 9
LABEL_CHARS = 40

YES_NO = re.compile(r'\b[yY]\s*/\s*[nN]\b|\byes\s+or\s+no\b|\byes/no\b', re.IGNORECASE)
RANGE = re.compile(r'\((\d+)\s*-\s*(\d+)\)')
NUMBERED = re.compile(r'^\s*[\[(]?(\d{1,2})[\])\.:]\s+(\S.*?)\s*$')


def options_for(prompt, recent_lines=()):
    """[(label, reply)] for the buttons under this prompt, or [] for free text.

    recent_lines are the output lines just before the prompt, oldest first.
    """
    if YES_NO.search(prompt or ''):
        return [('Yes', 'y'), ('No', 'n')]
    menu = _numbered_menu(recent_lines)
    if menu:
        return menu
    match = RANGE.search(prompt or '')
    if match:
        low, high = int(match.group(1)), int(match.group(2))
        if 0 < low < high and high - low + 1 <= MAX_BUTTONS:
            return [(str(n), str(n)) for n in range(low, high + 1)]
    return []


def _numbered_menu(lines):
    """The numbered items that end the output, if they run 1..n with 2 <= n <= 9.
    Blank lines between items are allowed; anything else ends the menu."""
    items = []
    for line in reversed(list(lines)):
        match = NUMBERED.match(line)
        if match:
            items.append((int(match.group(1)), match.group(2)))
        elif line.strip():
            break
    items.reverse()
    numbers = [n for n, _ in items]
    if not (2 <= len(items) <= MAX_BUTTONS) or numbers != list(range(1, len(items) + 1)):
        return []
    return [(_shorten(text), str(n)) for n, text in items]


def _shorten(text):
    if len(text) <= LABEL_CHARS:
        return text
    return text[:LABEL_CHARS - 1].rstrip() + '…'
