import datetime
import re

import requests
from colorama import Fore

from packages import geo
from plugin import plugin, require

# Version 1 of this API was retired (404). V2 returns every country in one
# response; name lookups are POST-only.
API = "https://nameday.abalin.net/api/V2"
HEADERS = {"User-Agent": "Jarvis-AI/1.0 (https://github.com/nbrookes80-spec/Jarvis)"}


def fetch(path, params=None, json=None):
    """The "data" member of an API response; raises ValueError on failure."""
    try:
        if json is not None:
            r = requests.post(API + path, json=json, headers=HEADERS, timeout=15)
        else:
            r = requests.get(API + path, params=params, headers=HEADERS, timeout=15)
        body = r.json()
    except (requests.RequestException, ValueError):
        raise ValueError("I couldn't reach the name day service.")
    if not body.get("success"):
        raise ValueError(body.get("message") or "The name day service returned an error.")
    return body["data"]


@require(network=True)
@plugin("name day")
class NameDay:
    """
    Name Day plugin provides information about your country's name days

    You can see today's, tomorrow's, or any other day's name day.

    You can also see the name day of a specific name.
    """
    def __call__(self, jarvis, s):
        self.jarvis = jarvis
        self.main()

    def __init__(self):
        self.jarvis = None
        self.location = ""
        self.countries = {
            "Austria": "at",
            "Bulgaria": "bg",
            "Croatia": "hr",
            "Czech Republic": "cz",
            "Denmark": "dk",
            "Estonia": "ee",
            "Finland": "fi",
            "France": "fr",
            "Germany": "de",
            "Greece": "gr",
            "Hungary": "hu",
            "Italy": "it",
            "Latvia": "lv",
            "Lithuania": "lt",
            "Poland": "pl",
            "Russia": "ru",
            "Slovakia": "sk",
            "Spain": "es",
            "Sweden": "se",
            "United States": "us"
        }

    def main(self):

        if self.location == "":
            self.get_location()
        while True:
            # main menu
            self.jarvis.say("It appears you are in " + self.location, color=Fore.BLUE)
            self.jarvis.say("1 See Today's name days")
            self.jarvis.say("2 See Tomorrow's name days")
            self.jarvis.say("3 Chose specific date")
            self.jarvis.say("4 Chose specific name")
            self.jarvis.say("5 Chose an other country")
            self.jarvis.say("6 Exit")

            # get user input
            try:
                inp = int(self.jarvis.input("Select the desired number: ", color=Fore.GREEN))
            except ValueError:
                self.jarvis.say("Please select a number")
                continue

            # handle input
            lookups = {1: self.today, 2: self.tomorrow,
                       3: self.specific_date, 4: self.specific_name}
            if inp in lookups:
                try:
                    lookups[inp]()
                except ValueError as error:     # the service is unreachable
                    self.jarvis.say(str(error), Fore.RED)
            elif inp == 5:
                self.change_country()
                continue
            elif inp == 6:
                break
            else:
                self.jarvis.say("Please select a valid number")

            # ask user if he wants to continue
            inp = self.jarvis.input("Do you want to continue? (Y/N)", color=Fore.RED)
            if inp.lower() == "n":
                break

    def get_country_code(self):
        """Return the two letter country code"""
        return self.countries[self.location]

    def get_location(self):
        """
        Get the location of the user.
        If the user is in a supported country, the country is saved in location class variable.
        otherwise, the user is asked to enter a country from the supported list.
        """
        self.jarvis.say("Getting Location ... ")
        try:
            loc = geo.locate_me()["country_name"]
        except geo.GeoError:
            loc = "an unknown country"

        if loc in self.countries.keys():
            self.location = loc
        else:
            self.jarvis.say("It appears you are in " + loc)
            self.jarvis.say("Your Country is not supported")
            self.jarvis.say("Please chose an other country")
            self.change_country()

    def today(self):
        """
        Show the name days for today.
        """
        country_code = self.get_country_code()
        names = self._names(fetch("/today", {"timezone": self._timezone()}), country_code)
        if names:
            self.jarvis.say("Say some kind words to " + names)
        else:
            self.jarvis.say("No name days today in " + str(self.location))

    def tomorrow(self):
        """
        Show the name days for tomorrow.
        """
        country_code = self.get_country_code()
        tomorrow = datetime.date.today() + datetime.timedelta(days=1)
        names = self._names(fetch("/date", {"day": tomorrow.day, "month": tomorrow.month}),
                            country_code)
        if names:
            self.jarvis.say("Say some kind words to " + names)
        else:
            self.jarvis.say("No name days for tomorrow in " + str(self.location))

    def specific_date(self):
        """
        Show the name days for a specific date.
        """
        country_code = self.get_country_code()
        self.jarvis.say("Please enter day/month")
        try:
            day, month = re.split(r'[ /-]+', self.jarvis.input().strip())
            self.check_if_date_is_valid(day, month)
        except ValueError:
            self.specific_date()
            return
        names = self._names(fetch("/date", {"day": int(day), "month": int(month)}),
                            country_code)
        if names:
            self.jarvis.say("Say some kind words to " + names + " on " + day + "/" + month)
        else:
            self.jarvis.say("No name days at " + day + "/" + month + " in " + self.location)

    def specific_name(self):
        """
        Show the name days for a specific name.
        """
        country_code = self.get_country_code()
        self.jarvis.say("Please enter name")
        name = self.jarvis.input().strip()
        data = fetch("/getname", json={"name": name, "country": country_code})

        # the same name may have several name days: entries "0", "1", ...
        days = []
        for entry in data:
            if entry.get("country") != country_code:
                continue
            for key, value in entry.items():
                if key != "country" and isinstance(value, dict):
                    days.append("{}/{}".format(value["day"], value["month"]))
        if days:
            self.jarvis.say("Say some kind words to " + name + " at " + ", ".join(days))
        else:
            self.jarvis.say("No name days found for " + name)

    @staticmethod
    def _names(data, country_code):
        names = data.get(country_code, "n/a")
        return "" if names in ("n/a", "", None) else names

    @staticmethod
    def _timezone():
        try:
            return geo.locate_me()["timezone"]
        except geo.GeoError:
            return "UTC"

    def change_country(self):
        """
        Change the location of the user manually.
        """
        self.jarvis.say("Select your country number from the list below:")
        for i, key in enumerate(self.countries.keys(), start=1):
            self.jarvis.say(str(i) + " " + key)
        self.jarvis.say(str(len(self.countries) + 1) + " Cancel")

        while True:
            country = int(self.jarvis.input("Select your country number: "))
            if country in range(1, len(self.countries) + 2):
                break
            else:
                self.jarvis.say("Please select a valid country number")

        if country == len(self.countries) + 1:
            return
        self.location = list(self.countries.keys())[country - 1]

    def check_if_date_is_valid(self, day, month):
        """
        Check if the date taken for user is valid.
        :raise ValueError: if the date is invalid.
        """
        day = int(day)
        month = int(month)
        m31 = [1, 3, 5, 7, 8, 10, 12]
        m30 = [4, 6, 9, 11]
        if month in m31:
            if 0 > day or day > 31:
                self.jarvis.say("Please enter a valid date")
                raise ValueError
        elif month in m30:
            if 0 > day or day > 30:
                self.jarvis.say("Please enter a valid date")
                raise ValueError
        elif month == 2:
            if 0 > day or day > 29:
                self.jarvis.say("Please enter a valid date")
                raise ValueError
        else:
            self.jarvis.say("Please enter a valid date")
            raise ValueError
