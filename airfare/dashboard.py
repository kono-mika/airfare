"""The AirFare dashboard (reports/latest.html, plus latest-en/es/ru.html so its language switch also works
opened from disk): the latest check, with one tab per route. A route that's no longer checked keeps its last
section on its own tab until it's cleared, so changing a route never loses what the dashboard showed.
data/dashboard.json keeps the sections in every language, so the page can be rebuilt after a clean-up.

No external files: the trend chart is inline SVG, so the page opens from the notification, from Settings,
or straight from disk, online or not. Its one small script only matters when Settings serves the page.
"""
from __future__ import annotations

import html
import math
import os
from datetime import datetime

from . import brand, i18n, limits, markup, money
from .config import DATA_DIR, REPORTS_DIR, read_json, write_json
from .extract import Flight
from .i18n import tr, trn
from .report import PageData, fastest_trip, usable

SOURCES = ("Skyscanner", "Aviasales", "Google Flights")
SOURCE_COLORS = {"Skyscanner": "var(--s1)", "Aviasales": "var(--s3)", "Google Flights": "var(--s2)"}
SOURCE_DASH = {"Skyscanner": "", "Aviasales": "2 4", "Google Flights": "6 4"}
TREND_RUNS = 30
LIST_SIZE = 3
KIND_LABELS = {"cheapest": "Cheapest", "fastest": "Fastest", "best": "Best value"}
TAGS = {"overnight layover": "overnight layover", "visa needed": "visa needed", "self-transfer": "self-transfer"}

e = html.escape


# ----- small formatting helpers -------------------------------------------------------------

