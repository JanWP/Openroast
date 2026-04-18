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
    class _FakeGraphWidget:
        def __init__(self):
            self.last_reference = None
            self.last_window_max_s = None
            self.append_calls = 0

        def append_x(self, _value):
            self.append_calls += 1

        def set_temperature_axis_reference_c(self, reference_c):
            self.last_reference = reference_c

        def set_time_window_max_seconds(self, max_seconds):
            self.last_window_max_s = max_seconds

    def _make_roast_tab(self, section_times):
        roast_tab = RoastTab.__new__(RoastTab)
        roast_tab.recipes = _FakeRecipes(section_times)
        roast_tab._graph_window_max_s_cached = None
        roast_tab._graph_window_cache_mode = "elapsed"
        roast_tab.graphWidget = self._FakeGraphWidget()
        roast_tab._get_roaster_current_temp_c = lambda: 100
        roast_tab._update_graph_temperature_axis_reference = lambda _temp_c: None
        roast_tab._get_roaster_time_remaining_s = lambda: 0
        roast_tab.roaster = type("R", (), {"get_roaster_state": lambda self: "idle"})()
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

        roast_tab.graphWidget = self._FakeGraphWidget()

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

    def test_graph_get_data_uses_cached_recipe_window_without_per_tick_recompute(self):
        roast_tab = self._make_roast_tab([10, 20])
        call_count = {"count": 0}

        def _counted_window(elapsed_s):
            call_count["count"] += 1
            return 30

        roast_tab._get_graph_time_window_max_s = _counted_window
        elapsed = {"value": 5}
        roast_tab._get_roaster_total_time_s = lambda: elapsed["value"]

        roast_tab.graph_get_data()
        elapsed["value"] = 6
        roast_tab.graph_get_data()

        self.assertEqual(call_count["count"], 1)
        self.assertEqual(roast_tab.graphWidget.last_window_max_s, 30)

    def test_graph_get_data_uses_fixed_cycle_window_for_non_recipe_runtime(self):
        roast_tab = self._make_roast_tab([])
        elapsed = {"value": 5}
        remaining = {"value": 20}
        roast_tab._get_roaster_total_time_s = lambda: elapsed["value"]
        roast_tab._get_roaster_time_remaining_s = lambda: remaining["value"]
        roast_tab.roaster = type("R", (), {"get_roaster_state": lambda self: "roasting"})()

        roast_tab.graph_get_data()
        first_window = roast_tab.graphWidget.last_window_max_s

        # Simulate the next tick in the same cycle: elapsed + remaining stays constant.
        elapsed["value"] = 6
        remaining["value"] = 19
        roast_tab.graph_get_data()

        self.assertEqual(first_window, 25)
        self.assertEqual(roast_tab.graphWidget.last_window_max_s, 25)

    def test_graph_get_data_recipe_mode_uses_runtime_cycle_window_when_section_extended(self):
        roast_tab = self._make_roast_tab([10, 20])
        elapsed = {"value": 9}
        remaining = {"value": 30}
        roast_tab._get_roaster_total_time_s = lambda: elapsed["value"]
        roast_tab._get_roaster_time_remaining_s = lambda: remaining["value"]
        roast_tab.roaster = type("R", (), {"get_roaster_state": lambda self: "roasting"})()

        # Recipe boundary at elapsed=9 is 10, but runtime section extension
        # should move the window to elapsed+remaining=39.
        roast_tab.graph_get_data()
        self.assertEqual(roast_tab.graphWidget.last_window_max_s, 39)

        # Next tick in same section keeps a stable horizon as remaining counts down.
        elapsed["value"] = 10
        remaining["value"] = 29
        roast_tab.graph_get_data()
        self.assertEqual(roast_tab.graphWidget.last_window_max_s, 39)


if __name__ == "__main__":
    unittest.main()

