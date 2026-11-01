"""Extracting a new AirFare over the old folder: what the install scripts do around pip so it just works.

    python -m airfare.upgrade prepare    before pip: stop the previous version's background checker and Settings
                                         server, and delete files the previous version left in the code folders
    python -m airfare.upgrade finish     after pip and the data migration: record what is installed, and start
                                         the background checker again when the settings need it

What is installed is recorded in .venv/airfare-install.json: {"app": version, "requirements": SHA-256 of
requirements.txt}. AirFare.exe compares it with the code and runs the update when they differ; `python -m airfare`
says what to run (mismatch()).

While an install script runs it holds .venv/airfare-install.lock, so AirFare.exe and `python -m airfare` say that
AirFare is being updated instead of starting anything (updating()). On Windows the lock is the script's exclusive
handle on the file; on macOS and Linux, where no lock command is everywhere, the file holds the script's process id.

`prepare` runs with the previous version's packages, so this module uses only the standard library and the
parts of AirFare that do too (config, platform). It never touches data/ or .venv/.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import signal
import socket
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from . import __version__, platform
from .config import CONFIG_FILE, DATA_DIR, LOGS_DIR, PROJECT_DIR, WEBUI_PORT, read_json, write_json
from .i18n import tr

log = logging.getLogger("airfare.upgrade")

UNFINISHED = 5                                 # python -m airfare's exit code when the setup doesn't match the code
UPDATING = 6                                   # its exit code while an install script is running
RECORD_NAME = "airfare-install.json"           # in .venv: it goes when the environment goes
INSTALL_LOCK = "airfare-install.lock"          # in .venv: held by install.ps1 and install.sh for their whole run
INSTALLER_ENV = "AIRFARE_INSTALLER"            # set for the background checker the installer itself starts
LOCK_MAX_AGE = 3 * 3600                        # seconds: an older lock file names a process id used again by another
BEING_UPDATED = "AirFare is being updated, try again in a few minutes"
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
    if not rec and (root / ".git").exists():
        return None                            # no install record in a git checkout: a developer's setup
    how = "Run AirFare.exe --install" if platform.WINDOWS else "Run sh install.sh"
    return (f"AirFare {__version__} is in this folder, but its setup is from "
            f"{'AirFare ' + rec['app'] if rec.get('app') else 'an earlier version'}. {how} to finish the update.")


def _alive(pid: int) -> bool:
    """macOS and Linux (on Windows, os.kill with 0 would send Ctrl+C)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except (OSError, OverflowError):
        return False
    return True


def updating(root: Path = PROJECT_DIR) -> bool:
    """Whether an install script is working on this folder right now. A crash never leaves it locked: Windows lets
    go of a dead process's handle, and elsewhere the process id in the file is no longer running."""
    if os.environ.get(INSTALLER_ENV):
        return False                           # started by that install script
    path = root / ".venv" / INSTALL_LOCK
    if platform.WINDOWS:
        try:
            open(path, "rb").close()
        except PermissionError:
            return True                        # in use: the script opened it for itself alone
        except OSError:
            pass
        return False
    try:
        pid = int(path.read_text(encoding="ascii").strip())
        fresh = time.time() - path.stat().st_mtime < LOCK_MAX_AGE
    except (OSError, ValueError):
        return False
    return pid > 1 and fresh and _alive(pid)


def tell_desktop(text: str | None = None) -> None:
    """Whatever started AirFare (the login entry, the app menu, a shortcut) may have no terminal to show why it
    stopped, so a notification says it too: by default, how to finish the update. In the language picked in Settings;
    nothing here migrates or loads the settings, since this runs before the update is finished."""
    stored = read_json(CONFIG_FILE, {})
    lang = stored.get("language") if isinstance(stored, dict) else None
    if text is None:
        text = (tr("Run AirFare.exe --install in the AirFare folder to finish the update", lang) if platform.WINDOWS
                else tr("Run sh install.sh in the AirFare folder to finish the update", lang))
    else:
        text = tr(text, lang)
    if not platform.WINDOWS:
        platform.notify("AirFare", [text])
    else:
        from . import notify                   # only what comes with Python, like this module
        if not notify.toast("AirFare", text):
            platform.message_box("AirFare", text)


