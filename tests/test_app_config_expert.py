import unittest
import json
import tempfile
from unittest import mock

from openroast import app_config
from openroast.temperature import TEMP_UNIT_C


class AppConfigExpertTests(unittest.TestCase):
    def test_normalize_populates_expert_defaults(self):
        cfg = app_config.normalize_config({})
        self.assertIn("control", cfg)
        self.assertIn("safety", cfg)
        self.assertIn("pid", cfg["control"])
        self.assertIn("pidProfiles", cfg["control"])
        self.assertTrue(cfg["safety"]["heaterCutoffEnabled"])

    def test_normalize_builds_pid_profiles_for_known_backends(self):
        cfg = app_config.normalize_config({})
        profiles = cfg["control"]["pidProfiles"]

        for backend in app_config.VALID_BACKENDS:
            with self.subTest(backend=backend):
                self.assertIn(backend, profiles)
                self.assertEqual(
                    set(str(v) for v in range(1, app_config.FAN_SPEED_MAX + 1)),
                    set(profiles[backend].keys()),
                )

    def test_get_set_pid_for_backend_speed_roundtrip(self):
        cfg = app_config.normalize_config({})
        cfg = app_config.set_pid_for_backend_speed(cfg, "local-mock", 4, 0.25, 0.05, 0.10)
        pid_values = app_config.get_pid_for_backend_speed(cfg, "local-mock", 4)

        self.assertEqual(pid_values["kp"], 0.25)
        self.assertEqual(pid_values["ki"], 0.05)
        self.assertEqual(pid_values["kd"], 0.10)

    def test_migrate_legacy_pid_to_backend_profiles(self):
        cfg = app_config.normalize_config(
            {
                "app": {"backendDefault": "local"},
                "control": {
                    "pid": {"kp": 0.4, "ki": 0.06, "kd": 0.8},
                },
            }
        )

        migrated = app_config.migrate_legacy_pid_to_backend_profiles(
            cfg,
            backend="local",
            runtime_fan_max=5,
        )

        self.assertNotIn("pid", migrated["control"])
        for fan in range(1, 6):
            row = migrated["control"]["pidProfiles"]["local"][str(fan)]
            self.assertEqual(row["kp"], 0.4)
            self.assertEqual(row["ki"], 0.06)
            self.assertEqual(row["kd"], 0.8)

    def test_save_config_omits_legacy_control_pid_field(self):
        cfg = app_config.normalize_config({})

        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_path = f"{tmpdir}/config.json"
            with mock.patch("openroast.app_config.get_config_path", return_value=cfg_path):
                app_config.save_config(cfg)

            with open(cfg_path, encoding="utf-8") as handle:
                saved = json.load(handle)

        self.assertIn("control", saved)
        self.assertNotIn("pid", saved["control"])
        self.assertIn("pidProfiles", saved["control"])

    def test_update_config_clamps_expert_values(self):
        cfg = app_config.update_config(
            app_config.DEFAULT_CONFIG,
            pid_kp=99.0,
            sample_period_seconds=0.001,
            safety_max_temp_c=999.0,
        )
        self.assertEqual(cfg["control"]["pid"]["kp"], app_config.MAX_PID_KP)
        self.assertEqual(cfg["control"]["samplePeriodSeconds"], app_config.MIN_SAMPLE_PERIOD_SECONDS)
        self.assertEqual(cfg["safety"]["maxTemp"]["unit"], TEMP_UNIT_C)
        self.assertEqual(cfg["safety"]["maxTemp"]["value"], app_config.MAX_SAFETY_MAX_TEMP_C)

    def test_normalize_migrates_legacy_celsius_plot_keys(self):
        cfg = app_config.normalize_config(
            {
                "plot": {
                    "yAxisHeadroomC": 7.0,
                    "yAxisStepC": 6.0,
                }
            }
        )

        self.assertEqual(app_config.get_plot_y_axis_headroom_c(cfg), 7.0)
        self.assertEqual(app_config.get_plot_y_axis_step_c(cfg), 6.0)


if __name__ == "__main__":
    unittest.main()

