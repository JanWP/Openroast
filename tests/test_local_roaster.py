import unittest
from unittest.mock import patch

from localroaster import RoasterState
from openroast.backends.local_roaster import LocalRoaster
from openroast.temperature import MAX_TEMPERATURE_C, MIN_TEMPERATURE_C, celsius_to_kelvin, kelvin_to_celsius


class FakeController:
    def __init__(self):
        self.connected = False
        self.fan_speed = 1
        self.max_fan_speed = 9
        self.heat_setting = 0
        self.target_temp_k = celsius_to_kelvin(200)
        self.current_temp_k = celsius_to_kelvin(100)
        self.time_remaining_s = 0
        self.total_time_s = 0
        self.heater_level = 0
        self.heater_output = False
        self.state = RoasterState.DISCONNECTED

        self.telemetry_listener = None
        self.state_transition_cb = None
        self.heater_output_listener = None
        self.heater_level_listener = None
        self.add_telemetry_listener_calls = 0
        self.add_heater_output_listener_calls = 0
        self.add_heater_level_listener_calls = 0
        self.set_state_transition_callback_calls = 0

        self.connect_calls = 0
        self.shutdown_calls = 0
        self.idle_calls = 0
        self.roast_calls = 0
        self.cool_calls = 0
        self.sleep_calls = 0
        self.reset_simulation_calls = 0
        self.runtime_config_calls = []
        self.autotune_calls = 0
        self.cancel_autotune_calls = 0
        self.reset_control_state_calls = 0

    def add_telemetry_listener(self, func):
        self.add_telemetry_listener_calls += 1
        self.telemetry_listener = func

    def set_state_transition_callback(self, func):
        self.set_state_transition_callback_calls += 1
        self.state_transition_cb = func

    def add_heater_output_listener(self, func):
        self.add_heater_output_listener_calls += 1
        self.heater_output_listener = func

    def add_heater_level_listener(self, func):
        self.add_heater_level_listener_calls += 1
        self.heater_level_listener = func

    def connect(self):
        self.connect_calls += 1
        self.connected = True

    def shutdown(self):
        self.shutdown_calls += 1
        self.connected = False

    def idle(self):
        self.idle_calls += 1

    def roast(self):
        self.roast_calls += 1

    def cool(self):
        self.cool_calls += 1

    def sleep(self):
        self.sleep_calls += 1

    def reset_simulation_state(self):
        self.reset_simulation_calls += 1

    def apply_runtime_config(self, **kwargs):
        self.runtime_config_calls.append(kwargs)

    def autotune_pid(self, **kwargs):
        self.autotune_calls += 1
        self.autotune_kwargs = kwargs
        return {"kp": 0.2, "ki": 0.03, "kd": 0.04}

    def cancel_autotune(self):
        self.cancel_autotune_calls += 1
        return True

    def reset_control_state(self):
        self.reset_control_state_calls += 1