def other_folder_name(root: Path = PROJECT_DIR) -> bool:
    """Whether this folder has another name than the one the zip's top folder has: extracting next to it then makes
    a new folder instead of updating this one. Windows and macOS folders ignore capitals."""
    same_name = str.casefold if platform.WINDOWS or platform.MACOS else str
    return same_name(root.name) != same_name("AirFare")


def note(text: str) -> None:
    """One line in AirFare's log, for a process that has no logging set up (and maybe no console)."""
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOGS_DIR / "airfare.log", "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} WARNING airfare.upgrade: {text}\n")
    except OSError:
        pass


# ----- files left over from the previous version ------------------------------------------------------------

def read_manifest(root: Path) -> set[str] | None:
    """The files MANIFEST.txt lists, or None unless it is whole and belongs to this code: its first line names this
    version, and its last line counts the files. (A zip writes it first, so an unzip that stopped has either the new
    manifest with files missing, or an old one with another version; a manifest cut short has no last line.)"""
    try:
        lines = (root / MANIFEST_NAME).read_text(encoding="utf-8").splitlines()
    except (OSError, ValueError):
        return None
    first = re.match(r"# AirFare (\S+?):", lines[0]) if lines else None
    end = re.fullmatch(r"# end: (\d+) files", lines[-1].strip()) if lines else None
    named = [line.strip().replace("\\", "/") for line in lines if line.strip() and not line.startswith("#")]
    if not (first and end) or first.group(1) != __version__ or int(end.group(1)) != len(named):
        log.warning("MANIFEST.txt isn't this version's whole list: nothing deleted")
        return None
    return set(named)


