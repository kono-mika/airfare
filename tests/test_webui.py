import json
import threading
import time
import urllib.request

from airfare import config, webui

ROUTE = {"id": "r1", "origin": "lhr", "destination": "bcn", "trip": "return",
         "depart_from": "2027-03-12", "return_from": "2027-03-15"}


def test_save_keeps_serpapi_key_and_sources(monkeypatch):
    monkeypatch.setattr(webui, "load_config", lambda: dict(config.DEFAULT_CONFIG))
    cfg = webui.clean_config({"domain": "www.skyscanner.es", "sources": ["extension", "serpapi"],
                              "serpapi_key": "  abc123def456  ", "currency": "eur", "routes": [ROUTE]})
    assert cfg["serpapi_key"] == "abc123def456" and cfg["sources"] == ["extension", "serpapi"]
    import pytest
    with pytest.raises(webui.Problem):                 # a pasted line break never gets into the settings
        webui.clean_config({"sources": ["serpapi"], "serpapi_key": "abc123def456\nX", "routes": [ROUTE]})
    assert cfg["currency"] == "EUR" and cfg["routes"][0]["origin"] == "lhr"


def _get(url):
    with urllib.request.urlopen(url, timeout=3) as r:
        return json.loads(r.read())


def test_opening_settings_replaces_an_outdated_server(monkeypatch):
    port = 8791
    monkeypatch.setattr(webui, "WEBUI_PORT", port)
    old = webui.Server(port)
    old.version = "older-code"

    def run_old():                     # like serve(): release the port once stopped
        old.serve_forever()
        old.server_close()
    threading.Thread(target=run_old, daemon=True).start()
    assert _get(f"http://127.0.0.1:{port}/api/version")["version"] == "older-code"

    threading.Thread(target=webui.serve, kwargs={"open_page": False}, daemon=True).start()
    deadline = time.monotonic() + 8
    version = None
    while time.monotonic() < deadline:
        try:
            version = _get(f"http://127.0.0.1:{port}/api/version")["version"]
            if version == webui.code_version():
                break
        except OSError:
            pass
        time.sleep(0.2)
    assert version == webui.code_version()
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/close", data=b"{}", method="POST",
                                 headers={"X-AirFare": "1"})
    urllib.request.urlopen(req, timeout=3).close()


def test_settings_page_has_every_shared_piece_filled_in():
    from airfare import brand
    page = webui.settings_page("es")
    for placeholder in ("/*TOKENS*/", "<!--LOGO-->", "<!--SKY-->", "__FAVICON__", "__PLANE__", "<!--ICON:",
                        "__LANG__", "<!--I18N-->"):
        assert placeholder not in page
    assert page.count('class="ico"') == 8 and 'class="logo"' in page and 'class="sky"' in page
    assert '<html lang="es">' in page and '<script type="application/json" id="i18n">' in page


def test_example_codes_are_neutral():
    page = (webui.STATIC / "index.html").read_text(encoding="utf-8").lower()
    assert "vno" not in page and "vilnius" not in page


def test_every_page_has_the_same_three_tabs_in_the_same_browser_tab():
    from datetime import datetime
    from airfare import brand, dashboard, historypage
    settings = webui.settings_page("en")
    dash = dashboard.build([], {"runs": []}, {}, {}, datetime(2026, 10, 26, 16, 0), "", False, {}, {}, "x.md")
    history = historypage.build(dict(config.DEFAULT_CONFIG), served=True)
    for page, current in ((settings, "Settings"), (dash, "Dashboard"), (history, "Price history")):
        nav = page.split('<nav class="tabs"', 1)[1].split("</nav>", 1)[0]
        assert 'href="latest.html"' in nav and 'href="history.html"' in nav and 'href="/"' in nav
        assert f'aria-current="page">{current}<' in nav and "target=" not in nav
    for page in (dash, history):
        assert "needs-server" in page and "/api/heartbeat" in page   # Settings tab and keep-alive when served
    assert 'target="_blank"' not in settings.split("<main>", 1)[1].split('<section class="block"', 1)[0]


def test_older_dashboards_get_the_new_tabs_when_served():
    headers = [
        # no tabs at all (the oldest dashboards)
        '<div class="top"><h1>AirFare</h1><p class="muted">Checked Mon 26 Oct 2026, 17:59</p></div>',
        # Dashboard and Price history only
        '<div class="top"><h1>AirFare</h1>\n  <nav class="tabs"><a class="on">Dashboard</a>'
        '<a href="history.html">Price history</a></nav></div>',
        # logo, Dashboard and Price history
        '<div class="top"><div class="brand"><svg class="logo"></svg><h1>AirFare</h1></div>\n'
        '  <nav class="tabs"><a class="on">Dashboard</a><a href="history.html">Price history</a></nav></div>',
    ]
    for header in headers:
        old = f'<html><head><style></style></head><body><main>\n{header}<p>prices</p></main></body></html>'
        page = webui.served_dashboard(old)
        assert page.count('<nav class="tabs"') == 1 and page.count("<h1>AirFare</h1>") == 1
        assert 'href="history.html"' in page and 'href="/"' in page and "/api/heartbeat" in page
        assert page.index('<nav class="tabs"') < page.index("<p>prices</p>")
        assert "<p>prices</p>" in page and webui.served_dashboard(page) == page
    assert "Checked Mon 26 Oct 2026, 17:59" in webui.served_dashboard(
        f'<html><head></head><body><main>{headers[0]}</main></body></html>')


