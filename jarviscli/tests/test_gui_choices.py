"""Answer buttons for prompts: which prompts get them, and what a click sends.

Headless: the button rules are pure functions and the engine is driven without
starting its worker thread, so no GTK, plugins or Claude are needed.
"""
import unittest

from gui import choices
from gui.engine import JarvisEngine


class YesNoTest(unittest.TestCase):

    def test_bracketed_y_n_prompt(self):
        prompt = 'Would you like to save the file in the same folder?[y/n] '
        self.assertEqual(choices.options_for(prompt), [('Yes', 'y'), ('No', 'n')])

    def test_parenthesised_and_spelled_out(self):
        self.assertEqual(choices.options_for('Would you like the play again? (Y/N)'),
                         [('Yes', 'y'), ('No', 'n')])
        self.assertEqual(choices.options_for('Keep going, yes or no?'),
                         [('Yes', 'y'), ('No', 'n')])

    def test_trailing_y_n_without_brackets(self):
        self.assertEqual(choices.options_for('for the next week? Y/N '),
                         [('Yes', 'y'), ('No', 'n')])

    def test_google_write_confirmation_gets_buttons(self):
        # plugins/google_workspace.py asks this before every calendar, mail or sheet write.
        self.assertEqual(choices.options_for('Yes or no, do you confirm? '),
                         [('Yes', 'y'), ('No', 'n')])

    def test_mentioning_no_is_not_a_yes_no_question(self):
        self.assertEqual(choices.options_for('Type anything to continue or No to exit'), [])


class FreeTextTest(unittest.TestCase):

    def test_free_text_prompts_get_no_buttons(self):
        for prompt in ('Enter city name: ', 'Enter the smallest number: ',
                       'Enter a periodic element: ', 'Your choice: ', ''):
            self.assertEqual(choices.options_for(prompt), [], prompt)


class NumberedMenuTest(unittest.TestCase):

    def test_menu_printed_above_the_prompt(self):
        lines = ['Pick one:', '1. Rock', '2. Paper', '3. Scissors']
        self.assertEqual(choices.options_for('Your choice: ', lines),
                         [('Rock', '1'), ('Paper', '2'), ('Scissors', '3')])

    def test_bracket_and_paren_styles(self):
        self.assertEqual(choices.options_for('?', ['[1] Tea', '[2] Coffee']),
                         [('Tea', '1'), ('Coffee', '2')])
        self.assertEqual(choices.options_for('?', ['(1) Tea', '(2) Coffee']),
                         [('Tea', '1'), ('Coffee', '2')])

    def test_blank_lines_inside_the_menu_are_allowed(self):
        self.assertEqual(choices.options_for('?', ['1) a', '', '2) b']),
                         [('a', '1'), ('b', '2')])

    def test_text_after_the_items_ends_the_menu(self):
        self.assertEqual(choices.options_for('?', ['1. a', '2. b', 'some text']), [])

    def test_menu_must_start_at_one_and_have_two_items(self):
        self.assertEqual(choices.options_for('?', ['2. b', '3. c']), [])
        self.assertEqual(choices.options_for('?', ['1. only one']), [])

    def test_too_many_items_fall_back_to_typing(self):
        lines = ['%d. item %d' % (n, n) for n in range(1, 11)]
        self.assertEqual(choices.options_for('?', lines), [])

    def test_long_items_are_shortened(self):
        label, reply = choices.options_for('?', ['1. ' + 'x' * 80, '2. b'])[0]
        self.assertLessEqual(len(label), choices.LABEL_CHARS)
        self.assertTrue(label.endswith('…'))
        self.assertEqual(reply, '1')


class RangeTest(unittest.TestCase):

    def test_range_in_the_prompt_gives_its_numbers(self):
        self.assertEqual(choices.options_for('Pick a column (1-7):'),
                         [(str(n), str(n)) for n in range(1, 8)])

    def test_wide_range_is_typed(self):
        self.assertEqual(choices.options_for('Choose your mood (1-12): '), [])


class EngineRecentLinesTest(unittest.TestCase):
    """The engine remembers the lines printed just before a prompt, so a menu
    above the prompt can become buttons."""

    def test_complete_lines_are_recorded(self):
        engine = JarvisEngine()
        engine._loading = False
        engine._emit('Pick one:\n1. Rock\n')
        engine._emit('2. Paper\nYour choice: ')
        self.assertEqual(engine.recent_lines(), ['Pick one:', '1. Rock', '2. Paper'])

    def test_recent_lines_are_kept_short(self):
        engine = JarvisEngine()
        engine._loading = False
        engine._emit(''.join('line %d\n' % n for n in range(100)))
        self.assertEqual(len(engine.recent_lines()), 20)
        self.assertEqual(engine.recent_lines()[-1], 'line 99')


if __name__ == '__main__':
    unittest.main()
