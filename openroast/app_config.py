import copy
import json
import os
import platform

from openroast.temperature import TEMP_UNIT_C, TEMP_UNIT_F, TEMP_UNIT_K, normalize_temperature_unit

VALID_BACKENDS = ("usb", "usb-mock", "local", "local-mock")

DEFAULT_CONFIG = {
    "configVersion": 1,
    "display": {
        "temperatureUnitDefault": TEMP_UNIT_C,
    },
    "ui": {
        "compactModeDefault": False,
        "fullscreenOnStart": False,
    },
    "app": {
        "backendDefault": "usb",
        "autoConnectOnStart": True,
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

    for section in ("display", "ui", "app"):
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

    backend = cfg["app"].get("backendDefault", "usb")
    if backend not in VALID_BACKENDS:
        backend = "usb"
    cfg["app"]["backendDefault"] = backend
    cfg["app"]["autoConnectOnStart"] = bool(cfg["app"].get("autoConnectOnStart", True))

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
                  backend=None, auto_connect=None):
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
    if auto_connect is not None:
        next_cfg["app"]["autoConnectOnStart"] = bool(auto_connect)

    return next_cfg

