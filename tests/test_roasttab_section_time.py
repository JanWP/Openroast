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
    def __init__(self, loaded=False, current_section_time=0):
        self._loaded = loaded
        self._current_section_time = current_section_time

    def check_recipe_loaded(self):
        return self._loaded

    def get_current_section_time(self):
        return self._current_section_time


class RoastTabSectionTimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def _make_tab_for_section_time(self, setpoint_s=0, remaining_s=0, recipes=None):
        tab = RoastTab.__new__(RoastTab)
        tab._section_time_setpoint_s = int(setpoint_s)
        tab._has_time_s = True
        tab.roaster = _FakeRoaster(remaining_s)
        tab.recipes = recipes if recipes is not None else _FakeRecipes(False, 0)

        tab.sectTimeSlider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        tab.sectTimeSlider.setRange(0, 900)
        tab.sectTimeSpinBox = QtWidgets.QTimeEdit()
        tab.sectionTimeLabel = QtWidgets.QLabel()

        return tab

    def test_section_time_slider_represents_setpoint_not_remaining(self):
        tab = self._make_tab_for_section_time(setpoint_s=120, remaining_s=90)

        tab.update_section_time_setpoint()
        tab.update_section_time()

        self.assertEqual(tab.sectTimeSlider.value(), 120)
        self.assertEqual(tab.sectionTimeLabel.text(), "01:30")

    def test_editing_section_time_preserves_elapsed_progress(self):
        tab = self._make_tab_for_section_time(setpoint_s=120, remaining_s=90)

        tab.update_section_time_setpoint()
        tab.sectTimeSlider.setValue(150)
        tab.update_sect_time_slider()

        self.assertEqual(tab._section_time_setpoint_s, 150)
        self.assertEqual(tab.roaster.time_remaining_s, 120)
        self.assertEqual(tab.sectionTimeLabel.text(), "02:00")

    def test_update_controllers_syncs_setpoint_from_recipe_section(self):
        recipes = _FakeRecipes(loaded=True, current_section_time=75)
        tab = self._make_tab_for_section_time(setpoint_s=10, remaining_s=50, recipes=recipes)
        tab.update_target_temp = lambda: None
        tab.update_fan_info = lambda: None

        tab.update_controllers()

        self.assertEqual(tab._section_time_setpoint_s, 75)
        self.assertEqual(tab.sectTimeSlider.value(), 75)

    def test_gauge_label_uses_remaining_section_time_text(self):
        tab = RoastTab.__new__(RoastTab)
        tab.compact_ui = False
        tab._min_temp_c = 20
        captured = []

        def fake_create_info_box(_self, label_text, _object_name, _value_label):
            captured.append(label_text)
            return QtWidgets.QVBoxLayout()

        tab.create_info_box = types.MethodType(fake_create_info_box, tab)
        tab.create_gauge_window()

        self.assertIn("REMAINING SECTION TIME", captured)


if __name__ == "__main__":
    unittest.main()

