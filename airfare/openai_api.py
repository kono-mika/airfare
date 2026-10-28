"""ChatGPT through the OpenAI API (an API key from platform.openai.com), with the Responses API.

Like DeepSeek, nothing is kept on OpenAI's side (store: false): AirFare keeps each conversation as a message
list in data/openai/<id>.json and sends it back on every check. OpenAI's automatic prompt caching makes the
repeated part cheap. Lookups can search the web with the API's own web_search tool.
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

API = "https://api.openai.com/v1"
MODELS = ("gpt-6.1-terra", "gpt-6-luna", "gpt-6.1-sol", "gpt-6-astra")
LABELS = {"gpt-6.1-terra": "GPT-6.1 Terra", "gpt-6-luna": "GPT-6 Luna", "gpt-6.1-sol": "GPT-6.1 Sol",
          "gpt-6-astra": "GPT-6 Astra"}
# Estimated USD per 1M tokens: (cached input, input, output), from OpenAI's pricing page; they only feed the
# logged estimate, OpenAI's billing is the source of truth.
PRICES = {"gpt-6.1-terra": (0.05, 1.00, 5.00), "gpt-6-luna": (0.01, 0.10, 0.50), "gpt-6.1-sol": (0.10, 2.00, 10.00),
          "gpt-6-astra": (1.00, 10.00, 50.00)}
SESSIONS_DIR = DATA_DIR / "openai"


class OpenAIError(RuntimeError):
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
        raise OpenAIError(f"OpenAI {e.code}: {msg}") from None
    except urllib.error.URLError as e:
        raise OpenAIError(f"couldn't reach OpenAI: {e.reason}") from None
    except ValueError:
        # http.client rejects a header with line breaks and quotes it, key included: never pass that on.
        raise OpenAIError("the OpenAI API key contains characters an API key can't have; add it again in Settings") from None


def output_text(data: dict) -> str:
    """The answer's text: the convenience field when present, otherwise the message items' output_text parts."""
    if isinstance(data.get("output_text"), str) and data["output_text"].strip():
        return data["output_text"]
    parts = []
    for item in data.get("output") or []:
        if isinstance(item, dict) and item.get("type") == "message":
            parts += [c.get("text") or "" for c in item.get("content") or []
                      if isinstance(c, dict) and c.get("type") == "output_text"]
    return "".join(parts)


def respond(messages: list[dict], system: str, model: str, api_key: str, web: bool = False,
            schema: dict | None = None) -> tuple[str, dict]:
    """One answer from the Responses API. Returns (text, usage)."""
    body = {"model": model, "instructions": system, "input": messages, "store": False}
    if web:
        body["tools"] = [{"type": "web_search"}]
    if schema:
        body["text"] = {"format": {"type": "json_schema", "name": "answer", "strict": True, "schema": schema}}
    data = _request("/responses", api_key, body)
    if data.get("error"):
        raise OpenAIError(f"OpenAI: {(data['error'] or {}).get('message') or data['error']}")
    text = output_text(data)
    if not text.strip():
        raise OpenAIError("OpenAI returned an empty answer")
    return text, data.get("usage") or {}


def estimate_cost(usage: dict, model: str) -> float | None:
    if model not in PRICES:
        return None
    hit, miss, out = PRICES[model]
    total_in = int(usage.get("input_tokens") or 0)
    cached = int((usage.get("input_tokens_details") or {}).get("cached_tokens") or 0)
    return round((cached * hit + max(total_in - cached, 0) * miss + int(usage.get("output_tokens") or 0) * out)
                 / 1_000_000, 6)


def _session_file(session_id: str):
    return SESSIONS_DIR / f"{session_id}.json"


def load_session(session_id: str) -> list[dict] | None:
    try:
        messages = json.loads(_session_file(session_id).read_text(encoding="utf-8"))
        return messages if isinstance(messages, list) else None
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _save_session(session_id: str, messages: list[dict]) -> None:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    _session_file(session_id).write_text(json.dumps(messages, ensure_ascii=False, indent=1), encoding="utf-8")


def ask(prompt: str, system: str, session_id: str | None, model: str, api_key: str) -> Reply:
    """Send one check, continuing the stored conversation when there is one."""
    if not api_key:
        raise OpenAIError("no OpenAI API key: add it in AirFare Settings")
    history = load_session(session_id) if session_id else None
    if session_id and history is None:
        log.warning("OpenAI conversation %s is gone; starting a new one", session_id)
    sid = session_id if history is not None else uuid.uuid4().hex
    history = history or []
    user = {"role": "user", "content": prompt}
    text, usage = respond([*history, user], system, model, api_key)
    _save_session(sid, [*history, user, {"role": "assistant", "content": text}])
    reasoning = int((usage.get("output_tokens_details") or {}).get("reasoning_tokens") or 0)
    context = int(usage.get("input_tokens") or 0) + int(usage.get("output_tokens") or 0) - reasoning
    log.info("OpenAI %s: %s input tokens (%s cached), %s out", model, usage.get("input_tokens"),
             (usage.get("input_tokens_details") or {}).get("cached_tokens"), usage.get("output_tokens"))
    return Reply(text, sid, context, estimate_cost(usage, model))


def check_key(api_key: str) -> dict:
    """Whether OpenAI accepts the key (listing models costs nothing)."""
    data = _request("/models", api_key, timeout=20)
    return {"ok": True, "models": len(data.get("data") or [])}
