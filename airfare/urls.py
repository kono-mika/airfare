"""Turn routes (airports + date ranges) into the Skyscanner result pages to check."""
from __future__ import annotations

import re
from datetime import date, timedelta
from urllib.parse import parse_qs, urlencode, urlparse

CABINS = ("economy", "premiumeconomy", "business", "first")

# The first two path parts are localized: /transport/flights/, /transporte/vuelos/, /transports/vols/, ...
_PATH_RE = re.compile(r"^/[^/]+/[^/]+/([a-z0-9]{2,8})/([a-z0-9]{2,8})/(\d{6})(?:/(\d{6}))?(?:/|$)", re.I)


def yymmdd(d: date) -> str:
    return d.strftime("%y%m%d")


def _from_yymmdd(s: str) -> date:
    return date(2000 + int(s[:2]), int(s[2:4]), int(s[4:6]))


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


def date_span(start: str | None, end: str | None) -> list[date]:
    """Every day from start to end inclusive; a missing end means just the start day."""
    if not start:
        return []
    a = date.fromisoformat(start)
    b = date.fromisoformat(end) if end else a
    if b < a:
        a, b = b, a
    return [a + timedelta(days=i) for i in range((b - a).days + 1)]


MAX_CHILDREN = 8
CHILD_MAX_AGE = 15         # Skyscanner counts travellers up to 15 as children (by age); older ones are adults


def clean_ages(raw) -> list[int] | None:
    """Children's ages as a sorted list, from a list or a typed "4, 9"; None when they aren't ages."""
    if raw in (None, ""):
        return []
    parts = re.split(r"[,\s;]+", raw.strip()) if isinstance(raw, str) else list(raw)
    ages = []
    for p in parts:
        if p in ("", None):
            continue
        try:
            age = int(p)
        except (TypeError, ValueError):
            return None
        if not 0 <= age <= CHILD_MAX_AGE:
            return None
        ages.append(age)
    return sorted(ages) if len(ages) <= MAX_CHILDREN else None


def passengers(adults, ages) -> tuple[int, int, int]:
    """(adults, children, infants) the way Aviasales and Google Flights count: under 2 is an infant, 2 to 11 a
    child, 12 and over an adult."""
    ages = clean_ages(ages) or []
    grown = max(1, min(9, int(adults or 1))) + sum(1 for a in ages if a >= 12)
    return min(grown, 9), min(sum(1 for a in ages if 2 <= a <= 11), 9), min(sum(1 for a in ages if a < 2), 9)


def build_url(domain: str, origin: str, destination: str, depart: date, ret: date | None = None,
              adults: int = 1, cabin: str = "economy", direct_only: bool = False, children=()) -> str:
    path = f"/transport/flights/{origin.lower()}/{destination.lower()}/{yymmdd(depart)}/"
    if ret:
        path += f"{yymmdd(ret)}/"
    query = {
        "adultsv2": adults,
        "cabinclass": cabin,
        "childrenv2": "|".join(str(a) for a in (clean_ages(children) or [])),     # the children's ages
        "inboundaltsenabled": "false",
        "outboundaltsenabled": "false",
        "preferdirects": str(bool(direct_only)).lower(),
        "rtn": 1 if ret else 0,
    }
    return f"https://{domain}{path}?{urlencode(query)}"


# Aviasales.ru: /search/<from><DDMM><to>[<DDMM back>][class]<adults>, e.g. BCN1503LON18031. City searches use
# IATA city codes, so Skyscanner's own city codes are mapped to them.
AVIASALES_SITE = "www.aviasales.ru"
AVIASALES_CLASS = {"economy": "", "premiumeconomy": "w", "business": "c", "first": "f"}
CITY_CODES = {"lond": "LON", "pari": "PAR", "nyca": "NYC", "rome": "ROM", "mila": "MIL", "stoc": "STO",
              "tyoa": "TYO", "chia": "CHI", "wasa": "WAS", "osaa": "OSA", "sela": "SEL", "mosc": "MOW"}
AVIASALES_DAYS = 360     # its links carry no year, so only dates within the coming year are unambiguous


def iata(code: str | None) -> str | None:
    """A 3-letter airport or city code for sites that take only IATA codes."""
    code = (code or "").strip().lower()
    if code in CITY_CODES:
        return CITY_CODES[code]
    return code.upper() if len(code) == 3 and code.isalpha() else None


def aviasales_url(page: dict, today: date | None = None) -> str | None:
    """The Aviasales search for one page's airports, dates, travellers and cabin, or None if it has none."""
    origin, dest = iata(page.get("origin")), iata(page.get("destination"))
    try:
        depart = date.fromisoformat(page["depart"]) if page.get("depart") else None
        ret = date.fromisoformat(page["return"]) if page.get("return") else None
    except ValueError:
        return None
    today = today or date.today()
    if not (origin and dest and depart) or not 0 <= (depart - today).days <= AVIASALES_DAYS:
        return None
    if ret and (ret < depart or (ret - today).days > AVIASALES_DAYS):
        return None
    adults, kids, infants = passengers(page.get("adults"), page.get("children"))
    cls = AVIASALES_CLASS.get(page.get("cabin") or "economy", "")
    back = ret.strftime("%d%m") if ret else ""
    who = f"{adults}{kids}{infants}" if kids or infants else str(adults)     # adults, children, infants
    return f"https://{AVIASALES_SITE}/search/{origin}{depart:%d%m}{dest}{back}{cls}{who}"


