import unittest

from openroast.temperature import (
    DEFAULT_TARGET_TEMPERATURE_C,
    MAX_TEMPERATURE_C,
    MIN_TEMPERATURE_C,
    TEMP_UNIT_C,
    TEMP_UNIT_F,
    celsius_to_fahrenheit,
    celsius_to_temperature_unit,
    clamp_temperature_c,
    fahrenheit_to_celsius,
    normalize_temperature_unit,
    recipe_to_celsius,
    temperature_to_celsius,
)


class TemperatureHelpersTests(unittest.TestCase):
    def test_normalize_temperature_unit_accepts_c_and_f(self):
        self.assertEqual(normalize_temperature_unit(" c "), TEMP_UNIT_C)
        self.assertEqual(normalize_temperature_unit("f"), TEMP_UNIT_F)

    def test_normalize_temperature_unit_falls_back_to_default(self):
        self.assertEqual(normalize_temperature_unit(None, default=TEMP_UNIT_F), TEMP_UNIT_F)
        self.assertEqual(normalize_temperature_unit("kelvin", default=TEMP_UNIT_C), TEMP_UNIT_C)

    def test_conversion_helpers_round_trip(self):
        self.assertAlmostEqual(fahrenheit_to_celsius(212), 100.0)
        self.assertAlmostEqual(celsius_to_fahrenheit(100), 212.0)
        self.assertAlmostEqual(celsius_to_fahrenheit(fahrenheit_to_celsius(347)), 347.0)

    def test_temperature_to_celsius_uses_unit(self):
        self.assertEqual(temperature_to_celsius(200, TEMP_UNIT_C), 200.0)
        self.assertAlmostEqual(temperature_to_celsius(212, TEMP_UNIT_F), 100.0)

    def test_celsius_to_temperature_unit_uses_unit(self):
        self.assertEqual(celsius_to_temperature_unit(200, TEMP_UNIT_C), 200.0)
        self.assertAlmostEqual(celsius_to_temperature_unit(100, TEMP_UNIT_F), 212.0)

    def test_clamp_temperature_c_bounds_and_rounding(self):
        self.assertEqual(clamp_temperature_c(MIN_TEMPERATURE_C - 50), MIN_TEMPERATURE_C)
        self.assertEqual(clamp_temperature_c(MAX_TEMPERATURE_C + 50), MAX_TEMPERATURE_C)
        self.assertEqual(clamp_temperature_c(DEFAULT_TARGET_TEMPERATURE_C + 0.6), DEFAULT_TARGET_TEMPERATURE_C + 1)

    def test_clamp_temperature_c_accepts_custom_bounds(self):
        self.assertEqual(clamp_temperature_c(15, low=10, high=20), 15)
        self.assertEqual(clamp_temperature_c(7, low=10, high=20), 10)
        self.assertEqual(clamp_temperature_c(42, low=10, high=20), 20)


class RecipeToCelsiusTests(unittest.TestCase):
    def test_recipe_to_celsius_converts_legacy_fahrenheit_when_unit_missing(self):
        recipe = {
            "name": "legacy",
            "steps": [{"targetTemp": 212, "fanSpeed": 5}],
        }

        normalized = recipe_to_celsius(recipe)

        self.assertEqual(normalized["temperatureUnit"], TEMP_UNIT_C)
        self.assertEqual(normalized["steps"][0]["targetTemp"], 100)
        # Ensure function returns a copy and leaves original recipe untouched.
        self.assertNotEqual(id(normalized), id(recipe))
        self.assertEqual(recipe["steps"][0]["targetTemp"], 212)

    def test_recipe_to_celsius_keeps_celsius_values_as_is(self):
        recipe = {
            "temperatureUnit": TEMP_UNIT_C,
            "steps": [{"targetTemp": 180}, {"targetTemp": 200}],
        }

        normalized = recipe_to_celsius(recipe)

        self.assertEqual(normalized["steps"][0]["targetTemp"], 180)
        self.assertEqual(normalized["steps"][1]["targetTemp"], 200)
        self.assertEqual(normalized["temperatureUnit"], TEMP_UNIT_C)

    def test_recipe_to_celsius_leaves_steps_without_target_temp_untouched(self):
        recipe = {
            "steps": [{"fanSpeed": 5, "sectionTime": 10}],
        }

        normalized = recipe_to_celsius(recipe)

        self.assertEqual(normalized["temperatureUnit"], TEMP_UNIT_C)
        self.assertEqual(normalized["steps"][0]["fanSpeed"], 5)
        self.assertNotIn("targetTemp", normalized["steps"][0])


if __name__ == "__main__":
    unittest.main()

