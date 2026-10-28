"""Regressions for problems found in review: each test fails on the code before its fix."""
import json
from datetime import datetime
from pathlib import Path

import pytest

from airfare import config, extension, markup, money, report, research, runner, webui
from airfare.results import PageResult
from airfare.extract import Flight, Leg, ParsedPage

AVIA = json.loads((Path(__file__).parent / "fixtures" / "aviasales_results.json").read_text(encoding="utf-8"))
RATES = {"rates": {"EUR": 1.0, "RUB": 100.0, "CAD": 1.5, "USD": 1.1}}
WHEN = datetime(2026, 10, 26, 16, 0)


def rules(**kw):
    return report.alert_rules({"alerts": {k: {"on": True, "drop": 3, "max": None} for k in ("cheapest", "fastest", "best")},
                               **kw})


def test_aviasales_results_from_the_extension_reach_the_report():
    raw = {"n": 0, "url": "https://www.aviasales.ru/search/MAD1503TYO18031", "payloads": AVIA, "text": "", "seconds": 20}
    res = extension._to_result({"site": "Aviasales", "route_id": "r", "url": raw["url"]}, raw)
    assert res.status == "ok" and res.payloads
    (pd,) = report.collect([res], "EUR", RATES)
    assert pd.parsed.flights[0].price_text == "€875"


def test_extension_opens_only_search_pages():
    assert extension.allowed("https://www.skyscanner.net/transport/flights/lhr/bcn/270312/")
    assert extension.allowed("https://www.aviasales.ru/search/BCN1503LON18031")
    for url in ("https://www.skyscanner.net/profile", "https://www.aviasales.ru/my/profile", "http://evil.example/",
                "https://u@www.skyscanner.net/transport/flights/lhr/bcn/270312/"):
        assert not extension.allowed(url)


def _summary(price, minutes, stops=0):
    return {"price": price, "price_text": f"€{price:.0f}", "currency": "EUR", "minutes": minutes, "stops": stops}


def test_a_slower_trip_never_counts_as_a_cheaper_fastest_one():
    bests = {"r": {"name": "R", "cheapest": _summary(150, 420, 1), "fastest": _summary(212, 145), "best_pick": None}}
    h = report.update_history({}, bests, WHEN, {}, currency="EUR")
    later = {"r": {**bests["r"], "fastest": _summary(150, 420, 1)}}       # the direct flight is gone
    t = report.alert_targets(h, ["r"], rules(), "EUR", RATES)
    assert report.threshold_hits(t, later, {}) == {}
    h = report.update_history(h, later, WHEN, {}, currency="EUR")
    assert h["routes"]["r"]["alert_refs"]["fastest"]["reason"] == "quicker trip gone"


def test_analyst_picks_must_be_captured_fares_the_filters_allow():
    long = Flight("a", 120.0, "€120", [Leg("MAD", "NRT", "2027-03-15T10:00", "2027-03-16T20:00", 1800, 2, "x")])
    page = {"route_id": "r", "route_name": "R", "key": "k", "url": "https://www.skyscanner.net/transport/flights/mad/nrt/270315/"}
    data = [report.PageData(PageResult(page=page, status="ok"), ParsedPage([long], {}, True, "€", 1, currency_code="EUR"))]
    summary = {"routes": {"r": {"best_value": 120.0, "best_value_stops": 2, "best_value_minutes": 1800}}}
    bv = runner._best_values(summary, "EUR", data, rules(alert_max_hours=20))
    assert bv["r"]["excluded"] is True
    targets = {"r": {"best": {"ref": {"price": 200.0, "text": "€200"}, "drop": 3, "max": None, "target": 194.0}}}
    assert report.threshold_hits(targets, {}, bv) == {}
    made_up = runner._best_values({"routes": {"r": {"best_value": 1.0}}}, "EUR", data, rules())
    assert made_up == {}
    for broken in ({"routes": [1, 2]}, {"routes": {"r": {"best_value": float("inf")}}}, []):
        assert runner._best_values(broken, "EUR", data, rules()) == {}


def test_nan_and_infinity_in_the_analyst_comment_are_ignored():
    from airfare import analyst
    _, summary = analyst.parse_reply('ok\n<!--airfare {"routes": {"r": {"best_value": NaN}}, "low_price": Infinity}-->')
    assert summary["routes"]["r"]["best_value"] is None and summary["low_price"] is None


def test_damaged_history_never_stops_the_checks():
    h = {"routes": {"r": {"alert_refs": {"best": {"price": float("inf"), "text": "x"}, "cheapest": {"price": -5}}}}}
    assert report.alert_targets(h, ["r"], rules(), "EUR", RATES) == {}


