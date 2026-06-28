import unittest

from hrv_psychology import (
    RATING_FIELDS,
    aftercare_transfer_suggestions,
    build_reflection_payload,
    learning_protocol,
    micro_practice_plan,
    preparation_readiness,
    rating_change,
    training_focus_cue,
    training_guidance,
)


class PsychologyProtocolTests(unittest.TestCase):
    def test_rating_change_uses_shared_fields(self):
        pre = {key: 5 for key in RATING_FIELDS}
        post = dict(pre)
        post["focus"] = 7
        change = rating_change(pre, post)
        self.assertEqual(change["focus"], 2)
        self.assertEqual(set(change), set(RATING_FIELDS))

    def test_training_guidance_names_signal_check(self):
        text = training_guidance(phase="training", signal_quality=0.2)
        self.assertIn("Signal", text)

    def test_reflection_payload_contains_transfer_suggestions(self):
        payload = build_reflection_payload(
            pre_ratings={"tension": 6, "focus": 4, "energy": 5, "body_contact": 5},
            post_ratings={"tension": 4, "focus": 6, "energy": 6, "body_contact": 7},
            notes="beobachtet",
            summary={"artifact_ratio": 0.0, "reward_count": 2, "mean_hrv_amplitude_60s": 6.0},
        )
        self.assertEqual(payload["rating_change"]["tension"], -2)
        self.assertTrue(payload["transfer_suggestions"])
        self.assertIn("phase_protocol", payload)
        self.assertIn("learning_protocol", payload)
        self.assertTrue(payload["micro_practice_plan"])

    def test_preparation_readiness_reacts_to_low_contact(self):
        readiness = preparation_readiness({"tension": 5, "focus": 5, "energy": 5, "body_contact": 2}, sensor_ready=False)
        self.assertTrue(any("Kontakt" in item or "Gurt" in item for item in readiness["suggestions"]))

    def test_training_focus_cue_changes_over_time(self):
        cue_a = training_focus_cue(phase="training", signal_quality=0.8, hrv_amplitude=4.0, elapsed_s=10)
        cue_b = training_focus_cue(phase="training", signal_quality=0.8, hrv_amplitude=4.0, elapsed_s=160)
        self.assertNotEqual(cue_a, cue_b)

    def test_learning_protocol_has_interpretation_boundary(self):
        protocol = learning_protocol()
        self.assertIn("keine Diagnosen", protocol.interpretation_boundary)

    def test_micro_practice_plan_mentions_two_minutes(self):
        plan = micro_practice_plan({"reward_count": 1, "artifact_ratio": 0.0})
        self.assertTrue(any("2-Minuten" in item for item in plan))

    def test_transfer_suggestions_react_to_artifacts(self):
        suggestions = aftercare_transfer_suggestions({"artifact_ratio": 0.5})
        self.assertTrue(any("Kontakt" in item for item in suggestions))


if __name__ == "__main__":
    unittest.main()

class EvidenceInformedPsychologyTests(unittest.TestCase):
    def test_learning_focus_options_are_exportable(self):
        from hrv_psychology import learning_focus_options, science_metadata
        options = learning_focus_options()
        self.assertGreaterEqual(len(options), 4)
        metadata = science_metadata()
        self.assertIn("foundation", metadata)
        self.assertIn("learning_focus_options", metadata)

    def test_implementation_intention_uses_focus(self):
        from hrv_psychology import implementation_intention
        sentence = implementation_intention({"artifact_ratio": 0.0}, "daily_transfer", "ich den Laptop schließe")
        self.assertTrue(sentence.startswith("Wenn"))
        self.assertIn("dann", sentence)
        self.assertIn("2 Minuten", sentence)
