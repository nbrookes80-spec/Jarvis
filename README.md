# Jarvis

[![CI](https://github.com/nbrookes80-spec/Jarvis/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/nbrookes80-spec/Jarvis/actions/workflows/ci.yml)

A Personal Non-AI Assistant for Linux, MacOS and Windows

![Jarvis](http://i.imgur.com/xZ8x9ES.jpg)

Jarvis is a simple personal assistant for Linux, MacOS and Windows which works on the command line. He can talk to you if you enable his voice. He can tell you the weather, he can find restaurants and other places near you. He can do some great stuff for you.

## 🚀 15+ Different Tasks That Jarvis Can Do For You:

1. **Entertainment & Suggestions**
   - Suggest activities if you're bored (`activity`, `bored`)
   - Provide ideas on what to draw, watch, or listen to (`prompt`, `top_media`, `taste dive`, `mood music`)

2. **Sports Updates**
   - Get up-to-date sports information: team rankings, match times, player stats (`basketball`, `cricket`, `soccer`, `tennis`)

3. **Games**
   - Play games: Blackjack, Connect Four, Hangman, Rock-Paper-Scissors, etc. (`blackjack`, `connect_four`, `guess_number_game`, `hangman`, `rockpaperscissors`, `roulette`, `tic_tac_toe`, `word_game`, `wordle`)

4. **Health & Fitness**
   - Access nutrition facts, recipes, workout programs, and health trackers (`bmi`, `bmr`, `calories`, `food recipe`, `fruit`, `fruit nutrition`, `workout`)

5. **Cocktail Recipes**
   - Learn how to make cocktails (`cocktail`, `drink`)

6. **Random Generators**
   - Generate random lists, numbers, passwords (`random list`, `random number`, `random password`)

7. **Unit Conversions**
   - Convert units: binary, currency, hex, length, mass, speed, temperature, time (`binary`, `currencyconv`, `hex`, `lengthconv`, `massconv`, `speedconv`, `string_convert`, `tempconv`, `timeconv`)

8. **Photography**
   - Take pictures and screenshots (`open camera`, `screencapture`)

9. **System Information**
   - Get computer specifications (`battery`, `cat his`, `dns forward`, `dns reverse`, `hostinfo`, `ip`, `scan_network`, `speedtest`, `os`, `check ram`, `systeminfo`)

10. **File Management**
    - Manage and organize files (`file manage`, `file organize`)

11. **Image Processing**
    - Upload, edit, and convert images (`imgur`, `image to pdf`, `image compressor`)

12. **PDF Conversion**
    - Convert webpages to PDF or PDFs to images (`htmltopdf`, `pdf to images`)

13. **Jokes & Facts**
    - Enjoy jokes and random facts (`dadjoke`, `joke daily`, `joke chuck`, `joke`, `fact`, `cat fact`)

14. **Calculations**
    - Perform calculations and solve equations (`calculate`, `factor`, `solve`, `equations`, `plot`, `matrix add`)

15. **QR Code Generation**
    - Generate QR codes for URLs (`qr`)

16. **Weather Updates**
    - Check the weather forecast (`weather report`)

17. **Language Translation**
    - Translate languages (`translate`)

18. **Stock Market Information**
    - Display stock and cryptocurrency information (`stock`, `cryptotracker`)

## 🛠️ Getting Started

### Installation

1. **Clone the Repository**

   ```bash
   git clone https://github.com/nbrookes80-spec/Jarvis.git jarvis-claude
   cd jarvis-claude
   ```

2. **Run the installer**

   On Debian, Ubuntu or Zorin OS use `./bootstrap.sh` (below). On other systems:
   ```bash
   python3 installer
   ```

The project plan, current state and next steps are in [doc/PROJECT_PLAN.md](doc/PROJECT_PLAN.md).

#### Debian / Ubuntu / Zorin: `./bootstrap.sh`

On Debian-family systems `./bootstrap.sh` is the recommended installer.
It installs the system packages the upstream installer assumes you already have,
is safe to re-run, prints every `sudo` command before running it, and sets up the
[Claude agent plugin](doc/CLAUDE_AGENT.md).

```bash
./bootstrap.sh            # interactive
./bootstrap.sh --yes      # no prompts
./bootstrap.sh --help     # all flags
```

It installs the runtime dependencies (`installer/requirements-lean.txt`), which
resolve on Python 3.10 through 3.13; `--full` adds the test and lint tools. See
[doc/CLAUDE_AGENT.md](doc/CLAUDE_AGENT.md#changes-to-upstream-dependencies) for
why `playsound` is dropped and how current setuptools (which no longer ships
`pkg_resources`) is handled.

Already have a virtualenv? `pip install -e .` installs Jarvis into it with the
`Jarvis-AI` and `jarvis-gui` commands (`pip install -e '.[gui]'` adds the voice
libraries).

### Desktop window and voice (Zorin OS / GNOME)

A native GTK 4 / libadwaita window you can talk to. Say **"Hey Jarvis"**, press
the microphone button (or Ctrl+Space), or type. Speech recognition and the voice
both run offline.

```bash
./scripts/install-gui.sh --autostart   # or: ./bootstrap.sh --gui --autostart
```

It adds Jarvis to the app menu and, with `--autostart`, opens it at login.
Details, settings and troubleshooting: [doc/GUI.md](doc/GUI.md).

### Chatting with Claude

After installing, `claude login` once, then inside Jarvis:

```
claude how much disk space am I using?
claude model sonnet
claude status
```

Claude can read files, run shell commands and use MCP connectors and skills on
this machine. It asks before anything that writes or executes, and refuses a
fixed set of destructive commands outright. Details, cost controls and the
permission model: [doc/CLAUDE_AGENT.md](doc/CLAUDE_AGENT.md).

### Running Jarvis

- Run Jarvis in a terminal from anywhere:
  
   ```bash
   Jarvis-AI
   ```

  Or from within the project folder:
  
   ```bash
   ./Jarvis-AI
   ```

  For the desktop window with voice, open **Jarvis** from the app menu or run `./jarvis-gui`.

You can start by typing `help` within the Jarvis command line to check what Jarvis can do for you.

## ❓Frequently encountered issues
**Question**: 
When I run Jarvis, it shows an error relating to module not found<br>

**Platform**: 
Windows<br>

**Solution 1**: Uninstall and/or install the module package.<br>

**Example:**<br>
Error: `ImportError: DLL load failed while importing win32api: The specified module could not be found.`<br>

**Solution:**<br>
`pip uninstall pywin32`<br>
`pip install pywin32` or `conda install pywin32`<br>

**Solution 2**: add the package to your environment variables system PATH.<br>

-----

**Question**: After cloning the repo in terminal it gives an error when running python3 installer saying please install virtual environemnt.

**Solution**: 
- Install virtual env using this command:
  ```bash
  python3 -m pip install virtualenv
  ```
- OR: On Linux use package manager (e.g. Ubuntu sudo apt install python3-venv)
  
- Restart Installer

-----

**If you find other issues and/or have found solutions to them on any platform, please consider adding to this list!**

## 💻 Youtube Video Showing Jarvis

[Click here](https://www.youtube.com/watch?v=PR-nxqmG3V8)

## 🤝 Contributing

Check out our [CONTRIBUTING.md](CONTRIBUTING.md) to learn how you can contribute!

### QuickStart: Create a new feature (plugin)

Create new file custom/hello_world.py

```
from plugin import plugin


@plugin("helloworld")
def helloworld(jarvis, s):
    """Repeats what you type"""
    jarvis.say(s)
```

Check it out!
```
./Jarvis-AI
Jarvis' sound is by default disabled.
In order to let Jarvis talk out loud type: enable sound
Type 'help' for a list of available actions.

~> Hi, what can I do for you?
helloworld Jarvis is cool!
jarvis is cool
```

### Plugins

[Click here](doc/PLUGINS.md) to learn more about plugins.

### Creating a test

Creating a test is optional but never a bad idea ;).

[Click here](doc/TESTING.md) to learn more about testing.

### How to run tests:

 Install the test tools once, then run `test.sh` (or `make test`):
 ```bash
 ./env/bin/pip install -r installer/requirements-dev.txt
 ./test.sh
 ```
## Optional Dependencies

- Any pyttsx3 text-to-speech engine (``sapi5, nsss or espeak``) for Jarvis to talk out loud (e.g. Ubuntu do ``sudo apt install espeak``)
- Portaudio + python-devel packages for voice control
- ``notify-send`` on Linux if you want to receive *nice* and desktop-notification instead of *ugly* pop up windows (e.g. Ubuntu do ``sudo apt install libnotify-bin``)
- ``ffmpeg`` if you want ``music`` to download songs as .mp3 instead of .webm

## Authors

 **sukeesh**

See also the list of [contributors](https://github.com/sukeesh/Jarvis/graphs/contributors) who have participated in this project.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
