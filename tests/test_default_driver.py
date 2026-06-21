import importlib
import sys
import types
import unittest
from unittest.mock import patch

from localroaster.api import ControllerConfig
from localroaster import parameter_catalog


class _FakeDigitalInOut:
    def __init__(self, pin):
        self.pin = pin
        self.direction = None
        self.value = None
        self.deinitialized = False

    def deinit(self):
        self.deinitialized = True


class _FakeMax31855:
    def __init__(self, _spi, _cs):
        self.temperature = 25.0


class _FakeHardwarePWM:
    instances = []

    def __init__(self, *, pwm_channel, hz, chip):
        self.pwm_channel = pwm_channel
        self.hz = hz
        self.chip = chip
        self.started_with = None
        self.duty_calls = []
        self.stopped = False
        self.__class__.instances.append(self)

    def start(self, duty_cycle):
        self.started_with = float(duty_cycle)

    def change_duty_cycle(self, duty_cycle):
        self.duty_calls.append(float(duty_cycle))

    def stop(self):
        self.stopped = True


class DefaultDriverPwmTests(unittest.TestCase):
    def _import_driver_module(self, *, with_pwm_module=True):
        fake_board = types.ModuleType("board")
        fake_board.D5 = object()
        fake_board.D17 = object()
        fake_board.SPI = lambda: object()

        fake_digitalio = types.ModuleType("digitalio")
        fake_digitalio.DigitalInOut = _FakeDigitalInOut
        fake_digitalio.Direction = types.SimpleNamespace(OUTPUT="output")

        fake_adafruit = types.ModuleType("adafruit_max31855")
        fake_adafruit.MAX31855 = _FakeMax31855

        fake_modules = {
            "board": fake_board,
            "digitalio": fake_digitalio,
            "adafruit_max31855": fake_adafruit,
        }
        if with_pwm_module:
            fake_pwm = types.ModuleType("rpi_hardware_pwm")
            fake_pwm.HardwarePWM = _FakeHardwarePWM
            fake_modules["rpi_hardware_pwm"] = fake_pwm

        _FakeHardwarePWM.instances = []

        with patch.dict(sys.modules, fake_modules, clear=False):
            if not with_pwm_module:
                sys.modules.pop("rpi_hardware_pwm", None)
            sys.modules.pop("localroaster.drivers.default", None)
            return importlib.import_module("localroaster.drivers.default")

    def test_set_fan_speed_uses_hardware_pwm_linear_mapping(self):
        module = self._import_driver_module(with_pwm_module=True)
        cfg = {
            "thermocouple": {"cs_pin": "D5"},
            "heater": {"gpio_pin": "D17", "active_high": True},
            "fan": {
                "pwm_chip": 0,
                "pwm_channel": 1,
                "frequency_hz": 2000,
                "duty_min_percent": 15.0,
                "duty_max_percent": 90.0,
                "active_high": True,
                "max_speed": 3,
            },
        }

        with patch.object(module, "load_hw_config", return_value=cfg):
            driver = module.Max31855SsrDriver(ControllerConfig())

        self.assertEqual(len(_FakeHardwarePWM.instances), 1)
        pwm = _FakeHardwarePWM.instances[0]
        self.assertEqual(pwm.pwm_channel, 1)
        self.assertEqual(pwm.hz, 2000)
        self.assertAlmostEqual(pwm.started_with, 15.0, places=4)

        driver.set_fan_speed(0)
        driver.set_fan_speed(2)
        driver.set_fan_speed(3)
        self.assertAlmostEqual(pwm.duty_calls[-3], 0.0, places=4)
        self.assertAlmostEqual(pwm.duty_calls[-2], 52.5, places=4)
        self.assertAlmostEqual(pwm.duty_calls[-1], 90.0, places=4)

        driver.close()
        self.assertTrue(pwm.stopped)
        self.assertAlmostEqual(pwm.duty_calls[-1], 0.0, places=4)

    def test_set_fan_speed_supports_active_low_pwm(self):
        module = self._import_driver_module(with_pwm_module=True)
        cfg = {
            "thermocouple": {"cs_pin": "D5"},
            "heater": {"gpio_pin": "D17", "active_high": True},
            "fan": {
                "pwm_channel": 1,
                "frequency_hz": 5000,
                "duty_min_percent": 20.0,
                "duty_max_percent": 80.0,
                "active_high": False,
                "max_speed": 3,
            },
        }

        with patch.object(module, "load_hw_config", return_value=cfg):
            driver = module.Max31855SsrDriver(ControllerConfig())

        pwm = _FakeHardwarePWM.instances[0]
        self.assertEqual(pwm.hz, 5000)
        # Speed 1 maps to min duty (20%), then active-low inversion -> 80%.
        self.assertAlmostEqual(pwm.started_with, 80.0, places=4)

        driver.set_fan_speed(3)
        # Speed 3 maps to max duty (80%), then inversion -> 20%.
        self.assertAlmostEqual(pwm.duty_calls[-1], 20.0, places=4)

        driver.set_fan_speed(0)
        # Speed 0 is fan off; active-low off maps to 100% duty.
        self.assertAlmostEqual(pwm.duty_calls[-1], 100.0, places=4)

    def test_heater_cannot_turn_on_when_fan_speed_is_zero(self):
        module = self._import_driver_module(with_pwm_module=True)
        cfg = {
            "thermocouple": {"cs_pin": "D5"},
            "heater": {"gpio_pin": "D17", "active_high": True},
            "fan": {"pwm_channel": 1, "frequency_hz": 2000},
        }

        with patch.object(module, "load_hw_config", return_value=cfg):
            driver = module.Max31855SsrDriver(ControllerConfig())

        driver.set_fan_speed(0)
        driver.set_heater(True)
        self.assertFalse(driver._heater.value)

    def test_driver_keeps_running_when_pwm_library_is_missing(self):
        module = self._import_driver_module(with_pwm_module=False)
        cfg = {
            "thermocouple": {"cs_pin": "D5"},
            "heater": {"gpio_pin": "D17", "active_high": True},
            "fan": {"pwm_channel": 1, "frequency_hz": 25000},
        }

        with patch.object(module, "load_hw_config", return_value=cfg):
            driver = module.Max31855SsrDriver(ControllerConfig())

        driver.set_fan_speed(3)
        driver.close()

        self.assertEqual(_FakeHardwarePWM.instances, [])

    def test_driver_uses_parameter_catalog_defaults_when_fan_tunables_missing(self):
        module = self._import_driver_module(with_pwm_module=True)
        cfg = {
            "thermocouple": {"cs_pin": "D5"},
            "heater": {"gpio_pin": "D17", "active_high": True},
            "fan": {"pwm_chip": 0, "pwm_channel": 1, "active_high": True, "max_speed": 3},
        }

        with patch.object(module, "load_hw_config", return_value=cfg):
            driver = module.Max31855SsrDriver(ControllerConfig())

        pwm = _FakeHardwarePWM.instances[0]
        self.assertEqual(pwm.hz, parameter_catalog.FAN_PWM_FREQUENCY_DEFAULT_HZ)
        self.assertAlmostEqual(
            pwm.started_with,
            parameter_catalog.FAN_PWM_DUTY_MIN_DEFAULT_PERCENT,
            places=4,
        )

        driver.set_fan_speed(3)
        self.assertAlmostEqual(
            pwm.duty_calls[-1],
            parameter_catalog.FAN_PWM_DUTY_MAX_DEFAULT_PERCENT,
            places=4,
        )

    def test_driver_startup_pwm_uses_configured_standby_fan_speed(self):
        module = self._import_driver_module(with_pwm_module=True)
        cfg = {
            "thermocouple": {"cs_pin": "D5"},
            "heater": {"gpio_pin": "D17", "active_high": True},
            "fan": {
                "pwm_chip": 0,
                "pwm_channel": 1,
                "frequency_hz": 2000,
                "duty_min_percent": 15.0,
                "duty_max_percent": 90.0,
                "active_high": True,
                "max_speed": 9,
            },
        }

        with patch.object(module.parameter_catalog, "FAN_SPEED_STANDBY_DEFAULT", 9):
            with patch.object(module, "load_hw_config", return_value=cfg):
                module.Max31855SsrDriver(ControllerConfig())

        pwm = _FakeHardwarePWM.instances[0]
        self.assertAlmostEqual(pwm.started_with, 90.0, places=4)


if __name__ == "__main__":
    unittest.main()

