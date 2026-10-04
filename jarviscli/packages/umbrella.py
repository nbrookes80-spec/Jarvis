# -*- coding: utf-8 -*-
from colorama import Fore

from . import geo


def main(city=None):
    try:
        print(Fore.CYAN + geo.umbrella_advice(geo.resolve(city or None)) + Fore.RESET)
    except geo.GeoError as e:
        print(Fore.RED + str(e) + Fore.RESET)