def test_old_dollar_prices_follow_the_site():
    h = {"routes": {"r": {"alert_ref": {"cheapest": 450.0, "cheapest_text": "$450", "set": "2026-10-01"}}}}
    t = report.alert_targets(h, ["r"], rules(), "CAD", RATES, site="www.skyscanner.ca")
    assert t["r"]["cheapest"]["ref"]["price"] == 450.0                 # Canadian dollars all along


def test_a_currency_change_without_a_rate_keeps_the_price_limits(monkeypatch):
    monkeypatch.setattr(webui, "load_config", lambda: {**config.DEFAULT_CONFIG, "currency": "EUR",
                                                       "alerts": {"cheapest": {"on": True, "drop": 5, "max": 180}}})
    monkeypatch.setattr(webui.money, "rates", lambda: {"rates": {"EUR": 1.0}})
    route = {"id": "r1", "origin": "mad", "destination": "ber", "trip": "oneway", "depart_from": "2027-03-12"}
    with pytest.raises(webui.Problem, match="no exchange rate"):
        webui.clean_config({"sources": ["extension"], "currency": "RUB",
                            "alerts": {"cheapest": {"on": True, "drop": 5, "max": 180}}, "routes": [route]})


def test_pasted_links_must_be_search_pages(monkeypatch):
    monkeypatch.setattr(webui, "load_config", lambda: dict(config.DEFAULT_CONFIG))
    route = {"id": "r1", "manual_pages": [{"key": None, "url": "http://evil.example/"}]}
    with pytest.raises(webui.Problem, match="search results page"):
        webui.clean_config({"sources": ["extension"], "routes": [route]})


def test_rates_survive_bad_answers_and_ignore_wild_jumps(monkeypatch):
    answers = iter([b"[]", b"<xml/>"])
    monkeypatch.setattr(money, "_get", lambda url: next(answers))
    with pytest.raises(OSError):               # no usable rates: an OSError the callers handle, never a crash
        money.fetch_rates()
    new = {"rates": {"EUR": 1.0, "RUB": 1_000_000.0, "GBP": 0.85}}
    steady = money._steady(new, {"rates": {"EUR": 1.0, "RUB": 91.0, "GBP": 0.84}})
    assert steady["rates"]["RUB"] == 91.0 and steady["rates"]["GBP"] == 0.85



def test_images_in_analyst_text_never_load_from_the_internet():
    html = markup.to_html("![map](https://attacker.example/p.gif?r=x)")
    assert "<img" not in html and "attacker" not in html and "map" in html


def test_lookup_answers_with_the_wrong_types_are_rejected():
    from datetime import date
    c = research.Conditions("r", "R", ["MAD"], ["BER"], "2027-03-01", "2027-03-31", today=date(2026, 10, 26).isoformat())
    good = {"status": "found", "lowest_price": 99.0, "currency": "EUR", "origin": "MAD", "destination": "BER",
            "depart_date": "2027-03-12", "return_date": None, "observed_on": "2026-05-01",
            "source_url": "https://example.test/p", "source_name": "x", "quote": "MAD-BER 99 EUR"}
    assert research.check_answer(good, c) is None
    assert research.check_answer({**good, "lowest_price": True}, c) == "the answer had no usable price"
    assert research.check_answer({**good, "depart_date": 20270312}, c) is not None


def test_an_old_copy_of_the_tab_script_is_swapped_for_todays():
    from airfare import brand
    stale = brand.NAV_SCRIPT.replace("127.0.0.1:", "127.0.0.1:1")
    page = f'<html><body><main><nav class="langs"></nav></main>{stale}</body></html>'
    served = webui.served_dashboard(page)
    assert brand.NAV_SCRIPT in served and stale not in served


def test_more_than_three_alerting_routes_are_all_named(monkeypatch):
    shown = []
    monkeypatch.setattr(runner.notify, "alert", lambda title, lines, buttons, **kw: shown.append((title, lines)) or True)
    data = [report.PageData(PageResult(page={"route_id": f"r{i}", "route_name": f"Route {i}", "url": "u"}), None)
            for i in range(5)]
    runner.send_alerts(data, {f"r{i}": ["cheapest"] for i in range(5)}, {}, {}, {}, None, "latest.html", "en")
    assert len(shown) == 4 and shown[-1][1] == ["Also cheaper: Route 3, Route 4"]


# ----- round 2 -------------------------------------------------------------------------------

