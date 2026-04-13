# -*- coding: utf-8 -*-
# Roastero, released under GPLv3

import os
import json
import time
import math

from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5 import QtWidgets

import pyqtgraph as pg
from pyqtgraph.exporters import ImageExporter
from openroast.temperature import (
    GRAPH_HEADROOM_C,
    MIN_TEMPERATURE_C,
    TEMP_UNIT_C,
    celsius_to_temperature_unit,
    normalize_temperature_unit,
    temperature_unit_symbol_to_display,
)
from openroast.views.ui_constants import GraphUI, SharedColors


class _TimeAxis(pg.AxisItem):
    def __init__(self, orientation="bottom"):
        super().__init__(orientation=orientation)
        self._seconds_per_x = 1.0

    def set_seconds_per_x(self, seconds_per_x):
        self._seconds_per_x = max(0.001, float(seconds_per_x))

    def tickStrings(self, values, scale, spacing):
        _ = scale, spacing
        labels = []
        for value in values:
            total_s = max(0, int(round(float(value) * self._seconds_per_x)))
            labels.append(time.strftime("%M:%S", time.gmtime(total_s)))
        return labels


class _TemperatureAxis(pg.AxisItem):
    def __init__(self, orientation="left"):
        super().__init__(orientation=orientation)
        self._unit = TEMP_UNIT_C

    def set_display_unit(self, unit):
        self._unit = normalize_temperature_unit(unit, default=TEMP_UNIT_C)

    def tickStrings(self, values, scale, spacing):
        _ = scale, spacing
        labels = []
        for value_c in values:
            labels.append(str(int(round(celsius_to_temperature_unit(value_c, self._unit)))))
        return labels


