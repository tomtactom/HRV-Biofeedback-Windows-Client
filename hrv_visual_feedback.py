"""Visual feedback helpers for the live HRV graph.

These functions modify only the display representation.  Exported RR intervals
and HRV metrics remain raw/algorithmic session data.  The goal is a calmer,
more legible graph for human biofeedback learning.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Iterable, Any

VISUAL_FEEDBACK_VERSION = "0.34-calm-hrv-graph-polish"


@dataclass(frozen=True)
class GraphDisplayRange:
    y_min: float
    y_max: float
    reason: str

    def to_dict(self) -> dict[str, float | str]:
        return asdict(self)


def _finite_values(values: Iterable[Any]) -> list[float]:
    cleaned: list[float] = []
    for item in values:
        try:
            value = float(item)
        except (TypeError, ValueError):
            continue
        if math.isfinite(value):
            cleaned.append(value)
    return cleaned


def smooth_display_series(values: Iterable[Any], *, enabled: bool = True, alpha: float = 0.34) -> list[float]:
    """Return an exponentially smoothed display series.

    Smoothing is intentionally display-only.  It reduces visual jitter in the
    HRV trace while preserving the original values in CSV/JSON exports.  Invalid
    values are dropped so one malformed UI value cannot break the graph.
    """

    raw = _finite_values(values)
    if not raw or not enabled:
        return raw
    alpha = max(0.05, min(1.0, float(alpha)))
    smoothed = [raw[0]]
    for value in raw[1:]:
        smoothed.append((alpha * value) + ((1.0 - alpha) * smoothed[-1]))
    return smoothed


def calm_graph_y_range(
    values: Iterable[Any],
    *,
    previous_y_max: float | None = None,
    min_y_max: float = 3.0,
    padding: float = 0.24,
) -> GraphDisplayRange:
    """Compute a stable y-range for the HRV graph.

    The range expands quickly when amplitude grows, but contracts slowly so the
    graph does not visually jump from moment to moment. Invalid and negative
    display values are ignored/clamped because axis errors would interrupt the
    training room for no physiological benefit.
    """

    data = [max(0.0, v) for v in _finite_values(values)]
    try:
        previous = float(previous_y_max) if previous_y_max is not None else None
    except (TypeError, ValueError):
        previous = None
    if previous is not None and not math.isfinite(previous):
        previous = None

    min_y_max = max(0.5, float(min_y_max or 3.0))
    if not data:
        return GraphDisplayRange(0.0, float(max(min_y_max, previous or min_y_max)), "no_data")

    observed = max(data)
    target = max(float(min_y_max), observed * (1.0 + max(0.0, padding)))
    if previous is None or previous <= 0:
        y_max = target
        reason = "initial_range"
    elif target > previous:
        # Expand promptly so positive amplitude changes remain visible.
        y_max = previous * 0.30 + target * 0.70
        reason = "expanding"
    else:
        # Contract slowly to prevent distracting axis pumping.
        y_max = previous * 0.88 + target * 0.12
        reason = "slow_contract"
    return GraphDisplayRange(0.0, round(float(y_max), 4), reason)


def graph_display_metadata(*, calm_visuals_enabled: bool, pyqtgraph_available: bool) -> dict[str, object]:
    return {
        "visual_feedback_version": VISUAL_FEEDBACK_VERSION,
        "calm_visuals_enabled": bool(calm_visuals_enabled),
        "pyqtgraph_available": bool(pyqtgraph_available),
        "display_only_smoothing": bool(calm_visuals_enabled),
        "invalid_display_values_are_dropped": True,
        "raw_data_export_unchanged": True,
    }
