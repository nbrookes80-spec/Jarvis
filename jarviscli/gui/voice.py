# -*- coding: utf-8 -*-
"""Offline speech for the Jarvis window: wake word, speech-to-text, and voice.

Everything runs locally once the models are on disk; nothing is sent to a
cloud service.

  * wake word:      openWakeWord's bundled ``hey_jarvis`` model (ONNX)
  * speech-to-text: faster-whisper (``base.en`` by default)
  * text-to-speech: Piper, falling back to espeak-ng when no voice is installed

Every class here degrades instead of raising when a library or model is
missing; ``voice_status()`` says what is available and why not.
"""
import os
import queue
import re
import shutil
import subprocess
import threading
import time
from collections import deque

try:
    import numpy as np
except ImportError:
    np = None

try:
    import sounddevice as sd
except (ImportError, OSError):
    sd = None

DATA_DIR = os.path.join(
    os.environ.get('XDG_DATA_HOME', os.path.expanduser('~/.local/share')), 'jarvis')
VOICE_DIR = os.path.join(DATA_DIR, 'voices')
WHISPER_DIR = os.path.join(DATA_DIR, 'whisper')

DEFAULT_VOICE = 'en_GB-alan-medium'
DEFAULT_WHISPER = 'base.en'

RATE = 16000            # what both openWakeWord and Whisper expect
BLOCK = 1280            # 80 ms, openWakeWord's native frame


def voice_status():
    """Map of feature -> None if usable, else a human-readable reason."""
    status = {}
    status['audio'] = None if (sd is not None and np is not None) else \
        'sounddevice/numpy not installed (pip install sounddevice numpy)'
    try:
        import faster_whisper  # noqa: F401
        status['stt'] = status['audio']
    except ImportError:
        status['stt'] = 'faster-whisper not installed'
    try:
        import openwakeword  # noqa: F401
        status['wake'] = status['audio']
    except ImportError:
        status['wake'] = 'openwakeword not installed'
    return status


# ------------------------------------------------------------------ speaking

_URL_RE = re.compile(r'https?://\S+')
_SPACE_RE = re.compile(r'[ \t]+')


