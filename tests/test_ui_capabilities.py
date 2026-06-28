import unittest

from hrv_ui_capabilities import (
    UI_CAPABILITY_VERSION,
    capability_metadata,
    detect_library_capabilities,
    recommended_ui_opportunities,
)
from hrv_visual_feedback import VISUAL_FEEDBACK_VERSION, calm_graph_y_range, smooth_display_series


class UiCapabilitiesTests(unittest.TestCase):
    def test_capability_map_contains_core_libraries(self):
        caps = detect_library_capabilities()
        names = {cap.name for cap in caps}
        self.assertIn("PySide6 / Qt for Python", names)
        self.assertIn("pyqtgraph", names)
        self.assertTrue(any(cap.integration_level == "core" for cap in caps))

    def test_metadata_is_serializable_shape(self):
        meta = capability_metadata()
        self.assertEqual(UI_CAPABILITY_VERSION, meta["ui_capability_version"])
        self.assertGreaterEqual(len(meta["libraries"]), 5)
        self.assertGreaterEqual(len(meta["opportunities"]), 3)

    def test_recommended_opportunities_prioritize_calm_graph(self):
        opportunities = recommended_ui_opportunities()
        self.assertIn("HRV", opportunities[0].title)
        self.assertIn("pyqtgraph", opportunities[0].source)

    def test_visual_smoothing_is_display_only_shape(self):
        raw = [1.0, 5.0, 1.0]
        smoothed = smooth_display_series(raw, enabled=True, alpha=0.5)
        self.assertEqual(len(raw), len(smoothed))
        self.assertEqual(raw[0], smoothed[0])
        self.assertLess(smoothed[1], raw[1])
        self.assertEqual(raw, [1.0, 5.0, 1.0])

    def test_calm_graph_range_contracts_slowly(self):
        expanded = calm_graph_y_range([1.0, 10.0], previous_y_max=3.0)
        contracted = calm_graph_y_range([1.0, 2.0], previous_y_max=expanded.y_max)
        self.assertEqual(VISUAL_FEEDBACK_VERSION, "0.34-calm-hrv-graph-polish")
        self.assertGreater(expanded.y_max, 3.0)
        self.assertGreater(contracted.y_max, 3.0)
        self.assertIn(contracted.reason, {"slow_contract", "expanding"})


if __name__ == "__main__":
    unittest.main()
