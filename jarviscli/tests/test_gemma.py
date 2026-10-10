"""Local Gemma 4: the client, private mode, and where Gemma sits in the answer order.

The server is mocked: these tests run offline.
"""
import unittest
from unittest import mock

import requests

from Jarvis import Jarvis
from packages import ai_brain, gemma


def fake_response(text="Hello."):
    r = mock.Mock()
    r.json.return_value = {'choices': [{'message': {'content': text}}]}
    r.raise_for_status.return_value = None
    return r


class GemmaClientTest(unittest.TestCase):

    def test_chat_keeps_history_and_trims_it(self):
        g = gemma.Gemma()
        with mock.patch.object(gemma.requests, 'post', return_value=fake_response("Hi.")) as post:
            for i in range(gemma.MAX_TURNS + 3):
                self.assertEqual(g.chat('q%d' % i), 'Hi.')
        self.assertEqual(len(g.history), 2 * gemma.MAX_TURNS)
        sent = post.call_args[1]['json']
        self.assertEqual(sent['messages'][0]['role'], 'system')
        self.assertEqual(sent['model'], gemma.MODEL)
        self.assertFalse(sent['stream'])

    def test_no_history_when_asked(self):
        g = gemma.Gemma()
        with mock.patch.object(gemma.requests, 'post', return_value=fake_response()):
            g.chat('one-off', keep_history=False)
        self.assertEqual(g.history, [])

    def test_errors_become_gemma_errors(self):
        g = gemma.Gemma()
        for exc, text in ((requests.ConnectionError(), 'not running'),
                          (requests.Timeout(), 'too long')):
            with mock.patch.object(gemma.requests, 'post', side_effect=exc):
                with self.assertRaises(gemma.GemmaError) as ctx:
                    g.chat('hello')
            self.assertIn(text, str(ctx.exception))

    def test_available_needs_the_model_listed(self):
        ok = mock.Mock(**{'json.return_value': {'data': [{'id': gemma.MODEL}]}})
        other = mock.Mock(**{'json.return_value': {'data': [{'id': 'something-else'}]}})
        with mock.patch.object(gemma.requests, 'get', return_value=ok):
            self.assertTrue(gemma.available())
        with mock.patch.object(gemma.requests, 'get', return_value=other):
            self.assertFalse(gemma.available())
        with mock.patch.object(gemma.requests, 'get', side_effect=requests.ConnectionError()):
            self.assertFalse(gemma.available())

    def test_private_mode_toggles(self):
        before = gemma.private_mode()
        try:
            gemma.set_private(True)
            self.assertTrue(gemma.private_mode())
            gemma.set_private(False)
            self.assertFalse(gemma.private_mode())
        finally:
            gemma.set_private(before)


class AnswerOrderTest(unittest.TestCase):
    """Claude, then Gemma, then Ollama. Private mode never touches Claude."""

    @classmethod
    def setUpClass(cls):
        cls.jarvis = Jarvis(first_reaction=False)

    def run_default(self, claude=None, private=False, gemma_up=True):
        said = []
        self.jarvis._raw_line = "What is the capital of Japan?"
        claude = claude or {'return_value': 'Tokyo (Claude).'}
        from packages import local_llm
        with mock.patch.object(ai_brain.brain, 'enabled', True), \
                mock.patch.object(type(ai_brain.brain), 'available',
                                  new_callable=mock.PropertyMock, return_value=True), \
                mock.patch.object(ai_brain.brain, 'ask', **claude) as claude_ask, \
                mock.patch.object(gemma, 'private_mode', return_value=private), \
                mock.patch.object(gemma, 'available', return_value=gemma_up), \
                mock.patch.object(gemma, 'ask', return_value='Tokyo (Gemma).') as gemma_ask, \
                mock.patch.object(local_llm, 'available', return_value=False), \
                mock.patch.object(self.jarvis._api, 'say',
                                  side_effect=lambda t, *a, **k: said.append(t)):
            self.jarvis.default("what is the capital of japan")
        return said, claude_ask, gemma_ask

    def test_claude_first_when_not_private(self):
        said, claude_ask, gemma_ask = self.run_default()
        self.assertEqual(said, ['Tokyo (Claude).'])
        gemma_ask.assert_not_called()

    def test_gemma_answers_when_claude_is_offline(self):
        said, _, gemma_ask = self.run_default(claude={'side_effect': RuntimeError('offline')})
        self.assertIn('Gemma', said[0])
        self.assertEqual(said[-1], 'Tokyo (Gemma).')
        gemma_ask.assert_called_once()

    def test_private_mode_never_asks_claude(self):
        said, claude_ask, gemma_ask = self.run_default(private=True)
        claude_ask.assert_not_called()
        self.assertEqual(said[-1], 'Tokyo (Gemma).')

    def test_private_mode_without_gemma_does_not_fall_back_to_claude(self):
        said, claude_ask, _ = self.run_default(private=True, gemma_up=False)
        claude_ask.assert_not_called()
        self.assertIn('private', said[0].lower())

    def test_router_is_skipped_in_private_mode(self):
        self.jarvis._raw_line = "can you tell me a joke please"
        with mock.patch.object(ai_brain.brain, 'enabled', True), \
                mock.patch.object(type(ai_brain.brain), 'available',
                                  new_callable=mock.PropertyMock, return_value=True), \
                mock.patch.object(gemma, 'private_mode', return_value=True), \
                mock.patch.object(ai_brain.router, 'confirms') as confirms:
            out = self.jarvis.parse_input("can you tell me a joke please")
        confirms.assert_not_called()
        self.assertTrue(out.startswith('joke'))


if __name__ == '__main__':
    unittest.main()
