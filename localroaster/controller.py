import atexit
import logging
import os
import signal
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

    def set_heater_level(self, level_percent: int) -> None:
        """Optional hook for drivers that can consume continuous heater duty.

        Real GPIO/SSR drivers typically ignore this and use set_heater(on/off)
        from the PWM loop. Simulated drivers can use this for smoother thermal
        integration than edge-only on/off state.
        """

    def reset_simulation(self) -> None:
        """Optional hook for simulated drivers to restore initial state."""

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

    def reset(self) -> None:
        """Clear accumulated state for a fresh control session."""
        self._integral = 0.0
        self._prev_error = 0.0

    def update(self, current: float, target: float) -> float:
        error = target - current
        self._integral += error
        # Anti-windup: clamp integral so that ki * integral stays within output range.
        if self.ki != 0.0:
            integral_max = self.output_max / self.ki
            integral_min = self.output_min / self.ki
            self._integral = max(integral_min, min(integral_max, self._integral))
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
        state, _ = self.state_and_delay(duty_percent, now=now)
        return state

    def state_and_delay(self, duty_percent: float, now: float | None = None) -> tuple[bool, float]:
        duty = max(0.0, min(100.0, float(duty_percent)))
        if now is None:
            now = time.monotonic()

        elapsed = now - self._cycle_start
        while elapsed >= self.cycle_s:
            self._cycle_start += self.cycle_s
            elapsed = now - self._cycle_start

        on_time = self.cycle_s * (duty / 100.0)
        heater_on = elapsed < on_time

        if duty <= 0.0 or duty >= 100.0:
            # No intra-cycle edge; wake at cycle boundary (or earlier on level change).
            delay_s = self.cycle_s - elapsed
        elif heater_on:
            # Next edge is falling edge at on_time.
            delay_s = on_time - elapsed
        else:
            # Next edge is rising edge at next cycle boundary.
            delay_s = self.cycle_s - elapsed

        return heater_on, max(0.001, float(delay_s))


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
        self._pwm_wake_event = threading.Event()
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
        self._exit_handler_registered = False

    # ------------------------------------------------------------------
    # Emergency shutdown on unexpected exit (atexit / SIGTERM)
    # ------------------------------------------------------------------

    def _register_exit_handler(self) -> None:
        """Register atexit + SIGTERM hooks that force the heater off.

        Only signals that Python can handle are covered (SIGTERM, SIGINT).
        A hard kill (SIGKILL / power loss) cannot be caught in software.
        """
        if self._exit_handler_registered:
            return
        self._exit_handler_registered = True

        atexit.register(self._emergency_heater_off)

        for sig in (signal.SIGTERM, signal.SIGINT):
            prev = signal.getsignal(sig)
            # Wrap any previous handler so we don't swallow it.

            def _handler(signum, frame, _prev=prev):  # noqa: E301
                self._emergency_heater_off()
                if callable(_prev) and _prev not in (signal.SIG_DFL, signal.SIG_IGN):
                    _prev(signum, frame)
                elif _prev == signal.SIG_DFL:
                    # Re-raise with default action so the process still exits.
                    signal.signal(signum, signal.SIG_DFL)
                    os.kill(os.getpid(), signum)

            try:
                signal.signal(sig, _handler)
            except (OSError, ValueError):
                # signal.signal() must be called from the main thread;
                # if connect() is called from a worker thread, skip gracefully.
                logging.debug(
                    "localroaster: cannot register %s handler from non-main thread", sig.name
                )

    def _emergency_heater_off(self) -> None:
        """Best-effort attempt to turn the heater off during process teardown."""
        try:
            self.hardware.set_heater(False)
        except Exception:  # pragma: no cover - last-resort safety
            pass

    def connect(self) -> None:
        with self._lock:
            self._connected = True
            if self._state == RoasterState.DISCONNECTED:
                self._state = RoasterState.IDLE
        self._register_exit_handler()
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
        self._pwm_wake_event.set()
        try:
            self.hardware.set_heater(False)
            self.hardware.close()
        except Exception as exc:  # pragma: no cover - defensive cleanup
            logging.warning("localroaster: hardware shutdown failed: %s", exc)
        self._emit_telemetry()

    def reset_simulation_state(self) -> None:
        """Best-effort reset for simulation backends.

        Real hardware drivers may not implement this hook; in that case this is
        a no-op.
        """
        reset_sim = getattr(self.hardware, "reset_simulation", None)
        if callable(reset_sim):
            try:
                reset_sim()
            except Exception as exc:  # pragma: no cover - defensive handling
                logging.warning("localroaster: reset_simulation failed: %s", exc)
                with self._lock:
                    self._fault = str(exc)
                return

            try:
                current_temp_k = self.hardware.read_temperature_k()
            except Exception as exc:  # pragma: no cover - defensive handling
                logging.warning("localroaster: read_temperature_k failed after reset: %s", exc)
                with self._lock:
                    self._fault = str(exc)
            else:
                with self._lock:
                    self._current_temp_k = current_temp_k
                    self._fault = None
                self._emit_telemetry()

    def apply_runtime_config(
        self,
        *,
        kp: float | None = None,
        ki: float | None = None,
        kd: float | None = None,
        pwm_cycle_s: float | None = None,
        sample_period_s: float | None = None,
        max_temp_k: float | None = None,
        heater_cutoff_enabled: bool | None = None,
    ) -> None:
        """Apply controller tuning/safety changes while running."""
        with self._lock:
            if kp is not None:
                self.config.kp = float(kp)
                self._pid.kp = float(kp)
            if ki is not None:
                self.config.ki = float(ki)
                self._pid.ki = float(ki)
            if kd is not None:
                self.config.kd = float(kd)
                self._pid.kd = float(kd)
            if pwm_cycle_s is not None:
                cycle_s = max(0.1, float(pwm_cycle_s))
                self.config.pwm_cycle_s = cycle_s
                self._pwm.cycle_s = cycle_s
            if sample_period_s is not None:
                self.config.sample_period_s = max(0.01, float(sample_period_s))
            if max_temp_k is not None:
                max_temp_k = float(max_temp_k)
                self.config.max_temp_k = max_temp_k
                if self._target_temp_k > max_temp_k:
                    self._target_temp_k = max_temp_k
            if heater_cutoff_enabled is not None:
                self.config.heater_cutoff_enabled = bool(heater_cutoff_enabled)

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
            if self._state != RoasterState.ROASTING:
                self._pid.reset()
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

        if changed:
            # Recompute PWM edge timing immediately on duty updates.
            self._pwm_wake_event.set()

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

    @staticmethod
    def _kelvin_to_celsius(temp_k: float) -> float:
        return float(temp_k) - 273.15

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
                max_temp_k = self.config.max_temp_k
                cutoff_enabled = bool(self.config.heater_cutoff_enabled)

                # Over-temperature safety: force heater off regardless of mode.
                if cutoff_enabled and current_temp_k > max_temp_k:
                    new_heater_level = 0
                    self._heat_setting = 0
                    if self._fault is None:
                        self._fault = "over-temperature safety cutoff"
                    logging.warning(
                        "localroaster: over-temperature cutoff at %.1f K (max %.1f K)",
                        current_temp_k,
                        max_temp_k,
                    )
                elif thermostat:
                    if state == RoasterState.ROASTING:
                        current_temp_c = self._kelvin_to_celsius(self._current_temp_k)
                        target_temp_c = self._kelvin_to_celsius(target_temp_k)
                        pid_percent = self._pid.update(current_temp_c, target_temp_c)
                        new_heater_level = int(round(pid_percent))
                        self._heat_setting = 3
                    else:
                        new_heater_level = 0
                        self._heat_setting = 0
                else:
                    # Non-thermostat: only heat when actively roasting.
                    if state == RoasterState.ROASTING:
                        duty_percent = (heat_setting * 100.0) / 3.0
                        new_heater_level = int(round(duty_percent))
                    else:
                        new_heater_level = 0

                heater_should_off = new_heater_level <= 0

            self._set_heater_level(new_heater_level)

            set_heater_level = getattr(self.hardware, "set_heater_level", None)
            if callable(set_heater_level):
                try:
                    set_heater_level(new_heater_level)
                except Exception as exc:
                    logging.warning("localroaster: set_heater_level failed: %s", exc)
                    with self._lock:
                        self._fault = str(exc)

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

        while not self._stop_event.is_set():
            start = time.monotonic()

            with self._lock:
                heater_level = self._heater_level

            heater_on, delay_s = self._pwm.state_and_delay(heater_level, now=start)

            if heater_on != last_written:
                try:
                    self.hardware.set_heater(heater_on)
                    last_written = heater_on
                except Exception as exc:
                    logging.warning("localroaster: heater command failed: %s", exc)
                    with self._lock:
                        self._fault = str(exc)

            # Reflect applied output state (best-effort if hardware writes fail).
            self._set_heater_output(False if last_written is None else last_written)

            if self._pwm_wake_event.wait(timeout=delay_s):
                self._pwm_wake_event.clear()
            if self._stop_event.is_set():
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
                        should_transition = self._time_remaining_s == 0
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

