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
            self.assertGreaterEqual(editor.recipeSteps.columnWidth(3), editor.COLUMN_WIDTH_MODIFY)
            expected_min_width = (
                editor.COLUMN_WIDTH_TEMP
                + editor.COLUMN_WIDTH_FAN
                + editor.COLUMN_WIDTH_DURATION_COMPACT
                + editor.COLUMN_WIDTH_MODIFY
                + editor.TABLE_MIN_EXTRA_WIDTH
            )
            self.assertGreaterEqual(editor.recipeSteps.minimumWidth(), expected_min_width)
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


if __name__ == "__main__":
    unittest.main()

