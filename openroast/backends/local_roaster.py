# -*- coding: utf-8 -*-
# Local hardware backend adapter for Openroast.
#
# The reusable controller logic now lives in the standalone `localroaster`
# package. This module intentionally stays thin and only translates the
# Openroast/freshroastsr700-style API into the frontend-agnostic controller.

import logging
import threading

from localroaster import ControllerConfig, RoasterState, create_controller
from openroast.temperature import (
    MAX_TEMPERATURE_C,
    MIN_TEMPERATURE_C,
    celsius_to_kelvin,
    kelvin_to_celsius,
)
from openroast import app_config


class LocalRoaster:
    """Openroast compatibility adapter over the standalone localroaster package."""

    CS_CONNECTING = 1
    temperature_unit = "C"
    temperature_min_c = MIN_TEMPERATURE_C
    temperature_max_c = MAX_TEMPERATURE_C

    def __init__(
        self,
        update_data_func=None,
        state_transition_func=None,
        heater_output_func=None,
        thermostat=True,
        kp=0.06,
        ki=0.0075,
        kd=0.01,
        heater_segments=8,
        force_mock=False,
        pwm_tick_s=None,
        sample_period_s=None,
        pwm_cycle_s=None,
        max_temp_c=None,
        heater_cutoff_enabled=True,
    ):
        max_temp_k = celsius_to_kelvin(self.temperature_max_c if max_temp_c is None else float(max_temp_c))
        config_kwargs = dict(
            thermostat=thermostat,
            kp=kp,
            ki=ki,
            kd=kd,
            min_display_temp_k=celsius_to_kelvin(self.temperature_min_c),
            max_temp_k=max_temp_k,
            heater_cutoff_enabled=bool(heater_cutoff_enabled),
        )
        if pwm_tick_s is not None:
            config_kwargs["pwm_tick_s"] = float(pwm_tick_s)
        if sample_period_s is not None:
            config_kwargs["sample_period_s"] = float(sample_period_s)
        if pwm_cycle_s is not None:
            config_kwargs["pwm_cycle_s"] = float(pwm_cycle_s)
        self._config = ControllerConfig(**config_kwargs)
        self._controller = create_controller(config=self._config, force_mock=force_mock)
        self._connect_state = 0
        self._listeners_registered = False
        self._callback_threads_started = False
        self._stop_callbacks = threading.Event()
        self._update_event = threading.Event()
        self._state_transition_event = threading.Event()
        self._heater_output_state = False
        self._heater_level_state = 0

        self._update_data_func = update_data_func
        self._state_transition_func = state_transition_func
        self._heater_output_func = heater_output_func
        self._heater_level_func = None
        self._update_thread = None
        self._state_transition_thread = None

    def _register_controller_listeners(self):
        if self._listeners_registered:
            return
        self._controller.add_telemetry_listener(self._on_telemetry)
        self._controller.set_state_transition_callback(self._on_state_transition)
        add_heater_listener = getattr(self._controller, "add_heater_output_listener", None)
        if callable(add_heater_listener):
            add_heater_listener(self._on_heater_output_changed)
        add_heater_level_listener = getattr(self._controller, "add_heater_level_listener", None)
        if callable(add_heater_level_listener):
            add_heater_level_listener(self._on_heater_level_changed)
        self._listeners_registered = True

    def _start_callback_threads(self):
        if self._callback_threads_started:
            return
        if self._update_data_func is not None:
            self._update_thread = threading.Thread(
                target=self._run_event_callback,
                args=(self._update_event, lambda: self._update_data_func()),
                name="openroast-local-update",
                daemon=True,
            )
            self._update_thread.start()
        if self._state_transition_func is not None:
            self._state_transition_thread = threading.Thread(
                target=self._run_event_callback,
                args=(self._state_transition_event, lambda: self._state_transition_func()),
                name="openroast-local-transition",
                daemon=True,
            )
            self._state_transition_thread.start()
        self._callback_threads_started = True

    def _run_event_callback(self, event, callback):
        while not self._stop_callbacks.is_set():
            if not event.wait(0.1):
                continue
            event.clear()
            try:
                callback()
            except Exception as exc:  # pragma: no cover - defensive callback handling
                logging.warning("LocalRoaster callback failed: %s", exc)

    def _on_telemetry(self, _telemetry):
        self._update_event.set()

    def _on_state_transition(self):
        self._state_transition_event.set()

    def _on_heater_output_changed(self, heater_on):
        self._heater_output_state = bool(heater_on)
        if self._heater_output_func is not None:
            try:
                self._heater_output_func(self._heater_output_state)
            except Exception as exc:  # pragma: no cover - defensive callback handling
                logging.warning("LocalRoaster callback failed: %s", exc)

    def _on_heater_level_changed(self, heater_level):
        self._heater_level_state = int(heater_level)
        if self._heater_level_func is not None:
            try:
                self._heater_level_func(self._heater_level_state)
            except Exception as exc:  # pragma: no cover - defensive callback handling
                logging.warning("LocalRoaster callback failed: %s", exc)

    @property
    def connected(self):
        return self._controller.connected

    @property
    def connect_state(self):
        return self._connect_state

    @property
    def fan_speed(self):
        return self._controller.fan_speed

    @fan_speed.setter
    def fan_speed(self, value):
        self._controller.fan_speed = value

    @property
    def heat_setting(self):
        return self._controller.heat_setting

    @heat_setting.setter
    def heat_setting(self, value):
        self._controller.heat_setting = value

    @property
    def target_temp(self):
        return int(round(kelvin_to_celsius(self._controller.target_temp_k)))

    @target_temp.setter
    def target_temp(self, value):
        self._controller.target_temp_k = celsius_to_kelvin(value)

    @property
    def target_temp_k(self):
        return float(self._controller.target_temp_k)

    @target_temp_k.setter
    def target_temp_k(self, value):
        self._controller.target_temp_k = float(value)

    @property
    def current_temp(self):
        temp_c = kelvin_to_celsius(self._controller.current_temp_k)
        max_temp_c = int(round(kelvin_to_celsius(self._config.max_temp_k)))
        # Preserve upper safety bound, but do not apply legacy SR700 low-temp floor.
        return int(round(min(max_temp_c, temp_c)))

    @property
    def current_temp_k(self):
        return float(self._controller.current_temp_k)

    @property
    def time_remaining(self):
        return self._controller.time_remaining_s

    @time_remaining.setter
    def time_remaining(self, value):
        self._controller.time_remaining_s = value

    @property
    def time_remaining_s(self):
        return self._controller.time_remaining_s

    @time_remaining_s.setter
    def time_remaining_s(self, value):
        self._controller.time_remaining_s = value

    @property
    def total_time(self):
        return self._controller.total_time_s

    @total_time.setter
    def total_time(self, value):
        self._controller.total_time_s = value

    @property
    def total_time_s(self):
        return self._controller.total_time_s

    @total_time_s.setter
    def total_time_s(self, value):
        self._controller.total_time_s = value

    @property
    def heater_level(self):
        return self._controller.heater_level

    @property
    def heater_output(self):
        return self._controller.heater_output

    def get_roaster_state(self):
        if self._connect_state == self.CS_CONNECTING and not self.connected:
            return "connecting"

        state = self._controller.state
        mapping = {
            RoasterState.DISCONNECTED: "connecting",
            RoasterState.IDLE: "idle",
            RoasterState.ROASTING: "roasting",
            RoasterState.COOLING: "cooling",
            RoasterState.SLEEPING: "sleeping",
            RoasterState.FAULT: "unknown",
        }
        return mapping.get(state, "unknown")

    def idle(self):
        self._controller.idle()

    def roast(self):
        self._controller.roast()

    def cool(self):
        self._controller.cool()

    def sleep(self):
        self._controller.sleep()

    def set_state_transition_func(self, func):
        if self.connected:
            logging.error(
                "LocalRoaster.set_state_transition_func must be called before "
                "auto_connect(). Not registering func."
            )
            return False
        self._state_transition_func = func
        return True

    def set_heater_output_func(self, func):
        self._heater_output_func = func
        if func is not None:
            self._heater_output_state = bool(self._controller.heater_output)
            try:
                func(self._heater_output_state)
            except Exception as exc:  # pragma: no cover - defensive callback handling
                logging.warning("LocalRoaster callback failed: %s", exc)
        return True

    def set_heater_level_func(self, func):
        self._heater_level_func = func
        if func is not None:
            self._heater_level_state = int(self._controller.heater_level)
            try:
                func(self._heater_level_state)
            except Exception as exc:  # pragma: no cover - defensive callback handling
                logging.warning("LocalRoaster callback failed: %s", exc)
        return True

    def auto_connect(self):
        self._connect_state = self.CS_CONNECTING
        self._register_controller_listeners()
        self._start_callback_threads()
        self._controller.connect()
        self._connect_state = 0

    def disconnect(self):
        self._stop_callbacks.set()
        self._update_event.set()
        self._state_transition_event.set()
        self._controller.shutdown()

    def reset_simulation_state(self):
        reset_sim = getattr(self._controller, "reset_simulation_state", None)
        if callable(reset_sim):
            reset_sim()
            return True
        return False

    def apply_runtime_preferences(self, config_data):
        config = app_config.normalize_config(config_data)
        apply_runtime_config = getattr(self._controller, "apply_runtime_config", None)
        if not callable(apply_runtime_config):
            return False

        apply_runtime_config(
            kp=float(config["control"]["pid"]["kp"]),
            ki=float(config["control"]["pid"]["ki"]),
            kd=float(config["control"]["pid"]["kd"]),
            pwm_cycle_s=float(config["control"]["pwmCycleSeconds"]),
            sample_period_s=float(config["control"]["samplePeriodSeconds"]),
            max_temp_k=celsius_to_kelvin(app_config.get_safety_max_temp_c(config)),
            heater_cutoff_enabled=bool(config["safety"]["heaterCutoffEnabled"]),
        )
        return True

    def autotune_pid(self, **kwargs):
        run_autotune = getattr(self._controller, "autotune_pid", None)
        if not callable(run_autotune):
            raise RuntimeError("Autotune is not supported by this backend")
        return run_autotune(**kwargs)

    def cancel_autotune(self):
        cancel = getattr(self._controller, "cancel_autotune", None)
        if callable(cancel):
            return bool(cancel())
        return False
