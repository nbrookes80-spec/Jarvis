from plugin import plugin, complete, require

from packages import wiki_api


@require(network=True)
@complete("search", "summary", "content")
@plugin('wiki')
class Wiki():
    """
    Look things up on Wikipedia.
    wiki search <subject>    related pages
    wiki summary <subject>   the opening paragraph
    wiki content <subject>   the full article text
    wiki <subject>           same as summary
    """

    def __call__(self, jarvis, s):
        k = s.split(' ', 1)
        if not s.strip():
            jarvis.say(
                "Do you mean:\n"
                "1. wiki search <subject>\n"
                "2. wiki summary <subject>\n"
                "3. wiki content <subject>")
            return
        if k[0] in ("search", "summary", "content") and len(k) > 1:
            action, subject = k[0], k[1]
        else:
            action, subject = "summary", s     # "wiki albert einstein"

        try:
            data = getattr(self, action)(subject)
        except wiki_api.WikiError as error:
            jarvis.say(str(error))
            return

        if isinstance(data, list):
            jarvis.say("Did you mean one of these pages?")
            for number, title in enumerate(data, 1):
                jarvis.say("{}: {}".format(number, title))
        else:
            jarvis.say(data)

    def search(self, query, count=10):
        """Titles of up to `count` related pages."""
        items = wiki_api.search(query, count)
        return items or "No articles with that name, try another item."

    def summary(self, query, sentences=0):
        """Plain-text opening section of the query's page."""
        return self._page(query, intro_only=True, sentences=sentences or None)

    def content(self, title):
        """Plain-text content of the page, without images and tables."""
        return self._page(title)

    def _page(self, title, **kwargs):
        try:
            return wiki_api.page(title, **kwargs)['text']
        except KeyError:
            return "No page matches, try another item."
        except wiki_api.Disambiguation as error:
            return error.options[:5]
