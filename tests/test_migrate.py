"""Updates never lose data: the data folder's version, its migration and backups, settings that survive going to
a newer or older AirFare, and the clean-up of files an older release left behind.

tests/fixtures/data-1.4.1/ is a complete data folder in 1.4.1's format, made of invented data (see its README)."""
import json
import shutil
import sys
from pathlib import Path

import pytest

from airfare import __main__ as cli, __version__, cleanup, config, migrate, platform, upgrade, webui

FIXTURE = Path(__file__).parent / "fixtures" / "data-1.4.1"
ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def data(tmp_path, monkeypatch):
    """A copy of the 1.4.1 data folder, as AirFare's data folder."""
    folder = tmp_path / "data"
    shutil.copytree(FIXTURE, folder, ignore=shutil.ignore_patterns("README.txt"))
    monkeypatch.setattr(migrate, "DATA_DIR", folder)
    monkeypatch.setattr(config, "CONFIG_FILE", folder / "config.json")
    return folder


def snapshot(folder: Path) -> dict[str, bytes]:
    """Every file and its bytes (but the lock file, which only says that a migration may be running)."""
    return {f.relative_to(folder).as_posix(): f.read_bytes() for f in sorted(folder.rglob("*"))
            if f.is_file() and f.name != migrate.LOCK_NAME}


def read(folder: Path, name: str):
    return json.loads((folder / name).read_text(encoding="utf-8"))


# ----- migrating 1.4.1's data --------------------------------------------------------------------------------

def test_a_folder_without_version_json_is_1_4_1s(data):
    assert not (data / "version.json").exists()
    assert migrate.read_version(data) == {"app": "1.4.1", "schema": 1}
    assert migrate.SCHEMA == 2


def test_migrating_1_4_1_data_keeps_every_route_record_reference_and_conversation(data):
    before = snapshot(data)
    result = migrate.ensure(data)
    assert result["steps"] == [2] and not result["newer"]
    assert read(data, "version.json")["app"] == __version__ and read(data, "version.json")["schema"] == 2
    after = {k: v for k, v in snapshot(data).items() if not k.startswith("backups/")}
    after.pop("version.json")
    assert after == before                       # 1.4.1's files come through byte for byte

    cfg = config.load_config()
    assert [r["id"] for r in cfg["routes"]] == ["fx01ab", "fx02cd"]
    assert cfg["routes"][0]["children"] == [7] and cfg["routes"][1]["manual_pages"][0]["url"].endswith("/270502/")
    assert cfg["alerts"]["fastest"] == {"on": True, "drop": 3, "max": 250} and cfg["schedule"] == "both"
    assert [r["id"] for r in read(data, "price_history.json")] == [f"inv0000rec0{i}" for i in range(1, 6)]
    assert [r["id"] for r in read(data, "price_research.json")] == ["inv0000look1", "inv0000look2"]
    assert set(read(data, "dashboard.json")["routes"]) == {"fx01ab", "fx02cd", "fx03ef"}
    history = read(data, "history.json")
    assert set(history["routes"]["fx01ab"]["alert_refs"]) == {"cheapest", "fastest", "best"}
    assert history["routes"]["fx02cd"]["alert_ref"]["cheapest"] == 655.0     # an older reference stays as it is
    state = read(data, "state.json")
    assert state["session_id"] == "11111111-2222-4333-8444-555555555555"
    assert state["deepseek"]["session_id"] == "invented-deepseek-0001"
    assert len(read(data, "deepseek/invented-deepseek-0001.json")) == 5


def test_the_backup_is_made_once_and_a_second_start_changes_nothing(data):
    migrate.ensure(data)
    backups = migrate.list_backups(data)
    assert len(backups) == 1 and backups[0]["app"] == "1.4.1" and backups[0]["bytes"] > 0
    saved = data / "backups" / backups[0]["name"]
    assert sorted(f.relative_to(saved).as_posix() for f in saved.rglob("*") if f.is_file()) == [
        "config.json", "dashboard.json", "deepseek/invented-deepseek-0001.json", "history.json", "price_history.json",
        "price_research.json", "rates.json", "state.json"]       # reports and logs aren't rewritten, so not copied
    assert (saved / "config.json").read_bytes() == (FIXTURE / "config.json").read_bytes()

    once = snapshot(data)
    second = migrate.ensure(data)
    assert second["steps"] == [] and second["backup"] is None
    assert snapshot(data) == once and len(migrate.list_backups(data)) == 1


def test_a_new_data_folder_only_gets_its_version(tmp_path):
    result = migrate.ensure(tmp_path / "new")
    assert result["steps"] == [] and result["backup"] is None
    assert migrate.read_version(tmp_path / "new")["schema"] == migrate.SCHEMA
    assert not (tmp_path / "new" / "backups").exists()


