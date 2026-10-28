"""Turn the sites' results feeds into plain flight rows: Skyscanner's web-unified-search JSON and
Aviasales' search results, plus converting a page's prices into the currency AirFare compares in."""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import datetime

from . import money


@dataclass
class Leg:
    origin: str
    destination: str
    depart: str          # local ISO time, e.g. 2026-12-18T06:15:00
    arrive: str
    minutes: int
    stops: int
    airlines: str


@dataclass
class Flight:
    id: str
    price: float
    price_text: str
    legs: list[Leg]
    tags: list[str] = field(default_factory=list)
    score: float | None = None
    self_transfer: bool = False
    orig_text: str = ""          # the price as the site showed it, when AirFare converted it

    @property
    def minutes(self) -> int:
        return sum(leg.minutes for leg in self.legs)

    @property
    def max_stops(self) -> int:
        return max((leg.stops for leg in self.legs), default=0)

    @property
    def airlines(self) -> str:
        names: list[str] = []
        for leg in self.legs:
            for n in leg.airlines.split(" + "):
                if n and n not in names:
                    names.append(n)
        return " + ".join(names)


TOP_N = 3     # flights kept per category


@dataclass
class ParsedPage:
    flights: list[Flight]                    # sorted by price
    picks: dict[str, list[str]]              # "best" / "cheapest" / "fastest" -> up to TOP_N flight ids, in order
    complete: bool
    currency: str
    total_results: int
    note: str = ""                           # extra context for the report, e.g. Google's price insight
    currency_code: str | None = None         # ISO code, when the source says which currency it used
    comparable: bool = True                  # False when the prices couldn't be converted to AirFare's currency


def top_picks(flights: list[Flight], ranked: list[Flight] | None = None, n: int = TOP_N) -> dict[str, list[str]]:
    """The n best, cheapest and fastest flights. `ranked` is the source's own best-first order, if it has one."""
    if ranked is None:
        ranked = sorted(flights, key=lambda f: (-(f.score if f.score is not None else -1.0), f.price))
    return {
        "best": [f.id for f in ranked[:n]],
        "cheapest": [f.id for f in sorted(flights, key=lambda f: f.price)[:n]],
        "fastest": [f.id for f in sorted(flights, key=lambda f: (f.minutes, f.price))[:n]],
    }


def _leg(raw: dict) -> Leg:
    carriers = (raw.get("carriers") or {}).get("marketing") or []
    return Leg(
        origin=(raw.get("origin") or {}).get("displayCode") or (raw.get("origin") or {}).get("id") or "?",
        destination=(raw.get("destination") or {}).get("displayCode") or (raw.get("destination") or {}).get("id") or "?",
        depart=raw.get("departure") or "",
        arrive=raw.get("arrival") or "",
        minutes=int(raw.get("durationInMinutes") or 0),
        stops=int(raw.get("stopCount") or 0),
        airlines=" + ".join(c.get("name", "?") for c in carriers) or "?",
    )


def _flight(raw: dict) -> Flight | None:
    price = raw.get("price") or {}
    if price.get("raw") is None:
        return None
    return Flight(
        id=str(raw.get("id")),
        price=float(price["raw"]),
        price_text=price.get("formatted") or f"{price['raw']:.0f}",
        legs=[_leg(leg) for leg in raw.get("legs") or []],
        tags=list(raw.get("tags") or []),
        score=raw.get("score"),
        self_transfer=bool(raw.get("isSelfTransfer")),
    )


def _itinerary_blocks(body) -> dict | None:
    if isinstance(body, dict) and isinstance(body.get("itineraries"), dict):
        return body["itineraries"]
    return None


def currency_of(price_text: str) -> str:
    return re.sub(r"[\d\s.,]", "", price_text or "") or "?"


