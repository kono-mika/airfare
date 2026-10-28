"""When AirFare resumes the Claude session and when it starts a fresh one."""
import asyncio
from datetime import datetime
from types import SimpleNamespace

from airfare import analyst

PROMPT = "x" * 30_000          # ~10k tokens at the 3-characters-per-token estimate


def test_reason_to_start_fresh():
    base = {"session_id": "s1", "session_model": "claude-sonnet-5-5", "context_tokens": 20_000}
    assert analyst.fresh_session_reason(base, PROMPT, "claude-sonnet-5-5", 40_000) is None
    assert "20k" in analyst.fresh_session_reason({**base, "context_tokens": 31_000}, PROMPT, "claude-sonnet-5-5", 40_000) \
        or "31k" in analyst.fresh_session_reason({**base, "context_tokens": 31_000}, PROMPT, "claude-sonnet-5-5", 40_000)
    assert "model" in analyst.fresh_session_reason(base, PROMPT, "claude-haiku-5-5", 40_000)
    assert analyst.fresh_session_reason({}, PROMPT, "claude-sonnet-5-5", 40_000) is None   # nothing to resume
    legacy = {"session_id": "s0"}                       # recorded before AirFare stored the model: account default
    assert "model" in analyst.fresh_session_reason(legacy, PROMPT, "claude-sonnet-5-5", 40_000)
    assert analyst.fresh_session_reason(legacy, PROMPT, "", 40_000) is None


def test_context_tokens_adds_every_part():
    usage = {"input_tokens": 2, "cache_creation_input_tokens": 9_000, "cache_read_input_tokens": 3_000, "output_tokens": 900}
    assert analyst.context_tokens(usage) == 12_902
    assert analyst.context_tokens(None) == 0


def run_checks(monkeypatch, sizes, model="claude-sonnet-5-5", max_tokens=40_000, start=None):
    """Run one analyse() per entry in sizes (the context size the fake reply reports)."""
    state = dict(start or {})
    monkeypatch.setattr(analyst, "load_state", lambda: dict(state))
    monkeypatch.setattr(analyst, "save_state", lambda s: (state.clear(), state.update(s)))
    monkeypatch.setattr(analyst.claude_agent_sdk, "rename_session", lambda *a, **k: None)
    calls, counter = [], {"n": 0}

    async def fake_ask(prompt, sid, model_, api_key=None):
        calls.append(sid)
        if sid is None:
            counter["n"] += 1
        result = SimpleNamespace(session_id=sid or f"s{counter['n']}", total_cost_usd=0.01,
                                 usage={"input_tokens": sizes[len(calls) - 1]})
        return "## ok", result

    monkeypatch.setattr(analyst, "_ask", fake_ask)
    for _ in sizes:
        asyncio.run(analyst.analyse("doc", "prev", datetime(2026, 10, 26), model, max_tokens=max_tokens))
    return calls, state


def test_session_is_resumed_until_it_gets_large(monkeypatch):
    # build_prompt adds ~100 characters, so each check here adds ~30 tokens on top of the reported size
    calls, state = run_checks(monkeypatch, [11_000, 22_000, 33_000, 44_000, 11_000], max_tokens=40_000)
    assert calls == [None, "s1", "s1", "s1", None]     # the 5th check starts fresh: 44k is past the limit
    assert state["session_id"] == "s2" and state["session_checks"] == 1
    assert state["previous_sessions"][-1] == {"id": "s1", "started": "2026-10-26T00:00", "checks": 4}


def test_cost_is_per_check_not_the_running_total(monkeypatch):
    state = {}
    monkeypatch.setattr(analyst, "load_state", lambda: dict(state))
    monkeypatch.setattr(analyst, "save_state", lambda s: (state.clear(), state.update(s)))
    monkeypatch.setattr(analyst.claude_agent_sdk, "rename_session", lambda *a, **k: None)
    totals = iter([0.068, 0.131])                       # what the CLI reports: the session's running total

    async def fake_ask(prompt, sid, model_, api_key=None):
        return "## ok", SimpleNamespace(session_id="s1", total_cost_usd=next(totals), usage={"input_tokens": 1000})

    monkeypatch.setattr(analyst, "_ask", fake_ask)
    costs = [asyncio.run(analyst.analyse("doc", "prev", datetime(2026, 10, 26), "claude-sonnet-5-5")).cost_usd
             for _ in range(2)]
    assert costs == [0.068, 0.063]


def test_model_change_starts_fresh(monkeypatch):
    opus_session = {"session_id": "old", "session_model": "", "context_tokens": 5_000, "session_checks": 2}
    calls, state = run_checks(monkeypatch, [5_000, 6_000], model="claude-sonnet-5-5", start=opus_session)
    assert calls == [None, "s1"]                        # fresh once for the new model, then resumed
    assert state["session_model"] == "claude-sonnet-5-5"
    assert state["previous_sessions"][-1]["id"] == "old"
