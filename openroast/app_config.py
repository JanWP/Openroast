import copy
import json
import os
import platform

from openroast.temperature import (
    TEMP_UNIT_C,
    celsius_to_temperature_delta_unit,
    celsius_to_temperature_unit,
    normalize_temperature_unit,
    temperature_delta_to_celsius,
    temperature_to_celsius,
)

VALID_BACKENDS = ("usb", "usb-mock", "local", "local-mock")

MIN_REFRESH_INTERVAL_MS = 100
MAX_REFRESH_INTERVAL_MS = 5000
MIN_Y_AXIS_HEADROOM_C = 1.0
MAX_Y_AXIS_HEADROOM_C = 100.0
MIN_Y_AXIS_STEP_C = 1.0
MAX_Y_AXIS_STEP_C = 25.0
MIN_PLOT_LINE_WIDTH = 1.0
MAX_PLOT_LINE_WIDTH = 8.0

MIN_PID_KP = 0.0
MAX_PID_KP = 2.0
MIN_PID_KI = 0.0
MAX_PID_KI = 1.0
MIN_PID_KD = 0.0
MAX_PID_KD = 1.0
MIN_PWM_CYCLE_SECONDS = 0.2
MAX_PWM_CYCLE_SECONDS = 10.0
MIN_SAMPLE_PERIOD_SECONDS = 0.05
MAX_SAMPLE_PERIOD_SECONDS = 5.0
MIN_SAFETY_MAX_TEMP_C = 120.0
MAX_SAFETY_MAX_TEMP_C = 350.0


def _clamp_int(value, low, high, default):
    try:
        ivalue = int(value)
    except (TypeError, ValueError):
        ivalue = int(default)
    return max(int(low), min(int(high), ivalue))


def _clamp_float(value, low, high, default):
    try:
        fvalue = float(value)
    except (TypeError, ValueError):
        fvalue = float(default)
    return max(float(low), min(float(high), fvalue))

DEFAULT_CONFIG = {
    "configVersion": 1,
    "display": {
        "temperatureUnitDefault": TEMP_UNIT_C,
    },
    "ui": {
        "compactModeDefault": False,
        "fullscreenOnStart": False,
        "refreshIntervalMs": 1000,
        "expertModeEnabled": False,
    },
    "plot": {
        "yAxisHeadroom": {"value": 5.0, "unit": TEMP_UNIT_C},
        "yAxisStep": {"value": 5.0, "unit": TEMP_UNIT_C},
        "showGrid": True,
        "lineWidth": 3.0,
    },
    "app": {
        "backendDefault": "usb",
    },
    "roast": {
        "confirmOnStop": False,
        "confirmOnClear": False,
    },
    "control": {
        "pid": {
            "kp": 0.108,
            "ki": 0.0135,
            "kd": 0.018,
        },
        "pwmCycleSeconds": 1.0,
        "samplePeriodSeconds": 0.5,
    },
    "safety": {
        "maxTemp": {"value": 287.78, "unit": TEMP_UNIT_C},
        "heaterCutoffEnabled": True,
    },
}


def _quantity_to_celsius(value, *, default_c, default_unit=TEMP_UNIT_C, delta=False):
    if isinstance(value, dict):
        unit = normalize_temperature_unit(value.get("unit"), default=default_unit)
        numeric_value = value.get("value", default_c)
    else:
        unit = normalize_temperature_unit(default_unit, default=TEMP_UNIT_C)
        numeric_value = value if value is not None else default_c

    if delta:
        return temperature_delta_to_celsius(numeric_value, unit)
    return temperature_to_celsius(numeric_value, unit)


def _celsius_to_quantity(value_c, *, unit, delta=False):
    normalized_unit = normalize_temperature_unit(unit, default=TEMP_UNIT_C)
    if delta:
        value = celsius_to_temperature_delta_unit(value_c, normalized_unit)
    else:
        value = celsius_to_temperature_unit(value_c, normalized_unit)
    return {"value": float(value), "unit": normalized_unit}