def _dt(iso: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(iso) if iso else None
    except ValueError:
        return None


def _dur(minutes: int) -> str:
    return f"{minutes // 60}h{minutes % 60:02d}"


def stops_text(n: int, lang: str | None) -> str:
    return tr("direct", lang) if n == 0 else trn(n, "{n} stop|{n} stops", lang)


# ----- data gathering ---------------------------------------------------------------------

def _merged(pages: list[PageData], source: str) -> dict[str, list[tuple[Flight, PageData]]]:
    """Top flights per category for one source, across all of a route's date pairs."""
    flights: dict[str, tuple[Flight, PageData]] = {}
    ranked: list[tuple[int, float, str]] = []
    for pd in pages:
        if pd.result.source != source or not pd.parsed:
            continue
        for f in pd.parsed.flights:
            flights.setdefault(f.id, (f, pd))
        for rank, fid in enumerate(pd.parsed.picks.get("best", [])):
            if fid in flights:
                ranked.append((rank, flights[fid][0].price, fid))
    every = list(flights.values())
    best_ids = list(dict.fromkeys(fid for _, _, fid in sorted(ranked)))
    return {
        "best": [flights[i] for i in best_ids[:LIST_SIZE]],
        "cheapest": sorted(every, key=lambda x: x[0].price)[:LIST_SIZE],
        "fastest": sorted(every, key=lambda x: (x[0].minutes, x[0].price))[:LIST_SIZE],
    }


def _cheapest(pages: list[PageData], source: str | None = None, rules: dict | None = None) -> tuple[Flight, PageData] | None:
    """The cheapest flight in AirFare's currency (of one source), counting only flights the alert filters allow."""
    found = [(f, pd) for pd in pages if pd.parsed and pd.parsed.comparable and (source is None or pd.result.source == source)
             for f in pd.parsed.flights if not rules or usable(f, rules)]
    return min(found, key=lambda x: x[0].price) if found else None


cheapest = _cheapest   # also used by other modules


# ----- pieces of the page -----------------------------------------------------------------

def _leg_line(f: Flight, i: int, lang: str) -> str:
    leg = f.legs[i]
    dep, arr = _dt(leg.depart), _dt(leg.arrive)
    plus = ""
    if dep and arr and arr.date() > dep.date():
        plus = f"<sup>+{(arr.date() - dep.date()).days}</sup>"
    dots = "".join(f'<span class="dot" style="left:calc({(k + 1) * 100 / (leg.stops + 1):.0f}% - 4px)"></span>'
                   for k in range(leg.stops))
    return (f'<div class="leg"><span class="day">{e(i18n.day(dep, lang))}</span>'
            f'<span class="t">{dep.strftime("%H:%M") if dep else "?"}</span><span class="bar">{dots}</span>'
            f'<span class="t">{arr.strftime("%H:%M") if arr else "?"}{plus}</span>'
            f'<span class="st">{e(stops_text(leg.stops, lang))}</span></div>')


def _flight_row(f: Flight, pd: PageData, lang: str) -> str:
    legs = "".join(_leg_line(f, i, lang) for i in range(len(f.legs)))
    if len(f.legs) == 1 and pd.page.get("return"):
        legs += (f'<div class="leg muted"><span class="day">{e(i18n.day(_dt(pd.page["return"]), lang))}</span>'
                 f'<span>{e(tr("return picked on {source}", lang, source=pd.result.source))}</span></div>')
    notes = [tr(TAGS.get(t, t.replace("_", " ")), lang) for t in f.tags if t not in ("cheapest", "shortest", "google best")]
    if f.self_transfer:
        notes.append(tr("self-transfer", lang))
    if f.orig_text:
        notes.insert(0, tr("on the site: {price}", lang, price=f.orig_text))
    extra = f'<br><span class="muted">{e(", ".join(notes[:2]))}</span>' if notes else ""
    return (f'<a class="flight" href="{e(pd.page["url"])}" target="_blank" rel="noopener">'
            f'<div class="price">{e(f.price_text)}</div><div class="legs">{legs}</div>'
            f'<div class="meta">{e(f.airlines)}<br>{_dur(f.minutes)}{extra}</div></a>')


def _source_column(pages: list[PageData], source: str, lang: str) -> str:
    merged = _merged(pages, source)
    head = (f'<h3><span class="sw" style="background:{SOURCE_COLORS.get(source, "var(--s3)")}"></span>'
            f'{e(source)}</h3>')
    if not any(merged.values()):
        notes = sorted({pd.result.note for pd in pages if pd.result.source == source and pd.result.note})
        text = tr("No prices this time", lang) + (": " + tr(notes[0], lang) if notes else ".")
        return f'<section class="col">{head}<p class="muted">{e(text)}</p></section>'
    titles = {"best": tr("Best (as ranked by {source})", lang, source=source), "cheapest": tr("Cheapest", lang),
              "fastest": tr("Fastest", lang)}
    blocks = "".join(f'<h4>{e(titles[cat])}</h4>' + "".join(_flight_row(f, pd, lang) for f, pd in rows)
                     for cat, rows in merged.items() if rows)
    return f'<section class="col">{head}{blocks}</section>'


def _trend_svg(runs: list[dict], rid: str, sources: list[str], target: float | None, currency: str,
               rates: dict | None, lang: str, site: str = "") -> str:
    points = []
    for run in runs[-TREND_RUNS:]:
        prices = (run.get("prices_by_route") or {}).get(rid)
        if not prices:
            continue
        # Checks from before a currency change are shown converted, at today's rate.
        src = run.get("currency") or money.detect(next((p.get("text") or "" for p in prices.values()), ""), site) or currency
        values = {}
        for s in sources:
            v = (prices.get(s) or {}).get("cheapest")
            values[s] = money.convert(v, src, currency, rates or {}) if v is not None else None
        if any(v is not None for v in values.values()):
            points.append((run["time"], values))
    if not points:
        return f'<p class="muted">{e(tr("The price trend appears after the next check.", lang))}</p>'
    values = [v for _, d in points for v in d.values() if v is not None] + ([target] if target else [])
    lo, hi = min(values), max(values)
    pad = max((hi - lo) * 0.15, 3)
    lo, hi = max(lo - pad, 0), hi + pad
    w, h, left, right, top, bottom = 640, 210, 56, 92, 14, 26
    n = len(points)

    def x(i):
        return left + (w - left - right) * (i / (n - 1) if n > 1 else 0.5)

    def y(v):
        return top + (h - top - bottom) * (1 - (v - lo) / (hi - lo))

    def price(v):
        return money.fmt(v, currency)

    parts = []
    for k in range(5):
        v = lo + (hi - lo) * k / 4
        parts.append(f'<line class="grid" x1="{left}" x2="{w - right}" y1="{y(v):.1f}" y2="{y(v):.1f}"/>'
                     f'<text class="ax" x="{left - 6}" y="{y(v) + 4:.1f}" text-anchor="end">{e(price(v))}</text>')
    same_day = len({t[:10] for t, _ in points}) == 1
    step = max(1, round(n / 6))
    for i, (t, _) in enumerate(points):
        if i % step == 0 or i == n - 1:
            d = _dt(t)
            label = d.strftime("%H:%M") if same_day else i18n.short_day(d, lang)
            parts.append(f'<text class="ax" x="{x(i):.1f}" y="{h - 6}" text-anchor="middle">{e(label)}</text>')
    if target:
        parts.append(f'<line class="target" x1="{left}" x2="{w - right}" y1="{y(target):.1f}" y2="{y(target):.1f}"/>'
                     f'<text class="ax" x="{w - right + 6}" y="{y(target) + 4:.1f}">'
                     f'{e(tr("alert", lang))} {e(price(target))}</text>')
    for s in sources:
        color, dash = SOURCE_COLORS.get(s, "var(--s3)"), SOURCE_DASH.get(s, "")
        seg, segs = [], []
        for i, (_, d) in enumerate(points):
            if d.get(s) is None:
                if seg:
                    segs.append(seg)
                seg = []
            else:
                seg.append((x(i), y(d[s]), d[s], points[i][0]))
        if seg:
            segs.append(seg)
        for seg in segs:
            if len(seg) > 1:
                pts = " ".join(f"{px:.1f},{py:.1f}" for px, py, _, _ in seg)
                parts.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2" '
                             f'stroke-linejoin="round" stroke-linecap="round" stroke-dasharray="{dash}"/>')
            for px, py, v, t in seg:
                parts.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3.5" fill="{color}" class="pt">'
                             f'<title>{e(s)}: {e(price(v))} ({e(t.replace("T", " "))})</title></circle>')
        if segs:
            px, py, v, _ = segs[-1][-1]
            parts.append(f'<text class="end" x="{px + 8:.1f}" y="{py + 4:.1f}">{e(price(v))}</text>')
    label = tr("Cheapest price per check", lang) + ": " + "; ".join(
        f"{s} {price(points[-1][1][s])}" for s in sources if points[-1][1].get(s) is not None)
    return (f'<svg viewBox="0 0 {w} {h}" class="chart" role="img" aria-label="{e(label)}">'
            f'<title>{e(label)}</title>{"".join(parts)}</svg>')


