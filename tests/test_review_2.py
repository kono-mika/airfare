"""Regressions for the second review (2026-10-27): each test fails on the code before its fix."""
import http.client
import json
import threading
import urllib.request

import pytest

from airfare import config, extract, money, notify, platform, pricelog, research, runner, serpapi, service, webui
from test_serpapi import BODY

RATES = {"rates": {"EUR": 1.0, "NOK": 11.0, "SEK": 11.5, "ZAR": 20.0}}


# ----- Google Flights prices keep the currency they were asked in ------------------------------------------

def test_google_prices_are_not_re_read_from_their_text(monkeypatch):
    monkeypatch.setattr(serpapi, "_get", lambda url, timeout=90: BODY)
    page = {"origin": "lhr", "destination": "bcn", "depart": "2027-03-12", "return": "2027-03-15", "url": "u", "key": "k"}
    for currency in ("NOK", "ZAR"):     # "118 kr" would read as SEK, "R118" as nothing, by the price text alone
        res = serpapi.search(page, "KEY", currency)
        assert res.parsed.currency_code == currency
        before = res.parsed.flights[0].price
        extract.convert_page(res.parsed, currency, RATES, "www.google.com")
        assert res.parsed.comparable and res.parsed.flights[0].price == before


def test_a_reply_cut_short_is_a_serpapi_error_not_a_crash(monkeypatch):
    class Reply:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def read(self):
            raise http.client.IncompleteRead(b"")

    monkeypatch.setattr(serpapi.urllib.request, "urlopen", lambda url, timeout=90: Reply())
    res = serpapi.search({"origin": "lhr", "destination": "bcn", "depart": "2027-03-12", "url": "u", "key": "k"},
                         "KEY", "EUR")
    assert res.status == "error" and "SerpApi" in res.note


# ----- a real exchange-rate move gets through on the second download ---------------------------------------

def test_a_repeated_rate_jump_is_accepted():
    saved = {"rates": {"EUR": 1.0, "TRY": 10.0}}
    first = money._steady({"rates": {"EUR": 1.0, "TRY": 40.0}}, saved)
    assert first["rates"]["TRY"] == 10.0 and first["rejected"] == {"TRY": 40.0}
    second = money._steady({"rates": {"EUR": 1.0, "TRY": 41.0}}, first)
    assert second["rates"]["TRY"] == 41.0 and "rejected" not in second
    # A lone wild figure still never gets through.
    assert money._steady({"rates": {"EUR": 1.0, "TRY": 1_000_000.0}}, second)["rates"]["TRY"] == 41.0


# ----- the price-history lookup ---------------------------------------------------------------------------

def test_lookup_refuses_a_city_code_it_cannot_map(monkeypatch, tmp_path):
    monkeypatch.setattr(pricelog, "LOG_FILE", tmp_path / "price_history.json")
    cfg = {"routes": [{"id": "x", "origin": "barc", "destination": "lhr", "trip": "oneway", "depart_from": "2027-03-12"}],
           "currency": "EUR"}
    with pytest.raises(research.Problem, match="BARC"):
        research.conditions_for(cfg, "x")


def test_source_check_survives_an_unknown_charset(monkeypatch):
    class Reply:
        headers = type("H", (), {"get_content_charset": staticmethod(lambda: "no-such-charset")})()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def read(self, n=-1):
            return b"<p>London to Barcelona return from \xe2\x82\xac149</p>"

    monkeypatch.setattr(research, "public_url", lambda url: True)
    monkeypatch.setattr(research, "_open", lambda req, timeout: Reply())
    why = research.verify_source("https://deals.example.test/x", "London to Barcelona return from €149", 149)
    assert why and "couldn't open" in why


# ----- the price history is changed under a lock ----------------------------------------------------------

def test_price_history_writes_take_a_lock(monkeypatch, tmp_path):
    monkeypatch.setattr(pricelog, "LOG_FILE", tmp_path / "price_history.json")
    monkeypatch.setattr(pricelog, "RESEARCH_FILE", tmp_path / "price_research.json")
    monkeypatch.setattr(pricelog, "LOCK_FILE", tmp_path / "price_history.lock")
    seen = []
    real_save = pricelog._save

    def save(records):
        seen.append(platform.FileLock(pricelog.LOCK_FILE).acquire())   # False: the lock is held while writing
        real_save(records)
    monkeypatch.setattr(pricelog, "_save", save)
    pricelog.add([{"id": "a"}, {"id": "b"}])
    assert pricelog.delete(ids=["a"]) == 1 and [r["id"] for r in pricelog.load()] == ["b"]
    assert seen == [False, False]
    assert platform.FileLock(pricelog.LOCK_FILE).acquire()               # and released afterwards


# ----- the settings server answers GET errors like POST errors ----------------------------------------------

def test_a_broken_setting_gives_an_error_answer_not_a_dropped_connection(monkeypatch):
    port = 8789
    monkeypatch.setattr(webui, "preview", lambda cfg: {}["missing"])
    server = webui.Server(port)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/state", headers={"X-AirFare": "1"})
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req, timeout=5)
        assert e.value.code == 500 and "error" in json.loads(e.value.read())
    finally:
        server.shutdown()
        server.server_close()


# ----- the background checker -----------------------------------------------------------------------------

def test_nothing_to_check_waits_a_whole_interval(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "SERVICE_LOCK", tmp_path / "service.lock")
    monkeypatch.setattr(service, "SERVICE_FILE", tmp_path / "service.json")
    monkeypatch.setattr(service.time, "sleep", lambda s: None)
    monkeypatch.setattr(service, "RETRY_AFTER", 0)                       # a failed check would retry at once
    monkeypatch.setattr(runner, "setup_logging", lambda console=False: None)
    runs = []
    monkeypatch.setattr(runner, "run", lambda *a, **k: runs.append("check") or 2)   # nothing to check
    every = {"schedule": "interval", "interval_hours": 6}
    monkeypatch.setattr(service, "load_config", lambda: every)
    monkeypatch.setattr(service, "load_state", lambda: {"last_check": "2026-10-20T08:00"})
    assert service.serve(max_ticks=4) == 0
    assert runs == ["check"]


# ----- Linux notifications and config.json permissions ----------------------------------------------------

def test_notification_text_starting_with_a_dash_is_not_an_option(monkeypatch):
    monkeypatch.setattr(platform, "WINDOWS", False)
    monkeypatch.setattr(platform, "MACOS", False)
    monkeypatch.setattr(platform, "LINUX", True)
    monkeypatch.setattr(platform, "_notify_send_actions", lambda: False)
    calls = []
    monkeypatch.setattr(platform.subprocess, "run",
                        lambda cmd, **kw: calls.append(cmd) or platform.subprocess.CompletedProcess(cmd, 0, "", ""))
    assert notify.toast("AirFare", "- Prices rose on both routes.")
    assert calls[0][-3:] == ["--", "AirFare", "- Prices rose on both routes."]


def test_config_is_private_from_the_moment_it_exists(monkeypatch, tmp_path):
    monkeypatch.setattr(platform, "WINDOWS", False)
    modes = {}
    monkeypatch.setattr(config.os, "chmod", lambda path, mode: modes.setdefault(str(path), mode))
    config.write_json(tmp_path / "config.json", {"a": 1}, mode=0o600)
    assert modes == {str(tmp_path / "config.json.tmp"): 0o600}         # set on the temporary file, before the rename
    config.write_json(tmp_path / "other.json", {"a": 1})
    assert len(modes) == 1                                              # other files keep the default
