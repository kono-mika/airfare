"""Every price AirFare has seen, kept locally in data/price_history.json for the History page.

One record per check, route, source and date pair: that page's cheapest flight. Deleting records here only
changes what the History page shows; LOW PRICE alert references live in history.json and are not touched.
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime

from . import platform
from .config import DATA_DIR, read_json, write_json

log = logging.getLogger(__name__)

LOG_FILE = DATA_DIR / "price_history.json"
RESEARCH_FILE = DATA_DIR / "price_research.json"
LOCK_FILE = DATA_DIR / "price_history.lock"


class _Locked:
    """Two processes change these files (the background check adds records, the History page deletes them),
    each by reading, changing and writing back: this lock keeps one from discarding the other's change."""

    def __enter__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.lock = platform.FileLock(LOCK_FILE)
        deadline = time.monotonic() + 10
        while not self.lock.acquire():
            if time.monotonic() > deadline:
                log.warning("the price history stayed locked for 10 s; writing anyway")
                break
            time.sleep(0.05)
        return self

    def __exit__(self, *exc):
        self.lock.release()


def load() -> list[dict]:
    return read_json(LOG_FILE, [])


def _save(records: list[dict]) -> None:
    write_json(LOG_FILE, records)


def records_from_check(pages, when: datetime) -> list[dict]:
    """The cheapest flight of each page that had prices (pages are report.PageData)."""
    out = []
    for pd in pages:
        if not pd.parsed or not pd.parsed.flights:
            continue
        f = pd.parsed.flights[0]
        page = pd.page
        out.append({
            "id": uuid.uuid4().hex[:12],
            "time": when.isoformat(timespec="minutes"),
            "route_id": page["route_id"],
            "route_name": page.get("route_name") or page["route_id"],
            "origin": (page.get("origin") or "").upper(),
            "destination": (page.get("destination") or "").upper(),
            "depart": page.get("depart"),
            "return": page.get("return"),
            "source": pd.result.source,
            "price": f.price,
            "price_text": f.price_text,
            "currency": pd.parsed.currency,
            "currency_code": pd.parsed.currency_code,
            "site_price": f.orig_text or None,
            "airlines": f.airlines,
            "stops": f.max_stops,
            "minutes": f.minutes,
            "url": page.get("url"),
        })
    return out


def add(records: list[dict]) -> None:
    if records:
        with _Locked():
            _save(load() + records)


def matches(r: dict, route_id: str | None = None, depart_from: str | None = None, depart_to: str | None = None,
            return_from: str | None = None, return_to: str | None = None, source: str | None = None) -> bool:
    """Whether a record fits the History page's conditions (empty conditions match everything)."""
    if route_id and r.get("route_id") != route_id:
        return False
    if source and r.get("source") != source:
        return False
    d, ret = r.get("depart") or "", r.get("return") or ""
    if depart_from and d < depart_from or depart_to and d > depart_to:
        return False
    if (return_from or return_to) and not ret:
        return False
    if return_from and ret < return_from or return_to and ret > return_to:
        return False
    return True


def delete(ids: list[str] | None = None, route_id: str | None = None, everything: bool = False) -> int:
    """Delete records by id, all of a route's records, or everything. Returns how many were removed."""
    with _Locked():
        records = load()
        if everything:
            keep = []
        elif route_id:
            keep = [r for r in records if r.get("route_id") != route_id]
        else:
            gone = set(ids or [])
            keep = [r for r in records if r.get("id") not in gone]
        _save(keep)
    return len(records) - len(keep)


# ----- results of "search the lowest price history" lookups ----------------------------------

def load_research() -> list[dict]:
    return read_json(RESEARCH_FILE, [])


def add_research(result: dict) -> dict:
    result = {"id": uuid.uuid4().hex[:12], **result}
    with _Locked():
        write_json(RESEARCH_FILE, load_research() + [result])
    return result


def delete_research(ids: list[str] | None = None, everything: bool = False) -> int:
    with _Locked():
        items = load_research()
        keep = [] if everything else [r for r in items if r.get("id") not in set(ids or [])]
        write_json(RESEARCH_FILE, keep)
    return len(items) - len(keep)
