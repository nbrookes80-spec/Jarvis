# Claude agent plugin

Adds a `claude` command to Jarvis, backed by the [Claude Agent SDK][sdk]. Claude
can read and write files, run shell commands, use MCP connectors and use Agent
Skills — all on the machine Jarvis is running on.

Upstream Jarvis describes itself as "A Personal **Non-AI** Assistant"; this
plugin is what makes the AI part true. Nothing about the existing 185 plugins
changes.

[sdk]: https://code.claude.com/docs/en/agent-sdk

## Install

```bash
./bootstrap.sh          # see the main README for flags
claude login            # authenticate; a Claude subscription works here
./jarvis
```

`bootstrap.sh` installs the `claude` CLI because the SDK shells out to it. Without
it the plugin reports `CLINotFoundError` and refuses to start.

## Usage

```
claude <question>      ask one question
claude                 interactive chat; blank line or 'exit' to leave
claude model opus      switch model (opus | sonnet | haiku | full model id)
claude status          model, session spend, MCP connector status
claude reset           discard the conversation and start a new one
```

`ai` and `ask` are aliases for `claude`.

The conversation persists across commands for as long as Jarvis is running, so
follow-up questions keep their context. `claude reset` clears it.

## Permissions

An LLM with shell access on your daily driver is a real risk, so the plugin does
not use Claude Code's `bypassPermissions`. It installs a `can_use_tool`
callback that sorts every tool call into one of three buckets:

| Bucket | Tools | Behaviour |
|---|---|---|
| Auto-allowed | `Read`, `Glob`, `Grep`, `WebFetch`, `WebSearch`, `TodoWrite`, `NotebookRead` | runs silently — none of these can mutate the machine |
| Confirmed | `Write`, `Edit`, `Bash`, MCP tools, anything else | shows you the exact command or path, then asks |
| Refused | see below | denied outright and never offered |

Answering `a` at a prompt auto-allows that tool for the rest of the Jarvis
session. `claude reset` clears those grants.

Refused outright, matched against the shell command: recursive deletes of `/`,
`mkfs`, raw writes to block devices, shutdown/reboot, fork bombs, `chmod 777 /`,
piping a download straight into a shell, and `git push --force`.

That list is a backstop, not a sandbox. It stops obvious catastrophes and
careless mistakes; it is not a defence against a determined attempt to work
around it. If you want a real boundary, run Jarvis in a container or a VM.

The patterns live in `HARD_DENY_PATTERNS` in
`jarviscli/plugins/claude_agent.py` — edit them to taste.

## Cost

Defaults to `claude-opus-5-5` at effort `high`, with a **$5.00 per-session
budget** enforced by the SDK's `max_budget_usd`. `claude status` shows spend so
far.

If you authenticated with `claude login` against a Claude subscription, usage
draws on that subscription rather than metered API credits. If you supplied an
`ANTHROPIC_API_KEY` instead, it is metered: Opus 5.5 is $4/$20 per million
input/output tokens, Sonnet 5.5 $2/$10, Haiku 4.5 $1/$5. **A Claude Pro or Max
subscription does not cover Anthropic API usage** — these are separate billing
paths.

Override the defaults with environment variables:

```bash
export JARVIS_CLAUDE_MODEL=claude-sonnet-5-5
export JARVIS_CLAUDE_EFFORT=medium
export JARVIS_CLAUDE_BUDGET_USD=2.00
```

## Connectors (MCP)

```bash
cp .mcp.json.example .mcp.json
# edit the paths, delete the servers you do not want
```

The plugin passes that file to the SDK on the next `claude` command. `stdio`,
`http` and `sse` servers are all supported. Confirm what actually loaded with
`claude status`.

Every connector widens what Claude can reach. Add them deliberately.

## Skills

The plugin runs with `skills="all"`, so Agent Skills available to your `claude`
CLI installation are available here too. Project skills go in `.claude/skills/`;
personal ones in `~/.claude/skills/`.

## Changes to upstream dependencies

`installer/requirements-lean.txt` is a trimmed version of
`installer/requirements.txt`. Two findings drove it:

1. **`playsound` is removed.** Nothing in the repository imports it. On Python
   3.12+ upstream resolves it from `github.com/taconi/playsound`, which no longer
   exists — that dead URL is why `pip install -r installer/requirements.txt`
   fails on Ubuntu 24.04 and Zorin 18. Removing it fixes the install and costs
   nothing. The audio path actually in use is `gtts` + `pyttsx3`.
2. **`Image` is removed.** It pulls Django in transitively — a web framework, for
   a terminal tool. `pillow` is depended on directly instead.

Also dropped, each disabling only its own plugin: `pydoc-markdown` (docs
tooling), `IMDbPY`, `opencv-python-headless`, `python-nmap`, `yeelight`,
`pycricbuzz`, `FlightRadarAPI`, `flake8`, `mock`.

This is safe because `PluginManager` swallows `ImportError` and skips the
affected plugin (`jarviscli/PluginManager.py:21-31`). To restore any of them:
`./env/bin/pip install <name>`.

The lean set was verified to resolve on Python 3.10, 3.12 and 3.13. Run
`./bootstrap.sh --full` to use the upstream file instead.

## Continuous integration

`.github/workflows/ci.yml` runs on pushes and pull requests. The repo previously
had no working CI at all — `.travis.yml` points at travis-ci.org, which has been
shut down for years.

Gated:

- `installer/requirements-lean.txt` resolves on Python 3.10, 3.11, 3.12 and 3.13
  (`pip install --dry-run`, so a requirement pinned to a URL that stops existing
  fails in seconds — the exact failure mode that broke Python 3.12+)
- `pkg_resources` still imports, i.e. the `setuptools<82` pin is holding
- `claude_agent_sdk` imports
- `./bootstrap.sh --yes --no-cli` completes, and `claude`, `ai` and `ask` all
  register afterwards
- lint on `jarviscli/plugins/claude_agent.py`, `bash -n bootstrap.sh`, JSON
  validity of `.mcp.json.example`

Deliberately **not** gated, because both already fail on `master` and would make
CI permanently red without telling you anything:

- the full unittest suite — 294 tests, 6 failures and 37 errors, mostly
  third-party APIs that no longer respond
- repo-wide lint — roughly 1,968 findings under the project's own settings in
  `test.sh`

Both are worth fixing. Neither is this workflow's job.

## Troubleshooting

**`The claude-agent-sdk package is not installed`** — `./env/bin/pip install
claude-agent-sdk`.

**`Could not start Claude` / `CLINotFoundError`** — the `claude` CLI is missing or
unauthenticated. `npm install -g @anthropic-ai/claude-code` then `claude login`.

**The `claude` command does not appear in Jarvis** — a plugin whose import fails
is skipped silently apart from a printed message. Check with:

```bash
./env/bin/python -c 'import claude_agent_sdk'
```

**Venv creation fails on Zorin/Ubuntu** — `sudo apt install python3-venv`. It is
not installed by default and is the most common cause.
