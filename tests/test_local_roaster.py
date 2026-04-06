import unittest
from unittest.mock import patch

from localroaster import RoasterState
from openroast.backends.local_roaster import LocalRoaster
from openroast.temperature import MAX_TEMPERATURE_C, MIN_TEMPERATURE_C


class FakeController:
    def __init__(self):
        self.connected = False
        self.fan_speed = 1
        self.heat_setting = 0
        self.target_temp_f = 392
        self.current_temp_f = 212
        self.time_remaining_s = 0
        self.total_time_s = 0
        self.heater_level = 0
        self.heater_output = False
        self.state = RoasterState.DISCONNECTED

        self.telemetry_listener = None
        self.state_transition_cb = None

        self.connect_calls = 0
        self.shutdown_calls = 0
        self.idle_calls = 0
        self.roast_calls = 0
        self.cool_calls = 0
        self.sleep_calls = 0

    def add_telemetry_listener(self, func):
        self.telemetry_listener = func

    def set_state_transition_callback(self, func):
        self.state_transition_cb = func

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


class LocalRoasterAdapterTests(unittest.TestCase):
    def test_constructor_passes_min_max_bounds_to_controller_config(self):
        fake_controller = FakeController()

        with patch("openroast.backends.local_roaster.create_controller", return_value=fake_controller) as create_mock:
            roaster = LocalRoaster()

        cfg = create_mock.call_args.kwargs["config"]
        self.assertAlmostEqual(cfg.min_display_temp_f, 68.0)
        self.assertAlmostEqual(cfg.max_temp_f, 554.0)
        self.assertEqual(roaster.temperature_min_c, MIN_TEMPERATURE_C)
        self.assertEqual(roaster.temperature_max_c, MAX_TEMPERATURE_C)

    def test_current_temp_clamps_only_to_max_bound(self):
        fake_controller = FakeController()
        fake_controller.current_temp_f = 1200

        with patch("openroast.backends.local_roaster.create_controller", return_value=fake_controller):
            roaster = LocalRoaster()

        self.assertEqual(roaster.current_temp, MAX_TEMPERATURE_C)

        # Do not apply any lower clamp in the adapter.
        fake_controller.current_temp_f = 32
        self.assertEqual(roaster.current_temp, 0)

    def test_target_temp_getter_setter_convert_between_c_and_f(self):
        fake_controller = FakeController()
        fake_controller.target_temp_f = 401

        with patch("openroast.backends.local_roaster.create_controller", return_value=fake_controller):
            roaster = LocalRoaster()

        self.assertEqual(roaster.target_temp, 205)

        roaster.target_temp = 100
        self.assertEqual(fake_controller.target_temp_f, 212)

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

    def test_set_state_transition_func_requires_pre_connect(self):
        fake_controller = FakeController()

        with patch("openroast.backends.local_roaster.create_controller", return_value=fake_controller):
            roaster = LocalRoaster()

        self.assertTrue(roaster.set_state_transition_func(lambda: None))

        fake_controller.connected = True
        self.assertFalse(roaster.set_state_transition_func(lambda: None))


if __name__ == "__main__":
    unittest.main()

