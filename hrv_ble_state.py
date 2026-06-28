"""Small BLE state machine for separating connection from usable RR streaming."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from time import monotonic
from typing import Any


class BleConnectionState(str, Enum):
    IDLE = "idle"
    SCANNING = "scanning"
    CANDIDATE_FOUND = "candidate_found"
    CONNECTING = "connecting"
    DISCOVERING_SERVICES = "discovering_services"
    WAITING_FOR_RR = "waiting_for_rr"
    STREAMING = "streaming"
    RECOVERING = "recovering"
    FAILED = "failed"
    DISCONNECTED = "disconnected"


@dataclass
class BleStateSnapshot:
    state: BleConnectionState = BleConnectionState.IDLE
    since_s: float = field(default_factory=monotonic)
    message: str = "Bereit"
    rr_ready: bool = False
    packet_count: int = 0
    rr_value_count: int = 0
    bpm_only_count: int = 0
    last_error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "state_age_s": max(0.0, monotonic() - self.since_s),
            "message": self.message,
            "rr_ready": self.rr_ready,
            "packet_count": self.packet_count,
            "rr_value_count": self.rr_value_count,
            "bpm_only_count": self.bpm_only_count,
            "last_error": self.last_error,
        }


class BleStateMachine:
    """Minimal explicit BLE state tracker.

    Windows BLE may report a device as connected before GATT services or RR
    notifications are actually usable.  This tracker keeps those meanings
    separate for the UI and diagnostics.
    """

    def __init__(self) -> None:
        self.snapshot = BleStateSnapshot()

    def transition(self, state: BleConnectionState | str, message: str = "", *, error: str = "") -> BleStateSnapshot:
        next_state = BleConnectionState(state)
        self.snapshot.state = next_state
        self.snapshot.since_s = monotonic()
        if message:
            self.snapshot.message = message
        self.snapshot.last_error = error
        if next_state in {BleConnectionState.IDLE, BleConnectionState.SCANNING, BleConnectionState.CONNECTING, BleConnectionState.DISCONNECTED}:
            self.snapshot.rr_ready = False
        if next_state == BleConnectionState.FAILED:
            self.snapshot.rr_ready = False
        return self.snapshot

    def note_packet(self, *, rr_values: int = 0, bpm_only: bool = False) -> BleStateSnapshot:
        self.snapshot.packet_count += 1
        if rr_values > 0:
            self.snapshot.rr_value_count += int(rr_values)
            self.snapshot.rr_ready = True
            self.transition(BleConnectionState.STREAMING, "RR-Daten aktiv")
        elif bpm_only:
            self.snapshot.bpm_only_count += 1
            if self.snapshot.state != BleConnectionState.STREAMING:
                self.transition(BleConnectionState.WAITING_FOR_RR, "Herzrate sichtbar; warte auf RR-Intervalle")
        return self.snapshot

    def reset_counters(self) -> None:
        self.snapshot.packet_count = 0
        self.snapshot.rr_value_count = 0
        self.snapshot.bpm_only_count = 0
        self.snapshot.rr_ready = False

    def user_label(self) -> tuple[str, str]:
        """Return (tone, label) for compact status UI."""
        state = self.snapshot.state
        if state == BleConnectionState.STREAMING:
            return "good", "BLE: RR aktiv"
        if state in {BleConnectionState.CONNECTING, BleConnectionState.SCANNING, BleConnectionState.DISCOVERING_SERVICES, BleConnectionState.WAITING_FOR_RR, BleConnectionState.RECOVERING}:
            return "active", {
                BleConnectionState.SCANNING: "BLE: Suche",
                BleConnectionState.CONNECTING: "BLE: Verbinde",
                BleConnectionState.DISCOVERING_SERVICES: "BLE: Prüfe",
                BleConnectionState.WAITING_FOR_RR: "BLE: RR wartet",
                BleConnectionState.RECOVERING: "BLE: Wiederherstellung",
            }.get(state, "BLE: aktiv")
        if state in {BleConnectionState.FAILED, BleConnectionState.DISCONNECTED}:
            return "warn", "BLE: Hinweis"
        return "neutral", "Input: —"
