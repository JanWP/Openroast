from copy import deepcopy
from typing import Any

TEMP_UNIT_C = "C"
TEMP_UNIT_F = "F"
TEMP_UNIT_K = "K"

RECIPE_UNIT_CELSIUS = "Celsius"
RECIPE_UNIT_FAHRENHEIT = "Fahrenheit"
RECIPE_UNIT_KELVIN = "Kelvin"
RECIPE_FORMAT_VERSION = 2

# Global temperature policy for Openroast UI/recipes.
MIN_TEMPERATURE_C = 20
MAX_TEMPERATURE_C = 290
TEMPERATURE_STEP_C = 5
DEFAULT_TARGET_TEMPERATURE_C = 65
GRAPH_HEADROOM_C = 5


def normalize_temperature_unit(unit: Any, default: str = TEMP_UNIT_C) -> str:
    if isinstance(unit, str):
        stripped = unit.strip()
        upper = stripped.upper()
        if upper in (TEMP_UNIT_C, TEMP_UNIT_F, TEMP_UNIT_K):
            return upper
        if upper == RECIPE_UNIT_CELSIUS.upper():
            return TEMP_UNIT_C
        if upper == RECIPE_UNIT_FAHRENHEIT.upper():
            return TEMP_UNIT_F
        if upper == RECIPE_UNIT_KELVIN.upper():
            return TEMP_UNIT_K
    return default


def fahrenheit_to_celsius(value_f: float) -> float:
    return (float(value_f) - 32.0) * 5.0 / 9.0


def celsius_to_fahrenheit(value_c: float) -> float:
    return float(value_c) * 9.0 / 5.0 + 32.0


def celsius_to_kelvin(value_c: float) -> float:
    return float(value_c) + 273.15


def kelvin_to_celsius(value_k: float) -> float:
    return float(value_k) - 273.15


def fahrenheit_to_kelvin(value_f: float) -> float:
    return celsius_to_kelvin(fahrenheit_to_celsius(value_f))


def kelvin_to_fahrenheit(value_k: float) -> float:
    return celsius_to_fahrenheit(kelvin_to_celsius(value_k))


def temperature_to_celsius(value: float, unit: Any) -> float:
    normalized_unit = normalize_temperature_unit(unit, default=TEMP_UNIT_C)
    if normalized_unit == TEMP_UNIT_F:
        return fahrenheit_to_celsius(value)
    if normalized_unit == TEMP_UNIT_K:
        return kelvin_to_celsius(value)
    return float(value)


def celsius_to_temperature_unit(value_c: float, unit: Any) -> float:
    normalized_unit = normalize_temperature_unit(unit, default=TEMP_UNIT_C)
    if normalized_unit == TEMP_UNIT_F:
        return celsius_to_fahrenheit(value_c)
    if normalized_unit == TEMP_UNIT_K:
        return celsius_to_kelvin(value_c)
    return float(value_c)


def temperature_unit_symbol_to_label(unit: Any) -> str:
    normalized_unit = normalize_temperature_unit(unit, default=TEMP_UNIT_C)
    if normalized_unit == TEMP_UNIT_F:
        return RECIPE_UNIT_FAHRENHEIT
    if normalized_unit == TEMP_UNIT_K:
        return RECIPE_UNIT_KELVIN
    return RECIPE_UNIT_CELSIUS


def clamp_temperature_c(value_c: float, *, low: int = MIN_TEMPERATURE_C, high: int = MAX_TEMPERATURE_C) -> int:
    return int(round(max(low, min(high, float(value_c)))))


def recipe_to_celsius(recipe: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of recipe with target temperatures normalized to Celsius.

    Legacy files without explicit temperature unit are treated as Fahrenheit for
    backward compatibility with existing Openroast recipe data.
    """
    normalized = deepcopy(recipe)
    unit = normalize_temperature_unit(normalized.get("temperatureUnit"), default=TEMP_UNIT_F)

    for step in normalized.get("steps", []):
        if "targetTemp" in step:
            step["targetTemp"] = int(round(temperature_to_celsius(step["targetTemp"], unit)))

    normalized["temperatureUnit"] = RECIPE_UNIT_CELSIUS
    normalized.setdefault("formatVersion", RECIPE_FORMAT_VERSION)
    return normalized
