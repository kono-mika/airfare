"""Paths and the JSON files that hold AirFare's settings, state and price history."""
from __future__ import annotations

import copy
import json
import logging
import os
from pathlib import Path

from . import platform, secrets
from .i18n import LANGS, system_language

log = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("AIRFARE_DATA", PROJECT_DIR / "data"))
CONFIG_FILE = DATA_DIR / "config.json"
STATE_FILE = DATA_DIR / "state.json"
HISTORY_FILE = DATA_DIR / "history.json"
REPORTS_DIR = DATA_DIR / "reports"
LOGS_DIR = DATA_DIR / "logs"
LOCK_FILE = DATA_DIR / "run.lock"

WEBUI_PORT = int(os.environ.get("AIRFARE_PORT", 8765))

# Skyscanner and Aviasales through the browser extension, Google Flights through SerpApi
SOURCES = ("extension", "aviasales", "serpapi")
# How many Skyscanner and Aviasales pages a check may open (limits.py); anything else counts as "personal".
LIMITS = ("personal", "extended")
ALERT_KINDS = ("cheapest", "fastest", "best")
# The API keys: encrypted in config.json for this Windows account, or in the keychain on macOS and Linux
# (secrets.py); plain text once loaded.
KEYS = ("serpapi_key", "deepseek_api_key", "openai_api_key", "anthropic_api_key")

DEFAULT_CONFIG = {
    "domain": "www.skyscanner.net",
    "wait_seconds": 20,
    "max_pages": 20,
    "limits": "personal",      # the browser sources' limits (limits.py): "personal" or "extended"
    # "claude" (Claude account or Anthropic API key), "chatgpt" (ChatGPT account), "openai" (OpenAI API key),
    # "deepseek" (DeepSeek API key) or "none" (AirFare's own rules only: no AI account needed)
    "llm_provider": "none",         # AirFare's own rules until the user picks an analyst (no account needed)
    "model": "claude-sonnet-5-5",   # Opus-level picks here at about half the cost (measured on real checks)
    "claude_mode": "key",           # "key" (Anthropic API key, the path meant for a shared tool) or "account" (Claude login)
    "anthropic_api_key": "",
    "deepseek_api_key": "",
    "deepseek_model": "deepseek-flash",
    "openai_api_key": "",
    "openai_model": "gpt-6.1-terra",
    "chatgpt_model": "",            # the ChatGPT account's own default model, through the Codex app
    "session_max_k": 40,            # start a fresh Claude session before one grows past this many thousand tokens
    "sources": [],                  # none until the user picks: the sites' terms are theirs to read first
    "serpapi_key": "",
    "currency": "EUR",         # every price is compared, alerted and shown in this currency (see money.py)
    "language": "",            # "en", "es" or "ru"; empty until picked, then the system's display language is used
    # LOW PRICE per kind: alert when its price is at least `drop` % below its reference, or at most `max`.
    "alerts": {"cheapest": {"on": True, "drop": 5, "max": None},
               "fastest": {"on": True, "drop": 3, "max": None},
               "best": {"on": True, "drop": 3, "max": None}},
    "alert_max_hours": None,         # alerts ignore trips where one direction takes longer than this
    "alert_no_self_transfer": False,  # alerts ignore self-transfer trips
    # Automatic clean-up after each check, in days (None keeps everything): price history records, check
    # reports, and earlier routes on the dashboard.
    "cleanup": {"records_days": None, "reports_days": None, "dashboard_days": None},
    "schedule": "startup",     # "startup", "interval" (every interval_hours while the PC is on) or "both"
    "interval_hours": 6,
    "browser": "chrome",       # the browser the extension runs in: "chrome", "edge", "brave", "opera" or "firefox"
                               # (see extension.py)
    "tray": False,             # keep a AirFare icon in the notification area while the background checker runs
    "update_check": True,      # ask GitHub for a newer release when Settings opens, at most once a day (update.py)
    "routes": [],
}
# The fields of a route that Settings writes. save_config keeps any other field a route has on disk (written by
# a newer or older AirFare), and any top-level key not in DEFAULT_CONFIG, so settings survive going either way.
ROUTE_FIELDS = ("id", "name", "enabled", "origin", "destination", "trip", "depart_from", "depart_to", "return_from",
                "return_to", "adults", "children", "cabin", "direct_only", "manual_pages")
