# -*- coding: utf-8 -*-
"""Entry points for `pip install -e .` (see pyproject.toml).

Jarvis's modules import each other as top-level names (`import Jarvis`,
`from plugins.message import ...`), because it has always been run as
`python jarviscli`. These wrappers put jarviscli/ on sys.path first, so the
installed `Jarvis-AI` and `jarvis-gui` commands behave like the launchers
that bootstrap.sh and install-gui.sh write.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _setup():
    if HERE not in sys.path:
        sys.path.insert(0, HERE)


def main():
    """Jarvis in the terminal."""
    _setup()
    import runpy
    runpy.run_path(os.path.join(HERE, '__main__.py'), run_name='__main__')


def gui():
    """The desktop window."""
    _setup()
    from gui.app import main as gui_main
    return gui_main()
