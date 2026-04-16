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
from tests.config_sandbox import ConfigSandboxMixin


class PreferencesTabExpertTests(ConfigSandboxMixin, unittest.TestCase):
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
        return PreferencesTab(config=app_config.DEFAULT_CONFIG, runtime_backend="local-mock")

    def test_explicit_runtime_backend_context_is_preserved(self):
        cfg = app_config.update_config(app_config.DEFAULT_CONFIG, backend="usb")
        widget = PreferencesTab(config=cfg, runtime_backend="local-mock")
        try:
            self.assertEqual(widget.runtime_backend, "local-mock")
            self.assertEqual(widget.backendSelect.currentText(), "usb")
        finally:
            widget.close()
            self._app.processEvents()

    def test_pid_fan_selector_uses_runtime_backend_capabilities(self):
        class DummyRoaster:
            max_fan_speed = 5

        widget = PreferencesTab(
            config=app_config.DEFAULT_CONFIG,
            runtime_backend="local-mock",
            roaster=DummyRoaster(),
        )
        try:
            self.assertEqual(widget.pidFanSpeedSelect.count(), 5)
            self.assertEqual(widget.pidFanSpeedSelect.itemData(0), 1)
            self.assertEqual(widget.pidFanSpeedSelect.itemData(4), 5)
        finally:
            widget.close()
            self._app.processEvents()

    def test_save_preferences_updates_only_runtime_backend_selected_fan_row(self):
        base = app_config.normalize_config(app_config.DEFAULT_CONFIG)
        base = app_config.set_pid_for_backend_speed(base, "local-mock", 2, 0.11, 0.012, 0.015)
        base = app_config.set_pid_for_backend_speed(base, "usb", 2, 0.7, 0.08, 0.09)

        saved_payloads = []

        def _capture_save(cfg):
            normalized = app_config.normalize_config(cfg)
            saved_payloads.append(normalized)
            return normalized

        with patch("openroast.views.preferencestab.app_config.save_config", side_effect=_capture_save):
            widget = PreferencesTab(config=base, runtime_backend="local-mock")
            try:
                idx = widget.pidFanSpeedSelect.findData(2)
                widget.pidFanSpeedSelect.setCurrentIndex(idx)
                widget.pidKp.setValue(0.22)
                widget.pidKi.setValue(0.023)
                widget.pidKd.setValue(0.024)
                widget.save_preferences()
            finally:
                widget.close()
                self._app.processEvents()

        self.assertEqual(len(saved_payloads), 1)
        saved = saved_payloads[0]
        local_row = saved["control"]["pidProfiles"]["local-mock"]["2"]
        usb_row = saved["control"]["pidProfiles"]["usb"]["2"]
        self.assertAlmostEqual(local_row["kp"], 0.22, places=6)
        self.assertAlmostEqual(local_row["ki"], 0.023, places=6)
        self.assertAlmostEqual(local_row["kd"], 0.024, places=6)
        self.assertAlmostEqual(usb_row["kp"], 0.7, places=6)
        self.assertAlmostEqual(usb_row["ki"], 0.08, places=6)
        self.assertAlmostEqual(usb_row["kd"], 0.09, places=6)

    def test_unsaved_pid_edits_are_preserved_when_switching_fan_speeds(self):
        base = app_config.normalize_config(app_config.DEFAULT_CONFIG)
        base = app_config.set_pid_for_backend_speed(base, "local-mock", 1, 0.11, 0.012, 0.015)
        base = app_config.set_pid_for_backend_speed(base, "local-mock", 2, 0.21, 0.022, 0.025)

        widget = PreferencesTab(config=base, runtime_backend="local-mock")
        try:
            idx1 = widget.pidFanSpeedSelect.findData(1)
            idx2 = widget.pidFanSpeedSelect.findData(2)
            widget.pidFanSpeedSelect.setCurrentIndex(idx1)
            widget.pidKp.setValue(0.314)
            widget.pidFanSpeedSelect.setCurrentIndex(idx2)
            widget.pidFanSpeedSelect.setCurrentIndex(idx1)

            self.assertAlmostEqual(widget.pidKp.value(), 0.314, places=6)
        finally:
            widget.close()
            self._app.processEvents()

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
                widget.restoreDefaultsButton.click()
                self._app.processEvents()

            self.assertEqual(widget.refreshIntervalMs.value(), app_config.DEFAULT_CONFIG["ui"]["refreshIntervalMs"])
            self.assertAlmostEqual(widget.pidKp.value(), 0.5, places=4)

            widget.expertModeEnabled.setChecked(True)
            widget._expert_warning_ack = True
            with patch("PyQt5.QtWidgets.QMessageBox.question", return_value=QtWidgets.QMessageBox.Yes):
                widget.tabs.setCurrentIndex(1)
                widget.restoreDefaultsButton.click()
                self._app.processEvents()

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
                widget.revertChangesButton.click()
                self._app.processEvents()

            self.assertEqual(widget.refreshIntervalMs.value(), app_config.DEFAULT_CONFIG["ui"]["refreshIntervalMs"])
            self.assertAlmostEqual(widget.pidKp.value(), 0.5, places=4)

            widget.expertModeEnabled.setChecked(True)
            widget._expert_warning_ack = True
            with patch("PyQt5.QtWidgets.QMessageBox.question", return_value=QtWidgets.QMessageBox.Yes):
                widget.tabs.setCurrentIndex(1)
                widget.revertChangesButton.click()
                self._app.processEvents()

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
                widget.revertChangesButton.click()
                self._app.processEvents()
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
        widget = PreferencesTab(config=app_config.DEFAULT_CONFIG, compact_ui=True, runtime_backend="local-mock")
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
        widget = PreferencesTab(config=app_config.DEFAULT_CONFIG, compact_ui=True, runtime_backend="local-mock")
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
            self.assertAlmostEqual(widget.pidKp.step_small(), PreferencesUI.PID_STEP_SMALL, places=6)
            self.assertAlmostEqual(widget.pidKp.step_large(), PreferencesUI.PID_STEP_LARGE, places=6)
            self.assertAlmostEqual(widget.pidKi.step_small(), PreferencesUI.PID_STEP_SMALL, places=6)
            self.assertAlmostEqual(widget.pidKi.step_large(), PreferencesUI.PID_STEP_LARGE, places=6)
            self.assertAlmostEqual(widget.pidKd.step_small(), PreferencesUI.PID_STEP_SMALL, places=6)
            self.assertAlmostEqual(widget.pidKd.step_large(), PreferencesUI.PID_STEP_LARGE, places=6)
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

        widget = PreferencesTab(config=app_config.DEFAULT_CONFIG, roaster=DummyRoaster(), runtime_backend="local-mock")
        try:
            widget.expertModeEnabled.setChecked(True)
            widget._expert_warning_ack = True
            widget.tabs.setCurrentIndex(1)

            with patch("PyQt5.QtWidgets.QMessageBox.question", return_value=QtWidgets.QMessageBox.Yes):
                widget.autotuneButton.click()
                self._app.processEvents()

            deadline = QtCore.QTime.currentTime().addMSecs(2000)
            while widget._autotune_worker is not None and QtCore.QTime.currentTime() < deadline:
                self._app.processEvents()

            self.assertIsNone(widget._autotune_worker)
            self.assertEqual(widget.statusLabel.text(), PreferencesUI.STATUS_AUTOTUNE_COMPLETE_AND_SAVED)
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

        widget = PreferencesTab(config=app_config.DEFAULT_CONFIG, roaster=SlowRoaster(), runtime_backend="local-mock")
        try:
            widget.expertModeEnabled.setChecked(True)
            widget._expert_warning_ack = True
            widget.tabs.setCurrentIndex(1)

            with patch("PyQt5.QtWidgets.QMessageBox.question", return_value=QtWidgets.QMessageBox.Yes):
                widget.autotuneButton.click()
                self._app.processEvents()

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
            runtime_backend="local-mock",
        )
        try:
            with patch("PyQt5.QtWidgets.QMessageBox.question", return_value=QtWidgets.QMessageBox.Yes):
                widget.autotuneButton.click()
                self._app.processEvents()

            self.assertEqual(len(hook_calls), 1)
            self.assertIsNone(widget._autotune_worker)
            self.assertEqual(widget.statusLabel.text(), PreferencesUI.STATUS_AUTOTUNE_CANCELED)
        finally:
            widget.close()
            self._app.processEvents()


if __name__ == "__main__":
    unittest.main()

