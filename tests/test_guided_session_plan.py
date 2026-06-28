import unittest

from hrv_guided_session import (
    GUIDED_SESSION_VERSION,
    compute_guided_session_plan,
    guided_session_contract,
)


class GuidedSessionPlanTests(unittest.TestCase):
    def test_no_rr_prioritizes_sensor_preparation(self):
        plan = compute_guided_session_plan(sensor_ready=False, ble_packet_count=0, ble_rr_value_count=0)
        self.assertEqual(GUIDED_SESSION_VERSION, plan.model_version)
        self.assertEqual("prepare_sensor", plan.plan_id)
        self.assertTrue(plan.show_details_preferred)
        self.assertIn("RR-Datenbasis", plan.preparation_hint)

    def test_bpm_without_rr_blocks_training(self):
        plan = compute_guided_session_plan(sensor_ready=False, ble_packet_count=8, ble_rr_value_count=0)
        self.assertEqual("repair_rr_stream", plan.plan_id)
        self.assertEqual("warn", plan.tone)
        self.assertIn("RR-Intervalle fehlen", plan.preparation_hint)

    def test_recent_good_session_can_suggest_direct_training(self):
        plan = compute_guided_session_plan(
            sensor_ready=True,
            ble_rr_value_count=30,
            signal_quality=0.9,
            ratings={"tension": 4, "focus": 6, "body_contact": 7},
            recent_review={"next_session_plan": {"primary_next_step": "training"}},
        )
        self.assertEqual("direct_training", plan.plan_id)
        self.assertFalse(plan.baseline_recommended)
        self.assertFalse(plan.show_details_preferred)

    def test_high_load_keeps_baseline(self):
        plan = compute_guided_session_plan(
            sensor_ready=True,
            ble_rr_value_count=20,
            signal_quality=0.8,
            ratings={"tension": 9, "focus": 5, "body_contact": 5},
        )
        self.assertEqual("settle_then_train", plan.plan_id)
        self.assertTrue(plan.baseline_recommended)

    def test_contract_protects_primary_signal(self):
        contract = guided_session_contract()
        self.assertEqual("HRV-Amplitude", contract["primary_signal"])
        self.assertIn("nicht das Hauptfeedbacksignal", contract["core_rule"])


if __name__ == "__main__":
    unittest.main()
