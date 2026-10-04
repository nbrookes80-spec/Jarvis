#!/usr/bin/env bash
#
# Install the Jarvis desktop window with offline voice, on Zorin OS / Ubuntu.
#
#   ./scripts/install-gui.sh              install (asks before sudo and downloads)
#   ./scripts/install-gui.sh --yes        no prompts
#   ./scripts/install-gui.sh --autostart  also open the window at login
#   ./scripts/install-gui.sh --no-models  skip the ~210 MB voice/speech models
#   ./scripts/install-gui.sh --remove     remove menu entry, icon and launcher
#
# Needs ./bootstrap.sh to have been run first (it creates env/).
# Safe to re-run: every step checks before it acts.
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$ROOT/env"
PY="$VENV/bin/python"
APP_ID="io.github.nbrookes80_spec.Jarvis"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
DESKTOP_FILE="$DATA_HOME/applications/$APP_ID.desktop"
ICON_SRC="$ROOT/jarviscli/gui/data/icons/hicolor/scalable/apps/$APP_ID.svg"
ICON_DST="$DATA_HOME/icons/hicolor/scalable/apps/$APP_ID.svg"
MODELS="$DATA_HOME/jarvis"
VOICE="en_GB-alan-medium"
WHISPER="base.en"

ASSUME_YES=0
DO_AUTOSTART=0
DO_MODELS=1

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

for arg in "$@"; do
  case "$arg" in
    --yes|-y) ASSUME_YES=1 ;;
    --autostart) DO_AUTOSTART=1 ;;
    --no-models) DO_MODELS=0 ;;
    --remove)
      rm -f "$DESKTOP_FILE" "$ICON_DST" "$ROOT/jarvis-gui"
      if grep -qs 'jarvis-gui' "${XDG_CONFIG_HOME:-$HOME/.config}/autostart/jarvis.desktop"; then
        rm -f "${XDG_CONFIG_HOME:-$HOME/.config}/autostart/jarvis.desktop"
      fi
      ok "removed menu entry, icon, launcher and GUI autostart"
      info "Models in $MODELS were kept; delete that folder to reclaim the space."
      exit 0 ;;
    -h|--help) awk 'NR>1 && /^#/ {sub(/^# ?/, ""); print; next} NR>1 {exit}' "$0"; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

if [ ! -x "$PY" ]; then
  err "No virtualenv at $VENV. Run ./bootstrap.sh first."
  exit 1
fi

# ------------------------------------------------------------ 1. system packages

bold "1. System packages"

# python3-gi + the two typelibs are the GTK 4 / libadwaita bindings.
# libportaudio2 is the audio backend sounddevice loads. espeak-ng is the
# fallback voice when the Piper model is not downloaded.
APT_GUI=(python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 libportaudio2 espeak-ng)
missing=()
for pkg in "${APT_GUI[@]}"; do
  dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q "install ok installed" \
    || missing+=("$pkg")
done
if [ "${#missing[@]}" -eq 0 ]; then
  ok "all present: ${APT_GUI[*]}"
elif ! command -v apt-get >/dev/null 2>&1; then
  err "Missing ${missing[*]} and apt-get is not available. Install them, then re-run."
  exit 1
else
  info "Needed: ${missing[*]}"
  echo "    sudo apt-get install -y ${missing[*]}"
  if confirm "Run that now?"; then
    sudo apt-get install -y "${missing[@]}"
    ok "installed"
  else
    err "Cannot continue without them."
    exit 1
  fi
fi

# ------------------------------------------------- 2. GTK bindings inside the venv

bold "2. GTK bindings"

SITE="$("$PY" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
SYS_GI="$(/usr/bin/python3 -c 'import gi, os; print(os.path.dirname(gi.__file__))' 2>/dev/null || true)"
VENV_MM="$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
SYS_MM="$(/usr/bin/python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"

if "$PY" -c 'import gi; gi.require_version("Adw", "1"); from gi.repository import Adw' 2>/dev/null; then
  ok "PyGObject with libadwaita already importable"
