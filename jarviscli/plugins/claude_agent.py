"""Claude agent plugin for Jarvis, built on the Claude Agent SDK."""

import asyncio
import os
import re
import threading
from pathlib import Path

from colorama import Fore
from plugin import alias, plugin, require

try:
    from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
    from claude_agent_sdk.types import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock
    try:
        from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny
    except ImportError:
        from claude_agent_sdk.types import PermissionResultAllow, PermissionResultDeny
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False


DEFAULT_MODEL = os.environ.get("JARVIS_CLAUDE_MODEL", "claude-opus-5-5")
DEFAULT_EFFORT = os.environ.get("JARVIS_CLAUDE_EFFORT", "high")
DEFAULT_BUDGET_USD = float(os.environ.get("JARVIS_CLAUDE_BUDGET_USD", "5.00"))
# "project": only connectors in this repo's .mcp.json. "all": also every
# connector on the user's Claude account and Claude Code plugins. Measured on a
# real account with ~60 of them: the first answer took over a minute while
# unreachable ones timed out (30-60 s each), and each turn cost ~10x more.
CONNECTORS = os.environ.get("JARVIS_CLAUDE_CONNECTORS", "project").strip().lower()

MODEL_ALIASES = {
    "opus": "claude-opus-5-5",
    "sonnet": "claude-sonnet-5-5",
    "haiku": "claude-haiku-4-5",
}

# Approved without prompting: these cannot mutate the machine.
READ_ONLY_TOOLS = frozenset({
    "Read", "Glob", "Grep", "WebFetch", "WebSearch", "TodoWrite", "NotebookRead",
})

# Refused outright, never offered for approval. Matched against the bash command.
HARD_DENY_PATTERNS = [
    (r"\brm\s+(-[a-zA-Z]*\s+)*-?[a-zA-Z]*[rf]{2}[a-zA-Z]*\s+/(\s|$)", "recursive delete of /"),
    (r"\bmkfs(\.|\s)", "filesystem format"),
    (r"\bdd\b[^|]*\bof=/dev/", "raw write to a block device"),
    (r">\s*/dev/[sh]d[a-z]", "redirect over a block device"),
    (r"\b(shutdown|reboot|halt|poweroff)\b", "power state change"),
    (r":\(\)\s*\{.*\}\s*;?\s*:", "fork bomb"),
    (r"\bchmod\s+(-[a-zA-Z]+\s+)*777\s+/(\s|$)", "world-writable /"),
    (r"\bcurl\b[^|]*\|\s*(sudo\s+)?(ba)?sh", "piping a download straight into a shell"),
    (r"\bwget\b[^|]*\|\s*(sudo\s+)?(ba)?sh", "piping a download straight into a shell"),
    (r"\bgit\s+push\b.*--force", "force push"),
]


