"""The version shown everywhere: at the bottom of every page, in Settings under Updates, in the tray menu and on the
command line. Versions other than this release's and every route here are invented."""
import json
import re
import shutil
import subprocess
import sys
import threading
import urllib.request
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from airfare import __main__ as cli, __version__, brand, config, dashboard, historypage, i18n, runner, tray, upgrade, webui

ROOT = Path(__file__).resolve().parent.parent
LABELS = {"en": "Version", "es": "Versión", "ru": "Версия"}
WHEN = datetime(2026, 10, 26, 16, 0)
PARTS = {"en": {"title": "Invented", "routes": {"r": {"name": "Invented", "origin": "zza", "destination": "zzb", "html": "<p>x</p>"}}}}


def line(lang: str = "en", version: str = __version__) -> str:
    return f'<p class="version" data-version="{version}">{LABELS[lang]}: {version}</p>'


def pages(lang: str) -> dict[str, str]:
    cfg = {**config.DEFAULT_CONFIG, "language": lang}
    return {"Settings": webui.settings_page(lang), "Clean up": webui.cleanup_page(lang),
            "Price history": historypage.build(cfg, served=True), "Price history on disk": historypage.build(cfg, served=False),
            "Dashboard": dashboard.page({}, lang), "Dashboard after a check": dashboard.page(dashboard.record_check({}, PARTS, WHEN), lang)}


# ----- every page ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("lang", LABELS)
def test_every_page_ends_with_the_same_version_line(lang):
    for name, page in pages(lang).items():
        assert line(lang) in page, name
        assert "<!--VERSION-->" not in page, name
        # At the bottom: nothing of the page's own content comes after it.
        bottom = page[page.rindex(line(lang)):]
        assert ("</main>" in bottom or "</footer>" in bottom) and "<section" not in bottom, name


