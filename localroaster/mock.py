import math
import threading
import time

from localroaster.api import ControllerConfig
from localroaster.controller import HardwareDriver, RoasterController
from localroaster import parameter_catalog


class MockHardwareDriver(HardwareDriver):
    """Simple thermal model for development without physical hardware.
    """

    def __init__(self, config: ControllerConfig | None = None, time_fn=None):
        self.config = config or ControllerConfig()
        self._time_fn = time_fn or time.monotonic
        self._lock = threading.Lock()
        self._temp_k = self.config.ambient_temp_k
        self._heater_on = False
        self._heater_level = float(parameter_catalog.HEATER_PERCENT_MIN)
        self._use_level_control = False
        self._airflow_alpha = max(1e-6, float(self.config.mock_airflow_alpha))
        self._hot_target_k_max_fan = max(
            float(self.config.ambient_temp_k),
            float(self.config.mock_hot_target_k_at_max_fan),
        )
        self._tau_max_fan_s = max(0.1, float(self.config.mock_tau_s_at_max_fan))
        self._fan_speed = 1
        self._last_update_s = float(self._time_fn())

    def read_temperature_k(self) -> float:
        with self._lock:
            now_s = float(self._time_fn())
            dt_s = max(0.0, now_s - self._last_update_s)
            self._last_update_s = now_s

            fan_max = max(1, int(parameter_catalog.FAN_SPEED_MAX))
            fan_fraction = max(0.0, min(1.0, float(self._fan_speed) / float(fan_max)))
            airflow_fraction = max(1e-6, fan_fraction ** self._airflow_alpha)
            hot_target_k = max(
                float(self.config.ambient_temp_k),
                float(self.config.ambient_temp_k)
                + (
                    (self._hot_target_k_max_fan - float(self.config.ambient_temp_k))
                    / airflow_fraction
                ),
            )
            tau_s = max(0.1, self._tau_max_fan_s / airflow_fraction)
            if self._use_level_control:
                if self._heater_level < parameter_catalog.HEATER_PERCENT_MIN:
                    duty = 0.0
                else:
                    duty = min(float(parameter_catalog.HEATER_PERCENT_MAX), float(self._heater_level)) / 100.0
            else:
                duty = 1.0 if self._heater_on else 0.0
            target_k = self.config.ambient_temp_k + duty * (hot_target_k - self.config.ambient_temp_k)
            a = math.exp(-dt_s / tau_s) if dt_s > 0.0 else 1.0
            b = 1.0 - a
            self._temp_k = a * self._temp_k + b * target_k
            return self._temp_k

    def set_heater(self, on: bool) -> None:
        with self._lock:
            self._heater_on = bool(on)
            if not self._use_level_control:
                self._heater_level = (
                    float(parameter_catalog.HEATER_PERCENT_MAX)
                    if self._heater_on
                    else float(parameter_catalog.HEATER_PERCENT_MIN)
                )

    def set_heater_level(self, level_percent: int) -> None:
        with self._lock:
            self._use_level_control = True
            if level_percent < parameter_catalog.HEATER_PERCENT_MIN:
                self._heater_level = 0.0
            else:
                self._heater_level = min(float(parameter_catalog.HEATER_PERCENT_MAX), float(level_percent))

    def reset_simulation(self) -> None:
        with self._lock:
            self._temp_k = self.config.ambient_temp_k
            self._heater_on = False
            self._heater_level = float(parameter_catalog.HEATER_PERCENT_MIN)
            self._use_level_control = False
            self._fan_speed = 1
            self._last_update_s = float(self._time_fn())

    def set_fan_speed(self, speed: int) -> None:
        speed = int(speed)
        if speed not in range(1, parameter_catalog.FAN_SPEED_MAX + 1):
            raise ValueError("fan_speed must be in range 1..FAN_SPEED_MAX")
        with self._lock:
            self._fan_speed = speed


def create_mock_controller(config: ControllerConfig | None = None) -> RoasterController:
    config = config or ControllerConfig()
    return RoasterController(MockHardwareDriver(config), config=config)

