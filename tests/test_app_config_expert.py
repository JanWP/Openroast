import unittest

from openroast import app_config
from openroast.temperature import TEMP_UNIT_C


class AppConfigExpertTests(unittest.TestCase):
    def test_normalize_populates_expert_defaults(self):
        cfg = app_config.normalize_config({})
        self.assertIn("control", cfg)
        self.assertIn("safety", cfg)
        self.assertIn("pid", cfg["control"])
        self.assertTrue(cfg["safety"]["heaterCutoffEnabled"])

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

