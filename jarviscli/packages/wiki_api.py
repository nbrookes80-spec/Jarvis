# -*- coding: utf-8 -*-
"""Minimal Wikipedia client on the MediaWiki API.

The `wikipedia` package sends a default user agent, which Wikipedia now
rejects with an HTML error page (seen as a JSON decode error). Calling the
API directly with an identifying User-Agent works and needs no key.
"""
import requests

API = 'https://en.wikipedia.org/w/api.php'
HEADERS = {'User-Agent': 'Jarvis-AI/1.0 (https://github.com/nbrookes80-spec/Jarvis)'}
TIMEOUT = 15


class WikiError(Exception):
    """Lookup failed; the message is fit to show the user."""


class Disambiguation(Exception):
    """The title names several pages; .options lists some of them."""

    def __init__(self, title, options):
        super().__init__(title)
        self.options = options


def _get(params):
    params = dict(params, format='json', formatversion=2)
    try:
        return requests.get(API, params=params, headers=HEADERS, timeout=TIMEOUT).json()
    except (requests.RequestException, ValueError):
        raise WikiError("I couldn't reach Wikipedia.")


def search(query, limit=10):
    """Titles of the best matching pages, best first."""
    hits = _get({'action': 'query', 'list': 'search', 'srsearch': query,
                 'srlimit': limit}).get('query', {}).get('search', [])
    return [h['title'] for h in hits]


def page(title, intro_only=False, sentences=None):
    """{'title', 'url', 'text'} for a page; follows redirects.

    Raises KeyError if there is no such page, Disambiguation for a
    disambiguation page.
    """
    params = {'action': 'query', 'titles': title, 'redirects': 1,
              'prop': 'extracts|info|pageprops', 'inprop': 'url',
              'ppprop': 'disambiguation', 'explaintext': 1}
    if intro_only:
        params['exintro'] = 1
    if sentences:
        params['exsentences'] = sentences
    pages = _get(params).get('query', {}).get('pages', [])
    if not pages or pages[0].get('missing') or pages[0].get('invalid'):
        raise KeyError(title)
    p = pages[0]
    if 'disambiguation' in p.get('pageprops', {}):
        links = _get({'action': 'query', 'titles': p['title'], 'prop': 'links',
                      'pllimit': 50, 'plnamespace': 0}).get('query', {}).get('pages', [{}])
        options = [link['title'] for link in links[0].get('links', [])]
        # Links come back alphabetically; "Mercury (planet)" beats "Anna Kavan".
        word = p['title'].lower()
        options.sort(key=lambda o: (word not in o.lower(), o))
        raise Disambiguation(p['title'], options)
    return {'title': p['title'], 'url': p.get('fullurl', ''), 'text': p.get('extract', '')}
