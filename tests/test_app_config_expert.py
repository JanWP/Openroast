import unittest
import json
import tempfile
from unittest import mock

from openroast import app_config
from openroast.temperature import TEMP_UNIT_C
from tests.config_sandbox import ConfigSandboxMixin


class AppConfigExpertTests(ConfigSandboxMixin, unittest.TestCase):
    def test_normalize_populates_expert_defaults(self):
        cfg = app_config.normalize_config({})
        self.assertIn("control", cfg)
        self.assertIn("safety", cfg)
        self.assertIn("plantProfiles", cfg["control"])
        self.assertIn("autotuneZnAlpha", cfg["control"])
        self.assertTrue(cfg["safety"]["heaterCutoffEnabled"])

    def test_normalize_builds_plant_profiles_for_known_backends(self):
        cfg = app_config.normalize_config({})
        profiles = cfg["control"]["plantProfiles"]

        for backend in app_config.VALID_BACKENDS:
            with self.subTest(backend=backend):
                self.assertIn(backend, profiles)
                self.assertEqual(
                    set(str(v) for v in range(1, app_config.FAN_SPEED_MAX + 1)),
                    set(profiles[backend].keys()),
                )

    def test_get_set_plant_for_backend_speed_roundtrip(self):
        cfg = app_config.normalize_config({})
        cfg = app_config.set_plant_for_backend_speed(cfg, "local-mock", 4, K=1.25, tau_s=20.5, L=0.7)
        row = app_config.get_profile_row_for_backend_speed(cfg, "local-mock", 4)

        self.assertEqual(row["K"], 1.25)
        self.assertEqual(row["tau_s"], 20.5)
        self.assertEqual(row["L"], 0.7)

    def test_set_plant_for_backend_speed_migrates_legacy_pidprofiles_row(self):
        cfg = app_config.normalize_config(
            {
                "control": {
                    "pidProfiles": {
                        "local-mock": {
                            "2": {
                                "K": 2.1,
                                "tau_s": 25.0,
                                "L": 0.4,
                            }
                        }
                    }
                }
            }
        )

        cfg = app_config.set_plant_for_backend_speed(cfg, "local-mock", 2, K=2.2, tau_s=26.0, L=0.5)
        row = cfg["control"]["plantProfiles"]["local-mock"]["2"]
        self.assertEqual(row["K"], 2.2)
        self.assertEqual(row["tau_s"], 26.0)
        self.assertEqual(row["L"], 0.5)

    def test_set_plant_for_backend_speed_sets_plant_keys(self):
        cfg = app_config.normalize_config(app_config.DEFAULT_CONFIG)

        cfg = app_config.set_plant_for_backend_speed(
            cfg,
            "local-mock",
            3,
            K=1.95,
            tau_s=28.0,
            L=0.55,
        )

        row = cfg["control"]["plantProfiles"]["local-mock"]["3"]
        self.assertAlmostEqual(row["K"], 1.95, places=6)
        self.assertAlmostEqual(row["tau_s"], 28.0, places=6)
        self.assertAlmostEqual(row["L"], 0.55, places=6)

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
        self.assertIn("plantProfiles", saved["control"])

    def test_load_config_auto_migrates_v1_and_preserves_startup_settings(self):
        legacy_v1 = {
            "configVersion": 1,
            "ui": {
                "compactModeDefault": True,
                "fullscreenOnStart": True,
            },
            "app": {
                "backendDefault": "local-mock",
            },
            "control": {
                "pid": {"kp": 0.2, "ki": 0.03, "kd": 0.04},
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_path = f"{tmpdir}/config.json"
            with open(cfg_path, "w", encoding="utf-8") as handle:
                json.dump(legacy_v1, handle, indent=2)

            with mock.patch("openroast.app_config.get_config_path", return_value=cfg_path):
                loaded = app_config.load_config()

            with open(cfg_path, encoding="utf-8") as handle:
                migrated_on_disk = json.load(handle)

        self.assertTrue(loaded["ui"]["compactModeDefault"])
        self.assertTrue(loaded["ui"]["fullscreenOnStart"])
        self.assertEqual(loaded["app"]["backendDefault"], "local-mock")
        self.assertEqual(loaded["configVersion"], app_config.CONFIG_VERSION)

        self.assertEqual(migrated_on_disk["configVersion"], app_config.CONFIG_VERSION)
        self.assertNotIn("pid", migrated_on_disk["control"])
        self.assertIn("plantProfiles", migrated_on_disk["control"])

    def test_save_load_preserves_optional_plant_keys(self):
        cfg = app_config.normalize_config(
            {
                "control": {
                    "plantProfiles": {
                        "local": {
                            "1": {
                                "K": 1.9,
                                "tau_s": 27.0,
                                "L": 0.6,
                            }
                        }
                    }
                }
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_path = f"{tmpdir}/config.json"
            with mock.patch("openroast.app_config.get_config_path", return_value=cfg_path):
                app_config.save_config(cfg)
                loaded = app_config.load_config()

        row = loaded["control"]["plantProfiles"]["local"]["1"]
        self.assertEqual(row["K"], 1.9)
        self.assertEqual(row["tau_s"], 27.0)
        self.assertEqual(row["L"], 0.6)



    def test_update_config_clamps_expert_values(self):
        cfg = app_config.update_config(
            app_config.DEFAULT_CONFIG,
            sample_period_seconds=0.001,
            autotune_zn_alpha=99.0,
            safety_max_temp_c=999.0,
        )
        self.assertEqual(cfg["control"]["samplePeriodSeconds"], app_config.MIN_SAMPLE_PERIOD_SECONDS)
        self.assertEqual(cfg["control"]["autotuneZnAlpha"], app_config.MAX_AUTOTUNE_ZN_ALPHA)
        self.assertEqual(cfg["safety"]["maxTemp"]["unit"], TEMP_UNIT_C)
        self.assertEqual(cfg["safety"]["maxTemp"]["value"], app_config.MAX_SAFETY_MAX_TEMP_C)

    def test_normalize_clamps_autotune_zn_alpha(self):
        cfg_low = app_config.normalize_config({"control": {"autotuneZnAlpha": -1.0}})
        cfg_high = app_config.normalize_config({"control": {"autotuneZnAlpha": 2.0}})
        self.assertEqual(cfg_low["control"]["autotuneZnAlpha"], app_config.MIN_AUTOTUNE_ZN_ALPHA)
        self.assertEqual(cfg_high["control"]["autotuneZnAlpha"], app_config.MAX_AUTOTUNE_ZN_ALPHA)

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