class _LoopThread:
    """A persistent asyncio loop, so one conversation survives across commands.

    Jarvis plugins are synchronous but the SDK is async, and a fresh
    asyncio.run() per command would discard the session after every turn.
    """

    def __init__(self):
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def submit(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()


class _Session:
    def __init__(self):
        self.loop = None
        self.client = None
        self.model = DEFAULT_MODEL
        self.effort = DEFAULT_EFFORT
        self.spend = 0.0
        self.always_allow = set()

    def shutdown(self):
        if self.client is not None:
            try:
                self.loop.submit(self.client.disconnect())
            except Exception:
                pass
        self.client = None


_session = _Session()


def _hard_denied(tool_name, input_data):
    if tool_name != "Bash":
        return None
    command = input_data.get("command", "")
    for pattern, label in HARD_DENY_PATTERNS:
        if re.search(pattern, command):
            return label
    return None


def _describe(tool_name, input_data):
    if tool_name == "Bash":
        return input_data.get("command", "")
    for key in ("file_path", "path", "url", "pattern", "notebook_path"):
        if key in input_data:
            return str(input_data[key])
    return ", ".join(sorted(input_data)) or "(no arguments)"


def _make_permission_handler(jarvis):
    def ask(tool_name, detail):
        jarvis.say("", speak=False)
        jarvis.say("  Claude wants to run: {}".format(tool_name), Fore.YELLOW, speak=False)
        jarvis.say("  {}".format(detail), Fore.YELLOW, speak=False)
        answer = jarvis.input("  allow? [y]es / [n]o / [a]lways this tool: ", Fore.YELLOW)
        return (answer or "").strip().lower()[:1]

    async def handler(tool_name, input_data, context):
        denied_reason = _hard_denied(tool_name, input_data)
        if denied_reason:
            jarvis.say(
                "  Refused {} ({}).".format(tool_name, denied_reason), Fore.RED, speak=False)
            return PermissionResultDeny(
                message="Blocked by Jarvis safety policy: {}.".format(denied_reason),
                interrupt=True,
            )

        if tool_name in READ_ONLY_TOOLS or tool_name in _session.always_allow:
            return PermissionResultAllow(updated_input=input_data)

        detail = _describe(tool_name, input_data)
        # Prompting blocks on stdin, so keep it off the event loop thread.
        choice = await asyncio.get_running_loop().run_in_executor(
            None, ask, tool_name, detail)

        if choice == "a":
            _session.always_allow.add(tool_name)
            return PermissionResultAllow(updated_input=input_data)
        if choice == "y":
            return PermissionResultAllow(updated_input=input_data)
        return PermissionResultDeny(message="The user declined this action.")

    return handler


def _build_options(jarvis, project_dir):
    kwargs = dict(
        model=_session.model,
        cwd=str(project_dir),
        can_use_tool=_make_permission_handler(jarvis),
        max_budget_usd=DEFAULT_BUDGET_USD,
        skills="all",
        system_prompt={
            "type": "preset",
            "preset": "claude_code",
            "append": (
                "You are running as a plugin inside Jarvis, a command-line assistant on "
                "the user's own Linux desktop. Keep answers short and terminal-friendly. "
                "This is the user's personal machine, not a source repository, so do not "
                "assume a codebase is present unless you have checked."
            ),
        },
    )

    # Haiku 4.5 does not support the effort parameter.
    if not _session.model.startswith("claude-haiku"):
        kwargs["effort"] = _session.effort

    mcp_config = project_dir / ".mcp.json"
    if mcp_config.is_file():
        kwargs["mcp_servers"] = str(mcp_config)
    if CONNECTORS != "all":
        kwargs["strict_mcp_config"] = True      # nothing beyond .mcp.json
        kwargs["setting_sources"] = []          # nor connectors from plugins/settings
        kwargs["plugins"] = []

    return ClaudeAgentOptions(**kwargs)


def _ensure_client(jarvis, project_dir):
    if _session.client is not None:
        return _session.client
    if _session.loop is None:
        _session.loop = _LoopThread()

    client = ClaudeSDKClient(options=_build_options(jarvis, project_dir))
    _session.loop.submit(client.connect())
    _session.client = client
    return client


def _render(jarvis, message):
    if isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, TextBlock):
                jarvis.say(block.text, Fore.CYAN, speak=False)
            elif isinstance(block, ToolUseBlock):
                jarvis.say("  [{}]".format(block.name), Fore.BLUE, speak=False)
    elif isinstance(message, ResultMessage):
        cost = getattr(message, "total_cost_usd", None)
        if cost:
            _session.spend += cost
            jarvis.say(
                "  (${:.4f} this turn, ${:.4f} this session)".format(cost, _session.spend),
                Fore.LIGHTBLACK_EX, speak=False)


def _ask(jarvis, client, prompt):
    async def run():
        await client.query(prompt)
        async for message in client.receive_response():
            _render(jarvis, message)

    _session.loop.submit(run())


def _handle_model(jarvis, argument):
    requested = MODEL_ALIASES.get(argument, argument)
    _session.model = requested
    if _session.client is not None:
        _session.loop.submit(_session.client.set_model(requested))
    jarvis.say("Model set to {}.".format(requested), Fore.GREEN)


