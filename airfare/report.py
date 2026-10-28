"""The price document sent to the analyst, and the per-route price history kept between runs.

LOW PRICE alerts come in three kinds, each with its own reference and threshold (Settings → Price alerts):

- cheapest: the lowest fare for the route, however long the trip;
- fastest: the cheapest of the quickest trips (within 10% or 30 minutes of the shortest travel time);
- best: the analyst's best-value pick (price, stops, travel time and hours together), or the sources' own
  best-ranked fare when there is no analyst pick.

A kind's reference is its price at the first check and moves only when that kind alerts, so a slow slide
still alerts once it adds up and one kind's alert never resets another's.
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse

from . import limits, money
from .results import PageResult
from .extract import Flight, ParsedPage, convert_page, parse_aviasales, parse_payloads

CATEGORIES = ("best", "cheapest", "fastest")       # the order of the tables in the price document
ALERT_KINDS = ("cheapest", "fastest", "best")
FAST_SLACK, FAST_MINUTES = 1.10, 30
BEST_LONGER = 1.20                                  # a best-value pick may take at most 20% longer than its reference


@dataclass
class PageData:
    result: PageResult
    parsed: ParsedPage | None

    @property
    def page(self) -> dict:
        return self.result.page


def _when(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%a %d %b %H:%M")
    except ValueError:
        return iso or "?"


def _day(iso: str | None) -> str:
    if not iso:
        return "?"
    try:
        return datetime.fromisoformat(iso).strftime("%a %d %b %Y")
    except ValueError:
        return iso


def _dur(minutes: int) -> str:
    return f"{minutes // 60}h{minutes % 60:02d}"


def _stops(n: int) -> str:
    return "direct" if n == 0 else f"{n} stop{'s' if n > 1 else ''}"


def _leg_cell(f: Flight, i: int) -> str:
    if i >= len(f.legs):
        return "—"
    leg = f.legs[i]
    return f"{_when(leg.depart)} {leg.origin}→{leg.destination} {_when(leg.arrive)[-5:]} ({_dur(leg.minutes)}, {_stops(leg.stops)})"


def flight_summary(f: Flight, pd: "PageData") -> dict:
    """The compact record kept in history.json and shown to the analyst as 'previous'."""
    return {
        "price": f.price,
        "price_text": f.price_text,
        "currency": (pd.parsed.currency_code if pd.parsed else None) or money.detect(f.price_text),
        "depart": f.legs[0].depart if f.legs else pd.page.get("depart"),
        "return": f.legs[1].depart if len(f.legs) > 1 else pd.page.get("return"),
        "airlines": f.airlines,
        "stops": f.max_stops,
        "minutes": f.minutes,
        "source": pd.result.source,
        "url": pd.page.get("url"),
    }


def describe(rec: dict) -> str:
    dates = (rec.get("depart") or "?")[:16].replace("T", " ")
    if rec.get("return"):
        dates += " / return " + rec["return"][:16].replace("T", " ")
    source = f" on {rec['source']}" if rec.get("source") else ""
    return (f"{rec.get('price_text')}{source} ({dates}, {rec.get('airlines')}, {_stops(rec.get('stops', 0))}, "
            f"{_dur(rec.get('minutes', 0))})")


def collect(results: list[PageResult], currency: str | None = None, rates: dict | None = None) -> list[PageData]:
    """Parse every page and, given a currency, show all prices in it (see extract.convert_page)."""
    out = []
    for r in results:
        parsed = r.parsed if r.parsed is not None else (
            parse_aviasales(r.payloads) if r.source == "Aviasales" else parse_payloads(r.payloads))
        if currency:
            convert_page(parsed, currency, rates or {}, urlparse(r.page.get("url") or "").hostname or "")
        out.append(PageData(r, parsed))
    return out


# ----- alert rules from Settings ----------------------------------------------------------

def alert_rules(cfg: dict) -> dict:
    """{"kinds": {kind: {"on", "drop", "max"}}, "max_hours", "no_self_transfer"} from the settings."""
    kinds = {}
    for kind in ALERT_KINDS:
        k = (cfg.get("alerts") or {}).get(kind) or {}
        kinds[kind] = {"on": k.get("on", True) is not False, "drop": max(float(k.get("drop") or 0), 0.0),
                       "max": float(k["max"]) if k.get("max") not in (None, "") else None}
    hours = cfg.get("alert_max_hours")
    return {"kinds": kinds, "max_hours": float(hours) if hours not in (None, "", 0) else None,
            "no_self_transfer": bool(cfg.get("alert_no_self_transfer"))}


def usable(f: Flight, rules: dict) -> bool:
    """Whether a flight may count for alerts: no direction longer than the limit, no self-transfer if asked."""
    if rules.get("no_self_transfer") and f.self_transfer:
        return False
    limit = rules.get("max_hours")
    return not (limit and any(leg.minutes > limit * 60 for leg in f.legs))


def fastest_trip(found: list[tuple[Flight, "PageData"]]) -> tuple[Flight, "PageData"] | None:
    """The cheapest of the quickest trips. Google Flights lists only the outbound flight of a return trip,
    so complete trips are compared with complete trips."""
    if not found:
        return None
    full = [(f, pd) for f, pd in found if len(f.legs) == (2 if pd.page.get("return") else 1)]
    pool = full or found
    shortest = min(f.minutes for f, _ in pool)
    quick = [(f, pd) for f, pd in pool if f.minutes <= max(shortest * FAST_SLACK, shortest + FAST_MINUTES)]
    return min(quick, key=lambda x: (x[0].price, x[0].minutes))


def route_bests(pages: list[PageData], rules: dict | None = None) -> dict[str, dict]:
    """Per route: this run's cheapest and fastest flights and the sources' cheapest 'Best' pick, counting
    only prices in AirFare's currency and flights the alert filters allow."""
    rules = rules or {}
    out: dict[str, dict] = {}
    found: dict[str, list[tuple[Flight, PageData]]] = {}
    for pd in pages:
        rid = pd.page["route_id"]
        entry = out.setdefault(rid, {"name": pd.page["route_name"], "cheapest": None, "fastest": None, "best_pick": None})
        if not pd.parsed or not pd.parsed.flights or not pd.parsed.comparable:
            continue
        usable_flights = [f for f in pd.parsed.flights if usable(f, rules)]
        found.setdefault(rid, []).extend((f, pd) for f in usable_flights)
        if usable_flights and (entry["cheapest"] is None or usable_flights[0].price < entry["cheapest"]["price"]):
            entry["cheapest"] = flight_summary(usable_flights[0], pd)
        by_id = {f.id: f for f in usable_flights}
        best = next((by_id[i] for i in pd.parsed.picks.get("best") or [] if i in by_id), None)
        if best and (entry["best_pick"] is None or best.price < entry["best_pick"]["price"]):
            entry["best_pick"] = flight_summary(best, pd)
    for rid, flights in found.items():
        fast = fastest_trip(flights)
        if fast:
            out[rid]["fastest"] = flight_summary(*fast)
    return {rid: e for rid, e in out.items() if e["cheapest"] or rid in found}


