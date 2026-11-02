"""Updates that never lose data: which AirFare wrote the data folder, and bringing an older one up to date.

data/version.json says which AirFare last brought the folder up to date and in which format ("schema"):
{"app": "1.5.0", "schema": 2, "updated": "2026-10-30T12:00:00"}. A folder without it was written by 1.4.1,
the first public release (schema 1).

ensure() runs at every start, before anything reads the data (__main__.py, the install scripts). Under a file
lock, so two AirFare processes never migrate at once, it backs the data up to data/backups/<old version>-
<YYYYMMDD-HHMM>/ and then runs every step newer than the folder's schema, in order. Each step is idempotent: run
twice, the second run changes nothing. If a step fails, the backup is copied back, so the data is as it was, and
the next attempt uses that same backup. Only a migration that worked removes old backups, so failures never push
out an earlier version's. A version.json that is there but can't be read is left alone: the data counts as this
version's format, with a warning in the log, and nothing is migrated.
Data written by a newer AirFare (the user went back to an older release) is never migrated or rewritten here.

Adding a step: bump SCHEMA, add the function to STEPS under the new number, and describe it in CHANGELOG.md.
A step may rename or convert stored keys; it never changes route ids, and it leaves fields it doesn't know alone.
"""
from __future__ import annotations

import json
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
                "dashboard.json", "rates.json", VERSION_NAME)
BACKUP_FOLDERS = ("openai", "deepseek")
KEEP_BACKUPS = 3
LOCK_WAIT = 120                                  # seconds to wait for another process's migration
BACKUP_RE = re.compile(r"^(?P<app>[0-9][0-9A-Za-z.\-]*?)-(?P<stamp>\d{8}-\d{4})(?:-(?P<n>\d+))?$")
PARTIAL = ".partial"                             # a backup being made; renamed when complete
NAME_LENGTH = 32                                 # the most of a version text that goes into a backup's name


class MigrationError(RuntimeError):
    """Bringing the data up to date failed; the message says what state it was left in."""


def parse(version: str) -> tuple[int, ...]:
    """The numeric release only: (1, 5, 0) from "1.5.0", "1.5" and "1.5.0rc1", (0, 0, 0) from text without one."""
    found = re.match(r"\s*v?(\d+(?:\.\d+)*)", str(version or ""))
    numbers = [int(n) for n in found.group(1).split(".")[:4]] if found else []
    numbers += [0] * (3 - len(numbers))
    while len(numbers) > 3 and numbers[-1] == 0:
        numbers.pop()
    return tuple(numbers)


def _why(e: Exception) -> str:
    """What went wrong, for logs and the console: an OSError's reason, without the path it carries."""
    return (e.strerror or type(e).__name__) if isinstance(e, OSError) else str(e) or type(e).__name__


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

_warned: set[str] = set()


def _unreadable(path: Path, why: str) -> dict:
    """A version.json that can't be read says nothing about the data: it stays as it is, and the data counts as
    this version's format. Migrating on a guess could rewrite data a newer AirFare wrote."""
    if str(path) not in _warned:                 # Settings asks on every page load: say it once
        _warned.add(str(path))
        log.warning("%s can't be read (%s): it is left as it is and the data is treated as AirFare %s's format",
                    path.name, why, __version__)
    return {"app": __version__, "schema": SCHEMA, "updated": None}


def read_version(data: Path | None = None) -> dict:
    """{"app", "schema", "updated"} of the data folder; FIRST when it has no version.json."""
    path = Path(data or DATA_DIR) / VERSION_NAME
    try:
        v = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return dict(FIRST)
    except (OSError, ValueError) as e:           # not read_json: it would rename a broken file
        return _unreadable(path, _why(e))
    if not isinstance(v, dict) or not isinstance(v.get("schema"), int) or isinstance(v.get("schema"), bool):
        return _unreadable(path, "no format number")
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
    AirFare's backups (another name, or a date that doesn't exist) aren't listed, and nothing here ever deletes
    them. Raises MigrationError when the folder can't be read."""
    folder = Path(data or DATA_DIR) / BACKUPS_NAME
    out = []
    try:
        for d in folder.iterdir() if folder.is_dir() else []:
            m = BACKUP_RE.match(d.name)
            if not (d.is_dir() and m):
                continue
            try:
                created = datetime.strptime(m["stamp"], "%Y%m%d-%H%M").isoformat(timespec="minutes")
            except ValueError:
                continue
            out.append({"name": d.name, "app": m["app"], "created": created, "bytes": _size(d),
                        "_order": (m["stamp"], int(m["n"] or 1), d.stat().st_mtime_ns)})
    except OSError as e:
        log.error("couldn't read the backups: %s", _why(e))
        raise MigrationError(f"Couldn't read the backups in the data folder ({_why(e)}).") from e
    out.sort(key=lambda b: b["_order"], reverse=True)
    return [{k: v for k, v in b.items() if k != "_order"} for b in out]