elif [ -n "$SYS_GI" ] && [ "$VENV_MM" = "$SYS_MM" ]; then
  # Same interpreter version, so the system's compiled _gi module loads as is.
  # Linking just this one package keeps every other system module out of env/.
  ln -sfn "$SYS_GI" "$SITE/gi"
  ok "linked system PyGObject ($SYS_GI) into env/"
else
  warn "env/ is Python $VENV_MM but the system is $SYS_MM; building PyGObject instead."
  warn "That needs: sudo apt-get install -y libgirepository-2.0-dev libcairo2-dev pkg-config"
  "$PY" -m pip install --quiet PyGObject
  ok "built PyGObject"
fi
"$PY" -c 'import gi; gi.require_version("Gtk", "4.0"); gi.require_version("Adw", "1"); from gi.repository import Gtk, Adw' \
  || { err "GTK 4 / libadwaita still not importable from env/"; exit 1; }

# ---------------------------------------------------------- 3. python packages

bold "3. Voice libraries"
info "faster-whisper, openWakeWord, Piper, sounddevice (a few minutes the first time)"
"$PY" -m pip install --quiet --requirement "$ROOT/installer/requirements-gui.txt"
ok "installed from installer/requirements-gui.txt"

# --------------------------------------------------------------------- 4. models

bold "4. Speech models"

if [ "$DO_MODELS" -eq 0 ]; then
  info "skipped (--no-models); they download on first use instead"
else
  mkdir -p "$MODELS/voices" "$MODELS/whisper"
  if [ -f "$MODELS/voices/$VOICE.onnx" ]; then
    ok "voice $VOICE present"
  elif confirm "Download the Piper voice $VOICE (~63 MB)?"; then
    "$PY" -m piper.download_voices --download-dir "$MODELS/voices" "$VOICE"
    ok "voice $VOICE downloaded"
  else
    info "skipped; Jarvis will use espeak-ng until it is downloaded"
  fi

  if confirm "Download the Whisper speech model $WHISPER (~145 MB)?"; then
    "$PY" - "$WHISPER" "$MODELS/whisper" <<'PYEOF'
import sys
from faster_whisper import WhisperModel
WhisperModel(sys.argv[1], device="cpu", compute_type="int8", download_root=sys.argv[2])
PYEOF
    ok "whisper $WHISPER ready"
  else
    info "skipped; it downloads the first time you use the microphone"
  fi
fi

# --------------------------------------------------- 5. launcher, menu, autostart

bold "5. Launcher and app menu"

cat > "$ROOT/jarvis-gui" <<LAUNCHER
#!/usr/bin/env bash
# Generated by scripts/install-gui.sh
cd "$ROOT" || exit 1
exec "$PY" "$ROOT/jarviscli/gui" "\$@"
LAUNCHER
chmod +x "$ROOT/jarvis-gui"
ok "wrote ./jarvis-gui"

mkdir -p "$(dirname "$ICON_DST")" "$(dirname "$DESKTOP_FILE")"
cp "$ICON_SRC" "$ICON_DST"
"$PY" - "$DESKTOP_FILE" "$ROOT/jarviscli" <<'PYEOF'
import sys
sys.path.insert(0, sys.argv[2])
from gui.app import desktop_entry
open(sys.argv[1], "w").write(desktop_entry())
PYEOF
command -v update-desktop-database >/dev/null 2>&1 \
  && update-desktop-database -q "$(dirname "$DESKTOP_FILE")" || true
command -v gtk-update-icon-cache >/dev/null 2>&1 \
  && gtk-update-icon-cache -q -t "$DATA_HOME/icons/hicolor" 2>/dev/null || true
ok "added Jarvis to the app menu ($DESKTOP_FILE)"

if [ "$DO_AUTOSTART" -eq 1 ]; then
  "$ROOT/scripts/install-autostart.sh" --gui
else
  info "To open the window at login:  ./scripts/install-autostart.sh --gui"
fi

echo
bold "Done."
info "Open Jarvis from the app menu, or run:  ./jarvis-gui"
info "Say \"Hey Jarvis\", press the microphone button, or press Ctrl+Space."
info "For a system-wide shortcut, add one in Settings > Keyboard > Custom Shortcuts"
info "with the command:  $ROOT/jarvis-gui --listen"
