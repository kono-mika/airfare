"""Send each price document to the analyst's ongoing session (Claude or DeepSeek) and read back its verdict."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import anyio
import claude_agent_sdk
from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, TextBlock, query

from . import chatgpt, deepseek, openai_api, platform
from .i18n import LANGUAGE_NAMES
from .config import PROJECT_DIR, load_state, save_state

log = logging.getLogger(__name__)

SESSION_TITLE = "AirFare flight prices"
# claude: the Claude Code CLI with the user's Claude account or an Anthropic API key; deepseek and openai: API
# keys; chatgpt: the user's ChatGPT account through OpenAI's Codex app; none: no analyst at all (AirFare's own
# rules still pick the cheapest and fastest flights and alert on them).
PROVIDER_NAMES = {"claude": "Claude", "deepseek": "DeepSeek", "openai": "ChatGPT", "chatgpt": "ChatGPT",
                  "none": "No analyst"}
CLAUDE_MODELS = {"claude-sonnet-5-5": "Sonnet 5.5", "claude-opus-5-5": "Opus 5.5", "claude-haiku-5-5": "Haiku 5.5"}
ANTHROPIC_API = "https://api.anthropic.com/v1"
ANTHROPIC_VERSION = "2023-06-01"

RULES = """You are the flight-price analyst for AirFare, a small app on the user's PC. Each time the computer starts, \
AirFare checks the user's tracked routes and sends you the prices as a new message. Recent checks may be above, but \
AirFare starts a fresh conversation when this one gets long, so the "Previous records" block in each message is the \
authoritative memory of earlier prices and of your last recommendation.

Reply to every check in Markdown:

1. First line: exactly `LOW PRICE` (in English, nothing else on that line) if and only if at least one route reaches \
one of its LOW PRICE targets under "Previous records". There are three kinds, each with its own target:
   - cheapest: today's cheapest fare reaches the cheapest target;
   - fastest: the cheapest of today's quickest trips (within 10% of the shortest travel time) reaches the fastest \
target;
   - best value: today's best-value option reaches the best-value target, with the same or fewer stops and at most \
about 20% longer total travel time than its reference.
   The targets already include the user's minimum drops and price ceilings, so smaller drops are not LOW PRICE: \
mention them under "Since last check" instead. Leave out trips the alert rules say the user ignores. Routes marked \
"no earlier prices" are a baseline. Without LOW PRICE, do not write those words anywhere and do not mention that \
they are absent; start directly with the analysis. With LOW PRICE, say which kind reached its target.
2. For each route (each source section lists its top 3 best, cheapest and fastest flights):
   - **3 cheapest**: the three cheapest options across all sources, each with price, source, outbound and return \
dates and times, airline(s), stops and total time.
   - **Fastest**: the cheapest of the quickest trips, with its price, source, dates and total time.
   - **3 best value**: your three recommendations, best first, balancing price, stops, total travel time and sensible \
departure hours (avoid self-transfers and very early or late departures unless they are much cheaper). Give price, \
source, dates and one short reason each.
   If several date combinations were checked, say which dates are cheapest.
3. **Overall**: the single cheapest and the single best-value pick across all routes.
4. **Since last check**: one or two lines on how prices moved compared with the previous records.
5. Briefly list pages that failed or were blocked, if any.

Prices can come from more than one source (each section names it: Skyscanner, Aviasales, Google Flights). Compare \
across sources and say which source each recommended flight is from. Google Flights prices for return trips are \
round-trip totals and only the outbound flight is listed. AirFare shows every price in the user's currency (the \
document says which) and has already converted prices a site showed in another currency; the Notes column keeps \
the site's own price. If a price is still in another currency (page text), convert it with the exchange rates in \
the document and show the converted price first, with the original in brackets. Never compare prices in different \
currencies directly.

Keep it short and scannable. Use only flights that appear in the document; never invent prices. Quote prices exactly as \
shown, with their currency.

Write the reply in the language each check asks for; the `LOW PRICE` line and the comment below stay as shown.