# Keys this version reads only to convert them (load_config, migrate.py): saving never brings them back.
RETIRED_KEYS = ("min_drop_percent",)


def ensure_dirs() -> None:
    for d in (DATA_DIR, REPORTS_DIR, LOGS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except json.JSONDecodeError:
        # Keep the broken file for inspection rather than silently overwriting it later.
        path.replace(path.with_suffix(path.suffix + ".broken"))
        return default


def write_json(path: Path, data, mode: int | None = None) -> None:
    """Write the file in one step (a temporary file, then a rename); `mode` is its permissions on macOS and
    Linux, set before the rename so the file never exists with wider ones."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    if mode is not None and not platform.WINDOWS:
        os.chmod(tmp, mode)
    os.replace(tmp, path)


def load_config() -> dict:
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    stored = read_json(CONFIG_FILE, {})
    cfg.update(stored)
    cfg["routes"] = list(cfg.get("routes") or [])
    alerts = stored.get("alerts") if isinstance(stored.get("alerts"), dict) else None
    if alerts is None and stored.get("min_drop_percent") is not None:
        # Settings from before alerts had kinds: one minimum drop for everything.
        alerts = {kind: {"on": True, "drop": stored["min_drop_percent"], "max": None} for kind in ALERT_KINDS}
    cfg["alerts"] = {kind: {**DEFAULT_CONFIG["alerts"][kind], **((alerts or {}).get(kind) or {})} for kind in ALERT_KINDS}
    cfg.pop("min_drop_percent", None)
    if cfg.get("language") not in LANGS:
        cfg["language"] = system_language()
    if cfg.get("limits") not in LIMITS:
        cfg["limits"] = "personal"
    _open_keys(cfg)
    return cfg


_warned: set[tuple[str, str]] = set()


def _open_keys(cfg: dict) -> None:
    """Decrypt the API keys in place. A plain key (config.json from before encryption) is used as it is and
    encrypted at the next save. A key this Windows account can't decrypt (config.json copied from another PC
    or user, or damaged; on macOS and Linux, one missing from the keychain) counts as missing; `unreadable_keys`
    names it so Settings and doctor ask for it again."""
    unreadable = []
    for name in KEYS:
        stored = str(cfg.get(name) or "")
        try:
            cfg[name] = secrets.unprotect(stored)
        except secrets.SecretError as e:
            if (name, stored) not in _warned:       # settings load on every page request: say it once
                _warned.add((name, stored))
                log.warning("%s in %s can't be decrypted on %s (%s); it has to be entered again in Settings",
                            name, CONFIG_FILE, secrets.ACCOUNT, e)
            cfg[name] = ""
            unreadable.append(name)
    if unreadable:
        cfg["unreadable_keys"] = unreadable


def save_config(cfg: dict) -> None:
    """Write the settings with the API keys encrypted (the caller's dict keeps them in plain text).

    What this version doesn't know stays as it was on disk: top-level keys outside DEFAULT_CONFIG and route
    fields outside ROUTE_FIELDS (matched by route id), so a newer AirFare's settings survive a save here."""
    stored = {k: v for k, v in cfg.items() if k != "unreadable_keys"}
    on_disk = read_json(CONFIG_FILE, {})
    if isinstance(on_disk, dict):
        for k, v in on_disk.items():
            if k not in stored and k not in DEFAULT_CONFIG and k not in RETIRED_KEYS and k != "unreadable_keys":
                stored[k] = v
        before = {r.get("id"): r for r in on_disk.get("routes") or [] if isinstance(r, dict) and r.get("id")}
        if isinstance(stored.get("routes"), list):
            stored["routes"] = [{**{k: v for k, v in before.get(r.get("id"), {}).items() if k not in ROUTE_FIELDS}, **r}
                                if isinstance(r, dict) else r for r in stored["routes"]]
    for name in KEYS:
        if stored.get(name):
            stored[name] = secrets.protect(stored[name], name)
    write_json(CONFIG_FILE, stored, mode=0o600)   # this user only: without a keychain, the keys are plain text


def load_state() -> dict:
    return read_json(STATE_FILE, {})


def save_state(state: dict) -> None:
    write_json(STATE_FILE, state)


def load_history() -> dict:
    return read_json(HISTORY_FILE, {"routes": {}, "runs": []})


def save_history(history: dict) -> None:
    write_json(HISTORY_FILE, history)