def speakable(text, limit=420):
    """Reduce plugin output to something worth reading aloud.

    Long tables and lists stay on screen; reading 200 command names aloud
    helps nobody.
    """
    text = _URL_RE.sub('a link', text)
    text = re.sub(r'[*_#`|>~=\-]{2,}', ' ', text)
    text = text.replace('*', ' ').replace('|', ' ')
    lines = [_SPACE_RE.sub(' ', ln).strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    if len(lines) > 6:
        # A list or table: read the opening, point at the screen for the rest.
        return ' '.join(lines[:2]) + '. And %d more lines on screen.' % (len(lines) - 2)
    out = ''
    for ln in lines:
        candidate = (out + ' ' + ln).strip() if out else ln
        if len(candidate) > limit:
            if not out:
                out = ln[:limit].rsplit(' ', 1)[0]
            out += '. The rest is on screen.'
            break
        out = candidate
    return out


class Speaker(object):
    """Queue of utterances played on a background thread; stop() interrupts."""

    def __init__(self, voice=DEFAULT_VOICE, on_state=None):
        self.on_state = on_state            # called with True/False
        self._queue = queue.Queue()
        self._piper = None
        self._piper_error = None
        self._voice_name = voice
        self._proc = None
        self._stop = threading.Event()
        self.speaking = False
        threading.Thread(target=self._run, name='jarvis-tts', daemon=True).start()

    @property
    def engine_name(self):
        if self._piper is not None:
            return 'Piper (%s)' % self._voice_name
        if shutil.which('espeak-ng'):
            return 'espeak-ng'
        return None

    def _load_piper(self):
        path = os.path.join(VOICE_DIR, self._voice_name + '.onnx')
        if not os.path.exists(path):
            self._piper_error = 'voice model missing: %s' % path
            return
        if sd is None or np is None:
            self._piper_error = 'sounddevice/numpy not installed'
            return
        try:
            from piper import PiperVoice
            self._piper = PiperVoice.load(path)
        except Exception as e:      # ImportError, bad model, onnxruntime
            self._piper_error = str(e)

    def say(self, text):
        text = text.strip()
        if text:
            self._queue.put(text)

    def stop(self):
        """Drop anything queued and cut off the current sentence."""
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        self._stop.set()
        if sd is not None:
            try:
                sd.stop()
            except Exception:
                pass
        proc = self._proc
        if proc is not None and proc.poll() is None:
            proc.terminate()

    def _set_state(self, speaking):
        self.speaking = speaking
        if self.on_state is not None:
            self.on_state(speaking)

    def _run(self):
        self._load_piper()
        while True:
            text = self._queue.get()
            self._stop.clear()
            self._set_state(True)
            try:
                if self._piper is not None:
                    self._say_piper(text)
                else:
                    self._say_espeak(text)
            except Exception:
                pass
            finally:
                if self._queue.empty():
                    self._set_state(False)

    def _say_piper(self, text):
        for chunk in self._piper.synthesize(text):
            if self._stop.is_set():
                return
            sd.play(chunk.audio_int16_array, chunk.sample_rate)
            sd.wait()

    def _say_espeak(self, text):
        exe = shutil.which('espeak-ng') or shutil.which('espeak')
        if not exe:
            return
        self._proc = subprocess.Popen(
            [exe, '-v', 'en-gb', '-s', '165', text],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._proc.wait()
        self._proc = None


# ----------------------------------------------------------------- listening

class Listener(object):
    """Owns the microphone. Wake word -> record until silence -> transcribe.

    Callbacks (all from background threads):
      on_state(state)    'idle' | 'wake' | 'recording' | 'transcribing' | 'off'
      on_level(0..1)     input level while recording, for a meter
      on_text(text)      a finished transcription (may be '')
      on_error(message)
    """

    MAX_SECONDS = 12.0
    MIN_SECONDS = 0.6
    END_SILENCE = 0.9       # seconds of quiet that end an utterance
    START_GRACE = 3.0       # how long to wait for speech to begin

    def __init__(self, whisper_model=DEFAULT_WHISPER, wake_threshold=0.5,
                 on_state=None, on_level=None, on_text=None, on_error=None):
        self.whisper_model = whisper_model
        self.wake_threshold = wake_threshold
        self.on_state = on_state
        self.on_level = on_level
        self.on_text = on_text
        self.on_error = on_error

        self.wake_enabled = False
        self.muted = False              # e.g. while Jarvis itself is talking
        self._record_request = threading.Event()
        self._cancel = threading.Event()
        self._whisper = None
        self._whisper_lock = threading.Lock()
        self._wake = None
        self._stream_thread = None
        self._running = False
        self._recent_rms = deque(maxlen=60)     # ~5 s of idle input levels
        self.state = 'off'

    # -------------------------------------------------------------- control

    def start(self):
        if self._running:
            return
        if sd is None or np is None:
            self._error('Microphone unavailable: sounddevice/numpy not installed')
            return
        self._running = True
        self._stream_thread = threading.Thread(
            target=self._loop, name='jarvis-mic', daemon=True)
        self._stream_thread.start()
        threading.Thread(target=self.preload, name='jarvis-stt-load',
                         daemon=True).start()

    def preload(self):
        """Load the Whisper model ahead of the first utterance (~10 s)."""
        try:
            self._get_whisper()
        except Exception as e:
            self._error('Speech recognition unavailable: %s' % e)

    def listen_now(self):
        """Push-to-talk: record the next utterance regardless of wake word."""
        self._cancel.clear()
        self._record_request.set()

    def cancel(self):
        self._cancel.set()

    def stop(self):
        self._running = False
        self._cancel.set()

    # ------------------------------------------------------------ internals

    def _error(self, msg):
        if self.on_error is not None:
            self.on_error(msg)

    def _set_state(self, state):
        if state != self.state:
            self.state = state
            if self.on_state is not None:
                self.on_state(state)

    def _get_whisper(self):
        with self._whisper_lock:
            if self._whisper is None:
                from faster_whisper import WhisperModel
                os.makedirs(WHISPER_DIR, exist_ok=True)
                self._whisper = WhisperModel(
                    self.whisper_model, device='cpu', compute_type='int8',
                    download_root=WHISPER_DIR)
            return self._whisper

    def _get_wake(self):
        if self._wake is None:
            import openwakeword
            from openwakeword.model import Model
            paths = [p for p in openwakeword.get_pretrained_model_paths()
                     if 'hey_jarvis' in os.path.basename(p)]
            if not paths:
                raise RuntimeError('hey_jarvis model not found in openwakeword')
            self._wake = Model(wakeword_model_paths=paths[:1])
        return self._wake

    def _loop(self):
        blocks = queue.Queue()

        def callback(indata, frames, t, status):
            blocks.put(indata[:, 0].copy())

        try:
            stream = sd.InputStream(samplerate=RATE, channels=1, dtype='int16',
                                    blocksize=BLOCK, callback=callback)
            stream.start()
        except Exception as e:
            self._running = False
            self._set_state('off')
            self._error('Could not open the microphone: %s' % e)
            return

        try:
            while self._running:
                self._set_state('wake' if self.wake_enabled else 'idle')
                try:
                    block = blocks.get(timeout=0.2)
                except queue.Empty:
                    block = None

                if block is not None:
                    self._recent_rms.append(_rms(block))
                triggered = self._record_request.is_set()
                if not triggered and block is not None and self.wake_enabled \
                        and not self.muted:
                    triggered = self._check_wake(block)
                if not triggered:
                    continue

                self._record_request.clear()
                self._cancel.clear()
                audio = self._record(blocks)
                if audio is None:
                    continue
                self._set_state('transcribing')
                text = self._transcribe(audio)
                if self.on_text is not None:
                    self.on_text(text)
                self._reset_wake()
                # Drop audio captured while transcribing (often our own echo).
                while not blocks.empty():
                    blocks.get_nowait()
        finally:
            stream.stop()
            stream.close()
            self._set_state('off')

    def _check_wake(self, block):
        try:
            scores = self._get_wake().predict(block)
        except Exception as e:
            self.wake_enabled = False
            self._error('Wake word unavailable: %s' % e)
            return False
        return max(scores.values()) >= self.wake_threshold

    def _reset_wake(self):
        # openWakeWord keeps a rolling buffer; clear it so the tail of the
        # last "hey jarvis" does not fire again immediately.
        if self._wake is not None:
            try:
                self._wake.reset()
            except AttributeError:
                for buf in getattr(self._wake, 'prediction_buffer', {}).values():
                    buf.clear()

    def _record(self, blocks):
        """Collect blocks until the speaker pauses. Returns float32 or None."""
        self._set_state('recording')
        frames = []
        # Room noise comes from the idle period before the trigger, so speech
        # that starts straight after "hey Jarvis" is not mistaken for it.
        noise = float(np.percentile(self._recent_rms, 30)) if self._recent_rms else 200.0
        threshold = max(noise * 2.5, 300.0)
        heard = False
        quiet_for = 0.0
        started = time.time()
        block_s = BLOCK / float(RATE)

        while self._running and not self._cancel.is_set():
            try:
                block = blocks.get(timeout=0.5)
            except queue.Empty:
                continue
            frames.append(block)
            rms = _rms(block)
            if self.on_level is not None:
                self.on_level(min(1.0, rms / 4000.0))
            if rms > threshold:
                heard = True
                quiet_for = 0.0
            else:
                quiet_for += block_s

            elapsed = time.time() - started
            if heard and quiet_for >= self.END_SILENCE:
                break
            if not heard and elapsed >= self.START_GRACE:
                break
            if elapsed >= self.MAX_SECONDS:
                break

        if self.on_level is not None:
            self.on_level(0.0)
        if self._cancel.is_set() or not heard:
            if not self._cancel.is_set() and self.on_text is not None:
                self.on_text('')
            return None
        audio = np.concatenate(frames).astype(np.float32) / 32768.0
        if len(audio) < self.MIN_SECONDS * RATE:
            return None
        return audio

    def _transcribe(self, audio):
        try:
            model = self._get_whisper()
            segments, _ = model.transcribe(
                audio, language='en', beam_size=1, vad_filter=True,
                condition_on_previous_text=False)
            text = ' '.join(s.text for s in segments).strip()
        except Exception as e:
            self._error('Transcription failed: %s' % e)
            return ''
        return strip_wake_phrase(text)


def _rms(block):
    return float(np.sqrt(np.mean(block.astype(np.float32) ** 2)))


_WAKE_RE = re.compile(r'^\s*(hey|hi|ok|okay|a)?[\s,]*(jarvis|jervis|jarvas)\b[\s,.!?]*',
                      re.IGNORECASE)


def strip_wake_phrase(text):
    """'Hey Jarvis, what time is it?' -> 'what time is it?'"""
    return _WAKE_RE.sub('', text, count=1).strip()
