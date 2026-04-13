# -*- coding: utf-8 -*-
# Roastero, released under GPLv3

import os
import errno
import json
import time
import functools

from PyQt5 import QtGui
from PyQt5 import QtCore
from PyQt5 import QtWidgets

import pyqtgraph as pg

from openroast import tools
from openroast import utils as utils
from openroast.controllers.recipe import build_default_recipe, normalize_recipe_for_runtime
from openroast.temperature import (
    DEFAULT_TARGET_TEMPERATURE_C,
    MAX_TEMPERATURE_C,
    MIN_TEMPERATURE_C,
    RECIPE_FORMAT_VERSION,
    RECIPE_UNIT_CELSIUS,
    RECIPE_UNIT_FAHRENHEIT,
    RECIPE_UNIT_KELVIN,
    TEMP_UNIT_C,
    TEMP_UNIT_F,
    TEMP_UNIT_K,
    TEMPERATURE_STEP_C,
    celsius_to_temperature_unit,
            get_default_display_temperature_unit,
    clamp_temperature_c,
    normalize_temperature_unit,
    temperature_to_celsius,
)
from openroast.views import customqtwidgets
from openroast.views.ui_constants import RecipeEditorUI


class _TimeAxis(pg.AxisItem):
    def tickStrings(self, values, scale, spacing):
        _ = scale, spacing
        labels = []
        for value in values:
            total_s = max(0, int(round(value)))
            labels.append(time.strftime("%M:%S", time.gmtime(total_s)))
        return labels


class CompactTempPickerCombo(customqtwidgets.ComboBoxNoWheel):
    """Combo that opens a compact touch picker instead of a long dropdown."""

    def __init__(self, on_pick, *args, **kwargs):
        super(CompactTempPickerCombo, self).__init__(*args, **kwargs)
        self._on_pick = on_pick

    def showPopup(self):
        if callable(self._on_pick):
            self._on_pick()


class CompactDurationEdit(customqtwidgets.TimeEditNoWheel):
    """Time edit that opens a touch picker in compact mode."""

    def __init__(self, on_pick, *args, **kwargs):
        super(CompactDurationEdit, self).__init__(*args, **kwargs)
        self._on_pick = on_pick
        self.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.installEventFilter(self)
        line_edit = self.lineEdit()
        if line_edit is not None:
            line_edit.installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() == QtCore.QEvent.MouseButtonRelease:
            if callable(self._on_pick):
                self._on_pick()
            return True
        return super(CompactDurationEdit, self).eventFilter(watched, event)


