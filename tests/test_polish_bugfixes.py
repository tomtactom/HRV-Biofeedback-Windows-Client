import math
import unittest

from hrv_core import RR_MAX_MS, RR_MIN_MS, sanitize_rr_values
from hrv_visual_feedback import calm_graph_y_range, graph_display_metadata, smooth_display_series


class FrontendBackendPolishTests(unittest.TestCase):
    def test_sanitize_rr_values_filters_malformed_packet_values(self):
        values = sanitize_rr_values([820, "900.5", None, float("nan"), RR_MIN_MS - 1, RR_MAX_MS + 1, object()])
        self.assertEqual(values, [820.0, 900.5])
        self.assertEqual(sanitize_rr_values(750), [750.0])
        self.assertEqual(sanitize_rr_values(None), [])

    def test_visual_series_drops_non_finite_values(self):
        series = smooth_display_series([1.0, float("nan"), "2", float("inf"), 3.0], enabled=False)
        self.assertEqual(series, [1.0, 2.0, 3.0])
        smoothed = smooth_display_series([1.0, None, 2.0, 3.0], enabled=True, alpha=0.5)
        self.assertEqual(len(smoothed), 3)
        self.assertTrue(all(math.isfinite(v) for v in smoothed))

    def test_graph_range_tolerates_invalid_previous_axis(self):
        display_range = calm_graph_y_range([None, float("nan")], previous_y_max=float("nan"))
        self.assertEqual(display_range.reason, "no_data")
        self.assertGreaterEqual(display_range.y_max, 3.0)
        metadata = graph_display_metadata(calm_visuals_enabled=True, pyqtgraph_available=False)
        self.assertTrue(metadata["invalid_display_values_are_dropped"])

    def test_no_data_stop_path_resets_phase_view_and_plot_state_in_code(self):
        text = __import__("pathlib").Path(__file__).resolve().parents[1].joinpath("main.py").read_text(encoding="utf-8")
        self.assertIn('self._sync_phase_view()\n            self._update_controls()\n            self._update_header_state()\n            self.statusBar().showMessage("Keine Sitzungsdaten zum Speichern.")', text)
        self.assertIn('self._plot_y_max = 3.0', text)

    def test_bpm_only_counter_does_not_count_empty_packets_in_code(self):
        text = __import__("pathlib").Path(__file__).resolve().parents[1].joinpath("main.py").read_text(encoding="utf-8")
        self.assertIn("rr_values = sanitize_rr_values(raw_rr_values)", text)
        self.assertIn("if bpm_only:\n                    self.ble_hr_only_packet_count += 1", text)


if __name__ == "__main__":
    unittest.main()
