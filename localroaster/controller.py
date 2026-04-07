import logging
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
    def read_temperature_k(self) -> float:
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


class DutyCyclePWM:
    """Generate low-frequency on/off output for an SSR from duty in percent."""

    def __init__(self, cycle_s: float):
        self.cycle_s = max(0.1, float(cycle_s))
        self._cycle_start = time.monotonic()

    def output(self, duty_percent: float, now: float | None = None) -> bool:
        duty = max(0.0, min(100.0, float(duty_percent)))
        if now is None:
            now = time.monotonic()

        elapsed = now - self._cycle_start
        while elapsed >= self.cycle_s:
            self._cycle_start += self.cycle_s
            elapsed = now - self._cycle_start

        on_time = self.cycle_s * (duty / 100.0)
        return elapsed < on_time


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
        self._target_temp_k = float(self.config.min_display_temp_k)
        self._current_temp_k = float(self.config.ambient_temp_k)
        self._fan_speed = 1
        self._heat_setting = 0
        self._heater_level = 0
        self._heater_output = False
        self._time_remaining_s = 0
        self._total_time_s = 0
        self._fault: str | None = None

        self._telemetry_listeners: list[Callable[[Telemetry], None]] = []
        self._heater_output_listeners: list[Callable[[bool], None]] = []
        self._heater_level_listeners: list[Callable[[int], None]] = []
        self._state_transition_callback: Callable[[], None] | None = None

        self._pid = PID(
            self.config.kp,
            self.config.ki,
            self.config.kd,
            output_max=100,
            output_min=0,
        )
        self._pwm = DutyCyclePWM(cycle_s=self.config.pwm_cycle_s)

    def connect(self) -> None:
        with self._lock:
            self._connected = True
            if self._state == RoasterState.DISCONNECTED:
                self._state = RoasterState.IDLE
        if not self._threads_started:
            self._threads_started = True
            self._stop_event.clear()
            threading.Thread(target=self._control_loop, name="localroaster-control", daemon=True).start()
            threading.Thread(target=self._pwm_loop, name="localroaster-pwm", daemon=True).start()
            threading.Thread(target=self._timer_loop, name="localroaster-timer", daemon=True).start()
        self._emit_telemetry()

    def shutdown(self) -> None:
        self._stop_event.set()
        with self._lock:
            self._connected = False
            self._state = RoasterState.DISCONNECTED
        self._set_heater_level(0)
        self._set_heater_output(False, emit_telemetry=False)
        try:
            self.hardware.set_heater(False)
            self.hardware.close()
        except Exception as exc:  # pragma: no cover - defensive cleanup
            logging.warning("localroaster: hardware shutdown failed: %s", exc)
        self._emit_telemetry()

    def add_telemetry_listener(self, callback: Callable[[Telemetry], None]) -> None:
        self._telemetry_listeners.append(callback)

    def add_heater_output_listener(self, callback: Callable[[bool], None]) -> None:
        self._heater_output_listeners.append(callback)

    def add_heater_level_listener(self, callback: Callable[[int], None]) -> None:
        self._heater_level_listeners.append(callback)

    def set_state_transition_callback(self, callback: Callable[[], None] | None) -> None:
        self._state_transition_callback = callback

    def telemetry(self) -> Telemetry:
        with self._lock:
            return Telemetry(
                state=self._state,
                connected=self._connected,
                current_temp_k=self._current_temp_k,
                target_temp_k=self._target_temp_k,
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
    def current_temp_k(self) -> float:
        with self._lock:
            return self._current_temp_k

    @property
    def target_temp_k(self) -> float:
        with self._lock:
            return self._target_temp_k

    @target_temp_k.setter
    def target_temp_k(self, value: float) -> None:
        if value < self.config.min_display_temp_k or value > self.config.max_temp_k:
            raise ValueError("target_temp_k out of range")
        with self._lock:
            self._target_temp_k = float(value)

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
    def heater_output(self) -> bool:
        with self._lock:
            return self._heater_output

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
        self._set_heater_level(0)
        self._set_heater_output(False, emit_telemetry=False)
        self._emit_telemetry()

    def sleep(self) -> None:
        with self._lock:
            self._state = RoasterState.SLEEPING
        self._set_heater_level(0)
        self._set_heater_output(False, emit_telemetry=False)
        self._emit_telemetry()

    def _set_heater_level(self, heater_level: int) -> bool:
        changed = False
        listeners: list[Callable[[int], None]] = []
        heater_level = int(max(0, min(100, int(heater_level))))
        with self._lock:
            if self._heater_level != heater_level:
                self._heater_level = heater_level
                changed = True
                listeners = list(self._heater_level_listeners)

        if not changed:
            return False

        for listener in listeners:
            try:
                listener(heater_level)
            except Exception as exc:  # pragma: no cover - listener safety
                logging.warning("localroaster: heater level listener failed: %s", exc)
        return True

    def _set_heater_output(self, heater_on: bool, emit_telemetry: bool = True) -> bool:
        changed = False
        listeners: list[Callable[[bool], None]] = []
        with self._lock:
            heater_on = bool(heater_on)
            if self._heater_output != heater_on:
                self._heater_output = heater_on
                changed = True
                listeners = list(self._heater_output_listeners)

        if not changed:
            return False

        for listener in listeners:
            try:
                listener(heater_on)
            except Exception as exc:  # pragma: no cover - listener safety
                logging.warning("localroaster: heater listener failed: %s", exc)

        if emit_telemetry:
            self._emit_telemetry()
        return True

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
            current_temp_k = 0.0

            with self._lock:
                current_temp_k = self._current_temp_k

            try:
                current_temp_k = self.hardware.read_temperature_k()
            except Exception as exc:
                logging.warning("localroaster: read_temperature_k failed: %s", exc)
                with self._lock:
                    self._fault = str(exc)

            with self._lock:
                self._current_temp_k = current_temp_k
                state = self._state
                thermostat = self.config.thermostat
                target_temp_k = self._target_temp_k
                heat_setting = self._heat_setting
                fan_speed = self._fan_speed

                if thermostat:
                    if state == RoasterState.ROASTING:
                        pid_percent = self._pid.update(self._current_temp_k, target_temp_k)
                        new_heater_level = int(round(pid_percent))
                        self._heat_setting = 3
                    else:
                        new_heater_level = 0
                        self._heat_setting = 0
                else:
                    # Map legacy heat setting 0..3 to 0..100% duty for PWM.
                    duty_percent = (heat_setting * 100.0) / 3.0
                    new_heater_level = int(round(duty_percent))

                heater_should_off = new_heater_level <= 0

            self._set_heater_level(new_heater_level)

            try:
                self.hardware.set_fan_speed(fan_speed)
            except Exception as exc:
                logging.warning("localroaster: hardware command failed: %s", exc)
                with self._lock:
                    self._fault = str(exc)

            if heater_should_off:
                self._set_heater_output(False)

            self._emit_telemetry()
            elapsed = time.monotonic() - start
            sleep_for = self.config.sample_period_s - elapsed
            if sleep_for > 0:
                self._stop_event.wait(sleep_for)

    def _pwm_loop(self) -> None:
        last_written: bool | None = None
        tick_s = max(0.01, float(self.config.pwm_tick_s))

        while not self._stop_event.is_set():
            start = time.monotonic()

            with self._lock:
                heater_level = self._heater_level

            heater_on = self._pwm.output(heater_level, now=start)

            if heater_on != last_written:
                try:
                    self.hardware.set_heater(heater_on)
                    last_written = heater_on
                except Exception as exc:
                    logging.warning("localroaster: heater command failed: %s", exc)
                    with self._lock:
                        self._fault = str(exc)

            self._set_heater_output(heater_on)

            elapsed = time.monotonic() - start
            sleep_for = tick_s - elapsed
            if sleep_for > 0 and self._stop_event.wait(sleep_for):
                break

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

