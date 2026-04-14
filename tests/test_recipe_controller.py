import unittest
import json
import os
import tempfile

from openroast.controllers.recipe import Recipe
from openroast.temperature import (
    DEFAULT_TARGET_TEMPERATURE_C,
    RECIPE_UNIT_CELSIUS,
    RECIPE_UNIT_KELVIN,
    TEMP_UNIT_C,
    TEMP_UNIT_F,
    celsius_to_fahrenheit,
)


class FakeApp:
    """Tracks section-change callback invocations."""
    def __init__(self):
        self.roasttab_update_calls = 0

    def __call__(self):
        self.roasttab_update_calls += 1

    def roasttab_flag_update_controllers(self):
        self.roasttab_update_calls += 1


class FakeRoaster:
    def __init__(self, temperature_unit="F"):
        self.temperature_unit = temperature_unit
        self.connected = True
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
        self.assertEqual(normalized["temperatureUnit"], RECIPE_UNIT_CELSIUS)
        self.assertEqual(normalized["displayTemperatureUnit"], TEMP_UNIT_F)
        self.assertEqual(normalized["steps"][0]["targetTemp"], 100)

    def test_load_recipe_json_accepts_kelvin_recipe_unit(self):
        recipe = Recipe(roaster=FakeRoaster("C"), app=FakeApp())
        recipe.load_recipe_json(
            {
                "temperatureUnit": RECIPE_UNIT_KELVIN,
                "steps": [{"targetTemp": 373.15, "fanSpeed": 4, "sectionTime": 30}],
            }
        )

        normalized = recipe.get_current_recipe()
        self.assertEqual(normalized["temperatureUnit"], RECIPE_UNIT_CELSIUS)
        self.assertEqual(normalized["displayTemperatureUnit"], "K")
        self.assertEqual(normalized["steps"][0]["targetTemp"], 100)

    def test_create_default_recipe_uses_celsius_display_intent(self):
        recipe = Recipe(roaster=FakeRoaster("C"), app=FakeApp())
        template = recipe.create_default_recipe()
        self.assertEqual(template["temperatureUnit"], RECIPE_UNIT_CELSIUS)
        self.assertEqual(template["displayTemperatureUnit"], TEMP_UNIT_C)

    def test_set_roaster_settings_converts_to_roaster_units_and_starts_roast(self):
        roaster = FakeRoaster("F")
        app = FakeApp()
        recipe = Recipe(roaster=roaster, on_section_change=app)

        # Section index > 0 enables roast() when section duration > 0 and not cooling.
        recipe._storage.current_step = 1
        recipe.set_roaster_settings(target_temp_c=100, fan_speed=7, section_duration_s=45, cooling=False)

        self.assertEqual(roaster.target_temp, int(round(celsius_to_fahrenheit(100))))
        self.assertEqual(roaster.fan_speed, 7)
        self.assertEqual(roaster.time_remaining, 45)
        self.assertEqual(roaster.roast_calls, 1)
        self.assertEqual(roaster.cool_calls, 0)

    def test_set_roaster_settings_cooling_path_calls_cool(self):
        roaster = FakeRoaster("F")
        app = FakeApp()
        recipe = Recipe(roaster=roaster, on_section_change=app)

        recipe._storage.current_step = 1
        recipe.set_roaster_settings(target_temp_c=80, fan_speed=9, section_duration_s=60, cooling=True)

        self.assertEqual(roaster.cool_calls, 1)
        self.assertEqual(roaster.roast_calls, 0)
        self.assertEqual(roaster.target_temp, int(round(celsius_to_fahrenheit(80))))

    def test_reset_roaster_settings_applies_default_target_and_base_fan(self):
        roaster = FakeRoaster("F")
        recipe = Recipe(roaster=roaster, on_section_change=FakeApp())

        recipe.reset_roaster_settings()

        self.assertEqual(roaster.target_temp, int(round(celsius_to_fahrenheit(DEFAULT_TARGET_TEMPERATURE_C))))
        self.assertEqual(roaster.fan_speed, 1)
        self.assertEqual(roaster.time_remaining, 0)

    def test_missing_target_temp_uses_default_target(self):
        recipe = Recipe(roaster=FakeRoaster("C"), app=FakeApp())
        recipe.load_recipe_json(
            {
                "temperatureUnit": RECIPE_UNIT_CELSIUS,
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
                "temperatureUnit": RECIPE_UNIT_CELSIUS,
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

    def test_move_to_next_section_end_of_recipe_sets_roaster_idle(self):
        roaster = FakeRoaster("C")
        recipe = Recipe(roaster=roaster, app=FakeApp())
        recipe.load_recipe_json(
            {
                "temperatureUnit": RECIPE_UNIT_CELSIUS,
                "steps": [{"targetTemp": 80, "fanSpeed": 3, "sectionTime": 20}],
            }
        )

        recipe.move_to_next_section()

        self.assertEqual(roaster.idle_calls, 1)
        self.assertEqual(recipe.get_current_step_number(), 0)

    def test_move_to_next_section_without_recipe_sets_roaster_idle(self):
        roaster = FakeRoaster("C")
        recipe = Recipe(roaster=roaster, app=FakeApp())

        recipe.move_to_next_section()

        self.assertEqual(roaster.idle_calls, 1)

    def test_set_roaster_settings_roast_start_guard_matrix(self):
        cases = [
            {"cooling": True, "section_duration": 30, "step": 1, "expect_roast": 0, "expect_cool": 1},
            {"cooling": False, "section_duration": 0, "step": 1, "expect_roast": 0, "expect_cool": 0},
            {"cooling": False, "section_duration": 30, "step": 0, "expect_roast": 0, "expect_cool": 0},
            {"cooling": False, "section_duration": 30, "step": 1, "expect_roast": 1, "expect_cool": 0},
        ]

        for case in cases:
            with self.subTest(case=case):
                roaster = FakeRoaster("C")
                recipe = Recipe(roaster=roaster, on_section_change=FakeApp())
                recipe._storage.current_step = case["step"]

                recipe.set_roaster_settings(
                    target_temp_c=100,
                    fan_speed=5,
                    section_duration_s=case["section_duration"],
                    cooling=case["cooling"],
                )

                self.assertEqual(roaster.roast_calls, case["expect_roast"])
                self.assertEqual(roaster.cool_calls, case["expect_cool"])

    def test_load_recipe_file_clear_and_reload_flow(self):
        roaster = FakeRoaster("F")
        recipe = Recipe(roaster=roaster, app=FakeApp())

        fd1, path1 = tempfile.mkstemp(suffix=".json")
        os.close(fd1)
        fd2, path2 = tempfile.mkstemp(suffix=".json")
        os.close(fd2)
        try:
            with open(path1, "w", encoding="utf-8") as handle:
                json.dump({"steps": [{"targetTemp": 212, "fanSpeed": 4, "sectionTime": 30}]}, handle)
            with open(path2, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "temperatureUnit": RECIPE_UNIT_CELSIUS,
                        "steps": [{"targetTemp": 95, "fanSpeed": 6, "sectionTime": 40}],
                    },
                    handle,
                )

            recipe.load_recipe_file(path1)
            self.assertTrue(recipe.check_recipe_loaded())
            self.assertEqual(recipe.get_current_target_temp(), 100)

            recipe.clear_recipe()
            self.assertFalse(recipe.check_recipe_loaded())
            self.assertEqual(recipe.get_num_recipe_sections(), 0)
            self.assertEqual(recipe.get_current_step_number(), 0)

            recipe.load_recipe_file(path2)
            self.assertTrue(recipe.check_recipe_loaded())
            self.assertEqual(recipe.get_current_target_temp(), 95)
            self.assertEqual(recipe.get_num_recipe_sections(), 1)
        finally:
            os.remove(path1)
            os.remove(path2)

    def test_loading_legacy_recipe_does_not_rewrite_source_file(self):
        roaster = FakeRoaster("C")
        recipe = Recipe(roaster=roaster, app=FakeApp())

        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        legacy = {"steps": [{"targetTemp": 212, "fanSpeed": 4, "sectionTime": 30}]}
        try:
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(legacy, handle)

            recipe.load_recipe_file(path)
            with open(path, encoding="utf-8") as handle:
                persisted = json.load(handle)

            self.assertEqual(persisted, legacy)
            self.assertEqual(recipe.get_current_target_temp(), 100)
        finally:
            os.remove(path)

    def test_disconnected_roaster_skips_reset_and_section_hardware_writes(self):
        roaster = FakeRoaster("F")
        roaster.connected = False
        recipe = Recipe(roaster=roaster, app=FakeApp())

        recipe.reset_roaster_settings()
        self.assertIsNone(roaster.target_temp)
        self.assertIsNone(roaster.fan_speed)
        self.assertIsNone(roaster.time_remaining)

        recipe.load_recipe_json(
            {
                "temperatureUnit": RECIPE_UNIT_CELSIUS,
                "steps": [{"targetTemp": 100, "fanSpeed": 5, "sectionTime": 30}],
            }
        )
        recipe.load_current_section()
        self.assertIsNone(roaster.target_temp)
        self.assertIsNone(roaster.fan_speed)
        self.assertIsNone(roaster.time_remaining)

    def test_move_to_next_section_no_callback_no_crash(self):
        """move_to_next_section with no section_change callback must not crash.

        This covers the startup race where the window may not exist yet.
        """
        roaster = FakeRoaster("C")
        recipe = Recipe(roaster=roaster, on_section_change=None, use_shared_memory=False)
        recipe.load_recipe_json(
            {
                "temperatureUnit": RECIPE_UNIT_CELSIUS,
                "steps": [
                    {"targetTemp": 80, "fanSpeed": 3, "sectionTime": 20},
                    {"targetTemp": 90, "fanSpeed": 5, "sectionTime": 30},
                ],
            }
        )
        # Should not crash even with no callback.
        recipe.move_to_next_section()
        self.assertEqual(recipe.get_current_step_number(), 1)

    def test_thread_safe_storage_backend(self):
        """Recipe with use_shared_memory=False uses lightweight thread-safe storage."""
        roaster = FakeRoaster("C")
        app = FakeApp()
        recipe = Recipe(roaster=roaster, on_section_change=app, use_shared_memory=False)

        recipe.load_recipe_json(
            {
                "temperatureUnit": RECIPE_UNIT_CELSIUS,
                "steps": [
                    {"targetTemp": 80, "fanSpeed": 3, "sectionTime": 20},
                    {"targetTemp": 90, "fanSpeed": 5, "sectionTime": 30},
                ],
            }
        )
        self.assertTrue(recipe.check_recipe_loaded())
        self.assertEqual(recipe.get_num_recipe_sections(), 2)
        self.assertEqual(recipe.get_current_step_number(), 0)

        recipe.move_to_next_section()
        self.assertEqual(recipe.get_current_step_number(), 1)
        self.assertEqual(app.roasttab_update_calls, 1)

        recipe.clear_recipe()
        self.assertFalse(recipe.check_recipe_loaded())
        self.assertEqual(recipe.get_current_step_number(), 0)


if __name__ == "__main__":
    unittest.main()

