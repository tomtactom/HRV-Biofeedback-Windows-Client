import unittest

from hrv_adaptive_ui import (
    ADAPTIVE_UI_VERSION,
    complementary_channel_contract,
    compute_training_display_policy,
)


class AdaptiveUiPolicyTests(unittest.TestCase):
    def test_ordinary_training_hides_details_by_default(self):
        policy = compute_training_display_policy(
            phase="training",
            signal_quality=0.88,
            hrv_amplitude=7.2,
            reward_active=True,
            elapsed_s=90.0,
            focus_key="observe_contact",
            user_details_visible=False,
            user_graph_visible=True,
            rr_ready=True,
        )
        self.assertEqual(ADAPTIVE_UI_VERSION, policy.model_version)
        self.assertEqual("focus", policy.display_mode)
        self.assertTrue(policy.show_graph)
        self.assertFalse(policy.show_details)

    def test_signal_problem_shows_details_for_repair(self):
        policy = compute_training_display_policy(
            phase="training",
            signal_quality=0.2,
            hrv_amplitude=None,
            reward_active=False,
            elapsed_s=50.0,
            focus_key="observe_contact",
            user_details_visible=False,
            user_graph_visible=True,
            rr_ready=False,
        )
        self.assertEqual("repair", policy.display_mode)
        self.assertTrue(policy.show_details)
        self.assertIn("Signal", policy.guidance)

    def test_contract_separates_feedback_channels(self):
        contract = complementary_channel_contract()
        self.assertIn("Kreis", contract["primary_feedback_channel"])
        self.assertIn("HRV-Spur", contract["context_channel"])
        self.assertIn("Kein zweites", contract["non_competition_rule"])


if __name__ == "__main__":
    unittest.main()