def test_the_line_is_written_in_one_place():
    assert brand.version_line("es") == line("es")
    for name in ("airfare/static/index.html", "airfare/static/cleanup.html", "airfare/historypage.py", "airfare/dashboard.py"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "<!--VERSION-->" in text or "brand.version_line" in text, name
        assert 'class="version"' not in text, name


def test_a_page_written_by_a_check_keeps_the_version_that_wrote_it(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard, "__version__", "1.4.9")
    store = dashboard.record_check({}, PARTS, WHEN)
    assert store["check"]["version"] == "1.4.9"
    monkeypatch.undo()
    assert line("en", "1.4.9") in dashboard.page(store, "en")          # today's AirFare, showing that check
    assert __version__ not in re.findall(r'data-version="([^"]+)"', dashboard.page(store, "en"))

    monkeypatch.setattr(dashboard, "REPORTS_DIR", tmp_path)
    dashboard.write_pages(store, "ru")
    assert line("ru", "1.4.9") in (tmp_path / "latest.html").read_text(encoding="utf-8")
    assert line("es", "1.4.9") in (tmp_path / "latest-es.html").read_text(encoding="utf-8")

    # Clean up writes the page again: it still shows that check.
    two = dashboard.record_check(store, {"en": {"title": "Invented", "routes": {"s": {"name": "Other", "origin": "zzc", "destination": "zzd", "html": ""}}}}, WHEN)
    two["check"]["version"] = "1.4.9"
    left, _ = dashboard.forget(two, ["s"])
    assert left["check"]["version"] == "1.4.9"


def test_the_live_dashboard_shows_the_version_of_the_check(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard, "__version__", "1.4.9")
    monkeypatch.setattr(dashboard, "STORE_FILE", tmp_path / "dashboard.json")
    dashboard.save_store(dashboard.record_check({}, PARTS, WHEN))
    monkeypatch.setattr(webui, "load_config", lambda: {**config.DEFAULT_CONFIG, "language": "en"})
    monkeypatch.setattr(webui, "REPORTS_DIR", tmp_path)
    port = 8793
    server = webui.Server(port)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/latest.html", timeout=5) as r:
            assert line("en", "1.4.9") in r.read().decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()


def test_the_history_page_on_disk_keeps_the_version_that_wrote_it(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(brand, "__version__", "1.4.9")
    runner.write_history_page({**config.DEFAULT_CONFIG, "language": "es"})
    monkeypatch.undo()
    assert line("es", "1.4.9") in (tmp_path / "history.html").read_text(encoding="utf-8")


def test_a_store_from_before_checks_recorded_it_names_the_version_building_the_page():
    store = dashboard.record_check({}, PARTS, WHEN)
    del store["check"]["version"]
    assert line() in dashboard.page(store, "en")


@pytest.mark.parametrize("stored", ['"><script>alert(1)</script>', 5, ["1.5.0"], {}, "", None])
def test_whatever_the_stored_version_says_stays_plain_text(stored):
    store = dashboard.record_check({}, PARTS, WHEN)
    store["check"]["version"] = stored
    page = dashboard.page(store, "en")
    assert "<script>alert(1)" not in page
    assert page.count('class="version"') == 1


def test_a_dashboard_written_before_this_release_isnt_given_a_version(monkeypatch):
    old = "<html><head></head><body><main><h1>AirFare</h1><p>invented</p></main></body></html>"
    assert 'class="version"' not in webui.served_dashboard(old, "en")


def test_the_language_links_switch_the_line_in_place():
    """The language links' script, run for real: Settings, Price history and Clean up don't reload."""
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js isn't installed")
    code = re.search(r"<script>(.*)</script>", brand.NAV_SCRIPT, re.S).group(1)
    script = """
const version = {dataset: {version: "1.4.9"}, textContent: "Version: 1.4.9"};
const link = {dataset: {lang: "ru"}, handlers: {}, addEventListener(k, f) { this.handlers[k] = f; }, toggleAttribute() {}};
globalThis.location = {protocol: "file:"};
globalThis.localStorage = {setItem() {}};
globalThis.fetch = () => Promise.resolve({ok: true});
globalThis.window = {airfareLanguage() {}};
globalThis.document = {documentElement: {}, querySelectorAll: s => s === ".langs a" ? [link] : s === ".version" ? [version] : []};
""" + code + """
link.handlers.click({preventDefault() {}, button: 0});
console.log(version.textContent);
"""
    out = subprocess.run([node, "-"], input=script, capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "Версия: 1.4.9"


# ----- Settings ------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("lang", LABELS)
def test_updates_in_settings_has_its_own_version_line_above_the_status(lang):
    page = webui.settings_page(lang)
    heading = page.index("<h3 data-i18n>Updates</h3>")
    status = page.index('id="update-status"')
    assert line(lang) in page[heading:status]


def test_the_update_status_no_longer_repeats_the_version():
    source = (ROOT / "airfare" / "static" / "index.html").read_text(encoding="utf-8")
    assert 'AirFare {version}."' not in source and "VERSION" not in source.replace("<!--VERSION-->", "")
    assert "AirFare {version}." not in i18n.T


# ----- the tray menu -------------------------------------------------------------------------------------------

def test_the_tray_menu_starts_with_the_greyed_out_version(monkeypatch):
    class Item:
        def __init__(self, text, action, enabled=True, default=False):
            self.text, self.action, self.enabled = text, action, enabled

    class Menu:
        SEPARATOR = object()

        def __init__(self, *items):
            self.items = items

    class Icon:
        def __init__(self, name, image, title, menu):
            self.menu = menu

    monkeypatch.setattr(tray, "pystray", SimpleNamespace(MenuItem=Item, Menu=Menu, Icon=Icon))
    monkeypatch.setattr(tray, "Image", SimpleNamespace(open=lambda path: None))
    items = tray.Tray("ru", lambda: None, lambda: None).icon.menu.items
    assert items[0].text == f"AirFare {__version__}" and items[0].enabled is False and items[0].action is None
    assert callable(items[1].text) and items[1].enabled is False           # the status line stays right below it
    assert items[2] is Menu.SEPARATOR


# ----- the command line ----------------------------------------------------------------------------------------

def test_version_on_the_command_line():
    r = subprocess.run([sys.executable, "-m", "airfare", "--version"], cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0 and r.stdout == f"AirFare {__version__}\n"


def test_version_answers_from_a_python_without_airfares_packages():
    """-S leaves out every installed package: what someone gets typing it into their system's Python."""
    r = subprocess.run([sys.executable, "-S", "-m", "airfare", "--version"], cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0 and r.stdout == f"AirFare {__version__}\n", r.stderr


def test_version_answers_during_an_update_and_an_unfinished_one(monkeypatch, capsys):
    monkeypatch.setattr(upgrade, "updating", lambda *a: True)
    monkeypatch.setattr(upgrade, "mismatch", lambda *a, **k: "invented")
    with pytest.raises(SystemExit) as e:
        cli.main(["--version"], check_install=True)
    assert e.value.code == 0 and capsys.readouterr().out == f"AirFare {__version__}\n"


def test_the_doctors_first_line_names_the_version(monkeypatch, capsys):
    monkeypatch.setattr(upgrade, "mismatch", lambda *a, **k: None)
    cli.cmd_doctor(None)
    assert capsys.readouterr().out.splitlines()[0] == f"AirFare doctor (version {__version__})"


# ----- the label, and what people read -------------------------------------------------------------------------

def test_the_label_in_three_languages():
    assert i18n.tr("Version", "en") == "Version" and i18n.tr("Version", "es") == "Versión" and i18n.tr("Version", "ru") == "Версия"
    tabs = json.loads(re.search(r"const TEXT = (\{.*?\});\n", brand.NAV_SCRIPT, re.S).group(1))
    assert {lang: tabs[lang]["version"] for lang in LABELS} == LABELS


def test_the_bug_report_says_where_to_find_the_version():
    text = (ROOT / ".github" / "ISSUE_TEMPLATE" / "bug_report.yml").read_text(encoding="utf-8")
    assert "description: Shown at the bottom of every AirFare page, or run python -m airfare --version\n" in text


def test_the_readme_and_changelog_mention_it():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "`python -m airfare --version`" in readme[readme.index("**Updates:**"):readme.index("## Update AirFare")]
    assert "**Version label.**" in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8").split("## 1.4.1")[0]
