"""API keys at rest: encrypted with Windows DPAPI in config.json, or in the keychain on macOS and Linux (a dict
in the tests, see conftest.keychain); plain text once loaded (secrets.py)."""
import json
import logging
import os
import subprocess
import threading
import urllib.request

import pytest

from airfare import __main__ as cli, config, platform, secrets, webui

KEY = "sk-test-0001-abcdef"
STORED = secrets.PREFIX if platform.WINDOWS else secrets.KEYCHAIN     # how config.json marks a protected key
REAL_GET, REAL_SET = secrets._keychain_get, secrets._keychain_set     # before conftest swaps them for a dict


@pytest.fixture
def config_file(monkeypatch, tmp_path):
    path = tmp_path / "config.json"
    monkeypatch.setattr(config, "CONFIG_FILE", path)
    monkeypatch.setattr(config, "_warned", set())
    return path


@pytest.fixture
def posix(monkeypatch):
    """The macOS and Linux code paths, on any system (the keychain itself is conftest's dict)."""
    monkeypatch.setattr(platform, "WINDOWS", False)


def test_a_key_round_trips():
    stored = secrets.protect(KEY)
    assert stored.startswith(STORED) and KEY not in stored
    assert secrets.unprotect(stored) == KEY
    assert secrets.protect("") == "" and secrets.unprotect("") == ""


def test_encrypted_values_are_told_apart_by_their_prefix():
    stored = secrets.protect(KEY)
    assert secrets.protected(stored) and not secrets.protected(KEY) and not secrets.protected(None)
    assert secrets.protect(stored) == stored            # never encrypted twice
    assert secrets.unprotect(KEY) == KEY                # a plain key from an older config.json works as it is


def test_a_key_that_cant_be_decrypted_counts_as_missing(config_file, monkeypatch, caplog, capsys):
    if platform.WINDOWS:
        with monkeypatch.context() as m:
            m.setattr(secrets, "ENTROPY", b"another program")
            elsewhere = secrets.protect(KEY)            # like a config.json from another Windows account
    else:
        elsewhere = "keychain:serpapi_key:0badc0de"     # like a config.json from another computer: no such entry
    config_file.write_text(json.dumps({
        "llm_provider": "none", "sources": ["serpapi"], "routes": [],
        "serpapi_key": elsewhere, "deepseek_api_key": "dpapi:AAAA", "openai_api_key": "dpapi:not base64!",
        "anthropic_api_key": secrets.protect(KEY, "anthropic_api_key")}), encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="airfare.config"):
        cfg = config.load_config()
        config.load_config()                            # loaded again: still one warning per key
    assert (cfg["serpapi_key"], cfg["deepseek_api_key"], cfg["openai_api_key"]) == ("", "", "")
    assert cfg["anthropic_api_key"] == KEY
    assert cfg["unreadable_keys"] == ["serpapi_key", "deepseek_api_key", "openai_api_key"]
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 3 and all("can't be decrypted" in w for w in warnings)
    assert KEY not in caplog.text and elsewhere not in caplog.text

    page = webui.public_config(cfg)
    assert page["saved_keys"]["serpapi_key"] == "" and "serpapi_key" in page["unreadable_keys"]
    assert cli.cmd_doctor(None) == 1
    out = capsys.readouterr().out
    assert f"The saved SerpApi key can't be decrypted on {secrets.ACCOUNT}" in out and KEY not in out
    if platform.WINDOWS:
        assert "on this Windows account" in out

    config.save_config(cfg)                             # the next save keeps only what this account can read
    stored = json.loads(config_file.read_text(encoding="utf-8"))
    assert stored["serpapi_key"] == "" and "unreadable_keys" not in stored
    assert "unreadable_keys" not in config.load_config()


def test_plain_keys_from_an_older_config_are_encrypted_at_the_next_save(config_file):
    config_file.write_text(json.dumps({"serpapi_key": KEY, "deepseek_api_key": "", "routes": []}), encoding="utf-8")
    cfg = config.load_config()
    assert cfg["serpapi_key"] == KEY and "unreadable_keys" not in cfg
    config.save_config(cfg)
    text = config_file.read_text(encoding="utf-8")
    assert KEY not in text and json.loads(text)["serpapi_key"].startswith(STORED)
    assert json.loads(text)["deepseek_api_key"] == ""
    assert cfg["serpapi_key"] == KEY                    # the caller's settings keep the key itself
    assert config.load_config()["serpapi_key"] == KEY


@pytest.mark.skipif(platform.WINDOWS, reason="Windows folders have no Unix permissions")
def test_config_json_is_readable_by_this_user_only(config_file):
    config.save_config({"serpapi_key": KEY, "routes": []})
    assert os.stat(config_file).st_mode & 0o777 == 0o600


