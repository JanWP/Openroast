import logging
import math
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable

from localroaster.api import ControllerConfig, RoasterState, Telemetry


class HardwareDriver(ABC):
    """Hardware-facing API for a roaster implementation.

    A future GPIO/SPI-backed driver can implement this interface while any
    frontend continues to use the higher-level RoasterController API.
    """

    @abstractmethod
    def read_temperature_f(self) -> float:
        raise NotImplementedError

    @abstractmethod
    def set_heater(self, on: bool) -> None:
        raise NotImplementedError

    @abstractmethod
    def set_fan_speed(self, speed: int) -> None:
        raise NotImplementedError

    def close(self) -> None:
        """Optional shutdown hook for hardware cleanup."""


class PID:
    def __init__(self, kp: float, ki: float, kd: float, output_max: int, output_min: int = 0):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.output_max = output_max
        self.output_min = output_min
        self._integral = 0.0
        self._prev_error = 0.0

    def update(self, current: float, target: float) -> float:
        error = target - current
        self._integral += error
        derivative = error - self._prev_error
        self._prev_error = error
        output = self.kp * error + self.ki * self._integral + self.kd * derivative
        return max(self.output_min, min(self.output_max, output))


class HeatController:
    """Pulse-modulates a bang-bang heater into multiple effective levels."""

    def __init__(self, number_of_segments: int = 8):
        self._num_segments = number_of_segments
        self._output_array = [[False] * number_of_segments for _ in range(1 + number_of_segments)]
        if number_of_segments == 8:
            self._output_array[0] = [False] * 8
            self._output_array[1] = [True, False, False, False, False, False, False, False]
            self._output_array[2] = [True, False, False, False, True, False, False, False]
            self._output_array[3] = [True, False, False, True, False, False, True, False]
            self._output_array[4] = [True, False, True, False, True, False, True, False]
            self._output_array[5] = [True, True, False, True, True, False, True, False]
            self._output_array[6] = [True, True, True, False, True, True, True, False]
            self._output_array[7] = [True, True, True, True, True, True, True, False]
            self._output_array[8] = [True] * 8
        else:
            for i in range(1 + number_of_segments):
                for j in range(number_of_segments):
                    self._output_array[i][j] = j < i
        self._heat_level = 0
        self._heat_level_now = 0
        self._current_index = 0

    @property
    def heat_level(self) -> int:
        return self._heat_level

    @heat_level.setter
    def heat_level(self, value: float) -> None:
        self._heat_level = max(0, min(self._num_segments, int(round(value))))

    def about_to_rollover(self) -> bool:
        return self._current_index >= self._num_segments

    def generate_bangbang_output(self) -> bool:
        if self._current_index >= self._num_segments:
            self._heat_level_now = self._heat_level
            self._current_index = 0
        out = self._output_array[self._heat_level_now][self._current_index]
        self._current_index += 1
        return out


