"""The 1.4 additions: no analyst, Claude by API key, every ECB currency, children, Edge and Brave, update checks,
the tray icon and the CSV export."""
import asyncio
import base64
import hashlib
from datetime import date, datetime

import pytest

from airfare import analyst, config, dashboard, extension, historypage, markup, money, report, research, runner, \
    serpapi, service, tray, update, urls, webui
from test_dashboard import WHEN, pages

ROUTE = {"id": "r1", "origin": "lhr", "destination": "bcn", "trip": "return",
         "depart_from": "2027-03-12", "return_from": "2027-03-15"}


# ----- no analyst ----------------------------------------------------------------------------

def test_no_analyst_is_a_choice_with_no_conversation():
    assert runner.analyst_choice({"llm_provider": "none"}) == ("none", None, "")
    assert runner.analyst_key({"llm_provider": "none", "anthropic_api_key": "k"}, "none") is None
    with pytest.raises(analyst.ClaudeError):
        asyncio.run(analyst.analyse("doc", "prev", datetime(2026, 10, 26), provider="none"))


def test_dashboard_without_an_analyst_says_so_and_shows_no_analysis():
    parts = dashboard.check_parts(pages(), {"runs": []}, {}, {}, datetime(2026, 10, 26, 16, 0), "", False,
                                  {"take": "ignored without an analyst"}, {}, "x.md", analyst_name="", lang="en")
    assert "<details" not in parts["analysis"] and "No analyst is set up" in parts["analysis"]
    assert parts["take"] == ""
    with_claude = dashboard.check_parts(pages(), {"runs": []}, {}, {}, datetime(2026, 10, 26, 16, 0), "", False, {},
                                        {}, "x.md", analyst_name="Claude", lang="en")
    assert "<details" in with_claude["analysis"]


def test_settings_accept_no_analyst_and_check_the_claude_key_mode(monkeypatch):
    monkeypatch.setattr(webui, "load_config", lambda: dict(config.DEFAULT_CONFIG))
    cfg = webui.clean_config({"sources": ["extension"], "llm_provider": "none", "routes": [ROUTE]})
    assert cfg["llm_provider"] == "none"
    with pytest.raises(webui.Problem, match="Anthropic API key"):
        webui.clean_config({"sources": ["extension"], "llm_provider": "claude", "claude_mode": "key", "routes": [ROUTE]})
    cfg = webui.clean_config({"sources": ["extension"], "llm_provider": "claude", "claude_mode": "key",
                              "anthropic_api_key": "sk-ant-abcdefghij", "routes": [ROUTE]})
    assert cfg["claude_mode"] == "key" and cfg["anthropic_api_key"] == "sk-ant-abcdefghij"
    assert analyst.claude_key(cfg) == "sk-ant-abcdefghij"
    assert analyst.claude_key({**cfg, "claude_mode": "account"}) is None
    assert analyst.claude_env("sk-ant-x")["ANTHROPIC_API_KEY"] == "sk-ant-x" and "ANTHROPIC_API_KEY" not in analyst.claude_env(None)
    assert webui.public_config(cfg)["anthropic_api_key"] == "" and webui.public_config(cfg)["saved_keys"]["anthropic_api_key"] == "…ghij"


def test_lookups_need_the_key_when_claude_runs_on_one():
    with pytest.raises(webui.Problem):
        research.resolve_analyst({"llm_provider": "claude", "claude_mode": "key"}, "claude")
    assert research.resolve_analyst({"llm_provider": "claude", "claude_mode": "key", "anthropic_api_key": "k"}, "claude")[0] == "claude"
    opts = historypage.lookup_options({"llm_provider": "claude", "claude_mode": "key"})
    assert opts["providers"][0]["available"] is False


# ----- currencies ------------------------------------------------------------------------------

def test_every_ecb_currency_formats_and_the_rate_line_stays_short():
    assert money.fmt(1234, "CZK") == "1 234 Kč" and money.fmt(1234.4, "PLN") == "1 234 zł"
    assert money.fmt(1234, "JPY") == "¥1,234" and money.fmt(15400, "RUB") == "15 400 ₽"
    assert money.fmt(99.6, "EUR") == "€100" and money.fmt(5, "XXX") == "5 XXX"
    assert len(money.CURRENCIES) >= 30 and all(len(c) == 3 for c in money.CURRENCIES)
    table = {"rates": {c: 2.0 for c in money.CURRENCIES} | {"EUR": 1.0}}
    line = money.rate_line("PLN", table, ("CZK",))
    assert line.startswith("1 PLN") and "CZK" in line and line.count("=") <= 6
    assert money.detect("1 234 Kč") == "CZK" and money.detect("₪350") == "ILS"


