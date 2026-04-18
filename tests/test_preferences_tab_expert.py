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

    def test_control_fan_selector_uses_runtime_backend_capabilities(self):
        class DummyRoaster:
            max_fan_speed = 5

        widget = PreferencesTab(
            config=app_config.DEFAULT_CONFIG,
            runtime_backend="local-mock",
            roaster=DummyRoaster(),
        )
        try:
            self.assertEqual(widget.controlFanSpeedSelect.count(), 5)
            self.assertEqual(widget.controlFanSpeedSelect.itemData(0), 1)
            self.assertEqual(widget.controlFanSpeedSelect.itemData(4), 5)
        finally:
            widget.close()
            self._app.processEvents()

    def test_save_preferences_updates_only_runtime_backend_selected_fan_row(self):
        base = app_config.normalize_config(app_config.DEFAULT_CONFIG)
        base = app_config.set_plant_for_backend_speed(base, "local-mock", 2, K=1.11, tau_s=22.0, L=0.4)
        base = app_config.set_plant_for_backend_speed(base, "usb", 2, K=1.7, tau_s=18.0, L=0.3)

        saved_payloads = []

        def _capture_save(cfg):
            normalized = app_config.normalize_config(cfg)
            saved_payloads.append(normalized)
            return normalized

        with patch("openroast.views.preferencestab.app_config.save_config", side_effect=_capture_save):
            widget = PreferencesTab(config=base, runtime_backend="local-mock")
            try:
                idx = widget.controlFanSpeedSelect.findData(2)
                widget.controlFanSpeedSelect.setCurrentIndex(idx)
                widget.plantK.setValue(1.22)
                widget.plantTauS.setValue(33.0)
                widget.plantL.setValue(0.62)
                widget.save_preferences()
            finally:
                widget.close()
                self._app.processEvents()

        self.assertEqual(len(saved_payloads), 1)
        saved = saved_payloads[0]
        local_row = saved["control"]["plantProfiles"]["local-mock"]["2"]
        usb_row = saved["control"]["plantProfiles"]["usb"]["2"]
        self.assertAlmostEqual(local_row["K"], 1.22, places=6)
        self.assertAlmostEqual(local_row["tau_s"], 33.0, places=6)
        self.assertAlmostEqual(local_row["L"], 0.62, places=6)
        self.assertAlmostEqual(usb_row["K"], 1.7, places=6)
        self.assertAlmostEqual(usb_row["tau_s"], 18.0, places=6)
        self.assertAlmostEqual(usb_row["L"], 0.3, places=6)

    def test_unsaved_plant_edits_are_preserved_when_switching_fan_speeds(self):
        base = app_config.normalize_config(app_config.DEFAULT_CONFIG)
        base = app_config.set_plant_for_backend_speed(base, "local-mock", 1, K=1.11, tau_s=22.0, L=0.4)
        base = app_config.set_plant_for_backend_speed(base, "local-mock", 2, K=1.21, tau_s=20.0, L=0.6)

        widget = PreferencesTab(config=base, runtime_backend="local-mock")
        try:
            idx1 = widget.controlFanSpeedSelect.findData(1)
            idx2 = widget.controlFanSpeedSelect.findData(2)
            widget.controlFanSpeedSelect.setCurrentIndex(idx1)
            widget.plantK.setValue(3.14)
            widget.controlFanSpeedSelect.setCurrentIndex(idx2)
            widget.controlFanSpeedSelect.setCurrentIndex(idx1)

            self.assertAlmostEqual(widget.plantK.value(), 3.14, places=6)
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
            widget.plantK.setValue(5.0)

            with patch("PyQt5.QtWidgets.QMessageBox.question", return_value=QtWidgets.QMessageBox.Yes):
                widget.tabs.setCurrentIndex(0)
                widget.restoreDefaultsButton.click()
                self._app.processEvents()

            self.assertEqual(widget.refreshIntervalMs.value(), app_config.DEFAULT_CONFIG["ui"]["refreshIntervalMs"])
            self.assertAlmostEqual(widget.plantK.value(), 5.0, places=4)

            widget.expertModeEnabled.setChecked(True)
            widget._expert_warning_ack = True
            with patch("PyQt5.QtWidgets.QMessageBox.question", return_value=QtWidgets.QMessageBox.Yes):
                widget.tabs.setCurrentIndex(1)
                widget.restoreDefaultsButton.click()
                self._app.processEvents()

            self.assertAlmostEqual(
                widget.plantK.value(),
                1.0,
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
            widget.plantK.setValue(5.0)

            with patch("PyQt5.QtWidgets.QMessageBox.question", return_value=QtWidgets.QMessageBox.Yes):
                widget.tabs.setCurrentIndex(0)
                widget.revertChangesButton.click()
                self._app.processEvents()

            self.assertEqual(widget.refreshIntervalMs.value(), app_config.DEFAULT_CONFIG["ui"]["refreshIntervalMs"])
            self.assertAlmostEqual(widget.plantK.value(), 5.0, places=4)

            widget.expertModeEnabled.setChecked(True)
            widget._expert_warning_ack = True
            with patch("PyQt5.QtWidgets.QMessageBox.question", return_value=QtWidgets.QMessageBox.Yes):
                widget.tabs.setCurrentIndex(1)
                widget.revertChangesButton.click()
                self._app.processEvents()

            self.assertAlmostEqual(
                widget.plantK.value(),
                1.0,
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
            self.assertEqual(widget.plantK.editorObjectName(), expected)
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

    def test_plant_editors_use_requested_step_sizes(self):
        widget = self._build_widget()
        try:
            self.assertAlmostEqual(widget.plantK.step_small(), PreferencesUI.CONTROL_STEP_SMALL, places=6)
            self.assertAlmostEqual(widget.plantK.step_large(), PreferencesUI.CONTROL_STEP_LARGE, places=6)
            self.assertAlmostEqual(widget.plantTauS.step_small(), PreferencesUI.CONTROL_STEP_SMALL, places=6)
            self.assertAlmostEqual(widget.plantTauS.step_large(), PreferencesUI.CONTROL_STEP_LARGE, places=6)
            self.assertAlmostEqual(widget.plantL.step_small(), PreferencesUI.CONTROL_STEP_SMALL, places=6)
            self.assertAlmostEqual(widget.plantL.step_large(), PreferencesUI.CONTROL_STEP_LARGE, places=6)
        finally:
            widget.close()
            self._app.processEvents()

    def test_autotune_worker_is_cleaned_up_after_finish(self):
        class DummyRoaster:
            connected = True
            max_fan_speed = 3

            def __init__(self):
                self.fan_speed = 1
                self.calls = []

            def get_roaster_state(self):
                return "idle"

            def reset_simulation_state(self):
                pass

            def autotune_pid(self, **_kwargs):
                self.calls.append(int(self.fan_speed))
                speed = float(self.fan_speed)
                return {
                    "kp": 0.2 + speed,
                    "ki": 0.03 + speed / 10.0,
                    "kd": 0.04 + speed / 10.0,
                    "process_gain": 2.0 + speed / 10.0,
                    "tau_s": 25.0 + speed,
                    "dead_time_s": 0.4 + speed / 10.0,
                }

        roaster = DummyRoaster()
        widget = PreferencesTab(config=app_config.DEFAULT_CONFIG, roaster=roaster, runtime_backend="local-mock")
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
            self.assertEqual(roaster.calls, [1, 2, 3])
            row3 = widget._config["control"]["plantProfiles"]["local-mock"]["3"]
            self.assertIn("K", row3)
            self.assertIn("tau_s", row3)
            self.assertIn("L", row3)
        finally:
            widget.close()
            self._app.processEvents()

    def test_autotune_partial_failure_saves_only_successful_rows(self):
        class FlakyRoaster:
            connected = True
            max_fan_speed = 3

            def __init__(self):
                self.fan_speed = 1

            def get_roaster_state(self):
                return "idle"

            def reset_simulation_state(self):
                pass

            def autotune_pid(self, **_kwargs):
                if int(self.fan_speed) == 2:
                    raise RuntimeError("forced failure")
                speed = float(self.fan_speed)
                return {
                    "kp": 1.0 + speed,
                    "ki": 0.1 + speed / 10.0,
                    "kd": 0.2 + speed / 10.0,
                    "process_gain": 2.0 + speed / 10.0,
                    "tau_s": 25.0 + speed,
                    "dead_time_s": 0.4 + speed / 10.0,
                }

        base = app_config.normalize_config(app_config.DEFAULT_CONFIG)
        base = app_config.set_plant_for_backend_speed(base, "local-mock", 1, K=1.11, tau_s=22.0, L=0.4)
        base = app_config.set_plant_for_backend_speed(base, "local-mock", 2, K=1.21, tau_s=20.0, L=0.6)
        base = app_config.set_plant_for_backend_speed(base, "local-mock", 3, K=1.31, tau_s=18.0, L=0.8)

        saved_payloads = []

        def _capture_save(cfg):
            normalized = app_config.normalize_config(cfg)
            saved_payloads.append(normalized)
            return normalized

        widget = PreferencesTab(config=base, roaster=FlakyRoaster(), runtime_backend="local-mock")
        try:
            widget.expertModeEnabled.setChecked(True)
            widget._expert_warning_ack = True
            widget.tabs.setCurrentIndex(1)

            with patch("openroast.views.preferencestab.app_config.save_config", side_effect=_capture_save), \
                 patch("PyQt5.QtWidgets.QMessageBox.question", return_value=QtWidgets.QMessageBox.Yes):
                widget.autotuneButton.click()
                self._app.processEvents()
                deadline = QtCore.QTime.currentTime().addMSecs(2000)
                while widget._autotune_worker is not None and QtCore.QTime.currentTime() < deadline:
                    self._app.processEvents()

            self.assertEqual(len(saved_payloads), 1)
            saved = saved_payloads[0]
            row1 = saved["control"]["plantProfiles"]["local-mock"]["1"]
            row2 = saved["control"]["plantProfiles"]["local-mock"]["2"]
            row3 = saved["control"]["plantProfiles"]["local-mock"]["3"]

            # Fan 1 tuned and saved.
            self.assertAlmostEqual(row1["K"], 2.1, places=6)
            self.assertIn("K", row1)
            self.assertIn("tau_s", row1)
            self.assertIn("L", row1)
            # Fan 2 failed, fan 3 not run: keep prior values.
            self.assertAlmostEqual(row2["K"], 1.21, places=6)
            self.assertAlmostEqual(row3["K"], 1.31, places=6)
            self.assertIn("failed at fan 2", widget.statusLabel.text())
        finally:
            widget.close()
            self._app.processEvents()

if __name__ == "__main__":
    unittest.main()

