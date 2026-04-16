import copy

from PyQt5 import QtCore
from PyQt5 import QtWidgets

from openroast import app_config
from openroast.controllers.autotune import autotune_pid_table_for_backend
from openroast.views import customqtwidgets
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
from openroast.views.ui_constants import PreferencesUI, SharedButtons, SharedColors, SharedTabStyle


class PreferencesTab(QtWidgets.QWidget):
    LEFT_COLUMN_MAX_WIDTH = PreferencesUI.LEFT_COLUMN_MAX_WIDTH
    RIGHT_COLUMN_MAX_WIDTH = PreferencesUI.RIGHT_COLUMN_MAX_WIDTH
    TAB_BG_COLOR = SharedColors.SURFACE_TAB_PANE
    TAB_BORDER_COLOR = SharedColors.BORDER_PANEL
    TAB_INACTIVE_BG_COLOR = SharedColors.SURFACE_TAB_INACTIVE
    TAB_TEXT_COLOR = SharedColors.FOREGROUND_TEXT_MUTED
    TAB_SELECTED_TEXT_COLOR = SharedColors.FOREGROUND_TEXT
    TAB_PADDING_V = SharedTabStyle.TAB_PADDING_V
    TAB_PADDING_H = SharedTabStyle.TAB_PADDING_H
    CORNER_BUTTON_HEIGHT = SharedButtons.CORNER_BUTTON_HEIGHT
    ROOT_MARGIN = PreferencesUI.ROOT_MARGIN
    ROOT_SPACING = PreferencesUI.ROOT_SPACING
    PAGE_MARGIN = PreferencesUI.PAGE_MARGIN
    CORNER_SPACING = PreferencesUI.CORNER_SPACING
    DIALOG_AUTOTUNE_TITLE = PreferencesUI.DIALOG_AUTOTUNE_TITLE
    DIALOG_AUTOTUNE_MESSAGE = PreferencesUI.DIALOG_AUTOTUNE_MESSAGE
    DIALOG_DISABLE_CUTOFF_TITLE = PreferencesUI.DIALOG_DISABLE_CUTOFF_TITLE
    DIALOG_DISABLE_CUTOFF_MESSAGE = PreferencesUI.DIALOG_DISABLE_CUTOFF_MESSAGE
    DIALOG_REVERT_EXPERT_TITLE = PreferencesUI.DIALOG_REVERT_EXPERT_TITLE
    DIALOG_REVERT_EXPERT_MESSAGE = PreferencesUI.DIALOG_REVERT_EXPERT_MESSAGE
    DIALOG_REVERT_USER_TITLE = PreferencesUI.DIALOG_REVERT_USER_TITLE
    DIALOG_REVERT_USER_MESSAGE = PreferencesUI.DIALOG_REVERT_USER_MESSAGE
    DIALOG_EXPERT_WARNING_TITLE = PreferencesUI.DIALOG_EXPERT_WARNING_TITLE
    DIALOG_EXPERT_WARNING_MESSAGE = PreferencesUI.DIALOG_EXPERT_WARNING_MESSAGE
    DIALOG_RESTORE_EXPERT_TITLE = PreferencesUI.DIALOG_RESTORE_EXPERT_TITLE
    DIALOG_RESTORE_EXPERT_MESSAGE = PreferencesUI.DIALOG_RESTORE_EXPERT_MESSAGE
    DIALOG_RESTORE_USER_TITLE = PreferencesUI.DIALOG_RESTORE_USER_TITLE
    DIALOG_RESTORE_USER_MESSAGE = PreferencesUI.DIALOG_RESTORE_USER_MESSAGE
    NUMERIC_EDITOR_OBJECT_NAME = PreferencesUI.NUMERIC_EDITOR_OBJECT_NAME
    NUMERIC_EDITOR_COMPACT_OBJECT_NAME = PreferencesUI.NUMERIC_EDITOR_COMPACT_OBJECT_NAME
    NUMERIC_EDITOR_HEIGHT_DEFAULT = PreferencesUI.NUMERIC_EDITOR_HEIGHT_DEFAULT
    NUMERIC_EDITOR_HEIGHT_COMPACT = PreferencesUI.NUMERIC_EDITOR_HEIGHT_COMPACT
    REFRESH_INTERVAL_STEP_SMALL_MS = PreferencesUI.REFRESH_INTERVAL_STEP_SMALL_MS
    REFRESH_INTERVAL_STEP_LARGE_MS = PreferencesUI.REFRESH_INTERVAL_STEP_LARGE_MS
    PID_STEP_SMALL = PreferencesUI.PID_STEP_SMALL
    PID_STEP_LARGE = PreferencesUI.PID_STEP_LARGE

    class _AutotuneWorker(QtCore.QThread):
        resultReady = QtCore.pyqtSignal(object, object)

        def __init__(self, autotune_callable, parent=None):
            super().__init__(parent)
            self._autotune_callable = autotune_callable

        def run(self):
            try:
                result = self._autotune_callable()
            except Exception as exc:  # pragma: no cover - worker failure path
                self.resultReady.emit(None, str(exc))
            else:
                self.resultReady.emit(result, None)

    def __init__(self, config, on_save=None, roaster=None, pre_autotune_hook=None, compact_ui=False,
                 runtime_backend=None):
        super().__init__()
        self._on_save = on_save
        self._roaster = roaster
        self._pre_autotune_hook = pre_autotune_hook
        self._config = app_config.normalize_config(config)
        backend_default = self._config.get("app", {}).get("backendDefault", "usb")
        runtime_backend = runtime_backend if runtime_backend is not None else backend_default
        self._runtime_backend = (
            runtime_backend if runtime_backend in app_config.VALID_BACKENDS else backend_default
        )
        self._selected_pid_fan_speed = 1
        self._pid_draft_profiles = {}
        self._saved_form_state = None
        self._expert_warning_ack = False
        self._tab_change_guard = False
        self._suppress_heater_cutoff_prompt = False
        self._active_display_unit = TEMP_UNIT_C
        self._autotune_worker = None
        self._compact_ui = bool(compact_ui)
        self._unit_options = [
            (RECIPE_UNIT_CELSIUS, TEMP_UNIT_C),
            (RECIPE_UNIT_FAHRENHEIT, TEMP_UNIT_F),
            (RECIPE_UNIT_KELVIN, TEMP_UNIT_K),
        ]
        self._build_ui()
        self._load_from_config(self._config)
        self._wire_change_signals()
        self._mark_saved_state()

    @property
    def runtime_backend(self):
        """Effective backend in use for this running app session."""
        return self._runtime_backend

    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(self.ROOT_MARGIN, self.ROOT_MARGIN, self.ROOT_MARGIN, self.ROOT_MARGIN)
        root.setSpacing(self.ROOT_SPACING)

        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setStyleSheet(
            "QTabWidget::pane {"
            f"background-color: {self.TAB_BG_COLOR};"
            f"border: 1px solid {self.TAB_BORDER_COLOR};"
            "}"
            "QTabBar::tab {"
            f"background: {self.TAB_INACTIVE_BG_COLOR}; color: {self.TAB_TEXT_COLOR};"
            f"padding: {self.TAB_PADDING_V}px {self.TAB_PADDING_H}px;"
            "}"
            "QTabBar::tab:selected {"
            f"background: {self.TAB_BG_COLOR}; color: {self.TAB_SELECTED_TEXT_COLOR};"
            "}"
        )
        self.tabs.addTab(self._create_user_preferences_page(), PreferencesUI.TAB_TITLE_USER)
        self.tabs.addTab(self._create_expert_preferences_page(), PreferencesUI.TAB_TITLE_EXPERT)

        controls = QtWidgets.QWidget()
        controls_layout = QtWidgets.QHBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(self.CORNER_SPACING)

        self.revertChangesButton = QtWidgets.QPushButton(PreferencesUI.BUTTON_REVERT)
        self.revertChangesButton.setObjectName("smallButtonAlt")
        self.revertChangesButton.setFixedHeight(self.CORNER_BUTTON_HEIGHT)
        self.revertChangesButton.clicked.connect(self._on_revert_changes_clicked)
        controls_layout.addWidget(self.revertChangesButton)

        self.restoreDefaultsButton = QtWidgets.QPushButton(PreferencesUI.BUTTON_RESTORE_DEFAULTS)
        self.restoreDefaultsButton.setObjectName("smallButtonAlt")
        self.restoreDefaultsButton.setFixedHeight(self.CORNER_BUTTON_HEIGHT)
        self.restoreDefaultsButton.clicked.connect(self._on_restore_defaults_clicked)
        controls_layout.addWidget(self.restoreDefaultsButton)

        self.saveButton = QtWidgets.QPushButton(PreferencesUI.BUTTON_SAVE)
        self.saveButton.setObjectName("smallButton")
        self.saveButton.setFixedHeight(self.CORNER_BUTTON_HEIGHT)
        self.saveButton.clicked.connect(self.save_preferences)
        controls_layout.addWidget(self.saveButton)

        self.tabs.setCornerWidget(controls, QtCore.Qt.TopRightCorner)
        root.addWidget(self.tabs)

        self.configPathLabel = QtWidgets.QLabel(
            PreferencesUI.LABEL_CONFIG_PATH_TEMPLATE.format(path=app_config.get_config_path())
        )
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
        page_layout.setContentsMargins(self.PAGE_MARGIN, self.PAGE_MARGIN, self.PAGE_MARGIN, self.PAGE_MARGIN)

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

        self.refreshIntervalMs = self._create_numeric_editor(
            customqtwidgets.ValueSpec(
                kind="int",
                minimum=app_config.MIN_REFRESH_INTERVAL_MS,
                maximum=app_config.MAX_REFRESH_INTERVAL_MS,
                decimals=0,
                step_small=self.REFRESH_INTERVAL_STEP_SMALL_MS,
                step_large=self.REFRESH_INTERVAL_STEP_LARGE_MS,
                suffix=" ms",
            )
        )

        self.plotYAxisHeadroomC = self._create_numeric_editor(
            customqtwidgets.ValueSpec(
                kind="float",
                minimum=app_config.MIN_Y_AXIS_HEADROOM_C,
                maximum=app_config.MAX_Y_AXIS_HEADROOM_C,
                decimals=2,
                step_small=0.5,
                step_large=5.0,
                suffix=" C",
            )
        )

        self.plotYAxisStepC = self._create_numeric_editor(
            customqtwidgets.ValueSpec(
                kind="float",
                minimum=app_config.MIN_Y_AXIS_STEP_C,
                maximum=app_config.MAX_Y_AXIS_STEP_C,
                decimals=2,
                step_small=0.5,
                step_large=5.0,
                suffix=" C",
            )
        )

        self.plotShowGrid = QtWidgets.QCheckBox()

        self.plotLineWidth = self._create_numeric_editor(
            customqtwidgets.ValueSpec(
                kind="float",
                minimum=app_config.MIN_PLOT_LINE_WIDTH,
                maximum=app_config.MAX_PLOT_LINE_WIDTH,
                decimals=2,
                step_small=0.5,
                step_large=2.0,
            )
        )

        self.confirmOnStop = QtWidgets.QCheckBox()
        self.confirmOnClear = QtWidgets.QCheckBox()

        form.addRow(PreferencesUI.FORM_LABEL_DISPLAY_TEMPERATURE_UNIT, self.temperatureUnitSelect)
        form.addRow(PreferencesUI.FORM_LABEL_DEFAULT_BACKEND, self.backendSelect)
        form.addRow(PreferencesUI.FORM_LABEL_ENABLE_COMPACT_UI_DEFAULT, self.compactUiDefault)
        form.addRow(PreferencesUI.FORM_LABEL_START_FULLSCREEN, self.fullscreenDefault)
        form.addRow(PreferencesUI.FORM_LABEL_ENABLE_EXPERT_OPTIONS, self.expertModeEnabled)
        form.addRow(PreferencesUI.FORM_LABEL_UI_REFRESH_INTERVAL, self.refreshIntervalMs)

        form_right.addRow(PreferencesUI.FORM_LABEL_PLOT_Y_AXIS_HEADROOM, self.plotYAxisHeadroomC)
        form_right.addRow(PreferencesUI.FORM_LABEL_PLOT_Y_AXIS_STEP, self.plotYAxisStepC)
        form_right.addRow(PreferencesUI.FORM_LABEL_SHOW_PLOT_GRID, self.plotShowGrid)
        form_right.addRow(PreferencesUI.FORM_LABEL_PLOT_LINE_WIDTH, self.plotLineWidth)
        form_right.addRow(PreferencesUI.FORM_LABEL_CONFIRM_ON_STOP, self.confirmOnStop)
        form_right.addRow(PreferencesUI.FORM_LABEL_CONFIRM_ON_RESET, self.confirmOnClear)

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
        layout.setContentsMargins(self.PAGE_MARGIN, self.PAGE_MARGIN, self.PAGE_MARGIN, self.PAGE_MARGIN)

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

        self.pidKp = self._create_numeric_editor(
            customqtwidgets.ValueSpec(
                kind="float",
                minimum=app_config.MIN_PID_KP,
                maximum=app_config.MAX_PID_KP,
                decimals=4,
                step_small=self.PID_STEP_SMALL,
                step_large=self.PID_STEP_LARGE,
            )
        )

        self.pidKi = self._create_numeric_editor(
            customqtwidgets.ValueSpec(
                kind="float",
                minimum=app_config.MIN_PID_KI,
                maximum=app_config.MAX_PID_KI,
                decimals=4,
                step_small=self.PID_STEP_SMALL,
                step_large=self.PID_STEP_LARGE,
            )
        )

        self.pidKd = self._create_numeric_editor(
            customqtwidgets.ValueSpec(
                kind="float",
                minimum=app_config.MIN_PID_KD,
                maximum=app_config.MAX_PID_KD,
                decimals=4,
                step_small=self.PID_STEP_SMALL,
                step_large=self.PID_STEP_LARGE,
            )
        )

        self.pwmCycleSeconds = self._create_numeric_editor(
            customqtwidgets.ValueSpec(
                kind="float",
                minimum=app_config.MIN_PWM_CYCLE_SECONDS,
                maximum=app_config.MAX_PWM_CYCLE_SECONDS,
                decimals=2,
                step_small=0.1,
                step_large=1.0,
                suffix=" s",
            )
        )

        self.samplePeriodSeconds = self._create_numeric_editor(
            customqtwidgets.ValueSpec(
                kind="float",
                minimum=app_config.MIN_SAMPLE_PERIOD_SECONDS,
                maximum=app_config.MAX_SAMPLE_PERIOD_SECONDS,
                decimals=2,
                step_small=0.05,
                step_large=0.5,
                suffix=" s",
            )
        )

        self.safetyMaxTempC = self._create_numeric_editor(
            customqtwidgets.ValueSpec(
                kind="float",
                minimum=app_config.MIN_SAFETY_MAX_TEMP_C,
                maximum=app_config.MAX_SAFETY_MAX_TEMP_C,
                decimals=1,
                step_small=1.0,
                step_large=10.0,
                suffix=" C",
            )
        )

        self.heaterCutoffEnabled = QtWidgets.QCheckBox()

        self.pidFanSpeedSelect = QtWidgets.QComboBox()
        self.pidFanSpeedSelect.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        control_form.addRow(PreferencesUI.FORM_LABEL_PID_FAN_SPEED, self.pidFanSpeedSelect)
        control_form.addRow(PreferencesUI.FORM_LABEL_PID_KP, self.pidKp)
        control_form.addRow(PreferencesUI.FORM_LABEL_PID_KI, self.pidKi)
        control_form.addRow(PreferencesUI.FORM_LABEL_PID_KD, self.pidKd)
        self.autotuneButton = QtWidgets.QPushButton(PreferencesUI.BUTTON_AUTOTUNE)
        self.autotuneButton.setObjectName("smallButtonAlt")
        control_form.addRow("", self.autotuneButton)
        control_form.addRow(PreferencesUI.FORM_LABEL_PWM_CYCLE_PERIOD, self.pwmCycleSeconds)
        control_form.addRow(PreferencesUI.FORM_LABEL_CONTROL_SAMPLE_PERIOD, self.samplePeriodSeconds)

        safety_form.addRow(PreferencesUI.FORM_LABEL_MAX_SAFE_TEMPERATURE, self.safetyMaxTempC)
        safety_form.addRow(PreferencesUI.FORM_LABEL_ENABLE_HEATER_CUTOFF, self.heaterCutoffEnabled)

        left_layout.addLayout(control_form)
        left_layout.addStretch(1)
        right_layout.addLayout(safety_form)
        right_layout.addStretch(1)

        layout.addWidget(left_column, 0)
        layout.addWidget(right_column, 0)
        layout.addStretch(1)
        self._update_pid_editor_visibility()
        return page

    def _pid_controls_supported(self):
        return self._runtime_backend in ("local", "local-mock")

    def _runtime_fan_max_for_pid(self):
        if not self._pid_controls_supported():
            return 0
        runtime_max = getattr(self._roaster, "max_fan_speed", app_config.FAN_SPEED_MAX)
        return max(1, int(runtime_max))

    def _populate_pid_fan_selector(self):
        max_fan = self._runtime_fan_max_for_pid()
        blocker = QtCore.QSignalBlocker(self.pidFanSpeedSelect)
        self.pidFanSpeedSelect.clear()
        if max_fan > 0:
            for fan_speed in range(1, max_fan + 1):
                self.pidFanSpeedSelect.addItem(str(fan_speed), fan_speed)
            idx = self.pidFanSpeedSelect.findData(self._selected_pid_fan_speed)
            if idx < 0:
                idx = 0
            self.pidFanSpeedSelect.setCurrentIndex(idx)
            selected = self.pidFanSpeedSelect.currentData()
            self._selected_pid_fan_speed = int(selected) if selected is not None else 1
        del blocker

    def _reset_pid_draft_from_config(self, config):
        normalized = app_config.normalize_config(config)
        self._pid_draft_profiles = copy.deepcopy(
            normalized.get("control", {}).get("pidProfiles", {})
        )

    def _get_pid_value_from_draft(self, fan_speed):
        temp_cfg = app_config.normalize_config(self._config)
        temp_cfg["control"]["pidProfiles"] = copy.deepcopy(self._pid_draft_profiles)
        return app_config.get_pid_for_backend_speed(
            temp_cfg,
            self._runtime_backend,
            fan_speed,
        )

    def _store_current_pid_editor_values_to_draft(self):
        if not self._pid_controls_supported():
            return
        current_fan = int(max(1, self._selected_pid_fan_speed))
        temp_cfg = app_config.normalize_config(self._config)
        temp_cfg["control"]["pidProfiles"] = copy.deepcopy(self._pid_draft_profiles)
        updated = app_config.set_pid_for_backend_speed(
            temp_cfg,
            self._runtime_backend,
            current_fan,
            self.pidKp.value(),
            self.pidKi.value(),
            self.pidKd.value(),
        )
        self._pid_draft_profiles = copy.deepcopy(updated["control"]["pidProfiles"])

    def _update_pid_editor_visibility(self):
        supported = self._pid_controls_supported()
        widgets = [
            self.pidFanSpeedSelect,
            self.pidKp,
            self.pidKi,
            self.pidKd,
            self.autotuneButton,
        ]
        for widget in widgets:
            label = None
            if hasattr(self, "pidKp"):
                label = self._find_form_label_for_widget(widget)
            if label is not None:
                label.setVisible(supported)
            widget.setVisible(supported)
            widget.setEnabled(supported)

    def _find_form_label_for_widget(self, field_widget):
        parent = field_widget.parentWidget()
        if parent is None:
            return None
        for form in parent.findChildren(QtWidgets.QFormLayout):
            label = form.labelForField(field_widget)
            if label is not None:
                return label
        return None

    def _create_numeric_editor(self, spec):
        editor = customqtwidgets.AdaptiveValueEditor(
            spec,
            compact=self._compact_ui,
            parent=self,
        )
        self._configure_numeric_editor(editor)
        return editor

    def _configure_numeric_editor(self, editor):
        editor.setEditorObjectName(
            self.NUMERIC_EDITOR_COMPACT_OBJECT_NAME
            if self._compact_ui
            else self.NUMERIC_EDITOR_OBJECT_NAME
        )
        editor.set_uniform_height(
            self.NUMERIC_EDITOR_HEIGHT_COMPACT
            if self._compact_ui
            else self.NUMERIC_EDITOR_HEIGHT_DEFAULT
        )

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

        self._reset_pid_draft_from_config(config)
        self._populate_pid_fan_selector()
        self._update_pid_editor_visibility()

        pid_values = self._get_pid_value_from_draft(self._selected_pid_fan_speed)
        self.pidKp.setValue(float(pid_values["kp"]))
        self.pidKi.setValue(float(pid_values["ki"]))
        self.pidKd.setValue(float(pid_values["kd"]))
        self.pwmCycleSeconds.setValue(float(config["control"].get("pwmCycleSeconds", 1.0)))
        self.samplePeriodSeconds.setValue(float(config["control"].get("samplePeriodSeconds", 0.5)))
        self.safetyMaxTempC.setValue(celsius_to_temperature_unit(app_config.get_safety_max_temp_c(config), unit))
        self._suppress_heater_cutoff_prompt = True
        self.heaterCutoffEnabled.setChecked(bool(config["safety"].get("heaterCutoffEnabled", True)))
        self._suppress_heater_cutoff_prompt = False
        self._set_expert_tab_visible(self.expertModeEnabled.isChecked())

        if not self._pid_controls_supported():
            self.statusLabel.setText(PreferencesUI.STATUS_PID_NOT_AVAILABLE)

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
        self.pidFanSpeedSelect.currentIndexChanged.connect(self._on_pid_fan_speed_changed)
        self.pwmCycleSeconds.valueChanged.connect(self._on_form_modified)
        self.samplePeriodSeconds.valueChanged.connect(self._on_form_modified)
        self.autotuneButton.clicked.connect(self._on_autotune_clicked)
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

    def _on_pid_fan_speed_changed(self, _index):
        self._store_current_pid_editor_values_to_draft()
        selected = self.pidFanSpeedSelect.currentData()
        if selected is None:
            return
        self._selected_pid_fan_speed = int(selected)
        pid_values = self._get_pid_value_from_draft(self._selected_pid_fan_speed)
        blockers = [
            QtCore.QSignalBlocker(self.pidKp),
            QtCore.QSignalBlocker(self.pidKi),
            QtCore.QSignalBlocker(self.pidKd),
        ]
        self.pidKp.setValue(float(pid_values["kp"]))
        self.pidKi.setValue(float(pid_values["ki"]))
        self.pidKd.setValue(float(pid_values["kd"]))
        for blocker in blockers:
            del blocker
        self._on_form_modified()

    def _on_expert_mode_toggled(self, enabled):
        self._set_expert_tab_visible(bool(enabled))
        self._on_form_modified()

    def _on_autotune_clicked(self):
        if self._autotune_worker is not None:
            return
        if self._roaster is None:
            self.statusLabel.setText(PreferencesUI.STATUS_AUTOTUNE_UNAVAILABLE)
            return

        if callable(self._pre_autotune_hook):
            ready = bool(self._pre_autotune_hook())
            if not ready:
                self.statusLabel.setText(PreferencesUI.STATUS_AUTOTUNE_CANCELED)
                return

        answer = QtWidgets.QMessageBox.question(
            self,
            self.DIALOG_AUTOTUNE_TITLE,
            self.DIALOG_AUTOTUNE_MESSAGE,
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return

        self._store_current_pid_editor_values_to_draft()
        self.autotuneButton.setEnabled(False)
        self.saveButton.setEnabled(False)
        self.statusLabel.setText(PreferencesUI.STATUS_AUTOTUNE_RUNNING)

        fan_speeds = None
        max_fan = self._runtime_fan_max_for_pid()
        if max_fan > 0:
            fan_speeds = list(range(1, max_fan + 1))

        self._autotune_worker = self._AutotuneWorker(
            lambda: autotune_pid_table_for_backend(self._roaster, fan_speeds=fan_speeds),
            parent=self,
        )
        self._autotune_worker.resultReady.connect(self._on_autotune_finished)
        self._autotune_worker.finished.connect(self._on_autotune_worker_finished)
        self._autotune_worker.start()

    def _merge_autotune_results_into_pid_draft(self, results_by_fan):
        if not self._pid_controls_supported() or not isinstance(results_by_fan, dict):
            return 0

        merged = 0
        temp_cfg = app_config.normalize_config(self._config)
        temp_cfg["control"]["pidProfiles"] = copy.deepcopy(self._pid_draft_profiles)

        for fan_key, values in results_by_fan.items():
            try:
                fan_speed = int(fan_key)
            except (TypeError, ValueError):
                continue
            if not isinstance(values, dict):
                continue
            if not all(k in values for k in ("kp", "ki", "kd")):
                continue

            temp_cfg = app_config.set_pid_for_backend_speed(
                temp_cfg,
                self._runtime_backend,
                fan_speed,
                values["kp"],
                values["ki"],
                values["kd"],
            )
            merged += 1

        self._pid_draft_profiles = copy.deepcopy(temp_cfg["control"]["pidProfiles"])

        # Refresh currently selected row in editors so UI reflects merged data.
        pid_values = self._get_pid_value_from_draft(self._selected_pid_fan_speed)
        self.pidKp.setValue(float(pid_values["kp"]))
        self.pidKi.setValue(float(pid_values["ki"]))
        self.pidKd.setValue(float(pid_values["kd"]))
        return merged

    def _on_autotune_finished(self, result, error_text):
        self.autotuneButton.setEnabled(True)
        self.saveButton.setEnabled(True)

        if error_text:
            self.statusLabel.setText(PreferencesUI.STATUS_AUTOTUNE_FAILED_TEMPLATE.format(error=error_text))
            return

        if not isinstance(result, dict):
            self.statusLabel.setText(
                PreferencesUI.STATUS_AUTOTUNE_FAILED_TEMPLATE.format(error="invalid autotune result")
            )
            return

        merged = self._merge_autotune_results_into_pid_draft(result.get("results", {}))
        if merged > 0:
            self.save_preferences()

        if result.get("ok", False):
            self.statusLabel.setText(PreferencesUI.STATUS_AUTOTUNE_COMPLETE_AND_SAVED)
        else:
            failed_speed = result.get("failed_speed")
            fail_reason = result.get("error") or "unknown error"
            self.statusLabel.setText(
                PreferencesUI.STATUS_AUTOTUNE_FAILED_TEMPLATE.format(
                    error=f"failed at fan {failed_speed} after saving {merged} row(s): {fail_reason}"
                )
            )

    def _on_autotune_worker_finished(self):
        worker = self._autotune_worker
        if worker is None:
            return
        worker.deleteLater()
        self._autotune_worker = None

    def _cleanup_autotune_worker(self, wait_ms=2000):
        worker = self._autotune_worker
        if worker is None:
            return
        if worker.isRunning():
            worker.wait(int(wait_ms))
        worker.deleteLater()
        self._autotune_worker = None

    def prepare_shutdown(self):
        """Best-effort cleanup used by app shutdown hooks."""
        self._cleanup_autotune_worker(wait_ms=2000)

    def closeEvent(self, event):
        self._cleanup_autotune_worker(wait_ms=2000)
        super().closeEvent(event)

    def _on_heater_cutoff_toggled(self, enabled):
        if self._suppress_heater_cutoff_prompt:
            return
        if enabled:
            return
        answer = QtWidgets.QMessageBox.question(
            self,
            self.DIALOG_DISABLE_CUTOFF_TITLE,
            self.DIALOG_DISABLE_CUTOFF_MESSAGE,
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
            title = self.DIALOG_REVERT_EXPERT_TITLE
            message = self.DIALOG_REVERT_EXPERT_MESSAGE
        else:
            title = self.DIALOG_REVERT_USER_TITLE
            message = self.DIALOG_REVERT_USER_MESSAGE

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
            self.DIALOG_EXPERT_WARNING_TITLE,
            self.DIALOG_EXPERT_WARNING_MESSAGE,
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
            title = self.DIALOG_RESTORE_EXPERT_TITLE
            message = self.DIALOG_RESTORE_EXPERT_MESSAGE
        else:
            title = self.DIALOG_RESTORE_USER_TITLE
            message = self.DIALOG_RESTORE_USER_MESSAGE

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
        self.statusLabel.setText(PreferencesUI.STATUS_UNSAVED_CHANGES)

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
        pid_values = app_config.get_pid_for_backend_speed(
            defaults,
            self._runtime_backend,
            self._selected_pid_fan_speed,
        )
        self.pidKp.setValue(float(pid_values["kp"]))
        self.pidKi.setValue(float(pid_values["ki"]))
        self.pidKd.setValue(float(pid_values["kd"]))
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
            "pid_fan_speed": int(self._selected_pid_fan_speed),
            "runtime_backend": self._runtime_backend,
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
            self.statusLabel.setText(PreferencesUI.STATUS_UNSAVED_CHANGES)
        else:
            self.statusLabel.setText("")

    def save_preferences(self):
        self._store_current_pid_editor_values_to_draft()
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
            pwm_cycle_seconds=self.pwmCycleSeconds.value(),
            sample_period_seconds=self.samplePeriodSeconds.value(),
            safety_max_temp_c=safety_max_temp_c,
            heater_cutoff_enabled=self.heaterCutoffEnabled.isChecked(),
        )
        if self._pid_controls_supported():
            updated["control"]["pidProfiles"] = copy.deepcopy(self._pid_draft_profiles)
        saved = app_config.save_config(updated)
        self._config = saved
        self._reset_pid_draft_from_config(saved)

        if callable(self._on_save):
            self._on_save(saved)

        self._mark_saved_state()
        self.statusLabel.setText(PreferencesUI.STATUS_PREFERENCES_SAVED)
