"""Ollama as a selectable answer model, next to the Claude models.

Ollama is mocked: these tests run offline, need no model download and cost
nothing.
"""
import os
import unittest
from unittest import mock

from packages import ai_brain, local_llm
from packages.ai_brain import AIBrain, CommandRouter, OLLAMA


class OllamaBackendTest(unittest.TestCase):

    def setUp(self):
        self.brain = AIBrain()
        self.brain.set_model('haiku')
        installed = mock.patch.object(ai_brain, '_ollama_installed', return_value=True)
        installed.start()
        self.addCleanup(installed.stop)

    def test_selecting_ollama_switches_backend(self):
        self.assertEqual(self.brain.set_model('ollama'), OLLAMA)
        self.assertEqual(self.brain.backend, OLLAMA)

    def test_switching_back_to_claude_restores_the_claude_model(self):
        self.brain.set_model('ollama')
        self.assertEqual(self.brain.set_model('sonnet'), 'claude-sonnet-5-5')
        self.assertEqual(self.brain.backend, 'claude')
        self.assertEqual(self.brain.model, 'claude-sonnet-5-5')

    def test_answers_come_from_the_local_model(self):
        self.brain.set_model('ollama')
        with mock.patch.object(local_llm.LocalLLM, 'chat', return_value='Paris.') as chat:
            self.assertEqual(self.brain.ask('capital of France?'), 'Paris.')
        self.assertEqual(chat.call_args[0][0], 'capital of France?')
        self.assertTrue(chat.call_args[1]['keep_history'])
        self.assertEqual(chat.call_args[1]['system'], ai_brain.SYSTEM_PROMPT)

    def test_conversation_context_is_kept_then_cleared_on_switch(self):
        self.brain.set_model('ollama')
        with mock.patch.object(local_llm.LocalLLM, 'chat', return_value='ok'), \
                mock.patch.object(local_llm.LocalLLM, 'reset') as reset:
            self.brain.ask('first')
            self.brain.set_model('haiku')
        reset.assert_called()

    def test_local_errors_become_runtime_errors_for_the_fallback(self):
        self.brain.set_model('ollama')
        err = local_llm.LocalLLMError('The model qwen3:8b isn\'t downloaded yet.')
        with mock.patch.object(local_llm.LocalLLM, 'chat', side_effect=err):
            with self.assertRaises(RuntimeError) as ctx:
                self.brain.ask('hello')
        self.assertIn('isn\'t downloaded', str(ctx.exception))

    def test_no_spend_cap_for_the_free_model(self):
        self.brain.set_model('ollama')
        self.brain.spend, self.brain.budget = 99.0, 1.0
        with mock.patch.object(local_llm.LocalLLM, 'chat', return_value='fine'):
            self.assertEqual(self.brain.ask('hi'), 'fine')

    def test_warm_up_does_not_start_claude(self):
        self.brain.set_model('ollama')
        with mock.patch.object(ai_brain.threading, 'Thread') as thread:
            self.brain.warm()
        thread.assert_not_called()

    def test_missing_ollama_is_reported(self):
        self.brain.set_model('ollama')
        with mock.patch.object(ai_brain, '_ollama_installed', return_value=False):
            self.assertFalse(self.brain.available)
            self.assertIn('Ollama is not installed', self.brain.unavailable_reason())
            with self.assertRaises(RuntimeError):
                self.brain.ask('hi')

    def test_describe_names_the_local_model(self):
        self.brain.set_model('ollama')
        self.assertIn(local_llm.DEFAULT_MODEL, self.brain.describe())
        self.assertIn('free', self.brain.describe())


class RemoteServerTest(unittest.TestCase):

    def test_remote_server_down_is_reported_not_started_locally(self):
        with mock.patch.object(local_llm, 'OLLAMA_URL', 'http://10.0.0.5:11434'), \
                mock.patch.object(local_llm, 'server_up', return_value=False), \
                mock.patch.object(local_llm.subprocess, 'Popen') as popen:
            with self.assertRaises(local_llm.LocalLLMError) as ctx:
                local_llm.ensure_server(wait=0)
        popen.assert_not_called()
        self.assertIn('10.0.0.5', str(ctx.exception))


class EnvironmentChoiceTest(unittest.TestCase):

    def test_terminal_users_can_pick_ollama_by_environment(self):
        with mock.patch.dict(os.environ, {'JARVIS_AI_MODEL': 'ollama'}):
            self.assertEqual(AIBrain().backend, OLLAMA)

    def test_router_stays_on_claude_even_when_ollama_is_chosen(self):
        with mock.patch.dict(os.environ, {'JARVIS_AI_MODEL': 'ollama'}):
            router = CommandRouter()
        self.assertEqual(router.backend, 'claude')
        self.assertEqual(router.model, ai_brain.MODELS['haiku'])
        router.set_model('ollama')
        self.assertEqual(router.backend, 'claude')


if __name__ == '__main__':
    unittest.main()
