# -*- encoding: utf-8 -*-

import os
from colorama import Fore
import nltk
import re
import sys
import tempfile
from utilities.GeneralUtilities import print_say
from CmdInterpreter import CmdInterpreter
from packages import gemma
from packages.ai_brain import brain, router

# register hist path
HISTORY_FILENAME = tempfile.TemporaryFile('w+t')


PROMPT_CHAR = '~>'

# Everyday phrasings that the word-matching in find_action() cannot place,
# because the plugin's name is two words ("check time") or the key word is
# not first. Matched against the lower-cased input; first match wins.
NATURAL_ROUTES = [
    # "what time is it in tokyo", "time in london", "what's the time in rome"
    (re.compile(r"^(?:what(?:'s| is)?\s+)?(?:the\s+)?(?:current\s+)?(?:local\s+)?"
                r"time(?:\s+is\s+it)?(?:\s+now)?\s+(?:in|at)\s+(.+)$"),
     r"check time in \1"),
    # "what's the time", "what time is it now"
    (re.compile(r"^(?:what(?:'s| is)\s+the\s+time|what time is it)(?:\s+now)?$"),
     "clock"),
    # "what's the forecast for london", "weather forecast"
    (re.compile(r"^(?:what(?:'s| is)?\s+)?(?:the\s+)?(?:weather\s+)?forecast\b(.*)$"),
     r"check forecast \1"),
    # "do i need an umbrella (in london)"
    (re.compile(r"^.*\bumbrella\b(.*)$"), r"weather umbrella \1"),
]

"""
    AUTHORS' SCOPE:
        We thought that the source code of Jarvis would
        be more organized if we treat Jarvis as Object.
        So we decided to create this Jarvis Class which
        implements the core functionality of Jarvis in a
        simpler way than the original __main__.py.
    HOW TO EXTEND JARVIS:
        In progress..
    DETECTED ISSUES:
        * Furthermore, "near me" command is unable to find
        the actual location of our laptops.
"""