def _date_grid(pages: list[PageData], sources: list[str], lang: str) -> str:
    keys = sorted({pd.page["key"] for pd in pages})
    if len(keys) < 2:
        return ""
    departs = {pd.page.get("depart") for pd in pages}
    cells, best_key, best_price = [], None, None
    by = {}
    for pd in pages:
        if pd.parsed and pd.parsed.flights and pd.parsed.comparable:
            by[(pd.page["key"], pd.result.source)] = pd.parsed.flights[0]
            p = pd.parsed.flights[0].price
            if best_price is None or p < best_price:
                best_price, best_key = p, pd.page["key"]
    for k in keys:
        dep, ret = (k.split("|") + [""])[:2]
        if len(departs) > 1:
            label = (f"{i18n.short_day(_dt(dep), lang)} → {i18n.short_day(_dt(ret), lang)}" if ret
                     else i18n.short_day(_dt(dep), lang))
        else:
            label = i18n.day(_dt(ret or dep), lang)
        rows = []
        for i, s in enumerate(sources):
            f = by.get((k, s))
            text = e(f.price_text) if f else "—"
            rows.append(f'<p class="{"big" if i == 0 else "small"}">{"" if i == 0 else e(s) + " "}{text}</p>')
        cells.append(f'<div class="tile{" win" if k == best_key else ""}"><p class="lab">{e(label)}</p>{"".join(rows)}</div>')
    title = tr("Cheapest by return date", lang) if len(departs) == 1 else tr("Cheapest by date pair", lang)
    return f'<h3 class="sec">{e(title)}</h3><div class="dates">{"".join(cells)}</div>'


def _alert_note(t: dict | None, lang: str) -> str:
    """'alert at €164' for a kind's tile (or the price ceiling, if that's all it has yet)."""
    if not t:
        return ""
    if t.get("target_text"):
        return tr("alert at {price}", lang, price=t["target_text"])
    if t.get("ref") and t["drop"] <= 0:
        return tr("alert below {price}", lang, price=t["ref"]["text"])
    return tr("alert at {price}", lang, price=t["max_text"]) if t.get("max_text") else ""


