from PyQt5 import QtCore
from PyQt5 import QtWidgets

from openroast import app_config
from openroast.temperature import (
    RECIPE_UNIT_CELSIUS,
    RECIPE_UNIT_FAHRENHEIT,
    RECIPE_UNIT_KELVIN,
    TEMP_UNIT_C,
    TEMP_UNIT_F,
    TEMP_UNIT_K,
    celsius_to_temperature_delta_unit,
    celsius_to_temperature_unit,
    normalize_temperature_unit,
    temperature_delta_to_celsius,
    temperature_to_celsius,
    temperature_unit_symbol_to_display,
)


class PreferencesTab(QtWidgets.QWidget):
    LEFT_COLUMN_MAX_WIDTH = 520
    RIGHT_COLUMN_MAX_WIDTH = 420
    TAB_BG_COLOR = "#444952"
    TAB_BORDER_COLOR = "#23252a"
    TAB_TEXT_COLOR = "#cfd6e0"
    TAB_SELECTED_TEXT_COLOR = "#ffffff"

    def __init__(self, config, on_save=None):
        super().__init__()
        self._on_save = on_save
        self._config = app_config.normalize_config(config)
        self._saved_form_state = None
        self._expert_warning_ack = False
        self._tab_change_guard = False
        self._suppress_heater_cutoff_prompt = False
        self._active_display_unit = TEMP_UNIT_C
        self._unit_options = [
            (RECIPE_UNIT_CELSIUS, TEMP_UNIT_C),
            (RECIPE_UNIT_FAHRENHEIT, TEMP_UNIT_F),
            (RECIPE_UNIT_KELVIN, TEMP_UNIT_K),
        ]
        self._build_ui()
        self._load_from_config(self._config)
        self._wire_change_signals()
        self._mark_saved_state()

    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setStyleSheet(
            "QTabWidget::pane {"
            f"background-color: {self.TAB_BG_COLOR};"
            f"border: 1px solid {self.TAB_BORDER_COLOR};"
            "}"
            "QTabBar::tab {"
            f"background: #2e3138; color: {self.TAB_TEXT_COLOR};"
            "padding: 6px 12px;"
            "}"
            "QTabBar::tab:selected {"
            f"background: {self.TAB_BG_COLOR}; color: {self.TAB_SELECTED_TEXT_COLOR};"
            "}"
        )
        self.tabs.addTab(self._create_user_preferences_page(), "User preferences")
        self.tabs.addTab(self._create_expert_preferences_page(), "Expert options")

        controls = QtWidgets.QWidget()
        controls_layout = QtWidgets.QHBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(6)

        self.revertChangesButton = QtWidgets.QPushButton("REVERT CHANGES")
        self.revertChangesButton.setObjectName("smallButtonAlt")
        self.revertChangesButton.clicked.connect(self._on_revert_changes_clicked)
        controls_layout.addWidget(self.revertChangesButton)

        self.restoreDefaultsButton = QtWidgets.QPushButton("RESTORE DEFAULTS")
        self.restoreDefaultsButton.setObjectName("smallButtonAlt")
        self.restoreDefaultsButton.clicked.connect(self._on_restore_defaults_clicked)
        controls_layout.addWidget(self.restoreDefaultsButton)

        self.saveButton = QtWidgets.QPushButton("SAVE")
        self.saveButton.setObjectName("smallButton")
        self.saveButton.clicked.connect(self.save_preferences)
        controls_layout.addWidget(self.saveButton)

        self.tabs.setCornerWidget(controls, QtCore.Qt.TopRightCorner)
        root.addWidget(self.tabs)

        self.configPathLabel = QtWidgets.QLabel(f"Config file: {app_config.get_config_path()}")
        self.configPathLabel.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        root.addWidget(self.configPathLabel)

        self.statusLabel = QtWidgets.QLabel("")
        root.addWidget(self.statusLabel)

    def _set_expert_tab_visible(self, visible):
        tab_bar = self.tabs.tabBar()
        is_visible = bool(visible)
        if hasattr(tab_bar, "setTabVisible"):
            tab_bar.setTabVisible(1, is_visible)
        else:
            self.tabs.setTabEnabled(1, is_visible)
        if not is_visible and self.tabs.currentIndex() == 1:
            self.tabs.setCurrentIndex(0)

    def _create_user_preferences_page(self):
        page = QtWidgets.QWidget()
        page_layout = QtWidgets.QHBoxLayout(page)
        page_layout.setContentsMargins(4, 4, 4, 4)

        left_column = QtWidgets.QWidget()
        left_column.setMaximumWidth(self.LEFT_COLUMN_MAX_WIDTH)
        left_layout = QtWidgets.QVBoxLayout(left_column)

        right_column = QtWidgets.QWidget()
        right_column.setMaximumWidth(self.RIGHT_COLUMN_MAX_WIDTH)
        right_layout = QtWidgets.QVBoxLayout(right_column)

        form = QtWidgets.QFormLayout()
        form.setLabelAlignment(QtCore.Qt.AlignLeft)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)

        form_right = QtWidgets.QFormLayout()
        form_right.setLabelAlignment(QtCore.Qt.AlignLeft)
        form_right.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)

        self.temperatureUnitSelect = QtWidgets.QComboBox()
        self.temperatureUnitSelect.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        for label, unit in self._unit_options:
            self.temperatureUnitSelect.addItem(label, unit)

        self.backendSelect = QtWidgets.QComboBox()
        self.backendSelect.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        for backend in app_config.VALID_BACKENDS:
            self.backendSelect.addItem(backend)

        self.compactUiDefault = QtWidgets.QCheckBox()
        self.fullscreenDefault = QtWidgets.QCheckBox()
        self.expertModeEnabled = QtWidgets.QCheckBox()

        self.refreshIntervalMs = QtWidgets.QSpinBox()
        self.refreshIntervalMs.setRange(
            app_config.MIN_REFRESH_INTERVAL_MS,
            app_config.MAX_REFRESH_INTERVAL_MS,
        )
        self.refreshIntervalMs.setSuffix(" ms")

        self.plotYAxisHeadroomC = QtWidgets.QDoubleSpinBox()
        self.plotYAxisHeadroomC.setRange(
            app_config.MIN_Y_AXIS_HEADROOM_C,
            app_config.MAX_Y_AXIS_HEADROOM_C,
        )
        self.plotYAxisHeadroomC.setSingleStep(0.5)
        self.plotYAxisHeadroomC.setSuffix(" C")

        self.plotYAxisStepC = QtWidgets.QDoubleSpinBox()
        self.plotYAxisStepC.setRange(
            app_config.MIN_Y_AXIS_STEP_C,
            app_config.MAX_Y_AXIS_STEP_C,
        )
        self.plotYAxisStepC.setSingleStep(0.5)
        self.plotYAxisStepC.setSuffix(" C")

        self.plotShowGrid = QtWidgets.QCheckBox()

        self.plotLineWidth = QtWidgets.QDoubleSpinBox()
        self.plotLineWidth.setRange(
            app_config.MIN_PLOT_LINE_WIDTH,
            app_config.MAX_PLOT_LINE_WIDTH,
        )
        self.plotLineWidth.setSingleStep(0.5)

        self.confirmOnStop = QtWidgets.QCheckBox()
        self.confirmOnClear = QtWidgets.QCheckBox()

        form.addRow("Display temperature unit:", self.temperatureUnitSelect)
        form.addRow("Default backend:", self.backendSelect)
        form.addRow("Enable compact UI by default:", self.compactUiDefault)
        form.addRow("Start in fullscreen:", self.fullscreenDefault)
        form.addRow("Enable expert options:", self.expertModeEnabled)
        form.addRow("UI refresh interval:", self.refreshIntervalMs)

        form_right.addRow("Plot y-axis headroom:", self.plotYAxisHeadroomC)
        form_right.addRow("Plot y-axis step:", self.plotYAxisStepC)
        form_right.addRow("Show plot grid:", self.plotShowGrid)
        form_right.addRow("Plot line width:", self.plotLineWidth)
        form_right.addRow("Confirm on STOP:", self.confirmOnStop)
        form_right.addRow("Confirm on RESET:", self.confirmOnClear)

        left_layout.addLayout(form)
        left_layout.addStretch(1)
        right_layout.addLayout(form_right)
        right_layout.addStretch(1)

        page_layout.addWidget(left_column, 0)
        page_layout.addWidget(right_column, 0)
        page_layout.addStretch(1)
        return page

    def _create_expert_preferences_page(self):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)

        left_column = QtWidgets.QWidget()
        left_column.setMaximumWidth(self.LEFT_COLUMN_MAX_WIDTH)
        left_layout = QtWidgets.QVBoxLayout(left_column)

        right_column = QtWidgets.QWidget()
        right_column.setMaximumWidth(self.RIGHT_COLUMN_MAX_WIDTH)
        right_layout = QtWidgets.QVBoxLayout(right_column)

        control_form = QtWidgets.QFormLayout()
        control_form.setLabelAlignment(QtCore.Qt.AlignLeft)
        control_form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)

        safety_form = QtWidgets.QFormLayout()
        safety_form.setLabelAlignment(QtCore.Qt.AlignLeft)
        safety_form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)

        self.pidKp = QtWidgets.QDoubleSpinBox()
        self.pidKp.setDecimals(4)
        self.pidKp.setRange(app_config.MIN_PID_KP, app_config.MAX_PID_KP)
        self.pidKp.setSingleStep(0.001)

        self.pidKi = QtWidgets.QDoubleSpinBox()
        self.pidKi.setDecimals(4)
        self.pidKi.setRange(app_config.MIN_PID_KI, app_config.MAX_PID_KI)
        self.pidKi.setSingleStep(0.001)

        self.pidKd = QtWidgets.QDoubleSpinBox()
        self.pidKd.setDecimals(4)
        self.pidKd.setRange(app_config.MIN_PID_KD, app_config.MAX_PID_KD)
        self.pidKd.setSingleStep(0.001)

        self.pwmCycleSeconds = QtWidgets.QDoubleSpinBox()
        self.pwmCycleSeconds.setDecimals(2)
        self.pwmCycleSeconds.setRange(
            app_config.MIN_PWM_CYCLE_SECONDS,
            app_config.MAX_PWM_CYCLE_SECONDS,
        )
        self.pwmCycleSeconds.setSingleStep(0.1)
        self.pwmCycleSeconds.setSuffix(" s")

        self.samplePeriodSeconds = QtWidgets.QDoubleSpinBox()
        self.samplePeriodSeconds.setDecimals(2)
        self.samplePeriodSeconds.setRange(
            app_config.MIN_SAMPLE_PERIOD_SECONDS,
            app_config.MAX_SAMPLE_PERIOD_SECONDS,
        )
        self.samplePeriodSeconds.setSingleStep(0.05)
        self.samplePeriodSeconds.setSuffix(" s")

        self.safetyMaxTempC = QtWidgets.QDoubleSpinBox()
        self.safetyMaxTempC.setDecimals(1)
        self.safetyMaxTempC.setRange(
            app_config.MIN_SAFETY_MAX_TEMP_C,
            app_config.MAX_SAFETY_MAX_TEMP_C,
        )
        self.safetyMaxTempC.setSingleStep(1.0)
        self.safetyMaxTempC.setSuffix(" C")

        self.heaterCutoffEnabled = QtWidgets.QCheckBox()

        control_form.addRow("PID Kp:", self.pidKp)
        control_form.addRow("PID Ki:", self.pidKi)
        control_form.addRow("PID Kd:", self.pidKd)
        control_form.addRow("PWM cycle period:", self.pwmCycleSeconds)
        control_form.addRow("Control sample period:", self.samplePeriodSeconds)

        safety_form.addRow("Max safe temperature:", self.safetyMaxTempC)
        safety_form.addRow("Enable heater over-temp cutoff:", self.heaterCutoffEnabled)

        left_layout.addLayout(control_form)
        left_layout.addStretch(1)
        right_layout.addLayout(safety_form)
        right_layout.addStretch(1)

        layout.addWidget(left_column, 0)
        layout.addWidget(right_column, 0)
        layout.addStretch(1)
        return page

    def _load_from_config(self, config):
        self._load_user_tab_from_config(config)
        self._load_expert_tab_from_config(config)

    def _load_user_tab_from_config(self, config):
        unit = normalize_temperature_unit(
            config["display"].get("temperatureUnitDefault"),
            default=TEMP_UNIT_C,
        )
        index = self.temperatureUnitSelect.findData(unit)
        self.temperatureUnitSelect.setCurrentIndex(max(index, 0))

        backend = config["app"].get("backendDefault", "usb")
        idx_backend = self.backendSelect.findText(backend)
        self.backendSelect.setCurrentIndex(max(idx_backend, 0))

        self.compactUiDefault.setChecked(bool(config["ui"].get("compactModeDefault", False)))
        self.fullscreenDefault.setChecked(bool(config["ui"].get("fullscreenOnStart", False)))
        self.expertModeEnabled.setChecked(bool(config["ui"].get("expertModeEnabled", False)))
        self.refreshIntervalMs.setValue(int(config["ui"].get("refreshIntervalMs", 1000)))

        self._set_temperature_field_unit(unit, convert_existing=False)
        self.plotYAxisHeadroomC.setValue(
            celsius_to_temperature_delta_unit(app_config.get_plot_y_axis_headroom_c(config), unit)
        )
        self.plotYAxisStepC.setValue(
            celsius_to_temperature_delta_unit(app_config.get_plot_y_axis_step_c(config), unit)
        )
        self.plotShowGrid.setChecked(bool(config["plot"].get("showGrid", True)))
        self.plotLineWidth.setValue(float(config["plot"].get("lineWidth", 3.0)))

        self.confirmOnStop.setChecked(bool(config["roast"].get("confirmOnStop", False)))
        self.confirmOnClear.setChecked(bool(config["roast"].get("confirmOnClear", False)))

    def _load_expert_tab_from_config(self, config):
        unit = normalize_temperature_unit(
            config["display"].get("temperatureUnitDefault"),
            default=TEMP_UNIT_C,
        )

        self.pidKp.setValue(float(config["control"]["pid"].get("kp", 0.108)))
        self.pidKi.setValue(float(config["control"]["pid"].get("ki", 0.0135)))
        self.pidKd.setValue(float(config["control"]["pid"].get("kd", 0.018)))
        self.pwmCycleSeconds.setValue(float(config["control"].get("pwmCycleSeconds", 1.0)))
        self.samplePeriodSeconds.setValue(float(config["control"].get("samplePeriodSeconds", 0.5)))
        self.safetyMaxTempC.setValue(celsius_to_temperature_unit(app_config.get_safety_max_temp_c(config), unit))
        self._suppress_heater_cutoff_prompt = True
        self.heaterCutoffEnabled.setChecked(bool(config["safety"].get("heaterCutoffEnabled", True)))
        self._suppress_heater_cutoff_prompt = False
        self._set_expert_tab_visible(self.expertModeEnabled.isChecked())

    def _wire_change_signals(self):
        self.temperatureUnitSelect.currentIndexChanged.connect(self._on_display_unit_changed)
        self.temperatureUnitSelect.currentIndexChanged.connect(self._on_form_modified)
        self.backendSelect.currentIndexChanged.connect(self._on_form_modified)
        self.compactUiDefault.toggled.connect(self._on_form_modified)
        self.fullscreenDefault.toggled.connect(self._on_form_modified)
        self.expertModeEnabled.toggled.connect(self._on_expert_mode_toggled)
        self.refreshIntervalMs.valueChanged.connect(self._on_form_modified)
        self.plotYAxisHeadroomC.valueChanged.connect(self._on_form_modified)
        self.plotYAxisStepC.valueChanged.connect(self._on_form_modified)
        self.plotShowGrid.toggled.connect(self._on_form_modified)
        self.plotLineWidth.valueChanged.connect(self._on_form_modified)
        self.confirmOnStop.toggled.connect(self._on_form_modified)
        self.confirmOnClear.toggled.connect(self._on_form_modified)
        self.pidKp.valueChanged.connect(self._on_form_modified)
        self.pidKi.valueChanged.connect(self._on_form_modified)
        self.pidKd.valueChanged.connect(self._on_form_modified)
        self.pwmCycleSeconds.valueChanged.connect(self._on_form_modified)
        self.samplePeriodSeconds.valueChanged.connect(self._on_form_modified)
        self.safetyMaxTempC.valueChanged.connect(self._on_form_modified)
        self.heaterCutoffEnabled.toggled.connect(self._on_heater_cutoff_toggled)
        self.heaterCutoffEnabled.toggled.connect(self._on_form_modified)
        self.tabs.currentChanged.connect(self._on_tab_changed)

    def _set_temperature_field_unit(self, unit, *, convert_existing):
        unit = normalize_temperature_unit(unit, default=TEMP_UNIT_C)
        previous_unit = self._active_display_unit

        if convert_existing:
            headroom_c = temperature_delta_to_celsius(self.plotYAxisHeadroomC.value(), previous_unit)
            step_c = temperature_delta_to_celsius(self.plotYAxisStepC.value(), previous_unit)
            max_temp_c = temperature_to_celsius(self.safetyMaxTempC.value(), previous_unit)

        degree_unit = temperature_unit_symbol_to_display(unit)

        self.plotYAxisHeadroomC.setSuffix(f" {degree_unit}")
        self.plotYAxisHeadroomC.setRange(
            celsius_to_temperature_delta_unit(app_config.MIN_Y_AXIS_HEADROOM_C, unit),
            celsius_to_temperature_delta_unit(app_config.MAX_Y_AXIS_HEADROOM_C, unit),
        )

        self.plotYAxisStepC.setSuffix(f" {degree_unit}")
        self.plotYAxisStepC.setRange(
            celsius_to_temperature_delta_unit(app_config.MIN_Y_AXIS_STEP_C, unit),
            celsius_to_temperature_delta_unit(app_config.MAX_Y_AXIS_STEP_C, unit),
        )

        self.safetyMaxTempC.setSuffix(f" {degree_unit}")
        self.safetyMaxTempC.setRange(
            celsius_to_temperature_unit(app_config.MIN_SAFETY_MAX_TEMP_C, unit),
            celsius_to_temperature_unit(app_config.MAX_SAFETY_MAX_TEMP_C, unit),
        )

        if convert_existing:
            self.plotYAxisHeadroomC.setValue(celsius_to_temperature_delta_unit(headroom_c, unit))
            self.plotYAxisStepC.setValue(celsius_to_temperature_delta_unit(step_c, unit))
            self.safetyMaxTempC.setValue(celsius_to_temperature_unit(max_temp_c, unit))

        self._active_display_unit = unit

    def _on_display_unit_changed(self, _index):
        self._set_temperature_field_unit(self.temperatureUnitSelect.currentData(), convert_existing=True)

    def _on_expert_mode_toggled(self, enabled):
        self._set_expert_tab_visible(bool(enabled))
        self._on_form_modified()

    def _on_heater_cutoff_toggled(self, enabled):
        if self._suppress_heater_cutoff_prompt:
            return
        if enabled:
            return
        answer = QtWidgets.QMessageBox.question(
            self,
            "Disable safety cutoff?",
            "Disabling over-temperature cutoff can damage equipment and increase fire risk. Continue?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if answer != QtWidgets.QMessageBox.Yes:
            blocker = QtCore.QSignalBlocker(self.heaterCutoffEnabled)
            self.heaterCutoffEnabled.setChecked(True)
            del blocker

    def _on_revert_changes_clicked(self):
        is_expert_tab = self.tabs.currentIndex() == 1
        if is_expert_tab:
            title = "Revert expert changes"
            message = "Revert unsaved expert options to last saved values?"
        else:
            title = "Revert user changes"
            message = "Revert unsaved user preferences to last saved values?"

        answer = QtWidgets.QMessageBox.question(
            self,
            title,
            message,
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return

        if is_expert_tab:
            self._load_expert_tab_from_config(self._config)
        else:
            self._load_user_tab_from_config(self._config)

        self._on_form_modified()

    def _on_tab_changed(self, index):
        if self._tab_change_guard or index != 1:
            return
        if not self.expertModeEnabled.isChecked():
            self._tab_change_guard = True
            self.tabs.setCurrentIndex(0)
            self._tab_change_guard = False
            return
        if self._expert_warning_ack:
            return

        answer = QtWidgets.QMessageBox.question(
            self,
            "Expert options warning",
            "These parameters affect control and safety behavior. "
            "Incorrect values can cause unstable heating or unsafe operation. "
            "Only change them if you understand the risks. Continue?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if answer == QtWidgets.QMessageBox.Yes:
            self._expert_warning_ack = True
            return

        self._tab_change_guard = True
        self.tabs.setCurrentIndex(0)
        self._tab_change_guard = False

    def _on_restore_defaults_clicked(self):
        is_expert_tab = self.tabs.currentIndex() == 1
        if is_expert_tab:
            title = "Restore expert defaults"
            message = "Reset all expert options to their defaults?"
        else:
            title = "Restore user defaults"
            message = "Reset all user preferences to their defaults?"

        answer = QtWidgets.QMessageBox.question(
            self,
            title,
            message,
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return

        defaults = app_config.DEFAULT_CONFIG
        if is_expert_tab:
            self._restore_expert_defaults(defaults)
        else:
            self._restore_user_defaults(defaults)
        self.statusLabel.setText("Unsaved changes")

    def _restore_user_defaults(self, defaults):
        unit = normalize_temperature_unit(
            defaults["display"].get("temperatureUnitDefault"),
            default=TEMP_UNIT_C,
        )
        idx = self.temperatureUnitSelect.findData(unit)
        self.temperatureUnitSelect.setCurrentIndex(max(idx, 0))

        backend = defaults["app"].get("backendDefault", "usb")
        idx_backend = self.backendSelect.findText(backend)
        self.backendSelect.setCurrentIndex(max(idx_backend, 0))

        self.compactUiDefault.setChecked(bool(defaults["ui"].get("compactModeDefault", False)))
        self.fullscreenDefault.setChecked(bool(defaults["ui"].get("fullscreenOnStart", False)))
        self.expertModeEnabled.setChecked(bool(defaults["ui"].get("expertModeEnabled", False)))
        self.refreshIntervalMs.setValue(int(defaults["ui"].get("refreshIntervalMs", 1000)))

        normalized_defaults = app_config.normalize_config(defaults)
        self.plotYAxisHeadroomC.setValue(
            celsius_to_temperature_delta_unit(
                app_config.get_plot_y_axis_headroom_c(normalized_defaults),
                unit,
            )
        )
        self.plotYAxisStepC.setValue(
            celsius_to_temperature_delta_unit(
                app_config.get_plot_y_axis_step_c(normalized_defaults),
                unit,
            )
        )
        self.plotShowGrid.setChecked(bool(defaults["plot"].get("showGrid", True)))
        self.plotLineWidth.setValue(float(defaults["plot"].get("lineWidth", 3.0)))

        self.confirmOnStop.setChecked(bool(defaults["roast"].get("confirmOnStop", False)))
        self.confirmOnClear.setChecked(bool(defaults["roast"].get("confirmOnClear", False)))

    def _restore_expert_defaults(self, defaults):
        unit = normalize_temperature_unit(self.temperatureUnitSelect.currentData(), default=TEMP_UNIT_C)
        normalized_defaults = app_config.normalize_config(defaults)
        self.pidKp.setValue(float(defaults["control"]["pid"].get("kp", 0.108)))
        self.pidKi.setValue(float(defaults["control"]["pid"].get("ki", 0.0135)))
        self.pidKd.setValue(float(defaults["control"]["pid"].get("kd", 0.018)))
        self.pwmCycleSeconds.setValue(float(defaults["control"].get("pwmCycleSeconds", 1.0)))
        self.samplePeriodSeconds.setValue(float(defaults["control"].get("samplePeriodSeconds", 0.5)))
        self.safetyMaxTempC.setValue(
            celsius_to_temperature_unit(
                app_config.get_safety_max_temp_c(normalized_defaults),
                unit,
            )
        )
        self.heaterCutoffEnabled.setChecked(bool(defaults["safety"].get("heaterCutoffEnabled", True)))

    def _current_form_state(self):
        return {
            "unit": self.temperatureUnitSelect.currentData(),
            "backend": self.backendSelect.currentText(),
            "compact": self.compactUiDefault.isChecked(),
            "fullscreen": self.fullscreenDefault.isChecked(),
            "expert_enabled": self.expertModeEnabled.isChecked(),
            "refresh_ms": self.refreshIntervalMs.value(),
            "y_headroom": float(self.plotYAxisHeadroomC.value()),
            "y_step": float(self.plotYAxisStepC.value()),
            "show_grid": self.plotShowGrid.isChecked(),
            "line_width": float(self.plotLineWidth.value()),
            "confirm_stop": self.confirmOnStop.isChecked(),
            "confirm_clear": self.confirmOnClear.isChecked(),
            "pid_kp": float(self.pidKp.value()),
            "pid_ki": float(self.pidKi.value()),
            "pid_kd": float(self.pidKd.value()),
            "pwm_cycle_s": float(self.pwmCycleSeconds.value()),
            "sample_period_s": float(self.samplePeriodSeconds.value()),
            "safety_max_temp_c": float(self.safetyMaxTempC.value()),
            "heater_cutoff": self.heaterCutoffEnabled.isChecked(),
        }

    def _mark_saved_state(self):
        self._saved_form_state = self._current_form_state()

    def _on_form_modified(self, *_args):
        if self._saved_form_state is None:
            return
        if self._current_form_state() != self._saved_form_state:
            self.statusLabel.setText("Unsaved changes")
        else:
            self.statusLabel.setText("")

    def save_preferences(self):
        selected_unit = self.temperatureUnitSelect.currentData()
        selected_backend = self.backendSelect.currentText()

        y_axis_headroom_c = temperature_delta_to_celsius(self.plotYAxisHeadroomC.value(), selected_unit)
        y_axis_step_c = temperature_delta_to_celsius(self.plotYAxisStepC.value(), selected_unit)
        safety_max_temp_c = temperature_to_celsius(self.safetyMaxTempC.value(), selected_unit)

        updated = app_config.update_config(
            self._config,
            display_unit=selected_unit,
            compact_mode=self.compactUiDefault.isChecked(),
            fullscreen=self.fullscreenDefault.isChecked(),
            expert_mode_enabled=self.expertModeEnabled.isChecked(),
            backend=selected_backend,
            refresh_interval_ms=self.refreshIntervalMs.value(),
            y_axis_headroom_c=y_axis_headroom_c,
            y_axis_step_c=y_axis_step_c,
            plot_show_grid=self.plotShowGrid.isChecked(),
            plot_line_width=self.plotLineWidth.value(),
            confirm_on_stop=self.confirmOnStop.isChecked(),
            confirm_on_clear=self.confirmOnClear.isChecked(),
            pid_kp=self.pidKp.value(),
            pid_ki=self.pidKi.value(),
            pid_kd=self.pidKd.value(),
            pwm_cycle_seconds=self.pwmCycleSeconds.value(),
            sample_period_seconds=self.samplePeriodSeconds.value(),
            safety_max_temp_c=safety_max_temp_c,
            heater_cutoff_enabled=self.heaterCutoffEnabled.isChecked(),
        )
        saved = app_config.save_config(updated)
        self._config = saved

        if callable(self._on_save):
            self._on_save(saved)

        self._mark_saved_state()
        self.statusLabel.setText("Preferences saved. Some changes apply on next start.")

