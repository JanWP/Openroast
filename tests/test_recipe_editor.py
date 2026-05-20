import json
import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import QtCore, QtWidgets

from openroast.controllers.recipe import RECIPE_STEP_AFTER_FIRST_CRACK_TIME_KEY
from openroast.temperature import RECIPE_UNIT_FAHRENHEIT
from openroast.views.recipeeditorwindow import RecipeEditor


class RecipeEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_editor_honors_fullscreen_flag(self):
        editor = RecipeEditor(compact_ui=True, fullscreen=True)
        try:
            self.assertTrue(bool(editor.windowState() & QtCore.Qt.WindowFullScreen))
        finally:
            editor.close()
            self._app.processEvents()

    def test_curve_canvas_is_lazy_loaded_when_profile_tab_opens(self):
        editor = RecipeEditor(compact_ui=True)
        try:
            self.assertIsNone(editor.recipeCurveCanvas)
            editor.editorTabs.setCurrentIndex(editor.TAB_INDEX_PROFILE)
            self._app.processEvents()
            self.assertIsNotNone(editor.recipeCurveCanvas)
        finally:
            editor.close()
            self._app.processEvents()

    def test_save_uses_selected_temperature_unit(self):
        editor = RecipeEditor(compact_ui=False)
        with tempfile.TemporaryDirectory() as temp_dir:
            recipe_path = os.path.join(temp_dir, "unit-test.json")
            editor.recipe["file"] = recipe_path
            editor.temperatureUnitSelect.setCurrentText(RECIPE_UNIT_FAHRENHEIT)
            editor.save_recipe()

            with open(recipe_path, encoding="utf-8") as handle:
                saved = json.load(handle)

        try:
            self.assertEqual(saved["temperatureUnit"], RECIPE_UNIT_FAHRENHEIT)
            self.assertIn("targetTemp", saved["steps"][0])
            self.assertEqual(saved["steps"][0]["targetTemp"], 149)
        finally:
            editor.close()
            self._app.processEvents()

    def test_unit_toggle_does_not_crash_with_empty_steps_table(self):
        editor = RecipeEditor(compact_ui=True)
        try:
            editor.recipeSteps.setRowCount(0)
            editor.temperatureUnitSelect.setCurrentText("Kelvin")
            self.assertEqual(editor.recipeSteps.rowCount(), 0)
            self.assertEqual(editor.temperatureUnitSelect.currentText(), "Kelvin")
        finally:
            editor.close()
            self._app.processEvents()

    def test_editor_uses_legacy_fahrenheit_display_intent(self):
        legacy_recipe = {
            "roastName": "Legacy",
            "creator": "",
            "roastDescription": {"roastType": "", "description": ""},
            "bean": {"region": "", "country": "", "source": {"reseller": "", "link": ""}},
            "steps": [{"targetTemp": 100, "fanSpeed": 5, "sectionTime": 30}],
            "displayTemperatureUnit": "F",
        }
        editor = RecipeEditor(recipe_data=legacy_recipe, compact_ui=True)
        try:
            self.assertEqual(editor.temperatureUnitSelect.currentText(), RECIPE_UNIT_FAHRENHEIT)
        finally:
            editor.close()
            self._app.processEvents()

    def test_compact_temp_picker_updates_cell_value(self):
        editor = RecipeEditor(compact_ui=True)
        try:
            temp_widget = editor.recipeSteps.cellWidget(0, 0)
            temp_widget.setCurrentText(editor.COOLING_LABEL)
            self.assertEqual(temp_widget.currentText(), editor.COOLING_LABEL)
        finally:
            editor.close()
            self._app.processEvents()

    def test_compact_duration_picker_updates_cell_value(self):
        editor = RecipeEditor(compact_ui=True)
        try:
            duration_widget = editor.recipeSteps.cellWidget(0, 2)
            duration_widget.setValue(95)
            self.assertEqual(duration_widget.value(), 95)
        finally:
            editor.close()
            self._app.processEvents()

    def test_after_first_crack_duration_picker_updates_cell_value(self):
        editor = RecipeEditor(compact_ui=True)
        try:
            after_first_crack_widget = editor.recipeSteps.cellWidget(0, 3)
            after_first_crack_widget.setValue(40)
            self.assertEqual(after_first_crack_widget.value(), 0)

            editor.recipeSteps.cellWidget(0, 2).setValue(95)
            after_first_crack_widget.setValue(40)
            self.assertEqual(after_first_crack_widget.value(), 40)
        finally:
            editor.close()
            self._app.processEvents()

    def test_only_one_after_first_crack_step_remains_selected(self):
        recipe_data = {
            "roastName": "",
            "creator": "",
            "roastDescription": {"roastType": "", "description": ""},
            "bean": {"region": "", "country": "", "source": {"reseller": "", "link": ""}},
            "steps": [
                {"targetTemp": 100, "fanSpeed": 5, "sectionTime": 60},
                {"targetTemp": 110, "fanSpeed": 5, "sectionTime": 60},
            ],
        }
        editor = RecipeEditor(recipe_data=recipe_data, compact_ui=False)
        try:
            first_widget = editor.recipeSteps.cellWidget(0, 3)
            second_widget = editor.recipeSteps.cellWidget(1, 3)

            first_widget.setValue(20)
            second_widget.setValue(25)

            self.assertEqual(first_widget.value(), 0)
            self.assertEqual(second_widget.value(), 25)
        finally:
            editor.close()
            self._app.processEvents()

    def test_save_persists_after_first_crack_time(self):
        editor = RecipeEditor(compact_ui=False)
        with tempfile.TemporaryDirectory() as temp_dir:
            recipe_path = os.path.join(temp_dir, "first-crack.json")
            editor.recipe["file"] = recipe_path
            editor.recipeSteps.cellWidget(0, 2).setValue(90)
            editor.recipeSteps.cellWidget(0, 3).setValue(30)
            editor.save_recipe()

            with open(recipe_path, encoding="utf-8") as handle:
                saved = json.load(handle)

        try:
            self.assertEqual(saved["steps"][0][RECIPE_STEP_AFTER_FIRST_CRACK_TIME_KEY], 30)
        finally:
            editor.close()
            self._app.processEvents()

    def test_save_as_writes_to_selected_path(self):
        editor = RecipeEditor(compact_ui=False)
        with tempfile.TemporaryDirectory() as temp_dir:
            selected = os.path.join(temp_dir, "saved-by-save-as.json")
            original = QtWidgets.QFileDialog.getSaveFileName
            QtWidgets.QFileDialog.getSaveFileName = staticmethod(
                lambda *_args, **_kwargs: (selected, "Recipe Files (*.json)")
            )
            try:
                editor.save_recipe_as()
            finally:
                QtWidgets.QFileDialog.getSaveFileName = original

            self.assertEqual(editor.recipe.get("file"), selected)
            self.assertTrue(os.path.exists(selected))

            with open(selected, encoding="utf-8") as handle:
                saved = json.load(handle)
            self.assertIn("steps", saved)

        editor.close()
        self._app.processEvents()

    def test_save_as_appends_json_extension(self):
        editor = RecipeEditor(compact_ui=False)
        with tempfile.TemporaryDirectory() as temp_dir:
            selected_without_ext = os.path.join(temp_dir, "saved-no-ext")
            expected_path = f"{selected_without_ext}.json"
            original = QtWidgets.QFileDialog.getSaveFileName
            QtWidgets.QFileDialog.getSaveFileName = staticmethod(
                lambda *_args, **_kwargs: (selected_without_ext, "Recipe Files (*.json)")
            )
            try:
                editor.save_recipe_as()
            finally:
                QtWidgets.QFileDialog.getSaveFileName = original

            self.assertEqual(editor.recipe.get("file"), expected_path)
            self.assertTrue(os.path.exists(expected_path))

        editor.close()
        self._app.processEvents()

    def test_save_as_cancel_does_not_change_file(self):
        editor = RecipeEditor(compact_ui=False)
        editor.recipe["file"] = "existing.json"
        original = QtWidgets.QFileDialog.getSaveFileName
        QtWidgets.QFileDialog.getSaveFileName = staticmethod(
            lambda *_args, **_kwargs: ("", "")
        )
        try:
            editor.save_recipe_as()
        finally:
            QtWidgets.QFileDialog.getSaveFileName = original

        self.assertEqual(editor.recipe.get("file"), "existing.json")
        editor.close()
        self._app.processEvents()

    def test_save_as_dialog_defaults_to_my_recipes_path(self):
        editor = RecipeEditor(compact_ui=False)
        editor.recipe["file"] = "/tmp/from-elsewhere.json"
        editor.recipeName.setText("My Default")

        captured = {}
        original = QtWidgets.QFileDialog.getSaveFileName

        def fake_get_save_file_name(_parent, _title, start_path, _filter):
            captured["start_path"] = start_path
            return "", ""

        QtWidgets.QFileDialog.getSaveFileName = staticmethod(fake_get_save_file_name)
        try:
            editor.save_recipe_as()
        finally:
            QtWidgets.QFileDialog.getSaveFileName = original

        self.assertEqual(captured["start_path"], editor._default_recipe_path())
        editor.close()
        self._app.processEvents()

    def test_save_as_failure_keeps_existing_file_path(self):
        editor = RecipeEditor(compact_ui=False)
        editor.recipe["file"] = "existing.json"
        original_dialog = QtWidgets.QFileDialog.getSaveFileName
        original_save_method = editor._save_recipe_to_path
        QtWidgets.QFileDialog.getSaveFileName = staticmethod(
            lambda *_args, **_kwargs: ("/tmp/will-fail.json", "Recipe Files (*.json)")
        )

        def fail_save(_path):
            raise OSError("simulated write failure")

        editor._save_recipe_to_path = fail_save
        try:
            with self.assertRaises(OSError):
                editor.save_recipe_as()
        finally:
            QtWidgets.QFileDialog.getSaveFileName = original_dialog
            editor._save_recipe_to_path = original_save_method

        self.assertEqual(editor.recipe.get("file"), "existing.json")
        editor.close()
        self._app.processEvents()


if __name__ == "__main__":
    unittest.main()

