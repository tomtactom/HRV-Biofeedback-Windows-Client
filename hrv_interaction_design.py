"""Adaptive interaction design policies for the HRV Biofeedback UI.

This module does not change the physiological data path. It only decides how
much interface stimulation is appropriate in a given moment. The goal is a
complementary surface: the circle is the direct feedback channel, the HRV trace
adds temporal context, text gives a next step only when useful, and numbers stay
optional unless signal repair requires them.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


INTERACTION_DESIGN_VERSION = "0.33-sensory-adaptive-interface"


@dataclass(frozen=True)
class InteractionProfile:
    """Display profile for a phase without adding new training targets."""

    model_version: str
    phase: str
    attention_load: str
    primary_surface: str
    guidance_style: str
    motion_policy: str
    detail_policy: str
    graph_policy: str
    next_micro_action: str
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _focus_phrase(focus_key: str | None) -> str:
    mapping = {
        "observe_contact": "Körperkontakt bemerken, ohne etwas erzwingen zu müssen.",
        "attention_return": "Aufmerksamkeit freundlich zum Kreis zurückführen.",
        "allow_variability": "Schwankungen als Teil des Lernsignals zulassen.",
        "daily_transfer": "einen kleinen Alltagsmoment wiedererkennen.",
        "values_intention": "die gewählte Absicht kurz mit dem Körperkontakt verbinden.",
    }
    return mapping.get(str(focus_key or ""), "Kreis und Körperkontakt gemeinsam wahrnehmen.")


def compute_interaction_profile(
    *,
    phase: str,
    signal_quality: float = 0.0,
    rr_ready: bool = False,
    hrv_amplitude: float | None = None,
    elapsed_s: float = 0.0,
    focus_key: str | None = None,
    details_visible: bool = False,
    focus_mode: bool = False,
    calm_visuals_enabled: bool = True,
    reduced_motion: bool = True,
) -> InteractionProfile:
    """Return the UI profile that best preserves learning conditions.

    The profile is intentionally conservative: it favours low cognitive load,
    progressive disclosure and stable visual movement. It may raise details only
    when the feedback loop is otherwise opaque, for example when RR data are not
    available or the signal quality is low.
    """
    phase = str(phase or "idle")
    signal_quality = max(0.0, min(1.0, float(signal_quality or 0.0)))
    motion_policy = "reduced" if reduced_motion else "standard"

    if phase in {"idle", "preparation"}:
        return InteractionProfile(
            model_version=INTERACTION_DESIGN_VERSION,
            phase="preparation",
            attention_load="low",
            primary_surface="guided_start",
            guidance_style="choice_supportive",
            motion_policy=motion_policy,
            detail_policy="show_only_if_sensor_problem",
            graph_policy="hidden_until_training",
            next_micro_action="Sensor vorbereiten oder Mock-Test nutzen.",
            rationale="Vorbereitung soll Wahl, Orientierung und Signalprüfung bündeln, ohne Formularlast zu erzeugen.",
        )

    if phase == "aftercare":
        return InteractionProfile(
            model_version=INTERACTION_DESIGN_VERSION,
            phase="aftercare",
            attention_load="low",
            primary_surface="brief_reflection",
            guidance_style="integrative",
            motion_policy=motion_policy,
            detail_policy="summary_first_exports_later",
            graph_policy="context_only",
            next_micro_action="Eine Beobachtung und einen kleinen Transfer notieren.",
            rationale="Nachbereitung integriert die Sitzung kurz; Auswertung und Rohdaten bleiben nachgelagert.",
        )

    # Training: distinguish ordinary feedback, early build-up and signal repair.
    if not rr_ready or signal_quality < 0.45:
        return InteractionProfile(
            model_version=INTERACTION_DESIGN_VERSION,
            phase="training",
            attention_load="repair",
            primary_surface="signal_repair",
            guidance_style="concrete_next_step",
            motion_policy=motion_policy,
            detail_policy="temporarily_visible",
            graph_policy="pause_interpretation",
            next_micro_action="Kontakt und Sensorposition ruhig prüfen; andere Apps getrennt lassen.",
            rationale="Wenn RR-Daten fehlen, ist Signaltransparenz wichtiger als ein reduzierter Trainingsraum.",
        )

    if hrv_amplitude is None or elapsed_s < 60:
        return InteractionProfile(
            model_version=INTERACTION_DESIGN_VERSION,
            phase="training",
            attention_load="settling",
            primary_surface="circle_first",
            guidance_style="minimal_anchor",
            motion_policy=motion_policy,
            detail_policy="hidden_unless_requested" if not details_visible else "user_visible",
            graph_policy="building_baseline",
            next_micro_action="Aufbauphase zulassen; " + _focus_phrase(focus_key),
            rationale="In den ersten Sekunden entsteht die 60-s-Amplitude; ruhige Erwartung schützt vor Überinterpretation.",
        )

    if focus_mode:
        attention = "very_low"
    else:
        attention = "low"
    graph_policy = "calm_trace" if calm_visuals_enabled else "raw_trace"
    return InteractionProfile(
        model_version=INTERACTION_DESIGN_VERSION,
        phase="training",
        attention_load=attention,
        primary_surface="circle_first",
        guidance_style="minimal_anchor",
        motion_policy=motion_policy,
        detail_policy="hidden_unless_requested" if not details_visible else "user_visible",
        graph_policy=graph_policy,
        next_micro_action=_focus_phrase(focus_key),
        rationale="Ordentliches Training braucht ein dominantes Feedbacksignal und nur ergänzende Kontextkanäle.",
    )


def interaction_design_contract() -> dict[str, Any]:
    """Exportable product contract for the new interaction layer."""
    return {
        "version": INTERACTION_DESIGN_VERSION,
        "primary_rule": "Der Kreis bleibt das unmittelbare Feedbacksignal; andere Kanäle erklären oder kontextualisieren nur.",
        "complementarity_rule": "Graph, Zahlen und Text dürfen nicht gleichzeitig als konkurrierende Ziele auftreten.",
        "adaptivity_rule": "Bei Signalproblemen darf die UI kurz technischer werden; bei stabilem Training wird sie wieder ruhiger.",
        "psychological_rule": "Sprache bleibt wahlorientiert, nicht bewertend und körpernah.",
        "windows_rule": "Bewegung, Skalierung und Details werden konservativ eingesetzt, um DPI- und Belastungsprobleme zu vermeiden.",
    }


def interaction_design_report_text(profile: InteractionProfile | None = None) -> str:
    """Human-readable expert report for the UI design layer."""
    contract = interaction_design_contract()
    lines = [
        "Interaktionsdesign & Adaptivität",
        f"Version: {INTERACTION_DESIGN_VERSION}",
        "",
        "Prinzipien:",
        f"- {contract['primary_rule']}",
        f"- {contract['complementarity_rule']}",
        f"- {contract['adaptivity_rule']}",
        f"- {contract['psychological_rule']}",
        f"- {contract['windows_rule']}",
        "",
        "Umsetzung:",
        "- Vorbereitung bündelt Wahl, Signalprüfung und Start.",
        "- Training nutzt Kreis, HRV-Spur, Hinweise und Details als komplementäre Kanäle.",
        "- Nachbereitung bleibt kurz und transferorientiert.",
        "- Reduzierte Bewegung ist die sichere Voreinstellung; Display-Glättung verändert keine Rohdaten.",
    ]
    if profile is not None:
        data = profile.to_dict()
        lines.extend([
            "",
            "Aktuelles Profil:",
            f"- Phase: {data['phase']}",
            f"- Aufmerksamkeitslast: {data['attention_load']}",
            f"- Hauptfläche: {data['primary_surface']}",
            f"- Details: {data['detail_policy']}",
            f"- Graph: {data['graph_policy']}",
            f"- Nächster kleiner Schritt: {data['next_micro_action']}",
            f"- Begründung: {data['rationale']}",
        ])
    return "\n".join(lines)
