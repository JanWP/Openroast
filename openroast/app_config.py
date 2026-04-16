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
CONFIG_VERSION = 2

# Openroast-level fan speed bounds. Backend-specific capability discovery
# will be layered on top of these defaults in a follow-up step.
FAN_SPEED_MAX = 9

MIN_REFRESH_INTERVAL_MS = 100
MAX_REFRESH_INTERVAL_MS = 5000
MIN_Y_AXIS_HEADROOM_C = 1.0
MAX_Y_AXIS_HEADROOM_C = 100.0
MIN_Y_AXIS_STEP_C = 1.0
MAX_Y_AXIS_STEP_C = 25.0
MIN_PLOT_LINE_WIDTH = 1.0
MAX_PLOT_LINE_WIDTH = 8.0

MIN_PID_KP = 0.0
MAX_PID_KP = 5.0
MIN_PID_KI = 0.0
MAX_PID_KI = 1.0
MIN_PID_KD = 0.0
MAX_PID_KD = 10.0
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
    "configVersion": CONFIG_VERSION,
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
        "pidProfiles": {},
        "pwmCycleSeconds": 1.0,
        "samplePeriodSeconds": 0.5,
    },
    "safety": {
        "maxTemp": {"value": 287.78, "unit": TEMP_UNIT_C},
        "heaterCutoffEnabled": True,
    },
}


def _to_serializable_config(config):
    """Return normalized config in on-disk v2 shape (without legacy shim keys)."""
    serialized = copy.deepcopy(normalize_config(config))
    serialized.setdefault("control", {}).pop("pid", None)
    serialized["configVersion"] = CONFIG_VERSION
    return serialized


def _default_pid_values():
    return {
        "kp": float(DEFAULT_CONFIG["control"]["pid"]["kp"]),
        "ki": float(DEFAULT_CONFIG["control"]["pid"]["ki"]),
        "kd": float(DEFAULT_CONFIG["control"]["pid"]["kd"]),
    }


def _normalized_pid_values(values):
    source = values if isinstance(values, dict) else {}
    defaults = _default_pid_values()
    return {
        "kp": _clamp_float(source.get("kp"), MIN_PID_KP, MAX_PID_KP, defaults["kp"]),
        "ki": _clamp_float(source.get("ki"), MIN_PID_KI, MAX_PID_KI, defaults["ki"]),
        "kd": _clamp_float(source.get("kd"), MIN_PID_KD, MAX_PID_KD, defaults["kd"]),
    }


def ensure_pid_profile_shape(cfg):
    """Ensure config contains normalized per-backend/per-fan PID tables.

    Unknown backend keys and out-of-default fan rows are preserved if valid.
    """
    if not isinstance(cfg, dict):
        cfg = {}
    control = cfg.setdefault("control", {})
    incoming = control.get("pidProfiles")
    profiles = {}

    if isinstance(incoming, dict):
        for backend_key, backend_rows in incoming.items():
            if not isinstance(backend_rows, dict):
                continue
            normalized_rows = {}
            for fan_key, pid_values in backend_rows.items():
                try:
                    fan_index = int(fan_key)
                except (TypeError, ValueError):
                    continue
                if fan_index < 1:
                    continue
                normalized_rows[str(fan_index)] = _normalized_pid_values(pid_values)
            profiles[str(backend_key)] = normalized_rows

    defaults = _default_pid_values()
    for backend in VALID_BACKENDS:
        rows = profiles.setdefault(backend, {})
        for fan_index in range(1, FAN_SPEED_MAX + 1):
            rows.setdefault(str(fan_index), dict(defaults))

    control["pidProfiles"] = profiles
    return cfg


def get_pid_for_backend_speed(config, backend, fan_speed):
    cfg = normalize_config(config)
    backend_key = str(backend)
    try:
        fan_index = int(fan_speed)
    except (TypeError, ValueError):
        fan_index = 1
    if fan_index < 1:
        fan_index = 1

    profiles = cfg.get("control", {}).get("pidProfiles", {})
    backend_rows = profiles.get(backend_key)
    if not isinstance(backend_rows, dict):
        backend_rows = profiles.get(cfg["app"].get("backendDefault", "usb"), {})
    values = backend_rows.get(str(fan_index), _default_pid_values())
    return _normalized_pid_values(values)


def set_pid_for_backend_speed(config, backend, fan_speed, kp, ki, kd):
    cfg = normalize_config(config)
    backend_key = str(backend)
    try:
        fan_index = int(fan_speed)
    except (TypeError, ValueError):
        fan_index = 1
    fan_index = max(1, fan_index)

    ensure_pid_profile_shape(cfg)
    cfg["control"]["pidProfiles"].setdefault(backend_key, {})
    cfg["control"]["pidProfiles"][backend_key][str(fan_index)] = _normalized_pid_values(
        {"kp": kp, "ki": ki, "kd": kd}
    )
    return cfg


