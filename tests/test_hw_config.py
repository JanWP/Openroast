import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from localroaster.hw_config import ENV_VAR, load_hw_config_with_path, resolve_hw_config_path


class HwConfigTests(unittest.TestCase):
    def test_resolve_hw_config_path_uses_explicit_path_over_env(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            explicit = Path(tmp_dir) / "explicit.json"
            env_path = Path(tmp_dir) / "env.json"
            explicit.write_text("{}", encoding="utf-8")
            env_path.write_text("{}", encoding="utf-8")

            with patch.dict(os.environ, {ENV_VAR: str(env_path)}, clear=False):
                resolved = resolve_hw_config_path(str(explicit))

            self.assertEqual(resolved, explicit)

    def test_resolve_hw_config_path_uses_env_when_no_explicit(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_path = Path(tmp_dir) / "env.json"
            env_path.write_text("{}", encoding="utf-8")

            with patch.dict(os.environ, {ENV_VAR: str(env_path)}, clear=False):
                resolved = resolve_hw_config_path()

            self.assertEqual(resolved, env_path)

    def test_resolve_hw_config_path_falls_back_to_package_default(self):
        with patch.dict(os.environ, {}, clear=True):
            resolved = resolve_hw_config_path()

        expected = Path(__file__).resolve().parent.parent / "localroaster" / "hardware_config.json"
        self.assertEqual(resolved, expected)

    def test_load_hw_config_with_path_returns_resolved_path_and_json(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_path = Path(tmp_dir) / "hw.json"
            cfg_data = {"heater": {"pin": 18}, "sensor": {"type": "MAX31855"}}
            cfg_path.write_text(json.dumps(cfg_data), encoding="utf-8")

            loaded_path, loaded_config = load_hw_config_with_path(cfg_path)

        self.assertEqual(loaded_path, cfg_path)
        self.assertEqual(loaded_config, cfg_data)


if __name__ == "__main__":
    unittest.main()

