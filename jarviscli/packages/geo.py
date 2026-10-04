# -*- coding: utf-8 -*-
"""Location, place lookup, local time and weather, with no API keys.

The original packages used ipstack, Google Geocoding, TimeZoneDB and
OpenWeatherMap, each with a key hardcoded in the source and shared by every
install. ipstack's ran out ("usage_limit_reached"), which crashed every
weather command; the Google one was never filled in, so "check time in X"
never worked. This module replaces them with services that need no key:

  * where am I:        ip-api.com, falling back to ipinfo.io
  * where is <place>:  Open-Meteo geocoding (also gives its time zone)
  * weather:           Open-Meteo forecast API
  * time in <place>:   the place's time zone, computed locally (zoneinfo)

Open-Meteo is free for non-commercial use (data CC BY 4.0, open-meteo.com).
"""
import datetime
import functools
import re

import requests

try:
    from zoneinfo import ZoneInfo
except ImportError:     # Python < 3.9
    ZoneInfo = None

TIMEOUT = 8
_location = None

# WMO weather interpretation codes, as used by Open-Meteo.
WMO = {
    0: 'clear', 1: 'mainly clear', 2: 'partly cloudy', 3: 'overcast',
    45: 'fog', 48: 'freezing fog',
    51: 'light drizzle', 53: 'drizzle', 55: 'heavy drizzle',
    56: 'freezing drizzle', 57: 'heavy freezing drizzle',
    61: 'light rain', 63: 'rain', 65: 'heavy rain',
    66: 'freezing rain', 67: 'heavy freezing rain',
    71: 'light snow', 73: 'snow', 75: 'heavy snow', 77: 'snow grains',
    80: 'light showers', 81: 'showers', 82: 'violent showers',
    85: 'snow showers', 86: 'heavy snow showers',
    95: 'thunderstorms', 96: 'thunderstorms with hail',
    99: 'severe thunderstorms with hail',
}

# Countries where the state/province is part of how a place is named
# ("Paris, Texas"); elsewhere "London, United Kingdom" is clearer spoken.
WITH_REGION = {'US', 'CA', 'AU', 'IN', 'BR', 'MX'}

# Countries that report in Fahrenheit.
FAHRENHEIT = {'US', 'LR', 'MM', 'BS', 'BZ', 'KY', 'PW'}


class GeoError(Exception):
    """A lookup failed; the message is fit to show the user."""


def _get_json(url, params=None, attempts=2):
    """GET with one retry: these free services occasionally stall."""
    last = None
    for attempt in range(attempts):
        try:
            return requests.get(url, params=params,
                                timeout=TIMEOUT * (attempt + 1)).json()
        except (requests.RequestException, ValueError) as e:
            last = e
    raise last


def describe(code):
    return WMO.get(code, 'unknown conditions')


# ------------------------------------------------------------------ location

def locate_me(refresh=False):
    """Approximate location of this machine from its public IP.

    Returns keys compatible with the old ipstack response, so existing
    callers (mapps.get_location()['city'] etc.) keep working.
    """
    global _location
    if _location is not None and not refresh:
        return _location

    loc = None
    try:
        j = _get_json('http://ip-api.com/json/', params={
            'fields': 'status,city,regionName,country,countryCode,lat,lon,timezone'})
        if j.get('status') == 'success':
            loc = {'city': j['city'], 'region_name': j['regionName'],
                   'country_name': j['country'], 'country_code': j['countryCode'],
                   'latitude': j['lat'], 'longitude': j['lon'],
                   'timezone': j['timezone']}
    except (requests.RequestException, ValueError, KeyError):
        pass

    if loc is None:
        try:
            j = _get_json('https://ipinfo.io/json')
            lat, lon = (float(x) for x in j['loc'].split(','))
            loc = {'city': j['city'], 'region_name': j.get('region', ''),
                   'country_name': j['country'], 'country_code': j['country'],
                   'latitude': lat, 'longitude': lon,
                   'timezone': j.get('timezone')}
        except (requests.RequestException, ValueError, KeyError):
            raise GeoError("I couldn't work out where you are. "
                           "Try naming a place, e.g. 'weather in Sydney'.")

    loc['time_zone'] = {'id': loc['timezone']}      # ipstack shape
    _location = loc
    return loc


