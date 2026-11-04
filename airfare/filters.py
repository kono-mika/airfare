"""A route's filters: which fares it shows at all, as opposed to the alert limits, which decide when to alert.

Route fields, all optional (missing means no filter): price_min and price_max in the user's currency, max_stops
(None for any; 0 is Direct only), exclude_airports (airport or city codes) and max_hours (the longest a direction
may take, door to door including stops, in hours from 1 to 99, decimals allowed).

apply() is the one place they work: after a check's prices are read and converted, it takes the fares that don't
match off each page, so the dashboard, the alerts, the price document, the analyst, the best-value pick, the price
history and the CSV export only ever see the rest. Fares it can't judge stay, marked (Flight.marks), and don't
count for alerts: connections that can't be read while the route excludes airports, prices that couldn't be
converted while it has a price range, directions that aren't known (page text) while it has a travel time limit.

max_hours is not the alerts' "longest trip" setting (alert_max_hours, report.usable): that one applies to every
route and only stops alerts, while this one hides the longer fares of one route everywhere.

Filters aren't part of what makes a route the same search (webui._trip): changing them keeps its id, tab, price
history and lookups. They do restart its alert references, because an old reference may be a fare that's now
hidden: history.json keeps the filters each route's references were set under, and restart_references() compares.
A currency change alone doesn't count: Settings converts the range and moves the kept filters along with it
(follow_currency()), at the same rate. A range the user changed in that same save does count.
"""
from __future__ import annotations

import logging
import math
import re

from . import money
from .extract import ParsedPage, TOP_N, top_picks
from .urls import CITY_AIRPORTS, CITY_CODES

log = logging.getLogger(__name__)

CONNECTIONS_UNKNOWN = "connections unknown"
PRICE_UNKNOWN = "price unknown"
TIME_UNKNOWN = "travel time unknown"
REASONS = ("price", "transfers", "airports", "travel time")
HOURS = (1, 99)         # the shortest and longest max_hours a route may have
_IATA_CITIES = {iata: city for city, iata in CITY_CODES.items()}
_CODE_RE = re.compile(r"^[A-Z]{3}$")
PRICE_KEYS = ("price_min", "price_max")
TOLERANCE = 0.005       # an amount this close to the converted one is that one (the rate may have moved a little)


# ----- reading a route's filters ------------------------------------------------------------------------------

def _is_city(code: str) -> bool:
    return code.lower() in CITY_AIRPORTS or code in _IATA_CITIES


def clean_codes(raw) -> list[str] | None:
    """Airport or city codes in upper case, once each, from a list or a typed "IST, lond"; None when one isn't."""
    parts = re.split(r"[,\s;]+", raw.strip()) if isinstance(raw, str) else raw if isinstance(raw, list) else []
    codes = [str(p).strip().upper() for p in parts if str(p).strip()]
    if not all(_CODE_RE.match(c) or _is_city(c) for c in codes):
        return None
    return list(dict.fromkeys(codes))


def expand(codes: list[str]) -> set[str]:
    """The airports these codes stand for: a city code (LOND or LON) becomes its airports."""
    out: set[str] = set()
    for code in codes:
        city = code.lower() if code.lower() in CITY_AIRPORTS else _IATA_CITIES.get(code)
        out |= set(CITY_AIRPORTS[city].split(",")) if city else {code}
    return out