class LocalRoasterAdapterTests(unittest.TestCase):
    def test_constructor_passes_min_max_bounds_to_controller_config(self):
        fake_controller = FakeController()

        with patch("openroast.backends.local_roaster.create_controller", return_value=fake_controller) as create_mock:
            roaster = LocalRoaster()

        cfg = create_mock.call_args.kwargs["config"]
        self.assertAlmostEqual(cfg.min_display_temp_k, celsius_to_kelvin(MIN_TEMPERATURE_C), places=2)
        self.assertAlmostEqual(cfg.max_temp_k, celsius_to_kelvin(MAX_TEMPERATURE_C), places=2)
        self.assertEqual(roaster.temperature_min_c, MIN_TEMPERATURE_C)
        self.assertEqual(roaster.temperature_max_c, MAX_TEMPERATURE_C)

    def test_constructor_forwards_expert_control_and_safety_settings(self):
        fake_controller = FakeController()

        with patch("openroast.backends.local_roaster.create_controller", return_value=fake_controller) as create_mock:
            LocalRoaster(
                kp=0.2,
                ki=0.03,
                kd=0.04,
                sample_period_s=0.25,
                pwm_cycle_s=2.0,
                max_temp_c=240.0,
                heater_cutoff_enabled=False,
            )

        cfg = create_mock.call_args.kwargs["config"]
        self.assertAlmostEqual(cfg.kp, 0.2, places=4)
        self.assertAlmostEqual(cfg.ki, 0.03, places=4)
        self.assertAlmostEqual(cfg.kd, 0.04, places=4)
        self.assertAlmostEqual(cfg.sample_period_s, 0.25, places=4)
        self.assertAlmostEqual(cfg.pwm_cycle_s, 2.0, places=4)
        self.assertAlmostEqual(cfg.max_temp_k, celsius_to_kelvin(240.0), places=2)
        self.assertFalse(cfg.heater_cutoff_enabled)

    def test_current_temp_clamps_only_to_max_bound(self):
        fake_controller = FakeController()
        fake_controller.current_temp_k = 1200

        with patch("openroast.backends.local_roaster.create_controller", return_value=fake_controller):
            roaster = LocalRoaster()

        self.assertEqual(roaster.current_temp, MAX_TEMPERATURE_C)

        # Do not apply any lower clamp in the adapter.
        fake_controller.current_temp_k = 273.15
        self.assertEqual(roaster.current_temp, 0)

    def test_target_temp_getter_setter_convert_between_c_and_k(self):
        fake_controller = FakeController()
        fake_controller.target_temp_k = celsius_to_kelvin(205)

        with patch("openroast.backends.local_roaster.create_controller", return_value=fake_controller):
            roaster = LocalRoaster()

        self.assertEqual(roaster.target_temp, 205)

        roaster.target_temp = 100
        self.assertAlmostEqual(fake_controller.target_temp_k, celsius_to_kelvin(100), places=2)

    def test_max_fan_speed_passthrough(self):
        fake_controller = FakeController()
        fake_controller.max_fan_speed = 7

        with patch("openroast.backends.local_roaster.create_controller", return_value=fake_controller):
            roaster = LocalRoaster()

        self.assertEqual(roaster.max_fan_speed, 7)

    def test_get_roaster_state_maps_controller_states(self):
        fake_controller = FakeController()

        with patch("openroast.backends.local_roaster.create_controller", return_value=fake_controller):
            roaster = LocalRoaster()

        fake_controller.state = RoasterState.IDLE
        self.assertEqual(roaster.get_roaster_state(), "idle")

        fake_controller.state = RoasterState.ROASTING
        self.assertEqual(roaster.get_roaster_state(), "roasting")

        fake_controller.state = RoasterState.COOLING
        self.assertEqual(roaster.get_roaster_state(), "cooling")

        fake_controller.state = RoasterState.SLEEPING
        self.assertEqual(roaster.get_roaster_state(), "sleeping")

        fake_controller.state = RoasterState.FAULT
        self.assertEqual(roaster.get_roaster_state(), "unknown")

    def test_get_roaster_state_uses_connecting_override_when_not_connected(self):
        fake_controller = FakeController()

        with patch("openroast.backends.local_roaster.create_controller", return_value=fake_controller):
            roaster = LocalRoaster()

        roaster._connect_state = roaster.CS_CONNECTING
        fake_controller.connected = False
        fake_controller.state = RoasterState.IDLE
        self.assertEqual(roaster.get_roaster_state(), "connecting")

        fake_controller.connected = True
        self.assertEqual(roaster.get_roaster_state(), "idle")

    def test_auto_connect_registers_listeners_once_and_resets_connect_state(self):
        fake_controller = FakeController()

        with patch("openroast.backends.local_roaster.create_controller", return_value=fake_controller):
            roaster = LocalRoaster()

        self.assertEqual(roaster.connect_state, 0)

        roaster.auto_connect()
        self.assertEqual(fake_controller.connect_calls, 1)
        self.assertEqual(roaster.connect_state, 0)
        self.assertEqual(fake_controller.add_telemetry_listener_calls, 1)
        self.assertEqual(fake_controller.add_heater_output_listener_calls, 1)
        self.assertEqual(fake_controller.add_heater_level_listener_calls, 1)
        self.assertEqual(fake_controller.set_state_transition_callback_calls, 1)

        roaster.auto_connect()
        self.assertEqual(fake_controller.connect_calls, 2)
        self.assertEqual(fake_controller.add_telemetry_listener_calls, 1)
        self.assertEqual(fake_controller.add_heater_output_listener_calls, 1)
        self.assertEqual(fake_controller.add_heater_level_listener_calls, 1)
        self.assertEqual(fake_controller.set_state_transition_callback_calls, 1)

    def test_auto_connect_with_callbacks_starts_threads_once(self):
        fake_controller = FakeController()

        class FakeThread:
            started_count = 0

            def __init__(self, *args, **kwargs):
                self.target = kwargs.get("target")
                self.args = kwargs.get("args")

            def start(self):
                FakeThread.started_count += 1

        with patch("openroast.backends.local_roaster.create_controller", return_value=fake_controller), patch(
            "openroast.backends.local_roaster.threading.Thread", FakeThread
        ):
            roaster = LocalRoaster(update_data_func=lambda: None, state_transition_func=lambda: None)
            roaster.auto_connect()
            roaster.auto_connect()

        self.assertEqual(FakeThread.started_count, 2)

    def test_auto_connect_wires_controller_callbacks_to_adapter_events(self):
        fake_controller = FakeController()

        with patch("openroast.backends.local_roaster.create_controller", return_value=fake_controller):
            roaster = LocalRoaster()

        roaster.auto_connect()
        self.assertIsNotNone(fake_controller.telemetry_listener)
        self.assertIsNotNone(fake_controller.state_transition_cb)

        self.assertFalse(roaster._update_event.is_set())
        self.assertFalse(roaster._state_transition_event.is_set())

        fake_controller.telemetry_listener(None)
        fake_controller.state_transition_cb()

        self.assertTrue(roaster._update_event.is_set())
        self.assertTrue(roaster._state_transition_event.is_set())

    def test_set_state_transition_func_requires_pre_connect(self):
        fake_controller = FakeController()

        with patch("openroast.backends.local_roaster.create_controller", return_value=fake_controller):
            roaster = LocalRoaster()

        roaster.set_state_transition_func(lambda: None)

        fake_controller.connected = True
        with self.assertRaises(RuntimeError):
            roaster.set_state_transition_func(lambda: None)

    def test_set_heater_output_func_allows_post_connect_registration(self):
        fake_controller = FakeController()

        class FakeThread:
            started_count = 0

            def __init__(self, *args, **kwargs):
                self.target = kwargs.get("target")
                self.args = kwargs.get("args")

            def start(self):
                FakeThread.started_count += 1

        with patch("openroast.backends.local_roaster.create_controller", return_value=fake_controller), patch(
            "openroast.backends.local_roaster.threading.Thread", FakeThread
        ):
            roaster = LocalRoaster()
            roaster.auto_connect()
            self.assertTrue(roaster.set_heater_output_func(lambda _value: None))

        self.assertEqual(FakeThread.started_count, 0)

    def test_heater_output_listener_calls_registered_callback(self):
        fake_controller = FakeController()

        with patch("openroast.backends.local_roaster.create_controller", return_value=fake_controller):
            roaster = LocalRoaster()

        seen = []
        roaster.set_heater_output_func(lambda value: seen.append(bool(value)))
        roaster.auto_connect()
        self.assertIsNotNone(fake_controller.heater_output_listener)

        fake_controller.heater_output_listener(True)

        self.assertTrue(roaster._heater_output_state)
        self.assertIn(True, seen)

    def test_set_heater_level_func_allows_post_connect_registration(self):
        fake_controller = FakeController()

        class FakeThread:
            started_count = 0

            def __init__(self, *args, **kwargs):
                self.target = kwargs.get("target")
                self.args = kwargs.get("args")

            def start(self):
                FakeThread.started_count += 1

        with patch("openroast.backends.local_roaster.create_controller", return_value=fake_controller), patch(
            "openroast.backends.local_roaster.threading.Thread", FakeThread
        ):
            roaster = LocalRoaster()
            roaster.auto_connect()
            self.assertTrue(roaster.set_heater_level_func(lambda _value: None))

        self.assertEqual(FakeThread.started_count, 0)

    def test_heater_level_listener_calls_registered_callback(self):
        fake_controller = FakeController()

        with patch("openroast.backends.local_roaster.create_controller", return_value=fake_controller):
            roaster = LocalRoaster()

        seen = []
        roaster.set_heater_level_func(lambda value: seen.append(int(value)))
        roaster.auto_connect()
        self.assertIsNotNone(fake_controller.heater_level_listener)

        fake_controller.heater_level_listener(67)

        self.assertEqual(roaster._heater_level_state, 67)
        self.assertIn(67, seen)

    def test_reset_simulation_state_forwards_to_controller(self):
        fake_controller = FakeController()

        with patch("openroast.backends.local_roaster.create_controller", return_value=fake_controller):
            roaster = LocalRoaster()

        self.assertTrue(roaster.reset_simulation_state())
        self.assertEqual(fake_controller.reset_simulation_calls, 1)

    def test_apply_runtime_preferences_forwards_pid_and_safety_settings(self):
        fake_controller = FakeController()

        with patch("openroast.backends.local_roaster.create_controller", return_value=fake_controller):
            roaster = LocalRoaster()

        config = {
            "display": {"temperatureUnitDefault": "F"},
            "control": {
                "pid": {"kp": 0.2, "ki": 0.03, "kd": 0.04},
                "pwmCycleSeconds": 1.5,
                "samplePeriodSeconds": 0.2,
            },
            "safety": {
                "maxTemp": {"value": 430.0, "unit": "F"},
                "heaterCutoffEnabled": True,
            },
        }

        self.assertTrue(roaster.apply_runtime_preferences(config))
        self.assertEqual(len(fake_controller.runtime_config_calls), 1)
        call = fake_controller.runtime_config_calls[0]
        self.assertAlmostEqual(call["kp"], 0.2, places=4)
        self.assertAlmostEqual(call["ki"], 0.03, places=4)
        self.assertAlmostEqual(call["kd"], 0.04, places=4)
        self.assertAlmostEqual(call["pwm_cycle_s"], 1.5, places=4)
        self.assertAlmostEqual(call["sample_period_s"], 0.2, places=4)
        self.assertTrue(call["heater_cutoff_enabled"])

    def test_autotune_pid_forwards_to_controller(self):
        fake_controller = FakeController()

        with patch("openroast.backends.local_roaster.create_controller", return_value=fake_controller):
            roaster = LocalRoaster()

        result = roaster.autotune_pid()
        self.assertEqual(fake_controller.autotune_calls, 1)
        self.assertAlmostEqual(result["kp"], 0.2, places=4)

        roaster.autotune_pid(settle_s=1.0, test_duration_s=10.0)
        self.assertEqual(fake_controller.autotune_calls, 2)
        self.assertAlmostEqual(fake_controller.autotune_kwargs["settle_s"], 1.0, places=4)

    def test_cancel_autotune_forwards_to_controller(self):
        fake_controller = FakeController()

        with patch("openroast.backends.local_roaster.create_controller", return_value=fake_controller):
            roaster = LocalRoaster()

        self.assertTrue(roaster.cancel_autotune())
        self.assertEqual(fake_controller.cancel_autotune_calls, 1)

    def test_reset_control_state_forwards_to_controller(self):
        fake_controller = FakeController()

        with patch("openroast.backends.local_roaster.create_controller", return_value=fake_controller):
            roaster = LocalRoaster()

        self.assertTrue(roaster.reset_control_state())
        self.assertEqual(fake_controller.reset_control_state_calls, 1)


if __name__ == "__main__":
    unittest.main()

