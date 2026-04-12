import copy
import json
import os
import platform

from openroast.temperature import TEMP_UNIT_C, TEMP_UNIT_F, TEMP_UNIT_K, normalize_temperature_unit

VALID_BACKENDS = ("usb", "usb-mock", "local", "local-mock")

MIN_REFRESH_INTERVAL_MS = 100
MAX_REFRESH_INTERVAL_MS = 5000
MIN_Y_AXIS_HEADROOM_C = 1.0
MAX_Y_AXIS_HEADROOM_C = 100.0
MIN_Y_AXIS_STEP_C = 1.0
MAX_Y_AXIS_STEP_C = 25.0
MIN_PLOT_LINE_WIDTH = 1.0
MAX_PLOT_LINE_WIDTH = 8.0


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
    },
    "plot": {
        "yAxisHeadroomC": 5.0,
        "yAxisStepC": 5.0,
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
}


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

    for section in ("display", "ui", "plot", "app", "roast"):
        incoming = raw_cfg.get(section)
        if isinstance(incoming, dict):
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
    cfg["ui"]["refreshIntervalMs"] = _clamp_int(
        cfg["ui"].get("refreshIntervalMs", 1000),
        MIN_REFRESH_INTERVAL_MS,
        MAX_REFRESH_INTERVAL_MS,
        1000,
    )

    cfg["plot"]["yAxisHeadroomC"] = _clamp_float(
        cfg["plot"].get("yAxisHeadroomC", 5.0),
        MIN_Y_AXIS_HEADROOM_C,
        MAX_Y_AXIS_HEADROOM_C,
        5.0,
    )
    cfg["plot"]["yAxisStepC"] = _clamp_float(
        cfg["plot"].get("yAxisStepC", 5.0),
        MIN_Y_AXIS_STEP_C,
        MAX_Y_AXIS_STEP_C,
        5.0,
    )
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
                  plot_line_width=None, confirm_on_stop=None, confirm_on_clear=None):
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
    if backend is not None and backend in VALID_BACKENDS:
        next_cfg["app"]["backendDefault"] = backend
    if refresh_interval_ms is not None:
        next_cfg["ui"]["refreshIntervalMs"] = _clamp_int(
            refresh_interval_ms,
            MIN_REFRESH_INTERVAL_MS,
            MAX_REFRESH_INTERVAL_MS,
            next_cfg["ui"].get("refreshIntervalMs", 1000),
        )
    if y_axis_headroom_c is not None:
        next_cfg["plot"]["yAxisHeadroomC"] = _clamp_float(
            y_axis_headroom_c,
            MIN_Y_AXIS_HEADROOM_C,
            MAX_Y_AXIS_HEADROOM_C,
            next_cfg["plot"].get("yAxisHeadroomC", 5.0),
        )
    if y_axis_step_c is not None:
        next_cfg["plot"]["yAxisStepC"] = _clamp_float(
            y_axis_step_c,
            MIN_Y_AXIS_STEP_C,
            MAX_Y_AXIS_STEP_C,
            next_cfg["plot"].get("yAxisStepC", 5.0),
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

    return next_cfg

