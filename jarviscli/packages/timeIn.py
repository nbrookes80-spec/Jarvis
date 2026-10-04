# -*- coding: utf-8 -*-
from colorama import Fore

from . import geo


def main(self, s):
    """Current time in the place named in s, e.g. 'in Tokyo'.

    Used to need a Google Geocoding key in data/key_timein.json plus a
    TimeZoneDB key; the place's time zone now comes from Open-Meteo's
    geocoder and the time is computed locally.
    """
    place = geo.place_from_text(s)
    try:
        target = geo.find_place(place) if place else geo.here_as_place()
        print(Fore.MAGENTA + geo.describe_time(target) + Fore.RESET)
    except geo.GeoError as e:
        print(Fore.RED + str(e) + Fore.RESET)
