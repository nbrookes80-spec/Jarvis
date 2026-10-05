import unittest
from unittest import mock

from plugins.cocktail import Cocktail
from tests import PluginTest


class CocktailTest(PluginTest):
    def setUp(self):
        self.test = self.load_plugin(Cocktail)
        self.test.jarvis = self.jarvis_api

    def test_has_base_ingredients(self):
        self.assertIn("Gin", self.test.ingredients)
        self.assertGreater(len(self.test.ingredients), 10)

    def test_cocktails_by_ingredient(self):
        drinks = {"drinks": [{"strDrink": "Negroni"}, {"strDrink": "Gimlet"}]}
        with mock.patch.object(self.test, "get_json", return_value=drinks) as get_json:
            gin = self.test.ingredients.index("Gin")
            self.assertEqual(self.test.get_cocktails_by_ingredient(gin), ["Negroni", "Gimlet"])
        self.assertTrue(get_json.call_args[0][0].endswith("filter.php?i=Gin"))

    def test_out_of_range_input_is_asked_again(self):
        self.queue_input("700")
        self.queue_input("-10")
        self.queue_input("3")
        self.assertEqual(self.test.get_input("Base Ingredient", 24), 3)

    def test_exit_input(self):
        self.queue_input("exit")
        self.assertEqual(self.test.get_input("Base Ingredient", 24), "exit")

    def test_is_out_of_range(self):
        self.assertTrue(self.test.is_out_of_range(25, 24))
        self.assertTrue(self.test.is_out_of_range(0, 24))
        self.assertFalse(self.test.is_out_of_range(10, 24))


if __name__ == '__main__':
    unittest.main()
