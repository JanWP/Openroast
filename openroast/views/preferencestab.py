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
    normalize_temperature_unit,
)


class PreferencesTab(QtWidgets.QWidget):
    LEFT_COLUMN_MAX_WIDTH = 520
    TAB_BG_COLOR = "#444952"
    TAB_BORDER_COLOR = "#23252a"
    TAB_TEXT_COLOR = "#cfd6e0"
    TAB_SELECTED_TEXT_COLOR = "#ffffff"

    def __init__(self, config, on_save=None):
        super().__init__()
        self._on_save = on_save
        self._config = app_config.normalize_config(config)
        self._saved_form_state = None
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
        self.expertPage = QtWidgets.QWidget()
        self.tabs.addTab(self.expertPage, "Expert options")
        # Expert page exists for future use but stays hidden in V1.
        self._set_expert_tab_visible(False)

        self.saveButton = QtWidgets.QPushButton("SAVE")
        self.saveButton.setObjectName("smallButton")
        self.saveButton.clicked.connect(self.save_preferences)
        self.tabs.setCornerWidget(self.saveButton, QtCore.Qt.TopRightCorner)
        root.addWidget(self.tabs)

        self.configPathLabel = QtWidgets.QLabel(f"Config file: {app_config.get_config_path()}")
        self.configPathLabel.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        root.addWidget(self.configPathLabel)

        self.statusLabel = QtWidgets.QLabel("")
        root.addWidget(self.statusLabel)

    def _set_expert_tab_visible(self, visible):
        tab_bar = self.tabs.tabBar()
        if hasattr(tab_bar, "setTabVisible"):
            tab_bar.setTabVisible(1, bool(visible))
        else:
            self.tabs.setTabEnabled(1, bool(visible))

    def _create_user_preferences_page(self):
        page = QtWidgets.QWidget()
        page_layout = QtWidgets.QHBoxLayout(page)
        page_layout.setContentsMargins(4, 4, 4, 4)

        left_column = QtWidgets.QWidget()
        left_column.setMaximumWidth(self.LEFT_COLUMN_MAX_WIDTH)
        left_layout = QtWidgets.QVBoxLayout(left_column)

        form = QtWidgets.QFormLayout()
        form.setLabelAlignment(QtCore.Qt.AlignLeft)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)

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
        self.autoConnectDefault = QtWidgets.QCheckBox()

        form.addRow("Display temperature unit:", self.temperatureUnitSelect)
        form.addRow("Default backend:", self.backendSelect)
        form.addRow("Enable compact UI by default:", self.compactUiDefault)
        form.addRow("Start in fullscreen:", self.fullscreenDefault)
        form.addRow("Auto-connect roaster on startup:", self.autoConnectDefault)

        left_layout.addLayout(form)
        left_layout.addStretch(1)

        page_layout.addWidget(left_column, 0)
        page_layout.addStretch(1)
        return page

    def _load_from_config(self, config):
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
        self.autoConnectDefault.setChecked(bool(config["app"].get("autoConnectOnStart", True)))

    def _wire_change_signals(self):
        self.temperatureUnitSelect.currentIndexChanged.connect(self._on_form_modified)
        self.backendSelect.currentIndexChanged.connect(self._on_form_modified)
        self.compactUiDefault.toggled.connect(self._on_form_modified)
        self.fullscreenDefault.toggled.connect(self._on_form_modified)
        self.autoConnectDefault.toggled.connect(self._on_form_modified)

    def _current_form_state(self):
        return {
            "unit": self.temperatureUnitSelect.currentData(),
            "backend": self.backendSelect.currentText(),
            "compact": self.compactUiDefault.isChecked(),
            "fullscreen": self.fullscreenDefault.isChecked(),
            "auto_connect": self.autoConnectDefault.isChecked(),
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

        updated = app_config.update_config(
            self._config,
            display_unit=selected_unit,
            compact_mode=self.compactUiDefault.isChecked(),
            fullscreen=self.fullscreenDefault.isChecked(),
            backend=selected_backend,
            auto_connect=self.autoConnectDefault.isChecked(),
        )
        saved = app_config.save_config(updated)
        self._config = saved

        if callable(self._on_save):
            self._on_save(saved)

        self._mark_saved_state()
        self.statusLabel.setText("Preferences saved. Some changes apply on next start.")