def test_history_page_knows_the_currency_sign(monkeypatch):
    monkeypatch.setattr(historypage.pricelog, "load", lambda: [])
    monkeypatch.setattr(historypage.pricelog, "load_research", lambda: [])
    monkeypatch.setattr(historypage.money, "rates", lambda refresh=True: {"rates": {"EUR": 1.0}})
    data = historypage.page_data({**config.DEFAULT_CONFIG, "currency": "CZK"})
    assert data["sign"] == "Kč" and data["sign_after"] is True
    assert historypage.page_data({**config.DEFAULT_CONFIG, "currency": "GBP"})["sign_after"] is False


def test_history_page_and_price_document_credit_exchangerate_api_only_for_its_rates(monkeypatch):
    both = {"rates": {"EUR": 1.0, "GBP": 0.8, "USD": 1.1, "RUB": 100.0}, "date": "2026-10-26",
            "source": "European Central Bank and open.er-api.com"}
    ecb = {**both, "source": "European Central Bank"}
    monkeypatch.setattr(historypage.money, "rates", lambda refresh=True: both)
    credited = historypage.build(dict(config.DEFAULT_CONFIG), served=True)
    monkeypatch.setattr(historypage.money, "rates", lambda refresh=True: ecb)
    plain = historypage.build(dict(config.DEFAULT_CONFIG), served=True)
    assert money.CREDIT_HTML in credited.split("</section>")[-1] and "exchangerate-api" not in plain
    # The link is plain HTML outside the scripts: every script still matches a hash in the content policy,
    # and its address is one the analyst-text link rules would keep too.
    policy = webui.content_policy()
    for script in webui.SCRIPT_RE.findall(credited):
        assert base64.b64encode(hashlib.sha256(script.encode("utf-8")).digest()).decode() in policy
    assert money.CREDIT_HTML.split('"')[1].startswith(markup.SAFE_SCHEMES)
    data = pages("EUR")
    assert money.CREDIT_MD in report.build_document(data, WHEN, 0, "EUR", both)
    assert "exchangerate-api" not in report.build_document(data, WHEN, 0, "EUR", ecb)


# ----- children --------------------------------------------------------------------------------

def test_children_ages_are_checked_and_counted_per_site():
    assert urls.clean_ages("4, 9") == [4, 9] and urls.clean_ages([9, 4]) == [4, 9] and urls.clean_ages("") == []
    assert urls.clean_ages("x") is None and urls.clean_ages("16") is None and urls.clean_ages("1,2,3,4,5,6,7,8,9") is None
    assert urls.passengers(2, [1, 5, 13]) == (3, 1, 1)       # 13 flies as an adult, 1 as an infant
    assert urls.passengers(1, []) == (1, 0, 0)


def test_children_reach_every_price_source():
    url = urls.build_url("www.skyscanner.net", "lhr", "bcn", date(2027, 3, 12), None, adults=2, children=[4, 9])
    assert "childrenv2=4%7C9" in url and "adultsv2=2" in url
    assert urls.parse_url(url)["children"] == [4, 9]
    assert "childrenv2" not in urls.parse_url(urls.build_url("www.skyscanner.net", "lhr", "bcn", date(2027, 3, 12)))
    page = {"origin": "bcn", "destination": "lon", "depart": "2027-03-15", "return": "2027-03-18", "adults": 2,
            "children": [1, 5], "cabin": "economy"}
    assert urls.aviasales_url(page, date(2027, 1, 1)).endswith("/search/BCN1503LON1803211")
    assert urls.aviasales_url({**page, "children": []}, date(2027, 1, 1)).endswith("/search/BCN1503LON18032")
    p = serpapi.params({**page, "depart": "2027-03-15"}, "key", "EUR")
    assert (p["adults"], p["children"], p["infants_on_lap"]) == (2, 1, 1)
    assert "children" not in serpapi.params({**page, "children": []}, "key", "EUR")


def test_route_pages_carry_the_children_and_a_pasted_link_wins():
    route = {**ROUTE, "children": [6], "manual_pages": [
        {"key": None, "url": "https://www.skyscanner.net/transport/flights/lhr/bcn/270320/?adultsv2=1&childrenv2=2%7C3"}]}
    planned, _ = urls.plan_pages({"domain": "www.skyscanner.net", "routes": [route], "max_pages": 20}, date(2027, 1, 1))
    by_source = {p["source"]: p for p in planned}
    assert by_source["auto"]["children"] == [6] and by_source["manual"]["children"] == [2, 3]


