#!/usr/bin/env bash
#
# Open Jarvis in a terminal window. The login autostart entry points here.
#
# Called with no arguments it finds a terminal emulator and re-invokes itself
# as `--run` inside it. That indirection is deliberate: every emulator quotes
# its -e/-x/-- argument differently, and handing each one a single script path
# avoids building a nested bash -c string per terminal.
#
#   jarvis-terminal.sh          find a terminal and open Jarvis in it
#   jarvis-terminal.sh --run    run Jarvis here, then wait before closing
#
set -u

SELF="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [ "${1:-}" = "--run" ]; then
  cd "$ROOT" || exit 1
  if [ ! -x ./jarvis ]; then
    echo "Jarvis launcher not found at $ROOT/jarvis"
    echo "Run ./bootstrap.sh first."
  else
    ./jarvis
  fi
  # Without this the window vanishes on exit, taking any error with it.
  echo
  printf '[Jarvis exited. Press Enter to close this window.] '
  read -r _
  exit 0
fi

# gnome-terminal is checked before x-terminal-emulator because on GNOME the
# latter is usually a symlink to it, and gnome-terminal wants `--`, not `-e`.
for term in gnome-terminal xfce4-terminal konsole tilix kitty alacritty \
            x-terminal-emulator xterm; do
  command -v "$term" >/dev/null 2>&1 || continue
  case "$term" in
    gnome-terminal)  exec "$term" --  "$SELF" --run ;;
    xfce4-terminal)  exec "$term" -x  "$SELF" --run ;;
    *)               exec "$term" -e  "$SELF" --run ;;
  esac
done

echo "No supported terminal emulator found." >&2
echo "Tried: gnome-terminal xfce4-terminal konsole tilix kitty alacritty" >&2
echo "       x-terminal-emulator xterm" >&2
exit 1
