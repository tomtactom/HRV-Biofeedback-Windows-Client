"""Adaptive session planning for the visible three-phase HRV workflow.

This module translates sensor state, a short self-check and the last session
review into a small, user-facing plan.  It keeps adaptivity complementary to the
biofeedback signal: the plan changes preparation and aftercare guidance, but it
never creates a second visible training target next to HRV amplitude.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

GUIDED_SESSION_VERSION = "0.30-guided-session-plan"


@dataclass(frozen=True)
class GuidedSessionPlan:
    """A compact plan for the next session."""

    model_version: str
    plan_id: str
    label: str
    primary_action: str
    preparation_hint: str
    training_hint: str
    aftercare_hint: str
    baseline_recommended: bool
    show_details_preferred: bool
    tone: str
    reason: str
    complementary_channels: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _rating(ratings: dict[str, Any], key: str, default: int = 5) -> int:
    try:
        return int(ratings.get(key, default))
    except Exception:
        return default


def _recent_primary_step(recent_review: dict[str, Any] | None) -> str:
    if not recent_review:
        return ""
    try:
        return str((recent_review.get("next_session_plan") or {}).get("primary_next_step") or "")
    except Exception:
        return ""


def guided_session_contract() -> dict[str, Any]:
    """Document how adaptive planning may influence the visible workflow."""

    return {
        "version": GUIDED_SESSION_VERSION,
        "core_rule": "Die Planung verändert Vorbereitung und Nachbereitung, nicht das Hauptfeedbacksignal.",
        "primary_signal": "HRV-Amplitude",
        "complementarity": {
            "preparation": "kleine Entscheidungshilfe vor dem Start",
            "training": "Kreis und HRV-Spur bleiben die eigentlichen Lernkanäle",
            "aftercare": "ein kurzer nächster Schritt statt langer Analyse",
        },
        "adaptivity_boundary": "Keine Diagnosen, keine normativen Bewertungen, keine versteckten Leistungsziele.",
    }


def compute_guided_session_plan(
    *,
    sensor_ready: bool,
    ble_packet_count: int = 0,
    ble_rr_value_count: int = 0,
    signal_quality: float = 0.0,
    ratings: dict[str, Any] | None = None,
    focus_key: str = "observe_contact",
    recent_review: dict[str, Any] | None = None,
    mock_active: bool = False,
) -> GuidedSessionPlan:
    """Return a small adaptive plan for the next visible step.

    The logic is intentionally conservative.  It prioritizes measurement first,
    then a baseline when arousal/contact suggests a slower start, and otherwise a
    direct training path.  It only produces UI guidance; it does not change HRV
    scoring, rewards or exported raw data.
    """

    ratings = ratings or {}
    tension = _rating(ratings, "tension")
    focus = _rating(ratings, "focus")
    body_contact = _rating(ratings, "body_contact")
    recent_step = _recent_primary_step(recent_review)
    rr_ready = bool(sensor_ready or ble_rr_value_count > 0 or mock_active)
    any_packets = bool(ble_packet_count > 0)
    complementary_channels = {
        "circle": "unmittelbare HRV-Amplitude",
        "trace": "zeitlicher Kontext derselben HRV-Amplitude",
        "guidance": "nächste kleine Handlung vor/nach dem Training",
        "details": "nur optional oder zur Signalreparatur",
    }

    if not rr_ready and not any_packets:
        return GuidedSessionPlan(
            model_version=GUIDED_SESSION_VERSION,
            plan_id="prepare_sensor",
            label="Sensor vorbereiten",
            primary_action="Sensor vorbereiten",
            preparation_hint="Zuerst Sensor und RR-Datenbasis herstellen. Danach erst Training starten.",
            training_hint="Noch nicht trainieren; verwertbare RR-Daten sind die Grundlage.",
            aftercare_hint="Nach einem Signaltest genügt ein kurzer Hinweis: kamen RR-Daten an oder nicht?",
            baseline_recommended=True,
            show_details_preferred=True,
            tone="active",
            reason="no_rr_stream_yet",
            complementary_channels=complementary_channels,
        )

    if any_packets and not rr_ready:
        return GuidedSessionPlan(
            model_version=GUIDED_SESSION_VERSION,
            plan_id="repair_rr_stream",
            label="RR-Signal prüfen",
            primary_action="Kontakt prüfen",
            preparation_hint="Herzrate ist sichtbar, RR-Intervalle fehlen. Kontakt, Gurtlage und konkurrierende Apps prüfen.",
            training_hint="Training erst starten, wenn RR-Daten ankommen; sonst wäre HRV-Feedback nicht belastbar.",
            aftercare_hint="Dokumentieren, welche Kontakt- oder Verbindungsänderung geholfen hat.",
            baseline_recommended=True,
            show_details_preferred=True,
            tone="warn",
            reason="bpm_without_rr",
            complementary_channels=complementary_channels,
        )

    if recent_step == "sensor_rr_check":
        return GuidedSessionPlan(
            model_version=GUIDED_SESSION_VERSION,
            plan_id="short_signal_check",
            label="Kurzer Signalcheck",
            primary_action="Training mit Baseline",
            preparation_hint="Die letzte Sitzung spricht für einen kurzen Signalcheck. 30–60 Sekunden Kontaktphase vor dem eigentlichen Training genügen.",
            training_hint="Erst Aufbauphase beobachten; danach HRV-Amplitude ruhig trainieren.",
            aftercare_hint="Kurz festhalten, ob die RR-Daten heute stabiler waren.",
            baseline_recommended=True,
            show_details_preferred=True,
            tone="active",
            reason="recent_review_prioritized_signal",
            complementary_channels=complementary_channels,
        )

    if tension >= 8 or body_contact <= 3 or signal_quality < 0.55:
        return GuidedSessionPlan(
            model_version=GUIDED_SESSION_VERSION,
            plan_id="settle_then_train",
            label="Ruhiger Einstieg",
            primary_action="Training mit Baseline",
            preparation_hint="Ein ruhiger Einstieg ist passend: kurz Kontakt, Sitzposition und Körperwahrnehmung sammeln.",
            training_hint="Baseline als Übergang nutzen; danach verstärkt der Kreis HRV-Amplitude.",
            aftercare_hint="Nachher reicht eine Beobachtung: Was hat den Einstieg erleichtert?",
            baseline_recommended=True,
            show_details_preferred=False,
            tone="active",
            reason="high_load_or_low_contact",
            complementary_channels=complementary_channels,
        )

    if recent_step == "training" and signal_quality >= 0.75 and body_contact >= 5:
        return GuidedSessionPlan(
            model_version=GUIDED_SESSION_VERSION,
            plan_id="direct_training",
            label="Direktes Training",
            primary_action="Training starten",
            preparation_hint="Signal und Selbstcheck wirken ausreichend geordnet. Eine kurze direkte Trainingseinheit passt.",
            training_hint="Kreis im Vordergrund lassen; Details nur öffnen, wenn du sie brauchst.",
            aftercare_hint="Ein kleiner Alltagstransfer genügt: Wann wäre eine 2-Minuten-Übung passend?",
            baseline_recommended=False,
            show_details_preferred=False,
            tone="good",
            reason="recent_good_session_and_ready_signal",
            complementary_channels=complementary_channels,
        )

    if focus <= 3:
        focus_hint = "Der Lernfokus kann als Aufmerksamkeitsanker dienen; kurze Hinweise bleiben hilfreicher als zusätzliche Zahlen."
    elif focus_key == "values_intention":
        focus_hint = "Wertebezogene Absicht kurz halten; im Training übernimmt der Kreis die Rückmeldung."
    else:
        focus_hint = "Der gewählte Fokus bündelt Aufmerksamkeit; das Hauptsignal bleibt HRV-Amplitude."

    return GuidedSessionPlan(
        model_version=GUIDED_SESSION_VERSION,
        plan_id="standard_guided_training",
        label="Geführtes Training",
        primary_action="Training starten",
        preparation_hint=focus_hint,
        training_hint="Mit Baseline starten und dann HRV-Amplitude trainieren; Details bleiben optional.",
        aftercare_hint="Kurz notieren, welcher kleine Schritt in den Alltag passt.",
        baseline_recommended=True,
        show_details_preferred=False,
        tone="active",
        reason="default_guided_flow",
        complementary_channels=complementary_channels,
    )
