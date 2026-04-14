"""Tests for localroaster.controller internals: PID, DutyCyclePWM, and
RoasterController safety behaviour."""

import threading
import time
import unittest

from openroast import app_config
from openroast.temperature import celsius_to_kelvin
from localroaster.api import ControllerConfig, RoasterState
from localroaster.controller import DutyCyclePWM, PID, RoasterController, HardwareDriver


# ---------------------------------------------------------------------------
# PID tests
# ---------------------------------------------------------------------------

class PIDTests(unittest.TestCase):
    def test_output_clamped_to_max(self):
        pid = PID(kp=10.0, ki=0.0, kd=0.0, output_max=100, output_min=0)
        result = pid.update(current=0.0, target=1000.0)
        self.assertEqual(result, 100)

    def test_output_clamped_to_min(self):
        pid = PID(kp=10.0, ki=0.0, kd=0.0, output_max=100, output_min=0)
        result = pid.update(current=1000.0, target=0.0)
        self.assertEqual(result, 0)

    def test_proportional_only(self):
        pid = PID(kp=0.5, ki=0.0, kd=0.0, output_max=100, output_min=0)
        result = pid.update(current=50.0, target=100.0)
        self.assertAlmostEqual(result, 25.0)

    def test_integral_accumulates(self):
        pid = PID(kp=0.0, ki=1.0, kd=0.0, output_max=200, output_min=0)
        pid.update(current=0.0, target=10.0)  # integral = 10
        result = pid.update(current=0.0, target=10.0)  # integral = 20
        self.assertAlmostEqual(result, 20.0)

    def test_integral_anti_windup_clamps(self):
        pid = PID(kp=0.0, ki=1.0, kd=0.0, output_max=50, output_min=0)
        # Push integral way beyond output_max / ki = 50
        for _ in range(200):
            pid.update(current=0.0, target=100.0)
        # Integral should be clamped to output_max / ki = 50
        result = pid.update(current=0.0, target=100.0)
        self.assertAlmostEqual(result, 50.0)

    def test_derivative_responds_to_measurement_change(self):
        """Derivative-on-measurement: derivative = -(current - prev_measurement) / dt.

        When the measurement rises (current > prev), the derivative term is
        negative, dampening the output.
        """
        pid = PID(kp=0.0, ki=0.0, kd=1.0, output_max=100, output_min=0)
        # First call: prev_measurement is None → derivative = 0
        pid.update(current=90.0, target=100.0)
        # Second call: measurement rose from 90 → 95 → derivative = -(95-90)/1 = -5
        result = pid.update(current=95.0, target=100.0)
        self.assertAlmostEqual(result, 0.0)  # clamped to 0 (kd * -5 = -5)

    def test_derivative_on_measurement_ignores_setpoint_change(self):
        """Setpoint step should not cause derivative kick."""
        pid = PID(kp=0.0, ki=0.0, kd=1.0, output_max=100, output_min=0)
        pid.update(current=90.0, target=100.0)  # prime measurement
        # Setpoint jumps from 100 → 200, but measurement stays at 90.
        result = pid.update(current=90.0, target=200.0)
        # derivative = -(90 - 90) / 1 = 0; no kick from setpoint change
        self.assertAlmostEqual(result, 0.0)

    def test_reset_clears_state(self):
        pid = PID(kp=0.0, ki=1.0, kd=0.0, output_max=100, output_min=0)
        pid.update(current=0.0, target=50.0)  # integral = 50
        pid.reset()
        result = pid.update(current=0.0, target=10.0)  # integral = 10
        self.assertAlmostEqual(result, 10.0)

    def test_integral_scales_with_dt(self):
        """Integral accumulates error * dt, so halving dt halves the accumulation rate."""
        pid = PID(kp=0.0, ki=1.0, kd=0.0, output_max=200, output_min=0)
        pid.update(current=0.0, target=10.0, dt=0.5)  # integral = 10 * 0.5 = 5
        result = pid.update(current=0.0, target=10.0, dt=0.5)  # integral = 5 + 5 = 10
        self.assertAlmostEqual(result, 10.0)

    def test_derivative_scales_with_dt(self):
        """Derivative divides by dt, so halving dt doubles the derivative response."""
        pid = PID(kp=0.0, ki=0.0, kd=1.0, output_max=100, output_min=0)
        pid.update(current=90.0, target=100.0, dt=0.5)  # primes measurement
        # Measurement drops from 90 → 80: derivative = -(80 - 90) / 0.5 = 20
        result = pid.update(current=80.0, target=100.0, dt=0.5)
        self.assertAlmostEqual(result, 20.0)


