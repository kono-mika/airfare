"""Google Flights prices through SerpApi (https://serpapi.com/google-flights-api).

One search per page (date combination). Identical searches within an hour come from SerpApi's
cache and don't count against the monthly quota.
"""
from __future__ import annotations

import asyncio
import http.client
import json
import logging
import urllib.error
import urllib.request
from datetime import datetime
from urllib.parse import urlencode

from . import money as cash
from .results import PageResult
from .extract import Flight, Leg, ParsedPage, top_picks
from .urls import passengers

log = logging.getLogger(__name__)

API = "https://serpapi.com/search.json"
ACCOUNT_API = "https://serpapi.com/account.json"
CLASSES = {"economy": 1, "premiumeconomy": 2, "business": 3, "first": 4}
# Skyscanner city codes → the airports Google Flights should search.
CITY_AIRPORTS = {
    "lond": "LHR,LGW,STN,LTN,LCY,SEN", "pari": "CDG,ORY,BVA", "nyca": "JFK,EWR,LGA", "rome": "FCO,CIA",
    "mila": "MXP,LIN,BGY", "stoc": "ARN,BMA,NYO", "tyoa": "HND,NRT", "chia": "ORD,MDW", "wasa": "IAD,DCA,BWI",
    "osaa": "KIX,ITM", "sela": "ICN,GMP", "mosc": "SVO,DME,VKO",
}
CONCURRENCY = 4


class SerpApiError(RuntimeError):
    pass


def airports(code: str) -> str:
    code = (code or "").strip().lower()
    if code in CITY_AIRPORTS:
        return CITY_AIRPORTS[code]
    if len(code) == 3 and code.isalpha():
        return code.upper()
    raise SerpApiError(f"Google Flights needs a 3-letter airport code instead of '{code.upper()}'")


def money(amount: float, currency: str) -> str:
    return cash.fmt(amount, currency)


def params(page: dict, api_key: str, currency: str) -> dict:
    adults, kids, infants = passengers(page.get("adults"), page.get("children"))
    p = {
        "engine": "google_flights",
        "departure_id": airports(page.get("origin")),
        "arrival_id": airports(page.get("destination")),
        "outbound_date": page["depart"],
        "type": 1 if page.get("return") else 2,
        "adults": adults,
        "travel_class": CLASSES.get(page.get("cabin") or "economy", 1),
        "currency": currency.upper(),
        "hl": "en",
        "api_key": api_key,
    }
    if kids:
        p["children"] = kids
    if infants:
        p["infants_on_lap"] = infants
    if page.get("return"):
        p["return_date"] = page["return"]
    return p


def _get(url: str, timeout: int = 90) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode("utf-8")).get("error") or str(e)
        except Exception:
            msg = str(e)
        raise SerpApiError(msg) from None
    except urllib.error.URLError as e:
        raise SerpApiError(f"couldn't reach SerpApi: {e.reason}") from None
    except (OSError, http.client.HTTPException) as e:   # a timeout or a cut connection while reading the reply
        raise SerpApiError(f"couldn't read SerpApi's reply: {e}") from None


def _iso(t: str) -> str:
    try:
        return datetime.strptime(t, "%Y-%m-%d %H:%M").isoformat()
    except (TypeError, ValueError):
        return t or ""


def _flight(item: dict, currency: str, best: bool) -> Flight | None:
    segs = item.get("flights") or []
    if not segs or item.get("price") is None:
        return None
    first, last = segs[0], segs[-1]
    names: list[str] = []
    for s in segs:
        if s.get("airline") and s["airline"] not in names:
            names.append(s["airline"])
    minutes = item.get("total_duration") or (sum(s.get("duration", 0) for s in segs)
                                             + sum(l.get("duration", 0) for l in item.get("layovers") or []))
    leg = Leg(
        origin=first["departure_airport"].get("id", "?"),
        destination=last["arrival_airport"].get("id", "?"),
        depart=_iso(first["departure_airport"].get("time")),
        arrive=_iso(last["arrival_airport"].get("time")),
        minutes=int(minutes),
        stops=len(segs) - 1,
        airlines=" + ".join(names) or "?",
    )
    tags = ["google best"] if best else []
    if any(l.get("overnight") for l in item.get("layovers") or []):
        tags.append("overnight layover")
    fid = "|".join(s.get("flight_number", "?") for s in segs) + "@" + leg.depart
    price = float(item["price"])
    return Flight(id=fid, price=price, price_text=money(price, currency), legs=[leg], tags=tags)


