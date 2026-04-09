import json
import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import QtCore, QtWidgets

from openroast.temperature import RECIPE_UNIT_FAHRENHEIT
from openroast.views.recipeeditorwindow import RecipeEditor


class RecipeEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_compact_editor_has_tabs_and_requested_headers(self):
        editor = RecipeEditor(compact_ui=True)
        try:
            self.assertEqual(editor.editorTabs.tabText(0), "Recipe info")
            self.assertEqual(editor.editorTabs.tabText(1), "Heating profile")

            headers = [editor.recipeSteps.horizontalHeaderItem(i).text() for i in range(4)]
            self.assertEqual(headers, [f"T ({chr(176)}C)", "Fan", "Duration", "Modify"])

            corner_widget = editor.editorTabs.cornerWidget(QtCore.Qt.TopRightCorner)
            corner_layout = corner_widget.layout()
            corner_texts = [corner_layout.itemAt(i).widget().text() for i in range(corner_layout.count())]
            self.assertEqual(corner_texts, ["CLOSE", "SAVE", "SAVE AS"])

            self.assertEqual(editor.closeButton.width(), editor.CORNER_BUTTON_WIDTH_CLOSE)
            self.assertEqual(editor.saveButton.width(), editor.CORNER_BUTTON_WIDTH_SAVE)
            self.assertEqual(editor.saveAsButton.width(), editor.CORNER_BUTTON_WIDTH_SAVE_AS)
            self.assertEqual(editor.closeButton.height(), editor.CORNER_BUTTON_HEIGHT)
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
            headers = [editor.recipeSteps.horizontalHeaderItem(i).text() for i in range(4)]
            self.assertEqual(headers, [f"T ({chr(176)}K)", "Fan", "Duration", "Modify"])
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
            headers = [editor.recipeSteps.horizontalHeaderItem(i).text() for i in range(4)]
            self.assertEqual(headers, [f"T ({chr(176)}F)", "Fan", "Duration", "Modify"])
            self.assertEqual(editor.temperatureUnitSelect.currentText(), RECIPE_UNIT_FAHRENHEIT)
        finally:
            editor.close()
            self._app.processEvents()

    def test_steps_table_uses_named_geometry_constants(self):
        editor = RecipeEditor(compact_ui=True)
        try:
            self.assertGreaterEqual(editor.recipeSteps.columnWidth(0), editor.COLUMN_WIDTH_TEMP)
            self.assertGreaterEqual(editor.recipeSteps.columnWidth(1), editor.COLUMN_WIDTH_FAN)
            self.assertGreaterEqual(
                editor.recipeSteps.columnWidth(2),
                editor.COLUMN_WIDTH_DURATION_COMPACT,
            )
            self.assertGreaterEqual(
                editor.recipeSteps.columnWidth(3),
                editor.COLUMN_WIDTH_MODIFY_COMPACT,
            )
            expected_min_width = (
                editor.COLUMN_WIDTH_TEMP
                + editor.COLUMN_WIDTH_FAN
                + editor.COLUMN_WIDTH_DURATION_COMPACT
                + editor.COLUMN_WIDTH_MODIFY_COMPACT
                + editor.TABLE_MIN_EXTRA_WIDTH
            )
            self.assertGreaterEqual(editor.recipeSteps.minimumWidth(), expected_min_width)
        finally:
            editor.close()
            self._app.processEvents()

    def test_compact_row_action_widget_omits_move_arrows(self):
        editor = RecipeEditor(compact_ui=True)
        try:
            action_widget = editor.recipeSteps.cellWidget(0, 3)
            self.assertIsNotNone(action_widget.findChild(QtWidgets.QPushButton, "deleteRow"))
            self.assertIsNotNone(action_widget.findChild(QtWidgets.QPushButton, "insertRow"))
            self.assertIsNone(action_widget.findChild(QtWidgets.QPushButton, "upArrow"))
            self.assertIsNone(action_widget.findChild(QtWidgets.QPushButton, "downArrow"))
        finally:
            editor.close()
            self._app.processEvents()

    def test_default_row_action_widget_keeps_move_arrows(self):
        editor = RecipeEditor(compact_ui=False)
        try:
            action_widget = editor.recipeSteps.cellWidget(0, 3)
            self.assertIsNotNone(action_widget.findChild(QtWidgets.QPushButton, "deleteRow"))
            self.assertIsNotNone(action_widget.findChild(QtWidgets.QPushButton, "insertRow"))
            self.assertIsNotNone(action_widget.findChild(QtWidgets.QPushButton, "upArrow"))
            self.assertIsNotNone(action_widget.findChild(QtWidgets.QPushButton, "downArrow"))
        finally:
            editor.close()
            self._app.processEvents()

    def test_compact_temp_picker_updates_cell_value(self):
        editor = RecipeEditor(compact_ui=True)
        try:
            editor._prompt_compact_temperature_selection = lambda _current: editor.COOLING_LABEL
            editor.open_compact_temp_picker(0)
            self.assertEqual(editor.recipeSteps.cellWidget(0, 0).currentText(), editor.COOLING_LABEL)
        finally:
            editor.close()
            self._app.processEvents()

    def test_compact_duration_picker_updates_cell_value(self):
        editor = RecipeEditor(compact_ui=True)
        try:
            editor._prompt_compact_duration_selection = lambda _seconds: 95
            editor.open_compact_duration_picker(0)
            duration = QtCore.QTime(0, 0, 0).secsTo(editor.recipeSteps.cellWidget(0, 2).time())
            self.assertEqual(duration, 95)
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

