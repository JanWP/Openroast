# -*- coding: utf-8 -*-
"""Fan-speed conversion helpers.

Two fan-speed domains are used in Openroast:
- recipe_fan_speed: legacy recipe/editor scale (1..recipe_fan_max)
- runtime_fan_speed: backend-native runtime scale (1..runtime_fan_max)

Current mapping semantics:
- 1 -> 1 (minimum non-off fan)
- recipe_fan_max -> runtime_fan_max
- values in-between use nearest-int linear scaling
- if runtime_fan_max == 1, every recipe value maps to 1
"""


def _clamp_int(value: int, low: int, high: int) -> int:
    return max(int(low), min(int(high), int(value)))


def recipe_fan_to_runtime_fan(
    recipe_fan_speed: int,
    *,
    recipe_fan_max: int,
    runtime_fan_max: int,
) -> int:
    recipe_max = max(1, int(recipe_fan_max))
    runtime_max = max(1, int(runtime_fan_max))
    recipe_fan = int(recipe_fan_speed)

    if recipe_fan >= recipe_max:
        return runtime_max
    if (recipe_fan <= 1) or (runtime_max == 1):
        return 1

    # Linear scaling on [1, max] anchors with nearest-int rounding.
    scaled = 1.0 + (float(recipe_fan - 1) * float(runtime_max - 1) / float(recipe_max - 1))
    return _clamp_int(int(round(scaled)), 1, runtime_max)


