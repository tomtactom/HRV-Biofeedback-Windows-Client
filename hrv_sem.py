"""
SEM-inspired latent scoring utilities for HRV Biofeedback.

This module provides a lightweight, dependency-free layer that translates
manifest live HRV indicators into theory-guided latent constructs. It is not a
replacement for a full confirmatory SEM fit on a sufficiently large independent
sample. It gives the application:

- real-time latent construct scores for feedback/documentation;
- an auditable SEM-style model specification;
- per-segment SEM-ready export tables;
- simple standardized path estimates for single-session documentation.

The design follows a cautious "SEM-informed measurement layer" approach:
latent scores are composites with explicit loadings/weights, and inferential
SEM fitting is intentionally left as an offline/optional analysis step.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional
import csv
import math
import tempfile
import os

import numpy as np


SEM_MODEL_VERSION = "sem_lite_neurovisceral_v1"

# lavaan/semopy-style syntax for documentation and future offline fitting.
SEM_MODEL_SYNTAX = """
# Measurement model
AutonomicFlexibility =~ hrv_amplitude_60s + rmssd_30s + sdnn_60s + coherence_90s + regularity_20s
MeasurementQuality =~ signal_quality + rr_valid_numeric
TrainingResponse =~ hrv_score + reward_active_numeric + circle_radius
IntegratedSelfRegulation =~ AutonomicFlexibility + MeasurementQuality + TrainingResponse

