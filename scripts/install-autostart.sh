#!/usr/bin/env bash
#
# Open Jarvis when you log in: in a terminal window, or as the desktop app.
#
#   ./scripts/install-autostart.sh            install (terminal)
#   ./scripts/install-autostart.sh --gui      install (desktop window, with voice)
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
COMMENT="in a terminal"
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
  --gui)
    # The window app; ./scripts/install-gui.sh writes this launcher.
    LAUNCHER="$ROOT/jarvis-gui"
    COMMENT="as the desktop window"
    [ -x "$LAUNCHER" ] || {
      echo "$LAUNCHER not found. Run ./scripts/install-gui.sh first." >&2
      exit 1
    }
    ;;
  "") ;;
  *)
    echo "Unknown option: $1" >&2
    echo "Use --gui, --remove, --status, or no argument to install." >&2
    exit 2
    ;;
esac

[ -x "$LAUNCHER" ] || {
  echo "Launcher missing or not executable: $LAUNCHER" >&2
  exit 1
}

if [ ! -x "$ROOT/Jarvis-AI" ]; then
  warn "$ROOT/Jarvis-AI does not exist yet."
  warn "Run ./bootstrap.sh first, or the login window will just report that."
fi

mkdir -p "$AUTOSTART_DIR"

cat > "$ENTRY" <<ENTRY_EOF
[Desktop Entry]
Type=Application
Name=Jarvis
Comment=Open the Jarvis assistant $COMMENT
Exec="$LAUNCHER"
Icon=$([ "$LAUNCHER" = "$ROOT/jarvis-gui" ] && echo io.github.nbrookes80_spec.Jarvis || echo utilities-terminal)
Terminal=false
NoDisplay=false
Hidden=false
X-GNOME-Autostart-enabled=true
ENTRY_EOF

ok "installed $ENTRY"
info "Jarvis will open next time you log in ($COMMENT)."
info "Test it now without logging out:  $LAUNCHER"
info "Undo:                             $0 --remove"