def parse(body: dict, currency: str, round_trip: bool) -> ParsedPage:
    # Google's own order (best_flights, then other_flights) is its "Top flights" ranking.
    ranked: list[Flight] = []
    seen: set = set()
    for group, best in (("best_flights", True), ("other_flights", False)):
        for item in body.get(group) or []:
            f = _flight(item, currency, best)
            if not f:
                continue
            # Codeshares repeat the same trip under other flight numbers; keep one.
            same_trip = (f.price, f.legs[0].depart, f.legs[0].arrive, f.airlines)
            if same_trip in seen:
                continue
            seen.add(same_trip)
            ranked.append(f)
    ordered = sorted(ranked, key=lambda f: f.price)
    picks = top_picks(ordered, ranked)
    notes = []
    if round_trip:
        notes.append("Prices are round-trip totals; the table shows the outbound flight "
                     "(the return flight is picked on Google Flights).")
    pi = body.get("price_insights") or {}
    if pi.get("lowest_price") is not None:
        line = f"Google price insight: lowest {money(pi['lowest_price'], currency)}"
        if pi.get("price_level"):
            line += f", price level {pi['price_level']}"
        rng = pi.get("typical_price_range") or []
        if len(rng) == 2:
            line += f", typical {money(rng[0], currency)}–{money(rng[1], currency)}"
        notes.append(line + ".")
    # Google quoted the prices in the currency the request asked for: say so, or the conversion would guess it
    # from the price text (and "kr" or "R" would be read as the wrong currency).
    return ParsedPage(ordered, picks, True, cash.sign(currency), len(ordered), " ".join(notes),
                      currency_code=currency.upper())


def search(page: dict, api_key: str, currency: str) -> PageResult:
    started = datetime.now()
    res = PageResult(page=dict(page), source="Google Flights")
    try:
        body = _get(f"{API}?{urlencode(params(page, api_key, currency))}")
        if body.get("error"):
            raise SerpApiError(body["error"])
        link = str((body.get("search_metadata") or {}).get("google_flights_url") or "")
        res.page["url"] = link if link.startswith("https://") else page["url"]   # used in links and "Book now"
        res.parsed = parse(body, currency, bool(page.get("return")))
        res.status = "ok" if res.parsed.flights else "no_results"
        if not res.parsed.flights:
            res.note = "Google Flights found no flights for these dates"
    except (SerpApiError, KeyError, ValueError) as e:
        res.status, res.note = "error", f"SerpApi: {e}"[:200]
    res.seconds = round((datetime.now() - started).total_seconds(), 1)
    log.info("serpapi %s %s: %s (%d flights, %.0fs) %s", page.get("route_name"), page.get("key"), res.status,
             len(res.parsed.flights) if res.parsed else 0, res.seconds, res.note)
    return res


async def search_all(pages: list[dict], api_key: str, currency: str) -> list[PageResult]:
    if not api_key:
        return [PageResult(page=p, status="error", note="no SerpApi key set in AirFare Settings",
                           source="Google Flights") for p in pages]
    sem = asyncio.Semaphore(CONCURRENCY)

    async def one(p):
        if not p.get("depart") or not p.get("origin"):
            return PageResult(page=p, status="error", note="this link has no dates or airports Google can use",
                              source="Google Flights")
        async with sem:
            return await asyncio.to_thread(search, p, api_key, currency)

    return list(await asyncio.gather(*(one(p) for p in pages)))


def account(api_key: str) -> dict:
    """Plan and searches left this month (this call is free)."""
    body = _get(f"{ACCOUNT_API}?{urlencode({'api_key': api_key})}", timeout=20)
    return {k: body.get(k) for k in ("plan_name", "searches_per_month", "this_month_usage",
                                     "plan_searches_left", "total_searches_left")}