def _route_section(rid: str, pages: list[PageData], history: dict, targets: dict, summary: dict,
                   alerted: list[str], analyst_name: str, lang: str, currency: str, rates: dict | None,
                   rules: dict, site: str = "") -> str:
    first = pages[0].page
    name = first.get("route_name") or rid
    present = {pd.result.source for pd in pages}
    sources = [s for s in SOURCES if s in present] + sorted(present - set(SOURCES))
    departs = sorted({pd.page.get("depart") for pd in pages if pd.page.get("depart")})
    returns = sorted({pd.page.get("return") for pd in pages if pd.page.get("return")})

    def span(ds):
        if not ds:
            return ""
        a, b = _dt(ds[0]), _dt(ds[-1])
        if a == b:
            return i18n.day(a, lang)
        if a.month == b.month:
            return f"{a.day}–{i18n.short_day(b, lang)}"
        return f"{i18n.short_day(a, lang)} – {i18n.short_day(b, lang)}"

    when = tr("Out {dates}", lang, dates=span(departs)) + " · " + (
        tr("back {dates}", lang, dates=span(returns)) if returns else tr("one-way", lang))
    origin, dest = (first.get("origin") or "").upper(), (first.get("destination") or "").upper()
    codes = (f'<div class="codes" aria-label="{e(origin)} → {e(dest)}"><span class="iata">{e(origin)}</span>'
             f'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="{brand.PLANE_PATH}"/></svg>'
             f'<span class="iata">{e(dest)}</span></div>') if origin and dest else ""

    def back(pd):
        return " · " + tr("back {dates}", lang, dates=i18n.day(_dt(pd.page.get("return")), lang)) if pd.page.get("return") else ""

    tiles = []
    cheap = _cheapest(pages, rules=rules)
    if cheap:
        f, pd = cheap
        tiles.append(("cheapest", tr("Cheapest", lang), f.price_text, f"{pd.result.source}{back(pd)}"))
    found = [(f, pd) for pd in pages if pd.parsed and pd.parsed.comparable for f in pd.parsed.flights if usable(f, rules)]
    if found:
        f, pd = fastest_trip(found)
        tiles.append(("fastest", tr("Fastest", lang), f.price_text,
                      f"{_dur(f.minutes)} · {stops_text(f.max_stops, lang)} · {pd.result.source}"))
    routes = summary.get("routes") if isinstance(summary.get("routes"), dict) else {}
    rs = routes.get(rid) if isinstance(routes.get(rid), dict) else {}
    try:
        value = float(rs.get("best_value"))
    except (TypeError, ValueError):
        value = None
    if value is not None and math.isfinite(value) and value > 0:
        text = rs.get("best_value_text") if isinstance(rs.get("best_value_text"), str) else ""
        tiles.append(("best", tr("Best value", lang), money.fmt(value, currency),
                      ", ".join(text.split(",")[1:]).strip()[:160] or tr("{name}'s pick", lang, name=analyst_name)))
    for s in sources:
        c = _cheapest(pages, s, rules)
        if c and cheap and s != cheap[1].result.source:
            tiles.append(("", s, c[0].price_text, tr("cheapest", lang) + back(c[1])))
    for kind in ("cheapest", "fastest", "best"):       # kinds with a target but nothing found this time
        if targets.get(kind) and not any(t[0] == kind for t in tiles):
            tiles.append((kind, tr(KIND_LABELS[kind], lang), "—", ""))
    tile_html = ""
    for kind, label, value, sub in tiles:
        note = _alert_note(targets.get(kind), lang) if kind else ""
        hit = ' hit' if kind and kind in alerted else ""
        tile_html += (f'<div class="kpi{hit}"><p class="lab">{e(label)}</p><p class="val">{e(value)}</p>'
                      f'<p class="sub">{e(sub)}</p>' + (f'<p class="next">{e(note)}</p>' if note else "") + '</div>')

    legend = "".join(f'<span><i style="border-top:2px {"dashed" if SOURCE_DASH.get(s) else "solid"} '
                     f'{SOURCE_COLORS.get(s, "var(--s3)")}"></i>{e(tr("{source} cheapest", lang, source=s))}</span>'
                     for s in sources)
    cheap_target = (targets.get("cheapest") or {}).get("target")
    if cheap_target:
        legend += f'<span><i style="border-top:1px dashed var(--muted)"></i>{e(tr("Next cheapest alert", lang))}</span>'
    chart = _trend_svg(history.get("runs", []), rid, sources, cheap_target, currency, rates, lang, site)
    badge = ""
    if alerted:
        kinds = ", ".join(tr(KIND_LABELS[k], lang).lower() for k in alerted)
        badge = f'<span class="badge">{e(tr("Low price", lang))}: {e(kinds)}</span>'
    columns = "".join(_source_column(pages, s, lang) for s in sources)
    return (f'<section class="route"><div class="rhead">{codes}<div><h2>{e(name)} {badge}</h2>'
            f'<p class="muted">{e(when)}</p></div></div>'
            f'<div class="kpis">{tile_html}</div>'
            f'<h3 class="sec">{e(tr("Price trend", lang))}</h3><div class="legend">{legend}</div>{chart}'
            f'{_date_grid(pages, sources, lang)}'
            f'<div class="cols">{columns}</div></section>')


# ----- the page ---------------------------------------------------------------------------

# ----- one check's pieces, and the page put together from the kept routes -------------------

