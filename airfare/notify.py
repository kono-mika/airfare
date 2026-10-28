"""Notifications. On Windows, toasts through PowerShell's WinRT bridge, so no extra packages are needed; on macOS
and Linux, the system's own notifications (see platform.notify)."""
from __future__ import annotations

import base64
import logging
import re
import subprocess
from pathlib import Path
from xml.sax.saxutils import escape

from . import platform
from .config import PROJECT_DIR

log = logging.getLogger(__name__)

# Toasts appear under AirFare's name and icon: the app id is registered per user in the registry (no admin,
# no installer needed). If that fails, Windows PowerShell's own registered id still gets the toast shown.
APP_ID = "AirFare.FlightPrices"
APP_KEY = rf"Software\Classes\AppUserModelId\{APP_ID}"
FALLBACK_APP_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"
ICON = PROJECT_DIR / "assets" / "airfare-256.png"
_app_id: str | None = None


def app_id() -> str:
    """Register AirFare as a notification sender (again, if the folder moved) and return the id to use."""
    global _app_id
    if _app_id is None:
        try:
            import winreg
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, APP_KEY) as k:
                winreg.SetValueEx(k, "DisplayName", 0, winreg.REG_SZ, "AirFare")
                if ICON.exists():
                    winreg.SetValueEx(k, "IconUri", 0, winreg.REG_SZ, str(ICON))
                winreg.SetValueEx(k, "IconBackgroundColor", 0, winreg.REG_SZ, "FF0E8F8B")
            _app_id = APP_ID
        except OSError as e:
            log.warning("couldn't register AirFare for notifications, using PowerShell's: %s", e)
            _app_id = FALLBACK_APP_ID
    return _app_id


def unregister() -> None:
    try:
        import winreg
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, APP_KEY)
    except OSError:
        pass


def _attr(s: str) -> str:
    return escape(re.sub(r"[\x00-\x1f\x7f]+", " ", str(s)), {'"': "&quot;"})


def _uri(target: Path | str) -> str:
    """Toast buttons and clicks open URIs: web and airfare: links as they are, local files as file:/// URIs."""
    text = str(target)
    return text if text.startswith(("http://", "https://", "airfare:")) else Path(target).resolve().as_uri()


def _text(s: str, limit: int = 300) -> str:
    """Toast text on one line: route names, prices and the analyst's words never carry control characters."""
    return escape(re.sub(r"[\x00-\x1f\x7f]+", " ", str(s)).strip()[:limit])


def _show(xml: str) -> bool:
    # The XML travels base64-encoded, so nothing in it (route names, prices, the analyst's text) can end the
    # string early and run as PowerShell.
    payload = base64.b64encode(xml.encode("utf-8")).decode()
    script = (
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null\n"
        "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null\n"
        "$xml = New-Object Windows.Data.Xml.Dom.XmlDocument\n"
        f"$xml.LoadXml([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{payload}')))\n"
        "$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)\n"
        f"[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{app_id()}').Show($toast)\n"
    )
    encoded = base64.b64encode(script.encode("utf-16-le")).decode()
    try:
        r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                           capture_output=True, text=True, timeout=30, creationflags=platform.NO_WINDOW)
    except Exception as e:
        log.warning("toast failed: %s", e)
        return False
    if r.returncode != 0:
        log.warning("toast failed: %s", (r.stderr or r.stdout).strip()[:300])
        return False
    return True


def toast(title: str, body: str, open_path: Path | str | None = None) -> bool:
    """A normal notification: shows for a few seconds, then waits in the notification centre."""
    if not platform.WINDOWS:
        return platform.notify(title, [body], _uri(open_path) if open_path else None, icon=ICON)
    launch = f' activationType="protocol" launch="{_attr(_uri(open_path))}"' if open_path else ""
    return _show(f"<toast{launch}><visual><binding template=\"ToastGeneric\">"
                 f"<text>{_text(title)}</text><text>{_text(body)}</text>"
                 f"</binding></visual></toast>")


def alert(title: str, lines: list[str], buttons: list[tuple[str, Path | str]],
          open_path: Path | str | None = None, dismiss: str = "Dismiss") -> bool:
    """A LOW PRICE alert: stays on screen until dismissed (Windows' reminder style), with a sound and
    buttons that open links. Up to two extra text lines are shown under the title. (On macOS and Linux, see
    platform.notify for what of this each system can show.)"""
    if not platform.WINDOWS:
        return platform.notify(title, lines, _uri(open_path) if open_path else None,
                               [(label, _uri(target)) for label, target in buttons], urgent=True, icon=ICON)
    texts = "".join(f"<text>{_text(t)}</text>" for t in [title, *[l for l in lines if l]][:3])
    actions = "".join(f'<action content="{_attr(label)}" activationType="protocol" arguments="{_attr(_uri(target))}"/>'
                      for label, target in buttons)
    actions += f'<action content="{_attr(dismiss)}" activationType="system" arguments="dismiss"/>'
    launch = f' activationType="protocol" launch="{_attr(_uri(open_path))}"' if open_path else ""
    xml = (f'<toast scenario="reminder"{launch}><visual><binding template="ToastGeneric">{texts}</binding></visual>'
           f'<actions>{actions}</actions><audio src="ms-winsoundevent:Notification.Reminder"/></toast>')
    return _show(xml) or toast(title, " · ".join(l for l in lines if l), open_path)
