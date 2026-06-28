"""Visible product contract for HRV Biofeedback.

The application has several expert layers (BLE diagnostics, research exports,
statistical background models).  This module defines the visible product core so
future changes do not accidentally turn the training room back into a technical
dashboard.
"""

from __future__ import annotations

APP_PRODUCT_CONTRACT_VERSION = "0.30-adaptive-guided-flow-consolidation"

PHASE_LABELS = {
    "idle": "Bereit",
    "reference": "Referenz",
    "baseline": "Baseline",
    "training": "Training",
    "paused": "Pausiert",
}

VISIBLE_PHASES = ("Vorbereitung", "Training", "Nachbereitung")
PRIMARY_VISIBLE_SIGNAL = "HRV-Amplitude"
VISIBLE_TRAINING_SIGNALS = ("HRV-Amplitude", "Signalqualität", "Herzrate")

# Terms that are useful in code/export but should not compete for attention in
# the normal training surface.
HIDDEN_EXPERT_TERMS = (
    "SEM",
    "Strukturgleichungsmodell",
    "Feedback-Score",
    "HRV-Score",
    "Modellvertrauen",
    "Integrationsindex",
    "Double-Loop",
)

PRODUCT_CORE_SUMMARY = (
    "Ein Hauptsignal: HRV-Amplitude. Komplementäre Kanäle statt konkurrierender Scores. "
    "Ein Hauptweg: Sensor vorbereiten, trainieren, kurz nachbereiten. "
    "Adaptive Sitzungsplanung unterstützt den nächsten Schritt, erzeugt aber kein zweites Trainingsziel. "
    "Expertentiefe bleibt verfügbar, aber außerhalb des Trainingsraums."
)


def visible_training_contract() -> dict[str, object]:
    """Return the user-facing design contract stored in session metadata."""
    return {
        "version": APP_PRODUCT_CONTRACT_VERSION,
        "primary_signal": PRIMARY_VISIBLE_SIGNAL,
        "visible_training_signals": list(VISIBLE_TRAINING_SIGNALS),
        "visible_phases": list(VISIBLE_PHASES),
        "summary": PRODUCT_CORE_SUMMARY,
        "expert_terms_hidden_from_default_flow": list(HIDDEN_EXPERT_TERMS),
    }
