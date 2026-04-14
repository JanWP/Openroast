import os
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import QtCore, QtWidgets

from openroast import app_config
from openroast.temperature import TEMP_UNIT_F
from openroast.views.preferencestab import PreferencesTab
from openroast.views.ui_constants import PreferencesUI


class PreferencesTabExpertTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    @staticmethod
    def _expert_tab_visible(tab_widget):
        tab_bar = tab_widget.tabBar()
        if hasattr(tab_bar, "isTabVisible"):
            return bool(tab_bar.isTabVisible(1))
        return bool(tab_widget.isTabEnabled(1))

    def _build_widget(self):
        return PreferencesTab(config=app_config.DEFAULT_CONFIG)

    def test_expert_toggle_controls_expert_tab_visibility(self):
        widget = self._build_widget()
        try:
            self.assertFalse(self._expert_tab_visible(widget.tabs))
            widget.expertModeEnabled.setChecked(True)
            self.assertTrue(self._expert_tab_visible(widget.tabs))
            widget.expertModeEnabled.setChecked(False)
            self.assertFalse(self._expert_tab_visible(widget.tabs))
        finally:
            widget.close()
            self._app.processEvents()

    def test_entering_expert_tab_requires_warning_ack(self):
        widget = self._build_widget()
        try:
            widget.expertModeEnabled.setChecked(True)

            with patch("PyQt5.QtWidgets.QMessageBox.question", return_value=QtWidgets.QMessageBox.No):
                widget.tabs.setCurrentIndex(1)
                self._app.processEvents()
                self.assertEqual(widget.tabs.currentIndex(), 0)

            with patch("PyQt5.QtWidgets.QMessageBox.question", return_value=QtWidgets.QMessageBox.Yes):
                widget.tabs.setCurrentIndex(1)
                self._app.processEvents()
                self.assertEqual(widget.tabs.currentIndex(), 1)
        finally:
            widget.close()
            self._app.processEvents()

    def test_restore_defaults_applies_only_current_tab(self):
        widget = self._build_widget()
        try:
            widget.expertModeEnabled.setChecked(True)
            widget.refreshIntervalMs.setValue(1300)
            widget.pidKp.setValue(0.5)

            with patch("PyQt5.QtWidgets.QMessageBox.question", return_value=QtWidgets.QMessageBox.Yes):
                widget.tabs.setCurrentIndex(0)
                widget._on_restore_defaults_clicked()

            self.assertEqual(widget.refreshIntervalMs.value(), app_config.DEFAULT_CONFIG["ui"]["refreshIntervalMs"])
            self.assertAlmostEqual(widget.pidKp.value(), 0.5, places=4)

            widget.expertModeEnabled.setChecked(True)
            widget._expert_warning_ack = True
            with patch("PyQt5.QtWidgets.QMessageBox.question", return_value=QtWidgets.QMessageBox.Yes):
                widget.tabs.setCurrentIndex(1)
                widget._on_restore_defaults_clicked()

            self.assertAlmostEqual(
                widget.pidKp.value(),
                app_config.DEFAULT_CONFIG["control"]["pid"]["kp"],
                places=4,
            )
        finally:
            widget.close()
            self._app.processEvents()

    def test_revert_changes_applies_only_current_tab(self):
        widget = self._build_widget()
        try:
            widget.expertModeEnabled.setChecked(True)
            widget.refreshIntervalMs.setValue(1300)
            widget.pidKp.setValue(0.5)

            with patch("PyQt5.QtWidgets.QMessageBox.question", return_value=QtWidgets.QMessageBox.Yes):
                widget.tabs.setCurrentIndex(0)
                widget._on_revert_changes_clicked()

            self.assertEqual(widget.refreshIntervalMs.value(), app_config.DEFAULT_CONFIG["ui"]["refreshIntervalMs"])
            self.assertAlmostEqual(widget.pidKp.value(), 0.5, places=4)

            widget.expertModeEnabled.setChecked(True)
            widget._expert_warning_ack = True
            with patch("PyQt5.QtWidgets.QMessageBox.question", return_value=QtWidgets.QMessageBox.Yes):
                widget.tabs.setCurrentIndex(1)
                widget._on_revert_changes_clicked()

            self.assertAlmostEqual(
                widget.pidKp.value(),
                app_config.DEFAULT_CONFIG["control"]["pid"]["kp"],
                places=4,
            )
        finally:
            widget.close()
            self._app.processEvents()

    def test_revert_changes_cancel_keeps_modified_values(self):
        widget = self._build_widget()
        try:
            widget.refreshIntervalMs.setValue(1300)
            with patch("PyQt5.QtWidgets.QMessageBox.question", return_value=QtWidgets.QMessageBox.No):
                widget.tabs.setCurrentIndex(0)
                widget._on_revert_changes_clicked()
            self.assertEqual(widget.refreshIntervalMs.value(), 1300)
        finally:
            widget.close()
            self._app.processEvents()

    def test_display_unit_switch_updates_temperature_fields(self):
        widget = self._build_widget()
        try:
            widget.plotYAxisHeadroomC.setValue(10.0)
            idx_f = widget.temperatureUnitSelect.findData(TEMP_UNIT_F)
            widget.temperatureUnitSelect.setCurrentIndex(idx_f)
            self._app.processEvents()

            self.assertIn("\N{DEGREE SIGN}F", widget.plotYAxisHeadroomC.suffix())
            # 10 C delta -> 18 F delta
            self.assertAlmostEqual(widget.plotYAxisHeadroomC.value(), 18.0, places=1)
        finally:
            widget.close()
            self._app.processEvents()

    def test_numeric_controls_use_unified_editor_style_ids(self):
        widget = self._build_widget()
        try:
            expected = widget.NUMERIC_EDITOR_OBJECT_NAME
            self.assertEqual(widget.refreshIntervalMs.editorObjectName(), expected)
            self.assertEqual(widget.plotYAxisHeadroomC.editorObjectName(), expected)
            self.assertEqual(widget.pidKp.editorObjectName(), expected)
        finally:
            widget.close()
            self._app.processEvents()

    def test_compact_numeric_controls_use_unified_compact_style_ids(self):
        widget = PreferencesTab(config=app_config.DEFAULT_CONFIG, compact_ui=True)
        try:
            expected = widget.NUMERIC_EDITOR_COMPACT_OBJECT_NAME
            self.assertEqual(widget.refreshIntervalMs.editorObjectName(), expected)
            self.assertEqual(widget.plotYAxisStepC.editorObjectName(), expected)
            self.assertEqual(widget.safetyMaxTempC.editorObjectName(), expected)
        finally:
            widget.close()
            self._app.processEvents()

    def test_numeric_controls_have_uniform_height_in_default_layout(self):
        widget = self._build_widget()
        try:
            expected = widget.NUMERIC_EDITOR_HEIGHT_DEFAULT
            self.assertEqual(widget.refreshIntervalMs.height(), expected)
            self.assertEqual(widget.plotYAxisHeadroomC.height(), expected)
            self.assertEqual(widget.plotYAxisStepC.height(), expected)
        finally:
            widget.close()
            self._app.processEvents()

    def test_numeric_controls_have_uniform_height_in_compact_layout(self):
        widget = PreferencesTab(config=app_config.DEFAULT_CONFIG, compact_ui=True)
        try:
            expected = widget.NUMERIC_EDITOR_HEIGHT_COMPACT
            self.assertEqual(widget.refreshIntervalMs.height(), expected)
            self.assertEqual(widget.plotYAxisHeadroomC.height(), expected)
            self.assertEqual(widget.plotYAxisStepC.height(), expected)
        finally:
            widget.close()
            self._app.processEvents()

    def test_pid_editors_use_requested_step_sizes(self):
        widget = self._build_widget()
        try:
            self.assertAlmostEqual(widget.pidKp._spec.step_small, PreferencesUI.PID_STEP_SMALL, places=6)
            self.assertAlmostEqual(widget.pidKp._spec.step_large, PreferencesUI.PID_STEP_LARGE, places=6)
            self.assertAlmostEqual(widget.pidKi._spec.step_small, PreferencesUI.PID_STEP_SMALL, places=6)
            self.assertAlmostEqual(widget.pidKi._spec.step_large, PreferencesUI.PID_STEP_LARGE, places=6)
            self.assertAlmostEqual(widget.pidKd._spec.step_small, PreferencesUI.PID_STEP_SMALL, places=6)
            self.assertAlmostEqual(widget.pidKd._spec.step_large, PreferencesUI.PID_STEP_LARGE, places=6)
        finally:
            widget.close()
            self._app.processEvents()

    def test_autotune_worker_is_cleaned_up_after_finish(self):
        class DummyRoaster:
            connected = True

            def get_roaster_state(self):
                return "idle"

            def autotune_pid(self, **_kwargs):
                return {"kp": 0.2, "ki": 0.03, "kd": 0.04}

        widget = PreferencesTab(config=app_config.DEFAULT_CONFIG, roaster=DummyRoaster())
        try:
            widget.expertModeEnabled.setChecked(True)
            widget._expert_warning_ack = True
            widget.tabs.setCurrentIndex(1)

            with patch("PyQt5.QtWidgets.QMessageBox.question", return_value=QtWidgets.QMessageBox.Yes):
                widget._on_autotune_clicked()

            deadline = QtCore.QTime.currentTime().addMSecs(2000)
            while widget._autotune_worker is not None and QtCore.QTime.currentTime() < deadline:
                self._app.processEvents()

            self.assertIsNone(widget._autotune_worker)
            self.assertIn("Autotune", widget.statusLabel.text())
        finally:
            widget.close()
            self._app.processEvents()

    def test_prepare_shutdown_waits_and_cleans_autotune_worker(self):
        class SlowRoaster:
            connected = True

            def get_roaster_state(self):
                return "idle"

            def autotune_pid(self, **_kwargs):
                time.sleep(0.05)
                return {"kp": 0.2, "ki": 0.03, "kd": 0.04}

        widget = PreferencesTab(config=app_config.DEFAULT_CONFIG, roaster=SlowRoaster())
        try:
            widget.expertModeEnabled.setChecked(True)
            widget._expert_warning_ack = True
            widget.tabs.setCurrentIndex(1)

            with patch("PyQt5.QtWidgets.QMessageBox.question", return_value=QtWidgets.QMessageBox.Yes):
                widget._on_autotune_clicked()

            widget.prepare_shutdown()
            self._app.processEvents()
            self.assertIsNone(widget._autotune_worker)
        finally:
            widget.close()
            self._app.processEvents()

    def test_autotune_uses_pre_autotune_hook(self):
        class DummyRoaster:
            connected = True

            def get_roaster_state(self):
                return "idle"

            def autotune_pid(self, **_kwargs):
                return {"kp": 0.2, "ki": 0.03, "kd": 0.04}

        hook_calls = []

        def pre_hook():
            hook_calls.append(True)
            return False

        widget = PreferencesTab(
            config=app_config.DEFAULT_CONFIG,
            roaster=DummyRoaster(),
            pre_autotune_hook=pre_hook,
        )
        try:
            with patch("PyQt5.QtWidgets.QMessageBox.question", return_value=QtWidgets.QMessageBox.Yes):
                widget._on_autotune_clicked()

            self.assertEqual(len(hook_calls), 1)
            self.assertIsNone(widget._autotune_worker)
            self.assertEqual(widget.statusLabel.text(), "Autotune canceled")
        finally:
            widget.close()
            self._app.processEvents()


if __name__ == "__main__":
    unittest.main()

