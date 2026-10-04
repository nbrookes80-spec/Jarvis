# -*- coding: utf-8 -*-
"""Run the Jarvis command interpreter behind a non-terminal frontend.

Jarvis was written for a terminal: plugins talk through print(), JarvisAPI.say()
and sys.stdin.readline(), and a few call sys.exit(). This module puts all of
that on one worker thread and turns it into callbacks:

  * everything written to stdout becomes ``on_output(text)`` chunks, with ANSI
    colour codes stripped
  * a plugin reading stdin blocks until the frontend calls ``reply(text)``;
    ``on_prompt(prompt)`` tells the frontend that it is waiting
  * ``on_busy(bool)`` brackets each command, ``on_ready(count)`` fires once
    the plugins have loaded

It imports nothing from GTK, so it can be driven and tested headless.
"""
import io
import os
import queue
import re
import signal
import sys
import threading
import traceback

ANSI_RE = re.compile(r'(\x9B|\x1B\[)[0-?]*[ -/]*[@-~]')

# Commands that end the terminal session. In a window they would sys.exit()
# the worker thread and leave a dead UI, so the frontend handles them itself.
EXIT_WORDS = {'exit', 'quit', 'goodbye', 'bye'}


def strip_ansi(text):
    return ANSI_RE.sub('', text)


class _StdinBridge(io.TextIOBase):
    """sys.stdin replacement: readline() blocks until the frontend replies."""

    def __init__(self, engine):
        self._engine = engine
        self._queue = queue.Queue()

    def readable(self):
        return True

    def readline(self, size=-1):
        return self._engine._wait_for_reply(self._queue) + '\n'

    def read(self, size=-1):
        return self.readline()

    def isatty(self):
        return False


class _StdoutBridge(io.TextIOBase):
    """sys.stdout replacement: forwards worker-thread writes to the engine.

    While a command runs, writes from any thread except the UI thread are
    Jarvis's output: some plugins print from their own threads (the claude
    plugin answers from an asyncio loop thread). Otherwise, and always for the
    UI thread, writes go to the real stream, so stray prints from the window
    never show up as Jarvis's reply.
    """

    def __init__(self, engine, real):
        self._engine = engine
        self._real = real

    def writable(self):
        return True

    def isatty(self):
        return False

    @property
    def encoding(self):
        return 'utf-8'

    def write(self, text):
        current = threading.current_thread()
        engine = self._engine
        if current is engine._thread or (
                engine._busy and current is not engine._ui_thread):
            engine._emit(text)
        elif self._real is not None:
            self._real.write(text)
        return len(text)

    def flush(self):
        if self._real is not None:
            self._real.flush()

    def fileno(self):
        # Some plugins hand sys.stdout to subprocess; give them the real fd.
        if self._real is None:
            raise io.UnsupportedOperation('fileno')
        return self._real.fileno()


class _SpeechAdapter(object):
    """Stands in for Jarvis's own speech engine.

    The frontend owns text-to-speech. Plugins that speak directly (for example
    voice_control's prompts) still reach the user, through on_speak.
    """

    rate = 180

    def __init__(self, engine):
        self._engine = engine

    def text_to_speech(self, text):
        cb = self._engine.on_speak
        if cb is not None:
            cb(strip_ansi(text))

    def change_rate(self, delta):
        self.rate += delta

    def destroy(self):
        pass