End the reply with this machine-readable comment on its own line (one entry per route id, plain numbers in the \
user's currency; "best_value" is your first best-value pick, "best_value_stops" its largest number of stops in one \
direction and "best_value_minutes" its total travel time in minutes; "take" is one or two plain sentences saying what \
you would book and why, shown at the top of the user's dashboard):
<!--airfare {"low_price": true, "take": "Book the €150 Ryanair direct on 18 Dec; the €120 fare saves €30 but \
takes 9 hours longer.", "routes": {"<route id>": {"cheapest": 123.45, "best_value": 150.0, \
"best_value_text": "€150, Thu 18 Dec 06:15 / Sat 27 Dec 11:25, Ryanair, direct", "best_value_stops": 0, \
"best_value_minutes": 290}}}-->"""

_SUMMARY_RE = re.compile(r"<!--\s*airfare\s*(\{.*?\})\s*-->", re.S)


class ClaudeError(RuntimeError):
    pass


@dataclass
class Verdict:
    text: str                 # the analysis, without the machine-readable comment
    low_price: bool
    session_id: str
    resumed: bool
    summary: dict = field(default_factory=dict)
    cost_usd: float | None = None


def build_prompt(document: str, previous: str, when: datetime, language: str | None = None) -> str:
    name = LANGUAGE_NAMES.get(language or "en", "English")
    return (f"New AirFare check — {when:%A %Y-%m-%d %H:%M}. Write your reply in {name}.\n\n"
            f"### Previous records\n{previous or '(none yet — this is the first check: baseline, no LOW PRICE)'}\n\n"
            f"### Today's price document\n\n{document}")


def says_low_price(text: str) -> bool:
    for line in text.splitlines():
        line = line.strip().strip("*#_` ").strip()
        if line:
            return line.upper() == "LOW PRICE"
    return False


def parse_reply(text: str) -> tuple[str, dict]:
    summary: dict = {}
    m = _SUMMARY_RE.search(text)
    if m:
        try:
            # NaN and Infinity aren't JSON, whatever Python's parser would let through.
            summary = json.loads(m.group(1), parse_constant=lambda c: None)
        except (json.JSONDecodeError, RecursionError):
            log.warning("could not parse the analyst's summary comment")
        if not isinstance(summary, dict):
            summary = {}
        text = (text[:m.start()] + text[m.end():]).rstrip()
    return text.strip(), summary


def cli_path() -> Path:
    return Path(claude_agent_sdk.__file__).parent / "_bundled" / ("claude.exe" if platform.WINDOWS else "claude")


def claude_command() -> str:
    """The Claude Code CLI that runs AirFare's checks: the copy bundled with the Agent SDK, so the login
    check and "Log in to Claude" use the same program. One on PATH only stands in when that copy is missing."""
    bundled = cli_path()
    return str(bundled) if bundled.exists() else (shutil.which("claude") or str(bundled))


def claude_key(cfg: dict) -> str | None:
    """The Anthropic API key the checks run with, or None when Claude runs through the user's Claude account."""
    return (cfg.get("anthropic_api_key") or None) if cfg.get("claude_mode") == "key" else None


def claude_env(api_key: str | None = None) -> dict:
    """The environment the Claude CLI runs with: an API key, when AirFare uses one, instead of the login."""
    env = {"CLAUDE_AGENT_SDK_CLIENT_APP": "airfare/1.0"}
    if api_key:
        env["ANTHROPIC_API_KEY"] = api_key
    return env


def check_key(api_key: str) -> dict:
    """Whether Anthropic accepts the key (listing the models costs nothing)."""
    import urllib.error
    import urllib.request
    req = urllib.request.Request(ANTHROPIC_API + "/models", headers={"x-api-key": api_key,
                                                                     "anthropic-version": ANTHROPIC_VERSION})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            msg = (json.loads(e.read().decode("utf-8")).get("error") or {}).get("message") or str(e)
        except Exception:
            msg = str(e)
        raise ClaudeError(f"Anthropic {e.code}: {msg}") from None
    except urllib.error.URLError as e:
        raise ClaudeError(f"couldn't reach Anthropic: {e.reason}") from None
    except ValueError:
        raise ClaudeError("the Anthropic API key contains characters an API key can't have; add it again in Settings") from None
    return {"ok": True, "models": len(data.get("data") or [])}


def login_status(cfg: dict | None = None) -> dict:
    """Whether the Claude CLI is logged in, and on which plan (no account details leave this function). With
    an Anthropic API key in Settings, whether Anthropic accepts the key instead."""
    key = claude_key(cfg or {})
    if key:
        try:
            check_key(key)
            return {"logged_in": True, "plan": "API key", "key": True}
        except ClaudeError as e:
            return {"logged_in": False, "error": f"Anthropic doesn't accept the saved API key: {e}", "key": True}
    try:
        # The CLI writes UTF-8 (its JSON holds the profile path, which may not be plain ASCII).
        r = subprocess.run([claude_command(), "auth", "status"], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=30, creationflags=platform.NO_WINDOW)
        data = json.loads(r.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired) as e:
        return {"logged_in": False, "error": f"Couldn't ask the Claude CLI whether it is logged in: {e}"}
    plan = str(data.get("subscriptionType") or "").strip()
    return {"logged_in": bool(data.get("loggedIn")), "plan": f"{plan.title()} plan" if plan else ""}