def _linked(path: Path) -> bool:
    """A symbolic link, a Windows junction or any other reparse point: what it holds lives somewhere else."""
    try:
        attributes = os.lstat(path)
    except OSError:
        return True                            # can't tell, so hands off
    return (stat.S_ISLNK(attributes.st_mode) or os.path.isjunction(path)
            or bool(getattr(attributes, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT))


def remove_leftovers(root: Path = PROJECT_DIR, data: Path = DATA_DIR) -> list[str]:
    """Delete the files in CODE_FOLDERS that MANIFEST.txt doesn't list, and the folders that leaves empty.

    Nothing happens without a whole manifest of this version (a copy that didn't come from a release zip), in a
    git checkout, or when a listed file is missing (an unzip that didn't finish: better to keep everything). data/
    and .venv/ are never touched, even when they sit inside a code folder. Links and junctions are never followed
    or deleted through, and a file is deleted only when it really is inside its code folder."""
    if not (root / MANIFEST_NAME).is_file() or (root / ".git").exists():
        return []
    listed = read_manifest(root)
    if not listed or "airfare/__init__.py" not in listed:
        return []
    missing = sorted(n for n in listed if not (root / n).is_file())
    # Windows and macOS folders ignore capitals: a file the release only renamed that way is still that file.
    same_name = str.casefold if platform.WINDOWS or platform.MACOS else str
    listed = {same_name(n) for n in listed}
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
        if not base.is_dir() or _linked(base) or protected(base):
            continue
        inside = base.resolve()
        visited = []
        for here, dirs, files in os.walk(base, topdown=True, followlinks=False):
            dirs[:] = [d for d in dirs if not _linked(Path(here) / d) and not protected(Path(here) / d)]
            visited += [Path(here) / d for d in dirs]
            for name in files:
                path = Path(here) / name
                rel = path.relative_to(root).as_posix()
                try:
                    if same_name(rel) in listed or protected(path) or not path.resolve().is_relative_to(inside):
                        continue
                    path.unlink()
                    removed.append(rel)
                except OSError as e:
                    log.warning("couldn't delete %s: %s", rel, e.strerror or type(e).__name__)
        for path in reversed(visited):         # deepest first
            try:
                path.rmdir()                   # only when empty
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
    try:
        if lock.acquire():
            lock.release()
            return False
    except OSError:
        pass                                   # can't take it, as when another process holds it
    return True


def _run_text(cmd: list[str]) -> str | None:
    try:
        # (LC_ALL: without a UTF-8 locale, ps on a Mac writes a folder name's other alphabets as escapes.)
        env = {**os.environ, "LC_ALL": "en_US.UTF-8"} if platform.MACOS else None
        r = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace", timeout=30,
                           creationflags=platform.NO_WINDOW, env=env)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def command_line(pid: int) -> str | None:
    """How this process was started, as one line; None when that can't be read (it is gone, or not ours to read)."""
    if platform.WINDOWS:
        # In UTF-8, so a folder name in any alphabet comes through; the process id is a checked int.
        script = ("[Console]::OutputEncoding = [Text.Encoding]::UTF8; "
                  f"(Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}').CommandLine")
        return _run_text(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script])
    if platform.MACOS:
        return _run_text(["ps", "-o", "command=", "-p", str(int(pid))])
    try:
        return Path(f"/proc/{int(pid)}/cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
    except OSError:
        return None


def _names_environment(text: str, root: Path) -> bool:
    """Whether this text runs a program of this folder's .venv, as a whole path (not one that only ends the same)."""
    def form(value: str) -> str:
        return value.replace("\\", "/").casefold() if platform.WINDOWS else value
    return any(re.search(r"(?:^|[\s\"'=])" + re.escape(form(str(r / ".venv"))) + "/", form(text))
               for r in dict.fromkeys((root, root.resolve())))


def is_checker(pid: int, root: Path = PROJECT_DIR) -> bool:
    """Whether this process is AirFare's background checker from this folder. A process id from a file may by now
    belong to anything: a process that isn't confirmed here is never stopped."""
    if pid <= (4 if platform.WINDOWS else 1):
        return False
    text = command_line(pid)
    if not text or not re.search(r"(?:^|\s)-m\s+airfare\s+service(?:\s|$)", text.strip()):
        return False
    if _names_environment(text, root):
        return True
    # A Python from python.org or Homebrew on a Mac starts its real program, which shows another path; the
    # environment it came from is still in what it was started with.
    return platform.MACOS and _names_environment(_run_text(["ps", "-E", "-o", "command=", "-p", str(int(pid))]) or "", root)


def stop_checker(data: Path = DATA_DIR, wait: float = 30, root: Path = PROJECT_DIR) -> bool:
    """Stop the background checker that runs the previous version's code. True when one was stopped; False with it
    still running when it can't be confirmed as AirFare's checker from this folder (prepare() says what to do)."""
    if not _checker_running(data):
        return False
    pid = (read_json(data / "service.json", {}) or {}).get("pid")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid == os.getpid():
        log.warning("a background checker runs, but its process id isn't known")
        return False
    if not is_checker(pid, root):
        log.warning("process %d isn't confirmed as this folder's background checker, so it wasn't stopped", pid)
        return False
    if not _checker_running(data):             # it quit by itself in the meantime: that id may soon mean nothing
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
    code = 0
    if stop_checker():
        print("Stopped the background checker of the previous version.")
    elif _checker_running(DATA_DIR):
        print("A background checker is still running and couldn't be stopped safely. "
              "Quit AirFare by hand (tray icon, Quit AirFare).")
        code = 1
    if stop_settings_server():
        print("Closed the Settings page server of the previous version.")
    removed = remove_leftovers()
    if removed:
        print(f"Removed {len(removed)} file(s) the previous version left behind.")
    return code


def finish() -> int:
    write_record()
    from . import service                      # the new packages are installed by now
    from .config import load_config
    cfg = load_config()
    os.environ[INSTALLER_ENV] = "1"            # the checker started here runs while the install script holds its lock
    if cfg["routes"] and service.needed(cfg) and service.start_in_background():
        print("Started the background checker.")
    return 0


if __name__ == "__main__":
    steps = {"prepare": prepare, "finish": finish}
    if len(sys.argv) != 2 or sys.argv[1] not in steps:
        print("usage: python -m airfare.upgrade prepare|finish", file=sys.stderr)
        sys.exit(2)
    sys.exit(steps[sys.argv[1]]())
