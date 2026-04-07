"""Tests for localroaster.controller internals: PID, DutyCyclePWM, and
RoasterController safety behaviour."""

import threading
import time
import unittest

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

    def test_derivative_responds_to_error_change(self):
        pid = PID(kp=0.0, ki=0.0, kd=1.0, output_max=100, output_min=0)
        pid.update(current=90.0, target=100.0)  # error=10, deriv=10
        result = pid.update(current=95.0, target=100.0)  # error=5, deriv=-5
        self.assertAlmostEqual(result, 0.0)  # clamped to 0

    def test_reset_clears_state(self):
        pid = PID(kp=0.0, ki=1.0, kd=0.0, output_max=100, output_min=0)
        pid.update(current=0.0, target=50.0)  # integral = 50
        pid.reset()
        result = pid.update(current=0.0, target=10.0)  # integral = 10
        self.assertAlmostEqual(result, 10.0)


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


# ---------------------------------------------------------------------------
# RoasterController safety tests (using a recording driver)
# ---------------------------------------------------------------------------

class RecordingDriver(HardwareDriver):
    """Records all hardware calls for verification."""

    def __init__(self, temperature_k: float = 300.0):
        self._temp_k = temperature_k
        self.heater_calls: list[bool] = []
        self.fan_calls: list[int] = []
        self.closed = False

    def read_temperature_k(self) -> float:
        return self._temp_k

    def set_heater(self, on: bool) -> None:
        self.heater_calls.append(on)

    def set_fan_speed(self, speed: int) -> None:
        self.fan_calls.append(speed)

    def close(self) -> None:
        self.closed = True


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


if __name__ == "__main__":
    unittest.main()