def test_the_settings_page_still_gets_only_the_last_four_characters(config_file, monkeypatch):
    config_file.write_text(json.dumps({"language": "en", "routes": []}), encoding="utf-8")
    monkeypatch.setattr(webui, "serpapi_account", lambda key: {"total_searches_left": 248})
    monkeypatch.setattr(webui.runner, "write_history_page", lambda cfg: None)
    port = 8793
    srv = webui.Server(port)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    def post(path, body):
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(body).encode(), method="POST",
                                     headers={"X-AirFare": "1", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=3) as r:
            return json.loads(r.read())
    try:
        assert post("/api/keys", {"name": "serpapi_key", "value": "abcdef1234567890"})["saved_keys"]["serpapi_key"] == "…7890"
        post("/api/language", {"language": "es"})       # any other save keeps the key encrypted
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/state", headers={"X-AirFare": "1"})
        with urllib.request.urlopen(req, timeout=3) as r:
            page = json.loads(r.read())["config"]
    finally:
        srv.shutdown()
        srv.server_close()
    text = config_file.read_text(encoding="utf-8")
    assert "abcdef1234567890" not in text and json.loads(text)["serpapi_key"].startswith(STORED)
    assert page["serpapi_key"] == "" and page["saved_keys"]["serpapi_key"] == "…7890"
    assert STORED not in json.dumps(page)               # the stored value doesn't reach the page either
    assert config.load_config()["serpapi_key"] == "abcdef1234567890"


# ----- the keychain (macOS, Linux) ------------------------------------------------------------------------

def test_keys_go_to_the_keychain_under_their_name(posix, keychain, monkeypatch):
    sets = []
    real_set = secrets._keychain_set
    monkeypatch.setattr(secrets, "_keychain_set", lambda name, value: sets.append(name) or real_set(name, value))
    stored = secrets.protect(KEY, "serpapi_key")
    assert stored.startswith("keychain:serpapi_key:") and KEY not in stored and keychain == {"serpapi_key": KEY}
    assert secrets.protect(KEY, "serpapi_key") == stored and sets == ["serpapi_key"]     # unchanged: not saved again
    newer = secrets.protect("sk-newer", "serpapi_key")
    assert newer != stored and keychain["serpapi_key"] == "sk-newer"
    assert secrets.unprotect(newer) == "sk-newer"


def test_another_process_sees_a_changed_key(posix, keychain, monkeypatch):
    old = secrets.protect(KEY, "serpapi_key")
    assert secrets.unprotect(old) == KEY                # this process has read it once
    keychain["serpapi_key"] = "sk-from-settings"        # Settings, in its own process, saved a new key...
    newer = "keychain:serpapi_key:1234abcd"             # ...and config.json now names a new tag
    assert secrets.unprotect(newer) == "sk-from-settings"


def test_a_key_missing_from_the_keychain_cant_be_read(posix, keychain):
    with pytest.raises(secrets.SecretError):
        secrets.unprotect("keychain:openai_api_key:00000000")
    with pytest.raises(secrets.SecretError):
        secrets.unprotect("dpapi:AAAA")                 # encrypted by Windows on another computer


@pytest.mark.skipif(not platform.WINDOWS, reason="Windows reads only its own DPAPI values")
def test_windows_cant_read_a_keychain_reference():
    with pytest.raises(secrets.SecretError):
        secrets.unprotect("keychain:serpapi_key:0badc0de")


def test_without_a_keychain_keys_stay_as_plain_text(posix, monkeypatch, caplog):
    monkeypatch.setattr(secrets, "_keychain_set", lambda name, value: False)
    monkeypatch.setattr(secrets, "_warned_plain", False)
    with caplog.at_level(logging.WARNING, logger="airfare.secrets"):
        assert secrets.protect(KEY, "serpapi_key") == KEY
        assert secrets.protect("sk-other", "deepseek_api_key") == "sk-other"
    assert len(caplog.records) == 1 and "no keychain" in caplog.text and KEY not in caplog.text


@pytest.mark.parametrize("system", ["macos", "linux"])
def test_the_keychain_commands(monkeypatch, system):
    """`security` on macOS; `secret-tool` on Linux, with the key on stdin."""
    monkeypatch.setattr(platform, "MACOS", system == "macos")
    calls = []

    def run(cmd, **kw):
        calls.append((cmd, kw.get("input")))
        return subprocess.CompletedProcess(cmd, 0, KEY + "\n", "")
    monkeypatch.setattr(secrets.subprocess, "run", run)
    assert REAL_SET("serpapi_key", KEY) and REAL_GET("serpapi_key") == KEY
    (store, data), (lookup, _) = calls
    if system == "macos":
        assert store[:2] == ["security", "add-generic-password"] and "-U" in store and store[-2:] == ["-w", KEY]
        assert lookup == ["security", "find-generic-password", "-s", "AirFare", "-a", "serpapi_key", "-w"]
    else:
        assert store[:2] == ["secret-tool", "store"] and KEY not in store and data == KEY
        assert lookup == ["secret-tool", "lookup", "service", "AirFare", "key", "serpapi_key"]
