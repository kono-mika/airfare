"""What differs between Windows, macOS and Linux (platform.py). The macOS and Linux code paths are also run on
the other systems, with platform.WINDOWS/MACOS/LINUX switched and the programs they'd start recorded."""
import argparse
import plistlib
import subprocess
import sys
from pathlib import Path, PurePosixPath

import pytest

from airfare import __main__ as cli, i18n, links, notify, platform, runner


@pytest.fixture
def system(monkeypatch):
    """Switch platform.py to another system: system("macos") or system("linux")."""
    def switch(name: str):
        monkeypatch.setattr(platform, "WINDOWS", name == "windows")
        monkeypatch.setattr(platform, "MACOS", name == "macos")
        monkeypatch.setattr(platform, "LINUX", name == "linux")
    return switch


@pytest.fixture
def started(monkeypatch):
    """The programs platform.py starts, instead of starting them: [(cmd, options)]."""
    calls = []

    def popen(cmd, **kw):
        calls.append((cmd, kw))
    monkeypatch.setattr(platform.subprocess, "Popen", popen)
    return calls


@pytest.fixture
def home(monkeypatch, tmp_path):
    monkeypatch.setattr(platform.Path, "home", lambda: tmp_path)
    for var in ("XDG_DATA_HOME", "XDG_CONFIG_HOME"):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


# ----- locks and processes ----------------------------------------------------------------------------------

def test_a_file_lock_is_held_until_released(tmp_path):
    first, second = platform.FileLock(tmp_path / "x.lock"), platform.FileLock(tmp_path / "x.lock")
    assert first.acquire()
    assert not second.acquire()                # also from the same process, as from another one
    first.release()
    assert second.acquire()
    second.release()
    second.release()                           # releasing twice is harmless


def test_a_check_is_busy_while_another_holds_the_lock(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "LOCK_FILE", tmp_path / "run.lock")
    with runner.ProcessLock():
        with pytest.raises(runner.Busy):
            with runner.ProcessLock():
                pass
    with runner.ProcessLock():                 # free again afterwards
        pass


def test_background_processes_use_the_windowless_python():
    python = platform.background_python()
    if platform.WINDOWS and Path(sys.executable).with_name("pythonw.exe").exists():
        assert Path(python).name.lower() == "pythonw.exe"
    elif not platform.WINDOWS:
        assert python == sys.executable


@pytest.mark.parametrize("name", ["windows", "linux"])
def test_detached_processes(system, started, tmp_path, name):
    if name == "windows" and not platform.WINDOWS:
        pytest.skip("Windows' process flags")
    system(name)
    platform.start_detached(["python", "-m", "airfare", "service"], tmp_path)
    cmd, kw = started[0]
    assert cmd == ["python", "-m", "airfare", "service"] and kw["cwd"] == tmp_path
    if name == "windows":
        assert kw["creationflags"] == subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        assert kw["start_new_session"] and kw["stdout"] == subprocess.DEVNULL and "creationflags" not in kw


def test_process_flags_are_nothing_off_windows():
    if platform.WINDOWS:
        assert platform.NO_WINDOW == subprocess.CREATE_NO_WINDOW and platform.tree_options() == {"creationflags": platform.NO_WINDOW}
    else:
        assert platform.NO_WINDOW == platform.NEW_CONSOLE == platform.DETACHED == 0
        assert platform.tree_options() == {"start_new_session": True}


def test_a_program_that_isnt_running():
    assert not platform.running("no-such-program-airfare.exe" if platform.WINDOWS else "no-such-airfare")
    assert not platform.running(("no-such-a", "no-such-b"))


def test_running_programs_are_found_by_pgrep_off_windows(system, monkeypatch):
    system("linux")
    asked = []
    monkeypatch.setattr(platform.subprocess, "run",
                        lambda cmd, **kw: asked.append(cmd) or subprocess.CompletedProcess(cmd, 0 if cmd[-1] == "chromium" else 1))
    assert platform.running(("chrome", "chromium")) and asked == [["pgrep", "-x", "chrome"], ["pgrep", "-x", "chromium"]]
    assert not platform.running("firefox")


# ----- browsers, files and terminals ------------------------------------------------------------------------

def test_a_mac_browser_opens_behind_the_window_in_use(system, started):
    system("macos")
    exe = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    platform.start_browser(exe, ["--new-window", "http://127.0.0.1:8766/start"])
    assert started[0][0] == ["open", "-g", "-a", str(Path("/Applications/Google Chrome.app")), "--args",
                             "--new-window", "http://127.0.0.1:8766/start"]


def test_a_linux_browser_is_its_command(system, started):
    system("linux")
    platform.start_browser(Path("/usr/bin/firefox"), ["--new-window", "http://127.0.0.1:8766/start"])
    assert started[0][0] == [str(Path("/usr/bin/firefox")), "--new-window", "http://127.0.0.1:8766/start"]
    assert started[0][1]["start_new_session"]


