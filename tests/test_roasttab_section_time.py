import os
import types
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import QtCore, QtWidgets

from openroast.views.roasttab import RoastTab


class _FakeRoaster:
    def __init__(self, remaining_s=0):
        self.time_remaining_s = remaining_s


class _FakeRecipes:
    def __init__(self, loaded=False, current_section_duration=0):
        self._loaded = loaded
        self._current_section_duration = current_section_duration

    def check_recipe_loaded(self):
        return self._loaded

    def get_current_section_duration(self):
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
        tab._has_time_s = True
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

            def reset_simulation_state(self):
                self.reset_calls += 1

        tab = RoastTab.__new__(RoastTab)
        tab._confirm_on_clear = False
        tab.roaster = _FakeRoasterWithReset()
        tab.recipes = _FakeRecipes(False, 0)
        tab.clear_roast_tab_gui = lambda: None

        self.assertTrue(tab.clear_roast())
        self.assertEqual(tab.roaster.reset_calls, 1)


if __name__ == "__main__":
    unittest.main()

