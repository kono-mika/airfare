"""The background checker that starts at login (the Startup shortcut on Windows, a LaunchAgent on macOS, an
autostart entry on Linux): checks at startup, every N hours while the PC is on, or both, as chosen in Settings.

It re-reads the settings every minute, so schedule changes apply without a restart; catches up after the
PC wakes from sleep (a check that came due while asleep runs on wake); and stops by itself when the
schedule is startup-only, unless Settings asks for the tray icon, which this process shows (see tray.py).
When the tray setting changes it restarts itself, since an icon can only be shown from the start.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime

from . import limits, platform, runner, tray
from .config import DATA_DIR, PROJECT_DIR, ensure_dirs, load_config, load_state, read_json, write_json
from .i18n import tr

log = logging.getLogger("airfare.service")

SERVICE_LOCK = DATA_DIR / "service.lock"
SERVICE_FILE = DATA_DIR / "service.json"     # status for Settings; separate from state.json, which checks write
RETRY_AFTER = 30 * 60        # seconds before retrying a check that failed (no network, robot check, ...)
TICK = 60
SCHEDULES = ("startup", "interval", "both")


def schedule(cfg: dict) -> tuple[str, float]:
    mode = cfg.get("schedule") if cfg.get("schedule") in SCHEDULES else "startup"
    return mode, max(1.0, min(48.0, float(cfg.get("interval_hours") or 6)))


def wants_tray(cfg: dict) -> bool:
    return bool(cfg.get("tray")) and tray.available()


def next_due(last_check: str | None, hours: float, started: float, last_attempt: float | None) -> float:
    """When the next interval check is due (epoch seconds)."""
    try:
        last = datetime.fromisoformat(last_check).timestamp() if last_check else started
    except ValueError:
        last = started
    due = last + hours * 3600
    if last_attempt:
        due = max(due, last_attempt + RETRY_AFTER) if last_attempt > last else due
    return due


class _Lock(platform.FileLock):
    """Only one background checker at a time; the system releases the lock if the process dies."""

    def __init__(self):
        super().__init__(SERVICE_LOCK)

    def acquire(self) -> bool:
        ensure_dirs()
        return super().acquire()


def is_running() -> bool:
    lock = _Lock()
    if lock.acquire():
        lock.release()
        return False
    return True


def start_in_background() -> bool:
    """Start the checker without its startup check (used when Settings switches to interval checks)."""
    if is_running():
        return False
    platform.start_detached([platform.background_python(), "-m", "airfare", "service", "--skip-startup-check"],
                            PROJECT_DIR)
    return True


def needed(cfg: dict) -> bool:
    """Whether the checker should stay running for these settings: interval checks, or the tray icon."""
    return schedule(cfg)[0] != "startup" or wants_tray(cfg)


def _status(**fields) -> None:
    write_json(SERVICE_FILE, {**read_json(SERVICE_FILE, {}), **fields})


def status() -> dict:
    """What Settings shows: whether the checker runs, and when the next interval check is due."""
    return {**read_json(SERVICE_FILE, {}), "running": is_running()}


def _when(iso: str | None) -> str:
    return (iso or "").replace("T", " ")


class _Checker:
    """The schedule loop, with the tray icon (if any) told what it's doing."""

    def __init__(self, icon: tray.Tray | None, started: float, max_ticks: int | None, lang: str | None):
        self.icon, self.started, self.max_ticks, self.lang = icon, started, max_ticks, lang
        self.last_attempt: float | None = None
        self.idle_until: float | None = None    # a check with nothing to do: don't try again before this
        self.stop = threading.Event()
        self.restart = False

    def say(self, text: str) -> None:
        if self.icon:
            self.icon.set_status(text)

    def check(self, automatic: bool = False) -> int:
        """A check: automatic when the schedule starts it, so the limits space out its browser pages; the tray
        icon's Check now is a manual one."""
        self.last_attempt = time.time()
        self.say(tr("Checking prices…", self.lang))
        code = runner.run(automatic=automatic)
        if code == 3:
            self.say(tr("A check is already running.", self.lang))
        self.idle_status()
        return code

    def idle_status(self, due: float | None = None) -> None:
        last = _when(load_state().get("last_check"))
        text = tr("Last check {when}.", self.lang, when=last) if last else tr("No checks yet.", self.lang)
        if due:
            text += " " + tr("Next around {when}.", self.lang, when=datetime.fromtimestamp(due).strftime("%Y-%m-%d %H:%M"))
        self.say(text)

    def loop(self, want_tray: bool) -> None:
        ticks = 0
        while not self.stop.is_set() and (self.max_ticks is None or ticks < self.max_ticks):
            ticks += 1
            cfg = load_config()
            mode, hours = schedule(cfg)
            if wants_tray(cfg) != want_tray:
                log.info("the tray setting changed; the background checker restarts")
                self.restart = True
                break
            if mode == "startup" and not want_tray:
                log.info("schedule is startup-only; the background checker stops")
                _status(pid=None, next_check=None, schedule=mode)
                break
            due = next_due(load_state().get("last_check"), hours, self.started, self.last_attempt) if mode != "startup" else None
            if due and self.idle_until:
                due = max(due, self.idle_until)
            if due and time.time() >= due:
                log.info("interval check due (every %gh)", hours)
                code = self.check(automatic=True)
                if code == 2:                       # nothing to check: the next look is one interval away
                    self.idle_until = time.time() + hours * 3600
                elif code == runner.HELD:           # only the browser sources, and the limits hold them for now
                    reopen = limits.reopens(cfg)
                    self.idle_until = reopen.timestamp() if reopen else time.time() + RETRY_AFTER
                else:
                    self.idle_until = None
                continue
            _status(pid=os.getpid(), schedule=mode,
                    next_check=datetime.fromtimestamp(due).isoformat(timespec="minutes") if due else None)
            self.idle_status(due)
            for _ in range(TICK):             # a minute, in seconds, so Quit in the tray menu is quick
                if self.stop.is_set():
                    break
                time.sleep(1)
        if self.icon:
            self.icon.stop()


def serve(skip_startup_check: bool = False, max_ticks: int | None = None) -> int:
    runner.setup_logging(False)
    lock = _Lock()
    if not lock.acquire():
        log.info("the background checker is already running")
        return 3
    started = time.time()
    cfg = load_config()
    mode, hours = schedule(cfg)
    want_tray = wants_tray(cfg)
    log.info("background checker started (schedule: %s, every %gh%s)", mode, hours, ", tray icon" if want_tray else "")
    _status(pid=os.getpid(), started=datetime.now().isoformat(timespec="minutes"), schedule=mode, next_check=None)
    icon = None
    checker = _Checker(None, started, max_ticks, cfg.get("language"))
    if want_tray:
        icon = tray.Tray(cfg.get("language"), on_check=checker.check, on_quit=checker.stop.set)
        checker.icon = icon
    if mode in ("startup", "both") and not skip_startup_check:
        if icon:
            threading.Thread(target=checker.check, args=(True,), daemon=True).start()   # the icon shows up straight away
        else:
            checker.check(automatic=True)
    if icon:
        worker = threading.Thread(target=checker.loop, args=(True,), daemon=True)
        worker.start()
        icon.run()                        # blocks until the loop ends or the user quits from the menu
        checker.stop.set()
        worker.join(timeout=5)
    else:
        checker.loop(False)
    if checker.restart or checker.stop.is_set():
        _status(pid=None, next_check=None)
    lock.release()
    if checker.restart:
        start_in_background()
    return 0