# ---------------------------------------------------------------------------
# DutyCyclePWM tests
# ---------------------------------------------------------------------------

class DutyCyclePWMTests(unittest.TestCase):
    def test_zero_percent_always_off(self):
        pwm = DutyCyclePWM(cycle_s=1.0)
        base = time.monotonic()
        for offset in [0.0, 0.1, 0.5, 0.9]:
            self.assertFalse(pwm.output(0.0, now=base + offset))

    def test_hundred_percent_always_on(self):
        pwm = DutyCyclePWM(cycle_s=1.0)
        base = time.monotonic()
        for offset in [0.0, 0.1, 0.5, 0.99]:
            self.assertTrue(pwm.output(100.0, now=base + offset))

    def test_fifty_percent_on_for_half_cycle(self):
        pwm = DutyCyclePWM(cycle_s=1.0)
        base = time.monotonic()
        self.assertTrue(pwm.output(50.0, now=base + 0.0))
        self.assertTrue(pwm.output(50.0, now=base + 0.49))
        self.assertFalse(pwm.output(50.0, now=base + 0.51))
        self.assertFalse(pwm.output(50.0, now=base + 0.99))

    def test_wraps_around_after_cycle(self):
        pwm = DutyCyclePWM(cycle_s=1.0)
        base = time.monotonic()
        # Second cycle
        self.assertTrue(pwm.output(50.0, now=base + 1.0))
        self.assertFalse(pwm.output(50.0, now=base + 1.6))

    def test_minimum_cycle_enforced(self):
        pwm = DutyCyclePWM(cycle_s=0.01)
        self.assertGreaterEqual(pwm.cycle_s, 0.1)

    def test_state_and_delay_reports_falling_edge_for_partial_duty(self):
        pwm = DutyCyclePWM(cycle_s=1.0)
        base = time.monotonic()
        heater_on, delay_s = pwm.state_and_delay(50.0, now=base + 0.1)
        self.assertTrue(heater_on)
        self.assertAlmostEqual(delay_s, 0.4, places=2)

    def test_state_and_delay_reports_next_cycle_when_currently_off(self):
        pwm = DutyCyclePWM(cycle_s=1.0)
        base = time.monotonic()
        heater_on, delay_s = pwm.state_and_delay(50.0, now=base + 0.8)
        self.assertFalse(heater_on)
        self.assertAlmostEqual(delay_s, 0.2, places=2)


# ---------------------------------------------------------------------------
# RoasterController safety tests (using a recording driver)
# ---------------------------------------------------------------------------

class RecordingDriver(HardwareDriver):
    """Records all hardware calls for verification."""

    def __init__(self, temperature_k: float = 300.0):
        self._temp_k = temperature_k
        self.heater_calls: list[bool] = []
        self.heater_level_calls: list[int] = []
        self.fan_calls: list[int] = []
        self.closed = False

    def read_temperature_k(self) -> float:
        return self._temp_k

    def set_heater(self, on: bool) -> None:
        self.heater_calls.append(on)

    def set_fan_speed(self, speed: int) -> None:
        self.fan_calls.append(speed)

    def set_heater_level(self, level_percent: int) -> None:
        self.heater_level_calls.append(int(level_percent))

    def close(self) -> None:
        self.closed = True


class _AutotuneDriver(HardwareDriver):
    def __init__(self, ambient_k: float = 295.0):
        self._ambient_k = ambient_k
        self._temp_k = ambient_k
        self._heater_level = 0.0

    def read_temperature_k(self) -> float:
        target_k = self._ambient_k + (self._heater_level / 100.0) * 180.0
        self._temp_k = self._temp_k + 0.08 * (target_k - self._temp_k)
        return self._temp_k

    def set_heater(self, on: bool) -> None:
        self._heater_level = 100.0 if on else 0.0

    def set_heater_level(self, level_percent: int) -> None:
        self._heater_level = max(0.0, min(100.0, float(level_percent)))

    def set_fan_speed(self, speed: int) -> None:
        _ = speed