def test_children_change_a_routes_identity_and_bad_ages_are_a_route_problem(monkeypatch):
    monkeypatch.setattr(webui, "load_config", lambda: {**config.DEFAULT_CONFIG, "routes": [dict(ROUTE)]})
    cfg = webui.clean_config({"sources": ["extension"], "routes": [{**ROUTE, "children": "4, 9"}]}, renew_ids=True)
    assert cfg["routes"][0]["children"] == [4, 9] and cfg["routes"][0]["id"] != "r1"     # a new search: new id
    same = webui.clean_config({"sources": ["extension"], "routes": [{**ROUTE, "children": ""}]}, renew_ids=True)
    assert same["routes"][0]["id"] == "r1"
    problems = {}
    webui.clean_config({"sources": ["extension"], "routes": [{**ROUTE, "children": "4, grown-up"}]}, problems)
    assert "ages" in problems["r1"]


# ----- Edge and Brave ---------------------------------------------------------------------------

def test_the_extension_can_run_in_edge_or_brave(monkeypatch):
    assert extension.browser_kind("edge") == "edge" and extension.browser_kind("safari") == "chrome"
    assert set(extension.installed_browsers()) == {"chrome", "edge", "brave", "opera", "firefox"}
    assert extension.BROWSERS["edge"]["page"] == "edge://extensions"
    seen = {}
    monkeypatch.setattr(extension, "chrome_running", lambda kind="chrome": seen.setdefault("kind", kind) and True)
    monkeypatch.setattr(extension, "_JobServer", lambda *a, **k: (_ for _ in ()).throw(OSError("busy")))
    extension.collect([{"url": "https://www.skyscanner.net/transport/flights/lhr/bcn/270312/", "site": "Skyscanner"}],
                      browser="brave")
    assert seen == {}       # the port was busy before the browser was looked at: nothing started
    with pytest.raises(webui.Problem):
        webui.clean_config({"sources": ["extension"], "browser": "safari", "routes": [ROUTE]})


# ----- update checks -------------------------------------------------------------------------------

def test_update_check_compares_versions_and_remembers_the_answer(monkeypatch, tmp_path):
    assert update.newer("1.4.1", "1.4.0") and update.newer("v2.0", "1.9.9") and not update.newer("1.4.0", "1.4.0")
    assert update.parse("v1.2.3-beta") == (1, 2, 3)
    state = {}
    monkeypatch.setattr(update, "load_state", lambda: dict(state))
    monkeypatch.setattr(update, "save_state", lambda s: (state.clear(), state.update(s)))
    monkeypatch.setattr(update, "__repo__", "someone/airfare")
    monkeypatch.setattr(update, "fetch", lambda: {"latest": "9.0.0", "url": "https://github.com/someone/airfare/releases/tag/v9.0.0",
                                                  "newer": True})
    first = update.check()
    assert first["newer"] and first["latest"] == "9.0.0" and state["update"]["checked"]
    monkeypatch.setattr(update, "fetch", lambda: (_ for _ in ()).throw(AssertionError("asked GitHub again within a day")))
    assert update.check()["latest"] == "9.0.0"                         # cached, no second request
    monkeypatch.setattr(update, "fetch", lambda: (_ for _ in ()).throw(OSError("offline")))
    forced = update.check(force=True)
    assert forced["error"] == "offline" and forced["latest"] == "9.0.0"   # the last good answer is kept
    monkeypatch.setattr(update, "__repo__", "")
    assert update.check(force=True)["set_up"] is False


# ----- the tray icon ------------------------------------------------------------------------------

def test_the_checker_stays_for_the_tray_icon_and_restarts_when_it_changes(monkeypatch, tmp_path):
    monkeypatch.setattr(tray, "available", lambda: True)
    assert service.needed({"schedule": "startup", "tray": True}) and not service.needed({"schedule": "startup"})
    assert service.needed({"schedule": "interval"})
    monkeypatch.setattr(tray, "available", lambda: False)
    assert not service.needed({"schedule": "startup", "tray": True})     # without pystray there is no icon to keep
    # A tray change mid-run: the loop ends and asks for a restart.
    checker = service._Checker(None, 0.0, 3, "en")
    configs = iter([{"schedule": "interval", "tray": True}])
    monkeypatch.setattr(tray, "available", lambda: True)
    monkeypatch.setattr(service, "load_config", lambda: next(configs))
    monkeypatch.setattr(service, "load_state", lambda: {})
    checker.loop(want_tray=False)
    assert checker.restart


def test_tray_menu_texts_are_translated():
    from airfare.i18n import tr
    assert tr("Check prices now", "es") != "Check prices now" and tr("Quit AirFare", "ru") != "Quit AirFare"


# ----- the CSV export -----------------------------------------------------------------------------

def test_history_page_offers_a_csv_export_from_disk_too():
    page = historypage.build(dict(config.DEFAULT_CONFIG), served=False)
    assert 'id="csv"' in page and "text/csv" in page and "uFEFF" in page     # the BOM, as a JS escape
