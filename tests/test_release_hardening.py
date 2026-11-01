"""The fixes before the 1.5.0 release: updating by unzipping, the installers' lock, the updater's safety, backups.
Every path, route and price here is invented. Scripts and the launcher run for real where the system has what they
need (sh, PowerShell, the C# compiler, Node.js), always in a temporary folder and never past the point being tested."""
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import pytest

from airfare import __main__ as cli, __version__, cleanup, config, extract, filters, historypage, i18n, migrate, money, notify, platform, serpapi, upgrade, webui

ROOT = Path(__file__).resolve().parent.parent
RATES = {"rates": {"EUR": 1.0, "RUB": 100.0, "GBP": 0.8, "JPY": 160.0}, "date": "2026-10-26", "source": "invented"}
windows_only = pytest.mark.skipif(not platform.WINDOWS, reason="Windows only")
posix_only = pytest.mark.skipif(platform.WINDOWS, reason="macOS and Linux only")
SH = shutil.which("sh")
needs_sh = pytest.mark.skipif(not SH, reason="no sh here")
INSIDE = "This copy was unzipped inside your AirFare folder. Delete this inner folder and extract the zip into"
UPDATING = "AirFare is being updated, try again in a few minutes"


def text(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8-sig")


# ----- 1. updating by unzipping --------------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["README.md", "docs/INSTALL_EN.md", "docs/INSTALL_ES.md", "docs/INSTALL_RU.md",
                                  "airfare/static/index.html", "airfare/translations.py", "install.ps1", "install.sh"])
def test_no_update_instruction_says_to_unzip_into_or_over_the_same_folder(name):
    found = text(name)
    for wrong in ("this same folder", "same** AirFare folder", "over this folder", "misma** carpeta", "misma carpeta,",
                  "**ту же** папку", "эту же папку", "over the folder"):
        assert wrong not in found, wrong


@pytest.mark.parametrize("name, words", [
    ("README.md", "**contains** your AirFare folder"), ("docs/INSTALL_EN.md", "**contains** your AirFare folder"),
    ("docs/INSTALL_ES.md", "**contiene** tu carpeta de AirFare"), ("docs/INSTALL_RU.md", "**лежит** ваша папка AirFare")])
def test_the_guides_say_to_extract_into_the_parent_and_give_the_terminal_command(name, words):
    found = text(name)
    assert words in found and "unzip -o AirFare.zip -d " in found and "AirFare 2" in found


