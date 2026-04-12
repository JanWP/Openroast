import unittest

from localroaster.api import ControllerConfig
from localroaster.mock import MockHardwareDriver


class MockDriverThermalModelTests(unittest.TestCase):
    def test_temperature_tracks_continuous_heater_level(self):
        cfg = ControllerConfig(sample_period_s=0.1, max_temp_k=560.0, ambient_temp_k=295.0)
        driver = MockHardwareDriver(cfg)

        for _ in range(80):
            temp_0 = driver.read_temperature_k()

        driver.set_heater_level(50)
        for _ in range(80):
            temp_50 = driver.read_temperature_k()

        driver.set_heater_level(100)
        for _ in range(80):
            temp_100 = driver.read_temperature_k()

        self.assertGreater(temp_50, temp_0)
        self.assertGreater(temp_100, temp_50)

    def test_reset_simulation_restores_ambient_temperature(self):
        cfg = ControllerConfig(sample_period_s=0.1, max_temp_k=560.0, ambient_temp_k=295.0)
        driver = MockHardwareDriver(cfg)

        driver.set_heater_level(100)
        for _ in range(80):
            heated_temp = driver.read_temperature_k()
        self.assertGreater(heated_temp, cfg.ambient_temp_k)

        driver.reset_simulation()
        reset_temp = driver.read_temperature_k()
        self.assertAlmostEqual(reset_temp, cfg.ambient_temp_k, places=2)


if __name__ == "__main__":
    unittest.main()