def _normalize_plot_and_safety_temperatures(cfg):
    display_unit = normalize_temperature_unit(
        cfg["display"].get("temperatureUnitDefault"),
        default=TEMP_UNIT_C,
    )

    legacy_headroom_c = cfg["plot"].get("yAxisHeadroomC")
    legacy_step_c = cfg["plot"].get("yAxisStepC")
    legacy_max_temp_c = cfg["safety"].get("maxTempC")

    headroom_source = cfg["plot"].get("yAxisHeadroom")
    if legacy_headroom_c is not None and headroom_source == DEFAULT_CONFIG["plot"]["yAxisHeadroom"]:
        headroom_source = legacy_headroom_c

    step_source = cfg["plot"].get("yAxisStep")
    if legacy_step_c is not None and step_source == DEFAULT_CONFIG["plot"]["yAxisStep"]:
        step_source = legacy_step_c

    max_temp_source = cfg["safety"].get("maxTemp")
    if legacy_max_temp_c is not None and max_temp_source == DEFAULT_CONFIG["safety"]["maxTemp"]:
        max_temp_source = legacy_max_temp_c

    headroom_c = _quantity_to_celsius(
        headroom_source,
        default_c=5.0,
        default_unit=TEMP_UNIT_C,
        delta=True,
    )
    step_c = _quantity_to_celsius(
        step_source,
        default_c=5.0,
        default_unit=TEMP_UNIT_C,
        delta=True,
    )
    max_temp_c = _quantity_to_celsius(
        max_temp_source,
        default_c=287.78,
        default_unit=TEMP_UNIT_C,
        delta=False,
    )

    headroom_c = _clamp_float(headroom_c, MIN_Y_AXIS_HEADROOM_C, MAX_Y_AXIS_HEADROOM_C, 5.0)
    step_c = _clamp_float(step_c, MIN_Y_AXIS_STEP_C, MAX_Y_AXIS_STEP_C, 5.0)
    max_temp_c = _clamp_float(max_temp_c, MIN_SAFETY_MAX_TEMP_C, MAX_SAFETY_MAX_TEMP_C, 287.78)

    cfg["plot"]["yAxisHeadroom"] = _celsius_to_quantity(headroom_c, unit=display_unit, delta=True)
    cfg["plot"]["yAxisStep"] = _celsius_to_quantity(step_c, unit=display_unit, delta=True)
    cfg["safety"]["maxTemp"] = _celsius_to_quantity(max_temp_c, unit=display_unit, delta=False)

    cfg["plot"].pop("yAxisHeadroomC", None)
    cfg["plot"].pop("yAxisStepC", None)
    cfg["safety"].pop("maxTempC", None)


def get_config_dir():
    system = platform.system().lower()
    if system == "windows":
        base = os.environ.get("APPDATA", os.path.expanduser("~/AppData/Roaming"))
        return os.path.join(base, "Openroast")
    if system == "darwin":
        return os.path.expanduser("~/Library/Application Support/Openroast")
    return os.path.expanduser("~/.config/openroast")


def get_config_path():
    return os.path.join(get_config_dir(), "config.json")


def _merge_defaults(raw_cfg):
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    if not isinstance(raw_cfg, dict):
        return cfg

    for section in ("display", "ui", "plot", "app", "roast", "control", "safety"):
        incoming = raw_cfg.get(section)
        if isinstance(incoming, dict):
            if section == "control":
                incoming_pid = incoming.get("pid")
                if isinstance(incoming_pid, dict):
                    cfg["control"]["pid"].update(incoming_pid)
                for key, value in incoming.items():
                    if key == "pid":
                        continue
                    cfg["control"][key] = value
            else:
                cfg[section].update(incoming)

    if "configVersion" in raw_cfg:
        cfg["configVersion"] = raw_cfg["configVersion"]
    return cfg


