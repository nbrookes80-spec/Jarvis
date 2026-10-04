import unittest
from unittest import mock

import plugins.hackernews as hackernews_module
from plugins.hackernews import HackerNews, HackerNewsInvalidInputException
from tests import PluginTest


class HackerNewsTest(PluginTest):
    """Tests for hackernews plugin"""

    def setUp(self):

        self.hackernews = self.load_plugin(HackerNews)

    def test_list_titles(self):
        # Offline: a trimmed copy of the front page's current markup.
        page = "".join(
            '<tr class="athing"><td class="title"><span class="titleline">'
            '<a href="https://example.com/{0}">Story {0}</a></span></td></tr>'.format(i)
            for i in range(1, 31))
        response = mock.Mock(content=page.encode(), raise_for_status=lambda: None)
        with mock.patch.object(hackernews_module.requests, "get", return_value=response):
            titles = self.hackernews._list_titles(self.jarvis_api)

        self.assertIsInstance(titles, list)
        self.assertEqual(len(titles), 30)
        self.assertEqual(titles[0], ("Story 1", "https://example.com/1"))

    def test_get_selected_titles(self):

        self.queue_input("3 17 29")
        indexes = self.hackernews._get_selected_titles(self.jarvis_api)

        self.assertIsInstance(indexes, set)
        self.assertEqual(len(indexes), 3)

        for index in indexes:
            self.assertGreaterEqual(index, 1)
            self.assertLessEqual(index, 30)

    def test_get_selected_titles_repeated_values(self):

        self.queue_input("1 3 10 10 13 13 29")
        indexes = self.hackernews._get_selected_titles(self.jarvis_api)

        self.assertIsInstance(indexes, set)
        self.assertEqual(len(indexes), 5)
        self.assertEqual(indexes, {1, 3, 10, 13, 29})

    def test_get_selected_titles_invalid_values(self):

        self.queue_input("1 aa 5 bb 7")
        indexes = self.hackernews._get_selected_titles(self.jarvis_api)

        self.assertIsInstance(indexes, set)
        self.assertEqual(len(indexes), 3)
        self.assertEqual(indexes, {1, 5, 7})

    def test_get_selected_titles_no_input(self):

        with self.assertRaises(HackerNewsInvalidInputException):
            self.queue_input("")
            indexes = self.hackernews._get_selected_titles(self.jarvis_api)

    def test_get_selected_titles_invalid_range(self):

        with self.assertRaises(HackerNewsInvalidInputException):
            self.queue_input("33")
            indexes = self.hackernews._get_selected_titles(self.jarvis_api)


if __name__ == "__main__":
    unittest.main()