class Jarvis(CmdInterpreter, object):
    # variable used at Breakpoint #1.
    # allows Jarvis say "Hi", only at the first interaction.
    first_reaction_text = ""
    first_reaction_text += Fore.CYAN + \
        'Jarvis\' sound is by default disabled.' + Fore.RESET
    first_reaction_text += "\n"
    first_reaction_text += Fore.CYAN + 'In order to let Jarvis talk out loud type: '
    first_reaction_text += Fore.RESET + Fore.MAGENTA + 'enable sound' + Fore.RESET
    first_reaction_text += "\n"
    first_reaction_text += Fore.CYAN + \
        "Type 'help' for a list of available actions." + Fore.RESET
    first_reaction_text += "\n"
    prompt = (
        Fore.MAGENTA
        + "{} Hi, what can I do for you?\n".format(PROMPT_CHAR)
        + Fore.RESET)

    # Used to store user specific data

    def __init__(self, first_reaction_text=first_reaction_text,
                 prompt=prompt, first_reaction=True,
                 directories=["jarviscli/plugins", "custom"]):
        directories = self._rel_path_fix(directories)

        if sys.platform == 'win32':
            self.use_rawinput = False
        self.regex_dot = re.compile('\\.(?!\\w)')
        CmdInterpreter.__init__(self, first_reaction_text, prompt,
                                directories, first_reaction)

    def _rel_path_fix(self, dirs):
        dirs_abs = []
        work_dir = os.path.dirname(__file__)
        # remove 'jarviscli/' from path
        work_dir = os.path.dirname(work_dir)

        # fix nltk path
        nltk.data.path.append(os.path.join(work_dir, "jarviscli/data/nltk"))

        # relative -> absolute paths
        for directory in dirs:
            if not directory.startswith(work_dir):
                directory = os.path.join(work_dir, directory)
            dirs_abs.append(directory)
        return dirs_abs

    def default(self, data):
        """No command matched: hand the original wording to the AI fallback.

        Claude (Haiku by default) answers first: quick and cheap. When it
        cannot (offline, not signed in, spend cap reached), the free local
        model answers instead, if it is installed; it is slower, so say so.
        """
        question = getattr(self, '_raw_line', '') or data
        if gemma.private_mode() and question.strip() and question != 'None':
            self._answer_with_gemma(question, private=True)     # never Claude
            return
        if not brain.enabled or not question.strip() or question == 'None':
            print_say("I could not identify your command...", self, Fore.MAGENTA)
            return

        if brain.available:
            try:
                self._api.say(brain.ask(question), Fore.CYAN)
                return
            except RuntimeError as e:
                claude_problem = str(e)
        else:
            claude_problem = 'AI answers are unavailable: %s.' % brain.unavailable_reason()

        if self._answer_with_gemma(question):
            return

        from packages import local_llm
        if local_llm.available():
            self._api.say("Claude isn't reachable, so the local model is answering. "
                          "It takes about half a minute.", Fore.MAGENTA)
            try:
                self._api.say(local_llm.ask(question).strip(), Fore.CYAN)
            except local_llm.LocalLLMError as e:
                self._api.say(str(e), Fore.MAGENTA)
            return
        self._api.say(claude_problem, Fore.MAGENTA)

    def _answer_with_gemma(self, question, private=False):
        """Answer with the local Gemma model. True when the question is dealt with.
        In private mode that includes Gemma being down: it is then reported and
        the question is not sent to Claude instead."""
        if not gemma.available():
            if private:
                self._api.say("Private mode is on but the local Gemma server is not running, "
                              "so I have not asked Claude.", Fore.MAGENTA)
                return True
            return False
        if not private:
            self._api.say("Claude isn't reachable, so local Gemma is answering.", Fore.MAGENTA)
        try:
            self._api.say(gemma.ask(question).strip(), Fore.CYAN)
        except gemma.GemmaError as e:
            self._api.say(str(e), Fore.MAGENTA)
            return private
        return True

    def precmd(self, line):
        """Hook that executes before every command."""
        words = line.split()
        HISTORY_FILENAME.write(line + '\n')
        # Kept verbatim for the AI fallback; parse_input() lower-cases and
        # strips punctuation, which is right for matching commands but mangles
        # a question ("Who wrote Hamlet?" -> "who wrote hamlet").
        self._raw_line = line.strip()

        rest = self._strip_name(line)
        if rest == '':
            return '__ai__'     # just "hey jarvis": no command, a greeting for the AI
        if rest != line.strip():
            return self.precmd(rest)

        # Questions for Claude or the local model go through untouched, for the
        # same reason, and so a word inside them cannot select another command.
        if words and words[0].lower() in ('claude', 'ai', 'ask', 'local', 'research', 'draft'):
            return words[0].lower() + line.strip()[len(words[0]):]

        # append calculate keyword to front of leading char digit (or '-') in line
        if words and (words[0].isdigit() or line[0] == "-"):
            line = "calculate " + line
            words = line.split()

        if line.startswith("help"):
            return line
        if line.startswith("status"):
            return line

        if not words:
            line = "None"
        else:
            line = self.parse_input(line)
        return line

    def postcmd(self, stop, line):
        """Hook that executes after every command."""
        if self.first_reaction:
            self.prompt = (
                Fore.MAGENTA
                + "{} What can I do for you?\n".format(PROMPT_CHAR)
                + Fore.RESET)
            self.first_reaction = False
        if self.enable_voice:
            self.speech.text_to_speech("What can I do for you?\n")

    def speak(self, text):
        if self.enable_voice:
            self.speech.text_to_speech(text)

    def _strip_name(self, text):
        """Drop a leading "Jarvis," / "Hey Jarvis" from text.

        People address the assistant by name, and "jarvis" is also a plugin
        (the tour), so "Jarvis, tell me a joke" used to open the tour. Returns
        the text unchanged when the words after the name are a real command
        of the jarvis plugin ("jarvis tour"), and '' when nothing follows.
        """
        text = text.strip()
        named = re.match(r"^(?:(?:hey|hi|hello|ok|okay)\s+)?jarvis\b[\s,.!?]*(.*)$",
                         text, re.IGNORECASE)
        if not named:
            return text
        rest = named.group(1)
        if not rest:
            return ''
        sub = self._plugin_manager.get_plugins().get('jarvis')
        subs = set(sub.get_plugins().keys()) if sub is not None else set()
        if subs and rest.split()[0].lower() in subs:
            return text
        return rest

    def parse_input(self, data):
        """This method gets the data and assigns it to an action"""
        data = self._strip_name(data) or data
        data = data.lower()
        # say command is better if data has punctuation marks
        if "say" not in data:
            data = data.replace("?", "")
            data = data.replace("!", "")
            data = data.replace(",", "")

            # input sanitisation to not mess up urls / numbers
            data = self.regex_dot.sub("", data)

        for pattern, replacement in NATURAL_ROUTES:
            if pattern.match(data):
                return pattern.sub(replacement, data).strip()

        # Check if Jarvis has a fixed response to this data
        if data in self.fixed_responses:
            output = self.fixed_responses[data]
        else:
            # if it doesn't have a fixed response, look if the data corresponds
            # to an action
            output = self.find_action(
                data, self._plugin_manager.get_plugins().keys())
            if self._keyword_was_hijacked(data, output):
                return '__ai__'
        return output

    def _keyword_was_hijacked(self, data, output):
        """Ask Claude whether a mid-sentence keyword match is really wanted.

        find_action() picks any command name found anywhere in the sentence,
        so "how far is the moon from earth" ran the moon-phase command. When
        the command word is not the first word of a longer request, Haiku
        confirms the match (about $0.001); if it says no, the request goes to
        the AI answer path instead. Without Claude, the match stands.
        """
        if output == "None" or gemma.private_mode() or not (brain.enabled and brain.available):
            return False
        words = data.split()
        command = output.split()[0]
        if len(words) < 4 or words[0] == command:
            return False
        plugin = self._plugin_manager.get_plugins().get(command)
        description = plugin.get_doc() if plugin is not None else ''
        request = getattr(self, '_raw_line', '') or data
        return router.confirms(request, command, description) is False

    def find_action(self, data, actions):
        """Checks if input is a defined action.

        The longest command name found in the sentence wins. On a tie the one
        said later wins: "I want to hear a joke" means `joke`, not `hear`.
        (Ties used to follow plugin load order, which varies between runs.)
        :return: returns the action"""
        actions = set(actions or ())
        words = data.split()
        best = None
        for index, word in enumerate(words):
            if word in actions and (best is None or (len(word), index) > (len(best[1]), best[0])):
                best = (index, word)
        if best is None:
            return "None"
        index, word = best
        if word == "near":
            # For 'near', the words before it are needed too
            return "near " + " ".join(words[:index] + ["|"] + words[index + 1:])
        return word + " " + " ".join(words[index + 1:])

    def executor(self, command):
        """
        If command is not empty, we execute it and terminate.
        Else, this method opens a terminal session with the user.
        We can say that it is the core function of this whole class
        and it joins all the function above to work together like a
        clockwork. (Terminates when the user send the "exit", "quit"
        or "goodbye command")
        :return: Nothing to return.
        """
        if command:
            self.execute_once(command)
        else:
            brain.warm()
            router.warm()
            self.cmdloop()
