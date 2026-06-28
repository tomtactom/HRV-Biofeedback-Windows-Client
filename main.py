"""
HRV Biofeedback - compact Windows desktop prototype for eSense Pulse HRV biofeedback.

Version 0.35 startup/menu bugfix:
- German Windows desktop UI with calm medical-psychological dashboard layout
- system / dark / light appearance switch and optional focus mode
- normal window + fullscreen via F11 / menu
- first-run introduction and connection assistant
- Windows 11 high-DPI/display handling, shortcuts and persisted window geometry
- simplified onboarding, status/diagnostics hub and clearer BLE recovery flow
- BLE self-healing: fresh advertisement scan, Windows GATT timing delays, uncached service discovery, bounded reconnects
- action-oriented BLE diagnostics, self-healing recovery and Heart Rate Service debug export
- redacted support bundle export and local self-test
- direct BLE Heart Rate Measurement parser when UUID 0x2A37 is available
- mock RR input for UI and feedback development
- 10-minute reference session, 10-minute training session, 180-second baseline, skip baseline
- phase-specific preparation/training/aftercare guidance and subjective check-ins
- research metadata sidecar with expert details kept out of the training view
- adaptive guided session plan for preparation, training and aftercare
- explicit product contract, BLE state machine and reusable UI components
- library capability audit and calm display-only HRV graph rendering
- sensory-load aware interaction design with reduced-motion policy
- startup/menu bugfix: restored menu action targets, safe layout reset and static UI contract tests
- green circle feedback with signal/threshold/reward states
- optional beep reward audio, off by default
- CSV session export to ~/Documents/HRV Biofeedback/sessions
- local BLE debug export to ~/Documents/HRV Biofeedback/debug
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import math
import random
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QKeySequence, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QStackedWidget,
    QSizePolicy,
    QStatusBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

try:
    import pyqtgraph as pg
except Exception:  # pragma: no cover - optional runtime fallback
    pg = None

from hrv_product_contract import (
    APP_PRODUCT_CONTRACT_VERSION,
    PHASE_LABELS,
    PRODUCT_CORE_SUMMARY,
    visible_training_contract,
)
from hrv_ble_state import BleConnectionState, BleStateMachine
from hrv_adaptive_ui import (
    ADAPTIVE_UI_VERSION,
    complementary_channel_contract,
    compute_training_display_policy,
)
from hrv_guided_session import (
    GUIDED_SESSION_VERSION,
    compute_guided_session_plan,
    guided_session_contract,
)

from hrv_evidence import (
    EVIDENCE_MODEL_VERSION,
    compute_evidence_session_recommendation,
    evidence_aftercare_summary,
    evidence_metadata,
)
from hrv_ui_capabilities import (
    UI_CAPABILITY_VERSION,
    capability_metadata,
    capability_report_text,
)
from hrv_visual_feedback import (
    VISUAL_FEEDBACK_VERSION,
    calm_graph_y_range,
    graph_display_metadata,
    smooth_display_series,
)
from hrv_interaction_design import (
    INTERACTION_DESIGN_VERSION,
    compute_interaction_profile,
    interaction_design_contract,
    interaction_design_report_text,
)
from ui_components import Card, FeedbackCircle, MetricCard, RatingScale, RoleCard, StatusPill, WorkflowStep

from hrv_diagnostics import (
    build_ble_diagnostic_report,
    classify_ble_error,
    describe_ble_error,
    diagnostic_report_to_text,
    sort_devices_for_connection,
)

from hrv_ble_strategy import (
    AUTO_SCAN_TIMEOUTS_S,
    BATTERY_LEVEL_UUID,
    BODY_SENSOR_LOCATION_UUID,
    FIRMWARE_REVISION_UUID,
    MANUFACTURER_NAME_UUID,
    MODEL_NUMBER_UUID,
    SERIAL_NUMBER_UUID,
    body_sensor_location_label,
    decode_gatt_text,
    is_probable_same_device,
    rank_ble_devices,
    select_best_device as select_best_ble_device,
    service_dump_has_characteristic,
    summarize_candidates_for_user,
)

from hrv_windows import (
    b64_to_qbytearray,
    center_and_fit_window,
    collect_display_snapshot,
    configure_qt_for_windows,
    detect_windows_app_theme,
    open_path_or_uri,
    open_windows_settings,
    qbytearray_to_b64,
)

from hrv_core import (
    APP_NAME,
    APP_VERSION,
    DEBUG_DIR,
    LOG_FILE,
    LOGS_DIR,
    CONFIG_PATH,
    HR_MEASUREMENT_UUID,
    HRVB_PROTOCOL_TYPES,
    HrvMetrics,
    HrvProcessor,
    FeedbackEngine,
    JsonlWriter,
    sanitize_rr_values,
    SESSIONS_DIR,
    app_system_snapshot,
    build_session_metadata,
    cleanup_runtime_files,
    default_session_context,
    ensure_data_dirs,
    install_global_exception_hooks,
    log_exception,
    load_config,
    now_stamp,
    run_core_self_test,
    parse_heart_rate_measurement,
    save_config,
    save_json,
    setup_logging,
    summarize_session,
    write_session_csv,
    write_session_metadata,
)

from hrv_sem import (
    estimate_sem_paths_from_segments,
    rows_to_sem_segments,
    write_sem_segments_csv,
)

from hrv_security import create_redacted_support_bundle


from hrv_adaptation import (
    ADAPTATION_MODEL_VERSION,
    current_preparation_compass,
    evaluate_double_loop,
    format_double_loop_review,
    load_recent_double_loop_review,
)

from hrv_psychology import (
    RATING_FIELDS,
    PSYCHOLOGY_MODEL_VERSION,
    aftercare_change_summary,
    aftercare_transfer_suggestions,
    autonomy_supportive_reason,
    build_reflection_payload,
    implementation_intention,
    learning_focus_options,
    learning_focus_by_key,
    learning_protocol,
    micro_practice_plan,
    phase_protocol,
    preparation_science_prompts,
    preparation_summary_text,
    psychological_foundation,
    science_metadata,
    training_focus_cue,
    training_guidance,
)


BASELINE_SECONDS = 180
REFERENCE_SECONDS = 600
TRAINING_SECONDS = 600
MOCK_TIMER_MS = 120
BLE_AUTO_RECOVERY_MAX_ATTEMPTS = 3
BLE_CONNECT_ATTEMPTS = 3
BLE_PREFLIGHT_SCAN_SECONDS = 4.5
BLE_SERVICE_SETTLE_SECONDS = 1.35
BLE_FIRST_PACKET_TIMEOUT_S = 28.0
BLE_FIRST_RR_TIMEOUT_S = 40.0
BLE_STALE_DATA_TIMEOUT_S = 18.0
BLE_STREAM_STALE_FATAL_S = 42.0
BLE_RR_STALE_FATAL_S = 36.0



class BleNonRecoverableError(RuntimeError):
    """BLE condition where reconnecting cannot create missing sensor capability."""


class BleWorker(QThread):
    """Qt worker around bleak so the GUI remains responsive."""

    status = Signal(str)
    scan_finished = Signal(list)
    packet_received = Signal(dict)
    services_finished = Signal(dict)
    error = Signal(str)

    def __init__(
        self,
        mode: str,
        address: str | None = None,
        parent: QWidget | None = None,
        *,
        target_name: str = "",
        scan_timeout: float = 7.0,
    ):
        super().__init__(parent)
        self.mode = mode
        self.address = address
        self.target_name = target_name
        self.scan_timeout = float(scan_timeout)
        self._stop_requested = False
        self._client = None
        self._raw_writer: Optional[JsonlWriter] = None
        self.logger = logging.getLogger("hrv_biofeedback.ble")

    def stop(self) -> None:
        self._stop_requested = True

    def run(self) -> None:  # noqa: D401 - Qt entrypoint
        try:
            asyncio.run(self._run_async())
        except Exception as exc:  # pragma: no cover - hardware/runtime dependent
            log_exception(self.logger, "BLE worker crashed", exc)
            self.error.emit("BLE-Aufgabe wurde unerwartet beendet. Details stehen in der Logdatei.")
        finally:
            if self._raw_writer:
                self._raw_writer.close()
                self._raw_writer = None

    async def _run_async(self) -> None:
        try:
            from bleak import BleakClient, BleakScanner
        except Exception as exc:
            log_exception(self.logger, "bleak import failed", exc)
            self.error.emit("Python-Paket 'bleak' ist nicht installiert oder konnte nicht geladen werden. Details stehen in der Logdatei.")
            return

        if self.mode == "scan":
            self.logger.info("BLE scan started")
            self.status.emit(f"BLE-Scan läuft ({self.scan_timeout:.0f} s) ...")
            try:
                devices = await BleakScanner.discover(timeout=self.scan_timeout, return_adv=True)
            except Exception as exc:  # pragma: no cover - hardware/runtime dependent
                log_exception(self.logger, "BLE scan failed", exc)
                self.error.emit(
                    "BLE-Scan konnte nicht abgeschlossen werden. Die automatische Diagnose wurde vorbereitet."
                )
                return

            found: list[dict[str, Any]] = []
            for _key, value in devices.items():
                device, adv = value
                found.append(
                    {
                        "name": device.name or "Unbekanntes Gerät",
                        "address": device.address,
                        "rssi": getattr(adv, "rssi", None),
                        "metadata": getattr(device, "metadata", {}),
                        "service_uuids": list(getattr(adv, "service_uuids", []) or []),
                    }
                )
            found = sort_devices_for_connection(found)
            save_json(DEBUG_DIR / f"ble_scan_{now_stamp()}.json", found)
            self.logger.info("BLE scan finished | devices=%s", len(found))
            self.scan_finished.emit(found)
            self.status.emit(f"BLE-Scan abgeschlossen: {len(found)} Geräte gefunden")
            return

        if self.mode != "connect" or not self.address:
            self.error.emit("Interner BLE-Fehler: kein gültiger Modus oder keine Adresse.")
            return

        self.logger.info("BLE connect requested | address=%s", self.address)
        self.status.emit(f"Verbinde mit {self.address} ...")
        self._raw_writer = JsonlWriter(DEBUG_DIR / f"raw_packets_{now_stamp()}.jsonl")

        # A complete BLE session has several failure points on Windows 11:
        # discovery object lookup, connection, GATT service discovery and notify
        # subscription.  Each step is retried inside this worker before the GUI
        # receives one actionable error.  This keeps the user flow simple and
        # avoids a chain of modal dialogs for transient Bluetooth issues.
        last_exc: BaseException | None = None
        attempt_count = BLE_CONNECT_ATTEMPTS
        for attempt in range(1, attempt_count + 1):
            if self._stop_requested:
                self.status.emit("BLE-Verbindung abgebrochen.")
                return
            try:
                await self._connect_stream_once(BleakClient, BleakScanner, attempt=attempt, attempt_count=attempt_count)
                return
            except BleNonRecoverableError as exc:  # pragma: no cover - hardware/runtime dependent
                log_exception(self.logger, "BLE non-recoverable connect issue", exc)
                self.error.emit(self._format_worker_error(exc))
                return
            except Exception as exc:  # pragma: no cover - hardware/runtime dependent
                last_exc = exc
                log_exception(self.logger, f"BLE connect attempt {attempt}/{attempt_count} failed", exc)
                if self._stop_requested:
                    self.status.emit("BLE-Verbindung abgebrochen.")
                    return
                if attempt < attempt_count:
                    self.status.emit(
                        f"BLE-Verbindung nicht stabil ({attempt}/{attempt_count}). "
                        "Ich scanne kurz neu und versuche es erneut ..."
                    )
                    await asyncio.sleep(1.2 + attempt * 0.9)

        if last_exc is not None:
            self.error.emit(self._format_worker_error(last_exc))
        else:
            self.error.emit("BLE-Verbindung nicht möglich. Diagnosebericht und Logdatei prüfen.")

    async def _connect_stream_once(self, BleakClient: Any, BleakScanner: Any, *, attempt: int, attempt_count: int) -> None:
        """Connect once, discover services and stream Heart Rate notifications.

        Windows 11/WinRT BLE stacks can expose a timing-sensitive GATT path:
        a device may be visible in advertisements, connect successfully, and
        still return an empty/unreachable service table when queried too early.
        This method therefore performs a short fresh advertisement scan before
        connecting, lets the connection settle, reads services with escalating
        waits, and only then subscribes to Heart Rate notifications.
        """
        self.status.emit(f"BLE-Verbindungsversuch {attempt}/{attempt_count}: Gerät suchen ...")
        target = await self._find_fresh_target(BleakScanner, timeout=BLE_PREFLIGHT_SCAN_SECONDS)
        connect_target = target or self.address

        client = self._make_bleak_client(BleakClient, connect_target, uncached_services=True)
        async with client:
            self._client = client
            if not client.is_connected:
                raise RuntimeError("BLE-Verbindung konnte nicht hergestellt werden.")

            self.status.emit("Verbunden. Warte kurz auf stabile GATT-Services ...")
            await asyncio.sleep(BLE_SERVICE_SETTLE_SECONDS + 0.35 * max(0, attempt - 1))

            self.status.emit("Lese GATT-Services ...")
            services = await self._read_services_with_retries(client, attempts=5)
            service_dump = self._dump_services(services)
            await self._enrich_service_dump_with_optional_reads(client, service_dump)
            save_json(DEBUG_DIR / f"ble_services_{now_stamp()}_attempt{attempt}.json", service_dump)
            self.services_finished.emit(service_dump)

            notify_uuid = self._find_hr_measurement_uuid(service_dump)
            if not notify_uuid:
                raise BleNonRecoverableError(
                    "Kein standardisierter Heart Rate Measurement Service (0x2A37) gefunden. "
                    "Die Service-Debugdatei wurde gespeichert."
                )

            self.status.emit("Heart Rate Measurement gefunden. Abonniere Live-Daten ...")
            packet_count = 0
            rr_packet_count = 0
            hr_only_packet_count = 0
            last_packet_monotonic = time.monotonic()
            last_rr_monotonic = time.monotonic()
            soft_hint_sent = False
            rr_hint_sent = False

            def handle_notification(_sender: Any, data: bytearray) -> None:
                nonlocal last_packet_monotonic, last_rr_monotonic, packet_count, rr_packet_count, hr_only_packet_count
                try:
                    last_packet_monotonic = time.monotonic()
                    packet_count += 1
                    raw = bytes(data)
                    parsed = parse_heart_rate_measurement(raw)
                    if parsed.rr_ms:
                        rr_packet_count += 1
                        last_rr_monotonic = time.monotonic()
                    elif parsed.bpm is not None:
                        hr_only_packet_count += 1
                    payload = asdict(parsed)
                    payload["time"] = time.time()
                    payload["source"] = "ble_heart_rate_measurement"
                    if self._raw_writer:
                        self._raw_writer.write(payload)
                    self.packet_received.emit(payload)
                except Exception as exc:  # pragma: no cover - hardware/runtime dependent
                    log_exception(self.logger, "BLE notification could not be processed", exc)

            try:
                await client.start_notify(notify_uuid, handle_notification)
            except Exception as exc:  # pragma: no cover - hardware/runtime dependent
                raise RuntimeError("BLE verbunden, aber Heart-Rate-Benachrichtigungen konnten nicht abonniert werden.") from exc

            self.status.emit("BLE verbunden. Warte auf RR-Intervalle ...")
            try:
                while not self._stop_requested and client.is_connected:
                    await asyncio.sleep(0.2)
                    now = time.monotonic()
                    since_packet = now - last_packet_monotonic
                    since_rr = now - last_rr_monotonic
                    if packet_count == 0 and since_packet > BLE_FIRST_PACKET_TIMEOUT_S:
                        raise RuntimeError(
                            "BLE verbunden, aber keine Live-Daten empfangen. "
                            "Kontakt/Gurt prüfen, andere Apps trennen und Sensor wach halten."
                        )
                    if packet_count > 0 and rr_packet_count == 0 and since_rr > BLE_FIRST_RR_TIMEOUT_S:
                        raise RuntimeError(
                            "BLE verbunden, aber keine RR-Intervalle empfangen. "
                            "Für HRV-Biofeedback werden RR-Intervalle aus dem Heart-Rate-Measurement benötigt. "
                            "Andere Apps trennen; falls nur Herzrate sichtbar bleibt, LSL/OSC als Eingang prüfen."
                        )
                    if packet_count > 0 and rr_packet_count == 0 and hr_only_packet_count >= 8 and not rr_hint_sent:
                        rr_hint_sent = True
                        self.status.emit("BLE liefert Herzrate, aber noch keine RR-Intervalle. Warte weiter ...")
                    if packet_count > 0 and since_packet > BLE_STALE_DATA_TIMEOUT_S and not soft_hint_sent:
                        soft_hint_sent = True
                        self.status.emit("BLE verbunden, aber zuletzt keine neuen Werte. Kontakt/Sensor prüfen.")
                    if packet_count > 0 and since_packet > BLE_STREAM_STALE_FATAL_S:
                        raise RuntimeError(
                            "BLE-Datenstrom ist stehen geblieben. Die App startet eine sichere Neuverbindung. "
                            "Kontakt, Abstand und parallele Apps prüfen."
                        )
                    if rr_packet_count > 0 and since_rr > BLE_RR_STALE_FATAL_S:
                        raise RuntimeError(
                            "RR-Datenstrom ist abgebrochen. Die App startet eine sichere Neuverbindung. "
                            "Für HRV-Biofeedback werden fortlaufende RR-Intervalle benötigt."
                        )
            finally:
                try:
                    await client.stop_notify(notify_uuid)
                except Exception:
                    pass
                self.status.emit("BLE-Verbindung beendet.")

    async def _find_fresh_target(self, BleakScanner: Any, *, timeout: float) -> Any:
        """Return a fresh BLEDevice object from current advertisements.

        Windows/WinRT can keep stale BLE objects in its cache.  Bleak's own
        troubleshooting guidance recommends scanning first and passing the
        returned BLEDevice object into BleakClient.  The method prefers the
        exact address, then a safe name/service match if the address presented
        differently in the current advertisement cycle.
        """
        if not self.address:
            return None
        try:
            found = await BleakScanner.discover(timeout=timeout, return_adv=True)
            candidates: list[dict[str, Any]] = []
            device_by_address: dict[str, Any] = {}
            device_by_key: dict[str, Any] = {}
            normalized_address = str(self.address).lower()
            for key, value in found.items():
                device, adv = value
                address = str(getattr(device, "address", ""))
                item = {
                    "name": getattr(device, "name", "") or "Unbekanntes Gerät",
                    "address": address,
                    "rssi": getattr(adv, "rssi", None),
                    "metadata": getattr(device, "metadata", {}),
                    "service_uuids": list(getattr(adv, "service_uuids", []) or []),
                }
                candidates.append(item)
                device_by_address[address.lower()] = device
                device_by_key[f"{item['name']}|{address}".lower()] = device
                if address.lower() == normalized_address:
                    self.logger.debug(
                        "Fresh BLE advertisement matched address | name=%s address=%s rssi=%s services=%s",
                        item["name"], address, item["rssi"], item["service_uuids"],
                    )
                    return device

            ranked = rank_ble_devices(candidates, preferred_address=self.address, preferred_name=self.target_name)
            if ranked:
                best = ranked[0]
                if is_probable_same_device(best, address=self.address, name=self.target_name) or int(best.get("connection_score") or 0) >= 120:
                    key = f"{best.get('name')}|{best.get('address')}".lower()
                    self.logger.debug(
                        "Fresh BLE advertisement matched by profile | name=%s address=%s score=%s reasons=%s",
                        best.get("name"), best.get("address"), best.get("connection_score"), best.get("connection_reasons"),
                    )
                    return device_by_address.get(str(best.get("address", "")).lower()) or device_by_key.get(key)
        except Exception as exc:
            self.logger.debug("Fresh advertisement scan before connect failed; fallback to address | %s", exc)
        try:
            return await BleakScanner.find_device_by_address(self.address, timeout=max(2.0, timeout))
        except Exception as exc:
            self.logger.debug("BLEDevice lookup before connect failed; fallback to address | %s", exc)
            return None

    async def _enrich_service_dump_with_optional_reads(self, client: Any, service_dump: dict[str, Any]) -> None:
        """Read optional low-risk characteristics for diagnostics.

        These reads are deliberately best-effort.  They add useful context such
        as battery level, body location and firmware/model identifiers, but a
        read failure must never block Heart Rate Measurement notifications.
        """
        optional = service_dump.setdefault("optional_reads", {})

        async def read_if_present(uuid: str, key: str, *, decoder: str = "text") -> None:
            if not service_dump_has_characteristic(service_dump, uuid):
                return
            try:
                raw = await self._read_gatt_char_uncached(client, uuid)
                if decoder == "battery":
                    optional[key] = int(raw[0]) if raw else None
                elif decoder == "body_location":
                    value = int(raw[0]) if raw else None
                    optional[key] = {"code": value, "label": body_sensor_location_label(value)}
                else:
                    optional[key] = decode_gatt_text(raw)
            except Exception as exc:
                optional[f"{key}_error"] = f"{type(exc).__name__}: {exc}"

        await read_if_present(BATTERY_LEVEL_UUID, "battery_level_percent", decoder="battery")
        await read_if_present(BODY_SENSOR_LOCATION_UUID, "body_sensor_location", decoder="body_location")
        await read_if_present(MANUFACTURER_NAME_UUID, "manufacturer_name")
        await read_if_present(MODEL_NUMBER_UUID, "model_number")
        await read_if_present(FIRMWARE_REVISION_UUID, "firmware_revision")
        await read_if_present(SERIAL_NUMBER_UUID, "serial_number")

    @staticmethod
    async def _read_gatt_char_uncached(client: Any, uuid: str) -> bytes:
        read = getattr(client, "read_gatt_char")
        try:
            result = read(uuid, use_cached=False)
        except TypeError:
            result = read(uuid)
        value = await result if inspect.isawaitable(result) else result
        return bytes(value)

    @staticmethod
    def _make_bleak_client(BleakClient: Any, target: Any, *, uncached_services: bool) -> Any:
        """Create a BleakClient with Windows-friendly, non-pairing options.

        The eSense Pulse is expected to be used as a BLE GATT sensor.  Pairing
        dialogs can make the UX brittle on Windows, so the app explicitly asks
        Bleak not to pair when the installed Bleak version supports it.  Older
        Bleak releases are handled by progressively falling back to simpler
        constructor signatures.
        """
        timeout_s = 30.0 if sys.platform.startswith("win") else 20.0
        attempts: list[dict[str, Any]] = []
        if sys.platform.startswith("win"):
            attempts.append({"timeout": timeout_s, "pair": False, "winrt": {"use_cached_services": not uncached_services}})
            attempts.append({"timeout": timeout_s, "winrt": {"use_cached_services": not uncached_services}})
        attempts.append({"timeout": timeout_s, "pair": False})
        attempts.append({"timeout": timeout_s})
        last_exc: TypeError | None = None
        for kwargs in attempts:
            try:
                return BleakClient(target, **kwargs)
            except TypeError as exc:
                last_exc = exc
                continue
        if last_exc is not None:
            raise last_exc
        return BleakClient(target)

    @staticmethod
    def _format_worker_error(exc: BaseException) -> str:
        text = f"{type(exc).__name__}: {exc}"
        lower = text.lower()
        if "0x2a37" in lower or "heart rate measurement" in lower:
            return "Kein standardisierter Heart Rate Measurement Service (0x2A37) gefunden. Service-Debugdatei prüfen; ggf. LSL/OSC als Eingang verwenden."
        if "gatt" in lower or "service" in lower:
            return "BLE-Verbindung steht, aber die GATT-Services konnten nicht zuverlässig gelesen werden. Andere Apps/Smartphones trennen, Sensor wach halten und Auto verbinden erneut ausführen."
        if "notify" in lower or "benachrichtig" in lower or "abonn" in lower:
            return "BLE verbunden, aber Heart-Rate-Benachrichtigungen konnten nicht abonniert werden. Andere Apps trennen und Auto verbinden erneut ausführen."
        if "keine rr-intervalle" in lower:
            return "BLE verbunden, aber keine RR-Intervalle empfangen. Andere Apps trennen; falls nur Herzrate sichtbar bleibt, LSL/OSC als Eingang prüfen."
        if "keine live-daten" in lower or "no heart-rate" in lower or "keine rr" in lower:
            return "BLE verbunden, aber keine Live-Daten empfangen. Kontakt/Gurt prüfen, Elektroden anfeuchten, andere Apps trennen und erneut verbinden."
        return f"BLE-Verbindung nicht möglich: {text}"

    async def _read_services_with_retries(self, client: Any, attempts: int = 3) -> Any:
        """Read GATT services across Bleak versions and WinRT timing quirks.

        Newer Bleak versions expose `client.services`; older versions used
        `await client.get_services()`. On Windows 11 the service table can need
        a short settling time after connection. Empty service collections are
        treated as "not ready yet" and retried before an error is surfaced.
        """
        last_exc: Exception | None = None
        last_empty = False
        for attempt in range(1, attempts + 1):
            try:
                services = getattr(client, "services", None)
                if services is not None:
                    try:
                        service_list = list(services)
                        if service_list:
                            return services
                        last_empty = True
                    except Exception:
                        # Some Bleak service containers are iterable only once or
                        # perform lazy lookups. Returning here is safer than
                        # converting again and accidentally losing the collection.
                        return services

                get_services = getattr(client, "get_services", None)
                if callable(get_services):
                    result = get_services()
                    services = await result if inspect.isawaitable(result) else result
                    try:
                        if len(list(services)) == 0:
                            last_empty = True
                        else:
                            return services
                    except Exception:
                        return services
            except Exception as exc:  # pragma: no cover - hardware/runtime dependent
                last_exc = exc
                self.logger.debug("BLE service read attempt %s/%s failed: %s", attempt, attempts, exc)
            await asyncio.sleep(0.65 * attempt)

        if last_exc is not None:
            raise last_exc
        if last_empty:
            raise RuntimeError("GATT service discovery returned an empty service table")
        raise RuntimeError("No GATT service API available on BleakClient")

    @staticmethod
    def _dump_services(services: Any) -> dict[str, Any]:
        out: dict[str, Any] = {"services": []}
        for service in services:
            service_entry = {
                "uuid": str(service.uuid).lower(),
                "description": getattr(service, "description", ""),
                "characteristics": [],
            }
            for char in service.characteristics:
                service_entry["characteristics"].append(
                    {
                        "uuid": str(char.uuid).lower(),
                        "description": getattr(char, "description", ""),
                        "properties": list(getattr(char, "properties", []) or []),
                    }
                )
            out["services"].append(service_entry)
        return out

    @staticmethod
    def _find_hr_measurement_uuid(service_dump: dict[str, Any]) -> str | None:
        for service in service_dump.get("services", []):
            for char in service.get("characteristics", []):
                uuid = char.get("uuid", "").lower()
                props = set(char.get("properties", []))
                if uuid == HR_MEASUREMENT_UUID and (("notify" in props or "indicate" in props) or not props):
                    return uuid
        return None




class SessionContextDialog(QDialog):
    """Small dialog for HRVB reporting/context variables."""

    def __init__(self, context: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Kontextangaben")
        self.setMinimumWidth(540)
        self._context = dict(context)

        layout = QVBoxLayout(self)
        intro = QLabel("Diese Angaben werden lokal in der Metadaten-Datei der Sitzung gespeichert.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        layout.addLayout(form)

        self.body_position = QComboBox()
        self.body_position.addItems(["sitting", "sitting_not_confirmed", "standing", "lying", "not_recorded"])
        self._set_combo_value(self.body_position, str(self._context.get("body_position", "sitting_not_confirmed")))
        form.addRow("Körperposition", self.body_position)

        self.eyes = QComboBox()
        self.eyes.addItems(["open", "closed", "open_inferred_from_screen_feedback", "not_recorded"])
        self._set_combo_value(self.eyes, str(self._context.get("eyes", "open_inferred_from_screen_feedback")))
        form.addRow("Augen", self.eyes)

        self.room_light = QComboBox()
        self.room_light.addItems(["normal", "dim", "bright", "dark", "not_recorded"])
        self._set_combo_value(self.room_light, str(self._context.get("room_light", "not_recorded")))
        form.addRow("Raumlicht", self.room_light)

        self.room_noise = QComboBox()
        self.room_noise.addItems(["quiet", "moderate", "noisy", "not_recorded"])
        self._set_combo_value(self.room_noise, str(self._context.get("room_noise", "not_recorded")))
        form.addRow("Raumgeräusch", self.room_noise)

        self.room_temperature = QLineEdit(str(self._context.get("room_temperature", "not_recorded")))
        form.addRow("Raumtemperatur", self.room_temperature)

        self.notes = QTextEdit(str(self._context.get("notes", "")))
        self.notes.setPlaceholderText("Optional: kurze Beobachtung zur Sitzung, z.B. Tagesform, Setting, Unterbrechungen.")
        self.notes.setMinimumHeight(110)
        form.addRow("Notizen", self.notes)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _set_combo_value(combo: QComboBox, value: str) -> None:
        idx = combo.findText(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def context(self) -> dict[str, Any]:
        out = dict(self._context)
        out.update(
            {
                "body_position": self.body_position.currentText(),
                "eyes": self.eyes.currentText(),
                "room_light": self.room_light.currentText(),
                "room_noise": self.room_noise.currentText(),
                "room_temperature": self.room_temperature.text().strip() or "not_recorded",
                "notes": self.notes.toPlainText().strip(),
            }
        )
        return out


class IntroductionDialog(QDialog):
    """First-run introduction for a calm setup path."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Einführung")
        self.setMinimumSize(640, 520)
        self.choice = "close"

        layout = QVBoxLayout(self)
        title = QLabel("HRV Biofeedback einrichten")
        title.setObjectName("PanelTitle")
        layout.addWidget(title)

        text = QTextEdit()
        text.setReadOnly(True)
        text.setHtml(
            "<h3>Willkommen</h3>"
            "<p>Diese App liest RR-Intervalle eines BLE-Herzfrequenzgeräts aus, berechnet HRV-nahe Live-Werte "
            "und zeigt eine ruhige visuelle Rückmeldung.</p>"
            "<h3>Erster sinnvoller Ablauf</h3>"
            "<ol>"
            "<li>Mit <b>Mock Start</b> die Oberfläche ohne Sensor testen.</li>"
            "<li>eSense Pulse anlegen, Kontakt prüfen und andere Apps trennen.</li>"
            "<li><b>Auto verbinden</b> nutzen. Die App scannt mehrstufig, wählt den besten Kandidaten und versucht eine stabile GATT-Verbindung.</li>"
            "<li>Bei Verbindungsproblemen die automatische Bluetooth-Diagnose öffnen.</li>"
            "<li>Training starten; die Baseline kann übersprungen werden.</li>"
            "</ol>"
            "<h3>Lokale Daten</h3>"
            "<p>Sitzungen, Debugdateien und Logs werden lokal unter Dokumente/HRV Biofeedback gespeichert. "
            "Die App nimmt keine medizinische Bewertung vor.</p>"
        )
        layout.addWidget(text, 1)

        self.do_not_show = QCheckBox("Beim nächsten Start nicht automatisch anzeigen")
        layout.addWidget(self.do_not_show)

        buttons = QHBoxLayout()
        self.assistant_button = QPushButton("Verbindungsassistent")
        self.mock_button = QPushButton("Mock-Test starten")
        self.close_button = QPushButton("Schließen")
        buttons.addWidget(self.assistant_button)
        buttons.addWidget(self.mock_button)
        buttons.addStretch(1)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)

        self.assistant_button.clicked.connect(lambda: self._finish("assistant"))
        self.mock_button.clicked.connect(lambda: self._finish("mock"))
        self.close_button.clicked.connect(lambda: self._finish("close"))

    def _finish(self, choice: str) -> None:
        self.choice = choice
        self.accept()


