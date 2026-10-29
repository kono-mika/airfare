"""Unzipping a new AirFare over the old folder: what the install scripts do around pip so it just works.

    python -m airfare.upgrade prepare    before pip: stop the previous version's background checker and Settings
                                         server, and delete files the previous version left in the code folders
    python -m airfare.upgrade finish     after pip and the data migration: record what is installed, and start
                                         the background checker again when the settings need it

What is installed is recorded in .venv/airfare-install.json: {"app": version, "requirements": SHA-256 of
requirements.txt}. AirFare.exe compares it with the code and runs the update when they differ; on macOS and
Linux, `python -m airfare` says to run install.sh (mismatch()).

`prepare` runs with the previous version's packages, so this module uses only the standard library and the
parts of AirFare that do too (config, platform). It never touches data/ or .venv/.
"""
from __future__ import annotations

import hashlib
import logging
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from . import __version__, platform
from .config import DATA_DIR, LOGS_DIR, PROJECT_DIR, WEBUI_PORT, read_json, write_json

log = logging.getLogger("airfare.upgrade")

RECORD_NAME = "airfare-install.json"           # in .venv: it goes when the environment goes
MANIFEST_NAME = "MANIFEST.txt"                 # every file of the release zip (tools/make_portable.py)
# The folders a release replaces whole: a file in them that the release doesn't list is left over from an
# earlier version. Nothing outside them is ever deleted (data/, .venv/, the user's own files).
CODE_FOLDERS = ("airfare", "extension", "extension-firefox", "tools", "launcher", "assets")


# ----- what is installed ------------------------------------------------------------------------------------

def requirements_hash(root: Path = PROJECT_DIR) -> str:
    try:
        return hashlib.sha256((root / "requirements.txt").read_bytes()).hexdigest()
    except OSError:
        return ""


def read_record(root: Path = PROJECT_DIR) -> dict:
    rec = read_json(root / ".venv" / RECORD_NAME, {})
    return rec if isinstance(rec, dict) else {}


def write_record(root: Path = PROJECT_DIR) -> dict:
    rec = {"app": __version__, "requirements": requirements_hash(root),
           "installed": datetime.now().isoformat(timespec="seconds")}
    write_json(root / ".venv" / RECORD_NAME, rec)
    return rec


def mismatch(root: Path = PROJECT_DIR, prefix: str | None = None) -> str | None:
    """What to say when this folder's code is newer (or older) than its setup; None when they match, or when
    this isn't AirFare's own environment (a developer's Python, the tests)."""
    try:
        ours = Path(prefix or sys.prefix).resolve() == (root / ".venv").resolve()
    except OSError:
        ours = False
    if not ours:
        return None
    rec = read_record(root)
    if rec.get("app") == __version__ and rec.get("requirements") == requirements_hash(root):
        return None
    how = "Start AirFare.exe" if platform.WINDOWS else "Run sh install.sh"
    return (f"AirFare {__version__} is in this folder, but its setup is from "
            f"{'AirFare ' + rec['app'] if rec.get('app') else 'an earlier version'}. {how} to finish the update.")


def note(text: str) -> None:
    """One line in AirFare's log, for a process that has no logging set up (and maybe no console)."""
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOGS_DIR / "airfare.log", "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} WARNING airfare.upgrade: {text}\n")
    except OSError:
        pass


# ----- files left over from the previous version ------------------------------------------------------------