@pytest.mark.parametrize("name, program", [("macos", "open"), ("linux", "xdg-open")])
def test_folders_open_in_the_file_manager(system, started, name, program):
    system(name)
    platform.open_path(Path("/opt/airfare/extension"))
    assert started[0][0] == [program, str(Path("/opt/airfare/extension"))]


def test_a_terminal_window_on_linux(system, started, monkeypatch, tmp_path):
    system("linux")
    monkeypatch.setattr(platform.shutil, "which", lambda name: "/usr/bin/xterm" if name == "xterm" else None)
    platform.open_terminal("AirFare: Claude login", ["/opt/air fare/claude", "auth", "login"], tmp_path)
    cmd = started[0][0]
    assert cmd[:4] == ["/usr/bin/xterm", "-e", "sh", "-c"]
    assert "'/opt/air fare/claude' auth login" in cmd[4] and "read _" in cmd[4]      # quoted; stays open after
    monkeypatch.setattr(platform.shutil, "which", lambda name: None)
    with pytest.raises(platform.NoTerminal, match="auth login"):
        platform.open_terminal("AirFare", ["claude", "auth", "login"], tmp_path)


def test_a_terminal_window_on_macos(system, started, tmp_path):
    system("macos")
    platform.open_terminal("AirFare: ChatGPT login", ["codex", "login"], tmp_path)
    cmd = started[0][0]
    assert cmd[0] == "osascript" and "do script (item 1 of argv)" in cmd and cmd[-1].endswith("read _")
    assert "codex login" in cmd[-1]            # the command travels as an argument, never inside the script


# ----- notifications ----------------------------------------------------------------------------------------

@pytest.fixture
def ran(monkeypatch):
    calls = []
    monkeypatch.setattr(platform.subprocess, "run",
                        lambda cmd, **kw: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0, "", ""))
    return calls


def test_a_linux_alert_has_buttons_when_notify_send_can_report_clicks(system, started, ran, monkeypatch):
    system("linux")
    monkeypatch.setattr(platform, "_notify_send_actions", lambda: True)
    assert notify.alert("LOW PRICE ✈ R: 99 €", ["Cheapest: <99> & more", ""],
                        [("Book now", "https://example.test/b?x=1&y=2"), ("Dashboard", "airfare:dashboard")],
                        open_path="airfare:dashboard")
    cmd, kw = started[0]
    assert cmd[:3] == ["sh", "-c", platform._CLICK_SCRIPT] and "--urgency=critical" in cmd and "--wait" in cmd
    assert "--action=default=Open" in cmd and "--action=b0=Book now" in cmd and "--action=b1=Dashboard" in cmd
    assert cmd[-2:] == ["LOW PRICE ✈ R: 99 €", "Cheapest: &lt;99&gt; &amp; more"]      # the body is markup
    assert kw["env"]["T_default"] == "airfare:dashboard" and kw["env"]["T_b0"] == "https://example.test/b?x=1&y=2"
    assert kw["start_new_session"] and not ran


def test_a_linux_notification_without_buttons(system, started, ran, monkeypatch, tmp_path):
    system("linux")
    monkeypatch.setattr(platform, "_notify_send_actions", lambda: False)
    assert notify.toast("AirFare", "No internet connection.", tmp_path / "latest.html")
    assert not started and ran[0][0] == "notify-send" and ran[0][-2:] == ["AirFare", "No internet connection."]
    assert "--urgency=critical" not in ran[0]


def test_the_click_script_opens_only_what_it_was_given():
    script = platform._CLICK_SCRIPT
    assert "eval" not in script and '"$@"' in script and 'exec xdg-open "$t"' in script


@pytest.mark.parametrize("notifier", [None, "/opt/homebrew/bin/terminal-notifier"])
def test_a_mac_notification(system, ran, monkeypatch, tmp_path, notifier):
    system("macos")
    monkeypatch.setattr(platform, "which", lambda name: notifier)
    page = tmp_path / "latest.html"
    assert notify.alert("LOW PRICE ✈ R", ["Cheapest: 99", "Book the direct one."], [("Book now", "https://e.test/b")],
                        open_path=page)
    cmd = ran[0]
    if notifier:
        assert cmd[0] == notifier and cmd[cmd.index("-open") + 1] == page.resolve().as_uri() and "-sound" in cmd
        assert cmd[cmd.index("-message") + 1] == "Cheapest: 99\nBook the direct one."
    else:
        assert cmd[0] == "osascript" and cmd[-2:] == ["LOW PRICE ✈ R", "Cheapest: 99\nBook the direct one."]
        assert any('sound name "Glass"' in a for a in cmd)        # the text goes in as arguments, not script


# ----- the display language ---------------------------------------------------------------------------------

def test_the_system_language_picks_one_airfare_speaks(monkeypatch):
    for code, lang in (("es", "es"), ("ru", "ru"), ("de", "en"), ("", "en")):
        monkeypatch.setattr(platform, "ui_language", lambda: code)
        assert i18n.system_language() == lang


