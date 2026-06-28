from pathlib import Path
import tempfile
import unittest

from hrv_adaptation import (
    ADAPTATION_MODEL_VERSION,
    current_preparation_compass,
    evaluate_double_loop,
    format_double_loop_review,
    load_recent_double_loop_review,
)


class DoubleLoopAdaptationTests(unittest.TestCase):
    def test_missing_rr_prioritizes_signal(self):
        review = evaluate_double_loop(summary={"row_count": 0, "valid_rr_count": 0})
        data = review.to_dict()
        self.assertEqual(ADAPTATION_MODEL_VERSION, data["model_version"])
        self.assertEqual("sensor_rr_check", data["next_session_plan"]["primary_next_step"])
        self.assertIn("RR-Datenbasis fehlt", data["assumption_status"]["measurement_first"])

    def test_good_session_can_suggest_optional_baseline_skip(self):
        review = evaluate_double_loop(summary={
            "row_count": 300,
            "valid_rr_count": 290,
            "artifact_ratio": 0.02,
            "reward_count": 8,
            "duration_s": 600,
            "mean_hrv_amplitude_60s": 6.0,
            "mean_score": 0.7,
        })
        self.assertFalse(review.next_session_plan["suggested_baseline"])
        self.assertEqual("training", review.next_session_plan["primary_next_step"])

    def test_compass_is_user_facing_and_nonempty(self):
        text = current_preparation_compass(
            {"tension": 8, "focus": 5, "energy": 5, "body_contact": 5},
            sensor_ready=True,
            recent_review=None,
            focus_key="observe_contact",
        )
        self.assertIn("Baseline", text)
        self.assertIn("Lernschleife", text)

    def test_format_review_contains_suggestions(self):
        review = evaluate_double_loop(summary={"row_count": 100, "valid_rr_count": 75, "artifact_ratio": 0.25})
        text = format_double_loop_review(review)
        self.assertIn("Lernschleife", text)
        self.assertIn("Kontaktphase", text)

    def test_load_recent_review_from_reflection(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.reflection.json"
            path.write_text('{"double_loop_learning":{"model_version":"x","next_session_plan":{"compass_text":"abc"}}}', encoding="utf-8")
            loaded = load_recent_double_loop_review(Path(tmp))
            self.assertIsNotNone(loaded)
            self.assertEqual("x", loaded["model_version"])


if __name__ == "__main__":
    unittest.main()