def check_parts(pages: list[PageData], history: dict, targets: dict[str, dict], rules: dict, when: datetime,
                analysis: str, low_price: bool, summary: dict, alerted: dict[str, list[str]], prices_name: str,
                analyst_name: str = "Claude", lang: str = "en", currency: str = money.DEFAULT,
                rates: dict | None = None, site: str = "", held: dict | None = None) -> dict:
    """This check's dashboard in one language: the header (when, what the limits left out, alert banner, the
    analyst's take and full analysis) and one section per route."""
    lang = i18n.norm(lang)
    route_ids = list(dict.fromkeys(pd.page["route_id"] for pd in pages))
    banner = ""
    if low_price:
        names = []
        for rid, kinds in (alerted or {}).items():
            rp = [pd for pd in pages if pd.page["route_id"] == rid]
            if not rp:
                continue
            parts = []
            for kind in kinds:
                label = tr(KIND_LABELS[kind], lang).lower()
                if kind == "cheapest":
                    c = _cheapest(rp, rules=rules)
                    parts.append(f"{label} {c[0].price_text}" if c else label)
                else:
                    parts.append(label)
            names.append(f"{rp[0].page.get('route_name', rid)}: {', '.join(parts)}")
        banner = (f'<div class="alert"><strong>{e(tr("Low price", lang))}</strong> '
                  f'{e(" · ".join(names) or tr("a tracked flight got cheaper", lang))}</div>')
    take = summary.get("take") if isinstance(summary.get("take"), str) else ""
    take_html = (f'<div class="take"><p class="lab">{e(tr("{name}'s take", lang, name=analyst_name))}</p>'
                 f'<p class="voice">{e(take)}</p></div>' if take and analyst_name else "")
    if not analyst_name:
        # No analyst in Settings: the tiles and lists come from AirFare's own rules, and that's all there is.
        analysis_html = f'<p class="muted">{e(tr("No analyst is set up: AirFare picked the cheapest and fastest flights by its own rules. Choose an analyst in Settings for best-value picks and advice.", lang))}</p>'
    else:
        if not analysis:
            analysis = tr("{name} couldn't analyse this check. The prices above are still current.", lang, name=analyst_name)
        elif analysis.splitlines()[0].strip().strip("*#_ ").upper() == "LOW PRICE":
            analysis = analysis.split("\n", 1)[1] if "\n" in analysis else ""
        full = e(tr("{name}'s full analysis", lang, name=analyst_name))
        analysis_html = f'<details><summary>{full}</summary>{markup.to_html(analysis)}</details>'
    routes = {}
    for rid in route_ids:
        rp = [pd for pd in pages if pd.page["route_id"] == rid]
        first = rp[0].page
        routes[rid] = {"name": first.get("route_name") or rid, "origin": (first.get("origin") or "").upper(),
                       "destination": (first.get("destination") or "").upper(),
                       "html": _route_section(rid, rp, history, targets.get(rid) or {}, summary,
                                              (alerted or {}).get(rid, []), analyst_name, lang, currency, rates,
                                              rules or {}, site)}
    ok = sum(1 for pd in pages if pd.result.status == "ok")
    rate = money.rate_line(currency, rates or {})
    credit = f" · {money.CREDIT_HTML}" if money.needs_credit(rates) else ""     # fixed HTML, so not escaped
    return {
        "title": f"AirFare · {i18n.short_day(when, lang)} {when:%H:%M}",
        "checked": e(tr("Checked {when}", lang, when=f"{i18n.day(when, lang, year=True)}, {when:%H:%M}")
                     + " · " + tr("{n} of {total} pages read", lang, n=ok, total=len(pages))
                     + " · " + tr("prices in {currency}", lang, currency=currency))
                   + (f"<br>{e(limits.describe(held, lang))}" if held else ""),
        "banner": banner, "take": take_html,
        "analysis": analysis_html,
        "footer": (f'<p>{e(tr("Full price data:", lang))} <a href="{e(prices_name)}">{e(prices_name)}</a></p>'
                   + (f'<p>{e(tr("Exchange rates ({source}, {date}): {rates}", lang, source=(rates or {}).get("source") or "", date=(rates or {}).get("date") or "", rates=rate))}{credit}</p>' if rate else "")),
        "routes": routes,
    }


KEEP_ROUTES = 20        # earlier routes kept on the dashboard; the oldest go first
STORE_FILE = DATA_DIR / "dashboard.json"


def load_store() -> dict:
    store = read_json(STORE_FILE, {})
    return store if isinstance(store, dict) else {}


def save_store(store: dict) -> None:
    write_json(STORE_FILE, store)


def write_pages(store: dict, lang: str):
    """Write reports/latest-<lang>.html for every language, and latest.html in the chosen one."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    latest = REPORTS_DIR / "latest.html"
    for code in i18n.LANGS:
        text = page(store, code)
        for path in [REPORTS_DIR / f"latest-{code}.html"] + ([latest] if code == i18n.norm(lang) else []):
            tmp = path.with_suffix(".tmp")
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, path)          # whole, so a browser never reads one half-written
    return latest


def record_check(store: dict, parts: dict[str, dict], when: datetime) -> dict:
    """The dashboard store after a check: this check's header, its routes' sections in every language, and
    the earlier routes' last sections, kept until cleared (Clean up, or the button on their tab)."""
    stamp = when.isoformat(timespec="minutes")
    first = next(iter(parts.values()))
    order = list(first["routes"])
    kept = {rid: r for rid, r in (store.get("routes") or {}).items() if isinstance(r, dict) and rid not in order}
    routes = {rid: {**{k: first["routes"][rid][k] for k in ("name", "origin", "destination")}, "checked": stamp,
                    "html": {lang: p["routes"][rid]["html"] for lang, p in parts.items()}} for rid in order}
    for rid in sorted(kept, key=lambda r: kept[r].get("checked") or "", reverse=True)[:max(KEEP_ROUTES - len(order), 0)]:
        routes[rid] = kept[rid]
    head = {lang: {k: v for k, v in p.items() if k != "routes"} for lang, p in parts.items()}
    return {"check": {"time": stamp, "order": order, "html": head}, "routes": routes}