def _hide_cli_console() -> None:
    """Start the Claude CLI without a console window: the startup run uses pythonw, which has no console,
    so Windows would otherwise open a new one for claude.exe. The SDK doesn't expose creationflags. (Only
    Windows opens console windows for programs.)"""
    if not platform.WINDOWS or getattr(anyio.open_process, "_airfare", False):
        return
    original = anyio.open_process

    async def open_process(*args, **kwargs):
        kwargs.setdefault("creationflags", subprocess.CREATE_NO_WINDOW)
        return await original(*args, **kwargs)

    open_process._airfare = True
    anyio.open_process = open_process


async def _ask(prompt: str, session_id: str | None, model: str | None,
               api_key: str | None = None) -> tuple[str, ResultMessage]:
    options = ClaudeAgentOptions(
        resume=session_id,
        cwd=str(PROJECT_DIR),
        tools=[],
        max_turns=1,
        setting_sources=[],
        # Rebuild the rules on every check, so rule changes reach a session that was started earlier.
        system_prompt={"type": "custom", "prompt": RULES, "snapshot": False},
        model=model or None,
        env=claude_env(api_key),
    )
    parts: list[str] = []
    result: ResultMessage | None = None
    _hide_cli_console()
    async for msg in query(prompt=prompt, options=options):
        if isinstance(msg, AssistantMessage):
            parts.extend(b.text for b in msg.content if isinstance(b, TextBlock))
        elif isinstance(msg, ResultMessage):
            result = msg
    if result is None:
        raise ClaudeError("Claude ended without a result")
    if result.is_error:
        raise ClaudeError(f"Claude returned an error ({result.subtype}): {result.result or result.errors}")
    return (result.result or "\n".join(parts)), result


def _missing_session(err: Exception) -> bool:
    msg = str(err).lower()
    return "no conversation found" in msg or ("session" in msg and "not found" in msg)


