import asyncio
import json
from datetime import datetime

import pytest

from airfare import analyst, config, deepseek, webui


@pytest.fixture
def api(monkeypatch, tmp_path):
    """Fake DeepSeek: records request bodies and answers with reasoning plus a final answer."""
    monkeypatch.setattr(deepseek, "SESSIONS_DIR", tmp_path / "deepseek")
    sent = []

    def fake_request(path, api_key, body=None, timeout=600):
        sent.append(body)
        n = len(sent)
        return {"choices": [{"message": {"content": f"## answer {n}\n<!--airfare {{\"low_price\": false, \"take\": \"t{n}\"}}-->",
                                         "reasoning_content": "secret chain of thought"}}],
                "usage": {"prompt_tokens": 10_000 * n, "completion_tokens": 3_000, "prompt_cache_hit_tokens": 6_000,
                          "prompt_cache_miss_tokens": 10_000 * n - 6_000,
                          "completion_tokens_details": {"reasoning_tokens": 2_000}}}

    monkeypatch.setattr(deepseek, "_request", fake_request)
    return sent


def test_new_then_resumed_conversation(api):
    first = deepseek.ask("check 1", "RULES", None, "deepseek-flash", "key")
    assert [m["role"] for m in api[0]["messages"]] == ["system", "user"]
    assert api[0]["thinking"] == {"type": "enabled"} and api[0]["model"] == "deepseek-flash"
    assert first.context_tokens == 10_000 + 3_000 - 2_000          # reasoning isn't kept in the conversation
    assert first.cost_usd == round((6_000 * 0.0028 + 4_000 * 0.14 + 3_000 * 0.28) / 1e6, 6)

    second = deepseek.ask("check 2", "RULES", first.session_id, "deepseek-flash", "key")
    assert second.session_id == first.session_id
    assert [m["role"] for m in api[1]["messages"]] == ["system", "user", "assistant", "user"]
    stored = deepseek.load_session(first.session_id)
    assert len(stored) == 4 and "secret chain of thought" not in json.dumps(stored)


def test_lost_conversation_starts_a_new_one(api):
    reply = deepseek.ask("check", "RULES", "gone", "deepseek-flash", "key")
    assert reply.session_id != "gone" and [m["role"] for m in api[0]["messages"]] == ["system", "user"]


def test_missing_key_is_explained():
    with pytest.raises(deepseek.DeepSeekError, match="API key"):
        deepseek.ask("check", "RULES", None, "deepseek-flash", "")


def test_analyse_keeps_deepseek_bookkeeping_apart_from_claude(api, monkeypatch):
    state = {"session_id": "claude-1", "session_model": "claude-sonnet-5-5", "context_tokens": 12_000}
    monkeypatch.setattr(analyst, "load_state", lambda: json.loads(json.dumps(state)))
    monkeypatch.setattr(analyst, "save_state", lambda s: (state.clear(), state.update(s)))
    v1 = asyncio.run(analyst.analyse("doc", "prev", datetime(2026, 10, 27), "deepseek-flash",
                                     provider="deepseek", api_key="key"))
    v2 = asyncio.run(analyst.analyse("doc", "prev", datetime(2026, 10, 27), "deepseek-flash",
                                     provider="deepseek", api_key="key"))
    assert v1.summary["take"] == "t1" and not v1.resumed and v2.resumed
    assert state["session_id"] == "claude-1"                     # Claude's session is untouched
    ds = state["deepseek"]
    assert ds["session_id"] == v1.session_id and ds["session_checks"] == 2
    assert ds["session_model"] == "deepseek-flash" and state["analyst"] == "deepseek"
    assert ds["session_cost_usd"] == round(v1.cost_usd + v2.cost_usd, 6)


def test_settings_need_a_key_for_deepseek(monkeypatch):
    monkeypatch.setattr(webui, "load_config", lambda: dict(config.DEFAULT_CONFIG))
    base = {"sources": ["serpapi"], "routes": [], "llm_provider": "deepseek"}
    with pytest.raises(ValueError, match="DeepSeek API key"):
        webui.clean_config(base)
    cfg = webui.clean_config({**base, "deepseek_api_key": " sk-test-0001 ", "deepseek_model": "deepseek-v4-pro"})
    assert cfg["llm_provider"] == "deepseek" and cfg["deepseek_api_key"] == "sk-test-0001"
    assert cfg["deepseek_model"] == "deepseek-v4-pro"
    with pytest.raises(ValueError, match="DeepSeek model"):
        webui.clean_config({**base, "deepseek_api_key": "sk-test-0001", "deepseek_model": "gpt-5"})
