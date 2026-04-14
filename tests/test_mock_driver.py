import unittest

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


if __name__ == "__main__":
    unittest.main()

