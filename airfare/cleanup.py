"""Clean up: what AirFare keeps about past checks, and removing parts of it.

The Clean up page (static/cleanup.html) shows a summary and runs one action at a time. Every action can
run as a dry run first, so the page can say exactly how much a button will delete before it's pressed.
Settings and API keys are never touched here. Automatic clean-up (Settings → cfg["cleanup"]) runs the
same actions after every check.
"""
from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import date, datetime, timedelta

from . import dashboard, deepseek, i18n, pricelog
from .config import LOGS_DIR, REPORTS_DIR, load_history, load_state, save_history, save_state
from .i18n import Problem

log = logging.getLogger(__name__)

ACTIONS = ("records", "lookups", "dashboard", "alerts", "reports", "logs", "conversations", "everything")
PROVIDERS = ("claude", "deepseek", "openai", "chatgpt")


def _yes(o: dict, key: str) -> bool:
    """A switch from the page: only a real true counts ("false", "no" or 1 never delete everything)."""
    return o.get(key) is True


def _id(value) -> str:
    return value if isinstance(value, str) else ""


def _days(value) -> int | None:
    """A number of days from the page: None when empty, otherwise 1 to 3650."""
    if value in (None, "", 0, "0"):
        return None
    try:
        days = int(value)
    except (TypeError, ValueError, OverflowError):
        raise Problem("Enter a number of days, like 30")
    if not 1 <= days <= 3650:
        raise Problem("Enter a number of days, like 30")
    return days


def _cutoff(days: int | None) -> str | None:
    return (datetime.now() - timedelta(days=days)).isoformat(timespec="minutes") if days else None


def _route_names(cfg: dict) -> dict[str, dict]:
    """Every route AirFare knows: the ones in Settings, then ones that live on only in history or the dashboard."""
    from .urls import route_label
    out = {r["id"]: {"name": route_label(r), "tracked": True} for r in cfg.get("routes") or []}
    for rec in pricelog.load():
        out.setdefault(rec.get("route_id"), {"name": rec.get("route_name") or rec.get("route_id"), "tracked": False})
    for rid, h in (load_history().get("routes") or {}).items():
        out.setdefault(rid, {"name": h.get("name") or rid, "tracked": False})
    for rid, r in (dashboard.load_store().get("routes") or {}).items():
        out.setdefault(rid, {"name": r.get("name") or rid, "tracked": False})
    return out


def _report_files() -> list:
    """Check reports (prices and analysis), newest first."""
    if not REPORTS_DIR.exists():
        return []
    return sorted((f for pattern in ("*-prices.md", "*-analysis.md") for f in REPORTS_DIR.glob(pattern)),
                  key=lambda f: f.name, reverse=True)


def _conversations(state: dict) -> dict[str, bool]:
    slots = {"claude": state, **{p: state.get(p) or {} for p in PROVIDERS if p != "claude"}}
    return {p: bool((slots[p] or {}).get("session_id")) for p in PROVIDERS}


def summary(cfg: dict) -> dict:
    records, research, history = pricelog.load(), pricelog.load_research(), load_history()
    store = dashboard.load_store()
    names = _route_names(cfg)
    today = date.today().isoformat()
    per_route = Counter(r.get("route_id") for r in records)
    lookups = Counter(r.get("route_id") for r in research)
    latest = set((store.get("check") or {}).get("order") or [])
    routes = []
    for rid, info in names.items():
        h = (history.get("routes") or {}).get(rid) or {}
        on_dash = (store.get("routes") or {}).get(rid)
        routes.append({"id": rid, "name": info["name"], "tracked": info["tracked"], "records": per_route.get(rid, 0),
                       "lookups": lookups.get(rid, 0), "alerts": bool(h.get("alert_refs") or h.get("alert_ref")),
                       "dashboard": bool(on_dash), "latest": rid in latest,
                       "checked": (on_dash or {}).get("checked") or (h.get("last") or {}).get("checked")})
    reports = _report_files()
    logs = [f for f in LOGS_DIR.glob("airfare.log*")] if LOGS_DIR.exists() else []
    return {
        "routes": routes,
        "records": {"total": len(records), "oldest": min((r.get("time") or "" for r in records), default=None),
                    "sources": dict(Counter(r.get("source") for r in records)),
                    "past_trips": sum(1 for r in records if (r.get("depart") or "9999") < today)},
        "lookups": len(research),
        "reports": {"files": len(reports), "bytes": sum(f.stat().st_size for f in reports)},
        "logs": {"bytes": sum(f.stat().st_size for f in logs)},
        "conversations": _conversations(load_state()),
        "auto": cfg.get("cleanup") or {},
    }


