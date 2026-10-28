import json
import threading
import urllib.request
from datetime import datetime, timedelta

import pytest

from airfare import cleanup, config, dashboard, pricelog, webui

WHEN = datetime(2026, 10, 26, 16, 0)


@pytest.fixture
def data(monkeypatch, tmp_path):
    """A throwaway data folder for everything clean-up touches."""
    reports, logs = tmp_path / "reports", tmp_path / "logs"
    reports.mkdir()
    logs.mkdir()
    for mod, name, value in ((pricelog, "LOG_FILE", tmp_path / "price_history.json"),
                             (pricelog, "RESEARCH_FILE", tmp_path / "price_research.json"),
                             (dashboard, "STORE_FILE", tmp_path / "dashboard.json"), (dashboard, "REPORTS_DIR", reports),
                             (cleanup, "REPORTS_DIR", reports), (cleanup, "LOGS_DIR", logs)):
        monkeypatch.setattr(mod, name, value)
    store = {"history": {"routes": {}, "runs": []}, "state": {}}
    monkeypatch.setattr(cleanup, "load_history", lambda: json.loads(json.dumps(store["history"])))
    monkeypatch.setattr(cleanup, "save_history", lambda h: store.update(history=h))
    monkeypatch.setattr(cleanup, "load_state", lambda: json.loads(json.dumps(store["state"])))
    monkeypatch.setattr(cleanup, "save_state", lambda s: store.update(state=s))
    return tmp_path, store


def parts(*routes):
    return {"en": {"title": "t", "checked": "c", "banner": "", "take": "", "analysis": "", "footer": "",
                   "routes": {rid: {"name": rid.upper(), "origin": rid[:3].upper(), "destination": "BCN",
                                    "html": f"<section>{rid}</section>"} for rid in routes}}}


def test_the_dashboard_keeps_earlier_routes_on_their_own_tabs():
    store = dashboard.record_check({}, parts("vlcrtm"), WHEN)
    store = dashboard.record_check(store, parts("rtmvlc"), WHEN + timedelta(days=1))   # the route was turned around
    page = dashboard.page(store, "en")
    assert page.count('class="rpanel"') == 2 and 'class="rtabs"' in page
    assert page.index('data-route="rtmvlc"') < page.index('data-route="vlcrtm"')         # the latest check first
    assert "Earlier route, last checked" in page and 'data-forget="vlcrtm"' in page
    store, n = dashboard.forget(store, ["vlcrtm"])
    assert n == 1 and 'class="rtabs"' not in dashboard.page(store, "en")
    assert "No dashboard yet" in dashboard.page(dashboard.forget(store, everything=True)[0], "en")


def test_the_oldest_earlier_routes_make_way():
    store = {}
    for i in range(dashboard.KEEP_ROUTES + 5):
        store = dashboard.record_check(store, parts(f"r{i:02d}"), WHEN + timedelta(hours=i))
    assert len(store["routes"]) == dashboard.KEEP_ROUTES and "r24" in store["routes"] and "r00" not in store["routes"]


def test_turning_a_route_around_makes_it_a_new_route(monkeypatch):
    old = {"id": "r1", "origin": "lhr", "destination": "bcn", "trip": "return", "depart_from": "2027-03-12",
           "return_from": "2027-03-15", "adults": 1, "cabin": "economy"}
    monkeypatch.setattr(webui, "load_config", lambda: {**config.DEFAULT_CONFIG, "routes": [old]})
    same = webui.clean_config({"sources": ["extension"], "routes": [{**old, "depart_from": "2027-03-13"}]}, renew_ids=True)
    assert same["routes"][0]["id"] == "r1"                       # new dates: still the same route
    turned = webui.clean_config({"sources": ["extension"], "routes": [{**old, "origin": "bcn", "destination": "lhr"}]},
                                renew_ids=True)
    assert turned["routes"][0]["id"] != "r1"
    preview = webui.clean_config({"sources": ["extension"], "routes": [{**old, "origin": "bcn", "destination": "lhr"}]})
    assert preview["routes"][0]["id"] == "r1"                    # only saving renames it, never a preview


def _records(n_days_ago, depart, route="r1", source="Skyscanner"):
    return {"id": f"{route}-{n_days_ago}-{source[:3]}", "route_id": route, "route_name": route.upper(), "source": source,
            "time": (datetime.now() - timedelta(days=n_days_ago)).isoformat(timespec="minutes"), "depart": depart,
            "price": 100.0, "price_text": "€100"}


def test_price_records_are_deleted_by_route_source_age_and_past_trips(data):
    pricelog._save([_records(1, "2099-01-01"), _records(40, "2099-01-01"), _records(40, "2020-01-01", "r2"),
                    _records(2, "2099-01-01", source="Aviasales")])
    cfg = dict(config.DEFAULT_CONFIG)
    with pytest.raises(cleanup.Problem):
        cleanup.run("records", {}, cfg, dry=True)               # nothing picked: nothing deleted by accident
    assert cleanup.run("records", {"older_than_days": 30}, cfg, dry=True) == 2
    assert cleanup.run("records", {"past_trips": True}, cfg, dry=True) == 1
    assert cleanup.run("records", {"source": "Aviasales"}, cfg, dry=True) == 1
    assert cleanup.run("records", {"route_id": "r1", "older_than_days": 30}, cfg) == 1
    assert len(pricelog.load()) == 3


