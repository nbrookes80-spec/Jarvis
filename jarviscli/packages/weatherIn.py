# -*- coding: utf-8 -*-
from colorama import Fore

from packages import weather_pinpoint as pinpoint
from packages.memory.memory import Memory
from . import geo, umbrella


def main(self, s):
    """Weather for the place named in s, e.g. 'in Paris' or 'like in Rome today'."""
    place = geo.place_from_text(s)
    if 'umbrella' in s.lower():
        return umbrella.main(place or Memory().get_data('city'))
    if not place:
        # "what's the weather like": no place named, so use the saved/current one
        return pinpoint.main(Memory(), self, s)
    try:
        print(Fore.BLUE + geo.describe_weather(geo.find_place(place)) + Fore.RESET)
    except geo.GeoError as e:
        print(Fore.RED + str(e) + Fore.RESET)