class RoasterController:
    """Reusable, frontend-agnostic roaster controller.

    Owns the machine state, timing, PID loop and hardware I/O while exposing a
    stable API that can be consumed by Openroast, a CLI, or a future web UI.
    """

    def __init__(self, hardware: HardwareDriver, config: ControllerConfig | None = None):
        self.hardware = hardware
        self.config = config or ControllerConfig()

        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._threads_started = False

        self._state = RoasterState.DISCONNECTED
        self._connected = False
        self._target_temp_f = int(self.config.min_display_temp_f)
        self._current_temp_f = self.config.ambient_temp_f
        self._fan_speed = 1
        self._heat_setting = 0
        self._heater_level = 0
        self._heater_output = False
        self._time_remaining_s = 0
        self._total_time_s = 0
        self._fault: str | None = None

        self._telemetry_listeners: list[Callable[[Telemetry], None]] = []
        self._state_transition_callback: Callable[[], None] | None = None

        self._pid = PID(
            self.config.kp,
            self.config.ki,
            self.config.kd,
            output_max=self.config.heater_segments,
            output_min=0,
        )
        self._heater = HeatController(number_of_segments=self.config.heater_segments)

    def connect(self) -> None:
        with self._lock:
            self._connected = True
            if self._state == RoasterState.DISCONNECTED:
                self._state = RoasterState.IDLE
        if not self._threads_started:
            self._threads_started = True
            self._stop_event.clear()
            threading.Thread(target=self._control_loop, name="localroaster-control", daemon=True).start()
            threading.Thread(target=self._timer_loop, name="localroaster-timer", daemon=True).start()
        self._emit_telemetry()

    def shutdown(self) -> None:
        self._stop_event.set()
        with self._lock:
            self._connected = False
            self._state = RoasterState.DISCONNECTED
            self._heater_output = False
            self._heater_level = 0
        try:
            self.hardware.set_heater(False)
            self.hardware.close()
        except Exception as exc:  # pragma: no cover - defensive cleanup
            logging.warning("localroaster: hardware shutdown failed: %s", exc)
        self._emit_telemetry()

    def add_telemetry_listener(self, callback: Callable[[Telemetry], None]) -> None:
        self._telemetry_listeners.append(callback)

    def set_state_transition_callback(self, callback: Callable[[], None] | None) -> None:
        self._state_transition_callback = callback

    def telemetry(self) -> Telemetry:
        with self._lock:
            return Telemetry(
                state=self._state,
                connected=self._connected,
                current_temp_f=self._current_temp_f,
                target_temp_f=self._target_temp_f,
                fan_speed=self._fan_speed,
                heater_output=self._heater_output,
                heater_level=self._heater_level,
                time_remaining_s=self._time_remaining_s,
                total_time_s=self._total_time_s,
                fault=self._fault,
            )

    @property
    def connected(self) -> bool:
        with self._lock:
            return self._connected

    @property
    def state(self) -> RoasterState:
        with self._lock:
            return self._state

    @property
    def current_temp_f(self) -> float:
        with self._lock:
            return self._current_temp_f

    @property
    def target_temp_f(self) -> int:
        with self._lock:
            return self._target_temp_f

    @target_temp_f.setter
    def target_temp_f(self, value: int) -> None:
        if value < self.config.min_display_temp_f or value > self.config.max_temp_f:
            raise ValueError("target_temp_f out of range")
        with self._lock:
            self._target_temp_f = int(value)

    @property
    def fan_speed(self) -> int:
        with self._lock:
            return self._fan_speed

    @fan_speed.setter
    def fan_speed(self, value: int) -> None:
        if value not in range(1, 10):
            raise ValueError("fan_speed must be 1-9")
        with self._lock:
            self._fan_speed = int(value)

    @property
    def heat_setting(self) -> int:
        with self._lock:
            return self._heat_setting

    @heat_setting.setter
    def heat_setting(self, value: int) -> None:
        if value not in range(0, 4):
            raise ValueError("heat_setting must be 0-3")
        with self._lock:
            self._heat_setting = int(value)

    @property
    def heater_level(self) -> int:
        with self._lock:
            return self._heater_level

    @property
    def time_remaining_s(self) -> int:
        with self._lock:
            return self._time_remaining_s

    @time_remaining_s.setter
    def time_remaining_s(self, value: int) -> None:
        with self._lock:
            self._time_remaining_s = max(0, int(value))

    @property
    def total_time_s(self) -> int:
        with self._lock:
            return self._total_time_s

    @total_time_s.setter
    def total_time_s(self, value: int) -> None:
        with self._lock:
            self._total_time_s = max(0, int(value))

    def roast(self) -> None:
        with self._lock:
            self._state = RoasterState.ROASTING
        self._emit_telemetry()

    def cool(self) -> None:
        with self._lock:
            self._state = RoasterState.COOLING
        self._emit_telemetry()

    def idle(self) -> None:
        with self._lock:
            self._state = RoasterState.IDLE
            self._heater_level = 0
            self._heater_output = False
        self._emit_telemetry()

    def sleep(self) -> None:
        with self._lock:
            self._state = RoasterState.SLEEPING
            self._heater_level = 0
            self._heater_output = False
        self._emit_telemetry()

    def _emit_telemetry(self) -> None:
        snapshot = self.telemetry()
        for listener in list(self._telemetry_listeners):
            try:
                listener(snapshot)
            except Exception as exc:  # pragma: no cover - listener safety
                logging.warning("localroaster: telemetry listener failed: %s", exc)

    def _control_loop(self) -> None:
        while not self._stop_event.is_set():
            start = time.monotonic()

            try:
                current_temp = self.hardware.read_temperature_f()
            except Exception as exc:
                logging.warning("localroaster: read_temperature_f failed: %s", exc)
                with self._lock:
                    current_temp = self._current_temp_f
                    self._fault = str(exc)

            with self._lock:
                self._current_temp_f = current_temp
                state = self._state
                thermostat = self.config.thermostat
                target_temp = self._target_temp_f
                heat_setting = self._heat_setting
                fan_speed = self._fan_speed

                if thermostat:
                    if state == RoasterState.ROASTING:
                        if self._heater.about_to_rollover():
                            output = self._pid.update(self._current_temp_f, target_temp)
                            self._heater.heat_level = output
                            self._heater_level = self._heater.heat_level
                        heater_on = self._heater.generate_bangbang_output()
                        self._heater_output = heater_on
                        self._heat_setting = 3 if heater_on else 0
                    else:
                        self._heater.heat_level = 0
                        self._heater_level = 0
                        self._heater_output = False
                        self._heat_setting = 0
                else:
                    self._heater_output = heat_setting > 0
                    self._heater_level = heat_setting

                heater_output = self._heater_output

            try:
                self.hardware.set_heater(heater_output)
                self.hardware.set_fan_speed(fan_speed)
            except Exception as exc:
                logging.warning("localroaster: hardware command failed: %s", exc)
                with self._lock:
                    self._fault = str(exc)

            self._emit_telemetry()
            elapsed = time.monotonic() - start
            sleep_for = self.config.sample_period_s - elapsed
            if sleep_for > 0:
                self._stop_event.wait(sleep_for)

    def _timer_loop(self) -> None:
        while not self._stop_event.is_set():
            with self._lock:
                state = self._state
            if state in (RoasterState.ROASTING, RoasterState.COOLING):
                if self._stop_event.wait(1.0):
                    break
                with self._lock:
                    self._total_time_s += 1
                    if self._time_remaining_s > 0:
                        self._time_remaining_s -= 1
                        should_transition = False
                    else:
                        should_transition = True
                self._emit_telemetry()
                if should_transition:
                    if self._state_transition_callback is not None:
                        try:
                            self._state_transition_callback()
                        except Exception as exc:  # pragma: no cover - listener safety
                            logging.warning("localroaster: state transition callback failed: %s", exc)
                    else:
                        self.idle()
            else:
                if self._stop_event.wait(0.05):
                    break

