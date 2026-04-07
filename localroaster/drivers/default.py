"""Default localroaster hardware driver.

This implementation uses a MAX31855 thermocouple breakout via SPI and drives an
SSR from a digital GPIO pin for low-frequency on/off heater control.
Board-specific pin mappings are loaded from `localroaster/hardware_config.json`
so the public API remains hardware-agnostic.
"""

import threading

from localroaster.api import ControllerConfig
from localroaster.controller import HardwareDriver
from localroaster.hw_config import load_hw_config

import adafruit_max31855
import board
import digitalio


class Max31855SsrDriver(HardwareDriver):
    def __init__(self, config: ControllerConfig):
        self.config = config
        self._lock = threading.Lock()

        hw_cfg = load_hw_config()
        thermo_cfg = hw_cfg.get("thermocouple", {})
        heater_cfg = hw_cfg.get("heater", {})
        cs_pin_name = str(thermo_cfg.get("cs_pin", "D5"))
        heater_pin_name = str(heater_cfg.get("gpio_pin", "D17"))
        self._heater_active_high = bool(heater_cfg.get("active_high", True))

        self._spi = board.SPI()
        cs_pin = getattr(board, cs_pin_name)
        self._cs = digitalio.DigitalInOut(cs_pin)
        self._sensor = adafruit_max31855.MAX31855(self._spi, self._cs)

        heater_pin = getattr(board, heater_pin_name)
        self._heater = digitalio.DigitalInOut(heater_pin)
        self._heater.direction = digitalio.Direction.OUTPUT
        self._heater.value = (not self._heater_active_high)

    def read_temperature_k(self) -> float:
        with self._lock:
            temp_c = self._sensor.temperature
        return float(temp_c) + 273.15

    def set_heater(self, on: bool) -> None:
        with self._lock:
            self._heater.value = bool(on) if self._heater_active_high else (not bool(on))

    def set_fan_speed(self, speed: int) -> None:
        # Placeholder. Fan control wiring/driver is hardware-specific and can
        # be added later without changing the controller API.
        _ = speed

    def close(self) -> None:
        with self._lock:
            self._heater.value = (not self._heater_active_high)
            self._heater.deinit()
            self._cs.deinit()



def create_driver(config: ControllerConfig) -> HardwareDriver:
    return Max31855SsrDriver(config)
