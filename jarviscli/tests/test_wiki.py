import unittest
from unittest import mock

import plugins.wiki as wiki
from packages import wiki_api
from tests import PluginTest


def fake_page(title, **kwargs):
    if title.lower() == 'obama':
        return {'title': 'Barack Obama', 'url': 'https://en.wikipedia.org/wiki/Barack_Obama',
                'text': 'Barack Hussein Obama II is an American politician.'}
    if title.lower() == 'mercury':
        raise wiki_api.Disambiguation('Mercury', ['Mercury (planet)', 'Mercury (element)',
                                                  'Mercury (mythology)', 'Mercury Records',
                                                  'Freddie Mercury', 'Mercury, Nevada'])
    raise KeyError(title)


@mock.patch.object(wiki_api, 'page', side_effect=fake_page)
@mock.patch.object(wiki_api, 'search', side_effect=lambda q, n=10: (
    ['Barack Obama'] + ['Barack %d' % i for i in range(n - 1)] if q == 'Barack' else []))
class WikiTest(PluginTest):

    def setUp(self):
        self.wiki = self.load_plugin(wiki.Wiki)

    def test_search(self, *_):
        d = self.wiki.search("Barack")
        self.assertIsInstance(d, list)
        self.assertEqual(len(d), 10)
        self.assertEqual(self.wiki.search("sldjflsfkdslfjsl"),
                         "No articles with that name, try another item.")

    def test_summary(self, *_):
        self.assertIn('Obama', self.wiki.summary("Obama"))
        self.assertEqual(self.wiki.summary("adfsklfdlksf"), "No page matches, try another item.")
        self.assertEqual(len(self.wiki.summary("mercury")), 5)

    def test_content(self, *_):
        self.assertIsInstance(self.wiki.content("Obama"), str)
        self.assertEqual(self.wiki.content("adfsklfdlksf"), "No page matches, try another item.")
        self.assertEqual(len(self.wiki.content("mercury")), 5)

    def test_bare_subject_means_summary(self, *_):
        self.wiki.run("obama")
        self.assertIn('Obama', self.history_say().last_text())

    def test_service_down_is_reported(self, search, page):
        page.side_effect = wiki_api.WikiError("I couldn't reach Wikipedia.")
        self.wiki.run("summary obama")
        self.assertEqual(self.history_say().last_text(), "I couldn't reach Wikipedia.")


if __name__ == '__main__':
    unittest.main()
