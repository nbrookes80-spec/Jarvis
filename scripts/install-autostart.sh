#!/usr/bin/env bash
#
# Open Jarvis in a terminal window when you log in.
#
#   ./scripts/install-autostart.sh            install
#   ./scripts/install-autostart.sh --remove   uninstall
#   ./scripts/install-autostart.sh --status   show what is currently set
#
# This is a login autostart entry, not a boot service. Jarvis is an interactive
# prompt: it needs a terminal attached and a logged-in session to be useful. A
# systemd unit would start it with no terminal, where it exits or sits idle.
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LAUNCHER="$ROOT/scripts/jarvis-terminal.sh"
AUTOSTART_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"
ENTRY="$AUTOSTART_DIR/jarvis.desktop"

ok()   { printf '\033[32m  = %s\033[0m\n' "$*"; }
info() { printf '  %s\n' "$*"; }
warn() { printf '\033[33m  ! %s\033[0m\n' "$*"; }

case "${1:-}" in
  --remove)
    if [ -e "$ENTRY" ]; then
      rm -f "$ENTRY"
      ok "removed $ENTRY"
      info "Jarvis will no longer open on login."
    else
      info "Nothing to remove; $ENTRY does not exist."
    fi
    exit 0
    ;;
  --status)
    if [ -e "$ENTRY" ]; then
      ok "autostart is installed"
      info "$ENTRY"
      echo
      cat "$ENTRY"
    else
      info "autostart is not installed"
    fi
    exit 0
    ;;
  "") ;;
  *)
    echo "Unknown option: $1" >&2
    echo "Use --remove, --status, or no argument to install." >&2
    exit 2
    ;;
esac

[ -x "$LAUNCHER" ] || {
  echo "Launcher missing or not executable: $LAUNCHER" >&2
  exit 1
}

if [ ! -x "$ROOT/jarvis" ]; then
  warn "$ROOT/jarvis does not exist yet."
  warn "Run ./bootstrap.sh first, or the login window will just report that."
fi

mkdir -p "$AUTOSTART_DIR"

cat > "$ENTRY" <<ENTRY_EOF
[Desktop Entry]
Type=Application
Name=Jarvis
Comment=Open the Jarvis assistant in a terminal
Exec=$LAUNCHER
Icon=utilities-terminal
Terminal=false
NoDisplay=false
Hidden=false
X-GNOME-Autostart-enabled=true
ENTRY_EOF

ok "installed $ENTRY"
info "Jarvis will open in a terminal next time you log in."
info "Test it now without logging out:  $LAUNCHER"
info "Undo:                             $0 --remove"
