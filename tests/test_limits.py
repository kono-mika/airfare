"""The limits on the browser sources (limits.py): pages per check, the gap between automatic checks and pages per
day, at both levels, applied where the pages are opened. Google Flights through SerpApi isn't limited."""
import asyncio
import json
import time
from datetime import date, datetime, timedelta

import pytest

from airfare import config, dashboard, extension, limits, report, runner, service, urls, webui
from airfare.results import PageResult
from airfare.translations import T
from test_dashboard import WHEN, pages as sample_pages

LEVELS = [("personal", 20, 6, 60), ("extended", 40, 3, 150)]      # level, pages per check, gap (hours), pages per day
WARNING = ("Extended limits load more pages from Skyscanner and Aviasales. Their terms don't allow automated visits, "
           "and more pages mean more robot checks or a blocked browser. Use it only for your own trips, at your own risk.")


@pytest.fixture
def files(monkeypatch, tmp_path):
    """config.json and state.json of this test's own."""
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(config, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(config, "_warned", set())
    return tmp_path


def trips(n: int) -> dict:
    """A one-way route with n departure days (n date combinations), a month from now."""
    start = date.today() + timedelta(days=30)
    return {"id": "r1", "origin": "lhr", "destination": "bcn", "trip": "oneway",
            "depart_from": start.isoformat(), "depart_to": (start + timedelta(days=n - 1)).isoformat()}


def settings(**kw) -> dict:
    return {**config.DEFAULT_CONFIG, "sources": ["extension", "serpapi"], **kw}


@pytest.fixture
def sources(monkeypatch):
    """The extension and SerpApi, faked: what each was asked for. The extension takes its job as the real one does,
    which counts the pages."""
    asked = {"opened": [], "sites": [], "searched": []}

    def collect(pages, wait, on_robot, lang="en", browser="chrome", on_taken=None):
        on_taken()
        asked["opened"].append(len(pages))
        asked["sites"].append([p["site"] for p in pages])
        return [PageResult(page=p, status="ok", source=p["site"], text="prices") for p in pages]

    async def search_all(pages, key, currency):
        asked["searched"].append(len(pages))
        return [PageResult(page=p, status="ok", source="Google Flights", text="prices") for p in pages]

    monkeypatch.setattr(runner.extension, "collect", collect)
    monkeypatch.setattr(runner.serpapi, "search_all", search_all)
    return asked


def collect(cfg: dict, automatic: bool = False):
    pages, _ = urls.plan_pages(cfg)
    return asyncio.run(runner.collect_prices(cfg, pages, cfg["sources"], automatic))


# ----- pages per check --------------------------------------------------------------------------------------

@pytest.mark.parametrize("level, per_check, hours, per_day", LEVELS)
def test_a_check_opens_at_most_the_levels_pages_even_when_config_json_asks_for_60(files, sources, level, per_check,
                                                                                   hours, per_day):
    config.CONFIG_FILE.write_text(json.dumps(settings(limits=level, max_pages=60, routes=[trips(60)])), encoding="utf-8")
    cfg = config.load_config()
    results, held = collect(cfg)
    assert sources["opened"] == [per_check] and sources["searched"] == [60]       # SerpApi isn't limited
    assert held["reason"] == "check" and held["opened"] == per_check and held["left_out"] == 60 - per_check
    assert sum(r.source == "Skyscanner" for r in results) == per_check


@pytest.mark.parametrize("level, per_check, hours, per_day", LEVELS)
def test_skyscanner_and_aviasales_pages_count_together_trip_by_trip(files, sources, level, per_check, hours, per_day):
    cfg = settings(limits=level, max_pages=60, sources=["extension", "aviasales"], routes=[trips(60)])
    _, held = collect(cfg)
    assert sources["opened"] == [per_check] and held["left_out"] == 120 - per_check
    assert sources["sites"][0] == ["Skyscanner", "Aviasales"] * (per_check // 2)   # whole trips, both sites


def test_an_unknown_level_in_config_json_gets_the_personal_limits(files, sources):
    config.CONFIG_FILE.write_text(json.dumps(settings(limits="unlimited", max_pages=60, routes=[trips(60)])),
                                  encoding="utf-8")
    collect(config.load_config())
    assert sources["opened"] == [20]
    collect({**settings(max_pages=60, routes=[trips(60)]), "limits": ["extended"]})     # not even a word
    assert sources["opened"] == [20, 20]


# ----- the gap between automatic checks -----------------------------------------------------------------------

@pytest.mark.parametrize("level, per_check, hours, per_day", LEVELS)
def test_automatic_checks_skip_the_browser_sources_within_the_gap_and_still_ask_serpapi(files, sources, level,
                                                                                         per_check, hours, per_day):
    cfg = settings(limits=level, routes=[trips(5)])
    last = datetime.now().replace(microsecond=0) - timedelta(hours=hours) + timedelta(minutes=5)
    config.save_state({"browser_check": last.isoformat()})
    results, held = collect(cfg, automatic=True)
    assert sources["opened"] == [] and sources["searched"] == [5]
    assert {r.source for r in results} == {"Google Flights"}
    assert held["reason"] == "gap" and held["left_out"] == 5 and held["opened"] == 0
    assert held["until"] == (last + timedelta(hours=hours)).isoformat(timespec="minutes")
    assert limits.reopens(cfg) == last + timedelta(hours=hours)

    _, held = collect(cfg)                                   # "Run check now" doesn't wait for the gap...
    assert sources["opened"] == [5] and held is None
    stamp = datetime.fromisoformat(config.load_state()["browser_check"])
    assert datetime.now() - stamp < timedelta(minutes=1)     # ...and it starts the gap again
    _, held = collect(cfg, automatic=True)
    assert sources["opened"] == [5] and held["reason"] == "gap"

    config.save_state({"browser_check": (datetime.now() - timedelta(hours=hours, minutes=1)).isoformat()})
    _, held = collect(cfg, automatic=True)                   # the gap is over
    assert sources["opened"] == [5, 5] and held is None


# ----- pages per day ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("level, per_check, hours, per_day", LEVELS)
def test_the_daily_cap_counts_manual_checks_too(files, sources, level, per_check, hours, per_day):
    cfg = settings(limits=level, max_pages=60, routes=[trips(60)])
    reasons = []
    for _ in range(6):                                       # "Run check now", again and again
        _, held = collect(cfg)
        reasons.append(held and held["reason"])
    full, rest = divmod(per_day, per_check)
    assert sources["opened"] == [per_check] * full + ([rest] if rest else [])
    assert sum(sources["opened"]) == per_day and sources["searched"] == [60] * 6     # SerpApi every time
    assert reasons[full - 1] == "check" and reasons[-1] == "day"
    assert held["opened"] == 0 and held["left_out"] == 60
    assert held["until"] == (datetime.combine(date.today() + timedelta(days=1), datetime.min.time())
                             .isoformat(timespec="minutes"))
    assert config.load_state()["browser_pages"] == {"day": date.today().isoformat(), "pages": per_day}


@pytest.mark.parametrize("level, per_check, hours, per_day", LEVELS)
def test_the_day_rolling_over_starts_a_new_count(files, level, per_check, hours, per_day):
    cfg = {"limits": level}
    pages = [{"url": f"https://example/{i}"} for i in range(per_check + 5)]
    evening = datetime(2026, 11, 2, 23, 30)
    limits.record(per_day - 3, evening)
    kept, held = limits.allow(cfg, pages, now=evening + timedelta(minutes=10))
    assert len(kept) == 3 and held["reason"] == "day" and held["left_out"] == per_check + 2
    limits.record(3, evening + timedelta(minutes=10))
    assert limits.allow(cfg, pages, now=evening + timedelta(minutes=20))[0] == []
    # Automatic checks wait for the later of the two: the gap after 23:40, or the new day.
    assert limits.reopens(cfg, evening + timedelta(minutes=20)) == evening + timedelta(hours=hours, minutes=10)
    config.save_state({"browser_pages": {"day": "2026-11-02", "pages": per_day}})
    assert limits.reopens(cfg, evening + timedelta(minutes=20)) == datetime(2026, 11, 3, 0, 0)

    midnight = datetime(2026, 11, 3, 0, 1)
    kept, held = limits.allow(cfg, pages, now=midnight)       # a manual check just after midnight
    assert len(kept) == per_check and held["reason"] == "check"
    limits.record(len(kept), midnight)
    assert config.load_state()["browser_pages"] == {"day": "2026-11-03", "pages": per_check}
    assert limits.reopens(cfg, midnight + timedelta(hours=hours)) is None


# ----- whole checks, Settings and the background checker -----------------------------------------------------

def fake_check(monkeypatch, files, cfg):
    """runner.run_check with everything but the limits, the sources and the price document faked."""
    seen = {"network": 0, "dashboard": "unset"}

    def network(host, limit=0):
        seen["network"] += 1
        return True

    def write_dashboard(*args):
        seen["dashboard"] = args[12]
        return files / "latest.html"

    monkeypatch.setattr(runner, "load_config", lambda: cfg)
    monkeypatch.setattr(runner, "wait_for_network", network)
    monkeypatch.setattr(runner.money, "rates", lambda refresh=True: {"rates": {"EUR": 1.0}})
    monkeypatch.setattr(runner.pricelog, "add", lambda records: None)
    monkeypatch.setattr(runner, "write_history_page", lambda cfg: None)
    monkeypatch.setattr(runner, "load_history", lambda: {"routes": {}, "runs": []})
    monkeypatch.setattr(runner, "save_history", lambda history: None)
    monkeypatch.setattr(runner.cleanup, "automatic", lambda cfg: None)
    monkeypatch.setattr(runner.notify, "toast", lambda *a, **k: None)
    monkeypatch.setattr(runner, "_write_dashboard", write_dashboard)
    monkeypatch.setattr(runner.links, "for_dashboard", lambda path: path)
    monkeypatch.setattr(runner, "REPORTS_DIR", files)
    return seen


@pytest.mark.parametrize("level, per_check, hours, per_day", LEVELS)
def test_an_automatic_check_in_the_gap_runs_serpapi_and_says_so(files, sources, monkeypatch, level, per_check,
                                                                 hours, per_day):
    cfg = settings(limits=level, llm_provider="none", serpapi_key="fake", routes=[trips(3)])    # SerpApi is faked
    seen = fake_check(monkeypatch, files, cfg)
    config.save_state({"browser_check": (datetime.now() - timedelta(hours=1)).isoformat()})
    assert asyncio.run(runner.run_check(automatic=True)) == 0
    assert sources["opened"] == [] and sources["searched"] == [3]
    assert seen["dashboard"]["reason"] == "gap"
    document = next(files.glob("*-prices.md")).read_text(encoding="utf-8")
    assert (f"Skyscanner and Aviasales were skipped this time: with the {limits.NAMES[level]} limits, automatic "
            f"checks open their pages at most once every {hours} hours.") in document


def test_a_check_with_only_browser_sources_and_the_day_used_up_checks_nothing(files, sources, monkeypatch):
    cfg = settings(sources=["extension"], llm_provider="none", routes=[trips(3)])
    config.CONFIG_FILE.write_text(json.dumps({"language": "en"}), encoding="utf-8")    # Settings answers in English
    seen = fake_check(monkeypatch, files, cfg)
    limits.record(60)
    monkeypatch.setattr(runner, "run", lambda console=False, automatic=False: asyncio.run(runner.run_check(automatic)))
    answer = webui.run_check()                            # "Run check now" in Settings
    assert answer["code"] == runner.HELD and seen["network"] == 0 and sources["opened"] == []
    assert answer["message"] == "Nothing was checked: the limits hold Skyscanner and Aviasales for now."
    assert answer["note"] == "3 Skyscanner and Aviasales pages wait until tomorrow: the Personal limits allow 60 a day."
    assert not list(files.glob("*-prices.md"))


def test_dashboard_and_price_document_say_what_the_limits_left_out():
    held = {"level": "personal", "reason": "check", "opened": 20, "left_out": 40, "pages": 20, "hours": 6,
            "per_day": 60, "until": None}
    document = report.build_document(sample_pages(), WHEN, 0, "EUR", {}, held)
    assert "40 Skyscanner and Aviasales pages were left out: the Personal limits allow 20 per check." in document
    parts = dashboard.check_parts(sample_pages(), {"runs": []}, {}, {}, WHEN, "", False, {}, {}, "x.md", lang="ru",
                                  held=held)
    assert "40 страниц Skyscanner и Aviasales пропущено: лимиты уровня «Личный» разрешают 20 за проверку." in parts["checked"]
    assert "<br>" not in dashboard.check_parts(sample_pages(), {"runs": []}, {}, {}, WHEN, "", False, {}, {},
                                               "x.md")["checked"]


def test_personal_is_the_default_for_old_and_unknown_configs(files):
    assert config.load_config()["limits"] == "personal"                       # no config.json yet
    config.CONFIG_FILE.write_text(json.dumps({"max_pages": 20, "routes": []}), encoding="utf-8")   # from before limits
    assert config.load_config()["limits"] == "personal"
    for odd in ("off", "unlimited", "Extended", "", None, 0, ["extended"], {"pages": 999}):
        config.CONFIG_FILE.write_text(json.dumps({"limits": odd}), encoding="utf-8")
        assert config.load_config()["limits"] == "personal", odd
        assert limits.level({"limits": odd}) == "personal"
    assert limits.level({}) == "personal" and limits.level({"limits": "extended"}) == "extended"


def test_extended_needs_the_warning_confirmed_in_settings(files):
    form = {"sources": ["extension"], "routes": [trips(3)]}
    assert webui.clean_config(form)["limits"] == "personal"
    with pytest.raises(webui.Problem, match="Confirm the warning"):
        webui.clean_config({**form, "limits": "extended"})                    # straight to Extended: refused
    cfg = webui.clean_config({**form, "limits": "extended", "limits_confirmed": True})
    assert cfg["limits"] == "extended" and "limits_confirmed" not in cfg
    config.save_config(cfg)
    assert webui.clean_config({**form, "limits": "extended"})["limits"] == "extended"   # kept: no new warning
    assert webui.clean_config({**form, "limits": "personal"})["limits"] == "personal"   # back: no warning at all
    with pytest.raises(webui.Problem):
        webui.clean_config({**form, "limits": "unlimited", "limits_confirmed": True})

    page = webui.settings_page("en")
    assert f'if (!confirm(t("{WARNING}"))) {{ e.target.value = "personal";' in page
    assert '<select id="limits">' in page and 'cfg.limits_confirmed = limitsOk;' in page
    assert T[WARNING]["es"].startswith("Los límites ampliados") and T[WARNING]["ru"].startswith("Расширенные лимиты")


@pytest.mark.parametrize("level, per_check, hours, per_day", LEVELS)
def test_settings_preview_counts_pages_over_the_per_check_limit(files, level, per_check, hours, per_day):
    cfg = settings(limits=level, max_pages=30, sources=["extension", "aviasales"], routes=[trips(30)])
    view = webui.preview(cfg)
    assert view["planned"] == 30 and view["browser_left_out"] == 60 - per_check
    assert webui.preview({**cfg, "sources": ["serpapi"]})["browser_left_out"] == 0


def test_the_extension_gets_its_job_only_once_the_pages_are_counted():
    page = {"url": "https://www.skyscanner.net/transport/flights/lhr/bcn/270312/", "site": "Skyscanner"}
    counted = []
    job = extension._Job([page], 1, 0, None, on_taken=lambda: counted.append(1))
    assert job.take() and not job.take() and counted == [1]

    def disk_full():
        raise OSError("disk full")

    job = extension._Job([page], 1, 0, None, on_taken=disk_full)
    with pytest.raises(OSError):
        job.take()
    assert not job.taken.is_set()                              # no page opens uncounted


def test_the_background_checker_waits_for_the_limits_after_a_held_check(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "SERVICE_LOCK", tmp_path / "service.lock")
    monkeypatch.setattr(service, "SERVICE_FILE", tmp_path / "service.json")
    monkeypatch.setattr(service.time, "sleep", lambda s: None)
    monkeypatch.setattr(runner, "setup_logging", lambda console=False: None)
    runs = []
    monkeypatch.setattr(runner, "run", lambda console=False, automatic=False: runs.append(automatic) or runner.HELD)
    every = {"schedule": "interval", "interval_hours": 1}
    monkeypatch.setattr(service, "load_config", lambda: every)
    monkeypatch.setattr(service, "load_state", lambda: {"last_check": "2026-10-20T08:00"})     # long overdue
    reopen = datetime.now().replace(second=0, microsecond=0) + timedelta(hours=5)
    monkeypatch.setattr(service.limits, "reopens", lambda cfg: reopen)
    service.serve(max_ticks=4)
    assert runs == [True]                       # one automatic check, then no retry until the limits allow one
    assert service.status()["next_check"] == reopen.isoformat(timespec="minutes")
    service._Checker(None, time.time(), 1, "en").check()       # the tray icon's Check now is a manual check
    assert runs == [True, False]


# ----- found in the bug check ---------------------------------------------------------------------------------

def test_a_check_without_an_analyst_records_its_time_for_the_schedule(files, sources, monkeypatch):
    cfg = settings(llm_provider="none", serpapi_key="fake", routes=[trips(2)])
    fake_check(monkeypatch, files, cfg)
    assert asyncio.run(runner.run_check()) == 0
    last = datetime.fromisoformat(config.load_state()["last_check"])
    assert datetime.now() - last < timedelta(minutes=2)       # so interval checks wait their hours, not 30 minutes


def test_test_links_count_toward_the_day_but_dont_start_the_gap(files, sources):
    cfg = settings(routes=[trips(5)])
    pages, _ = urls.plan_pages(cfg)
    asyncio.run(runner.collect_prices(cfg, pages, cfg["sources"], test=True))
    state = config.load_state()
    assert state["browser_pages"]["pages"] == 5 and "browser_check" not in state
    _, held = collect(cfg, automatic=True)                     # the next automatic check still opens them
    assert sources["opened"] == [5, 5] and held is None


def test_a_gap_stamp_from_a_wrong_clock_doesnt_hold_the_sites_for_months(files):
    now = datetime(2026, 11, 2, 12, 0)
    pages = [{"url": "https://example/1"}]
    config.save_state({"browser_check": "2026-12-25T12:00:00"})          # written while the clock was ahead
    assert limits.allow({}, pages, automatic=True, now=now)[0] == pages
    config.save_state({"browser_check": "2026-11-02T12:40:00"})          # the clock went back an hour: still a gap
    assert limits.allow({}, pages, automatic=True, now=now)[1]["reason"] == "gap"


def test_pages_the_limits_left_out_bring_no_notes_of_their_own(files, sources):
    route = {**trips(3), "origin": "xxxx", "destination": "bcn"}          # a code Aviasales can't search
    cfg = settings(sources=["extension", "aviasales", "serpapi"], routes=[route])
    config.save_state({"browser_check": datetime.now().isoformat()})
    results, held = collect(cfg, automatic=True)
    assert held["reason"] == "gap" and {r.source for r in results} == {"Google Flights"}
    results, held = collect(cfg)                                          # a manual check: notes as before
    assert held is None and sum(r.source == "Aviasales" and r.status == "error" for r in results) == 3


def test_the_update_check_keeps_a_page_count_written_meanwhile(files, monkeypatch):
    from airfare import update

    def fetch():
        limits.record(7)                         # a check opened pages while GitHub was answering
        return {"latest": "9.9.9", "url": "https://example/release"}

    monkeypatch.setattr(update, "fetch", fetch)
    update.check(force=True)
    state = config.load_state()
    assert state["browser_pages"]["pages"] == 7 and state["update"]["latest"] == "9.9.9"
