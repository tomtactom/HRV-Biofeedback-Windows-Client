"""Windows, display and OS integration helpers for HRV Biofeedback.

The functions in this module are intentionally low-risk. They do not modify
Windows settings by themselves. They collect local state, open standard Windows
settings pages on request, and help the Qt UI adapt to screen size, scaling and
multi-monitor setups.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import base64
import json
import os
import platform
import subprocess
import sys


WINDOWS_SETTINGS_URIS = {
    "bluetooth": "ms-settings:bluetooth",
    "display": "ms-settings:display",
    "sound": "ms-settings:sound",
    "privacy": "ms-settings:privacy",
}


@dataclass
class ScreenInfo:
    name: str
    primary: bool
    geometry: dict[str, int]
    available_geometry: dict[str, int]
    device_pixel_ratio: float
    logical_dpi: float
    physical_dpi: float


def is_windows() -> bool:
    return sys.platform.startswith("win")


def configure_qt_for_windows() -> None:
    """Prepare Qt for Windows 11 high-DPI and mixed-scale monitor setups."""
    # Qt 6 handles High-DPI automatically, but these environment variables make
    # the behavior explicit for Conda/embedded launch contexts.
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")
    os.environ.setdefault("QT_SCALE_FACTOR_ROUNDING_POLICY", "PassThrough")

    try:  # Qt must be imported lazily so this can be called before QApplication.
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtCore import Qt

        if hasattr(Qt, "HighDpiScaleFactorRoundingPolicy"):
            QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
                Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
            )
    except Exception:
        # DPI configuration is best-effort; the app can still run without it.
        pass


def safe_subprocess(cmd: list[str], timeout_s: float = 6.0) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
        return {
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }
    except Exception as exc:  # pragma: no cover - OS dependent
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def powershell_json(command: str, timeout_s: float = 7.0) -> dict[str, Any]:
    if not is_windows():
        return {"ok": False, "reason": "not_windows"}
    ps = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command"]
    return safe_subprocess(ps + [command], timeout_s=timeout_s)


def collect_windows_bluetooth_snapshot() -> dict[str, Any]:
    """Collect Windows Bluetooth state without changing any settings."""
    if not is_windows():
        return {"platform": platform.platform(), "available": False, "reason": "not_windows"}

    return {
        "platform": platform.platform(),
        "available": True,
        "bthserv": powershell_json(
            "Get-Service bthserv | Select-Object Status,Name,DisplayName,StartType | ConvertTo-Json -Compress"
        ),
        "device_association_service": powershell_json(
            "Get-Service DeviceAssociationService | Select-Object Status,Name,DisplayName,StartType | ConvertTo-Json -Compress"
        ),
        "bluetooth_pnp": powershell_json(
            "Get-PnpDevice -Class Bluetooth | Select-Object Status,FriendlyName,InstanceId,Problem | ConvertTo-Json -Compress"
        ),
        "radio_adapter": powershell_json(
            "Get-CimInstance Win32_PnPEntity | Where-Object {$_.PNPClass -eq 'Bluetooth'} | "
            "Select-Object Status,Name,DeviceID,ConfigManagerErrorCode | ConvertTo-Json -Compress"
        ),
    }




def _parse_powershell_json_result(result: dict[str, Any]) -> Any:
    if not result.get("ok"):
        return None
    stdout = result.get("stdout") or ""
    if not stdout:
        return None
    try:
        return json.loads(stdout)
    except Exception:
        return None


def summarize_windows_bluetooth_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Extract a compact status summary from the raw Windows Bluetooth snapshot.

    Windows 11 often keeps Bluetooth-related services in a stopped trigger-start
    state while BLE scanning and GATT access still work normally through WinRT.
    Treat non-disabled stopped services as notes, not as warnings, when the PnP
    adapter is present.  This avoids alarming users with a false problem after a
    successful BLE scan/connection.
    """
    if not snapshot.get("available"):
        return {"available": False, "status": "not_windows", "issues": [snapshot.get("reason", "not_windows")], "notes": []}
    issues: list[str] = []
    notes: list[str] = []
    services: dict[str, Any] = {}
    for key in ("bthserv", "device_association_service"):
        parsed = _parse_powershell_json_result(snapshot.get(key, {}) or {})
        services[key] = parsed
        status = str((parsed or {}).get("Status", "")).lower() if isinstance(parsed, dict) else ""
        start_type = str((parsed or {}).get("StartType", "")).lower() if isinstance(parsed, dict) else ""
        if status and status != "running":
            if "disabled" in start_type:
                issues.append(f"{key}_disabled:{status}")
            else:
                notes.append(f"{key}_not_running_trigger_start:{status}")
    pnp = _parse_powershell_json_result(snapshot.get("bluetooth_pnp", {}) or {})
    adapters = pnp if isinstance(pnp, list) else ([pnp] if isinstance(pnp, dict) else [])
    adapter_count = len(adapters)
    if adapter_count == 0:
        issues.append("no_bluetooth_pnp_device_reported")
    else:
        bad = [a for a in adapters if isinstance(a, dict) and str(a.get("Status", "")).upper() not in {"OK", "UNKNOWN"}]
        if bad:
            issues.append("bluetooth_pnp_status_not_ok")
    status = "ok" if not issues else "warn"
    return {"available": True, "status": status, "issues": issues, "notes": notes, "services": services, "adapter_count": adapter_count}


