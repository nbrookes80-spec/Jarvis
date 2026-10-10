# -*- coding: utf-8 -*-
"""Jarvis's conversational fallback: questions no command handles go to Claude.

This is deliberately the *lean* path, separate from the `claude` plugin:

  * default model is Claude Haiku 4.5, Anthropic's cheapest current model
    ($1 / $5 per million input / output tokens)
  * no Claude Code system prompt, no plugins, no MCP connectors, no inherited
    settings; the only tool is web search, for current facts
  * answers are one or two short spoken sentences

Measured: about $0.004-0.007 and 2-3 s per answer, versus ~$0.02 when the
same question goes through the full `claude` agent with its connectors.
Follow-up questions keep context ("and how long to drive there?").

It runs through the Claude Agent SDK, so it uses the same login as Claude
Code (`claude login`); no API key is needed. Configure with environment
variables, or from the desktop window's menu:

  JARVIS_AI_FALLBACK=0           turn the fallback off
  JARVIS_AI_MODEL=sonnet         haiku (default) | sonnet | opus | full model id
                                 | ollama (the free local model, see local_llm)
  JARVIS_AI_BUDGET_USD=1.00      spend cap per session
"""
import asyncio
import os
import shutil
import threading

try:
    from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
    from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False

MODELS = {
    'haiku': 'claude-haiku-4-5',      # cheapest: $1 / $5 per MTok
    'sonnet': 'claude-sonnet-5-5',    # $2 / $10
    'opus': 'claude-opus-5-5',        # $4 / $20
}
DEFAULT_MODEL = 'haiku'
OLLAMA = 'ollama'                     # the local model, free and private; not a Claude model

SYSTEM_PROMPT = (
    "You are Jarvis, a voice assistant on the user's Linux desktop. Your replies "
    "are read aloud, so answer in one to three short, natural sentences, with no "
    "markdown, lists, tables, code blocks or URLs unless the user asks for them. "
    "Use web search when the answer depends on current information. If a request "
    "needs access to the user's files, apps or accounts, say they can ask with "
    "'claude' followed by the request, which has those tools."
)


def resolve_model(name):
    return MODELS.get((name or '').strip().lower(), name or MODELS[DEFAULT_MODEL])


def _ollama_installed():
    from packages import local_llm
    return local_llm.ollama_binary() is not None


