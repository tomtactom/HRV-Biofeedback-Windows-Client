import math
import unittest

from hrv_core import (
    FeedbackEngine,
    HrvProcessor,
    parse_heart_rate_measurement,
    rmssd_ms,
    sdnn_ms,
    summarize_session,
)
from hrv_sem import (
    compute_sem_latents,
    compute_sem_live_feedback,
    estimate_sem_paths_from_segments,
    rows_to_sem_segments,
    sem_model_info,
)


class HeartRateParserTests(unittest.TestCase):
    def test_parse_rr_intervals(self):
        # Flags: RR present, 8-bit HR. HR=60. RR raw=1024 -> 1000 ms.
        packet = bytes([0x10, 60, 0x00, 0x04])
        parsed = parse_heart_rate_measurement(packet)
        self.assertEqual(parsed.bpm, 60)
        self.assertEqual(len(parsed.rr_ms), 1)
        self.assertAlmostEqual(parsed.rr_ms[0], 1000.0)

    def test_parse_empty_packet(self):
        parsed = parse_heart_rate_measurement(b"")
        self.assertIsNone(parsed.bpm)
        self.assertEqual(parsed.rr_ms, [])

    def test_parse_malformed_packet_is_safe(self):
        parsed = parse_heart_rate_measurement(None)
        self.assertIsNone(parsed.bpm)
        self.assertEqual(parsed.rr_ms, [])
        parsed = parse_heart_rate_measurement(bytes([0x01, 0x3C]))
        self.assertIsNone(parsed.bpm)
        self.assertEqual(parsed.rr_ms, [])


class MetricTests(unittest.TestCase):
    def test_time_domain_metrics(self):
        rr = [1000, 1010, 990, 1005]
        self.assertGreater(rmssd_ms(rr), 0)
        self.assertGreater(sdnn_ms(rr), 0)

    def test_processor_recovers_from_sustained_rr_jump(self):
        proc = HrvProcessor()
        first = proc.add_rr(1.0, 1000.0, "training")
        self.assertTrue(first.rr_valid)
        # A single large jump is treated as an artifact. Consecutive stable
        # values in the new range are accepted to avoid artifact lockout.
        rows = [proc.add_rr(float(i), 620.0 + (i % 2), "training") for i in range(2, 6)]
        self.assertFalse(rows[0].rr_valid)
        self.assertTrue(any(r.rr_valid for r in rows[2:]))

    def test_processor_and_feedback(self):
        proc = HrvProcessor()
        feedback = FeedbackEngine()
        proc.use_default_baseline()
        last = None
        for i in range(1, 120):
            rr = 900 + 70 * math.sin(i / 4)
            last = proc.add_rr(float(i), rr, "training")
            last = feedback.update(last, "training")
        self.assertIsNotNone(last)
        self.assertGreaterEqual(last.hrv_score, 0.0)
        self.assertLessEqual(last.hrv_score, 1.0)
        self.assertGreaterEqual(last.feedback_strength, 0.0)
        self.assertLessEqual(last.feedback_strength, 1.0)
        self.assertAlmostEqual(last.sem_feedback_target, last.feedback_strength, delta=0.25)
        self.assertGreaterEqual(last.signal_quality, 0.0)
        self.assertLessEqual(last.signal_quality, 1.0)
        self.assertIsNotNone(last.sem_feedback_target)
        self.assertIsNotNone(last.sem_live_confidence)

    def test_summary_handles_empty(self):
        self.assertEqual(summarize_session([]), {})


class SemLatentModelTests(unittest.TestCase):
    def test_sem_latents_are_bounded(self):
        scores = compute_sem_latents(
            hrv_amplitude_60s=10.0,
            rmssd_30s=40.0,
            sdnn_60s=50.0,
            regularity_20s=0.8,
            coherence_90s=0.4,
            signal_quality=0.9,
            rr_valid=True,
            hrv_score=0.7,
            circle_radius=0.6,
            reward_active=True,
        )
        self.assertIn("sem_integrated_self_regulation", scores)
        for value in scores.values():
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 1.0)

    def test_sem_segments_and_path_summary(self):
        proc = HrvProcessor()
        feedback = FeedbackEngine()
        proc.use_default_baseline()
        rows = []
        for i in range(1, 260):
            rr = 900 + 75 * math.sin(i / 7)
            m = proc.add_rr(float(i), rr, "training")
            rows.append(feedback.update(m, "training"))
        segments = rows_to_sem_segments(rows, segment_s=60.0)
        self.assertGreaterEqual(len(segments), 4)
        self.assertIn("mean_sem_live_confidence", segments[0])
        path_summary = estimate_sem_paths_from_segments(segments)
        self.assertIn("status", path_summary)
        self.assertIn("model_syntax", sem_model_info())


