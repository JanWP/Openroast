import math

from localroaster.api import ControllerConfig
from localroaster.controller import HardwareDriver, RoasterController


class MockHardwareDriver(HardwareDriver):
    """Simple thermal model for development without physical hardware."""

    def __init__(self, config: ControllerConfig | None = None):
        self.config = config or ControllerConfig()
        self._temp = self.config.ambient_temp_f
        self._heater_on = False
        self._tau = 30.0
        self._a = math.exp(-self.config.sample_period_s / self._tau)
        self._b = 1.0 - self._a
        self._fan_speed = 1

    def read_temperature_f(self) -> float:
        fan_cooling = (self._fan_speed - 1) * 2.0
        hot_target = max(self.config.max_temp_f - fan_cooling, self.config.ambient_temp_f)
        target = hot_target if self._heater_on else self.config.ambient_temp_f
        self._temp = self._a * self._temp + self._b * target
        return self._temp

    def set_heater(self, on: bool) -> None:
        self._heater_on = bool(on)

    def set_fan_speed(self, speed: int) -> None:
        self._fan_speed = int(speed)


def create_mock_controller(config: ControllerConfig | None = None) -> RoasterController:
    config = config or ControllerConfig()
    return RoasterController(MockHardwareDriver(config), config=config)

