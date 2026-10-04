#!/usr/bin/env bash
#
# Install a free, open-source AI model that runs locally (no account, no API
# key, no per-use cost), for Jarvis's `local`, `research` and `draft` commands.
#
#   ./scripts/install-local-llm.sh                 Ollama + qwen3:8b (~2.2 GB + ~5 GB)
#   ./scripts/install-local-llm.sh qwen3:4b        a smaller, faster model instead
#
# Installs Ollama into ~/.local/ollama, so no sudo is needed. Safe to re-run.
#
set -euo pipefail

MODEL="${1:-qwen3:8b}"
DEST="$HOME/.local/ollama"
BIN="$DEST/bin/ollama"
URL="http://127.0.0.1:11434"

ok()   { printf '\033[32m  = %s\033[0m\n' "$*"; }
info() { printf '  %s\n' "$*"; }

if command -v ollama >/dev/null 2>&1; then
  BIN="$(command -v ollama)"
  ok "Ollama already installed: $BIN"
elif [ -x "$BIN" ]; then
  ok "Ollama already installed: $BIN"
else
  command -v zstd >/dev/null || { echo "Needs zstd: sudo apt-get install -y zstd" >&2; exit 1; }
  TAG="$(curl -sSfL https://api.github.com/repos/ollama/ollama/releases/latest \
          | python3 -c 'import json,sys; print(json.load(sys.stdin)["tag_name"])')"
  info "Downloading Ollama $TAG (~1.4 GB) into $DEST"
  mkdir -p "$DEST"
  curl -sSfL "https://github.com/ollama/ollama/releases/download/$TAG/ollama-linux-amd64.tar.zst" \
    | tar --zstd -x -C "$DEST"
  ok "installed $BIN"
fi

if ! curl -s -m 2 "$URL/api/version" >/dev/null; then
  mkdir -p "$HOME/.local/share"
  setsid nohup "$BIN" serve >> "$HOME/.local/share/jarvis-ollama.log" 2>&1 < /dev/null &
  for _ in $(seq 30); do curl -s -m 1 "$URL/api/version" >/dev/null && break; sleep 0.5; done
fi
ok "Ollama server running at $URL"

info "Downloading $MODEL (Qwen3 8B is ~5 GB)"
"$BIN" pull "$MODEL"
ok "$MODEL ready"

echo
info "In Jarvis try:"
info "  local what is the difference between weather and climate?"
info "  research the history of the Sydney Opera House"
info "  draft a one-page cover letter for a library assistant job"
[ "$MODEL" = "qwen3:8b" ] || info "and set JARVIS_LOCAL_MODEL=$MODEL so Jarvis uses it by default."