class ControllerSafetyTests(unittest.TestCase):
    def _make_controller(self, thermostat=True, temp_k=400.0, **config_kwargs):
        config = ControllerConfig(
            thermostat=thermostat,
            sample_period_s=0.05,
            pwm_cycle_s=0.1,
            pwm_tick_s=0.02,
            **config_kwargs,
        )
        driver = RecordingDriver(temperature_k=temp_k)
        ctrl = RoasterController(driver, config=config)
        return ctrl, driver, config

    def test_shutdown_turns_heater_off(self):
        ctrl, driver, _ = self._make_controller()
        ctrl.connect()
        time.sleep(0.15)
        ctrl.shutdown()
        # Last hardware call should be set_heater(False)
        self.assertTrue(len(driver.heater_calls) > 0)
        self.assertFalse(driver.heater_calls[-1])
        self.assertTrue(driver.closed)

    def test_heater_off_when_idle_thermostat_mode(self):
        ctrl, driver, _ = self._make_controller(thermostat=True)
        ctrl.connect()
        ctrl.idle()
        time.sleep(0.2)
        ctrl.shutdown()
        self.assertEqual(ctrl.heater_level, 0)

    def test_heater_off_when_idle_non_thermostat_mode(self):
        """Verify the safety fix: non-thermostat mode does NOT heat when idle."""
        ctrl, driver, _ = self._make_controller(thermostat=False)
        ctrl.connect()
        ctrl.heat_setting = 3  # Would produce 100% if unguarded
        ctrl.idle()
        time.sleep(0.2)
        # Heater level must be 0 despite heat_setting=3
        self.assertEqual(ctrl.heater_level, 0)
        ctrl.shutdown()

    def test_over_temperature_forces_heater_off(self):
        """Verify over-temp safety: heater forced off when temp > max."""
        ctrl, driver, config = self._make_controller(
            thermostat=True,
            temp_k=600.0,  # Above default max_temp_k of 560.93
        )
        ctrl.connect()
        ctrl.roast()
        time.sleep(0.2)
        # Heater level should be 0 due to over-temp protection
        self.assertEqual(ctrl.heater_level, 0)
        ctrl.shutdown()

    def test_over_temperature_cutoff_can_be_disabled(self):
        ctrl, _driver, _config = self._make_controller(
            thermostat=False,
            temp_k=600.0,
            heater_cutoff_enabled=False,
        )
        ctrl.connect()
        ctrl.heat_setting = 3
        ctrl.roast()
        time.sleep(0.2)
        # In expert mode, disabled cutoff keeps manual heat command active.
        self.assertGreater(ctrl.heater_level, 0)
        ctrl.shutdown()

    def test_over_temperature_cutoff_respected_for_all_config_units(self):
        # Custom (non-default) limits in each unit; all should map to a valid C cutoff.
        unit_cases = [
            ("C", 230.0),
            ("F", 430.0),
            ("K", 510.0),
        ]

        for unit_symbol, cutoff_value in unit_cases:
            with self.subTest(unit=unit_symbol, cutoff_value=cutoff_value):
                cfg = app_config.normalize_config(
                    {
                        "display": {"temperatureUnitDefault": unit_symbol},
                        "safety": {
                            "maxTemp": {"value": cutoff_value, "unit": unit_symbol},
                            "heaterCutoffEnabled": True,
                        },
                    }
                )
                cutoff_c = app_config.get_safety_max_temp_c(cfg)

                # Simulate hardware reading above the configured cutoff.
                ctrl, _driver, _config = self._make_controller(
                    thermostat=False,
                    temp_k=celsius_to_kelvin(cutoff_c + 10.0),
                    max_temp_k=celsius_to_kelvin(cutoff_c),
                    heater_cutoff_enabled=bool(cfg["safety"]["heaterCutoffEnabled"]),
                )
                ctrl.connect()
                ctrl.heat_setting = 3
                ctrl.roast()
                time.sleep(0.2)

                self.assertEqual(ctrl.heater_level, 0)
                self.assertEqual(ctrl.heat_setting, 0)
                self.assertIn("cutoff", (ctrl.telemetry().fault or "").lower())
                ctrl.shutdown()

    def test_over_temperature_cutoff_disabled_for_all_config_units(self):
        unit_cases = [
            ("C", 230.0),
            ("F", 430.0),
            ("K", 510.0),
        ]

        for unit_symbol, cutoff_value in unit_cases:
            with self.subTest(unit=unit_symbol, cutoff_value=cutoff_value):
                cfg = app_config.normalize_config(
                    {
                        "display": {"temperatureUnitDefault": unit_symbol},
                        "safety": {
                            "maxTemp": {"value": cutoff_value, "unit": unit_symbol},
                            "heaterCutoffEnabled": False,
                        },
                    }
                )
                cutoff_c = app_config.get_safety_max_temp_c(cfg)

                ctrl, _driver, _config = self._make_controller(
                    thermostat=False,
                    temp_k=celsius_to_kelvin(cutoff_c + 10.0),
                    max_temp_k=celsius_to_kelvin(cutoff_c),
                    heater_cutoff_enabled=bool(cfg["safety"]["heaterCutoffEnabled"]),
                )
                ctrl.connect()
                ctrl.heat_setting = 3
                ctrl.roast()
                time.sleep(0.2)

                self.assertGreater(ctrl.heater_level, 0)
                ctrl.shutdown()

    def test_control_loop_calls_continuous_heater_level_hook(self):
        ctrl, driver, _ = self._make_controller(thermostat=False, temp_k=350.0)
        ctrl.connect()
        ctrl.heat_setting = 1
        ctrl.roast()
        time.sleep(0.2)
        ctrl.shutdown()

        self.assertTrue(driver.heater_level_calls)
        self.assertTrue(any(0 < level < 100 for level in driver.heater_level_calls))

    def test_apply_runtime_config_updates_pid_and_limits(self):
        ctrl, _driver, _config = self._make_controller(thermostat=True)

        ctrl.apply_runtime_config(
            kp=0.2,
            ki=0.03,
            kd=0.04,
            pwm_cycle_s=1.5,
            sample_period_s=0.25,
            max_temp_k=500.0,
            heater_cutoff_enabled=False,
        )

        self.assertAlmostEqual(ctrl.config.kp, 0.2, places=4)
        self.assertAlmostEqual(ctrl.config.ki, 0.03, places=4)
        self.assertAlmostEqual(ctrl.config.kd, 0.04, places=4)
        self.assertAlmostEqual(ctrl.config.pwm_cycle_s, 1.5, places=4)
        self.assertAlmostEqual(ctrl.config.sample_period_s, 0.25, places=4)
        self.assertAlmostEqual(ctrl.config.max_temp_k, 500.0, places=4)
        self.assertFalse(ctrl.config.heater_cutoff_enabled)

    def test_autotune_pid_returns_positive_coefficients(self):
        cfg = ControllerConfig(
            thermostat=True,
            sample_period_s=0.05,
            pwm_cycle_s=0.2,
            pwm_tick_s=0.05,
            max_temp_k=560.0,
            min_display_temp_k=293.15,
        )
        driver = _AutotuneDriver(ambient_k=295.0)
        ctrl = RoasterController(driver, config=cfg)
        ctrl.connect()

        tuned = ctrl.autotune_pid(settle_s=0.5, test_duration_s=6.0, min_rise_c=2.0)

        self.assertGreater(tuned["kp"], 0.0)
        self.assertGreater(tuned["ki"], 0.0)
        self.assertGreater(tuned["kd"], 0.0)
        self.assertEqual(ctrl.state, RoasterState.IDLE)
        self.assertTrue(ctrl.config.thermostat)
        ctrl.shutdown()

    def test_autotune_pid_suppresses_state_transition_callback(self):
        cfg = ControllerConfig(
            thermostat=True,
            sample_period_s=0.05,
            pwm_cycle_s=0.2,
            pwm_tick_s=0.05,
            max_temp_k=560.0,
            min_display_temp_k=293.15,
        )
        driver = _AutotuneDriver(ambient_k=295.0)
        ctrl = RoasterController(driver, config=cfg)
        transitions = []
        ctrl.set_state_transition_callback(lambda: transitions.append("transition"))
        ctrl.connect()

        ctrl.autotune_pid(settle_s=0.2, test_duration_s=1.2, min_rise_c=1.0)

        self.assertEqual(transitions, [])
        ctrl.shutdown()

    def test_cancel_autotune_aborts_autotune_run(self):
        cfg = ControllerConfig(
            thermostat=True,
            sample_period_s=0.05,
            pwm_cycle_s=0.2,
            pwm_tick_s=0.05,
            max_temp_k=560.0,
            min_display_temp_k=293.15,
        )
        driver = _AutotuneDriver(ambient_k=295.0)
        ctrl = RoasterController(driver, config=cfg)
        ctrl.connect()

        result = {}

        def _run_autotune():
            try:
                ctrl.autotune_pid(settle_s=0.2, test_duration_s=8.0, min_rise_c=1.0)
            except Exception as exc:  # pragma: no cover - asserted below
                result["error"] = exc

        worker = threading.Thread(target=_run_autotune)
        worker.start()
        time.sleep(0.25)
        ctrl.cancel_autotune()
        worker.join(timeout=3.0)

        self.assertFalse(worker.is_alive(), "autotune thread did not exit after cancel")
        self.assertIn("error", result)
        self.assertIn("canceled", str(result["error"]).lower())
        self.assertEqual(ctrl.state, RoasterState.IDLE)
        ctrl.shutdown()

    def test_pid_resets_on_roast_from_idle(self):
        ctrl, driver, _ = self._make_controller(thermostat=True)
        ctrl.connect()
        ctrl.roast()
        time.sleep(0.15)
        # Record PID state before idle
        ctrl.idle()
        time.sleep(0.1)
        # Start a new roast — PID should be fresh
        ctrl.roast()
        time.sleep(0.15)
        # Just verify it doesn't crash and heater_level is reasonable
        level = ctrl.heater_level
        self.assertGreaterEqual(level, 0)
        self.assertLessEqual(level, 100)
        ctrl.shutdown()

    def test_reset_control_state_clears_pid_and_heater_outputs(self):
        ctrl, _driver, _ = self._make_controller(thermostat=True)
        ctrl._pid.update(current=0.0, target=100.0)
        ctrl._set_heater_level(42)

        ctrl.reset_control_state()

        self.assertEqual(ctrl._pid._integral, 0.0)
        self.assertIsNone(ctrl._pid._prev_measurement)
        self.assertEqual(ctrl.heater_level, 0)
        self.assertFalse(ctrl.heater_output)

    def test_pid_preserved_on_roast_to_roast_transition(self):
        """Calling roast() while already roasting must NOT reset the PID.

        This is the recipe section-transition scenario: the recipe controller
        calls roast() again to load new settings.  Resetting the PID here
        would drop the heater percentage to near-zero and cause a visible
        temperature dip.

        We use a temperature close to the target so that the proportional
        term is small and the accumulated integral is what keeps the heater
        output high — exactly the regime where an accidental PID reset is
        most damaging.
        """
        # Temperature just 20 K below max → proportional term is small,
        # integral must accumulate to sustain output.
        target_k = 540.0
        current_k = target_k - 20.0
        ctrl, driver, _ = self._make_controller(
            thermostat=True,
            temp_k=current_k,
            # Bump ki so integral builds meaningfully in a short test window.
            ki=0.5,
            kp=0.06,
            kd=0.0,
        )
        ctrl.connect()
        ctrl.target_temp_k = target_k
        ctrl.roast()
        # Let the PID accumulate for many control cycles (0.05 s each).
        time.sleep(0.6)
        level_before = ctrl.heater_level
        self.assertGreater(level_before, 0, "PID should have produced nonzero output")

        # Simulate a recipe section transition: roast() called again.
        ctrl.roast()
        time.sleep(0.15)
        level_after = ctrl.heater_level

        # With the buggy unconditional reset, the integral drops to zero and
        # level_after would fall to just kp*error ≈ 0.06*20 = 1.
        # With the fix, level_after stays near level_before.
        self.assertGreaterEqual(
            level_after,
            level_before // 2,
            f"Heater level dropped from {level_before} to {level_after} after "
            f"roast-to-roast transition — PID was likely reset",
        )
        ctrl.shutdown()

    def test_state_transitions(self):
        ctrl, driver, _ = self._make_controller()
        self.assertEqual(ctrl.state, RoasterState.DISCONNECTED)
        ctrl.connect()
        self.assertEqual(ctrl.state, RoasterState.IDLE)
        ctrl.roast()
        self.assertEqual(ctrl.state, RoasterState.ROASTING)
        ctrl.cool()
        self.assertEqual(ctrl.state, RoasterState.COOLING)
        ctrl.sleep()
        self.assertEqual(ctrl.state, RoasterState.SLEEPING)
        ctrl.idle()
        self.assertEqual(ctrl.state, RoasterState.IDLE)
        ctrl.shutdown()
        self.assertEqual(ctrl.state, RoasterState.DISCONNECTED)

    def test_telemetry_snapshot(self):
        ctrl, _, _ = self._make_controller(temp_k=350.0)
        ctrl.connect()
        t = ctrl.telemetry()
        self.assertTrue(t.connected)
        self.assertEqual(t.state, RoasterState.IDLE)
        self.assertAlmostEqual(t.current_temp_k, 350.0, places=0)
        ctrl.shutdown()

    def test_fan_speed_validation(self):
        ctrl, _, _ = self._make_controller()
        with self.assertRaises(ValueError):
            ctrl.fan_speed = 0
        with self.assertRaises(ValueError):
            ctrl.fan_speed = 10

    def test_target_temp_validation(self):
        ctrl, _, config = self._make_controller()
        with self.assertRaises(ValueError):
            ctrl.target_temp_k = config.min_display_temp_k - 1
        with self.assertRaises(ValueError):
            ctrl.target_temp_k = config.max_temp_k + 1

    def test_timer_loop_transitions_immediately_when_countdown_hits_zero(self):
        class _ImmediateStopEvent:
            def __init__(self):
                self._is_set = False
                self.wait_calls = 0

            def is_set(self):
                return self._is_set

            def wait(self, _timeout):
                self.wait_calls += 1
                return self._is_set

            def set(self):
                self._is_set = True

        ctrl, _, _ = self._make_controller()
        ctrl._stop_event = _ImmediateStopEvent()
        transitions = []

        def _on_transition():
            transitions.append(ctrl.time_remaining_s)
            ctrl._stop_event.set()

        ctrl.set_state_transition_callback(_on_transition)
        with ctrl._lock:
            ctrl._state = RoasterState.ROASTING
            ctrl._time_remaining_s = 1
            ctrl._total_time_s = 0

        ctrl._timer_loop()

        self.assertEqual(transitions, [0])
        self.assertEqual(ctrl.time_remaining_s, 0)
        self.assertEqual(ctrl.total_time_s, 1)
        self.assertEqual(ctrl._stop_event.wait_calls, 1)


    def test_heater_off_when_cooling_non_thermostat(self):
        """Heater must stay off when the state is COOLING, even if heat_setting > 0."""
        ctrl, driver, _ = self._make_controller(thermostat=False)
        ctrl.connect()
        ctrl.heat_setting = 3
        ctrl.cool()
        time.sleep(0.2)
        self.assertEqual(ctrl.heater_level, 0, "Heater should be off in COOLING state")
        ctrl.shutdown()

    def test_heater_off_when_cooling_thermostat(self):
        """Heater must stay off when the state is COOLING in thermostat mode."""
        ctrl, driver, _ = self._make_controller(thermostat=True, temp_k=400.0)
        ctrl.connect()
        ctrl.target_temp_k = 500.0
        ctrl.cool()
        time.sleep(0.2)
        self.assertEqual(ctrl.heater_level, 0, "Heater should be off in COOLING state (thermostat)")
        ctrl.shutdown()
    def test_clear_fault_resets_latched_fault(self):
        """Manual clear_fault() should reset a latched over-temperature fault."""
        ctrl, driver, _ = self._make_controller(
            thermostat=True,
            temp_k=600.0,
        )
        ctrl.connect()
        ctrl.roast()
        time.sleep(0.2)

        self.assertIsNotNone(ctrl.telemetry().fault)

        # Keep temperature high — manual clear should still work.
        ctrl.clear_fault()
        self.assertIsNone(ctrl.telemetry().fault)
        ctrl.shutdown()


if __name__ == "__main__":
    unittest.main()

