import unittest

from openroast.controllers.autotune import autotune_pid_for_backend, autotune_pid_table_for_backend


class _NativeAutotuneRoaster:
    def __init__(self):
        self.connected = True
        self._state = "idle"
        self.autotune_calls = 0

    def get_roaster_state(self):
        return self._state

    def idle(self):
        self._state = "idle"

    def autotune_pid(self, **kwargs):
        self.autotune_calls += 1
        self.last_kwargs = kwargs
        return {"kp": 0.2, "ki": 0.03, "kd": 0.04}


class _NativeMultiSpeedRoaster:
    def __init__(self, *, max_fan_speed=4, initial_fan_speed=2, fail_on_fan=None):
        self.connected = True
        self._state = "idle"
        self.max_fan_speed = int(max_fan_speed)
        self._fan_speed = int(initial_fan_speed)
        self.fail_on_fan = fail_on_fan
        self.autotune_calls = 0
        self.fan_set_history = []
        self.autotune_fan_history = []

    def get_roaster_state(self):
        return self._state

    def idle(self):
        self._state = "idle"

    @property
    def fan_speed(self):
        return self._fan_speed

    @fan_speed.setter
    def fan_speed(self, value):
        self._fan_speed = int(value)
        self.fan_set_history.append(int(value))

    def autotune_pid(self, **_kwargs):
        self.autotune_calls += 1
        self.autotune_fan_history.append(int(self._fan_speed))
        if self.fail_on_fan is not None and int(self._fan_speed) == int(self.fail_on_fan):
            raise RuntimeError(f"forced failure at fan {self._fan_speed}")
        speed = float(self._fan_speed)
        return {
            "kp": 0.1 + speed,
            "ki": 0.01 + speed / 10.0,
            "kd": 0.02 + speed / 10.0,
            "process_gain": 2.0 + speed / 10.0,
            "tau_s": 25.0 + speed,
            "dead_time_s": 0.4 + speed / 10.0,
        }


class _GenericFallbackRoaster:
    temperature_unit = "C"

    def __init__(self):
        self.connected = True
        self._state = "idle"
        self.fan_speed = 1
        self.heat_setting = 0
        self.target_temp = 25
        self._ambient = 25.0
        self._temp = 25.0

    def get_roaster_state(self):
        return self._state

    def roast(self):
        self._state = "roasting"

    def idle(self):
        self._state = "idle"
        self.heat_setting = 0

    @property
    def current_temp(self):
        if self._state == "roasting":
            heater_target = self._ambient + 40.0 * (self.heat_setting / 3.0)
            thermostat_target = float(self.target_temp)
            target = max(heater_target, thermostat_target)
        else:
            target = self._ambient
        self._temp = self._temp + 0.2 * (target - self._temp)
        return self._temp


class AutotuneTests(unittest.TestCase):
    def test_prefers_backend_native_autotune(self):
        roaster = _NativeAutotuneRoaster()

        result = autotune_pid_for_backend(roaster, settle_s=0.5, test_duration_s=2.0, min_rise_c=1.0)

        self.assertEqual(roaster.autotune_calls, 1)
        self.assertIn("settle_s", roaster.last_kwargs)
        self.assertAlmostEqual(result["kp"], 0.2, places=4)

    def test_generic_fallback_autotune_runs_without_backend_method(self):
        roaster = _GenericFallbackRoaster()

        result = autotune_pid_for_backend(roaster, settle_s=0.3, test_duration_s=1.2, min_rise_c=1.0)

        self.assertGreater(result["kp"], 0.0)
        self.assertGreater(result["ki"], 0.0)
        self.assertGreater(result["kd"], 0.0)
        self.assertGreater(result["delta_c"], 1.0)

    def test_uses_controller_native_autotune_when_adapter_method_missing(self):
        class Controller:
            def __init__(self):
                self.calls = 0

            def autotune_pid(self, **_kwargs):
                self.calls += 1
                return {"kp": 0.3, "ki": 0.04, "kd": 0.05}

        class AdapterWithoutMethod:
            connected = True

            def __init__(self):
                self._controller = Controller()

            def get_roaster_state(self):
                return "idle"

        roaster = AdapterWithoutMethod()
        result = autotune_pid_for_backend(roaster)

        self.assertEqual(roaster._controller.calls, 1)
        self.assertAlmostEqual(result["kp"], 0.3, places=4)

    def test_multispeed_autotune_runs_low_to_high(self):
        roaster = _NativeMultiSpeedRoaster(max_fan_speed=4, initial_fan_speed=3)

        result = autotune_pid_table_for_backend(roaster)

        self.assertTrue(result["ok"])
        self.assertEqual(result["fan_speeds"], [1, 2, 3, 4])
        self.assertEqual(result["completed_speeds"], [1, 2, 3, 4])
        self.assertEqual(roaster.autotune_fan_history, [1, 2, 3, 4])
        self.assertIn("K", result["results"]["1"])
        self.assertIn("tau_s", result["results"]["1"])
        self.assertIn("L", result["results"]["1"])
        # Final fan set restores the original fan speed.
        self.assertEqual(roaster.fan_set_history[-1], 3)

    def test_multispeed_autotune_aborts_on_failure_and_keeps_partial_results(self):
        roaster = _NativeMultiSpeedRoaster(max_fan_speed=4, initial_fan_speed=2, fail_on_fan=3)

        result = autotune_pid_table_for_backend(roaster)

        self.assertFalse(result["ok"])
        self.assertEqual(result["failed_speed"], 3)
        self.assertEqual(result["completed_speeds"], [1, 2])
        self.assertEqual(sorted(result["results"].keys()), ["1", "2"])
        self.assertIn("forced failure", result["error"])
        self.assertEqual(roaster.autotune_fan_history, [1, 2, 3])
        self.assertEqual(roaster.fan_set_history[-1], 2)

    def test_multispeed_autotune_normalizes_custom_speed_list(self):
        roaster = _NativeMultiSpeedRoaster(max_fan_speed=9, initial_fan_speed=4)

        result = autotune_pid_table_for_backend(roaster, fan_speeds=[3, 1, 2, 2, 0, "bad", 5])

        self.assertTrue(result["ok"])
        self.assertEqual(result["fan_speeds"], [1, 2, 3, 5])
        self.assertEqual(result["completed_speeds"], [1, 2, 3, 5])


if __name__ == "__main__":
    unittest.main()