class JarvisEngine(object):

    def __init__(self, on_output=None, on_prompt=None, on_busy=None,
                 on_ready=None, on_error=None, on_speak=None):
        self.on_output = on_output
        self.on_prompt = on_prompt
        self.on_busy = on_busy
        self.on_ready = on_ready
        self.on_error = on_error
        self.on_speak = on_speak

        self.jarvis = None
        self.plugin_count = 0
        self._commands = queue.Queue()
        self._thread = None
        self._waiting = None        # the stdin queue a plugin is blocked on
        self._pending = ''          # partial line not yet ending in newline
        self._loading = True        # plugin-load noise is not a reply
        self._busy = False
        self._ui_thread = None
        self._lock = threading.Lock()
        self._stdin = _StdinBridge(self)

    # ------------------------------------------------------------ public API

    def start(self):
        self._thread = threading.Thread(
            target=self._run, name='jarvis-engine', daemon=True)
        self._ui_thread = threading.current_thread()
        self._saved_streams = (sys.stdout, sys.stdin)
        sys.stdout = _StdoutBridge(self, sys.stdout)
        sys.stdin = self._stdin
        self._thread.start()

    @property
    def waiting_for_input(self):
        return self._waiting is not None

    def submit(self, text):
        """Route user text: answer a waiting plugin, or run a new command."""
        text = text.strip()
        with self._lock:
            waiting = self._waiting
        if waiting is not None:
            waiting.put(text)
        elif text:
            self._commands.put(text)

    def reply(self, text):
        self.submit(text)

    def cancel_input(self):
        """Unblock a plugin waiting on stdin, as if the user pressed Enter."""
        with self._lock:
            waiting = self._waiting
        if waiting is not None:
            waiting.put('')

    def command_names(self):
        if self.jarvis is None:
            return []
        return sorted(self.jarvis._plugin_manager.get_plugins().keys())

    # ------------------------------------------------------ worker internals

    def _call(self, cb, *args):
        if cb is not None:
            try:
                cb(*args)
            except Exception:
                traceback.print_exc(file=sys.__stderr__)

    def _emit(self, text):
        if self._loading:
            # Tracebacks from plugins that fail to import: keep them visible
            # in the terminal/journal, out of the conversation.
            sys.__stderr__.write(text)
            return
        text = strip_ansi(text)
        if not text:
            return
        # Buffer to whole lines so a prompt written as "Name? " followed by a
        # readline() can be told apart from ordinary output.
        self._pending += text
        if '\n' in self._pending:
            head, _, tail = self._pending.rpartition('\n')
            self._pending = tail
            self._call(self.on_output, head + '\n')

    def _flush_pending(self):
        pending, self._pending = self._pending, ''
        return pending

    def _wait_for_reply(self, q):
        prompt = self._flush_pending()
        with self._lock:
            self._waiting = q
        self._call(self.on_prompt, prompt.strip())
        try:
            return q.get()
        finally:
            with self._lock:
                self._waiting = None

    def _load(self):
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if here not in sys.path:
            sys.path.insert(0, here)

        # CmdInterpreter treats sys.argv as a one-shot command and installs a
        # SIGINT handler, which only the main thread may do. Neutralise both
        # for the duration of construction.
        saved_argv, saved_signal = sys.argv, signal.signal
        sys.argv = [saved_argv[0]]
        signal.signal = lambda *a, **k: None
        try:
            import Jarvis
            jarvis = Jarvis.Jarvis(first_reaction=False)
        finally:
            sys.argv, signal.signal = saved_argv, saved_signal

        # The frontend speaks; keep Jarvis's own engine (and its postcmd
        # "What can I do for you?") silent so nothing is said twice.
        jarvis.enable_voice = False
        jarvis.speech = _SpeechAdapter(self)
        return jarvis

    def _run(self):
        try:
            self.jarvis = self._load()
            self.plugin_count = self.jarvis._plugin_manager.get_number_plugins_loaded()
        except BaseException:
            self._call(self.on_error, traceback.format_exc())
            return
        self._loading = False
        self._call(self.on_ready, self.plugin_count)
        from packages.ai_brain import brain, router
        brain.warm()
        router.warm()

        while True:
            command = self._commands.get()
            if command is None:
                break
            self._busy = True
            self._call(self.on_busy, True)
            try:
                self.jarvis.get_api().eval(command)
            except SystemExit:
                pass
            except BaseException:
                self._emit(traceback.format_exc())
            finally:
                tail = self._flush_pending()
                if tail.strip():
                    self._call(self.on_output, tail + '\n')
                self._busy = False
                self._call(self.on_busy, False)

    def stop(self):
        self._commands.put(None)
        self.cancel_input()
        saved = getattr(self, '_saved_streams', None)
        if saved is not None:
            sys.stdout, sys.stdin = saved
            self._saved_streams = None
