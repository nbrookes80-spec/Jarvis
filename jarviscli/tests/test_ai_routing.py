"""When Claude gets a second opinion on keyword matches, and what follows.

Claude itself is mocked: these tests run offline and cost nothing.
"""
import unittest
from unittest import mock

from Jarvis import Jarvis
from packages import ai_brain


class KeywordRouterTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.jarvis = Jarvis(first_reaction=False)

    def setUp(self):
        patches = [
            mock.patch.object(ai_brain.brain, 'enabled', True),
            mock.patch.object(type(ai_brain.brain), 'available',
                              new_callable=mock.PropertyMock, return_value=True),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def parse(self, text, verdict):
        self.jarvis._raw_line = text
        with mock.patch.object(ai_brain.router, 'confirms', return_value=verdict) as confirms:
            return self.jarvis.parse_input(text), confirms

    def test_mid_sentence_match_rejected_goes_to_ai(self):
        out, confirms = self.parse("I need to open up to my family about something", False)
        self.assertEqual(out, '__ai__')
        request, command, _ = confirms.call_args[0]
        self.assertEqual(command, 'open')
        self.assertEqual(request, "I need to open up to my family about something")

    def test_mid_sentence_match_confirmed_runs(self):
        out, _ = self.parse("can you tell me a joke please", True)
        self.assertTrue(out.startswith('joke'))

    def test_no_answer_from_claude_keeps_the_match(self):
        out, _ = self.parse("can you tell me a joke please", None)
        self.assertTrue(out.startswith('joke'))

    def test_command_first_is_not_checked(self):
        out, confirms = self.parse("joke about chuck norris please", False)
        self.assertTrue(out.startswith('joke'))
        confirms.assert_not_called()

    def test_short_input_is_not_checked(self):
        out, confirms = self.parse("a good joke", False)
        self.assertTrue(out.startswith('joke'))
        confirms.assert_not_called()

    def test_not_checked_when_ai_answers_are_off(self):
        with mock.patch.object(ai_brain.brain, 'enabled', False):
            out, confirms = self.parse("can you tell me a joke please", False)
        self.assertTrue(out.startswith('joke'))
        confirms.assert_not_called()


class RouterAnswerTest(unittest.TestCase):

    def test_reads_yes_and_no(self):
        router = ai_brain.CommandRouter()
        with mock.patch.object(type(router), 'available', new_callable=mock.PropertyMock,
                               return_value=True):
            for reply, expected in (("YES", True), ("No.", False), ("maybe", None)):
                with mock.patch.object(router, 'ask', return_value=reply):
                    self.assertIs(router.confirms("x y z w", "joke", "Tells a joke"), expected)
            with mock.patch.object(router, 'ask', side_effect=RuntimeError("offline")):
                self.assertIsNone(router.confirms("x y z w", "joke", "Tells a joke"))

    def test_router_stays_on_the_cheapest_model(self):
        router = ai_brain.CommandRouter()
        router.set_model('opus')
        self.assertEqual(router.model, 'claude-haiku-4-5')



class FallbackOrderTest(unittest.TestCase):
    """Claude first; the local model when Claude can't answer."""

    @classmethod
    def setUpClass(cls):
        cls.jarvis = Jarvis(first_reaction=False)

    def answer(self, claude, local_available, local_reply="Tokyo."):
        from packages import local_llm
        said = []
        self.jarvis._raw_line = "What is the capital of Japan?"
        with mock.patch.object(ai_brain.brain, 'enabled', True), \
                mock.patch.object(type(ai_brain.brain), 'available',
                                  new_callable=mock.PropertyMock, return_value=True), \
                mock.patch.object(ai_brain.brain, 'ask', **claude), \
                mock.patch.object(local_llm, 'available', return_value=local_available), \
                mock.patch.object(local_llm, 'ask', return_value=local_reply) as local_ask, \
                mock.patch.object(self.jarvis._api, 'say', side_effect=lambda t, *a, **k: said.append(t)):
            self.jarvis.default("what is the capital of japan")
        return said, local_ask

    def test_claude_answers_when_it_can(self):
        said, local_ask = self.answer({'return_value': "Tokyo."}, True)
        self.assertEqual(said, ["Tokyo."])
        local_ask.assert_not_called()

    def test_local_model_answers_when_claude_fails(self):
        said, local_ask = self.answer({'side_effect': RuntimeError("offline")}, True)
        self.assertIn("local model is answering", said[0])
        self.assertEqual(said[-1], "Tokyo.")
        local_ask.assert_called_once()

    def test_claude_problem_reported_when_no_local_model(self):
        said, _ = self.answer({'side_effect': RuntimeError("I could not reach Claude: offline")}, False)
        self.assertEqual(said, ["I could not reach Claude: offline"])


if __name__ == '__main__':
    unittest.main()