@pytest.mark.skipif(platform.WINDOWS, reason="the locale variables (Windows asks its display language)")
def test_the_language_comes_from_the_locale_variables(monkeypatch):
    monkeypatch.setattr(platform, "_mac_language", lambda: "")
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("LANG", "es_ES.UTF-8")
    assert platform.ui_language() == "es"
    monkeypatch.setenv("LC_ALL", "C.UTF-8")             # C says nothing about the language
    assert platform.ui_language() == "es"
    monkeypatch.setenv("LANGUAGE", "ru_RU:en")
    assert platform.ui_language() == "ru"


def test_the_mac_language_list_is_read(monkeypatch):
    out = '(\n    "es-ES",\n    en\n)\n'
    monkeypatch.setattr(platform.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, out, ""))
    assert platform._mac_language.__wrapped__() == "es"
    out = "(\n    ru\n)\n"
    assert platform._mac_language.__wrapped__() == "ru"


# ----- desktop entries, links and start-at-login ------------------------------------------------------------

def test_desktop_entry_arguments_are_quoted_as_the_spec_says():
    assert platform.exec_arg("/home/me/airfare/.venv/bin/python") == "/home/me/airfare/.venv/bin/python"
    assert platform.exec_arg("/home/me/My Apps/python") == '"/home/me/My Apps/python"'
    # Inside quotes, " ` $ \\ take a backslash; then every backslash is doubled, and % is written %%.
    assert platform.exec_arg('/a "b" $HOME\\x 50%') == '"/a \\\\"b\\\\" \\\\$HOME\\\\\\\\x 50%%"'


def test_linux_desktop_entry_opens_links_and_settings(system, home, monkeypatch):
    system("linux")
    root = PurePosixPath("/opt/My AirFare")
    path = platform.add_app_entry(root)
    text = path.read_text(encoding="utf-8")
    assert path == home / ".local" / "share" / "applications" / "airfare.desktop"
    assert f'Exec="{root / ".venv/bin/python"}" -m airfare link %u\n' in text
    assert "MimeType=x-scheme-handler/airfare;\n" in text and f"Path={root}\n" in text


def test_links_register_the_desktop_entry_on_linux(system, home, monkeypatch, tmp_path):
    system("linux")
    python = tmp_path / "python"
    python.touch()
    monkeypatch.setattr(platform, "venv_python", lambda root: python)
    monkeypatch.setattr(links, "_registered", None)
    calls = []
    monkeypatch.setattr(links.subprocess, "run",
                        lambda cmd, **kw: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0, "", ""))
    assert links.register() and links.for_dashboard(tmp_path / "latest.html") == "airfare:dashboard"
    assert ["xdg-mime", "default", "airfare.desktop", "x-scheme-handler/airfare"] in calls
    assert (home / ".local" / "share" / "applications" / "airfare.desktop").exists()


def test_macos_registers_no_link_type(system, monkeypatch, tmp_path):
    system("macos")
    monkeypatch.setattr(links, "_registered", None)
    assert links.register() is False and links.for_dashboard(tmp_path / "latest.html") == tmp_path / "latest.html"


def test_start_at_login_on_linux(system, home):
    system("linux")
    path = platform.add_login_item(PurePosixPath("/opt/airfare"))
    assert path == home / ".config" / "autostart" / "airfare.desktop"
    assert "Exec=/opt/airfare/.venv/bin/python -m airfare service\n" in path.read_text(encoding="utf-8")
    platform.remove_login_item()
    assert not path.exists()


def test_start_at_login_on_macos(system, home, monkeypatch):
    system("macos")
    booted = []
    monkeypatch.setattr(platform.subprocess, "run", lambda cmd, **kw: booted.append(cmd))
    monkeypatch.setattr(platform.os, "getuid", lambda: 501, raising=False)
    path = platform.add_login_item(PurePosixPath("/Users/me/AirFare"))
    assert path == home / "Library" / "LaunchAgents" / "AirFare.FlightPrices.plist"
    plist = plistlib.loads(path.read_bytes())
    assert plist["ProgramArguments"] == ["/Users/me/AirFare/.venv/bin/python", "-m", "airfare", "service"]
    assert plist["RunAtLoad"] and plist["WorkingDirectory"] == "/Users/me/AirFare"
    assert plist["LimitLoadToSessionType"] == "Aqua"
    platform.remove_login_item()
    assert not path.exists() and booted == [["launchctl", "bootout", "gui/501/AirFare.FlightPrices"]]


@pytest.mark.parametrize("url, opened", [
    (None, ("settings", False)), ("airfare:dashboard", ("dashboard", False)), ("AIRFARE://history/", ("history", False)),
    ("airfare:settings?x=1", ("settings", False)), ("airfare:start", ("settings", True)),
    ("airfare:run-something", None), ("https://example.test/", None)])
def test_the_link_command_opens_only_its_four_pages(monkeypatch, url, opened):
    seen = []
    monkeypatch.setattr(cli, "cmd_setup", lambda args: seen.append((args.page, args.no_open)) or 0)
    code = cli.cmd_link(argparse.Namespace(url=url))
    assert (code, seen) == ((0, [opened]) if opened else (2, []))
