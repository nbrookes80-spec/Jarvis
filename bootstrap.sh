#!/usr/bin/env bash
#
# Install Jarvis plus the Claude agent plugin on a Debian/Ubuntu-family system
# (tested target: Zorin OS, which is Ubuntu-based).
#
# Safe to re-run: every step checks before it acts.
#
#   ./bootstrap.sh              # interactive, lean dependency set
#   ./bootstrap.sh --yes        # no prompts
#   ./bootstrap.sh --full       # upstream installer/requirements.txt instead
#   ./bootstrap.sh --no-apt     # skip system packages
#   ./bootstrap.sh --no-cli     # skip the Claude Code CLI
#   ./bootstrap.sh --autostart  # also open Jarvis in a terminal on login
#
set -euo pipefail

cd "$(dirname "$0")"
ROOT="$(pwd)"
VENV="$ROOT/env"

ASSUME_YES=0
USE_FULL=0
DO_APT=1
DO_CLI=1
DO_AUTOSTART=0

for arg in "$@"; do
  case "$arg" in
    --yes|-y) ASSUME_YES=1 ;;
    --full) USE_FULL=1 ;;
    --no-apt) DO_APT=0 ;;
    --no-cli) DO_CLI=0 ;;
    --autostart) DO_AUTOSTART=1 ;;
    # Prints the header block, however long it grows, and stops at the code.
    -h|--help) awk 'NR>1 && /^#/ {sub(/^# ?/, ""); print; next} NR>1 {exit}' "$0"; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
info() { printf '  %s\n' "$*"; }
warn() { printf '\033[33m  ! %s\033[0m\n' "$*"; }
err()  { printf '\033[31m  x %s\033[0m\n' "$*" >&2; }
ok()   { printf '\033[32m  = %s\033[0m\n' "$*"; }

confirm() {
  [ "$ASSUME_YES" -eq 1 ] && return 0
  read -r -p "  $1 [y/N] " reply
  [[ "$reply" =~ ^[Yy] ]]
}

# ---------------------------------------------------------------- 1. interpreter

bold "1. Checking Python"

if ! command -v python3 >/dev/null 2>&1; then
  err "python3 not found. Install it first: sudo apt install python3"
  exit 1
fi

PY_MM="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
PY_OK="$(python3 -c 'import sys; print(1 if sys.version_info[:2] >= (3, 10) else 0)')"
if [ "$PY_OK" -ne 1 ]; then
  err "Python $PY_MM is too old; 3.10 or newer is required."
  exit 1
fi
ok "python3 is $PY_MM"

# -------------------------------------------------------------- 2. system packages

# python3-venv is not installed by default on Ubuntu/Zorin and is the single
# most common reason this install fails.
APT_REQUIRED=(python3-venv python3-dev build-essential git curl)
APT_FEATURES=(espeak-ng ffmpeg poppler-utils libenchant-2-2 python3-tk)
APT_OPTIONAL=(portaudio19-dev wkhtmltopdf nmap)

bold "2. System packages"

if [ "$DO_APT" -eq 0 ]; then
  info "skipped (--no-apt)"
elif ! command -v apt-get >/dev/null 2>&1; then
  warn "apt-get not found; this is not a Debian-family system."
  warn "Install these yourself: ${APT_REQUIRED[*]} ${APT_FEATURES[*]}"
else
  missing=()
  for pkg in "${APT_REQUIRED[@]}" "${APT_FEATURES[@]}"; do
    dpkg -s "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
  done

  if [ "${#missing[@]}" -eq 0 ]; then
    ok "all required system packages already present"
  else
    info "These need root. The exact command that will run:"
    echo
    echo "    sudo apt-get install -y ${missing[*]}"
    echo
    if confirm "Run it?"; then
      sudo apt-get update
      sudo apt-get install -y "${missing[@]}"
      ok "system packages installed"
    else
      warn "Skipped. Some plugins will be unavailable, and venv creation may fail."
    fi
  fi

  info "Optional extras (not installed): ${APT_OPTIONAL[*]}"
  info "  portaudio19-dev = voice input, wkhtmltopdf = htmltopdf, nmap = scan_network"
