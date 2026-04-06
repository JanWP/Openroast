import unittest

from openroast.controllers.recipe import Recipe
from openroast.temperature import DEFAULT_TARGET_TEMPERATURE_C


class FakeApp:
    def __init__(self):
        self.roasttab_update_calls = 0

    def roasttab_flag_update_controllers(self):
        self.roasttab_update_calls += 1


class FakeRoaster:
    def __init__(self, temperature_unit="F"):
        self.temperature_unit = temperature_unit
        self.target_temp = None
        self.fan_speed = None
        self.time_remaining = None
        self.cool_calls = 0
        self.roast_calls = 0
        self.idle_calls = 0

    def cool(self):
        self.cool_calls += 1

    def roast(self):
        self.roast_calls += 1

    def idle(self):
        self.idle_calls += 1


class RecipeControllerIntegrationTests(unittest.TestCase):
    def test_load_recipe_json_normalizes_legacy_fahrenheit_to_celsius(self):
        recipe = Recipe(roaster=FakeRoaster("F"), app=FakeApp())
        recipe.load_recipe_json(
            {
                "name": "legacy",
                "steps": [{"targetTemp": 212, "fanSpeed": 4, "sectionTime": 30}],
            }
        )

        normalized = recipe.get_current_recipe()
        self.assertEqual(normalized["temperatureUnit"], "C")
        self.assertEqual(normalized["steps"][0]["targetTemp"], 100)

    def test_set_roaster_settings_converts_to_roaster_units_and_starts_roast(self):
        roaster = FakeRoaster("F")
        recipe = Recipe(roaster=roaster, app=FakeApp())

        # Section index > 0 enables roast() when sectionTime > 0 and not cooling.
        recipe.currentRecipeStep.value = 1
        recipe.set_roaster_settings(targetTemp=100, fanSpeed=7, sectionTime=45, cooling=False)

        self.assertEqual(roaster.target_temp, 212)
        self.assertEqual(roaster.fan_speed, 7)
        self.assertEqual(roaster.time_remaining, 45)
        self.assertEqual(roaster.roast_calls, 1)
        self.assertEqual(roaster.cool_calls, 0)

    def test_set_roaster_settings_cooling_path_calls_cool(self):
        roaster = FakeRoaster("F")
        recipe = Recipe(roaster=roaster, app=FakeApp())

        recipe.currentRecipeStep.value = 1
        recipe.set_roaster_settings(targetTemp=80, fanSpeed=9, sectionTime=60, cooling=True)

        self.assertEqual(roaster.cool_calls, 1)
        self.assertEqual(roaster.roast_calls, 0)
        self.assertEqual(roaster.target_temp, 176)

    def test_reset_roaster_settings_applies_default_target_and_base_fan(self):
        roaster = FakeRoaster("F")
        recipe = Recipe(roaster=roaster, app=FakeApp())

        recipe.reset_roaster_settings()

        self.assertEqual(roaster.target_temp, 149)
        self.assertEqual(roaster.fan_speed, 1)
        self.assertEqual(roaster.time_remaining, 0)

    def test_missing_target_temp_uses_default_target(self):
        recipe = Recipe(roaster=FakeRoaster("C"), app=FakeApp())
        recipe.load_recipe_json(
            {
                "temperatureUnit": "C",
                "steps": [{"fanSpeed": 5, "sectionTime": 20}],
            }
        )

        self.assertEqual(recipe.get_current_target_temp(), DEFAULT_TARGET_TEMPERATURE_C)

    def test_move_to_next_section_loads_section_and_notifies_app(self):
        roaster = FakeRoaster("C")
        app = FakeApp()
        recipe = Recipe(roaster=roaster, app=app)
        recipe.load_recipe_json(
            {
                "temperatureUnit": "C",
                "steps": [
                    {"targetTemp": 80, "fanSpeed": 3, "sectionTime": 20},
                    {"targetTemp": 100, "fanSpeed": 4, "sectionTime": 25},
                ],
            }
        )

        recipe.move_to_next_section()

        self.assertEqual(recipe.get_current_step_number(), 1)
        self.assertEqual(roaster.target_temp, 100)
        self.assertEqual(roaster.fan_speed, 4)
        self.assertEqual(roaster.time_remaining, 25)
        self.assertEqual(app.roasttab_update_calls, 1)


if __name__ == "__main__":
    unittest.main()

