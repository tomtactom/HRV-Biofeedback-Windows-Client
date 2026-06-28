"""Adaptive and complementary display policy for HRV Biofeedback.

The live training view should not become a dashboard.  This module keeps the
visible channels complementary:

- circle: immediate primary feedback (HRV amplitude)
- graph: temporal context for the same signal
- text: only short orientation or signal repair
- numbers: optional detail layer, automatically shown only when useful

The policy is deliberately conservative and user-overridable.  It does not
change the measurement or reward algorithm; it only decides how much interface
complexity is helpful in the current moment.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from hrv_psychology import training_focus_cue, training_guidance

ADAPTIVE_UI_VERSION = "0.29-complementary-adaptive-display"


@dataclass(frozen=True)
class AdaptiveDisplayPolicy:
    """Display decisions for one UI update."""

    model_version: str
    display_mode: str
    guidance: str
    focus_cue: str
    show_graph: bool
    show_details: bool
    tone: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def complementary_channel_contract() -> dict[str, Any]:
    """Return the intended role of each visible feedback channel.

    This is saved in metadata and tested so later feature additions do not turn
    the training room back into competing graphs, scores and long explanations.
    """

    return {
        "version": ADAPTIVE_UI_VERSION,
        "primary_feedback_channel": "Kreis: unmittelbare HRV-Amplitude",
        "context_channel": "HRV-Spur: zeitlicher Verlauf desselben Signals",
        "orientation_channel": "kurze Hinweise: nur Start, Signalreparatur oder Fokusanker",
        "detail_channel": "Kernzahlen: optional oder bei Signalproblemen sichtbar",
        "non_competition_rule": "Kein zweites sichtbares Zielsignal neben HRV-Amplitude.",
    }


def _is_signal_problem(signal_quality: float, hrv_amplitude: float | None, elapsed_s: float, rr_ready: bool) -> bool:
    if not rr_ready and elapsed_s > 8.0:
        return True
    if hrv_amplitude is None and elapsed_s > 45.0:
        return True
    return signal_quality < 0.55 and elapsed_s > 20.0


def compute_training_display_policy(
    *,
    phase: str,
    signal_quality: float,
    hrv_amplitude: float | None,
    reward_active: bool,
    elapsed_s: float,
    focus_key: str,
    user_details_visible: bool,
    user_graph_visible: bool,
    rr_ready: bool,
) -> AdaptiveDisplayPolicy:
    """Compute the least complex helpful training view.

    Details are hidden in ordinary training to reduce cognitive load. They are
    shown if the user explicitly asks for them or if signal repair information is
    useful.  The graph remains visible as a complementary time-context channel,
    unless the user/focus mode hides it.
    """

    if phase == "paused":
        return AdaptiveDisplayPolicy(
            model_version=ADAPTIVE_UI_VERSION,
            display_mode="paused",
            guidance="Pausiert. Du kannst fortsetzen oder speichern.",
            focus_cue="Pause wahrnehmen; kein Signal bewerten.",
            show_graph=user_graph_visible,
            show_details=user_details_visible,
            tone="warn",
            reason="session_paused",
        )

    if phase not in {"reference", "baseline", "training"}:
        return AdaptiveDisplayPolicy(
            model_version=ADAPTIVE_UI_VERSION,
            display_mode="preparation",
            guidance="Sensor vorbereiten und dann Training starten.",
            focus_cue="Einen kleinen Lernfokus wählen.",
            show_graph=False,
            show_details=False,
            tone="neutral",
            reason="not_training_phase",
        )

    signal_problem = _is_signal_problem(signal_quality, hrv_amplitude, elapsed_s, rr_ready)
    building = hrv_amplitude is None or elapsed_s < 60.0

    if signal_problem:
        return AdaptiveDisplayPolicy(
            model_version=ADAPTIVE_UI_VERSION,
            display_mode="repair",
            guidance="Signal prüfen: Sensor-Kontakt, ruhige Hand und RR-Daten beobachten.",
            focus_cue="Kurz beim Kontakt bleiben; erst danach weitertrainieren.",
            show_graph=user_graph_visible,
            show_details=True,
            tone="warn",
            reason="signal_repair",
        )

    if building:
        return AdaptiveDisplayPolicy(
            model_version=ADAPTIVE_UI_VERSION,
            display_mode="build",
            guidance="Aufbauphase: Die App sammelt RR-Daten für die HRV-Amplitude.",
            focus_cue=training_focus_cue(
                phase=phase,
                signal_quality=signal_quality,
                hrv_amplitude=hrv_amplitude,
                reward_active=reward_active,
                elapsed_s=elapsed_s,
                focus_key=focus_key,
            ),
            show_graph=user_graph_visible,
            show_details=user_details_visible,
            tone="active",
            reason="hrv_window_building",
        )

    # Stable ordinary training: the circle is primary, the graph is context, and
    # numbers stay out of the way unless requested.
    return AdaptiveDisplayPolicy(
        model_version=ADAPTIVE_UI_VERSION,
        display_mode="focus",
        guidance=training_guidance(
            phase=phase,
            signal_quality=signal_quality,
            hrv_amplitude=hrv_amplitude,
            reward_active=reward_active,
            elapsed_s=elapsed_s,
        ),
        focus_cue=training_focus_cue(
            phase=phase,
            signal_quality=signal_quality,
            hrv_amplitude=hrv_amplitude,
            reward_active=reward_active,
            elapsed_s=elapsed_s,
            focus_key=focus_key,
        ),
        show_graph=user_graph_visible,
        show_details=user_details_visible,
        tone="good" if reward_active else "active",
        reason="ordinary_focus_training",
    )
