"""Reusable Qt widgets for HRV Biofeedback.

These components are intentionally presentation-only. Keeping them outside
main.py reduces coupling between the guided training workflow and visual
rendering details.
"""

from __future__ import annotations

from typing import Any
import math

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QBrush
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QSlider, QVBoxLayout, QWidget

from hrv_core import HrvMetrics
from hrv_product_contract import PHASE_LABELS

class Card(QFrame):
    """Simple reusable card surface."""

    def __init__(self, object_name: str = "Card") -> None:
        super().__init__()
        self.setObjectName(object_name)
        self.setFrameShape(QFrame.NoFrame)


class StatusPill(QLabel):
    def __init__(self, text: str = "") -> None:
        super().__init__(text)
        self.setObjectName("StatusPill")
        self.setProperty("tone", "neutral")
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(28)

    def set_tone(self, tone: str, text: str | None = None) -> None:
        self.setProperty("tone", tone)
        if text is not None:
            self.setText(text)
        self.style().unpolish(self)
        self.style().polish(self)


class MetricCard(Card):
    def __init__(self, title: str, value: str = "—", helper: str = "") -> None:
        super().__init__("MetricCard")
        self.setMinimumHeight(94)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("MetricTitle")
        self.title_label.setWordWrap(True)
        self.value_label = QLabel(value)
        self.value_label.setObjectName("MetricValue")
        self.value_label.setWordWrap(True)
        self.value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.helper_label = QLabel(helper)
        self.helper_label.setObjectName("MetricHelper")
        self.helper_label.setWordWrap(True)
        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.helper_label)

    def set_value(self, value: str, helper: str | None = None) -> None:
        self.value_label.setText(value)
        if helper is not None:
            self.helper_label.setText(helper)


class RatingScale(Card):
    """Compact 0-10 self-observation scale used before and after training."""

    def __init__(self, title: str, low_label: str, high_label: str, default: int = 5) -> None:
        super().__init__("RatingScale")
        self.setMinimumHeight(84)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        header = QHBoxLayout()
        self.title_label = QLabel(title)
        self.title_label.setObjectName("RatingTitle")
        self.value_label = QLabel(str(default))
        self.value_label.setObjectName("RatingValue")
        self.value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        header.addWidget(self.title_label, 1)
        header.addWidget(self.value_label)
        layout.addLayout(header)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(10)
        self.slider.setValue(default)
        self.slider.setTickInterval(1)
        self.slider.setTickPosition(QSlider.TicksBelow)
        self.slider.valueChanged.connect(lambda value: self.value_label.setText(str(value)))
        layout.addWidget(self.slider)

        footer = QLabel(f"{low_label}  ·  {high_label}")
        footer.setObjectName("RatingHelper")
        footer.setWordWrap(True)
        layout.addWidget(footer)

    def value(self) -> int:
        return int(self.slider.value())

    def set_value(self, value: int) -> None:
        self.slider.setValue(max(0, min(10, int(value))))


class WorkflowStep(Card):
    """Compact clinical workflow indicator for onboarding and everyday use."""

    def __init__(self, number: str, title: str, helper: str) -> None:
        super().__init__("WorkflowStep")
        self.setProperty("tone", "neutral")
        self.setMinimumHeight(66)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        self.number_label = QLabel(number)
        self.number_label.setObjectName("StepNumber")
        self.number_label.setAlignment(Qt.AlignCenter)
        self.number_label.setFixedSize(28, 28)
        layout.addWidget(self.number_label)

        text_box = QVBoxLayout()
        text_box.setContentsMargins(0, 0, 0, 0)
        text_box.setSpacing(2)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("StepTitle")
        self.helper_label = QLabel(helper)
        self.helper_label.setObjectName("StepHelper")
        self.helper_label.setWordWrap(True)
        text_box.addWidget(self.title_label)
        text_box.addWidget(self.helper_label)
        layout.addLayout(text_box, 1)

    def set_state(self, tone: str, helper: str | None = None) -> None:
        self.setProperty("tone", tone)
        if helper is not None:
            self.helper_label.setText(helper)
        self.style().unpolish(self)
        self.style().polish(self)