class AIBrain(object):
    """One lean conversation with the chosen model: Claude on a background
    asyncio loop, or the local Ollama model."""

    system_prompt = SYSTEM_PROMPT
    tools = ('WebSearch',)
    max_turns = 4

    def __init__(self):
        self.enabled = os.environ.get('JARVIS_AI_FALLBACK', '1') not in ('0', 'false', 'no')
        self.backend = 'claude'
        self.model = MODELS[DEFAULT_MODEL]      # the Claude model, kept while Ollama is chosen
        self.budget = float(os.environ.get('JARVIS_AI_BUDGET_USD', '1.00'))
        self.spend = 0.0
        self.last_error = None
        self._client = None
        self._loop = None
        self._local = None
        self._lock = threading.Lock()
        self.set_model(os.environ.get('JARVIS_AI_MODEL', DEFAULT_MODEL))

    # ----------------------------------------------------------- status

    @property
    def available(self):
        """Claude: SDK importable and a Claude Code CLI to talk to.
        Ollama: the Ollama program is installed."""
        if self.backend == OLLAMA:
            return _ollama_installed()
        return SDK_AVAILABLE and (shutil.which('claude') is not None
                                  or os.path.exists(os.path.expanduser('~/.claude/local/claude')))

    def unavailable_reason(self):
        if self.backend == OLLAMA:
            if not _ollama_installed():
                return 'Ollama is not installed (see scripts/install-local-llm.sh)'
            return None
        if not SDK_AVAILABLE:
            return 'claude-agent-sdk is not installed'
        if not self.available:
            return 'the Claude Code CLI is not installed (see bootstrap.sh)'
        return None

    def describe(self):
        if self.backend == OLLAMA:
            from packages import local_llm
            return 'Ollama (%s, runs on this computer, free)' % local_llm.DEFAULT_MODEL
        name = next((k for k, v in MODELS.items() if v == self.model), self.model)
        return 'Claude %s (%s), $%.4f spent of $%.2f' % (
            name.title(), self.model, self.spend, self.budget)

    # ---------------------------------------------------------- control

    def set_model(self, name):
        """Choose a Claude model (alias or full id) or OLLAMA. Returns the choice."""
        if (name or '').strip().lower() == OLLAMA:
            backend, model = OLLAMA, self.model
        else:
            backend, model = 'claude', resolve_model(name)
        if (backend, model) != (self.backend, self.model):
            self.backend, self.model = backend, model
            self.reset()
        return OLLAMA if backend == OLLAMA else model

    def warm(self):
        """Start the Claude session in the background. The first connection
        takes 10-25 s (it starts the Claude Code CLI); doing it at launch
        keeps that wait off the user's first question. Ollama needs no warm-up."""
        if self.backend != 'claude' or not (self.enabled and self.available):
            return

        def connect():
            try:
                self._get_client()
            except Exception as e:
                self.last_error = str(e)
        threading.Thread(target=connect, name='jarvis-ai-warm', daemon=True).start()

    def reset(self):
        """Forget the conversation; the next question starts fresh."""
        if self._local is not None:
            self._local.reset()
        with self._lock:
            client, self._client = self._client, None
        if client is not None and self._loop is not None:
            try:
                self._submit(client.disconnect(), timeout=10)
            except Exception:
                pass

    # ------------------------------------------------------------- asking

    def ask(self, question, timeout=90):
        """Return Claude's answer as text. Raises RuntimeError with a message
        fit for the user on failure."""
        reason = self.unavailable_reason()
        if reason:
            raise RuntimeError('AI answers are unavailable: %s.' % reason)
        if self.backend == OLLAMA:
            return self._ask_local(question)
        if self.spend >= self.budget:
            raise RuntimeError('The AI spend cap of $%.2f for this session is used up.' % self.budget)

        async def run(client):
            await client.query(question)
            parts, cost = [], None
            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    parts += [b.text for b in message.content if isinstance(b, TextBlock)]
                elif isinstance(message, ResultMessage):
                    cost = getattr(message, 'total_cost_usd', None)
                    if getattr(message, 'is_error', False):
                        raise RuntimeError(getattr(message, 'result', None) or 'Claude returned an error')
            return ' '.join(p.strip() for p in parts if p.strip()), cost

        try:
            text, cost = self._submit(run(self._get_client()), timeout=timeout)
        except Exception as e:
            self.last_error = str(e)
            self.reset()        # a broken session should not poison the next question
            raise RuntimeError('I could not reach Claude: %s' % e)
        if cost:
            self.spend += cost
        return text or "I don't have an answer for that."

    # ---------------------------------------------------------- internals

    def _ask_local(self, question):
        """Answer with the Ollama model. It is free, so there is no spend cap;
        its errors are already fit for the user."""
        from packages import local_llm
        if self._local is None:
            self._local = local_llm.LocalLLM()
        try:
            text = self._local.chat(question, keep_history=True, system=self.system_prompt)
        except local_llm.LocalLLMError as e:
            self.last_error = str(e)
            raise RuntimeError(str(e))
        return text or "I don't have an answer for that."

    def _submit(self, coro, timeout):
        if self._loop is None:
            self._loop = asyncio.new_event_loop()
            threading.Thread(target=self._loop.run_forever, name='jarvis-ai',
                             daemon=True).start()
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout)

    def _options(self):
        kwargs = dict(
            model=self.model,
            system_prompt=self.system_prompt,
            tools=list(self.tools),
            allowed_tools=list(self.tools),
            mcp_servers={},
            strict_mcp_config=True,     # ignore every MCP config on disk
            setting_sources=[],         # and the user's Claude Code settings/plugins
            plugins=[],
            max_turns=self.max_turns,
            max_budget_usd=self.budget,
            cwd=os.path.expanduser('~'),
        )
        # Haiku 4.5 does not take the effort parameter; the others answer
        # short questions well at low effort, which keeps them quick.
        if not self.model.startswith('claude-haiku'):
            kwargs['effort'] = 'low'
        return ClaudeAgentOptions(**kwargs)

    def _get_client(self):
        with self._lock:
            if self._client is None:
                client = ClaudeSDKClient(options=self._options())
                self._submit(client.connect(), timeout=60)
                self._client = client
            return self._client


ROUTER_PROMPT = (
    "You route requests for a voice assistant that has built-in commands. You are "
    "given the user's words and one command that keyword matching picked. Answer "
    "YES if the user wants that command to run, NO if they are asking something "
    "else (a general question, or a different task that merely mentions the word). "
    "Answer with the single word YES or NO."
)


class CommandRouter(AIBrain):
    """Second opinion on keyword matches, so a word mid-sentence cannot hijack a
    question: "how far is the moon from earth" should not run the moon-phase
    command. Always Haiku, no tools, one short answer per call."""

    system_prompt = ROUTER_PROMPT
    tools = ()
    max_turns = 1
    RESET_EVERY = 20        # each check is independent; keep the history short

    def __init__(self):
        super().__init__()
        self.enabled = os.environ.get('JARVIS_AI_ROUTER', '1') not in ('0', 'false', 'no')
        self.model = MODELS['haiku']
        self._calls = 0

    def set_model(self, name):
        return self.model       # the router stays on Claude's cheapest model

    def confirms(self, request, command, description):
        """True/False from Claude, or None when it could not be asked."""
        if not (self.enabled and self.available):
            return None
        self._calls += 1
        if self._calls % self.RESET_EVERY == 0:
            self.reset()
        question = 'User said: "%s"\nCommand: %s - %s\nRun this command?' % (
            request, command, (description or 'no description').strip().split('\n')[0])
        try:
            answer = self.ask(question, timeout=20)
        except RuntimeError:
            return None
        word = answer.strip().upper()
        if word.startswith('YES'):
            return True
        if word.startswith('NO'):
            return False
        return None


brain = AIBrain()
router = CommandRouter()