def forget(store: dict, route_ids: list[str] | None = None, everything: bool = False) -> tuple[dict, int]:
    """Remove routes from the dashboard (all of them with everything=True). Returns (store, how many)."""
    routes = dict(store.get("routes") or {})
    gone = list(routes) if everything else [r for r in (route_ids or []) if r in routes]
    for rid in gone:
        routes.pop(rid)
    check = dict(store.get("check") or {})
    check["order"] = [r for r in check.get("order") or [] if r in routes]
    if not routes:
        return {}, len(gone)
    return {"check": check, "routes": routes}, len(gone)


def _pick(versions: dict, lang: str):
    return versions.get(lang) or versions.get("en") or next(iter(versions.values()), None) if versions else None


def _tab_label(r: dict) -> str:
    if r.get("origin") and r.get("destination"):
        return f"{r['origin']} → {r['destination']}"
    return r.get("name") or "?"


def page(store: dict, lang: str = "en") -> str:
    """The dashboard: the latest check's header, then one tab per route; earlier routes keep their last
    check until cleared."""
    lang = i18n.norm(lang)
    routes = {rid: r for rid, r in (store.get("routes") or {}).items() if isinstance(r, dict)}
    check = store.get("check") or {}
    head = _pick(check.get("html") or {}, lang) or {}
    latest = [rid for rid in check.get("order") or [] if rid in routes]
    earlier = sorted((rid for rid in routes if rid not in latest), key=lambda r: routes[r].get("checked") or "", reverse=True)
    order = latest + earlier
    if not order:
        body = (f'<div class="empty">{brand.SKY_SVG}<h2>{e(tr("No dashboard yet", lang))}</h2><p>'
                f'{e(tr("It appears after the first price check. Save your routes in Settings, then press Run check now.", lang))}'
                f'</p></div>')
        return PAGE.format(lang=lang, tokens=brand.TOKENS_CSS + brand.NAV_CSS + brand.LEGAL_CSS,
                           top=brand.top_bar("dashboard", lang), nav_script=brand.NAV_SCRIPT, dash_script="",
                           favicon=brand.FAVICON, title="AirFare", checked="", banner="", take="", tabs="", routes=body,
                           analysis="", footer=brand.legal(lang))
    tabs, panels = [], []
    for rid in order:
        r = routes[rid]
        when = _dt(r.get("checked"))
        old = rid not in latest
        date = f' <small>{e(i18n.short_day(when, lang))}</small>' if old and when else ""
        tabs.append(f'<button type="button" role="tab" data-route="{e(rid)}" title="{e(r.get("name") or "")}">'
                    f'{e(_tab_label(r))}{date}</button>')
        note = ""
        if old:
            ask = tr("Remove {name} from the dashboard? Its price history stays.", lang, name=r.get("name") or _tab_label(r))
            note = (f'<div class="earlier"><p>{e(tr("Earlier route, last checked {when}. It isn't in the latest check.", lang, when=i18n.day(when, lang, year=True) if when else "?"))}</p>'
                    f'<button type="button" class="btn" data-forget="{e(rid)}" data-ask="{e(ask)}" hidden>'
                    f'{e(tr("Remove from the dashboard", lang))}</button></div>')
        panels.append(f'<div class="rpanel" role="tabpanel" data-route="{e(rid)}">{note}{_pick(r.get("html") or {}, lang) or ""}</div>')
    strip = (f'<nav class="rtabs" role="tablist" aria-label="{e(tr("Routes", lang))}" data-check="{e(check.get("time") or "")}">'
             f'{"".join(tabs)}</nav>' if len(order) > 1 else "")
    return PAGE.format(
        lang=lang, tokens=brand.TOKENS_CSS + brand.NAV_CSS + brand.LEGAL_CSS, top=brand.top_bar("dashboard", lang),
        nav_script=brand.NAV_SCRIPT, dash_script=DASH_SCRIPT, favicon=brand.FAVICON,
        title=e(head.get("title") or "AirFare"),
        checked=f'<p class="muted" style="margin:-8px 0 14px">{head.get("checked") or ""}</p>' if head.get("checked") else "",
        banner=head.get("banner") or "", take=head.get("take") or "", tabs=strip, routes="".join(panels),
        analysis=head.get("analysis") or "", footer=(head.get("footer") or "") + brand.legal(lang))


def build(pages: list[PageData], history: dict, targets: dict[str, dict], rules: dict, when: datetime,
          analysis: str, low_price: bool, summary: dict, alerted: dict[str, list[str]], prices_name: str,
          analyst_name: str = "Claude", lang: str = "en", currency: str = money.DEFAULT,
          rates: dict | None = None, site: str = "") -> str:
    """One check's dashboard on its own (no earlier routes)."""
    parts = check_parts(pages, history, targets, rules, when, analysis, low_price, summary, alerted, prices_name,
                        analyst_name, lang, currency, rates, site)
    return page(record_check({}, {i18n.norm(lang): parts}, when), lang)


