# -*- coding: utf-8 -*-
# Roastero, released under GPLv3

import json
import threading
from multiprocessing import sharedctypes, Array
import ctypes

from openroast.temperature import (
            get_default_display_temperature_unit,
    DEFAULT_TARGET_TEMPERATURE_C,
    RECIPE_FORMAT_VERSION,
    RECIPE_UNIT_CELSIUS,
    TEMP_UNIT_F,
    TEMP_UNIT_C,
    celsius_to_kelvin,
    celsius_to_temperature_unit,
    normalize_temperature_unit,
    recipe_to_celsius,
)


# ---------------------------------------------------------------------------
# Recipe storage backends
# ---------------------------------------------------------------------------

class _SharedMemoryStorage:
    """Process-safe storage using multiprocessing shared memory.

    This is required for the USB (freshroastsr700) backend which spawns a
    child process that calls Recipe.move_to_next_section().
    """

    def __init__(self, max_recipe_size_bytes: int):
        self._current_step = sharedctypes.Value('i', 0)
        self._recipe_str = Array(ctypes.c_char, max_recipe_size_bytes)
        self._loaded = sharedctypes.Value('i', 0)

    @property
    def current_step(self) -> int:
        return self._current_step.value

    @current_step.setter
    def current_step(self, value: int):
        self._current_step.value = value

    @property
    def recipe_bytes(self) -> bytes:
        return self._recipe_str.value

    @recipe_bytes.setter
    def recipe_bytes(self, value: bytes):
        self._recipe_str.value = value

    @property
    def loaded(self) -> bool:
        return self._loaded.value != 0

    @loaded.setter
    def loaded(self, value: bool):
        self._loaded.value = 1 if value else 0


