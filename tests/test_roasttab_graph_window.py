import unittest

from openroast.views.roasttab import RoastTab


class _FakeRecipes:
    def __init__(self, section_times=None):
        self._section_times = section_times or []

    def check_recipe_loaded(self):
        return bool(self._section_times)

    def get_num_recipe_sections(self):
        return len(self._section_times)

    def get_section_duration(self, index):
        return self._section_times[index]

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


if __name__ == "__main__":
    unittest.main()

