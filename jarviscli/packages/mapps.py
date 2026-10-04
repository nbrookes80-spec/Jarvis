# -*- coding: utf-8 -*-
import json
import webbrowser
import requests
from colorama import Fore

from . import geo


def get_location():
    """This machine's approximate location (see packages/geo.py)."""
    return geo.locate_me()


def directions(to_city, from_city=0):
    if not from_city:
        from_city = get_location()['city']
    url = "https://www.google.com/maps/dir/{0}/{1}".format(from_city, to_city)
    webbrowser.open(url)


def locate_me():
    hcity = get_location()['city']
    print(Fore.BLUE + "You are at " + hcity + Fore.RESET)


def weather(city=None):
    try:
        print(Fore.BLUE + geo.describe_weather(geo.resolve(city)) + Fore.RESET)
    except geo.GeoError as e:
        print(Fore.RED + str(e) + Fore.RESET)
        return False
    return True


def search_near(things, city=0):
    if city:
        print("{COLOR}Hold on! I'll show {THINGS} near {CITY}{COLOR_RESET}"
              .format(COLOR=Fore.GREEN, COLOR_RESET=Fore.RESET,
                      THINGS=things, CITY=city))
        url = "https://www.google.com/maps/search/{0}+near+{1}".format(
            things, city)
    else:
        print("{COLOR}Hold on!, I'll show {THINGS} near you{COLOR_RESET}"
              .format(COLOR=Fore.GREEN, COLOR_RESET=Fore.RESET, THINGS=things))
        url = "https://www.google.com/maps/search/{0}/@{1},{2}".format(
            things, get_location()['latitude'], get_location()['longitude'])
    webbrowser.open(url)