def find_place(name):
    """Look a place up by name. Returns dict with name, lat/lon, timezone."""
    name = name.strip(' ,.?!')
    if not name:
        raise GeoError('Which place?')
    # "Paris, France" -> search "Paris", prefer results in France.
    head, _, hint = name.partition(',')
    try:
        results = list(_search(head.strip().lower()))
    except (requests.RequestException, ValueError):
        raise GeoError("I couldn't reach the place lookup service.")
    if not results and not hint and ' ' in head.strip():
        # Commas are stripped before commands reach plugins, so "Paris, Texas"
        # arrives as "paris texas": retry with the last word as the hint.
        first, _, last = head.strip().rpartition(' ')
        try:
            return find_place('%s, %s' % (first, last))
        except GeoError:
            pass
    if not results:
        raise GeoError("I couldn't find a place called %s." % name.title())

    hint = hint.strip().lower()
    if hint:
        for res in results:
            if hint in (res.get('country', '').lower(), res.get('country_code', '').lower(),
                        res.get('admin1', '').lower()):
                return _place(res)
        if ',' in name and len(results) and not any(
                hint in (r.get('country', '') + r.get('admin1', '')).lower() for r in results):
            raise GeoError("I couldn't find %s." % name.title())
    # Otherwise the most populous match: "London" means the one in England.
    results.sort(key=lambda res: res.get('population') or 0, reverse=True)
    return _place(results[0])


@functools.lru_cache(maxsize=256)
def _search(name):
    """Place search, cached: places do not move, and the service can be slow."""
    return tuple(_get_json('https://geocoding-api.open-meteo.com/v1/search',
                           params={'name': name, 'count': 10,
                                   'language': 'en'}).get('results') or [])


def _place(res):
    parts = [res['name']]
    if res.get('admin1') and res['admin1'] != res['name'] \
            and res.get('country_code', '').upper() in WITH_REGION:
        parts.append(res['admin1'])
    if res.get('country'):
        parts.append(res['country'])
    return {'name': res['name'], 'label': ', '.join(parts),
            'latitude': res['latitude'], 'longitude': res['longitude'],
            'timezone': res.get('timezone'),
            'country_code': res.get('country_code', '')}


def here_as_place():
    me = locate_me()
    return {'name': me['city'], 'label': me['city'],
            'latitude': me['latitude'], 'longitude': me['longitude'],
            'timezone': me['timezone'], 'country_code': me['country_code']}


def resolve(name=None):
    """A named place, or this machine's location when no name is given."""
    return find_place(name) if name and name.strip() else here_as_place()


# ---------------------------------------------------------------------- time

def time_in(place):
    if ZoneInfo is None or not place.get('timezone'):
        raise GeoError("I don't know the time zone for %s." % place['name'])
    return datetime.datetime.now(ZoneInfo(place['timezone']))


def _spoken_hours(h):
    whole, minutes = int(h), int(round((h - int(h)) * 60))
    if not whole:
        return 'half an hour' if minutes == 30 else '%d minutes' % minutes
    text = '%d hour%s' % (whole, '' if whole == 1 else 's')
    if minutes == 30:
        return 'an hour and a half' if whole == 1 else '%d and a half hours' % whole
    if minutes:
        text += ' %d minutes' % minutes
    return text


def describe_time(place):
    now = time_in(place)
    local = datetime.datetime.now().astimezone()
    diff = (now.utcoffset() - local.utcoffset()).total_seconds() / 3600.0
    if abs(diff) < 0.01:
        rel = 'the same as here'
    else:
        rel = '%s %s' % (_spoken_hours(abs(diff)),
                         'ahead of here' if diff > 0 else 'behind here')
    clock = now.strftime('%I:%M %p').lstrip('0')
    return "It's %s on %s in %s (%s)." % (
        clock, now.strftime('%A %d %B').replace(' 0', ' '), place['label'], rel)