def _update_steps(system: str, parent: str, folder: str, other_name: str = "", lang: dict | None = None) -> list[str]:
    """updateSteps from the Settings page, run for real."""
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js isn't installed")
    source = text("airfare/static/index.html")
    code = source[source.index("function shellArg(text)"):source.index("function showDataVersion()")]
    script = """
const TEXTS = {lang: %s}, LANG = "lang";
const fill = (s, p) => String(s).replace(/\\{(\\w+)\\}/g, (m, k) => (p && k in p ? p[k] : m));
const t = (text, params) => fill((TEXTS[LANG] || {})[text] || text, params);
const esc = s => String(s);
const box = {hidden: true, innerHTML: ""};
const $ = () => box;
const FOLDER = %s, PARENT = %s, OTHER_NAME = %s, SYSTEM = %s;
""" % (json.dumps(lang or {}), json.dumps(folder), json.dumps(parent), json.dumps(other_name), json.dumps(system)) + code + """
updateSteps({newer: true});
console.log(JSON.stringify(box.innerHTML.split("</li>").map(x => x.replace("<li>", "")).filter(Boolean)));
"""
    out = subprocess.run([node, "-"], input=script, capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_the_steps_in_settings_show_the_real_parent_folder_on_windows():
    steps = _update_steps("windows", "D:\\Invented", "D:\\Invented\\AirFare")
    assert any("Extract All, choose D:\\Invented and replace the files" in s and "Not into D:\\Invented\\AirFare" in s for s in steps)
    assert any("Double-click AirFare.exe" in s for s in steps)
    assert not any("unzip" in s or "Rename" in s for s in steps)


@pytest.mark.parametrize("parent, shown", [("/home/invented/apps", '"/home/invented/apps"'),
                                           ('/home/in$vent "x"/a`b', r'"/home/in\$vent \"x\"/a\`b"')])
def test_the_steps_in_settings_give_macos_and_linux_a_terminal_command(parent, shown):
    steps = _update_steps("macos", parent, parent + "/AirFare")
    assert any(f"unzip -o AirFare.zip -d {shown}" in s and "AirFare 2" in s for s in steps)
    assert any("sh install.sh" in s for s in steps)


def test_a_folder_with_another_name_is_told_to_rename_first():
    steps = _update_steps("windows", "D:\\Invented", "D:\\Invented\\flights", "flights")
    assert any("called flights" in s and "Rename yours to AirFare first" in s for s in steps)
    assert upgrade.other_folder_name(Path("/invented/flights")) and not upgrade.other_folder_name(Path("/invented/AirFare"))


def test_the_steps_are_translated():
    t = i18n.T
    source = text("airfare/static/index.html")
    start = source.index("function updateSteps(u)")
    for key in re.findall(r't\("((?:[^"\\]|\\.)*)"', source[start:source.index("function showDataVersion()")]):
        assert t[key]["es"] and t[key]["ru"], key
    es = _update_steps("windows", "D:\\Invented", "D:\\Invented\\AirFare", lang={k: v["es"] for k, v in t.items()})
    assert any("Extraer todo, elige D:\\Invented" in s for s in es)


def test_settings_is_told_the_parent_folder():
    source = text("airfare/webui.py")
    assert '"parent": str(PROJECT_DIR.parent)' in source and "s.parent" in text("airfare/static/index.html")


def outer_and_inner(tmp_path: Path, script: str, language: str = "en", outer_name: str = "AirFare") -> tuple[Path, Path]:
    outer = tmp_path / "Invented" / outer_name
    inner = outer / "AirFare"
    (outer / "airfare").mkdir(parents=True)
    (outer / "airfare" / "__init__.py").write_text('__version__ = "1.4.1"\n', encoding="utf-8")
    (outer / "data").mkdir()
    (outer / "data" / "config.json").write_text(json.dumps({"language": language, "routes": ["invented"]}), encoding="utf-8")
    inner.mkdir(exist_ok=True)                 # where capitals don't count, it is the same folder as outer/airfare
    shutil.copy(ROOT / script, inner / script)
    return outer, inner


@needs_sh
def test_install_sh_inside_an_airfare_folder_stops_before_installing_anything(tmp_path):
    outer, inner = outer_and_inner(tmp_path, "install.sh")
    before = (outer / "data" / "config.json").read_bytes()
    r = subprocess.run([SH, str(inner / "install.sh"), "--quiet"], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 1 and INSIDE in r.stdout and "Invented" in r.stdout
    assert not (inner / ".venv").exists() and not (outer / ".venv").exists()
    assert (outer / "data" / "config.json").read_bytes() == before


@needs_sh
@pytest.mark.parametrize("language, words", [("es", "Esta copia se descomprimió"), ("ru", "Эта копия распакована")])
def test_install_sh_says_so_in_the_language_of_settings(tmp_path, language, words):
    _, inner = outer_and_inner(tmp_path, "install.sh", language)
    r = subprocess.run([SH, str(inner / "install.sh"), "--quiet"], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 1 and words in r.stdout


@needs_sh
def test_install_sh_warns_about_an_inner_data_folder_and_another_name_and_touches_neither(tmp_path):
    outer, inner = outer_and_inner(tmp_path, "install.sh", outer_name="flights")
    (inner / "data").mkdir()
    (inner / "data" / "config.json").write_text("{}", encoding="utf-8")
    r = subprocess.run([SH, str(inner / "install.sh"), "--quiet"], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 1 and "folder is called flights" in r.stdout and "has a data folder of its own" in r.stdout
    assert (inner / "data" / "config.json").read_text(encoding="utf-8") == "{}" and (outer / "data").is_dir()


@windows_only
def test_install_ps1_inside_an_airfare_folder_stops_before_installing_anything(tmp_path):
    outer, inner = outer_and_inner(tmp_path, "install.ps1")
    before = (outer / "data" / "config.json").read_bytes()
    r = _powershell_file(inner / "install.ps1")
    assert r.returncode == 1 and INSIDE in re.sub(r"\s+", " ", r.stdout), r.stdout + r.stderr
    assert not (inner / ".venv").exists() and not (outer / ".venv").exists()
    assert (outer / "data" / "config.json").read_bytes() == before


def _powershell_file(script: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script),
                           "-Quiet", *args], capture_output=True, text=True, encoding="oem", errors="replace", timeout=120,
                          creationflags=platform.NO_WINDOW)


@windows_only
def test_windows_powershell_reads_the_spanish_and_russian_texts_of_install_ps1(tmp_path):
    """Windows PowerShell reads a script without a UTF-8 mark in the ANSI code page."""
    assert (ROOT / "install.ps1").read_bytes().startswith(b"\xef\xbb\xbf")
    out = tmp_path / "tokens.txt"
    script = ("$t = $null; $e = $null; [void][Management.Automation.Language.Parser]::ParseFile("
              f"'{ROOT / 'install.ps1'}', [ref]$t, [ref]$e); "
              f"[IO.File]::WriteAllText('{out}', ($e.Count.ToString() + ' ' + (($t | ForEach-Object {{ $_.Text }}) -join ' ')), [Text.Encoding]::UTF8)")
    r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, timeout=120,
                       creationflags=platform.NO_WINDOW)
    assert r.returncode == 0, r.stderr
    tokens = out.read_text(encoding="utf-8-sig")
    assert tokens.startswith("0 ")                       # no parse errors
    for words in ("Эта копия распакована", "Esta copia se descomprimió", "AirFare обновляется", "se está actualizando"):
        assert words in tokens


# ----- the launcher, built for real ----------------------------------------------------------------------------

@pytest.fixture(scope="module")
def launcher(tmp_path_factory) -> Path:
    if not platform.WINDOWS:
        pytest.skip("Windows only")
    csc = Path(os.environ["WINDIR"]) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
    if not csc.exists():
        pytest.skip("no C# compiler here")
    exe = tmp_path_factory.mktemp("launcher") / "AirFare.exe"
    r = subprocess.run([str(csc), "/nologo", "/codepage:65001", "/target:winexe", f"/out:{exe}",
                        "/reference:System.Windows.Forms.dll", str(ROOT / "launcher" / "AirFare.cs")],
                       capture_output=True, text=True, errors="replace", timeout=120)
    assert r.returncode == 0, r.stdout
    return exe


def test_the_launcher_inside_an_airfare_folder_stops_before_anything(launcher, tmp_path):
    outer, inner = outer_and_inner(tmp_path, "install.ps1")
    shutil.copy(launcher, inner / "AirFare.exe")
    # --service never shows a window, so it can run here; the others show the same text in a message box.
    assert subprocess.run([str(inner / "AirFare.exe"), "--service"], timeout=60).returncode == 7
    assert not (inner / ".venv").exists() and not (outer / ".venv").exists()


def test_the_launcher_stops_while_an_installer_holds_the_lock(launcher, tmp_path):
    root = tmp_path / "AirFare"
    (root / ".venv").mkdir(parents=True)
    shutil.copy(launcher, root / "AirFare.exe")
    lock = hold_lock(root / ".venv" / upgrade.INSTALL_LOCK)
    try:
        assert subprocess.run([str(root / "AirFare.exe"), "--service"], timeout=60).returncode == 6
    finally:
        lock()
    # Not held any more: on to the next thing it checks (no environment here), which never shows a window either.
    assert subprocess.run([str(root / "AirFare.exe"), "--service"], timeout=60).returncode == 1


@pytest.mark.parametrize("words", [
    "This copy was unzipped inside your AirFare folder", "Esta copia se descomprimió dentro", "Эта копия распакована внутри",
    "AirFare is being updated, try again in a few minutes", "AirFare se está actualizando", "AirFare обновляется"])
def test_the_launcher_and_the_scripts_have_each_text(words):
    for name in ("launcher/AirFare.cs", "install.ps1", "install.sh"):
        assert words in text(name), name


def test_the_launchers_version_is_the_codes():
    """install.ps1 rebuilds AirFare.exe whenever they differ, so forgetting to raise it rebuilds at every install."""
    found = re.search(r'AssemblyFileVersion\("([\d.]+)"\)', text("launcher/AirFare.cs")).group(1)
    assert migrate.parse(found) == migrate.parse(__version__)


# ----- 2. currency + price range -------------------------------------------------------------------------------

def _route(**fields) -> dict:
    return {"id": "r", "name": "Invented", "origin": "zza", "destination": "zzb", "trip": "oneway",
            "depart_from": "2027-03-12", **fields}


def _saved(monkeypatch, old_fields: dict, form_fields: dict, currency: str = "RUB", rates: dict | None = RATES) -> tuple[dict, dict]:
    old = _route(**old_fields)
    monkeypatch.setattr(webui, "load_config", lambda: {**config.DEFAULT_CONFIG, "currency": "EUR", "routes": [old]})
    monkeypatch.setattr(webui.money, "rates", lambda refresh=True: rates or {"rates": {"EUR": 1.0}})
    cfg = webui.clean_config({"sources": ["extension"], "currency": currency, "routes": [_route(**form_fields)]})
    return old, cfg["routes"][0]


def test_a_range_edited_in_the_same_save_as_the_currency_restarts_the_references(monkeypatch):
    old, route = _saved(monkeypatch, {"price_min": 100.0, "price_max": 300.0}, {"price_min": 100.0, "price_max": 25000})
    assert route["price_min"] == 10000 and route["price_max"] == 25000
    assert filters.changed_routes([old], [route], "EUR", "RUB", RATES) == [route]
    history = {"routes": {"r": {"name": "Invented", "alert_refs": {"cheapest": {"price": 100.0}},
                                "filters": filters.stamped(old, "EUR")}}}
    assert filters.follow_currency(history, [old], [route], "EUR", "RUB", RATES) is False
    assert filters.restart_references(history, [route], "RUB", RATES) == ["r"] and "alert_refs" not in history["routes"]["r"]


def test_a_range_equal_to_the_converted_one_within_the_tolerance_keeps_them(monkeypatch):
    old, route = _saved(monkeypatch, {"price_max": 300.0}, {"price_max": "30100"})
    assert route["price_max"] == 30100                       # typed, not converted: 0.33% off
    assert filters.changed_routes([old], [route], "EUR", "RUB", RATES) == []
    assert filters.changed_routes([old], [{**route, "price_max": 30200}], "EUR", "RUB", RATES) != []    # 0.67% off


def test_rounding_a_small_amount_stays_within_the_tolerance():
    assert filters.same({"price_max": 149.0, "currency": "JPY"}, {"price_max": 1, "currency": "EUR"}, RATES)
    assert money.convert_limit(10, "JPY", "EUR", RATES) == 1              # never rounds down to "no limit"


@pytest.mark.parametrize("rates", [None, {}, {"rates": {"EUR": 1.0}}])
def test_without_rates_the_references_restart(rates):
    old, new = {"price_max": 300.0, "currency": "EUR"}, {"price_max": 30000, "currency": "RUB"}
    assert not filters.same(old, new, rates)
    history = {"routes": {"r": {"name": "Invented", "alert_refs": {"cheapest": {"price": 100.0}}, "filters": old}}}
    assert filters.restart_references(history, [_route(price_max=30000)], "RUB", rates) == ["r"]
    assert filters.changed_routes([_route(price_max=300.0)], [_route(price_max=30000)], "EUR", "RUB", rates)


def test_a_save_without_rates_where_both_bounds_were_typed_restarts_and_says_so(monkeypatch):
    old, route = _saved(monkeypatch, {"price_min": 100.0, "price_max": 300.0}, {"price_min": "9000", "price_max": "29000"}, rates=None)
    assert filters.changed_routes([old], [route], "EUR", "RUB", {"rates": {"EUR": 1.0}}) == [route]


def test_a_conversion_keeps_its_references_even_if_the_rate_moves_before_the_next_check(monkeypatch):
    old, route = _saved(monkeypatch, {"price_max": 300.0}, {"price_max": 300.0})
    history = {"routes": {"r": {"name": "Invented", "alert_refs": {"cheapest": {"price": 100.0}},
                                "filters": filters.stamped(old, "EUR")}}}
    assert filters.follow_currency(history, [old], [route], "EUR", "RUB", RATES) is True
    assert history["routes"]["r"]["filters"] == {"price_max": 30000.0, "currency": "RUB"}
    moved = {"rates": {"EUR": 1.0, "RUB": 110.0}}             # 10% in a day
    assert filters.restart_references(history, [route], "RUB", moved) == [] and history["routes"]["r"]["alert_refs"]


def test_following_the_currency_never_cancels_a_restart_still_to_come(monkeypatch):
    old, route = _saved(monkeypatch, {"price_max": 300.0}, {"price_max": 300.0})
    history = {"routes": {"r": {"name": "Invented", "alert_refs": {"cheapest": {"price": 100.0}},
                                "filters": {"price_max": 500.0, "currency": "EUR"}}}}      # saved, no check since
    assert filters.follow_currency(history, [old], [route], "EUR", "RUB", RATES) is False
    assert filters.restart_references(history, [route], "RUB", RATES) == ["r"]


def test_saving_a_new_currency_in_settings_keeps_the_references_of_a_converted_range(tmp_path, monkeypatch):
    stored = {"routes": {"r": {"name": "Invented", "alert_refs": {"cheapest": {"price": 100.0}},
                               "filters": {"price_max": 300.0, "currency": "EUR"}}}}
    written = []
    monkeypatch.setattr(webui, "LOCK_FILE", tmp_path / "run.lock")
    monkeypatch.setattr(webui, "load_history", lambda: stored)
    monkeypatch.setattr(webui, "save_history", written.append)
    old, route = _route(price_max=300.0), _route(price_max=30000)
    webui._keep_references({"routes": [old], "currency": "EUR"}, {"routes": [route], "currency": "RUB"}, RATES)
    assert written and stored["routes"]["r"]["filters"]["currency"] == "RUB"
    written.clear()
    check = platform.FileLock(tmp_path / "run.lock")
    assert check.acquire()                                     # a check is running: it has the file open
    try:
        stored["routes"]["r"]["filters"] = {"price_max": 300.0, "currency": "EUR"}
        webui._keep_references({"routes": [old], "currency": "EUR"}, {"routes": [route], "currency": "RUB"}, RATES)
        assert not written and stored["routes"]["r"]["filters"]["currency"] == "EUR"
    finally:
        check.release()


def test_from_and_to_are_compared_after_the_conversion(monkeypatch):
    _, route = _saved(monkeypatch, {"price_min": 100.0, "price_max": 300.0}, {"price_min": "5000", "price_max": 300.0})
    assert (route["price_min"], route["price_max"]) == (5000, 30000)     # 5000 RUB is below 300 EUR in rubles
    problems = {}
    monkeypatch.setattr(webui, "load_config", lambda: {**config.DEFAULT_CONFIG, "currency": "EUR",
                                                       "routes": [_route(price_min=100.0, price_max=300.0)]})
    form = {"sources": ["extension"], "currency": "RUB", "routes": [_route(price_min=100.0, price_max="5000")]}
    assert webui.clean_config(form, problems)["routes"] == [] and "From no higher than To" in problems["r"]


# ----- 3. Windows, unfinished update ---------------------------------------------------------------------------

def _windows_desktop(monkeypatch, tmp_path, language="es", toast_works=True):
    calls = {"toast": [], "box": []}
    monkeypatch.setattr(upgrade, "CONFIG_FILE", tmp_path / "config.json")
    (tmp_path / "config.json").write_text(json.dumps({"language": language}), encoding="utf-8")
    monkeypatch.setattr(platform, "WINDOWS", True)
    monkeypatch.setattr(notify, "toast", lambda title, body: calls["toast"].append(body) or toast_works)
    monkeypatch.setattr(platform, "message_box", lambda title, body: calls["box"].append(body), raising=False)
    return calls


@pytest.mark.parametrize("language, words", [("en", "Run AirFare.exe --install"), ("es", "Ejecuta AirFare.exe --install"),
                                             ("ru", "Запустите AirFare.exe --install")])
def test_an_unfinished_update_on_windows_says_to_run_the_installer(monkeypatch, tmp_path, language, words):
    calls = _windows_desktop(monkeypatch, tmp_path, language)
    upgrade.tell_desktop()
    assert words in calls["toast"][0] and not calls["box"]


def test_a_message_box_says_it_when_the_toast_fails(monkeypatch, tmp_path):
    calls = _windows_desktop(monkeypatch, tmp_path, "en", toast_works=False)
    upgrade.tell_desktop()
    assert "AirFare.exe --install" in calls["box"][0]


def test_exit_code_5_on_windows_tells_the_desktop(monkeypatch, tmp_path, capsys):
    calls = _windows_desktop(monkeypatch, tmp_path, "en")
    monkeypatch.setattr(upgrade, "mismatch", lambda *a, **k: "Run AirFare.exe --install to finish the update.")
    monkeypatch.setattr(upgrade, "note", lambda text: None)
    monkeypatch.setattr(upgrade, "updating", lambda *a: False)
    assert cli.main(["run"], check_install=True) == upgrade.UNFINISHED
    assert calls["toast"] and "AirFare.exe --install" in capsys.readouterr().err


@windows_only
def test_the_build_script_rebuilds_only_a_stale_launcher(tmp_path):
    root = tmp_path / "Invented folder [1]"
    (root / "airfare").mkdir(parents=True)
    (root / "launcher").mkdir()
    (root / "assets").mkdir()
    for name in ("launcher/AirFare.cs", "launcher/build.ps1", "assets/airfare.ico"):
        shutil.copy(ROOT / name, root / name)
    (root / "airfare" / "__init__.py").write_text(f'__version__ = "{__version__}"\n', encoding="utf-8")
    exe, source = root / "AirFare.exe", root / "launcher" / "AirFare.cs"
    past = time.time() - 3600
    os.utime(source, (past, past))

    def build() -> float:
        r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                            str(root / "launcher" / "build.ps1"), "-IfStale"], capture_output=True, text=True, errors="replace",
                           timeout=180, creationflags=platform.NO_WINDOW)
        assert r.returncode == 0, r.stdout + r.stderr
        return exe.stat().st_mtime_ns

    first = build()                                            # missing: built
    assert exe.exists() and build() == first                   # the same version and an older source: left alone
    release = ".".join(str(n) for n in migrate.parse(__version__))
    (root / "airfare" / "__init__.py").write_text(f'__version__ = "{release}rc1"\n', encoding="utf-8")
    assert build() == first                                    # a release candidate counts as its release
    (root / "airfare" / "__init__.py").write_text('__version__ = "9.1.0"\n', encoding="utf-8")
    second = build()                                           # another version: built again
    assert second != first
    (root / "airfare" / "__init__.py").write_text(f'__version__ = "{__version__}"\n', encoding="utf-8")
    os.utime(source, None)
    os.utime(exe, (past, past))
    assert build() != past                                     # the source is newer: built again


