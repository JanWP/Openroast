import json
import os
from pathlib import Path
from typing import Any

ENV_VAR = "LOCALROASTER_HW_CONFIG"


def resolve_hw_config_path(path: str | Path | None = None) -> Path:
    """Resolve the hardware config path from arg, env var, or package default."""
    if path is not None:
        return Path(path).expanduser()

    cfg_path = os.environ.get(ENV_VAR)
    if cfg_path:
        return Path(cfg_path).expanduser()

    return Path(__file__).resolve().parent / "hardware_config.json"


def load_hw_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load hardware configuration JSON as a dict."""
    _, config = load_hw_config_with_path(path)
    return config


def load_hw_config_with_path(
    path: str | Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Load hardware config and return both path and parsed JSON."""
    cfg_path = resolve_hw_config_path(path)
    with cfg_path.open("r", encoding="utf-8") as handle:
        return cfg_path, json.load(handle)

