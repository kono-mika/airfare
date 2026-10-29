"""Updates that never lose data: which AirFare wrote the data folder, and bringing an older one up to date.

data/version.json says which AirFare last brought the folder up to date and in which format ("schema"):
{"app": "1.5.0", "schema": 2, "updated": "2026-10-30T12:00:00"}. A folder without it was written by 1.4.1,
the first public release (schema 1).

ensure() runs at every start, before anything reads the data (__main__.py, the install scripts). Under a file
lock, so two AirFare processes never migrate at once, it backs the data up to data/backups/<old version>-
<YYYYMMDD-HHMM>/ and then runs every step newer than the folder's schema, in order. Each step is idempotent: run
twice, the second run changes nothing. If a step fails, the backup is copied back, so the data is as it was.
Data written by a newer AirFare (the user went back to an older release) is never migrated or rewritten here.

Adding a step: bump SCHEMA, add the function to STEPS under the new number, and describe it in CHANGELOG.md.
A step may rename or convert stored keys; it never changes route ids, and it leaves fields it doesn't know alone.
"""
from __future__ import annotations

import logging
import re
import shutil
import time
from datetime import datetime
from pathlib import Path

from . import __version__, platform
from .config import ALERT_KINDS, DATA_DIR, LOGS_DIR, read_json, write_json

log = logging.getLogger("airfare.migrate")

SCHEMA = 2
FIRST = {"app": "1.4.1", "schema": 1}          # what a folder without version.json holds
VERSION_NAME = "version.json"
BACKUPS_NAME = "backups"
LOCK_NAME = "migrate.lock"
# Everything a step may change. Reports and logs are never rewritten, so they aren't copied.
BACKUP_FILES = ("config.json", "state.json", "history.json", "price_history.json", "price_research.json",
                "dashboard.json", "rates.json")
BACKUP_FOLDERS = ("openai", "deepseek")
KEEP_BACKUPS = 3
LOCK_WAIT = 120                                  # seconds to wait for another process's migration
BACKUP_RE = re.compile(r"^(?P<app>[0-9][0-9A-Za-z.\-]*?)-(?P<stamp>\d{8}-\d{4})(?:-(?P<n>\d+))?$")


class MigrationError(RuntimeError):
    """A step failed; the data was put back as it was before the update."""


def parse(version: str) -> tuple[int, ...]:
    """(1, 5, 0) from "1.5.0"; letters after the numbers are ignored."""
    return tuple(int(n) for n in re.findall(r"\d+", str(version or ""))[:4]) or (0,)


# ----- the steps, one per schema number ------------------------------------------------------------------

def _alert_kinds(data: Path) -> None:
    """Schema 2. Settings from before alerts had kinds kept one minimum drop for everything (min_drop_percent):
    it becomes the three kinds, each with that drop. Settings with kinds already, as 1.4.1 writes them, stay as
    they are; so do the API keys (still encrypted: the file is changed as stored) and every other field."""
    path = data / "config.json"
    cfg = read_json(path, None)
    if not isinstance(cfg, dict) or "min_drop_percent" not in cfg:
        return
    drop = cfg.pop("min_drop_percent")
    if not isinstance(cfg.get("alerts"), dict) and drop is not None:
        cfg["alerts"] = {kind: {"on": True, "drop": drop, "max": None} for kind in ALERT_KINDS}
    write_json(path, cfg, mode=0o600)


STEPS = {2: _alert_kinds}


# ----- the version record -----------------------------------------------------------------------------------

def read_version(data: Path | None = None) -> dict:
    """{"app", "schema", "updated"} of the data folder; FIRST when it has no (readable) version.json."""
    data = Path(data or DATA_DIR)
    v = read_json(data / VERSION_NAME, None)
    if not isinstance(v, dict) or not isinstance(v.get("schema"), int) or isinstance(v.get("schema"), bool):
        return dict(FIRST)
    return {"app": str(v.get("app") or FIRST["app"]), "schema": v["schema"], "updated": v.get("updated")}


def _write_version(data: Path) -> None:
    write_json(data / VERSION_NAME, {"app": __version__, "schema": SCHEMA,
                                     "updated": datetime.now().isoformat(timespec="seconds")})


def newer(found: dict) -> bool:
    """Whether a newer AirFare wrote this data (the user went back to an older release)."""
    return found["schema"] > SCHEMA or parse(found["app"]) > parse(__version__)


def _due(found: dict) -> bool:
    return not newer(found) and (found["schema"] < SCHEMA or parse(found["app"]) < parse(__version__))


def status(data: Path | None = None) -> dict:
    """What Settings and doctor show: {"app", "schema", "current", "newer", "message"}."""
    found = read_version(data)
    is_newer = newer(found)
    return {"app": found["app"], "schema": found["schema"], "current": __version__, "newer": is_newer,
            "message": NEWER_MESSAGE.format(version=found["app"]) if is_newer else None}


NEWER_MESSAGE = "This data was written by AirFare {version}; install that version or newer"


# ----- backups ----------------------------------------------------------------------------------------------

def _size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def list_backups(data: Path | None = None) -> list[dict]:
    """The backups in data/backups, newest first: {"name", "app", "created", "bytes"}. Folders that aren't
    AirFare's backups (another name) aren't listed, and nothing here ever deletes them."""
    folder = Path(data or DATA_DIR) / BACKUPS_NAME
    out = []
    for d in folder.iterdir() if folder.is_dir() else []:
        m = BACKUP_RE.match(d.name)
        if not (d.is_dir() and m):
            continue
        created = datetime.strptime(m["stamp"], "%Y%m%d-%H%M").isoformat(timespec="minutes")
        out.append({"name": d.name, "app": m["app"], "created": created, "bytes": _size(d),
                    "_order": (m["stamp"], int(m["n"] or 1), d.stat().st_mtime_ns)})
    out.sort(key=lambda b: b["_order"], reverse=True)
    return [{k: v for k, v in b.items() if k != "_order"} for b in out]


