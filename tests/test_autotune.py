import unittest

from openroast.controllers.autotune import autotune_pid_for_backend


class _NativeAutotuneRoaster:
    def __init__(self):
        self.connected = True
        self._state = "idle"
        self.reset_calls = 0
        self.autotune_calls = 0

    def get_roaster_state(self):
        return self._state

    def idle(self):
        self._state = "idle"

    def reset_simulation_state(self):
        self.reset_calls += 1

    def autotune_pid(self, **kwargs):
        self.autotune_calls += 1
        self.last_kwargs = kwargs
        return {"kp": 0.2, "ki": 0.03, "kd": 0.04}


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

        self.assertEqual(roaster.reset_calls, 1)
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


if __name__ == "__main__":
    unittest.main()