fi

# ------------------------------------------------------------------ 3. virtualenv

bold "3. Virtualenv"

if [ -x "$VENV/bin/python" ]; then
  ok "reusing existing venv at env/"
else
  python3 -m venv "$VENV"
  ok "created venv at env/"
fi

# setuptools is deliberately held below 82: the pluginmanager package Jarvis is
# built on imports pkg_resources, which setuptools dropped in 82.0.0. With a
# newer setuptools, Jarvis fails to start at all.
"$VENV/bin/python" -m pip install --quiet --upgrade pip wheel
"$VENV/bin/python" -m pip install --quiet "setuptools<82"
ok "pip up to date (setuptools held <82 for pkg_resources)"

# --------------------------------------------------------------- 4. python deps

bold "4. Python dependencies"

if [ "$USE_FULL" -eq 1 ]; then
  REQ="installer/requirements.txt"
  warn "Using the full upstream set. On Python 3.12+ this is expected to fail:"
  warn "it pins a playsound fork at a GitHub URL that no longer exists."
else
  REQ="installer/requirements-lean.txt"
fi

info "installing from $REQ (this takes a few minutes)"
"$VENV/bin/python" -m pip install --requirement "$REQ"
ok "dependencies installed"

# ------------------------------------------------------------------- 5. nltk data

bold "5. Language data"

if [ -d "$ROOT/jarviscli/data/nltk/corpora/wordnet" ] \
   || [ -f "$ROOT/jarviscli/data/nltk/corpora/wordnet.zip" ]; then
  ok "nltk data already present"
else
  nltk_failed=0
  for corpus in wordnet punkt; do
    info "downloading $corpus"
    # </dev/null because nltk.downloader prompts "Retry? [n/y/e]" on failure and
    # would otherwise hang, or die on EOF, taking the whole install with it.
    if ! "$VENV/bin/python" -m nltk.downloader \
          -d "$ROOT/jarviscli/data/nltk" "$corpus" >/dev/null 2>&1 </dev/null; then
      nltk_failed=1
      warn "could not download $corpus"
    fi
  done
  if [ "$nltk_failed" -eq 0 ]; then
    ok "nltk data downloaded"
  else
    warn "Language data is optional: only dictionary-style plugins need it, and"
    warn "the claude plugin does not. Retry later with:"
    warn "  ./env/bin/python -m nltk.downloader -d jarviscli/data/nltk wordnet punkt"
  fi
fi

# ------------------------------------------------------------- 6. claude code cli

bold "6. Claude Code CLI"

# claude-agent-sdk shells out to this CLI; without it the plugin raises
# CLINotFoundError. It is also what lets Claude authenticate against an existing
# Claude subscription instead of metered API credits.
if [ "$DO_CLI" -eq 0 ]; then
  info "skipped (--no-cli)"
elif command -v claude >/dev/null 2>&1; then
  ok "claude CLI already installed ($(claude --version 2>/dev/null || echo 'version unknown'))"
else
  if ! command -v npm >/dev/null 2>&1; then
    info "npm is required to install the CLI. The command that will run:"
    echo
    echo "    sudo apt-get install -y nodejs npm"
    echo
    if confirm "Run it?"; then
      sudo apt-get install -y nodejs npm
    else
      warn "Skipped. Install the CLI yourself later, or the claude plugin will not start."
    fi
  fi

  if command -v npm >/dev/null 2>&1; then
    info "installing @anthropic-ai/claude-code globally"
    if npm install -g @anthropic-ai/claude-code 2>/dev/null; then
      ok "claude CLI installed"
    else
      info "global install needs root. The command that will run:"
      echo
      echo "    sudo npm install -g @anthropic-ai/claude-code"
      echo
      if confirm "Run it?"; then
        sudo npm install -g @anthropic-ai/claude-code
        ok "claude CLI installed"
      else
        warn "Skipped; the claude plugin will not start until the CLI exists."
      fi
    fi
  fi