def test_reports_keep_the_latest_check_and_logs_clear(data):
    tmp, _ = data
    for stamp in ("2020-01-01_100000", "2020-01-02_100000"):
        for kind in ("prices", "analysis"):
            (tmp / "reports" / f"{stamp}-{kind}.md").write_text("x")
    assert cleanup.run("reports", {"older_than_days": 30}, {}, dry=True) == 2
    assert cleanup.run("reports", {"everything": True}, {}) == 2
    assert sorted(f.name for f in (tmp / "reports").iterdir()) == ["2020-01-02_100000-analysis.md",
                                                                   "2020-01-02_100000-prices.md"]
    (tmp / "logs" / "airfare.log").write_text("x" * 50)
    (tmp / "logs" / "airfare.log.1").write_text("old")
    assert cleanup.run("logs", {}, {}) == 53
    assert [f.name for f in (tmp / "logs").iterdir()] == ["airfare.log"] and (tmp / "logs" / "airfare.log").read_text() == ""


def test_alerts_reset_and_conversations_start_fresh(data, monkeypatch):
    tmp, store = data
    store["history"] = {"routes": {"r1": {"alert_refs": {"cheapest": {"price": 1}}, "all_time_low": {"price": 1}},
                                   "r2": {"alert_refs": {"best": {"price": 2}}}}, "runs": []}
    assert cleanup.run("alerts", {"route_id": "r1"}, {}) == 1
    assert "alert_refs" not in store["history"]["routes"]["r1"] and "alert_refs" in store["history"]["routes"]["r2"]
    from airfare import deepseek, openai_api
    monkeypatch.setattr(deepseek, "SESSIONS_DIR", tmp / "deepseek")
    monkeypatch.setattr(openai_api, "SESSIONS_DIR", tmp / "openai")
    (tmp / "deepseek").mkdir()
    (tmp / "deepseek" / "abc.json").write_text("[]")
    store["state"] = {"session_id": "claude-1", "deepseek": {"session_id": "abc"}, "openai": {}}
    assert cleanup.run("conversations", {"providers": ["deepseek"]}, {}, dry=True) == 1
    assert cleanup.run("conversations", {"providers": ["deepseek"]}, {}) == 1
    assert store["state"]["session_id"] == "claude-1" and "session_id" not in store["state"]["deepseek"]
    assert not list((tmp / "deepseek").iterdir())


def test_start_over_keeps_settings_and_automatic_cleanup_runs_after_checks(data):
    tmp, store = data
    pricelog._save([_records(400, "2099-01-01"), _records(1, "2099-01-01")])
    dashboard.save_store(dashboard.record_check({}, parts("a"), WHEN))
    cfg = {**config.DEFAULT_CONFIG, "cleanup": cleanup.clean_auto({"records_days": "365", "reports_days": ""})}
    assert cfg["cleanup"] == {"records_days": 365, "reports_days": None, "dashboard_days": None}
    cleanup.automatic(cfg)
    assert len(pricelog.load()) == 1
    assert cleanup.run("everything", {}, cfg) >= 2
    assert pricelog.load() == [] and dashboard.load_store() == {}
    with pytest.raises(cleanup.Problem):
        cleanup.clean_auto({"records_days": "-4"})


def test_cleanup_page_and_api(data, monkeypatch):
    port = 8797
    cfg = {**config.DEFAULT_CONFIG, "language": "es", "routes": []}
    monkeypatch.setattr(webui, "load_config", lambda: dict(cfg))
    monkeypatch.setattr(cleanup, "load_config", lambda: dict(cfg), raising=False)
    monkeypatch.setattr(webui.runner, "write_history_page", lambda c: None)
    monkeypatch.setattr(webui.runner, "ProcessLock", lambda: __import__("contextlib").nullcontext())
    pricelog._save([_records(40, "2099-01-01")])
    srv = webui.Server(port)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    def call(path, body=None):
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method="POST" if body is not None else "GET",
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"X-AirFare": "1", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.read().decode("utf-8"), dict(r.headers)
    try:
        page, headers = call("/cleanup.html")
        assert '<html lang="es">' in page and "Limpieza" in page and "script-src 'sha256-" in headers["Content-Security-Policy"]
        summary = json.loads(call("/api/cleanup")[0])
        assert summary["records"]["total"] == 1 and summary["routes"][0]["records"] == 1
        assert json.loads(call("/api/cleanup", {"action": "records", "older_than_days": 30, "dry_run": True})[0]) == {"count": 1}
        done = json.loads(call("/api/cleanup", {"action": "records", "older_than_days": 30})[0])
        assert done["removed"] == 1 and done["message"] == "Borrado 1 elemento." and pricelog.load() == []
    finally:
        srv.shutdown()
        srv.server_close()