def parse_url(url: str) -> dict | None:
    """Read origin, destination, dates, adults and cabin out of a Skyscanner results URL, if it has the usual
    shape (so the other sources search the same trip)."""
    parts = urlparse(url.strip())
    m = _PATH_RE.search(parts.path)
    if not m:
        return None
    try:
        depart = _from_yymmdd(m.group(3))
        ret = _from_yymmdd(m.group(4)) if m.group(4) else None
    except ValueError:
        return None
    out = {"origin": m.group(1).lower(), "destination": m.group(2).lower(), "depart": _iso(depart), "return": _iso(ret)}
    query = parse_qs(parts.query)
    adults = (query.get("adultsv2") or query.get("adults") or [""])[0]
    if adults.isdigit() and 1 <= int(adults) <= 9:
        out["adults"] = int(adults)
    cabin = (query.get("cabinclass") or [""])[0].lower()
    if cabin in CABINS:
        out["cabin"] = cabin
    kids = (query.get("childrenv2") or [""])[0].replace("|", ",")
    if kids and clean_ages(kids):
        out["children"] = clean_ages(kids)
    return out


def page_key(depart: str | None, ret: str | None) -> str:
    return f"{depart or ''}|{ret or ''}"


def route_label(route: dict) -> str:
    if route.get("name"):
        return route["name"]
    if route.get("origin") and route.get("destination"):
        arrow = "⇄" if route.get("trip") == "return" else "→"
        return f"{route['origin'].upper()} {arrow} {route['destination'].upper()}"
    return f"Route {route.get('id', '?')}"


def route_pages(route: dict, domain: str, today: date | None = None) -> list[dict]:
    """All pages for one route: generated date combinations, with pasted URLs replacing or adding pages."""
    today = today or date.today()
    pages: dict[str, dict] = {}

    if route.get("origin") and route.get("destination"):
        departs = [d for d in date_span(route.get("depart_from"), route.get("depart_to")) if d >= today]
        if route.get("trip") == "return":
            returns = date_span(route.get("return_from"), route.get("return_to"))
            combos = [(d, r) for d in departs for r in returns if r >= d]
        else:
            combos = [(d, None) for d in departs]
        for d, r in combos:
            key = page_key(_iso(d), _iso(r))
            pages[key] = {
                "key": key, "depart": _iso(d), "return": _iso(r), "source": "auto",
                "origin": route["origin"], "destination": route["destination"],
                "url": build_url(domain, route["origin"], route["destination"], d, r,
                                 int(route.get("adults") or 1), route.get("cabin") or "economy",
                                 bool(route.get("direct_only")), route.get("children") or []),
            }

    for i, manual in enumerate(route.get("manual_pages") or []):
        url = (manual.get("url") or "").strip()
        if not url:
            continue
        info = parse_url(url) or {}
        depart, ret = info.get("depart"), info.get("return")
        if depart and date.fromisoformat(depart) < today:
            continue
        key = manual.get("key") or (page_key(depart, ret) if depart else f"manual-{i}")
        pages[key] = {"key": key, "depart": depart, "return": ret, "url": url, "source": "manual",
                      "origin": info.get("origin") or route.get("origin"),
                      "destination": info.get("destination") or route.get("destination"),
                      "adults": info.get("adults"), "cabin": info.get("cabin"), "children": info.get("children")}

    return sorted(pages.values(), key=lambda p: (p["depart"] or "9999", p["return"] or "", p["key"]))


def plan_pages(cfg: dict, today: date | None = None) -> tuple[list[dict], int]:
    """Pages for every enabled route, capped at max_pages and shared fairly between routes.

    Returns (pages, number_left_out_by_the_cap).
    """
    per_route = [(r, route_pages(r, cfg["domain"], today))
                 for r in cfg.get("routes", []) if r.get("enabled", True)]
    cap = int(cfg.get("max_pages") or 20)
    out: list[dict] = []
    i = 0
    while len(out) < cap and any(i < len(p) for _, p in per_route):
        for route, pages in per_route:
            if i < len(pages) and len(out) < cap:
                # A pasted link's own travellers and cabin win over the route card's.
                kids = pages[i].get("children")
                out.append({**pages[i], "route_id": route["id"], "route_name": route_label(route),
                            "adults": pages[i].get("adults") or int(route.get("adults") or 1),
                            "children": list(kids if kids is not None else (route.get("children") or [])),
                            "cabin": pages[i].get("cabin") or route.get("cabin") or "economy",
                            "direct_only": bool(route.get("direct_only"))})
        i += 1
    total = sum(len(p) for _, p in per_route)
    return out, total - len(out)