# ------------------------------------------------------------------- weather

def _forecast(place, days):
    imperial = place.get('country_code', '').upper() in FAHRENHEIT
    params = {
        'latitude': place['latitude'], 'longitude': place['longitude'],
        'current': 'temperature_2m,apparent_temperature,relative_humidity_2m,'
                   'weather_code,wind_speed_10m',
        'daily': 'weather_code,temperature_2m_max,temperature_2m_min,'
                 'precipitation_probability_max',
        'timezone': 'auto', 'forecast_days': days,
    }
    if imperial:
        params.update(temperature_unit='fahrenheit', wind_speed_unit='mph')
    try:
        j = _get_json('https://api.open-meteo.com/v1/forecast', params=params)
    except (requests.RequestException, ValueError):
        raise GeoError("I couldn't reach the weather service.")
    if 'current' not in j:
        raise GeoError('The weather service returned an error: %s'
                       % j.get('reason', 'unknown'))
    j['_unit'] = '°F' if imperial else '°C'
    j['_wind'] = 'mph' if imperial else 'km/h'
    return j


def describe_weather(place):
    j = _forecast(place, 1)
    c, d, u = j['current'], j['daily'], j['_unit']
    text = "It's %d%s and %s in %s" % (round(c['temperature_2m']), u,
                                       describe(c['weather_code']), place['label'])
    if abs(c['apparent_temperature'] - c['temperature_2m']) >= 2:
        text += ', feels like %d%s' % (round(c['apparent_temperature']), u)
    text += '. Today: high %d%s, low %d%s' % (
        round(d['temperature_2m_max'][0]), u, round(d['temperature_2m_min'][0]), u)
    rain = d['precipitation_probability_max'][0]
    if rain is not None:
        text += ', %d%% chance of rain' % rain
    return text + '.'


def describe_forecast(place, days=7):
    j = _forecast(place, days)
    d, u = j['daily'], j['_unit']
    lines = ['%d-day forecast for %s:' % (days, place['label'])]
    for i, day in enumerate(d['time']):
        date = datetime.date.fromisoformat(day)
        name = 'Today' if i == 0 else ('Tomorrow' if i == 1 else date.strftime('%A'))
        rain = d['precipitation_probability_max'][i]
        lines.append('%-9s %3d%s / %3d%s  %s%s' % (
            name, round(d['temperature_2m_max'][i]), u,
            round(d['temperature_2m_min'][i]), u, describe(d['weather_code'][i]),
            ', %d%% rain' % rain if rain else ''))
    return '\n'.join(lines)


def umbrella_advice(place):
    d = _forecast(place, 1)['daily']
    chance = d['precipitation_probability_max'][0] or 0
    wet = d['weather_code'][0] >= 51
    if chance >= 60 or (wet and chance >= 40):
        return 'Take an umbrella: %d%% chance of rain in %s today.' % (chance, place['label'])
    if chance >= 30:
        return 'Maybe take an umbrella: %d%% chance of rain in %s today.' % (chance, place['label'])
    return 'No umbrella needed in %s today: %d%% chance of rain.' % (place['label'], chance)


# --------------------------------------------------------- parsing requests

_FILLER = re.compile(
    r"\b(what'?s|what|is|it|the|like|weather|forecast|check|today|now|"
    r"currently|right|outside|please|tell|me|how|time|current|for|a|week|"
    r"umbrella|do|i|need|an)\b", re.IGNORECASE)


def place_from_text(text):
    """'what's the weather like in Paris today' -> 'Paris'; '' if none."""
    m = re.search(r'\b(?:in|at|for)\s+(.+)$', text, re.IGNORECASE)
    rest = m.group(1) if m else text
    rest = _FILLER.sub(' ', rest)
    return re.sub(r'\s+', ' ', rest).strip(' ,.?!')