fi

# -------------------------------------------------------------------- 7. launcher

bold "7. Launcher"

cat > "$ROOT/jarvis" <<LAUNCHER
#!/usr/bin/env bash
source "$VENV/bin/activate"
exec python "$ROOT/jarviscli" "\$@"
LAUNCHER
chmod +x "$ROOT/jarvis"
ok "wrote ./jarvis"

LOCAL_BIN="$HOME/.local/bin"
if [ -L "$LOCAL_BIN/jarvis" ] && [ "$(readlink -f "$LOCAL_BIN/jarvis")" = "$ROOT/jarvis" ]; then
  ok "already linked into ~/.local/bin"
elif confirm "Link ./jarvis into ~/.local/bin so you can run it from anywhere?"; then
  mkdir -p "$LOCAL_BIN"
  ln -sf "$ROOT/jarvis" "$LOCAL_BIN/jarvis"
  ok "linked $LOCAL_BIN/jarvis"
  case ":$PATH:" in
    *":$LOCAL_BIN:"*) ;;
    *) warn "$LOCAL_BIN is not on your PATH. Add this to ~/.bashrc:"
       echo "         export PATH=\"\$PATH:$LOCAL_BIN\"" ;;
  esac
fi

# --------------------------------------------------------------------- 8. verify

bold "8. Verifying"

if "$VENV/bin/python" -c 'import claude_agent_sdk' 2>/dev/null; then
  ok "claude_agent_sdk imports"
else
  err "claude_agent_sdk did not import; the claude plugin will be skipped."
fi

# Plugins with a broken import print a traceback and are skipped, so look only
# at the summary line this prints last.
VERIFY="$(cd "$ROOT/jarviscli" && "$VENV/bin/python" -c '
import sys
sys.path.insert(0, ".")
from PluginManager import PluginManager
m = PluginManager()
m.add_directory("plugins")
names = set(m.get_plugins())
print("RESULT %d %s" % (
    m.get_number_plugins_loaded(),
    "yes" if "claude" in names else "no",
))
' 2>/dev/null | sed -n 's/^RESULT //p')"

if [ -n "$VERIFY" ]; then
  set -- $VERIFY
  info "plugins loaded: $1"
  if [ "$2" = "yes" ]; then
    ok "claude plugin registered"
  else
    err "claude plugin did NOT register"
  fi
else
  warn "could not inspect plugins; start ./jarvis and run 'help' to check"
fi

# Loading plugins is not the same as starting up: an import error in
# jarviscli/__main__.py crashes ./jarvis while leaving PluginManager happy.
if printf 'exit\n' | timeout 180 "$ROOT/jarvis" >/dev/null 2>&1; then
  ok "./jarvis starts and exits cleanly"
else
  err "./jarvis failed to start. Run it directly to see the error:"
  err "  ./jarvis"
fi

if [ "$DO_AUTOSTART" -eq 1 ]; then
  echo
  bold "9. Login autostart"
  "$ROOT/scripts/install-autostart.sh"
fi

echo
bold "Done."
echo
if [ "$DO_AUTOSTART" -eq 0 ]; then
  info "To open Jarvis in a terminal on login:"
  info "  ./scripts/install-autostart.sh"
  echo
fi
info "Next steps:"
info "  1. Authenticate Claude:   claude login"
info "  2. Start Jarvis:          ./jarvis       (or just: jarvis)"
info "  3. Inside Jarvis:         claude what is using my disk space?"
info "                            claude status"
info "                            claude model sonnet"
echo
info "Claude asks before any write, edit or shell command, and refuses a"
info "hardcoded set of destructive ones outright. See jarviscli/plugins/claude_agent.py."
echo