def test_install_ps1_asks_for_a_stale_launcher_to_be_rebuilt():
    source = text("install.ps1")
    assert '"launcher\\build.ps1") -IfStale' in source
    assert source.index("build.ps1") < source.index("New-Shortcut (Join-Path")


# ----- 4. backups and migration --------------------------------------------------------------------------------

FIXTURE = Path(__file__).parent / "fixtures" / "data-1.4.1"


@pytest.fixture
def data(tmp_path, monkeypatch):
    folder = tmp_path / "data"
    shutil.copytree(FIXTURE, folder, ignore=shutil.ignore_patterns("README.txt"))
    monkeypatch.setattr(migrate, "DATA_DIR", folder)
    return folder


def files_of(folder: Path) -> dict[str, bytes]:
    return {f.relative_to(folder).as_posix(): f.read_bytes() for f in sorted(folder.rglob("*"))
            if f.is_file() and f.name != migrate.LOCK_NAME}


def not_backups(found: dict[str, bytes]) -> dict[str, bytes]:
    return {k: v for k, v in found.items() if not k.startswith("backups/")}


@pytest.mark.parametrize("error", [OSError("invented"), ValueError("invented")])
def test_a_failed_backup_is_a_migration_error_and_leaves_nothing_half_made(data, monkeypatch, caplog, error):
    before = files_of(data)

    def broken(*a, **k):
        raise error
    monkeypatch.setattr(migrate.shutil, "copy2", broken)
    with caplog.at_level(logging.ERROR, logger="airfare.migrate"), pytest.raises(migrate.MigrationError, match="Couldn't back up"):
        migrate.ensure(data)
    assert files_of(data) == before and "couldn't back up" in caplog.text
    assert not list((data / "backups").glob("*"))              # no .partial left behind
    assert not (data / "version.json").exists()


def test_listing_the_backups_when_that_fails_is_a_migration_error(data, monkeypatch, caplog):
    (data / "backups").mkdir()

    def broken(self):
        raise PermissionError(13, "invented", "/invented/path/backups")
    monkeypatch.setattr(Path, "iterdir", broken)
    with caplog.at_level(logging.ERROR, logger="airfare.migrate"), pytest.raises(migrate.MigrationError) as e:
        migrate.list_backups(data)
    assert "/invented/path" not in str(e.value) and "couldn't read the backups" in caplog.text
    with pytest.raises(migrate.MigrationError):
        migrate.ensure(data)
    assert not (data / "version.json").exists()
    assert cleanup._listed_backups() == [] and migrate.delete_backups(everything=True, data=data) == 0     # Clean up still opens


