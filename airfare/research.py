"""'Search the lowest price history': ask the chosen analyst for the lowest price recorded in the past two
years for exactly this route and these dates, then check the answer before showing it.

The prompt forbids guessing, other airports and other dates, but AirFare doesn't rely on the prompt alone.
An answer only counts when its route and travel dates match the request, it was observed inside the
two-year window, it cites a source, and AirFare finds the quoted text with that price on the source page.
Anything else is recorded as "No information".
"""
from __future__ import annotations

import asyncio
import html
import http.client
import ipaddress
import json
import logging
import math
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, TextBlock, query

from . import analyst, chatgpt, deepseek, money, openai_api, pricelog, serpapi
from .i18n import LANGUAGE_NAMES, Problem
from .config import PROJECT_DIR

log = logging.getLogger(__name__)

WINDOW_DAYS = 730
NO_INFO = "No information"

SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["found", "no_information"]},
        "lowest_price": {"type": ["number", "null"]},
        "currency": {"type": ["string", "null"], "description": "ISO code of the currency the source shows"},
        "price_converted": {"type": ["number", "null"],
                            "description": "lowest_price converted to the user's currency with the given rates"},
        "origin": {"type": ["string", "null"], "description": "IATA code of the departure airport in the source"},
        "destination": {"type": ["string", "null"], "description": "IATA code of the arrival airport in the source"},
        "depart_date": {"type": ["string", "null"], "description": "YYYY-MM-DD departure date the price is for"},
        "return_date": {"type": ["string", "null"], "description": "YYYY-MM-DD return date, or null for one-way"},
        "observed_on": {"type": ["string", "null"], "description": "YYYY-MM-DD date the price was recorded or published"},
        "source_url": {"type": ["string", "null"]},
        "source_name": {"type": ["string", "null"]},
        "quote": {"type": ["string", "null"], "description": "Exact text copied from the source that states the price"},
        "notes": {"type": "string"},
    },
    "required": ["status", "lowest_price", "currency", "price_converted", "origin", "destination", "depart_date", "return_date",
                 "observed_on", "source_url", "source_name", "quote", "notes"],
    "additionalProperties": False,
}

SYSTEM = ("You are a strict fact-checker for historical airfares. You never estimate, extrapolate, round or invent "
          "numbers. When the evidence does not meet every rule, the correct answer is status \"no_information\".")


@dataclass
class Conditions:
    route_id: str
    route_name: str
    origins: list[str]              # IATA codes that count as the departure airport
    destinations: list[str]
    depart_from: str
    depart_to: str
    return_from: str | None = None  # None for one-way
    return_to: str | None = None
    adults: int = 1
    cabin: str = "economy"
    children: list[int] = field(default_factory=list)      # the children's ages
    today: str = field(default_factory=lambda: date.today().isoformat())
    currency: str = money.DEFAULT       # the user's currency: answers are converted to it
    language: str = "en"                # the language the notes are written in

    @property
    def window_start(self) -> str:
        return (date.fromisoformat(self.today) - timedelta(days=WINDOW_DAYS)).isoformat()


