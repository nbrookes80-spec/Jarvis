"""Headless tests for the desktop window's backend (jarviscli/gui).

No GTK, microphone or speech models needed: the engine is driven directly and
only the pure helpers of the voice module are exercised.
"""
import threading
import time
import unittest

from gui import voice
from gui.engine import JarvisEngine, strip_ansi
from packages.ai_brain import brain, resolve_model


class VoiceHelpersTest(unittest.TestCase):

    def test_wake_phrase_removed(self):
        self.assertEqual(voice.strip_wake_phrase('Hey Jarvis, what time is it?'),
                         'what time is it?')
        self.assertEqual(voice.strip_wake_phrase('Jarvis. Tell me a joke'),
                         'Tell me a joke')

    def test_text_without_wake_phrase_unchanged(self):
        self.assertEqual(voice.strip_wake_phrase('weather in London'),
                         'weather in London')

    def test_long_lists_are_summarised(self):
        text = 'Commands\nFormat: name\n' + '* command\n' * 50
        said = voice.speakable(text)
        self.assertTrue(said.startswith('Commands Format: name'))
        self.assertIn('50 more lines on screen', said)

    def test_links_and_markup_not_read_out(self):
        said = voice.speakable('See https://example.com/a?b=1 for **details**')
        self.assertEqual(said, 'See a link for details')

    def test_ansi_stripped(self):
        self.assertEqual(strip_ansi('\x1b[35mhello\x1b[39m'), 'hello')


class AIModelTest(unittest.TestCase):

    def test_cheapest_model_is_default_alias(self):
        self.assertEqual(resolve_model('haiku'), 'claude-haiku-4-5')
        self.assertEqual(resolve_model('Sonnet'), 'claude-sonnet-5-5')
        self.assertEqual(resolve_model('opus'), 'claude-opus-5-5')
        self.assertEqual(resolve_model('claude-opus-5'), 'claude-opus-5')


class EngineTest(unittest.TestCase):
    """Loads the real plugin set once (~10-20 s), then runs commands."""

    @classmethod
    def setUpClass(cls):
        # Deterministic and offline: no Claude calls from the test suite.
        cls._ai_was = brain.enabled
        brain.enabled = False
        cls.output = []
        cls.prompts = []
        cls.busy = []
        cls.ready = threading.Event()
        cls.error = []
        cls.engine = JarvisEngine(
            on_output=cls.output.append, on_prompt=cls.prompts.append,
            on_busy=cls.busy.append, on_ready=lambda n: cls.ready.set(),
            on_error=lambda tb: (cls.error.append(tb), cls.ready.set()))
        cls.engine.start()
        cls.ready.wait(240)

    @classmethod
    def tearDownClass(cls):
        cls.engine.stop()
        brain.enabled = cls._ai_was

    def setUp(self):
        self.assertFalse(self.error, self.error and self.error[0])
        self.assertGreater(self.engine.plugin_count, 100)
        del self.output[:]
        del self.prompts[:]

    def run_command(self, command, answers=(), timeout=30):
        del self.output[:]
        start = len(self.busy)
        answers = list(answers)
        self.engine.submit(command)
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.engine.waiting_for_input:
                self.engine.reply(answers.pop(0) if answers else '')
            if len(self.busy) >= start + 2 and self.busy[-1] is False:
                return ''.join(self.output)
            time.sleep(0.02)
        self.fail('command %r did not finish' % command)

    def test_output_captured_without_colour_codes(self):
        self.assertEqual(self.run_command('binary 10').strip(), '1010')

    def test_unknown_command(self):
        self.assertIn('could not identify', self.run_command('qwertyuiop'))

    def test_addressing_jarvis_by_name(self):
        self.assertEqual(self.run_command('Hey Jarvis, binary 10').strip(), '1010')
        self.assertEqual(self.run_command('Jarvis binary 10').strip(), '1010')

    def test_world_time_phrasing_routed(self):
        line = self.engine.jarvis.precmd('What time is it in Tokyo?')
        self.assertEqual(line, 'check time in tokyo')

    def test_questions_for_claude_keep_their_wording(self):
        line = self.engine.jarvis.precmd('claude Who wrote "Hamlet", and when?')
        self.assertEqual(line, 'claude Who wrote "Hamlet", and when?')
        # A word inside the question must not pick another command ("weather").
        line = self.engine.jarvis.precmd('local What is the weather and climate of Sydney?')
        self.assertEqual(line, 'local What is the weather and climate of Sydney?')

    def test_plugin_question_routed_back(self):
        # bmi asks for a unit system, then height and weight.
        out = self.run_command('bmi', answers=['1', '180', '75'])
        self.assertTrue(self.prompts, 'plugin never asked a question')
        self.assertIn('BMI', out)

    def test_print_from_other_thread_not_captured(self):
        before = len(self.output)
        t = threading.Thread(target=print, args=('not jarvis output',))
        t.start()
        t.join()
        self.assertEqual(len(self.output), before)


if __name__ == '__main__':
    unittest.main()
