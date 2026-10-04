# -*- coding: utf-8 -*-
from colorama import Fore

from . import geo


def main(jarvis, s):
    place = geo.place_from_text(s)
    try:
        jarvis.say(geo.describe_forecast(geo.resolve(place)), Fore.BLUE)
    except geo.GeoError as e:
        jarvis.say(str(e), Fore.RED)