def open_path_or_uri(target: str | Path) -> None:
    """Open a folder, file or settings URI using the host OS."""
    target_str = str(target)
    if is_windows():
        os.startfile(target_str)  # type: ignore[attr-defined]  # pragma: no cover - Windows only
    elif sys.platform == "darwin":
        subprocess.Popen(["open", target_str])
    else:
        subprocess.Popen(["xdg-open", target_str])


def open_windows_settings(kind: str) -> None:
    """Open a Windows Settings page when available; fallback to display folder."""
    uri = WINDOWS_SETTINGS_URIS.get(kind, kind)
    open_path_or_uri(uri)


def detect_windows_app_theme() -> str:
    """Return dark/light based on Windows app theme registry if available."""
    if not is_windows():
        return "light"
    try:  # pragma: no cover - Windows registry dependent
        import winreg

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return "light" if int(value) == 1 else "dark"
    except Exception:
        return "light"


def _rect_to_dict(rect: Any) -> dict[str, int]:
    return {"x": int(rect.x()), "y": int(rect.y()), "width": int(rect.width()), "height": int(rect.height())}


def collect_display_snapshot() -> dict[str, Any]:
    """Return Qt screen information useful for display/scale troubleshooting."""
    try:
        from PySide6.QtGui import QGuiApplication

        primary = QGuiApplication.primaryScreen()
        screens = []
        for screen in QGuiApplication.screens():
            screens.append(
                asdict(
                    ScreenInfo(
                        name=screen.name(),
                        primary=screen is primary,
                        geometry=_rect_to_dict(screen.geometry()),
                        available_geometry=_rect_to_dict(screen.availableGeometry()),
                        device_pixel_ratio=float(screen.devicePixelRatio()),
                        logical_dpi=float(screen.logicalDotsPerInch()),
                        physical_dpi=float(screen.physicalDotsPerInch()),
                    )
                )
            )
        return {"platform": platform.platform(), "screen_count": len(screens), "screens": screens}
    except Exception as exc:  # pragma: no cover - GUI runtime dependent
        return {"platform": platform.platform(), "error": f"{type(exc).__name__}: {exc}"}


def center_and_fit_window(window: Any, preferred_width: int = 1280, preferred_height: int = 820) -> None:
    """Fit the main window into the current screen's available geometry."""
    try:
        screen = window.screen() or window.windowHandle().screen()
        available = screen.availableGeometry()
        width = min(preferred_width, max(900, available.width() - 80))
        height = min(preferred_height, max(640, available.height() - 80))
        x = available.x() + max(0, (available.width() - width) // 2)
        y = available.y() + max(0, (available.height() - height) // 2)
        window.resize(width, height)
        window.move(x, y)
    except Exception:
        pass


def qbytearray_to_b64(value: Any) -> str:
    try:
        return base64.b64encode(bytes(value)).decode("ascii")
    except Exception:
        return ""


def b64_to_qbytearray(value: str) -> Any | None:
    if not value:
        return None
    try:
        from PySide6.QtCore import QByteArray

        return QByteArray(base64.b64decode(value.encode("ascii")))
    except Exception:
        return None