def test_the_newest_three_backups_are_kept(data):
    made = [migrate.backup(data, "1.4.1").name for _ in range(4)]
    assert [b["name"] for b in migrate.list_backups(data)] == made[:0:-1]       # newest first, the oldest gone
    assert not (data / "backups" / made[0]).exists()


def test_settings_from_before_alert_kinds_become_three_kinds_and_keep_the_rest(data):
    cfg = read(data, "config.json")
    del cfg["alerts"]
    cfg.update(min_drop_percent=7, serpapi_key="dpapi:fake", future_option={"x": 1})
    (data / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    migrate.ensure(data)
    after = read(data, "config.json")
    assert "min_drop_percent" not in after
    assert after["alerts"] == {k: {"on": True, "drop": 7, "max": None} for k in ("cheapest", "fastest", "best")}
    assert after["serpapi_key"] == "dpapi:fake"            # changed as stored: still encrypted
    assert after["future_option"] == {"x": 1} and [r["id"] for r in after["routes"]] == ["fx01ab", "fx02cd"]
    migrate._alert_kinds(data)                                                 # a second run changes nothing
    assert read(data, "config.json") == after


def test_a_failed_step_puts_the_data_back(data, monkeypatch):
    before = snapshot(data)

    def broken(folder):
        (folder / "config.json").write_text("{}", encoding="utf-8")
        raise ValueError("invented failure")
    monkeypatch.setattr(migrate, "STEPS", {2: broken})
    with pytest.raises(migrate.MigrationError, match="put back as it was"):
        migrate.ensure(data)
    after = snapshot(data)
    assert not any(k.startswith("backups/") for k in before)
    assert {k: v for k, v in after.items() if not k.startswith("backups/")} == before
    assert not (data / "version.json").exists()              # the next start tries again


def test_a_migration_another_process_finished_is_not_run_again(data, monkeypatch):
    real = migrate._lock

    def other_process_first(folder):
        lock = real(folder)
        (folder / "version.json").write_text(json.dumps({"app": __version__, "schema": 2}), encoding="utf-8")
        return lock
    monkeypatch.setattr(migrate, "_lock", other_process_first)
    result = migrate.ensure(data)
    assert result["steps"] == [] and migrate.list_backups(data) == []


def test_the_lock_is_one_file_every_process_sees(data):
    lock = platform.FileLock(data / migrate.LOCK_NAME)
    assert lock.acquire()
    try:
        assert not platform.FileLock(data / migrate.LOCK_NAME).acquire()       # a second migration has to wait
    finally:
        lock.release()


# ----- data from a newer AirFare -----------------------------------------------------------------------------

@pytest.mark.parametrize("written", [{"app": "9.1.0", "schema": 99}, {"app": "9.1.0", "schema": 2}])
def test_data_from_a_newer_airfare_is_never_migrated_or_rewritten(data, written, monkeypatch, capsys):
    (data / "version.json").write_text(json.dumps(written), encoding="utf-8")
    before = snapshot(data)
    result = migrate.ensure(data)
    assert result["newer"] and result["steps"] == [] and snapshot(data) == before
    status = migrate.status(data)
    assert status["newer"] and status["message"] == "This data was written by AirFare 9.1.0; install that version or newer"

    monkeypatch.setattr(upgrade, "mismatch", lambda *a, **k: None)
    cli.cmd_doctor(None)
    assert "This data was written by AirFare 9.1.0; install that version or newer" in capsys.readouterr().out
    assert cli.cmd_migrate(None) == 0 and snapshot(data) == before


def test_settings_say_when_the_data_is_newer():
    page = (ROOT / "airfare" / "static" / "index.html").read_text(encoding="utf-8")
    assert 'id="data-newer"' in page and "data_version" in page
    assert 't("This data was written by AirFare {version}; install that version or newer"' in page


# ----- settings survive going to a newer or older AirFare ----------------------------------------------------

def test_save_config_keeps_keys_and_route_fields_it_doesnt_know(data):
    cfg = read(data, "config.json")
    cfg["future_option"] = {"from": "a newer AirFare"}
    cfg["routes"][0]["future_field"] = "kept"
    (data / "config.json").write_text(json.dumps(cfg), encoding="utf-8")

    loaded = config.load_config()
    loaded.pop("future_option")                        # a caller that only knows today's keys
    loaded["routes"] = [{k: v for k, v in r.items() if k in config.ROUTE_FIELDS} for r in loaded["routes"]]
    loaded["currency"] = "GBP"
    config.save_config(loaded)
    stored = read(data, "config.json")
    assert stored["future_option"] == {"from": "a newer AirFare"} and stored["currency"] == "GBP"
    assert stored["routes"][0]["future_field"] == "kept" and "future_field" not in stored["routes"][1]
    assert "min_drop_percent" not in stored


def test_saving_in_settings_keeps_what_a_newer_airfare_stored(data, monkeypatch):
    cfg = read(data, "config.json")
    cfg["future_option"] = 1
    cfg["routes"][0]["future_field"] = "kept"
    (data / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    form = config.load_config()
    form["routes"][0]["name"] = "Renamed invented route"
    form["llm_provider"] = "none"                      # the invented data has no DeepSeek key
    saved = webui.clean_config(form, renew_ids=True)
    assert set(saved["routes"][0]) == set(config.ROUTE_FIELDS)        # what the form writes, and nothing else
    config.save_config(saved)
    stored = read(data, "config.json")
    assert stored["future_option"] == 1 and stored["routes"][0]["future_field"] == "kept"
    assert [r["id"] for r in stored["routes"]] == ["fx01ab", "fx02cd"] and stored["routes"][0]["name"] == "Renamed invented route"


# ----- Clean up: the backups ---------------------------------------------------------------------------------

def test_clean_up_lists_the_backups_and_start_over_keeps_them(data, monkeypatch):
    for name in ("history", "state"):
        monkeypatch.setattr(cleanup, f"load_{name}", lambda n=name: read(data, f"{n}.json"))
        monkeypatch.setattr(cleanup, f"save_{name}", lambda v: None)
    for mod, attr, value in ((cleanup.pricelog, "LOG_FILE", data / "price_history.json"),
                             (cleanup.pricelog, "RESEARCH_FILE", data / "price_research.json"),
                             (cleanup.dashboard, "STORE_FILE", data / "dashboard.json"),
                             (cleanup.dashboard, "REPORTS_DIR", data / "reports"),
                             (cleanup, "REPORTS_DIR", data / "reports"), (cleanup, "LOGS_DIR", data / "logs")):
        monkeypatch.setattr(mod, attr, value)
    migrate.ensure(data)
    migrate.backup(data, __version__)
    listed = cleanup.summary(config.load_config())["backups"]
    assert len(listed) == 2 and all(b["bytes"] > 0 and b["created"] for b in listed)

    cleanup.run("everything", {}, config.load_config())
    assert len(migrate.list_backups(data)) == 2                         # Start over leaves them alone
    with pytest.raises(cleanup.Problem):
        cleanup.run("backups", {}, config.load_config())
    assert cleanup.run("backups", {"names": [listed[1]["name"], "../config.json"]}, config.load_config(), dry=True) == 1
    assert cleanup.run("backups", {"names": [listed[1]["name"]]}, config.load_config()) == 1
    assert [b["name"] for b in migrate.list_backups(data)] == [listed[0]["name"]]
    assert cleanup.run("backups", {"everything": True}, config.load_config()) == 1
    assert migrate.list_backups(data) == [] and (data / "config.json").exists()


def test_a_folder_in_backups_that_isnt_a_backup_is_never_listed_or_deleted(data):
    other = data / "backups" / "my own notes"
    other.mkdir(parents=True)
    (other / "keep.txt").write_text("mine", encoding="utf-8")
    assert migrate.list_backups(data) == [] and migrate.delete_backups(everything=True, data=data) == 0
    assert (other / "keep.txt").exists()


# ----- unzipping a release over the old folder ---------------------------------------------------------------

def make_release(root: Path, listed: list[str], extra: list[str]) -> None:
    for name in listed + extra:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(name, encoding="utf-8")
    (root / "MANIFEST.txt").write_text("# invented manifest\n" + "\n".join(listed + ["MANIFEST.txt"]) + "\n",
                                       encoding="utf-8")


LISTED = ["airfare/__init__.py", "airfare/config.py", "airfare/static/index.html", "extension/manifest.json",
          "tools/make_firefox.py", "launcher/AirFare.cs", "assets/airfare.ico", "install.ps1", "README.md"]
LEFT_OVER = ["airfare/retired_module.py", "airfare/__pycache__/retired_module.cpython-312.pyc",
             "airfare/static/old_page.html", "extension/old.js", "extension-firefox/old.js", "launcher/old.cs",
             "assets/old.png", "tools/old_tool.py"]
NOT_OURS = ["data/config.json", "data/backups/1.4.1-20261030-1200/config.json", "data/reports/2026-10-28_080000-prices.md",
            ".venv/Lib/site-packages/pkg/module.py", ".venv/airfare-install.json", "my notes.txt", "AirFare.exe",
            "airfare/mydata/config.json"]


def test_the_manifest_clean_up_deletes_only_left_over_code_and_never_data_or_venv(tmp_path):
    make_release(tmp_path, LISTED, LEFT_OVER + NOT_OURS)
    removed = upgrade.remove_leftovers(tmp_path, data=tmp_path / "airfare" / "mydata")   # AIRFARE_DATA anywhere
    assert sorted(removed) == sorted(LEFT_OVER)
    for name in LISTED + NOT_OURS:
        assert (tmp_path / name).read_text(encoding="utf-8") == name, name
    assert not (tmp_path / "airfare" / "__pycache__").exists()            # emptied folders go, the code folders stay
    assert (tmp_path / "extension-firefox").is_dir() and not any((tmp_path / "extension-firefox").iterdir())


@pytest.mark.parametrize("why", ["no manifest", "unfinished unzip", "git checkout"])
def test_without_a_complete_release_nothing_is_deleted(tmp_path, why):
    make_release(tmp_path, LISTED, LEFT_OVER)
    if why == "no manifest":
        (tmp_path / "MANIFEST.txt").unlink()
    elif why == "unfinished unzip":
        (tmp_path / "airfare" / "config.py").unlink()
    else:
        (tmp_path / ".git").mkdir()
    assert upgrade.remove_leftovers(tmp_path, data=tmp_path / "data") == []
    assert all((tmp_path / name).exists() for name in LEFT_OVER)


def test_the_release_zip_lists_every_file_in_its_manifest():
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        import make_portable
    finally:
        sys.path.remove(str(ROOT / "tools"))
    text = make_portable.manifest(["airfare/config.py", "airfare/__init__.py", "Install-EN.html"])
    lines = [line for line in text.splitlines() if not line.startswith("#")]
    assert lines == ["Install-EN.html", "MANIFEST.txt", "airfare/__init__.py", "airfare/config.py"]
    assert text.startswith(f"# AirFare {__version__}:")


def test_the_install_record_tells_when_the_code_is_newer_than_its_setup(tmp_path, monkeypatch):
    (tmp_path / ".venv").mkdir()
    (tmp_path / "requirements.txt").write_text("invented-package>=1\n", encoding="utf-8")
    venv = str(tmp_path / ".venv")
    assert "an earlier version" in upgrade.mismatch(tmp_path, prefix=venv)          # 1.4.1 kept no record
    rec = upgrade.write_record(tmp_path)
    assert rec["app"] == __version__ and len(rec["requirements"]) == 64
    assert upgrade.mismatch(tmp_path, prefix=venv) is None
    (tmp_path / "requirements.txt").write_text("invented-package>=2\n", encoding="utf-8")
    for windows, how in ((False, "Run sh install.sh to finish the update."), (True, "Start AirFare.exe to finish the update.")):
        monkeypatch.setattr(platform, "WINDOWS", windows)
        assert upgrade.mismatch(tmp_path, prefix=venv).endswith(how)
    assert upgrade.mismatch(tmp_path, prefix=str(tmp_path / "another-python")) is None   # not AirFare's environment


def test_python_m_airfare_stops_until_the_update_is_finished(monkeypatch, capsys):
    monkeypatch.setattr(upgrade, "mismatch", lambda *a, **k: "Run sh install.sh to finish the update.")
    monkeypatch.setattr(upgrade, "note", lambda text: None)
    assert cli.main(["run"], check_install=True) == 4
    assert "Run sh install.sh to finish the update." in capsys.readouterr().err


def test_the_previous_versions_checker_is_stopped(tmp_path, monkeypatch):
    ended = []
    monkeypatch.setattr(upgrade, "_end", lambda pid: ended.append(pid) or lock.release())
    (tmp_path / "service.json").write_text(json.dumps({"pid": 424242}), encoding="utf-8")
    assert not upgrade.stop_checker(tmp_path)                    # no lock file: no checker ever ran here
    lock = platform.FileLock(tmp_path / "service.lock")
    assert lock.acquire()                                        # a checker holds it, as service.serve does
    assert upgrade.stop_checker(tmp_path, wait=60) and ended == [424242]
    assert not upgrade.stop_checker(tmp_path)


def test_finishing_the_update_records_it_and_starts_the_checker_the_settings_need(tmp_path, monkeypatch):
    from airfare import service
    started = []
    monkeypatch.setattr(upgrade, "write_record", lambda root=None: started.append("record"))
    monkeypatch.setattr(service, "start_in_background", lambda: started.append("checker") or True)
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    config.save_config({**config.DEFAULT_CONFIG, "schedule": "interval", "routes": [{"id": "fx01ab", "origin": "zzaa"}]})
    assert upgrade.finish() == 0 and started == ["record", "checker"]