def parse_payloads(payloads: list) -> ParsedPage | None:
    """Merge every results payload of one page (the feed is polled, later payloads win)."""
    flights: dict[str, Flight] = {}
    buckets: dict[str, list[str]] = {}
    complete = False
    total = 0
    seen = False
    for body in payloads:
        it = _itinerary_blocks(body)
        if it is None:
            continue
        seen = True
        for raw in it.get("results") or []:
            f = _flight(raw)
            if f:
                flights[f.id] = f
        for bucket in it.get("buckets") or []:
            ids = []
            for item in (bucket.get("items") or [])[:TOP_N]:
                if isinstance(item, dict):
                    f = _flight(item)
                    if f:
                        flights.setdefault(f.id, f)
                    ids.append(str(item.get("id")))
                else:
                    ids.append(str(item))
            if ids:
                buckets[str(bucket.get("id") or bucket.get("name") or "").lower()] = ids
        ctx = it.get("context") or body.get("context") or {}
        complete = str(ctx.get("status", "")).lower() == "complete"
        total = int(ctx.get("totalResults") or len(flights))
    if not seen:
        return None

    ordered = sorted(flights.values(), key=lambda f: f.price)
    picks = top_picks(ordered)
    for name in ("best", "cheapest", "fastest"):       # Skyscanner's own buckets win when the feed has them
        ids = [i for i in buckets.get(name, []) if i in flights]
        if ids:
            picks[name] = ids
    currency = currency_of(ordered[0].price_text) if ordered else "?"
    return ParsedPage(ordered, picks, complete, currency, total)


# ----- Aviasales ------------------------------------------------------------------------------
# A results payload is a list of chunks. Each chunk has its own flight_legs table, and tickets point
# into it by index: ticket -> segments (one per direction) -> flights (leg indices) and transfers.
# The newest payload is a full snapshot of the top tickets in Aviasales' "best" order; a chunk whose
# last_update_timestamp is 0 marks the end of the search.

def is_aviasales(body) -> bool:
    return isinstance(body, list) and any(isinstance(c, dict) and "tickets" in c and "flight_legs" in c for c in body)


def _avia_name(airlines: dict, code: str | None) -> str:
    names = ((airlines or {}).get(code or "") or {}).get("name") or {}
    for value in names.values():
        if isinstance(value, dict) and value.get("default"):
            return str(value["default"])
    return code or "?"


def _avia_time(local: str) -> str:
    try:
        return datetime.strptime(local, "%Y-%m-%d %H:%M").isoformat()
    except (TypeError, ValueError):
        return local or ""


def _avia_flight(ticket: dict, legs: list, airlines: dict) -> tuple[Flight, str | None] | None:
    offers = [p for p in ticket.get("proposals") or []
              if isinstance(p, dict) and isinstance((p.get("price") or {}).get("value"), (int, float))]
    if not offers or not ticket.get("segments"):
        return None
    offer = min(offers, key=lambda p: p["price"]["value"])
    terms = offer.get("flight_terms") or {}
    out, tags, self_transfer = [], [], False
    for seg in ticket["segments"]:
        idx = [i for i in (seg or {}).get("flights") or [] if isinstance(i, int) and 0 <= i < len(legs)]
        hops = [legs[i] for i in idx]
        if not hops or not all(isinstance(h, dict) and h.get("departure_unix_timestamp") for h in hops):
            return None
        names: list[str] = []
        for i, hop in zip(idx, hops):
            code = (((terms.get(str(i)) or {}).get("marketing_carrier_designator") or {}).get("carrier")
                    or (hop.get("operating_carrier_designator") or {}).get("carrier"))
            name = _avia_name(airlines, code)
            if name not in names:
                names.append(name)
        seconds = int(hops[-1].get("arrival_unix_timestamp") or 0) - int(hops[0]["departure_unix_timestamp"])
        out.append(Leg(origin=str(hops[0].get("origin") or "?"), destination=str(hops[-1].get("destination") or "?"),
                       depart=_avia_time(hops[0].get("local_departure_date_time")),
                       arrive=_avia_time(hops[-1].get("local_arrival_date_time")),
                       minutes=max(round(seconds / 60), 0), stops=len(hops) - 1, airlines=" + ".join(names)))
        for t in seg.get("transfers") or []:
            if not isinstance(t, dict):
                continue
            self_transfer |= bool(t.get("recheck_baggage"))   # bags collected and checked in again
            if t.get("night_transfer") and "overnight layover" not in tags:
                tags.append("overnight layover")
            if (t.get("visa_rules") or {}).get("required") and "visa needed" not in tags:
                tags.append("visa needed")
    value = float(offer["price"]["value"])
    code = str(offer["price"].get("currency_code") or "").upper() or None
    flight = Flight(id=str(ticket.get("id")), price=value, price_text=money.fmt(value, code or "RUB"), legs=out,
                    tags=tags, score=ticket.get("score"), self_transfer=self_transfer)
    return flight, code


