# -*- coding: utf-8 -*-
# Roastero, released under GPLv3

import os
import json
import time
import math

from PyQt5 import QtCore
from PyQt5 import QtWidgets

import pyqtgraph as pg
from pyqtgraph.exporters import ImageExporter
from openroast.temperature import GRAPH_HEADROOM_C, MIN_TEMPERATURE_C


class _TimeAxis(pg.AxisItem):
    def tickStrings(self, values, scale, spacing):
        _ = scale, spacing
        labels = []
        for value in values:
            total_s = max(0, int(round(value)))
            labels.append(time.strftime("%M:%S", time.gmtime(total_s)))
        return labels


class RoastGraphWidget():
    Y_AXIS_STEP_C = 5.0

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
        self._x_window_max_s = None
        self._graph_timer = None

        self.widget = self.create_graph()

    def create_graph(self):
        # Create the graph widget.
        graphWidget = QtWidgets.QWidget()
        graphWidget.setObjectName("graph")

        self.plotWidget = pg.PlotWidget(axisItems={"bottom": _TimeAxis(orientation="bottom")})
        self.plotWidget.setBackground('#23252a')
        self.plotWidget.setLabel('left', 'TEMPERATURE (°C)', color='w')
        self.plotWidget.setLabel('bottom', 'TIME', color='w')
        self.plotWidget.showGrid(x=self._plot_show_grid, y=self._plot_show_grid, alpha=0.2 if self._plot_show_grid else 0.0)
        self.plotWidget.getAxis('left').setTextPen('w')
        self.plotWidget.getAxis('bottom').setTextPen('w')
        self.graphLine = self.plotWidget.plot([], [], pen=pg.mkPen('#8ab71b', width=self._line_width))
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
            self.graphLine.setPen(pg.mkPen('#8ab71b', width=self._line_width))

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
            xmin = self.graphXValueList[0]
            elapsed_s = self.counter
            if self._x_window_max_s is None:
                x_limit_s = elapsed_s
            else:
                # Keep section-based window, but never clip live data.
                x_limit_s = max(int(self._x_window_max_s), int(elapsed_s))
            self.plotWidget.setXRange(xmin, max(1, x_limit_s), padding=0)
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
                'Save Roast Graph',
                os.path.expanduser('~/'),
                'Graph (*.png);;All Files (*)')
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
                'Save Roast Graph CSV',
                os.path.expanduser('~/'),
                'CSV (*.csv);;All Files (*)')
            with open(file_name[0], 'w') as outfile:
                outfile.write("Seconds,Temperature\n")
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