# The route tabs: show one route at a time and remember the last one picked. Served by AirFare, an earlier
# route's tab also offers "Remove from the dashboard". Without scripts every route simply shows in a row.
DASH_SCRIPT = """<script>
(() => {
  const tabs = [...document.querySelectorAll(".rtabs button")];
  const panels = [...document.querySelectorAll(".rpanel")];
  // The tab picked is remembered for this check only: after the next check the latest route shows first.
  const key = "airfare.route:" + ((document.querySelector(".rtabs") || {}).dataset || {}).check;
  const show = id => {
    tabs.forEach(t => t.setAttribute("aria-selected", String(t.dataset.route === id)));
    panels.forEach(p => { p.hidden = p.dataset.route !== id; });
    try { localStorage.setItem(key, id); } catch (e) { /* private window */ }
  };
  if (tabs.length) {
    tabs.forEach(t => t.addEventListener("click", () => show(t.dataset.route)));
    let start = null;
    try { start = localStorage.getItem(key); } catch (e) { /* private window */ }
    show(tabs.some(t => t.dataset.route === start) ? start : tabs[0].dataset.route);
  }
  if (!location.protocol.startsWith("http")) return;
  document.querySelectorAll("[data-forget]").forEach(b => {
    b.hidden = false;
    b.addEventListener("click", async () => {
      if (!confirm(b.dataset.ask)) return;
      const r = await fetch("/api/cleanup", {method: "POST", body: JSON.stringify({action: "dashboard", route_ids: [b.dataset.forget]}),
        headers: {"Content-Type": "application/json", "X-AirFare": "1"}});
      if (r.ok) location.reload();
      else alert(((await r.json().catch(() => ({}))).error) || r.status);
    });
  });
})();
</script>"""