def parse_aviasales(payloads: list) -> ParsedPage | None:
    """Aviasales results feed -> flights, its "best" order, and whether the search finished."""
    flights: dict[str, Flight] = {}
    ranked: list[str] = []
    same_trip: dict[tuple, str] = {}
    currency, complete, total, seen = None, False, 0, False
    for body in payloads:
        if not is_aviasales(body):
            continue
        seen = True
        for chunk in body:
            if not isinstance(chunk, dict) or "tickets" not in chunk:
                continue
            legs, airlines = chunk.get("flight_legs") or [], chunk.get("airlines") or {}
            cheapest = chunk.get("cheapest_ticket") if isinstance(chunk.get("cheapest_ticket"), dict) else None
            order = []
            for ticket in [*(chunk.get("tickets") or []), *([cheapest] if cheapest else [])]:
                got = _avia_flight(ticket, legs, airlines) if isinstance(ticket, dict) else None
                if not got:
                    continue
                f, code = got
                currency = currency or code
                # The cheapest ticket comes again under its own id; keep one copy of each trip.
                trip = (f.price, tuple((l.depart, l.arrive, l.origin, l.destination) for l in f.legs))
                fid = same_trip.setdefault(trip, f.id)
                flights[fid] = replace(f, id=fid)
                if ticket is not cheapest:
                    order.append((ticket.get("position") or 999, fid))
            if order:
                ranked = [fid for _, fid in sorted(order)]
            complete |= chunk.get("last_update_timestamp") == 0
            total = int((chunk.get("meta") or {}).get("total_tickets_count") or total)
    if not seen:
        return None
    ordered = sorted(flights.values(), key=lambda f: f.price)
    best = [flights[i] for i in dict.fromkeys(ranked) if i in flights]
    return ParsedPage(ordered, top_picks(ordered, best or None), complete, money.sign(currency or "RUB"),
                      max(total, len(flights)), currency_code=currency or "RUB")


# ----- one currency for every page --------------------------------------------------------

def convert_page(parsed: ParsedPage | None, dst: str, table: dict, site: str = "") -> None:
    """Show every price of the page in dst (the currency AirFare compares in), keeping the site's own
    price text in Flight.orig_text. Without an exchange rate the page stays as it was, marked not comparable."""
    if not parsed or not parsed.flights:
        return
    src = parsed.currency_code or money.detect(parsed.flights[0].price_text, site)
    if not src:
        parsed.comparable = False
        parsed.note = (parsed.note + " The currency of these prices is unknown, so they weren't converted.").strip()
        return
    if money.convert(1.0, src, dst, table) is None:
        parsed.comparable, parsed.currency_code = False, src
        parsed.note = (parsed.note + f" Prices are in {src}; there was no exchange rate to convert them to {dst}.").strip()
        return
    for f in parsed.flights:
        if src != dst:
            f.orig_text = f.price_text
            f.price = round(money.convert(f.price, src, dst, table), 2)
        f.price_text = money.fmt(f.price, dst)
    if src != dst:
        line = money.rate_line(dst, table, (src,))
        parsed.note = (parsed.note + f" Prices converted from {src} to {dst}" + (f" ({line})." if line else ".")).strip()
    parsed.currency_code, parsed.currency = dst, money.sign(dst)
