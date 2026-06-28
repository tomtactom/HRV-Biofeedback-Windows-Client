"""Double-loop learning helpers for HRV Biofeedback.

This module separates adaptive protocol reflection from the live feedback
algorithm.  The app keeps the immediate training signal simple (HRV amplitude)
and uses these helpers for preparation, aftercare and documentation.

The functions are deliberately conservative: they do not diagnose, rank people
or infer stable traits.  They question the current session assumptions from the
available evidence and return small, reversible protocol suggestions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
from typing import Any


ADAPTATION_MODEL_VERSION = "0.25-double-loop-learning"


@dataclass(frozen=True)
class AdaptiveSuggestion:
    """One small protocol suggestion with an explicit rationale."""

    title: str
    rationale: str
    action: str
    priority: str = "normal"


@dataclass(frozen=True)
class DoubleLoopReview:
    """A lightweight session review that questions protocol assumptions."""

    model_version: str
    assumption_status: dict[str, str]
    suggestions: list[AdaptiveSuggestion]
    next_session_plan: dict[str, Any]
    safety_boundary: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["suggestions"] = [asdict(item) for item in self.suggestions]
        return data


def _float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        if math.isfinite(out):
            return out
    except Exception:
        pass
    return default


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(round(float(value)))
    except Exception:
        return default


def _ratings_delta(pre: dict[str, Any] | None, post: dict[str, Any] | None) -> dict[str, int]:
    pre = pre or {}
    post = post or {}
    keys = {"tension", "focus", "energy", "body_contact"}
    return {key: _int(post.get(key), _int(pre.get(key), 5)) - _int(pre.get(key), 5) for key in keys}


def _first_suggestion_text(review: DoubleLoopReview) -> str:
    if not review.suggestions:
        return "Heute mit dem Standardprotokoll beginnen: Sensor prüfen, Baseline sammeln, HRV-Amplitude beobachten."
    item = review.suggestions[0]
    return f"{item.title}: {item.action}"


def evaluate_double_loop(
    *,
    summary: dict[str, Any] | None,
    pre_ratings: dict[str, Any] | None = None,
    post_ratings: dict[str, Any] | None = None,
    focus_key: str | None = None,
) -> DoubleLoopReview:
    """Evaluate whether the current training assumptions still fit.

    This is double-loop learning in a pragmatic software sense: instead of only
    adjusting thresholds, the app questions whether the chosen protocol path,
    measurement quality and transfer framing are currently useful enough.
    """

    summary = summary or {}
    artifact_ratio = _float(summary.get("artifact_ratio"), 0.0)
    valid_rr_count = _int(summary.get("valid_rr_count"), 0)
    row_count = _int(summary.get("row_count"), 0)
    reward_count = _int(summary.get("reward_count"), 0)
    duration_s = _float(summary.get("duration_s"), 0.0)
    mean_amp = summary.get("mean_hrv_amplitude_60s")
    mean_score = summary.get("mean_score")
    deltas = _ratings_delta(pre_ratings, post_ratings)

    assumption_status: dict[str, str] = {}
    suggestions: list[AdaptiveSuggestion] = []

    if row_count == 0 or valid_rr_count == 0:
        assumption_status["measurement_first"] = "RR-Datenbasis fehlt; Trainingseffekte sollten noch nicht interpretiert werden."
        suggestions.append(AdaptiveSuggestion(
            title="Signal zuerst stabilisieren",
            rationale="Ohne gültige RR-Intervalle kann HRV-Amplitude nicht belastbar rückgemeldet werden.",
            action="Vor dem nächsten Training 30–60 Sekunden nur RR-Signal prüfen; bei Bedarf Sensorposition und andere Apps prüfen.",
            priority="high",
        ))
    elif artifact_ratio > 0.20:
        assumption_status["measurement_first"] = "Messqualität ist der begrenzende Faktor."
        suggestions.append(AdaptiveSuggestion(
            title="Kontaktphase verlängern",
            rationale="Ein hoher Artefaktanteil kann Rückmeldung unruhig machen und Lernmomente verwischen.",
            action="Vor dem Feedback eine kurze Kontaktphase nutzen und erst starten, wenn RR aktiv und stabil angezeigt wird.",
            priority="high",
        ))
    else:
        assumption_status["measurement_first"] = "RR-Signal wirkt für Training ausreichend beobachtbar."

    if mean_amp is None:
        assumption_status["amplitude_first"] = "HRV-Amplitude konnte noch nicht ausreichend aufgebaut werden."
        suggestions.append(AdaptiveSuggestion(
            title="Aufbauzeit erlauben",
            rationale="Die HRV-Spur braucht genug echte RR-Daten im 60-Sekunden-Fenster.",
            action="Eine Baseline oder die erste Trainingsminute nur als Aufbauphase betrachten.",
        ))
    elif _float(mean_amp, 0.0) < 3.0 and duration_s >= 360:
        assumption_status["amplitude_first"] = "Amplitude bleibt niedrig; das Protokoll sollte die Lernbedingungen sanft anpassen."
        suggestions.append(AdaptiveSuggestion(
            title="Rückmeldung etwas sensitiver machen",
            rationale="Bei geringer Amplitude können sehr kleine Änderungen sichtbar gemacht werden, ohne Normwerte zu setzen.",
            action="Für die nächste Sitzung Baseline beibehalten und auf kleine Kreisveränderungen achten; Schwelle nicht manuell erhöhen.",
        ))
    else:
        assumption_status["amplitude_first"] = "HRV-Amplitude bleibt als primäres Feedbacksignal passend."

    if reward_count == 0 and row_count > 60 and artifact_ratio <= 0.20:
        assumption_status["reinforcement"] = "Belohnungsereignisse waren selten; die Kontingenz könnte zu streng sein."
        suggestions.append(AdaptiveSuggestion(
            title="Kleine Fortschritte deutlicher sichtbar machen",
            rationale="Positive operante Rückmeldung sollte erreichbar bleiben, damit Verhalten und Konsequenz zeitlich gekoppelt sind.",
            action="Nächste Sitzung mit Baseline starten und stabile kleine Kreisveränderungen als Lernsignal nutzen.",
        ))
    elif reward_count > 0:
        assumption_status["reinforcement"] = "Stabile Zielphasen wurden beobachtet und können als Lernspur genutzt werden."
    else:
        assumption_status["reinforcement"] = "Noch zu wenig Trainingsdaten für eine Kontingenzbewertung."

    if post_ratings:
        if deltas.get("tension", 0) > 2:
            suggestions.append(AdaptiveSuggestion(
                title="Aktivierung nach der Sitzung beachten",
                rationale="Die subjektive Anspannung lag nach der Sitzung höher als vorher.",
                action="Beim nächsten Mal kürzer starten oder zuerst Referenz/Beobachtung wählen.",
            ))
        if deltas.get("focus", 0) < -2:
            suggestions.append(AdaptiveSuggestion(
                title="Kognitive Last senken",
                rationale="Fokus wurde nach der Sitzung niedriger angegeben.",
                action="Im Training nur Kreis und HRV-Spur beachten; optionale Werte ausblenden oder Fokusmodus nutzen.",
            ))
        if deltas.get("body_contact", 0) > 0:
            assumption_status["interoceptive_learning"] = "Körperkontakt wurde stärker beobachtet; der Lernfokus kann beibehalten werden."
        else:
            assumption_status.setdefault("interoceptive_learning", "Körperkontakt bleibt optionaler Lernanker.")
    else:
        assumption_status["subjective_loop"] = "Nachher-Selbstcheck offen; Reflexion kann die nächste Empfehlung verfeinern."

    suggested_baseline = True
    if artifact_ratio <= 0.08 and valid_rr_count > 120 and mean_amp is not None and reward_count > 0:
        suggested_baseline = False

    next_session_plan = {
        "suggested_baseline": suggested_baseline,
        "suggested_start": "training_with_baseline" if suggested_baseline else "training_or_skip_baseline",
        "suggested_duration_s": 600 if duration_s >= 360 else 360,
        "suggested_focus_key": focus_key or "observe_contact",
        "primary_next_step": "sensor_rr_check" if valid_rr_count == 0 or artifact_ratio > 0.20 else "training",
        "compass_text": None,
    }

    review = DoubleLoopReview(
        model_version=ADAPTATION_MODEL_VERSION,
        assumption_status=assumption_status,
        suggestions=suggestions[:5],
        next_session_plan=next_session_plan,
        safety_boundary=(
            "Diese Lernschleife passt Protokollhinweise an. Sie ersetzt keine medizinische Bewertung "
            "und interpretiert HRV nicht als Persönlichkeits- oder Symptomurteil."
        ),
    )
    review.next_session_plan["compass_text"] = _first_suggestion_text(review)
    return review


def current_preparation_compass(
    ratings: dict[str, Any] | None,
    *,
    sensor_ready: bool,
    recent_review: dict[str, Any] | None = None,
    focus_key: str | None = None,
) -> str:
    """Return a short preparation message for the UI."""
    ratings = ratings or {}
    tension = _int(ratings.get("tension"), 5)
    focus = _int(ratings.get("focus"), 5)
    body_contact = _int(ratings.get("body_contact"), 5)
    lines: list[str] = []
    if recent_review:
        plan = recent_review.get("next_session_plan", {}) if isinstance(recent_review, dict) else {}
        compass = plan.get("compass_text")
        if compass:
            lines.append(f"Letzte Lernschleife: {compass}")
    if not sensor_ready:
        lines.append("Heute zuerst Sensor verbinden und RR aktiv prüfen.")
    elif body_contact <= 3:
        lines.append("Sensor ist bereit; vor dem Start kurz Körperkontakt und Sitzposition sammeln.")
    elif tension >= 8:
        lines.append("Start mit Beobachtung oder Baseline passt bei hoher Aktivierung oft ruhiger.")
    elif focus <= 3:
        lines.append("Ein einzelner Anker kann reichen: grüner Kreis und HRV-Spur.")
    else:
        lines.append("Startbedingungen wirken übersichtlich: Training mit Baseline oder bewusster Baseline-Übersprung ist möglich.")
    lines.append("Lernschleife: Die App passt Hinweise aus Messqualität, Lernfokus und Reflexion an, ohne dich zu bewerten.")
    return "\n".join(f"• {line}" for line in lines)


def load_recent_double_loop_review(sessions_dir: Path, limit: int = 12) -> dict[str, Any] | None:
    """Load the most recent stored double-loop review from reflection/metadata files."""
    try:
        candidates = sorted(
            list(Path(sessions_dir).glob("*.reflection.json")) + list(Path(sessions_dir).glob("*.metadata.json")),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )[: max(1, limit)]
    except Exception:
        return None

    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for key in ("double_loop_learning", "protocol_adaptation", "adaptive_learning_review"):
            value = data.get(key) if isinstance(data, dict) else None
            if isinstance(value, dict) and value.get("model_version"):
                return value
    return None


def format_double_loop_review(review: DoubleLoopReview | dict[str, Any] | None) -> str:
    """Format a concise, user-facing review text."""
    if review is None:
        return "Noch keine Lernschleife vorhanden. Nach der ersten gespeicherten Sitzung erscheinen hier angepasste Hinweise."
    data = review.to_dict() if isinstance(review, DoubleLoopReview) else review
    lines = ["Lernschleife:"]
    assumptions = data.get("assumption_status", {}) or {}
    for label, value in assumptions.items():
        readable = str(label).replace("_", " ")
        lines.append(f"• {readable}: {value}")
    suggestions = data.get("suggestions", []) or []
    if suggestions:
        lines.append("")
        lines.append("Nächste kleine Anpassungen:")
        for suggestion in suggestions[:3]:
            if isinstance(suggestion, dict):
                lines.append(f"• {suggestion.get('title', 'Hinweis')}: {suggestion.get('action', '')}")
    plan = data.get("next_session_plan", {}) or {}
    if plan.get("compass_text"):
        lines.append("")
        lines.append(f"Kompass: {plan['compass_text']}")
    return "\n".join(lines)
