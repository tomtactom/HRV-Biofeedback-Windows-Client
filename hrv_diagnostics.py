"""BLE onboarding and diagnostics helpers for HRV Biofeedback.

This module is UI-free.  It turns BLE/app state into an auditable diagnostic
report and into action-oriented German guidance for the Qt layer.  It also
contains the small self-healing policy used by the connection flow: safe actions
such as rescan/reconnect may be automated; Windows settings are only opened for
manual review and are not changed by the app.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any
import importlib.util
import platform

from hrv_ble_strategy import (
    HR_SERVICE_UUID,
    HR_MEASUREMENT_UUID,
    ALL_DEVICE_TERMS,
    normalize_uuid,
    rank_ble_devices,
    select_best_device as _select_best_ble_device,
)
from hrv_windows import collect_windows_bluetooth_snapshot, summarize_windows_bluetooth_snapshot

HR_SERVICE_UUID_SUFFIX = HR_SERVICE_UUID
HR_MEASUREMENT_UUID_SUFFIX = HR_MEASUREMENT_UUID


@dataclass
class DiagnosticCheck:
    """Single diagnostic finding with a stable machine-readable status."""

    key: str
    label: str
    status: str  # ok | warn | error | info
    detail: str
    suggestion: str = ""


@dataclass(frozen=True)
class BleErrorGuidance:
    """Human and machine readable explanation for a BLE connection issue."""

    category: str
    title: str
    likely_cause: str
    automated_action: str
    user_action: str
    can_auto_recover: bool = True
    severity: str = "warn"


LIKELY_DEVICE_TERMS = ALL_DEVICE_TERMS

_ERROR_GUIDANCE: dict[str, BleErrorGuidance] = {
    "missing_dependency": BleErrorGuidance(
        category="missing_dependency",
        title="BLE-Bibliothek fehlt",
        likely_cause="Das Python-Paket 'bleak' ist nicht installiert oder wird in dieser Umgebung nicht gefunden.",
        automated_action="Kein automatischer Verbindungsversuch möglich.",
        user_action="Im aktivierten Conda-Environment ausführen: pip install -r requirements.txt",
        can_auto_recover=False,
        severity="error",
    ),
    "scan_failed": BleErrorGuidance(
        category="scan_failed",
        title="BLE-Scan nicht abgeschlossen",
        likely_cause="Windows hat den Bluetooth-Scan abgebrochen, der Adapter ist kurz blockiert oder der BLE-Stack antwortet nicht.",
        automated_action="Die App speichert Diagnoseinformationen und kann nach kurzer Pause erneut scannen.",
        user_action="Bluetooth in Windows kurz aus/ein schalten; danach Auto verbinden erneut ausführen.",
    ),
    "no_devices_found": BleErrorGuidance(
        category="no_devices_found",
        title="Kein BLE-Gerät gefunden",
        likely_cause="Der Sensor ist nicht wach, zu weit entfernt, die Batterie ist schwach oder Windows liefert im Moment keine BLE-Werbung.",
        automated_action="Die App kann erneut scannen und das wahrscheinlichste Gerät automatisch auswählen.",
        user_action="Sensor anlegen/aktivieren, näher an den Laptop bringen und andere Apps/Smartphones trennen.",
    ),
    "device_not_reachable": BleErrorGuidance(
        category="device_not_reachable",
        title="Gerät nicht erreichbar",
        likely_cause="Das Gerät war im Scan sichtbar, antwortet beim Verbinden aber nicht mehr oder wird bereits von einem anderen Gerät gehalten.",
        automated_action="Die App führt einen frischen Scan aus und versucht die Verbindung mit dem neu gefundenen Geräteobjekt erneut.",
        user_action="Andere Apps/Smartphones trennen, Sensor kurz vom Körper lösen und erneut anlegen, dann Auto verbinden.",
    ),
    "connection_timeout": BleErrorGuidance(
        category="connection_timeout",
        title="Verbindung dauert zu lange",
        likely_cause="Die Funkverbindung ist schwach, der Sensor antwortet verzögert oder Windows wartet auf eine blockierte BLE-Operation.",
        automated_action="Die App wartet kurz, scannt erneut und startet einen begrenzten Wiederholversuch.",
        user_action="Sensor näher an den Laptop bringen und Störquellen/andere Bluetooth-Verbindungen reduzieren.",
    ),
    "paired_or_busy": BleErrorGuidance(
        category="paired_or_busy",
        title="Sensor vermutlich durch anderes Gerät belegt",
        likely_cause="Der eSense Pulse oder ein anderer HR-Sensor kann meist nur eine aktive BLE-Verbindung gleichzeitig halten. Eine Smartphone-App, eSense-App oder Windows-Kopplung kann den Zugriff blockieren.",
        automated_action="Die App trennt die eigene Verbindung, wartet kurz, scannt neu und verbindet erneut mit einem frischen Geräteobjekt.",
        user_action="eSense-App/Smartphone trennen, Sensor in anderen Apps schließen und bei Bedarf Windows-Bluetooth einmal aus/ein schalten.",
    ),
    "connection_failed": BleErrorGuidance(
        category="connection_failed",
        title="BLE-Verbindung nicht hergestellt",
        likely_cause="Windows konnte den BLE-Kanal nicht öffnen oder der Sensor hat den Verbindungsaufbau abgelehnt.",
        automated_action="Die App speichert einen Diagnosebericht und versucht nach kurzer Pause neu zu scannen und zu verbinden.",
        user_action="Bluetooth kurz aus/ein schalten; bei Wiederholung Sensorbatterie und parallele Verbindungen prüfen.",
    ),
    "permission_or_stack": BleErrorGuidance(
        category="permission_or_stack",
        title="Windows-Bluetooth-Stack blockiert",
        likely_cause="Ein Zugriffs-/WinRT-/Bluetooth-Stack-Problem verhindert die BLE-Operation.",
        automated_action="Die App beendet die laufende BLE-Aufgabe, speichert Diagnoseinformationen und versucht einen neuen Scan.",
        user_action="Windows Bluetooth-Einstellungen öffnen, Bluetooth aus/ein schalten, danach Auto verbinden.",
    ),
    "gatt_service_read_failed": BleErrorGuidance(
        category="gatt_service_read_failed",
        title="GATT-Services nicht lesbar",
        likely_cause="Die Verbindung steht, aber Windows liefert die BLE-Service-Tabelle nicht. Häufige Auslöser: Sensor noch mit Smartphone/App verbunden, instabiler Windows-BLE-Cache oder zu frühe Service-Abfrage nach dem Connect.",
        automated_action="Die App wartet, liest Services mehrfach, verbindet mit deaktiviertem Windows-Servicecache und startet bei Bedarf einen frischen Scan/Wiederholversuch.",
        user_action="eSense-App/Smartphone trennen, Sensor wach halten, Bluetooth kurz aus/ein schalten und Auto verbinden erneut ausführen. Unter Windows kann auch ein vorheriges Scan-Signal vor dem Verbinden helfen; die App versucht das automatisch.",
    ),
    "no_standard_hr_service": BleErrorGuidance(
        category="no_standard_hr_service",
        title="Standard-Herzfrequenzdienst nicht gefunden",
        likely_cause="Das Gerät bietet den BLE-Standarddienst Heart Rate Measurement 0x2A37 nicht an oder Windows zeigt ihn nicht an.",
        automated_action="Die App speichert die gefundenen Services; ein automatisches Auslesen ohne 0x2A37 ist nicht belastbar möglich.",
        user_action="Service-Debugdatei prüfen. Falls der eSense Pulse hier kein Standard-HRS anbietet oder Windows ihn nicht freigibt: LSL/OSC-Streaming als Eingang verwenden.",
        can_auto_recover=False,
    ),
    "notify_subscribe_failed": BleErrorGuidance(
        category="notify_subscribe_failed",
        title="Live-Benachrichtigungen nicht abonnierbar",
        likely_cause="Der Heart-Rate-Dienst wurde gefunden, aber Windows oder der Sensor akzeptiert das Notification-Abonnement nicht.",
        automated_action="Die App verbindet nach kurzem Warten erneut und versucht das Abonnement noch einmal.",
        user_action="Andere Apps trennen; Sensor kurz neu anlegen; danach Auto verbinden.",
    ),
    "no_rr_intervals": BleErrorGuidance(
        category="no_rr_intervals",
        title="Keine RR-Intervalle empfangen",
        likely_cause="Der Sensor sendet zwar Herzfrequenzpakete, aber im Heart-Rate-Measurement fehlen RR-Intervalle. Für HRV-Biofeedback reichen BPM-Schätzwerte nicht aus. Häufige Auslöser: parallele App hält den Sensor, Sensorprofil wird von Windows unvollständig geliefert oder das Gerät streamt RR nur über eSense/LSL/OSC.",
        automated_action="Die App scannt und verbindet begrenzt neu. BPM-only-Daten werden nicht als HRV-Quelle verwendet, damit keine künstliche HRV berechnet wird.",
        user_action="Andere Apps/Smartphones trennen, Sensor kurz neu anlegen, danach Auto verbinden. Wenn weiterhin nur BPM erscheint: LSL/OSC-Streaming als Eingang prüfen.",
    ),
    "no_sensor_data": BleErrorGuidance(
        category="no_sensor_data",
        title="Verbunden, aber keine Live-Daten",
        likely_cause="Der Sensor sendet noch keine Heart-Rate-/RR-Werte. Häufig: Hautkontakt noch nicht stabil, Elektroden/Gurt nicht feucht genug, Sensor schläft oder parallele App blockiert Daten.",
        automated_action="Die App reconnectet begrenzt. Danach bleibt die Diagnose sichtbar, damit Kontakt und parallele Verbindungen geprüft werden können.",
        user_action="Gurt/Kontakt prüfen, Elektroden anfeuchten, Sensor mittig anlegen, andere Apps/Smartphones trennen.",
    ),
    "parse_error": BleErrorGuidance(
        category="parse_error",
        title="BLE-Datenpaket nicht interpretierbar",
        likely_cause="Ein empfangenes Paket entspricht nicht dem erwarteten Heart-Rate-Measurement-Format oder war unvollständig.",
        automated_action="Die App verwirft das einzelne Paket und wartet auf weitere Werte; Rohdaten werden gespeichert.",
        user_action="Bei häufiger Wiederholung Debugdatei prüfen und Sensor/Verbindung erneut starten.",
        can_auto_recover=False,
    ),
    "stale_data_stream": BleErrorGuidance(
        category="stale_data_stream",
        title="BLE-Datenstrom ist stehen geblieben",
        likely_cause="Die Verbindung besteht noch, aber es kommen keine neuen Werte mehr. Häufige Auslöser: Sensor ist eingeschlafen, Kontakt ist instabil, Windows BLE-Stack hat den Notification-Stream verloren oder eine andere App greift auf den Sensor zu.",
        automated_action="Die App stoppt den aktuellen Stream, scannt frisch und verbindet begrenzt automatisch neu.",
        user_action="Sensorkontakt prüfen, andere Apps/Smartphones trennen und den Sensor nah am Laptop lassen. Danach Auto verbinden erneut ausführen, falls der Wiederherstellungsversuch endet.",
    ),
    "adapter_or_service_issue": BleErrorGuidance(
        category="adapter_or_service_issue",
        title="Bluetooth-Dienst oder Adapter prüfen",
        likely_cause="Windows meldet einen auffälligen Bluetooth-Dienst- oder Adapterzustand.",
        automated_action="Die App speichert den lokalen Windows-Bluetooth-Snapshot und setzt die BLE-Verbindung zurück, ändert aber keine Windows-Einstellungen automatisch.",
        user_action="Windows Bluetooth-Einstellungen öffnen, Bluetooth aus/ein schalten und den Laptop-Bluetooth-Adapter prüfen.",
    ),
    "generic": BleErrorGuidance(
        category="generic",
        title="Bluetooth-Hinweis",
        likely_cause="Die genaue Ursache wurde nicht eindeutig erkannt.",
        automated_action="Die App speichert Diagnose- und Logdaten und kann einen begrenzten Wiederholversuch ausführen.",
        user_action="Diagnosebericht und Logdatei prüfen; danach Scan oder Auto verbinden wiederholen.",
    ),
}


def _normalize_uuid(value: Any) -> str:
    return normalize_uuid(value)


def sort_devices_for_connection(devices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return BLE scan results ordered for a low-friction connection flow."""
    return rank_ble_devices(list(devices or []))