class _ThreadSafeStorage:
    """Thread-safe storage using a plain threading.Lock.

    This is lighter weight and does not allocate a 64 KB shared-memory
    segment, making it ideal for the local backend which only uses threads.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._current_step = 0
        self._recipe_bytes = b""
        self._loaded = False

    @property
    def current_step(self) -> int:
        with self._lock:
            return self._current_step

    @current_step.setter
    def current_step(self, value: int):
        with self._lock:
            self._current_step = int(value)

    @property
    def recipe_bytes(self) -> bytes:
        with self._lock:
            return self._recipe_bytes

    @recipe_bytes.setter
    def recipe_bytes(self, value: bytes):
        with self._lock:
            self._recipe_bytes = bytes(value)

    @property
    def loaded(self) -> bool:
        with self._lock:
            return self._loaded

    @loaded.setter
    def loaded(self, value: bool):
        with self._lock:
            self._loaded = bool(value)


def normalize_recipe_for_runtime(recipe_json, *, default_source_unit=TEMP_UNIT_F):
    source_unit = normalize_temperature_unit(
        recipe_json.get("displayTemperatureUnit", recipe_json.get("temperatureUnit")),
        default=default_source_unit,
    )
    normalized_recipe = recipe_to_celsius(recipe_json)
    normalized_recipe["displayTemperatureUnit"] = source_unit
    return normalized_recipe


def build_default_recipe(*, default_display_unit=None):
    resolved_default = default_display_unit
    if resolved_default is None:
        resolved_default = get_default_display_temperature_unit()
    display_unit = normalize_temperature_unit(resolved_default, default=TEMP_UNIT_C)
    return {
        "roastName": "",
        "creator": "",
        "roastDescription": {
            "roastType": "",
            "description": "",
        },
        "bean": {
            "region": "",
            "country": "",
            "source": {
                "reseller": "",
                "link": "",
            },
        },
        "steps": [
            {
                "fanSpeed": 5,
                "targetTemp": DEFAULT_TARGET_TEMPERATURE_C,
                "sectionTime": 0,
            }
        ],
        "totalTime": 0,
        "formatVersion": RECIPE_FORMAT_VERSION,
        "temperatureUnit": RECIPE_UNIT_CELSIUS,
        "displayTemperatureUnit": display_unit,
    }


class Recipe(object):
    def __init__(self, roaster, app=None, max_recipe_size_bytes=64*1024,
                 on_section_change=None, use_shared_memory=True):
        # Select storage backend.
        if use_shared_memory:
            self._storage = _SharedMemoryStorage(max_recipe_size_bytes)
        else:
            self._storage = _ThreadSafeStorage()

        # Backward-compatible aliases for any external code (e.g. USB backend
        # child process) that directly touches these attributes.
        if use_shared_memory:
            self.currentRecipeStep = self._storage._current_step
            self.recipe_str = self._storage._recipe_str
            self.recipeLoaded = self._storage._loaded
        else:
            self.currentRecipeStep = None
            self.recipe_str = None
            self.recipeLoaded = None

        self.roaster = roaster

        # Accept both legacy 'app' and new callback style.
        if on_section_change is not None:
            self._on_section_change = on_section_change
        elif app is not None:
            self._on_section_change = getattr(app, "roasttab_flag_update_controllers", None)
        else:
            self._on_section_change = None

        self._default_target_temp_c = DEFAULT_TARGET_TEMPERATURE_C
        self._roaster_temperature_unit = normalize_temperature_unit(
            getattr(self.roaster, "temperature_unit", TEMP_UNIT_F),
            default=TEMP_UNIT_F,
        )

        # Cache for parsed recipe to avoid repeated json.loads().
        self._cached_recipe = None
        self._cached_recipe_raw = b""

    def _normalize_recipe_for_runtime(self, recipe_json):
        return normalize_recipe_for_runtime(
            recipe_json,
            default_source_unit=TEMP_UNIT_F,
        )

    def create_default_recipe(self):
        return build_default_recipe(default_display_unit=get_default_display_temperature_unit())

    def _invalidate_cache(self):
        self._cached_recipe = None
        self._cached_recipe_raw = b""

    def _recipe(self):
        if self._storage.loaded:
            raw = self._storage.recipe_bytes
            if raw == self._cached_recipe_raw and self._cached_recipe is not None:
                return self._cached_recipe
            parsed = json.loads(raw.decode('utf_8'))
            self._cached_recipe_raw = raw
            self._cached_recipe = parsed
            return parsed
        else:
            return {}

    def load_recipe_json(self, recipe_json):
        normalized_recipe = self._normalize_recipe_for_runtime(recipe_json)
        self._storage.recipe_bytes = json.dumps(normalized_recipe).encode('utf_8')
        self._storage.loaded = True
        self._invalidate_cache()
        return normalized_recipe

    def load_recipe_file(self, recipeFile, store=True):
        with open(recipeFile, encoding='utf-8') as recipeFileHandler:
            recipe_dict = json.load(recipeFileHandler)
        normalized_recipe = self._normalize_recipe_for_runtime(recipe_dict)
        if store:
            self._storage.recipe_bytes = json.dumps(normalized_recipe).encode('utf_8')
            self._storage.loaded = True
            self._invalidate_cache()
        return normalized_recipe

    def clear_recipe(self):
        self._storage.loaded = False
        self._storage.recipe_bytes = b''
        self._storage.current_step = 0
        self._invalidate_cache()

    def check_recipe_loaded(self):
        return self._storage.loaded

    def get_num_recipe_sections(self):
        if not self.check_recipe_loaded():
            return 0
        return len(self._recipe()["steps"])

    def get_current_step_number(self):
        return self._storage.current_step

    def get_current_fan_speed(self):
        current_step = self._storage.current_step
        return self._recipe()["steps"][current_step]["fanSpeed"]

    def get_current_target_temp(self):
        current_step = self._storage.current_step
        if(self._recipe()["steps"][current_step].get("targetTemp")):
            return self._recipe()["steps"][current_step]["targetTemp"]
        else:
            return self._default_target_temp_c

    def get_current_target_temp_c(self):
        return self.get_current_target_temp()

    def get_current_section_duration(self):
        current_step = self._storage.current_step
        return self._recipe()["steps"][current_step]["sectionTime"]

    # Backward-compatible alias.
    def get_current_section_time(self):
        return self.get_current_section_duration()

    def get_current_section_time_s(self):
        return self.get_current_section_duration()

    def get_current_section_duration_s(self):
        return self.get_current_section_duration()

    def restart_current_recipe(self):
        self._storage.current_step = 0
        self.load_current_section()

    def more_recipe_sections(self):
        if not self.check_recipe_loaded():
            return False
        if(len(self._recipe()["steps"]) - self._storage.current_step == 0):
            return False
        else:
            return True

    def get_current_cooling_status(self):
        current_step = self._storage.current_step
        if(self._recipe()["steps"][current_step].get("cooling")):
            return self._recipe()["steps"][current_step]["cooling"]
        else:
            return False

    def get_section_duration(self, index):
        return self._recipe()["steps"][index]["sectionTime"]

    # Backward-compatible alias.
    def get_section_time(self, index):
        return self.get_section_duration(index)

    def get_section_temp(self, index):
        if(self._recipe()["steps"][index].get("targetTemp")):
            return self._recipe()["steps"][index]["targetTemp"]
        else:
            return self._default_target_temp_c

    def get_display_temperature_unit(self):
        if not self.check_recipe_loaded():
            return get_default_display_temperature_unit()
        recipe_unit = self._recipe().get("displayTemperatureUnit")
        return normalize_temperature_unit(recipe_unit, default=get_default_display_temperature_unit())

    def _is_roaster_connected(self):
        connected = getattr(self.roaster, "connected", None)
        if connected is None:
            return True
        return bool(connected)

    def reset_roaster_settings(self):
        if not self._is_roaster_connected():
            return
        self._set_roaster_target_temp_c(self._default_target_temp_c)
        self.roaster.fan_speed = 1
        self._set_roaster_time_remaining_s(0)

    def _set_roaster_target_temp_c(self, target_temp_c):
        if hasattr(self.roaster, "target_temp_k"):
            self.roaster.target_temp_k = celsius_to_kelvin(target_temp_c)
            return
        self.roaster.target_temp = int(round(celsius_to_temperature_unit(
            target_temp_c,
            self._roaster_temperature_unit,
        )))

    def _set_roaster_time_remaining_s(self, section_duration_s):
        if hasattr(self.roaster, "time_remaining_s"):
            self.roaster.time_remaining_s = section_duration_s
            return
        self.roaster.time_remaining = section_duration_s

    def set_roaster_settings(self, target_temp_c, fan_speed, section_duration_s, cooling):
        if not self._is_roaster_connected():
            return
        if cooling:
            self.roaster.cool()

        # Prevent the roaster from starting when section duration = 0 (e.g. clear)
        if(not cooling and section_duration_s > 0 and
           self._storage.current_step > 0):
            self.roaster.roast()

        self._set_roaster_target_temp_c(target_temp_c)
        self.roaster.fan_speed = fan_speed
        self._set_roaster_time_remaining_s(section_duration_s)

    def load_current_section(self):
        self.set_roaster_settings(self.get_current_target_temp(),
                                self.get_current_fan_speed(),
                                self.get_current_section_duration(),
                                self.get_current_cooling_status())

    def move_to_next_section(self):
        if self.check_recipe_loaded():
            if(
                (self._storage.current_step + 1) >=
                    self.get_num_recipe_sections()):
                self.roaster.idle()
            else:
                self._storage.current_step = self._storage.current_step + 1
                self.load_current_section()
                # Notify frontend (e.g. RoastTab) via callback.
                if callable(self._on_section_change):
                    self._on_section_change()
        else:
            self.roaster.idle()

    def get_current_recipe(self):
        return self._recipe()