class SemLiveFeedbackTests(unittest.TestCase):
    def test_sem_live_feedback_gates_low_quality(self):
        state = compute_sem_live_feedback(
            autonomic_flexibility=0.8,
            measurement_quality=0.2,
            hrv_score=0.9,
            phase="training",
        )
        self.assertEqual(state["sem_gate_reason"], "low_measurement_quality")
        self.assertEqual(state["sem_feedback_target"], 0.0)

    def test_sem_live_feedback_allows_training_with_quality(self):
        state = compute_sem_live_feedback(
            autonomic_flexibility=0.75,
            measurement_quality=0.9,
            hrv_score=0.65,
            phase="training",
        )
        self.assertGreater(state["sem_feedback_target"], 0.0)
        self.assertGreaterEqual(state["sem_live_confidence"], 0.0)
        self.assertLessEqual(state["sem_live_confidence"], 1.0)


if __name__ == "__main__":
    unittest.main()

from hrv_diagnostics import (
    build_ble_diagnostic_report,
    classify_ble_error,
    select_best_device,
    sort_devices_for_connection,
)


class BleDiagnosticsTests(unittest.TestCase):
    def test_device_sorting_prefers_hr_service(self):
        devices = [
            {"name": "Keyboard", "address": "1", "rssi": -30, "service_uuids": []},
            {"name": "eSense Pulse", "address": "2", "rssi": -70, "service_uuids": ["0000180d-0000-1000-8000-00805f9b34fb"]},
        ]
        ordered = sort_devices_for_connection(devices)
        self.assertEqual(ordered[0]["address"], "2")
        self.assertEqual(select_best_device(devices)["address"], "2")

    def test_ble_diagnostic_report_is_serializable_shape(self):
        report = build_ble_diagnostic_report(
            devices=[],
            selected_device="",
            selected_address="",
            last_error="Timeout while connecting",
            include_windows_snapshot=False,
        )
        self.assertIn("checks", report)
        self.assertIn("suggestions", report)
        self.assertGreaterEqual(len(report["checks"]), 1)

    def test_classify_ble_error(self):
        category, suggestion = classify_ble_error("Kein standardisierter Heart Rate Measurement Service (0x2A37) gefunden")
        self.assertEqual(category, "no_standard_hr_service")
        self.assertIn("LSL", suggestion)

    def test_classify_gatt_service_error(self):
        category, suggestion = classify_ble_error("BLE-Verbindung steht, aber die GATT-Services konnten nicht gelesen werden")
        self.assertEqual(category, "gatt_service_read_failed")
        self.assertIn("Bluetooth", suggestion)

from hrv_windows import collect_windows_bluetooth_snapshot, qbytearray_to_b64, b64_to_qbytearray


class WindowsIntegrationHelperTests(unittest.TestCase):
    def test_windows_bluetooth_snapshot_shape(self):
        snapshot = collect_windows_bluetooth_snapshot()
        self.assertIn("platform", snapshot)
        self.assertIn("available", snapshot)

    def test_qbytearray_helpers_tolerate_empty_values(self):
        self.assertEqual(qbytearray_to_b64(None), "")
        self.assertIsNone(b64_to_qbytearray(""))

from hrv_diagnostics import describe_ble_error, should_auto_recover_ble_error


class BleSelfHealingPolicyTests(unittest.TestCase):
    def test_describe_no_sensor_data(self):
        info = describe_ble_error("BLE verbunden, aber keine Live-Daten empfangen")
        self.assertEqual(info["category"], "no_sensor_data")
        self.assertTrue(info["can_auto_recover"])
        self.assertIn("Kontakt", info["user_action"])

    def test_no_standard_hr_service_does_not_auto_recover(self):
        message = "Kein standardisierter Heart Rate Measurement Service (0x2A37) gefunden"
        self.assertFalse(should_auto_recover_ble_error(message))

class BleTechnologyHardeningTests(unittest.TestCase):
    def test_parser_multiple_rr_intervals_and_contact(self):
        # Flags: 8-bit HR + sensor contact supported/detected + RR present.
        packet = bytes([0x16, 72, 0x00, 0x04, 0x20, 0x04])
        parsed = parse_heart_rate_measurement(packet)
        self.assertEqual(parsed.bpm, 72)
        self.assertTrue(parsed.contact_supported)
        self.assertTrue(parsed.contact_detected)
        self.assertEqual(len(parsed.rr_ms), 2)
        self.assertAlmostEqual(parsed.rr_ms[0], 1000.0)
        self.assertAlmostEqual(parsed.rr_ms[1], 1031.25)

    def test_classify_no_rr_intervals(self):
        info = describe_ble_error("BLE verbunden, aber keine RR-Intervalle empfangen")
        self.assertEqual(info["category"], "no_rr_intervals")
        self.assertIn("LSL", info["user_action"])

    def test_classify_paired_or_busy(self):
        category, suggestion = classify_ble_error("Sensor vermutlich durch andere App oder Smartphone belegt")
        self.assertEqual(category, "paired_or_busy")
        self.assertIn("Smartphone", suggestion)

