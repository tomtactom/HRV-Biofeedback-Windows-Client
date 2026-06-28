"""Bluetooth LE connection strategy for HRV Biofeedback.

This module keeps the BLE connection heuristics UI-free and testable.  It is
based on three practical constraints of the eSense Pulse workflow:

1. HRV feedback needs true RR-Intervals from the standard Heart Rate
   Measurement characteristic (0x2A37); BPM-only packets are not sufficient.
2. Windows/WinRT BLE is sensitive to stale device objects and GATT caching, so
   a fresh advertisement immediately before connect is preferable.
3. The eSense Pulse is a simple low-energy peripheral.  The safest recovery
   actions are non-invasive: rescan, reconnect, wait for GATT settling, and
   guide the user to free the sensor from other apps/devices.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
import re


HR_SERVICE_UUID = "0000180d-0000-1000-8000-00805f9b34fb"
HR_MEASUREMENT_UUID = "00002a37-0000-1000-8000-00805f9b34fb"
BODY_SENSOR_LOCATION_UUID = "00002a38-0000-1000-8000-00805f9b34fb"
BATTERY_SERVICE_UUID = "0000180f-0000-1000-8000-00805f9b34fb"
BATTERY_LEVEL_UUID = "00002a19-0000-1000-8000-00805f9b34fb"
DEVICE_INFORMATION_SERVICE_UUID = "0000180a-0000-1000-8000-00805f9b34fb"
MANUFACTURER_NAME_UUID = "00002a29-0000-1000-8000-00805f9b34fb"
MODEL_NUMBER_UUID = "00002a24-0000-1000-8000-00805f9b34fb"
FIRMWARE_REVISION_UUID = "00002a26-0000-1000-8000-00805f9b34fb"
SERIAL_NUMBER_UUID = "00002a25-0000-1000-8000-00805f9b34fb"

# eSense-specific terms are first; generic HR-device terms make the app useful
# for standard-compatible chest straps during debugging without changing the
# training logic.
ESENSE_DEVICE_TERMS = ("esense", "mindfield", "pulse")
GENERIC_HR_DEVICE_TERMS = ("heart", "hr", "hrm", "cardio", "polar", "h10", "h9", "h7")
ALL_DEVICE_TERMS = ESENSE_DEVICE_TERMS + GENERIC_HR_DEVICE_TERMS

# Scan schedule for a low-friction Auto Connect flow.  The first scan feels
# quick, later scans are long enough to catch slow advertising intervals or a
# sensor that was just clipped onto the chest strap.
AUTO_SCAN_TIMEOUTS_S = (5.5, 8.5, 12.0)


@dataclass(frozen=True)
class CandidateScore:
    """Ranking result for one BLE advertisement."""

    score: int
    label: str
    reasons: tuple[str, ...]
    signal_label: str
    rssi: int | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_uuid(value: Any) -> str:
    """Return lower-case full UUID where possible; keep short UUIDs searchable."""
    text = str(value or "").strip().lower()
    if not text:
        return ""
    # Windows/Bleak can return short UUIDs in manufacturer/service metadata.
    if re.fullmatch(r"0x[0-9a-f]{4}", text):
        text = text[2:]
    if re.fullmatch(r"[0-9a-f]{4}", text):
        return f"0000{text}-0000-1000-8000-00805f9b34fb"
    return text


def clean_device_name(name: Any) -> str:
    """Normalize a BLE name for robust matching across Windows scans."""
    return re.sub(r"\s+", " ", str(name or "").strip()).lower()


def device_service_uuids(device: dict[str, Any]) -> list[str]:
    return [normalize_uuid(x) for x in (device.get("service_uuids") or []) if normalize_uuid(x)]


def has_hr_service(device: dict[str, Any]) -> bool:
    return HR_SERVICE_UUID in device_service_uuids(device)


def has_likely_name(device: dict[str, Any]) -> bool:
    name = clean_device_name(device.get("name"))
    return any(term in name for term in ALL_DEVICE_TERMS)


def has_esense_name(device: dict[str, Any]) -> bool:
    name = clean_device_name(device.get("name"))
    return any(term in name for term in ESENSE_DEVICE_TERMS)


def _rssi_value(device: dict[str, Any]) -> int | None:
    value = device.get("rssi")
    try:
        return int(value) if value is not None else None
    except Exception:
        return None


def rssi_signal_label(rssi: int | None) -> str:
    """Coarse UX-friendly signal interpretation.

    RSSI is noisy and hardware-dependent; the label is deliberately broad and
    should be treated as connection guidance, not distance measurement.
    """
    if rssi is None:
        return "unbekannt"
    if rssi >= -60:
        return "stark"
    if rssi >= -75:
        return "ausreichend"
    if rssi >= -88:
        return "schwach"
    return "sehr schwach"


def score_device_candidate(device: dict[str, Any], *, preferred_address: str = "", preferred_name: str = "") -> CandidateScore:
    """Score a BLE device for automatic HRV-sensor connection."""
    name = clean_device_name(device.get("name"))
    address = str(device.get("address") or "").lower()
    preferred_address = str(preferred_address or "").lower()
    preferred_name_clean = clean_device_name(preferred_name.split(" | ")[0] if preferred_name else "")
    rssi = _rssi_value(device)
    reasons: list[str] = []
    score = 0

    if preferred_address and address == preferred_address:
        score += 120
        reasons.append("zuletzt/aktuell ausgewählte Geräteadresse")
    if preferred_name_clean and name and (name == preferred_name_clean or preferred_name_clean in name or name in preferred_name_clean):
        score += 70
        reasons.append("passender Gerätename")
    if has_hr_service(device):
        score += 90
        reasons.append("Heart-Rate-Service angekündigt")
    if has_esense_name(device):
        score += 85
        reasons.append("eSense/Mindfield/Pulse im Gerätenamen")
    elif has_likely_name(device):
        score += 35
        reasons.append("typischer Herzsensor-Name")

    if rssi is not None:
        # Normalize roughly from -100..-40 dBm into 0..30 points.
        score += max(0, min(30, int((rssi + 100) / 2)))
        reasons.append(f"Signal {rssi_signal_label(rssi)} ({rssi} dBm)")
    else:
        reasons.append("Signalstärke unbekannt")

    if not name or name in {"unknown", "unbekanntes gerät"}:
        score -= 15
        reasons.append("Name nicht eindeutig")

    if score >= 150:
        label = "sehr wahrscheinlich"
    elif score >= 95:
        label = "wahrscheinlich"
    elif score >= 55:
        label = "möglich"
    else:
        label = "unklar"

    return CandidateScore(score=score, label=label, reasons=tuple(reasons), signal_label=rssi_signal_label(rssi), rssi=rssi)


def rank_ble_devices(devices: list[dict[str, Any]], *, preferred_address: str = "", preferred_name: str = "") -> list[dict[str, Any]]:
    """Return devices sorted by HRV-sensor likelihood, with score metadata."""
    ranked: list[dict[str, Any]] = []
    for device in devices or []:
        enriched = dict(device)
        score = score_device_candidate(enriched, preferred_address=preferred_address, preferred_name=preferred_name)
        enriched["connection_score"] = score.score
        enriched["connection_label"] = score.label
        enriched["connection_reasons"] = list(score.reasons)
        enriched["signal_label"] = score.signal_label
        ranked.append(enriched)
    return sorted(
        ranked,
        key=lambda d: (
            -int(d.get("connection_score") or 0),
            -int(d.get("rssi") if isinstance(d.get("rssi"), int) else -999),
            clean_device_name(d.get("name")),
        ),
    )


def select_best_device(devices: list[dict[str, Any]], *, preferred_address: str = "", preferred_name: str = "") -> dict[str, Any] | None:
    ranked = rank_ble_devices(devices, preferred_address=preferred_address, preferred_name=preferred_name)
    return ranked[0] if ranked else None


def is_probable_same_device(device: dict[str, Any], *, address: str = "", name: str = "") -> bool:
    """Return True when a fresh advertisement probably represents the target.

    Address is used first.  Name matching is a fallback for BLE stacks that expose
    a fresh device object differently across scans; it is only accepted when the
    device is also plausible as an HR sensor.
    """
    if address and str(device.get("address") or "").lower() == str(address).lower():
        return True
    target_name = clean_device_name(name.split(" | ")[0] if name else "")
    current_name = clean_device_name(device.get("name"))
    if not target_name or not current_name:
        return False
    name_match = target_name == current_name or target_name in current_name or current_name in target_name
    return bool(name_match and (has_hr_service(device) or has_likely_name(device)))


def body_sensor_location_label(value: int | None) -> str:
    mapping = {
        0: "other",
        1: "chest",
        2: "wrist",
        3: "finger",
        4: "hand",
        5: "ear_lobe",
        6: "foot",
    }
    return mapping.get(value, "unknown") if value is not None else "unknown"


def decode_gatt_text(raw: bytes | bytearray | None) -> str:
    if raw is None:
        return ""
    data = bytes(raw)
    for encoding in ("utf-8", "latin-1"):
        try:
            return data.decode(encoding).strip("\x00\r\n\t ")
        except Exception:
            continue
    return data.hex()


def service_dump_has_characteristic(service_dump: dict[str, Any], uuid: str) -> bool:
    uuid = normalize_uuid(uuid)
    for service in service_dump.get("services", []) or []:
        for char in service.get("characteristics", []) or []:
            if normalize_uuid(char.get("uuid")) == uuid:
                return True
    return False


def summarize_candidates_for_user(devices: list[dict[str, Any]]) -> str:
    """Short German summary for status dialogs."""
    if not devices:
        return "Kein BLE-Gerät sichtbar. Sensor aktivieren, nah an den Laptop bringen und erneut automatisch verbinden."
    best = rank_ble_devices(devices)[0]
    reasons = "; ".join(best.get("connection_reasons") or [])
    return f"Wahrscheinlichstes Gerät: {best.get('name') or 'Unbekannt'} · {best.get('connection_label')} · {reasons}"
