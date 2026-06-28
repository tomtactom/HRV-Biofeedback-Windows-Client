"""Privacy, support-bundle and defensive-export helpers for HRV Biofeedback.

The app stores data locally.  When a user wants to share troubleshooting data,
this module creates a small redacted support package so BLE addresses, Windows
user names and local absolute paths are not exposed accidentally.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
import json
import re
import zipfile

MAC_ADDRESS_RE = re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b")
WINDOWS_USER_PATH_RE = re.compile(r"[A-Za-z]:\\Users\\[^\\\r\n]+")
USB_DEVICE_ID_RE = re.compile(r"\bUSB\\\\VID_[0-9A-Fa-f]{4}&PID_[0-9A-Fa-f]{4}[^\s\"']*")
BLE_RAW_HEX_RE = re.compile(r'("raw_hex"\s*:\s*")[0-9A-Fa-f]+(")')


def redact_text(text: Any, *, home: Path | None = None) -> str:
    """Return text with common local identifiers removed.

    This keeps troubleshooting useful while reducing accidental disclosure of
    BLE MAC addresses, the Windows account name and raw packet bytes.
    """
    out = str(text)
    if home is None:
        try:
            home = Path.home()
        except Exception:
            home = None
    if home:
        out = out.replace(str(home), "%USERPROFILE%")
        out = out.replace(str(home).replace("/", "\\\\"), "%USERPROFILE%")
    out = WINDOWS_USER_PATH_RE.sub(r"%USERPROFILE%", out)
    out = USB_DEVICE_ID_RE.sub("<USB_DEVICE_ID>", out)
    out = MAC_ADDRESS_RE.sub("<BLE_ADDRESS>", out)
    out = BLE_RAW_HEX_RE.sub(r'\1<RAW_HEX_REDACTED>\2', out)
    return out


def redact_obj(obj: Any) -> Any:
    """Recursively redact strings in JSON-like data."""
    if isinstance(obj, dict):
        redacted: dict[str, Any] = {}
        for key, value in obj.items():
            lowered = str(key).lower()
            if lowered in {"address", "deviceid", "device_id", "instanceid", "instance_id", "pnpdeviceid", "raw_hex"}:
                redacted[key] = "<REDACTED>"
            else:
                redacted[key] = redact_obj(value)
        return redacted
    if isinstance(obj, list):
        return [redact_obj(item) for item in obj]
    if isinstance(obj, str):
        return redact_text(obj)
    return obj


def _read_text_tail(path: Path, max_chars: int = 80_000) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return f"Could not read {path.name}: {type(exc).__name__}: {exc}"
    return text[-max_chars:]


def _latest_files(folder: Path, *, suffixes: tuple[str, ...], limit: int) -> list[Path]:
    try:
        files = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in suffixes]
    except Exception:
        return []
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)[:limit]


def create_redacted_support_bundle(
    *,
    output_path: Path,
    app_snapshot: dict[str, Any],
    debug_dir: Path,
    logs_dir: Path,
    config_path: Path | None = None,
    extra_report: dict[str, Any] | None = None,
) -> Path:
    """Create a small ZIP with redacted logs and diagnostic JSON files.

    Raw packet JSONL files are intentionally excluded by default. They can be
    inspected locally but are too identifying/noisy for a first support bundle.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "bundle_type": "redacted_support_bundle",
        "privacy_note": "Local paths, BLE addresses, USB IDs and raw packet bytes are redacted best-effort.",
    }
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        zf.writestr("app_snapshot.redacted.json", json.dumps(redact_obj(app_snapshot), ensure_ascii=False, indent=2, default=str))
        if extra_report:
            zf.writestr("latest_diagnostic.redacted.json", json.dumps(redact_obj(extra_report), ensure_ascii=False, indent=2, default=str))
        if config_path and config_path.exists():
            try:
                cfg = json.loads(config_path.read_text(encoding="utf-8"))
                zf.writestr("config.redacted.json", json.dumps(redact_obj(cfg), ensure_ascii=False, indent=2, default=str))
            except Exception:
                zf.writestr("config.redacted.txt", redact_text(_read_text_tail(config_path, 20_000)))
        for log_file in _latest_files(logs_dir, suffixes=(".log",), limit=3):
            zf.writestr(f"logs/{log_file.name}.redacted.txt", redact_text(_read_text_tail(log_file)))
        for json_file in _latest_files(debug_dir, suffixes=(".json",), limit=12):
            # Keep service/diagnostic/display JSON; skip huge raw packet-like files by name.
            if "raw_packets" in json_file.name:
                continue
            try:
                obj = json.loads(json_file.read_text(encoding="utf-8"))
                zf.writestr(f"debug/{json_file.name}.redacted.json", json.dumps(redact_obj(obj), ensure_ascii=False, indent=2, default=str))
            except Exception:
                zf.writestr(f"debug/{json_file.name}.redacted.txt", redact_text(_read_text_tail(json_file)))
    return output_path