@pytest.mark.parametrize("error", [OSError(28, "No space left", "/invented/path/config.json"), ValueError("invented")])
def test_a_failed_step_says_so_without_paths_and_puts_the_data_back(data, monkeypatch, caplog, error):
    before = not_backups(files_of(data))

    def broken(folder):
        (folder / "config.json").write_text("{}", encoding="utf-8")
        (folder / "state.json").unlink()
        (folder / "deepseek" / "added-by-the-step.json").write_text("{}", encoding="utf-8")
        (folder / "openai").mkdir(exist_ok=True)
        (folder / "openai" / "added-by-the-step.json").write_text("{}", encoding="utf-8")
        raise error
    monkeypatch.setattr(migrate, "STEPS", {2: broken})
    with caplog.at_level(logging.ERROR, logger="airfare.migrate"), pytest.raises(migrate.MigrationError, match="put back as it was") as e:
        migrate.ensure(data)
    assert "/invented/path" not in str(e.value) and "/invented/path" not in caplog.text
    assert not_backups(files_of(data)) == before               # also what the step added is gone


def test_when_putting_it_back_fails_the_message_doesnt_claim_it_did(data, monkeypatch, caplog):
    def broken_step(folder):
        raise ValueError("invented")

    def broken_restore(saved, folder):
        raise OSError(5, "invented")
    monkeypatch.setattr(migrate, "STEPS", {2: broken_step})
    monkeypatch.setattr(migrate, "restore", broken_restore)
    with pytest.raises(migrate.MigrationError) as e:
        migrate.ensure(data)
    assert "put back as it was" not in str(e.value) and "putting it back failed too" in str(e.value)
    assert str(e.value).count(migrate.list_backups(data)[0]["name"]) == 1
    assert str(data) not in str(e.value)


def test_a_failed_version_record_puts_the_data_back(data, monkeypatch):
    before = not_backups(files_of(data))

    def broken(folder):
        raise OSError(13, "invented")
    monkeypatch.setattr(migrate, "_write_version", broken)
    with pytest.raises(migrate.MigrationError, match="put back as it was"):
        migrate.ensure(data)
    assert not_backups(files_of(data)) == before


def test_a_lock_that_cant_be_opened_is_a_migration_error(data, monkeypatch):
    def broken(folder):
        raise PermissionError(13, "invented", "/invented/path/migrate.lock")
    monkeypatch.setattr(migrate, "_lock", broken)
    with pytest.raises(migrate.MigrationError, match="Nothing in it was changed") as e:
        migrate.ensure(data)
    assert "/invented/path" not in str(e.value)


def test_unfinished_backups_go_at_the_next_start_and_other_folders_stay(data):
    root = data / "backups"
    (root / "1.4.1-20261030-1200.partial").mkdir(parents=True)
    (root / "1.4.1-20261030-1200.partial" / "config.json").write_text("{}", encoding="utf-8")
    (root / "my own.partial").mkdir()
    (root / "my own.partial" / "keep.txt").write_text("mine", encoding="utf-8")
    migrate.ensure(data)
    assert not (root / "1.4.1-20261030-1200.partial").exists() and (root / "my own.partial" / "keep.txt").exists()
    (root / "1.5.0-20261031-1200.partial").mkdir()              # this time with nothing else to do
    assert migrate.ensure(data)["steps"] == []
    assert not (root / "1.5.0-20261031-1200.partial").exists()


def test_an_unfinished_backup_another_process_is_making_stays(data):
    migrate.ensure(data)
    partial = data / "backups" / "1.5.0-20261031-1200.partial"
    partial.mkdir()
    other = platform.FileLock(data / migrate.LOCK_NAME)
    assert other.acquire()                                      # it holds the migration lock
    try:
        migrate.ensure(data)
        assert partial.exists()
    finally:
        other.release()


def test_data_from_a_newer_airfare_keeps_even_its_unfinished_backups(data):
    (data / "version.json").write_text(json.dumps({"app": "9.1.0", "schema": 99}), encoding="utf-8")
    partial = data / "backups" / "9.1.0-20261031-1200.partial"
    partial.mkdir(parents=True)
    migrate.ensure(data)
    assert partial.exists()


def test_failures_reuse_one_backup_and_never_push_out_earlier_versions(data, monkeypatch):
    earlier = ["1.2.0-20240101-1200", "1.3.0-20250101-1200", "1.4.0-20260101-1200"]
    for name in earlier:
        (data / "backups" / name).mkdir(parents=True)
        (data / "backups" / name / "config.json").write_text(json.dumps({"from": name}), encoding="utf-8")

    def broken(folder):
        (folder / "config.json").write_text("{}", encoding="utf-8")
        raise ValueError("invented")
    monkeypatch.setattr(migrate, "STEPS", {2: broken})
    for _ in range(4):
        with pytest.raises(migrate.MigrationError):
            migrate.ensure(data)
    names = {b["name"] for b in migrate.list_backups(data)}
    assert set(earlier) <= names and len(names) == 4           # three earlier ones, and one for all four attempts

    monkeypatch.undo()
    monkeypatch.setattr(migrate, "DATA_DIR", data)
    result = migrate.ensure(data)                               # the attempt that works prunes, and keeps its own
    after = [b["name"] for b in migrate.list_backups(data)]
    assert result["backup"] in after and len(after) == migrate.KEEP_BACKUPS and earlier[0] not in after


def test_changed_data_gets_a_new_backup_and_another_version_too(data):
    first = migrate.backup(data, "1.4.1")
    assert migrate.backup(data, "1.4.1") == first
    assert migrate.backup(data, "1.4.2") != first
    (data / "state.json").write_text("{}", encoding="utf-8")
    assert migrate.backup(data, "1.4.1") != first
    (data / "deepseek" / "new.json").write_text("{}", encoding="utf-8")
    assert migrate.backup(data, "1.4.1") not in (None, first)
    assert len({b["name"] for b in migrate.list_backups(data)}) == 4


def test_pruning_problems_dont_fail_an_update_that_worked(data, monkeypatch):
    real = migrate.list_backups
    calls = []

    def listing(folder=None):
        calls.append(1)
        if len(calls) > 1:                                      # the one in backup() works
            raise migrate.MigrationError("invented")
        return real(folder)
    monkeypatch.setattr(migrate, "list_backups", listing)
    assert migrate.ensure(data)["steps"] == [2]


def test_folders_whose_dates_dont_exist_are_skipped_and_never_deleted(data):
    bad = data / "backups" / "1.4.1-20261399-9999"
    bad.mkdir(parents=True)
    (bad / "keep.txt").write_text("mine", encoding="utf-8")
    assert migrate.list_backups(data) == [] and migrate.delete_backups(everything=True, data=data) == 0
    assert (bad / "keep.txt").exists()


@pytest.mark.parametrize("app", ["", "old", "../../etc", "v1.5.0", "...", "-", "1.5.0-rc.1", "x" * 500, "9" * 500, "1.5.0..."])
def test_any_version_text_makes_a_name_the_backups_list_can_find(data, app):
    made = migrate.backup(data, app)
    assert migrate.BACKUP_RE.match(made.name) and made.parent == data / "backups"
    assert len(made.name) < 64 and [b["name"] for b in migrate.list_backups(data)] == [made.name]


def test_backups_hold_version_json_and_a_backup_can_go_back_to_it(data):
    (data / "version.json").write_text(json.dumps({"app": "1.4.9", "schema": 1, "updated": "invented"}), encoding="utf-8")
    original = (data / "version.json").read_bytes()
    result = migrate.ensure(data)
    saved = data / "backups" / result["backup"]
    assert (saved / "version.json").read_bytes() == original
    assert migrate.read_version(data)["app"] == __version__
    migrate.restore(saved, data)
    assert (data / "version.json").read_bytes() == original


def test_restoring_a_backup_without_version_json_removes_the_new_one(data):
    result = migrate.ensure(data)
    assert (data / "version.json").exists()
    migrate.restore(data / "backups" / result["backup"], data)
    assert not (data / "version.json").exists()


@pytest.mark.parametrize("content", [b"{ broken", b"\xff\xfe\x00 not text", b"[1, 2]", b'{"app": "1.4.1"}', b'{"schema": true}', b""])
def test_a_version_json_that_cant_be_read_stays_and_nothing_is_migrated(data, caplog, content):
    (data / "version.json").write_bytes(content)
    before = files_of(data)
    with caplog.at_level(logging.WARNING, logger="airfare.migrate"):
        result = migrate.ensure(data)
    assert result["steps"] == [] and not result["newer"] and result["backup"] is None
    assert files_of(data) == before and not (data / "version.json.broken").exists()
    assert result["to"]["schema"] == migrate.SCHEMA and result["to"]["app"] == __version__
    assert "version.json can't be read" in caplog.text and str(data) not in caplog.text
    assert migrate.status(data)["newer"] is False


