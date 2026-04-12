import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import QtWidgets

from openroast.temperature import TEMP_UNIT_F
from openroast.views.customqtwidgets import RoastGraphWidget


class RoastGraphWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_append_draw_and_clear(self):
        widget = RoastGraphWidget(animated=False)
        widget.append_x(21)
        widget.append_x(22)
        widget.set_time_window_max_seconds(30)
        widget.graph_draw(force=True)

        self.assertEqual(widget.counter, 2)
        self.assertEqual(widget.graphXValueList, [1, 2])
        self.assertEqual(widget.graphYValueList, [21, 22])

        widget.clear_graph()
        self.assertEqual(widget.counter, 0)
        self.assertEqual(widget.graphXValueList, [])
        self.assertEqual(widget.graphYValueList, [])

    def test_save_roast_graph_csv_writes_elapsed_seconds(self):
        widget = RoastGraphWidget(animated=False)
        widget.append_x(21)
        widget.append_x(25)
        widget.append_x(30)

        fd, path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        try:
            with patch("openroast.views.customqtwidgets.QtWidgets.QFileDialog.getSaveFileName", return_value=(path, "CSV (*.csv)")):
                widget.save_roast_graph_csv()

            with open(path, encoding="utf-8") as handle:
                rows = [line.strip() for line in handle.readlines() if line.strip()]
            self.assertEqual(rows[0], "Seconds,Temperature")
            self.assertEqual(rows[1], "0,21")
            self.assertEqual(rows[2], "1,25")
            self.assertEqual(rows[3], "2,30")
        finally:
            os.remove(path)

    def test_display_unit_updates_axis_label(self):
        widget = RoastGraphWidget(animated=False)
        widget.set_display_temperature_unit(TEMP_UNIT_F)
        axis_label = widget.plotWidget.getAxis("left").labelText
        self.assertIn("\N{DEGREE SIGN}F", axis_label)


if __name__ == "__main__":
    unittest.main()

