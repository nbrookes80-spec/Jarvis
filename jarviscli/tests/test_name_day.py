import datetime
from unittest import mock

import plugins.name_day as name_day_module
from plugins.name_day import NameDay
from tests import PluginTest

GREEK_DAYS = {(17, 3): "Alekos, Alexios, Alexis", (18, 11): "Platonas"}


def fake_fetch(path, params=None, json=None):
    """V2 API shapes: every country per day; getname is a list of entries."""
    if path == "/today":
        return {"gr": "Platonas", "bg": "n/a"}
    if path == "/date":
        names = GREEK_DAYS.get((params["day"], params["month"]), "n/a")
        return {"gr": names, "bg": "n/a"}
    if path == "/getname":
        if json["name"] == "Alexios":
            return [{"country": "gr", "0": {"day": 17, "month": 3, "name": "Alekos, Alexios, Alexis"}}]
        return []
    raise AssertionError(path)


@mock.patch.object(name_day_module, "fetch", side_effect=fake_fetch)
class TestNameDay(PluginTest):
    def setUp(self):
        self.plugin = self.load_plugin(NameDay)
        self.plugin.location = "Greece"
        self.plugin.jarvis = self.jarvis_api

    def test_today(self, _):
        self.plugin.today()
        self.assertEqual(self.history_say().last_text(), "Say some kind words to Platonas")

    def test_tomorrow_asks_for_the_next_date(self, fetch):
        self.plugin.tomorrow()
        tomorrow = datetime.date.today() + datetime.timedelta(days=1)
        fetch.assert_called_with("/date", {"day": tomorrow.day, "month": tomorrow.month})

    def test_specific_date(self, _):
        self.queue_input("17/3")
        self.plugin.specific_date()
        self.assertEqual(self.history_say().last_text(),
                         "Say some kind words to Alekos, Alexios, Alexis on 17/3")

    def test_specific_date_without_names(self, _):
        self.queue_input("1/1")
        self.plugin.specific_date()
        self.assertEqual(self.history_say().last_text(), "No name days at 1/1 in Greece")

    def test_specific_name(self, _):
        self.queue_input("Alexios")
        self.plugin.specific_name()
        self.assertEqual(self.history_say().last_text(), "Say some kind words to Alexios at 17/3")

    def test_unknown_name(self, _):
        self.queue_input("Zzyzx")
        self.plugin.specific_name()
        self.assertEqual(self.history_say().last_text(), "No name days found for Zzyzx")