def test_a_version_json_that_cant_be_opened_stays_and_nothing_is_migrated(data, monkeypatch):
    (data / "version.json").write_text("{}", encoding="utf-8")
    before = files_of(data)
    real = Path.read_text

    def locked(self, *a, **k):
        if self.name == "version.json":
            raise PermissionError(13, "invented")
        return real(self, *a, **k)
    monkeypatch.setattr(Path, "read_text", locked)
    assert migrate.ensure(data)["steps"] == []
    monkeypatch.undo()
    assert files_of(data) == before


@pytest.mark.parametrize("version, numbers", [("1.5.0", (1, 5, 0)), ("1.5.0rc1", (1, 5, 0)), ("1.5", (1, 5, 0)), ("1.5.0.0", (1, 5, 0)),
                                              ("1.5.0-rc.1", (1, 5, 0)), ("v1.5.0", (1, 5, 0)), ("1.5.0.1", (1, 5, 0, 1)),
                                              ("1.10.0", (1, 10, 0)), ("", (0, 0, 0)), ("old", (0, 0, 0)), (None, (0, 0, 0))])
def test_only_the_numeric_release_is_compared(version, numbers):
    assert migrate.parse(version) == numbers


def test_a_release_candidate_is_not_newer_than_its_release(monkeypatch):
    monkeypatch.setattr(migrate, "__version__", "1.5.0")
    assert not migrate.newer({"app": "1.5.0rc1", "schema": migrate.SCHEMA})
    monkeypatch.setattr(migrate, "__version__", "1.5.0rc1")
    assert not migrate.newer({"app": "1.5.0", "schema": migrate.SCHEMA})


# ----- 5. one installer at a time ------------------------------------------------------------------------------

def hold_lock(path: Path):
    """Hold the install lock as install.ps1 does: the file open for this process alone. Returns how to let go."""
    if platform.WINDOWS:
        import ctypes
        from ctypes import wintypes
        create = ctypes.windll.kernel32.CreateFileW
        create.restype = wintypes.HANDLE
        create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        handle = create(str(path), 0xC0000000, 0, None, 4, 0, None)
        assert handle != wintypes.HANDLE(-1).value
        close = ctypes.windll.kernel32.CloseHandle
        close.argtypes = [wintypes.HANDLE]
        return lambda: close(handle)
    path.write_text(str(os.getpid()), encoding="ascii")
    return lambda: path.unlink()


def test_the_lock_is_seen_while_held_and_not_after(tmp_path):
    (tmp_path / ".venv").mkdir()
    assert not upgrade.updating(tmp_path)                       # no file yet
    release = hold_lock(tmp_path / ".venv" / upgrade.INSTALL_LOCK)
    assert upgrade.updating(tmp_path)
    release()
    assert not upgrade.updating(tmp_path)


def test_a_left_over_lock_file_on_macos_and_linux_holds_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(platform, "WINDOWS", False)
    alive = []
    monkeypatch.setattr(upgrade, "_alive", lambda pid: alive.append(pid) or pid == 4242)
    (tmp_path / ".venv").mkdir()
    lock = tmp_path / ".venv" / upgrade.INSTALL_LOCK
    assert not upgrade.updating(tmp_path)
    for content, held in (("4242", True), ("4243", False), ("not a number", False), ("1", False), ("-1", False), ("", False)):
        lock.write_text(content, encoding="ascii")
        assert upgrade.updating(tmp_path) is held, content
    lock.write_text("4242", encoding="ascii")
    long_ago = time.time() - upgrade.LOCK_MAX_AGE - 60
    os.utime(lock, (long_ago, long_ago))                        # that id belongs to something else by now
    assert not upgrade.updating(tmp_path)


def test_python_m_airfare_says_so_while_held_and_starts_nothing(monkeypatch, capsys):
    told, started = [], []
    monkeypatch.setattr(upgrade, "updating", lambda *a: True)
    monkeypatch.setattr(upgrade, "tell_desktop", lambda text=None: told.append(text))
    monkeypatch.setattr(migrate, "at_start", lambda: started.append("migration"))
    monkeypatch.setattr(cli.runner, "run", lambda **k: started.append("check"))
    assert cli.main(["run"], check_install=True) == upgrade.UPDATING == 6
    assert UPDATING in capsys.readouterr().err and told == [UPDATING] and not started


@pytest.mark.parametrize("language, words", [("es", "AirFare se está actualizando"), ("ru", "AirFare обновляется")])
def test_the_notification_says_so_in_the_language_of_settings(monkeypatch, tmp_path, language, words):
    calls = _windows_desktop(monkeypatch, tmp_path, language)
    upgrade.tell_desktop(upgrade.BEING_UPDATED)
    assert words in calls["toast"][0]


@pytest.mark.parametrize("command", ["migrate", "doctor"])
def test_what_the_installer_runs_itself_isnt_stopped_by_its_lock(monkeypatch, command):
    monkeypatch.setattr(upgrade, "updating", lambda *a: True)
    monkeypatch.setattr(upgrade, "mismatch", lambda *a, **k: None)
    monkeypatch.setattr(migrate, "at_start", lambda: None)
    assert cli._starting(command, True) is None


def test_the_checker_the_installer_starts_isnt_stopped_by_its_lock(tmp_path, monkeypatch):
    from airfare import service
    (tmp_path / ".venv").mkdir()
    release = hold_lock(tmp_path / ".venv" / upgrade.INSTALL_LOCK)
    seen = []
    try:
        monkeypatch.setattr(upgrade, "write_record", lambda root=None: None)
        monkeypatch.setattr(service, "start_in_background", lambda: seen.append(upgrade.updating(tmp_path)) or True)
        monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
        config.save_config({**config.DEFAULT_CONFIG, "schedule": "interval", "routes": [{"id": "fx01ab", "origin": "zzaa"}]})
        assert upgrade.updating(tmp_path)
        assert upgrade.finish() == 0 and seen == [False]
    finally:
        release()


@pytest.mark.parametrize("script, release, opens", [("install.ps1", "Release-Lock\n", "[Diagnostics.Process]::Start($open)"),
                                                    ("install.sh", "release_lock  ", 'nohup "$venv_py" -m airfare setup')])
def test_the_lock_goes_before_settings_opens_and_before_waiting_for_enter(script, release, opens):
    source = text(script).replace("\r\n", "\n")
    assert source.rindex("Release-Lock" if script == "install.ps1" else "release_lock") < source.index(opens)
    wait = "Read-Host \"Press Enter" if script == "install.ps1" else "Press Enter to close"
    name = "Release-Lock" if script == "install.ps1" else "release_lock"
    finish = source[source.index("function Done" if script == "install.ps1" else "finish() {"):source.index(wait)]
    assert name in finish


def test_making_the_environment_again_keeps_the_lock():
    assert 'Where-Object { $_.Name -ne $lockName } | Remove-Item' in text("install.ps1")
    source = text("install.sh")
    assert "! -name airfare-install.lock" in source and 'rm -rf "$root/.venv"' not in source


@windows_only
def test_install_ps1_says_so_while_another_holds_the_lock(tmp_path):
    root = tmp_path / "AirFare"
    (root / ".venv").mkdir(parents=True)
    shutil.copy(ROOT / "install.ps1", root / "install.ps1")
    (root / "data").mkdir()
    (root / "data" / "config.json").write_text(json.dumps({"language": "en"}), encoding="utf-8")
    release = hold_lock(root / ".venv" / upgrade.INSTALL_LOCK)
    try:
        r = _powershell_file(root / "install.ps1", "-Upgrade")
    finally:
        release()
    assert r.returncode == 1 and UPDATING in re.sub(r"\s+", " ", r.stdout)
    assert not (root / ".venv" / "Scripts").exists()


@windows_only
def test_install_ps1s_lock_is_seen_by_python_and_goes_with_its_process(tmp_path):
    source = text("install.ps1").replace("\r\n", "\n")
    block = source[source.index('try { [void][IO.Directory]::CreateDirectory'):source.index('try {\n    if ($Upgrade) { Write-Host "Updating')]
    (tmp_path / "AirFare").mkdir()
    script = tmp_path / "held.ps1"
    python = ("import sys; from pathlib import Path; sys.path.insert(0, sys.argv[2]); from airfare import upgrade; "
              "print('HELD' if upgrade.updating(Path(sys.argv[1])) else 'FREE')")
    script.write_text("\ufeff" + f"""param($python)
$root = '{tmp_path / 'AirFare'}'
$installLock = $null
function Fail($t) {{ Write-Host $t; exit 9 }}
function Pick-Text($a, $b) {{ return $b }}
function Get-Language($f) {{ return 'en' }}
{block}
& $python -c "{python}" $root '{ROOT}'
""", encoding="utf-8")
    r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script), sys.executable],
                       capture_output=True, text=True, errors="replace", timeout=120, creationflags=platform.NO_WINDOW)
    assert "HELD" in r.stdout, r.stdout + r.stderr
    assert not upgrade.updating(tmp_path / "AirFare")           # the script ended without letting go by itself


