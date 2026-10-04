import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from packages import geo, weather_pinpoint, weatherIn


class WeatherInTest(unittest.TestCase):
    def test_no_place_named_uses_your_location(self):
        with patch.object(weather_pinpoint, 'main') as pinpoint_mock:
            weatherIn.main(self, 'weather')
            self.assertTrue(pinpoint_mock.called)

    def test_unknown_place_is_reported_not_replaced(self):
        # Earlier versions silently showed the weather where you are instead,
        # which reads as an answer for the place you asked about.
        geo._search.cache_clear()
        out = io.StringIO()
        with patch.object(geo, '_get_json', return_value={'results': []}), \
                patch.object(weather_pinpoint, 'main') as pinpoint_mock, redirect_stdout(out):
            weatherIn.main(self, 'weather in UnknownLocationhjbahbchjba')
        self.assertFalse(pinpoint_mock.called)
        self.assertIn("couldn't find a place called", out.getvalue())


if __name__ == '__main__':
    unittest.main()
