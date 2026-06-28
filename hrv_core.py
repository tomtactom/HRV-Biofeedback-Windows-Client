"""
Core HRV and feedback utilities for HRV Biofeedback.

Compact, testable core module:
- BLE Heart Rate Measurement parser
- rolling HRV metrics and artifact handling
- lightweight rhythm/coherence estimation for no-pacer HRVB
- adaptive reward gate and feedback smoothing
- CSV/debug/metadata helpers
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
import csv
import json
import logging
from logging.handlers import RotatingFileHandler
import math
import os
import platform
import shutil
import sys
import tempfile
import threading
import traceback

import numpy as np

from hrv_sem import (
    SEM_MODEL_VERSION,
    SemReference,
    compute_sem_latents,
    compute_sem_live_feedback,
    sem_model_info,
)


APP_NAME = "HRV Biofeedback"
APP_VERSION = "0.35-startup-menu-bugfix"
APP_DIR = Path.home() / "Documents" / APP_NAME
SESSIONS_DIR = APP_DIR / "sessions"
DEBUG_DIR = APP_DIR / "debug"
LOGS_DIR = APP_DIR / "logs"
CONFIG_PATH = APP_DIR / "config.json"
LOG_FILE = LOGS_DIR / "app.log"

HR_SERVICE_UUID = "0000180d-0000-1000-8000-00805f9b34fb"
HR_MEASUREMENT_UUID = "00002a37-0000-1000-8000-00805f9b34fb"

# RR validity limits are intentionally conservative for live feedback.
RR_MIN_MS = 300.0
RR_MAX_MS = 2000.0
RR_MAX_RELATIVE_JUMP = 0.30

# Rolling windows.
SIGNAL_QUALITY_WINDOW_S = 10.0
RMSSD_WINDOW_S = 30.0
SDNN_WINDOW_S = 60.0
AMPLITUDE_WINDOW_S = 60.0
REGULARITY_WINDOW_S = 20.0
RHYTHM_WINDOW_S = 90.0
PROCESSOR_RETENTION_S = 900.0

# Score weights for live feedback. Version 0.11 keeps HRV amplitude the
# primary positively reinforced signal; the other terms stabilize the display
# and reduce false reinforcement during noisy or irregular windows.
SCORE_WEIGHTS = {
    # Primary operant reinforcer: HRV amplitude.
    # Regularity/RMSSD/coherence remain small stabilizers for noisy windows,
    # but they no longer dominate the live feedback channel.
    "amplitude": 0.86,
    "regularity": 0.08,
    "rmssd": 0.04,
    "coherence": 0.02,
}


def ensure_data_dirs() -> None:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def setup_logging() -> logging.Logger:
    """Configure rotating application logs once and return the app logger."""
    ensure_data_dirs()
    logger = logging.getLogger("hrv_biofeedback")
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(threadName)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=1_000_000,
        backupCount=7,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    logging.captureWarnings(True)
    logger.info("Logging initialized | app=%s version=%s log=%s", APP_NAME, APP_VERSION, LOG_FILE)
    return logger


def log_exception(logger: logging.Logger, message: str, exc: BaseException | None = None) -> None:
    if exc is None:
        logger.exception(message)
    else:
        logger.error("%s | %s: %s\n%s", message, type(exc).__name__, exc, "".join(traceback.format_exception(exc)))


def install_global_exception_hooks(logger: logging.Logger) -> None:
    """Write otherwise uncaught exceptions to the rotating log file."""

    def excepthook(exc_type: type[BaseException], exc: BaseException, tb: Any) -> None:
        logger.critical("Uncaught exception", exc_info=(exc_type, exc, tb))
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = excepthook

    if hasattr(threading, "excepthook"):
        old_threading_hook = threading.excepthook

        def threading_hook(args: Any) -> None:
            logger.critical(
                "Uncaught thread exception in %s",
                getattr(args.thread, "name", "unknown"),
                exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
            )
            old_threading_hook(args)

        threading.excepthook = threading_hook


def cleanup_runtime_files(*, max_age_days: int = 30, max_files_per_dir: int = 250) -> dict[str, int]:
    """Prune old debug/log side files without touching session CSV/metadata files."""
    ensure_data_dirs()
    logger = logging.getLogger("hrv_biofeedback")
    now = datetime.now().timestamp()
    max_age_s = max_age_days * 24 * 60 * 60
    deleted: dict[str, int] = {"debug": 0, "logs": 0}

    for label, folder in {"debug": DEBUG_DIR, "logs": LOGS_DIR}.items():
        try:
            files = [p for p in folder.iterdir() if p.is_file() and p.name != ".gitkeep"]
        except Exception as exc:
            logger.warning("Could not list %s directory %s: %s", label, folder, exc)
            continue

        by_age = [p for p in files if now - p.stat().st_mtime > max_age_s]
        by_count = sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)[max_files_per_dir:]
        for path in set(by_age + by_count):
            try:
                path.unlink()
                deleted[label] += 1
            except Exception as exc:
                logger.warning("Could not delete old runtime file %s: %s", path, exc)
    if any(deleted.values()):
        logger.info("Runtime cleanup deleted files: %s", deleted)
    return deleted


def app_system_snapshot() -> dict[str, Any]:
    return {
        "app_name": APP_NAME,
        "app_version": APP_VERSION,
        "python": sys.version,
        "platform": platform.platform(),
        "executable": sys.executable,
        "app_dir": str(APP_DIR),
        "sessions_dir": str(SESSIONS_DIR),
        "debug_dir": str(DEBUG_DIR),
        "logs_dir": str(LOGS_DIR),
    }




def run_core_self_test() -> dict[str, Any]:
    """Run a small non-invasive health check of local core functionality.

    The test avoids hardware access. It checks whether the app can write into
    its local folders, parse a known BLE Heart Rate packet, compute a few HRV
    values and serialize JSON atomically. It is useful before troubleshooting
    Bluetooth, because it separates app/runtime problems from sensor problems.
    """
    ensure_data_dirs()
    checks: list[dict[str, Any]] = []

    def add(key: str, ok: bool, detail: str, suggestion: str = "") -> None:
        checks.append({"key": key, "status": "ok" if ok else "error", "detail": detail, "suggestion": suggestion})

    try:
        test_path = DEBUG_DIR / ".selftest_write.tmp"
        _atomic_write_text(test_path, "selftest")
        test_path.unlink(missing_ok=True)
        add("data_folder_write", True, f"Writable: {APP_DIR}")
    except Exception as exc:
        add("data_folder_write", False, f"Cannot write to {APP_DIR}: {type(exc).__name__}: {exc}", "Datenordnerrechte prüfen oder App aus einem beschreibbaren Benutzerkonto starten.")

    try:
        parsed = parse_heart_rate_measurement(bytes([0x10, 60, 0x00, 0x04]))
        add("ble_parser", parsed.bpm == 60 and len(parsed.rr_ms) == 1, f"Parser bpm={parsed.bpm} rr_count={len(parsed.rr_ms)}")
    except Exception as exc:
        add("ble_parser", False, f"Parser failed: {type(exc).__name__}: {exc}")

    try:
        rr = [1000.0, 1012.0, 992.0, 1006.0]
        add("hrv_metrics", bool(rmssd_ms(rr) and sdnn_ms(rr)), "RMSSD/SDNN calculable")
    except Exception as exc:
        add("hrv_metrics", False, f"Metric calculation failed: {type(exc).__name__}: {exc}")

    try:
        save_json(DEBUG_DIR / f"selftest_{now_stamp()}.json", {"ok": True, "created_at": iso_now()})
        add("json_export", True, "Atomic JSON export works")
    except Exception as exc:
        add("json_export", False, f"JSON export failed: {type(exc).__name__}: {exc}")

    ok = all(item["status"] == "ok" for item in checks)
    return {"ok": ok, "created_at": iso_now(), "checks": checks, "app_snapshot": app_system_snapshot()}


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
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


def now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def iso_now() -> str:
    return datetime.now().isoformat(timespec="milliseconds")


@dataclass
class ParsedHeartRatePacket:
    bpm: Optional[int]
    rr_ms: list[float]
    contact_supported: bool
    contact_detected: Optional[bool]
    raw_hex: str


@dataclass
class HrvMetrics:
    timestamp_iso: str = ""
    elapsed_s: float = 0.0
    phase: str = "idle"
    rr_ms: float | None = None
    bpm: float | None = None
    rr_valid: bool = True
    artifact_reason: str = ""
    sensor_contact_supported: bool = False
    sensor_contact_detected: bool | None = None
    rmssd_30s: float | None = None
    sdnn_60s: float | None = None
    hrv_amplitude_60s: float | None = None
    regularity_20s: float | None = None
    dominant_frequency_hz: float | None = None
    dominant_frequency_bpm: float | None = None
    coherence_90s: float | None = None
    signal_quality: float = 0.0
    hrv_score: float = 0.0
    feedback_strength: float = 0.0
    sem_autonomic_flexibility: float | None = None
    sem_measurement_quality: float | None = None
    sem_training_response: float | None = None
    sem_integrated_self_regulation: float | None = None
    sem_expected_training_response: float | None = None
    sem_latent_alignment: float | None = None
    sem_live_confidence: float | None = None
    sem_feedback_target: float | None = None
    sem_gate_reason: str = ""
    sem_model_version: str = SEM_MODEL_VERSION
    adaptive_threshold: float = 0.52
    reward_active: bool = False
    reward_count: int = 0
    feedback_mode: str = "green_circle"
    audio_enabled: bool = False
    circle_radius: float = 0.0
    protocol_type: str = "individual_hrvb_no_pacer"
    input_mode: str = "unknown"


HRVB_PROTOCOL_TYPES = {
    "optimal_rf": {
        "label": "Optimal RF",
        "description": "Personal resonance frequency is assessed before training and then used during sessions.",
        "implemented": False,
    },
    "individual_hrvb_no_pacer": {
        "label": "Individual HRVB without breathing pacer",
        "description": "Live cardiovascular feedback is used without a forced breathing pacer. This is the default mode.",
        "implemented": True,
    },
    "preset_pace": {
        "label": "Preset-Pace RF",
        "description": "A fixed breathing pace, commonly around 6 breaths/min, is used for all sessions.",
        "implemented": False,
    },
}


HRVB_REPORTING_CHECKLIST = [
    "protocol_type",
    "baseline_duration_s",
    "training_duration_s",
    "reference_duration_s",
    "feedback_mode",
    "audio_enabled",
    "input_mode",
    "device_identifier",
    "rr_source",
    "artifact_rules",
    "body_position",
    "eyes",
    "room_light",
    "room_noise",
    "room_temperature",
    "time_of_day",
    "participant_count",
    "breathing_pacer_enabled",
    "breathing_rate_bpm",
    "inhale_hold_exhale_s",
    "notes",
]


def default_session_context() -> dict[str, Any]:
    """Context variables inspired by HRVB reporting checklists.

    The GUI exposes the most useful fields. Unknown items are kept as explicit
    placeholders so exported sessions remain auditable and easy to extend later.
    """
    return {
        "body_position": "sitting_not_confirmed",
        "eyes": "open_inferred_from_screen_feedback",
        "room_light": "not_recorded",
        "room_noise": "not_recorded",
        "room_temperature": "not_recorded",
        "time_of_day": datetime.now().strftime("%H:%M:%S"),
        "participant_count": 1,
        "pre_session_instructions": [
            "sit comfortably if possible",
            "avoid interpreting the score as a diagnosis",
            "use the session as training/self-observation data",
            "positive feedback is linked primarily to HRV amplitude",
        ],
        "pre_session_ratings": {},
        "pre_session_rating_labels": {},
        "psychology_model_version": "not_started",
        "training_frame": "not_started",
        "notes": "",
    }


def build_reporting_checklist(context: dict[str, Any]) -> dict[str, bool]:
    always_present = {
        "protocol_type",
        "baseline_duration_s",
        "training_duration_s",
        "reference_duration_s",
        "feedback_mode",
        "audio_enabled",
        "input_mode",
        "device_identifier",
        "rr_source",
        "artifact_rules",
        "breathing_pacer_enabled",
        "breathing_rate_bpm",
        "inhale_hold_exhale_s",
    }
    checklist: dict[str, bool] = {}
    for key in HRVB_REPORTING_CHECKLIST:
        value = context.get(key, None)
        checklist[key] = key in always_present or (value not in (None, "", "not_recorded"))
    return checklist


def build_session_metadata(
    *,
    session_label: str,
    csv_filename: str,
    row_count: int,
    phases: list[str],
    baseline_duration_s: float,
    reference_duration_s: float,
    training_duration_s: float,
    feedback_mode: str,
    audio_enabled: bool,
    sem_live_enabled: bool,
    input_mode: str,
    device_identifier: str,
    protocol_type: str = "individual_hrvb_no_pacer",
    context: Optional[dict[str, Any]] = None,
    summary: Optional[dict[str, Any]] = None,
    sem_segments_filename: str | None = None,
    sem_path_summary: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    ctx = default_session_context()
    if context:
        ctx.update(context)

    return {
        "app": {
            "name": APP_NAME,
            "version": APP_VERSION,
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "created_at": iso_now(),
        },
        "session": {
            "label": session_label,
            "csv_filename": csv_filename,
            "row_count": row_count,
            "phases": phases,
            "summary": summary or {},
            "sem_segments_filename": sem_segments_filename,
        },
        "protocol": {
            "type": protocol_type,
            "type_label": HRVB_PROTOCOL_TYPES.get(protocol_type, {}).get("label", protocol_type),
            "baseline_duration_s": baseline_duration_s,
            "reference_duration_s": reference_duration_s,
            "training_duration_s": training_duration_s,
            "breathing_pacer_enabled": False,
            "breathing_rate_bpm": None,
            "inhale_hold_exhale_s": None,
            "rf_detection": "not_implemented_in_v0_14",
            "feedback_mode": feedback_mode,
            "audio_enabled": audio_enabled,
            "sem_live_enabled": sem_live_enabled,
            "sem_live_rule": "background model only; the frontend reinforces HRV amplitude while the model gates noisy or internally inconsistent feedback",
            "onboarding_and_ble_diagnostics": "first-run guidance, connection assistant, scan/connect debug reports and non-invasive troubleshooting suggestions are available",
            "reward_rule": "reward after control score above adaptive threshold for 3 seconds; off after 2 seconds below threshold",
            "adaptive_threshold_rule": "threshold slowly increases when reward ratio over last 60 s exceeds 70 percent and decreases when below 15 percent",
        },
        "measurement": {
            "input_mode": input_mode,
            "device_identifier": device_identifier or "not_recorded",
            "rr_source": "BLE Heart Rate Measurement 0x2A37 when available; otherwise mock/development stream",
            "artifact_rules": {
                "rr_min_ms": RR_MIN_MS,
                "rr_max_ms": RR_MAX_MS,
                "max_relative_jump": RR_MAX_RELATIVE_JUMP,
                "signal_quality_window_s": SIGNAL_QUALITY_WINDOW_S,
            },
            "metrics": {
                "rmssd_window_s": RMSSD_WINDOW_S,
                "sdnn_window_s": SDNN_WINDOW_S,
                "hrv_amplitude_window_s": AMPLITUDE_WINDOW_S,
                "regularity_window_s": REGULARITY_WINDOW_S,
                "rhythm_window_s": RHYTHM_WINDOW_S,
                "score_weights": SCORE_WEIGHTS,
                "dominant_rhythm_band_hz": [0.04, 0.15],
                "note": "dominant rhythm is estimated from HR only; it is not a respiratory measurement",
            },
        },
        "context": ctx,
        "reporting_checklist": build_reporting_checklist(ctx),
        "sem_latent_model": {
            **sem_model_info(),
            "path_summary": sem_path_summary or {},
        },
        "protocol_adaptation": ctx.get("double_loop_learning", {}),
        "literature_integration": [
            "Lalanza et al. 2023: keep protocol type explicit and log context variables relevant for replication.",
            "Schoenberg & David 2014: keep claims descriptive, log modality/design details, and leave multimodal expansion possible.",
            "Mann et al. 2015: use SEM as an explicit latent-variable framing for HRV, affective/cognitive self-regulation constructs, with covariates handled cautiously offline.",
            "Thayer & Lane 2000: integrate autonomic, attentional and affective regulation as a feedback-system model rather than a single raw HRV value.",
            "Rossi/Lipsey/Henry evaluation approach: make the program theory and observable process/outcome indicators explicit to avoid black-box evaluation.",
            "Double-loop learning: review not only thresholds, but also whether signal quality, reinforcement and transfer assumptions fit the current session data.",
            "Mindfield/eSense and HRV-practice sources: train HRV amplitude and regularity with raw RR export.",
            "Quigley et al. 2024 HR/HRV publication guidelines: record measurement, derivation, context, artifact rules and interpretation boundaries transparently.",
            "Vann-Adibe et al. 2025 remote HRV-B meta-analysis: short repeatable practice and resonance-maximizing interfaces are plausible; stress effects remain mixed.",
            "Wang et al. 2025 umbrella review: HRV findings in mental disorders are heterogeneous; use HRV as a training signal, not as diagnosis.",
            "Balaji et al. 2025 global HRVB dataset and Sumińska et al. 2026 RF-vs-0.1Hz comparison: 0.1-Hz/RF information is useful context but not a required visible target.",
        ],
    }


def write_session_metadata(path: Path, metadata: dict[str, Any]) -> None:
    save_json(path, metadata)


class JsonlWriter:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("a", encoding="utf-8")

    def write(self, obj: dict[str, Any]) -> None:
        self._fh.write(json.dumps(obj, ensure_ascii=False, default=str) + "\n")
        self._fh.flush()

    def close(self) -> None:
        try:
            self._fh.close()
        except Exception:
            pass


def save_json(path: Path, data: Any) -> None:
    serialized = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    _atomic_write_text(path, serialized)


def load_config() -> dict[str, Any]:
    ensure_data_dirs()
    logger = logging.getLogger("hrv_biofeedback")
    if not CONFIG_PATH.exists():
        return {}
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning("Config could not be read. A backup copy is kept and defaults are used: %s", exc)
        try:
            backup = CONFIG_PATH.with_suffix(f".invalid_{now_stamp()}.json")
            shutil.copy2(CONFIG_PATH, backup)
        except Exception as backup_exc:
            logger.warning("Config backup failed: %s", backup_exc)
        return {}


def save_config(config: dict[str, Any]) -> None:
    ensure_data_dirs()
    config = dict(config)
    config.setdefault("config_schema", 1)
    config["last_saved_at"] = iso_now()
    save_json(CONFIG_PATH, config)




def sanitize_rr_values(values: Any) -> list[float]:
    """Return finite, physiologically plausible RR intervals from a packet-like value.

    BLE callbacks should never crash or pollute counters because a backend,
    mock source or future input adapter passes a scalar, string, NaN or mixed
    iterable.  The physiological bounds mirror the live RR validator so the
    UI state machine only sees RR intervals that could become HRV data.
    """
    if values is None:
        return []
    if isinstance(values, (str, bytes, bytearray, memoryview)):
        candidates: list[Any] = [values]
    else:
        try:
            candidates = list(values)
        except TypeError:
            candidates = [values]

    rr_values: list[float] = []
    for item in candidates:
        try:
            value = float(item)
        except (TypeError, ValueError):
            continue
        if math.isfinite(value) and RR_MIN_MS <= value <= RR_MAX_MS:
            rr_values.append(value)
    return rr_values

def parse_heart_rate_measurement(data: bytes | bytearray | memoryview | None) -> ParsedHeartRatePacket:
    """Parse Bluetooth Heart Rate Measurement characteristic (UUID 0x2A37).

    RR intervals in the Bluetooth HRS profile use units of 1/1024 second.
    One notification may contain zero, one, or multiple RR intervals. The
    parser is intentionally defensive: malformed packets become empty parsed
    packets instead of crashing the BLE notification thread.
    """
    try:
        data = bytes(data or b"")
    except Exception:
        return ParsedHeartRatePacket(None, [], False, None, "")
    if not data:
        return ParsedHeartRatePacket(None, [], False, None, "")

    flags = data[0]
    offset = 1

    hr_is_uint16 = bool(flags & 0x01)
    contact_detected_bit = bool(flags & 0x02)
    contact_supported = bool(flags & 0x04)
    energy_present = bool(flags & 0x08)
    rr_present = bool(flags & 0x10)

    bpm: Optional[int]
    if len(data) <= offset:
        bpm = None
    elif hr_is_uint16:
        if len(data) < offset + 2:
            bpm = None
        else:
            bpm = int.from_bytes(data[offset:offset + 2], "little")
        offset += 2
    else:
        bpm = int(data[offset])
        offset += 1

    if energy_present:
        # Skip Energy Expended. Defensive bounds handling keeps malformed packets harmless.
        offset = min(len(data), offset + 2)

    rr_ms: list[float] = []
    if rr_present:
        while offset + 1 < len(data):
            raw_rr = int.from_bytes(data[offset:offset + 2], "little")
            rr_ms.append(raw_rr * 1000.0 / 1024.0)
            offset += 2

    contact_detected: Optional[bool]
    if contact_supported:
        contact_detected = contact_detected_bit
    else:
        contact_detected = None

    return ParsedHeartRatePacket(
        bpm=bpm,
        rr_ms=rr_ms,
        contact_supported=contact_supported,
        contact_detected=contact_detected,
        raw_hex=data.hex(),
    )


def rmssd_ms(rr_ms: list[float] | np.ndarray) -> Optional[float]:
    rr = np.asarray(rr_ms, dtype=float)
    rr = rr[np.isfinite(rr)]
    if rr.size < 3:
        return None
    diff = np.diff(rr)
    return float(np.sqrt(np.mean(diff * diff)))


def sdnn_ms(rr_ms: list[float] | np.ndarray) -> Optional[float]:
    rr = np.asarray(rr_ms, dtype=float)
    rr = rr[np.isfinite(rr)]
    if rr.size < 3:
        return None
    return float(np.std(rr, ddof=1))


def hrv_amplitude_bpm(bpm_values: list[float] | np.ndarray) -> Optional[float]:
    bpm = np.asarray(bpm_values, dtype=float)
    bpm = bpm[np.isfinite(bpm)]
    if bpm.size < 10:
        return None
    return float(np.percentile(bpm, 95) - np.percentile(bpm, 5))


def regularity_score_bpm(bpm_values: list[float] | np.ndarray) -> Optional[float]:
    """Lightweight live-safe regularity estimate between 0 and 1.

    It rewards smooth recurring HR oscillations and dampens jagged curves.
    """
    bpm = np.asarray(bpm_values, dtype=float)
    bpm = bpm[np.isfinite(bpm)]
    if bpm.size < 12:
        return None

    x = bpm - np.mean(bpm)
    if np.std(x) < 1e-6:
        return 0.0

    kernel_len = min(7, max(3, bpm.size // 8))
    kernel = np.ones(kernel_len) / kernel_len
    smooth = np.convolve(x, kernel, mode="same")

    slope = np.diff(smooth)
    if slope.size < 3:
        return None
    jerk = np.diff(slope)

    roughness = np.std(jerk) / max(np.std(smooth), 1e-6)
    score = 1.0 - roughness / 1.6
    return float(np.clip(score, 0.0, 1.0))


def dominant_rhythm_from_samples(samples: list[dict[str, Any]]) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """Estimate dominant HR rhythm in 0.04-0.15 Hz from irregular beat samples.

    Returns (frequency_hz, frequency_bpm, coherence_score). This is not a
    breathing measurement; it is a helpful live feature for no-pacer HRVB.
    """
    if len(samples) < 35:
        return None, None, None

    pairs = [(float(s["elapsed_s"]), float(s["bpm"])) for s in samples if s.get("bpm") is not None]
    if len(pairs) < 35:
        return None, None, None

    pairs.sort(key=lambda x: x[0])
    t = np.asarray([p[0] for p in pairs], dtype=float)
    y = np.asarray([p[1] for p in pairs], dtype=float)
    finite = np.isfinite(t) & np.isfinite(y)
    t, y = t[finite], y[finite]
    if t.size < 35:
        return None, None, None

    # Remove duplicate timestamps that can appear when one BLE packet contains multiple RR values.
    unique_t, unique_idx = np.unique(t, return_index=True)
    t = unique_t
    y = y[unique_idx]
    duration = float(t[-1] - t[0])
    if duration < 45.0:
        return None, None, None

    fs = 4.0
    n = int(duration * fs)
    if n < 180:
        return None, None, None
    grid = np.linspace(t[0], t[-1], n)
    interp = np.interp(grid, t, y)
    interp = interp - np.mean(interp)
    if np.std(interp) < 1e-6:
        return None, None, 0.0

    window = np.hanning(interp.size)
    spectrum = np.fft.rfft(interp * window)
    power = np.abs(spectrum) ** 2
    freqs = np.fft.rfftfreq(interp.size, d=1.0 / fs)

    band = (freqs >= 0.04) & (freqs <= 0.15)
    wider = (freqs >= 0.03) & (freqs <= 0.40)
    if not np.any(band):
        return None, None, None

    band_power = power[band]
    if float(np.sum(band_power)) <= 1e-12:
        return None, None, 0.0

    idx = int(np.argmax(band_power))
    dom_freq = float(freqs[band][idx])
    peak_concentration = float(band_power[idx] / max(np.sum(band_power), 1e-12))
    band_share = float(np.sum(band_power) / max(np.sum(power[wider]), 1e-12)) if np.any(wider) else 0.0
    coherence = np.clip(0.65 * peak_concentration + 0.35 * band_share, 0.0, 1.0)
    return dom_freq, dom_freq * 60.0, float(coherence)


def safe_div(a: float, b: float, default: float = 0.0) -> float:
    if not math.isfinite(a) or not math.isfinite(b) or abs(b) < 1e-9:
        return default
    return a / b


class HrvProcessor:
    def __init__(self) -> None:
        self.samples: list[dict[str, Any]] = []
        self.baseline_amp = 8.0
        self.baseline_rmssd = 35.0
        self.baseline_sdnn = 42.0
        self.baseline_coherence = 0.30
        self.baseline_ready = False
        self.last_valid_rr: Optional[float] = None
        self.pending_jump_rr: Optional[float] = None
        self.pending_jump_count = 0

    def reset(self) -> None:
        self.samples.clear()
        self.baseline_ready = False
        self.last_valid_rr = None
        self.pending_jump_rr = None
        self.pending_jump_count = 0
        self.baseline_amp = 8.0
        self.baseline_rmssd = 35.0
        self.baseline_sdnn = 42.0
        self.baseline_coherence = 0.30

    def add_rr(
        self,
        elapsed_s: float,
        rr_ms: float,
        phase: str,
        *,
        sensor_contact_supported: bool = False,
        sensor_contact_detected: bool | None = None,
    ) -> HrvMetrics:
        valid, reason = self._validate_rr(rr_ms, sensor_contact_supported, sensor_contact_detected)
        bpm = 60000.0 / rr_ms if rr_ms > 0 else None

        row = {
            "elapsed_s": float(elapsed_s),
            "rr_ms": float(rr_ms),
            "bpm": float(bpm) if bpm is not None else None,
            "valid": bool(valid),
            "reason": reason,
            "phase": phase,
            "sensor_contact_supported": bool(sensor_contact_supported),
            "sensor_contact_detected": sensor_contact_detected,
        }
        self.samples.append(row)
        if valid:
            self.last_valid_rr = rr_ms

        metrics = self.compute_metrics(
            elapsed_s,
            phase,
            rr_ms,
            bpm,
            valid,
            reason,
            sensor_contact_supported=sensor_contact_supported,
            sensor_contact_detected=sensor_contact_detected,
        )
        self._prune_samples(elapsed_s)
        return metrics

    def _prune_samples(self, elapsed_s: float) -> None:
        cutoff = elapsed_s - PROCESSOR_RETENTION_S
        if cutoff <= 0:
            return
        self.samples = [
            s for s in self.samples
            if s["elapsed_s"] >= cutoff or (not self.baseline_ready and s.get("phase") == "baseline")
        ]

    def _validate_rr(
        self,
        rr_ms: float,
        sensor_contact_supported: bool = False,
        sensor_contact_detected: bool | None = None,
    ) -> tuple[bool, str]:
        """Validate an RR interval and recover from sustained real HR changes.

        Single implausible jumps are treated as artifacts. A genuine abrupt
        but stable heart-rate change can otherwise create an "artifact lock"
        because every new RR value remains far away from the last accepted RR.
        To avoid that, three consecutive RR values in the new range are accepted
        as a new baseline for live processing. This keeps noisy spikes out while
        allowing physiological transitions and sensor re-stabilization.
        """
        if sensor_contact_supported and sensor_contact_detected is False:
            self._reset_pending_jump()
            return False, "sensor_contact_not_detected"
        if not math.isfinite(rr_ms):
            self._reset_pending_jump()
            return False, "non_finite_rr"
        if rr_ms < RR_MIN_MS:
            self._reset_pending_jump()
            return False, "rr_too_short"
        if rr_ms > RR_MAX_MS:
            self._reset_pending_jump()
            return False, "rr_too_long"
        if self.last_valid_rr is not None:
            jump = abs(rr_ms - self.last_valid_rr) / max(self.last_valid_rr, 1.0)
            if jump > RR_MAX_RELATIVE_JUMP:
                if self._pending_jump_is_stable(rr_ms):
                    self._reset_pending_jump()
                    return True, ""
                return False, "rr_jump_gt_30_percent"
        self._reset_pending_jump()
        return True, ""

    def _pending_jump_is_stable(self, rr_ms: float) -> bool:
        """Return True when repeated jump artifacts form a stable new RR band."""
        if self.pending_jump_rr is None:
            self.pending_jump_rr = float(rr_ms)
            self.pending_jump_count = 1
            return False
        rel = abs(rr_ms - self.pending_jump_rr) / max(self.pending_jump_rr, 1.0)
        if rel <= 0.12:
            self.pending_jump_count += 1
            self.pending_jump_rr = float(0.65 * self.pending_jump_rr + 0.35 * rr_ms)
        else:
            self.pending_jump_rr = float(rr_ms)
            self.pending_jump_count = 1
        return self.pending_jump_count >= 3

    def _reset_pending_jump(self) -> None:
        self.pending_jump_rr = None
        self.pending_jump_count = 0

    def valid_samples_since(self, elapsed_s: float, window_s: float) -> list[dict[str, Any]]:
        cutoff = elapsed_s - window_s
        return [s for s in self.samples if s["valid"] and s["elapsed_s"] >= cutoff]

    def all_valid_samples(self, phase: str | None = None) -> list[dict[str, Any]]:
        return [s for s in self.samples if s["valid"] and (phase is None or s.get("phase") == phase)]

    def compute_metrics(
        self,
        elapsed_s: float,
        phase: str,
        rr_ms: float | None = None,
        bpm: float | None = None,
        rr_valid: bool = True,
        artifact_reason: str = "",
        *,
        sensor_contact_supported: bool = False,
        sensor_contact_detected: bool | None = None,
    ) -> HrvMetrics:
        valid_10 = self.valid_samples_since(elapsed_s, SIGNAL_QUALITY_WINDOW_S)
        total_10 = [s for s in self.samples if s["elapsed_s"] >= elapsed_s - SIGNAL_QUALITY_WINDOW_S]
        signal_quality = safe_div(len(valid_10), max(len(total_10), 1))
        signal_quality *= min(1.0, len(valid_10) / 8.0)
        signal_quality = float(np.clip(signal_quality, 0.0, 1.0))

        rr_30 = [s["rr_ms"] for s in self.valid_samples_since(elapsed_s, RMSSD_WINDOW_S)]
        rr_60 = [s["rr_ms"] for s in self.valid_samples_since(elapsed_s, SDNN_WINDOW_S)]
        bpm_20 = [s["bpm"] for s in self.valid_samples_since(elapsed_s, REGULARITY_WINDOW_S)]
        bpm_60 = [s["bpm"] for s in self.valid_samples_since(elapsed_s, AMPLITUDE_WINDOW_S)]
        rhythm_samples = self.valid_samples_since(elapsed_s, RHYTHM_WINDOW_S)

        rmssd = rmssd_ms(rr_30)
        sdnn = sdnn_ms(rr_60)
        amp = hrv_amplitude_bpm(bpm_60)
        reg = regularity_score_bpm(bpm_20)
        dom_hz, dom_bpm, coherence = dominant_rhythm_from_samples(rhythm_samples)

        amp_component = 0.0 if amp is None else float(np.clip(amp / max(self.baseline_amp * 1.5, 1.0), 0.0, 1.0))
        rmssd_component = 0.0 if rmssd is None else float(np.clip(rmssd / max(self.baseline_rmssd * 1.5, 5.0), 0.0, 1.0))
        reg_component = 0.0 if reg is None else reg
        coh_component = 0.0 if coherence is None else float(np.clip(coherence / max(self.baseline_coherence * 1.5, 0.2), 0.0, 1.0))

        score = (
            SCORE_WEIGHTS["amplitude"] * amp_component
            + SCORE_WEIGHTS["regularity"] * reg_component
            + SCORE_WEIGHTS["rmssd"] * rmssd_component
            + SCORE_WEIGHTS["coherence"] * coh_component
        )
        score = float(np.clip(score * signal_quality, 0.0, 1.0))

        # The live training channel is intentionally narrower than the full
        # documentation model: the visible circle reinforces HRV amplitude.
        # Other metrics stabilize exports and signal checks without becoming
        # a second visible task for the user.
        feedback_strength = float(np.clip(amp_component * signal_quality, 0.0, 1.0))

        sem = compute_sem_latents(
            hrv_amplitude_60s=amp,
            rmssd_30s=rmssd,
            sdnn_60s=sdnn,
            regularity_20s=reg,
            coherence_90s=coherence,
            signal_quality=signal_quality,
            rr_valid=rr_valid,
            hrv_score=score,
            reference=SemReference(
                amplitude_bpm=self.baseline_amp,
                rmssd_ms=self.baseline_rmssd,
                sdnn_ms=self.baseline_sdnn,
                coherence=self.baseline_coherence,
            ),
        )
        sem_live = compute_sem_live_feedback(
            autonomic_flexibility=sem["sem_autonomic_flexibility"],
            measurement_quality=sem["sem_measurement_quality"],
            hrv_score=score,
            phase=phase,
        )

        return HrvMetrics(
            timestamp_iso=iso_now(),
            elapsed_s=float(elapsed_s),
            phase=phase,
            rr_ms=rr_ms,
            bpm=bpm,
            rr_valid=rr_valid,
            artifact_reason=artifact_reason,
            sensor_contact_supported=sensor_contact_supported,
            sensor_contact_detected=sensor_contact_detected,
            rmssd_30s=rmssd,
            sdnn_60s=sdnn,
            hrv_amplitude_60s=amp,
            regularity_20s=reg,
            dominant_frequency_hz=dom_hz,
            dominant_frequency_bpm=dom_bpm,
            coherence_90s=coherence,
            signal_quality=signal_quality,
            hrv_score=score,
            feedback_strength=feedback_strength,
            sem_autonomic_flexibility=sem["sem_autonomic_flexibility"],
            sem_measurement_quality=sem["sem_measurement_quality"],
            sem_training_response=sem["sem_training_response"],
            sem_integrated_self_regulation=sem["sem_integrated_self_regulation"],
            sem_expected_training_response=sem_live["sem_expected_training_response"],
            sem_latent_alignment=sem_live["sem_latent_alignment"],
            sem_live_confidence=sem_live["sem_live_confidence"],
            sem_feedback_target=sem_live["sem_feedback_target"],
            sem_gate_reason=sem_live["sem_gate_reason"],
        )

    def finalize_baseline(self) -> None:
        valid = self.all_valid_samples(phase="baseline") or self.all_valid_samples()
        if not valid:
            self.use_default_baseline()
            return

        rr = [s["rr_ms"] for s in valid]
        bpm = [s["bpm"] for s in valid]
        amp = hrv_amplitude_bpm(bpm)
        rmssd = rmssd_ms(rr)
        sdnn = sdnn_ms(rr)
        dom_hz, dom_bpm, coherence = dominant_rhythm_from_samples(valid)
        self.baseline_amp = float(max(amp or 8.0, 1.0))
        self.baseline_rmssd = float(max(rmssd or 35.0, 5.0))
        self.baseline_sdnn = float(max(sdnn or 42.0, 5.0))
        self.baseline_coherence = float(max(coherence or 0.30, 0.15))
        self.baseline_ready = True

    def use_default_baseline(self) -> None:
        self.baseline_amp = 8.0
        self.baseline_rmssd = 35.0
        self.baseline_sdnn = 42.0
        self.baseline_coherence = 0.30
        self.baseline_ready = True


class RewardGate:
    def __init__(self, on_seconds: float = 3.0, off_seconds: float = 2.0) -> None:
        self.on_seconds = on_seconds
        self.off_seconds = off_seconds
        self.above_since: Optional[float] = None
        self.below_since: Optional[float] = None
        self.active = False

    def reset(self) -> None:
        self.above_since = None
        self.below_since = None
        self.active = False

    def update(self, now_s: float, score: float, threshold: float, signal_ok: bool) -> bool:
        if not signal_ok:
            self.reset()
            return False

        if score >= threshold:
            self.below_since = None
            if self.above_since is None:
                self.above_since = now_s
            if now_s - self.above_since >= self.on_seconds:
                self.active = True
        else:
            self.above_since = None
            if self.below_since is None:
                self.below_since = now_s
            if now_s - self.below_since >= self.off_seconds:
                self.active = False
        return self.active


class FeedbackEngine:
    def __init__(self, sem_live_enabled: bool = True) -> None:
        self.threshold = 0.52
        self.reward_gate = RewardGate()
        self.reward_history: list[tuple[float, bool]] = []
        self.feedback_value = 0.0
        self.reward_count = 0
        self._last_reward = False
        self.sem_live_enabled = bool(sem_live_enabled)

    def reset(self) -> None:
        self.threshold = 0.52
        self.reward_gate.reset()
        self.reward_history.clear()
        self.feedback_value = 0.0
        self.reward_count = 0
        self._last_reward = False

    def set_sem_live_enabled(self, enabled: bool) -> None:
        self.sem_live_enabled = bool(enabled)

    def update(self, metrics: HrvMetrics, phase: str) -> HrvMetrics:
        training_active = phase == "training"
        # The visible biofeedback channel is intentionally simple: circle size
        # and rewards follow normalized HRV amplitude. Composite metrics and
        # latent model values stay in export/quality control.
        control_score = metrics.feedback_strength
        signal_ok = metrics.signal_quality >= 0.65 and metrics.rr_valid and training_active
        if self.sem_live_enabled and metrics.sem_gate_reason == "low_measurement_quality":
            signal_ok = False
        reward = self.reward_gate.update(metrics.elapsed_s, control_score, self.threshold, signal_ok)
        if reward and not self._last_reward:
            self.reward_count += 1
        self._last_reward = reward

        self.reward_history.append((metrics.elapsed_s, reward))
        self.reward_history = [(t, r) for t, r in self.reward_history if t >= metrics.elapsed_s - 60.0]

        if training_active and len(self.reward_history) >= 10:
            ratio = sum(1 for _, r in self.reward_history if r) / len(self.reward_history)
            if ratio > 0.70:
                self.threshold = min(0.76, self.threshold + 0.002)
            elif ratio < 0.15:
                self.threshold = max(0.38, self.threshold - 0.001)

        target = control_score if training_active else 0.0
        self.feedback_value = smooth_feedback(self.feedback_value, target, alpha=0.08)

        metrics.reward_active = reward
        metrics.reward_count = self.reward_count
        metrics.adaptive_threshold = self.threshold
        metrics.circle_radius = self.feedback_value
        metrics.sem_feedback_target = float(np.clip(control_score, 0.0, 1.0))

        # Update the background training and higher-order documentation scores after reward/circle state
        # is known. Keep the autonomic and measurement latent scores computed by HrvProcessor,
        # because they are baseline-referenced.
        reward_numeric = 1.0 if metrics.reward_active else 0.0
        training_response = (
            0.55 * float(np.clip(metrics.feedback_strength, 0.0, 1.0))
            + 0.25 * float(np.clip(metrics.circle_radius, 0.0, 1.0))
            + 0.20 * reward_numeric
        )
        metrics.sem_training_response = float(np.clip(training_response, 0.0, 1.0))
        autonomic = 0.5 if metrics.sem_autonomic_flexibility is None else metrics.sem_autonomic_flexibility
        measurement = 0.0 if metrics.sem_measurement_quality is None else metrics.sem_measurement_quality
        metrics.sem_integrated_self_regulation = float(np.clip(
            0.55 * autonomic + 0.20 * measurement + 0.25 * metrics.sem_training_response,
            0.0,
            1.0,
        ))
        sem_live = compute_sem_live_feedback(
            autonomic_flexibility=metrics.sem_autonomic_flexibility,
            measurement_quality=metrics.sem_measurement_quality,
            hrv_score=metrics.hrv_score,
            phase=phase,
            training_response=metrics.sem_training_response,
        )
        metrics.sem_expected_training_response = sem_live["sem_expected_training_response"]
        metrics.sem_latent_alignment = sem_live["sem_latent_alignment"]
        metrics.sem_live_confidence = sem_live["sem_live_confidence"]
        # Keep sem_feedback_target as the actual visible target (HRV amplitude).
        # Background model confidence is documented separately and does not steer
        # the live circle.
        metrics.sem_gate_reason = sem_live["sem_gate_reason"]
        return metrics


def smooth_feedback(prev_value: float, target_value: float, alpha: float = 0.08) -> float:
    return float(prev_value + alpha * (target_value - prev_value))


def metrics_to_csv_row(metrics: HrvMetrics) -> dict[str, Any]:
    return asdict(metrics)


def write_session_csv(path: Path, rows: list[HrvMetrics]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(asdict(HrvMetrics()).keys())
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(metrics_to_csv_row(row))
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


def summarize_session(rows: list[HrvMetrics]) -> dict[str, Any]:
    if not rows:
        return {}
    valid = [r for r in rows if r.rr_valid]
    reward_rows = [r for r in rows if r.reward_active]
    bpm_values = [r.bpm for r in valid if r.bpm is not None]
    score_values = [r.hrv_score for r in rows]
    rmssd_values = [r.rmssd_30s for r in rows if r.rmssd_30s is not None]
    amp_values = [r.hrv_amplitude_60s for r in rows if r.hrv_amplitude_60s is not None]
    coherence_values = [r.coherence_90s for r in rows if r.coherence_90s is not None]
    dom_values = [r.dominant_frequency_bpm for r in rows if r.dominant_frequency_bpm is not None]
    sem_af_values = [r.sem_autonomic_flexibility for r in rows if r.sem_autonomic_flexibility is not None]
    sem_mq_values = [r.sem_measurement_quality for r in rows if r.sem_measurement_quality is not None]
    sem_tr_values = [r.sem_training_response for r in rows if r.sem_training_response is not None]
    sem_isr_values = [r.sem_integrated_self_regulation for r in rows if r.sem_integrated_self_regulation is not None]
    sem_align_values = [r.sem_latent_alignment for r in rows if r.sem_latent_alignment is not None]
    sem_conf_values = [r.sem_live_confidence for r in rows if r.sem_live_confidence is not None]
    sem_target_values = [r.sem_feedback_target for r in rows if r.sem_feedback_target is not None]

    duration_s = max(r.elapsed_s for r in rows) - min(r.elapsed_s for r in rows)
    return {
        "duration_s": round(duration_s, 3),
        "row_count": len(rows),
        "valid_rr_count": len(valid),
        "artifact_count": len(rows) - len(valid),
        "artifact_ratio": safe_div(len(rows) - len(valid), len(rows)),
        "reward_row_count": len(reward_rows),
        "reward_count": max((r.reward_count for r in rows), default=0),
        "mean_bpm": _mean_or_none(bpm_values),
        "mean_rmssd_30s": _mean_or_none(rmssd_values),
        "mean_hrv_amplitude_60s": _mean_or_none(amp_values),
        "mean_coherence_90s": _mean_or_none(coherence_values),
        "median_dominant_frequency_bpm": _median_or_none(dom_values),
        "best_score": max(score_values) if score_values else None,
        "mean_score": _mean_or_none(score_values),
        "mean_sem_autonomic_flexibility": _mean_or_none(sem_af_values),
        "mean_sem_measurement_quality": _mean_or_none(sem_mq_values),
        "mean_sem_training_response": _mean_or_none(sem_tr_values),
        "mean_sem_integrated_self_regulation": _mean_or_none(sem_isr_values),
        "mean_sem_latent_alignment": _mean_or_none(sem_align_values),
        "mean_sem_live_confidence": _mean_or_none(sem_conf_values),
        "mean_sem_feedback_target": _mean_or_none(sem_target_values),
    }


def _mean_or_none(values: list[float | None]) -> Optional[float]:
    arr = np.asarray([v for v in values if v is not None and math.isfinite(float(v))], dtype=float)
    if arr.size == 0:
        return None
    return float(np.mean(arr))


def _median_or_none(values: list[float | None]) -> Optional[float]:
    arr = np.asarray([v for v in values if v is not None and math.isfinite(float(v))], dtype=float)
    if arr.size == 0:
        return None
    return float(np.median(arr))


def coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        x = float(value)
        if math.isfinite(x):
            return x
    except Exception:
        pass
    return default
