# -*- coding: utf-8 -*-
"""Jarvis desktop window: GTK 4 + libadwaita, built for GNOME / Zorin OS."""
import json
import os
import sys

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from gui import voice  # noqa: E402
from packages.ai_brain import brain, router  # noqa: E402
from gui.engine import EXIT_WORDS, JarvisEngine  # noqa: E402

APP_ID = 'io.github.nbrookes80_spec.Jarvis'
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CONFIG_DIR = os.path.join(
    os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.config')), 'jarvis')
SETTINGS_FILE = os.path.join(CONFIG_DIR, 'gui.json')
AUTOSTART_FILE = os.path.join(
    os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.config')),
    'autostart', 'jarvis.desktop')

SUGGESTIONS = ['what time is it', 'weather', 'joke', 'help']

CSS = b"""
.bubble { padding: 8px 12px; border-radius: 16px; }
.bubble.user { background: @accent_bg_color; color: @accent_fg_color;
               border-bottom-right-radius: 4px; }
.bubble.jarvis { background: @card_bg_color; color: @card_fg_color;
                 border-bottom-left-radius: 4px;
                 box-shadow: 0 1px 2px alpha(black, 0.12); }
.bubble.prompt { border: 1px solid @accent_color; }
.bubble.error { background: alpha(@error_color, 0.12); }
.mono { font-family: monospace; font-size: 0.92em; }
.composer { padding: 10px 12px 12px 12px; }
.mic { min-width: 46px; min-height: 46px; }
.mic.active { background: @destructive_bg_color; color: @destructive_fg_color;
              animation: pulse 1.2s ease-in-out infinite; }
@keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.6; } 100% { opacity: 1; } }
.listen-bar { padding: 6px 14px; }
"""

STATE_LABELS = {
    'wake': 'Say “Hey Jarvis”',
    'idle': 'Ready',
    'recording': 'Listening…',
    'transcribing': 'Understanding…',
    'off': 'Microphone off',
}


class Settings(dict):
    DEFAULTS = {
        'speak_replies': True,
        'wake_word': True,
        'background': True,
        'whisper_model': voice.DEFAULT_WHISPER,
        'voice': voice.DEFAULT_VOICE,
        'wake_threshold': 0.5,
        'ai_fallback': True,
        'ai_model': 'haiku',
        'ai_router': True,
    }

    def __init__(self):
        super().__init__(self.DEFAULTS)
        try:
            with open(SETTINGS_FILE) as f:
                self.update(json.load(f))
        except (OSError, ValueError):
            pass

    def save(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        tmp = SETTINGS_FILE + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(self, f, indent=2)
        os.replace(tmp, SETTINGS_FILE)


def autostart_enabled():
    try:
        with open(AUTOSTART_FILE) as f:
            return 'jarvis-gui' in f.read()
    except OSError:
        return False


def set_autostart(enabled):
    if not enabled:
        if autostart_enabled():
            os.remove(AUTOSTART_FILE)
        return
    os.makedirs(os.path.dirname(AUTOSTART_FILE), exist_ok=True)
    with open(AUTOSTART_FILE, 'w') as f:
        f.write(desktop_entry(autostart=True))


def desktop_entry(autostart=False):
    lines = [
        '[Desktop Entry]',
        'Type=Application',
        'Name=Jarvis',
        'Comment=Personal assistant you can talk to',
        'Exec="%s"' % os.path.join(ROOT, 'jarvis-gui'),
        'Icon=%s' % APP_ID,
        'Terminal=false',
        'Categories=Utility;',
        'Keywords=assistant;voice;jarvis;',
        'StartupWMClass=%s' % APP_ID,
    ]
    if autostart:
        lines += ['X-GNOME-Autostart-enabled=true', 'X-GNOME-Autostart-Delay=5']
    return '\n'.join(lines) + '\n'


def idle(fn):
    """Decorator: run a callback on the GTK main loop, from any thread."""
    def wrapper(*args):
        GLib.idle_add(lambda: fn(*args) and False)
    return wrapper


class JarvisWindow(Adw.ApplicationWindow):

    def __init__(self, app):
        super().__init__(application=app, title='Jarvis')
        self.app = app
        self.set_default_size(480, 720)
        self.set_size_request(360, 420)
        self._reply = []
        self._building = None       # Jarvis bubble collecting current output

        toolbar = Adw.ToolbarView()
        self.set_content(toolbar)

        header = Adw.HeaderBar()
        self.title = Adw.WindowTitle(title='Jarvis', subtitle='Starting…')
        header.set_title_widget(self.title)
        menu = Gio.Menu()
        voice_section = Gio.Menu()
        voice_section.append('Speak replies', 'app.speak')
        voice_section.append('Listen for “Hey Jarvis”', 'app.wake')
        menu.append_section(None, voice_section)
        ai_section = Gio.Menu()
        ai_section.append('Answer other questions with Claude', 'app.ai')
        ai_section.append('Let Claude check which command you meant', 'app.ai-router')
        models = Gio.Menu()
        for key, label in (('haiku', 'Haiku 4.5 (cheapest)'), ('sonnet', 'Sonnet 5.5'),
                           ('opus', 'Opus 5.5 (most capable)')):
            models.append(label, 'app.ai-model::' + key)
        ai_section.append_submenu('Claude model', models)
        menu.append_section(None, ai_section)
        app_section = Gio.Menu()
        app_section.append('Keep running when closed', 'app.background')
        app_section.append('Open at login', 'app.autostart')
        menu.append_section(None, app_section)
        about_section = Gio.Menu()
        about_section.append('List commands', 'app.commands')
        about_section.append('About Jarvis', 'app.about')
        menu.append_section(None, about_section)
        menu_button = Gtk.MenuButton(icon_name='open-menu-symbolic', menu_model=menu,
                                     tooltip_text='Menu')
        header.pack_end(menu_button)
        toolbar.add_top_bar(header)

        self.banner = Adw.Banner()
        toolbar.add_top_bar(self.banner)

        # --- conversation
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        # Plain boxes rather than Adw.StatusPage/Adw.Clamp: inside a clamp,
        # wrapping labels are allocated their minimum width (one word per
        # line), which wrecks chat bubbles.
        loading = self._centered_page(
            Gtk.Spinner(spinning=True, width_request=32, height_request=32),
            'Starting Jarvis', 'Loading plugins…')
        self.stack.add_named(loading, 'loading')

        chips = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,
                            min_children_per_line=2, max_children_per_line=4,
                            halign=Gtk.Align.CENTER,
                            column_spacing=6, row_spacing=6)
        for s in SUGGESTIONS:
            b = Gtk.Button(label=s, css_classes=['pill'])
            b.connect('clicked', lambda _b, t=s: self.send(t))
            chips.append(b)
        self.empty = self._centered_page(
            Gtk.Image(icon_name=APP_ID, pixel_size=112),
            'Hi, I’m Jarvis',
            'Say “Hey Jarvis”, press the microphone, or type a command.',
            chips)

        self.messages = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                                margin_top=12, margin_bottom=12,
                                margin_start=12, margin_end=12)
        self.scroller = Gtk.ScrolledWindow(child=self.messages, vexpand=True,
                                           hscrollbar_policy=Gtk.PolicyType.NEVER)
        chat = Gtk.Stack()
        chat.add_named(self.empty, 'empty')
        chat.add_named(self.scroller, 'messages')
        self.chat = chat
        self.stack.add_named(chat, 'chat')

        # --- listening strip
        self.listen_revealer = Gtk.Revealer(
            transition_type=Gtk.RevealerTransitionType.SLIDE_UP)
        strip = Gtk.Box(spacing=10, css_classes=['listen-bar'])
        self.listen_label = Gtk.Label(label='Listening…', xalign=0)
        self.level = Gtk.LevelBar(min_value=0, max_value=1, hexpand=True,
                                  valign=Gtk.Align.CENTER)
        cancel = Gtk.Button(icon_name='window-close-symbolic', css_classes=['flat', 'circular'],
                            tooltip_text='Stop listening')
        cancel.connect('clicked', lambda *_: self.app.listener.cancel())
        strip.append(self.listen_label)
        strip.append(self.level)
        strip.append(cancel)
        self.listen_revealer.set_child(strip)

        # --- composer
        composer = Gtk.Box(spacing=8, css_classes=['composer'])
        self.entry = Gtk.Entry(hexpand=True, placeholder_text='Type a command…')
        self.entry.connect('activate', lambda e: self._send_entry())
        self.mic = Gtk.Button(icon_name='audio-input-microphone-symbolic',
                              css_classes=['circular', 'suggested-action', 'mic'],
                              tooltip_text='Talk to Jarvis (Ctrl+Space)',
                              valign=Gtk.Align.CENTER)
        self.mic.connect('clicked', lambda *_: self.app.toggle_listen())
        send = Gtk.Button(icon_name='go-up-symbolic', css_classes=['circular'],
                          tooltip_text='Send', valign=Gtk.Align.CENTER)
        send.connect('clicked', lambda *_: self._send_entry())
        composer.append(self.entry)
        composer.append(send)
        composer.append(self.mic)

        bottom = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        bottom.append(self.listen_revealer)
        bottom.append(composer)

        toolbar.set_content(self.stack)
        toolbar.add_bottom_bar(bottom)
        toolbar.set_bottom_bar_style(Adw.ToolbarStyle.RAISED)

        keys = Gtk.ShortcutController(scope=Gtk.ShortcutScope.GLOBAL)
        keys.add_shortcut(Gtk.Shortcut(
            trigger=Gtk.ShortcutTrigger.parse_string('<Control>space'),
            action=Gtk.CallbackAction.new(lambda *_: self.app.toggle_listen() or True)))
        keys.add_shortcut(Gtk.Shortcut(
            trigger=Gtk.ShortcutTrigger.parse_string('Escape'),
            action=Gtk.CallbackAction.new(lambda *_: self.app.interrupt() or True)))
        self.add_controller(keys)

        self.connect('close-request', self._on_close)

    # -------------------------------------------------------------- display

    @staticmethod
    def _centered_page(top, title, description, extra=None):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                       valign=Gtk.Align.CENTER, margin_start=24, margin_end=24)
        top.set_halign(Gtk.Align.CENTER)
        page.append(top)
        page.append(Gtk.Label(label=title, wrap=True, justify=Gtk.Justification.CENTER,
                              css_classes=['title-1'], margin_top=12))
        page.append(Gtk.Label(label=description, wrap=True,
                              justify=Gtk.Justification.CENTER, css_classes=['dim-label']))
        if extra is not None:
            extra.set_margin_top(12)
            page.append(extra)
        return page

    def _on_close(self, *_):
        if self.app.settings['background']:
            self.set_visible(False)
            return True     # keep running; relaunching shows the window
        self.app.quit()
        return False

    def show_ready(self):
        self.stack.set_visible_child_name('chat')
        self.entry.grab_focus()

    def set_status(self, text):
        self.title.set_subtitle(text)

    def _bubble(self, text, kind):
        mono = kind == 'jarvis' and ('  ' in text.strip() or '\t' in text)
        label = Gtk.Label(label=text.strip('\n'), wrap=True, selectable=True,
                          xalign=0, max_width_chars=60)
        label.set_wrap_mode(2)      # Pango.WrapMode.WORD_CHAR
        if mono:
            label.add_css_class('mono')
        box = Gtk.Box(css_classes=['bubble', kind.split()[0]] + kind.split()[1:])
        box.append(label)
        box.set_halign(Gtk.Align.END if kind == 'user' else Gtk.Align.START)
        if kind != 'user':
            box.set_margin_end(36)
        else:
            box.set_margin_start(36)
        self.chat.set_visible_child_name('messages')
        self.messages.append(box)
        GLib.timeout_add(30, self._scroll_to_end)
        return label

    def _scroll_to_end(self):
        adj = self.scroller.get_vadjustment()
        adj.set_value(adj.get_upper())
        return False

    def add_user(self, text):
        self._building = None
        self._bubble(text, 'user')

    def add_output(self, text):
        if self._building is None and not text.strip():
            return      # no empty bubble for a plugin's leading blank line
        if self._building is None:
            self._building = self._bubble(text, 'jarvis')
        else:
            self._building.set_label(self._building.get_label() + '\n' + text.rstrip('\n'))
            if '  ' in text.strip():
                self._building.add_css_class('mono')
            GLib.timeout_add(30, self._scroll_to_end)

    def add_prompt(self, prompt):
        self._building = None
        if prompt:
            self._bubble(prompt, 'jarvis prompt')
        self.entry.set_placeholder_text('Answer Jarvis…')

    def add_error(self, text):
        self._building = None
        self._bubble(text, 'jarvis error')

    def end_reply(self):
        self._building = None
        self.entry.set_placeholder_text('Type a command…')

    def _send_entry(self):
        text = self.entry.get_text().strip()
        if text:
            self.entry.set_text('')
            self.send(text)

    def send(self, text):
        self.app.handle_input(text)

    def set_listening(self, state):
        active = state in ('recording', 'transcribing')
        self.listen_revealer.set_reveal_child(active)
        self.listen_label.set_label(STATE_LABELS.get(state, state))
        if active:
            self.mic.add_css_class('active')
        else:
            self.mic.remove_css_class('active')
            self.level.set_value(0)


