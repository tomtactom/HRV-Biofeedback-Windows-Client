"""Psychological protocol helpers for HRV Biofeedback.

The helpers in this module keep the user-facing training logic neutral,
observable and auditable. They do not infer diagnoses. They translate a
small set of biofeedback and self-regulation principles into the three app
phases: preparation, training and aftercare.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from hrv_evidence import evidence_metadata, EVIDENCE_MODEL_VERSION

PSYCHOLOGY_MODEL_VERSION = "0.31-autonomy-evidence-integrated-protocol"

RATING_FIELDS = {
    "tension": "Anspannung",
    "focus": "Fokus",
    "energy": "Energie",
    "body_contact": "Körperkontakt",
}


@dataclass(frozen=True)
class PhaseProtocol:
    preparation: str
    training: str
    aftercare: str


@dataclass(frozen=True)
class LearningProtocol:
    """Concise, non-clinical protocol assumptions documented per session."""

    primary_feedback_signal: str
    reinforcement_principle: str
    attention_principle: str
    transfer_principle: str
    interpretation_boundary: str


@dataclass(frozen=True)
class PsychologicalFoundation:
    """Scientific and language principles used by the app.

    The fields are documented in metadata so that the live intervention stays
    transparent and auditable without turning the UI into a theory lecture.
    """

    hrvb_protocol: str
    cognitive_psychology: str
    biological_psychology: str
    self_determination: str
    act_rft_language: str
    social_psychology: str
    reporting_boundary: str


@dataclass(frozen=True)
class LearningFocusOption:
    key: str
    label: str
    preparation_prompt: str
    training_anchor: str
    aftercare_prompt: str


def phase_protocol() -> PhaseProtocol:
    """Return the human-readable training rationale used by the app."""
    return PhaseProtocol(
        preparation=(
            "Vorbereitung schafft einen ruhigen Start: Sensor prüfen, Kontext erfassen, "
            "subjektiven Ausgangszustand benennen, einen frei wählbaren Lernfokus wählen "
            "und das Training als beobachtendes Lernfenster rahmen."
        ),
        training=(
            "Im Training wird primär HRV-Amplitude positiv rückgemeldet. Die Rückmeldung bleibt "
            "graduell und kontingent, damit kleine physiologische Veränderungen sichtbar werden, "
            "ohne harte Bewertung."
        ),
        aftercare=(
            "Nachbereitung dokumentiert Mess- und Erlebensdaten, unterstützt Transferideen, "
            "fördert Selbstwirksamkeit, unterstützt Wenn-Dann-Transfer und trennt Trainingserfahrung von medizinischer Bewertung."
        ),
    )


def learning_protocol() -> LearningProtocol:
    """Protocol principles used for metadata and the protocol dialog."""
    return LearningProtocol(
        primary_feedback_signal="HRV-Amplitude im gleitenden 60-s-Fenster",
        reinforcement_principle=(
            "Positive, zeitnahe und graduelle Rückmeldung: Der Kreis wird größer, wenn das "
            "primäre Zielsignal ansteigt. Stabile Abschnitte werden im Hintergrund dokumentiert, "
            "ohne als sichtbares Punktesystem zu dominieren. Das Feedback bleibt informativ statt kontrollierend."
        ),
        attention_principle=(
            "Aufmerksamkeitslenkung mit niedriger kognitiver Last: Ein klarer Graph, ein Kreis, "
            "ein optionaler Lernfokus. Die Hinweise bleiben kurz, beobachtend und nicht bewertend."
        ),
        transfer_principle=(
            "Nach der Sitzung wird ein selbstgewählter Wenn-Dann-Mini-Plan angeboten. Kurze, "
            "wiederholte Übungsfenster unterstützen Alltagstransfer und Selbstwirksamkeit."
        ),
        interpretation_boundary=(
            "Subjektive Ratings und HRV-Werte werden als Selbstbeobachtung dokumentiert. "
            "Es werden keine Diagnosen, Symptomurteile oder medizinischen Bewertungen abgeleitet."
        ),
    )


def psychological_foundation() -> PsychologicalFoundation:
    """Return the non-clinical theory frame used for the UI and metadata."""
    return PsychologicalFoundation(
        hrvb_protocol=(
            "Individual HRVB ohne Atem-Pacer: primäres Live-Ziel ist eine höhere, gleichmäßigere "
            "HRV-Amplitude auf Basis echter RR-Intervalle. Resonanzfrequenz-/Pacer-Elemente bleiben optional vorbereitet."
        ),
        cognitive_psychology=(
            "Reduzierte visuelle Konkurrenz, klare Phasen, ein dominantes Biofeedback-Signal, kurze "
            "Aufmerksamkeitsanker und Wiederholung statt Informationsüberladung."
        ),
        biological_psychology=(
            "HRV wird als neurokardiales Selbstregulationssignal beobachtet. Interpretation bleibt vorsichtig, "
            "weil Kontext, Sensorqualität, Tageszeit, Bewegung, Medikamente, Atmung, Schlaf und körperliche Belastung HRV beeinflussen können."
        ),
        self_determination=(
            "Autonomie, Kompetenz und Verbundenheit werden unterstützt: Wahlmöglichkeiten, nachvollziehbare Gründe, "
            "machbare nächste Schritte und Sprache ohne Druck."
        ),
        act_rft_language=(
            "Hinweise bevorzugen Beobachten, Kontakt zum gegenwärtigen Signal und wertebezogene kleine Handlungen. "
            "Vermeidbar sind Labels wie Erfolg/Versagen oder starre Sollwerte."
        ),
        social_psychology=(
            "Selbstbindung wird über freiwillige kleine Wenn-Dann-Pläne unterstützt; Fortschritt wird als Lernspur "
            "dokumentiert, nicht als Vergleich mit anderen Personen."
        ),
        reporting_boundary=(
            "Alle Protokoll- und Kontextdaten bleiben lokal, transparent exportierbar und dienen der Replizierbarkeit. "
            "Neuere HRV-Leitlinien stützen diese Zurückhaltung: Messmethode, Artefaktregeln, Kontext und Interpretationsgrenzen sind Teil der Sitzung. "
            "Die App nutzt reflektierte Lernschleifen: Auch eigene Annahmen über Signal, Verstärkung und Transfer werden nach Sitzungen überprüft."
        ),
    )


def learning_focus_options() -> list[LearningFocusOption]:
    """Autonomy-supportive choices for the preparation screen."""
    return [
        LearningFocusOption(
            key="observe_contact",
            label="Körperkontakt beobachten",
            preparation_prompt="Gurtkontakt, Sitzfläche und Haltung kurz wahrnehmen.",
            training_anchor="Körperkontakt und grünen Kreis gemeinsam beobachten.",
            aftercare_prompt="Welche Körperposition oder welcher Kontakt fühlte sich während stabiler Phasen stimmig an?",
        ),
        LearningFocusOption(
            key="soft_attention",
            label="Aufmerksamkeit sanft zurückführen",
            preparation_prompt="Einen ruhigen Blickpunkt wählen und die Rückmeldung als Orientierung nutzen.",
            training_anchor="Wenn Gedanken wandern: freundlich zurück zu Kreis und HRV-Spur.",
            aftercare_prompt="Woran war bemerkbar, dass Aufmerksamkeit zurückkehren konnte?",
        ),
        LearningFocusOption(
            key="allow_variability",
            label="Schwankungen zulassen",
            preparation_prompt="Die Sitzung als Lernfenster rahmen: Schwankungen gehören zur Messung.",
            training_anchor="Veränderungen bemerken, ohne sie festhalten zu müssen.",
            aftercare_prompt="Welche Schwankungen waren beobachtbar, ohne dass daraus eine Bewertung entstehen musste?",
        ),
        LearningFocusOption(
            key="daily_transfer",
            label="Alltagstransfer erkunden",
            preparation_prompt="Eine kurze Alltagssituation auswählen, in der 2 Minuten Übung denkbar sind.",
            training_anchor="Auf ein Element achten, das später im Alltag wiederholbar wirkt.",
            aftercare_prompt="Welche kleine Alltagssituation passt zu deinem heutigen Übungselement?",
        ),
        LearningFocusOption(
            key="values_based",
            label="Wertebezogene Absicht",
            preparation_prompt="Kurz benennen, wofür diese Übung heute stehen soll, z. B. Fürsorge oder Präsenz.",
            training_anchor="Die Rückmeldung als Kontakt mit der gewählten Absicht nutzen.",
            aftercare_prompt="Welcher nächste kleine Schritt passt zu deiner gewählten Absicht?",
        ),
    ]


def learning_focus_by_key(key: str | None) -> LearningFocusOption:
    options = learning_focus_options()
    lookup = {option.key: option for option in options}
    return lookup.get(str(key or ""), options[0])


def learning_focus_labels() -> dict[str, str]:
    return {option.key: option.label for option in learning_focus_options()}


def clamp_rating(value: Any, default: int = 5) -> int:
    try:
        return max(0, min(10, int(round(float(value)))))
    except Exception:
        return default


def normalize_ratings(ratings: dict[str, Any] | None) -> dict[str, int]:
    ratings = ratings or {}
    return {key: clamp_rating(ratings.get(key, 5)) for key in RATING_FIELDS}


def rating_change(pre: dict[str, Any] | None, post: dict[str, Any] | None) -> dict[str, int]:
    pre_n = normalize_ratings(pre)
    post_n = normalize_ratings(post)
    return {key: post_n[key] - pre_n[key] for key in RATING_FIELDS}


def preparation_readiness(ratings: dict[str, Any] | None, sensor_ready: bool = False) -> dict[str, Any]:
    """Return a neutral preparation summary.

    This is not a gatekeeper. It only helps the UI suggest a next step.
    """
    values = normalize_ratings(ratings)
    observations: list[str] = []
    suggestions: list[str] = []
    if values["body_contact"] <= 3:
        observations.append("Körperkontakt niedrig")
        suggestions.append("Gurt/Kontakt prüfen und 20–30 Sekunden ruhig sitzen, bevor du startest.")
    if values["tension"] >= 8:
        observations.append("hohe Aktivierung")
        suggestions.append("Mit Referenz oder Baseline beginnen und die erste Minute nur beobachten.")
    if values["focus"] <= 3:
        observations.append("Fokus zerstreut")
        suggestions.append("Eine einfache Beobachtungsabsicht wählen, z. B. ‚Kreis und Körperkontakt bemerken‘.")
    if values["energy"] <= 2:
        observations.append("Energie sehr niedrig")
        suggestions.append("Sitzung kurz halten oder Referenz/Mock-Test nutzen.")
    if not sensor_ready:
        suggestions.append("Sensor automatisch verbinden und RR-Signal prüfen; alternativ zunächst Mock-Test nutzen.")

    if not observations:
        observations.append("Startbedingungen wirken ausreichend stabil")
    if not suggestions:
        suggestions.append("Training starten, Baseline überspringen oder zunächst Referenz wählen — je nachdem, was gerade passend wirkt.")

    readiness_score = (
        (10 - values["tension"] if values["tension"] > 7 else 8)
        + values["focus"]
        + values["energy"]
        + values["body_contact"]
        + (8 if sensor_ready else 4)
    ) / 5.0
    return {
        "readiness_score": round(float(max(0.0, min(10.0, readiness_score))), 1),
        "observations": observations,
        "suggestions": suggestions,
    }


def preparation_summary_text(ratings: dict[str, Any] | None, sensor_ready: bool = False) -> str:
    readiness = preparation_readiness(ratings, sensor_ready=sensor_ready)
    lines = [f"Startbereitschaft: {readiness['readiness_score']:.1f}/10"]
    lines.append("Beobachtung: " + ", ".join(readiness["observations"]))
    lines.append("Nächster Schritt: " + readiness["suggestions"][0])
    return "\n".join(lines)


def training_focus_cue(
    *,
    phase: str,
    elapsed_s: float = 0.0,
    reward_active: bool = False,
    signal_quality: float = 0.0,
    hrv_amplitude: float | None = None,
    focus_key: str | None = None,
) -> str:
    """Short attention cue for the training screen.

    The cues are deliberately sparse. They support attentional regulation while
    keeping the operant visual feedback dominant.
    """
    focus = learning_focus_by_key(focus_key)
    if phase == "reference":
        return "Nur beobachten: Sensor, Kurve und Körperkontakt wahrnehmen."
    if phase == "baseline":
        return "Ankommen: Haltung finden, Schultern lösen, Kontakt zum Gurt bemerken."
    if phase == "paused":
        return "Pausiert: fortsetzen, wenn es passend ist; Pausenzeit wird herausgerechnet."
    if phase != "training":
        return "Bereit: Sensor verbinden oder Mock-Test starten."
    if signal_quality < 0.55:
        return "Signal zuerst: ruhig sitzen, Kontakt prüfen, größere Bewegungen reduzieren."
    if hrv_amplitude is None or elapsed_s < 60:
        return "Aufbauphase: der Graph sammelt erst genügend RR-Daten."
    if reward_active:
        return "Stabile Phase: nichts erzwingen; " + focus.training_anchor

    cue_bank = [
        focus.training_anchor,
        "Lernmodus: kleine Veränderungen reichen; der Kreis gibt unmittelbare Rückmeldung.",
        "Aufmerksamkeit: freundlich zurück zur Rückmeldung, wenn Gedanken wandern.",
        "Körperbezug: Sitzfläche, Gurtkontakt und ruhige Haltung bemerken.",
        "Transferblick: merken, welches Element später wiederholbar wirkt.",
    ]
    index = int(max(0.0, elapsed_s) // 75) % len(cue_bank)
    return cue_bank[index]


def training_guidance(
    *,
    phase: str,
    signal_quality: float = 0.0,
    hrv_amplitude: float | None = None,
    reward_active: bool = False,
    elapsed_s: float = 0.0,
) -> str:
    """Small, phase-sensitive user guidance for the training screen."""
    if phase == "reference":
        return "Referenz: Werte werden nur beobachtet und gespeichert. Es gibt keine Zielbewertung."
    if phase == "baseline":
        return "Baseline: kurz ankommen und beobachten. Die App sammelt deinen Ausgangsbereich."
    if phase == "paused":
        return "Pausiert: Fortsetzen oder speichern. Die Pausenzeit wird nicht als Trainingszeit gezählt."
    if phase != "training":
        return "Training startet, sobald Sensor oder Mock aktiv ist."

    if signal_quality < 0.55:
        return "Training: Signal prüfen. Kontakt, Sitzposition oder störende Bewegungen können die Rückmeldung beeinflussen."
    if hrv_amplitude is None or elapsed_s < 60:
        return "Training: HRV-Spur baut sich auf. Der Kreis reagiert, sobald genug RR-Daten vorhanden sind."
    if reward_active:
        return "Training: stabile Zielphase. Weiter beobachten, wie sich der Kreis und die HRV-Spur verändern."
    return "Training: der Kreis wächst mit deiner HRV-Amplitude. Kleine Veränderungen werden positiv sichtbar gemacht."


def preparation_science_prompts(ratings: dict[str, Any] | None, focus_key: str | None, sensor_ready: bool = False) -> list[str]:
    """Return short preparation prompts grounded in current protocol principles."""
    focus = learning_focus_by_key(focus_key)
    readiness = preparation_readiness(ratings, sensor_ready=sensor_ready)
    prompts = [
        "Wähle die Sitzungsform frei: Referenz, Training mit Baseline oder Baseline überspringen.",
        focus.preparation_prompt,
        readiness["suggestions"][0],
        "Die Werte werden als Lern- und Verlaufsdaten gespeichert, nicht als Bewertung der Person.",
    ]
    return prompts


def autonomy_supportive_reason() -> str:
    return (
        "Die App gibt Wahlmöglichkeiten, kurze Begründungen und konkrete nächste Schritte. "
        "So bleibt die Übung selbstbestimmt und nachvollziehbar."
    )


def implementation_intention(summary: dict[str, Any] | None, focus_key: str | None, custom_context: str = "") -> str:
    """Generate a small if-then transfer sentence for aftercare."""
    focus = learning_focus_by_key(focus_key)
    context = custom_context.strip() or "wenn ich eine kurze Pause bemerke"
    if summary and float(summary.get("artifact_ratio") or 0.0) > 0.20:
        action = "prüfe ich zuerst Körperkontakt und Sitzposition für 30 Sekunden"
    elif focus.key == "daily_transfer":
        action = "nutze ich 2 Minuten für das heute gewählte Übungselement"
    elif focus.key == "values_based":
        action = "verbinde ich einen Atemzug lang Haltung und gewählte Absicht"
    else:
        action = focus.training_anchor.lower().rstrip(".")
    return f"Wenn {context}, dann {action}."


def science_metadata() -> dict[str, Any]:
    """Return auditable science notes saved with each session."""
    return {
        "psychology_model_version": PSYCHOLOGY_MODEL_VERSION,
        "evidence_model_version": EVIDENCE_MODEL_VERSION,
        "latest_evidence": evidence_metadata(),
        "foundation": asdict(psychological_foundation()),
        "learning_focus_options": [asdict(option) for option in learning_focus_options()],
        "language_policy": {
            "style": "autonomieunterstützend, beobachtend, nicht-diagnostisch",
            "avoid": ["Erfolg/Versagen", "Sollwert als Norm", "Druck oder Defizitlabels"],
            "prefer": ["du kannst", "beobachte", "wenn passend", "nächster kleiner Schritt"],
        },
    }


def aftercare_change_summary(pre: dict[str, Any] | None, post: dict[str, Any] | None) -> list[str]:
    changes = rating_change(pre, post)
    labels = RATING_FIELDS
    lines: list[str] = []
    for key in ["tension", "focus", "energy", "body_contact"]:
        delta = changes[key]
        if delta == 0:
            direction = "unverändert"
        elif delta > 0:
            direction = f"+{delta}"
        else:
            direction = str(delta)
        lines.append(f"{labels[key]}: {direction}")
    return lines


def aftercare_transfer_suggestions(summary: dict[str, Any] | None, focus_key: str | None = None) -> list[str]:
    """Generate non-prescriptive transfer prompts from the recorded session."""
    summary = summary or {}
    artifact_ratio = float(summary.get("artifact_ratio") or 0.0)
    reward_count = int(summary.get("reward_count") or 0)
    mean_amp = summary.get("mean_hrv_amplitude_60s")
    duration_s = float(summary.get("duration_s") or 0.0)
    suggestions: list[str] = []
    focus = learning_focus_by_key(focus_key)
    suggestions.append(f"Lernfokus nachklingen lassen: {focus.aftercare_prompt}")
    if artifact_ratio > 0.20:
        suggestions.append("Beim nächsten Mal zuerst Kontakt/Gurt und eine ruhige Sitzposition prüfen.")
    elif mean_amp is not None:
        suggestions.append("Eine kurze Alltagssituation wählen, in der 2–3 Minuten ruhige HRV-Übung möglich sind.")
    else:
        suggestions.append("Beim nächsten Mal etwas länger messen, damit die HRV-Spur genug Daten sammeln kann.")
    if reward_count > 0:
        suggestions.append("Notieren, welche Haltung, Atmung oder Aufmerksamkeit während stabiler Phasen hilfreich war.")
    else:
        suggestions.append("Den nächsten Durchgang als weiteres Beobachten beginnen; der Feedbackkanal bleibt graduell.")
    if duration_s < 360:
        suggestions.append("Für Vergleichbarkeit gelegentlich eine längere Sitzung wählen, wenn es gut in den Alltag passt.")
    else:
        suggestions.append("Für Verlaufsauswertung möglichst ähnliche Sitzungsdauer und ähnlichen Kontext verwenden.")
    return suggestions


def micro_practice_plan(summary: dict[str, Any] | None, changes: dict[str, int] | None = None, focus_key: str | None = None) -> list[str]:
    """Small transfer plan for aftercare.

    The plan stays optional and non-prescriptive. It documents implementation
    intention without presenting HRV as a symptom score.
    """
    summary = summary or {}
    changes = changes or {}
    reward_count = int(summary.get("reward_count") or 0)
    artifact_ratio = float(summary.get("artifact_ratio") or 0.0)
    focus = learning_focus_by_key(focus_key)
    plan = [
        "Heute oder morgen eine 2-Minuten-Situation auswählen: Ampel, Warteschlange, Schreibtischpause oder vor einem Termin.",
        f"Währenddessen einen Anker wählen: {focus.training_anchor}",
    ]
    if reward_count > 0:
        plan.append("Ein Element aus einer stabilen Zielphase wiederholen, ohne den Effekt erzwingen zu wollen.")
    if artifact_ratio > 0.20:
        plan.append("Beim nächsten Gerätetraining zuerst 30 Sekunden Kontaktqualität sammeln, bevor das Feedback bewertet wird.")
    if changes.get("tension", 0) < 0:
        plan.append("Die beobachtete Anspannungsabnahme als mögliche Ressource notieren, ohne sie als Muss zu setzen.")
    return plan


def build_reflection_payload(
    *,
    pre_ratings: dict[str, Any] | None,
    post_ratings: dict[str, Any] | None,
    notes: str,
    summary: dict[str, Any] | None,
    intention: str = "",
    sensor_ready: bool = False,
    focus_key: str | None = None,
    implementation_context: str = "",
) -> dict[str, Any]:
    pre = normalize_ratings(pre_ratings)
    post = normalize_ratings(post_ratings)
    changes = rating_change(pre, post)
    focus = learning_focus_by_key(focus_key)
    return {
        "psychology_model_version": PSYCHOLOGY_MODEL_VERSION,
        "ratings_scale": "0-10, subjektive Selbstbeobachtung, keine Diagnose",
        "rating_labels": RATING_FIELDS,
        "pre_session_ratings": pre,
        "post_session_ratings": post,
        "rating_change": changes,
        "rating_change_text": aftercare_change_summary(pre, post),
        "intention": intention.strip(),
        "learning_focus": asdict(focus),
        "preparation_readiness": preparation_readiness(pre, sensor_ready=sensor_ready),
        "preparation_prompts": preparation_science_prompts(pre, focus.key, sensor_ready=sensor_ready),
        "notes": notes.strip(),
        "transfer_suggestions": aftercare_transfer_suggestions(summary, focus.key),
        "micro_practice_plan": micro_practice_plan(summary, changes, focus.key),
        "implementation_intention": implementation_intention(summary, focus.key, implementation_context),
        "phase_protocol": asdict(phase_protocol()),
        "learning_protocol": asdict(learning_protocol()),
        "science_metadata": science_metadata(),
    }
