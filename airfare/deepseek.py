"""DeepSeek as AirFare's analyst, through its OpenAI-format chat API (https://api-docs.deepseek.com).

DeepSeek keeps no conversation on its side, so AirFare stores each "session" as a message list in
data/deepseek/<id>.json and sends it back on every check. DeepSeek's automatic context cache makes the
repeated part of that history cheap.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass

from .config import DATA_DIR

log = logging.getLogger(__name__)

API = "https://api.deepseek.com"
MODELS = ("deepseek-flash", "deepseek-v4-pro")
# Estimated USD per 1M tokens: (input cache hit, input cache miss, output). DeepSeek changes prices and runs
# promotions, so these only feed the logged estimate; https://api-docs.deepseek.com/quick_start/pricing is the source.
PRICES = {"deepseek-flash": (0.0028, 0.14, 0.28), "deepseek-v4-pro": (0.003625, 0.435, 0.87)}
SESSIONS_DIR = DATA_DIR / "deepseek"


class DeepSeekError(RuntimeError):
    pass


@dataclass
class Reply:
    text: str
    session_id: str
    context_tokens: int        # size of the stored conversation after this reply
    cost_usd: float | None     # estimate for this call


def _request(path: str, api_key: str, body: dict | None = None, timeout: int = 600) -> dict:
    req = urllib.request.Request(
        API + path, method="POST" if body is not None else "GET",
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            msg = (json.loads(e.read().decode("utf-8")).get("error") or {}).get("message") or str(e)
        except Exception:
            msg = str(e)
        raise DeepSeekError(f"DeepSeek {e.code}: {msg}") from None
    except urllib.error.URLError as e:
        raise DeepSeekError(f"couldn't reach DeepSeek: {e.reason}") from None
    except ValueError:
        # http.client rejects a header with line breaks and quotes it, key included: never pass that on.
        raise DeepSeekError("the DeepSeek API key contains characters an API key can't have; add it again in Settings") from None


def _session_file(session_id: str):
    return SESSIONS_DIR / f"{session_id}.json"


def load_session(session_id: str) -> list[dict] | None:
    try:
        return json.loads(_session_file(session_id).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _save_session(session_id: str, messages: list[dict]) -> None:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    _session_file(session_id).write_text(json.dumps(messages, ensure_ascii=False, indent=1), encoding="utf-8")


def estimate_cost(usage: dict, model: str) -> float | None:
    if model not in PRICES:
        return None
    hit, miss, out = PRICES[model]
    return round((int(usage.get("prompt_cache_hit_tokens") or 0) * hit
                  + int(usage.get("prompt_cache_miss_tokens") or 0) * miss
                  + int(usage.get("completion_tokens") or 0) * out) / 1_000_000, 6)


def complete(messages: list[dict], model: str, api_key: str, json_mode: bool = False) -> tuple[str, dict]:
    """One chat completion in thinking mode. Returns (answer, usage). json_mode asks for a JSON object
    (the prompt itself must also ask for JSON)."""
    body = {"model": model, "messages": messages, "stream": False,
            "thinking": {"type": "enabled"}, "reasoning_effort": "high"}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    data = _request("/chat/completions", api_key, body)
    message = ((data.get("choices") or [{}])[0]).get("message") or {}
    text = message.get("content") or ""
    if not text.strip():
        raise DeepSeekError("DeepSeek returned an empty answer")
    return text, data.get("usage") or {}


def ask(prompt: str, system: str, session_id: str | None, model: str, api_key: str) -> Reply:
    """Send one check, continuing the stored conversation when there is one."""
    if not api_key:
        raise DeepSeekError("no DeepSeek API key: add it in AirFare Settings")
    history = load_session(session_id) if session_id else None
    if session_id and history is None:
        log.warning("DeepSeek conversation %s is gone; starting a new one", session_id)
    sid = session_id if history is not None else uuid.uuid4().hex
    history = history or []
    user = {"role": "user", "content": prompt}
    # Only the answer goes back into the history; the reasoning is not part of the conversation.
    text, usage = complete([{"role": "system", "content": system}, *history, user], model, api_key)
    _save_session(sid, [*history, user, {"role": "assistant", "content": text}])
    reasoning = int(((usage.get("completion_tokens_details") or {}).get("reasoning_tokens")) or 0)
    context = int(usage.get("prompt_tokens") or 0) + int(usage.get("completion_tokens") or 0) - reasoning
    log.info("DeepSeek %s: %s prompt tokens (%s cached), %s out", model, usage.get("prompt_tokens"),
             usage.get("prompt_cache_hit_tokens"), usage.get("completion_tokens"))
    return Reply(text, sid, context, estimate_cost(usage, model))


def balance(api_key: str) -> dict:
    """Account balance (free call), for the Settings check and doctor."""
    data = _request("/user/balance", api_key, timeout=20)
    infos = data.get("balance_infos") or []
    return {"available": data.get("is_available"),
            "balance": ", ".join(f"{i.get('total_balance')} {i.get('currency')}" for i in infos) or "?"}


def chat(session_id: str | None, model: str, api_key: str, system: str) -> None:
    """A small console chat that continues AirFare's DeepSeek conversation."""
    history = (load_session(session_id) if session_id else None) or []
    sid = session_id or uuid.uuid4().hex
    print(f"DeepSeek ({model}) · conversation {sid[:8]} · {len(history) // 2} earlier message(s). "
          "Empty line to quit.")
    while True:
        try:
            line = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            break
        user = {"role": "user", "content": line}
        try:
            text, _ = complete([{"role": "system", "content": system}, *history, user], model, api_key)
        except DeepSeekError as e:
            print(f"! {e}")
            continue
        history += [user, {"role": "assistant", "content": text}]
        _save_session(sid, history)
        print(f"\ndeepseek> {text}")
