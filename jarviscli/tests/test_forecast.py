# -*- coding: utf-8 -*-
"""Location, time and weather (packages/geo.py), with the network mocked."""
import datetime
import unittest
from unittest import mock

from packages import geo

PLACES = {
    'london': [
        {'name': 'London', 'latitude': 42.98, 'longitude': -81.23, 'timezone': 'America/Toronto',
         'country': 'Canada', 'country_code': 'CA', 'admin1': 'Ontario', 'population': 346765},
        {'name': 'London', 'latitude': 51.51, 'longitude': -0.13, 'timezone': 'Europe/London',
         'country': 'United Kingdom', 'country_code': 'GB', 'admin1': 'England',
         'population': 8961989},
    ],
    'paris': [
        {'name': 'Paris', 'latitude': 48.85, 'longitude': 2.35, 'timezone': 'Europe/Paris',
         'country': 'France', 'country_code': 'FR', 'admin1': 'Île-de-France',
         'population': 2138551},
        {'name': 'Paris', 'latitude': 33.66, 'longitude': -95.56, 'timezone': 'America/Chicago',
         'country': 'United States', 'country_code': 'US', 'admin1': 'Texas',
         'population': 24782},
    ],
}

FORECAST = {
    'current': {'temperature_2m': 14.6, 'apparent_temperature': 11.2,
                'relative_humidity_2m': 90, 'weather_code': 61, 'wind_speed_10m': 6.4},
    'daily': {'time': ['2026-10-05', '2026-10-06', '2026-10-07'],
              'weather_code': [61, 3, 0],
              'temperature_2m_max': [22.2, 27.4, 19.0],
              'temperature_2m_min': [13.1, 15.0, 12.5],
              'precipitation_probability_max': [65, 12, 0]},
}


def fake_get_json(url, params=None, attempts=2):
    if 'geocoding' in url:
        return {'results': PLACES.get(params['name'], [])}
    if 'forecast' in url:
        days = params['forecast_days']
        out = {'current': FORECAST['current'],
               'daily': {k: v[:days] for k, v in FORECAST['daily'].items()}}
        return out
    if 'ip-api' in url:
        return {'status': 'success', 'city': 'Sydney', 'regionName': 'New South Wales',
                'country': 'Australia', 'countryCode': 'AU', 'lat': -33.87, 'lon': 151.21,
                'timezone': 'Australia/Sydney'}
    raise AssertionError('unexpected URL ' + url)


@mock.patch.object(geo, '_get_json', side_effect=fake_get_json)
class GeoTest(unittest.TestCase):

    def setUp(self):
        geo._search.cache_clear()
        geo._location = None

    def test_most_populous_match_wins(self, _):
        self.assertEqual(geo.find_place('London')['label'], 'London, United Kingdom')

    def test_region_hint_selects_match(self, _):
        self.assertEqual(geo.find_place('Paris, Texas')['label'], 'Paris, Texas, United States')

    def test_unknown_place(self, _):
        with self.assertRaises(geo.GeoError):
            geo.find_place('Atlantis')

    def test_locate_me_keeps_old_ipstack_keys(self, _):
        me = geo.locate_me()
        self.assertEqual((me['city'], me['country_name'], me['time_zone']['id']),
                         ('Sydney', 'Australia', 'Australia/Sydney'))

    def test_weather_sentence(self, _):
        text = geo.describe_weather(geo.find_place('London'))
        self.assertEqual(text, "It's 15°C and light rain in London, United Kingdom, "
                               "feels like 11°C. Today: high 22°C, low 13°C, 65% chance of rain.")

    def test_fahrenheit_in_the_us(self, mocked):
        geo.describe_weather(geo.find_place('Paris, Texas'))
        params = mocked.call_args[1]['params']
        self.assertEqual(params['temperature_unit'], 'fahrenheit')

    def test_forecast_lines(self, _):
        lines = geo.describe_forecast(geo.find_place('London'), days=3).splitlines()
        self.assertEqual(lines[0], '3-day forecast for London, United Kingdom:')
        self.assertTrue(lines[1].startswith('Today'))
        self.assertTrue(lines[2].startswith('Tomorrow'))
        self.assertEqual(len(lines), 4)

    def test_umbrella(self, _):
        self.assertTrue(geo.umbrella_advice(geo.find_place('London')).startswith('Take an umbrella'))

    def test_time_in_place_uses_its_zone(self, _):
        now = geo.time_in(geo.find_place('London'))
        self.assertEqual(now.tzinfo.key, 'Europe/London')
        self.assertLess(abs((now - datetime.datetime.now(datetime.timezone.utc)).total_seconds()), 5)

    def test_place_extracted_from_phrases(self, _):
        cases = {
            'what time is it in tokyo': 'tokyo',
            "what's the weather like in rome today": 'rome',
            'weather like': '',
            'do i need an umbrella in london': 'london',
            'for new york': 'new york',
        }
        for phrase, place in cases.items():
            self.assertEqual(geo.place_from_text(phrase), place, phrase)

    def test_spoken_offsets(self, _):
        self.assertEqual([geo._spoken_hours(h) for h in (0.5, 1, 1.5, 5.75)],
                         ['half an hour', '1 hour', 'an hour and a half', '5 hours 45 minutes'])


if __name__ == '__main__':
    unittest.main()
