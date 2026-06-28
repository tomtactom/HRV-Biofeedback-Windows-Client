"""Optional Python library and UX capability map for HRV Biofeedback.

The app should stay dependable on Windows with a small required dependency set.
This module therefore does not import optional packages eagerly.  It detects what
is available, classifies what each library could add, and keeps risky or
license-sensitive ideas out of the default training path.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from importlib import util
from typing import Any

UI_CAPABILITY_VERSION = "0.32-library-capability-map"


@dataclass(frozen=True)
class LibraryCapability:
    """One detected or potential Python library capability."""

    name: str
    import_name: str
    installed: bool
    role: str
    integration_level: str
    user_experience_value: str
    risk: str
    decision: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class UiOpportunity:
    """Concrete UX opportunity derived from the capability map."""

    title: str
    source: str
    implementation: str
    default_visibility: str
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _installed(import_name: str) -> bool:
    try:
        return util.find_spec(import_name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def detect_library_capabilities() -> list[LibraryCapability]:
    """Return the current capability map without importing heavy modules."""

    specs = [
        (
            "PySide6 / Qt for Python",
            "PySide6",
            "native_windows_gui",
            "core",
            "moderne native Windows-Oberfläche, DPI-Skalierung, Animationen, Dialoge und Barrierefreiheitsoptionen",
            "mittlere Komplexität, aber bereits stabil im Projekt",
            "beibehalten und vorhandene Qt-Fähigkeiten besser nutzen",
        ),
        (
            "pyqtgraph",
            "pyqtgraph",
            "real_time_plotting",
            "core",
            "schnelle Live-Visualisierung direkt in Qt; passend für eine einzelne HRV-Spur",
            "visuelle Überladung möglich, wenn zu viele Kurven/Interaktionen aktiv sind",
            "beibehalten, aber als ruhige Ein-Signal-Spur konfigurieren",
        ),
        (
            "NumPy",
            "numpy",
            "numeric_core",
            "core",
            "performante Fensterberechnung und robuste Skalenlogik",
            "gering; Standard im wissenschaftlichen Python-Stack",
            "beibehalten",
        ),
        (
            "bleak",
            "bleak",
            "ble_input",
            "core",
            "plattformübergreifender BLE-Zugriff auf RR-Daten",
            "Windows-BLE bleibt zustands- und geräteabhängig",
            "beibehalten, aber weiter über BLE-State-Machine absichern",
        ),
        (
            "PySide6.QtAsyncio",
            "PySide6.QtAsyncio",
            "async_qt_bridge",
            "optional_core_candidate",
            "könnte BLE/Asyncio langfristig näher an den Qt-Eventloop bringen",
            "Refactor-Risiko; aktuell läuft QThread + asyncio stabiler für die vorhandene Struktur",
            "später in isoliertem BLE-Controller prüfen, nicht sofort erzwingen",
        ),
        (
            "qasync",
            "qasync",
            "async_qt_bridge",
            "optional_candidate",
            "sauberere Coroutine-Integration für Qt-Anwendungen",
            "zusätzliche Abhängigkeit; Eventloop-Refactor berührt BLE-Stabilität",
            "nur als geplantes Experiment, nicht als Pflichtdependency",
        ),
        (
            "NeuroKit2",
            "neurokit2",
            "offline_hrv_research",
            "optional_research",
            "umfangreiche HRV-Indizes für Offline-Auswertung, Validierung und Forschungsberichte",
            "für Live-Feedback zu schwergewichtig und kann Interpretationsüberhang erzeugen",
            "optional für Expert-/Research-Export, nicht für den Trainingskreis",
        ),
        (
            "SciPy",
            "scipy",
            "signal_processing",
            "optional_research",
            "robuste Filter, Spektralanalyse und spätere Resonanzfrequenz-Schätzung",
            "zusätzliche Installationslast; Live-Training braucht es nicht zwingend",
            "optional für RF-/Offline-Analyse vorbereiten",
        ),
        (
            "PySide6-Fluent-Widgets / QFluentWidgets",
            "qfluentwidgets",
            "fluent_design_widgets",
            "deferred_ui_candidate",
            "Windows-11-nahe Komponenten wie Cards, InfoBars, Segmented Controls und Navigation",
            "GPLv3-/Lizenzthema und potenzielle Versionssensitivität; kann die stabile Qt-Basis verkomplizieren",
            "nicht automatisch integrieren; Designprinzipien übernehmen, Abhängigkeit nur nach Lizenzentscheidung",
        ),
        (
            "Dear PyGui",
            "dearpygui",
            "gpu_visual_lab",
            "prototype_only",
            "sehr schnelle GPU-Visualisierungen und ImPlot für experimentelle Biofeedback-Labore",
            "anderes UI-Paradigma; würde native Windows-/Qt-App faktisch neu aufbauen",
            "höchstens Prototyp für alternative Visualisierungen, nicht Hauptapp",
        ),
        (
            "Flet",
            "flet",
            "cross_platform_frontend",
            "prototype_only",
            "Flutter-artige Cross-Plattform-Oberfläche mit Python-Logik",
            "BLE, lokale Windows-Integration und Packaging müssten neu bewertet werden",
            "nicht für die aktuelle lokale Windows-Hauptapp übernehmen",
        ),
        (
            "NiceGUI",
            "nicegui",
            "browser_dashboard",
            "prototype_only",
            "schnelle browserbasierte Dashboards und 3D/Plot-Experimente",
            "Browser-UI passt weniger zu fokussiertem Offline-BLE-Training",
            "für Remote-/Trainer-Dashboard denkbar, nicht für den Trainingsraum",
        ),
    ]
    return [
        LibraryCapability(
            name=name,
            import_name=import_name,
            installed=_installed(import_name),
            role=role,
            integration_level=level,
            user_experience_value=value,
            risk=risk,
            decision=decision,
        )
        for name, import_name, role, level, value, risk, decision in specs
    ]


def recommended_ui_opportunities() -> list[UiOpportunity]:
    """Rank near-term UX improvements that fit the product contract."""

    return [
        UiOpportunity(
            title="Ruhige HRV-Spur",
            source="pyqtgraph + eigene Visual-Policy",
            implementation="visuelle Glättung, trägere Y-Skalierung, keine Mausinteraktion, nur ein Signal",
            default_visibility="Training, wenn HRV-Spur sichtbar ist",
            rationale="reduziert visuelles Rauschen ohne Messdaten zu verändern",
        ),
        UiOpportunity(
            title="Adaptive Detailschicht",
            source="Qt Widgets + hrv_adaptive_ui",
            implementation="Kernzahlen nur bei Bedarf oder Signalreparatur anzeigen",
            default_visibility="ausgeblendet im normalen Training",
            rationale="Kreis, Graph, Text und Zahlen bleiben komplementär statt konkurrierend",
        ),
        UiOpportunity(
            title="Bibliotheks- und UX-Audit",
            source="importlib + Expertenbereich",
            implementation="lokal anzeigen, welche optionalen Bibliotheken vorhanden sind und was sie leisten könnten",
            default_visibility="nur Expertenbereich",
            rationale="Innovation wird dokumentierbar, ohne das Training zu überladen",
        ),
        UiOpportunity(
            title="Eventloop-Experiment",
            source="PySide6.QtAsyncio oder qasync",
            implementation="später isoliert im BLE-Controller testen, bevor der stabile QThread-Pfad ersetzt wird",
            default_visibility="nicht sichtbar",
            rationale="potenziell sauberere Architektur, aber nur mit geringem Risiko einführen",
        ),
        UiOpportunity(
            title="Research-Export-Erweiterung",
            source="NeuroKit2/SciPy optional",
            implementation="Offline-Report für Forschung, nicht Live-Feedback",
            default_visibility="Experten-/Auswertungsbereich",
            rationale="mehr Analysefähigkeit ohne Diagnostik- oder Dashboard-Sog im Training",
        ),
    ]


def capability_report_text() -> str:
    """Format the capability map for the expert dialog."""

    lines = [
        "Bibliotheken & UX-Potenzial",
        f"Capability-Modell: {UI_CAPABILITY_VERSION}",
        "",
        "Grundentscheidung: Die Hauptapp bleibt PySide6/pyqtgraph-basiert. Neue Bibliotheken werden nur übernommen, wenn sie den Trainingsraum ruhiger, stabiler oder besser dokumentierbar machen.",
        "",
        "Aktueller Capability-Scan:",
    ]
    for cap in detect_library_capabilities():
        state = "installiert" if cap.installed else "nicht installiert"
        lines.append(f"- {cap.name}: {state} · {cap.integration_level}")
        lines.append(f"  Nutzen: {cap.user_experience_value}")
        lines.append(f"  Entscheidung: {cap.decision}")
        lines.append(f"  Risiko: {cap.risk}")
    lines.extend(["", "Passende nächste UX-Schritte:"])
    for idx, item in enumerate(recommended_ui_opportunities(), start=1):
        lines.append(f"{idx}. {item.title} — {item.implementation}")
        lines.append(f"   Sichtbarkeit: {item.default_visibility}. Begründung: {item.rationale}")
    return "\n".join(lines)


def capability_metadata() -> dict[str, Any]:
    """Serializable capability data for session metadata."""

    return {
        "ui_capability_version": UI_CAPABILITY_VERSION,
        "libraries": [cap.to_dict() for cap in detect_library_capabilities()],
        "opportunities": [item.to_dict() for item in recommended_ui_opportunities()],
    }