def normalize_config(raw_cfg):
    cfg = _merge_defaults(raw_cfg)

    cfg["display"]["temperatureUnitDefault"] = normalize_temperature_unit(
        cfg["display"].get("temperatureUnitDefault"),
        default=TEMP_UNIT_C,
    )

    cfg["ui"]["compactModeDefault"] = bool(cfg["ui"].get("compactModeDefault", False))
    cfg["ui"]["fullscreenOnStart"] = bool(cfg["ui"].get("fullscreenOnStart", False))
    cfg["ui"]["expertModeEnabled"] = bool(cfg["ui"].get("expertModeEnabled", False))
    cfg["ui"]["refreshIntervalMs"] = _clamp_int(
        cfg["ui"].get("refreshIntervalMs", 1000),
        MIN_REFRESH_INTERVAL_MS,
        MAX_REFRESH_INTERVAL_MS,
        1000,
    )

    _normalize_plot_and_safety_temperatures(cfg)
    cfg["plot"]["showGrid"] = bool(cfg["plot"].get("showGrid", True))
    cfg["plot"]["lineWidth"] = _clamp_float(
        cfg["plot"].get("lineWidth", 3.0),
        MIN_PLOT_LINE_WIDTH,
        MAX_PLOT_LINE_WIDTH,
        3.0,
    )

    backend = cfg["app"].get("backendDefault", "usb")
    if backend not in VALID_BACKENDS:
        backend = "usb"
    cfg["app"]["backendDefault"] = backend
    # V1 autoConnectOnStart is deprecated: app always auto-connects at startup.
    cfg["app"].pop("autoConnectOnStart", None)

    cfg["roast"]["confirmOnStop"] = bool(cfg["roast"].get("confirmOnStop", False))
    cfg["roast"]["confirmOnClear"] = bool(cfg["roast"].get("confirmOnClear", False))

    cfg["control"]["pid"]["kp"] = _clamp_float(
        cfg["control"]["pid"].get("kp", 0.108),
        MIN_PID_KP,
        MAX_PID_KP,
        0.108,
    )
    cfg["control"]["pid"]["ki"] = _clamp_float(
        cfg["control"]["pid"].get("ki", 0.0135),
        MIN_PID_KI,
        MAX_PID_KI,
        0.0135,
    )
    cfg["control"]["pid"]["kd"] = _clamp_float(
        cfg["control"]["pid"].get("kd", 0.018),
        MIN_PID_KD,
        MAX_PID_KD,
        0.018,
    )
    cfg["control"]["pwmCycleSeconds"] = _clamp_float(
        cfg["control"].get("pwmCycleSeconds", 1.0),
        MIN_PWM_CYCLE_SECONDS,
        MAX_PWM_CYCLE_SECONDS,
        1.0,
    )
    cfg["control"]["samplePeriodSeconds"] = _clamp_float(
        cfg["control"].get("samplePeriodSeconds", 0.5),
        MIN_SAMPLE_PERIOD_SECONDS,
        MAX_SAMPLE_PERIOD_SECONDS,
        0.5,
    )

    cfg["safety"]["heaterCutoffEnabled"] = bool(cfg["safety"].get("heaterCutoffEnabled", True))

    cfg["configVersion"] = int(cfg.get("configVersion", 1))
    return cfg


def load_config():
    config_path = get_config_path()
    if not os.path.exists(config_path):
        return copy.deepcopy(DEFAULT_CONFIG)

    try:
        with open(config_path, encoding="utf-8") as handle:
            loaded = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return copy.deepcopy(DEFAULT_CONFIG)

    return normalize_config(loaded)


def save_config(config):
    config_path = get_config_path()
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    normalized = normalize_config(config)
    with open(config_path, "w", encoding="utf-8") as handle:
        json.dump(normalized, handle, indent=4)
    return normalized


