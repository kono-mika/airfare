import asyncio
import json
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from airfare import analyst, chatgpt, openai_api, platform, research

EVENTS = "\n".join(json.dumps(e) for e in (
    {"type": "thread.started", "thread_id": "01a1-thread"},
    {"type": "turn.started"},
    {"type": "item.completed", "item": {"id": "item_1", "type": "agent_message", "text": "## Analysis\nok"}},
    {"type": "turn.completed", "usage": {"input_tokens": 9000, "cached_input_tokens": 8000, "output_tokens": 700}},
))


def test_codex_events_are_read_in_old_and_new_shapes():
    ev = chatgpt.parse_events("noise\n" + EVENTS + '\n{"type":"item.completed","item":{"item_type":"assistant_message","text":"old"}}')
    assert ev["thread_id"] == "01a1-thread" and ev["messages"] == ["## Analysis\nok", "old"]
    assert ev["usage"]["output_tokens"] == 700
    failed = chatgpt.parse_events('{"type":"error","message":"Reconnecting... 1/5"}\n{"type":"turn.failed","error":{"message":"quota"}}')
    assert failed["errors"] == ["quota"]


def test_codex_runs_read_only_and_continues_the_thread(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(chatgpt, "codex_path", lambda: "codex.exe")
    monkeypatch.setattr(chatgpt, "WORK_DIR", tmp_path / "work")

    def fake_call(cmd, prompt):
        calls.append((cmd, prompt, chatgpt.WORK_DIR))
        Path(cmd[cmd.index("-o") + 1]).write_text("final answer", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, EVENTS, "")
    monkeypatch.setattr(chatgpt, "_call", fake_call)
    first = chatgpt.ask("prices", "RULES", None)
    assert first.text == "final answer" and first.session_id == "01a1-thread" and first.context_tokens == 9700
    cmd, prompt, cwd = calls[0]
    assert cmd[1] == "exec" and "resume" not in cmd and "sandbox_mode=read-only" in cmd and "approval_policy=never" in cmd
    assert "web_search=disabled" in cmd and cmd[-1] == "-" and prompt.startswith("RULES") and cwd == tmp_path / "work"
    chatgpt.ask("more prices", "RULES", "01a1-thread")
    cmd, prompt, _ = calls[1]
    assert cmd[1:4] == ["exec", "resume", "01a1-thread"] and prompt == "more prices"   # the rules are already in it


def test_codex_problems_are_reported_plainly(monkeypatch, tmp_path):
    monkeypatch.setattr(chatgpt, "WORK_DIR", tmp_path)
    monkeypatch.setattr(chatgpt, "codex_path", lambda: None)
    with pytest.raises(chatgpt.ChatGPTError, match="isn't installed"):
        chatgpt.run("x")
    monkeypatch.setattr(chatgpt, "codex_path", lambda: "codex.exe")
    out = '{"type":"turn.failed","error":{"message":"unexpected status 401 Unauthorized"}}'
    monkeypatch.setattr(chatgpt, "_call", lambda cmd, prompt: subprocess.CompletedProcess(cmd, 1, out, ""))
    with pytest.raises(chatgpt.ChatGPTError, match="isn't signed in"):
        chatgpt.run("x")


def test_openai_api_keeps_the_conversation_locally(monkeypatch, tmp_path):
    monkeypatch.setattr(openai_api, "SESSIONS_DIR", tmp_path)
    sent = []

    def fake_request(path, key, body=None, timeout=600):
        sent.append(body)
        return {"output": [{"type": "reasoning"}, {"type": "message", "content": [{"type": "output_text", "text": "answer"}]}],
                "usage": {"input_tokens": 10000, "input_tokens_details": {"cached_tokens": 8000}, "output_tokens": 1000,
                          "output_tokens_details": {"reasoning_tokens": 400}}}
    monkeypatch.setattr(openai_api, "_request", fake_request)
    first = openai_api.ask("check 1", "RULES", None, "gpt-6.1-terra", "sk-test")
    second = openai_api.ask("check 2", "RULES", first.session_id, "gpt-6.1-terra", "sk-test")
    assert first.text == "answer" and second.session_id == first.session_id
    assert sent[1]["instructions"] == "RULES" and sent[1]["store"] is False
    assert [m["role"] for m in sent[1]["input"]] == ["user", "assistant", "user"]
    assert first.cost_usd == round((8000 * 0.05 + 2000 * 1.0 + 1000 * 5.0) / 1e6, 6) and first.context_tokens == 10600


def test_the_analyst_runs_through_either_chatgpt(monkeypatch):
    state = {}
    monkeypatch.setattr(analyst, "load_state", lambda: json.loads(json.dumps(state)))
    monkeypatch.setattr(analyst, "save_state", lambda s: (state.clear(), state.update(s)))
    monkeypatch.setattr(chatgpt, "ask", lambda p, s, sid, m=None: chatgpt.Reply("ok\n<!--airfare {\"take\": \"t\"}-->", "th-1", 100))
    monkeypatch.setattr(openai_api, "ask", lambda p, s, sid, m, k: openai_api.Reply("ok", "oa-1", 50, 0.01))
    v = asyncio.run(analyst.analyse("doc", "prev", datetime(2026, 10, 27), None, provider="chatgpt"))
    assert v.session_id == "th-1" and v.summary["take"] == "t" and state["chatgpt"]["rules_id"] == chatgpt.rules_id(analyst.RULES)
    v = asyncio.run(analyst.analyse("doc", "prev", datetime(2026, 10, 27), "gpt-6-luna", provider="openai", api_key="k"))
    assert v.session_id == "oa-1" and state["openai"]["session_cost_usd"] == 0.01 and state["chatgpt"]["session_id"] == "th-1"


def test_lookups_can_use_chatgpt(monkeypatch):
    cfg = {"llm_provider": "openai", "openai_model": "gpt-6.1-sol", "openai_api_key": "sk-test-0001"}
    assert research.resolve_analyst(cfg, "openai") == ("openai", "gpt-6.1-sol", True, "ChatGPT GPT-6.1 Sol")
    with pytest.raises(research.Problem):
        research.resolve_analyst({**cfg, "openai_api_key": ""}, "openai")
    monkeypatch.setattr(chatgpt, "codex_path", lambda: None)
    with pytest.raises(research.Problem, match="Codex"):
        research.resolve_analyst(cfg, "chatgpt")


def test_a_codex_threads_size_is_its_latest_turn(monkeypatch):
    state = {}
    monkeypatch.setattr(analyst, "load_state", lambda: json.loads(json.dumps(state)))
    monkeypatch.setattr(analyst, "save_state", lambda s: (state.clear(), state.update(s)))
    totals = iter([1050, 3100, 6150])                       # Codex's running totals over three turns
    monkeypatch.setattr(chatgpt, "ask", lambda p, s, sid, m=None: chatgpt.Reply("ok", "th-1", next(totals)))
    for _ in range(3):
        asyncio.run(analyst.analyse("doc", "prev", datetime(2026, 10, 27), None, provider="chatgpt"))
    assert state["chatgpt"]["context_tokens"] == 3050 and state["chatgpt"]["session_checks"] == 3


@pytest.mark.skipif(not platform.WINDOWS, reason="taskkill is Windows'; see the next test")
def test_a_codex_that_hangs_is_ended_with_its_children(monkeypatch, tmp_path):
    monkeypatch.setattr(chatgpt, "WORK_DIR", tmp_path)
    monkeypatch.setattr(chatgpt, "TIMEOUT", 1)
    killed = []
    real_run = subprocess.run
    monkeypatch.setattr(chatgpt.subprocess, "run", lambda cmd, **kw: killed.append(cmd) or real_run(cmd, **kw))
    import sys
    with pytest.raises(subprocess.TimeoutExpired):
        chatgpt._call([sys.executable, "-c", "import time; time.sleep(30)"], "")
    assert killed and killed[0][:3] == ["taskkill", "/T", "/F"]


@pytest.mark.skipif(platform.WINDOWS, reason="Windows ends the tree with taskkill (above)")
def test_a_codex_that_hangs_is_ended_with_its_children_on_mac_and_linux(monkeypatch, tmp_path):
    import os
    import sys
    import time
    monkeypatch.setattr(chatgpt, "WORK_DIR", tmp_path)
    monkeypatch.setattr(chatgpt, "TIMEOUT", 3)               # time for the child to start and write its pid
    child = tmp_path / "child.pid"
    script = ("import subprocess, sys, time; p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
              f"open({str(child)!r}, 'w').write(str(p.pid)); time.sleep(60)")
    started = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        chatgpt._call([sys.executable, "-c", script], "")
    assert time.monotonic() - started < 30               # the child held the output pipes too: it was ended
    pid = int(child.read_text())
    for _ in range(50):                                  # gone once the system has collected it
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    else:
        pytest.fail("the Codex child process is still running")
