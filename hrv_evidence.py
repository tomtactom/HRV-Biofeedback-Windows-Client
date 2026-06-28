"""Evidence-integration helpers for HRV Biofeedback.

This module translates recent HRV / HRVB publications into small product rules.
It is intentionally conservative: it improves documentation, preparation and
aftercare, but it does not turn the app into a medical device or add a second
visible training target next to HRV amplitude.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

EVIDENCE_MODEL_VERSION = "0.31-2026-evidence-integration"


@dataclass(frozen=True)
class EvidenceFinding:
    """A concise, auditable research finding used by the app."""

    key: str
    source: str
    year: int
    evidence_type: str
    finding: str
    product_implication: str
    visibility: str = "metadata_and_brief_ui"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceSessionRecommendation:
    """Small evidence-informed recommendation for the current session."""

    model_version: str
    recommendation_id: str
    visible_hint: str
    practice_window: str
    protocol_choice: str
    measurement_guardrail: str
    aftercare_hint: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def latest_evidence_findings() -> list[EvidenceFinding]:
    """Return the research points currently implemented in product logic."""

    return [
        EvidenceFinding(
            key="hrv_reporting_guidelines_2024",
            source="Quigley et al. 2024, Psychophysiology HR/HRV publication guidelines",
            year=2024,
            evidence_type="committee_report_reporting_guideline",
            finding=(
                "HRV studies should report physiological foundations, recording method, derivation, "
                "sample/context details and analysis choices transparently."
            ),
            product_implication=(
                "Keep raw RR export, artifact rules, context variables, app version, protocol type and "
                "interpretation boundaries in metadata."
            ),
        ),
        EvidenceFinding(
            key="remote_hrvb_meta_2025",
            source="Vann-Adibe et al. 2025, systematic review and meta-analysis of remote HRV-B",
            year=2025,
            evidence_type="systematic_review_meta_analysis",
            finding=(
                "Remote HRV-B appears useful for depression and HRV outcomes, while effects for stress "
                "are more mixed; protocol features such as resonance-maximizing feedback and shorter "
                "daily practice windows may matter."
            ),
            product_implication=(
                "Prefer short, repeatable training windows; keep visual feedback on the device; do not "
                "claim reliable stress reduction from a single session."
            ),
        ),
        EvidenceFinding(
            key="mental_disorders_umbrella_2025",
            source="Wang et al. 2025, umbrella review of HRV in mental disorders",
            year=2025,
            evidence_type="umbrella_review",
            finding=(
                "HRV differences in mental disorders are heterogeneous; suggestive evidence exists for "
                "some conditions, while many associations remain weak or controversial."
            ),
            product_implication=(
                "Use HRV as a self-regulation training signal, not as a diagnostic or symptom-inference signal."
            ),
        ),
        EvidenceFinding(
            key="global_coherence_dataset_2025",
            source="Balaji et al. 2025, Scientific Reports global HRV biofeedback dataset",
            year=2025,
            evidence_type="large_observational_app_dataset",
            finding=(
                "A large app dataset found common coherence frequencies around 0.10 Hz and associations "
                "between positive emotional states, higher coherence and more stable HRV frequencies."
            ),
            product_implication=(
                "Document dominant rhythm near 0.1 Hz as descriptive context, while avoiding causal claims; "
                "support gentle positive-affect/values prompts without making them mandatory."
            ),
        ),
        EvidenceFinding(
            key="rf_vs_fixed_2026",
            source="Sumińska et al. 2026, RF versus fixed 0.1 Hz randomized comparison",
            year=2026,
            evidence_type="randomized_trial",
            finding=(
                "Both individualized resonance-frequency HRVB and fixed 0.1 Hz breathing groups showed "
                "reductions in self-reported stress, anxiety and depressive symptoms versus control, with "
                "no meaningful difference between RF and fixed 0.1 Hz in that study."
            ),
            product_implication=(
                "Keep individual HRV-amplitude training as default, but prepare an optional fixed 0.1 Hz / "
                "six-breaths-per-minute mode as a pragmatic future option rather than a required step."
            ),
        ),
        EvidenceFinding(
            key="cad_pilot_2025",
            source="Shah et al. 2025, JAMA Network Open HRVB and mental-stress myocardial flow reserve",
            year=2025,
            evidence_type="pilot_randomized_clinical_trial",
            finding=(
                "In a small pilot RCT with coronary artery disease, six weeks of HRVB was associated with "
                "improved myocardial flow reserve during mental stress, but larger trials are still needed."
            ),
            product_implication=(
                "Mention HRVB as training/self-regulation only; include conservative health boundaries and avoid "
                "cardiovascular treatment claims."
            ),
        ),
        EvidenceFinding(
            key="brief_rfb_2025",
            source="Spalding et al. 2025, brief resonance frequency breathing in high GAD scorers",
            year=2025,
            evidence_type="single_session_experiment",
            finding=(
                "A brief resonance-frequency breathing exercise can acutely increase HRV, while single-session "
                "effects on worry or inhibitory control were not demonstrated."
            ),
            product_implication=(
                "Separate acute physiological feedback from psychological outcome claims; aftercare should ask "
                "what was observed rather than state that symptoms changed."
            ),
        ),
        EvidenceFinding(
            key="vr_biofeedback_sleep_2025",
            source="Seong et al. 2025, JMIR randomized VR/conventional biofeedback study",
            year=2025,
            evidence_type="randomized_controlled_study",
            finding=(
                "Both VR-based and conventional biofeedback improved sleep-quality measures in people with "
                "depressive/anxiety symptoms; VR was not clearly superior to conventional biofeedback."
            ),
            product_implication=(
                "Use modern visual design without assuming immersive or complex visuals are better; clarity and adherence matter."
            ),
        ),
    ]


def evidence_metadata() -> dict[str, Any]:
    """Auditable evidence profile saved with sessions and reflections."""

    return {
        "evidence_model_version": EVIDENCE_MODEL_VERSION,
        "implemented_findings": [finding.to_dict() for finding in latest_evidence_findings()],
        "product_rules": {
            "primary_signal": "HRV-Amplitude bleibt das einzige sichtbare Trainingsziel.",
            "clinical_boundary": "Keine Diagnose, keine Symptomurteile, keine Behandlungsaussage aus Einzelsitzungen.",
            "measurement_boundary": "RR-Qualität, Artefaktanteil, Kontext und App-Version werden dokumentiert.",
            "practice_boundary": "Kurze, wiederholbare Sitzungen werden bevorzugt; >20 Minuten tägliche Pflichtpraxis wird nicht empfohlen.",
            "resonance_boundary": "0.1-Hz-/RF-Information wird als optionaler Kontext vorbereitet, nicht als verpflichtender Atem-Pacer.",
        },
    }


def compute_evidence_session_recommendation(
    *,
    guided_plan: dict[str, Any] | None = None,
    ratings: dict[str, Any] | None = None,
    sensor_ready: bool = False,
    signal_quality: float = 0.0,
    session_minutes: float = 10.0,
) -> EvidenceSessionRecommendation:
    """Return a conservative session recommendation based on current evidence."""

    guided_plan = guided_plan or {}
    ratings = ratings or {}
    try:
        tension = int(ratings.get("tension", 5))
    except Exception:
        tension = 5
    try:
        focus = int(ratings.get("focus", 5))
    except Exception:
        focus = 5
    plan_id = str(guided_plan.get("plan_id") or "")
    session_minutes = max(1.0, float(session_minutes or 10.0))

    if not sensor_ready:
        return EvidenceSessionRecommendation(
            model_version=EVIDENCE_MODEL_VERSION,
            recommendation_id="quality_before_training",
            visible_hint="Evidenzrahmen: Erst RR-Datenqualität sichern, dann trainieren.",
            practice_window="Heute genügt ein kurzer Signaltest; keine Trainingswirkung aus fehlenden RR-Daten ableiten.",
            protocol_choice="Kein Atem-Pacer aktiv; 0.1-Hz-/RF-Modus bleibt optionaler Zukunftsbaustein.",
            measurement_guardrail="Ohne echte RR-Intervalle keine HRV-Amplitude bewerten.",
            aftercare_hint="Nachher nur dokumentieren, ob RR-Daten ankamen und was beim Kontakt geholfen hat.",
            reason="sensor_or_rr_not_ready",
        )

    if plan_id in {"settle_then_train", "short_signal_check"} or tension >= 8 or signal_quality < 0.55:
        return EvidenceSessionRecommendation(
            model_version=EVIDENCE_MODEL_VERSION,
            recommendation_id="settled_short_practice",
            visible_hint="Evidenzrahmen: Kurz, ruhig und messbar starten; Baseline beibehalten.",
            practice_window="6–10 Minuten Training sind passend; bei hoher Aktivierung lieber kürzer und wiederholbar.",
            protocol_choice="HRV-Amplitude bleibt Hauptfeedback; eine spätere 0.1-Hz-Option kann als vereinfachter Pacer dienen.",
            measurement_guardrail="Artefaktanteil und Kontext sind wichtiger als ein einzelner hoher HRV-Wert.",
            aftercare_hint="Nachher eine beobachtete hilfreiche Bedingung notieren, nicht interpretieren.",
            reason="high_load_or_quality_needs_settling",
        )

    if plan_id == "direct_training" and focus >= 5 and signal_quality >= 0.75:
        return EvidenceSessionRecommendation(
            model_version=EVIDENCE_MODEL_VERSION,
            recommendation_id="direct_compact_training",
            visible_hint="Evidenzrahmen: Direktes kompaktes Training passt; Details bleiben optional.",
            practice_window="6–10 Minuten reichen für ein sauberes Trainingsfenster; tägliche Pflichtdauer unter 20 Minuten halten.",
            protocol_choice="Individualisiertes HRV-Amplitudenfeedback bleibt default; 0.1 Hz ist kein Muss.",
            measurement_guardrail="Vergleiche nur mit ähnlicher Dauer, Haltung und Kontext vornehmen.",
            aftercare_hint="Eine 2-Minuten-Alltagssituation auswählen, in der das Übungselement wiederholbar ist.",
            reason="ready_signal_and_low_load",
        )

    return EvidenceSessionRecommendation(
        model_version=EVIDENCE_MODEL_VERSION,
        recommendation_id="standard_evidence_informed",
        visible_hint="Evidenzrahmen: Ein klares Signal, kurze Übungszeit, vorsichtige Interpretation.",
        practice_window=f"Geplantes Fenster: etwa {int(round(session_minutes))} Minuten; Wiederholbarkeit zählt mehr als Länge.",
        protocol_choice="Kein verpflichtender Atem-Pacer; 0.1-Hz-/RF-Elemente werden nur als optionale Ergänzung vorbereitet.",
        measurement_guardrail="RR-Daten, Artefakte und Kontext bestimmen, wie belastbar die Sitzung ist.",
        aftercare_hint="Nachher Selbstbeobachtung und Transfer trennen: Was war messbar, was war erlebbar, was passt in den Alltag?",
        reason="default_evidence_informed_flow",
    )


def measurement_quality_notes(summary: dict[str, Any] | None) -> list[str]:
    """Return short aftercare notes on measurement quality."""

    summary = summary or {}
    artifact_ratio = float(summary.get("artifact_ratio") or 0.0)
    valid_rr = int(summary.get("valid_rr_count") or 0)
    duration_s = float(summary.get("duration_s") or 0.0)
    notes: list[str] = []
    if valid_rr < 60:
        notes.append("Wenig RR-Daten: Die Sitzung eher als Signaltest betrachten.")
    if artifact_ratio > 0.20:
        notes.append("Erhöhter Artefaktanteil: Kontakt und Bewegungsruhe sind beim nächsten Mal wichtiger als Interpretation.")
    elif valid_rr >= 60:
        notes.append("RR-Datenbasis ausreichend für eine beschreibende Sitzungsnotiz; keine Diagnose ableiten.")
    if duration_s and duration_s < 300:
        notes.append("Kurze Dauer: Für Verlaufsaussagen möglichst ähnliche Sitzungsfenster wiederholen.")
    return notes or ["Messqualität beschreibend dokumentiert; Kontext bleibt für Vergleiche wichtig."]


def evidence_aftercare_summary(summary: dict[str, Any] | None) -> list[str]:
    """Return short evidence-informed aftercare prompts."""

    notes = measurement_quality_notes(summary)
    notes.append("Einzelne HRV-Sitzungen zeigen Trainingserfahrung, keine medizinische Veränderung.")
    notes.append("Kurze wiederholbare Praxisfenster sind derzeit plausibler als lange Pflichtübungen.")
    return notes