class RoleCard(Card):
    """A labeled panel used by the redesigned dashboard command area."""

    def __init__(self, title: str, subtitle: str = "") -> None:
        super().__init__("RoleCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(14, 14, 14, 14)
        self.layout.setSpacing(10)
        title_row = QVBoxLayout()
        title_row.setSpacing(2)
        title_label = QLabel(title)
        title_label.setObjectName("PanelTitle")
        title_row.addWidget(title_label)
        if subtitle:
            subtitle_label = QLabel(subtitle)
            subtitle_label.setObjectName("HintLabel")
            subtitle_label.setWordWrap(True)
            title_row.addWidget(subtitle_label)
        self.layout.addLayout(title_row)


def _finite_float(value: Any, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    return numeric if math.isfinite(numeric) else default


def _clamp(value: Any, low: float = 0.0, high: float = 1.0) -> float:
    numeric = _finite_float(value, low)
    return max(low, min(high, numeric))


class FeedbackCircle(QWidget):
    """Large calm visual feedback widget.

    The circle size follows normalized HRV amplitude. A soft glow indicates a
    stable target phase; a muted gray state indicates signal uncertainty.
    """

    def __init__(self) -> None:
        super().__init__()
        self.feedback_value = 0.0
        self.threshold = 0.52
        self.hrv_amplitude_60s: float | None = None
        self.reward_active = False
        self.reward_count = 0
        self.signal_quality = 0.0
        self.phase = "idle"
        self.feedback_mode = "green_circle"
        self.setMinimumSize(440, 340)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_state(self, metrics: HrvMetrics) -> None:
        self.feedback_value = _clamp(metrics.circle_radius)
        self.threshold = _clamp(metrics.adaptive_threshold)
        amp = metrics.hrv_amplitude_60s
        self.hrv_amplitude_60s = _finite_float(amp) if amp is not None else None
        self.reward_active = bool(metrics.reward_active)
        try:
            self.reward_count = max(0, int(metrics.reward_count))
        except (TypeError, ValueError):
            self.reward_count = 0
        self.signal_quality = _clamp(metrics.signal_quality)
        self.phase = str(metrics.phase or "idle")
        self.feedback_mode = str(metrics.feedback_mode or "green_circle")
        self.update()

    def paintEvent(self, _event: Any) -> None:  # noqa: D401 - Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()
        painter.fillRect(rect, self.palette().window())

        w, h = rect.width(), rect.height()
        center_x, center_y = w / 2, h / 2 - 8
        scale = max(1.0, float(min(w, h)))
        base = scale * 0.15
        radius = max(2.0, base + _clamp(self.feedback_value) * scale * 0.27)

        text_color = self.palette().text().color()
        muted = QColor(text_color)
        muted.setAlpha(140)

        # Ambient guide rings: quiet orientation without a hard target feel.
        painter.setBrush(Qt.NoBrush)
        for factor, alpha in [(0.42, 35), (0.58, 26), (0.74, 20)]:
            guide = scale * factor / 2
            ring = QColor(120, 140, 155, alpha)
            painter.setPen(QPen(ring, 1))
            painter.drawEllipse(QRectF(center_x - guide, center_y - guide, guide * 2, guide * 2))

        signal_ok = self.signal_quality >= 0.65 or self.phase in {"idle", "reference", "baseline"}
        if self.phase == "idle":
            circle_color = QColor(86, 145, 107, 120)
            outline_color = QColor(70, 120, 90, 120)
        elif not signal_ok:
            circle_color = QColor(132, 137, 142, 135)
            outline_color = QColor(110, 115, 120, 160)
        else:
            circle_color = QColor(28, 190, 92, 205)
            outline_color = QColor(22, 110, 58, 220)

        if self.reward_active:
            glow_radius = radius * 1.26
            painter.setBrush(QBrush(QColor(28, 190, 92, 58)))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QRectF(center_x - glow_radius, center_y - glow_radius, glow_radius * 2, glow_radius * 2))

        painter.setBrush(QBrush(circle_color))
        painter.setPen(QPen(outline_color, 2.2))
        painter.drawEllipse(QRectF(center_x - radius, center_y - radius, radius * 2, radius * 2))

        painter.setPen(text_color)
        phase_text = PHASE_LABELS.get(self.phase, self.phase)
        painter.drawText(rect.adjusted(0, 18, 0, -h + 54), Qt.AlignCenter, phase_text)
        painter.setPen(muted)
        state_text = "stabile Zielphase" if self.reward_active else "beobachtende Rückmeldung"
        if not signal_ok and self.phase not in {"idle", "reference", "baseline"}:
            state_text = "Signal prüfen"
        amp_text = "HRV-Amplitude sammelt sich" if self.hrv_amplitude_60s is None else f"HRV-Amplitude {self.hrv_amplitude_60s:.1f} BPM"
        painter.drawText(rect.adjusted(0, h - 72, 0, -42), Qt.AlignCenter, f"{amp_text} · {state_text}")
        painter.drawText(rect.adjusted(0, h - 42, 0, -14), Qt.AlignCenter, f"Stabile Phasen {self.reward_count}")