# ----- the price document -----------------------------------------------------------------

def build_document(pages: list[PageData], when: datetime, left_out: int, currency: str | None = None,
                   rates: dict | None = None, held: dict | None = None) -> str:
    ok = sum(1 for p in pages if p.result.status == "ok")
    lines = [f"# Flight prices — {when:%Y-%m-%d %H:%M}",
             "",
             f"Pages checked: {len(pages)} ({ok} ok"
             + "".join(f", {n} {s}" for s, n in _status_counts(pages).items() if s != "ok") + ")."]
    sources = sorted({p.result.source for p in pages})
    lines.append(f"Price sources: {', '.join(sources)}.")
    if currency:
        rate = money.rate_line(currency, rates or {})
        lines.append(f"All prices are in {currency} ({money.sign(currency)}). AirFare converted prices that a site "
                     f"showed in another currency" + (f" with today's exchange rates: {rate}." if rate else ".")
                     + " If a page below still shows another currency (page text), convert it to "
                     f"{currency} with these rates before comparing.")
        if rate and money.needs_credit(rates):
            lines.append(money.CREDIT_MD)
    else:
        currencies = {p.parsed.currency for p in pages if p.parsed and p.parsed.flights}
        if currencies:
            lines.append(f"Currencies as shown: {', '.join(sorted(currencies))}.")
    if left_out:
        lines.append(f"{left_out} more date combinations were skipped by the page limit.")
    if held:
        lines.append(limits.describe(held, "en"))

    by_route: dict[str, list[PageData]] = {}
    for p in pages:
        by_route.setdefault(p.page["route_id"], []).append(p)

    for rid, rpages in by_route.items():
        lines += ["", f"## {rpages[0].page['route_name']} (route `{rid}`)"]
        for pd in sorted(rpages, key=lambda p: (p.page.get("depart") or "", p.page.get("return") or "", p.result.source)):
            lines += _page_section(pd)
    return "\n".join(lines) + "\n"


