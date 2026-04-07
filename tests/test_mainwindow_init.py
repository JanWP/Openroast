import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import QtWidgets

from openroast.views.mainwindow import MainWindow


class _DummyRoastTab(QtWidgets.QWidget):
    def __init__(self, roaster, recipes, compact_ui=False):
        super().__init__()
        self._roaster = roaster
        self._recipes = recipes
        self._compact_ui = compact_ui

    def clear_roast(self):
        return None

    def reset_current_roast(self):
        return None

    def save_roast_graph(self):
        return None

    def save_roast_graph_csv(self):
        return None

    def schedule_update_controllers(self):
        return None


class _DummyRecipesTab(QtWidgets.QWidget):
    def __init__(self, roastTabObject, MainWindowObject, recipes_object):
        super().__init__()
        self.roast_tab = roastTabObject
        self.main_window = MainWindowObject
        self.recipes = recipes_object


class _FakeRoaster:
    heater_level = 50
    heater_output = True
    heat_setting = 2

    def __init__(self):
        self._heater_cb = None
        self._heater_level_cb = None
        self.disconnect_called = False

    def set_heater_output_func(self, callback):
        self._heater_cb = callback
        # Simulate immediate backend edge callback on subscription.
        callback(True)
        return True

    def set_heater_level_func(self, callback):
        self._heater_level_cb = callback
        callback(50)
        return True

    def disconnect(self):
        self.disconnect_called = True


class MainWindowInitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_mainwindow_initializes_and_handles_heater_led_callback(self):
        fake_roaster = _FakeRoaster()

        with patch("openroast.views.mainwindow.roasttab.RoastTab", _DummyRoastTab), patch(
            "openroast.views.mainwindow.recipestab.RecipesTab", _DummyRecipesTab
        ):
            window = MainWindow(recipes=object(), roaster=fake_roaster, compact_ui=True)
            try:
                self.assertTrue(hasattr(window, "_heaterLedOn"))
                self.assertTrue(window._heaterLedOn)
                self.assertEqual(window.heaterDebugLabel.text(), "Heater:  50%")
                self.assertIn("background-color: #8ab71b", window.heaterDebugLed.styleSheet())
            finally:
                window.close()
                self._app.processEvents()

        self.assertTrue(fake_roaster.disconnect_called)


if __name__ == "__main__":
    unittest.main()

