import math
import threading
import time

from localroaster.api import ControllerConfig
from localroaster.controller import HardwareDriver, RoasterController


class MockHardwareDriver(HardwareDriver):
    """Simple thermal model for development without physical hardware.
    """

    def __init__(self, config: ControllerConfig | None = None, time_fn=None):
        self.config = config or ControllerConfig()
        self._time_fn = time_fn or time.monotonic
        self._lock = threading.Lock()
        self._temp_k = self.config.ambient_temp_k
        self._heater_on = False
        self._heater_level = 0.0
        self._use_level_control = False
        self._tau = 30.0
        self._thermal_max_temp_k = max(
            float(self.config.ambient_temp_k),
            float(self.config.mock_thermal_max_temp_k),
        )
        self._fan_speed = 1
        self._last_update_s = float(self._time_fn())

    def read_temperature_k(self) -> float:
        with self._lock:
            now_s = float(self._time_fn())
            dt_s = max(0.0, now_s - self._last_update_s)
            self._last_update_s = now_s

            fan_cooling = (self._fan_speed - 1) * 2.0
            hot_target_k = max(self._thermal_max_temp_k - fan_cooling, self.config.ambient_temp_k)
            if self._use_level_control:
                duty = max(0.0, min(100.0, float(self._heater_level))) / 100.0
            else:
                duty = 1.0 if self._heater_on else 0.0
            target_k = self.config.ambient_temp_k + duty * (hot_target_k - self.config.ambient_temp_k)
            a = math.exp(-dt_s / self._tau) if dt_s > 0.0 else 1.0
            b = 1.0 - a
            self._temp_k = a * self._temp_k + b * target_k
            return self._temp_k

    def set_heater(self, on: bool) -> None:
        with self._lock:
            self._heater_on = bool(on)
            if not self._use_level_control:
                self._heater_level = 100.0 if self._heater_on else 0.0

    def set_heater_level(self, level_percent: int) -> None:
        with self._lock:
            self._use_level_control = True
            self._heater_level = max(0.0, min(100.0, float(level_percent)))

    def reset_simulation(self) -> None:
        with self._lock:
            self._temp_k = self.config.ambient_temp_k
            self._heater_on = False
            self._heater_level = 0.0
            self._use_level_control = False
            self._fan_speed = 1
            self._last_update_s = float(self._time_fn())

    def set_fan_speed(self, speed: int) -> None:
        with self._lock:
            self._fan_speed = int(speed)


def create_mock_controller(config: ControllerConfig | None = None) -> RoasterController:
    config = config or ControllerConfig()
    return RoasterController(MockHardwareDriver(config), config=config)

