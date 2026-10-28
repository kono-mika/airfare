"""Limits on the browser sources (Skyscanner and Aviasales, which the extension opens in your browser), so every
copy of AirFare stays personal, small-scale use. Two levels, picked in Settings; there is no "off":

- pages per check: the browser pages one check (or link test) may open, Skyscanner and Aviasales together;
- the gap: automatic checks (at startup, on the interval, from the background checker) open them at most this
  often; one that comes sooner leaves them out and still asks Google Flights (SerpApi);
- pages per day: every browser page opened that calendar day, manual checks and link tests included.

runner.collect_prices applies them where the pages are opened, so a hand-edited config.json can't raise them: an
unknown or missing level counts as Personal. Google Flights through SerpApi isn't limited here.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta

from .config import load_state, save_state
from .i18n import tr, trn

LEVELS = {
    "personal": {"pages": 20, "hours": 6, "per_day": 60},
    "extended": {"pages": 40, "hours": 3, "per_day": 150},
}
NAMES = {"personal": "Personal", "extended": "Extended"}


def level(cfg: dict) -> str:
    name = cfg.get("limits")
    return name if isinstance(name, str) and name in LEVELS else "personal"


def _time(text) -> datetime | None:
    try:
        return datetime.fromisoformat(text) if isinstance(text, str) else None
    except ValueError:
        return None


def _tomorrow(now: datetime) -> datetime:
    return datetime.combine(now.date() + timedelta(days=1), time.min)


def used_today(state: dict, now: datetime) -> int:
    """Browser pages opened so far on now's calendar day (state.json: browser_pages)."""
    day = state.get("browser_pages")
    if not isinstance(day, dict) or day.get("day") != now.date().isoformat():
        return 0
    try:
        return max(0, int(day.get("pages") or 0))
    except (TypeError, ValueError):
        return 0


def _too_soon(state: dict, hours: float, now: datetime) -> datetime | None:
    """When the gap after the last browser-source check ends, if it hasn't yet. A time a little ahead of the clock
    (it went back an hour) still counts; one more than a gap ahead was written by a wrong clock and is ignored, so
    it can't hold the browser sources back for months."""
    last = _time(state.get("browser_check"))
    gap = timedelta(hours=hours)
    if last and -gap < now - last < gap:
        return last + gap
    return None


def allow(cfg: dict, pages: list[dict], automatic: bool = False,
          now: datetime | None = None) -> tuple[list[dict], dict | None]:
    """The browser pages this check may open (the first ones, in order) and, when some are left out, why:
    {"reason": "check" | "gap" | "day", "opened": n, "left_out": n, "level", "pages", "hours", "per_day", "until"}."""
    if not pages:
        return pages, None
    now = now or datetime.now()
    name = level(cfg)
    rule = LEVELS[name]
    state = load_state()
    held = {"level": name, **rule, "until": None}
    if automatic:
        until = _too_soon(state, rule["hours"], now)
        if until:
            return [], {**held, "reason": "gap", "opened": 0, "left_out": len(pages),
                        "until": until.isoformat(timespec="minutes")}
    left = rule["per_day"] - used_today(state, now)
    cap = max(0, min(rule["pages"], left))
    if len(pages) <= cap:
        return pages, None
    held.update(opened=cap, left_out=len(pages) - cap)
    if cap == rule["pages"]:
        return pages[:cap], {**held, "reason": "check"}
    return pages[:cap], {**held, "reason": "day", "until": _tomorrow(now).isoformat(timespec="minutes")}


def record(count: int, now: datetime | None = None, check: bool = True) -> None:
    """Count the pages the extension is opening and, for a check (not Test links), remember when it was."""
    now = now or datetime.now()
    state = load_state()
    state["browser_pages"] = {"day": now.date().isoformat(), "pages": used_today(state, now) + count}
    if check:
        state["browser_check"] = now.isoformat(timespec="seconds")
    save_state(state)


def reopens(cfg: dict, now: datetime | None = None) -> datetime | None:
    """When an automatic check may open browser pages again; None when it may now."""
    now = now or datetime.now()
    rule = LEVELS[level(cfg)]
    state = load_state()
    times = [t for t in (_too_soon(state, rule["hours"], now),
                         _tomorrow(now) if used_today(state, now) >= rule["per_day"] else None) if t]
    return max(times) if times else None


def describe(held: dict | None, lang: str | None) -> str:
    """One sentence on what the limits left out, for the dashboard, the price document and Settings."""
    if not held:
        return ""
    name = tr("Extended" if held.get("level") == "extended" else "Personal", lang)
    n = int(held.get("left_out") or 0)
    if held.get("reason") == "gap":
        return tr("Skyscanner and Aviasales were skipped this time: with the {level} limits, automatic checks open "
                  "their pages at most once every {hours} hours.", lang, level=name, hours=held.get("hours"))
    if held.get("reason") == "day":
        return trn(n, "{n} Skyscanner or Aviasales page waits until tomorrow: the {level} limits allow {max} a day.|"
                      "{n} Skyscanner and Aviasales pages wait until tomorrow: the {level} limits allow {max} a day.",
                   lang, level=name, max=held.get("per_day"))
    return trn(n, "{n} Skyscanner or Aviasales page was left out: the {level} limits allow {max} per check.|"
                  "{n} Skyscanner and Aviasales pages were left out: the {level} limits allow {max} per check.",
               lang, level=name, max=held.get("pages"))