def _price(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        return None
    return float(value)


def hours(value) -> float | None:
    """A route's max_hours as a number of hours, or None when it isn't one from 1 to 99."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value) if HOURS[0] <= value <= HOURS[1] else None


def normal(raw: dict | None) -> dict:
    """The filters that are really on, always in the same form. Missing or damaged fields (config.json can be
    edited by hand, or come from another version) count as no filter."""
    raw = raw if isinstance(raw, dict) else {}
    out: dict = {}
    for k in ("price_min", "price_max"):
        value = _price(raw.get(k))
        if value is not None:
            out[k] = value
    stops = raw.get("max_stops")
    if stops in (0, 1, 2) and not isinstance(stops, bool):
        out["max_stops"] = int(stops)
    airports = clean_codes(raw.get("exclude_airports"))
    if airports:
        out["exclude_airports"] = sorted(airports)
    limit = hours(raw.get("max_hours"))
    if limit is not None:
        out["max_hours"] = limit
    return out


def stamped(raw: dict | None, currency: str | None) -> dict:
    """The filters as they are kept with a price record or an alert reference: a price range names its currency."""
    out = normal(raw)
    if currency and ("price_min" in out or "price_max" in out):
        out["currency"] = currency
    return out


def same(a: dict | None, b: dict | None, rates: dict | None = None) -> bool:
    """Whether two kept filters are the same. Amounts in different currencies are the same when b's is what Settings
    would have converted a's to, within TOLERANCE; without a rate that can't be told, so they count as different."""
    x, y = normal(a), normal(b)
    if (a or {}).get("currency") and (b or {}).get("currency") and a["currency"] != b["currency"]:
        for k in PRICE_KEYS:
            if (k in x) != (k in y):
                return False
            if k in x:
                converted = money.convert_limit(x[k], a["currency"], b["currency"], rates or {})
                if converted is None or abs(converted - y[k]) > max(0.5, TOLERANCE * converted):
                    return False
            x.pop(k, None)
            y.pop(k, None)
    return x == y


# ----- taking fares off a page --------------------------------------------------------------------------------

def _why_hidden(f, chosen: dict, excluded: set[str], comparable: bool) -> str | None:
    """Why this fare doesn't match: its first reason, so the reasons add up to the fares hidden."""
    if comparable and (f.price < chosen.get("price_min", 0) or f.price > chosen.get("price_max", math.inf)):
        return "price"
    if "max_stops" in chosen and f.max_stops > chosen["max_stops"]:
        return "transfers"
    if excluded & set(f.connections):
        return "airports"
    if "max_hours" in chosen and any(leg.minutes > _minutes(chosen["max_hours"]) for leg in f.legs):
        return "travel time"
    return None


def _minutes(limit: float) -> float:
    """max_hours in minutes; a direction that takes exactly this long is kept."""
    return round(limit * 60, 6)


def _repick(parsed: ParsedPage) -> None:
    """The top lists after fares went: the source's order for best, as far as it is known."""
    kept = {f.id: f for f in parsed.flights}
    first = [i for i in parsed.picks.get("best") or [] if i in kept]
    picks = top_picks(parsed.flights, [kept[i] for i in parsed.ranked if i in kept] or None)
    picks["best"] = list(dict.fromkeys(first + picks["best"]))[:TOP_N]
    parsed.picks = picks


def apply_page(parsed: ParsedPage | None, chosen: dict) -> None:
    """Take the fares that don't match off this page, count them per reason, and mark the ones it can't judge."""
    if not parsed or not chosen:
        return
    excluded = expand(chosen.get("exclude_airports") or [])
    has_range = "price_min" in chosen or "price_max" in chosen
    kept, hidden = [], {}
    for f in parsed.flights:
        why = _why_hidden(f, chosen, excluded, parsed.comparable)
        if why:
            hidden[why] = hidden.get(why, 0) + 1
            continue
        kept.append(f)
        if (excluded and f.connections_unknown or "max_stops" in chosen and not f.legs) and CONNECTIONS_UNKNOWN not in f.marks:
            f.marks.append(CONNECTIONS_UNKNOWN)
        if has_range and not parsed.comparable and PRICE_UNKNOWN not in f.marks:
            f.marks.append(PRICE_UNKNOWN)
        if "max_hours" in chosen and not f.legs and TIME_UNKNOWN not in f.marks:
            f.marks.append(TIME_UNKNOWN)
    if hidden:
        parsed.flights, parsed.hidden = kept, hidden
        _repick(parsed)


def apply(pages: list, currency: str | None = None) -> None:
    """Apply each page's route's filters (pages are report.PageData, read and converted). Pages of routes without
    filters aren't touched. Afterwards page["filters"] is what the page was taken under (stamped())."""
    for pd in pages:
        chosen = stamped(pd.page.get("filters"), currency)
        pd.page.pop("filters", None)
        if chosen:
            pd.page["filters"] = chosen
            apply_page(pd.parsed, chosen)


def hidden_counts(pages: list) -> dict[str, int]:
    """Fares hidden on these pages, per reason."""
    out: dict[str, int] = {}
    for pd in pages:
        for why, n in (pd.parsed.hidden if pd.parsed else {}).items():
            out[why] = out.get(why, 0) + n
    return {why: out[why] for why in REASONS if why in out}


# ----- saying what they do (the price document is always in English) --------------------------------------------

def describe(chosen: dict) -> str:
    """"price from €100 to €300; at most 1 transfer per direction; no transfers at IST; each direction at most
    7.5 hours"."""
    parts = []

    def amount(key: str) -> str:
        return money.fmt(chosen[key], chosen["currency"]) if chosen.get("currency") else f"{chosen[key]:g}"

    if "price_min" in chosen and "price_max" in chosen:
        parts.append(f"price from {amount('price_min')} to {amount('price_max')}")
    elif "price_min" in chosen:
        parts.append(f"price from {amount('price_min')}")
    elif "price_max" in chosen:
        parts.append(f"price up to {amount('price_max')}")
    if "max_stops" in chosen:
        n = chosen["max_stops"]
        parts.append("direct flights only" if n == 0 else f"at most {n} transfer{'s' if n > 1 else ''} per direction")
    if chosen.get("exclude_airports"):
        parts.append("no transfers at " + ", ".join(sorted(expand(chosen["exclude_airports"]))))
    if "max_hours" in chosen:
        h = chosen["max_hours"]
        parts.append(f"each direction at most {h:g} hour{'' if h == 1 else 's'}")
    return "; ".join(parts)


def text_marks(chosen: dict) -> list[str]:
    """What fares that only came as page text are, under these filters: none of them can be checked."""
    marks = [CONNECTIONS_UNKNOWN] if set(chosen) - {"max_hours", "currency"} else []
    return marks + ([TIME_UNKNOWN] if "max_hours" in chosen else [])


def hidden_line(hidden: dict[str, int]) -> str:
    """"3 fares hidden by this route's filters (price 2, travel time 1)"."""
    total = sum(hidden.values())
    why = ", ".join(f"{r} {hidden[r]}" for r in REASONS if r in hidden)
    return f"{total} fare{'' if total == 1 else 's'} hidden by this route's filters ({why})"


# ----- alert references ---------------------------------------------------------------------------------------

def changed_routes(before: list[dict], after: list[dict], old_currency: str | None, currency: str | None,
                   rates: dict | None = None) -> list[dict]:
    """The routes of `after` whose filters differ from the same route's in `before`."""
    old = {r.get("id"): r for r in before}
    return [r for r in after if r.get("id") in old
            and not same(stamped(old[r["id"]], old_currency), stamped(r, currency), rates)]


def follow_currency(history: dict, before: list[dict], after: list[dict], old_currency: str | None,
                    currency: str | None, rates: dict | None) -> bool:
    """After a save that changed the currency: a route whose range was only converted keeps its references. Kept
    now, at the rate it was converted at, since the next check's rate may have moved enough to look like an edit.
    Filters that changed before this save and haven't had a check yet stay as they are: that restart still stands.
    Returns whether anything changed."""
    old = {r.get("id"): r for r in before}
    moved = False
    for route in after:
        h = (history.get("routes") or {}).get(route.get("id"))
        was = old.get(route.get("id"))
        if not (h and was and h.get("filters")):
            continue
        kept, now = stamped(was, old_currency), stamped(route, currency)
        if kept.get("currency") != now.get("currency") and same(h["filters"], kept) and same(kept, now, rates):
            h["filters"] = now
            moved = True
    return moved


def restart_references(history: dict, routes: list[dict], currency: str | None = None, rates: dict | None = None) -> list[str]:
    """Before a check: a route whose filters changed since its references were set starts again, as Clean up's
    "alert references" does: each kind from this check's prices, like a new route. Its old references, low and last
    prices may be fares that are now hidden. Everything else about the route stays. Returns the ids restarted."""
    kept = history.setdefault("routes", {})
    restarted = []
    for route in routes:
        rid = route.get("id")
        now = stamped(route, currency)
        h = kept.get(rid)
        if not now and not (h or {}).get("filters"):
            continue
        if h is None:
            h = kept.setdefault(rid, {"name": route.get("name") or rid})
        if not same(h.get("filters"), now, rates):
            for k in ("alert_refs", "alert_ref", "all_time_low", "last"):
                h.pop(k, None)
            restarted.append(rid)
        h.pop("filters", None)
        if now:
            h["filters"] = now
    if restarted:
        log.info("filters changed: alert references restart from this check for %s", ", ".join(map(str, restarted)))
    return restarted