# Structural model
TrainingResponse ~ AutonomicFlexibility + MeasurementQuality
IntegratedSelfRegulation ~ AutonomicFlexibility + MeasurementQuality + TrainingResponse
""".strip()

SEM_CONSTRUCTS: dict[str, dict[str, Any]] = {
    "autonomic_flexibility": {
        "label": "Autonomic Flexibility",
        "description": "Latent composite of amplitude, RMSSD, SDNN, rhythm coherence and HR-curve regularity.",
        "indicators": {
            "hrv_amplitude_60s_ratio": 0.35,
            "rmssd_30s_ratio": 0.25,
            "sdnn_60s_ratio": 0.15,
            "coherence_90s_ratio": 0.15,
            "regularity_20s": 0.10,
        },
    },
    "measurement_quality": {
        "label": "Measurement Quality",
        "description": "Latent composite of usable signal quality and current RR validity.",
        "indicators": {
            "signal_quality": 0.80,
            "rr_valid_numeric": 0.20,
        },
    },
    "training_response": {
        "label": "Training Response",
        "description": "Latent composite of HRV score, visual feedback intensity and reward state.",
        "indicators": {
            "hrv_score": 0.55,
            "circle_radius": 0.25,
            "reward_active_numeric": 0.20,
        },
    },
    "integrated_self_regulation": {
        "label": "Integrated Self-Regulation",
        "description": "Theory-guided higher-order composite joining physiological flexibility, measurement quality and training response.",
        "indicators": {
            "autonomic_flexibility": 0.55,
            "measurement_quality": 0.20,
            "training_response": 0.25,
        },
    },
}


def _finite(value: Any) -> Optional[float]:
    try:
        x = float(value)
        if math.isfinite(x):
            return x
    except Exception:
        pass
    return None


def _bounded_ratio_score(value: Any, reference: float, *, neutral: float = 0.5) -> float:
    """Map value/reference onto 0..1 with 0.5 at the reference value.

    This gives a stable real-time transformation without relying on population
    norms. Doubling relative to baseline moves the score upward smoothly; values
    below baseline move it downward. Missing values become neutral.
    """
    x = _finite(value)
    if x is None or reference <= 1e-9:
        return neutral
    ratio = max(x / reference, 1e-6)
    z = math.log(ratio) * 1.35
    return float(np.clip(1.0 / (1.0 + math.exp(-z)), 0.0, 1.0))


def _bounded_unit(value: Any, *, neutral: float = 0.5) -> float:
    x = _finite(value)
    if x is None:
        return neutral
    return float(np.clip(x, 0.0, 1.0))


def _weighted_mean(items: Iterable[tuple[float, float]]) -> float:
    pairs = [(float(w), float(v)) for w, v in items if math.isfinite(float(w)) and math.isfinite(float(v))]
    denom = sum(abs(w) for w, _ in pairs)
    if denom <= 1e-12:
        return 0.0
    return float(np.clip(sum(w * v for w, v in pairs) / denom, 0.0, 1.0))


@dataclass
class SemReference:
    amplitude_bpm: float = 8.0
    rmssd_ms: float = 35.0
    sdnn_ms: float = 42.0
    coherence: float = 0.30


def compute_sem_latents(
    *,
    hrv_amplitude_60s: float | None,
    rmssd_30s: float | None,
    sdnn_60s: float | None,
    regularity_20s: float | None,
    coherence_90s: float | None,
    signal_quality: float,
    rr_valid: bool,
    hrv_score: float,
    circle_radius: float = 0.0,
    reward_active: bool = False,
    reference: SemReference | None = None,
) -> dict[str, float]:
    """Return SEM-style latent scores in 0..1.

    The indicators are intentionally transparent and bounded. This supports live
    feedback while preserving an explicit bridge to a later offline SEM model.
    """
    ref = reference or SemReference()

    amp = _bounded_ratio_score(hrv_amplitude_60s, max(ref.amplitude_bpm, 1.0))
    rmssd = _bounded_ratio_score(rmssd_30s, max(ref.rmssd_ms, 5.0))
    sdnn = _bounded_ratio_score(sdnn_60s, max(ref.sdnn_ms, 5.0))
    coherence = _bounded_ratio_score(coherence_90s, max(ref.coherence, 0.15))
    regularity = _bounded_unit(regularity_20s)
    quality = _bounded_unit(signal_quality, neutral=0.0)
    rr_valid_numeric = 1.0 if rr_valid else 0.0
    reward_numeric = 1.0 if reward_active else 0.0

    autonomic = _weighted_mean(
        [
            (0.35, amp),
            (0.25, rmssd),
            (0.15, sdnn),
            (0.15, coherence),
            (0.10, regularity),
        ]
    )
    measurement = _weighted_mean([(0.80, quality), (0.20, rr_valid_numeric)])
    training = _weighted_mean(
        [
            (0.55, _bounded_unit(hrv_score, neutral=0.0)),
            (0.25, _bounded_unit(circle_radius, neutral=0.0)),
            (0.20, reward_numeric),
        ]
    )
    integrated = _weighted_mean([(0.55, autonomic), (0.20, measurement), (0.25, training)])

    return {
        "sem_autonomic_flexibility": autonomic,
        "sem_measurement_quality": measurement,
        "sem_training_response": training,
        "sem_integrated_self_regulation": integrated,
    }



SEM_LIVE_NOTE = (
    "Live SEM use is implemented as an adaptive, SEM-informed control layer. "
    "It stabilizes feedback from theory-guided latent composites and measurement quality; "
    "it does not estimate a confirmatory structural equation model during a single session."
)


def compute_sem_live_feedback(
    *,
    autonomic_flexibility: float | None,
    measurement_quality: float | None,
    hrv_score: float,
    phase: str,
    training_response: float | None = None,
) -> dict[str, Any]:
    """Compute an SEM-informed live-control state.

    Live HRVB has too few independent observations for valid confirmatory SEM fitting.
    This function therefore uses the explicit measurement/structural model as a
    *control model*: measurement quality gates the signal, autonomic flexibility
    stabilizes the target, and a residual/alignment indicator documents whether
    observed training response is congruent with the model-implied response.
    """
    af = _bounded_unit(autonomic_flexibility, neutral=0.5)
    mq = _bounded_unit(measurement_quality, neutral=0.0)
    raw = _bounded_unit(hrv_score, neutral=0.0)

    # Model-implied training response from the structural part of the lite model.
    expected_training = float(np.clip(0.72 * af + 0.28 * mq, 0.0, 1.0))
    observed_training = _bounded_unit(training_response, neutral=raw) if training_response is not None else raw
    latent_alignment = float(np.clip(1.0 - abs(observed_training - expected_training), 0.0, 1.0))

    # Measurement quality is a prerequisite for using latent values in live feedback.
    # Below about .35 the app should observe but not amplify feedback.
    quality_gate = float(np.clip((mq - 0.35) / 0.65, 0.0, 1.0))
    phase_gate = 1.0 if phase == "training" else 0.0
    live_confidence = float(np.clip(mq * (0.65 + 0.35 * latent_alignment), 0.0, 1.0))

    # The feedback target remains primarily the direct HRV score. SEM contributes
    # as a stabilizer, not as a diagnostic or normative score.
    blended = 0.72 * raw + 0.28 * expected_training
    feedback_target = float(np.clip(blended * quality_gate * phase_gate, 0.0, 1.0))

    if phase != "training":
        gate_reason = "not_training_phase"
    elif mq < 0.35:
        gate_reason = "low_measurement_quality"
    elif latent_alignment < 0.45:
        gate_reason = "latent_mismatch_observe"
    else:
        gate_reason = "sem_live_ok"

    return {
        "sem_expected_training_response": expected_training,
        "sem_latent_alignment": latent_alignment,
        "sem_live_confidence": live_confidence,
        "sem_feedback_target": feedback_target,
        "sem_gate_reason": gate_reason,
    }


def sem_model_info() -> dict[str, Any]:
    return {
        "model_version": SEM_MODEL_VERSION,
        "model_syntax": SEM_MODEL_SYNTAX,
        "constructs": SEM_CONSTRUCTS,
        "real_time_method": "theory_guided_reflective_composite_scores_0_to_1",
        "live_feedback_method": SEM_LIVE_NOTE,
        "interpretation_note": (
            "These values are SEM-inspired latent scores for feedback and documentation. "
            "They are not a diagnostic classification and are not confirmatory SEM fit statistics. "
            "For formal SEM, aggregate multi-session data should be analyzed offline with a package such as semopy/lavaan."
        ),
    }


def _mean(values: list[float]) -> float | None:
    arr = np.asarray([v for v in values if math.isfinite(v)], dtype=float)
    if arr.size == 0:
        return None
    return float(np.mean(arr))


def _rate(values: list[bool]) -> float | None:
    if not values:
        return None
    return float(sum(1 for v in values if v) / len(values))


def rows_to_sem_segments(rows: list[Any], segment_s: float = 60.0) -> list[dict[str, Any]]:
    """Aggregate HrvMetrics-like rows into SEM-ready time segments."""
    if not rows:
        return []

    groups: dict[int, list[Any]] = {}
    for row in rows:
        elapsed = _finite(getattr(row, "elapsed_s", None))
        if elapsed is None:
            continue
        bucket = int(elapsed // segment_s)
        groups.setdefault(bucket, []).append(row)

    segments: list[dict[str, Any]] = []
    for bucket in sorted(groups):
        grp = groups[bucket]
        if not grp:
            continue
        valid_flags = [bool(getattr(r, "rr_valid", False)) for r in grp]
        reward_flags = [bool(getattr(r, "reward_active", False)) for r in grp]
        phase_values = sorted({str(getattr(r, "phase", "")) for r in grp if getattr(r, "phase", "")})
        segment = {
            "segment_index": bucket,
            "segment_start_s": bucket * segment_s,
            "segment_end_s": (bucket + 1) * segment_s,
            "n_rows": len(grp),
            "phases": ";".join(phase_values),
            "valid_rr_rate": _rate(valid_flags),
            "reward_rate": _rate(reward_flags),
            "mean_bpm": _mean([v for r in grp if (v := _finite(getattr(r, "bpm", None))) is not None]),
            "mean_rmssd_30s": _mean([v for r in grp if (v := _finite(getattr(r, "rmssd_30s", None))) is not None]),
            "mean_sdnn_60s": _mean([v for r in grp if (v := _finite(getattr(r, "sdnn_60s", None))) is not None]),
            "mean_hrv_amplitude_60s": _mean([v for r in grp if (v := _finite(getattr(r, "hrv_amplitude_60s", None))) is not None]),
            "mean_regularity_20s": _mean([v for r in grp if (v := _finite(getattr(r, "regularity_20s", None))) is not None]),
            "mean_coherence_90s": _mean([v for r in grp if (v := _finite(getattr(r, "coherence_90s", None))) is not None]),
            "mean_signal_quality": _mean([v for r in grp if (v := _finite(getattr(r, "signal_quality", None))) is not None]),
            "mean_hrv_score": _mean([v for r in grp if (v := _finite(getattr(r, "hrv_score", None))) is not None]),
            "mean_circle_radius": _mean([v for r in grp if (v := _finite(getattr(r, "circle_radius", None))) is not None]),
            "mean_sem_autonomic_flexibility": _mean([v for r in grp if (v := _finite(getattr(r, "sem_autonomic_flexibility", None))) is not None]),
            "mean_sem_measurement_quality": _mean([v for r in grp if (v := _finite(getattr(r, "sem_measurement_quality", None))) is not None]),
            "mean_sem_training_response": _mean([v for r in grp if (v := _finite(getattr(r, "sem_training_response", None))) is not None]),
            "mean_sem_integrated_self_regulation": _mean([v for r in grp if (v := _finite(getattr(r, "sem_integrated_self_regulation", None))) is not None]),
            "mean_sem_expected_training_response": _mean([v for r in grp if (v := _finite(getattr(r, "sem_expected_training_response", None))) is not None]),
            "mean_sem_latent_alignment": _mean([v for r in grp if (v := _finite(getattr(r, "sem_latent_alignment", None))) is not None]),
            "mean_sem_live_confidence": _mean([v for r in grp if (v := _finite(getattr(r, "sem_live_confidence", None))) is not None]),
            "mean_sem_feedback_target": _mean([v for r in grp if (v := _finite(getattr(r, "sem_feedback_target", None))) is not None]),
        }
        segments.append(segment)
    return segments


def estimate_sem_paths_from_segments(segments: list[dict[str, Any]]) -> dict[str, Any]:
    """Estimate simple standardized paths between latent segment scores.

    This is a descriptive within-session path summary, not a formal SEM test.
    It is useful for documentation and for checking whether later offline models
    have enough usable segment-level observations.
    """
    cols = [
        "mean_sem_autonomic_flexibility",
        "mean_sem_measurement_quality",
        "mean_sem_training_response",
        "mean_sem_integrated_self_regulation",
    ]
    data = []
    for seg in segments:
        row = [_finite(seg.get(c)) for c in cols]
        if all(v is not None for v in row):
            data.append([float(v) for v in row])
    if len(data) < 4:
        return {
            "method": "standardized_ols_on_sem_segments",
            "n_segments": len(data),
            "status": "insufficient_segments_for_path_summary",
            "minimum_recommended_segments": 4,
        }

    arr = np.asarray(data, dtype=float)
    # Standardize columns; protect against constant columns.
    mu = np.mean(arr, axis=0)
    sd = np.std(arr, axis=0, ddof=1)
    sd[sd < 1e-9] = 1.0
    z = (arr - mu) / sd
    af = z[:, 0]
    mq = z[:, 1]
    tr = z[:, 2]
    isr = z[:, 3]

    def fit(y: np.ndarray, xs: list[np.ndarray], names: list[str]) -> dict[str, Any]:
        X = np.column_stack([np.ones_like(y)] + xs)
        try:
            beta, *_ = np.linalg.lstsq(X, y, rcond=None)
            pred = X @ beta
            ss_res = float(np.sum((y - pred) ** 2))
            ss_tot = float(np.sum((y - np.mean(y)) ** 2))
            r2 = 1.0 - ss_res / ss_tot if ss_tot > 1e-12 else None
            return {
                "standardized_coefficients": {name: float(beta[i + 1]) for i, name in enumerate(names)},
                "intercept": float(beta[0]),
                "r_squared": r2,
            }
        except Exception as exc:
            return {"error": f"{type(exc).__name__}: {exc}"}

    return {
        "method": "standardized_ols_on_sem_segments",
        "n_segments": len(data),
        "status": "descriptive_path_summary_available",
        "paths": {
            "TrainingResponse ~ AutonomicFlexibility + MeasurementQuality": fit(
                tr,
                [af, mq],
                ["AutonomicFlexibility", "MeasurementQuality"],
            ),
            "IntegratedSelfRegulation ~ AutonomicFlexibility + MeasurementQuality + TrainingResponse": fit(
                isr,
                [af, mq, tr],
                ["AutonomicFlexibility", "MeasurementQuality", "TrainingResponse"],
            ),
        },
        "caution": "Single-session time segments are autocorrelated; use this as descriptive documentation, not causal inference.",
    }


def write_sem_segments_csv(path: Path, segments: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "segment_index",
        "segment_start_s",
        "segment_end_s",
        "n_rows",
        "phases",
        "valid_rr_rate",
        "reward_rate",
        "mean_bpm",
        "mean_rmssd_30s",
        "mean_sdnn_60s",
        "mean_hrv_amplitude_60s",
        "mean_regularity_20s",
        "mean_coherence_90s",
        "mean_signal_quality",
        "mean_hrv_score",
        "mean_circle_radius",
        "mean_sem_autonomic_flexibility",
        "mean_sem_measurement_quality",
        "mean_sem_training_response",
        "mean_sem_integrated_self_regulation",
        "mean_sem_expected_training_response",
        "mean_sem_latent_alignment",
        "mean_sem_live_confidence",
        "mean_sem_feedback_target",
    ]
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            for seg in segments:
                writer.writerow({k: seg.get(k) for k in fieldnames})
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except Exception:
                pass
        tmp_path.replace(path)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise
