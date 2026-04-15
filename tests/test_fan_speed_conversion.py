import unittest

from openroast.fan_speed import (
    recipe_fan_to_runtime_fan,
)


class FanSpeedConversionTests(unittest.TestCase):
    def test_identity_when_scales_match(self):
        for value in (0, 1, 3, 7, 9):
            with self.subTest(value=value):
                self.assertEqual(
                    recipe_fan_to_runtime_fan(value, recipe_fan_max=9, runtime_fan_max=9),
                    value,
                )

    def test_mapping_preserves_required_anchors(self):
        self.assertEqual(recipe_fan_to_runtime_fan(0, recipe_fan_max=9, runtime_fan_max=5), 0)
        self.assertEqual(recipe_fan_to_runtime_fan(1, recipe_fan_max=9, runtime_fan_max=5), 1)
        self.assertEqual(recipe_fan_to_runtime_fan(9, recipe_fan_max=9, runtime_fan_max=5), 5)

    def test_mapping_uses_nearest_int_rounding(self):
        # 1 + (4 * (5-1)/(9-1)) = 3.0
        self.assertEqual(recipe_fan_to_runtime_fan(5, recipe_fan_max=9, runtime_fan_max=5), 3)

    def test_runtime_max_one_maps_all_nonzero_recipe_values_to_one(self):
        for value in (1, 2, 5, 9):
            with self.subTest(value=value):
                self.assertEqual(recipe_fan_to_runtime_fan(value, recipe_fan_max=9, runtime_fan_max=1), 1)
        self.assertEqual(recipe_fan_to_runtime_fan(0, recipe_fan_max=9, runtime_fan_max=1), 0)


if __name__ == "__main__":
    unittest.main()