class RoastGraphWidget():
    Y_AXIS_STEP_C = 5.0
    PLOT_BG_COLOR = SharedColors.SURFACE_PANEL
    PLOT_LINE_COLOR = SharedColors.ACCENT_PRIMARY
    PLOT_LABEL_COLOR = SharedColors.FOREGROUND_TEXT
    AXIS_BOTTOM_TIME = GraphUI.AXIS_BOTTOM_TIME
    AXIS_LEFT_TEMPERATURE_TEMPLATE = GraphUI.AXIS_LEFT_TEMPERATURE_TEMPLATE
    DIALOG_SAVE_GRAPH_TITLE = GraphUI.SAVE_GRAPH_TITLE
    DIALOG_SAVE_GRAPH_FILTER = GraphUI.SAVE_GRAPH_FILTER
    DIALOG_SAVE_GRAPH_CSV_TITLE = GraphUI.SAVE_GRAPH_CSV_TITLE
    DIALOG_SAVE_GRAPH_CSV_FILTER = GraphUI.SAVE_GRAPH_CSV_FILTER
    CSV_HEADER = GraphUI.CSV_HEADER

    def __init__(self, graphXValueList=None, graphYValueList=None,
            animated=False, updateMethod=None, animatingMethod=None):
        self.graphXValueList = graphXValueList or []
        self.graphYValueList = graphYValueList or []
        self.counter = 0
        self.updateMethod = updateMethod
        self.animated = animated
        # Check if graph should continue to graph.
        self.animatingMethod = animatingMethod
        self._last_drawn_len = -1
        self._ymax_seen = float(MIN_TEMPERATURE_C)
        self._y_reference_c = float(MIN_TEMPERATURE_C)
        self._y_axis_top = None
        self._y_axis_headroom_c = float(GRAPH_HEADROOM_C)
        self._y_axis_step_c = float(self.Y_AXIS_STEP_C)
        self._plot_show_grid = True
        self._line_width = 3.0
        self._refresh_interval_ms = 1000
        self._seconds_per_sample = 1.0
        self._x_window_max_s = None
        self._graph_timer = None
        self._display_temp_unit = TEMP_UNIT_C

        self.widget = self.create_graph()

    def create_graph(self):
        # Create the graph widget.
        graphWidget = QtWidgets.QWidget()
        graphWidget.setObjectName("graph")

        self._temp_axis = _TemperatureAxis(orientation="left")
        self._time_axis = _TimeAxis(orientation="bottom")
        self.plotWidget = pg.PlotWidget(
            axisItems={
                "bottom": self._time_axis,
                "left": self._temp_axis,
            }
        )
        self.plotWidget.setBackground(self.PLOT_BG_COLOR)
        self.set_display_temperature_unit(self._display_temp_unit)
        self.plotWidget.setLabel('bottom', self.AXIS_BOTTOM_TIME, color='w')
        self.plotWidget.showGrid(x=self._plot_show_grid, y=self._plot_show_grid, alpha=0.2 if self._plot_show_grid else 0.0)
        self.plotWidget.getAxis('left').setTextPen('w')
        self.plotWidget.getAxis('bottom').setTextPen('w')
        self.graphLine = self.plotWidget.plot([], [], pen=pg.mkPen(self.PLOT_LINE_COLOR, width=self._line_width))
        self._apply_temperature_axis_limits()

        # Add graph widgets to layout for graph.
        graphVerticalBox = QtWidgets.QVBoxLayout()
        graphVerticalBox.setContentsMargins(0, 0, 0, 0)
        graphVerticalBox.setSpacing(0)
        graphVerticalBox.addWidget(self.plotWidget)
        graphWidget.setLayout(graphVerticalBox)

        # Animate the the graph with new data
        if self.animated:
            self._graph_timer = QtCore.QTimer()
            self._graph_timer.setInterval(self._refresh_interval_ms)
            self._graph_timer.timeout.connect(self.graph_draw)
            self._graph_timer.start()
        else:
            self.graph_draw(force=True)

        return graphWidget

    def set_display_temperature_unit(self, unit):
        self._display_temp_unit = normalize_temperature_unit(unit, default=TEMP_UNIT_C)
        self._temp_axis.set_display_unit(self._display_temp_unit)
        left_axis = self.plotWidget.getAxis('left')
        left_axis.setLabel(
            text=self.AXIS_LEFT_TEMPERATURE_TEMPLATE.format(
                unit=temperature_unit_symbol_to_display(self._display_temp_unit)
            ),
            color=self.PLOT_LABEL_COLOR,
        )
        if hasattr(left_axis, "label") and hasattr(left_axis.label, "setDefaultTextColor"):
            left_axis.label.setDefaultTextColor(QtGui.QColor(self.PLOT_LABEL_COLOR))

    def _apply_temperature_axis_limits(self):
        bottom = float(MIN_TEMPERATURE_C)
        min_top = bottom + float(self._y_axis_headroom_c)
        raw_top = max(
            min_top,
            self._ymax_seen + float(self._y_axis_headroom_c),
            self._y_reference_c + float(self._y_axis_headroom_c),
        )
        step_c = max(0.1, float(self._y_axis_step_c))
        target_top = math.ceil(raw_top / step_c) * step_c

        if target_top <= bottom:
            target_top = bottom + float(GRAPH_HEADROOM_C)

        # Only grow the axis when needed to avoid expensive redraw churn.
        if self._y_axis_top is None or target_top > self._y_axis_top:
            self._y_axis_top = target_top
            self.plotWidget.setYRange(bottom, target_top, padding=0)

    def set_refresh_interval_ms(self, refresh_interval_ms):
        self._refresh_interval_ms = int(max(1, refresh_interval_ms))
        self._seconds_per_sample = self._refresh_interval_ms / 1000.0
        self._time_axis.set_seconds_per_x(self._seconds_per_sample)
        if self._graph_timer is not None:
            self._graph_timer.setInterval(self._refresh_interval_ms)

    def apply_plot_preferences(self, *, y_axis_headroom_c=None, y_axis_step_c=None,
                               show_grid=None, line_width=None):
        if y_axis_headroom_c is not None:
            self._y_axis_headroom_c = max(0.1, float(y_axis_headroom_c))
        if y_axis_step_c is not None:
            self._y_axis_step_c = max(0.1, float(y_axis_step_c))
        if show_grid is not None:
            self._plot_show_grid = bool(show_grid)
            self.plotWidget.showGrid(
                x=self._plot_show_grid,
                y=self._plot_show_grid,
                alpha=0.2 if self._plot_show_grid else 0.0,
            )
        if line_width is not None:
            self._line_width = max(1.0, float(line_width))
            self.graphLine.setPen(pg.mkPen(self.PLOT_LINE_COLOR, width=self._line_width))

        self._y_axis_top = None
        self._apply_temperature_axis_limits()

    def set_temperature_axis_reference_c(self, reference_c):
        if reference_c is None:
            return
        reference_c = float(reference_c)
        if reference_c > self._y_reference_c:
            self._y_reference_c = reference_c

    def graph_draw(self, *args, force=False, **kwargs):
        # Start graphing the roast if the roast has started.
        if self.animatingMethod is not None:
            if self.animatingMethod():
                self.updateMethod()

        current_len = len(self.graphYValueList)
        if not force and current_len == self._last_drawn_len:
            return

        if current_len:
            last_y = float(self.graphYValueList[-1])
            if last_y > self._ymax_seen:
                self._ymax_seen = last_y

        self.graphLine.setData(self.graphXValueList, self.graphYValueList)
        if current_len > 1:
            xmin = float(self.graphXValueList[0])
            elapsed_samples = float(self.counter)
            if self._x_window_max_s is None:
                x_limit_samples = elapsed_samples
            else:
                # Convert section-window seconds to sample-index units.
                window_samples = math.ceil(float(self._x_window_max_s) / self._seconds_per_sample)
                x_limit_samples = max(elapsed_samples, float(window_samples))
            self.plotWidget.setXRange(xmin, max(xmin + 1.0, x_limit_samples), padding=0)
        # Keep graph baseline at room temperature (20 C) without flipping axis.
        self._apply_temperature_axis_limits()
        self._last_drawn_len = current_len
        self.plotWidget.repaint()

    def append_x(self, temp_c):
        self.counter += 1
        self.graphXValueList.append(self.counter)
        self.graphYValueList.append(temp_c)

    def clear_graph(self):
        self.graphXValueList = []
        self.graphYValueList = []
        self.counter = 0
        self._ymax_seen = float(MIN_TEMPERATURE_C)
        self._y_reference_c = float(MIN_TEMPERATURE_C)
        self._y_axis_top = None
        self._x_window_max_s = None
        self.graphLine.setData([], [])
        self._apply_temperature_axis_limits()
        self.plotWidget.setXRange(0, 1, padding=0)
        self._last_drawn_len = 0
        self.plotWidget.repaint()

    def set_time_window_max_seconds(self, max_seconds):
        if max_seconds is None:
            self._x_window_max_s = None
        else:
            self._x_window_max_s = max(1, int(max_seconds))

    def save_roast_graph(self):
        try:
            file_name = QtWidgets.QFileDialog.getSaveFileName(
                None,
                self.DIALOG_SAVE_GRAPH_TITLE,
                os.path.expanduser('~/'),
                self.DIALOG_SAVE_GRAPH_FILTER)
            if file_name[0]:
                exporter = ImageExporter(self.plotWidget.plotItem)
                exporter.export(file_name[0])
        except FileNotFoundError:
            # Occurs if file browser is canceled
            pass
        else:
            pass

    def save_roast_graph_csv(self):
        try:
            file_name = QtWidgets.QFileDialog.getSaveFileName(
                None,
                self.DIALOG_SAVE_GRAPH_CSV_TITLE,
                os.path.expanduser('~/'),
                self.DIALOG_SAVE_GRAPH_CSV_FILTER)
            with open(file_name[0], 'w') as outfile:
                outfile.write(self.CSV_HEADER)
                if not self.graphXValueList:
                    return
                init_s = int(self.graphXValueList[0])
                for x_val, temp_c in zip(self.graphXValueList, self.graphYValueList):
                    elapsed_seconds = int(x_val) - init_s
                    outfile.write("{0},{1}\n".format(elapsed_seconds, temp_c))
        except FileNotFoundError:
            # Occurs if file browser is canceled
            pass
        else:
            pass