def delete_backups(names: list[str] | None = None, everything: bool = False, data: Path | None = None) -> int:
    """Delete these backups (by name, as list_backups gives them), or all of them. Returns how many went."""
    folder = Path(data or DATA_DIR) / BACKUPS_NAME
    known = {b["name"] for b in list_backups(data)}
    wanted = known if everything else {n for n in names or [] if n in known}
    gone = 0
    for name in sorted(wanted):
        try:
            shutil.rmtree(folder / name)
            gone += 1
        except OSError as e:
            log.warning("couldn't delete the backup %s: %s", name, e)
    return gone


def _stored(data: Path) -> tuple[list[Path], list[Path]]:
    """The files and folders a step may change that this data folder has."""
    return ([data / n for n in BACKUP_FILES if (data / n).is_file()],
            [data / n for n in BACKUP_FOLDERS if (data / n).is_dir()])


def backup(data: Path, old_app: str) -> Path | None:
    """Copy what a step may change to data/backups/<old version>-<YYYYMMDD-HHMM>/ and keep the newest
    KEEP_BACKUPS. None when there is nothing to copy (a new data folder)."""
    files, folders = _stored(data)
    if not files and not folders:
        return None
    root = data / BACKUPS_NAME
    stamp = f"{re.sub(r'[^0-9A-Za-z.]', '', old_app) or 'old'}-{datetime.now():%Y%m%d-%H%M}"
    name, n = stamp, 1
    while (root / name).exists() or (root / f"{name}.partial").exists():
        n += 1
        name = f"{stamp}-{n}"
    partial = root / f"{name}.partial"          # renamed when complete: a half-made copy is never listed
    partial.mkdir(parents=True)
    for f in files:
        shutil.copy2(f, partial / f.name)
    for d in folders:
        shutil.copytree(d, partial / d.name)
    target = root / name
    partial.rename(target)
    for old in list_backups(data)[KEEP_BACKUPS:]:
        delete_backups([old["name"]], data=data)
    return target


def restore(saved: Path, data: Path) -> None:
    """Put the backed-up files back into the data folder."""
    for f in saved.iterdir():
        if f.is_file():
            shutil.copy2(f, data / f.name)
        elif f.is_dir():
            shutil.copytree(f, data / f.name, dirs_exist_ok=True)


# ----- the migration ----------------------------------------------------------------------------------------

def _lock(data: Path) -> platform.FileLock:
    lock = platform.FileLock(data / LOCK_NAME)
    deadline = time.monotonic() + LOCK_WAIT
    while not lock.acquire():
        if time.monotonic() > deadline:
            raise MigrationError("Another AirFare is updating the data folder. Try again in a minute.")
        time.sleep(0.2)
    return lock


def ensure(data: Path | None = None) -> dict:
    """Bring the data folder up to date (see the module's description). Returns {"from", "to", "steps",
    "backup", "newer"}; raises MigrationError when a step fails, after putting the data back."""
    data = Path(data or DATA_DIR)
    found = read_version(data)
    result = {"from": found, "to": found, "steps": [], "backup": None, "newer": newer(found)}
    if not _due(found):
        return result
    data.mkdir(parents=True, exist_ok=True)
    lock = _lock(data)
    try:
        found = read_version(data)            # another process may have finished while this one waited
        result.update({"from": found, "to": found, "newer": newer(found)})
        if not _due(found):
            return result
        steps = [n for n in sorted(STEPS) if n > found["schema"]]
        if not (data / VERSION_NAME).exists() and not any(_stored(data)):
            steps = []                        # a new data folder: nothing to bring up to date, only to record
        saved = backup(data, found["app"]) if steps else None
        for n in steps:
            try:
                STEPS[n](data)
            except Exception as e:
                if saved:
                    restore(saved, data)
                log.exception("updating the data to schema %d failed; it was put back as it was", n)
                raise MigrationError(f"Updating the data folder to AirFare {__version__} failed ({e}). "
                                     "It was put back as it was.") from e
        _write_version(data)
        result.update({"to": read_version(data), "steps": steps, "backup": str(saved) if saved else None})
        if steps:
            log.info("data updated from AirFare %s (schema %d) to %s (schema %d)%s", found["app"], found["schema"],
                     __version__, SCHEMA, f"; backup in {saved}" if saved else "")
        return result
    finally:
        lock.release()


def at_start() -> dict:
    """ensure() for a command that's starting: logs to AirFare's log even before the command sets up its own
    logging, and says once when the data comes from a newer AirFare."""
    handler = None
    if not logging.getLogger().handlers:
        try:
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            handler = logging.FileHandler(LOGS_DIR / "airfare.log", encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
            log.addHandler(handler)
            log.setLevel(logging.INFO)
        except OSError:
            handler = None
    try:
        result = ensure()
        if result["newer"]:
            log.warning("%s (this is %s): the data is used as it is and never migrated",
                        NEWER_MESSAGE.format(version=result["from"]["app"]), __version__)
        return result
    finally:
        if handler:
            log.removeHandler(handler)
            handler.close()