def remove_leftovers(root: Path = PROJECT_DIR, data: Path = DATA_DIR) -> list[str]:
    """Delete the files in CODE_FOLDERS that MANIFEST.txt doesn't list, and the folders that leaves empty.

    Nothing happens without a manifest (a copy that didn't come from a release zip), in a git checkout, or
    when a listed file is missing (an unzip that didn't finish: better to keep everything). data/ and .venv/
    are never touched, even when they sit inside a code folder."""
    manifest = root / MANIFEST_NAME
    if not manifest.is_file() or (root / ".git").exists():
        return []
    listed = {line.strip().replace("\\", "/") for line in manifest.read_text(encoding="utf-8").splitlines()
              if line.strip() and not line.startswith("#")}
    if "airfare/__init__.py" not in listed:
        return []
    missing = sorted(n for n in listed if not (root / n).is_file())
    if missing:
        log.warning("MANIFEST.txt lists %d file(s) that aren't here (%s ...): nothing deleted", len(missing), missing[0])
        return []
    keep_out = [p.resolve() for p in (data, root / "data", root / ".venv")]

    def protected(path: Path) -> bool:
        p = path.resolve()
        return any(p == k or k in p.parents for k in keep_out)

    removed = []
    for folder in CODE_FOLDERS:
        base = root / folder
        if not base.is_dir() or base.is_symlink() or protected(base):
            continue
        for here, dirs, files in os.walk(base, topdown=False, followlinks=False):
            for name in files:
                path = Path(here) / name
                rel = path.relative_to(root).as_posix()
                if rel in listed or protected(path):
                    continue
                try:
                    path.unlink()
                    removed.append(rel)
                except OSError as e:
                    log.warning("couldn't delete %s: %s", rel, e)
            for name in dirs:
                path = Path(here) / name
                if not path.is_symlink() and not protected(path):
                    try:
                        path.rmdir()                # only when empty
                    except OSError:
                        pass
    return removed


# ----- the previous version's processes ---------------------------------------------------------------------

def _end(pid: int) -> None:
    """End one process (not its children: a browser AirFare opened is the user's)."""
    if platform.WINDOWS:
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, creationflags=platform.NO_WINDOW)
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass


def _checker_running(data: Path) -> bool:
    if not (data / "service.lock").exists():
        return False
    lock = platform.FileLock(data / "service.lock")
    if lock.acquire():
        lock.release()
        return False
    return True


def stop_checker(data: Path = DATA_DIR, wait: float = 30) -> bool:
    """Stop the background checker that runs the previous version's code. True when one was stopped."""
    if not _checker_running(data):
        return False
    pid = (read_json(data / "service.json", {}) or {}).get("pid")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid == os.getpid():
        log.warning("a background checker runs, but its process id isn't known")
        return False
    _end(pid)
    deadline = time.monotonic() + wait
    while _checker_running(data):
        if time.monotonic() > deadline:
            return False
        time.sleep(0.25)
    return True


def stop_settings_server(port: int = WEBUI_PORT, wait: float = 15) -> bool:
    """Ask a Settings server on AirFare's port to stop (every AirFare since 1.0 answers /api/close)."""
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/close", data=b"{}", method="POST",
                                 headers={"X-AirFare": "1", "Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=3).close()
    except (urllib.error.URLError, OSError):
        return False
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        with socket.socket() as s:
            s.settimeout(1)
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return True
        time.sleep(0.25)
    return False


# ----- the two steps the install scripts run ----------------------------------------------------------------

def prepare() -> int:
    if stop_checker():
        print("Stopped the background checker of the previous version.")
    if stop_settings_server():
        print("Closed the Settings page server of the previous version.")
    removed = remove_leftovers()
    if removed:
        print(f"Removed {len(removed)} file(s) the previous version left behind.")
    return 0


def finish() -> int:
    write_record()
    from . import service                      # the new packages are installed by now
    from .config import load_config
    cfg = load_config()
    if cfg["routes"] and service.needed(cfg) and service.start_in_background():
        print("Started the background checker.")
    return 0


if __name__ == "__main__":
    steps = {"prepare": prepare, "finish": finish}
    if len(sys.argv) != 2 or sys.argv[1] not in steps:
        print("usage: python -m airfare.upgrade prepare|finish", file=sys.stderr)
        sys.exit(2)
    sys.exit(steps[sys.argv[1]]())
