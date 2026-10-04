# -*- coding: utf-8 -*-
"""Entry point: python jarviscli/gui  (the ./jarvis-gui launcher runs this)."""
import os
import sys

# Running a directory puts that directory on sys.path, not its parent; Jarvis
# imports its modules as top-level names from jarviscli/.
HERE = os.path.dirname(os.path.abspath(__file__))
JARVISCLI = os.path.dirname(HERE)
# Drop gui/ itself so its voice.py/app.py can never shadow a plugin's import.
sys.path = [p for p in sys.path if os.path.abspath(p or '.') != HERE]
if JARVISCLI not in sys.path:
    sys.path.insert(0, JARVISCLI)

from gui.app import main  # noqa: E402

if __name__ == '__main__':
    sys.exit(main())