class RecipeEditor(QtWidgets.QDialog):
    # Centralized UI constants (kept as class aliases for compatibility/tests).
    WINDOW_MIN_WIDTH = RecipeEditorUI.WINDOW_MIN_WIDTH
    WINDOW_MIN_HEIGHT_COMPACT = RecipeEditorUI.WINDOW_MIN_HEIGHT_COMPACT
    WINDOW_MIN_HEIGHT_DEFAULT = RecipeEditorUI.WINDOW_MIN_HEIGHT_DEFAULT
    WINDOW_RESIZE_WIDTH_DEFAULT = RecipeEditorUI.WINDOW_RESIZE_WIDTH_DEFAULT
    WINDOW_RESIZE_HEIGHT_DEFAULT = RecipeEditorUI.WINDOW_RESIZE_HEIGHT_DEFAULT

    COLUMN_WIDTH_TEMP = RecipeEditorUI.COLUMN_WIDTH_TEMP
    COLUMN_WIDTH_FAN = RecipeEditorUI.COLUMN_WIDTH_FAN
    COLUMN_WIDTH_DURATION_COMPACT = RecipeEditorUI.COLUMN_WIDTH_DURATION_COMPACT
    COLUMN_WIDTH_DURATION_DEFAULT = RecipeEditorUI.COLUMN_WIDTH_DURATION_DEFAULT
    COLUMN_WIDTH_MODIFY_COMPACT = RecipeEditorUI.COLUMN_WIDTH_MODIFY_COMPACT
    COLUMN_WIDTH_MODIFY_DEFAULT = RecipeEditorUI.COLUMN_WIDTH_MODIFY_DEFAULT
    TABLE_MIN_EXTRA_WIDTH = RecipeEditorUI.TABLE_MIN_EXTRA_WIDTH
    TABLE_MIN_WIDTH = RecipeEditorUI.TABLE_MIN_WIDTH
    TABLE_ROW_HEIGHT_COMPACT = RecipeEditorUI.TABLE_ROW_HEIGHT_COMPACT

    TEMP_EDITOR_WIDTH_COMPACT = RecipeEditorUI.TEMP_EDITOR_WIDTH_COMPACT
    TEMP_EDITOR_WIDTH_DEFAULT = RecipeEditorUI.TEMP_EDITOR_WIDTH_DEFAULT
    FAN_EDITOR_WIDTH_COMPACT = RecipeEditorUI.FAN_EDITOR_WIDTH_COMPACT
    FAN_EDITOR_WIDTH_DEFAULT = RecipeEditorUI.FAN_EDITOR_WIDTH_DEFAULT
    TIME_EDITOR_WIDTH_COMPACT = RecipeEditorUI.TIME_EDITOR_WIDTH_COMPACT
    TIME_EDITOR_WIDTH_DEFAULT = RecipeEditorUI.TIME_EDITOR_WIDTH_DEFAULT

    DURATION_STEP_SMALL_S = RecipeEditorUI.DURATION_STEP_SMALL_S
    DURATION_STEP_LARGE_S = RecipeEditorUI.DURATION_STEP_LARGE_S
    DURATION_MAX_S = RecipeEditorUI.DURATION_MAX_S

    COOLING_LABEL = RecipeEditorUI.COOLING_LABEL

    TAB_WIDGET_OBJECT_NAME = RecipeEditorUI.TAB_WIDGET_OBJECT_NAME
    TAB_PAGE_OBJECT_NAME_INFO = RecipeEditorUI.TAB_PAGE_OBJECT_NAME_INFO
    TAB_PAGE_OBJECT_NAME_PROFILE = RecipeEditorUI.TAB_PAGE_OBJECT_NAME_PROFILE
    TAB_TITLE_INFO = RecipeEditorUI.TAB_TITLE_INFO
    TAB_TITLE_PROFILE = RecipeEditorUI.TAB_TITLE_PROFILE

    COLOR_TAB_PANE_BG = RecipeEditorUI.COLOR_TAB_PANE_BG
    COLOR_TAB_PANE_BORDER = RecipeEditorUI.COLOR_TAB_PANE_BORDER
    COLOR_TAB_BG = RecipeEditorUI.COLOR_TAB_BG
    COLOR_TAB_TEXT = RecipeEditorUI.COLOR_TAB_TEXT
    COLOR_TAB_SELECTED_TEXT = RecipeEditorUI.COLOR_TAB_SELECTED_TEXT
    TAB_PADDING_V = RecipeEditorUI.TAB_PADDING_V
    TAB_PADDING_H = RecipeEditorUI.TAB_PADDING_H

    CORNER_BUTTON_HEIGHT = RecipeEditorUI.CORNER_BUTTON_HEIGHT
    CORNER_BUTTON_WIDTH_CLOSE = RecipeEditorUI.CORNER_BUTTON_WIDTH_CLOSE
    CORNER_BUTTON_WIDTH_SAVE = RecipeEditorUI.CORNER_BUTTON_WIDTH_SAVE
    CORNER_BUTTON_WIDTH_SAVE_AS = RecipeEditorUI.CORNER_BUTTON_WIDTH_SAVE_AS

    CURVE_MIN_HEIGHT_COMPACT = RecipeEditorUI.CURVE_MIN_HEIGHT_COMPACT
    CURVE_MIN_HEIGHT_DEFAULT = RecipeEditorUI.CURVE_MIN_HEIGHT_DEFAULT

    TEMP_PICKER_STEP_SMALL = RecipeEditorUI.TEMP_PICKER_STEP_SMALL
    TEMP_PICKER_STEP_LARGE = RecipeEditorUI.TEMP_PICKER_STEP_LARGE

    TAB_INDEX_INFO = RecipeEditorUI.TAB_INDEX_INFO
    TAB_INDEX_PROFILE = RecipeEditorUI.TAB_INDEX_PROFILE

    ROOT_MARGIN = RecipeEditorUI.ROOT_MARGIN
    ROOT_SPACING = RecipeEditorUI.ROOT_SPACING
    PAGE_MARGIN = RecipeEditorUI.PAGE_MARGIN
    PAGE_SPACING = RecipeEditorUI.PAGE_SPACING
    FORM_H_SPACING = RecipeEditorUI.FORM_H_SPACING
    FORM_V_SPACING = RecipeEditorUI.FORM_V_SPACING

    CORNER_BUTTON_TEXT_CLOSE = RecipeEditorUI.CORNER_BUTTON_TEXT_CLOSE
    CORNER_BUTTON_TEXT_SAVE = RecipeEditorUI.CORNER_BUTTON_TEXT_SAVE
    CORNER_BUTTON_TEXT_SAVE_AS = RecipeEditorUI.CORNER_BUTTON_TEXT_SAVE_AS

    PICKER_DIALOG_WIDTH_COMPACT = RecipeEditorUI.PICKER_DIALOG_WIDTH_COMPACT
    PICKER_DIALOG_WIDTH_DEFAULT = RecipeEditorUI.PICKER_DIALOG_WIDTH_DEFAULT
    PICKER_CANCEL_TEXT = RecipeEditorUI.PICKER_CANCEL_TEXT
    PICKER_APPLY_TEXT = RecipeEditorUI.PICKER_APPLY_TEXT

    SPLITTER_LAYOUT_OVERHEAD = RecipeEditorUI.SPLITTER_LAYOUT_OVERHEAD
    SPLITTER_MIN_PLOT_WIDTH = RecipeEditorUI.SPLITTER_MIN_PLOT_WIDTH

    PLOT_BG_COLOR = RecipeEditorUI.PLOT_BG_COLOR
    PLOT_LINE_COLOR = RecipeEditorUI.PLOT_LINE_COLOR
    PLOT_LABEL_COLOR = RecipeEditorUI.PLOT_LABEL_COLOR

    WINDOW_TITLE = RecipeEditorUI.WINDOW_TITLE

    FORM_LABEL_RECIPE_NAME = RecipeEditorUI.FORM_LABEL_RECIPE_NAME
    FORM_LABEL_CREATED_BY = RecipeEditorUI.FORM_LABEL_CREATED_BY
    FORM_LABEL_ROAST_TYPE = RecipeEditorUI.FORM_LABEL_ROAST_TYPE
    FORM_LABEL_BEAN_REGION = RecipeEditorUI.FORM_LABEL_BEAN_REGION
    FORM_LABEL_BEAN_COUNTRY = RecipeEditorUI.FORM_LABEL_BEAN_COUNTRY
    FORM_LABEL_BEAN_LINK = RecipeEditorUI.FORM_LABEL_BEAN_LINK
    FORM_LABEL_BEAN_STORE_NAME = RecipeEditorUI.FORM_LABEL_BEAN_STORE_NAME
    FORM_LABEL_TEMPERATURE_UNIT = RecipeEditorUI.FORM_LABEL_TEMPERATURE_UNIT
    FORM_LABEL_DESCRIPTION = RecipeEditorUI.FORM_LABEL_DESCRIPTION

    SECTION_LABEL_HEATING_CURVE = RecipeEditorUI.SECTION_LABEL_HEATING_CURVE
    SECTION_LABEL_LOADING_CURVE = RecipeEditorUI.SECTION_LABEL_LOADING_CURVE

    TABLE_HEADER_TEMPERATURE_PREFIX = RecipeEditorUI.TABLE_HEADER_TEMPERATURE_PREFIX
    TABLE_HEADER_FAN = RecipeEditorUI.TABLE_HEADER_FAN
    TABLE_HEADER_DURATION = RecipeEditorUI.TABLE_HEADER_DURATION
    TABLE_HEADER_MODIFY = RecipeEditorUI.TABLE_HEADER_MODIFY

    PLOT_AXIS_TIME = RecipeEditorUI.PLOT_AXIS_TIME
    PLOT_AXIS_TEMPERATURE = RecipeEditorUI.PLOT_AXIS_TEMPERATURE

    PICKER_TEMPERATURE_TITLE = RecipeEditorUI.PICKER_TEMPERATURE_TITLE
    PICKER_TEMPERATURE_COOLING_TOGGLE = RecipeEditorUI.PICKER_TEMPERATURE_COOLING_TOGGLE
    PICKER_DURATION_TITLE = RecipeEditorUI.PICKER_DURATION_TITLE

    ALERT_MIN_STEPS_TITLE = RecipeEditorUI.ALERT_MIN_STEPS_TITLE
    ALERT_MIN_STEPS_TEXT = RecipeEditorUI.ALERT_MIN_STEPS_TEXT

    FILE_DIALOG_SAVE_AS_TITLE = RecipeEditorUI.FILE_DIALOG_SAVE_AS_TITLE
    FILE_DIALOG_SAVE_AS_FILTER = RecipeEditorUI.FILE_DIALOG_SAVE_AS_FILTER

    # Match roast window pyqtgraph axis label sizing.
    PLOT_LABEL_STYLE = {'color': PLOT_LABEL_COLOR, 'font-size': '11pt'}

    def __init__(self, recipe_data=None, recipe_path=None, compact_ui=False, fullscreen=False):
        super(RecipeEditor, self).__init__()

        self.compact_ui = bool(compact_ui)
        self.fullscreen = bool(fullscreen)
        self._display_temp_unit = get_default_display_temperature_unit()
        self._selected_recipe_unit_label = RECIPE_UNIT_CELSIUS
        self._updating_steps_table = False
        self._curve_update_pending = False
        self._curve_update_force = False
        self._row_action_icons = None
        self.recipeCurveFigure = None
        self.recipeCurveCanvas = None
        self.recipeCurveAxes = None
        self.recipeCurvePlotWidget = None
        self.recipeCurveCurve = None

        # Define main window for the application.
        self.setWindowTitle(self.WINDOW_TITLE)
        if self.compact_ui:
            self.setMinimumSize(self.WINDOW_MIN_WIDTH, self.WINDOW_MIN_HEIGHT_COMPACT)
            self.resize(self.WINDOW_MIN_WIDTH, self.WINDOW_MIN_HEIGHT_COMPACT)
        else:
            self.setMinimumSize(self.WINDOW_MIN_WIDTH, self.WINDOW_MIN_HEIGHT_DEFAULT)
            self.resize(self.WINDOW_RESIZE_WIDTH_DEFAULT, self.WINDOW_RESIZE_HEIGHT_DEFAULT)
        if self.fullscreen:
            self.setWindowState(self.windowState() | QtCore.Qt.WindowFullScreen)
        self.setContextMenuPolicy(QtCore.Qt.NoContextMenu)

        self.create_ui()

        self.recipe = {}
        self.load_recipe_data(
            recipe_data if recipe_data is not None else build_default_recipe(
                default_display_unit=get_default_display_temperature_unit()
            ),
            recipe_path=recipe_path,
        )
        self.preload_recipe_information()

    def load_recipe_data(self, recipe_data, recipe_path=None):
        """Load recipe dictionary into editor state without reading files."""
        self.recipe = normalize_recipe_for_runtime(
            recipe_data,
            default_source_unit=get_default_display_temperature_unit(),
        )
        self._display_temp_unit = normalize_temperature_unit(
            self.recipe.get("displayTemperatureUnit", self.recipe.get("temperatureUnit")),
            default=get_default_display_temperature_unit(),
        )
        self._selected_recipe_unit_label = {
            TEMP_UNIT_C: RECIPE_UNIT_CELSIUS,
            TEMP_UNIT_F: RECIPE_UNIT_FAHRENHEIT,
            TEMP_UNIT_K: RECIPE_UNIT_KELVIN,
        }[self._display_temp_unit]
        self.recipe["displayTemperatureUnit"] = self._display_temp_unit
        if recipe_path:
            self.recipe["file"] = recipe_path

    def create_ui(self):
        """Create the recipe editor UI using top-level tabs."""
        self.layout = QtWidgets.QGridLayout(self)
        self.layout.setContentsMargins(self.ROOT_MARGIN, self.ROOT_MARGIN, self.ROOT_MARGIN, self.ROOT_MARGIN)
        self.layout.setSpacing(self.ROOT_SPACING)

        self.create_editor_tabs()
        self.layout.addWidget(self.editorTabs, 0, 0)

    def create_editor_tabs(self):
        self.editorTabs = QtWidgets.QTabWidget()
        self.editorTabs.setObjectName(self.TAB_WIDGET_OBJECT_NAME)
        self.editorTabs.setStyleSheet(self._build_tab_stylesheet())
        self.editorTabs.addTab(self.create_recipe_info_tab(), self.TAB_TITLE_INFO)
        self.editorTabs.addTab(self.create_heating_profile_tab(), self.TAB_TITLE_PROFILE)
        self.editorTabs.currentChanged.connect(self._on_editor_tab_changed)
        self.editorTabs.setCornerWidget(self._create_tab_corner_actions(), QtCore.Qt.TopRightCorner)

    def _is_profile_tab_active(self):
        return self.editorTabs.currentIndex() == self.TAB_INDEX_PROFILE

    def _on_editor_tab_changed(self, index):
        if index == self.TAB_INDEX_PROFILE:
            self.request_update_recipe_curve(force=True)

    def request_update_recipe_curve(self, force=False):
        if force:
            self._curve_update_force = True
        if self._curve_update_pending:
            return
        self._curve_update_pending = True
        QtCore.QTimer.singleShot(0, self._flush_curve_update)

    def _flush_curve_update(self):
        self._curve_update_pending = False
        force = self._curve_update_force
        self._curve_update_force = False
        if not force and not self._is_profile_tab_active():
            return
        self._ensure_recipe_curve_canvas()
        self.update_recipe_curve()

    def _ensure_recipe_curve_canvas(self):
        if self.recipeCurveCanvas is not None:
            return

        if hasattr(self, "curveLoadingLabel") and self.curveLoadingLabel is not None:
            self.curveLayout.removeWidget(self.curveLoadingLabel)
            self.curveLoadingLabel.deleteLater()
            self.curveLoadingLabel = None

        self.recipeCurveFigure = None
        self.recipeCurvePlotWidget = pg.PlotWidget(axisItems={"bottom": _TimeAxis(orientation="bottom")})
        self.recipeCurvePlotWidget.setBackground(self.PLOT_BG_COLOR)
        self.recipeCurvePlotWidget.setLabel('left', f"{self.PLOT_AXIS_TEMPERATURE} ({chr(176)}C)", **self.PLOT_LABEL_STYLE)
        self.recipeCurvePlotWidget.setLabel('bottom', self.PLOT_AXIS_TIME, **self.PLOT_LABEL_STYLE)
        self.recipeCurvePlotWidget.showGrid(x=True, y=True, alpha=0.2)
        self.recipeCurvePlotWidget.getAxis('left').setTextPen('w')
        self.recipeCurvePlotWidget.getAxis('bottom').setTextPen('w')
        self.recipeCurveCurve = self.recipeCurvePlotWidget.plot([], [], pen=pg.mkPen(self.PLOT_LINE_COLOR, width=2))

        self.recipeCurveCanvas = self.recipeCurvePlotWidget
        self.recipeCurveCanvas.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.recipeCurveCanvas.setMinimumHeight(
            self.CURVE_MIN_HEIGHT_COMPACT if self.compact_ui else self.CURVE_MIN_HEIGHT_DEFAULT
        )
        self.curveLayout.addWidget(self.recipeCurveCanvas)

    def _create_tab_corner_actions(self):
        container = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.closeButton = QtWidgets.QPushButton(self.CORNER_BUTTON_TEXT_CLOSE)
        self.saveButton = QtWidgets.QPushButton(self.CORNER_BUTTON_TEXT_SAVE)
        self.saveAsButton = QtWidgets.QPushButton(self.CORNER_BUTTON_TEXT_SAVE_AS)
        self.closeButton.setObjectName("smallButton")
        self.saveButton.setObjectName("smallButton")
        self.saveAsButton.setObjectName("smallButton")

        self.closeButton.setFixedSize(
            self.CORNER_BUTTON_WIDTH_CLOSE,
            self.CORNER_BUTTON_HEIGHT,
        )
        self.saveButton.setFixedSize(
            self.CORNER_BUTTON_WIDTH_SAVE,
            self.CORNER_BUTTON_HEIGHT,
        )
        self.saveAsButton.setFixedSize(
            self.CORNER_BUTTON_WIDTH_SAVE_AS,
            self.CORNER_BUTTON_HEIGHT,
        )

        self.closeButton.clicked.connect(self.close_edit_window)
        self.saveButton.clicked.connect(self.save_recipe)
        self.saveAsButton.clicked.connect(self.save_recipe_as)

        layout.addWidget(self.closeButton)
        layout.addWidget(self.saveButton)
        layout.addWidget(self.saveAsButton)
        return container

    def _build_tab_stylesheet(self):
        return (
            f"QTabWidget#{self.TAB_WIDGET_OBJECT_NAME}::pane {{"
            f"background-color: {self.COLOR_TAB_PANE_BG}; border: 1px solid {self.COLOR_TAB_PANE_BORDER}; }}"
            "QTabBar::tab {"
            f"background: {self.COLOR_TAB_BG}; color: {self.COLOR_TAB_TEXT}; "
            f"padding: {self.TAB_PADDING_V}px {self.TAB_PADDING_H}px; }}"
            "QTabBar::tab:selected {"
            f"background: {self.COLOR_TAB_PANE_BG}; color: {self.COLOR_TAB_SELECTED_TEXT}; }}"
            f"QWidget#{self.TAB_PAGE_OBJECT_NAME_INFO}, QWidget#{self.TAB_PAGE_OBJECT_NAME_PROFILE} {{"
            f"background-color: {self.COLOR_TAB_PANE_BG}; }}"
            f"QWidget#{self.TAB_PAGE_OBJECT_NAME_INFO} QLabel, "
            f"QWidget#{self.TAB_PAGE_OBJECT_NAME_PROFILE} QLabel {{"
            f"color: {self.COLOR_TAB_SELECTED_TEXT}; }}"
        )

    def create_recipe_info_tab(self):
        page = QtWidgets.QWidget()
        page.setObjectName(self.TAB_PAGE_OBJECT_NAME_INFO)
        layout = QtWidgets.QGridLayout(page)
        layout.setContentsMargins(self.PAGE_MARGIN, self.PAGE_MARGIN, self.PAGE_MARGIN, self.PAGE_MARGIN)
        layout.setSpacing(self.PAGE_SPACING)

        # Left side: short metadata fields and temperature unit selector.
        formWidget = QtWidgets.QWidget()
        formLayout = QtWidgets.QGridLayout(formWidget)
        formLayout.setContentsMargins(0, 0, 0, 0)
        formLayout.setHorizontalSpacing(self.FORM_H_SPACING)
        formLayout.setVerticalSpacing(self.FORM_V_SPACING)

        self.recipeName = QtWidgets.QLineEdit()
        self.recipeCreator = QtWidgets.QLineEdit()
        self.recipeRoastType = QtWidgets.QLineEdit()
        self.beanRegion = QtWidgets.QLineEdit()
        self.beanCountry = QtWidgets.QLineEdit()
        self.beanLink = QtWidgets.QLineEdit()
        self.beanStore = QtWidgets.QLineEdit()

        for edit in (
            self.recipeName,
            self.recipeCreator,
            self.recipeRoastType,
            self.beanRegion,
            self.beanCountry,
            self.beanLink,
            self.beanStore,
        ):
            edit.setAttribute(QtCore.Qt.WA_MacShowFocusRect, 0)

        self.temperatureUnitSelect = customqtwidgets.ComboBoxNoWheel()
        self.temperatureUnitSelect.addItems([
            RECIPE_UNIT_CELSIUS,
            RECIPE_UNIT_FAHRENHEIT,
            RECIPE_UNIT_KELVIN,
        ])
        self.temperatureUnitSelect.currentIndexChanged.connect(self.on_temperature_unit_changed)

        form_fields = [
            (self.FORM_LABEL_RECIPE_NAME, self.recipeName),
            (self.FORM_LABEL_CREATED_BY, self.recipeCreator),
            (self.FORM_LABEL_ROAST_TYPE, self.recipeRoastType),
            (self.FORM_LABEL_BEAN_REGION, self.beanRegion),
            (self.FORM_LABEL_BEAN_COUNTRY, self.beanCountry),
            (self.FORM_LABEL_BEAN_LINK, self.beanLink),
            (self.FORM_LABEL_BEAN_STORE_NAME, self.beanStore),
            (self.FORM_LABEL_TEMPERATURE_UNIT, self.temperatureUnitSelect),
        ]
        for row, (label_text, widget) in enumerate(form_fields):
            formLayout.addWidget(QtWidgets.QLabel(label_text), row, 0)
            formLayout.addWidget(widget, row, 1)

        # Right side: large description box.
        descWidget = QtWidgets.QWidget()
        descLayout = QtWidgets.QVBoxLayout(descWidget)
        descLayout.setContentsMargins(0, 0, 0, 0)
        descLayout.setSpacing(4)
        descLayout.addWidget(QtWidgets.QLabel(self.FORM_LABEL_DESCRIPTION))
        self.recipeDescriptionBox = QtWidgets.QTextEdit()
        descLayout.addWidget(self.recipeDescriptionBox)

        layout.addWidget(formWidget, 0, 0)
        layout.addWidget(descWidget, 0, 1)
        layout.setColumnStretch(0, 2)
        layout.setColumnStretch(1, 3)

        return page

    def create_heating_profile_tab(self):
        page = QtWidgets.QWidget()
        page.setObjectName(self.TAB_PAGE_OBJECT_NAME_PROFILE)
        layout = QtWidgets.QHBoxLayout(page)
        layout.setContentsMargins(self.PAGE_MARGIN, self.PAGE_MARGIN, self.PAGE_MARGIN, self.PAGE_MARGIN)
        layout.setSpacing(self.PAGE_SPACING)
        page.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

        self.recipeSteps = self.create_steps_spreadsheet()
        self._configure_steps_table_widths()

        # Right side uses as much area as possible to prepare for drag-edit support.
        self.curveWidget = QtWidgets.QWidget()
        self.curveWidget.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        curveLayout = QtWidgets.QVBoxLayout(self.curveWidget)
        self.curveLayout = curveLayout
        curveLayout.setContentsMargins(0, 0, 0, 0)
        curveLayout.setSpacing(4)
        curveLayout.addWidget(QtWidgets.QLabel(self.SECTION_LABEL_HEATING_CURVE))
        self.curveLoadingLabel = QtWidgets.QLabel(self.SECTION_LABEL_LOADING_CURVE)
        self.curveLoadingLabel.setAlignment(QtCore.Qt.AlignCenter)
        curveLayout.addWidget(self.curveLoadingLabel)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        splitter.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        splitter.addWidget(self.recipeSteps)
        splitter.addWidget(self.curveWidget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setChildrenCollapsible(False)

        # Derive initial split from table geometry constants so tuning constants
        # (column widths/editor widths/TABLE_MIN_WIDTH) directly affects layout.
        base_width = self.WINDOW_MIN_WIDTH if self.compact_ui else self.WINDOW_RESIZE_WIDTH_DEFAULT
        layout_overhead = self.SPLITTER_LAYOUT_OVERHEAD  # outer margins + splitter handle + tab/frame overhead
        min_plot_width = self.SPLITTER_MIN_PLOT_WIDTH
        left_width = self.recipeSteps.minimumWidth()
        right_width = max(min_plot_width, base_width - left_width - layout_overhead)
        splitter.setSizes([left_width, right_width])

        layout.addWidget(splitter)
        return page


    def create_steps_spreadsheet(self):
        """Creates Recipe Steps table. It does not populate the table in this method."""
        recipeStepsTable = QtWidgets.QTableWidget()
        recipeStepsTable.setShowGrid(False)
        recipeStepsTable.setAlternatingRowColors(True)
        recipeStepsTable.setCornerButtonEnabled(False)
        recipeStepsTable.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        recipeStepsTable.verticalHeader().setVisible(False)

        recipeStepsTable.setColumnCount(4)
        self._update_steps_header_labels(recipeStepsTable)

        return recipeStepsTable

    def _configure_steps_table_widths(self):
        header = self.recipeSteps.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.Fixed)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.Fixed)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.Fixed)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.Fixed)

        if self.compact_ui:
            font = header.font()
            base_size = font.pointSizeF()
            if base_size <= 0:
                base_size = 11.0
            font.setPointSizeF(max(8.0, base_size - 1.0))
            header.setFont(font)

        duration_width = (
            self.COLUMN_WIDTH_DURATION_COMPACT
            if self.compact_ui
            else self.COLUMN_WIDTH_DURATION_DEFAULT
        )
        modify_width = (
            self.COLUMN_WIDTH_MODIFY_COMPACT
            if self.compact_ui
            else self.COLUMN_WIDTH_MODIFY_DEFAULT
        )

        self.recipeSteps.setColumnWidth(0, self.COLUMN_WIDTH_TEMP)
        self.recipeSteps.setColumnWidth(1, self.COLUMN_WIDTH_FAN)
        self.recipeSteps.setColumnWidth(2, duration_width)
        self.recipeSteps.setColumnWidth(3, modify_width)
        # Keep a little extra width beyond column sum for a vertical scroll bar and padding.
        self.recipeSteps.setMinimumWidth(
            self.COLUMN_WIDTH_TEMP
            + self.COLUMN_WIDTH_FAN
            + duration_width
            + modify_width
            + self.TABLE_MIN_EXTRA_WIDTH
        )

        if self.compact_ui:
            self.recipeSteps.verticalHeader().setDefaultSectionSize(self.TABLE_ROW_HEIGHT_COMPACT)

    def _current_unit_symbol(self):
        return normalize_temperature_unit(
            self._display_temp_unit,
            default=get_default_display_temperature_unit(),
        )

    def _current_unit_display_label(self):
        return self._current_unit_symbol()

    def _update_steps_header_labels(self, table):
        unit_symbol = self._current_unit_display_label()
        table.setHorizontalHeaderLabels([
            f"{self.TABLE_HEADER_TEMPERATURE_PREFIX} ({chr(176)}{unit_symbol})",
            self.TABLE_HEADER_FAN,
            self.TABLE_HEADER_DURATION,
            self.TABLE_HEADER_MODIFY,
        ])

    def close_edit_window(self):
        """Method used to close the Recipe Editor Window."""
        self.close()

    def preload_recipe_steps(self, recipeStepsTable):
        """Load existing recipe steps into the editor table."""
        steps = self.recipe["steps"]
        self.load_recipe_steps(recipeStepsTable, steps)

    def _display_temp_choices(self):
        choices = []
        for temp_c in range(MIN_TEMPERATURE_C, MAX_TEMPERATURE_C + 1, TEMPERATURE_STEP_C):
            display_value = int(round(celsius_to_temperature_unit(temp_c, self._display_temp_unit)))
            if str(display_value) not in choices:
                choices.append(str(display_value))
        return [self.COOLING_LABEL] + choices

    def load_recipe_steps(self, recipeStepsTable, steps):
        """Populate a recipe steps table from normalized Celsius step values."""
        fanSpeedChoices = [str(x) for x in range(1, 10)]
        targetTempChoices = self._display_temp_choices()
        if self._row_action_icons is None:
            self._row_action_icons = {
                "delete": QtGui.QIcon(utils.get_resource_filename('static/images/delete.png')),
                "insert": QtGui.QIcon(utils.get_resource_filename('static/images/plus.png')),
                "up": QtGui.QIcon(utils.get_resource_filename('static/images/upSmall.png')),
                "down": QtGui.QIcon(utils.get_resource_filename('static/images/downSmall.png')),
            }

        self._updating_steps_table = True
        try:
            for row in range(len(steps)):
                recipeStepsTable.insertRow(recipeStepsTable.rowCount())

                if self.compact_ui:
                    sectionTempWidget = CompactTempPickerCombo(
                        functools.partial(self.open_compact_temp_picker, row)
                    )
                else:
                    sectionTempWidget = customqtwidgets.ComboBoxNoWheel()
                sectionTempWidget.setObjectName("recipeEditCombo")
                sectionTempWidget.setFixedWidth(
                    self.TEMP_EDITOR_WIDTH_COMPACT if self.compact_ui else self.TEMP_EDITOR_WIDTH_DEFAULT
                )
                sectionTempWidget.addItems(targetTempChoices)
                sectionTempWidget.insertSeparator(1)

                if 'targetTemp' in steps[row]:
                    temp_display = int(round(
                        celsius_to_temperature_unit(steps[row]["targetTemp"], self._display_temp_unit)
                    ))
                    temp_display_text = str(temp_display)
                    if temp_display_text in targetTempChoices:
                        sectionTempWidget.setCurrentIndex(targetTempChoices.index(temp_display_text) + 1)
                    else:
                        sectionTempWidget.addItem(temp_display_text)
                        sectionTempWidget.setCurrentIndex(sectionTempWidget.count() - 1)
                elif 'cooling' in steps[row]:
                    sectionTempWidget.setCurrentIndex(targetTempChoices.index(self.COOLING_LABEL))

                if not self.compact_ui:
                    sectionTempWidget.currentIndexChanged.connect(self.on_steps_changed)

                if self.compact_ui:
                    sectionDurationWidget = CompactDurationEdit(
                        functools.partial(self.open_compact_duration_picker, row)
                    )
                else:
                    sectionDurationWidget = customqtwidgets.TimeEditNoWheel()
                sectionDurationWidget.setObjectName("recipeEditTime")
                sectionDurationWidget.setFixedWidth(
                    self.TIME_EDITOR_WIDTH_COMPACT if self.compact_ui else self.TIME_EDITOR_WIDTH_DEFAULT
                )
                sectionDurationWidget.setAttribute(QtCore.Qt.WA_MacShowFocusRect, 0)
                sectionDurationWidget.setDisplayFormat("mm:ss")
                sectionDurationStr = time.strftime("%M:%S", time.gmtime(steps[row]["sectionTime"]))
                sectionDuration = QtCore.QTime().fromString(sectionDurationStr, "mm:ss")
                sectionDurationWidget.setTime(sectionDuration)
                if not self.compact_ui:
                    sectionDurationWidget.timeChanged.connect(self.on_steps_changed)

                sectionFanSpeedWidget = customqtwidgets.ComboBoxNoWheel()
                sectionFanSpeedWidget.setObjectName("recipeEditCombo")
                sectionFanSpeedWidget.setFixedWidth(
                    self.FAN_EDITOR_WIDTH_COMPACT if self.compact_ui else self.FAN_EDITOR_WIDTH_DEFAULT
                )
                sectionFanSpeedWidget.addItems(fanSpeedChoices)
                sectionFanSpeedWidget.setCurrentIndex(fanSpeedChoices.index(str(steps[row]["fanSpeed"])))

                deleteRow = QtWidgets.QPushButton()
                deleteRow.setIcon(self._row_action_icons["delete"])
                deleteRow.setObjectName("deleteRow")
                deleteRow.clicked.connect(functools.partial(self.delete_recipe_step, row))

                insertRow = QtWidgets.QPushButton()
                insertRow.setIcon(self._row_action_icons["insert"])
                insertRow.setObjectName("insertRow")
                insertRow.clicked.connect(functools.partial(self.insert_recipe_step, row))

                modifyRowWidgetLayout = QtWidgets.QHBoxLayout()
                modifyRowWidgetLayout.setSpacing(0)
                modifyRowWidgetLayout.setContentsMargins(0, 0, 0, 0)
                if not self.compact_ui:
                    upArrow = QtWidgets.QPushButton()
                    upArrow.setObjectName("upArrow")
                    upArrow.setIcon(self._row_action_icons["up"])
                    upArrow.clicked.connect(functools.partial(self.move_recipe_step_up, row))

                    downArrow = QtWidgets.QPushButton()
                    downArrow.setObjectName("downArrow")
                    downArrow.setIcon(self._row_action_icons["down"])
                    downArrow.clicked.connect(functools.partial(self.move_recipe_step_down, row))

                    modifyRowWidgetLayout.addWidget(upArrow)
                    modifyRowWidgetLayout.addWidget(downArrow)
                modifyRowWidgetLayout.addWidget(deleteRow)
                modifyRowWidgetLayout.addWidget(insertRow)

                modifyRowWidget = QtWidgets.QWidget()
                modifyRowWidget.setObjectName("buttonTable")
                modifyRowWidget.setLayout(modifyRowWidgetLayout)

                recipeStepsTable.setCellWidget(row, 0, sectionTempWidget)
                recipeStepsTable.setCellWidget(row, 1, sectionFanSpeedWidget)
                recipeStepsTable.setCellWidget(row, 2, sectionDurationWidget)
                recipeStepsTable.setCellWidget(row, 3, modifyRowWidget)
        finally:
            self._updating_steps_table = False


    def preload_recipe_information(self):
        """Load information from self.recipe and prefill all form fields."""
        self.recipeName.setText(self.recipe["roastName"])
        self.recipeCreator.setText(self.recipe["creator"])
        self.recipeRoastType.setText(self.recipe["roastDescription"]["roastType"])
        self.beanRegion.setText(self.recipe["bean"]["region"])
        self.beanCountry.setText(self.recipe["bean"]["country"])
        self.beanLink.setText(self.recipe["bean"]["source"]["link"])
        self.beanStore.setText(self.recipe["bean"]["source"]["reseller"])
        self.recipeDescriptionBox.setText(self.recipe["roastDescription"]["description"])

        index = self.temperatureUnitSelect.findText(self._selected_recipe_unit_label)
        if index >= 0:
            self.temperatureUnitSelect.setCurrentIndex(index)

        self.preload_recipe_steps(self.recipeSteps)
        self.request_update_recipe_curve()

    def on_temperature_unit_changed(self):
        steps_c = self.get_current_table_values()
        selected_label = self.temperatureUnitSelect.currentText()
        self._display_temp_unit = normalize_temperature_unit(
            selected_label,
            default=get_default_display_temperature_unit(),
        )
        self._selected_recipe_unit_label = selected_label
        self._update_steps_header_labels(self.recipeSteps)
        if not steps_c:
            self.request_update_recipe_curve()
            return
        self.rebuild_recipe_steps_table(steps_c)

    def on_steps_changed(self):
        if self._updating_steps_table:
            return
        self.request_update_recipe_curve()

    def open_compact_temp_picker(self, row):
        """Open touch picker for temperature selection in compact mode."""
        widget = self.recipeSteps.cellWidget(row, 0)
        if widget is None:
            return
        selected_text = self._prompt_compact_temperature_selection(widget.currentText())
        if selected_text is None:
            return

        selected_index = widget.findText(selected_text)
        if selected_index < 0:
            widget.addItem(selected_text)
            selected_index = widget.findText(selected_text)

        widget.blockSignals(True)
        widget.setCurrentIndex(selected_index)
        widget.blockSignals(False)
        self.on_steps_changed()

    def open_compact_duration_picker(self, row):
        """Open touch picker for duration selection in compact mode."""
        widget = self.recipeSteps.cellWidget(row, 2)
        if widget is None:
            return
        current_seconds = QtCore.QTime(0, 0, 0).secsTo(widget.time())
        selected_seconds = self._prompt_compact_duration_selection(current_seconds)
        if selected_seconds is None:
            return

        widget.blockSignals(True)
        widget.setTime(QtCore.QTime(0, 0, 0).addSecs(int(selected_seconds)))
        widget.blockSignals(False)
        self.on_steps_changed()

    def _prompt_compact_temperature_selection(self, current_text):
        """Return selected display-unit temperature text or None if canceled."""
        min_display = int(round(celsius_to_temperature_unit(MIN_TEMPERATURE_C, self._display_temp_unit)))
        max_display = int(round(celsius_to_temperature_unit(MAX_TEMPERATURE_C, self._display_temp_unit)))

        state = {
            "cooling": current_text == self.COOLING_LABEL,
            "value": min_display,
        }
        if not state["cooling"]:
            try:
                state["value"] = int(current_text)
            except (TypeError, ValueError):
                state["value"] = min_display

        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(self.PICKER_TEMPERATURE_TITLE)
        dialog.setModal(True)
        dialog.setMinimumWidth(
            self.PICKER_DIALOG_WIDTH_COMPACT if self.compact_ui else self.PICKER_DIALOG_WIDTH_DEFAULT
        )

        layout = QtWidgets.QVBoxLayout(dialog)
        value_label = QtWidgets.QLabel()
        value_label.setAlignment(QtCore.Qt.AlignCenter)
        value_label.setObjectName("label")

        def refresh_label():
            if state["cooling"]:
                value_label.setText(self.COOLING_LABEL)
            else:
                value_label.setText(f"{state['value']} {self._current_unit_display_label()}")

        def set_cooling(enabled):
            state["cooling"] = bool(enabled)
            refresh_label()

        def adjust(delta):
            if state["cooling"]:
                state["cooling"] = False
            state["value"] = max(min_display, min(max_display, state["value"] + int(delta)))
            refresh_label()

        cooling_toggle = QtWidgets.QPushButton(self.PICKER_TEMPERATURE_COOLING_TOGGLE)
        cooling_toggle.setCheckable(True)
        cooling_toggle.setChecked(state["cooling"])
        cooling_toggle.clicked.connect(set_cooling)

        step_row = QtWidgets.QHBoxLayout()
        minus_big = QtWidgets.QPushButton(f"-{self.TEMP_PICKER_STEP_LARGE}")
        minus_small = QtWidgets.QPushButton(f"-{self.TEMP_PICKER_STEP_SMALL}")
        plus_small = QtWidgets.QPushButton(f"+{self.TEMP_PICKER_STEP_SMALL}")
        plus_big = QtWidgets.QPushButton(f"+{self.TEMP_PICKER_STEP_LARGE}")
        minus_big.clicked.connect(lambda: adjust(-self.TEMP_PICKER_STEP_LARGE))
        minus_small.clicked.connect(lambda: adjust(-self.TEMP_PICKER_STEP_SMALL))
        plus_small.clicked.connect(lambda: adjust(self.TEMP_PICKER_STEP_SMALL))
        plus_big.clicked.connect(lambda: adjust(self.TEMP_PICKER_STEP_LARGE))
        step_row.addWidget(minus_big)
        step_row.addWidget(minus_small)
        step_row.addWidget(plus_small)
        step_row.addWidget(plus_big)

        action_row = QtWidgets.QHBoxLayout()
        cancel_button = QtWidgets.QPushButton(self.PICKER_CANCEL_TEXT)
        apply_button = QtWidgets.QPushButton(self.PICKER_APPLY_TEXT)
        cancel_button.clicked.connect(dialog.reject)
        apply_button.clicked.connect(dialog.accept)
        action_row.addWidget(cancel_button)
        action_row.addWidget(apply_button)

        refresh_label()
        layout.addWidget(value_label)
        layout.addWidget(cooling_toggle)
        layout.addLayout(step_row)
        layout.addLayout(action_row)

        dialog_exec = getattr(dialog, "exec", dialog.exec_)
        if not dialog_exec():
            return None
        if state["cooling"]:
            return self.COOLING_LABEL
        return str(state["value"])

    def _prompt_compact_duration_selection(self, current_seconds):
        """Return selected duration in seconds, or None if canceled."""
        state = {
            "seconds": int(max(0, min(self.DURATION_MAX_S, int(current_seconds)))),
        }

        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(self.PICKER_DURATION_TITLE)
        dialog.setModal(True)
        dialog.setMinimumWidth(
            self.PICKER_DIALOG_WIDTH_COMPACT if self.compact_ui else self.PICKER_DIALOG_WIDTH_DEFAULT
        )

        layout = QtWidgets.QVBoxLayout(dialog)
        value_label = QtWidgets.QLabel()
        value_label.setAlignment(QtCore.Qt.AlignCenter)
        value_label.setObjectName("label")

        def format_mmss(total_seconds):
            return time.strftime("%M:%S", time.gmtime(max(0, int(total_seconds))))

        def refresh_label():
            value_label.setText(format_mmss(state["seconds"]))

        def adjust(delta):
            state["seconds"] = max(0, min(self.DURATION_MAX_S, state["seconds"] + int(delta)))
            refresh_label()

        step_row = QtWidgets.QHBoxLayout()
        minus_big = QtWidgets.QPushButton(f"-{self.DURATION_STEP_LARGE_S}s")
        minus_small = QtWidgets.QPushButton(f"-{self.DURATION_STEP_SMALL_S}s")
        plus_small = QtWidgets.QPushButton(f"+{self.DURATION_STEP_SMALL_S}s")
        plus_big = QtWidgets.QPushButton(f"+{self.DURATION_STEP_LARGE_S}s")
        minus_big.clicked.connect(lambda: adjust(-self.DURATION_STEP_LARGE_S))
        minus_small.clicked.connect(lambda: adjust(-self.DURATION_STEP_SMALL_S))
        plus_small.clicked.connect(lambda: adjust(self.DURATION_STEP_SMALL_S))
        plus_big.clicked.connect(lambda: adjust(self.DURATION_STEP_LARGE_S))
        step_row.addWidget(minus_big)
        step_row.addWidget(minus_small)
        step_row.addWidget(plus_small)
        step_row.addWidget(plus_big)

        action_row = QtWidgets.QHBoxLayout()
        cancel_button = QtWidgets.QPushButton(self.PICKER_CANCEL_TEXT)
        apply_button = QtWidgets.QPushButton(self.PICKER_APPLY_TEXT)
        cancel_button.clicked.connect(dialog.reject)
        apply_button.clicked.connect(dialog.accept)
        action_row.addWidget(cancel_button)
        action_row.addWidget(apply_button)

        refresh_label()
        layout.addWidget(value_label)
        layout.addLayout(step_row)
        layout.addLayout(action_row)

        dialog_exec = getattr(dialog, "exec", dialog.exec_)
        if not dialog_exec():
            return None
        return int(state["seconds"])

    def move_recipe_step_up(self, row):
        """This method will take a row and swap it the row above it."""
        if row != 0:
            newSteps = self.get_current_table_values()
            newSteps[row], newSteps[row - 1] = newSteps[row - 1], newSteps[row]
            self.rebuild_recipe_steps_table(newSteps)

    def move_recipe_step_down(self, row):
        """This method will take a row and swap it the row below it."""
        if row != self.recipeSteps.rowCount() - 1:
            newSteps = self.get_current_table_values()
            newSteps[row], newSteps[row + 1] = newSteps[row + 1], newSteps[row]
            self.rebuild_recipe_steps_table(newSteps)

    def delete_recipe_step(self, row):
        """This method will take a row delete it."""
        newSteps = self.get_current_table_values()
        newSteps.pop(row)
        self.rebuild_recipe_steps_table(newSteps)

    def insert_recipe_step(self, row):
        """Inserts a row below the specified row with generic values."""
        newSteps = self.get_current_table_values()
        newSteps.insert(row + 1, {
            'fanSpeed': 5,
            'targetTemp': DEFAULT_TARGET_TEMPERATURE_C,
            'sectionTime': 0,
        })
        self.rebuild_recipe_steps_table(newSteps)

    def _parse_display_temperature(self, value_text):
        temp_display = int(value_text)
        temp_c = temperature_to_celsius(temp_display, self._display_temp_unit)
        return clamp_temperature_c(temp_c)

    def get_current_table_values(self):
        """Read current table values and return step dictionaries in Celsius."""
        recipeSteps = []
        for row in range(0, self.recipeSteps.rowCount()):
            currentRow = {}
            currentRow["sectionTime"] = QtCore.QTime(0, 0, 0).secsTo(
                self.recipeSteps.cellWidget(row, 2).time()
            )
            currentRow["fanSpeed"] = int(self.recipeSteps.cellWidget(row, 1).currentText())

            temp_text = self.recipeSteps.cellWidget(row, 0).currentText()
            if temp_text == self.COOLING_LABEL:
                currentRow["cooling"] = True
            else:
                currentRow["targetTemp"] = self._parse_display_temperature(temp_text)

            recipeSteps.append(currentRow)

        return recipeSteps

    def rebuild_recipe_steps_table(self, newSteps):
        """Reload rows in the recipe steps table with new steps."""
        if len(newSteps) < 1:
            alert = QtWidgets.QMessageBox()
            alert.setWindowTitle(self.ALERT_MIN_STEPS_TITLE)
            style_sheet = self.styleSheet()
            if not style_sheet:
                app = QtWidgets.QApplication.instance()
                style_sheet = app.styleSheet() if app is not None else ""
            if isinstance(style_sheet, str) and style_sheet:
                alert.setStyleSheet(style_sheet)
            alert.setText(self.ALERT_MIN_STEPS_TEXT)
            dialog_exec = getattr(alert, "exec", alert.exec_)
            dialog_exec()
            return

        while self.recipeSteps.rowCount() > 0:
            self.recipeSteps.removeRow(0)
        self.load_recipe_steps(self.recipeSteps, newSteps)
        self.request_update_recipe_curve()

    def update_recipe_curve(self):
        self._ensure_recipe_curve_canvas()
        steps = self.get_current_table_values()

        unit_symbol = self._current_unit_display_label()
        self.recipeCurvePlotWidget.setLabel('bottom', self.PLOT_AXIS_TIME, **self.PLOT_LABEL_STYLE)
        self.recipeCurvePlotWidget.setLabel('left', f"{self.PLOT_AXIS_TEMPERATURE} ({chr(176)}{unit_symbol})", **self.PLOT_LABEL_STYLE)

        x_seconds = [0]
        baseline_c = float(MIN_TEMPERATURE_C)
        y_values = [celsius_to_temperature_unit(baseline_c, self._display_temp_unit)]

        elapsed_s = 0
        last_temp_display = y_values[0]
        for step in steps:
            target_c = baseline_c if step.get("cooling") else float(step.get("targetTemp", baseline_c))
            target_display = celsius_to_temperature_unit(target_c, self._display_temp_unit)

            x_seconds.append(elapsed_s)
            y_values.append(target_display)

            elapsed_s += int(step.get("sectionTime", 0))
            x_seconds.append(elapsed_s)
            y_values.append(target_display)
            last_temp_display = target_display

        if elapsed_s == 0:
            x_seconds.append(1)
            y_values.append(last_temp_display)

        self.recipeCurveCurve.setData(x_seconds, y_values)

        y_min_display = celsius_to_temperature_unit(float(MIN_TEMPERATURE_C), self._display_temp_unit)
        y_max_display = max(y_values) if y_values else y_min_display
        if y_max_display <= y_min_display:
            y_max_display = y_min_display + 1.0

        self.recipeCurvePlotWidget.setXRange(0, max(1, elapsed_s), padding=0)
        self.recipeCurvePlotWidget.setYRange(y_min_display, y_max_display + 5.0, padding=0)
        self.recipeCurveCanvas.repaint()

    def _convert_steps_for_save(self, steps_c, output_unit_symbol):
        converted_steps = []
        for step in steps_c:
            converted = {
                "sectionTime": int(step["sectionTime"]),
                "fanSpeed": int(step["fanSpeed"]),
            }
            if step.get("cooling"):
                converted["cooling"] = True
            else:
                converted["targetTemp"] = int(round(
                    celsius_to_temperature_unit(step["targetTemp"], output_unit_symbol)
                ))
            converted_steps.append(converted)
        return converted_steps

    def save_recipe(self):
        """Save recipe to current file path or default path."""
        if "file" in self.recipe:
            filePath = self.recipe["file"]
        else:
            filePath = self._default_recipe_path()

        self._save_recipe_to_path(filePath)

    def save_recipe_as(self):
        """Prompt for a new path and save recipe there."""
        start_path = self._default_recipe_path()
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            self.FILE_DIALOG_SAVE_AS_TITLE,
            start_path,
            self.FILE_DIALOG_SAVE_AS_FILTER,
        )
        if not file_path:
            return

        if not file_path.lower().endswith(".json"):
            file_path = f"{file_path}.json"

        self._save_recipe_to_path(file_path)
        self.recipe["file"] = file_path

    def _default_recipe_path(self):
        return (
            os.path.expanduser('~/Documents/Openroast/Recipes/My Recipes/')
            + tools.format_filename(self.recipeName.text())
            + ".json"
        )

    def _save_recipe_to_path(self, filePath):
        """Create and save a recipe file at the specified path."""

        steps_c = self.get_current_table_values()
        selected_unit_label = self.temperatureUnitSelect.currentText()
        output_unit_symbol = normalize_temperature_unit(
            selected_unit_label,
            default=get_default_display_temperature_unit(),
        )

        self.newRecipe = {}
        self.newRecipe["roastName"] = self.recipeName.text()
        self.newRecipe["formatVersion"] = RECIPE_FORMAT_VERSION
        self.newRecipe["temperatureUnit"] = selected_unit_label
        self.newRecipe["steps"] = self._convert_steps_for_save(steps_c, output_unit_symbol)
        self.newRecipe["roastDescription"] = {}
        self.newRecipe["roastDescription"]["roastType"] = self.recipeRoastType.text()
        self.newRecipe["roastDescription"]["description"] = self.recipeDescriptionBox.toPlainText()
        self.newRecipe["creator"] = self.recipeCreator.text()
        self.newRecipe["bean"] = {}
        self.newRecipe["bean"]["region"] = self.beanRegion.text()
        self.newRecipe["bean"]["country"] = self.beanCountry.text()
        self.newRecipe["bean"]["source"] = {}
        self.newRecipe["bean"]["source"]["reseller"] = self.beanStore.text()
        self.newRecipe["bean"]["source"]["link"] = self.beanLink.text()
        self.newRecipe["totalTime"] = 0
        for step in self.newRecipe["steps"]:
            self.newRecipe["totalTime"] += step["sectionTime"]

        jsonObject = json.dumps(self.newRecipe, indent=4)
        dir_path = os.path.dirname(filePath)
        if dir_path and not os.path.exists(dir_path):
            try:
                os.makedirs(dir_path)
            except OSError as exc:  # Guard against race condition
                if exc.errno != errno.EEXIST:
                    raise
        with open(filePath, 'w', encoding='utf-8') as file:
            file.write(jsonObject)
