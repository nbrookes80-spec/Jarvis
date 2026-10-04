# -*- coding: utf-8 -*-
from colorama import Fore

from . import geo, umbrella


def main(memory, self, s):
    """Weather where you are: your saved city if set, else located by IP.

    Set a city with the 'update location' command. Earlier versions asked
    "It appears you are in X, is this correct? (y/n)" on first use and on every
    change of network, which is awkward to answer by voice; the IP location is
    now just used, and said, so a wrong guess is obvious.
    """
    city = memory.get_data('city')
    if 'umbrella' in s:
        return umbrella.main(city)
    try:
        place = geo.find_place(city) if city else geo.here_as_place()
        print(Fore.BLUE + geo.describe_weather(place) + Fore.RESET)
    except geo.GeoError as e:
        print(Fore.RED + str(e) + Fore.RESET)