from hrv_core import run_core_self_test
from hrv_security import redact_text, redact_obj, create_redacted_support_bundle
from hrv_windows import summarize_windows_bluetooth_snapshot
from pathlib import Path
import tempfile
import zipfile


class SecurityAndSelfTestTests(unittest.TestCase):
    def test_redact_text_masks_ble_address_and_home(self):
        text = r"C:\Users\Tom Uni\Documents\HRV Biofeedback E5:88:3A:97:3E:FD raw"
        redacted = redact_text(text)
        self.assertIn("<BLE_ADDRESS>", redacted)
        self.assertNotIn("E5:88:3A:97:3E:FD", redacted)
        self.assertIn("%USERPROFILE%", redacted)

    def test_redact_obj_masks_address_keys(self):
        obj = {"address": "E5:88:3A:97:3E:FD", "nested": ["Device E5:88:3A:97:3E:FD"]}
        redacted = redact_obj(obj)
        self.assertEqual(redacted["address"], "<REDACTED>")
        self.assertIn("<BLE_ADDRESS>", redacted["nested"][0])

    def test_support_bundle_is_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            debug = root / "debug"
            logs = root / "logs"
            debug.mkdir()
            logs.mkdir()
            (logs / "app.log").write_text("Device E5:88:3A:97:3E:FD", encoding="utf-8")
            (debug / "ble_diagnostics.json").write_text('{"address":"E5:88:3A:97:3E:FD"}', encoding="utf-8")
            out = create_redacted_support_bundle(
                output_path=root / "support.zip",
                app_snapshot={"path": r"C:\Users\Tom Uni\x"},
                debug_dir=debug,
                logs_dir=logs,
            )
            self.assertTrue(out.exists())
            with zipfile.ZipFile(out) as zf:
                joined = "\n".join(zf.read(name).decode("utf-8") for name in zf.namelist() if name.endswith((".json", ".txt")))
            self.assertNotIn("E5:88:3A:97:3E:FD", joined)

    def test_core_self_test_shape(self):
        report = run_core_self_test()
        self.assertIn("checks", report)
        self.assertIn("ok", report)

    def test_windows_snapshot_summary_shape(self):
        summary = summarize_windows_bluetooth_snapshot({"available": False, "reason": "not_windows"})
        self.assertFalse(summary["available"])

    def test_windows_trigger_start_services_are_notes_not_warnings(self):
        snapshot = {
            "available": True,
            "bthserv": {"ok": True, "stdout": '{"Status":4,"Name":"bthserv","StartType":3}', "stderr": ""},
            "device_association_service": {"ok": True, "stdout": '{"Status":4,"Name":"DeviceAssociationService","StartType":3}', "stderr": ""},
            "bluetooth_pnp": {"ok": True, "stdout": '[{"Status":"OK","FriendlyName":"Intel Bluetooth"}]', "stderr": ""},
        }
        summary = summarize_windows_bluetooth_snapshot(snapshot)
        self.assertEqual(summary["status"], "ok")
        self.assertTrue(summary.get("notes"))

from hrv_ble_strategy import (
    HR_SERVICE_UUID,
    AUTO_SCAN_TIMEOUTS_S,
    body_sensor_location_label,
    decode_gatt_text,
    is_probable_same_device,
    rank_ble_devices,
    score_device_candidate,
)


class BleStrategyTests(unittest.TestCase):
    def test_candidate_scoring_prefers_esense_with_hr_service(self):
        devices = [
            {"name": "Bluetooth Mouse", "address": "1", "rssi": -45, "service_uuids": []},
            {"name": "eSense Pulse", "address": "2", "rssi": -78, "service_uuids": [HR_SERVICE_UUID]},
        ]
        ranked = rank_ble_devices(devices)
        self.assertEqual(ranked[0]["address"], "2")
        self.assertGreater(ranked[0]["connection_score"], ranked[1]["connection_score"])

    def test_probable_same_device_by_name_and_hr_profile(self):
        dev = {"name": "eSense Pulse", "address": "fresh", "rssi": -60, "service_uuids": [HR_SERVICE_UUID]}
        self.assertTrue(is_probable_same_device(dev, address="old", name="eSense Pulse | old"))

    def test_optional_gatt_decoders(self):
        self.assertEqual(body_sensor_location_label(1), "chest")
        self.assertEqual(decode_gatt_text(b"Mindfield\x00"), "Mindfield")
        self.assertGreaterEqual(len(AUTO_SCAN_TIMEOUTS_S), 2)
        score = score_device_candidate({"name": "Unknown", "address": "x", "rssi": None, "service_uuids": []})
        self.assertIn(score.label, {"unklar", "möglich", "wahrscheinlich", "sehr wahrscheinlich"})
