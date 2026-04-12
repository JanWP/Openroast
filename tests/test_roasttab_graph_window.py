import unittest

from openroast.views.roasttab import RoastTab


class _FakeRecipes:
    def __init__(self, section_times=None, section_temps=None, current_step=0):
        self._section_times = section_times or []
        self._section_temps = section_temps or []
        self._current_step = current_step

    def check_recipe_loaded(self):
        return bool(self._section_times)

    def get_num_recipe_sections(self):
        return len(self._section_times)

    def get_section_duration(self, index):
        return self._section_times[index]

    def get_current_step_number(self):
        return self._current_step

    def get_section_temp(self, index):
        return self._section_temps[index]

    # Backward-compatible alias.
    def get_section_time(self, index):
        return self.get_section_duration(index)


class RoastTabGraphWindowTests(unittest.TestCase):
    def _make_roast_tab(self, section_times):
        roast_tab = RoastTab.__new__(RoastTab)
        roast_tab.recipes = _FakeRecipes(section_times)
        return roast_tab

    def test_section_boundary_switch_happens_exactly_at_boundary(self):
        roast_tab = self._make_roast_tab([10, 20])

        self.assertEqual(roast_tab._get_graph_time_window_max_s(0), 10)
        self.assertEqual(roast_tab._get_graph_time_window_max_s(9), 10)
        self.assertEqual(roast_tab._get_graph_time_window_max_s(10), 30)
        self.assertEqual(roast_tab._get_graph_time_window_max_s(29), 30)
        self.assertEqual(roast_tab._get_graph_time_window_max_s(30), 30)

    def test_elapsed_fallback_used_after_last_section(self):
        roast_tab = self._make_roast_tab([10, 20])
        self.assertEqual(roast_tab._get_graph_time_window_max_s(31), 31)

    def test_no_recipe_loaded_uses_elapsed_time(self):
        roast_tab = self._make_roast_tab([])
        self.assertEqual(roast_tab._get_graph_time_window_max_s(0), 1)
        self.assertEqual(roast_tab._get_graph_time_window_max_s(15), 15)

    def test_temperature_axis_reference_tracks_measured_and_target_peaks(self):
        roast_tab = RoastTab.__new__(RoastTab)
        roast_tab._min_temp_c = 20
        roast_tab._graph_measured_peak_c = 20.0
        roast_tab._graph_target_peak_c = 20.0
        roast_tab._graph_last_scanned_target_step = -1
        roast_tab.recipes = _FakeRecipes(
            section_times=[10, 10],
            section_temps=[160, 190],
            current_step=0,
        )
        roast_tab._get_roaster_target_temp_c = lambda: 150

        class _FakeGraphWidget:
            def __init__(self):
                self.last_reference = None

            def set_temperature_axis_reference_c(self, reference_c):
                self.last_reference = reference_c

        roast_tab.graphWidget = _FakeGraphWidget()

        ref0 = roast_tab._update_graph_temperature_axis_reference(80)
        self.assertEqual(ref0, 160.0)
        self.assertEqual(roast_tab.graphWidget.last_reference, 160.0)

        # Move to step 1 and ensure newly reached section target expands the reference.
        roast_tab.recipes._current_step = 1
        ref1 = roast_tab._update_graph_temperature_axis_reference(100)
        self.assertEqual(ref1, 190.0)
        self.assertEqual(roast_tab.graphWidget.last_reference, 190.0)

        # Lower readings/targets must not reduce the tracked ceiling.
        roast_tab._get_roaster_target_temp_c = lambda: 120
        ref2 = roast_tab._update_graph_temperature_axis_reference(90)
        self.assertEqual(ref2, 190.0)


if __name__ == "__main__":
    unittest.main()

