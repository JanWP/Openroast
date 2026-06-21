"""Default localroaster hardware driver.

This implementation uses a MAX31855 thermocouple breakout via SPI and drives an
SSR from a digital GPIO pin for low-frequency on/off heater control.
Board-specific pin mappings are loaded from `localroaster/hardware_config.json`
so the public API remains hardware-agnostic.
"""

import logging
import threading
from typing import Any, cast

from localroaster import parameter_catalog
from localroaster.api import ControllerConfig
from localroaster.controller import HardwareDriver
from localroaster.hw_config import load_hw_config

import adafruit_max31855
import board
import digitalio

try:
    from rpi_hardware_pwm import HardwarePWM
except ImportError:  # pragma: no cover - exercised on non-RPi dev hosts
    HardwarePWM = None


class Max31855SsrDriver(HardwareDriver):
    def __init__(self, config: ControllerConfig):
        self.config = config
        self._lock = threading.Lock()

        hw_cfg = load_hw_config()
        thermo_cfg = hw_cfg.get("thermocouple", {})
        heater_cfg = hw_cfg.get("heater", {})
        fan_cfg = hw_cfg.get("fan", {})
        cs_pin_name = str(thermo_cfg.get("cs_pin", "D5"))
        heater_pin_name = str(heater_cfg.get("gpio_pin", "D17"))
        self._heater_active_high = bool(heater_cfg.get("active_high", True))

        self._fan_duty_min_percent = max(
            0.0,
            min(
                100.0,
                float(
                    fan_cfg.get(
                        "duty_min_percent",
                        parameter_catalog.FAN_PWM_DUTY_MIN_DEFAULT_PERCENT,
                    )
                ),
            ),
        )
        self._fan_duty_max_percent = max(
            self._fan_duty_min_percent,
            min(
                100.0,
                float(
                    fan_cfg.get(
                        "duty_max_percent",
                        parameter_catalog.FAN_PWM_DUTY_MAX_DEFAULT_PERCENT,
                    )
                ),
            ),
        )
        self._fan_active_high = bool(fan_cfg.get("active_high", True))
        self._fan_max_speed = max(1, int(fan_cfg.get("max_speed", self.config_max_fan_speed)))
        self._fan_speed = int(parameter_catalog.FAN_SPEED_STANDBY_DEFAULT)
        self._fan_pwm = None

        self._spi = board.SPI()
        cs_pin = getattr(board, cs_pin_name)
        self._cs = digitalio.DigitalInOut(cs_pin)
        self._sensor = adafruit_max31855.MAX31855(self._spi, self._cs)

        heater_pin = getattr(board, heater_pin_name)
        self._heater = digitalio.DigitalInOut(heater_pin)
        self._heater.direction = digitalio.Direction.OUTPUT
        self._heater.value = (not self._heater_active_high)

        if HardwarePWM is None:
            logging.warning(
                "localroaster: rpi_hardware_pwm not available; fan PWM output disabled"
            )
        else:
            pwm_class = cast(Any, HardwarePWM)
            pwm_channel = int(fan_cfg.get("pwm_channel", 1))
            pwm_chip = int(fan_cfg.get("pwm_chip", 0))
            pwm_frequency_hz = max(
                1,
                int(
                    fan_cfg.get(
                        "frequency_hz",
                        parameter_catalog.FAN_PWM_FREQUENCY_DEFAULT_HZ,
                    )
                ),
            )
            self._fan_pwm = pwm_class(
                pwm_channel=pwm_channel,
                hz=pwm_frequency_hz,
                chip=pwm_chip,
            )
            # Initialize fan output to the backend standby speed.
            self._fan_pwm.start(
                self._fan_duty_for_speed(parameter_catalog.FAN_SPEED_STANDBY_DEFAULT)
            )

    @property
    def config_max_fan_speed(self) -> int:
        max_fan = getattr(self.config, "max_fan_speed", None)
        if max_fan is None:
            return int(parameter_catalog.FAN_SPEED_MAX)
        try:
            return max(1, int(str(max_fan)))
        except (TypeError, ValueError):
            return int(parameter_catalog.FAN_SPEED_MAX)

    def _fan_duty_for_speed(self, speed: int) -> float:
        speed = max(0, min(self._fan_max_speed, int(speed)))
        if speed == 0:
            return 0.0 if self._fan_active_high else 100.0
        speed = max(parameter_catalog.FAN_SPEED_MIN, speed)
        if self._fan_max_speed <= 1:
            duty_percent = self._fan_duty_max_percent
        else:
            ratio = float(speed - parameter_catalog.FAN_SPEED_MIN) / float(
                self._fan_max_speed - parameter_catalog.FAN_SPEED_MIN
            )
            duty_percent = self._fan_duty_min_percent + (
                (self._fan_duty_max_percent - self._fan_duty_min_percent) * ratio
            )
        if not self._fan_active_high:
            duty_percent = 100.0 - duty_percent
        return max(0.0, min(100.0, float(duty_percent)))

    def read_temperature_k(self) -> float:
        with self._lock:
            temp_c = self._sensor.temperature
        return float(temp_c) + 273.15

    def set_heater(self, on: bool) -> None:
        with self._lock:
            safe_on = bool(on) and self._fan_speed > 0
            self._heater.value = safe_on if self._heater_active_high else (not safe_on)

    def set_fan_speed(self, speed: int) -> None:
        with self._lock:
            self._fan_speed = max(0, min(self._fan_max_speed, int(speed)))
            if self._fan_speed == 0:
                self._heater.value = (not self._heater_active_high)
            if self._fan_pwm is None:
                return
            self._fan_pwm.change_duty_cycle(self._fan_duty_for_speed(self._fan_speed))

    def close(self) -> None:
        with self._lock:
            if self._fan_pwm is not None:
                try:
                    self._fan_pwm.change_duty_cycle(0.0)
                    self._fan_pwm.stop()
                finally:
                    self._fan_pwm = None
            self._heater.value = (not self._heater_active_high)
            self._heater.deinit()
            self._cs.deinit()



def create_driver(config: ControllerConfig) -> HardwareDriver:
    return Max31855SsrDriver(config)