def migrate_legacy_pid_to_backend_profiles(config, *, backend, runtime_fan_max):
    """Copy legacy global PID values into backend fan rows, then drop legacy key."""
    cfg = normalize_config(config)
    ensure_pid_profile_shape(cfg)

    legacy_pid = cfg.get("control", {}).get("pid")
    pid_values = _normalized_pid_values(legacy_pid)
    backend_key = str(backend)
    max_fan = _clamp_int(runtime_fan_max, 1, 10_000, FAN_SPEED_MAX)

    rows = cfg["control"]["pidProfiles"].setdefault(backend_key, {})
    for fan_index in range(1, max_fan + 1):
        rows[str(fan_index)] = dict(pid_values)

    cfg["control"].pop("pid", None)
    cfg["configVersion"] = CONFIG_VERSION
    return cfg


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
                incoming_profiles = incoming.get("pidProfiles")
                if isinstance(incoming_profiles, dict):
                    cfg["control"]["pidProfiles"] = copy.deepcopy(incoming_profiles)
                for key, value in incoming.items():
                    if key in ("pid", "pidProfiles"):
                        continue
                    cfg["control"][key] = value
            else:
                cfg[section].update(incoming)

    if "configVersion" in raw_cfg:
        cfg["configVersion"] = raw_cfg["configVersion"]
    return cfg


def normalize_config(raw_cfg):
    cfg = _merge_defaults(raw_cfg)
    ensure_pid_profile_shape(cfg)

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

    raw_control = raw_cfg.get("control") if isinstance(raw_cfg, dict) else None
    raw_has_profiles = isinstance(raw_control, dict) and isinstance(raw_control.get("pidProfiles"), dict)
    raw_legacy_pid = raw_control.get("pid") if isinstance(raw_control, dict) else None
    if isinstance(raw_legacy_pid, dict) and not raw_has_profiles:
        # Legacy config import: preserve tuned values in current default backend rows.
        backend_default = cfg["app"].get("backendDefault", "usb")
        rows = cfg["control"]["pidProfiles"].setdefault(str(backend_default), {})
        migrated = _normalized_pid_values(raw_legacy_pid)
        for fan_index in range(1, FAN_SPEED_MAX + 1):
            rows[str(fan_index)] = dict(migrated)

    # Runtime compatibility shim during migration window: derive scalar pid from
    # backend-default profile at fan speed 1.
    backend_default = str(cfg["app"].get("backendDefault", "usb"))
    profiles = cfg["control"].get("pidProfiles", {})
    backend_rows = profiles.get(backend_default)
    if not isinstance(backend_rows, dict):
        backend_rows = profiles.get("usb", {})
    compat_pid = _normalized_pid_values(backend_rows.get("1"))
    cfg["control"]["pid"] = dict(compat_pid)
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

    cfg["configVersion"] = CONFIG_VERSION
    return cfg


def load_config():
    config_path = get_config_path()
    config_dir = os.path.dirname(config_path)

    def _read_json_file(path):
        try:
            with open(path, encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, json.JSONDecodeError):
            return None

    loaded = _read_json_file(config_path) if os.path.exists(config_path) else None

    if loaded is None:
        return normalize_config(copy.deepcopy(DEFAULT_CONFIG))

    normalized = normalize_config(loaded)
    # Auto-migrate on read: preserve settings, upgrade schema, and remove
    # legacy scalar control.pid from file contents.
    serialized = _to_serializable_config(normalized)
    if loaded != serialized:
        try:
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            with open(config_path, "w", encoding="utf-8") as handle:
                json.dump(serialized, handle, indent=4)
        except OSError:
            # Migration failure must not block startup; continue with normalized
            # in-memory config.
            pass

    return normalized


def save_config(config):
    config_path = get_config_path()
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    normalized = normalize_config(config)
    serialized = _to_serializable_config(normalized)
    with open(config_path, "w", encoding="utf-8") as handle:
        json.dump(serialized, handle, indent=4)
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
    if pid_kp is not None or pid_ki is not None or pid_kd is not None:
        ensure_pid_profile_shape(next_cfg)
        compat_pid = _normalized_pid_values(next_cfg["control"].get("pid"))
        for backend_rows in next_cfg["control"]["pidProfiles"].values():
            if not isinstance(backend_rows, dict):
                continue
            for fan_key in list(backend_rows.keys()):
                backend_rows[fan_key] = dict(compat_pid)
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