def _sh_lock(root: Path, line: str) -> subprocess.CompletedProcess:
    source = text("install.sh")
    block = source[source.index('lock="$root/.venv/airfare-install.lock"'):source.index("# A copy unzipped inside an AirFare folder")]
    return subprocess.run([SH, "-c", f'root="{root.as_posix()}"\n{block}\n{line}\n'], capture_output=True, text=True, timeout=60)


@needs_sh
def test_install_sh_takes_the_lock_once_and_replaces_a_left_over_one(tmp_path):
    root = tmp_path / "AirFare"
    root.mkdir()
    lock = root / ".venv" / upgrade.INSTALL_LOCK
    r = _sh_lock(root, 'take_lock && echo taken "$$"')
    assert r.stdout.startswith("taken ") and lock.read_text(encoding="ascii").strip() == r.stdout.split()[1]
    lock.write_text("999999", encoding="ascii")                 # no such process
    assert "taken" in _sh_lock(root, "take_lock && echo taken").stdout
    r = _sh_lock(root, 'echo "$$" > "$lock"; take_lock && echo taken; release_lock; [ -e "$lock" ] && echo kept || echo gone')
    assert "gone" in r.stdout                                   # its own lock: released


@needs_sh
@posix_only
def test_install_sh_says_so_while_a_running_process_holds_the_lock(tmp_path):
    root = tmp_path / "AirFare"
    (root / ".venv").mkdir(parents=True)
    shutil.copy(ROOT / "install.sh", root / "install.sh")
    lock = root / ".venv" / upgrade.INSTALL_LOCK
    lock.write_text(str(os.getpid()), encoding="ascii")
    r = subprocess.run([SH, str(root / "install.sh"), "--quiet"], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 1 and UPDATING in r.stdout
    assert lock.read_text(encoding="ascii") == str(os.getpid()) and not (root / ".venv" / "bin").exists()


# ----- 6. the updater's safety ---------------------------------------------------------------------------------

LISTED = ["airfare/__init__.py", "airfare/config.py", "extension/manifest.json", "install.ps1", "MANIFEST.txt"]


def release(root: Path, *extra: str, version: str = __version__, listed: list[str] = LISTED) -> None:
    for name in [*listed, *extra]:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text("invented", encoding="utf-8")
    (root / "MANIFEST.txt").write_text(f"# AirFare {version}: invented\n" + "".join(f"{n}\n" for n in listed)
                                       + f"# end: {len(listed)} files\n", encoding="utf-8")


def link_or_skip(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=target.is_dir())
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links aren't allowed here")


def junction_or_skip(link: Path, target: Path) -> None:
    if not platform.WINDOWS:
        pytest.skip("Windows only")
    r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, creationflags=platform.NO_WINDOW)
    if r.returncode != 0:
        pytest.skip("junctions aren't possible here")


def outside_folder(tmp_path: Path) -> Path:
    folder = tmp_path / "outside"
    (folder / "deep").mkdir(parents=True)
    (folder / "precious.txt").write_text("mine", encoding="utf-8")
    (folder / "deep" / "precious.txt").write_text("mine", encoding="utf-8")
    return folder


@pytest.mark.parametrize("make", [link_or_skip, junction_or_skip])
def test_the_clean_up_never_enters_a_linked_folder(tmp_path, make):
    root, outside = tmp_path / "AirFare", outside_folder(tmp_path)
    release(root, "airfare/retired.py")
    make(root / "airfare" / "linked", outside)
    assert upgrade.remove_leftovers(root, data=root / "data") == ["airfare/retired.py"]
    assert (outside / "precious.txt").exists() and (outside / "deep" / "precious.txt").exists()
    assert os.path.lexists(root / "airfare" / "linked")         # the link stays too


@pytest.mark.parametrize("make", [link_or_skip, junction_or_skip])
def test_a_code_folder_that_is_a_link_is_skipped(tmp_path, make):
    root, outside = tmp_path / "AirFare", outside_folder(tmp_path)
    release(root)
    make(root / "tools", outside)
    assert upgrade.remove_leftovers(root, data=root / "data") == []
    assert (outside / "precious.txt").exists() and (outside / "deep" / "precious.txt").exists()


def test_a_linked_file_pointing_outside_is_left_alone(tmp_path):
    root, outside = tmp_path / "AirFare", outside_folder(tmp_path)
    release(root, "airfare/retired.py")
    link_or_skip(root / "airfare" / "linked.txt", outside / "precious.txt")
    assert upgrade.remove_leftovers(root, data=root / "data") == ["airfare/retired.py"]
    assert (root / "airfare" / "linked.txt").is_symlink() and (outside / "precious.txt").exists()


def test_a_reparse_point_counts_as_a_link(tmp_path, monkeypatch):
    class Stat:
        st_mode = 0o040777
        st_file_attributes = 0x400
    monkeypatch.setattr(upgrade.os, "lstat", lambda path: Stat())
    monkeypatch.setattr(upgrade.os.path, "isjunction", lambda path: False)
    assert upgrade._linked(tmp_path)


def test_a_folder_that_cant_be_inspected_counts_as_a_link(tmp_path):
    assert upgrade._linked(tmp_path / "not there")


def test_emptied_folders_go_deepest_first(tmp_path):
    root = tmp_path / "AirFare"
    release(root, "airfare/a/b/c/retired.py", "airfare/a/retired2.py")
    upgrade.remove_leftovers(root, data=root / "data")
    assert not (root / "airfare" / "a").exists() and (root / "airfare" / "__init__.py").exists()


@pytest.mark.parametrize("change", ["other version", "no end line", "wrong count", "cut short", "no version line", "not text", "empty"])
def test_a_manifest_that_isnt_this_versions_whole_list_deletes_nothing(tmp_path, change):
    root = tmp_path / "AirFare"
    release(root, "airfare/retired.py", version="9.1.0" if change == "other version" else __version__)
    path = root / "MANIFEST.txt"
    lines = path.read_text(encoding="utf-8").splitlines()
    if change == "no end line":
        path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
    elif change == "wrong count":
        path.write_text("\n".join([*lines[:-1], "# end: 99 files"]) + "\n", encoding="utf-8")
    elif change == "cut short":
        path.write_text("\n".join(lines[:2]) + "\n", encoding="utf-8")
    elif change == "no version line":
        path.write_text("\n".join(lines[1:]) + "\n", encoding="utf-8")
    elif change == "not text":
        path.write_bytes(b"\xff\xfe\x00")
    elif change == "empty":
        path.write_text("", encoding="utf-8")
    assert upgrade.remove_leftovers(root, data=root / "data") == []
    assert (root / "airfare" / "retired.py").exists()


def test_the_zip_starts_with_the_manifest_and_its_last_line_counts_the_files(tmp_path):
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        import make_portable
    finally:
        sys.path.remove(str(ROOT / "tools"))
    (tmp_path / "install.sh").write_bytes(b"#!/bin/sh\r\necho invented\r\n")
    (tmp_path / "one.py").write_text("invented", encoding="utf-8")
    files = [(tmp_path / "install.sh", "install.sh"), (tmp_path / "one.py", "airfare/one.py")]
    pages = {"Install-EN.html": "invented"}
    pages[make_portable.MANIFEST] = make_portable.manifest([name for _, name in files] + list(pages))
    target = tmp_path / "AirFare.zip"
    make_portable.write_zip(target, files, pages)
    with zipfile.ZipFile(target) as z:
        names = z.namelist()
        assert names[0] == "AirFare/MANIFEST.txt" and len(names) == len(set(names)) == 4
        manifest = z.read("AirFare/MANIFEST.txt").decode("utf-8")
        assert z.read("AirFare/install.sh") == b"#!/bin/sh\necho invented\n"
        z.extractall(tmp_path / "out")
    assert manifest.startswith(f"# AirFare {__version__}:") and manifest.endswith("# end: 4 files\n")
    assert upgrade.read_manifest(tmp_path / "out" / "AirFare") == {n.removeprefix("AirFare/") for n in names}


class _Folder:
    """A folder as a given system writes it, whichever one the tests run on."""

    def __init__(self, path: str, sep: str = "/"):
        self.path, self.sep = path, sep

    def __truediv__(self, name: str) -> str:
        return self.path + self.sep + name

    def resolve(self):
        return self


@pytest.mark.parametrize("pid, windows, confirmed", [(1, False, False), (0, False, False), (-1, False, False), (2, False, True),
                                                     (4, True, False), (0, True, False), (5, True, True)])