class JarvisApp(Adw.Application):

    def __init__(self):
        super().__init__(application_id=APP_ID,
                         flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        GLib.set_application_name('Jarvis')
        self.add_main_option('background', 0, GLib.OptionFlags.NONE,
                             GLib.OptionArg.NONE, 'Start without showing the window', None)
        self.add_main_option('listen', 0, GLib.OptionFlags.NONE,
                             GLib.OptionArg.NONE, 'Start listening for a command now', None)
        self.settings = Settings()
        self.window = None
        self.engine = None
        self.speaker = None
        self.listener = None
        self.ready = False
        self._busy = False
        self._held = False
        self._reply_text = []

    # ------------------------------------------------------------ lifecycle

    def do_startup(self):
        Adw.Application.do_startup(self)
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        Gtk.IconTheme.get_for_display(Gdk.Display.get_default()).add_search_path(
            os.path.join(HERE, 'data', 'icons'))
        Gtk.Window.set_default_icon_name(APP_ID)

        for name, key in (('speak', 'speak_replies'), ('wake', 'wake_word'),
                          ('background', 'background')):
            action = Gio.SimpleAction.new_stateful(
                name, None, GLib.Variant.new_boolean(bool(self.settings[key])))
            action.connect('change-state', self._on_toggle, key)
            self.add_action(action)
        brain.enabled = bool(self.settings['ai_fallback'])
        brain.set_model(self.settings['ai_model'])
        router.enabled = bool(self.settings['ai_router'])
        action = Gio.SimpleAction.new_stateful(
            'ai-router', None, GLib.Variant.new_boolean(router.enabled))
        action.connect('change-state', self._on_toggle, 'ai_router')
        self.add_action(action)
        action = Gio.SimpleAction.new_stateful(
            'ai', None, GLib.Variant.new_boolean(brain.enabled))
        action.connect('change-state', self._on_ai_toggle)
        self.add_action(action)
        action = Gio.SimpleAction.new_stateful(
            'ai-model', GLib.VariantType.new('s'),
            GLib.Variant.new_string(self.settings['ai_model']))
        action.connect('change-state', self._on_ai_model)
        self.add_action(action)
        action = Gio.SimpleAction.new_stateful(
            'autostart', None, GLib.Variant.new_boolean(autostart_enabled()))
        action.connect('change-state', self._on_autostart)
        self.add_action(action)
        for name, cb in (('commands', lambda *_: self.handle_input('help')),
                         ('about', self._on_about),
                         ('listen', lambda *_: self.toggle_listen()),
                         ('quit', lambda *_: self.quit())):
            a = Gio.SimpleAction.new(name, None)
            a.connect('activate', cb)
            self.add_action(a)
        self.set_accels_for_action('app.quit', ['<Control>q'])

        self.window = JarvisWindow(self)
        self._start_backends()

    def do_command_line(self, command_line):
        opts = command_line.get_options_dict().end().unpack()
        if opts.get('background'):
            if not self._held:
                self.hold()     # stay alive with no window, still listening
                self._held = True
        else:
            self.window.present()
        if opts.get('listen'):
            self.window.present()
            self.toggle_listen()
        return 0

    def do_shutdown(self):
        if self.listener is not None:
            self.listener.stop()
        if self.speaker is not None:
            self.speaker.stop()
        if self.engine is not None:
            self.engine.stop()
        Adw.Application.do_shutdown(self)

    def _start_backends(self):
        self.engine = JarvisEngine(
            on_output=idle(self._on_output), on_prompt=idle(self._on_prompt),
            on_busy=idle(self._on_busy), on_ready=idle(self._on_ready),
            on_error=idle(self._on_engine_error), on_speak=self._speak)
        self.engine.start()

        status = voice.voice_status()
        self.speaker = voice.Speaker(self.settings['voice'],
                                     on_state=idle(self._on_speaking))
        self.listener = voice.Listener(
            whisper_model=self.settings['whisper_model'],
            wake_threshold=float(self.settings['wake_threshold']),
            on_state=idle(self._on_listen_state), on_level=idle(self._on_level),
            on_text=idle(self._on_heard), on_error=idle(self._on_voice_error))
        problems = [v for v in (status['stt'], status['wake']) if v]
        if status['stt'] is None:
            self.listener.wake_enabled = bool(self.settings['wake_word']) and status['wake'] is None
            self.listener.start()
        if problems:
            self._show_banner('Voice input unavailable: %s. Run scripts/install-gui.sh.'
                              % problems[0])

    # ------------------------------------------------------------- settings

    def _on_toggle(self, action, value, key):
        action.set_state(value)
        self.settings[key] = value.get_boolean()
        self.settings.save()
        if key == 'wake_word' and self.listener is not None:
            self.listener.wake_enabled = self.settings[key]
            self._on_listen_state(self.listener.state)
        if key == 'speak_replies' and not self.settings[key]:
            self.speaker.stop()
        if key == 'ai_router':
            router.enabled = self.settings[key]

    def _on_ai_toggle(self, action, value):
        action.set_state(value)
        brain.enabled = self.settings['ai_fallback'] = value.get_boolean()
        self.settings.save()
        if brain.enabled and brain.unavailable_reason():
            self._show_banner('Claude answers unavailable: %s.' % brain.unavailable_reason())

    def _on_ai_model(self, action, value):
        action.set_state(value)
        self.settings['ai_model'] = value.get_string()
        self.settings.save()
        brain.set_model(self.settings['ai_model'])
        self.window.set_status('Claude model: %s' % value.get_string().title())

    def _on_autostart(self, action, value):
        try:
            set_autostart(value.get_boolean())
            action.set_state(value)
        except OSError as e:
            self._show_banner('Could not change login startup: %s' % e)

    def _on_about(self, *_):
        about = Adw.AboutWindow(
            transient_for=self.window, application_name='Jarvis',
            application_icon=APP_ID, developer_name='Jarvis contributors',
            website='https://github.com/nbrookes80-spec/Jarvis',
            license_type=Gtk.License.MIT_X11,
            comments='%d commands. Speech runs offline: openWakeWord, '
                     'faster-whisper and %s.\n\nOther questions: %s.' % (
                         self.engine.plugin_count if self.engine else 0,
                         self.speaker.engine_name or 'no voice',
                         ('Claude ' + brain.describe()) if brain.enabled else 'off'))
        about.present()

    def _show_banner(self, text):
        self.window.banner.set_title(text)
        self.window.banner.set_revealed(True)

    # ---------------------------------------------------------------- input

    def handle_input(self, text, spoken=False):
        text = text.strip()
        if not text:
            return
        self.speaker.stop()
        self.window.add_user(text)
        if text.lower().strip('.!? ') in EXIT_WORDS and not self.engine.waiting_for_input:
            self._reply('Goodbye.')
            self.window.end_reply()
            if self.settings['background']:
                GLib.timeout_add(900, lambda: self.window.set_visible(False) and False)
            else:
                GLib.timeout_add(1200, lambda: self.quit() and False)
            return
        if not self.ready:
            self._reply('Still loading, one moment…')
            return
        self.engine.submit(text)

    def toggle_listen(self):
        if self.listener is None or self.listener.state == 'off':
            self._show_banner('The microphone is not available.')
            return
        if self.speaker.speaking:
            self.speaker.stop()
        if self.listener.state in ('recording', 'transcribing'):
            self.listener.cancel()
        else:
            self.listener.listen_now()

    def interrupt(self):
        self.speaker.stop()
        if self.listener is not None:
            self.listener.cancel()

    def _reply(self, text):
        self.window.add_output(text)
        self._speak(text)

    def _speak(self, text):
        if self.settings['speak_replies'] and self.speaker is not None:
            said = voice.speakable(text)
            if said:
                self.speaker.say(said)

    # -------------------------------------------------- engine callbacks

    def _on_ready(self, count):
        self.ready = True
        self.window.show_ready()
        self._on_listen_state(self.listener.state if self.listener else 'off')

    def _on_engine_error(self, tb):
        self.window.show_ready()
        self.window.add_error('Jarvis failed to start:\n\n' + tb)
        self.window.set_status('Error')

    def _on_output(self, text):
        self.window.add_output(text)
        self._reply_text.append(text)

    def _on_prompt(self, prompt):
        self._flush_speech()
        self.window.add_prompt(prompt)
        self.window.set_status('Waiting for your answer')
        if prompt:
            self._speak(prompt)

    def _on_busy(self, busy):
        self._busy = busy
        if busy:
            self.window.set_status('Working…')
        else:
            self._flush_speech()
            self.window.end_reply()
            self._on_listen_state(self.listener.state if self.listener else 'off')

    def _flush_speech(self):
        text, self._reply_text = ''.join(self._reply_text), []
        if text.strip():
            self._speak(text)

    # --------------------------------------------------- voice callbacks

    def _on_listen_state(self, state):
        self.window.set_listening(state)
        if not self.ready:
            return
        if self._busy and state not in ('recording', 'transcribing'):
            return
        if self.speaker and self.speaker.speaking and state not in ('recording', 'transcribing'):
            self.window.set_status('Speaking…')
            return
        self.window.set_status(STATE_LABELS.get(state, state))

    def _on_level(self, level):
        self.window.level.set_value(level)

    def _on_heard(self, text):
        if text:
            self.handle_input(text, spoken=True)
        else:
            self.window.set_status('Didn’t catch that')

    def _on_voice_error(self, message):
        self._show_banner(message)

    def _on_speaking(self, speaking):
        if self.listener is not None:
            # Stops Jarvis waking itself up by saying its own name.
            self.listener.muted = speaking
        self._on_listen_state(self.listener.state if self.listener else 'off')


def main(argv=None):
    app = JarvisApp()
    return app.run(argv if argv is not None else sys.argv)
