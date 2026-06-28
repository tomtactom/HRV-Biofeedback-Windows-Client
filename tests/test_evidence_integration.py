import unittest

from hrv_evidence import (
    EVIDENCE_MODEL_VERSION,
    compute_evidence_session_recommendation,
    evidence_aftercare_summary,
    evidence_metadata,
    latest_evidence_findings,
)
from hrv_psychology import science_metadata


class EvidenceIntegrationTests(unittest.TestCase):
    def test_latest_findings_include_recent_guidelines_and_2026_rf_comparison(self):
        findings = {item.key: item for item in latest_evidence_findings()}
        self.assertIn("hrv_reporting_guidelines_2024", findings)
        self.assertIn("rf_vs_fixed_2026", findings)
        self.assertIn("mental_disorders_umbrella_2025", findings)
        self.assertIn("0.1", findings["rf_vs_fixed_2026"].product_implication)

    def test_no_rr_recommendation_prioritizes_measurement_quality(self):
        rec = compute_evidence_session_recommendation(sensor_ready=False)
        self.assertEqual(EVIDENCE_MODEL_VERSION, rec.model_version)
        self.assertEqual("quality_before_training", rec.recommendation_id)
        self.assertIn("RR-Datenqualität", rec.visible_hint)
        self.assertIn("keine HRV-Amplitude", rec.measurement_guardrail)

    def test_direct_training_keeps_practice_short_and_primary_signal(self):
        rec = compute_evidence_session_recommendation(
            guided_plan={"plan_id": "direct_training"},
            ratings={"tension": 3, "focus": 7},
            sensor_ready=True,
            signal_quality=0.9,
        )
        self.assertEqual("direct_compact_training", rec.recommendation_id)
        self.assertIn("6–10 Minuten", rec.practice_window)
        self.assertIn("HRV-Amplitudenfeedback", rec.protocol_choice)

    def test_evidence_metadata_is_in_psychology_science_metadata(self):
        metadata = science_metadata()
        self.assertEqual(EVIDENCE_MODEL_VERSION, metadata["evidence_model_version"])
        self.assertIn("latest_evidence", metadata)
        self.assertIn("implemented_findings", metadata["latest_evidence"])

    def test_aftercare_notes_are_conservative(self):
        notes = evidence_aftercare_summary({"valid_rr_count": 20, "artifact_ratio": 0.3, "duration_s": 180})
        joined = "\n".join(notes)
        self.assertIn("Signaltest", joined)
        self.assertIn("keine medizinische Veränderung", joined)


if __name__ == "__main__":
    unittest.main()