def test_system_process_ids_are_never_checked_or_stopped(monkeypatch, pid, windows, confirmed):
    monkeypatch.setattr(platform, "WINDOWS", windows)
    monkeypatch.setattr(platform, "MACOS", False)
    monkeypatch.setattr(upgrade, "command_line", lambda p: "/invented/AirFare/.venv/bin/python -m airfare service")
    if windows:
        monkeypatch.setattr(upgrade, "command_line", lambda p: r"D:\Invented\AirFare\.venv\Scripts\python.exe -m airfare service")
    assert upgrade.is_checker(pid, _Folder(r"D:\Invented\AirFare", "\\") if windows else _Folder("/invented/AirFare")) is confirmed


@pytest.mark.parametrize("command, confirmed", [
    ("{root}/.venv/bin/python -m airfare service", True),
    ("{root}/.venv/bin/python -m airfare service --skip-startup-check", True),
    ("{root}/.venv/bin/python -m airfare setup", False),
    ("{root}/.venv/bin/python -m airfare setup --page service", False),
    ("/usr/bin/python -m airfare service", False),
    ("{root}-2/.venv/bin/python -m airfare service", False),
    ("/mnt/copy{root}/.venv/bin/python -m airfare service", False),
    ("{root}/.venv2/bin/python -m airfare service", False),
    ("{root}/.venv/bin/python /tmp/-m airfare service", False),
    ("/usr/bin/vim {root}/.venv/notes service", False),
    ("", False)])
def test_only_this_folders_checker_is_confirmed(monkeypatch, command, confirmed):
    monkeypatch.setattr(platform, "WINDOWS", False)
    monkeypatch.setattr(platform, "MACOS", False)
    monkeypatch.setattr(upgrade, "command_line", lambda pid: command.format(root="/invented/AirFare"))
    assert upgrade.is_checker(4242, _Folder("/invented/AirFare")) is confirmed


def test_windows_command_lines_are_compared_as_windows_paths(monkeypatch):
    monkeypatch.setattr(platform, "WINDOWS", True)
    line = r'"D:\INVENTED\airfare\.venv\Scripts\pythonw.exe" -m airfare service'
    assert upgrade._names_environment(line, _Folder(r"D:\Invented\AirFare", "\\"))
    assert not upgrade._names_environment(line, _Folder(r"D:\Invented\Other", "\\"))


def test_a_mac_python_that_hides_the_environment_is_confirmed_by_how_it_was_started(monkeypatch):
    monkeypatch.setattr(platform, "WINDOWS", False)
    monkeypatch.setattr(platform, "MACOS", True)
    root = _Folder("/invented/AirFare")
    monkeypatch.setattr(upgrade, "command_line", lambda pid: "/invented/Python.app/Contents/MacOS/Python -m airfare service")
    monkeypatch.setattr(upgrade, "_run_text", lambda cmd: "/invented/Python -m airfare service __PYVENV_LAUNCHER__=/invented/AirFare/.venv/bin/python")
    assert upgrade.is_checker(4242, root)
    monkeypatch.setattr(upgrade, "_run_text", lambda cmd: "/invented/Python -m airfare service __PYVENV_LAUNCHER__=/invented/Other/.venv/bin/python")
    assert not upgrade.is_checker(4242, root)


def test_the_real_checker_process_is_confirmed_and_another_isnt(tmp_path):
    """A real process in a real environment, on each system: how each shows its command line, and what it hides."""
    root = tmp_path / "Invented АирФаре" / "AirFare"
    (root / "airfare").mkdir(parents=True)
    pid_file = root / "pid.txt"
    (root / "airfare" / "__init__.py").write_text("", encoding="utf-8")
    (root / "airfare" / "__main__.py").write_text(
        "import os, sys, time\n"
        f"open(r'{pid_file}', 'w').write(str(os.getpid()))\n"
        "time.sleep(60)\n", encoding="utf-8")
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(root / ".venv")], check=True, timeout=180)
    python = root / ".venv" / ("Scripts/python.exe" if platform.WINDOWS else "bin/python")
    process = subprocess.Popen([str(python), "-m", "airfare", "service"], cwd=root, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, creationflags=platform.NO_WINDOW)
    try:
        deadline = time.monotonic() + 60
        while not (pid_file.exists() and pid_file.read_text(encoding="ascii")) and time.monotonic() < deadline:
            time.sleep(0.1)
        pid = int(pid_file.read_text(encoding="ascii"))
        assert upgrade.is_checker(pid, root), upgrade.command_line(pid)
        assert not upgrade.is_checker(pid, tmp_path / "Other" / "AirFare")
        assert not upgrade.is_checker(os.getpid(), root)        # this test's own process
    finally:
        if platform.WINDOWS:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True, creationflags=platform.NO_WINDOW)
        else:
            process.kill()
        process.wait(timeout=30)


@pytest.fixture
def checker(tmp_path):
    """A background checker's lock held and its process id on record, as service.serve leaves them."""
    (tmp_path / "service.json").write_text(json.dumps({"pid": 424242}), encoding="utf-8")
    lock = platform.FileLock(tmp_path / "service.lock")
    assert lock.acquire()
    yield lock
    lock.release()


def test_an_unconfirmed_process_is_not_stopped(tmp_path, checker, monkeypatch):
    ended = []
    monkeypatch.setattr(upgrade, "_end", ended.append)
    monkeypatch.setattr(upgrade, "is_checker", lambda pid, root: False)
    assert upgrade.stop_checker(tmp_path, wait=0) is False and ended == []


@pytest.mark.parametrize("pid", [1, 0, -1, True, "424242", None])
def test_a_process_id_that_makes_no_sense_is_not_stopped(tmp_path, checker, monkeypatch, pid):
    ended = []
    monkeypatch.setattr(upgrade, "_end", ended.append)
    monkeypatch.setattr(upgrade, "command_line", lambda pid: "/invented/.venv/bin/python -m airfare service")
    (tmp_path / "service.json").write_text(json.dumps({"pid": pid}), encoding="utf-8")
    assert upgrade.stop_checker(tmp_path, wait=0, root=_Folder("/invented")) is False and ended == []


def test_the_lock_is_checked_again_right_before_stopping(tmp_path, checker, monkeypatch):
    ended = []
    monkeypatch.setattr(upgrade, "_end", ended.append)

    def it_quits_meanwhile(pid, root):
        checker.release()
        return True
    monkeypatch.setattr(upgrade, "is_checker", it_quits_meanwhile)
    assert upgrade.stop_checker(tmp_path, wait=0) is False and ended == []


def test_prepare_says_to_quit_by_hand_when_the_checker_stays(tmp_path, checker, monkeypatch, capsys):
    monkeypatch.setattr(upgrade, "DATA_DIR", tmp_path)
    monkeypatch.setattr(upgrade, "stop_checker", lambda: False)
    monkeypatch.setattr(upgrade, "stop_settings_server", lambda: False)
    monkeypatch.setattr(upgrade, "remove_leftovers", lambda: [])
    assert upgrade.prepare() == 1
    assert "Quit AirFare by hand" in capsys.readouterr().out