PAGE = """<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<link rel="icon" href="{favicon}">
<style>{tokens}
:root {{ --bg:var(--paper); --fg:var(--ink); --accent:var(--sky); --warn-fg:var(--warn); --win:var(--sky); }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--fg); font:15px/1.5 var(--text); }}
body::before {{ content:""; display:block; height:6px; background:var(--stripe); }}
main {{ max-width:1080px; margin:0 auto; padding:24px 16px 56px; }}
h2 {{ font:600 20px/1.2 var(--display); margin:0; }}
h3 {{ font:600 16px var(--display); margin:0 0 8px; }}
h4 {{ font-size:13px; margin:14px 0 4px; color:var(--muted); font-weight:600; }}
p {{ margin:0; }} a {{ color:var(--accent); }}
.muted {{ color:var(--muted); font-size:13px; }}
.alert {{ position:relative; overflow:hidden; background:var(--warn-bg); color:var(--warn-fg); border-radius:10px;
  padding:10px 14px 10px 24px; margin-bottom:14px; }}
.alert::before {{ content:""; position:absolute; left:0; top:0; bottom:0; width:8px; background:var(--stripe); }}
.take {{ border-left:3px solid var(--accent); padding:2px 0 2px 14px; margin:0 0 20px; }}
.voice {{ font-family:Georgia,"Times New Roman",serif; font-size:17px; line-height:1.55; margin-top:2px;
  font-variant-numeric:lining-nums; }}
.lab {{ font-size:12px; color:var(--muted); }}
.route {{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:18px; margin-bottom:20px; }}
.rhead {{ display:flex; gap:18px; align-items:center; flex-wrap:wrap; margin-bottom:16px; padding-bottom:14px;
  border-bottom:2px dashed var(--line); }}
.codes {{ display:flex; align-items:center; gap:8px; background:var(--sky-soft); border-radius:10px; padding:8px 14px; }}
.codes .iata {{ font:600 26px/1 var(--display); letter-spacing:.05em; }}
.codes svg {{ width:22px; height:22px; fill:var(--sky); }}
.badge {{ font-size:12px; font-weight:500; background:var(--warn-bg); color:var(--warn-fg); border-radius:6px; padding:2px 8px; vertical-align:3px; }}
.kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:10px; margin-bottom:18px; }}
.kpi {{ background:var(--soft); border-radius:10px; padding:12px 14px; min-width:0; border:1.5px solid transparent; }}
.kpi.hit {{ border-color:var(--warn); background:var(--warn-bg); }}
.kpi .val {{ font:600 26px var(--display); font-variant-numeric:tabular-nums; }}
.kpi .sub {{ font-size:12px; color:var(--muted); overflow-wrap:anywhere; }}
.kpi .next {{ font-size:12px; margin-top:4px; padding-top:4px; border-top:1px dashed var(--line); }}
.sec {{ margin-top:6px; }}
.legend {{ display:flex; gap:16px; flex-wrap:wrap; font-size:12px; color:var(--muted); margin-bottom:4px; }}
.legend span {{ display:flex; align-items:center; gap:6px; }} .legend i {{ width:16px; height:0; display:inline-block; }}
.chart {{ width:100%; height:auto; display:block; margin-bottom:16px; }}
.chart .grid {{ stroke:var(--line); stroke-width:1; }} .chart .target {{ stroke:var(--muted); stroke-dasharray:3 3; }}
.chart .ax {{ fill:var(--muted); font-size:11px; }} .chart .end {{ fill:var(--fg); font-size:12px; font-weight:600; }}
.chart .pt {{ stroke:var(--card); stroke-width:2; }}
.dates {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(120px,1fr)); gap:8px; margin-bottom:18px; }}
.tile {{ background:var(--soft); border-radius:10px; padding:10px 12px; border:1.5px solid transparent; }}
.tile.win {{ border-color:var(--win); }} .tile .big {{ font:600 20px var(--display); font-variant-numeric:tabular-nums; }}
.tile .small {{ font-size:12px; color:var(--muted); }}
.cols {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr)); gap:18px; }}
.col h3 {{ display:flex; align-items:center; gap:8px; border-bottom:1px solid var(--line); padding-bottom:6px; }}
.sw {{ width:10px; height:10px; border-radius:2px; display:inline-block; }}
.flight {{ display:grid; grid-template-columns:84px minmax(0,1fr) 108px; gap:10px; align-items:center; padding:9px 6px;
  border-bottom:1px solid var(--line); color:inherit; text-decoration:none; border-radius:6px; }}
.flight:hover {{ background:var(--soft); }}
.price {{ font:600 18px var(--display); font-variant-numeric:tabular-nums; }}
.legs {{ display:grid; gap:3px; min-width:0; }}
.leg {{ display:flex; align-items:center; gap:7px; font-size:12px; font-variant-numeric:tabular-nums; min-width:0; }}
.leg .day {{ width:74px; color:var(--muted); flex:none; white-space:nowrap; }} .leg .t {{ flex:none; }} .leg sup {{ font-size:9px; }}
.leg .st {{ width:72px; text-align:right; color:var(--muted); flex:none; }}
.bar {{ flex:1; height:2px; background:var(--muted); position:relative; min-width:24px; opacity:.6; }}
.dot {{ position:absolute; top:-3px; width:8px; height:8px; border-radius:50%; background:var(--card); border:1.5px solid var(--fg); }}
.meta {{ font-size:12px; text-align:right; overflow-wrap:anywhere; }}
details {{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:12px 18px; }}
summary {{ cursor:pointer; font-weight:600; }}
details table {{ border-collapse:collapse; font-size:13px; display:block; overflow-x:auto; }}
details th, details td {{ border-bottom:1px solid var(--line); padding:4px 8px; text-align:left; }}
footer {{ margin-top:16px; }} footer p {{ margin-top:4px; }}
.rtabs {{ display:flex; gap:6px; flex-wrap:wrap; margin:0 0 14px; }}
.rtabs button {{ font:600 15px var(--display); letter-spacing:.03em; border:1px solid var(--line); background:var(--card);
  color:var(--ink); border-radius:999px; padding:6px 14px; cursor:pointer; }}
.rtabs button small {{ font:400 12px var(--text); color:var(--muted); margin-left:4px; letter-spacing:0; }}
.rtabs button[aria-selected="true"] {{ background:var(--sky); border-color:var(--sky); color:var(--sky-ink); }}
.rtabs button[aria-selected="true"] small {{ color:inherit; opacity:.8; }}
.earlier {{ display:flex; gap:12px; align-items:center; justify-content:space-between; flex-wrap:wrap;
  background:var(--soft); border-radius:10px; padding:8px 14px; margin-bottom:12px; font-size:13px; color:var(--muted); }}
.btn {{ border:1px solid var(--line); background:var(--card); color:var(--ink); border-radius:8px; padding:5px 12px;
  cursor:pointer; font:inherit; }}
.btn:hover {{ border-color:var(--sky); color:var(--sky); }}
.empty {{ max-width:520px; margin:40px auto 0; text-align:center; }} .empty .sky {{ width:100%; color:var(--muted); }}
.empty h2 {{ font:600 26px var(--display); margin:8px 0 6px; }} .empty p {{ color:var(--muted); }}
[hidden] {{ display:none !important; }}
@media (max-width:560px) {{ .flight {{ grid-template-columns:72px minmax(0,1fr); }} .meta {{ grid-column:2; text-align:left; }}
  .leg .day {{ display:none; }} }}
</style></head>
<body><main>
{top}
{checked}
{banner}{take}{tabs}{routes}
{analysis}
<footer class="muted">{footer}</footer>
</main>{nav_script}{dash_script}</body></html>
"""
