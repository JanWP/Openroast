from copy import deepcopy
from typing import Any

TEMP_UNIT_C = "C"
TEMP_UNIT_F = "F"


def normalize_temperature_unit(unit: Any, default: str = TEMP_UNIT_C) -> str:
    if isinstance(unit, str):
        upper = unit.strip().upper()
        if upper in (TEMP_UNIT_C, TEMP_UNIT_F):
            return upper
    return default


def fahrenheit_to_celsius(value_f: float) -> float:
    return (float(value_f) - 32.0) * 5.0 / 9.0


def celsius_to_fahrenheit(value_c: float) -> float:
    return float(value_c) * 9.0 / 5.0 + 32.0


def temperature_to_celsius(value: float, unit: Any) -> float:
    normalized_unit = normalize_temperature_unit(unit, default=TEMP_UNIT_C)
    if normalized_unit == TEMP_UNIT_F:
        return fahrenheit_to_celsius(value)
    return float(value)


def celsius_to_temperature_unit(value_c: float, unit: Any) -> float:
    normalized_unit = normalize_temperature_unit(unit, default=TEMP_UNIT_C)
    if normalized_unit == TEMP_UNIT_F:
        return celsius_to_fahrenheit(value_c)
    return float(value_c)


def recipe_to_celsius(recipe: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of recipe with target temperatures normalized to Celsius.

    Legacy files without explicit temperature unit are treated as Fahrenheit for
    backward compatibility with existing Openroast recipe data.
    """
    normalized = deepcopy(recipe)
    unit = normalize_temperature_unit(normalized.get("temperatureUnit"), default=TEMP_UNIT_F)

    if unit == TEMP_UNIT_F:
        for step in normalized.get("steps", []):
            if "targetTemp" in step:
                step["targetTemp"] = int(round(fahrenheit_to_celsius(step["targetTemp"])))

    normalized["temperatureUnit"] = TEMP_UNIT_C
    return normalized
