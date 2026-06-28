import unittest

from hrv_ble_state import BleConnectionState, BleStateMachine
from hrv_product_contract import (
    PRIMARY_VISIBLE_SIGNAL,
    PRODUCT_CORE_SUMMARY,
    VISIBLE_PHASES,
    visible_training_contract,
)


class ProductConsolidationTests(unittest.TestCase):
    def test_visible_contract_has_one_primary_signal(self):
        contract = visible_training_contract()
        self.assertEqual("HRV-Amplitude", PRIMARY_VISIBLE_SIGNAL)
        self.assertEqual("HRV-Amplitude", contract["primary_signal"])
        self.assertEqual(["Vorbereitung", "Training", "Nachbereitung"], list(VISIBLE_PHASES))
        self.assertIn("Ein Hauptsignal", PRODUCT_CORE_SUMMARY)
        self.assertIn("Komplementäre Kanäle", PRODUCT_CORE_SUMMARY)

    def test_ble_state_separates_connected_from_rr_ready(self):
        state = BleStateMachine()
        state.transition(BleConnectionState.CONNECTING, "Verbinde")
        self.assertFalse(state.snapshot.rr_ready)
        state.transition(BleConnectionState.WAITING_FOR_RR, "GATT ok")
        state.note_packet(rr_values=0, bpm_only=True)
        self.assertFalse(state.snapshot.rr_ready)
        tone, label = state.user_label()
        self.assertEqual("active", tone)
        self.assertIn("RR", label)
        state.note_packet(rr_values=2)
        self.assertTrue(state.snapshot.rr_ready)
        self.assertEqual(BleConnectionState.STREAMING, state.snapshot.state)
        self.assertEqual(("good", "BLE: RR aktiv"), state.user_label())

    def test_ble_state_snapshot_is_exportable(self):
        state = BleStateMachine()
        state.transition("failed", "Fehler", error="timeout")
        data = state.snapshot.to_dict()
        self.assertEqual("failed", data["state"])
        self.assertEqual("timeout", data["last_error"])
        self.assertIn("state_age_s", data)


if __name__ == "__main__":
    unittest.main()
