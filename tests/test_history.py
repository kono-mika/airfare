import asyncio
import io
from datetime import datetime

import pytest

from airfare import config, historypage, pricelog, research
from test_dashboard import pages


@pytest.fixture
def store(monkeypatch, tmp_path):
    monkeypatch.setattr(pricelog, "LOG_FILE", tmp_path / "price_history.json")
    monkeypatch.setattr(pricelog, "RESEARCH_FILE", tmp_path / "price_research.json")


def test_check_records_and_deleting(store):
    recs = pricelog.records_from_check(pages(), datetime(2026, 10, 27, 9, 0))
    assert {r["source"] for r in recs} == {"Skyscanner", "Google Flights"}
    sky = next(r for r in recs if r["source"] == "Skyscanner")
    assert sky["price"] == 154.97 and sky["depart"] == "2026-12-18" and sky["return"] == "2026-12-27"
    assert sky["origin"] == "VNO" and sky["url"] == "https://example.test/s"
    pricelog.add(recs)
    pricelog.add(pricelog.records_from_check(pages(), datetime(2026, 10, 28, 9, 0)))
    assert len(pricelog.load()) == 4
    assert pricelog.delete(ids=[recs[0]["id"]]) == 1 and len(pricelog.load()) == 3
    assert pricelog.delete(route_id="r") == 3 and pricelog.load() == []


def test_matching_conditions():
    rec = {"route_id": "r", "source": "Skyscanner", "depart": "2027-03-12", "return": "2027-03-18"}
    assert pricelog.matches(rec, "r", "2027-03-12", "2027-03-12", "2027-03-15", "2027-03-18")
    assert not pricelog.matches(rec, "r", return_to="2027-03-17")
    assert not pricelog.matches(rec, "r", depart_from="2027-03-13")
    assert not pricelog.matches(rec, source="Google Flights")


COND = research.Conditions("r", "London ⇄ Barcelona", ["LHR"], ["BCN"], "2027-03-12", "2027-03-12",
                           "2027-03-15", "2027-03-18", today="2026-10-27")
GOOD = {"status": "found", "lowest_price": 149, "currency": "EUR", "origin": "LHR", "destination": "BCN",
        "depart_date": "2027-03-12", "return_date": "2027-03-16", "observed_on": "2026-09-01",
        "source_url": "https://deals.example.test/lhr-bcn", "source_name": "Deals", "notes": "",
        "quote": "London to Barcelona return from €149"}


@pytest.mark.parametrize("change, reason", [
    ({}, None),
    ({"status": "no_information"}, "no price"),
    ({"destination": "AMS"}, "different route"),
    ({"depart_date": "2027-03-13"}, "departure date is outside"),
    ({"return_date": "2027-03-20"}, "return date is outside"),
    ({"observed_on": "2024-01-01"}, "past two years"),
    ({"observed_on": "2026-11-15"}, "past two years"),            # can't be recorded in the future
    ({"quote": ""}, "cite a source"),
    ({"lowest_price": None}, "usable price"),
])
def test_answers_are_checked_against_the_request(change, reason):
    got = research.check_answer({**GOOD, **change}, COND)
    assert got is None if reason is None else reason in got


def test_source_must_show_the_quoted_price(monkeypatch):
    page = "<html><body><p>London to Barcelona   return from &euro;149</p></body></html>"
    monkeypatch.setattr(research, "_open", lambda req, timeout=0: _Resp(page))
    monkeypatch.setattr(research, "public_url", lambda url: True)
    assert research.verify_source(GOOD["source_url"], GOOD["quote"], 149) is None
    assert "couldn't find" in research.verify_source(GOOD["source_url"], "London to Barcelona return from €129", 129)
    assert "doesn't contain the price" in research.verify_source(GOOD["source_url"], GOOD["quote"], 139)


def test_sources_on_this_pc_or_the_local_network_are_never_opened(monkeypatch):
    opened = []
    monkeypatch.setattr(research, "_open", lambda req, timeout=0: opened.append(req.full_url))
    for url in ("http://127.0.0.1:8765/api/state", "http://localhost:8765/", "http://192.168.1.1/",
                "http://[::1]/", "file:///C:/Windows/win.ini", "ftp://example.com/x"):
        assert "public internet" in research.verify_source(url, GOOD["quote"], 149)
    assert opened == []


class _Resp(io.BytesIO):
    def __init__(self, text):
        super().__init__(text.encode("utf-8"))
        self.headers = type("H", (), {"get_content_charset": lambda self: "utf-8"})()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_lookup_keeps_only_verified_answers(store, monkeypatch):
    async def honest(prompt, model, web=True, api_key=None):
        return GOOD, 0.12

    async def invented(prompt, model, web=True, api_key=None):
        return {**GOOD, "source_url": None, "quote": None}, 0.05

    monkeypatch.setattr(research, "verify_source", lambda url, quote, price: None)
    monkeypatch.setattr(research, "_ask_claude", honest)
    found = asyncio.run(research.lookup(COND, {"llm_provider": "claude", "model": "claude-sonnet-5-5"}))
    assert found["status"] == "found" and found["lowest_price"] == 149 and found["cost_usd"] == 0.12

    monkeypatch.setattr(research, "_ask_claude", invented)
    rejected = asyncio.run(research.lookup(COND, {"llm_provider": "claude"}))
    assert rejected["status"] == "no_information" and "lowest_price" not in rejected
    assert len(pricelog.load_research()) == 2
    assert pricelog.delete_research(ids=[rejected["id"]]) == 1