def _status_counts(pages: list[PageData]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for p in pages:
        counts[p.result.status] = counts.get(p.result.status, 0) + 1
    return counts


def _page_section(pd: PageData) -> list[str]:
    page, res, parsed = pd.page, pd.result, pd.parsed
    title = f"{res.source} · depart {_day(page.get('depart'))}"
    if page.get("return"):
        title += f" · return {_day(page.get('return'))}"
    state = res.status
    if parsed:
        state += f", {len(parsed.flights)} of {parsed.total_results} results" + ("" if parsed.complete else " (search still running)")
    if res.note:
        state += f" — {res.note}"
    out = ["", f"### {title} — {state}", f"Link: {page['url']}"]
    if parsed and parsed.note:
        out.append(parsed.note)

    if parsed and parsed.flights:
        by_id = {f.id: f for f in parsed.flights}
        two_way = any(len(f.legs) > 1 for f in parsed.flights)
        for cat in CATEGORIES:
            rows = [by_id[i] for i in parsed.picks.get(cat, []) if i in by_id]
            if not rows:
                continue
            label = f"Best (as ranked by {res.source})" if cat == "best" else cat.title()
            out += ["", f"**{label}**", "",
                    "| # | Price | Outbound | " + ("Return | " if two_way else "") + "Airlines | Travel time | Notes |",
                    "|---|---|---|" + ("---|" if two_way else "") + "---|---|---|"]
            for i, f in enumerate(rows, 1):
                notes = [t.replace("_", " ") for t in f.tags]
                if f.self_transfer:
                    notes.append("self-transfer")
                if f.orig_text:
                    notes.append(f"site price {f.orig_text}")
                out.append(f"| {i} | {f.price_text} | {_leg_cell(f, 0)} | " + (f"{_leg_cell(f, 1)} | " if two_way else "")
                           + f"{f.airlines} | {_dur(f.minutes)} | {', '.join(notes)} |")
    elif res.text.strip():
        out += ["", "No structured results were captured; this is the visible page text:", "", "```",
                res.text.strip()[:6000], "```"]
    return out


def price_summary(pages: list[PageData]) -> dict:
    """This run's cheapest price per route, source and date pair (kept in history for the trend chart)."""
    out: dict = {}
    for pd in pages:
        if not pd.parsed or not pd.parsed.flights or not pd.parsed.comparable:
            continue
        f = pd.parsed.flights[0]
        src = out.setdefault(pd.page["route_id"], {}).setdefault(
            pd.result.source, {"cheapest": None, "text": None, "dates": {}})
        src["dates"][pd.page["key"]] = f.price
        if src["cheapest"] is None or f.price < src["cheapest"]:
            src["cheapest"], src["text"] = f.price, f.price_text
    return out


# ----- history and alert references -------------------------------------------------------
# Prices saved before AirFare recorded currencies carry only their text ("$450"). `site` (the Skyscanner
# site in Settings) tells what such a sign meant there: "$" on skyscanner.ca is Canadian dollars.

def _good(value) -> bool:
    """A usable price: a finite number above zero (history files can be hand-edited or damaged)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def _currency_of(rec: dict, site: str = "") -> str | None:
    return rec.get("currency") or money.detect(rec.get("price_text") or rec.get("text") or "", site)


def in_currency(rec: dict | None, currency: str | None, rates: dict | None, site: str = "") -> dict | None:
    """A price record (a flight summary or an alert reference) shown in currency, if it was saved in another.
    None when it can't be used: no exchange rate, or no sensible price."""
    if not rec or not _good(rec.get("price")):
        return None
    if not currency:
        return rec
    src = _currency_of(rec, site) or currency
    if src == currency:
        return rec
    value = money.convert(rec["price"], src, currency, rates or {})
    if value is None:
        return None                       # can't compare without a rate
    out = {**rec, "price": round(value, 2), "currency": currency}
    for k in ("price_text", "text"):
        if k in rec:
            out[k] = money.fmt(value, currency)
    return out


def _ref(rec: dict, stamp: str, reason: str) -> dict:
    return {"price": rec["price"], "text": rec.get("price_text") or rec.get("text"), "currency": _currency_of(rec),
            "minutes": rec.get("minutes"), "stops": rec.get("stops"), "set": stamp, "reason": reason}


def _old_refs(h: dict, site: str = "") -> dict:
    """Alert references kept by AirFare before alerts had kinds: one cheapest reference and a best-value one."""
    ref = h.get("alert_ref")
    if not ref and h.get("all_time_low"):          # history from before alert references existed
        last = h.get("last") or {}
        best = last.get("best_value_price") or (last.get("best_pick") or {}).get("price")
        ref = {"cheapest": h["all_time_low"].get("price"), "cheapest_text": h["all_time_low"].get("price_text"),
               "best_value": best, "set": h["all_time_low"].get("seen"), "reason": "earlier low"}
    if not isinstance(ref, dict) or not _good(ref.get("cheapest")):
        return {}
    cur = money.detect(ref.get("cheapest_text") or "", site)
    out = {"cheapest": {"price": ref["cheapest"], "text": ref.get("cheapest_text"), "currency": cur,
                        "set": ref.get("set"), "reason": ref.get("reason")}}
    if _good(ref.get("best_value")):
        out["best"] = {"price": ref["best_value"], "text": money.fmt(ref["best_value"], cur) if cur else None,
                       "currency": cur, "set": ref.get("set"), "reason": ref.get("reason")}
    return out


def alert_refs(h: dict, site: str = "") -> dict:
    return h["alert_refs"] if isinstance(h.get("alert_refs"), dict) else _old_refs(h, site)


def best_record(rid: str, bests: dict, best_values: dict) -> dict | None:
    """The best-value price this run: the analyst's pick, else the sources' best-ranked fare."""
    bv = (best_values or {}).get(rid)
    if bv:
        return {"price": bv["price"], "price_text": bv.get("text"), "currency": bv.get("currency"),
                "stops": bv.get("stops"), "minutes": bv.get("minutes"), "url": bv.get("url"),
                "excluded": bool(bv.get("excluded"))}
    return ((bests or {}).get(rid) or {}).get("best_pick")


def _fast_enough(rec: dict, ref: dict | None) -> bool:
    """Whether today's fastest trip is about as quick as the one its reference was set on."""
    if not ref or not ref.get("minutes") or not rec.get("minutes"):
        return True
    return rec["minutes"] <= max(ref["minutes"] * FAST_SLACK, ref["minutes"] + FAST_MINUTES)


def update_history(history: dict, bests: dict[str, dict], when: datetime, run_info: dict,
                   best_values: dict[str, dict] | None = None, alerted: dict[str, list[str]] | None = None,
                   currency: str | None = None, rates: dict | None = None, site: str = "") -> dict:
    """Record this run. Each alert kind's reference is set on its first check and moves only when it alerts,
    or, for the fastest trip, when the quick trip it was set on is gone (a slower one is a different thing)."""
    stamp = when.isoformat(timespec="minutes")
    best_values, alerted = best_values or {}, alerted or {}
    routes = history.setdefault("routes", {})
    for rid, b in bests.items():
        h = routes.setdefault(rid, {})
        refs = copy.deepcopy(alert_refs(h, site))     # before this run's prices change the record
        h["name"] = b["name"]
        if b["cheapest"]:
            low = in_currency(h.get("all_time_low"), currency, rates, site)
            if low is None or b["cheapest"]["price"] < low["price"]:
                h["all_time_low"] = {**b["cheapest"], "seen": stamp}
        h["last"] = {"checked": stamp, "currency": currency, "cheapest": b["cheapest"], "fastest": b.get("fastest"),
                     "best_pick": b["best_pick"]}
        best = best_record(rid, bests, best_values)
        if best and best.get("excluded"):
            best = None                                # the analyst's pick is a trip the user's filters leave out
        if best:
            h["last"]["best_value"] = (best_values.get(rid) or {}).get("text") or describe(best)
            h["last"]["best_value_price"] = best["price"]
        for kind, rec in (("cheapest", b["cheapest"]), ("fastest", b.get("fastest")), ("best", best)):
            if not rec or not _good(rec.get("price")):
                continue
            fired = kind in alerted.get(rid, [])
            if fired or not _good((refs.get(kind) or {}).get("price")):
                refs[kind] = _ref({**rec, "currency": rec.get("currency") or currency}, stamp,
                                  "LOW PRICE alert" if fired else "first check")
            elif kind == "fastest" and not _fast_enough(rec, refs[kind]):
                refs[kind] = _ref({**rec, "currency": rec.get("currency") or currency}, stamp, "quicker trip gone")
        h["alert_refs"] = refs
        h.pop("alert_ref", None)
    history.setdefault("runs", []).append({"time": stamp, **run_info})
    history["runs"] = history["runs"][-200:]
    return history


def alert_targets(history: dict, route_ids: list[str], rules: dict, currency: str | None = None,
                  rates: dict | None = None, site: str = "") -> dict[str, dict]:
    """Per route and alert kind (only kinds switched on): its reference and the price that counts as LOW PRICE."""
    out: dict[str, dict] = {}
    for rid in route_ids:
        refs = alert_refs(history.get("routes", {}).get(rid) or {}, site)
        for kind, rule in rules["kinds"].items():
            if not rule["on"]:
                continue
            ref = in_currency(refs.get(kind), currency, rates, site) if refs.get(kind) else None
            if refs.get(kind) and ref is None:
                continue                      # saved in another currency with no rate, or damaged
            if ref is None and rule["max"] is None:
                continue                      # a first check only sets the reference
            cur = currency or (ref or {}).get("currency")
            t = {"ref": ref, "drop": rule["drop"], "max": rule["max"], "target": None, "target_text": None,
                 "max_text": money.fmt(rule["max"], cur) if rule["max"] is not None and cur else None}
            if ref and rule["drop"] > 0:
                t["target"] = money.floor_price(ref["price"] * (1 - rule["drop"] / 100))
                t["target_text"] = money.fmt(t["target"], cur) if cur else f"{t['target']:g}"
            out.setdefault(rid, {})[kind] = t
    return out


def reaches(price: float | None, t: dict, rec: dict | None = None, kind: str = "cheapest") -> bool:
    """Whether a price reaches one alert target: the drop below the reference, or the price ceiling.
    Fastest and best value only count against a comparable trip (see comparable())."""
    if not _good(price):
        return False
    ref = t["ref"]
    if rec is not None and not comparable(rec, ref, kind):
        return False
    if ref:
        if t["drop"] > 0 and t["target"] is not None and price <= t["target"]:
            return True
        if t["drop"] <= 0 and price < ref["price"]:
            return True
    return t["max"] is not None and price <= t["max"] and (ref is None or price < ref["price"])


def comparable(rec: dict, ref: dict | None, kind: str) -> bool:
    """Fastest: about as quick as its reference. Best value: same or fewer stops, at most ~20% longer, and a
    trip the user's alert filters allow."""
    if kind == "fastest":
        return _fast_enough(rec, ref)
    if kind == "best":
        if rec.get("excluded"):
            return False
        if ref and ref.get("stops") is not None and rec.get("stops") is not None and rec["stops"] > ref["stops"]:
            return False
        return not (ref and ref.get("minutes") and rec.get("minutes") and rec["minutes"] > ref["minutes"] * BEST_LONGER)
    return True


def threshold_hits(targets: dict[str, dict], bests: dict[str, dict], best_values: dict[str, dict]) -> dict[str, list[str]]:
    """Per route, the alert kinds whose LOW PRICE target this run reached."""
    hits: dict[str, list[str]] = {}
    for rid, kinds in targets.items():
        b = bests.get(rid) or {}
        found = {"cheapest": b.get("cheapest"), "fastest": b.get("fastest"), "best": best_record(rid, bests, best_values)}
        for kind, t in kinds.items():
            rec = found.get(kind)
            if rec and reaches(rec.get("price"), t, rec, kind):
                hits.setdefault(rid, []).append(kind)
    return hits


KIND_TEXT = {"cheapest": "the cheapest fare", "fastest": "the fastest trip (cheapest within 10% of the shortest travel time)",
             "best": "a comparable best-value option (same or fewer stops, at most ~20% longer than its reference)"}


def previous_records(history: dict, route_ids: list[str], targets: dict[str, dict], rules: dict,
                     currency: str | None = None, rates: dict | None = None, site: str = "") -> str:
    """What the analyst compares against: each route's LOW PRICE targets per kind, all-time low and last check,
    all in today's currency."""
    on = [k for k, r in rules["kinds"].items() if r["on"]]
    lines = ["Alert rules: LOW PRICE has three kinds, each with its own reference (its price at its last LOW PRICE "
             "alert, or the first price seen) and threshold: "
             + "; ".join(f"{k} {'on' if rules['kinds'][k]['on'] else 'off'}" for k in ALERT_KINDS) + "."]
    if rules.get("max_hours") or rules.get("no_self_transfer"):
        parts = []
        if rules.get("max_hours"):
            parts.append(f"trips where one direction takes longer than {rules['max_hours']:g} hours")
        if rules.get("no_self_transfer"):
            parts.append("self-transfer trips")
        lines.append("For alerts the user ignores " + " and ".join(parts) + ".")
    for rid in route_ids:
        h = history.get("routes", {}).get(rid) or {}
        kinds = targets.get(rid) or {}
        if not kinds and not alert_refs(h, site):
            lines.append(f"- route `{rid}`: no earlier prices (first check for this route: baseline, not a LOW PRICE).")
            continue
        parts = []
        for kind in on:
            t = kinds.get(kind)
            if not t:
                continue
            conds = []
            if t["ref"]:
                ref = t["ref"]
                if t["drop"] > 0:
                    conds.append(f"{t['target_text']} or less ({t['drop']:g}% below its reference {ref['text']}, set {ref.get('set')})")
                else:
                    conds.append(f"below its reference {ref['text']} (set {ref.get('set')})")
            if t["max_text"]:
                conds.append(f"{t['max_text']} or less (the user's price ceiling)")
            parts.append(f"{kind}: LOW PRICE if {KIND_TEXT[kind]} costs " + " or ".join(conds))
        line = f"- route `{rid}` {h.get('name', '')}: " + ("; ".join(parts) or "no alert targets")
        last = h.get("last") or {}
        low = in_currency(h.get("all_time_low"), currency, rates, site)
        if low:
            line += f". All-time low {describe(low)}, seen {low.get('seen')}"
        same = not currency or (last.get("currency") or currency) == currency
        if last.get("best_value") and same:
            line += f"; last best-value choice {last['best_value']}"
        last_cheap = in_currency(last.get("cheapest"), currency, rates, site)
        if last_cheap:
            line += f"; last check ({last.get('checked')}) cheapest {last_cheap.get('price_text')}"
        lines.append(line + ".")
    take = next((r["take"] for r in reversed(history.get("runs", [])) if r.get("take")), None)
    if take:
        lines.append(f"Your recommendation at the last check: {take}")
    return "\n".join(lines)