class ConnectionAssistantDialog(QDialog):
    """Action-oriented dialog for scan/connect troubleshooting."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Verbindungsassistent")
        self.setMinimumSize(680, 520)
        self.choice = "close"

        layout = QVBoxLayout(self)
        title = QLabel("eSense Pulse verbinden")
        title.setObjectName("PanelTitle")
        layout.addWidget(title)

        text = QTextEdit()
        text.setReadOnly(True)
        text.setHtml(
            "<h3>Vorbereitung</h3>"
            "<ul>"
            "<li>Brustgurt anlegen und Elektroden/Kontaktstellen befeuchten.</li>"
            "<li>Sensor in die Nähe des Laptops bringen.</li>"
            "<li>Andere Apps oder Smartphones, die bereits verbunden sind, kurz trennen.</li>"
            "<li>Windows Bluetooth eingeschaltet lassen; bei eSense/HRV-Sensoren nicht zuerst in Windows koppeln, sondern direkt in der App verbinden.</li>"
            "</ul>"
            "<h3>Empfohlene Verbindung</h3>"
            "<ol>"
            "<li><b>Auto verbinden</b> führt mehrere sichere Schritte aus: Scan, Kandidatenbewertung, frischer Advertisement-Check, GATT-Service-Lesen und Live-RR-Prüfung.</li>"
            "<li>Wenn kein Gerät sichtbar ist, verlängert die App den Scan automatisch. Danach zeigt die Diagnose konkrete nächste Schritte.</li>"
            "<li>Wenn GATT-Services nicht gelesen werden: andere Apps/Smartphones trennen, Bluetooth kurz aus/ein schalten und erneut Auto verbinden.</li>"
            "<li>Wenn das Gerät sichtbar ist, aber keine RR-Werte liefert: Kontakt prüfen; Service-Debug prüfen; ggf. LSL/OSC später nutzen.</li>"
            "</ol>"
        )
        layout.addWidget(text, 1)

        buttons = QHBoxLayout()
        actions = [
            ("auto", "Auto verbinden"),
            ("scan", "Scan starten"),
            ("diagnostics", "Diagnose ausführen"),
            ("close", "Schließen"),
        ]
        for value, label in actions:
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, v=value: self._finish(v))
            buttons.addWidget(button)
        layout.addLayout(buttons)

    def _finish(self, choice: str) -> None:
        self.choice = choice
        self.accept()


class BleDiagnosticsDialog(QDialog):
    """Read-only BLE diagnostic report dialog."""

    def __init__(self, report_text: str, report_path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Bluetooth-Diagnose")
        self.setMinimumSize(760, 560)
        layout = QVBoxLayout(self)
        info = QLabel(f"Diagnosebericht gespeichert: {report_path}")
        info.setWordWrap(True)
        layout.addWidget(info)
        text = QTextEdit()
        text.setReadOnly(True)
        text.setPlainText(report_text)
        layout.addWidget(text, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)



class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        ensure_data_dirs()
        self.logger = logging.getLogger("hrv_biofeedback.gui")
        self.logger.info("MainWindow initializing")
        self.config = load_config()
        self.setWindowTitle(APP_NAME)
        self.resize(1360, 900)
        self.setMinimumSize(1120, 760)

        self.processor = HrvProcessor()
        self.sem_live_enabled = bool(self.config.get("background_model_enabled", self.config.get("sem_live_enabled", True)))
        self.feedback = FeedbackEngine(sem_live_enabled=self.sem_live_enabled)
        self.session_rows: list[HrvMetrics] = []
        self.phase = "idle"
        self.previous_phase = "idle"
        self.session_start_monotonic: float | None = None
        self.session_duration_s: Optional[float] = None
        self.feedback_mode = "green_circle"
        self.protocol_type = "individual_hrvb_no_pacer"
        self.input_mode = "unknown"
        self.device_identifier = ""
        self.audio_enabled = bool(self.config.get("audio_enabled", False))
        self.appearance = str(self.config.get("appearance", "system"))
        self.focus_mode = bool(self.config.get("focus_mode", False))
        self.plot_visible = bool(self.config.get("plot_visible", True))
        # Calm visuals are display-only. Raw RR/HRV data in exports are not smoothed.
        self.calm_visuals_enabled = bool(self.config.get("calm_visuals_enabled", True))
        # Reduced motion is the safe Windows/default path for a psychophysiological
        # training surface. It affects UI policy only, never the measured data.
        self.reduced_motion_enabled = bool(self.config.get("reduced_motion_enabled", True))
        # Numeric training details are a complementary channel. They stay hidden
        # during ordinary training and are shown on request or for signal repair.
        self.training_details_visible = bool(self.config.get("training_details_visible", False))
        self._last_adaptive_display_policy: dict[str, Any] = {}
        self._last_interaction_profile: dict[str, Any] = {}
        self._last_guided_session_plan: dict[str, Any] = {}
        self._last_evidence_session_recommendation: dict[str, Any] = {}
        self.session_context = default_session_context()
        self.session_context.update(self.config.get("session_context", {}))
        self.last_session_csv_path: Optional[Path] = None
        self.last_session_summary: dict[str, Any] = {}
        self.last_reflection_path: Optional[Path] = None
        self.recent_double_loop_review = load_recent_double_loop_review(SESSIONS_DIR)
        self.last_double_loop_review: dict[str, Any] | None = self.recent_double_loop_review
        self.paused_total_s = 0.0
        self.pause_started_monotonic: float | None = None

        self.ble_worker: Optional[BleWorker] = None
        self.ble_state = BleStateMachine()
        self.devices: list[dict[str, Any]] = []
        self.last_ble_error = ""
        self.last_service_dump: dict[str, Any] = {}
        self.last_ble_packet_monotonic: float | None = None
        self.last_ble_rr_monotonic: float | None = None
        self.ble_packet_count = 0
        self.ble_rr_packet_count = 0
        self.ble_rr_value_count = 0
        self.ble_hr_only_packet_count = 0
        self.last_ble_bpm: float | None = None
        self.last_ble_rr_ms: float | None = None
        self.last_ble_stream_hint = "—"
        self.pending_auto_connect = False
        self.auto_scan_pass = 0
        self.ble_auto_recovery_attempts = 0
        self._screen_signal_connected = False

        self.mock_timer = QTimer(self)
        self.mock_timer.timeout.connect(self._mock_tick)
        self.mock_next_beat_s = 0.0
        self.mock_last_beat_s = 0.0

        self.ui_timer = QTimer(self)
        self.ui_timer.timeout.connect(self._ui_tick)
        self.ui_timer.start(500)

        self._last_reward_active = False
        self._last_metrics = HrvMetrics()
        # HRV graph stores only the primary feedback signal.  BPM and composite
        # scores are intentionally not plotted to keep the live view calm and
        # cognitively focused during training.
        self._plot_elapsed: list[float] = []
        self._plot_hrv_amp: list[float] = []
        self._plot_y_max: float = 3.0

        self._build_ui()
        self._build_menus()
        self.apply_appearance(self.appearance)
        self._restore_window_layout()
        self._set_focus_mode(self.focus_mode, save=False)
        self._set_plot_visible(self.plot_visible, save=False)
        self._set_calm_visuals_enabled(self.calm_visuals_enabled, save=False)
        self._set_reduced_motion_enabled(self.reduced_motion_enabled, save=False)
        self._set_training_details_visible(self.training_details_visible, save=False)
        self._update_controls()
        self._update_header_state()
        self.statusBar().showMessage(f"Bereit. Datenordner: {Path.home() / 'Documents' / APP_NAME}")
        self.logger.info("MainWindow initialized | data_dir=%s", Path.home() / "Documents" / APP_NAME)
        QTimer.singleShot(0, self._connect_screen_signals)
        QTimer.singleShot(350, self._maybe_show_first_run_introduction)

    def _build_ui(self) -> None:
        """Build the phase-based application interface.

        The primary workspace is split into exactly three mutually exclusive
        views: preparation, training and aftercare.  This reduces split-attention
        in the critical live-feedback moment and keeps all preparation/diagnosis
        controls outside the training field.
        """
        central = QWidget(self)
        central.setObjectName("WindowRoot")
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.dashboard_scroll = QScrollArea()
        self.dashboard_scroll.setWidgetResizable(True)
        self.dashboard_scroll.setFrameShape(QFrame.NoFrame)
        self.dashboard_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(self.dashboard_scroll, 1)

        content = QWidget()
        content.setObjectName("AppRoot")
        self.dashboard_scroll.setWidget(content)
        root = QVBoxLayout(content)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(12)

        # Orientation header -------------------------------------------------
        self.header = Card("HeaderCard")
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(20, 14, 20, 14)
        header_layout.setSpacing(18)
        root.addWidget(self.header)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel(APP_NAME)
        title.setObjectName("AppTitle")
        subtitle = QLabel("Geführtes HRV-Biofeedback · eSense Pulse · lokale Sitzungen")
        subtitle.setObjectName("AppSubtitle")
        self.next_step_label = QLabel("Nächster Schritt: Sensor vorbereiten oder Training im Mock-Test ausprobieren.")
        self.next_step_label.setObjectName("NextStepLabel")
        self.next_step_label.setWordWrap(True)
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        title_box.addWidget(self.next_step_label)
        header_layout.addLayout(title_box, 1)

        self.phase_pill = StatusPill("Bereit")
        self.input_pill = StatusPill("Input: —")
        self.quality_pill = StatusPill("Signal: —")
        self.view_pill = StatusPill("Vorbereitung")
        self.timer_label = QLabel("00:00")
        self.timer_label.setObjectName("TimerLabel")
        for widget in [self.view_pill, self.phase_pill, self.input_pill, self.quality_pill, self.timer_label]:
            header_layout.addWidget(widget)

        # Three exclusive phase pages ---------------------------------------
        self.phase_stack = QStackedWidget()
        self.phase_stack.setObjectName("PhaseStack")
        root.addWidget(self.phase_stack, 1)

        # PREPARATION --------------------------------------------------------
        self.preparation_page = QWidget()
        self.preparation_page.setObjectName("PhasePage")
        prep = QVBoxLayout(self.preparation_page)
        prep.setContentsMargins(0, 0, 0, 0)
        prep.setSpacing(12)

        prep_hero = Card("HeroCard")
        hero_layout = QHBoxLayout(prep_hero)
        hero_layout.setContentsMargins(22, 18, 22, 18)
        hero_layout.setSpacing(18)
        hero_text = QVBoxLayout()
        hero_text.setSpacing(6)
        hero_title = QLabel("Vorbereitung")
        hero_title.setObjectName("PhaseTitle")
        hero_subtitle = QLabel("Ein klarer Ablauf: Sensor vorbereiten, kurz einordnen, Training starten.")
        hero_subtitle.setObjectName("PhaseSubtitle")
        hero_subtitle.setWordWrap(True)
        hero_text.addWidget(hero_title)
        hero_text.addWidget(hero_subtitle)
        hero_layout.addLayout(hero_text, 1)
        hero_action = QPushButton("Sensor vorbereiten")
        hero_action.setObjectName("PrimaryButton")
        hero_action.setMinimumHeight(44)
        hero_layout.addWidget(hero_action)
        prep.addWidget(prep_hero)

        prep_grid = QGridLayout()
        prep_grid.setHorizontalSpacing(12)
        prep_grid.setVerticalSpacing(12)
        prep.addLayout(prep_grid, 1)

        device_card = RoleCard("Sensor vorbereiten", "Ein Hauptbutton prüft Sensor, Verbindung und RR-Daten. Details bleiben verfügbar, falls etwas hakt.")
        self.device_combo = QComboBox()
        self.device_combo.setMinimumHeight(40)
        self.device_hint = QLabel("Noch kein Sensor vorbereitet. Die App sucht automatisch den wahrscheinlichsten eSense Pulse.")
        self.device_hint.setObjectName("HintLabel")
        self.device_hint.setWordWrap(True)
        device_card.layout.addWidget(self.device_combo)
        device_card.layout.addWidget(self.device_hint)

        self.auto_connect_button = QPushButton("Sensor vorbereiten")
        self.auto_connect_button.setObjectName("PrimaryButton")
        self.scan_button = QPushButton("Scan (Detail)")
        self.connect_button = QPushButton("Manuell verbinden")
        self.connection_help_button = QPushButton("Hilfe")
        self.status_diagnostics_button = QPushButton("Status & Diagnose")
        self.disconnect_button = QPushButton("Trennen")
        self.disconnect_button.setObjectName("SubtleButton")
        sensor_grid = QGridLayout()
        sensor_grid.setHorizontalSpacing(8)
        sensor_grid.setVerticalSpacing(8)
        for button in [self.auto_connect_button, self.scan_button, self.connect_button, self.connection_help_button, self.status_diagnostics_button, self.disconnect_button]:
            button.setMinimumHeight(40)
        sensor_grid.addWidget(self.auto_connect_button, 0, 0, 1, 2)
        sensor_grid.addWidget(self.scan_button, 1, 0)
        sensor_grid.addWidget(self.connect_button, 1, 1)
        sensor_grid.addWidget(self.connection_help_button, 2, 0)
        sensor_grid.addWidget(self.status_diagnostics_button, 2, 1)
        sensor_grid.addWidget(self.disconnect_button, 3, 0, 1, 2)
        device_card.layout.addLayout(sensor_grid)
        prep_grid.addWidget(device_card, 0, 0, 2, 1)

        session_card = RoleCard("Sitzung", "Wähle einen kleinen Fokus. Danach reicht ein Startbutton.")
        protocol_label = "HRV-Amplitude trainieren"
        self.protocol_value = QLabel(protocol_label)
        self.protocol_value.setObjectName("ProtocolValue")
        self.protocol_note = QLabel("Der Kreis zeigt das Hauptsignal. Details werden automatisch gespeichert.")
        self.protocol_note.setObjectName("HintLabel")
        self.protocol_note.setWordWrap(True)
        session_card.layout.addWidget(self.protocol_value)
        session_card.layout.addWidget(self.protocol_note)
        self.session_plan_label = QLabel("Plan: Sensor vorbereiten, dann Training starten.")
        self.session_plan_label.setObjectName("NextStepLabel")
        self.session_plan_label.setWordWrap(True)
        session_card.layout.addWidget(self.session_plan_label)

        focus_label = QLabel("Lernfokus wählen")
        focus_label.setObjectName("SectionLabel")
        session_card.layout.addWidget(focus_label)
        self.training_focus_combo = QComboBox()
        self.training_focus_combo.setMinimumHeight(38)
        for option in learning_focus_options():
            self.training_focus_combo.addItem(option.label, option.key)
        self.training_focus_combo.setToolTip("Der Lernfokus bündelt Aufmerksamkeit und erleichtert späteren Transfer. Du kannst ihn jederzeit ändern.")
        session_card.layout.addWidget(self.training_focus_combo)

        self.training_intention = QLineEdit()
        self.training_intention.setPlaceholderText("Optional ergänzen: eigener Satz oder Alltagssituation")
        self.training_intention.setToolTip("Freie Ergänzung; wird lokal dokumentiert und nicht bewertet.")
        session_card.layout.addWidget(self.training_intention)

        self.training_button = QPushButton("Training starten")
        self.training_button.setObjectName("PrimaryButton")
        self.training_button.setMinimumHeight(48)
        session_card.layout.addWidget(self.training_button)
        prep_session_grid = QGridLayout()
        prep_session_grid.setHorizontalSpacing(8)
        prep_session_grid.setVerticalSpacing(8)
        self.reference_button = QPushButton("Referenz 10 min")
        self.skip_baseline_button = QPushButton("Baseline überspringen")
        self.mock_button = QPushButton("Mock-Test")
        for button in [self.reference_button, self.skip_baseline_button, self.mock_button]:
            button.setMinimumHeight(40)
        prep_session_grid.addWidget(self.reference_button, 0, 0)
        prep_session_grid.addWidget(self.skip_baseline_button, 0, 1)
        prep_session_grid.addWidget(self.mock_button, 1, 0, 1, 2)
        session_card.layout.addLayout(prep_session_grid)
        prep_grid.addWidget(session_card, 0, 1)

        workflow_card = RoleCard("Ablauf", "Der Hauptweg bleibt klein: Sensor → Signal → Training.")
        self.workflow_sensor = WorkflowStep("1", "Sensor", "Auto verbinden starten.")
        self.workflow_signal = WorkflowStep("2", "Signal", "Kontakt und RR-Daten prüfen.")
        self.workflow_training = WorkflowStep("3", "Training", "Positive Rückmeldung über HRV-Amplitude.")
        workflow_card.layout.addWidget(self.workflow_sensor)
        workflow_card.layout.addWidget(self.workflow_signal)
        workflow_card.layout.addWidget(self.workflow_training)
        prep_grid.addWidget(workflow_card, 0, 2)

        prep_info = Card("InfoCard")
        prep_info_layout = QVBoxLayout(prep_info)
        prep_info_layout.setContentsMargins(16, 14, 16, 14)
        prep_info_layout.setSpacing(8)
        prep_info_layout.addWidget(self._section_label("Vor dem Start"))
        prep_info_text = QLabel(
            "• eSense Pulse anlegen und Kontakt prüfen.\n"
            "• Kurz Sitzposition, Licht, Tagesform und Lernfokus wahrnehmen.\n"
            "• Andere Smartphone-Apps trennen, falls RR-Daten fehlen.\n"
            "• Der Mock-Test prüft die Oberfläche ohne Sensor."
        )
        prep_info_text.setObjectName("HintLabel")
        prep_info_text.setWordWrap(True)
        prep_info_layout.addWidget(prep_info_text)
        self.evidence_hint_label = QLabel(
            "Evidenzrahmen: kurze, wiederholbare HRV-Übung; RR-Qualität vor Interpretation."
        )
        self.evidence_hint_label.setObjectName("NextStepLabel")
        self.evidence_hint_label.setWordWrap(True)
        prep_info_layout.addWidget(self.evidence_hint_label)
        prep_grid.addWidget(prep_info, 1, 1, 1, 2)

        self.learning_compass_card = RoleCard(
            "Lernkompass",
            "Die App hinterfragt nach jeder Sitzung, ob Signal, Rückmeldung und Transfer gerade gut zusammenpassen.",
        )
        self.learning_compass_label = QLabel("Nach der ersten gespeicherten Sitzung erscheinen hier adaptive Hinweise.")
        self.learning_compass_label.setObjectName("HintLabel")
        self.learning_compass_label.setWordWrap(True)
        self.learning_compass_card.layout.addWidget(self.learning_compass_label)
        prep_grid.addWidget(self.learning_compass_card, 1, 0)
        self.learning_compass_card.setVisible(False)  # Expert/adaptation layer stays in metadata, not in the default flow.

        self.pre_check_card = RoleCard(
            "Kurzer Selbstcheck",
            "Drei Beobachtungsskalen reichen für den Start. Weitere Kontextdaten bleiben im Hintergrund dokumentierbar.",
        )
        self.pre_rating_widgets: dict[str, RatingScale] = {
            "tension": RatingScale("Anspannung", "ruhig", "stark aktiviert", 5),
            "focus": RatingScale("Fokus", "zerstreut", "gesammelt", 5),
            "body_contact": RatingScale("Körperkontakt", "kaum wahrnehmbar", "gut wahrnehmbar", 5),
        }
        for widget in self.pre_rating_widgets.values():
            self.pre_check_card.layout.addWidget(widget)
        self.pre_readiness_label = QLabel("Startbereitschaft wird aus Selbstcheck und Sensorstatus abgeleitet.")
        self.pre_readiness_label.setObjectName("HintLabel")
        self.pre_readiness_label.setWordWrap(True)
        self.pre_check_card.layout.addWidget(self.pre_readiness_label)
        self.pre_science_prompt_label = QLabel("Rahmen: wählen, beobachten, kleine nächste Schritte.")
        self.pre_science_prompt_label.setObjectName("HintLabel")
        self.pre_science_prompt_label.setWordWrap(True)
        self.pre_check_card.layout.addWidget(self.pre_science_prompt_label)
        prep_grid.addWidget(self.pre_check_card, 2, 0)

        protocol = phase_protocol()
        learning = learning_protocol()
        self.pre_protocol_card = RoleCard("Trainingsrahmen", "Wertfreie Orientierung für die Sitzung.")
        foundation = psychological_foundation()
        protocol_text = QLabel(
            f"Vorbereitung: {protocol.preparation}\n\n"
            f"Rückmeldung: {learning.reinforcement_principle}\n\n"
            f"Sprache: {foundation.self_determination} {foundation.act_rft_language}\n\n"
            "Aktuelle Evidenz: kurze wiederholbare Praxis, transparente Messqualität und vorsichtige Interpretation. "
            "Die Anzeige dient der Selbstbeobachtung, nicht der Diagnose."
        )
        protocol_text.setObjectName("HintLabel")
        protocol_text.setWordWrap(True)
        self.pre_protocol_card.layout.addWidget(protocol_text)
        prep_grid.addWidget(self.pre_protocol_card, 2, 1, 1, 2)
        self.pre_protocol_card.setVisible(False)  # Scientific details stay available through export/help, not on the main preparation screen.

        prep_grid.setColumnStretch(0, 3)
        prep_grid.setColumnStretch(1, 2)
        prep_grid.setColumnStretch(2, 2)
        self.phase_stack.addWidget(self.preparation_page)

        # TRAINING -----------------------------------------------------------
        self.training_page = QWidget()
        self.training_page.setObjectName("PhasePage")
        train = QVBoxLayout(self.training_page)
        train.setContentsMargins(0, 0, 0, 0)
        train.setSpacing(12)

        train_control = Card("TrainingControlCard")
        control_layout = QHBoxLayout(train_control)
        control_layout.setContentsMargins(16, 12, 16, 12)
        control_layout.setSpacing(10)
        control_text = QVBoxLayout()
        control_text.setSpacing(2)
        train_title = QLabel("Training")
        train_title.setObjectName("PhaseTitleSmall")
        self.training_guidance_label = QLabel("Ein Signal steht im Mittelpunkt: HRV-Amplitude. Der Kreis zeigt sie ruhig und graduell.")
        self.training_guidance_label.setObjectName("HintLabel")
        self.training_guidance_label.setWordWrap(True)
        self.training_focus_label = QLabel("Aufmerksamkeitsanker: Kreis und Körperkontakt wahrnehmen.")
        self.training_focus_label.setObjectName("NextStepLabel")
        self.training_focus_label.setWordWrap(True)
        control_text.addWidget(train_title)
        control_text.addWidget(self.training_guidance_label)
        control_text.addWidget(self.training_focus_label)
        control_layout.addLayout(control_text, 1)
        self.details_button = QPushButton("Details")
        self.details_button.setCheckable(True)
        self.details_button.setToolTip("Zeigt Kernzahlen nur bei Bedarf. Bei Signalproblemen erscheinen sie automatisch.")
        self.pause_button = QPushButton("Pause")
        self.stop_button = QPushButton("Stop & Speichern")
        self.stop_button.setObjectName("DangerButton")
        for button in [self.details_button, self.pause_button, self.stop_button]:
            button.setMinimumHeight(42)
            control_layout.addWidget(button)
        train.addWidget(train_control)

        training_body = QHBoxLayout()
        training_body.setSpacing(12)
        train.addLayout(training_body, 1)

        training_center = QVBoxLayout()
        training_center.setSpacing(12)
        training_body.addLayout(training_center, 1)

        self.feedback_card = Card("FeedbackCard")
        self.feedback_card.setMinimumHeight(470)
        feedback_layout = QVBoxLayout(self.feedback_card)
        feedback_layout.setContentsMargins(16, 16, 16, 16)
        feedback_layout.setSpacing(10)
        feedback_head = QHBoxLayout()
        feedback_title = QLabel("Trainingsraum")
        feedback_title.setObjectName("PanelTitle")
        self.feedback_state_label = QLabel("HRV-Amplitude · positive Rückmeldung")
        self.feedback_state_label.setObjectName("HintLabel")
        feedback_head.addWidget(feedback_title)
        feedback_head.addStretch(1)
        feedback_head.addWidget(self.feedback_state_label)
        feedback_layout.addLayout(feedback_head)
        self.circle = FeedbackCircle()
        feedback_layout.addWidget(self.circle, 1)
        training_center.addWidget(self.feedback_card, 1)

        self.plot_card = Card("HrvGraphCard")
        self.plot_card.setMinimumHeight(300)
        plot_layout = QVBoxLayout(self.plot_card)
        plot_layout.setContentsMargins(16, 14, 16, 14)
        plot_layout.setSpacing(10)
        plot_header = QHBoxLayout()
        plot_title_box = QVBoxLayout()
        plot_title_box.setSpacing(2)
        plot_title = QLabel("HRV-Spur")
        plot_title.setObjectName("PanelTitle")
        plot_hint = QLabel("Ein Graph: HRV-Amplitude im gleitenden 60-s-Fenster · letzte 5 Minuten")
        plot_hint.setObjectName("HintLabel")
        plot_hint.setWordWrap(True)
        plot_title_box.addWidget(plot_title)
        plot_title_box.addWidget(plot_hint)
        plot_header.addLayout(plot_title_box, 1)
        hrv_value_box = QVBoxLayout()
        hrv_value_box.setSpacing(0)
        self.hrv_graph_value = QLabel("—")
        self.hrv_graph_value.setObjectName("HrvGraphValue")
        self.hrv_graph_value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.hrv_graph_helper = QLabel("Sammelt RR-Intervalle")
        self.hrv_graph_helper.setObjectName("HrvGraphHelper")
        self.hrv_graph_helper.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.hrv_graph_helper.setWordWrap(True)
        hrv_value_box.addWidget(self.hrv_graph_value)
        hrv_value_box.addWidget(self.hrv_graph_helper)
        plot_header.addLayout(hrv_value_box)
        plot_layout.addLayout(plot_header)
        if pg is not None:
            self.plot = pg.PlotWidget()
            self.plot.setMinimumHeight(230)
            self.plot.setMenuEnabled(False)
            self.plot.setMouseEnabled(x=False, y=False)
            self.plot.hideButtons()
            self.plot.showGrid(x=True, y=True, alpha=0.16)
            self.plot.setLabel("bottom", "Zeit", units="min")
            self.plot.setLabel("left", "HRV-Amplitude", units="BPM")
            self.plot.setClipToView(True)
            self.hrv_curve = self.plot.plot(name="HRV-Amplitude")
            plot_layout.addWidget(self.plot)
        else:
            self.plot = None
            self.hrv_curve = None
            no_plot = QLabel("pyqtgraph nicht verfügbar: HRV-Spur deaktiviert.")
            no_plot.setObjectName("HintLabel")
            no_plot.setWordWrap(True)
            plot_layout.addWidget(no_plot)
        training_center.addWidget(self.plot_card)

        self.right_panel = Card("MetricPanel")
        self.right_panel.setMinimumWidth(260)
        self.right_panel.setMaximumWidth(340)
        self.right_panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        training_body.addWidget(self.right_panel, 0)
        right = QVBoxLayout(self.right_panel)
        right.setContentsMargins(14, 14, 14, 14)
        right.setSpacing(10)
        right.addWidget(self._section_label("Kernsignale"))

        self.metrics_scroll = QScrollArea()
        self.metrics_scroll.setWidgetResizable(True)
        self.metrics_scroll.setFrameShape(QFrame.NoFrame)
        self.metrics_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        metrics_container = QWidget()
        metrics_layout = QVBoxLayout(metrics_container)
        metrics_layout.setContentsMargins(0, 0, 0, 0)
        metrics_layout.setSpacing(10)

        self.metric_cards: dict[str, MetricCard] = {
            "amp": MetricCard("HRV-Amplitude", "—", "primäres Feedbacksignal"),
            "quality": MetricCard("Signalqualität", "—", "gültige RR-Werte im Kurzfenster"),
            "bpm": MetricCard("Herzrate", "—", "BPM"),
            "stable_phases": MetricCard("Stabile Phasen", "0", "kurze Verstärkungsmomente"),
        }
        for _key, card in self.metric_cards.items():
            metrics_layout.addWidget(card)
        metrics_layout.addStretch(1)
        self.metrics_scroll.setWidget(metrics_container)
        right.addWidget(self.metrics_scroll, 1)

        self.phase_stack.addWidget(self.training_page)

        # AFTERCARE ----------------------------------------------------------
        self.aftercare_page = QWidget()
        self.aftercare_page.setObjectName("PhasePage")
        after = QVBoxLayout(self.aftercare_page)
        after.setContentsMargins(0, 0, 0, 0)
        after.setSpacing(12)

        after_hero = Card("HeroCard")
        after_hero_layout = QVBoxLayout(after_hero)
        after_hero_layout.setContentsMargins(22, 18, 22, 18)
        after_hero_layout.setSpacing(8)
        after_title = QLabel("Nachbereitung")
        after_title.setObjectName("PhaseTitle")
        after_subtitle = QLabel("Kurz integrieren: Was war beobachtbar, was passt als kleiner Alltagsschritt?")
        after_subtitle.setObjectName("PhaseSubtitle")
        after_subtitle.setWordWrap(True)
        after_hero_layout.addWidget(after_title)
        after_hero_layout.addWidget(after_subtitle)
        after.addWidget(after_hero)

        after_grid = QGridLayout()
        after_grid.setHorizontalSpacing(12)
        after_grid.setVerticalSpacing(12)
        after.addLayout(after_grid, 1)
        summary_card = RoleCard("Kurzrückblick", "Wenige Kerndaten zur Sitzung. Details liegen in CSV/JSON.")
        self.aftercare_summary_text = QTextEdit()
        self.aftercare_summary_text.setReadOnly(True)
        self.aftercare_summary_text.setMinimumHeight(240)
        self.aftercare_summary_text.setText("Noch keine gespeicherte Sitzung.")
        summary_card.layout.addWidget(self.aftercare_summary_text, 1)
        after_grid.addWidget(summary_card, 0, 0, 2, 1)

        reflection_card = RoleCard(
            "Kurz nachspüren",
            "Unter 60 Sekunden: drei Werte, eine optionale Beobachtung, speichern.",
        )
        self.post_rating_widgets: dict[str, RatingScale] = {
            "tension": RatingScale("Anspannung", "ruhig", "stark aktiviert", 5),
            "focus": RatingScale("Fokus", "zerstreut", "gesammelt", 5),
            "body_contact": RatingScale("Körperkontakt", "kaum wahrnehmbar", "gut wahrnehmbar", 5),
        }
        for widget in self.post_rating_widgets.values():
            reflection_card.layout.addWidget(widget)
        self.aftercare_notes = QTextEdit()
        self.aftercare_notes.setPlaceholderText("Optional: Was war beobachtbar? Was passt als 2-Minuten-Übung im Alltag?")
        self.aftercare_notes.setMinimumHeight(90)
        reflection_card.layout.addWidget(self.aftercare_notes)
        self.aftercare_context = QLineEdit()
        self.aftercare_context.setPlaceholderText("Optionaler Wenn-Teil, z. B. ich am Schreibtisch ankomme")
        self.aftercare_context.setToolTip("Aus dieser Angabe erstellt die App einen freiwilligen Wenn-Dann-Mini-Plan.")
        reflection_card.layout.addWidget(self.aftercare_context)
        self.aftercare_save_reflection_button = QPushButton("Reflexion speichern")
        self.aftercare_save_reflection_button.setObjectName("PrimaryButton")
        self.aftercare_save_reflection_button.setMinimumHeight(42)
        reflection_card.layout.addWidget(self.aftercare_save_reflection_button)
        self.aftercare_reflection_hint = QLabel("Noch nicht gespeichert.")
        self.aftercare_reflection_hint.setObjectName("HintLabel")
        self.aftercare_reflection_hint.setWordWrap(True)
        reflection_card.layout.addWidget(self.aftercare_reflection_hint)
        after_grid.addWidget(reflection_card, 0, 1, 2, 1)

        transfer_card = RoleCard("Transfer", "Eine kleine Alltagssituation genügt.")
        self.aftercare_transfer_text = QLabel("Nach dem Speichern erscheinen hier passende Transferideen.")
        self.aftercare_transfer_text.setObjectName("HintLabel")
        self.aftercare_transfer_text.setWordWrap(True)
        transfer_card.layout.addWidget(self.aftercare_transfer_text)
        self.aftercare_learning_loop_label = QLabel("")
        self.aftercare_learning_loop_label.setObjectName("HintLabel")
        self.aftercare_learning_loop_label.setWordWrap(True)
        self.aftercare_learning_loop_label.setVisible(False)
        transfer_card.layout.addWidget(self.aftercare_learning_loop_label)
        after_grid.addWidget(transfer_card, 0, 2)

        next_card = RoleCard("Nächste Schritte", "Einfach fortfahren oder die Daten prüfen.")
        self.aftercare_new_training_button = QPushButton("Neue Vorbereitung")
        self.aftercare_new_training_button.setObjectName("PrimaryButton")
        self.aftercare_open_sessions_button = QPushButton("Sitzungsordner öffnen")
        self.aftercare_open_diagnostics_button = QPushButton("Status & Diagnose")
        for button in [self.aftercare_new_training_button, self.aftercare_open_sessions_button, self.aftercare_open_diagnostics_button]:
            button.setMinimumHeight(42)
            next_card.layout.addWidget(button)
        after_grid.addWidget(next_card, 1, 2)
        after_grid.setColumnStretch(0, 2)
        after_grid.setColumnStretch(1, 2)
        after_grid.setColumnStretch(2, 1)
        self.phase_stack.addWidget(self.aftercare_page)

        for widget in self.pre_rating_widgets.values():
            widget.slider.valueChanged.connect(lambda _value: self._update_preparation_readiness())
        if hasattr(self, "training_focus_combo"):
            self.training_focus_combo.currentIndexChanged.connect(lambda _index: self._update_preparation_readiness())
        self._update_preparation_readiness()

        # Legacy-compatible aliases used by focus/visibility helpers.
        self.left_panel = self.preparation_page

        # Signal wiring ------------------------------------------------------
        hero_action.clicked.connect(self.auto_connect_ble)
        self.scan_button.clicked.connect(self.scan_ble)
        self.connect_button.clicked.connect(self.connect_ble)
        self.disconnect_button.clicked.connect(self.disconnect_ble)
        self.auto_connect_button.clicked.connect(self.auto_connect_ble)
        self.connection_help_button.clicked.connect(self.show_connection_assistant)
        self.status_diagnostics_button.clicked.connect(self.show_status_diagnostics)
        self.reference_button.clicked.connect(self.start_reference)
        self.training_button.clicked.connect(self.start_training_with_baseline)
        self.skip_baseline_button.clicked.connect(self.skip_baseline)
        self.pause_button.clicked.connect(self.toggle_pause)
        self.stop_button.clicked.connect(self.stop_session)
        self.mock_button.clicked.connect(self.toggle_mock)
        self.aftercare_new_training_button.clicked.connect(self.show_preparation_view)
        self.aftercare_open_sessions_button.clicked.connect(lambda: open_path_or_uri(SESSIONS_DIR))
        self.aftercare_open_diagnostics_button.clicked.connect(self.show_status_diagnostics)
        self.aftercare_save_reflection_button.clicked.connect(self.save_aftercare_reflection)
        self.details_button.toggled.connect(lambda checked: self._set_training_details_visible(bool(checked)))

        self.setStatusBar(QStatusBar(self))

    def show_preparation_view(self) -> None:
        """Return to the preparation page without touching the active sensor connection."""
        if hasattr(self, "phase_stack"):
            self.phase_stack.setCurrentWidget(self.preparation_page)
            self.view_pill.set_tone("neutral", "Vorbereitung")
        self.statusBar().showMessage("Vorbereitung geöffnet.")

    def _sync_phase_view(self, *, force_aftercare: bool = False) -> None:
        """Show exactly one major phase page.

        Preparation is used while no session is running, Training is used for
        reference/baseline/training/pause, and Aftercare is used after a saved
        session.  Only the visible page is part of the primary workflow.
        """
        if not hasattr(self, "phase_stack"):
            return
        if force_aftercare:
            self.phase_stack.setCurrentWidget(self.aftercare_page)
            self.view_pill.set_tone("good", "Nachbereitung")
            return
        if self.phase in {"reference", "baseline", "training", "paused"}:
            self.phase_stack.setCurrentWidget(self.training_page)
            self.view_pill.set_tone("active", "Training")
        else:
            # Keep aftercare visible until the user intentionally returns to preparation.
            if self.phase_stack.currentWidget() is self.aftercare_page:
                self.view_pill.set_tone("good", "Nachbereitung")
            else:
                self.phase_stack.setCurrentWidget(self.preparation_page)
                self.view_pill.set_tone("neutral", "Vorbereitung")

    def _set_aftercare_summary(self, csv_path: Path, summary: dict[str, Any]) -> None:
        def fmt(value: Any, suffix: str = "") -> str:
            if value is None:
                return "—"
            if isinstance(value, float):
                return f"{value:.2f}{suffix}"
            return f"{value}{suffix}"

        focus_key = self.session_context.get("learning_focus_key", self._current_focus_key())
        suggestions = aftercare_transfer_suggestions(summary, focus_key)
        plan = micro_practice_plan(summary, focus_key=focus_key)
        evidence_notes = evidence_aftercare_summary(summary)
        adaptive_review = evaluate_double_loop(
            summary=summary,
            pre_ratings=self.session_context.get("pre_session_ratings", {}),
            post_ratings=None,
            focus_key=focus_key,
        )
        self.last_double_loop_review = adaptive_review.to_dict()
        text = (
            f"Gespeichert:\n{csv_path}\n\n"
            f"Dauer: {fmt(summary.get('duration_s'), ' s')}\n"
            f"Gültige RR-Werte: {summary.get('valid_rr_count', 0)} / {summary.get('row_count', 0)}\n"
            f"Artefaktanteil: {fmt((summary.get('artifact_ratio') or 0) * 100, ' %')}\n"
            f"Ø HRV-Amplitude: {fmt(summary.get('mean_hrv_amplitude_60s'), ' BPM')}\n"
            f"Ø Herzrate: {fmt(summary.get('mean_bpm'), ' BPM')}\n"
            f"Stabile Phasen: {summary.get('reward_count', 0)}\n\n"
            "Einordnung:\n"
            "Die Werte beschreiben diese Sitzung und dienen der Selbstbeobachtung. "
            "Sie sind keine medizinische Bewertung. Details liegen in den Exportdateien.\n\n"
            "Evidenzhinweise:\n"
            + "\n".join(f"• {item}" for item in evidence_notes[:3])
            + "\n"
        )
        if hasattr(self, "aftercare_summary_text"):
            self.aftercare_summary_text.setText(text)
        if hasattr(self, "aftercare_transfer_text"):
            transfer_lines = ["Transferideen:"] + [f"• {item}" for item in suggestions]
            transfer_lines += ["", "Mini-Übungsplan:"] + [f"• {item}" for item in plan]
            next_actions = [s.action for s in adaptive_review.suggestions[:1]]
            if next_actions:
                transfer_lines += ["", "Nächste Sitzung:"] + [f"• {item}" for item in next_actions]
            transfer_lines += ["", "Wenn-Dann-Vorschlag:", f"• {implementation_intention(summary, focus_key)}"]
            self.aftercare_transfer_text.setText("\n".join(transfer_lines))
        if hasattr(self, "aftercare_learning_loop_label"):
            self.aftercare_learning_loop_label.setText(format_double_loop_review(adaptive_review))
            self.aftercare_learning_loop_label.setVisible(False)
        self._prepare_aftercare_reflection_defaults()

    @staticmethod
    def _section_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("SectionLabel")
        return label

    @staticmethod
    def _collect_rating_values(widgets: dict[str, RatingScale]) -> dict[str, int]:
        # Keep exports schema-stable even when the visible self-check is reduced.
        values = {key: 5 for key in RATING_FIELDS}
        values.update({key: widget.value() for key, widget in widgets.items()})
        return values

    def _current_focus_key(self) -> str:
        if hasattr(self, "training_focus_combo"):
            key = self.training_focus_combo.currentData()
            return str(key or "observe_contact")
        return "observe_contact"

    def _current_intention(self) -> str:
        focus = learning_focus_by_key(self._current_focus_key()).label
        extra = self.training_intention.text().strip() if hasattr(self, "training_intention") else ""
        return f"{focus}: {extra}" if extra else focus

    def _current_guided_session_plan(self):
        ratings = self._collect_rating_values(self.pre_rating_widgets) if hasattr(self, "pre_rating_widgets") else {}
        sensor_ready = bool(self.input_mode == "ble" and self.ble_rr_value_count > 0) or bool(self.input_mode == "mock")
        signal_quality = float(getattr(self._last_metrics, "signal_quality", 0.0) or 0.0)
        if sensor_ready and self.phase == "idle" and not self.session_rows and signal_quality <= 0.0:
            # Before a session starts there may be RR preview but no computed
            # metrics yet. Treat a confirmed RR stream as usable, not as low quality.
            signal_quality = 0.75
        return compute_guided_session_plan(
            sensor_ready=sensor_ready,
            ble_packet_count=int(self.ble_packet_count),
            ble_rr_value_count=int(self.ble_rr_value_count),
            signal_quality=signal_quality,
            ratings=ratings,
            focus_key=self._current_focus_key(),
            recent_review=self.last_double_loop_review or self.recent_double_loop_review,
            mock_active=bool(self.mock_timer.isActive()),
        )

    def _update_preparation_readiness(self) -> None:
        if not hasattr(self, "pre_readiness_label") or not hasattr(self, "pre_rating_widgets"):
            return
        sensor_ready = bool(self.input_mode == "ble" and self.ble_rr_value_count > 0) or bool(self.input_mode == "mock")
        ratings = self._collect_rating_values(self.pre_rating_widgets)
        self.pre_readiness_label.setText(preparation_summary_text(ratings, sensor_ready=sensor_ready))
        if hasattr(self, "pre_science_prompt_label"):
            prompts = preparation_science_prompts(ratings, self._current_focus_key(), sensor_ready=sensor_ready)
            self.pre_science_prompt_label.setText("\n".join(f"• {item}" for item in prompts))
        if hasattr(self, "learning_compass_label"):
            self.learning_compass_label.setText(
                current_preparation_compass(
                    ratings,
                    sensor_ready=sensor_ready,
                    recent_review=self.last_double_loop_review or self.recent_double_loop_review,
                    focus_key=self._current_focus_key(),
                )
            )
        plan = self._current_guided_session_plan()
        self._last_guided_session_plan = plan.to_dict()
        evidence_rec = compute_evidence_session_recommendation(
            guided_plan=self._last_guided_session_plan,
            ratings=ratings,
            sensor_ready=sensor_ready,
            signal_quality=float(getattr(self._last_metrics, "signal_quality", 0.0) or (0.75 if sensor_ready else 0.0)),
            session_minutes=TRAINING_SECONDS / 60.0,
        )
        self._last_evidence_session_recommendation = evidence_rec.to_dict()
        if hasattr(self, "evidence_hint_label"):
            self.evidence_hint_label.setText(evidence_rec.visible_hint + " " + evidence_rec.practice_window)
        if hasattr(self, "session_plan_label"):
            self.session_plan_label.setText(
                f"Plan: {plan.label} · {plan.preparation_hint}"
            )
        if hasattr(self, "training_button") and self.phase == "idle":
            self.training_button.setText("Training starten" if not plan.baseline_recommended else "Training mit Baseline starten")
            self.training_button.setToolTip(plan.training_hint)
        if hasattr(self, "skip_baseline_button"):
            self.skip_baseline_button.setVisible(bool(not plan.baseline_recommended or plan.plan_id == "direct_training"))

    def _capture_pre_session_ratings(self) -> None:
        if not hasattr(self, "pre_rating_widgets"):
            return
        ratings = self._collect_rating_values(self.pre_rating_widgets)
        self.session_context["pre_session_ratings"] = ratings
        self.session_context["pre_session_rating_labels"] = dict(RATING_FIELDS)
        self.session_context["psychology_model_version"] = PSYCHOLOGY_MODEL_VERSION
        self.session_context["adaptation_model_version"] = ADAPTATION_MODEL_VERSION
        self.session_context["recent_double_loop_review"] = self.last_double_loop_review or self.recent_double_loop_review or {}
        self.session_context["phase_protocol"] = phase_protocol().__dict__
        self.session_context["learning_protocol"] = learning_protocol().__dict__
        focus_key = self._current_focus_key()
        focus = learning_focus_by_key(focus_key)
        sensor_ready = (self.input_mode == "ble" and self.ble_rr_value_count > 0) or self.input_mode == "mock"
        self.session_context["training_intention"] = self._current_intention()
        self.session_context["learning_focus_key"] = focus_key
        self.session_context["learning_focus_label"] = focus.label
        self.session_context["preparation_readiness"] = preparation_summary_text(
            ratings,
            sensor_ready=sensor_ready,
        )
        self.session_context["preparation_science_prompts"] = preparation_science_prompts(ratings, focus_key, sensor_ready=sensor_ready)
        self.session_context["psychological_foundation"] = psychological_foundation().__dict__
        self.session_context["science_metadata"] = science_metadata()
        self.session_context["training_frame"] = (
            "Positive operante Rückmeldung über HRV-Amplitude; subjektive Ratings dienen nur der Selbstbeobachtung; "
            "kurze Aufmerksamkeitsanker, Autonomieunterstützung und Wenn-Dann-Transfer unterstützen Lernprozesse."
        )
        guided_plan = self._current_guided_session_plan()
        self._last_guided_session_plan = guided_plan.to_dict()
        self.session_context["visible_product_contract"] = visible_training_contract()
        self.session_context["adaptive_ui_version"] = ADAPTIVE_UI_VERSION
        self.session_context["complementary_channel_contract"] = complementary_channel_contract()
        self.session_context["guided_session_version"] = GUIDED_SESSION_VERSION
        self.session_context["guided_session_contract"] = guided_session_contract()
        self.session_context["guided_session_plan"] = guided_plan.to_dict()
        evidence_rec = compute_evidence_session_recommendation(
            guided_plan=self._last_guided_session_plan,
            ratings=ratings,
            sensor_ready=sensor_ready,
            signal_quality=float(getattr(self._last_metrics, "signal_quality", 0.0) or (0.75 if sensor_ready else 0.0)),
            session_minutes=TRAINING_SECONDS / 60.0,
        )
        self._last_evidence_session_recommendation = evidence_rec.to_dict()
        self.session_context["evidence_model_version"] = EVIDENCE_MODEL_VERSION
        self.session_context["evidence_metadata"] = evidence_metadata()
        self.session_context["evidence_session_recommendation"] = self._last_evidence_session_recommendation
        self.session_context["ui_capability_version"] = UI_CAPABILITY_VERSION
        self.session_context["ui_capability_metadata"] = capability_metadata()
        self.session_context["visual_feedback_version"] = VISUAL_FEEDBACK_VERSION
        self.session_context["graph_display_metadata"] = graph_display_metadata(
            calm_visuals_enabled=self.calm_visuals_enabled,
            pyqtgraph_available=pg is not None,
        )
        self.session_context["interaction_design_version"] = INTERACTION_DESIGN_VERSION
        self.session_context["interaction_design_contract"] = interaction_design_contract()
        self.session_context["reduced_motion_enabled"] = bool(self.reduced_motion_enabled)
        self.session_context["last_interaction_profile"] = self._last_interaction_profile

    def _capture_post_session_ratings(self) -> dict[str, int]:
        if not hasattr(self, "post_rating_widgets"):
            return {}
        return self._collect_rating_values(self.post_rating_widgets)

    def _prepare_aftercare_reflection_defaults(self) -> None:
        if not hasattr(self, "post_rating_widgets"):
            return
        pre = self.session_context.get("pre_session_ratings", {})
        for key, widget in self.post_rating_widgets.items():
            if key in pre:
                widget.set_value(int(pre[key]))
        if hasattr(self, "aftercare_notes"):
            self.aftercare_notes.clear()
        if hasattr(self, "aftercare_context"):
            self.aftercare_context.clear()
        if hasattr(self, "aftercare_reflection_hint"):
            self.aftercare_reflection_hint.setText("Noch nicht gespeichert.")

    def save_aftercare_reflection(self) -> None:
        if not self.last_session_csv_path:
            QMessageBox.information(self, "Nachbereitung", "Es gibt noch keine gespeicherte Sitzung für eine Reflexion.")
            return
        post = self._capture_post_session_ratings()
        notes = self.aftercare_notes.toPlainText() if hasattr(self, "aftercare_notes") else ""
        payload = build_reflection_payload(
            pre_ratings=self.session_context.get("pre_session_ratings", {}),
            post_ratings=post,
            notes=notes,
            summary=self.last_session_summary,
            intention=self.session_context.get("training_intention", self._current_intention()),
            sensor_ready=(self.input_mode == "ble" and self.ble_rr_value_count > 0) or self.input_mode == "mock",
            focus_key=self.session_context.get("learning_focus_key", self._current_focus_key()),
            implementation_context=(self.aftercare_context.text() if hasattr(self, "aftercare_context") else ""),
        )
        payload["session_csv"] = self.last_session_csv_path.name
        payload["guided_session_version"] = GUIDED_SESSION_VERSION
        payload["guided_session_contract"] = guided_session_contract()
        payload["guided_session_plan"] = self._last_guided_session_plan or self.session_context.get("guided_session_plan", {})
        payload["evidence_model_version"] = EVIDENCE_MODEL_VERSION
        payload["evidence_metadata"] = evidence_metadata()
        payload["evidence_session_recommendation"] = self._last_evidence_session_recommendation or self.session_context.get("evidence_session_recommendation", {})
        payload["evidence_aftercare"] = evidence_aftercare_summary(self.last_session_summary)
        payload["interaction_design_version"] = INTERACTION_DESIGN_VERSION
        payload["interaction_design_contract"] = interaction_design_contract()
        payload["last_interaction_profile"] = self._last_interaction_profile or self.session_context.get("last_interaction_profile", {})
        payload["reduced_motion_enabled"] = bool(self.reduced_motion_enabled)
        adaptive_review = evaluate_double_loop(
            summary=self.last_session_summary,
            pre_ratings=self.session_context.get("pre_session_ratings", {}),
            post_ratings=post,
            focus_key=self.session_context.get("learning_focus_key", self._current_focus_key()),
        )
        payload["double_loop_learning"] = adaptive_review.to_dict()
        self.last_double_loop_review = payload["double_loop_learning"]
        path = self.last_session_csv_path.with_suffix(".reflection.json")
        try:
            save_json(path, payload)
            self.last_reflection_path = path
            if hasattr(self, "aftercare_reflection_hint"):
                self.aftercare_reflection_hint.setText(f"Reflexion gespeichert: {path.name}")
            if hasattr(self, "aftercare_transfer_text"):
                transfer_items = payload.get("transfer_suggestions", []) + payload.get("micro_practice_plan", [])
                evidence_items = payload.get("evidence_aftercare", [])
                change_items = payload.get("rating_change_text", [])
                text_parts = ["Transferideen:"] + [f"• {item}" for item in transfer_items]
                if payload.get("implementation_intention"):
                    text_parts += ["", "Wenn-Dann-Plan:", f"• {payload['implementation_intention']}"]
                if evidence_items:
                    text_parts += ["", "Evidenzrahmen:"] + [f"• {item}" for item in evidence_items[:3]]
                if change_items:
                    text_parts += ["", "Selbstcheck-Veränderung:"] + [f"• {item}" for item in change_items]
                self.aftercare_transfer_text.setText("\n".join(text_parts))
            if hasattr(self, "aftercare_learning_loop_label"):
                self.aftercare_learning_loop_label.setText(format_double_loop_review(adaptive_review))
            self.statusBar().showMessage(f"Reflexion gespeichert: {path}")
        except Exception as exc:
            log_exception(self.logger, "Aftercare reflection export failed", exc)
            QMessageBox.critical(self, "Nachbereitung", "Die Reflexion konnte nicht gespeichert werden. Details stehen in der Logdatei.")

    def _exit_focus_or_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
            return
        if self.focus_mode:
            self._set_focus_mode(False)

    def _restore_window_layout(self) -> None:
        restored = False
        geometry = b64_to_qbytearray(str(self.config.get("window_geometry", "")))
        if geometry is not None:
            try:
                restored = bool(self.restoreGeometry(geometry))
            except Exception as exc:
                self.logger.debug("Could not restore saved window geometry: %s", exc)
        if not restored:
            center_and_fit_window(self)
        if bool(self.config.get("window_maximized", False)):
            self.showMaximized()

    def _save_window_layout(self) -> None:
        if self.isFullScreen():
            # Fullscreen is a transient view state; keep the next normal start usable.
            return
        try:
            self.config["window_geometry"] = qbytearray_to_b64(self.saveGeometry())
            self.config["window_maximized"] = self.isMaximized()
            save_config(self.config)
        except Exception as exc:
            self.logger.debug("Could not save window geometry: %s", exc)

    def open_sessions_folder(self) -> None:
        """Open the folder containing exported session files."""
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        self._open_path(SESSIONS_DIR, "Sitzungsordner")

    def reset_dashboard_layout(self) -> None:
        """Return the window and visible training surface to safe defaults.

        This method is intentionally conservative: it resets only layout/view
        preferences that can make the app hard to reach or visually confusing.
        It does not delete sessions, logs, BLE settings or training data.
        """
        self._set_focus_mode(False)
        self._set_plot_visible(True)
        self._set_calm_visuals_enabled(True)
        self._set_reduced_motion_enabled(True)
        self._set_training_details_visible(False)
        if self.isFullScreen():
            self.showNormal()
        elif self.isMaximized():
            self.showNormal()
        center_and_fit_window(self)
        self.config.pop("window_geometry", None)
        self.config["window_maximized"] = False
        self.config["focus_mode"] = False
        self.config["plot_visible"] = True
        self.config["calm_visuals_enabled"] = True
        self.config["reduced_motion_enabled"] = True
        self.config["training_details_visible"] = False
        save_config(self.config)
        self._sync_phase_view()
        self._update_controls()
        self._update_header_state()
        self.statusBar().showMessage("Dashboard-Layout zurückgesetzt.")

    def open_data_folder(self) -> None:
        folder = Path.home() / "Documents" / APP_NAME
        folder.mkdir(parents=True, exist_ok=True)
        self._open_path(folder, "Datenordner")

    def open_log_file(self) -> None:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        if not LOG_FILE.exists():
            LOG_FILE.write_text("", encoding="utf-8")
        self._open_path(LOG_FILE, "Logdatei")

    def open_debug_folder(self) -> None:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        self._open_path(DEBUG_DIR, "Debugordner")

    def open_windows_settings_page(self, kind: str) -> None:
        try:
            open_windows_settings(kind)
        except Exception as exc:
            log_exception(self.logger, f"Could not open Windows settings page: {kind}", exc)
            QMessageBox.information(
                self,
                "Windows-Einstellungen",
                f"Die Windows-Einstellungen konnten nicht automatisch geöffnet werden.\n\n{exc}",
            )

    def show_display_info(self) -> None:
        snapshot = collect_display_snapshot()
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        path = DEBUG_DIR / f"display_snapshot_{now_stamp()}.json"
        save_json(path, snapshot)
        lines = ["Monitor-/Display-Info", f"Gespeichert: {path}", ""]
        for idx, screen in enumerate(snapshot.get("screens", []) or [], start=1):
            available = screen.get("available_geometry", {})
            lines.append(
                f"{idx}. {screen.get('name', 'Screen')}"
                f"{' · primär' if screen.get('primary') else ''} · "
                f"verfügbar {available.get('width', '?')}×{available.get('height', '?')} · "
                f"DPI {float(screen.get('logical_dpi', 0) or 0):.1f} · "
                f"DPR {float(screen.get('device_pixel_ratio', 0) or 0):.2f}"
            )
        if not snapshot.get("screens"):
            lines.append(str(snapshot))
        QMessageBox.information(self, "Monitor-/Display-Info", "\n".join(lines))

    def show_shortcuts_dialog(self) -> None:
        rows = getattr(self, "shortcut_help_specs", []) or []
        if not rows:
            text = "F11 · Vollbild\nEsc · Vollbild/Fokusansicht verlassen\nF1 · Tastenkürzel"
        else:
            lines = ["Zentrale Tastenkürzel", ""]
            for label, shortcut, tip in rows:
                clean_tip = f" — {tip}" if tip else ""
                lines.append(f"{shortcut:<14} {label}{clean_tip}")
            lines.append("")
            lines.append("Esc           Vollbild oder Fokusansicht verlassen")
            text = "\n".join(lines)
        QMessageBox.information(self, "Tastenkürzel", text)

    def _connect_screen_signals(self) -> None:
        if self._screen_signal_connected:
            return
        handle = self.windowHandle()
        if handle is not None:
            handle.screenChanged.connect(lambda _screen: self._on_screen_changed())
            self._screen_signal_connected = True

    def _on_screen_changed(self) -> None:
        self.logger.info("Window moved to another screen | snapshot=%s", collect_display_snapshot())
        if not self.isFullScreen() and not self.isMaximized():
            # Keep the app reachable after monitor unplug/replug or DPI changes.
            center_and_fit_window(self, preferred_width=self.width(), preferred_height=self.height())

    def _build_menus(self) -> None:
        """Build a reduced menu with progressive disclosure.

        Default use stays close to the training task. Technical tools remain
        available under Help > Expert tools instead of competing with the live
        biofeedback workspace.
        """
        menu_bar = self.menuBar()
        menu_bar.clear()
        self.shortcut_help_specs: list[tuple[str, str, str]] = []
        used_shortcuts: set[str] = set()

        def make_action(
            text: str,
            slot: Any | None = None,
            *,
            shortcut: str | None = None,
            tip: str = "",
            checkable: bool = False,
            checked: bool = False,
        ) -> QAction:
            act = QAction(text, self)
            if shortcut and shortcut not in used_shortcuts:
                act.setShortcut(QKeySequence(shortcut))
                used_shortcuts.add(shortcut)
                self.shortcut_help_specs.append((text.replace("&", ""), shortcut, tip))
            if tip:
                act.setStatusTip(tip)
                act.setToolTip(tip)
            if checkable:
                act.setCheckable(True)
                act.setChecked(checked)
            if slot is not None:
                act.triggered.connect(slot)
            return act

        def add_section(menu: Any, title: str) -> None:
            if menu.actions():
                menu.addSeparator()
            header = QAction(title.upper(), self)
            header.setEnabled(False)
            menu.addAction(header)

        # Start: the everyday path.
        start_menu = menu_bar.addMenu("Start")
        self.start_auto_connect_action = make_action(
            "Sensor vorbereiten",
            self.auto_connect_ble,
            shortcut="Ctrl+Shift+A",
            tip="Sensor suchen, verbinden und RR-Daten prüfen.",
        )
        self.start_training_quick_action = make_action("Training starten", self.start_training_with_baseline, shortcut="Ctrl+T", tip="Training mit Baseline starten.")
        self.start_skip_baseline_action = make_action("Baseline überspringen", self.skip_baseline, shortcut="Ctrl+Shift+B", tip="Direkt in das Training wechseln.")
        self.start_mock_action = make_action("Mock-Test", self.toggle_mock, shortcut="Ctrl+M", tip="Oberfläche ohne Sensor ausprobieren.")
        start_menu.addActions([self.start_auto_connect_action, self.start_training_quick_action, self.start_skip_baseline_action, self.start_mock_action])
        start_menu.addSeparator()
        start_menu.addAction(make_action("Einführung", self.show_introduction, tip="Kurze Orientierung öffnen."))
        start_menu.addAction(make_action("Status & Diagnose", self.show_status_diagnostics, shortcut="Ctrl+I", tip="Bei Verbindungs- oder Signalfragen öffnen."))

        # Session: training control and context.
        session_menu = menu_bar.addMenu("Sitzung")
        self.reference_action = make_action("Referenzmessung 10 min", self.start_reference, shortcut="Ctrl+R", tip="Messung ohne Feedback starten.")
        self.training_action = make_action("Training starten", self.start_training_with_baseline, shortcut="Ctrl+T", tip="HRV-Biofeedback starten.")
        self.skip_baseline_action = make_action("Baseline überspringen", self.skip_baseline, shortcut="Ctrl+Shift+B", tip="Direkt in das Training wechseln.")
        self.pause_action = make_action("Pause/Fortsetzen", self.toggle_pause, shortcut="Space", tip="Aktive Sitzung pausieren oder fortsetzen.")
        self.stop_action = make_action("Stop & Speichern", self.stop_session, shortcut="Ctrl+Shift+X", tip="Sitzung beenden und speichern.")
        session_menu.addActions([self.reference_action, self.training_action, self.skip_baseline_action, self.pause_action, self.stop_action])
        session_menu.addSeparator()
        self.audio_action = make_action("Audio-Belohnung", self.set_audio_enabled, shortcut="Ctrl+Alt+M", checkable=True, checked=self.audio_enabled, tip="Kurzen Ton bei stabilen Zielphasen aktivieren.")
        session_menu.addAction(self.audio_action)
        session_menu.addAction(make_action("Kontext bearbeiten", self.edit_session_context, shortcut="Ctrl+K", tip="Sitzposition, Licht, Geräusch und Notizen erfassen."))

        # Device: simple first, details second.
        device_menu = menu_bar.addMenu("Gerät")
        self.auto_connect_action = make_action("Sensor vorbereiten", self.auto_connect_ble, shortcut="Ctrl+Shift+A", tip="Automatisch scannen, auswählen, verbinden und RR-Daten prüfen.")
        self.status_diag_action = make_action("Status & Diagnose", self.show_status_diagnostics, shortcut="Ctrl+I", tip="Status und verständliche nächste Schritte anzeigen.")
        device_menu.addActions([self.auto_connect_action, self.status_diag_action])
        add_section(device_menu, "Details")
        self.scan_action = make_action("BLE-Scan", self.scan_ble, shortcut="Ctrl+Shift+S", tip="Manuell nach BLE-Geräten suchen.")
        self.connect_action = make_action("Manuell verbinden", self.connect_ble, shortcut="Ctrl+Shift+C", tip="Ausgewähltes Gerät verbinden.")
        self.disconnect_action = make_action("Trennen", self.disconnect_ble, shortcut="Ctrl+Shift+T", tip="Aktive Verbindung trennen.")
        self.ble_diagnostics_action = make_action("Bluetooth-Diagnose", self.run_ble_diagnostics, shortcut="Ctrl+Shift+D", tip="Bluetooth und Sensorzustand prüfen.")
        device_menu.addActions([self.scan_action, self.connect_action, self.disconnect_action, self.ble_diagnostics_action])
        device_menu.addAction(make_action("Verbindungsassistent", self.show_connection_assistant, shortcut="Ctrl+Alt+A", tip="Geführte Hilfe bei Sensorverbindung."))

        # View: visual workspace.
        view_menu = menu_bar.addMenu("Ansicht")
        fullscreen_action = make_action("Vollbild", self.toggle_fullscreen, shortcut="F11", tip="Vollbild ein- oder ausschalten.")
        self.focus_action = make_action("Fokusansicht", lambda checked: self._set_focus_mode(bool(checked)), shortcut="Ctrl+Shift+F", checkable=True, checked=self.focus_mode, tip="Training visuell reduzieren.")
        self.plot_action = make_action("HRV-Spur anzeigen", lambda checked: self._set_plot_visible(bool(checked)), shortcut="Ctrl+P", checkable=True, checked=self.plot_visible, tip="Einzelnen HRV-Amplituden-Graphen ein- oder ausblenden.")
        self.calm_visuals_action = make_action("Ruhige HRV-Spur", lambda checked: self._set_calm_visuals_enabled(bool(checked)), shortcut="Ctrl+Alt+G", checkable=True, checked=self.calm_visuals_enabled, tip="Display-Glättung und stabile Graph-Skalierung verwenden. Messdaten bleiben unverändert.")
        self.reduced_motion_action = make_action("Reduzierte Bewegung", lambda checked: self._set_reduced_motion_enabled(bool(checked)), shortcut="Ctrl+Alt+R", checkable=True, checked=self.reduced_motion_enabled, tip="Konservative Bewegungs-/Animationspolitik für einen ruhigeren Trainingsraum.")
        view_menu.addActions([fullscreen_action, self.focus_action, self.plot_action, self.calm_visuals_action, self.reduced_motion_action])
        view_menu.addAction(make_action("Dashboard zurücksetzen", self.reset_dashboard_layout, shortcut="Ctrl+Alt+0", tip="Fensterlayout zurücksetzen."))
        appearance_menu = view_menu.addMenu("Darstellung")
        self.system_theme_action = make_action("Systemdesign", lambda: self.set_appearance("system"), checkable=True, checked=self.appearance == "system", tip="Windows-Systemdesign verwenden.")
        self.dark_theme_action = make_action("Darkmode", lambda: self.set_appearance("dark"), checkable=True, checked=self.appearance == "dark", tip="Dunkle Oberfläche verwenden.")
        self.light_theme_action = make_action("Lightmode", lambda: self.set_appearance("light"), checkable=True, checked=self.appearance == "light", tip="Helle Oberfläche verwenden.")
        appearance_menu.addActions([self.system_theme_action, self.dark_theme_action, self.light_theme_action])

        # Evaluation: data after the session.
        evaluation_menu = menu_bar.addMenu("Auswertung")
        evaluation_menu.addAction(make_action("Letzte Sitzungen", self.show_recent_sessions, shortcut="Ctrl+Alt+R", tip="Gespeicherte Sitzungen anzeigen."))
        evaluation_menu.addAction(make_action("Sitzungsordner öffnen", self.open_sessions_folder, tip="CSV- und Metadatendateien öffnen."))
        evaluation_menu.addAction(make_action("Diagnosebericht speichern", self.save_diagnostics_report, shortcut="Ctrl+Alt+S", tip="System- und App-Diagnose dokumentieren."))

        # Help: orientation + expert tools through progressive disclosure.
        help_menu = menu_bar.addMenu("Hilfe")
        help_menu.addAction(make_action("Einführung", self.show_introduction, tip="Einführung erneut öffnen."))
        help_menu.addAction(make_action("Verbindungsassistent", self.show_connection_assistant, shortcut="Ctrl+Alt+A", tip="Verbindungshilfe öffnen."))
        help_menu.addAction(make_action("Tastenkürzel", self.show_shortcuts_dialog, shortcut="F1", tip="Tastenkürzel anzeigen."))
        help_menu.addAction(make_action("Über HRV Biofeedback", self.show_about_dialog, tip="App-Version und lokale Datenhinweise anzeigen."))
        expert_menu = help_menu.addMenu("Expertenbereich")
        expert_menu.addAction(make_action("Selbsttest ausführen", self.run_self_test, shortcut="Ctrl+Alt+T", tip="Lokale Kernfunktionen prüfen."))
        expert_menu.addAction(make_action("Bibliotheken & UX-Potenzial", self.show_library_ux_report, shortcut="Ctrl+Alt+U", tip="Optionale Python-Bibliotheken und passende UX-Ideen anzeigen."))
        expert_menu.addAction(make_action("Interaktionsdesign & Adaptivität", self.show_interaction_design_report, shortcut="Ctrl+Alt+J", tip="Aktuelle UI-Adaptivität, Komplementarität und Bewegungsregeln anzeigen."))
        expert_menu.addAction(make_action("Supportpaket speichern", self.save_support_bundle, shortcut="Ctrl+Alt+B", tip="Redaktiertes Support-ZIP erstellen."))
        expert_menu.addAction(make_action("Logdatei öffnen", self.open_log_file, shortcut="Ctrl+L", tip="Logdatei öffnen."))
        expert_menu.addAction(make_action("Debugordner öffnen", self.open_debug_folder, shortcut="Ctrl+Alt+D", tip="Debugordner öffnen."))
        expert_menu.addAction(make_action("Datenordner öffnen", self.open_data_folder, shortcut="Ctrl+O", tip="Datenordner öffnen."))
        expert_menu.addAction(make_action("Monitor-/Display-Info", self.show_display_info, shortcut="Ctrl+Alt+I", tip="Display-Snapshot anzeigen."))
        expert_menu.addAction(make_action("Windows Bluetooth-Einstellungen", lambda: self.open_windows_settings_page("bluetooth"), tip="Windows-Bluetooth-Einstellungen öffnen."))
        expert_menu.addAction(make_action("Windows Anzeige-Einstellungen", lambda: self.open_windows_settings_page("display"), tip="Windows-Anzeigeeinstellungen öffnen."))

        # Background model stays enabled by default but not exposed in the menu.
        self.green_circle_action = QAction("HRV-Amplitude · Grüner Kreis", self)
        self.green_circle_action.setCheckable(True)
        self.green_circle_action.setChecked(True)
        self.background_stabilization_action = QAction("Adaptive Stabilisierung", self)
        self.background_stabilization_action.setCheckable(True)
        self.background_stabilization_action.setChecked(self.sem_live_enabled)
        self.background_stabilization_action.triggered.connect(self.set_sem_live_enabled)

    def show_library_ux_report(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Bibliotheken & UX-Potenzial")
        dialog.resize(900, 700)
        layout = QVBoxLayout(dialog)
        intro = QLabel(
            "Lokaler Capability-Scan: Welche vorhandenen und optionalen Python-Bibliotheken passen zur App, "
            "ohne den Trainingsraum zu überladen."
        )
        intro.setObjectName("HintLabel")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        text = QTextEdit()
        text.setReadOnly(True)
        text.setPlainText(capability_report_text())
        layout.addWidget(text, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def show_interaction_design_report(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Interaktionsdesign & Adaptivität")
        dialog.resize(860, 680)
        layout = QVBoxLayout(dialog)
        intro = QLabel(
            "Zeigt, wie die App Komplementarität, adaptive Sichtbarkeit und reduzierte kognitive Last im Training steuert."
        )
        intro.setObjectName("HintLabel")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        text = QTextEdit()
        text.setReadOnly(True)
        current_profile = None
        if self._last_interaction_profile:
            try:
                from hrv_interaction_design import InteractionProfile
                current_profile = InteractionProfile(**self._last_interaction_profile)
            except Exception:
                current_profile = None
        text.setPlainText(interaction_design_report_text(current_profile))
        layout.addWidget(text, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def show_introduction(self, first_run: bool = False) -> None:
        dialog = IntroductionDialog(self)
        if first_run:
            dialog.do_not_show.setChecked(True)
        if dialog.exec() == QDialog.Accepted:
            if dialog.do_not_show.isChecked():
                self.config["onboarding_completed"] = True
                save_config(self.config)
            if dialog.choice == "assistant":
                self.show_connection_assistant()
            elif dialog.choice == "mock":
                if self.phase == "idle":
                    self.start_training_with_baseline()
                    self.skip_baseline()
                if not self.mock_timer.isActive():
                    self.toggle_mock()

    def show_connection_assistant(self) -> None:
        dialog = ConnectionAssistantDialog(self)
        if dialog.exec() == QDialog.Accepted:
            if dialog.choice == "auto":
                self.auto_connect_ble()
            elif dialog.choice == "scan":
                self.scan_ble()
            elif dialog.choice == "diagnostics":
                self.run_ble_diagnostics()

    def show_status_diagnostics(self) -> None:
        """Show a single, action-oriented status report for connection and app state."""
        report = self.run_ble_diagnostics(auto=False, show_dialog=False)
        saved_path = Path(str(report.get("_saved_path", DEBUG_DIR)))
        category, suggestion = classify_ble_error(self.last_ble_error) if self.last_ble_error else ("", "")
        selected = self.device_combo.currentText() if hasattr(self, "device_combo") else "—"
        rr_count = len(self.session_rows)
        service_count = len(self.last_service_dump.get("services", [])) if self.last_service_dump else 0
        stream_summary = (
            f"Pakete: {self.ble_packet_count} · "
            f"RR-Pakete: {self.ble_rr_packet_count} · "
            f"RR-Werte: {self.ble_rr_value_count} · "
            f"BPM-only: {self.ble_hr_only_packet_count}"
        )
        if self.input_mode == "ble" and self.ble_packet_count > 0 and self.ble_rr_value_count == 0:
            next_step = (
                "Sensor sendet bisher nur Herzrate, keine RR-Intervalle. Gurt/Kontakt prüfen, "
                "andere Apps/Smartphones trennen und Auto verbinden erneut ausführen. Für HRV werden echte RR-Werte benötigt."
            )
        elif self.input_mode == "ble" and self.ble_rr_value_count > 0 and self.phase == "idle":
            next_step = "RR-Daten kommen an. Training starten oder Baseline überspringen."
        else:
            next_step = suggestion or (
                "Auto verbinden ausführen." if not self.devices else
                "Ausgewähltes Gerät verbinden und auf RR-Werte warten." if self.input_mode != "ble" else
                "Wenn keine Werte erscheinen: Kontakt prüfen und andere Apps/Smartphones trennen."
            )
        text = (
            "Status & Diagnose\n"
            f"Gespeichert: {saved_path}\n\n"
            f"Phase: {PHASE_LABELS.get(self.phase, self.phase)}\n"
            f"Input: {self.input_mode}\n"
            f"Ausgewähltes Gerät: {selected}\n"
            f"Gefundene Geräte: {len(self.devices)}\n"
            f"Gelesene GATT-Services: {service_count}\n"
            f"Datenzeilen in aktueller Sitzung: {rr_count}\n"
            f"BLE-Datenstrom: {stream_summary}\n"
            f"Letzte Herzrate: {self.last_ble_bpm if self.last_ble_bpm is not None else '—'}\n"
            f"Letztes RR-Intervall: {self.last_ble_rr_ms if self.last_ble_rr_ms is not None else '—'}\n"
            f"Sensor-Hinweis: {self.last_ble_stream_hint}\n"
            f"Letzter BLE-Hinweis: {self.last_ble_error or '—'}\n"
            f"Nächster sinnvoller Schritt: {next_step}\n\n"
            "Hinweis: Datenzeilen entstehen nur während einer Referenz-, Baseline- oder Trainingssitzung. "
            "Vor dem Start zeigt der BLE-Datenstrom, ob der Sensor grundsätzlich RR-Werte sendet.\n\n"
            "Bluetooth-Diagnose\n"
            "-------------------\n"
            f"{diagnostic_report_to_text(report)}"
        )
        dialog = BleDiagnosticsDialog(text, saved_path, self)
        dialog.setWindowTitle("Status & Diagnose")
        dialog.exec()

    def show_recent_sessions(self) -> None:
        """List recent CSV session exports without introducing a database dependency."""
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        files = sorted(SESSIONS_DIR.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)[:15]
        if not files:
            text = "Noch keine gespeicherten Sitzungen gefunden.\n\nSitzungen werden als CSV-Dateien im lokalen Sitzungsordner gespeichert."
        else:
            lines = ["Letzte gespeicherte Sitzungen", "", f"Ordner: {SESSIONS_DIR}", ""]
            for idx, path in enumerate(files, start=1):
                try:
                    size_kb = path.stat().st_size / 1024
                    modified = time.strftime("%Y-%m-%d %H:%M", time.localtime(path.stat().st_mtime))
                    lines.append(f"{idx}. {path.name} · {modified} · {size_kb:.1f} KB")
                except Exception:
                    lines.append(f"{idx}. {path.name}")
            lines.append("\nÜber Datei > Datenordner öffnen kannst du die Dateien direkt öffnen oder sichern.")
            text = "\n".join(lines)
        dialog = QDialog(self)
        dialog.setWindowTitle("Letzte Sitzungen")
        dialog.setMinimumSize(760, 520)
        layout = QVBoxLayout(dialog)
        box = QTextEdit()
        box.setReadOnly(True)
        box.setPlainText(text)
        layout.addWidget(box, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dialog.reject)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)
        dialog.exec()

    @staticmethod
    def _model_gate_label(gate_reason: str) -> str:
        mapping = {
            "low_measurement_quality": "Messqualität bremst Rückmeldung",
            "latent_mismatch_observe": "Abweichung wird beobachtet",
            "sem_live_ok": "Rückmeldung stabil",
            "not_training": "außerhalb Training",
        }
        return mapping.get(gate_reason or "", "Hintergrundmodell")

    def show_about_dialog(self) -> None:
        QMessageBox.information(
            self,
            "Über HRV Biofeedback",
            f"{APP_NAME}\nVersion {APP_VERSION}\n\n"
            "Lokale Trainings- und Selbstbeobachtungssoftware für HRV-Biofeedback. "
            "Die App speichert Sitzungen, Logs und Debugdaten lokal im Dokumente-Ordner."
        )

    def _open_path(self, path: Path, title: str) -> None:
        try:
            open_path_or_uri(path)
        except Exception as exc:
            log_exception(self.logger, f"Could not open {title}: {path}", exc)
            QMessageBox.information(self, title, f"{title}:\n{path}\n\n{exc}")

    def save_diagnostics_report(self) -> None:
        report = {
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "system": app_system_snapshot(),
            "app_state": {
                "phase": self.phase,
                "input_mode": self.input_mode,
                "appearance": self.appearance,
                "audio_enabled": self.audio_enabled,
                "feedback_mode": self.feedback_mode,
                "sem_live_enabled": self.sem_live_enabled,
                "rows_in_memory": len(self.session_rows),
                "device_identifier_set": bool(self.device_identifier),
                "ble_worker_running": bool(self.ble_worker and self.ble_worker.isRunning()),
                "mock_active": self.mock_timer.isActive(),
            },
            "config_keys": sorted(self.config.keys()),
            "log_file": str(LOG_FILE),
            "ble_state": {
                "devices_seen": len(self.devices),
                "selected_device": self.device_combo.currentText() if hasattr(self, "device_combo") else "",
                "selected_address": str(self.device_combo.currentData() or "") if hasattr(self, "device_combo") else "",
                "last_ble_error": self.last_ble_error,
                "last_service_count": len(self.last_service_dump.get("services", [])) if self.last_service_dump else 0,
            },
        }
        path = DEBUG_DIR / f"diagnostics_{now_stamp()}.json"
        save_json(path, report)
        self.logger.info("Diagnostics report saved | path=%s", path)
        QMessageBox.information(self, "Diagnosebericht", f"Diagnosebericht gespeichert:\n{path}")


    def run_self_test(self) -> None:
        """Run a local, non-invasive app self-test and show an actionable result."""
        try:
            core_report = run_core_self_test()
            ble_report = build_ble_diagnostic_report(
                devices=self.devices,
                selected_device=self.device_combo.currentText() if hasattr(self, "device_combo") else "",
                selected_address=str(self.device_combo.currentData() or "") if hasattr(self, "device_combo") else "",
                last_error=self.last_ble_error,
                service_dump=self.last_service_dump,
                app_snapshot=app_system_snapshot(),
                include_windows_snapshot=True,
            )
            report = {"core": core_report, "bluetooth": ble_report, "created_at": now_stamp()}
            path = DEBUG_DIR / f"selftest_full_{now_stamp()}.json"
            save_json(path, report)
            ok = bool(core_report.get("ok", False))
            lines = ["Selbsttest", f"Gespeichert: {path}", ""]
            for check in core_report.get("checks", []) or []:
                status = str(check.get("status", "info")).upper()
                lines.append(f"- [{status}] {check.get('key', '')}: {check.get('detail', '')}")
                if check.get("suggestion"):
                    lines.append(f"  → {check.get('suggestion')}")
            win_summary = ble_report.get("windows_bluetooth_summary") or {}
            if win_summary:
                lines.extend(["", f"Windows-Bluetooth: {win_summary.get('status', '—')}"])
                for issue in win_summary.get("issues", []) or []:
                    lines.append(f"- {issue}")
            if ok:
                lines.append("\nLokale Kernfunktionen wirken verwendbar. Falls BLE nicht funktioniert, liegt der Fokus auf Sensor/Windows-Bluetooth/Verbindung.")
            else:
                lines.append("\nMindestens ein lokaler Kerncheck ist auffällig. Bitte die genannten Punkte vor dem Sensor-Test prüfen.")
            QMessageBox.information(self, "Selbsttest", "\n".join(lines))
        except Exception as exc:
            log_exception(self.logger, "Self-test failed", exc)
            QMessageBox.warning(self, "Selbsttest", f"Der Selbsttest konnte nicht abgeschlossen werden.\n\n{exc}")

    def save_support_bundle(self) -> None:
        """Create a redacted troubleshooting ZIP for sharing/debugging."""
        try:
            latest_ble = build_ble_diagnostic_report(
                devices=self.devices,
                selected_device=self.device_combo.currentText() if hasattr(self, "device_combo") else "",
                selected_address=str(self.device_combo.currentData() or "") if hasattr(self, "device_combo") else "",
                last_error=self.last_ble_error,
                service_dump=self.last_service_dump,
                app_snapshot=app_system_snapshot(),
                include_windows_snapshot=True,
            )
            path = DEBUG_DIR / f"support_bundle_redacted_{now_stamp()}.zip"
            create_redacted_support_bundle(
                output_path=path,
                app_snapshot=app_system_snapshot(),
                debug_dir=DEBUG_DIR,
                logs_dir=LOGS_DIR,
                config_path=CONFIG_PATH,
                extra_report=latest_ble,
            )
            QMessageBox.information(
                self,
                "Supportpaket gespeichert",
                f"Redaktiertes Supportpaket gespeichert:\n{path}\n\nEs enthält keine absichtlich unredigierten Rohpaket-Logs.",
            )
            self.statusBar().showMessage(f"Supportpaket gespeichert: {path}")
        except Exception as exc:
            log_exception(self.logger, "Support bundle creation failed", exc)
            QMessageBox.warning(self, "Supportpaket", f"Das Supportpaket konnte nicht erstellt werden.\n\n{exc}")

    def run_ble_diagnostics(self, checked: bool = False, *, auto: bool = False, show_dialog: bool = True) -> dict[str, Any]:  # noqa: ARG002
        """Create a non-invasive BLE diagnostic report; optionally show it."""
        selected_address = str(self.device_combo.currentData() or "") if hasattr(self, "device_combo") else ""
        selected_device = self.device_combo.currentText() if hasattr(self, "device_combo") else ""
        report = build_ble_diagnostic_report(
            devices=self.devices,
            selected_device=selected_device,
            selected_address=selected_address,
            last_error=self.last_ble_error,
            service_dump=self.last_service_dump,
            app_snapshot={
                **app_system_snapshot(),
                "display": collect_display_snapshot(),
                "ble_state": self.ble_state.snapshot.to_dict() if hasattr(self, "ble_state") else {},
                "visible_product_contract": visible_training_contract(),
                "ble_stream": {
                    "packet_count": self.ble_packet_count,
                    "rr_packet_count": self.ble_rr_packet_count,
                    "rr_value_count": self.ble_rr_value_count,
                    "hr_only_packet_count": self.ble_hr_only_packet_count,
                    "last_bpm": self.last_ble_bpm,
                    "last_rr_ms": self.last_ble_rr_ms,
                    "hint": self.last_ble_stream_hint,
                    "session_rows": len(self.session_rows),
                    "phase": self.phase,
                },
            },
            include_windows_snapshot=not auto,
        )
        path = DEBUG_DIR / f"ble_diagnostics_{now_stamp()}.json"
        report["_saved_path"] = str(path)
        save_json(path, report)
        self.logger.info("BLE diagnostics saved | auto=%s path=%s", auto, path)
        report_text = diagnostic_report_to_text(report)
        if auto:
            self.statusBar().showMessage(f"Bluetooth-Diagnose gespeichert: {path}")
        if show_dialog:
            dialog = BleDiagnosticsDialog(report_text, path, self)
            dialog.exec()
        return report

    def edit_session_context(self) -> None:
        dialog = SessionContextDialog(self.session_context, self)
        if dialog.exec() == QDialog.Accepted:
            self.session_context = dialog.context()
            self.config["session_context"] = self.session_context
            save_config(self.config)
            self.statusBar().showMessage("Kontextangaben gespeichert.")

    def show_protocol_note(self) -> None:
        learning = learning_protocol()
        QMessageBox.information(
            self,
            "Protokollnotiz",
            "Aktueller Modus: Individual HRVB ohne Atem-Pacer.\n\n"
            "Vorbereitung: Sensor, Kontext, Selbstcheck und ein optionaler Lernfokus werden erfasst.\n"
            "Training: Der grüne Kreis verstärkt primär HRV-Amplitude. Kurze Aufmerksamkeitsanker unterstützen Selbstregulation, ohne Leistungsdruck zu erzeugen.\n"
            "Nachbereitung: Messdaten, Signalqualität, Selbstcheck-Veränderungen, Reflexion und Mini-Transferplan werden lokal dokumentiert.\n\n"
            f"Feedbackprinzip: {learning.reinforcement_principle}\n\n"
            f"Transferprinzip: {learning.transfer_principle}\n\n"
            f"Grenze der Interpretation: {learning.interpretation_boundary}\n\n"
            "Optimal-RF- und Preset-Pace-Protokolle sind als spätere Erweiterung vorbereitet."
        )

    def set_appearance(self, mode: str) -> None:
        self.appearance = mode
        self.config["appearance"] = mode
        save_config(self.config)
        self.apply_appearance(mode)

    def apply_appearance(self, mode: str) -> None:
        app = QApplication.instance()
        if app is None:
            return

        effective = mode
        if mode == "system":
            effective = self._detect_system_appearance()

        if effective == "dark":
            pal = QPalette()
            pal.setColor(QPalette.Window, QColor(18, 22, 27))
            pal.setColor(QPalette.WindowText, QColor(235, 239, 244))
            pal.setColor(QPalette.Base, QColor(13, 17, 23))
            pal.setColor(QPalette.AlternateBase, QColor(29, 35, 42))
            pal.setColor(QPalette.Text, QColor(235, 239, 244))
            pal.setColor(QPalette.Button, QColor(31, 39, 48))
            pal.setColor(QPalette.ButtonText, QColor(235, 239, 244))
            pal.setColor(QPalette.Highlight, QColor(47, 129, 247))
            pal.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
            app.setPalette(pal)
            app.setStyleSheet(self._dark_stylesheet())
            if pg is not None:
                pg.setConfigOption("background", (18, 22, 27))
                pg.setConfigOption("foreground", (215, 221, 228))
                self._style_plot(dark=True)
        else:
            app.setPalette(app.style().standardPalette())
            app.setStyleSheet(self._light_stylesheet())
            if pg is not None:
                pg.setConfigOption("background", "w")
                pg.setConfigOption("foreground", (40, 45, 50))
                self._style_plot(dark=False)

        self.system_theme_action.setChecked(mode == "system")
        self.dark_theme_action.setChecked(mode == "dark")
        self.light_theme_action.setChecked(mode == "light")
        self.circle.update()

    def _style_plot(self, *, dark: bool) -> None:
        if self.plot is None or self.hrv_curve is None or pg is None:
            return
        self.plot.setBackground((18, 22, 27) if dark else "w")
        self.plot.getAxis("bottom").setPen(pg.mkPen("#7b8794" if dark else "#94a3b8"))
        self.plot.getAxis("left").setPen(pg.mkPen("#7b8794" if dark else "#94a3b8"))
        self.plot.getAxis("bottom").setTextPen(pg.mkPen("#cbd5e1" if dark else "#475569"))
        self.plot.getAxis("left").setTextPen(pg.mkPen("#cbd5e1" if dark else "#475569"))
        self.hrv_curve.setPen(pg.mkPen("#34d399" if dark else "#15803d", width=3))

    @staticmethod
    def _detect_system_appearance() -> str:
        app = QApplication.instance()
        if app is None:
            return detect_windows_app_theme()
        try:
            scheme = app.styleHints().colorScheme()
            if hasattr(Qt, "ColorScheme") and scheme == Qt.ColorScheme.Dark:
                return "dark"
            if str(scheme).lower().endswith("dark"):
                return "dark"
        except Exception:
            pass
        return detect_windows_app_theme()

    @staticmethod
    def _base_stylesheet(tokens: dict[str, str]) -> str:
        return f"""
        QWidget#AppRoot {{ background: {tokens['bg']}; color: {tokens['text']}; font-size: 10.5pt; }}
        QMainWindow {{ background: {tokens['bg']}; }}
        QMenuBar {{ background: {tokens['surface']}; color: {tokens['text']}; border-bottom: 1px solid {tokens['border']}; padding: 3px 6px; }}
        QMenuBar::item {{ padding: 7px 10px; border-radius: 8px; }}
        QMenuBar::item:selected {{ background: {tokens['hover']}; }}
        QMenu {{ background: {tokens['surface']}; color: {tokens['text']}; border: 1px solid {tokens['border']}; padding: 6px; }}
        QMenu::item {{ padding: 7px 24px 7px 12px; border-radius: 7px; }}
        QMenu::item:selected {{ background: {tokens['hover']}; }}
        QFrame#HeaderCard, QFrame#CommandPanel, QFrame#MetricPanel, QFrame#FeedbackCard, QFrame#PlotCard,
        QFrame#HeroCard, QFrame#InfoCard, QFrame#TrainingControlCard {{
            background: {tokens['surface']}; border: 1px solid {tokens['border']}; border-radius: 18px;
        }}
        QFrame#RoleCard {{
            background: {tokens['surface2']}; border: 1px solid {tokens['border']}; border-radius: 16px;
        }}
        QFrame#MetricCard {{
            background: {tokens['surface2']}; border: 1px solid {tokens['border']}; border-radius: 14px;
            min-height: 74px;
        }}
        QFrame#WorkflowStep {{ background: {tokens['input']}; border: 1px solid {tokens['border']}; border-radius: 14px; }}
        QFrame#WorkflowStep[tone="active"] {{ background: {tokens['active_bg']}; border-color: {tokens['active_border']}; }}
        QFrame#WorkflowStep[tone="good"] {{ background: {tokens['good_bg']}; border-color: {tokens['good_border']}; }}
        QFrame#WorkflowStep[tone="warn"] {{ background: {tokens['warn_bg']}; border-color: {tokens['warn_border']}; }}
        QLabel#AppTitle {{ font-size: 21pt; font-weight: 750; color: {tokens['text']}; letter-spacing: -0.03em; }}
        QLabel#PhaseTitle {{ font-size: 24pt; font-weight: 820; color: {tokens['text']}; letter-spacing: -0.04em; }}
        QLabel#PhaseTitleSmall {{ font-size: 15pt; font-weight: 800; color: {tokens['text']}; letter-spacing: -0.02em; }}
        QLabel#PhaseSubtitle {{ font-size: 11pt; color: {tokens['muted']}; }}
        QLabel#AppSubtitle, QLabel#HintLabel, QLabel#MetricHelper, QLabel#StepHelper {{ color: {tokens['muted']}; }}
        QLabel#NextStepLabel {{ color: {tokens['accent']}; font-weight: 650; padding-top: 4px; }}
        QLabel#SectionLabel {{ color: {tokens['accent']}; font-size: 9pt; font-weight: 750; letter-spacing: 0.08em; text-transform: uppercase; }}
        QLabel#PanelTitle {{ font-size: 12.5pt; font-weight: 750; color: {tokens['text']}; }}
        QLabel#ProtocolValue {{ font-size: 12pt; font-weight: 700; color: {tokens['text']}; }}
        QLabel#MetricTitle {{ color: {tokens['muted']}; font-size: 8.7pt; font-weight: 650; }}
        QLabel#MetricValue {{ color: {tokens['text']}; font-size: 17pt; font-weight: 760; letter-spacing: -0.02em; }}
        QLabel#StepTitle {{ color: {tokens['text']}; font-weight: 700; }}
        QLabel#StepNumber {{ background: {tokens['surface']}; color: {tokens['accent']}; border: 1px solid {tokens['border']}; border-radius: 14px; font-weight: 800; }}
        QLabel#TimerLabel {{ color: {tokens['text']}; font-size: 22pt; font-weight: 800; padding: 0 8px; min-width: 92px; }}
        QLabel#StatusPill {{ border-radius: 14px; padding: 5px 13px; background: {tokens['pill']}; color: {tokens['text']}; border: 1px solid {tokens['border']}; min-width: 76px; }}
        QLabel#StatusPill[tone="good"] {{ background: {tokens['good_bg']}; color: {tokens['good_text']}; border-color: {tokens['good_border']}; }}
        QLabel#StatusPill[tone="warn"] {{ background: {tokens['warn_bg']}; color: {tokens['warn_text']}; border-color: {tokens['warn_border']}; }}
        QLabel#StatusPill[tone="active"] {{ background: {tokens['active_bg']}; color: {tokens['active_text']}; border-color: {tokens['active_border']}; }}
        QPushButton {{
            background: {tokens['button']}; color: {tokens['text']}; border: 1px solid {tokens['border']};
            border-radius: 11px; padding: 8px 12px; font-weight: 600;
        }}
        QPushButton:hover {{ background: {tokens['hover']}; }}
        QPushButton:pressed {{ background: {tokens['pressed']}; }}
        QPushButton:disabled {{ color: {tokens['disabled_text']}; background: {tokens['disabled_bg']}; border-color: {tokens['border']}; }}
        QPushButton#PrimaryButton {{ background: {tokens['primary']}; color: white; border-color: {tokens['primary']}; font-weight: 800; }}
        QPushButton#PrimaryButton:hover {{ background: {tokens['primary_hover']}; }}
        QPushButton#DangerButton {{ background: {tokens['danger_bg']}; color: {tokens['danger_text']}; border-color: {tokens['danger_border']}; font-weight: 700; }}
        QPushButton#SubtleButton {{ color: {tokens['muted']}; }}
        QComboBox, QLineEdit, QTextEdit {{
            background: {tokens['input']}; color: {tokens['text']}; border: 1px solid {tokens['border']};
            border-radius: 10px; padding: 7px; selection-background-color: {tokens['accent']};
        }}
        QProgressBar {{ background: {tokens['input']}; border: 1px solid {tokens['border']}; border-radius: 7px; height: 12px; }}
        QProgressBar::chunk {{ background: {tokens['accent']}; border-radius: 6px; }}
        QScrollArea {{ background: transparent; border: none; }}
        QStatusBar {{ background: {tokens['surface']}; color: {tokens['muted']}; border-top: 1px solid {tokens['border']}; }}
        """

    @classmethod
    def _dark_stylesheet(cls) -> str:
        return cls._base_stylesheet(
            {
                "bg": "#0f141a",
                "surface": "#151b23",
                "surface2": "#1a222c",
                "text": "#e6edf3",
                "muted": "#9aa7b4",
                "border": "#2a3441",
                "hover": "#202a35",
                "pressed": "#263342",
                "button": "#1f2935",
                "input": "#10161d",
                "pill": "#1f2935",
                "accent": "#58c27d",
                "primary": "#238636",
                "primary_hover": "#2ea043",
                "danger_bg": "#2a1a1d",
                "danger_text": "#ffb4b4",
                "danger_border": "#5c2b31",
                "disabled_bg": "#161b22",
                "disabled_text": "#59636e",
                "good_bg": "#143222",
                "good_text": "#a7f3c1",
                "good_border": "#2d7a4a",
                "warn_bg": "#332a13",
                "warn_text": "#fbd38d",
                "warn_border": "#80621f",
                "active_bg": "#102b40",
                "active_text": "#b9e6ff",
                "active_border": "#2b6f9d",
            }
        )

    @classmethod
    def _light_stylesheet(cls) -> str:
        return cls._base_stylesheet(
            {
                "bg": "#f5f7fa",
                "surface": "#ffffff",
                "surface2": "#f8fafc",
                "text": "#17202a",
                "muted": "#64748b",
                "border": "#d9e2ec",
                "hover": "#edf3f8",
                "pressed": "#e2eaf2",
                "button": "#ffffff",
                "input": "#ffffff",
                "pill": "#f1f5f9",
                "accent": "#16803c",
                "primary": "#18803a",
                "primary_hover": "#0f6c2f",
                "danger_bg": "#fff1f2",
                "danger_text": "#9f1239",
                "danger_border": "#fecdd3",
                "disabled_bg": "#f1f5f9",
                "disabled_text": "#94a3b8",
                "good_bg": "#dcfce7",
                "good_text": "#166534",
                "good_border": "#86efac",
                "warn_bg": "#fef3c7",
                "warn_text": "#92400e",
                "warn_border": "#fde68a",
                "active_bg": "#dbeafe",
                "active_text": "#1e40af",
                "active_border": "#93c5fd",
            }
        )

    def set_feedback_mode(self, mode: str) -> None:
        self.feedback_mode = mode
        self.green_circle_action.setChecked(mode == "green_circle")
        self._update_feedback_state_label()
        self.statusBar().showMessage("Trainingssignal: HRV-Amplitude")

    def set_audio_enabled(self, enabled: bool) -> None:
        self.audio_enabled = enabled
        self.config["audio_enabled"] = enabled
        save_config(self.config)
        self._update_feedback_state_label()
        self.statusBar().showMessage("Audio aktiviert" if enabled else "Audio deaktiviert")

    def set_sem_live_enabled(self, enabled: bool) -> None:
        self.sem_live_enabled = bool(enabled)
        self.feedback.set_sem_live_enabled(self.sem_live_enabled)
        self.config["background_model_enabled"] = self.sem_live_enabled
        self.config["sem_live_enabled"] = self.sem_live_enabled
        save_config(self.config)
        self._update_feedback_state_label()
        if hasattr(self, "background_stabilization_action"):
            self.background_stabilization_action.setChecked(self.sem_live_enabled)
        self.statusBar().showMessage(
            "Adaptive Stabilisierung aktiv" if self.sem_live_enabled else "Adaptive Stabilisierung deaktiviert"
        )

    def _update_feedback_state_label(self) -> None:
        audio = "Audio an" if self.audio_enabled else "Audio aus"
        self.feedback_state_label.setText(f"Grüner Kreis · HRV-Amplitude · positive Rückmeldung · {audio}")

    def _set_focus_mode(self, enabled: bool, *, save: bool = True) -> None:
        self.focus_mode = enabled
        # Focus mode removes the optional context/detail channels. Signal repair
        # can still show the minimal details needed to make the next step clear.
        self._apply_adaptive_training_policy(self._last_metrics)
        if hasattr(self, "focus_action"):
            self.focus_action.setChecked(enabled)
        if save:
            self.config["focus_mode"] = enabled
            save_config(self.config)

    def _set_plot_visible(self, visible: bool, *, save: bool = True) -> None:
        self.plot_visible = visible
        self._apply_adaptive_training_policy(self._last_metrics)
        if hasattr(self, "plot_action"):
            self.plot_action.setChecked(visible)
        if save:
            self.config["plot_visible"] = visible
            save_config(self.config)

    def _set_calm_visuals_enabled(self, enabled: bool, *, save: bool = True) -> None:
        self.calm_visuals_enabled = bool(enabled)
        if hasattr(self, "calm_visuals_action"):
            self.calm_visuals_action.setChecked(self.calm_visuals_enabled)
        # Repaint the current plot with the chosen display policy. This does
        # not alter stored RR or HRV values.
        if self.plot is not None and self.hrv_curve is not None and self._plot_hrv_amp:
            display_values = smooth_display_series(self._plot_hrv_amp, enabled=self.calm_visuals_enabled)
            self.hrv_curve.setData(self._plot_elapsed, display_values)
            display_range = calm_graph_y_range(display_values, previous_y_max=None)
            self._plot_y_max = display_range.y_max
            self.plot.setYRange(display_range.y_min, display_range.y_max, padding=0.04)
        if save:
            self.config["calm_visuals_enabled"] = self.calm_visuals_enabled
            save_config(self.config)

    def _set_training_details_visible(self, visible: bool, *, save: bool = True) -> None:
        self.training_details_visible = bool(visible)
        self._apply_adaptive_training_policy(self._last_metrics)
        if hasattr(self, "details_button"):
            was_blocked = self.details_button.blockSignals(True)
            self.details_button.setChecked(self.training_details_visible)
            self.details_button.blockSignals(was_blocked)
        if save:
            self.config["training_details_visible"] = self.training_details_visible
            save_config(self.config)

    def _set_reduced_motion_enabled(self, enabled: bool, *, save: bool = True) -> None:
        self.reduced_motion_enabled = bool(enabled)
        self._apply_adaptive_training_policy(self._last_metrics)
        if hasattr(self, "reduced_motion_action"):
            self.reduced_motion_action.setChecked(self.reduced_motion_enabled)
        if save:
            self.config["reduced_motion_enabled"] = self.reduced_motion_enabled
            save_config(self.config)

    def toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def keyPressEvent(self, event: Any) -> None:
        if event.key() == Qt.Key_F11:
            self.toggle_fullscreen()
            event.accept()
            return
        if event.key() == Qt.Key_Escape and (self.isFullScreen() or self.focus_mode):
            self._exit_focus_or_fullscreen()
            event.accept()
            return
        super().keyPressEvent(event)

    def scan_ble(self, checked: bool = False, *, timeout: float | None = None) -> None:  # noqa: ARG002
        if self.ble_worker and self.ble_worker.isRunning():
            self.statusBar().showMessage("BLE-Aufgabe läuft bereits.")
            return
        self.last_ble_error = ""
        self.ble_state.transition(BleConnectionState.SCANNING, "Suche nach HRV-Sensoren")
        self.input_mode = "ble_scan"
        self._update_header_state()
        self._update_controls()
        self.ble_worker = BleWorker("scan", parent=self, scan_timeout=float(timeout or 7.0))
        self.ble_worker.status.connect(self.statusBar().showMessage)
        self.ble_worker.scan_finished.connect(self._on_scan_finished)
        self.ble_worker.error.connect(self._on_ble_error)
        self.ble_worker.finished.connect(self._on_ble_worker_finished)
        self.ble_worker.start()

    def _on_scan_finished(self, devices: list[dict[str, Any]]) -> None:
        devices = sort_devices_for_connection(devices)
        self.devices = devices
        self.device_combo.clear()
        for dev in devices:
            name = dev.get("name") or "Unbekanntes Gerät"
            address = dev.get("address") or ""
            rssi = dev.get("rssi")
            signal = dev.get("signal_label") or "?"
            label = dev.get("connection_label") or "unklar"
            suffix = f" | RSSI {rssi} · {signal}" if rssi is not None else f" | {signal}"
            self.device_combo.addItem(f"{name} | {address}{suffix} · {label}", userData=address)
        if devices:
            self.ble_state.transition(BleConnectionState.CANDIDATE_FOUND, f"{len(devices)} Gerät(e) gefunden")
            self.ble_auto_recovery_attempts = 0
            self.auto_scan_pass = 0
            self.device_hint.setText(summarize_candidates_for_user(devices))
            if self.pending_auto_connect:
                self.pending_auto_connect = False
                best = select_best_ble_device(devices, preferred_name=self.device_combo.currentText() if hasattr(self, "device_combo") else "")
                if best:
                    address = best.get("address")
                    for idx in range(self.device_combo.count()):
                        if self.device_combo.itemData(idx) == address:
                            self.device_combo.setCurrentIndex(idx)
                            break
                    self.statusBar().showMessage("Wahrscheinlichstes Gerät ausgewählt. Verbindung startet ...")
                    QTimer.singleShot(250, self.connect_ble)
        else:
            self.ble_state.transition(BleConnectionState.FAILED, "Kein BLE-Gerät gefunden", error="no_device_found")
            self.last_ble_error = "Kein BLE-Gerät gefunden. Sensor aktivieren, näher an den Laptop bringen und andere Apps/Smartphones trennen."
            self.device_hint.setText("Kein BLE-Gerät gefunden. Sensor aktivieren, Abstand verringern und erneut scannen.")
            was_auto = self.pending_auto_connect
            self.pending_auto_connect = False
            QTimer.singleShot(200, lambda: self.run_ble_diagnostics(auto=True, show_dialog=False))
            if was_auto and self.auto_scan_pass < len(AUTO_SCAN_TIMEOUTS_S) - 1:
                self.auto_scan_pass += 1
                self.pending_auto_connect = True
                next_timeout = AUTO_SCAN_TIMEOUTS_S[self.auto_scan_pass]
                self.statusBar().showMessage(f"Kein Gerät gefunden. Ich wiederhole den Scan automatisch ({next_timeout:.0f} s) ...")
                QTimer.singleShot(1600, lambda: self.scan_ble(timeout=next_timeout))
                return
        self.statusBar().showMessage(f"{len(devices)} BLE-Geräte gefunden. Scan-Debug wurde gespeichert.")
        self._update_header_state()
        self._update_controls()

    def connect_ble(self, checked: bool = False) -> None:  # noqa: ARG002
        address = self.device_combo.currentData()
        if not address:
            self.statusBar().showMessage("Kein Gerät ausgewählt. Ich starte zuerst einen Scan.")
            self.pending_auto_connect = True
            self.scan_ble()
            return
        if self.ble_worker and self.ble_worker.isRunning():
            self.statusBar().showMessage("BLE-Aufgabe läuft bereits.")
            return
        self.last_ble_error = ""
        self.ble_state.reset_counters()
        self.ble_state.transition(BleConnectionState.CONNECTING, "Verbinde mit Sensor")
        self.last_ble_packet_monotonic = None
        self.last_ble_rr_monotonic = None
        self.ble_packet_count = 0
        self.ble_rr_packet_count = 0
        self.ble_rr_value_count = 0
        self.ble_hr_only_packet_count = 0
        self.last_ble_bpm = None
        self.last_ble_rr_ms = None
        self.last_ble_stream_hint = "Verbinde ..."
        self.input_mode = "ble"
        self.device_identifier = self.device_combo.currentText()
        self._update_header_state()
        self._update_controls()
        self.ble_worker = BleWorker("connect", address=address, parent=self, target_name=self.device_identifier)
        self.ble_worker.status.connect(self.statusBar().showMessage)
        self.ble_worker.packet_received.connect(self._on_ble_packet)
        self.ble_worker.services_finished.connect(self._on_services_finished)
        self.ble_worker.error.connect(self._on_ble_error)
        self.ble_worker.finished.connect(self._on_ble_worker_finished)
        self.ble_worker.start()

    def auto_connect_ble(self) -> None:
        if self.ble_worker and self.ble_worker.isRunning():
            self.statusBar().showMessage("BLE-Aufgabe läuft bereits.")
            return
        if self.device_combo.count() == 0:
            self.pending_auto_connect = True
            self.auto_scan_pass = 0
            first_timeout = AUTO_SCAN_TIMEOUTS_S[0]
            self.statusBar().showMessage(f"Auto-Verbindung: intelligenter Scan startet ({first_timeout:.0f} s) ...")
            self.scan_ble(timeout=first_timeout)
            return
        best = select_best_ble_device(self.devices, preferred_name=self.device_combo.currentText() if hasattr(self, "device_combo") else "")
        if best:
            address = best.get("address")
            for idx in range(self.device_combo.count()):
                if self.device_combo.itemData(idx) == address:
                    self.device_combo.setCurrentIndex(idx)
                    break
        self.connect_ble()

    def _on_services_finished(self, service_dump: dict[str, Any]) -> None:
        self.last_service_dump = service_dump or {}
        self.ble_state.transition(BleConnectionState.WAITING_FOR_RR, "GATT gelesen; warte auf RR-Intervalle")
        self.last_ble_stream_hint = "GATT ok; warte auf Heart-Rate-/RR-Notifications."
        self.statusBar().showMessage("GATT-Debug wurde gespeichert. Warte auf RR-Intervalle ...")
        self._update_header_state()

    def _on_ble_worker_finished(self) -> None:
        self._update_controls()
        if self.input_mode == "ble_scan":
            self.input_mode = "unknown" if not self.mock_timer.isActive() else "mock"
        elif self.input_mode == "ble" and not (self.ble_worker and self.ble_worker.isRunning()):
            if not self.mock_timer.isActive():
                self.input_pill.set_tone("warn", "BLE: getrennt")
        self._update_header_state()

    def disconnect_ble(self) -> None:
        if self.ble_worker and self.ble_worker.isRunning():
            self.ble_state.transition(BleConnectionState.DISCONNECTED, "Verbindung wird getrennt")
            self.ble_worker.stop()
            self.statusBar().showMessage("Trenne BLE-Verbindung ...")
        else:
            self.statusBar().showMessage("Keine aktive BLE-Verbindung.")

    def _on_ble_error(self, message: str) -> None:
        self.last_ble_error = message
        self.ble_state.transition(BleConnectionState.FAILED, "Bluetooth-Hinweis", error=message)
        info = describe_ble_error(message)
        category = str(info.get("category", "generic"))
        self.logger.warning("BLE issue | category=%s message=%s", category, message)
        self.statusBar().showMessage(f"{info.get('title', 'Bluetooth-Hinweis')}: {info.get('user_action', message)}")
        self.input_pill.set_tone("warn", "BLE: Hinweis")
        report = self.run_ble_diagnostics(auto=True, show_dialog=False)
        if self._maybe_auto_recover_ble(category, info):
            self.statusBar().showMessage(
                f"{info.get('title', 'Bluetooth-Hinweis')}: {info.get('automated_action', 'automatischer Wiederholversuch')}"
            )
            return
        report_text = diagnostic_report_to_text(report)
        saved_path = Path(str(report.get("_saved_path", DEBUG_DIR)))
        dialog = BleDiagnosticsDialog(report_text, saved_path, self)
        # The full report is already saved by run_ble_diagnostics; one dialog is
        # easier to follow than a warning followed by a second report window.
        dialog.exec()

    def _maybe_auto_recover_ble(self, category: str, info: dict[str, Any] | None = None) -> bool:
        info = info or describe_ble_error(self.last_ble_error)
        if not bool(info.get("can_auto_recover", True)):
            return False
        if category in {"missing_dependency", "no_standard_hr_service", "parse_error"}:
            return False
        if self.ble_auto_recovery_attempts >= BLE_AUTO_RECOVERY_MAX_ATTEMPTS:
            return False
        self.ble_auto_recovery_attempts += 1
        self.ble_state.transition(BleConnectionState.RECOVERING, "Automatische Wiederherstellung")
        delay_ms = 1000 + 900 * (self.ble_auto_recovery_attempts - 1)
        self.logger.info("Scheduling BLE auto recovery | attempt=%s category=%s", self.ble_auto_recovery_attempts, category)
        if self.ble_worker and self.ble_worker.isRunning():
            self.ble_worker.stop()

        # A fresh scan is more robust than reconnecting to the stale WinRT device
        # object after GATT/service/timeout problems.  The pending flag lets the
        # normal scan-finished path select the best device and connect.
        self.pending_auto_connect = True
        self.auto_scan_pass = min(self.ble_auto_recovery_attempts - 1, len(AUTO_SCAN_TIMEOUTS_S) - 1)
        timeout_s = AUTO_SCAN_TIMEOUTS_S[self.auto_scan_pass]
        QTimer.singleShot(delay_ms, lambda: self.scan_ble(timeout=timeout_s))
        return True

    def _on_ble_packet(self, payload: dict[str, Any]) -> None:
        try:
            self.ble_auto_recovery_attempts = 0
            self.last_ble_packet_monotonic = time.monotonic()
            self.ble_packet_count += 1
            raw_rr_values = payload.get("rr_ms")
            rr_values = sanitize_rr_values(raw_rr_values)
            bpm = payload.get("bpm")
            contact_supported = bool(payload.get("contact_supported", False))
            contact_detected = payload.get("contact_detected", None)
            if bpm is not None:
                try:
                    self.last_ble_bpm = float(bpm)
                except (TypeError, ValueError):
                    self.last_ble_bpm = None
            if rr_values:
                self.ble_state.note_packet(rr_values=len(rr_values))
                self.last_ble_rr_monotonic = time.monotonic()
                self.ble_rr_packet_count += 1
                self.ble_rr_value_count += len(rr_values)
                try:
                    self.last_ble_rr_ms = float(rr_values[-1])
                except (TypeError, ValueError):
                    self.last_ble_rr_ms = None
                self.last_ble_stream_hint = "RR-Intervalle aktiv. Training kann gestartet werden."
                self._update_ble_preview_cards(rr_available=True)
            else:
                bpm_only = bpm is not None
                self.ble_state.note_packet(rr_values=0, bpm_only=bpm_only)
                if bpm_only:
                    self.ble_hr_only_packet_count += 1
                # HRV feedback should be based on true RR intervals.  A BPM-only
                # packet is logged and shown diagnostically, but not converted
                # into synthetic RR because that would create artificial HRV.
                if bpm is not None:
                    self.last_ble_stream_hint = "Herzrate empfangen, RR-Intervalle fehlen noch."
                    self._update_ble_preview_cards(rr_available=False)
                    if self.ble_hr_only_packet_count in {1, 8, 20}:
                        self.statusBar().showMessage("BLE liefert Herzrate, aber noch keine RR-Intervalle.")
                self._update_header_state()
                return
            for rr in rr_values:
                self._handle_rr(
                    rr,
                    sensor_contact_supported=contact_supported,
                    sensor_contact_detected=contact_detected,
                )
        except Exception as exc:
            log_exception(self.logger, "BLE packet handling failed", exc)
            self.statusBar().showMessage("BLE-Paket konnte nicht verarbeitet werden. Details stehen in der Logdatei.")

    def _update_ble_preview_cards(self, *, rr_available: bool) -> None:
        """Show sensor-readiness even when no session is currently running.

        Session rows are only created during reference/baseline/training.  Before
        a session starts, users still need to know whether the sensor is sending
        useful RR intervals.  This preview prevents the confusing state
        "connected, but zero session rows" from looking like a sensor failure.
        """
        if self.phase != "idle":
            return
        if self.last_ble_bpm is not None:
            self.metric_cards["bpm"].set_value(f"{self.last_ble_bpm:.1f}", "Live-Vorschau")
        # RR preview is reflected through signal readiness.  The focused training
        # surface intentionally does not expose a separate RR card.
        if rr_available:
            self.metric_cards["quality"].set_value("bereit", f"{self.ble_rr_value_count} RR-Werte empfangen")
            self.quality_pill.set_tone("good", "Signal: RR aktiv")
            self.next_step_label.setText("Nächster Schritt: Training starten oder Baseline überspringen. RR-Daten kommen an.")
        else:
            self.metric_cards["quality"].set_value("prüfen", "BPM da, RR fehlt")
            self.quality_pill.set_tone("warn", "Signal: RR fehlt")
            self.next_step_label.setText("Sensor ist verbunden, aber RR-Intervalle fehlen noch. Kontakt prüfen und andere Apps/Smartphones trennen.")

    def toggle_mock(self) -> None:
        if self.mock_timer.isActive():
            self.mock_timer.stop()
            self.mock_button.setText("Mock Start")
            self.statusBar().showMessage("Mock-Modus gestoppt.")
            self.logger.info("Mock mode stopped")
        else:
            self.input_mode = "mock"
            self.device_identifier = "mock_rr_generator"
            self.mock_next_beat_s = 0.0
            self.mock_last_beat_s = self._elapsed_s()
            self.mock_timer.start(MOCK_TIMER_MS)
            self.mock_button.setText("Mock Stop")
            self.statusBar().showMessage("Mock-Modus gestartet.")
            self.logger.info("Mock mode started")
        self._update_header_state()

    def _mock_tick(self) -> None:
        if self.phase == "idle" or self.phase == "paused":
            return
        elapsed = self._elapsed_s()
        if elapsed < self.mock_next_beat_s:
            return
        hr = 68.0 + 7.5 * math.sin(2 * math.pi * 0.10 * elapsed) + random.gauss(0, 1.2)
        hr = max(48.0, min(105.0, hr))
        rr = 60000.0 / hr
        self.mock_next_beat_s = elapsed + rr / 1000.0
        self._handle_rr(rr)

    def start_reference(self) -> None:
        self._start_new_session(phase="reference", duration_s=REFERENCE_SECONDS, use_default_baseline=True)
        self.logger.info("Reference session started")
        self.statusBar().showMessage("10-minütige Referenzmessung gestartet. Feedback bleibt neutral.")

    def start_training_with_baseline(self) -> None:
        plan = self._current_guided_session_plan()
        self._last_guided_session_plan = plan.to_dict()
        if plan.plan_id == "prepare_sensor" and self.input_mode != "mock":
            self.statusBar().showMessage("Vor dem Training wird zuerst der Sensor vorbereitet.")
            self.auto_connect_ble()
            return
        if plan.plan_id == "repair_rr_stream" and self.input_mode != "mock":
            self.statusBar().showMessage("Vor dem Training bitte RR-Signal prüfen. Diagnose wird vorbereitet.")
            QTimer.singleShot(150, lambda: self.run_ble_diagnostics(auto=True, show_dialog=False))
            return
        if plan.baseline_recommended:
            self._start_new_session(phase="baseline", duration_s=TRAINING_SECONDS, use_default_baseline=False)
            self.logger.info("Training session started with baseline | baseline_s=%s plan=%s", BASELINE_SECONDS, plan.plan_id)
            self.statusBar().showMessage(f"Training gestartet. Baseline: {BASELINE_SECONDS} s.")
        else:
            self._start_new_session(phase="training", duration_s=TRAINING_SECONDS, use_default_baseline=True)
            self.logger.info("Direct training session started | plan=%s", plan.plan_id)
            self.statusBar().showMessage("Training direkt gestartet. Details bleiben optional.")

    def skip_baseline(self) -> None:
        if self.phase == "idle":
            self._start_new_session(phase="training", duration_s=TRAINING_SECONDS, use_default_baseline=True)
        elif self.phase == "baseline":
            self.processor.use_default_baseline()
            self.phase = "training"
        elif self.phase == "training":
            self.statusBar().showMessage("Training läuft bereits.")
            return
        elif self.phase == "reference":
            self.statusBar().showMessage("Während der Referenzmessung wird die Baseline nicht übersprungen.")
            return
        self.statusBar().showMessage("Baseline übersprungen. Training läuft mit neutralen Startwerten.")
        self.logger.info("Baseline skipped | previous_phase=%s", self.previous_phase)
        self._update_controls()
        self._update_header_state()

    def _start_new_session(self, phase: str, duration_s: Optional[float], use_default_baseline: bool) -> None:
        self._capture_pre_session_ratings()
        self.processor.reset()
        self.feedback.reset()
        if use_default_baseline:
            self.processor.use_default_baseline()
        self.session_rows.clear()
        self._plot_elapsed.clear()
        self._plot_hrv_amp.clear()
        self._plot_y_max = 3.0
        if hasattr(self, "hrv_graph_value"):
            self.hrv_graph_value.setText("—")
            self.hrv_graph_helper.setText("Sammelt RR-Intervalle")
        if self.plot is not None and self.hrv_curve is not None:
            self.hrv_curve.setData([], [])
        self.phase = phase
        self.previous_phase = phase
        self.session_duration_s = duration_s
        self.session_start_monotonic = time.monotonic()
        self.paused_total_s = 0.0
        self.pause_started_monotonic = None
        self._last_reward_active = False
        self.circle.set_state(HrvMetrics(phase=phase))
        self._sync_phase_view()
        self._update_controls()
        self._update_header_state()

    def toggle_pause(self) -> None:
        if self.phase == "idle":
            return
        if self.phase == "paused":
            if self.pause_started_monotonic is not None:
                self.paused_total_s += max(0.0, time.monotonic() - self.pause_started_monotonic)
            self.pause_started_monotonic = None
            self.phase = self.previous_phase if self.previous_phase != "paused" else "training"
            self.statusBar().showMessage("Fortgesetzt.")
        else:
            self.previous_phase = self.phase
            self.phase = "paused"
            self.pause_started_monotonic = time.monotonic()
            self.statusBar().showMessage("Pausiert.")
        self._update_controls()
        self._update_header_state()

    def stop_session(self, checked: bool = False, force_save: bool = False) -> None:  # noqa: ARG002
        if not self.session_rows:
            self.phase = "idle"
            self.session_start_monotonic = None
            self.session_duration_s = None
            self.pause_started_monotonic = None
            self._plot_elapsed.clear()
            self._plot_hrv_amp.clear()
            self._plot_y_max = 3.0
            if hasattr(self, "hrv_graph_value"):
                self.hrv_graph_value.setText("—")
                self.hrv_graph_helper.setText("Keine Sitzungsdaten gespeichert")
            if self.plot is not None and self.hrv_curve is not None:
                self.hrv_curve.setData([], [])
            if hasattr(self, "circle"):
                self.circle.set_state(HrvMetrics(phase="idle"))
            self._sync_phase_view()
            self._update_controls()
            self._update_header_state()
            self.statusBar().showMessage("Keine Sitzungsdaten zum Speichern.")
            return

        filename = f"{now_stamp()}_{self._session_label_for_filename()}.csv"
        path = SESSIONS_DIR / filename
        count = len(self.session_rows)
        summary = summarize_session(self.session_rows)
        sem_segments = rows_to_sem_segments(self.session_rows, segment_s=60.0)
        sem_path_summary = estimate_sem_paths_from_segments(sem_segments)
        sem_segments_path = path.with_suffix(".sem_segments.csv")
        adaptive_review = evaluate_double_loop(
            summary=summary,
            pre_ratings=self.session_context.get("pre_session_ratings", {}),
            post_ratings=None,
            focus_key=self.session_context.get("learning_focus_key", self._current_focus_key()),
        ).to_dict()
        self.session_context["double_loop_learning"] = adaptive_review
        self.last_double_loop_review = adaptive_review
        self.session_context["visible_product_contract"] = visible_training_contract()
        self.session_context["adaptive_ui_version"] = ADAPTIVE_UI_VERSION
        self.session_context["complementary_channel_contract"] = complementary_channel_contract()
        self.session_context["guided_session_version"] = GUIDED_SESSION_VERSION
        self.session_context["guided_session_contract"] = guided_session_contract()
        self.session_context["guided_session_plan"] = self._last_guided_session_plan
        pre_ratings = self.session_context.get("pre_session_ratings", {})
        evidence_sensor_ready = (self.input_mode == "ble" and self.ble_rr_value_count > 0) or self.input_mode == "mock"
        evidence_rec = compute_evidence_session_recommendation(
            guided_plan=self._last_guided_session_plan,
            ratings=pre_ratings,
            sensor_ready=bool(evidence_sensor_ready),
            signal_quality=float(getattr(self._last_metrics, "signal_quality", 0.0) or (0.75 if evidence_sensor_ready else 0.0)),
            session_minutes=TRAINING_SECONDS / 60.0,
        )
        self._last_evidence_session_recommendation = evidence_rec.to_dict()
        self.session_context["evidence_model_version"] = EVIDENCE_MODEL_VERSION
        self.session_context["evidence_metadata"] = evidence_metadata()
        self.session_context["evidence_session_recommendation"] = self._last_evidence_session_recommendation
        self.session_context["ui_capability_version"] = UI_CAPABILITY_VERSION
        self.session_context["ui_capability_metadata"] = capability_metadata()
        self.session_context["visual_feedback_version"] = VISUAL_FEEDBACK_VERSION
        self.session_context["graph_display_metadata"] = graph_display_metadata(
            calm_visuals_enabled=self.calm_visuals_enabled,
            pyqtgraph_available=pg is not None,
        )
        self.session_context["interaction_design_version"] = INTERACTION_DESIGN_VERSION
        self.session_context["interaction_design_contract"] = interaction_design_contract()
        self.session_context["reduced_motion_enabled"] = bool(self.reduced_motion_enabled)
        self.session_context["last_interaction_profile"] = self._last_interaction_profile
        self.session_context["ble_state_snapshot"] = self.ble_state.snapshot.to_dict() if hasattr(self, "ble_state") else {}
        metadata = build_session_metadata(
            session_label=self._session_label_for_filename(),
            csv_filename=path.name,
            row_count=count,
            phases=sorted({row.phase for row in self.session_rows}),
            baseline_duration_s=BASELINE_SECONDS,
            reference_duration_s=REFERENCE_SECONDS,
            training_duration_s=TRAINING_SECONDS,
            feedback_mode=self.feedback_mode,
            audio_enabled=self.audio_enabled,
            sem_live_enabled=self.sem_live_enabled,
            input_mode=self.input_mode,
            device_identifier=self.device_identifier,
            protocol_type=self.protocol_type,
            context=self.session_context,
            summary=summary,
            sem_segments_filename=sem_segments_path.name,
            sem_path_summary=sem_path_summary,
        )
        try:
            write_session_csv(path, self.session_rows)
            write_sem_segments_csv(sem_segments_path, sem_segments)
            write_session_metadata(path.with_suffix(".metadata.json"), metadata)
            self.logger.info("Session saved | path=%s rows=%s summary=%s sem=%s", path, count, summary, sem_path_summary)
        except Exception as exc:
            log_exception(self.logger, "Session export failed", exc)
            QMessageBox.critical(
                self,
                "Speichern nicht abgeschlossen",
                "Die Sitzung konnte nicht vollständig gespeichert werden. Details stehen in der Logdatei. "
                "Die Daten bleiben bis zum Schließen der App im Speicher."
            )
            return
        self.last_session_csv_path = path
        self.last_session_summary = summary
        self.last_reflection_path = None
        self.phase = "idle"
        self.session_start_monotonic = None
        self.session_duration_s = None
        self._update_controls()
        self._update_header_state()
        self.statusBar().showMessage(f"Sitzung gespeichert: {path}")
        self._set_aftercare_summary(path, summary)
        self._sync_phase_view(force_aftercare=True)
        if force_save:
            QMessageBox.information(self, "Export", f"{count} Datenzeilen gespeichert:\n{path}")
        else:
            self.show_session_summary(path, summary)

    def show_session_summary(self, csv_path: Path, summary: dict[str, Any]) -> None:
        def fmt(value: Any, suffix: str = "") -> str:
            if value is None:
                return "—"
            if isinstance(value, float):
                return f"{value:.2f}{suffix}"
            return f"{value}{suffix}"

        text = (
            f"Gespeichert:\n{csv_path}\n\n"
            f"Dauer: {fmt(summary.get('duration_s'), ' s')}\n"
            f"Gültige RR-Werte: {summary.get('valid_rr_count', 0)} / {summary.get('row_count', 0)}\n"
            f"Artefaktanteil: {fmt((summary.get('artifact_ratio') or 0) * 100, ' %')}\n"
            f"Ø HRV-Amplitude: {fmt(summary.get('mean_hrv_amplitude_60s'), ' BPM')}\n"
            f"Ø Herzrate: {fmt(summary.get('mean_bpm'), ' BPM')}\n"
            f"Stabile Phasen: {summary.get('reward_count', 0)}"
        )
        QMessageBox.information(self, "Sitzungszusammenfassung", text)

    def _session_label_for_filename(self) -> str:
        phases = {row.phase for row in self.session_rows}
        if "reference" in phases:
            return "reference"
        if "training" in phases or "baseline" in phases:
            return "training"
        return "session"

    def _handle_rr(
        self,
        rr_ms: float,
        *,
        sensor_contact_supported: bool = False,
        sensor_contact_detected: bool | None = None,
    ) -> None:
        if self.phase in {"idle", "paused"}:
            return
        elapsed = self._elapsed_s()
        metrics = self.processor.add_rr(
            elapsed,
            rr_ms,
            self.phase,
            sensor_contact_supported=sensor_contact_supported,
            sensor_contact_detected=sensor_contact_detected,
        )
        metrics.feedback_mode = self.feedback_mode
        metrics.audio_enabled = self.audio_enabled
        metrics.protocol_type = self.protocol_type
        metrics.input_mode = self.input_mode

        metrics = self.feedback.update(metrics, self.phase)
        metrics.phase = self.phase
        self._last_metrics = metrics
        self.session_rows.append(metrics)
        self._update_metrics_labels(metrics)
        self.circle.set_state(metrics)
        self._update_plot(metrics)
        self._update_header_state(metrics)

        if self.audio_enabled and metrics.reward_active and not self._last_reward_active:
            QApplication.beep()
        self._last_reward_active = metrics.reward_active

    def _training_rr_ready(self, metrics: HrvMetrics | None = None) -> bool:
        metrics = metrics or self._last_metrics
        if self.input_mode == "mock":
            return bool(metrics.rr_ms or self.session_rows)
        if hasattr(self, "ble_state") and self.ble_state.snapshot.rr_ready:
            return True
        return bool(self.ble_rr_value_count > 0 or (metrics.rr_ms is not None and metrics.rr_valid))

    def _adaptive_display_policy(self, metrics: HrvMetrics | None = None):
        metrics = metrics or self._last_metrics
        return compute_training_display_policy(
            phase=self.phase,
            signal_quality=float(metrics.signal_quality or 0.0),
            hrv_amplitude=metrics.hrv_amplitude_60s,
            reward_active=bool(metrics.reward_active),
            elapsed_s=self._elapsed_s(),
            focus_key=self.session_context.get("learning_focus_key", self._current_focus_key()),
            user_details_visible=bool(self.training_details_visible),
            user_graph_visible=bool(self.plot_visible),
            rr_ready=self._training_rr_ready(metrics),
        )

    def _apply_adaptive_training_policy(self, metrics: HrvMetrics | None = None) -> None:
        if not hasattr(self, "training_guidance_label"):
            return
        policy = self._adaptive_display_policy(metrics)
        interaction_profile = compute_interaction_profile(
            phase=self.phase,
            signal_quality=float((metrics or self._last_metrics).signal_quality or 0.0),
            rr_ready=self._training_rr_ready(metrics),
            hrv_amplitude=(metrics or self._last_metrics).hrv_amplitude_60s,
            elapsed_s=self._elapsed_s(),
            focus_key=self.session_context.get("learning_focus_key", self._current_focus_key()),
            details_visible=bool(self.training_details_visible),
            focus_mode=bool(self.focus_mode),
            calm_visuals_enabled=bool(self.calm_visuals_enabled),
            reduced_motion=bool(self.reduced_motion_enabled),
        )
        self._last_interaction_profile = interaction_profile.to_dict()
        self._last_adaptive_display_policy = policy.to_dict()
        self.training_guidance_label.setText(policy.guidance)
        if hasattr(self, "training_focus_label"):
            if policy.display_mode == "repair":
                self.training_focus_label.setText("Nächster Schritt: " + interaction_profile.next_micro_action)
            else:
                self.training_focus_label.setText("Aufmerksamkeitsanker: " + interaction_profile.next_micro_action)
        # Complementarity rule: the circle is always primary. The graph adds
        # temporal context. Numeric details are optional, except when signal
        # repair would otherwise be opaque.
        if hasattr(self, "plot_card"):
            self.plot_card.setVisible(bool(policy.show_graph and not self.focus_mode))
        if hasattr(self, "right_panel"):
            details_visible = bool(policy.show_details and (not self.focus_mode or policy.display_mode == "repair"))
            self.right_panel.setVisible(details_visible)
        if hasattr(self, "details_button"):
            was_blocked = self.details_button.blockSignals(True)
            self.details_button.setChecked(bool(self.training_details_visible))
            self.details_button.blockSignals(was_blocked)
            label = "Details ausblenden" if self.training_details_visible else "Details"
            if policy.display_mode == "repair" and not self.training_details_visible:
                label = "Details · Signal"
            self.details_button.setText(label)
        self.session_context["adaptive_ui_version"] = ADAPTIVE_UI_VERSION
        self.session_context["interaction_design_version"] = INTERACTION_DESIGN_VERSION
        self.session_context["complementary_channel_contract"] = complementary_channel_contract()
        self.session_context["interaction_design_contract"] = interaction_design_contract()
        self.session_context["last_adaptive_display_policy"] = policy.to_dict()
        self.session_context["last_interaction_profile"] = interaction_profile.to_dict()

    def _update_training_guidance(self, metrics: HrvMetrics | None = None) -> None:
        self._apply_adaptive_training_policy(metrics)

    def _update_metrics_labels(self, metrics: HrvMetrics) -> None:
        self._update_training_guidance(metrics)
        self.metric_cards["bpm"].set_value(f"{metrics.bpm:.1f}" if metrics.bpm else "—", "BPM")
        self.metric_cards["amp"].set_value(
            f"{metrics.hrv_amplitude_60s:.1f}" if metrics.hrv_amplitude_60s is not None else "—",
            "BPM, 60-s-Fenster",
        )
        quality_helper = "Signal verwendbar" if metrics.signal_quality >= 0.65 else "Kontakt/Ruhe prüfen"
        self.metric_cards["quality"].set_value(f"{metrics.signal_quality:.2f}", quality_helper)
        self.metric_cards["stable_phases"].set_value(str(metrics.reward_count), "stabile Zielphasen")

    def _update_plot(self, metrics: HrvMetrics) -> None:
        """Update the single HRV graph used during training.

        The graph intentionally shows only HRV amplitude.  Heart rate and
        composite feedback scores stay in the metric cards, because plotting
        them together can create visual competition and make the biofeedback
        signal harder to read.
        """
        if self.plot is None or self.hrv_curve is None:
            return
        amp = metrics.hrv_amplitude_60s
        if amp is None:
            if hasattr(self, "hrv_graph_value"):
                self.hrv_graph_value.setText("—")
                self.hrv_graph_helper.setText("Aufbauphase · etwa 60 s RR-Daten")
            return

        self._plot_elapsed.append(metrics.elapsed_s / 60.0)
        self._plot_hrv_amp.append(float(amp))
        self._plot_elapsed = self._plot_elapsed[-300:]
        self._plot_hrv_amp = self._plot_hrv_amp[-300:]
        display_amp = smooth_display_series(self._plot_hrv_amp, enabled=self.calm_visuals_enabled)
        self.hrv_curve.setData(self._plot_elapsed, display_amp)

        # Keep the visible range stable enough for feedback, but responsive to
        # individual amplitude differences. This is display-only, not a norm.
        display_range = calm_graph_y_range(display_amp, previous_y_max=self._plot_y_max)
        self._plot_y_max = display_range.y_max
        self.plot.setYRange(display_range.y_min, display_range.y_max, padding=0.04)
        if self._plot_elapsed:
            x_max = max(self._plot_elapsed[-1], 0.2)
            self.plot.setXRange(max(0.0, x_max - 5.0), x_max, padding=0.02)

        trend = "stabil"
        if len(self._plot_hrv_amp) >= 8:
            recent = self._plot_hrv_amp[-8:]
            delta = recent[-1] - recent[0]
            if delta > 0.4:
                trend = "steigend"
            elif delta < -0.4:
                trend = "sinkend"
        if hasattr(self, "hrv_graph_value"):
            self.hrv_graph_value.setText(f"{amp:.1f} BPM")
            helper = "HRV-Amplitude"
            if metrics.signal_quality < 0.65 and metrics.phase not in {"reference", "baseline"}:
                helper = "Signal prüfen · Graph pausiert nicht, aber Feedback bremst"
            else:
                if self.calm_visuals_enabled:
                    helper = f"Trend {trend} · ruhige Spur · 60-s-Fenster"
                else:
                    helper = f"Trend {trend} · 60-s-Fenster"
            self.hrv_graph_helper.setText(helper)

    def _ui_tick(self) -> None:
        if self.phase == "idle" or self.session_start_monotonic is None:
            return
        elapsed = self._elapsed_s()
        self._update_progress(elapsed)
        self._update_header_state()

        self._watch_ble_stream_health()

        if self.phase == "baseline" and elapsed >= BASELINE_SECONDS:
            self.processor.finalize_baseline()
            self.phase = "training"
            self.statusBar().showMessage("Baseline abgeschlossen. Training läuft.")
            self._update_controls()
            self._update_header_state()

        if self.session_duration_s is not None and elapsed >= self.session_duration_s:
            self.stop_session()


    def _watch_ble_stream_health(self) -> None:
        """Detect stalled BLE streams from the GUI side as a second safety net."""
        if self.input_mode != "ble" or self.phase not in {"reference", "baseline", "training"}:
            return
        if not (self.ble_worker and self.ble_worker.isRunning()):
            return
        now = time.monotonic()
        if self.last_ble_packet_monotonic is not None and now - self.last_ble_packet_monotonic > BLE_STREAM_STALE_FATAL_S + 8:
            self.last_ble_error = "BLE-Datenstrom ist stehen geblieben. Die App startet eine sichere Neuverbindung."
            self.logger.warning("GUI BLE watchdog detected stale packet stream")
            if self._maybe_auto_recover_ble("stale_data_stream", describe_ble_error(self.last_ble_error)):
                self.statusBar().showMessage("BLE-Datenstrom steht. Ich starte eine sichere Neuverbindung ...")
        elif self.last_ble_rr_monotonic is not None and now - self.last_ble_rr_monotonic > BLE_RR_STALE_FATAL_S + 8:
            self.last_ble_error = "RR-Datenstrom ist abgebrochen. Die App startet eine sichere Neuverbindung."
            self.logger.warning("GUI BLE watchdog detected stale RR stream")
            if self._maybe_auto_recover_ble("stale_data_stream", describe_ble_error(self.last_ble_error)):
                self.statusBar().showMessage("RR-Datenstrom steht. Ich starte eine sichere Neuverbindung ...")

    def _elapsed_s(self) -> float:
        if self.session_start_monotonic is None:
            return 0.0
        paused_current = 0.0
        if self.phase == "paused" and self.pause_started_monotonic is not None:
            paused_current = max(0.0, time.monotonic() - self.pause_started_monotonic)
        return max(0.0, time.monotonic() - self.session_start_monotonic - self.paused_total_s - paused_current)

    def _update_progress(self, elapsed: float | None = None) -> None:
        if elapsed is None:
            elapsed = self._elapsed_s()
        if self.session_duration_s:
            fraction = min(1.0, max(0.0, elapsed / self.session_duration_s))
            self.session_progress.setValue(int(fraction * 1000))
            remaining = max(0, int(self.session_duration_s - elapsed))
            self.progress_caption.setText(f"{self._format_time(elapsed)} / {self._format_time(self.session_duration_s)} · Rest {self._format_time(remaining)}")
        elif self.phase != "idle":
            self.session_progress.setValue(0)
            self.progress_caption.setText(f"laufend · {self._format_time(elapsed)}")
        else:
            self.session_progress.setValue(0)
            self.progress_caption.setText("Keine Sitzung aktiv")
        self.timer_label.setText(self._format_time(elapsed))

    @staticmethod
    def _format_time(seconds: float) -> str:
        total = max(0, int(seconds))
        return f"{total // 60:02d}:{total % 60:02d}"

    def _update_header_state(self, metrics: HrvMetrics | None = None) -> None:
        metrics = metrics or self._last_metrics
        phase_label = PHASE_LABELS.get(self.phase, self.phase)
        tone = "neutral"
        if self.phase in {"baseline", "reference"}:
            tone = "active"
        elif self.phase == "training":
            tone = "good" if metrics.reward_active else "active"
        elif self.phase == "paused":
            tone = "warn"
        self.phase_pill.set_tone(tone, phase_label)

        if self.input_mode == "mock":
            input_tone, input_label = "good", "Mock aktiv"
        elif self.input_mode in {"ble", "ble_scan"} or getattr(self, "ble_state", None):
            input_tone, input_label = self.ble_state.user_label() if hasattr(self, "ble_state") else ("active", "BLE")
            if self.input_mode == "unknown" and input_label.startswith("Input"):
                input_tone, input_label = "neutral", "Input: —"
        else:
            input_tone, input_label = "neutral", f"Input: {self.input_mode}"
        self.input_pill.set_tone(input_tone, input_label)

        if self.phase == "idle" and not self.session_rows:
            if self.input_mode == "ble" and self.ble_rr_value_count > 0:
                self.quality_pill.set_tone("good", "Signal: RR aktiv")
            elif self.input_mode == "ble" and self.ble_packet_count > 0:
                self.quality_pill.set_tone("warn", "Signal: RR fehlt")
            elif self.input_mode == "ble":
                self.quality_pill.set_tone("active", "Signal: warte")
            else:
                self.quality_pill.set_tone("neutral", "Signal: —")
        else:
            quality = metrics.signal_quality
            if quality >= 0.80:
                self.quality_pill.set_tone("good", f"Signal {quality:.2f}")
            elif quality >= 0.55:
                self.quality_pill.set_tone("active", f"Signal {quality:.2f}")
            else:
                self.quality_pill.set_tone("warn", f"Signal {quality:.2f}")
        self._update_training_guidance(metrics)
        self._update_preparation_readiness()
        self._update_progress()
        self._update_workflow_state(metrics)
        self._sync_phase_view()

    def _update_workflow_state(self, metrics: HrvMetrics | None = None) -> None:
        if not hasattr(self, "workflow_sensor"):
            return
        metrics = metrics or self._last_metrics

        # Sensor step
        if self.input_mode == "ble":
            if self.ble_rr_value_count > 0:
                self.workflow_sensor.set_state("good", "Sensor verbunden. RR-Daten kommen an.")
            elif self.ble_packet_count > 0:
                self.workflow_sensor.set_state("warn", "Sensor verbunden, aber RR-Intervalle fehlen noch.")
            else:
                self.workflow_sensor.set_state("active", "Sensor verbunden. Warte auf Live-Daten.")
        elif self.input_mode == "ble_scan":
            self.workflow_sensor.set_state("active", "Scan läuft. Ich suche relevante HRV-Geräte.")
        elif self.input_mode == "mock":
            self.workflow_sensor.set_state("good", "Mock-Test aktiv. Oberfläche kann ohne Sensor geprüft werden.")
        elif self.devices:
            self.workflow_sensor.set_state("active", "Gerät gefunden. Jetzt Auto verbinden oder Verbinden wählen.")
        else:
            self.workflow_sensor.set_state("neutral", "Auto verbinden starten.")

        # Signal step
        if self.phase in {"idle"} and not self.session_rows:
            if self.input_mode == "ble" and self.ble_rr_value_count > 0:
                self.workflow_signal.set_state("good", f"RR aktiv: {self.ble_rr_value_count} Werte empfangen.")
            elif self.input_mode == "ble" and self.ble_packet_count > 0:
                self.workflow_signal.set_state("warn", "BPM sichtbar, RR-Intervalle fehlen.")
            elif self.input_mode == "ble":
                self.workflow_signal.set_state("active", "Warte auf Heart-Rate-/RR-Daten.")
            else:
                self.workflow_signal.set_state("neutral", "Kontakt und RR-Daten prüfen.")
        elif metrics.signal_quality >= 0.80:
            self.workflow_signal.set_state("good", "Signal wirkt stabil.")
        elif metrics.signal_quality >= 0.55:
            self.workflow_signal.set_state("active", "Signal verwendbar; Kontakt weiter beobachten.")
        else:
            self.workflow_signal.set_state("warn", "Kontakt, Ruhe oder Sensorposition prüfen.")

        # Training step
        if self.phase == "training":
            self.workflow_training.set_state("good" if metrics.reward_active else "active", "Feedback läuft über HRV-Amplitude.")
        elif self.phase == "baseline":
            self.workflow_training.set_state("active", "Baseline läuft; kann übersprungen werden.")
        elif self.phase == "reference":
            self.workflow_training.set_state("active", "Referenzmessung läuft ohne Bewertung.")
        elif self.phase == "paused":
            self.workflow_training.set_state("warn", "Sitzung pausiert.")
        else:
            self.workflow_training.set_state("neutral", "Training starten, sobald Sensor oder Mock bereit ist.")

        if hasattr(self, "next_step_label"):
            self.next_step_label.setText(self._next_step_text(metrics))

    def _next_step_text(self, metrics: HrvMetrics | None = None) -> str:
        metrics = metrics or self._last_metrics
        if self.phase == "training":
            if metrics.signal_quality < 0.55:
                return "Nächster Schritt: Signalqualität beobachten; Kontakt oder Ruheposition prüfen."
            return "Nächster Schritt: ruhig weitertrainieren; der Kreis verstärkt stabile HRV-Amplitude."
        if self.phase == "baseline":
            return "Nächster Schritt: Baseline laufen lassen oder bei Bedarf überspringen."
        if self.phase == "reference":
            return "Nächster Schritt: Referenzmessung ohne Bewertung abschließen lassen."
        if self.phase == "paused":
            return "Nächster Schritt: Fortsetzen oder Sitzung speichern."
        if self.input_mode == "ble_scan":
            return "Nächster Schritt: Scan abwarten; die App sortiert relevante Sensoren automatisch."
        if self.input_mode == "ble":
            if self.ble_rr_value_count > 0:
                return "Nächster Schritt: RR-Daten kommen an. Training starten oder Baseline überspringen."
            if self.ble_packet_count > 0:
                return "Nächster Schritt: Sensor sendet Herzrate, aber noch keine RR-Intervalle. Kontakt prüfen und andere Apps/Smartphones trennen."
            return "Nächster Schritt: Sensor ist verbunden. Kurz auf RR-Daten warten; bei Stillstand Status & Diagnose öffnen."
        if self.input_mode == "mock":
            return "Nächster Schritt: Oberfläche testen oder Training im Mock-Modus starten."
        if self.devices:
            return "Nächster Schritt: wahrscheinlichstes Gerät verbinden."
        return "Nächster Schritt: Auto verbinden wählen. Alternativ Mock-Test starten."

    def _update_controls(self) -> None:
        running = self.phase != "idle"
        self.reference_button.setEnabled(not running)
        self.training_button.setEnabled(not running)
        self.skip_baseline_button.setEnabled((not running) or self.phase == "baseline")
        self.pause_button.setEnabled(running)
        self.stop_button.setEnabled(running or bool(self.session_rows))
        if hasattr(self, "reference_action"):
            self.reference_action.setEnabled(not running)
            self.training_action.setEnabled(not running)
            self.start_training_quick_action.setEnabled(not running)
            self.skip_baseline_action.setEnabled((not running) or self.phase == "baseline")
            self.start_skip_baseline_action.setEnabled((not running) or self.phase == "baseline")
            self.pause_action.setEnabled(running)
            self.stop_action.setEnabled(running or bool(self.session_rows))

        ble_busy = bool(self.ble_worker and self.ble_worker.isRunning())
        self.scan_button.setEnabled(not ble_busy)
        self.auto_connect_button.setEnabled(not ble_busy)
        self.connection_help_button.setEnabled(not ble_busy)
        self.connect_button.setEnabled(not ble_busy)
        self.disconnect_button.setEnabled(ble_busy)
        if hasattr(self, "scan_action"):
            self.scan_action.setEnabled(not ble_busy)
            self.auto_connect_action.setEnabled(not ble_busy)
            self.start_auto_connect_action.setEnabled(not ble_busy)
            self.connect_action.setEnabled(not ble_busy)
            self.disconnect_action.setEnabled(ble_busy)
            self.ble_diagnostics_action.setEnabled(not ble_busy or bool(self.last_ble_error))
        self.pause_button.setText("Fortsetzen" if self.phase == "paused" else "Pause")
        if hasattr(self, "pause_action"):
            self.pause_action.setText("Fortsetzen" if self.phase == "paused" else "Pause/Fortsetzen")

    def closeEvent(self, event: Any) -> None:  # noqa: D401 - Qt override
        self.logger.info("Application closing | phase=%s rows_in_memory=%s", self.phase, len(self.session_rows))
        if self.phase != "idle" and self.session_rows:
            reply = QMessageBox.question(
                self,
                "Sitzung noch aktiv",
                "Es liegen Sitzungsdaten im Speicher. Vor dem Schließen speichern?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                QMessageBox.Yes,
            )
            if reply == QMessageBox.Cancel:
                event.ignore()
                return
            if reply == QMessageBox.Yes:
                self.stop_session(force_save=True)
                if self.phase != "idle":
                    event.ignore()
                    return
        if self.ble_worker and self.ble_worker.isRunning():
            self.ble_worker.stop()
            self.ble_worker.wait(2500)
        self._save_window_layout()
        event.accept()


def main() -> int:
    logger = setup_logging()
    install_global_exception_hooks(logger)
    ensure_data_dirs()
    cleanup_runtime_files()
    logger.info("Application starting | snapshot=%s", app_system_snapshot())
    configure_qt_for_windows()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    try:
        window = MainWindow()
        window.show()
        exit_code = app.exec()
        logger.info("Application exited | code=%s", exit_code)
        return exit_code
    except Exception as exc:
        log_exception(logger, "Fatal application startup/runtime error", exc)
        raise


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