def test_a_key_saves_on_its_own_without_any_route(monkeypatch, tmp_path):
    saved = {}
    monkeypatch.setattr(webui, "load_config", lambda: {**config.DEFAULT_CONFIG, "routes": []})
    monkeypatch.setattr(webui, "save_config", lambda cfg: saved.update(cfg))
    monkeypatch.setattr(webui, "serpapi_account", lambda key: {"total_searches_left": 248})
    out = webui.save_key("serpapi_key", "  abcdef1234567890  ")
    assert saved["serpapi_key"] == "abcdef1234567890" and saved["routes"] == []
    assert out == {"saved_keys": {"serpapi_key": "…7890", "deepseek_api_key": "", "openai_api_key": "", "anthropic_api_key": ""},
                   "check": {"total_searches_left": 248}}
    import pytest
    for name, value in (("domain", "x" * 10), ("serpapi_key", "not a key; drop table"), ("serpapi_key", "short")):
        with pytest.raises(ValueError):
            webui.save_key(name, value)
    assert webui.save_key("serpapi_key", "")["saved_keys"]["serpapi_key"] == ""     # removing needs no check


def test_alert_settings_are_checked_and_follow_the_currency(monkeypatch):
    monkeypatch.setattr(webui, "load_config", lambda: {**config.DEFAULT_CONFIG, "currency": "EUR",
                                                       "alerts": {"fastest": {"on": True, "drop": 2, "max": 140}}})
    monkeypatch.setattr(webui.money, "rates", lambda: {"rates": {"EUR": 1.0, "RUB": 100.0}})
    alerts = {"cheapest": {"on": False, "drop": 10, "max": None}, "fastest": {"on": True, "drop": 2, "max": 140},
              "best": {"on": True, "drop": "", "max": ""}}
    cfg = webui.clean_config({"sources": ["extension"], "currency": "RUB", "alerts": alerts, "alert_max_hours": "20",
                              "alert_no_self_transfer": True, "language": "es", "routes": [ROUTE]})
    assert cfg["alerts"]["cheapest"] == {"on": False, "drop": 10.0, "max": None}
    assert cfg["alerts"]["fastest"]["max"] == 14000                  # €140 became ₽14 000 with the currency
    assert cfg["alerts"]["best"] == {"on": True, "drop": 0.0, "max": None}
    assert cfg["alert_max_hours"] == 20.0 and cfg["alert_no_self_transfer"] and cfg["language"] == "es"
    import pytest
    with pytest.raises(webui.Problem) as e:
        webui.clean_config({"sources": ["extension"], "alerts": {"cheapest": {"drop": 80}}, "routes": [ROUTE]})
    assert e.value.text("ru").startswith("Самый дешёвый: снижение цены (%): значение от 0 до 50")


def test_an_untouched_empty_route_card_doesnt_block_saving(monkeypatch):
    monkeypatch.setattr(webui, "load_config", lambda: dict(config.DEFAULT_CONFIG))
    blank = {"id": "b", "origin": "", "destination": "", "trip": "return", "depart_from": "2027-03-12"}
    cfg = webui.clean_config({"sources": ["extension"], "routes": [blank]})
    assert cfg["routes"] == []
    import pytest
    with pytest.raises(ValueError, match="Route 1"):
        webui.clean_config({"sources": ["extension"], "routes": [{**blank, "name": "Somewhere"}]})


def test_language_is_saved_and_errors_come_back_in_it(monkeypatch):
    port = 8792
    store = {**config.DEFAULT_CONFIG, "language": "en"}
    monkeypatch.setattr(webui, "load_config", lambda: dict(store))
    monkeypatch.setattr(webui, "save_config", lambda cfg: store.update(cfg))
    monkeypatch.setattr(webui.runner, "write_history_page", lambda cfg: None)
    srv = webui.Server(port)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    def post(path, body):
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(body).encode(), method="POST",
                                     headers={"X-AirFare": "1", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=3) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())
    try:
        assert post("/api/language", {"language": "ru"}) == (200, {"language": "ru"}) and store["language"] == "ru"
        assert post("/api/language", {"language": "xx"})[0] == 400
        code, body = post("/api/save", {"config": {"sources": []}})
        assert code == 400 and body["error"] == "Выберите хотя бы один источник цен"
    finally:
        srv.shutdown()
        srv.server_close()