def select_best_device(devices: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the most plausible device from a scan, if any."""
    return _select_best_ble_device(list(devices or []))


def _has_hr_measurement(service_dump: dict[str, Any] | None) -> bool:
    if not service_dump:
        return False
    for service in service_dump.get("services", []) or []:
        for char in service.get("characteristics", []) or []:
            if _normalize_uuid(char.get("uuid")) == HR_MEASUREMENT_UUID_SUFFIX:
                return True
    return False


def _service_uuid_summary(service_dump: dict[str, Any] | None) -> list[str]:
    if not service_dump:
        return []
    out: list[str] = []
    for service in service_dump.get("services", []) or []:
        service_uuid = _normalize_uuid(service.get("uuid"))
        if service_uuid:
            out.append(service_uuid)
    return out


def describe_ble_error(message: str) -> dict[str, Any]:
    """Return a stable category plus plain-language explanation for a BLE message."""
    text = (message or "").lower()
    category = "generic"
    if "bleak" in text or "nicht installiert" in text or "not installed" in text:
        category = "missing_dependency"
    elif "scan" in text and ("konnte nicht" in text or "failed" in text or "abgeschlossen" in text):
        category = "scan_failed"
    elif "0 devices" in text or "kein ble-gerät" in text or "keine geräte" in text:
        category = "no_devices_found"
    elif "kein standardisierter heart rate" in text or "0x2a37" in text or "heart rate measurement" in text and "nicht gefunden" in text:
        category = "no_standard_hr_service"
    elif "notification" in text or "benachrichtig" in text or "start_notify" in text or "abonn" in text:
        category = "notify_subscribe_failed"
    elif "datenstrom" in text or "stream" in text and ("stale" in text or "stehen" in text or "abgebrochen" in text):
        category = "stale_data_stream"
    elif "keine rr-intervalle" in text or "no rr intervals" in text or ("rr-intervalle" in text and ("nicht" in text or "keine" in text)) :
        category = "no_rr_intervals"
    elif "keine rr" in text or "keine live-daten" in text or "no rr" in text or "no heart-rate notifications" in text or "noch keine rr-werte" in text:
        category = "no_sensor_data"
    elif "gatt" in text or "services" in text or "dienste" in text or "service discovery" in text or "no gatt service" in text:
        category = "gatt_service_read_failed"
    elif "already in use" in text or "busy" in text or "belegt" in text or (("ander" in text or "andere" in text) and "app" in text) or "smartphone" in text:
        category = "paired_or_busy"
    elif "zugriff" in text or "access" in text or "permission" in text or "winrt" in text or "protocolerror" in text or "operation canceled" in text:
        category = "permission_or_stack"
    elif "timeout" in text or "timed out" in text:
        category = "connection_timeout"
    elif "not found" in text or "nicht gefunden" in text or "unreachable" in text or "not reachable" in text or "device can not be reached" in text:
        category = "device_not_reachable"
    elif "parse" in text or "paket" in text and "verarbeitet" in text:
        category = "parse_error"
    elif "konnte nicht hergestellt" in text or "failed" in text or "nicht verbunden" in text or "could not connect" in text:
        category = "connection_failed"

    guidance = _ERROR_GUIDANCE.get(category, _ERROR_GUIDANCE["generic"])
    return {
        "category": guidance.category,
        "title": guidance.title,
        "likely_cause": guidance.likely_cause,
        "automated_action": guidance.automated_action,
        "user_action": guidance.user_action,
        "can_auto_recover": guidance.can_auto_recover,
        "severity": guidance.severity,
        "raw_message": message or "",
    }


def classify_ble_error(message: str) -> tuple[str, str]:
    """Map common BLE errors to a short category and a concrete next step."""
    info = describe_ble_error(message)
    return str(info["category"]), str(info["user_action"])


def should_auto_recover_ble_error(message: str) -> bool:
    """Whether the app may safely rescan/reconnect without changing OS settings."""
    return bool(describe_ble_error(message).get("can_auto_recover", True))


def build_ble_diagnostic_report(
    *,
    devices: list[dict[str, Any]] | None = None,
    selected_device: str = "",
    selected_address: str = "",
    last_error: str = "",
    service_dump: dict[str, Any] | None = None,
    app_snapshot: dict[str, Any] | None = None,
    include_windows_snapshot: bool = True,
) -> dict[str, Any]:
    """Build a serializable BLE diagnostic report for logs, UI and support."""
    devices = devices or []
    ordered = sort_devices_for_connection(devices)
    best = select_best_device(ordered)
    checks: list[DiagnosticCheck] = []

    bleak_available = importlib.util.find_spec("bleak") is not None
    checks.append(
        DiagnosticCheck(
            key="bleak_dependency",
            label="Python BLE package",
            status="ok" if bleak_available else "error",
            detail="bleak importable" if bleak_available else "bleak not found",
            suggestion="pip install -r requirements.txt" if not bleak_available else "",
        )
    )

    checks.append(
        DiagnosticCheck(
            key="scan_result",
            label="BLE scan result",
            status="ok" if devices else "warn",
            detail=f"{len(devices)} device(s) found",
            suggestion=_ERROR_GUIDANCE["no_devices_found"].user_action if not devices else "",
        )
    )

    if selected_address:
        checks.append(
            DiagnosticCheck(
                key="selected_device",
                label="Selected device",
                status="ok",
                detail=f"{selected_device} [{selected_address}]",
            )
        )
    else:
        checks.append(
            DiagnosticCheck(
                key="selected_device",
                label="Selected device",
                status="warn",
                detail="No device selected",
                suggestion="Scan ausführen und das wahrscheinlichste eSense/Pulse/Heart-Rate-Gerät auswählen.",
            )
        )

    if best:
        best_name = best.get("name") or "Unbekanntes Gerät"
        best_addr = best.get("address") or ""
        best_services = " ".join(_normalize_uuid(x) for x in best.get("service_uuids", []) or [])
        status = "ok" if ("180d" in best_services or any(term in str(best_name).lower() for term in LIKELY_DEVICE_TERMS)) else "info"
        reasons = "; ".join(best.get("connection_reasons") or [])
        checks.append(
            DiagnosticCheck(
                key="best_candidate",
                label="Best candidate",
                status=status,
                detail=f"{best_name} [{best_addr}] RSSI={best.get('rssi')} · {best.get('connection_label', 'unklar')} · {reasons}",
                suggestion="Dieses Gerät zuerst testen." if status == "ok" else "Gerätename ist nicht eindeutig; Service-Debug nach Verbindung prüfen.",
            )
        )

    if service_dump:
        has_hr = _has_hr_measurement(service_dump)
        checks.append(
            DiagnosticCheck(
                key="heart_rate_measurement_service",
                label="Heart Rate Measurement 0x2A37",
                status="ok" if has_hr else "warn",
                detail="0x2A37 present" if has_hr else "0x2A37 not present in service dump",
                suggestion=_ERROR_GUIDANCE["no_standard_hr_service"].user_action if not has_hr else "",
            )
        )

    error_info = describe_ble_error(last_error) if last_error else {}
    if last_error:
        checks.append(
            DiagnosticCheck(
                key="last_error",
                label=f"Last BLE error: {error_info.get('category', 'generic')}",
                status=str(error_info.get("severity", "warn")),
                detail=last_error,
                suggestion=str(error_info.get("user_action", "")),
            )
        )

    suggestions = []
    if error_info:
        for text in (error_info.get("automated_action"), error_info.get("user_action")):
            if text and text not in suggestions:
                suggestions.append(str(text))
    for check in checks:
        if check.suggestion and check.suggestion not in suggestions:
            suggestions.append(check.suggestion)
    if not suggestions:
        suggestions.append("Scan wiederholen und bei Bedarf die gespeicherten Debugdateien prüfen.")

    report = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "app_snapshot": app_snapshot or {},
        "platform": platform.platform(),
        "devices_ordered": ordered,
        "selected_device": selected_device,
        "selected_address": selected_address,
        "last_error": last_error,
        "last_error_info": error_info,
        "service_uuids": _service_uuid_summary(service_dump),
        "checks": [asdict(check) for check in checks],
        "suggestions": suggestions,
    }
    if include_windows_snapshot:
        snapshot = collect_windows_bluetooth_snapshot()
        report["windows_bluetooth_snapshot"] = snapshot
        report["windows_bluetooth_summary"] = summarize_windows_bluetooth_snapshot(snapshot)
        summary = report["windows_bluetooth_summary"]
        if summary.get("status") == "warn":
            report["checks"].append(asdict(DiagnosticCheck(
                key="windows_bluetooth_summary",
                label="Windows Bluetooth status",
                status="warn",
                detail=", ".join(summary.get("issues", [])) or "Windows Bluetooth snapshot contains warnings",
                suggestion=_ERROR_GUIDANCE["adapter_or_service_issue"].user_action,
            )))
            if _ERROR_GUIDANCE["adapter_or_service_issue"].user_action not in report["suggestions"]:
                report["suggestions"].append(_ERROR_GUIDANCE["adapter_or_service_issue"].user_action)
        elif summary.get("notes"):
            report["checks"].append(asdict(DiagnosticCheck(
                key="windows_bluetooth_summary",
                label="Windows Bluetooth status",
                status="info",
                detail=", ".join(summary.get("notes", [])),
                suggestion="Bluetooth-Dienste stehen im normalen Windows-Trigger-Start-Zustand; kein manueller Eingriff nötig, solange Scan/GATT funktionieren.",
            )))
    return report


def diagnostic_report_to_text(report: dict[str, Any]) -> str:
    """Render a concise German report for the troubleshooting dialog."""
    lines = [
        "Automatische Bluetooth-Diagnose",
        f"Zeitpunkt: {report.get('created_at', '—')}",
        f"Plattform: {report.get('platform', '—')}",
    ]
    win_summary = report.get("windows_bluetooth_summary") or {}
    if win_summary:
        lines.append(f"Windows-Bluetooth-Status: {win_summary.get('status', '—')}")
    error_info = report.get("last_error_info") or {}
    if error_info:
        lines.extend(
            [
                "",
                f"Erkannter Bereich: {error_info.get('title', 'Bluetooth-Hinweis')}",
                f"Woran es wahrscheinlich liegt: {error_info.get('likely_cause', '—')}",
                f"Was die App automatisch versucht: {error_info.get('automated_action', '—')}",
                f"Was du tun kannst: {error_info.get('user_action', '—')}",
            ]
        )

    lines.extend(["", "Prüfpunkte:"])
    for check in report.get("checks", []) or []:
        status = str(check.get("status", "info")).upper()
        lines.append(f"- [{status}] {check.get('label', check.get('key', ''))}: {check.get('detail', '')}")
        suggestion = check.get("suggestion")
        if suggestion:
            lines.append(f"  → {suggestion}")

    lines.append("")
    lines.append("Nächste mögliche Schritte:")
    for idx, suggestion in enumerate(report.get("suggestions", []) or [], start=1):
        lines.append(f"{idx}. {suggestion}")

    lines.append("")
    lines.append("Hinweis: Die automatische Korrektur macht nur sichere Schritte wie Scan, Neuverbinden und Diagnoseexport. Windows-Einstellungen werden nicht ohne dein Zutun geändert.")
    return "\n".join(lines)
