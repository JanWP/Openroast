import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import QtWidgets

from openroast.views.recipestab import RecipesTab


class _FakeRoastTab:
    def __init__(self, has_previous_state, clear_result=True, load_error=None):
        self._has_previous_state = has_previous_state
        self._clear_result = clear_result
        self._load_error = load_error
        self.clear_calls = 0
        self.load_calls = 0

    def has_previous_roast_state(self):
        return self._has_previous_state

    def clear_roast(self):
        self.clear_calls += 1
        return self._clear_result

    def load_recipe_into_roast_tab(self):
        self.load_calls += 1
        if self._load_error is not None:
            raise self._load_error


class _FakeMainWindow:
    def __init__(self):
        self.select_roast_calls = 0

    def select_roast_tab(self):
        self.select_roast_calls += 1


class _FakeRecipes:
    def __init__(self):
        self.loaded = False
        self.loaded_recipe = None
        self.clear_calls = 0

    def check_recipe_loaded(self):
        return self.loaded

    def load_recipe_json(self, recipe):
        self.loaded_recipe = recipe

    def clear_recipe(self):
        self.clear_calls += 1
        self.loaded_recipe = None


class RecipesTabLoadStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def _build_tab(self, roast_tab, recipes_obj=None):
        recipes_obj = recipes_obj or _FakeRecipes()
        window = _FakeMainWindow()
        tab = RecipesTab(roastTabObject=roast_tab, MainWindowObject=window, recipes_object=recipes_obj)
        tab.currentlySelectedRecipe = {"roastName": "Test"}
        return tab, recipes_obj, window

    def test_load_recipe_clears_previous_state_before_loading(self):
        roast_tab = _FakeRoastTab(has_previous_state=True, clear_result=True)
        tab, recipes_obj, window = self._build_tab(roast_tab)
        try:
            tab.load_recipe()
            self.assertEqual(roast_tab.clear_calls, 1)
            self.assertEqual(roast_tab.load_calls, 1)
            self.assertEqual(window.select_roast_calls, 1)
            self.assertEqual(recipes_obj.loaded_recipe["roastName"], "Test")
        finally:
            tab.close()
            self._app.processEvents()

    def test_load_recipe_aborts_when_clear_is_cancelled(self):
        roast_tab = _FakeRoastTab(has_previous_state=True, clear_result=False)
        tab, recipes_obj, window = self._build_tab(roast_tab)
        try:
            tab.load_recipe()
            self.assertEqual(roast_tab.clear_calls, 1)
            self.assertEqual(roast_tab.load_calls, 0)
            self.assertEqual(window.select_roast_calls, 0)
            self.assertIsNone(recipes_obj.loaded_recipe)
        finally:
            tab.close()
            self._app.processEvents()

    def test_load_recipe_shows_error_dialog_when_roast_tab_load_fails(self):
        roast_tab = _FakeRoastTab(
            has_previous_state=False,
            load_error=ValueError("target_temp_k out of range"),
        )
        tab, recipes_obj, window = self._build_tab(roast_tab)
        try:
            with patch("PyQt5.QtWidgets.QMessageBox.critical") as critical:
                tab.load_recipe()
                self.assertEqual(roast_tab.load_calls, 1)
                self.assertEqual(window.select_roast_calls, 0)
                self.assertEqual(recipes_obj.clear_calls, 1)
                critical.assert_called_once()
                _args, kwargs = critical.call_args
                # title/message are positional in this code path
                self.assertIn("Cannot load recipe", critical.call_args[0][1])
                self.assertIn("target_temp_k out of range", critical.call_args[0][2])
        finally:
            tab.close()
            self._app.processEvents()


if __name__ == "__main__":
    unittest.main()