def test_prepare_says_nothing_when_no_checker_runs(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(upgrade, "DATA_DIR", tmp_path)
    monkeypatch.setattr(upgrade, "stop_checker", lambda: False)
    monkeypatch.setattr(upgrade, "stop_settings_server", lambda: False)
    monkeypatch.setattr(upgrade, "remove_leftovers", lambda: [])
    assert upgrade.prepare() == 0 and capsys.readouterr().out == ""


# ----- 7. small hardening --------------------------------------------------------------------------------------

@pytest.mark.parametrize("value, stops", [(0, 0), (2, 2), (9, 9), (10, 9), (10 ** 12, 9), (-5, 0), (None, 0), ("3", 3), ("many", 0),
                                          ([], 0), (float("inf"), 0), (float("nan"), 0), (2.9, 2)])
def test_a_feeds_stops_are_clamped(value, stops):
    assert extract.stop_count(value) == stops


def _sky_leg(stops, segments=()):
    return {"origin": {"displayCode": "ZZA"}, "destination": {"displayCode": "ZZB"}, "durationInMinutes": 120, "stopCount": stops,
            "departure": "2027-03-12T08:00:00", "arrival": "2027-03-12T12:00:00", "carriers": {"marketing": [{"name": "Invented Air"}]},
            "segments": list(segments)}


def test_a_feed_claiming_endless_stops_builds_nothing_endless():
    flight = extract._flight({"id": "x", "price": {"raw": 100, "formatted": "€100"}, "legs": [_sky_leg(10 ** 9)]})
    assert flight.legs[0].stops == 9 and flight.max_stops == 9
    assert flight.connections == ["?"] * 9 and flight.connections_unknown


def test_the_connections_list_is_capped_and_counts_as_unknown_when_cut():
    hops = [{"origin": {"displayCode": f"Z{i:02}"}, "destination": {"displayCode": f"Y{i:02}"}} for i in range(500)]
    flight = extract._flight({"id": "x", "price": {"raw": 100, "formatted": "€100"}, "legs": [_sky_leg(1, hops), _sky_leg(1, hops)]})
    assert len(flight.connections) == extract.MAX_CONNECTIONS and flight.connections[-1] == "?"
    assert flight.connections_unknown
    assert extract.capped_connections(["ZZA"] * extract.MAX_CONNECTIONS) == ["ZZA"] * extract.MAX_CONNECTIONS


def test_serpapi_stops_and_layovers_are_capped_too():
    segment = {"departure_airport": {"id": "ZZA", "time": "2027-03-12 08:00"}, "arrival_airport": {"id": "ZZB", "time": "2027-03-12 09:00"},
               "duration": 60, "airline": "Invented Air", "flight_number": "ZZ 1"}
    parsed = serpapi.parse({"best_flights": [{"flights": [segment] * 200, "price": 100, "layovers": [{"id": "ZZH", "duration": 60}] * 200}]}, "EUR", False)
    flight = parsed.flights[0]
    assert flight.legs[0].stops == 9 and len(flight.connections) == extract.MAX_CONNECTIONS


CSV_CASES = {"=1+1": "'=1+1", "+34": "'+34", "-5": "'-5", "@SUM(A1)": "'@SUM(A1)", "\tx": "'\tx", "\rx": "\"'\rx\"",
             '=HYPERLINK("a")': '"\'=HYPERLINK(""a"")"', "plain": "plain", "a=b": "a=b", "12": "12", "": "", "a,b": '"a,b"'}


def test_csv_cells_that_a_spreadsheet_would_run_get_an_apostrophe():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js isn't installed")
    source = historypage.PAGE
    code = source[source.index("function csvCell(v)"):source.index('$("#csv").onclick')]
    script = code + f"\nconsole.log(JSON.stringify(Object.fromEntries({json.dumps(list(CSV_CASES))}.map(k => [k, csvCell(k)])).valueOf()));\nconsole.log(JSON.stringify([csvCell(-5), csvCell(null), csvCell(undefined), csvCell(120)]));"
    out = subprocess.run([node, "-"], input=script, capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stderr
    first, second = out.stdout.strip().splitlines()
    assert json.loads(first) == CSV_CASES
    assert json.loads(second) == ["'-5", "", "", "120"]


def test_the_csv_export_uses_it():
    source = historypage.PAGE
    assert "r.map(cell)" in source and "const cell = csvCell;" in source


def test_logs_and_console_name_the_backup_folder_not_its_path(data, caplog, capsys, monkeypatch):
    with caplog.at_level(logging.INFO, logger="airfare.migrate"):
        result = migrate.ensure(data)
    assert result["backup"] == migrate.list_backups(data)[0]["name"]
    assert result["backup"] in caplog.text and str(data) not in caplog.text
    monkeypatch.setattr(migrate, "at_start", lambda: result)
    assert cli.cmd_migrate(None) == 0
    out = capsys.readouterr().out
    assert result["backup"] in out and str(data) not in out


@pytest.mark.parametrize("code, table, cap", [("EUR", RATES, 1e7), ("RUB", RATES, 1e9), ("GBP", RATES, 8e6), ("rub", RATES, 1e9),
                                              ("IDR", RATES, 1e14), ("EUR", None, 1e14)])
def test_the_price_cap_goes_by_the_currency(code, table, cap):
    assert money.price_cap(code, table) == cap


def _form(monkeypatch, currency="RUB", route=None, alerts=None, old_currency="EUR", old_route=None, old_alerts=None):
    old = {**config.DEFAULT_CONFIG, "currency": old_currency, "routes": [old_route] if old_route else [],
           **({"alerts": old_alerts} if old_alerts else {})}
    monkeypatch.setattr(webui, "load_config", lambda: old)
    monkeypatch.setattr(webui.money, "rates", lambda refresh=True: RATES)
    return {"sources": ["extension"], "currency": currency, "routes": [route] if route else [], **({"alerts": alerts} if alerts else {})}


def test_a_range_in_a_small_unit_may_pass_the_old_flat_cap(monkeypatch):
    form = _form(monkeypatch, "RUB", _route(price_max="50000000"), old_currency="RUB")
    assert webui.clean_config(form)["routes"][0]["price_max"] == 50000000


@pytest.mark.parametrize("value", ["1000000001", "1e300", "inf", "Infinity"])
def test_a_range_over_the_cap_has_its_own_message(monkeypatch, value):
    form = _form(monkeypatch, "RUB", _route(price_max=value), old_currency="RUB")
    with pytest.raises(webui.Problem) as e:
        webui.clean_config(form)
    assert "the price range is too high for this currency" in str(e.value)
    assert "Диапазон цен".lower() in e.value.text("ru").lower() and "demasiado alto" in e.value.text("es")
    problems = {}
    assert webui.clean_config(form, problems)["routes"] == [] and problems["r"] == "The price range is too high for this currency"


def test_a_range_is_checked_against_the_cap_after_converting(monkeypatch):
    old = _route(price_max=9_000_000.0)
    form = _form(monkeypatch, "GBP", _route(price_max=9_000_000.0), old_route=old)
    assert webui.clean_config(form)["routes"][0]["price_max"] == 7_200_000     # fine: 8,000,000 is the cap in pounds
    form = _form(monkeypatch, "EUR", _route(price_max=9_000_000.0), old_currency="GBP", old_route=old)
    with pytest.raises(webui.Problem, match="too high"):                       # £9,000,000 is €11,250,000
        webui.clean_config(form)


def test_an_alert_limit_over_the_cap_has_its_own_message_also_after_converting(monkeypatch):
    limit = {"on": True, "drop": 3, "max": 9_000_000}
    alerts = {"cheapest": limit, "fastest": {"on": True, "drop": 3, "max": None}, "best": {"on": True, "drop": 3, "max": None}}
    form = _form(monkeypatch, "EUR", alerts=alerts, old_currency="GBP", old_alerts=alerts)
    with pytest.raises(webui.Problem) as e:
        webui.clean_config(form)
    assert str(e.value) == "Cheapest: the price limit is too high for EUR"
    assert e.value.text("es") == "Más barato: el límite de precio es demasiado alto para EUR"
    form = _form(monkeypatch, "RUB", alerts={**alerts, "cheapest": {"on": True, "drop": 3, "max": 900_000_000}}, old_currency="RUB")
    assert webui.clean_config(form)["alerts"]["cheapest"]["max"] == 900_000_000
    form = _form(monkeypatch, "EUR", alerts={**alerts, "cheapest": {"on": True, "drop": 3, "max": "inf"}}, old_currency="GBP", old_alerts=alerts)
    with pytest.raises(webui.Problem, match="too high"):
        webui.clean_config(form)


def test_an_alert_limit_never_converts_down_to_nothing(monkeypatch):
    limit = {"on": True, "drop": 3, "max": 10}
    alerts = {"cheapest": limit, "fastest": {"on": True, "drop": 3, "max": None}, "best": {"on": True, "drop": 3, "max": None}}
    form = _form(monkeypatch, "EUR", alerts=alerts, old_currency="JPY", old_alerts=alerts)
    assert webui.clean_config(form)["alerts"]["cheapest"]["max"] == 1


def test_no_record_and_a_git_folder_is_a_developers_setup(tmp_path, monkeypatch):
    (tmp_path / ".venv").mkdir()
    venv = str(tmp_path / ".venv")
    assert upgrade.mismatch(tmp_path, prefix=venv)
    (tmp_path / ".git").mkdir()
    assert upgrade.mismatch(tmp_path, prefix=venv) is None
    (tmp_path / ".venv" / upgrade.RECORD_NAME).write_text(json.dumps({"app": "1.4.9"}), encoding="utf-8")
    assert upgrade.mismatch(tmp_path, prefix=venv)              # an install record: an update to finish after all


# ----- 8. what users are told ----------------------------------------------------------------------------------

def test_the_changelog_lists_these_fixes():
    section = text("CHANGELOG.md").split("## 1.4.1")[0]
    for words in ("Updating by unzipping", "Currency and price range", "Unfinished updates on Windows", "Backups and migration",
                  "One installer at a time", "The updater's safety", "Small hardening"):
        assert words in section


def test_data_kept_for_every_promise_of_contributing_after_a_failed_then_working_update(data, monkeypatch):
    """1.4.1's data comes through a failed attempt and a working one with every file byte for byte."""
    before = not_backups(files_of(data))

    def broken(folder):
        raise ValueError("invented")
    monkeypatch.setattr(migrate, "STEPS", {2: broken})
    with pytest.raises(migrate.MigrationError):
        migrate.ensure(data)
    monkeypatch.undo()
    assert migrate.ensure(data)["steps"] == [2]
    after = not_backups(files_of(data))
    after.pop("version.json")
    assert after == before and migrate.SCHEMA == 2
