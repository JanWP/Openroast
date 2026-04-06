import json
import os
import sys

from localroaster.hw_config import ENV_VAR, load_hw_config, resolve_hw_config_path


def main() -> int:
    cfg_path = resolve_hw_config_path()

    try:
        config = load_hw_config(cfg_path)
    except FileNotFoundError:
        env_value = os.environ.get(ENV_VAR)
        if env_value:
            print(
                f"error: config file not found: {env_value} (from {ENV_VAR})",
                file=sys.stderr,
            )
        else:
            print(f"error: default hardware config not found: {cfg_path}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(
            f"error: invalid JSON in {cfg_path} at line {exc.lineno}, column {exc.colno}: {exc.msg}",
            file=sys.stderr,
        )
        return 1
    except OSError as exc:
        print(f"error: failed to read config from {cfg_path}: {exc}", file=sys.stderr)
        return 1

    print(f"Active hardware config path: {cfg_path}")
    print(json.dumps(config, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
