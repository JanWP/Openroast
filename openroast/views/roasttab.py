# -*- coding: utf-8 -*-
# Roastero, released under GPLv3

import time
import math
from multiprocessing import sharedctypes

from PyQt5 import QtCore
from PyQt5 import QtWidgets

from openroast.temperature import (
    MAX_TEMPERATURE_C,
    MIN_TEMPERATURE_C,
    TEMP_UNIT_F,
    celsius_to_kelvin,
    celsius_to_formatted_display,
    celsius_to_temperature_unit,
    get_default_display_temperature_unit,
    clamp_temperature_c,
    kelvin_to_celsius,
    normalize_temperature_unit,
    temperature_to_celsius,
)
from openroast.views import customqtwidgets
from openroast.views.ui_constants import RoastTabUI
from openroast import app_config


NON_COMPACT_PROGRESS_ROW_MIN_HEIGHT = RoastTabUI.NON_COMPACT_PROGRESS_ROW_MIN_HEIGHT

class RoastTab(QtWidgets.QWidget):
    COMPACT_CONTENTS_MARGINS = RoastTabUI.COMPACT_CONTENTS_MARGINS
    COMPACT_HORIZONTAL_SPACING = RoastTabUI.COMPACT_HORIZONTAL_SPACING
    COMPACT_VERTICAL_SPACING = RoastTabUI.COMPACT_VERTICAL_SPACING

    BUTTON_ROAST = RoastTabUI.BUTTON_ROAST
    BUTTON_COOL = RoastTabUI.BUTTON_COOL
    BUTTON_STOP = RoastTabUI.BUTTON_STOP
    BUTTON_RESET = RoastTabUI.BUTTON_RESET

    LABEL_TARGET_TEMP = RoastTabUI.LABEL_TARGET_TEMP
    LABEL_SECTION_DURATION = RoastTabUI.LABEL_SECTION_DURATION
    LABEL_FAN_SPEED = RoastTabUI.LABEL_FAN_SPEED
    LABEL_CURRENT_TEMP = RoastTabUI.LABEL_CURRENT_TEMP
    LABEL_REMAINING_SECTION_DURATION = RoastTabUI.LABEL_REMAINING_SECTION_DURATION
    LABEL_TOTAL_TIME = RoastTabUI.LABEL_TOTAL_TIME
    BUTTON_NEXT = RoastTabUI.BUTTON_NEXT
    BUTTON_NEXT_WIDTH = RoastTabUI.BUTTON_NEXT_WIDTH
    TIMELINE_MAX_LABELS = RoastTabUI.TIMELINE_MAX_LABELS
    TIMELINE_COMPACT_SPACING = RoastTabUI.TIMELINE_COMPACT_SPACING
    TIMELINE_DEFAULT_SPACING = RoastTabUI.TIMELINE_DEFAULT_SPACING
    TIMELINE_TICK_WIDTH = RoastTabUI.TIMELINE_TICK_WIDTH
    TIMELINE_TICK_HEIGHT = RoastTabUI.TIMELINE_TICK_HEIGHT
    TIMELINE_LABEL_GAP = RoastTabUI.TIMELINE_LABEL_GAP

    DIALOG_RESET_TITLE = RoastTabUI.DIALOG_RESET_TITLE
    DIALOG_RESET_STATE_MESSAGE = RoastTabUI.DIALOG_RESET_STATE_MESSAGE
    DIALOG_RESET_BEGINNING_MESSAGE = RoastTabUI.DIALOG_RESET_BEGINNING_MESSAGE
    DIALOG_STOP_TITLE = RoastTabUI.DIALOG_STOP_TITLE
    DIALOG_STOP_MESSAGE = RoastTabUI.DIALOG_STOP_MESSAGE

    def __init__(self, roaster, recipes, compact_ui=False):
        super(RoastTab, self).__init__()

        # Class variables.
        self.sectionDurationSliderPressed = False
        self.tempSliderPressed = False

        # Use a blinker for connect_state == CS_CONNECTING...
        self._connecting_blinker = True
        self.CONNECT_TXT_PLEASE_CONNECT = RoastTabUI.CONNECT_TEXT_PLEASE_CONNECT
        self.CONNECT_TXT_CONNECTING = RoastTabUI.CONNECT_TEXT_CONNECTING

        # process-safe flag to schedule controller vars update from recipe obj
        self._flag_update_controllers = sharedctypes.Value('i', 0)

        # store roaster object
        self.roaster = roaster
        # store recipes object
        self.recipes = recipes
        self.compact_ui = compact_ui

        # Convert all temperature values to Celsius for display/control.
        self._roaster_temperature_unit = normalize_temperature_unit(
            getattr(self.roaster, "temperature_unit", TEMP_UNIT_F),
            default=TEMP_UNIT_F,
        )
        self._min_temp_c = int(getattr(self.roaster, "temperature_min_c", MIN_TEMPERATURE_C))
        self._max_temp_c = int(getattr(self.roaster, "temperature_max_c", MAX_TEMPERATURE_C))
        self._has_temp_k = hasattr(self.roaster, "current_temp_k")
        self._has_target_temp_k = hasattr(self.roaster, "target_temp_k")
        self._has_time_s = hasattr(self.roaster, "time_remaining_s")
        self._has_total_time_s = hasattr(self.roaster, "total_time_s")
        self._section_duration_setpoint_s = 0
        self._confirm_on_stop = False
        self._confirm_on_clear = False
        self._reset_graph_axis_tracking()

        # Create the tab ui.
        self.create_ui()

        # Update initial GUI information
        self.update_remaining_section_duration()
        self.update_total_time()

        # Create timer to update gui data.
        self.timer = QtCore.QTimer()
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.update_data)
        self.timer.start()

        # Apply app-level preferences once widgets/timers exist.
        self.apply_preferences({})

        # Set the roast tab diabled when starting.
        self.setEnabled(False)

    def create_ui(self):
        # Create the main layout for the roast tab.
        self.layout = QtWidgets.QGridLayout()
        if self.compact_ui:
            self.layout.setContentsMargins(*self.COMPACT_CONTENTS_MARGINS)
            self.layout.setHorizontalSpacing(self.COMPACT_HORIZONTAL_SPACING)
            self.layout.setVerticalSpacing(self.COMPACT_VERTICAL_SPACING)

        # Create graph widget.
        self.graphWidget = customqtwidgets.RoastGraphWidget(
            animated = True,
            updateMethod = self.graph_get_data,
            animatingMethod = self.check_roaster_status)
        self.layout.addWidget(self.graphWidget.widget, 0, 0)
        self.layout.setColumnStretch(0, 1)

        # Create right pane.
        self.rightPane = self.create_right_pane()
        self.layout.addLayout(self.rightPane, 0, 1)

        # Create fault banner (hidden by default).
        self._faultBannerWidget = QtWidgets.QWidget()
        fault_banner_layout = QtWidgets.QHBoxLayout(self._faultBannerWidget)
        fault_banner_layout.setContentsMargins(4, 2, 4, 2)
        fault_banner_layout.setSpacing(8)
        self._faultLabel = QtWidgets.QLabel(RoastTabUI.FAULT_BANNER_TEXT)
        self._faultLabel.setStyleSheet(RoastTabUI.FAULT_BANNER_STYLE)
        fault_banner_layout.addWidget(self._faultLabel, 1)
        self._faultResetButton = QtWidgets.QPushButton(RoastTabUI.FAULT_RESET_BUTTON_TEXT)
        self._faultResetButton.setStyleSheet(RoastTabUI.FAULT_RESET_BUTTON_STYLE)
        self._faultResetButton.clicked.connect(self._on_fault_reset_clicked)
        fault_banner_layout.addWidget(self._faultResetButton, 0)
        self._faultBannerWidget.setHidden(True)
        self.layout.addWidget(self._faultBannerWidget, 1, 0, 1, 2)

        # Create progress bar.
        self.progressBar = self.create_progress_bar()
        self.layout.addLayout(self.progressBar, 2, 0, 1, 2, QtCore.Qt.AlignCenter)
        if self.compact_ui:
            self.layout.setRowStretch(0, 10)
            self.layout.setRowStretch(2, 1)
        else:
            # Reserve progress-bar space from startup so graph/control bottoms
            # stay aligned before and after a recipe is loaded.
            self.layout.setRowMinimumHeight(2, NON_COMPACT_PROGRESS_ROW_MIN_HEIGHT)

        # Create not connected label.
        self.connectionStatusLabel = QtWidgets.QLabel(self.CONNECT_TXT_PLEASE_CONNECT)
        self.connectionStatusLabel.setObjectName("connectionStatus")
        self.connectionStatusLabel.setAlignment(QtCore.Qt.AlignCenter)
        self.layout.addWidget(self.connectionStatusLabel, 0, 0)

        # Set main layout for widget.
        self.setLayout(self.layout)

    def check_roaster_status(self):
        if (self.roaster.get_roaster_state() == 'roasting' or
                self.roaster.get_roaster_state() == 'cooling'):
            return True
        else:
            return False

    def _roaster_temp_to_c(self, value):
        return clamp_temperature_c(
            temperature_to_celsius(value, self._roaster_temperature_unit),
            low=self._min_temp_c,
            high=self._max_temp_c,
        )

    def _c_to_roaster_temp(self, value):
        return int(round(celsius_to_temperature_unit(value, self._roaster_temperature_unit)))

    def _get_display_temperature_unit(self):
        return get_default_display_temperature_unit()

    def _format_display_temperature(self, temp_c):
        display_unit = self._get_display_temperature_unit()
        return celsius_to_formatted_display(temp_c, display_unit)

    def graph_get_data(self):
        current_temp_c = self._get_roaster_current_temp_c()
        self.graphWidget.append_x(current_temp_c)
        self._update_graph_temperature_axis_reference(current_temp_c)
        self.graphWidget.set_time_window_max_seconds(
            self._get_graph_time_window_max_s(self._get_roaster_total_time_s())
        )

    def _reset_graph_axis_tracking(self):
        self._graph_measured_peak_c = float(self._min_temp_c)
        self._graph_target_peak_c = float(self._min_temp_c)
        self._graph_last_scanned_target_step = -1

    def _update_graph_temperature_axis_reference(self, current_temp_c):
        self._graph_measured_peak_c = max(self._graph_measured_peak_c, float(current_temp_c))
        self._graph_target_peak_c = max(self._graph_target_peak_c, float(self._get_roaster_target_temp_c()))

        if self.recipes.check_recipe_loaded():
            current_step = max(0, int(self.recipes.get_current_step_number()))
            if current_step > self._graph_last_scanned_target_step:
                for idx in range(self._graph_last_scanned_target_step + 1, current_step + 1):
                    self._graph_target_peak_c = max(
                        self._graph_target_peak_c,
                        float(self.recipes.get_section_temp(idx)),
                    )
                self._graph_last_scanned_target_step = current_step

        axis_reference_c = max(
            float(self._min_temp_c),
            self._graph_measured_peak_c,
            self._graph_target_peak_c,
        )
        self.graphWidget.set_temperature_axis_reference_c(axis_reference_c)
        return axis_reference_c

    def _get_graph_time_window_max_s(self, elapsed_s):
        """Return section-aligned graph x-limit for current elapsed roast time."""
        elapsed_s = int(max(0, elapsed_s))
        if not self.recipes.check_recipe_loaded():
            return max(1, elapsed_s)

        section_end_s = 0
        for idx in range(self.recipes.get_num_recipe_sections()):
            section_end_s += int(self.recipes.get_section_duration(idx))
            # Use strict '<' so we switch window exactly at section boundary.
            if elapsed_s < section_end_s:
                return max(1, section_end_s)

        return max(1, elapsed_s)

    def _check_graph_bounds(self):
        """Warn the user if total recipe duration exceeds graph deque capacity.

        This is a non-blocking informational check — the roast will proceed
        normally, but the earliest graph data points will be silently dropped
        once the deque is full.
        """
        if not self.recipes.check_recipe_loaded():
            return
        total_s = 0
        for idx in range(self.recipes.get_num_recipe_sections()):
            total_s += int(self.recipes.get_section_duration(idx))
        if total_s <= 0:
            return
        refresh_ms = self.graphWidget.get_refresh_interval_ms()
        seconds_per_sample = max(0.001, refresh_ms / 1000.0)
        estimated_samples = total_s / seconds_per_sample
        max_len = customqtwidgets.RoastGraphWidget.GRAPH_DATA_MAX_LEN
        if estimated_samples > max_len:
            lost_s = int((estimated_samples - max_len) * seconds_per_sample)
            QtWidgets.QMessageBox.information(
                self,
                RoastTabUI.DIALOG_GRAPH_BOUNDS_TITLE,
                RoastTabUI.DIALOG_GRAPH_BOUNDS_MESSAGE.format(
                    total_minutes=total_s / 60.0,
                    max_minutes=max_len * seconds_per_sample / 60.0,
                    lost_seconds=lost_s,
                ),
            )

    def _get_roaster_current_temp_c(self):
        if self._has_temp_k:
            return clamp_temperature_c(
                kelvin_to_celsius(self.roaster.current_temp_k),
                low=self._min_temp_c,
                high=self._max_temp_c,
            )
        return self._roaster_temp_to_c(self.roaster.current_temp)

    def _get_roaster_target_temp_c(self):
        if self._has_target_temp_k:
            return clamp_temperature_c(
                kelvin_to_celsius(self.roaster.target_temp_k),
                low=self._min_temp_c,
                high=self._max_temp_c,
            )
        return self._roaster_temp_to_c(self.roaster.target_temp)

    def _set_roaster_target_temp_c(self, value_c):
        if self._has_target_temp_k:
            target_temp_k = celsius_to_kelvin(value_c)
            if self.roaster.target_temp_k != target_temp_k:
                self.roaster.target_temp_k = target_temp_k
            return
        roaster_value = self._c_to_roaster_temp(value_c)
        if self.roaster.target_temp != roaster_value:
            self.roaster.target_temp = roaster_value

    def _get_roaster_time_remaining_s(self):
        if self._has_time_s:
            return self.roaster.time_remaining_s
        return self.roaster.time_remaining

    def _set_roaster_time_remaining_s(self, value_s):
        if self._has_time_s:
            if self.roaster.time_remaining_s != value_s:
                self.roaster.time_remaining_s = value_s
            return
        if self.roaster.time_remaining != value_s:
            self.roaster.time_remaining = value_s

    def _get_roaster_total_time_s(self):
        if self._has_total_time_s:
            return self.roaster.total_time_s
        return self.roaster.total_time

    def _set_roaster_total_time_s(self, value_s):
        if self._has_total_time_s:
            self.roaster.total_time_s = value_s
            return
        self.roaster.total_time = value_s

    def save_roast_graph(self):
        self.graphWidget.save_roast_graph()

    def save_roast_graph_csv(self):
        self.graphWidget.save_roast_graph_csv()

    def update_data(self):
        # Update temperature widgets.
        self._set_text_if_changed(
            self.currentTempLabel,
            self._format_display_temperature(self._get_roaster_current_temp_c()),
        )

        # Update timers.
        self.update_remaining_section_duration()
        self.update_total_time()

        # Update current section progress bar.
        if(self.recipes.check_recipe_loaded()):
            timeline_widget = getattr(self, "sectionTimelineWidget", None)
            if timeline_widget is not None:
                elapsed_s = self._get_roaster_total_time_s() if self.check_roaster_status() else 0
                timeline_widget.set_elapsed_seconds(elapsed_s)

        # Check connection status of the openroast.roaster.
        roaster_connected = bool(self.roaster.connected)
        if roaster_connected:
            if not self.connectionStatusLabel.isHidden():
                self.connectionStatusLabel.setHidden(True)
            if not self.isEnabled():
                self.setEnabled(True)
        else:
            connect_state = getattr(self.roaster, "connect_state", None)
            cs_connecting = getattr(self.roaster, "CS_CONNECTING", None)
            if connect_state is not None and cs_connecting is not None and connect_state == cs_connecting:
                # this means that the roaster has just been plugged in
                # sometimes, it takes a while to complete the connection...
                connecting_str = self.CONNECT_TXT_CONNECTING
                if self._connecting_blinker:
                    connecting_str += "  ...   "
                else:
                    connecting_str += "     ..."
                self._connecting_blinker = not self._connecting_blinker
                self._set_text_if_changed(self.connectionStatusLabel, connecting_str)
            else:
                self._set_text_if_changed(self.connectionStatusLabel, self.CONNECT_TXT_PLEASE_CONNECT)
            if self.connectionStatusLabel.isHidden():
                self.connectionStatusLabel.setHidden(False)
            if self.isEnabled():
                self.setEnabled(False)

        # if openroast.roaster has moved the recipe to the next section,
        # update the controller-related info onscreen.
        # print("roasttab.update_data: f_u_c = %s" %  self._flag_update_controllers.value)
        if self._flag_update_controllers.value:
            self._flag_update_controllers.value = 0
            self.update_controllers()

        # Update over-temperature fault banner.
        self._update_fault_banner()

    def _update_fault_banner(self):
        fault = getattr(self.roaster, "fault", None)
        banner = getattr(self, "_faultBannerWidget", None)
        if banner is None:
            return
        if fault:
            if banner.isHidden():
                banner.setHidden(False)
        else:
            if not banner.isHidden():
                banner.setHidden(True)

    def _on_fault_reset_clicked(self):
        clear_fault = getattr(self.roaster, "clear_fault", None)
        if callable(clear_fault):
            clear_fault()
        self._update_fault_banner()

    def create_right_pane(self):
        rightPane = QtWidgets.QVBoxLayout()
        if self.compact_ui:
            rightPane.setContentsMargins(0, 0, 0, 0)
            rightPane.setSpacing(4)

        # Create guage window.
        guageWindow = self.create_gauge_window()
        rightPane.addLayout(guageWindow)

        # Create sliders.
        sliderPanel = self.create_slider_panel()
        rightPane.addLayout(sliderPanel)

        # In non-compact mode, place a stretchable spacer before buttons so
        # the button row anchors to the bottom and aligns with graph bottom.
        if not self.compact_ui:
            spacer = QtWidgets.QWidget()
            spacer.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
            rightPane.addWidget(spacer)

        # Create button panel.
        buttonPanel = self.create_button_panel()
        rightPane.addLayout(buttonPanel)

        return rightPane

    def create_progress_bar(self):
        progressBar = QtWidgets.QVBoxLayout()
        progressBar.setSpacing(
            self.TIMELINE_COMPACT_SPACING if self.compact_ui else self.TIMELINE_DEFAULT_SPACING
        )
        if self.compact_ui:
            progressBar.setContentsMargins(0, 0, 0, 0)

        rowLayout = QtWidgets.QHBoxLayout()
        rowLayout.setSpacing(4)
        rowLayout.setContentsMargins(0, 0, 0, 0)

        self.sectionTimelineWidget = customqtwidgets.SectionProgressTimelineWidget(
            max_labels=self.TIMELINE_MAX_LABELS,
            tick_height=self.TIMELINE_TICK_HEIGHT,
            tick_label_gap=self.TIMELINE_LABEL_GAP,
        )
        rowLayout.addWidget(self.sectionTimelineWidget, 1)

        if(self.recipes.check_recipe_loaded()):
            counter = 0
            display_unit = self._get_display_temperature_unit()
            section_durations_s = []
            section_labels = []

            for i in range(0, self.recipes.get_num_recipe_sections()):
                # Calculate display time and generate label text.
                section_duration_s = self.recipes.get_section_duration(i)
                label_text = celsius_to_formatted_display(
                    self.recipes.get_section_temp(i),
                    display_unit,
                )

                section_durations_s.append(int(section_duration_s))
                section_labels.append(label_text)

                # Make the counter equal to i.
                counter = i

            self.sectionTimelineWidget.set_sections(section_durations_s, section_labels)

           # Create next button.
            nextButton = QtWidgets.QPushButton(self.BUTTON_NEXT)
            nextButton.setObjectName("nextButton")
            nextButton.setFixedWidth(self.BUTTON_NEXT_WIDTH)
            nextButton.clicked.connect(self.next_section)
            rowLayout.addWidget(nextButton, 0)
        else:
            self.sectionTimelineWidget.clear()

        progressBar.addLayout(rowLayout)
        return progressBar

    def recreate_progress_bar(self):
        self.layout.removeItem(self.progressBar)
        self._clear_layout_items(self.progressBar)
        self.progressBar = self.create_progress_bar()
        self.layout.addLayout(self.progressBar, 2, 0, 1, 2, QtCore.Qt.AlignCenter)

    def _clear_layout_items(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.setParent(None)
            elif child_layout is not None:
                self._clear_layout_items(child_layout)

    def calc_display_time(self, duration_s):
        duration_min = duration_s / 60
        minutes = math.floor((duration_min))
        seconds = int((duration_min - math.floor(duration_min)) * 60)

        if(seconds == 0):
            seconds = '00'

        return(minutes, seconds)

    def create_gauge_window(self):
        guageWindow = QtWidgets.QGridLayout()
        if self.compact_ui:
            guageWindow.setHorizontalSpacing(6)
            guageWindow.setVerticalSpacing(4)

        # Create current temp gauge.
        self.currentTempLabel = QtWidgets.QLabel(self._format_display_temperature(self._min_temp_c))
        currentTemp = self.create_info_box(self.LABEL_CURRENT_TEMP, "tempGauge",
            self.currentTempLabel)
        guageWindow.addLayout(currentTemp, 0, 0)

        # Create target temp gauge.
        self.targetTempLabel = QtWidgets.QLabel()
        targetTemp = self.create_info_box(self.LABEL_TARGET_TEMP, "tempGauge", self.targetTempLabel)
        guageWindow.addLayout(targetTemp, 0, 1)

        # Create current duration.
        self.sectionDurationLabel = QtWidgets.QLabel()
        # Backward-compatible alias for tests/callers still using the old name.
        self.sectionTimeLabel = self.sectionDurationLabel
        currentTime = self.create_info_box(
            self.LABEL_REMAINING_SECTION_DURATION,
            "timeWindow",
            self.sectionDurationLabel,
        )
        guageWindow.addLayout(currentTime, 1, 0)

        # Create totalTime.
        self.totalTimeLabel = QtWidgets.QLabel()
        totalTime = self.create_info_box(self.LABEL_TOTAL_TIME, "timeWindow", self.totalTimeLabel)
        guageWindow.addLayout(totalTime, 1, 1)

        return guageWindow

    def create_button_panel(self):
        buttonPanel = QtWidgets.QGridLayout()
        if self.compact_ui:
            buttonPanel.setContentsMargins(0, 0, 0, 0)
            buttonPanel.setHorizontalSpacing(4)
            buttonPanel.setVerticalSpacing(2)

        # Create start roast button.
        self.startButton = QtWidgets.QPushButton(self.BUTTON_ROAST)
        self.startButton.setObjectName("roastControlButton")
        self.startButton.clicked.connect(self.roaster.roast)
        buttonPanel.addWidget(self.startButton, 0, 0)

        # Create cool button.
        self.coolButton = QtWidgets.QPushButton(self.BUTTON_COOL)
        self.coolButton.setObjectName("roastControlButton")
        self.coolButton.clicked.connect(self.roaster.cool)
        buttonPanel.addWidget(self.coolButton, 0, 1)

        # Create stop roast button.
        self.stopButton = QtWidgets.QPushButton(self.BUTTON_STOP)
        self.stopButton.setObjectName("roastControlButton")
        self.stopButton.clicked.connect(self.on_stop_clicked)
        buttonPanel.addWidget(self.stopButton, 0, 2)

        # Create reset roast button.
        self.resetButton = QtWidgets.QPushButton(self.BUTTON_RESET)
        self.resetButton.setObjectName("roastControlButton")
        self.resetButton.clicked.connect(self.reset_current_roast)
        buttonPanel.addWidget(self.resetButton, 0, 3)

        return buttonPanel

    def create_slider_panel(self):
        sliderPanel = QtWidgets.QGridLayout()
        sliderPanel.setColumnStretch(0, 3)
        if self.compact_ui:
            sliderPanel.setContentsMargins(0, 0, 0, 0)
            sliderPanel.setHorizontalSpacing(4)
            sliderPanel.setVerticalSpacing(2)

        # Create temperature slider label.
        tempSliderLabel = QtWidgets.QLabel(self.LABEL_TARGET_TEMP)
        sliderPanel.addWidget(tempSliderLabel, 0, 0)

        # Create temperature slider.
        self.tempSlider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.tempSlider.setRange(self._min_temp_c, self._max_temp_c)
        self.tempSlider.valueChanged.connect(self.update_target_temp_slider)
        sliderPanel.addWidget(self.tempSlider, 1, 0)

        # Create temperature spin box.
        self.tempSpinBox = QtWidgets.QSpinBox()
        self.tempSpinBox.setObjectName("miniSpinBox")
        self.tempSpinBox.setButtonSymbols(2)      # Remove arrows.
        self.tempSpinBox.setAlignment(QtCore.Qt.AlignCenter)
        self.tempSpinBox.setRange(self._min_temp_c, self._max_temp_c)
        self.tempSpinBox.valueChanged.connect(self.update_target_temp_spin_box)
        self.tempSpinBox.setAttribute(QtCore.Qt.WA_MacShowFocusRect, 0)
        sliderPanel.addWidget(self.tempSpinBox, 1, 1)

        # Update temperature data.
        self.update_target_temp()

        # Create duration slider label.
        durationSliderLabel = QtWidgets.QLabel(self.LABEL_SECTION_DURATION)
        sliderPanel.addWidget(durationSliderLabel, 2, 0)

        # Create duration slider.
        self.sectionDurationSlider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.sectionDurationSlider.setRange(0, 900)
        self.sectionDurationSlider.valueChanged.connect(self.update_section_duration_slider)
        sliderPanel.addWidget(self.sectionDurationSlider, 3, 0)

        # Create mini duration spin box.
        self.sectionDurationSpinBox = customqtwidgets.TimeEditNoWheel()
        self.sectionDurationSpinBox.setObjectName("miniSpinBox")
        self.sectionDurationSpinBox.setButtonSymbols(2)      # Remove arrows.
        self.sectionDurationSpinBox.setAlignment(QtCore.Qt.AlignCenter)
        self.sectionDurationSpinBox.setAttribute(QtCore.Qt.WA_MacShowFocusRect, 0)
        self.sectionDurationSpinBox.setDisplayFormat("mm:ss")
        self.sectionDurationSpinBox.timeChanged.connect(self.update_section_duration_spin_box)
        sliderPanel.addWidget(self.sectionDurationSpinBox, 3, 1)

        # Backward-compatible aliases used by older tests/callers.
        self.sectTimeSlider = self.sectionDurationSlider
        self.sectTimeSpinBox = self.sectionDurationSpinBox

        self.update_section_duration_setpoint()

        # Create fan speed slider.
        fanSliderLabel = QtWidgets.QLabel(self.LABEL_FAN_SPEED)
        sliderPanel.addWidget(fanSliderLabel, 4, 0)

        # Create fan speed slider.
        self.fanSlider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.fanSlider.setRange(1, 9)  # set minimum and maximum fan speed
        self.fanSlider.valueChanged.connect(self.update_fan_speed_slider)
        sliderPanel.addWidget(self.fanSlider, 5, 0)

        # Create mini fan spin box
        self.fanSpeedSpinBox = QtWidgets.QSpinBox()
        self.fanSpeedSpinBox.setObjectName("miniSpinBox")
        self.fanSpeedSpinBox.setButtonSymbols(2)      # Remove arrows.
        self.fanSpeedSpinBox.setRange(1, 9)
        self.fanSpeedSpinBox.setAttribute(QtCore.Qt.WA_MacShowFocusRect, 0)
        self.fanSpeedSpinBox.setAlignment(QtCore.Qt.AlignCenter)
        self.fanSpeedSpinBox.valueChanged.connect(self.update_fan_spin_box)
        sliderPanel.addWidget(self.fanSpeedSpinBox, 5, 1)

        return sliderPanel

    def create_info_box(self, labelText, objectName, valueLabel):
        # Create temp/time info boxes.
        infoBox = QtWidgets.QVBoxLayout()
        infoBox.setSpacing(0)
        label = QtWidgets.QLabel(labelText)
        label.setObjectName("label")
        valueLabel.setAlignment(QtCore.Qt.AlignCenter)
        valueLabel.setObjectName(objectName)
        infoBox.addWidget(label)
        infoBox.addWidget(valueLabel)
        return infoBox

    def _set_text_if_changed(self, widget, text):
        if widget.text() != text:
            widget.setText(text)

    def _format_mmss(self, duration_s):
        return time.strftime("%M:%S", time.gmtime(duration_s))

    def _set_value_if_changed(self, widget, value):
        if widget.value() != value:
            blocker = QtCore.QSignalBlocker(widget)
            widget.setValue(value)
            del blocker

    def _set_time_if_changed(self, widget, value):
        if widget.time() != value:
            blocker = QtCore.QSignalBlocker(widget)
            widget.setTime(value)
            del blocker

    def update_target_temp(self):
        target_temp_c = self._get_roaster_target_temp_c()
        self._set_text_if_changed(
            self.targetTempLabel,
            self._format_display_temperature(target_temp_c),
        )
        self._set_value_if_changed(self.tempSlider, target_temp_c)
        self._set_value_if_changed(self.tempSpinBox, target_temp_c)

    def update_target_temp_spin_box(self):
        value_c = self.tempSpinBox.value()
        self._set_text_if_changed(self.targetTempLabel, self._format_display_temperature(value_c))
        self._set_value_if_changed(self.tempSlider, value_c)
        self._set_roaster_target_temp_c(value_c)

    def update_target_temp_slider(self):
        value_c = self.tempSlider.value()
        self._set_text_if_changed(self.targetTempLabel, self._format_display_temperature(value_c))
        self._set_value_if_changed(self.tempSpinBox, value_c)
        self._set_roaster_target_temp_c(value_c)

    def update_fan_info(self):
        fan_speed = self.roaster.fan_speed
        self._set_value_if_changed(self.fanSlider, fan_speed)
        self._set_value_if_changed(self.fanSpeedSpinBox, fan_speed)

    def update_fan_speed_slider(self):
        fan_speed = self.fanSlider.value()
        self._set_value_if_changed(self.fanSpeedSpinBox, fan_speed)
        if self.roaster.fan_speed != fan_speed:
            self.roaster.fan_speed = fan_speed

    def update_fan_spin_box(self):
        fan_speed = self.fanSpeedSpinBox.value()
        self._set_value_if_changed(self.fanSlider, fan_speed)
        if self.roaster.fan_speed != fan_speed:
            self.roaster.fan_speed = fan_speed

    def set_section_duration(self):
        section_duration_s = self.sectionDurationSlider.value()
        self._set_section_duration_setpoint(section_duration_s)
        self._set_roaster_time_remaining_from_setpoint(section_duration_s)

    # Backward-compatible alias.
    def set_section_time(self):
        self.set_section_duration()

    def _set_section_duration_setpoint(self, section_duration_s):
        self._section_duration_setpoint_s = int(max(0, section_duration_s))
        self._set_value_if_changed(self.sectionDurationSlider, self._section_duration_setpoint_s)
        hhmmss = time.strftime("%H:%M:%S", time.gmtime(self._section_duration_setpoint_s))
        spin_time = QtCore.QTime.fromString(hhmmss)
        self._set_time_if_changed(self.sectionDurationSpinBox, spin_time)

    def sync_section_duration_setpoint_from_recipe(self):
        if self.recipes.check_recipe_loaded():
            section_duration_s = int(self.recipes.get_current_section_duration())
        else:
            section_duration_s = 0
        self._set_section_duration_setpoint(section_duration_s)

    # Backward-compatible alias.
    def sync_section_time_setpoint_from_recipe(self):
        self.sync_section_duration_setpoint_from_recipe()

    def update_section_duration_setpoint(self):
        self._set_section_duration_setpoint(self._section_duration_setpoint_s)

    # Backward-compatible alias.
    def update_section_time_setpoint(self):
        self.update_section_duration_setpoint()

    def _set_roaster_time_remaining_from_setpoint(self, new_setpoint_s):
        # Preserve elapsed time when user edits section duration during a roast.
        current_remaining_s = int(max(0, self._get_roaster_time_remaining_s()))
        elapsed_s = max(0, int(self._section_duration_setpoint_s) - current_remaining_s)
        new_remaining_s = max(0, int(new_setpoint_s) - elapsed_s)
        self._set_roaster_time_remaining_s(new_remaining_s)
        self._set_text_if_changed(self.sectionDurationLabel, self._format_mmss(new_remaining_s))

    def update_remaining_section_duration(self):
        remaining_section_s = self._get_roaster_time_remaining_s()
        self._set_text_if_changed(self.sectionDurationLabel, self._format_mmss(remaining_section_s))

    # Backward-compatible alias.
    def update_remaining_section_time(self):
        self.update_remaining_section_duration()

    # Backward-compatible alias.
    def update_section_time(self):
        self.update_remaining_section_duration()

    def update_section_duration_spin_box(self):
        section_duration_s = QtCore.QTime(0, 0, 0).secsTo(self.sectionDurationSpinBox.time())
        self._set_value_if_changed(self.sectionDurationSlider, section_duration_s)
        self._set_roaster_time_remaining_from_setpoint(section_duration_s)
        self._set_section_duration_setpoint(section_duration_s)

    # Backward-compatible alias.
    def update_sect_time_spin_box(self):
        self.update_section_duration_spin_box()

    def update_section_duration_slider(self):
        section_duration_s = self.sectionDurationSlider.value()
        self._set_roaster_time_remaining_from_setpoint(section_duration_s)
        self._set_section_duration_setpoint(section_duration_s)

    # Backward-compatible alias.
    def update_sect_time_slider(self):
        self.update_section_duration_slider()

    def update_total_time(self):
        self._set_text_if_changed(self.totalTimeLabel, self._format_mmss(self._get_roaster_total_time_s()))

    def clear_roast(self):
        """ This method will clear the openroast.roaster, recipe, and reset the gui back
        to their original state. """

        if self._confirm_on_clear:
            answer = QtWidgets.QMessageBox.question(
                self,
                self.DIALOG_RESET_TITLE,
                self.DIALOG_RESET_STATE_MESSAGE,
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No,
            )
            if answer != QtWidgets.QMessageBox.Yes:
                return False

        self._prepare_backend_for_stop(reset_control_state=True)

        # Reset openroast.roaster.
        self.recipes.reset_roaster_settings()
        self._reset_backend_simulation_state()

        # Clear the recipe.
        self.recipes.clear_recipe()

        # Clear roast tab gui.
        self.clear_roast_tab_gui()
        return True

    def has_graph_data(self):
        graph_widget = getattr(self, "graphWidget", None)
        if graph_widget is None:
            return False
        return bool(getattr(graph_widget, "counter", 0) > 0)

    def has_previous_roast_state(self):
        if self.recipes.check_recipe_loaded():
            return True
        if self.has_graph_data():
            return True
        return int(max(0, self._get_roaster_total_time_s())) > 0

    def reset_current_roast(self):
        """ Used to reset the current loaded recipe """

        if self._confirm_on_clear:
            answer = QtWidgets.QMessageBox.question(
                self,
                self.DIALOG_RESET_TITLE,
                self.DIALOG_RESET_BEGINNING_MESSAGE,
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No,
            )
            if answer != QtWidgets.QMessageBox.Yes:
                return

        self._prepare_backend_for_stop(reset_control_state=True)

        # Verify that the recipe is loaded and reset it.
        if(self.recipes.check_recipe_loaded()):
            self.recipes.restart_current_recipe()
            self.recreate_progress_bar()

        self._reset_backend_simulation_state()

        # Clear roast tab gui.
        self.clear_roast_tab_gui()

    def clear_roast_tab_gui(self):
        """ Clears all of the graphical elements on the roast tab """

        # Recreate the progress bar or remove it.
        self.recreate_progress_bar()

        # Clear sliders.
        self._set_section_duration_setpoint(0)
        self.update_remaining_section_duration()
        self.update_fan_info()
        self.update_target_temp()

        # Set totalTime to zero.
        self._set_roaster_total_time_s(0)
        self.update_total_time()

        # Clear roast graph.
        self._reset_graph_axis_tracking()
        self.graphWidget.clear_graph()

    def _reset_backend_simulation_state(self):
        """Reset optional backend simulation state (used by local-mock)."""
        reset_simulation = getattr(self.roaster, "reset_simulation_state", None)
        if callable(reset_simulation):
            reset_simulation()

    def _reset_backend_control_state(self):
        """Reset optional backend control internals (PID/integrator state)."""
        reset_control = getattr(self.roaster, "reset_control_state", None)
        if callable(reset_control):
            reset_control()

    def _idle_backend(self):
        idle = getattr(self.roaster, "idle", None)
        if callable(idle):
            idle()

    def _cancel_autotune_if_running(self):
        cancel_autotune = getattr(self.roaster, "cancel_autotune", None)
        if callable(cancel_autotune):
            cancel_autotune()

    def _prepare_backend_for_stop(self, reset_control_state=False):
        self._cancel_autotune_if_running()
        self._idle_backend()
        if reset_control_state:
            self._reset_backend_control_state()

    def load_recipe_into_roast_tab(self):
        self.recipes.load_current_section()
        self.recreate_progress_bar()
        self.sync_section_duration_setpoint_from_recipe()
        self.update_remaining_section_duration()
        self.update_target_temp()
        self.update_fan_info()

    def next_section(self):
        self.recipes.move_to_next_section()
        self.update_controllers()

    def update_controllers(self):
        self.sync_section_duration_setpoint_from_recipe()
        self.update_remaining_section_duration()
        self.update_target_temp()
        self.update_fan_info()

    def schedule_update_controllers(self):
        # print("roasttab.schedule_update_controllers called")
        self._flag_update_controllers.value = 1

    def get_recipe_object(self):
        return self.recipes

    def on_stop_clicked(self):
        if self._confirm_on_stop:
            answer = QtWidgets.QMessageBox.question(
                self,
                self.DIALOG_STOP_TITLE,
                self.DIALOG_STOP_MESSAGE,
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No,
            )
            if answer != QtWidgets.QMessageBox.Yes:
                return
        self._prepare_backend_for_stop(reset_control_state=False)

    def apply_preferences(self, config_data):
        config = app_config.normalize_config(config_data)
        display_unit = config["display"]["temperatureUnitDefault"]

        refresh_ms = config["ui"]["refreshIntervalMs"]
        self.timer.setInterval(refresh_ms)
        self.graphWidget.set_refresh_interval_ms(refresh_ms)
        self.graphWidget.set_display_temperature_unit(display_unit)

        self.graphWidget.apply_plot_preferences(
            y_axis_headroom_c=app_config.get_plot_y_axis_headroom_c(config),
            y_axis_step_c=app_config.get_plot_y_axis_step_c(config),
            show_grid=config["plot"]["showGrid"],
            line_width=config["plot"]["lineWidth"],
        )

        self._confirm_on_stop = bool(config["roast"]["confirmOnStop"])
        self._confirm_on_clear = bool(config["roast"]["confirmOnClear"])

