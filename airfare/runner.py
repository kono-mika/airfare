"""One AirFare check: fetch pages, write the price document, ask the analyst (Claude or DeepSeek), notify on LOW PRICE."""
from __future__ import annotations

import asyncio
import logging
import logging.handlers
import math
import os
import socket
import time
from datetime import datetime

from . import (analyst, cleanup, dashboard, deepseek, extension, historypage, i18n, limits, links, money, notify,
               openai_api, platform, pricelog, report, results, serpapi)
from .config import (LOCK_FILE, LOGS_DIR, REPORTS_DIR, ensure_dirs, load_config, load_history, load_state,
                     save_history, save_state)
from .i18n import tr
from .urls import aviasales_url, plan_pages

log = logging.getLogger("airfare")

NETWORK_WAIT = 600
HELD = 4                # run()'s code when nothing was checked: only the browser sources are on, and the limits hold them
last_limits: dict | None = None     # what the limits left out of this process's latest check (Settings says so)


def setup_logging(console: bool = False) -> None:
    ensure_dirs()
    root = logging.getLogger()
    if root.handlers:
        return
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    fh = logging.handlers.RotatingFileHandler(LOGS_DIR / "airfare.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)
    if console:
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        root.addHandler(sh)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


class Busy(RuntimeError):
    """Another AirFare process is using the tracker browser."""


class ProcessLock:
    """Cross-process lock on data/run.lock; the system releases it if the process dies."""

    def __init__(self):
        self._lock = None

    def __enter__(self):
        ensure_dirs()
        lock = platform.FileLock(LOCK_FILE)
        if not lock.acquire():
            raise Busy("another AirFare check (or the tracker browser) is already running")
        self._lock = lock
        return self

    def __exit__(self, *exc):
        self._lock.release()


def wait_for_network(host: str, limit: int = NETWORK_WAIT) -> bool:
    deadline = time.monotonic() + limit
    while True:
        try:
            socket.create_connection((host, 443), timeout=5).close()
            return True
        except OSError as e:
            if time.monotonic() > deadline:
                log.error("no network after %ss: %s", limit, e)
                return False
            time.sleep(15)


def _robot_toast(page: dict) -> None:
    cfg = load_config()
    lang = cfg.get("language")
    site = page.get("site") or "Skyscanner"
    browser = extension.BROWSERS[extension.browser_kind(cfg.get("browser"))]["name"]
    notify.toast(tr("AirFare needs a hand", lang),
                 tr("{site} is asking for a robot check. Please solve it in the {browser} window that just opened; "
                    "AirFare continues by itself afterwards.", lang, site=site, browser=browser))


def _toast_line(analysis: str) -> str:
    """'<route heading> — <first line with a price>' from the analysis."""
    heading = ""
    for raw in analysis.splitlines()[1:]:
        line = raw.strip().lstrip("#*->• ").replace("**", "").strip()
        if not line:
            continue
        if raw.lstrip().startswith("#"):
            heading = line
        elif any(c.isdigit() for c in line):
            return f"{heading} — {line}" if heading else line
    return heading or "A tracked flight got cheaper."


def aviasales_pages(pages: list[dict]) -> tuple[list[dict], list[results.PageResult]]:
    """The Aviasales search for each page, and a failed result for pages Aviasales can't search."""
    out, skipped = [], []
    for p in pages:
        url = aviasales_url(p)
        if url:
            out.append({**p, "url": url, "site": "Aviasales"})
        else:
            skipped.append(results.PageResult(
                page={**p, "site": "Aviasales"}, status="error", source="Aviasales",
                note="Aviasales needs 3-letter airport or city codes and dates within the coming year"))
    return out, skipped


def browser_pages(pages: list[dict], sources: list[str]) -> tuple[list[dict], list[results.PageResult]]:
    """The Skyscanner and Aviasales pages for these trips, each trip's pages next to each other (so a limit that
    cuts the list leaves out whole trips, not one site), and a failed result for those the extension can't open."""
    out, done = [], []
    for p in pages:
        if "extension" in sources:
            out.append({**p, "site": "Skyscanner"})
        if "aviasales" in sources:
            avia, skipped = aviasales_pages([p])
            out += avia
            done += skipped
    # The extension opens only search pages on its own sites; anything else would make it refuse the whole job.
    ok = [extension.allowed(p["url"]) for p in out]
    done += [results.PageResult(page=p, status="error", source=p["site"],
                                note="this link isn't a search results page on a site the extension covers")
             for p, fine in zip(out, ok) if not fine]
    return [p for p, fine in zip(out, ok) if fine], done


async def collect_prices(cfg: dict, pages: list[dict], sources: list[str], automatic: bool = False,
                         test: bool = False) -> tuple[list[results.PageResult], dict | None]:
    """Ask every enabled source for every page, in parallel. Skyscanner and Aviasales pages go to the
    browser extension as one job, so they open together in one minimized window, as many as the limits allow
    (limits.py; automatic is for a scheduled check, test for Test links, whose pages count toward the day but
    don't start the gap). Returns the results and what the limits left out, if anything."""
    wait = int(cfg["wait_seconds"])
    jobs = []
    ext_pages, done = browser_pages(pages, sources)
    ext_pages, held = limits.allow(cfg, ext_pages, automatic)
    if held:
        log.info("limits (%s): %d browser page(s) left out (%s)", held["level"], held["left_out"], held["reason"])
        # Notes on pages that couldn't be opened anyway, only for the trips that weren't left out.
        kept = {(p.get("route_id"), p.get("key")) for p in ext_pages}
        done = [r for r in done if (r.page.get("route_id"), r.page.get("key")) in kept]
    if ext_pages:
        # The pages count once the extension takes the job, before it opens any of them.
        jobs.append(asyncio.to_thread(extension.collect, ext_pages, wait, _robot_toast,
                                      lang=cfg.get("language") or "en", browser=cfg.get("browser") or "chrome",
                                      on_taken=lambda: limits.record(len(ext_pages), check=not test)))
    if "serpapi" in sources:
        jobs.append(serpapi.search_all(pages, cfg.get("serpapi_key") or "", cfg.get("currency") or "EUR"))
    return done + [r for group in await asyncio.gather(*jobs) for r in group], held


async def run_check(automatic: bool = False) -> int:
    global last_limits
    cfg = load_config()
    lang = cfg.get("language")
    pages, left_out = plan_pages(cfg)
    if not pages:
        log.warning("nothing to check: no routes with future dates")
        return 2
    sources = list(cfg.get("sources") or ["extension"])
    if "serpapi" in sources and not cfg.get("serpapi_key"):
        log.warning("Google Flights (SerpApi) is switched on but has no key; skipping it")
        sources.remove("serpapi")
    if not sources:
        return 2
    if "serpapi" not in sources:
        # Only the browser sources: when the limits hold every page, there's nothing to check (or wait online for).
        _, held = limits.allow(cfg, browser_pages(pages, sources)[0], automatic)
        if held and not held["opened"]:
            last_limits = held
            log.info("nothing checked: %s", limits.describe(held, "en"))
            return HELD
    if not await asyncio.to_thread(wait_for_network, cfg["domain"]):
        notify.toast("AirFare", tr("No internet connection, so prices were not checked this time.", lang))
        return 1

    log.info("checking %d pages with %s (%d skipped by the page limit)", len(pages), ", ".join(sources), left_out)
    fetched, held = await collect_prices(cfg, pages, sources, automatic)
    last_limits = held
    currency = cfg.get("currency") or money.DEFAULT
    rates = await asyncio.to_thread(money.rates)
    data = report.collect(fetched, currency, rates)
    when = datetime.now()
    pricelog.add(pricelog.records_from_check(data, when))
    write_history_page(cfg)
    document = report.build_document(data, when, left_out, currency, rates, held)
    stem = f"{when:%Y-%m-%d_%H%M%S}"
    prices_path = REPORTS_DIR / f"{stem}-prices.md"
    prices_path.write_text(document, encoding="utf-8")
    log.info("price document: %s", prices_path)

    history = load_history()
    run_info = {"pages": len(data), "ok": sum(1 for d in data if d.result.status == "ok"), "currency": currency,
                "prices": prices_path.name, "prices_by_route": report.price_summary(data)}
    if not any(d.parsed and d.parsed.flights for d in data) and not any(d.result.text.strip() for d in data):
        reasons = list(dict.fromkeys(f"{d.result.source}: {d.result.note}" for d in data if d.result.note))
        notify.toast(tr("AirFare couldn't read any prices", lang),
                     "; ".join(reasons)[:250] or tr("See the log for details.", lang), prices_path)
        save_history(report.update_history(history, {}, when, {**run_info, "error": "no prices"}))
        cleanup.automatic(cfg)
        return 1
    # Prices were read: the schedule counts from here, whatever the analyst does (it may be "none", or fail).
    state = load_state()
    state["last_check"] = when.isoformat(timespec="minutes")
    save_state(state)

    rules, site = report.alert_rules(cfg), cfg.get("domain") or ""
    bests = report.route_bests(data, rules)
    route_ids = list(dict.fromkeys(p["route_id"] for p in pages))
    targets = report.alert_targets(history, route_ids, rules, currency, rates, site)
    previous = report.previous_records(history, route_ids, targets, rules, currency, rates, site)
    provider, model, name = analyst_choice(cfg)
    if provider == "none":
        # No analyst: AirFare's own rules decide. Cheapest and fastest alert as usual; best value needs an analyst.
        hits = report.threshold_hits(targets, bests, {})
        history = report.update_history(history, bests, when, {**run_info, "analyst": "none", "low_price": bool(hits),
                                                                 "alerted": hits}, alerted=hits, currency=currency,
                                        rates=rates, site=site)
        save_history(history)
        latest = links.for_dashboard(_write_dashboard(cfg, data, history, route_ids, when, "", bool(hits), {}, hits,
                                                      prices_path, "", rates, held))
        cleanup.automatic(cfg)
        log.info("no analyst: %s", f"LOW PRICE {hits}" if hits else "no alert")
        if hits:
            send_alerts(data, hits, targets, bests, {}, None, latest, lang)
        return 0
    try:
        verdict = await analyst.analyse(document, previous, when, model,
                                        max_tokens=int(cfg.get("session_max_k") or 40) * 1000,
                                        provider=provider, language=lang, api_key=analyst_key(cfg, provider))
    except Exception as e:
        log.exception("%s analysis failed", name)
        reason = tr("Claude isn't logged in. Open AirFare and press Log in to Claude.", lang) \
            if provider == "claude" and "logged in" in str(e).lower() else str(e)[:150]
        # The price targets don't need the analyst: cheapest and fastest still alert.
        hits = report.threshold_hits(targets, bests, {})
        history = report.update_history(history, bests, when, {**run_info, "error": provider}, alerted=hits,
                                        currency=currency, rates=rates, site=site)
        save_history(history)
        latest = links.for_dashboard(_write_dashboard(cfg, data, history, route_ids, when, "", bool(hits), {}, hits,
                                                      prices_path, name, rates, held))
        send_alerts(data, hits, targets, bests, {}, None, latest, lang)
        notify.toast("AirFare", tr("Prices were saved, but {name} couldn't analyse them. {reason}", lang,
                                   name=name, reason=reason), latest)
        cleanup.automatic(cfg)
        return 1

    best_values = _best_values(verdict.summary, currency, data, rules)
    hits = report.threshold_hits(targets, bests, best_values)
    low_price, text = bool(hits), verdict.text
    if verdict.low_price and not hits:
        # The alert thresholds are hard rules: never notify for a smaller drop.
        log.warning("%s said LOW PRICE but no alert target was reached; not alerting", name)
        text = text.split("\n", 1)[1].lstrip() if "\n" in text else ""
    elif hits and not verdict.low_price:
        log.warning("%s didn't say LOW PRICE, but these targets were reached: %s", name, hits)

    analysis_path = REPORTS_DIR / f"{stem}-analysis.md"
    analysis_path.write_text(text + "\n", encoding="utf-8")
    take = verdict.summary.get("take") if isinstance(verdict.summary.get("take"), str) else None
    history = report.update_history(history, bests, when, {
        **run_info, "analysis": analysis_path.name, "low_price": low_price, "session_id": verdict.session_id,
        "take": take, "cost_usd": verdict.cost_usd, "analyst": f"{provider}:{model or 'default'}",
        "alerted": hits,
    }, best_values, alerted=hits, currency=currency, rates=rates, site=site)
    save_history(history)
    latest = links.for_dashboard(_write_dashboard(cfg, data, history, route_ids, when, text, low_price,
                                                  verdict.summary, hits, prices_path, name, rates, held))
    cleanup.automatic(cfg)                     # the automatic clean-up picked in Clean up, if any
    log.info("%s %s (%s session %s, $%s): %s", name, model or "default", "resumed" if verdict.resumed else "new",
             verdict.session_id, verdict.cost_usd, f"LOW PRICE {hits}" if low_price else "no alert")

    if low_price:
        send_alerts(data, hits, targets, bests, best_values, take, latest, lang) or \
            notify.toast("LOW PRICE ✈ AirFare", _toast_line(text), latest)
    return 0


KIND_LABELS = {"cheapest": "Cheapest", "fastest": "Fastest", "best": "Best value"}


def alert_message(data, rid: str, kinds: list[str], targets: dict, bests: dict, best_values: dict,
                  take: str | None, lang: str | None) -> tuple[str, list[str], str | None]:
    """(title, lines, booking link) for one route's LOW PRICE alert: what dropped, by how much, and when."""
    pages = [d for d in data if d.page["route_id"] == rid]
    name = pages[0].page.get("route_name", rid) if pages else rid
    found, book = [], None
    for kind in kinds:
        rec = report.best_record(rid, bests, best_values) if kind == "best" else (bests.get(rid) or {}).get(kind)
        if not rec:
            continue
        ref = ((targets.get(rid) or {}).get(kind) or {}).get("ref") or {}
        text = rec.get("price_text") or ""
        if ref.get("price"):
            text += f" (−{(ref['price'] - rec['price']) / ref['price'] * 100:.1f}% " + tr("vs", lang) + f" {ref['text']})"
        detail = []
        if rec.get("depart"):
            d = dashboard._dt(rec["depart"])
            detail.append(i18n.day(d, lang) + (f" → {i18n.day(dashboard._dt(rec['return']), lang)}" if rec.get("return") else ""))
        if rec.get("airlines"):
            detail.append(rec["airlines"])
        if rec.get("stops") is not None:
            detail.append(dashboard.stops_text(rec["stops"], lang))
        if rec.get("minutes"):
            detail.append(dashboard._dur(rec["minutes"]))
        found.append(f"{tr(KIND_LABELS[kind], lang)}: {text}" + (f" · {', '.join(detail)}" if detail else ""))
        book = book or rec.get("url")
    # A notification has room for two lines under the title: what dropped, then the analyst's advice.
    return f"LOW PRICE ✈ {name}", ["; ".join(found), take or ""], book


def send_alerts(data, hits: dict, targets: dict, bests: dict, best_values: dict, take: str | None, latest,
                lang: str | None) -> bool:
    """One sticky notification per alerted route, with Book now and Dashboard buttons. Past three routes, one
    more notification names the rest, so no alert goes unseen."""
    shown = False
    routes = list(hits.items())
    for rid, kinds in routes[:3]:
        title, lines, book = alert_message(data, rid, kinds, targets, bests, best_values, take, lang)
        buttons = ([(tr("Book now", lang), book)] if book else []) + [(tr("Dashboard", lang), latest)]
        shown = notify.alert(title, lines, buttons, open_path=latest, dismiss=tr("Dismiss", lang)) or shown
    if len(routes) > 3:
        names = [next((d.page.get("route_name") for d in data if d.page["route_id"] == rid), rid) for rid, _ in routes[3:]]
        shown = notify.alert("LOW PRICE ✈ AirFare", [tr("Also cheaper: {routes}", lang, routes=", ".join(names))],
                             [(tr("Dashboard", lang), latest)], open_path=latest, dismiss=tr("Dismiss", lang)) or shown
    return shown


def _write_page(path, text: str) -> None:
    """Write a page whole, so a browser or AirFare Settings never reads one half-written."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def write_history_page(cfg: dict) -> None:
    """Refresh reports/history.html, the Price history page that opens from disk."""
    try:
        _write_page(REPORTS_DIR / "history.html", historypage.build(cfg, served=False))
    except Exception:
        log.exception("couldn't write the price history page")


def analyst_choice(cfg: dict) -> tuple[str, str | None, str]:
    """(provider, model, display name) of the analyst picked in Settings; "none" when there is none."""
    provider = cfg.get("llm_provider") or "claude"
    if provider == "none":
        return provider, None, ""
    if provider == "deepseek":
        return provider, cfg.get("deepseek_model") or deepseek.MODELS[0], "DeepSeek"
    if provider == "openai":
        return provider, cfg.get("openai_model") or openai_api.MODELS[0], "ChatGPT"
    if provider == "chatgpt":
        return provider, cfg.get("chatgpt_model") or None, "ChatGPT"
    return "claude", cfg.get("model") or None, "Claude"


def analyst_key(cfg: dict, provider: str) -> str | None:
    """The API key the provider runs with (None for the ChatGPT and Claude accounts)."""
    if provider == "openai":
        return cfg.get("openai_api_key") or None
    if provider == "deepseek":
        return cfg.get("deepseek_api_key") or None
    if provider == "claude":
        return analyst.claude_key(cfg)
    return None


def _write_dashboard(cfg, data, history, route_ids, when, analysis, low_price, summary, alerted,
                     prices_path, analyst_name: str = "Claude", rates: dict | None = None, held: dict | None = None):
    """Rebuild reports/latest.html, the page the LOW PRICE notification and Settings open, in the chosen
    language, plus latest-en/es/ru.html, so the dashboard's language switch works opened from disk too.
    Routes this check didn't include keep their earlier tabs (data/dashboard.json)."""
    rules, currency, site = report.alert_rules(cfg), cfg.get("currency") or money.DEFAULT, cfg.get("domain") or ""
    targets = report.alert_targets(history, route_ids, rules, currency, rates, site)   # after this run: the next alert
    parts = {lang: dashboard.check_parts(data, history, targets, rules, when, analysis, low_price, summary, alerted,
                                         prices_path.name, analyst_name, lang=lang, currency=currency, rates=rates,
                                         site=site, held=held)
             for lang in i18n.LANGS}
    store = dashboard.record_check(dashboard.load_store(), parts, when)
    dashboard.save_store(store)
    return dashboard.write_pages(store, cfg.get("language"))


def _best_values(summary: dict, currency: str, data, rules: dict | None = None) -> dict[str, dict]:
    """The analyst's best-value pick per route, from the machine-readable comment at the end of its reply.

    A pick counts only if it is a fare AirFare actually captured for that route (within half a unit), so a
    made-up or garbled number can never alert. It is marked "excluded" when every captured flight at that
    price is one the user's alert filters leave out."""
    routes = summary.get("routes") if isinstance(summary, dict) else None
    out = {}
    for rid, r in (routes.items() if isinstance(routes, dict) else []):
        if not isinstance(r, dict):
            continue
        try:
            price = float(r["best_value"])
        except (KeyError, TypeError, ValueError):
            continue
        matches = [(f, d) for d in data if d.page["route_id"] == rid and d.parsed and d.parsed.comparable
                   for f in d.parsed.flights if abs(f.price - price) < 0.5]
        if not math.isfinite(price) or price <= 0 or not matches:
            log.warning("ignoring the analyst's best-value pick for %s: it isn't a captured fare", rid)
            continue
        text = r.get("best_value_text") if isinstance(r.get("best_value_text"), str) else ""
        rec = {"price": price, "text": text[:200] or money.fmt(price, currency), "currency": currency}
        for k, field in (("stops", "best_value_stops"), ("minutes", "best_value_minutes")):
            try:
                rec[k] = int(r[field]) if r.get(field) is not None else None
            except (TypeError, ValueError, OverflowError):
                rec[k] = None
        usable = [(f, d) for f, d in matches if not rules or report.usable(f, rules)]
        rec["excluded"] = not usable
        rec["url"] = (usable or matches)[0][1].page.get("url")
        out[rid] = rec
    return out


def run(console: bool = False, automatic: bool = False) -> int:
    """One check; automatic for the scheduled ones (at startup, on the interval), which the limits space out."""
    global last_limits
    last_limits = None
    setup_logging(console)
    try:
        with ProcessLock():
            return asyncio.run(run_check(automatic))
    except Busy as e:
        log.info("skipped: %s", e)
        return 3
    except Exception:
        log.exception("check failed")
        notify.toast("AirFare", tr("The price check failed. See data\\logs\\airfare.log for details.",
                                   load_config().get("language")))
        return 1