def delete_backups(names: list[str] | None = None, everything: bool = False, data: Path | None = None) -> int:
    """Delete these backups (by name, as list_backups gives them), or all of them. Returns how many went."""
    folder = Path(data or DATA_DIR) / BACKUPS_NAME
    try:
        known = {b["name"] for b in list_backups(data)}
    except MigrationError:
        return 0
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


def _tree(folder: Path) -> dict[str, Path]:
    return {p.relative_to(folder).as_posix(): p for p in folder.rglob("*") if p.is_file()}


def _same_data(saved: Path, data: Path) -> bool:
    """Whether this backup holds exactly what the data folder holds now."""
    files, folders = _stored(data)
    now = {f.name: f for f in files}
    for d in folders:
        now.update({f"{d.name}/{rel}": p for rel, p in _tree(d).items()})
    kept = _tree(saved)
    return now.keys() == kept.keys() and all(now[k].read_bytes() == kept[k].read_bytes() for k in now)


def _name_part(version: str) -> str:
    """A version text as it goes into a backup's name, whatever version.json says: BACKUP_RE always matches."""
    safe = re.sub(r"[^0-9A-Za-z.]", "", str(version))[:NAME_LENGTH].rstrip(".")
    return safe if safe[:1].isdigit() else "0"


def backup(data: Path, old_app: str) -> Path | None:
    """Copy what a step may change to data/backups/<old version>-<YYYYMMDD-HHMM>/; a backup of this version that
    already holds exactly this data is used instead (the attempt before this one failed). None when there is
    nothing to copy (a new data folder). Raises MigrationError when it can't be made, leaving nothing half-made."""
    partial = None
    try:
        files, folders = _stored(data)
        if not files and not folders:
            return None
        root = data / BACKUPS_NAME
        part = _name_part(old_app)
        for old in list_backups(data):
            if old["app"] == part and _same_data(root / old["name"], data):
                return root / old["name"]
        stamp = f"{part}-{datetime.now():%Y%m%d-%H%M}"
        name, n = stamp, 1
        while (root / name).exists() or (root / f"{name}{PARTIAL}").exists():
            n += 1
            name = f"{stamp}-{n}"
        partial = root / f"{name}{PARTIAL}"      # renamed when complete: a half-made copy is never listed
        partial.mkdir(parents=True)
        for f in files:
            shutil.copy2(f, partial / f.name)
        for d in folders:
            shutil.copytree(d, partial / d.name)
        target = root / name
        partial.rename(target)
        return target
    except (OSError, ValueError) as e:
        if partial:
            shutil.rmtree(partial, ignore_errors=True)
        log.error("couldn't back up the data folder: %s", _why(e))
        raise MigrationError(f"Couldn't back up the data folder ({_why(e)}). Nothing in it was changed.") from e


def _clear_partials(data: Path) -> None:
    """Backups a process died in the middle of. Only under the lock: another process's may be in progress."""
    root = data / BACKUPS_NAME
    for d in root.glob(f"*{PARTIAL}") if root.is_dir() else []:
        if BACKUP_RE.match(d.name[:-len(PARTIAL)]) and d.is_dir():
            shutil.rmtree(d, ignore_errors=True)
            log.info("removed the unfinished backup %s", d.name)


def _has_partials(data: Path) -> bool:
    root = data / BACKUPS_NAME
    return root.is_dir() and any(BACKUP_RE.match(d.name[:-len(PARTIAL)]) for d in root.glob(f"*{PARTIAL}"))


def _prune(data: Path, keep: Path | None = None) -> None:
    """Keep the newest KEEP_BACKUPS (and the one this update made). After a migration that worked, never before:
    a failing one must not push out an earlier version's backups. A problem here doesn't fail the update."""
    try:
        for old in list_backups(data)[KEEP_BACKUPS:]:
            if not keep or old["name"] != keep.name:
                delete_backups([old["name"]], data=data)
    except MigrationError as e:
        log.warning("old backups stay for now: %s", e)