def test_lookup_uses_the_picked_analyst_model_and_mode(store, monkeypatch):
    calls = []

    async def fake_claude(prompt, model, web=True, api_key=None):
        calls.append(("claude", model, web, "cannot browse" in prompt))
        return None, 0.01

    def fake_deepseek(prompt, model, key):
        calls.append(("deepseek", model, key, "cannot browse" in prompt))
        return None, 0.0001

    monkeypatch.setattr(research, "_ask_claude", fake_claude)
    monkeypatch.setattr(research, "_ask_deepseek", fake_deepseek)
    cfg = {"llm_provider": "claude", "model": "claude-sonnet-5-5", "deepseek_api_key": "k"}
    a = asyncio.run(research.lookup(COND, cfg))                                       # defaults: Settings' analyst
    b = asyncio.run(research.lookup(COND, cfg, "claude", "claude-opus-5-5", web=False))
    c = asyncio.run(research.lookup(COND, cfg, "deepseek", "deepseek-v4-pro"))
    assert calls == [("claude", "claude-sonnet-5-5", True, False), ("claude", "claude-opus-5-5", False, True),
                     ("deepseek", "deepseek-v4-pro", "k", True)]
    assert a["analyst"] == "Claude Sonnet 5.5" and a["web_search"] is True
    assert b["analyst"] == "Claude Opus 5.5 (no web search)" and b["web_search"] is False
    assert c["analyst"] == "DeepSeek deepseek-v4-pro" and c["web_search"] is False


def test_unusable_picks_are_refused():
    with pytest.raises(ValueError, match="DeepSeek API key"):
        research.resolve_analyst({"llm_provider": "claude"}, "deepseek")
    with pytest.raises(ValueError, match="Claude model"):
        research.resolve_analyst({}, "claude", "gpt-5")
    with pytest.raises(ValueError, match="DeepSeek model"):
        research.resolve_analyst({"deepseek_api_key": "k"}, "deepseek", "deepseek-r9")
    assert research.resolve_analyst({"model": ""}, "claude", "") == ("claude", None, True, "Claude account default")


def test_history_page_offers_analysts_and_models(store):
    cfg = {**config.DEFAULT_CONFIG, "llm_provider": "deepseek", "deepseek_model": "deepseek-flash", "deepseek_api_key": ""}
    opts = historypage.lookup_options(cfg)
    claude, gpt, gpt_api, ds = opts["providers"]
    assert claude["can_browse"] and ["claude-opus-5-5", "Opus 5.5"] in claude["models"]
    assert gpt["id"] == "chatgpt" and gpt["can_browse"] and gpt_api["id"] == "openai" and not gpt_api["available"]
    assert ["gpt-6.1-terra", "GPT-6.1 Terra"] in gpt_api["models"]
    assert not ds["can_browse"] and not ds["available"] and ["deepseek-flash", "V4.1 Flash"] in ds["models"]
    assert opts["default"] == {"provider": "deepseek", "model": "deepseek-flash"}


def test_prompt_is_strict_about_route_dates_and_window():
    p = research.build_prompt(COND, can_browse=True)
    assert "LHR → BCN" in p and "departing between 2027-03-12 and 2027-03-12" in p
    assert "returning between 2027-03-15 and 2027-03-18" in p and "between 2024-10-27 and 2026-10-27" in p
    assert "Never estimate" in p and "similar destinations" in p and "no_information" in p
    assert "cannot browse" in research.build_prompt(COND, can_browse=False)


def test_conditions_from_route_expand_city_codes(store):
    cfg = {"routes": [{"id": "x", "origin": "vno", "destination": "lond", "trip": "return",
                       "depart_from": "2026-12-18", "depart_to": "2026-12-19", "return_from": "2026-12-27"}]}
    c = research.conditions_for(cfg, "x")
    assert c.origins == ["VNO"] and "STN" in c.destinations and "LON" in c.destinations
    assert (c.depart_from, c.depart_to, c.return_from, c.return_to) == ("2026-12-18", "2026-12-19", "2026-12-27", "2026-12-27")
    with pytest.raises(ValueError, match="after"):
        research.conditions_for(cfg, "x", depart_from="2026-12-20", depart_to="2026-12-18")


def test_history_page_embeds_data_safely(store):
    pricelog.add([{"id": "1", "time": "2026-10-27T09:00", "route_id": "r", "route_name": "</script><b>x",
                   "source": "Skyscanner", "price": 1, "price_text": "1 €", "depart": "2027-03-12"}])
    page = historypage.build({**config.DEFAULT_CONFIG, "routes": []}, served=False)
    assert "</script><b>" not in page and "\\u003c/script>\\u003cb>x" in page
    assert '"served": false' in page
