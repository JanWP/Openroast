import unittest
import math
from unittest.mock import patch

from localroaster.api import ControllerConfig
from localroaster.mock import MockHardwareDriver


class _FakeClock:
    def __init__(self):
        self._t = 0.0

    def monotonic(self):
        return self._t

    def advance(self, dt_s):
        self._t += float(dt_s)


class MockDriverThermalModelTests(unittest.TestCase):
    @staticmethod
    def _run_for(driver, clock, *, dt_s, steps):
        temp_k = driver.read_temperature_k()
        for _ in range(steps):
            clock.advance(dt_s)
            temp_k = driver.read_temperature_k()
        return temp_k

    def test_temperature_tracks_continuous_heater_level(self):
        cfg = ControllerConfig(sample_period_s=0.1, max_temp_k=560.0, ambient_temp_k=295.0)
        clock = _FakeClock()
        driver = MockHardwareDriver(cfg, time_fn=clock.monotonic)

        temp_0 = self._run_for(driver, clock, dt_s=0.1, steps=80)

        driver.set_heater_level(50)
        temp_50 = self._run_for(driver, clock, dt_s=0.1, steps=80)

        driver.set_heater_level(100)
        temp_100 = self._run_for(driver, clock, dt_s=0.1, steps=80)

        self.assertGreater(temp_50, temp_0)
        self.assertGreater(temp_100, temp_50)

    def test_reset_simulation_restores_ambient_temperature(self):
        cfg = ControllerConfig(sample_period_s=0.1, max_temp_k=560.0, ambient_temp_k=295.0)
        clock = _FakeClock()
        driver = MockHardwareDriver(cfg, time_fn=clock.monotonic)

        driver.set_heater_level(100)
        heated_temp = self._run_for(driver, clock, dt_s=0.1, steps=80)
        self.assertGreater(heated_temp, cfg.ambient_temp_k)

        driver.reset_simulation()
        reset_temp = driver.read_temperature_k()
        self.assertAlmostEqual(reset_temp, cfg.ambient_temp_k, places=2)

    def test_temperature_is_invariant_to_read_cadence_for_same_elapsed_time(self):
        cfg = ControllerConfig(sample_period_s=0.5, max_temp_k=560.0, ambient_temp_k=295.0)

        slow_clock = _FakeClock()
        slow_driver = MockHardwareDriver(cfg, time_fn=slow_clock.monotonic)
        slow_driver.set_heater_level(100)
        slow_temp_k = self._run_for(slow_driver, slow_clock, dt_s=0.5, steps=120)  # 60 s

        fast_clock = _FakeClock()
        fast_driver = MockHardwareDriver(cfg, time_fn=fast_clock.monotonic)
        fast_driver.set_heater_level(100)
        fast_temp_k = self._run_for(fast_driver, fast_clock, dt_s=0.1, steps=600)  # 60 s

        self.assertAlmostEqual(fast_temp_k, slow_temp_k, places=6)

    def test_temperature_is_invariant_to_config_sample_period_for_same_elapsed_time(self):
        slow_cfg = ControllerConfig(sample_period_s=0.5, max_temp_k=560.0, ambient_temp_k=295.0)
        fast_cfg = ControllerConfig(sample_period_s=0.1, max_temp_k=560.0, ambient_temp_k=295.0)

        slow_clock = _FakeClock()
        slow_driver = MockHardwareDriver(slow_cfg, time_fn=slow_clock.monotonic)
        slow_driver.set_heater_level(100)
        slow_temp_k = self._run_for(slow_driver, slow_clock, dt_s=0.1, steps=600)  # 60 s

        fast_clock = _FakeClock()
        fast_driver = MockHardwareDriver(fast_cfg, time_fn=fast_clock.monotonic)
        fast_driver.set_heater_level(100)
        fast_temp_k = self._run_for(fast_driver, fast_clock, dt_s=0.1, steps=600)  # 60 s

        self.assertAlmostEqual(fast_temp_k, slow_temp_k, places=6)

    def test_live_fan_speed_change_affects_next_temperature_sample(self):
        cfg = ControllerConfig(
            sample_period_s=0.1,
            max_temp_k=560.0,
            ambient_temp_k=295.0,
            mock_airflow_alpha=0.5,
            mock_hot_target_k_at_max_fan=544.93,
            mock_tau_s_at_max_fan=15.0,
        )
        clock = _FakeClock()
        driver = MockHardwareDriver(cfg, time_fn=clock.monotonic)
        driver.set_heater_level(100)

        # Warm state so fan cooling effect is measurable.
        self._run_for(driver, clock, dt_s=0.1, steps=220)

        # Establish a common pre-step state at fan=1.
        driver.set_fan_speed(1)
        clock.advance(0.1)
        temp_pre = driver.read_temperature_k()

        dt_s = 0.1
        fan_max = 3.0
        ambient = float(cfg.ambient_temp_k)
        u_f1 = max(1e-6, (1.0 / fan_max) ** float(cfg.mock_airflow_alpha))
        u_f3 = max(1e-6, (3.0 / fan_max) ** float(cfg.mock_airflow_alpha))
        tau_f1 = float(cfg.mock_tau_s_at_max_fan) / u_f1
        tau_f3 = float(cfg.mock_tau_s_at_max_fan) / u_f3
        hot_target_f1 = ambient + ((float(cfg.mock_hot_target_k_at_max_fan) - ambient) / u_f1)
        hot_target_f3 = ambient + ((float(cfg.mock_hot_target_k_at_max_fan) - ambient) / u_f3)

        a = math.exp(-dt_s / tau_f3)
        b = 1.0 - a
        predicted_next_f1 = math.exp(-dt_s / tau_f1) * temp_pre + (1.0 - math.exp(-dt_s / tau_f1)) * hot_target_f1
        predicted_next_f3 = a * temp_pre + b * hot_target_f3

        # Live change to fan=3 must affect the immediate next sample.
        driver.set_fan_speed(3)
        clock.advance(dt_s)
        temp_post = driver.read_temperature_k()

        self.assertAlmostEqual(temp_post, predicted_next_f3, places=9)
        self.assertLess(predicted_next_f3, predicted_next_f1)

    def test_same_normalized_fan_fraction_matches_across_3_and_9_speed_configs(self):
        cfg = ControllerConfig(
            sample_period_s=0.1,
            ambient_temp_k=295.0,
            mock_airflow_alpha=0.5,
            mock_hot_target_k_at_max_fan=544.93,
            mock_tau_s_at_max_fan=15.0,
        )

        # Fan fraction 1/3: i=1,N=3 and i=3,N=9.
        clock_a = _FakeClock()
        with patch("localroaster.parameter_catalog.FAN_SPEED_MAX", 3):
            driver_a = MockHardwareDriver(cfg, time_fn=clock_a.monotonic)
            driver_a.set_heater_level(100)
            driver_a.set_fan_speed(1)
            self._run_for(driver_a, clock_a, dt_s=0.1, steps=80)
            clock_a.advance(0.1)
            temp_a = driver_a.read_temperature_k()

        clock_b = _FakeClock()
        with patch("localroaster.parameter_catalog.FAN_SPEED_MAX", 9):
            driver_b = MockHardwareDriver(cfg, time_fn=clock_b.monotonic)
            driver_b.set_heater_level(100)
            driver_b.set_fan_speed(3)
            self._run_for(driver_b, clock_b, dt_s=0.1, steps=80)
            clock_b.advance(0.1)
            temp_b = driver_b.read_temperature_k()

        self.assertAlmostEqual(temp_a, temp_b, places=6)


if __name__ == "__main__":
    unittest.main()