def _summarise_mcp(status):
    """'3 connected (gmail, drive, ...), 12 need sign-in, 2 failed' instead of raw JSON."""
    servers = status.get("mcpServers", []) if isinstance(status, dict) else []
    if not servers:
        return "none"
    groups = {}
    for server in servers:
        name = server.get("name", "?").split(":")[-1]
        groups.setdefault(server.get("status", "unknown"), []).append(name)
    labels = {"connected": "connected", "needs-auth": "need sign-in", "pending": "starting",
              "failed": "failed"}
    parts = []
    for key in ("connected", "needs-auth", "pending", "failed"):
        names = groups.pop(key, [])
        if names:
            shown = ", ".join(names[:4]) + (", ..." if len(names) > 4 else "")
            parts.append("{} {} ({})".format(len(names), labels[key], shown))
    parts += ["{} {}".format(len(v), k) for k, v in groups.items()]
    return "; ".join(parts)


def _handle_status(jarvis):
    jarvis.say("model:   {}".format(_session.model), Fore.GREEN)
    jarvis.say("effort:  {}".format(_session.effort), Fore.GREEN)
    jarvis.say("budget:  ${:.2f} per session".format(DEFAULT_BUDGET_USD), Fore.GREEN)
    jarvis.say("connectors: {} (JARVIS_CLAUDE_CONNECTORS=project|all)".format(CONNECTORS), Fore.GREEN)
    jarvis.say("spent:   ${:.4f}".format(_session.spend), Fore.GREEN)
    jarvis.say("session: {}".format("live" if _session.client else "not started"), Fore.GREEN)
    if _session.always_allow:
        jarvis.say("auto-allowed: {}".format(", ".join(sorted(_session.always_allow))), Fore.GREEN)
    if _session.client is not None:
        try:
            status = _session.loop.submit(_session.client.get_mcp_status())
            jarvis.say("mcp:     {}".format(_summarise_mcp(status)), Fore.GREEN)
        except Exception as error:
            jarvis.say("mcp:     unavailable ({})".format(error), Fore.YELLOW)


@alias("ai", "ask")
@require(network=True)
@plugin("claude")
def claude(jarvis, s):
    """Chat with Claude, with access to local tools, MCP connectors and skills.

    claude <question>   ask one question
    claude              start an interactive chat (blank line or 'exit' to leave)
    claude model opus   switch model (opus | sonnet | haiku | any full model id)
    claude status       show model, spend and MCP connector status
    claude reset        forget the conversation and start fresh
    """
    if not SDK_AVAILABLE:
        jarvis.say("The claude-agent-sdk package is not installed.", Fore.RED)
        jarvis.say("Install it with: pip install claude-agent-sdk", Fore.YELLOW)
        return

    argument = (s or "").strip()
    project_dir = Path(__file__).resolve().parent.parent.parent

    if argument.startswith("model"):
        rest = argument[len("model"):].strip()
        if not rest:
            jarvis.say("Current model: {}".format(_session.model), Fore.GREEN)
        else:
            _handle_model(jarvis, rest)
        return

    if argument == "status":
        _handle_status(jarvis)
        return

    if argument == "reset":
        _session.shutdown()
        _session.always_allow.clear()
        jarvis.say("Conversation reset.", Fore.GREEN)
        return

    try:
        client = _ensure_client(jarvis, project_dir)
    except Exception as error:
        jarvis.say("Could not start Claude: {}".format(error), Fore.RED)
        jarvis.say(
            "The Claude Code CLI must be installed and authenticated "
            "(run: claude login).", Fore.YELLOW)
        return

    if argument:
        _ask(jarvis, client, argument)
        return

    jarvis.say("Chatting with {}. Blank line or 'exit' to leave.".format(_session.model), Fore.GREEN)
    while True:
        try:
            line = jarvis.input("you> ", Fore.GREEN)
        except (EOFError, KeyboardInterrupt):
            jarvis.say("", speak=False)
            break
        line = (line or "").strip()
        if not line or line.lower() in ("exit", "quit", "bye"):
            break
        _ask(jarvis, client, line)
