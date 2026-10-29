"""Local setup form: edit routes and dates, test the generated links, open the tracker browser, run a check."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import re
import threading
import time
import urllib.error
import urllib.request
import uuid
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import (__version__, analyst, brand, chatgpt, cleanup, dashboard, deepseek, extension, historypage, i18n,
               limits, links, markup, migrate, money, openai_api, platform, pricelog, report, research, runner, serpapi,
               service, tray, update)
from .i18n import Problem
from .config import (ALERT_KINDS, KEYS, LIMITS, PROJECT_DIR, REPORTS_DIR, SOURCES, WEBUI_PORT, load_config,
                     load_state, save_config)
from .urls import CABINS, aviasales_url, clean_ages, plan_pages, route_label, route_pages

log = logging.getLogger(__name__)

PACKAGE = Path(__file__).parent
STATIC = PACKAGE / "static"
IDLE_LIMIT = 120          # seconds without a heartbeat from an open form before the server exits
OUTDATED = "AirFare was updated. Close this tab and open AirFare Settings again."
SYSTEM = "windows" if platform.WINDOWS else "macos" if platform.MACOS else "linux"
KEY_RE = re.compile(r"^[A-Za-z0-9_\-]{8,200}$")


def code_version() -> str:
    """Changes whenever AirFare's code or form changes, so a running server can tell it is outdated."""
    files = [*PACKAGE.glob("*.py"), *STATIC.glob("*.html")]
    return str(max(int(f.stat().st_mtime) for f in files))
CODE_RE = re.compile(r"^[a-z0-9]{2,8}$")
def empty_dashboard(lang: str) -> str:
    return dashboard.page({}, lang)


OLD_TABS_RE = re.compile(r'<nav class="tabs".*?</nav>', re.S)
OLD_BRAND_RE = re.compile(r'<div class="brand">.*?<h1>AirFare</h1>\s*</div>|<h1>AirFare</h1>', re.S)


def served_dashboard(page: str, lang: str = "en") -> str:
    """A dashboard written by an older AirFare gets today's tab bar (which also keeps this server running).

    Older dashboards had no tabs, or only Dashboard and Price history: their title and tabs make way for the
    current bar at the top of the page, and anything else in their header (like "Checked ...") stays below it.
    """
    if brand.NAV_SCRIPT in page:
        return page
    if '<nav class="langs"' in page:
        # Today's bar with an older copy of its script (another version or port): only the script is swapped,
        # since the page's security policy runs today's script alone.
        page, n = re.subn(r"<script>\s*\(\(\) => \{\s*const served = location\.protocol.*?</script>",
                          lambda m: brand.NAV_SCRIPT, page, count=1, flags=re.S)
        return page if n else page.replace("</body>", brand.NAV_SCRIPT + "</body>", 1)
    page = OLD_TABS_RE.sub("", page, count=1)
    page = OLD_BRAND_RE.sub("", page, count=1)
    page = re.sub(r'<div class="top">\s*</div>', "", page, count=1)
    page, added = re.subn(r"<main\b[^>]*>", lambda m: m.group(0) + brand.top_bar("dashboard", lang), page, count=1)
    if not added:
        page = re.sub(r"<body\b[^>]*>", lambda m: m.group(0) + brand.top_bar("dashboard", lang), page, count=1)
    page = page.replace("</head>", f"<style>{brand.TOKENS_CSS}{brand.NAV_CSS}</style></head>", 1)
    return page.replace("</body>", brand.NAV_SCRIPT + "</body>", 1)