def test_cleanup_switches_need_a_real_true(monkeypatch, tmp_path):
    from airfare import cleanup, pricelog
    monkeypatch.setattr(pricelog, "LOG_FILE", tmp_path / "p.json")
    pricelog._save([{"id": "a", "route_id": "r", "time": "2026-01-01T00:00", "depart": "2020-01-01"}])
    for flag in ("everything", "past_trips"):
        with pytest.raises(cleanup.Problem):
            cleanup.run("records", {flag: "false"}, {}, dry=True)        # text is never a yes
    with pytest.raises(cleanup.Problem):
        cleanup.run("records", {"older_than_days": float("inf")}, {}, dry=True)
    assert cleanup.run("dashboard", {"route_ids": [["x"], 3]}, {}, dry=True) == 0
    assert cleanup.run("conversations", {"providers": "openai"}, {}, dry=True) == 0
    assert len(pricelog.load()) == 1


def test_codex_never_gets_odd_arguments(monkeypatch, tmp_path):
    from airfare import chatgpt
    calls = []
    monkeypatch.setattr(chatgpt, "codex_path", lambda: "codex.exe")
    monkeypatch.setattr(chatgpt, "WORK_DIR", tmp_path)
    monkeypatch.setattr(chatgpt, "_call", lambda cmd, prompt: calls.append(cmd) or __import__("subprocess").CompletedProcess(cmd, 1, "", "x"))
    with pytest.raises(chatgpt.ChatGPTError, match="model"):
        chatgpt.run("x", None, 'gpt & calc')
    with pytest.raises(chatgpt.ChatGPTError):
        chatgpt.run("x", "id & calc")
    assert "resume" not in calls[-1]                                     # a malformed id starts a new thread
    assert "--ignore-user-config" in calls[-1] and calls[-1].count("--disable") >= 2
    assert calls[-1][calls[-1].index("--disable") + 1] == "shell_tool"
    with pytest.raises(research.Problem):
        research.resolve_analyst({"llm_provider": "chatgpt"}, "chatgpt", "a / b")


def test_server_errors_never_show_file_paths(monkeypatch):
    import threading
    import urllib.request
    monkeypatch.setattr(webui, "load_config", lambda: {**config.DEFAULT_CONFIG, "language": "en"})

    def broken(*a, **k):
        raise PermissionError(r"[WinError 32] C:\Users\someone\data\logs\airfare.log.1")
    monkeypatch.setattr(webui.cleanup, "run", broken)
    monkeypatch.setattr(webui.runner, "ProcessLock", lambda: __import__("contextlib").nullcontext())
    srv = webui.Server(8798)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        req = urllib.request.Request("http://127.0.0.1:8798/api/cleanup", data=b'{"action": "logs"}', method="POST",
                                     headers={"X-AirFare": "1", "Content-Type": "application/json"})
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req, timeout=5)
        body = json.loads(e.value.read())
        assert e.value.code == 500 and "Users" not in body["error"] and "log" in body["error"]
    finally:
        srv.shutdown()
        srv.server_close()


def test_reports_pages_link_to_are_kept(monkeypatch, tmp_path):
    from airfare import cleanup, dashboard
    monkeypatch.setattr(cleanup, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(dashboard, "STORE_FILE", tmp_path / "dashboard.json")
    for name in ("2020-01-01_100000-prices.md", "2020-01-01_100000-analysis.md", "2020-01-02_100000-prices.md"):
        (tmp_path / name).write_text("x")
    # The second check read no prices: the dashboard and Settings still show the first one.
    dashboard.save_store({"check": {"html": {"en": {"footer": '<a href="2020-01-01_100000-prices.md">x</a>'}}}, "routes": {"r": {}}})
    assert cleanup.run("reports", {"everything": True}, {}) == 0
    assert len(list(tmp_path.glob("*.md"))) == 3


def test_a_cleanup_refuses_when_its_count_changed(monkeypatch):
    import threading
    import urllib.request
    monkeypatch.setattr(webui, "load_config", lambda: {**config.DEFAULT_CONFIG, "language": "en"})
    monkeypatch.setattr(webui.cleanup, "run", lambda action, o, cfg, dry=False: 3)
    monkeypatch.setattr(webui.runner, "ProcessLock", lambda: __import__("contextlib").nullcontext())
    srv = webui.Server(8799)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        req = urllib.request.Request("http://127.0.0.1:8799/api/cleanup", method="POST",
                                     data=json.dumps({"action": "dashboard", "earlier": True, "expect": 2}).encode(),
                                     headers={"X-AirFare": "1", "Content-Type": "application/json"})
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req, timeout=5)
        assert e.value.code == 400 and "changed" in json.loads(e.value.read())["error"]
    finally:
        srv.shutdown()
        srv.server_close()