def restore(saved: Path, data: Path) -> None:
    """Put the data folder's backed-up files and folders back as they were, also where a step added to them."""
    for name in BACKUP_FILES:
        if (saved / name).is_file():
            shutil.copy2(saved / name, data / name)
        else:
            (data / name).unlink(missing_ok=True)
    for name in BACKUP_FOLDERS:
        if (saved / name).is_dir():
            shutil.copytree(saved / name, data / name, dirs_exist_ok=True)
            kept = _tree(saved / name)
            for rel, path in _tree(data / name).items():
                if rel not in kept:
                    path.unlink()
        elif (data / name).is_dir():
            shutil.rmtree(data / name)


# ----- the migration ----------------------------------------------------------------------------------------

def _lock(data: Path) -> platform.FileLock:
    lock = platform.FileLock(data / LOCK_NAME)
    deadline = time.monotonic() + LOCK_WAIT
    while not lock.acquire():
        if time.monotonic() > deadline:
            raise MigrationError("Another AirFare is updating the data folder. Try again in a minute.")
        time.sleep(0.2)
    return lock


def _migrate(data: Path, found: dict, steps: list[int]) -> Path | None:
    """Back up and run the steps, then record the version; on any problem, the data goes back as it was."""
    saved = backup(data, found["app"]) if steps else None
    try:
        for n in steps:
            STEPS[n](data)
        _write_version(data)
    except Exception as e:
        target = f"AirFare {__version__}"
        if not saved:
            log.error("recording the data's version failed: %s", _why(e))
            raise MigrationError(f"Updating the data folder to {target} failed ({_why(e)}). "
                                 "Nothing in it was changed.") from e
        try:
            restore(saved, data)
        except (OSError, ValueError) as again:
            log.error("updating the data failed (%s), and so did putting it back (%s); the backup is %s",
                      _why(e), _why(again), saved.name)
            raise MigrationError(f"Updating the data folder to {target} failed ({_why(e)}), and putting it back "
                                 f"failed too ({_why(again)}). Your data is safe in {BACKUPS_NAME}/{saved.name}: "
                                 "close AirFare and copy its files into the data folder.") from e
        log.error("updating the data to %s failed (%s); it was put back as it was", target, _why(e))
        log.debug("the step's failure in detail", exc_info=True)
        raise MigrationError(f"Updating the data folder to {target} failed ({_why(e)}). "
                             "It was put back as it was.") from e
    return saved


def ensure(data: Path | None = None) -> dict:
    """Bring the data folder up to date (see the module's description). Returns {"from", "to", "steps",
    "backup" (the backup folder's name), "newer"}; raises MigrationError when it can't, saying what state the data
    is in, after putting it back when a step had changed it."""
    data = Path(data or DATA_DIR)
    found = read_version(data)
    result = {"from": found, "to": found, "steps": [], "backup": None, "newer": newer(found)}
    if newer(found) or not (_due(found) or _has_partials(data)):
        return result
    lock = None
    try:
        data.mkdir(parents=True, exist_ok=True)
        if not _due(found):                   # only an unfinished backup to clear: never worth waiting for
            lock = platform.FileLock(data / LOCK_NAME)
            if lock.acquire():
                _clear_partials(data)
            else:
                lock = None
            return result
        lock = _lock(data)
        found = read_version(data)            # another process may have finished while this one waited
        result.update({"from": found, "to": found, "newer": newer(found)})
        _clear_partials(data)
        if not _due(found):
            return result
        steps = [n for n in sorted(STEPS) if n > found["schema"]]
        if not (data / VERSION_NAME).exists() and not any(_stored(data)):
            steps = []                        # a new data folder: nothing to bring up to date, only to record
        saved = _migrate(data, found, steps)
        if saved:
            _prune(data, keep=saved)
        result.update({"to": read_version(data), "steps": steps, "backup": saved.name if saved else None})
        if steps:
            log.info("data updated from AirFare %s (schema %d) to %s (schema %d)%s", found["app"], found["schema"],
                     __version__, SCHEMA, f"; backup: {saved.name}" if saved else "")
        return result
    except (OSError, ValueError) as e:
        log.error("couldn't update the data folder: %s", _why(e))
        raise MigrationError(f"Couldn't update the data folder to AirFare {__version__} ({_why(e)}). "
                             "Nothing in it was changed.") from e
    finally:
        if lock:
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