REPORT_FILE_RE = re.compile(r"^/\d{4}-\d{2}-\d{2}_\d{4,6}-(prices|analysis)\.md$")
LATEST_RE = re.compile(r"^/latest(?:-(en|es|ru))?(?:\.html)?$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class Tasks:
    """At most one browser task (test, check, tracker browser) at a time."""

    def __init__(self):
        self.lock = threading.Lock()
        self.current: str | None = None
        self.last: dict = {}

    def start(self, name: str, fn) -> bool:
        with self.lock:
            if self.current:
                return False
            self.current = name

        def work():
            started = time.time()
            try:
                self.last = {"task": name, "ok": True, "result": fn(), "at": started}
            except Exception as e:
                log.exception("%s failed", name)
                self.last = {"task": name, "ok": False, "error": str(e), "at": started}
            finally:
                self.current = None

        threading.Thread(target=work, daemon=True).start()
        return True

    def run_now(self, name: str, fn):
        with self.lock:
            if self.current:
                raise runner.Busy(f"busy with: {self.current}")
            self.current = name
        try:
            return fn()
        finally:
            self.current = None

    def wait_idle(self, limit: float = 3600) -> None:
        """Let a running check, test or lookup finish before this process exits."""
        deadline = time.monotonic() + limit
        while self.current and time.monotonic() < deadline:
            time.sleep(1)


TASKS = Tasks()


CLAUDE_MODES = ("account", "key")


def _number(raw, what: str, lo: float, hi: float, default=None):
    """A number from the form within lo..hi; None (or default) when left empty."""
    if raw in (None, ""):
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise Problem("{what} should be a number", what=what)
    if not lo <= value <= hi:
        raise Problem("{what} should be between {lo} and {hi}", what=what, lo=f"{lo:g}", hi=f"{hi:g}")
    return value


def clean_alerts(raw: dict, cfg: dict, rates: dict | None) -> dict:
    """The three alert kinds from the form. Price ceilings follow a currency change at today's rate."""
    old_currency, new_currency = cfg.get("currency") or money.DEFAULT, raw.get("currency") or cfg.get("currency")
    out = {}
    for kind in ALERT_KINDS:
        k = ((raw.get("alerts") or {}).get(kind)) or {}
        prev = (cfg.get("alerts") or {}).get(kind) or {}
        label = {"cheapest": "Cheapest", "fastest": "Fastest", "best": "Best value"}[kind]
        drop = _number(k.get("drop", prev.get("drop")), f"{label}: the price drop (%)", 0, 50, 0.0)
        ceiling = _number(k.get("max"), f"{label}: the price limit", 1, 10_000_000)
        if ceiling is not None and old_currency != new_currency and k.get("max") == prev.get("max"):
            converted = money.convert(ceiling, old_currency, new_currency, rates or {})
            if converted is None:
                raise Problem("There's no exchange rate for {currency} yet, so your price limits can't be "
                              "converted. Connect to the internet and save again.", currency=new_currency)
            ceiling = round(converted)
        out[kind] = {"on": bool(k.get("on", prev.get("on", True))), "drop": drop, "max": ceiling}
    return out


def new_key(raw: dict, cfg: dict, name: str) -> str:
    """The form never receives saved API keys, so a blank field keeps the saved key; "Remove" clears it."""
    if name in (raw.get("clear_keys") or []):
        return ""
    typed = str(raw.get(name) or "").strip()
    if typed and not KEY_RE.match(typed):
        raise Problem("That doesn't look like an API key: paste only the key itself")
    return typed or cfg.get(name) or ""


def public_config(cfg: dict) -> dict:
    """The settings as the browser gets them: API keys left out, with only their last four characters shown."""
    return {**cfg, **{k: "" for k in KEYS},
            "saved_keys": {k: f"…{cfg[k][-4:]}" if cfg.get(k) else "" for k in KEYS}}


def _trip(r: dict) -> tuple | None:
    """What makes a route the same search: airports, direction, trip type, travellers and cabin."""
    if not (r.get("origin") or r.get("destination")):
        return None
    return (str(r.get("origin") or "").lower(), str(r.get("destination") or "").lower(),
            "return" if r.get("trip") == "return" else "oneway", int(r.get("adults") or 1),
            tuple(clean_ages(r.get("children")) or []), r.get("cabin") or "economy")


def clean_config(raw: dict, problems: dict | None = None, renew_ids: bool = False) -> dict:
    """Validate what the form sent; raise ValueError with a readable message.

    With a `problems` dict (live preview), unfinished routes are left out and their message is
    recorded per route id instead of raising.
    """
    cfg = load_config()
    domain = str(raw.get("domain") or cfg["domain"]).strip().lower()
    domain = re.sub(r"^https?://", "", domain).strip("/")
    if not re.match(r"^[a-z0-9.-]*skyscanner\.[a-z.]+$", domain):
        raise Problem("The Skyscanner domain should look like www.skyscanner.net")
    sources = [s for s in SOURCES if s in (raw.get("sources") or [])]
    if not sources:
        raise Problem("Pick at least one price source")
    if "extension" in sources and domain not in extension.supported_hosts():
        raise Problem("The Chrome extension doesn't cover {domain}; pick a site from the list", domain=domain)
    currency = str(raw.get("currency") or cfg.get("currency") or money.DEFAULT).strip().upper()
    if not re.match(r"^[A-Z]{3}$", currency):
        raise Problem("Pick a currency from the list")
    rates = money.rates() if currency != (cfg.get("currency") or money.DEFAULT) else None
    alerts = clean_alerts({**raw, "currency": currency}, cfg, rates)
    max_hours = _number(raw.get("alert_max_hours"), "The longest trip for alerts (hours)", 1, 99)
    language = raw.get("language") or cfg.get("language") or "en"
    if language not in i18n.LANGS:
        raise Problem("Pick English, Spanish or Russian")
    model = str(raw.get("model") if raw.get("model") is not None else cfg.get("model") or "").strip()
    if model and not re.match(r"^claude-[a-z0-9-]+$", model):
        raise Problem("Pick a Claude model from the list")
    try:
        session_k = int(raw.get("session_max_k") or cfg.get("session_max_k") or 40)
    except (TypeError, ValueError):
        raise Problem("The session size should be a number of thousand tokens, like 40")
    if not 10 <= session_k <= 500:
        raise Problem("The session size should be between 10 and 500 thousand tokens")
    provider = raw.get("llm_provider") or cfg.get("llm_provider") or "claude"
    if provider not in analyst.PROVIDER_NAMES:
        raise Problem("Pick Claude, ChatGPT, DeepSeek or no analyst")
    claude_mode = raw.get("claude_mode") or cfg.get("claude_mode") or "account"
    if claude_mode not in CLAUDE_MODES:
        raise Problem("Pick your Claude account or an Anthropic API key")
    an_key = new_key(raw, cfg, "anthropic_api_key")
    if provider == "claude" and claude_mode == "key" and not an_key:
        raise Problem("Add your Anthropic API key, or use Claude with your Claude account")
    oa_key = new_key(raw, cfg, "openai_api_key")
    oa_model = raw.get("openai_model") or cfg.get("openai_model") or openai_api.MODELS[0]
    if oa_model not in openai_api.MODELS:
        raise Problem("Pick a ChatGPT model from the list")
    if provider == "openai" and not oa_key:
        raise Problem("Add your OpenAI API key, or use ChatGPT with your ChatGPT account")
    gpt_model = str(raw.get("chatgpt_model") if raw.get("chatgpt_model") is not None else cfg.get("chatgpt_model") or "").strip()
    if gpt_model and not re.match(r"^[a-z0-9][a-z0-9.\-]{1,40}$", gpt_model):
        raise Problem("Pick a ChatGPT model from the list")
    ds_key = new_key(raw, cfg, "deepseek_api_key")
    ds_model = raw.get("deepseek_model") or cfg.get("deepseek_model") or deepseek.MODELS[0]
    if ds_model not in deepseek.MODELS:
        raise Problem("Pick a DeepSeek model from the list")
    if provider == "deepseek" and not ds_key:
        raise Problem("Add your DeepSeek API key, or switch the analyst back to Claude")
    sched = raw.get("schedule") or cfg.get("schedule") or "startup"
    if sched not in service.SCHEDULES:
        raise Problem("Pick when AirFare should check")
    try:
        interval = float(raw.get("interval_hours") or cfg.get("interval_hours") or 6)
    except (TypeError, ValueError):
        raise Problem("The check interval should be a number of hours, like 6")
    if not 1 <= interval <= 48:
        raise Problem("Check every 1 to 48 hours")
    browser_kind = raw.get("browser") or cfg.get("browser") or "chrome"
    if browser_kind not in extension.BROWSERS:
        raise Problem("Pick Chrome, Edge, Brave, Opera or Firefox for the extension")
    level = raw.get("limits") or cfg.get("limits") or "personal"
    if level not in LIMITS:
        raise Problem("Pick Personal or Extended limits")
    if level == "extended" and cfg.get("limits") != "extended" and not raw.get("limits_confirmed"):
        # The form asks first, with the warning about the sites' terms; nothing else switches to Extended.
        raise Problem("Confirm the warning about Extended limits first")
    cfg.update(
        browser=browser_kind,
        tray=bool(raw.get("tray", cfg.get("tray"))),
        update_check=bool(raw.get("update_check", cfg.get("update_check", True))),
        domain=domain,
        wait_seconds=max(10, min(90, int(raw.get("wait_seconds") or 20))),
        max_pages=max(1, min(60, int(raw.get("max_pages") or 20))),
        limits=level,
        schedule=sched,
        interval_hours=interval,
        llm_provider=provider,
        model=model,
        claude_mode=claude_mode,
        anthropic_api_key=an_key,
        deepseek_api_key=ds_key,
        deepseek_model=ds_model,
        openai_api_key=oa_key,
        openai_model=oa_model,
        chatgpt_model=gpt_model,
        session_max_k=session_k,
        sources=sources,
        serpapi_key=new_key(raw, cfg, "serpapi_key"),
        currency=currency,
        language=language,
        alerts=alerts,
        alert_max_hours=max_hours,
        alert_no_self_transfer=bool(raw.get("alert_no_self_transfer")),
    )
    before = {r.get("id"): r for r in cfg.get("routes") or []}
    routes = []
    for i, r in enumerate(raw.get("routes") or [], 1):
        manual = [{"key": m.get("key") or None, "url": m["url"].strip()}
                  for m in r.get("manual_pages") or [] if (m.get("url") or "").strip().startswith("http")]
        # The extension opens only search result pages on its own sites; another link would stop the whole job.
        bad_link = next((m["url"] for m in manual if not extension.allowed(m["url"])), None)
        origin = str(r.get("origin") or "").strip().lower()
        dest = str(r.get("destination") or "").strip().lower()
        children = clean_ages(r.get("children"))
        route = {
            "id": r.get("id") or uuid.uuid4().hex[:6],
            "name": str(r.get("name") or "").strip(),
            "enabled": bool(r.get("enabled", True)),
            "origin": origin, "destination": dest,
            "trip": "return" if r.get("trip") == "return" else "oneway",
            "depart_from": r.get("depart_from") or "", "depart_to": r.get("depart_to") or "",
            "return_from": r.get("return_from") or "", "return_to": r.get("return_to") or "",
            "adults": max(1, min(9, int(r.get("adults") or 1))),
            "children": children or [],
            "cabin": r.get("cabin") if r.get("cabin") in CABINS else "economy",
            "direct_only": bool(r.get("direct_only")),
            "manual_pages": manual,
        }
        old = before.get(route["id"])
        if renew_ids and old and _trip(old) and _trip(route) and _trip(old) != _trip(route):
            route["id"] = uuid.uuid4().hex[:6]
        problem = None
        if origin or dest:
            if not (CODE_RE.match(origin) and CODE_RE.match(dest)):
                problem = "use airport or city codes like LHR, LOND or BCN for From and To"
            elif not DATE_RE.match(route["depart_from"]):
                problem = "pick a departure date"
            elif route["trip"] == "return" and not DATE_RE.match(route["return_from"]):
                problem = "pick a return date, or switch to one-way"
        elif not manual:
            if not route["name"]:
                if problems is not None:      # an untouched empty card: a hint, never an error
                    problems[route["id"]] = "Enter From/To codes or paste a Skyscanner link"
                continue
            problem = "enter From/To codes or paste a Skyscanner link"
        if not problem and bad_link:
            problem = "paste the address of a Skyscanner search results page (https://www.skyscanner…/transport/flights/…)"
        if not problem and children is None:
            problem = "children's ages should be whole numbers from 0 to 15 (at most 8), like 4, 9"
        if problem:
            if problems is None:
                raise Problem("Route {i}: {problem}", i=i, problem=problem)
            problems[route["id"]] = problem[0].upper() + problem[1:]
            continue
        routes.append(route)
    cfg["routes"] = routes
    return cfg


def preview(cfg: dict, problems: dict | None = None) -> dict:
    planned, left_out = plan_pages(cfg)
    planned_keys = {(p["route_id"], p["key"]) for p in planned}
    routes = {}
    for r in cfg["routes"]:
        pages = route_pages(r, cfg["domain"])
        routes[r["id"]] = {
            "label": route_label(r),
            "pages": [{**p, "planned": (r["id"], p["key"]) in planned_keys and r.get("enabled", True)} for p in pages],
        }
    # Skyscanner and Aviasales pages past the limits' per-check maximum (the check leaves them out).
    sources = cfg.get("sources") or []
    browser = sum(("extension" in sources) + ("aviasales" in sources and aviasales_url(p) is not None) for p in planned)
    over = max(0, browser - limits.LEVELS[limits.level(cfg)]["pages"])
    return {"routes": routes, "planned": len(planned), "left_out": left_out, "browser_left_out": over,
            "problems": problems or {}}


def test_pages(cfg: dict, route_id: str | None) -> dict:
    pages, _ = plan_pages(cfg)
    if route_id:
        pages = [p for p in pages if p["route_id"] == route_id]
    with runner.ProcessLock():
        results, held = asyncio.run(runner.collect_prices(cfg, pages, cfg["sources"], test=True))
    data = report.collect(results, cfg.get("currency") or money.DEFAULT, money.rates())
    out = []
    for pd in data:
        res, parsed = pd.result, pd.parsed
        cheapest = parsed.flights[0].price_text if parsed and parsed.flights else None
        status = res.status
        note = res.note
        if status == "ok" and not cheapest:
            note = note or "page loaded but no flight results were found"
        out.append({"route_id": res.page["route_id"], "key": res.page["key"], "source": res.source,
                    "status": status, "note": note, "cheapest": cheapest,
                    "results": len(parsed.flights) if parsed else 0, "seconds": res.seconds})
    return {"pages": out, "limits": limits.describe(held, cfg.get("language"))}


def save_key(name: str, value: str) -> dict:
    """Save (or, with an empty value, remove) one API key on its own, without the rest of the form, and say
    whether the service accepts it."""
    if name not in KEYS:
        raise Problem("Unknown key")
    value = (value or "").strip()
    if value and not KEY_RE.match(value):
        raise Problem("That doesn't look like an API key: paste only the key itself")
    cfg = load_config()
    cfg[name] = value
    save_config(cfg)
    log.info("%s %s", name, "saved" if value else "removed")
    check = {}
    if value and name == "serpapi_key":
        check = serpapi_account(value)
    elif value and name == "deepseek_api_key":
        try:
            check = deepseek.balance(value)
        except deepseek.DeepSeekError as e:
            check = {"error": str(e)}
    elif value and name == "openai_api_key":
        try:
            check = openai_api.check_key(value)
        except openai_api.OpenAIError as e:
            check = {"error": str(e)}
    elif value and name == "anthropic_api_key":
        try:
            check = analyst.check_key(value)
        except analyst.ClaudeError as e:
            check = {"error": str(e)}
    return {"saved_keys": public_config(cfg)["saved_keys"], "check": check}


def serpapi_account(key: str) -> dict:
    if not key:
        return {"error": "No SerpApi key yet"}
    try:
        return serpapi.account(key)
    except serpapi.SerpApiError as e:
        return {"error": str(e)}


def run_check() -> dict:
    code = runner.run(console=False)
    held = runner.last_limits
    return {"code": code, "message": {0: "Check finished.", 2: "Nothing to check: add a route with future dates.",
                                       3: "Another check is already running.",
                                       runner.HELD: "Nothing was checked: the limits hold Skyscanner and Aviasales for now."
                                       }.get(code, "The check failed; see the log."),
            "note": limits.describe(held, load_config().get("language"))}


def latest_analysis() -> dict:
    files = sorted(REPORTS_DIR.glob("*-analysis.md")) if REPORTS_DIR.exists() else []
    if not files:
        return {}
    f = files[-1]
    return {"name": f.name, "html": markup.to_html(f.read_text(encoding="utf-8"))}


SCRIPT_RE = re.compile(r"<script(?![^>]*application/json)[^>]*>(.*?)</script>", re.S)


def settings_page(lang: str | None, name: str = "index.html") -> str:
    """Settings (or Clean up) in the chosen language, with every language's texts so it can switch without
    reloading."""
    lang = i18n.norm(lang)
    texts = json.dumps(i18n.bundle(), ensure_ascii=False).replace("<", "\\u003c")
    page = (STATIC / name).read_text(encoding="utf-8").replace("__LANG__", lang)
    return brand.fill(page.replace("<!--I18N-->", f'<script type="application/json" id="i18n">{texts}</script>'), lang)


def cleanup_page(lang: str | None) -> str:
    return settings_page(lang, "cleanup.html")


def content_policy() -> str:
    """Pages run only AirFare's own scripts, matched by hash, so a script that got into a page (say, in the
    analyst's text) never runs. They talk to this server only and can't be framed by other sites."""
    pages = [settings_page("en"), cleanup_page("en"), brand.fill(historypage.PAGE), brand.NAV_SCRIPT,
             dashboard.DASH_SCRIPT]
    hashes = {base64.b64encode(hashlib.sha256(s.encode("utf-8")).digest()).decode()
              for page in pages for s in SCRIPT_RE.findall(page)}
    scripts = " ".join(f"'sha256-{h}'" for h in sorted(hashes))
    return (f"default-src 'self'; script-src {scripts}; style-src 'unsafe-inline'; img-src 'self' data:; "
            "connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")


class Handler(BaseHTTPRequestHandler):
    server_version = "AirFare"

    def log_message(self, fmt, *args):
        log.debug("webui: " + fmt, *args)

    def _send(self, status: int, body: bytes, ctype: str):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        if ctype.startswith("text/html"):
            self.send_header("Content-Security-Policy", content_policy())
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data, status: int = 200):
        self._send(status, json.dumps(data, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def _local(self) -> bool:
        """Answer only requests addressed to this PC by name. A web page whose own domain points at 127.0.0.1
        (DNS rebinding) would otherwise count as this site and could read the settings, keys included."""
        port = self.server.server_port
        if (self.headers.get("Host") or "").lower() in (f"127.0.0.1:{port}", f"localhost:{port}"):
            return True
        self._json({"error": "forbidden"}, HTTPStatus.FORBIDDEN)
        return False

    def _current(self) -> bool:
        """False (and the server stops) when AirFare's code changed after this server started."""
        if code_version() == self.server.version:
            return True
        log.info("AirFare's code changed since this settings server started; stopping it")
        self._json({"error": OUTDATED, "outdated": True}, HTTPStatus.CONFLICT)
        self.server.stop()
        return False

    def do_GET(self):
        try:
            self._get()
        except ConnectionError:
            pass                        # the page went away mid-request (closed tab, navigation)
        except Exception:
            # The details (which may name files on this PC) go to the log, not the page.
            log.exception("webui error")
            self._json({"error": i18n.tr("Something went wrong. Details are in AirFare's log.",
                                         load_config().get("language"))}, 500)

    def _get(self):
        if not self._local():
            return
        self.server.touch()
        if self.path in ("/", "/index.html"):
            self._send(200, settings_page(load_config().get("language")).encode("utf-8"), "text/html; charset=utf-8")
        elif self.path == "/api/version":
            self._json({"version": self.server.version})
        elif self.path.startswith("/api/") and self.headers.get("X-AirFare") != "1":
            # Only AirFare's own pages read the settings: not other sites, link checkers or fetch tools.
            self._json({"error": "forbidden"}, HTTPStatus.FORBIDDEN)
        elif self.path.startswith("/api/") and not self._current():
            return
        elif self.path == "/api/state":
            cfg = load_config()
            state = load_state()
            self._json({"config": public_config(cfg), "preview": preview(cfg), "state": state,
                        "task": TASKS.current, "last_task": TASKS.last, "latest": latest_analysis(),
                        "cabins": CABINS, "extension_hosts": extension.supported_hosts(),
                        "extension_dir": str(extension.EXTENSION_DIR), "extension_latest": extension.latest_version(),
                        "browsers": {k: {"name": b["name"], "page": b["page"], "installed": on,
                                         "folder": str(extension.extension_dir(k)), "latest": extension.latest_version(k)}
                                     for k, b in extension.BROWSERS.items() for on in [extension.chrome_path(k) is not None]},
                        "service": service.status(), "currencies": money.CURRENCIES, "tray_available": tray.available(),
                        "limits": limits.LEVELS,
                        "update": update.cached(state), "version": __version__, "data_version": migrate.status(),
                        # where the update steps say to unzip a new release, and which steps they are
                        "folder": str(PROJECT_DIR), "system": SYSTEM})
        elif self.path == "/api/status":
            self._json({"task": TASKS.current, "last_task": TASKS.last, "latest": latest_analysis()})
        elif self.path in ("/cleanup", "/cleanup.html"):
            self._send(200, cleanup_page(load_config().get("language")).encode("utf-8"), "text/html; charset=utf-8")
        elif self.path == "/api/cleanup":
            self._json(cleanup.summary(load_config()))
        elif self.path in ("/history", "/history.html"):
            self._send(200, historypage.build(load_config(), served=True).encode("utf-8"), "text/html; charset=utf-8")
        elif LATEST_RE.match(self.path):
            # The dashboard in the language picked in Settings (or the one asked for), from its kept routes; a
            # dashboard written by an older AirFare is served as it was written.
            lang = LATEST_RE.match(self.path).group(1) or i18n.norm(load_config().get("language"))
            f = next((x for x in (REPORTS_DIR / f"latest-{lang}.html", REPORTS_DIR / "latest.html") if x.exists()), None)
            if dashboard.STORE_FILE.exists():
                self._send(200, dashboard.page(dashboard.load_store(), lang).encode("utf-8"), "text/html; charset=utf-8")
            elif f:
                page = served_dashboard(f.read_text(encoding="utf-8"), lang)
                self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
            else:
                self._send(200, empty_dashboard(lang).encode("utf-8"), "text/html; charset=utf-8")
        elif REPORT_FILE_RE.match(self.path) and (REPORTS_DIR / self.path[1:]).exists():
            # The dashboard links to its price document by file name.
            self._send(200, (REPORTS_DIR / self.path[1:]).read_bytes(), "text/plain; charset=utf-8")
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        if not self._local():
            return
        self.server.touch()
        # Only the form itself may drive the API (blocks cross-site requests from other pages).
        if self.headers.get("X-AirFare") != "1":
            return self._json({"error": "forbidden"}, HTTPStatus.FORBIDDEN)
        try:
            body = self._body()
            if self.path == "/api/close":
                self._json({"ok": True})
                return self.server.stop()
            if not self._current():
                return
            if self.path == "/api/heartbeat":
                return self._json({"task": TASKS.current})
            if self.path == "/api/preview":
                problems: dict = {}
                return self._json(preview(clean_config(body.get("config") or {}, problems), problems))
            if self.path == "/api/save":
                cfg = clean_config(body.get("config") or {}, renew_ids=True)
                save_config(cfg)
                if service.needed(cfg) and cfg["routes"] and service.start_in_background():
                    log.info("started the background checker (interval checks or the tray icon)")
                return self._json({"config": public_config(cfg), "preview": preview(cfg), "service": service.status()})
            if self.path == "/api/update":
                return self._json(update.check(force=bool(body.get("force"))))
            if self.path == "/api/keys":
                return self._json(save_key(str(body.get("name") or ""), str(body.get("value") or "")))
            if self.path == "/api/language":
                lang = body.get("language")
                if lang not in i18n.LANGS:
                    raise Problem("Pick English, Spanish or Russian")
                cfg = load_config()
                cfg["language"] = lang
                save_config(cfg)
                runner.write_history_page(cfg)
                return self._json({"language": lang})
            if self.path == "/api/test":
                cfg = clean_config(body.get("config") or {})
                return self._json(TASKS.run_now("test", lambda: test_pages(cfg, body.get("route_id"))))
            if self.path == "/api/claude":
                # The page may have switched between the account and a key without saving yet.
                cfg = load_config()
                if body.get("mode") in CLAUDE_MODES:
                    cfg = {**cfg, "claude_mode": body["mode"]}
                return self._json(analyst.login_status(cfg))
            if self.path == "/api/anthropic":
                key = str(body.get("key") or load_config().get("anthropic_api_key") or "")
                if not key:
                    return self._json({"error": "No Anthropic key yet"})
                try:
                    return self._json(analyst.check_key(key))
                except analyst.ClaudeError as e:
                    return self._json({"error": str(e)})
            if self.path == "/api/claude-login":
                from .__main__ import open_login_console
                open_login_console()
                return self._json({"ok": True})
            if self.path == "/api/chatgpt":
                return self._json(chatgpt.login_status())
            if self.path == "/api/chatgpt-login":
                chatgpt.open_login_console()
                return self._json({"ok": True})
            if self.path == "/api/openai":
                key = str(body.get("key") or load_config().get("openai_api_key") or "")
                if not key:
                    return self._json({"error": "No OpenAI key yet"})
                try:
                    return self._json(openai_api.check_key(key))
                except openai_api.OpenAIError as e:
                    return self._json({"error": str(e)})
            if self.path == "/api/cleanup":
                cfg = load_config()
                action, dry = str(body.get("action") or ""), bool(body.get("dry_run"))
                if dry:
                    return self._json({"count": cleanup.run(action, body, cfg, dry=True)})
                with runner.ProcessLock():              # never while a check is writing the same files
                    if body.get("expect") is not None and cleanup.run(action, body, cfg, dry=True) != body["expect"]:
                        raise Problem("What this would delete has changed since the page showed it. Check the "
                                      "numbers and try again.")
                    removed = TASKS.run_now("cleanup", lambda: cleanup.run(action, body, cfg))
                log.info("clean up: %s removed %d", action, removed)
                runner.write_history_page(cfg)
                return self._json({"removed": removed, "message": cleanup.message(cfg.get("language"), removed, action),
                                   "summary": cleanup.summary(cfg)})
            if self.path == "/api/cleanup/auto":
                cfg = load_config()
                cfg["cleanup"] = cleanup.clean_auto(body)
                save_config(cfg)
                return self._json({"summary": cleanup.summary(cfg)})
            if self.path == "/api/extension-folder":
                platform.open_path(extension.extension_dir(body.get("browser")))
                return self._json({"ok": True})
            if self.path == "/api/history/delete":
                removed = 0
                if body.get("everything") or body.get("ids") or body.get("route_id"):
                    removed += pricelog.delete(ids=body.get("ids"), route_id=body.get("route_id"),
                                               everything=bool(body.get("everything")))
                if body.get("research_ids"):
                    removed += pricelog.delete_research(ids=body["research_ids"])
                log.info("price history: deleted %d record(s)", removed)
                runner.write_history_page(load_config())
                cfg = load_config()
                records = historypage.in_currency(pricelog.load(), cfg.get("currency") or money.DEFAULT,
                                                  money.rates(refresh=False))   # as the page shows them
                return self._json({"removed": removed, "records": records, "research": pricelog.load_research()})
            if self.path == "/api/history/research":
                cfg = load_config()
                cond = research.conditions_for(cfg, str(body.get("route_id") or ""), body.get("depart_from") or None,
                                               body.get("depart_to") or None, body.get("return_from") or None,
                                               body.get("return_to") or None)
                pick = (body.get("provider") or None, body.get("model"), body.get("web", True) is not False)
                research.resolve_analyst(cfg, *pick)         # reject an unusable choice before starting
                result = TASKS.run_now("lookup", lambda: asyncio.run(research.lookup(cond, cfg, *pick)))
                runner.write_history_page(cfg)
                return self._json({"result": result, "research": pricelog.load_research()})
            if self.path == "/api/deepseek":
                key = str(body.get("key") or load_config().get("deepseek_api_key") or "")
                if not key:
                    return self._json({"error": "No DeepSeek key yet"})
                try:
                    return self._json(deepseek.balance(key))
                except deepseek.DeepSeekError as e:
                    return self._json({"error": str(e)})
            if self.path == "/api/serpapi":
                return self._json(serpapi_account(str(body.get("key") or load_config().get("serpapi_key") or "")))
            if self.path == "/api/run":
                ok = TASKS.start("check", run_check)
                return self._json({"started": ok, "task": TASKS.current}, 200 if ok else 409)
            self._json({"error": "not found"}, 404)
        except ValueError as e:
            lang = load_config().get("language")
            self._json({"error": e.text(lang) if isinstance(e, Problem) else i18n.tr(str(e), lang)}, 400)
        except runner.Busy as e:
            log.info("busy: %s", e)
            self._json({"error": i18n.tr("AirFare is busy with another check or test. Try again in a minute.",
                                         load_config().get("language"))}, 409)
        except ConnectionError:
            pass                        # the page went away mid-request (closed tab, navigation)
        except (chatgpt.ChatGPTError, openai_api.OpenAIError, deepseek.DeepSeekError, analyst.ClaudeError,
                serpapi.SerpApiError) as e:
            self._json({"error": i18n.tr(str(e), load_config().get("language"))}, 400)
        except Exception:
            # The details (which may name files on this PC) go to the log, not the page.
            log.exception("webui error")
            self._json({"error": i18n.tr("Something went wrong. Details are in AirFare's log.",
                                         load_config().get("language"))}, 500)


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = not platform.WINDOWS    # see extension._JobServer

    def __init__(self, port: int):
        super().__init__(("127.0.0.1", port), Handler)
        self.last_seen = time.monotonic()
        self.version = code_version()

    def touch(self):
        self.last_seen = time.monotonic()

    def stop(self):
        threading.Thread(target=self.shutdown, daemon=True).start()

    def watch_idle(self):
        tick = time.monotonic()
        while True:
            time.sleep(10)
            now = time.monotonic()
            if now - tick > 60:
                self.touch()        # the PC slept: give open pages time to check in again
            tick = now
            if TASKS.current is None and now - self.last_seen > IDLE_LIMIT:
                log.info("setup form closed; stopping the local server")
                self.shutdown()
                return


def _bind() -> Server | None:
    try:
        return Server(WEBUI_PORT)
    except OSError:
        return None


def _replace_outdated(url: str) -> bool:
    """Ask a settings server already on our port to step aside if it runs older code."""
    try:
        with urllib.request.urlopen(url + "api/version", timeout=3) as r:
            if json.loads(r.read()).get("version") == code_version():
                return False
    except urllib.error.HTTPError:
        pass                     # too old to know /api/version
    except (OSError, ValueError):
        return False             # something else owns the port
    req = urllib.request.Request(url + "api/close", data=b"{}", method="POST",
                                 headers={"X-AirFare": "1", "Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=3).close()
    except OSError:
        return False
    log.info("asked an outdated settings server to stop")
    return True


def serve(open_page: bool = True, page: str = "settings") -> None:
    links.register()
    url = f"http://127.0.0.1:{WEBUI_PORT}/"
    show = url + {"dashboard": "latest.html", "history": "history.html"}.get(page, "")
    server = _bind()
    if server is None and _replace_outdated(url):
        deadline = time.monotonic() + 5
        while server is None and time.monotonic() < deadline:
            time.sleep(0.25)
            server = _bind()
    if server is None:
        # An up-to-date settings server is already running (another AirFare window): just show it.
        if open_page:
            webbrowser.open(show)
        return
    log.info("setup form at %s", url)
    threading.Thread(target=server.watch_idle, daemon=True).start()
    if open_page:
        webbrowser.open(show)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        TASKS.wait_idle()   # a newer AirFare took over the port; finish this one's running check first