class SectionProgressTimelineWidget(QtWidgets.QWidget):
    """Lightweight roast timeline with duration-accurate sections and ticks."""

    def __init__(self, max_labels=6, tick_height=10, tick_label_gap=3, parent=None):
        super().__init__(parent)
        self._max_labels = max(2, int(max_labels))
        self._tick_height = max(4, int(tick_height))
        self._tick_label_gap = max(1, int(tick_label_gap))

        self._durations_s = []
        self._labels = []
        self._total_s = 0
        self._elapsed_s = 0

        self._bar_h = 20
        self._ticks_top_gap = 2
        self._bar_round = 5
        self._timeline_rounding_s = 30

        self._static_cache = None
        self._static_cache_size = QtCore.QSize()

        self._color_bg = QtGui.QColor("#23252b")
        self._color_fill = QtGui.QColor(SharedColors.ACCENT_PRIMARY)
        self._color_border = QtGui.QColor("#171a1e")
        self._color_section_boundary = QtGui.QColor(SharedColors.FOREGROUND_TEXT)
        self._color_tick = QtGui.QColor(SharedColors.FOREGROUND_TEXT)
        self._color_text = QtGui.QColor(SharedColors.FOREGROUND_TEXT)

        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.setMinimumHeight(self.sizeHint().height())

    def sizeHint(self):
        return QtCore.QSize(480, self._bar_h + self._tick_height + 8)

    def set_sections(self, durations_s, labels):
        durations = [max(0, int(v)) for v in durations_s]
        section_count = len(durations)
        text_labels = [str(v) for v in labels[:section_count]]
        if len(text_labels) < section_count:
            text_labels.extend([""] * (section_count - len(text_labels)))

        if self._durations_s == durations and self._labels == text_labels:
            return

        self._durations_s = durations
        self._labels = text_labels
        self._total_s = sum(self._durations_s)
        self._elapsed_s = 0
        self._invalidate_static_cache()
        self.update()

    def set_elapsed_seconds(self, elapsed_s):
        if not self._durations_s:
            return
        elapsed_s = max(0, int(elapsed_s))
        if elapsed_s == self._elapsed_s:
            return
        self._elapsed_s = elapsed_s
        self.update(self._bar_rect().toRect().adjusted(-2, -2, 2, 2))

    def clear(self):
        self._durations_s = []
        self._labels = []
        self._total_s = 0
        self._elapsed_s = 0
        self._invalidate_static_cache()
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._invalidate_static_cache()

    def _invalidate_static_cache(self):
        self._static_cache = None
        self._static_cache_size = QtCore.QSize()

    def _bar_rect(self):
        y = 0
        return QtCore.QRectF(0, y, max(1, self.width() - 1), self._bar_h)

    def _section_and_progress_for_elapsed(self):
        if not self._durations_s:
            return (0, 0)

        elapsed_s = max(0, int(self._elapsed_s))
        running = 0
        for idx, duration_s in enumerate(self._durations_s):
            duration_s = max(1, int(duration_s))
            if elapsed_s < running + duration_s:
                return (idx, int(round(((elapsed_s - running) / duration_s) * 100.0)))
            running += duration_s
        return (len(self._durations_s) - 1, 100)

    def _section_boundaries(self):
        count = len(self._durations_s)
        if count == 0:
            return [0, max(1, int(self._bar_rect().width()))]

        bar = self._bar_rect()
        left = int(bar.left())
        width = max(1, int(bar.width()))

        if self._total_s <= 0:
            return [left + round((i * width) / count) for i in range(count + 1)]

        boundaries = [left]
        acc = 0
        for duration_s in self._durations_s:
            acc += int(duration_s)
            boundaries.append(left + int(round((acc / self._total_s) * width)))
        boundaries[-1] = left + width
        return boundaries

    def _tick_times(self):
        total_s = int(self._total_s)
        if total_s <= 0:
            return [0]

        marker_count = min(
            self._max_labels,
            max(2, int(total_s / self._timeline_rounding_s) + 1),
        )
        values = [0]
        for idx in range(1, marker_count - 1):
            raw = (idx * total_s) / (marker_count - 1)
            rounded = int(round(raw / self._timeline_rounding_s) * self._timeline_rounding_s)
            rounded = max(0, min(total_s, rounded))
            if rounded > values[-1]:
                values.append(rounded)
        if values[-1] != total_s:
            values.append(total_s)
        return values

    def _time_to_x(self, seconds):
        bar = self._bar_rect()
        if self._total_s <= 0:
            return int(bar.left())
        ratio = max(0.0, min(1.0, float(seconds) / float(self._total_s)))
        return int(round(bar.left() + ratio * bar.width()))

    def _ensure_static_cache(self):
        size = self.size()
        if self._static_cache is not None and self._static_cache_size == size:
            return

        dpr = self.devicePixelRatioF()
        pixmap = QtGui.QPixmap(max(1, int(size.width() * dpr)), max(1, int(size.height() * dpr)))
        pixmap.setDevicePixelRatio(dpr)
        pixmap.fill(QtCore.Qt.transparent)

        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.TextAntialiasing, True)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, False)

        bar = self._bar_rect()
        boundaries = self._section_boundaries()

        if not self._durations_s:
            painter.end()
            self._static_cache = pixmap
            self._static_cache_size = size
            return

        fm = painter.fontMetrics()

        # Draw bar background and border.
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(self._color_bg)
        painter.drawRoundedRect(bar, self._bar_round, self._bar_round)

        painter.setPen(self._color_border)
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.drawRoundedRect(bar, self._bar_round, self._bar_round)

        # Draw fixed timeline ticks + labels on one compact row.
        ticks_top = int(bar.bottom()) + self._ticks_top_gap
        ticks_bottom = ticks_top + self._tick_height
        tick_times = self._tick_times()
        baseline = ticks_top + int((self._tick_height + fm.ascent() - fm.descent()) / 2)

        for i, tick_s in enumerate(tick_times):
            x = self._time_to_x(tick_s)
            painter.setPen(self._color_tick)
            painter.drawLine(x, ticks_top, x, ticks_bottom)

            label = time.strftime("%M:%S", time.gmtime(int(tick_s)))
            text_w = fm.horizontalAdvance(label)
            if i == len(tick_times) - 1:
                text_x = x - text_w - self._tick_label_gap
            else:
                text_x = x + self._tick_label_gap
            painter.drawText(text_x, baseline, label)

        painter.end()
        self._static_cache = pixmap
        self._static_cache_size = size

    def paintEvent(self, event):
        _ = event
        self._ensure_static_cache()

        painter = QtGui.QPainter(self)
        if self._static_cache is not None:
            painter.drawPixmap(0, 0, self._static_cache)

        if not self._durations_s:
            painter.end()
            return

        bar = self._bar_rect()
        boundaries = self._section_boundaries()
        current_section, current_progress_pct = self._section_and_progress_for_elapsed()

        # Clip fills to rounded bar to avoid overdraw artifacts.
        clip_path = QtGui.QPainterPath()
        clip_path.addRoundedRect(bar, self._bar_round, self._bar_round)
        painter.save()
        painter.setClipPath(clip_path)

        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(self._color_fill)

        for idx in range(len(self._durations_s)):
            x0 = boundaries[idx]
            x1 = boundaries[idx + 1]
            width = max(0, x1 - x0)
            if idx < current_section:
                fill_w = width
            elif idx == current_section:
                fill_w = int(round(width * (current_progress_pct / 100.0)))
            else:
                fill_w = 0
            if fill_w <= 0:
                continue
            painter.drawRect(QtCore.QRectF(x0, bar.top(), fill_w, bar.height()))
        painter.restore()

        # Draw section target labels inside the bar for compact vertical layout.
        fm = painter.fontMetrics()
        for idx, label_text in enumerate(self._labels):
            x0 = boundaries[idx]
            x1 = boundaries[idx + 1]
            rect = QtCore.QRect(x0 + 1, int(bar.top()), max(1, x1 - x0 - 2), int(bar.height()))
            painter.setPen(self._color_text)
            painter.save()
            painter.setClipRect(rect)
            # Center text when it fits; otherwise left-align and clip to preserve leading digits.
            text_width = fm.horizontalAdvance(label_text)
            if text_width + 4 <= rect.width():
                align = QtCore.Qt.AlignCenter
                draw_rect = rect
            else:
                align = QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter
                draw_rect = rect.adjusted(2, 0, 0, 0)
            painter.drawText(draw_rect, align, label_text)
            painter.restore()

        # Re-draw boundaries over fill for crisp section separation.
        painter.setPen(self._color_section_boundary)
        for x in boundaries[1:-1]:
            painter.drawLine(x, int(bar.top()), x, int(bar.bottom()))
        painter.setPen(self._color_border)
        painter.drawRoundedRect(bar, self._bar_round, self._bar_round)
        painter.end()

