"""airfare: links. Opening airfare:dashboard, airfare:history or airfare:settings starts AirFare (through
AirFare.exe on Windows, `python -m airfare link` on Linux) and shows that page live, so notifications and pages
opened from disk always reach working tabs. airfare:start only starts AirFare; a page opened from disk then
switches to Settings in its own browser tab.

The link type is registered for the current user only (no admin rights), again on every start so it follows
the folder if AirFare moves: in the registry on Windows, as AirFare's desktop entry (x-scheme-handler/airfare)
on Linux. Without AirFare.exe, or on Linux without AirFare's .venv (a developer checkout), nothing is
registered and notifications open the dashboard file instead. macOS registers no link type (that takes an app
bundle): notifications open the dashboard file, and a page opened from disk asks to start AirFare from its
icon when the local server isn't running.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from . import platform
from .config import PROJECT_DIR

log = logging.getLogger(__name__)

SCHEME = "airfare"
LAUNCHER = PROJECT_DIR / "AirFare.exe"
KEY = rf"Software\Classes\{SCHEME}"
_registered: bool | None = None


def register() -> bool:
    global _registered
    if _registered is None:
        _registered = False
        if not platform.WINDOWS:
            _registered = _register_desktop_entry()
        elif LAUNCHER.exists():
            try:
                import winreg
                hkcu, sz = winreg.HKEY_CURRENT_USER, winreg.REG_SZ
                with winreg.CreateKey(hkcu, KEY) as k:
                    winreg.SetValueEx(k, "", 0, sz, "URL:AirFare")
                    winreg.SetValueEx(k, "URL Protocol", 0, sz, "")
                with winreg.CreateKey(hkcu, KEY + r"\DefaultIcon") as k:
                    winreg.SetValueEx(k, "", 0, sz, f'"{LAUNCHER}",0')
                with winreg.CreateKey(hkcu, KEY + r"\shell\open\command") as k:
                    winreg.SetValueEx(k, "", 0, sz, f'"{LAUNCHER}" "%1"')
                _registered = True
            except OSError as e:
                log.warning("couldn't register airfare: links: %s", e)
    return _registered


def _register_desktop_entry() -> bool:
    """Linux: AirFare's desktop entry, which opens airfare: links, made the handler for them (xdg-mime)."""
    if not platform.LINUX or not platform.venv_python(PROJECT_DIR).exists():
        return False
    try:
        entry = platform.add_app_entry(PROJECT_DIR)
        mime = f"x-scheme-handler/{SCHEME}"
        current = subprocess.run(["xdg-mime", "query", "default", mime], capture_output=True, text=True, timeout=20)
        if current.stdout.strip() != entry.name:
            subprocess.run(["xdg-mime", "default", entry.name, mime], check=True, capture_output=True, timeout=20)
            subprocess.run(["update-desktop-database", str(entry.parent)], capture_output=True, timeout=20)
        return True
    except (OSError, subprocess.SubprocessError) as e:
        log.warning("couldn't register airfare: links: %s", e)
        return False


def unregister() -> None:
    if not platform.WINDOWS:
        if platform.LINUX:
            platform.app_entry_path().unlink(missing_ok=True)
        return
    import winreg
    for sub in (r"\shell\open\command", r"\shell\open", r"\shell", r"\DefaultIcon", ""):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, KEY + sub)
        except OSError:
            pass


def for_dashboard(path: Path) -> str | Path:
    """What a notification opens for the dashboard: the live page when airfare: links work, else the file."""
    return f"{SCHEME}:dashboard" if register() else path
