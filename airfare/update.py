"""Is there a newer AirFare? Asks GitHub for the latest release of the repository named in airfare/__init__.py
(__repo__), at most once a day when Settings opens, or whenever the user presses "Check for updates".
Nothing about this PC goes out: it is one anonymous GET of a public page."""
from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta

from . import __repo__, __version__
from .config import load_state, save_state

log = logging.getLogger(__name__)

API = "https://api.github.com/repos/{repo}/releases/latest"
EVERY = timedelta(days=1)
NOT_SET_UP = "Update checks aren't set up for this copy of AirFare."


def parse(version: str) -> tuple[int, ...]:
    """(1, 3, 0) from "1.3.0" or "v1.3"; letters after the numbers are ignored."""
    return tuple(int(n) for n in re.findall(r"\d+", str(version or ""))[:4]) or (0,)


def newer(latest: str, current: str) -> bool:
    return parse(latest) > parse(current)


def fetch() -> dict:
    """The latest release on GitHub: {"latest", "url", "newer"}. Raises OSError when it can't be reached."""
    if not __repo__:
        raise OSError(NOT_SET_UP)
    req = urllib.request.Request(API.format(repo=__repo__),
                                 headers={"Accept": "application/vnd.github+json", "User-Agent": "AirFare"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise OSError("no release found" if e.code == 404 else f"GitHub answered {e.code}") from None
    except (urllib.error.URLError, ValueError) as e:
        raise OSError(f"couldn't reach GitHub: {getattr(e, 'reason', e)}") from None
    tag = str(data.get("tag_name") or "")
    url = str(data.get("html_url") or f"https://github.com/{__repo__}/releases")
    if not re.fullmatch(r"v?\d+(\.\d+)*", tag) or not url.startswith("https://github.com/"):
        raise OSError("GitHub's answer didn't look like a release")
    return {"latest": tag.lstrip("v"), "url": url, "newer": newer(tag, __version__)}


def cached(state: dict | None = None) -> dict:
    """The last answer, with no network: {"current", "checked", "latest", "url", "newer", "error"}."""
    info = (state if state is not None else load_state()).get("update") or {}
    return {"current": __version__, "set_up": bool(__repo__), **{k: info.get(k) for k in ("checked", "latest", "url", "error")},
            "newer": bool(info.get("latest")) and newer(info["latest"], __version__)}


def check(force: bool = False) -> dict:
    """Ask GitHub (when it's time, or forced), remember the answer in state.json, and return it."""
    state = load_state()
    info = state.get("update") or {}
    try:
        due = force or datetime.now() - datetime.fromisoformat(info.get("checked", "")) > EVERY
    except ValueError:
        due = True
    if not due or not __repo__:
        return cached(state)
    stamp = datetime.now().isoformat(timespec="minutes")
    try:
        info = {"checked": stamp, **fetch(), "error": None}
        log.info("update check: AirFare %s, latest release %s", __version__, info["latest"])
    except OSError as e:
        info = {**info, "checked": stamp, "error": str(e)}
        log.warning("update check failed: %s", e)
    # Read state.json again: a check may have written it (the limits' page count) while GitHub answered.
    state = load_state()
    state["update"] = {k: info.get(k) for k in ("checked", "latest", "url", "error")}
    save_state(state)
    return cached(state)