class ComboBoxNoWheel(QtWidgets.QComboBox):
    """A combobox with the wheel removed."""
    def __init__(self, *args, **kwargs):
        super(ComboBoxNoWheel, self).__init__()

    def wheelEvent(self, event):
        event.ignore()


class TimeEditNoWheel(QtWidgets.QTimeEdit):
    """A time edit combobox with the wheel removed."""
    def __init__(self, *args, **kwargs):
        super(TimeEditNoWheel, self).__init__()

    def wheelEvent(self, event):
        event.ignore()


class RecipeModel(QtWidgets.QFileSystemModel):
    """A Subclass of QFileSystemModel to add a column."""
    def __init__(self, *args, **kwargs):
        super(RecipeModel, self).__init__()

    def columnCount(self, parent = QtCore.QModelIndex()):
        return super(RecipeModel, self).columnCount()+1

    def data(self, index, role):
        if index.column() == self.columnCount() - 1:
            if role == QtCore.Qt.DisplayRole:
                filePath = self.filePath(index)
                if os.path.isfile(filePath):
                    with open(filePath) as json_data:
                        fileContents = json.load(json_data)
                    return fileContents["roastName"]
                else:
                    path = self.filePath(index)
                    position = path.rfind("/")
                    return path[position+1:]

        return super(RecipeModel, self).data(index, role)


class LogModel(QtWidgets.QFileSystemModel):
    """A Subclass of QFileSystemModel to add a column."""
    def __init__(self, *args, **kwargs):
        super(LogModel, self).__init__()

    def columnCount(self, parent = QtCore.QModelIndex()):
        return super(LogModel, self).columnCount()+1

    def data(self, index, role):
        if index.column() == self.columnCount() - 1:
            if role == QtCore.Qt.DisplayRole:
                filePath = self.filePath(index)
                if os.path.isfile(filePath):
                    with open(filePath) as json_data:
                        fileContents = json.load(json_data)
                    return fileContents["recipeName"]
                else:
                    path = self.filePath(index)
                    position = path.rfind("/")
                    return path[position+1:]

        return super(LogModel, self).data(index, role)
