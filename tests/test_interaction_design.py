import unittest

from hrv_interaction_design import (
    INTERACTION_DESIGN_VERSION,
    compute_interaction_profile,
    interaction_design_contract,
    interaction_design_report_text,
)


class InteractionDesignTests(unittest.TestCase):
    def test_stable_training_uses_low_load_circle_first(self):
        profile = compute_interaction_profile(
            phase="training",
            signal_quality=0.9,
            rr_ready=True,
            hrv_amplitude=6.0,
            elapsed_s=120.0,
            focus_key="attention_return",
            calm_visuals_enabled=True,
            reduced_motion=True,
        )
        self.assertEqual(INTERACTION_DESIGN_VERSION, profile.model_version)
        self.assertEqual("circle_first", profile.primary_surface)
        self.assertEqual("low", profile.attention_load)
        self.assertEqual("reduced", profile.motion_policy)
        self.assertIn("Aufmerksamkeit", profile.next_micro_action)

    def test_missing_rr_temporarily_raises_repair_details(self):
        profile = compute_interaction_profile(
            phase="training",
            signal_quality=0.2,
            rr_ready=False,
            hrv_amplitude=None,
            elapsed_s=30.0,
        )
        self.assertEqual("repair", profile.attention_load)
        self.assertEqual("temporarily_visible", profile.detail_policy)
        self.assertIn("Kontakt", profile.next_micro_action)

    def test_contract_names_complementarity_and_adaptivity(self):
        contract = interaction_design_contract()
        self.assertIn("Kreis", contract["primary_rule"])
        self.assertIn("konkurrierende Ziele", contract["complementarity_rule"])
        self.assertIn("Signalproblemen", contract["adaptivity_rule"])

    def test_report_includes_current_profile(self):
        profile = compute_interaction_profile(phase="aftercare")
        report = interaction_design_report_text(profile)
        self.assertIn("Interaktionsdesign", report)
        self.assertIn("Aktuelles Profil", report)
        self.assertIn("Nachbereitung", report)


if __name__ == "__main__":
    unittest.main()