# ----- the actions ------------------------------------------------------------------------

def _records(o: dict, dry: bool) -> int:
    records = pricelog.load()
    route, source, past = _id(o.get("route_id")), _id(o.get("source")), _yes(o, "past_trips")
    if _yes(o, "everything"):
        gone = records
    else:
        days, today = _cutoff(_days(o.get("older_than_days"))), date.today().isoformat()
        if not (route or source or days or past):
            raise Problem("Pick which records to delete")
        gone = [r for r in records
                if (not route or r.get("route_id") == route)
                and (not source or r.get("source") == source)
                and (not days or (r.get("time") or "") < days)
                and (not past or (r.get("depart") or "9999") < today)]
    if not dry and gone:
        if _yes(o, "everything"):
            pricelog.delete(everything=True)
        else:
            pricelog.delete(ids=[r.get("id") for r in gone])
    return len(gone)


def _lookups(o: dict, dry: bool) -> int:
    items = pricelog.load_research()
    days, route = _cutoff(_days(o.get("older_than_days"))), _id(o.get("route_id"))
    gone = items if _yes(o, "everything") else [
        r for r in items if (not route or r.get("route_id") == route) and (not days or (r.get("time") or "") < days)]
    if not dry and gone:
        pricelog.delete_research(ids=[r.get("id") for r in gone])
    return len(gone)


def _dashboard(o: dict, dry: bool, lang: str) -> int:
    store = dashboard.load_store()
    latest = set((store.get("check") or {}).get("order") or [])
    routes = store.get("routes") or {}
    days = _cutoff(_days(o.get("older_than_days")))
    if _yes(o, "everything"):
        ids = list(routes)
    elif _yes(o, "earlier") or days:
        ids = [rid for rid, r in routes.items() if rid not in latest and (not days or (r.get("checked") or "") < days)]
    else:
        wanted = o.get("route_ids") if isinstance(o.get("route_ids"), list) else []
        ids = [rid for rid in wanted if isinstance(rid, str) and rid in routes]
    if not dry and ids:
        store, _ = dashboard.forget(store, ids)
        dashboard.save_store(store)
        dashboard.write_pages(store, lang)
    elif not dry and _yes(o, "everything") and not dashboard.STORE_FILE.exists():
        # A dashboard written by AirFare before route tabs: replace it with the empty one.
        dashboard.save_store({})
        dashboard.write_pages({}, lang)
    return len(ids)


def _alerts(o: dict, dry: bool) -> int:
    everything, route = _yes(o, "everything"), _id(o.get("route_id"))
    if not everything and not route:
        raise Problem("Pick a route")
    history = load_history()
    routes = history.get("routes") or {}
    ids = [rid for rid, h in routes.items() if (everything or rid == route) and (h.get("alert_refs") or h.get("alert_ref"))]
    if not dry and ids:
        for rid in ids:
            # Each kind starts again from the next check's prices, like a new route.
            routes[rid].pop("alert_refs", None)
            routes[rid].pop("alert_ref", None)
            routes[rid].pop("all_time_low", None)
        save_history(history)
    return len(ids)


def _reports(o: dict, dry: bool) -> int:
    days, everything = _days(o.get("older_than_days")), _yes(o, "everything")
    if not everything and not days:
        raise Problem("Enter a number of days, like 30")
    files = _report_files()
    stamp = lambda f: f.name.rsplit("-", 1)[0]                    # 2026-10-26_175912
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d_%H%M%S") if days else None
    keep = _linked_reports(files)
    gone = [f for f in files if f.name not in keep and (everything or stamp(f) < cutoff)]
    if not dry:
        gone = [f for f in gone if _unlink(f)]
    return len(gone)


def _linked_reports(files: list) -> set[str]:
    """Reports a page still shows: the newest price document and analysis (Settings shows the latest analysis),
    and every price document a dashboard links to."""
    keep = {next((f.name for f in files if f.name.endswith(kind)), "") for kind in ("-prices.md", "-analysis.md")}
    for versions in ((dashboard.load_store().get("check") or {}).get("html") or {}).values():
        keep.update(re.findall(r'href="(\d{4}-\d{2}-\d{2}_\d{4,6}-prices\.md)"', (versions or {}).get("footer") or ""))
    return keep


