import os
import types
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import QtCore, QtWidgets

from openroast.views.roasttab import RoastTab


class _FakeRoaster:
    def __init__(self, remaining_s=0):
        self.time_remaining_s = remaining_s
        self.total_time_s = 0
        self.time_remaining = remaining_s
        self.total_time = 0
        self.max_fan_speed = 9
        self.fan_speed = 1
        self.cancel_autotune_calls = 0
        self.idle_calls = 0
        self.reset_control_state_calls = 0

    def cancel_autotune(self):
        self.cancel_autotune_calls += 1
        return True

    def idle(self):
        self.idle_calls += 1

    def reset_control_state(self):
        self.reset_control_state_calls += 1


class _FakeRecipes:
    def __init__(self, loaded=False, current_section_duration=0):
        self._loaded = loaded
        self._current_section_duration = current_section_duration

    def check_recipe_loaded(self):
        return self._loaded

    def get_current_section_duration(self):
        return self._current_section_duration

    def get_num_recipe_sections(self):
        return 1 if self._loaded else 0

    def get_section_duration(self, _index):
        return self._current_section_duration

    def reset_roaster_settings(self):
        return None

    def clear_recipe(self):
        return None


class RoastTabSectionTimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def _make_tab_for_section_duration(self, setpoint_s=0, remaining_s=0, recipes=None):
        tab = RoastTab.__new__(RoastTab)
        tab._section_duration_setpoint_s = int(setpoint_s)
        tab._is_local_roaster = True
        tab.roaster = _FakeRoaster(remaining_s)
        tab.recipes = recipes if recipes is not None else _FakeRecipes(False, 0)

        tab.sectionDurationSlider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        tab.sectionDurationSlider.setRange(0, 900)
        tab.sectionDurationSpinBox = QtWidgets.QTimeEdit()
        # Backward-compatible aliases retained in RoastTab.
        tab.sectTimeSlider = tab.sectionDurationSlider
        tab.sectTimeSpinBox = tab.sectionDurationSpinBox
        tab.sectionDurationLabel = QtWidgets.QLabel()
        tab.sectionTimeLabel = tab.sectionDurationLabel

        return tab

    def test_section_duration_slider_represents_setpoint_not_remaining(self):
        tab = self._make_tab_for_section_duration(setpoint_s=120, remaining_s=90)

        tab.update_section_duration_setpoint()
        tab.update_remaining_section_duration()

        self.assertEqual(tab.sectTimeSlider.value(), 120)
        self.assertEqual(tab.sectionDurationLabel.text(), "01:30")

    def test_editing_section_duration_preserves_elapsed_progress(self):
        tab = self._make_tab_for_section_duration(setpoint_s=120, remaining_s=90)

        tab.update_section_duration_setpoint()
        tab.sectTimeSlider.setValue(150)
        tab.update_section_duration_slider()

        self.assertEqual(tab._section_duration_setpoint_s, 150)
        self.assertEqual(tab.roaster.time_remaining_s, 120)
        self.assertEqual(tab.sectionDurationLabel.text(), "02:00")

    def test_update_controllers_syncs_setpoint_from_recipe_section_duration(self):
        recipes = _FakeRecipes(loaded=True, current_section_duration=75)
        tab = self._make_tab_for_section_duration(setpoint_s=10, remaining_s=50, recipes=recipes)
        tab.update_target_temp = lambda: None
        tab.update_fan_info = lambda: None

        tab.update_controllers()

        self.assertEqual(tab._section_duration_setpoint_s, 75)
        self.assertEqual(tab.sectTimeSlider.value(), 75)

    def test_gauge_label_uses_remaining_section_duration_text(self):
        tab = RoastTab.__new__(RoastTab)
        tab.compact_ui = False
        tab._min_temp_c = 20
        captured = []

        def fake_create_info_box(_self, label_text, _object_name, _value_label):
            captured.append(label_text)
            return QtWidgets.QVBoxLayout()

        tab.create_info_box = types.MethodType(fake_create_info_box, tab)
        tab.create_gauge_window()

        self.assertIn("REMAINING SECTION DURATION", captured)

    def test_clear_roast_resets_backend_simulation_state(self):
        class _FakeRoasterWithReset:
            def __init__(self):
                self.reset_calls = 0
                self.cancel_autotune_calls = 0
                self.idle_calls = 0
                self.reset_control_state_calls = 0

            def cancel_autotune(self):
                self.cancel_autotune_calls += 1

            def idle(self):
                self.idle_calls += 1

            def reset_control_state(self):
                self.reset_control_state_calls += 1

            def reset_simulation_state(self):
                self.reset_calls += 1

        tab = RoastTab.__new__(RoastTab)
        tab._confirm_on_clear = False
        tab.roaster = _FakeRoasterWithReset()
        tab.recipes = _FakeRecipes(False, 0)
        tab.clear_roast_tab_gui = lambda: None

        self.assertTrue(tab.clear_roast())
        self.assertEqual(tab.roaster.reset_calls, 1)
        self.assertEqual(tab.roaster.cancel_autotune_calls, 1)
        self.assertEqual(tab.roaster.idle_calls, 1)
        self.assertEqual(tab.roaster.reset_control_state_calls, 1)

    def test_stop_click_cancels_autotune_and_idles_roaster(self):
        tab = RoastTab.__new__(RoastTab)
        tab._confirm_on_stop = False
        tab.roaster = _FakeRoaster()

        tab.on_stop_clicked()

        self.assertEqual(tab.roaster.cancel_autotune_calls, 1)
        self.assertEqual(tab.roaster.idle_calls, 1)

    def test_reset_current_roast_cancels_autotune_and_resets_control_state(self):
        tab = RoastTab.__new__(RoastTab)
        tab._confirm_on_clear = False
        tab.roaster = _FakeRoaster()
        tab.recipes = _FakeRecipes(False, 0)
        tab._reset_backend_simulation_state = lambda: None
        tab.clear_roast_tab_gui = lambda: None

        tab.reset_current_roast()

        self.assertEqual(tab.roaster.cancel_autotune_calls, 1)
        self.assertEqual(tab.roaster.idle_calls, 1)
        self.assertEqual(tab.roaster.reset_control_state_calls, 1)

    def test_create_right_pane_non_compact_places_spacer_above_buttons(self):
        tab = RoastTab.__new__(RoastTab)
        tab.compact_ui = False
        tab.create_gauge_window = lambda: QtWidgets.QVBoxLayout()
        tab.create_slider_panel = lambda: QtWidgets.QGridLayout()
        tab.create_button_panel = lambda: QtWidgets.QGridLayout()

        pane = tab.create_right_pane()

        self.assertEqual(pane.count(), 4)
        self.assertIsNotNone(pane.itemAt(2).widget())
        self.assertIsNotNone(pane.itemAt(3).layout())

    def test_create_right_pane_compact_has_no_extra_spacer(self):
        tab = RoastTab.__new__(RoastTab)
        tab.compact_ui = True
        tab.create_gauge_window = lambda: QtWidgets.QVBoxLayout()
        tab.create_slider_panel = lambda: QtWidgets.QGridLayout()
        tab.create_button_panel = lambda: QtWidgets.QGridLayout()

        pane = tab.create_right_pane()

        self.assertEqual(pane.count(), 3)
        self.assertIsNotNone(pane.itemAt(2).layout())

    def test_create_slider_panel_uses_backend_runtime_fan_max(self):
        tab = RoastTab.__new__(RoastTab)
        tab.compact_ui = False
        tab.roaster = _FakeRoaster()
        tab.roaster.max_fan_speed = 5
        tab._min_temp_c = 20
        tab._max_temp_c = 250

        # Keep this test focused on fan control bounds.
        tab.update_target_temp = lambda: None
        tab.update_section_duration_setpoint = lambda: None

        tab.create_slider_panel()

        self.assertEqual(tab.fanSlider.minimum(), 1)
        self.assertEqual(tab.fanSlider.maximum(), 5)
        self.assertEqual(tab.fanSpeedSpinBox.minimum(), 1)
        self.assertEqual(tab.fanSpeedSpinBox.maximum(), 5)

    def test_update_fan_info_syncs_controls_to_runtime_fan_speed(self):
        tab = RoastTab.__new__(RoastTab)
        tab.roaster = _FakeRoaster()
        tab.roaster.max_fan_speed = 6
        tab.roaster.fan_speed = 4
        tab.fanSlider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        tab.fanSlider.setRange(1, 9)
        tab.fanSpeedSpinBox = QtWidgets.QSpinBox()
        tab.fanSpeedSpinBox.setRange(1, 9)

        tab.update_fan_info()

        self.assertEqual(tab.fanSlider.maximum(), 6)
        self.assertEqual(tab.fanSpeedSpinBox.maximum(), 6)
        self.assertEqual(tab.fanSlider.value(), 4)
        self.assertEqual(tab.fanSpeedSpinBox.value(), 4)