def update_config(config, *, display_unit=None, compact_mode=None, fullscreen=None,
                  backend=None, refresh_interval_ms=None,
                  y_axis_headroom_c=None, y_axis_step_c=None, plot_show_grid=None,
                  plot_line_width=None, confirm_on_stop=None, confirm_on_clear=None,
                  expert_mode_enabled=None, pid_kp=None, pid_ki=None, pid_kd=None,
                  pwm_cycle_seconds=None, sample_period_seconds=None,
                  safety_max_temp_c=None, heater_cutoff_enabled=None):
    next_cfg = normalize_config(config)

    if display_unit is not None:
        next_cfg["display"]["temperatureUnitDefault"] = normalize_temperature_unit(
            display_unit,
            default=TEMP_UNIT_C,
        )
    if compact_mode is not None:
        next_cfg["ui"]["compactModeDefault"] = bool(compact_mode)
    if fullscreen is not None:
        next_cfg["ui"]["fullscreenOnStart"] = bool(fullscreen)
    if expert_mode_enabled is not None:
        next_cfg["ui"]["expertModeEnabled"] = bool(expert_mode_enabled)
    if backend is not None and backend in VALID_BACKENDS:
        next_cfg["app"]["backendDefault"] = backend
    if refresh_interval_ms is not None:
        next_cfg["ui"]["refreshIntervalMs"] = _clamp_int(
            refresh_interval_ms,
            MIN_REFRESH_INTERVAL_MS,
            MAX_REFRESH_INTERVAL_MS,
            next_cfg["ui"].get("refreshIntervalMs", 1000),
        )
    current_headroom_c = get_plot_y_axis_headroom_c(next_cfg)
    current_step_c = get_plot_y_axis_step_c(next_cfg)
    current_max_temp_c = get_safety_max_temp_c(next_cfg)

    if y_axis_headroom_c is not None:
        current_headroom_c = _clamp_float(
            y_axis_headroom_c,
            MIN_Y_AXIS_HEADROOM_C,
            MAX_Y_AXIS_HEADROOM_C,
            current_headroom_c,
        )
    if y_axis_step_c is not None:
        current_step_c = _clamp_float(
            y_axis_step_c,
            MIN_Y_AXIS_STEP_C,
            MAX_Y_AXIS_STEP_C,
            current_step_c,
        )
    if plot_show_grid is not None:
        next_cfg["plot"]["showGrid"] = bool(plot_show_grid)
    if plot_line_width is not None:
        next_cfg["plot"]["lineWidth"] = _clamp_float(
            plot_line_width,
            MIN_PLOT_LINE_WIDTH,
            MAX_PLOT_LINE_WIDTH,
            next_cfg["plot"].get("lineWidth", 3.0),
        )
    if confirm_on_stop is not None:
        next_cfg["roast"]["confirmOnStop"] = bool(confirm_on_stop)
    if confirm_on_clear is not None:
        next_cfg["roast"]["confirmOnClear"] = bool(confirm_on_clear)

    if pid_kp is not None:
        next_cfg["control"]["pid"]["kp"] = _clamp_float(
            pid_kp,
            MIN_PID_KP,
            MAX_PID_KP,
            next_cfg["control"]["pid"].get("kp", 0.108),
        )
    if pid_ki is not None:
        next_cfg["control"]["pid"]["ki"] = _clamp_float(
            pid_ki,
            MIN_PID_KI,
            MAX_PID_KI,
            next_cfg["control"]["pid"].get("ki", 0.0135),
        )
    if pid_kd is not None:
        next_cfg["control"]["pid"]["kd"] = _clamp_float(
            pid_kd,
            MIN_PID_KD,
            MAX_PID_KD,
            next_cfg["control"]["pid"].get("kd", 0.018),
        )
    if pwm_cycle_seconds is not None:
        next_cfg["control"]["pwmCycleSeconds"] = _clamp_float(
            pwm_cycle_seconds,
            MIN_PWM_CYCLE_SECONDS,
            MAX_PWM_CYCLE_SECONDS,
            next_cfg["control"].get("pwmCycleSeconds", 1.0),
        )
    if sample_period_seconds is not None:
        next_cfg["control"]["samplePeriodSeconds"] = _clamp_float(
            sample_period_seconds,
            MIN_SAMPLE_PERIOD_SECONDS,
            MAX_SAMPLE_PERIOD_SECONDS,
            next_cfg["control"].get("samplePeriodSeconds", 0.5),
        )
    if safety_max_temp_c is not None:
        current_max_temp_c = _clamp_float(
            safety_max_temp_c,
            MIN_SAFETY_MAX_TEMP_C,
            MAX_SAFETY_MAX_TEMP_C,
            current_max_temp_c,
        )
    if heater_cutoff_enabled is not None:
        next_cfg["safety"]["heaterCutoffEnabled"] = bool(heater_cutoff_enabled)

    effective_unit = next_cfg["display"]["temperatureUnitDefault"]
    next_cfg["plot"]["yAxisHeadroom"] = _celsius_to_quantity(
        current_headroom_c,
        unit=effective_unit,
        delta=True,
    )
    next_cfg["plot"]["yAxisStep"] = _celsius_to_quantity(
        current_step_c,
        unit=effective_unit,
        delta=True,
    )
    next_cfg["safety"]["maxTemp"] = _celsius_to_quantity(
        current_max_temp_c,
        unit=effective_unit,
        delta=False,
    )
    next_cfg["plot"].pop("yAxisHeadroomC", None)
    next_cfg["plot"].pop("yAxisStepC", None)
    next_cfg["safety"].pop("maxTempC", None)

    return next_cfg


def get_plot_y_axis_headroom_c(config):
    cfg = normalize_config(config)
    return _quantity_to_celsius(cfg["plot"].get("yAxisHeadroom"), default_c=5.0, delta=True)


def get_plot_y_axis_step_c(config):
    cfg = normalize_config(config)
    return _quantity_to_celsius(cfg["plot"].get("yAxisStep"), default_c=5.0, delta=True)


def get_safety_max_temp_c(config):
    cfg = normalize_config(config)
    return _quantity_to_celsius(cfg["safety"].get("maxTemp"), default_c=287.78, delta=False)