def build_prompt(c: Conditions, can_browse: bool, rates: dict | None = None) -> str:
    trip = "return" if c.return_from else "one-way"
    dates = f"departing between {c.depart_from} and {c.depart_to}"
    if c.return_from:
        dates += f" and returning between {c.return_from} and {c.return_to}"
    how = ("Use web search and open the pages you rely on. Only report a price that you read on a page you opened "
           "during this task." if can_browse else
           "You cannot browse the web. Only report a price if you know a specific source page (URL) that states it "
           "word for word; AirFare will open that page and reject the answer if the quoted text is not there.")
    rate = money.rate_line(c.currency, rates or {})
    money_rule = (f"The user compares prices in {c.currency}. Prefer sources that show {c.currency}. If the source shows "
                  f"another currency, still copy lowest_price and currency exactly as the source shows them (the quote "
                  f"is checked against the page), and give price_converted: that price in {c.currency}"
                  + (f", using these exchange rates: {rate}." if rate else ".")
                  + f" If the source already shows {c.currency}, price_converted equals lowest_price.")
    kids = f", children aged {', '.join(str(a) for a in c.children)}" if c.children else ""
    return f"""Find the LOWEST price that was actually recorded for this exact flight search:

- Route: {"/".join(c.origins)} → {"/".join(c.destinations)} ({trip}). Only these airports count.
- Travel dates: {dates}. Only prices for travel dates inside these ranges count.
- Passengers: {c.adults} adult(s){kids}, {c.cabin} class.
- Recorded or published between {c.window_start} and {c.today} (the past two years).

{how}

{money_rule}

Hard rules:
1. Never estimate, extrapolate, average, round or invent a price. A number you did not read in a source does not exist.
2. Do not use other airports, nearby cities, "similar destinations", or the reverse direction.
3. Do not use prices for travel dates outside the ranges above, "from" prices without exact dates, or monthly or
   seasonal averages.
4. Do not use prices recorded before {c.window_start}.
5. "quote" must be text copied exactly from the source that contains the price.
6. If no source meets every rule, set status to "no_information" and every other field except "notes" to null.
   In "notes", say briefly what you checked, in {LANGUAGE_NAMES.get(c.language, "English")}.

Answer with only a JSON object with these keys: status ("found" or "no_information"), lowest_price (number),
currency (ISO code as the source shows it), price_converted (number in {c.currency}), origin, destination (IATA codes
as in the source), depart_date, return_date (YYYY-MM-DD or null), observed_on (YYYY-MM-DD the price was recorded or
published), source_url, source_name, quote, notes."""


# ----- asking the analysts ------------------------------------------------------------------

async def _ask_claude(prompt: str, model: str | None, web: bool = True,
                      api_key: str | None = None) -> tuple[dict | None, float | None]:
    tools = ["WebSearch", "WebFetch"] if web else []
    options = ClaudeAgentOptions(
        cwd=str(PROJECT_DIR), tools=tools, allowed_tools=tools,
        max_turns=25, setting_sources=[], system_prompt=SYSTEM, model=model or None,
        output_format={"type": "json_schema", "schema": SCHEMA},
        env=analyst.claude_env(api_key),
    )
    parts, result = [], None
    analyst._hide_cli_console()
    async for msg in query(prompt=prompt, options=options):
        if isinstance(msg, AssistantMessage):
            parts.extend(b.text for b in msg.content if isinstance(b, TextBlock))
        elif isinstance(msg, ResultMessage):
            result = msg
    if result is None or result.is_error:
        raise analyst.ClaudeError(f"Claude couldn't finish the lookup: {result and (result.result or result.errors)}")
    answer = result.structured_output if isinstance(result.structured_output, dict) else _json_in(result.result or "\n".join(parts))
    return answer, result.total_cost_usd