def _unlink(f) -> bool:
    """Delete one file; one that's open elsewhere is skipped (and logged) rather than stopping the clean-up."""
    try:
        f.unlink(missing_ok=True)
        return True
    except OSError as e:
        log.warning("couldn't delete %s: %s", f.name, e)
        return False


def _logs(o: dict, dry: bool) -> int:
    files = sorted(LOGS_DIR.glob("airfare.log*")) if LOGS_DIR.exists() else []
    size = sum(f.stat().st_size for f in files)
    if not dry:
        for f in files:
            if f.name == "airfare.log":
                try:
                    f.write_text("", encoding="utf-8")      # the running log handler keeps writing to it
                except OSError as e:
                    log.warning("couldn't clear the log: %s", e)
            else:
                _unlink(f)
    return size


def _conversations_reset(o: dict, dry: bool) -> int:
    state = load_state()
    asked = o.get("providers") if isinstance(o.get("providers"), list) else list(PROVIDERS)
    wanted = [p for p in asked if isinstance(p, str) and p in PROVIDERS]
    active = [p for p, on in _conversations(state).items() if on and p in wanted]
    if not dry:
        for p in active:
            slot = state if p == "claude" else state.setdefault(p, {})
            for k in ("session_id", "session_started", "session_checks", "context_tokens", "session_cost_usd",
                      "session_model", "previous_sessions"):
                slot.pop(k, None)
        save_state(state)
        # DeepSeek and OpenAI API conversations are stored here; Claude and ChatGPT keep theirs in their own apps.
        from . import openai_api
        stored = {"deepseek": deepseek.SESSIONS_DIR, "openai": openai_api.SESSIONS_DIR}
        for p in wanted:
            folder = stored.get(p)
            for f in (folder.glob("*.json") if folder and folder.exists() else []):
                _unlink(f)
    return len(active)


def run(action: str, o: dict, cfg: dict, dry: bool = False) -> int:
    """Do (or with dry=True only count) one clean-up action. Returns how many things it removes."""
    lang = cfg.get("language")
    if action == "records":
        return _records(o, dry)
    if action == "lookups":
        return _lookups(o, dry)
    if action == "dashboard":
        return _dashboard(o, dry, lang)
    if action == "alerts":
        return _alerts(o, dry)
    if action == "reports":
        return _reports(o, dry)
    if action == "logs":
        return _logs(o, dry)
    if action == "conversations":
        return _conversations_reset(o, dry)
    if action == "everything":
        # Everything AirFare learned from checks; settings, keys and the analysts' accounts stay.
        n = _records({"everything": True}, dry) + _lookups({"everything": True}, dry)
        n += _dashboard({"everything": True}, dry, lang) + _alerts({"everything": True}, dry)
        n += _reports({"everything": True}, dry)
        if not dry:
            history = load_history()
            history["runs"] = []
            save_history(history)
        return n
    raise Problem("Unknown clean-up action")


def automatic(cfg: dict) -> None:
    """The automatic clean-up chosen in Settings, run after each check. Problems are logged, never raised."""
    auto = cfg.get("cleanup") or {}
    for action, key in (("records", "records_days"), ("reports", "reports_days"), ("dashboard", "dashboard_days")):
        if auto.get(key):
            try:
                n = run(action, {"older_than_days": auto[key]}, cfg)
                if n:
                    log.info("automatic clean-up: %s removed %d", action, n)
            except Exception:
                log.exception("automatic clean-up of %s failed", action)


def clean_auto(raw: dict) -> dict:
    """The automatic clean-up settings from the page."""
    return {key: _days(raw.get(key)) for key in ("records_days", "reports_days", "dashboard_days")}


def message(lang: str | None, removed: int, action: str) -> str:
    if action == "logs":
        return i18n.tr("The log is cleared.", lang)
    if action == "conversations":
        return i18n.trn(removed, "{n} conversation will start fresh at the next check.|"
                                 "{n} conversations will start fresh at the next check.", lang)
    return i18n.trn(removed, "Deleted {n} item.|Deleted {n} items.", lang)