def context_tokens(usage: dict | None) -> int:
    """How big the conversation is after this reply: everything sent plus what Claude wrote."""
    u = usage or {}
    return sum(int(u.get(k) or 0) for k in
               ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens"))


def fresh_session_reason(state: dict, prompt: str, model: str | None, max_tokens: int) -> str | None:
    """Why this check should start a new session instead of resuming, or None to resume.

    Checks are hours apart, so the prompt cache has always expired and a resumed session pays for its
    whole history again. Past a size limit that costs more than it helps: the price memory lives in
    history.json and reaches Claude through the "Previous records" block anyway.
    """
    if not state.get("session_id"):
        return None
    if state.get("session_model", "") != (model or ""):     # sessions from before this was recorded used the default
        return "the model changed"
    size = int(state.get("context_tokens") or 0)
    if size and size + len(prompt) // 3 > max_tokens:    # ~3 characters per token, on the safe side
        return f"the session reached about {size // 1000}k tokens"
    return None


def session_slot(state: dict, provider: str) -> dict:
    """Where a provider's session bookkeeping lives in state.json (Claude's at the top, as it always was)."""
    return state if provider == "claude" else state.setdefault(provider, {})


async def _ask_claude(prompt: str, sid: str | None, model: str | None, slot: dict,
                      api_key: str | None = None) -> tuple[str, str, int, float | None, bool]:
    resumed = bool(sid)
    try:
        text, result = await _ask(prompt, sid, model, api_key)
    except Exception as e:
        if not (sid and _missing_session(e)):
            raise
        log.warning("saved Claude session %s is gone (%s); starting a new one", sid, e)
        resumed = False
        text, result = await _ask(prompt, None, model, api_key)
    # The CLI reports the session's running total; this check's own cost is the difference.
    before = float(slot.get("session_cost_usd") or 0) if resumed else 0.0
    total = result.total_cost_usd
    check_cost = None if total is None else round(max(total - before, 0.0), 6)
    slot["session_cost_usd"] = total
    return text, result.session_id, context_tokens(result.usage), check_cost, resumed


async def _ask_deepseek(prompt: str, sid: str | None, model: str, api_key: str, slot: dict) -> tuple[str, str, int, float | None, bool]:
    reply = await asyncio.to_thread(deepseek.ask, prompt, RULES, sid, model, api_key)
    resumed = bool(sid) and reply.session_id == sid
    slot["session_cost_usd"] = round((float(slot.get("session_cost_usd") or 0) if resumed else 0.0)
                                     + (reply.cost_usd or 0.0), 6)
    return reply.text, reply.session_id, reply.context_tokens, reply.cost_usd, resumed


async def _ask_openai(prompt: str, sid: str | None, model: str, api_key: str, slot: dict) -> tuple[str, str, int, float | None, bool]:
    reply = await asyncio.to_thread(openai_api.ask, prompt, RULES, sid, model, api_key)
    resumed = bool(sid) and reply.session_id == sid
    slot["session_cost_usd"] = round((float(slot.get("session_cost_usd") or 0) if resumed else 0.0)
                                     + (reply.cost_usd or 0.0), 6)
    return reply.text, reply.session_id, reply.context_tokens, reply.cost_usd, resumed


async def _ask_chatgpt(prompt: str, sid: str | None, model: str | None, slot: dict) -> tuple[str, str, int, float | None, bool]:
    reply = await asyncio.to_thread(chatgpt.ask, prompt, RULES, sid, model)
    slot["rules_id"] = chatgpt.rules_id(RULES)
    resumed = bool(sid) and reply.session_id == sid
    # Codex counts tokens for the whole thread so far; this turn (the conversation's size now) is the difference.
    before = int(slot.get("codex_tokens_total") or 0) if resumed else 0
    slot["codex_tokens_total"] = reply.context_tokens
    return reply.text, reply.session_id, max(reply.context_tokens - before, 0), None, resumed


async def analyse(document: str, previous: str, when: datetime, model: str | None = None,
                  max_tokens: int = 40_000, provider: str = "claude", api_key: str | None = None,
                  language: str | None = None) -> Verdict:
    name = PROVIDER_NAMES.get(provider, provider)
    if provider == "none":
        raise ClaudeError("no analyst is set up")      # runner.run_check never asks in that case
    state = load_state()
    slot = session_slot(state, provider)
    prompt = build_prompt(document, previous, when, language)
    sid = slot.get("session_id")
    reason = fresh_session_reason(slot, prompt, model, max_tokens)
    if not reason and provider == "chatgpt" and sid and slot.get("rules_id") != chatgpt.rules_id(RULES):
        reason = "AirFare's rules changed"       # Codex keeps the rules inside the conversation itself
    if reason:
        log.info("starting a fresh %s session: %s", name, reason)
        slot["previous_sessions"] = (slot.get("previous_sessions") or [])[-19:] + [
            {"id": sid, "started": slot.get("session_started"), "checks": slot.get("session_checks")}]
        sid = None

    if provider == "deepseek":
        text, new_sid, size, check_cost, resumed = await _ask_deepseek(prompt, sid, model or deepseek.MODELS[0],
                                                                       api_key or "", slot)
    elif provider == "openai":
        text, new_sid, size, check_cost, resumed = await _ask_openai(prompt, sid, model or openai_api.MODELS[0],
                                                                     api_key or "", slot)
    elif provider == "chatgpt":
        text, new_sid, size, check_cost, resumed = await _ask_chatgpt(prompt, sid, model, slot)
    else:
        text, new_sid, size, check_cost, resumed = await _ask_claude(prompt, sid, model, slot, api_key)

    if new_sid != slot.get("session_id"):
        log.info("%s session is now %s (was %s)", name, new_sid, slot.get("session_id"))
        slot.update(session_id=new_sid, session_started=when.isoformat(timespec="minutes"),
                    session_model=model or "", session_checks=0)
        if provider == "claude":
            try:
                claude_agent_sdk.rename_session(new_sid, f"{SESSION_TITLE} (from {when:%d %b %H:%M})",
                                                directory=str(PROJECT_DIR))
            except Exception as e:
                log.debug("could not name the session: %s", e)
    slot["session_checks"] = int(slot.get("session_checks") or 0) + 1
    slot["context_tokens"] = size
    state["last_check"] = when.isoformat(timespec="minutes")
    state["analyst"] = provider
    save_state(state)

    analysis, summary = parse_reply(text)
    low = says_low_price(analysis)
    if bool(summary.get("low_price")) != low and summary:
        log.warning("%s's LOW PRICE line (%s) and its summary flag (%s) disagree; using the line",
                    name, low, summary.get("low_price"))
    return Verdict(analysis, low, new_sid, resumed, summary, check_cost)
