# Jarvis desktop window

A GTK 4 / libadwaita front end for Jarvis, built for Zorin OS and other GNOME
desktops. It runs the same 240-odd commands as the terminal version, in a chat
window you can type or talk to.

- **Wake word:** say "Hey Jarvis", then your command, e.g. *"Hey Jarvis… what
  time is it?"*
- **Push to talk:** the microphone button, or Ctrl+Space while the window is
  focused
- **Spoken replies** in a British Piper voice, falling back to espeak-ng
- **Offline:** wake word, speech recognition and voice all run on this
  machine once the models are downloaded. Individual commands (weather, news…)
  still use the internet as they do in the terminal.

## Install

```bash
./bootstrap.sh                          # if you have not already
./scripts/install-gui.sh --autostart    # window + voice, open at login
```

Or both at once: `./bootstrap.sh --gui --autostart`.

`install-gui.sh` asks before it uses `sudo` or downloads anything. It:

1. installs the system packages it needs, if any are missing:
   `python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 libportaudio2 espeak-ng`
2. makes the system's GTK bindings importable from `env/` (see
   [Why GTK comes from the system](#why-gtk-comes-from-the-system))
3. installs `installer/requirements-gui.txt`
4. downloads the speech models (~210 MB) to `~/.local/share/jarvis/`
5. writes `./jarvis-gui` and adds Jarvis to the app menu

Options: `--yes` (no prompts), `--no-models` (download on first use instead),
`--autostart`, `--remove`.

## Use

Open **Jarvis** from the app menu, or run `./jarvis-gui`.

| To | Do |
|---|---|
| Talk | Say "Hey Jarvis", click the microphone, or press Ctrl+Space |
| Stop Jarvis talking | Escape, or click the microphone |
| Cancel listening | Escape, or the × on the listening strip |
| Answer a question a command asks | Type or say the answer; the box says *Answer Jarvis…* |
| See all commands | Menu → List commands, or say "help" |
| Quit | Ctrl+Q (closing the window keeps it running if that option is on) |

**A keyboard shortcut that works anywhere:** Settings → Keyboard → View and
Customise Shortcuts → Custom Shortcuts → add one with the command
`/path/to/jarvis-claude/jarvis-gui --listen`. It brings the window up and
starts listening.

### Menu options

| Option | Default | Effect |
|---|---|---|
| Speak replies | on | Read replies aloud. Long lists are summarised ("…and 80 more lines on screen"). |
| Listen for "Hey Jarvis" | on | Keep the wake word active. Off = microphone button only. |
| Keep running when closed | on | Closing the window hides it and keeps listening. Opening Jarvis again from the menu brings it back. |
| Open at login | follows install | Adds or removes `~/.config/autostart/jarvis.desktop`. |
| Answer other questions with Claude | on | Anything that is not a Jarvis command ("Who wrote Hamlet?") is answered by Claude in a sentence or two. Needs `claude login`. |
| Claude model | Haiku 4.5 (cheapest) | Haiku 4.5 ($1/$5 per million tokens), Sonnet 5.5 ($2/$10) or Opus 5.5 ($4/$20). Typical cost per answer on Haiku: under a cent. |

Settings are stored in `~/.config/jarvis/gui.json`. A few extra keys are only
settable there:

```json
{
  "whisper_model": "base.en",
  "voice": "en_GB-alan-medium",
  "wake_threshold": 0.5
}
```

- `whisper_model`: `tiny.en` is faster and less accurate; `small.en` is
  more accurate and about 3× slower. A new model downloads on first use.
- `voice`: any [Piper voice](https://huggingface.co/rhasspy/piper-voices),
  downloaded with
  `./env/bin/python -m piper.download_voices --download-dir ~/.local/share/jarvis/voices <name>`
- `wake_threshold`: raise it (e.g. `0.7`) if Jarvis wakes up by mistake;
  lower it if it misses you

You can address it by name: "Jarvis, what time is it in London?" and "Hey
Jarvis, how are you?" both work, typed or spoken. Everyday phrasings for time
and weather in other places are understood: "what time is it in Tokyo",
"what's the weather like in Rome", "do I need an umbrella".

## How it works

```
 microphone ─▶ openWakeWord ("hey jarvis") ─▶ record until you pause
                                                   │
                                                   ▼
 speakers ◀─ Piper ◀─ reply text ◀─ Jarvis engine ◀─ faster-whisper
                                     (gui/engine.py)
```

- `jarviscli/gui/engine.py` runs the normal Jarvis command interpreter on a
  background thread. Everything a command prints becomes a chat bubble; when
  a command asks a question (reads stdin), the next thing you type or say is
  sent as the answer. No GTK imports, so it is tested headless.
- `jarviscli/gui/voice.py` owns the microphone and speaker. The wake word is
  openWakeWord's bundled `hey_jarvis` model; an utterance ends after 0.9 s of
  quiet, measured against the room's noise level just before you spoke.
  While Jarvis is talking, the wake word is paused, so it cannot wake itself
  by saying its own name.
- `jarviscli/gui/app.py` is the window.

Measured on an 8-core laptop: the wake word scored 0.996 on a test phrase;
`base.en` transcribed a 2.4 s utterance in 0.8 s; Piper synthesised 2.4 s of
speech in 0.2 s. Allow ~10 s after startup for the speech model to load.

## Why GTK comes from the system

PyGObject (the GTK bindings) is a compiled extension. Installing it with pip
builds it from source, which needs a compiler plus `libgirepository-2.0-dev`
and `libcairo2-dev`. Zorin already ships a built copy (`python3-gi`) for the
same Python version as `env/`, so `install-gui.sh` symlinks that one package
into the virtualenv rather than opening `env/` to every system package. If the
Python versions ever differ, it falls back to building with pip.

## Limitations

- Commands written for a terminal UI (curses games, `clear`, `typing_test`) do
  not work well in the window; use `./jarvis` for those.
- `hear` (the old voice_control plugin) also wants the microphone; use the
  window's own voice input instead.
- There is no tray icon: Zorin's tray needs GTK 3, and one process cannot
  load both GTK 3 and GTK 4. With *Keep running when closed* on, open Jarvis
  from the app menu to bring the window back.
- Whisper occasionally mishears short commands. Typing always works.

## Troubleshooting

**"The microphone is not available"**: check Settings → Sound → Input, and
that `./env/bin/python -c "import sounddevice; print(sounddevice.query_devices())"`
lists an input device.

**It never hears "Hey Jarvis"**: lower `wake_threshold` to `0.35`, or use
the microphone button. Make sure the menu option is on.

**It talks in a robotic voice**: the Piper model is missing, so it fell back
to espeak-ng. Re-run `./scripts/install-gui.sh`.

**Start it from a terminal to see errors**: `./jarvis-gui`

**Remove it**: `./scripts/install-gui.sh --remove` (models are kept in
`~/.local/share/jarvis/`; delete that folder to reclaim the space).

## Licences

The window code is MIT, like the rest of Jarvis. It uses, without bundling:
[faster-whisper](https://github.com/SYSTRAN/faster-whisper) (MIT),
[openWakeWord](https://github.com/dscripka/openWakeWord) (Apache-2.0; the
pretrained models are CC BY-NC-SA 4.0, i.e. non-commercial),
[Piper](https://github.com/OHF-Voice/piper1-gpl) (GPL-3.0), and the
[en_GB-alan-medium](https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_GB/alan/medium/MODEL_CARD)
voice (its model card gives the dataset licence).