def _ask_deepseek(prompt: str, model: str, api_key: str) -> tuple[dict | None, float | None]:
    text, usage = deepseek.complete([{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
                                    model, api_key, json_mode=True)
    return _json_in(text), deepseek.estimate_cost(usage, model)


def _ask_openai(prompt: str, model: str, api_key: str, web: bool) -> tuple[dict | None, float | None]:
    text, usage = openai_api.respond([{"role": "user", "content": prompt}], SYSTEM, model, api_key, web=web,
                                     schema=SCHEMA)
    return _json_in(text), openai_api.estimate_cost(usage, model)


def _ask_chatgpt(prompt: str, model: str | None, web: bool) -> tuple[dict | None, float | None]:
    # A one-off conversation (not kept in Codex's history), answering in AirFare's JSON shape.
    text, _ = chatgpt.run(f"{SYSTEM}\n\n{prompt}", None, model, web=web, schema=SCHEMA, keep=False)
    return _json_in(text), None


def _json_in(text: str) -> dict | None:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


# ----- checking the answer ------------------------------------------------------------------

def _in(day: str | None, lo: str, hi: str) -> bool:
    try:
        return lo <= date.fromisoformat(str(day)[:10]).isoformat() <= hi
    except (TypeError, ValueError):
        return False


def check_answer(a: dict | None, c: Conditions) -> str | None:
    """None when the answer meets every rule, otherwise why it doesn't."""
    if not isinstance(a, dict) or a.get("status") != "found":
        return "the analyst found no price that meets the rules"
    price = a.get("lowest_price")
    if not isinstance(price, (int, float)) or isinstance(price, bool) or not math.isfinite(price) or price <= 0:
        return "the answer had no usable price"
    if not all(isinstance(a.get(k), str) for k in ("origin", "destination", "depart_date", "observed_on",
                                                   "source_url", "quote")) or \
            not isinstance(a.get("return_date"), (str, type(None))) or \
            not isinstance(a.get("currency"), (str, type(None))) or not isinstance(a.get("source_name"), (str, type(None))):
        return "the answer had no usable price"
    if str(a.get("origin") or "").upper() not in c.origins or str(a.get("destination") or "").upper() not in c.destinations:
        return "the answer was for a different route"
    if not _in(a.get("depart_date"), c.depart_from, c.depart_to):
        return "the answer's departure date is outside your range"
    if c.return_from and not _in(a.get("return_date"), c.return_from, c.return_to):
        return "the answer's return date is outside your range"
    if not _in(a.get("observed_on"), c.window_start, c.today):
        return "the price wasn't recorded within the past two years"
    if not str(a.get("source_url") or "").startswith(("http://", "https://")) or not (a.get("quote") or "").strip():
        return "the answer didn't cite a source and quote it"
    return None


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(s)).strip().lower()


def _price_tokens(price: float) -> set[str]:
    whole = f"{price:.0f}" if float(price).is_integer() else None
    two = f"{price:.2f}"
    return {t for t in (whole, two, two.replace(".", ","), f"{price:,.2f}") if t}


def public_url(url: str) -> bool:
    """True for http(s) pages on the public internet. The source address comes from the analyst, so it must
    never lead to this PC (AirFare's own settings server) or to the local network."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return False
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80))
    except (OSError, ValueError):
        return False
    return bool(infos) and all(ipaddress.ip_address(info[4][0].split("%")[0]).is_global for info in infos)


def _public_ip(host: str, port: int) -> str:
    """The address to connect to, checked at the moment of connecting (a name that resolves to a public
    address for the check and to this PC a moment later can't slip through)."""
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    ips = [info[4][0] for info in infos]
    if not ips or not all(ipaddress.ip_address(ip.split("%")[0]).is_global for ip in ips):
        raise OSError("the source page isn't on the public internet")
    return ips[0]


class _PinnedHTTP(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.create_connection((_public_ip(self.host, self.port), self.port), self.timeout)


class _PinnedHTTPS(http.client.HTTPSConnection):
    def connect(self):
        sock = socket.create_connection((_public_ip(self.host, self.port), self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class _PinnedHTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, req):
        return self.do_open(_PinnedHTTP, req)


class _PinnedHTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_PinnedHTTPS, req, context=self._context)


class _PublicRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not public_url(newurl):
            raise urllib.error.URLError("the source page redirects away from the public internet")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open(req, timeout: float):
    # No proxy: the connection goes straight to the checked public address.
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _PinnedHTTPHandler(), _PinnedHTTPSHandler(),
                                       _PublicRedirects()).open(req, timeout=timeout)


def verify_source(url: str, quote: str, price: float) -> str | None:
    """None when the quote, containing the price, is on the source page; otherwise why not."""
    if not any(t in quote for t in _price_tokens(price)):
        return "the quote doesn't contain the price"
    if not public_url(url):
        return "AirFare only opens source pages on the public internet"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AirFare/1.0"})
    try:
        with _open(req, timeout=25) as r:
            raw = r.read(3_000_000).decode(r.headers.get_content_charset() or "utf-8", "replace")
    except (OSError, http.client.HTTPException, LookupError, ValueError) as e:   # also a read cut short, an odd charset
        return f"AirFare couldn't open the source page to confirm it ({getattr(e, 'reason', e)})"
    text = _norm(re.sub(r"<script.*?</script>|<style.*?</style>|<[^>]+>", " ", raw, flags=re.S | re.I))
    if _norm(quote) not in text:
        return "AirFare couldn't find the quoted price on the source page"
    return None


# ----- the lookup ---------------------------------------------------------------------------

def resolve_analyst(cfg: dict, provider: str | None = None, model: str | None = None,
                    web: bool = True) -> tuple[str, str | None, bool, str]:
    """(provider, model, web search, display name) for a lookup: the History page's picks, defaulting to the
    analyst in Settings. Raises ValueError for a choice that can't run."""
    provider = provider or cfg.get("llm_provider") or "claude"
    if provider == "deepseek":
        model = model or cfg.get("deepseek_model") or deepseek.MODELS[0]
        if model not in deepseek.MODELS:
            raise Problem("Pick a DeepSeek model from the list")
        if not cfg.get("deepseek_api_key"):
            raise Problem("Add a DeepSeek API key in AirFare Settings to use DeepSeek")
        return provider, model, False, f"DeepSeek {model}"           # its API can't browse
    if provider == "openai":
        model = model or cfg.get("openai_model") or openai_api.MODELS[0]
        if model not in openai_api.MODELS:
            raise Problem("Pick a ChatGPT model from the list")
        if not cfg.get("openai_api_key"):
            raise Problem("Add an OpenAI API key in AirFare Settings to use ChatGPT through the API")
        label = openai_api.LABELS.get(model, model)
        return provider, model, web, f"ChatGPT {label}" + ("" if web else " (no web search)")
    if provider == "chatgpt":
        if not chatgpt.codex_path():
            raise Problem("Install the Codex app and sign in to ChatGPT in AirFare Settings")
        if model and not chatgpt.MODEL_RE.match(model):
            raise Problem("Pick a ChatGPT model from the list")
        return provider, model or None, web, "ChatGPT" + ("" if web else " (no web search)")
    if provider != "claude":
        raise Problem("Pick Claude, ChatGPT or DeepSeek")
    if cfg.get("claude_mode") == "key" and not cfg.get("anthropic_api_key"):
        raise Problem("Add an Anthropic API key in AirFare Settings, or switch Claude to your Claude account")
    model = model if model is not None else (cfg.get("model") or "")
    if model and model not in analyst.CLAUDE_MODELS:
        raise Problem("Pick a Claude model from the list")
    label = analyst.CLAUDE_MODELS.get(model, "account default")
    return provider, model or None, web, f"Claude {label}" + ("" if web else " (no web search)")


async def lookup(c: Conditions, cfg: dict, provider: str | None = None, model: str | None = None,
                 web: bool = True) -> dict:
    """Ask the chosen analyst (default: the one in Settings), check the answer, store and return the result."""
    provider, model, web, name = resolve_analyst(cfg, provider, model, web)
    rates = await asyncio.to_thread(money.rates)
    if provider == "deepseek":
        answer, cost = await asyncio.to_thread(_ask_deepseek, build_prompt(c, False, rates), model,
                                               cfg.get("deepseek_api_key") or "")
    elif provider == "openai":
        answer, cost = await asyncio.to_thread(_ask_openai, build_prompt(c, web, rates), model,
                                               cfg.get("openai_api_key") or "", web)
    elif provider == "chatgpt":
        answer, cost = await asyncio.to_thread(_ask_chatgpt, build_prompt(c, web, rates), model, web)
    else:
        answer, cost = await _ask_claude(build_prompt(c, web, rates), model, web, analyst.claude_key(cfg))

    reason = check_answer(answer, c)
    if reason is None:
        reason = verify_source(answer["source_url"], answer["quote"], float(answer["lowest_price"]))
    found = reason is None
    log.info("price history lookup for %s with %s: %s", c.route_id, name, "found" if found else reason)
    result = {
        "time": datetime.now().isoformat(timespec="minutes"),
        "analyst": name,
        "route_id": c.route_id,
        "route_name": c.route_name,
        "conditions": asdict(c),
        "status": "found" if found else "no_information",
        "web_search": web,
        "cost_usd": cost,
        "notes": (answer or {}).get("notes") if isinstance(answer, dict) else None,
    }
    if found:
        result.update({k: answer.get(k) for k in ("lowest_price", "currency", "origin", "destination", "depart_date",
                                                  "return_date", "observed_on", "source_url", "source_name", "quote")})
        result.update(converted(answer, c.currency, rates))
    else:
        result["reason"] = reason
    return pricelog.add_research(result)


def converted(answer: dict, currency: str, rates: dict) -> dict:
    """The found price in the user's currency, by AirFare's own conversion. The analyst's conversion is only a
    cross-check: when the two differ by more than 5%, AirFare's figure is used and the gap is logged."""
    raw = str(answer.get("currency") or "").strip()
    src = raw.upper() if re.fullmatch(r"[A-Za-z]{3}", raw) else money.detect(raw)
    price = float(answer["lowest_price"])
    value = money.convert(price, src, currency, rates) if src else None
    if value is None:
        return {"converted_price": None, "converted_currency": currency}
    theirs = answer.get("price_converted")
    if isinstance(theirs, (int, float)) and value and abs(theirs - value) / value > 0.05:
        log.warning("the analyst converted %s %s to %s %s; AirFare's rate gives %.2f", price, src, theirs, currency, value)
    return {"converted_price": round(value, 2), "converted_currency": currency,
            "converted_text": money.fmt(value, currency)}


def conditions_for(cfg: dict, route_id: str, depart_from: str | None = None, depart_to: str | None = None,
                   return_from: str | None = None, return_to: str | None = None) -> Conditions:
    """The lookup's conditions: the History page's filters, falling back to the route's own dates."""
    route = next((r for r in cfg.get("routes", []) if r.get("id") == route_id), None)
    if route is None:
        raise Problem("That route isn't in your settings any more")
    seen = [r for r in pricelog.load() if r.get("route_id") == route_id]
    origin = (route.get("origin") or (seen[0]["origin"] if seen else "")).lower()
    dest = (route.get("destination") or (seen[0]["destination"] if seen else "")).lower()
    if not origin or not dest:
        raise Problem("This route has no airport codes to look up")

    def airports(code: str) -> list[str]:
        # A city code AirFare can't map to airports would make every answer "for a different route".
        if code not in serpapi.CITY_AIRPORTS and not (len(code) == 3 and code.isalpha()):
            raise Problem("This route uses the city code {code}, which AirFare can't map to airports; "
                          "the lookup needs 3-letter airport codes", code=code.upper())
        codes = serpapi.CITY_AIRPORTS.get(code, code.upper()).split(",")
        return sorted({*codes, code.upper()[:3] if code in serpapi.CITY_AIRPORTS else code.upper()})

    one_way = route.get("trip") != "return" and not any(r.get("return") for r in seen)
    d_from = depart_from or route.get("depart_from") or min((r["depart"] for r in seen if r.get("depart")), default="")
    d_to = depart_to or route.get("depart_to") or d_from
    r_from = None if one_way else (return_from or route.get("return_from") or d_from)
    r_to = None if one_way else (return_to or route.get("return_to") or r_from)
    if not d_from:
        raise Problem("Pick the departure dates to look up")
    if d_to < d_from or (r_from and r_to < r_from):
        raise Problem("The 'until' dates must come after the 'from' dates")
    return Conditions(route_id, route.get("name") or f"{origin.upper()} → {dest.upper()}", airports(origin),
                      airports(dest), d_from, d_to, r_from, r_to, int(route.get("adults") or 1),
                      route.get("cabin") or "economy", children=list(route.get("children") or []),
                      currency=cfg.get("currency") or money.DEFAULT, language=cfg.get("language") or "en")
