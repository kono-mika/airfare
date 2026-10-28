from datetime import datetime

from airfare import notify, runner, service
from test_dashboard import pages


def test_next_due_after_last_check_and_retry_after_failure():
    start = datetime(2026, 10, 27, 8, 0).timestamp()
    assert service.next_due("2026-10-27T08:00", 6, start, None) == start + 6 * 3600
    failed_at = start + 7 * 3600                       # a check was attempted at 15:00 and didn't finish
    assert service.next_due("2026-10-27T08:00", 6, start, failed_at) == failed_at + service.RETRY_AFTER
    assert service.next_due(None, 6, start, None) == start + 6 * 3600   # never checked: one interval from start
    assert service.next_due("garbage", 6, start, None) == start + 6 * 3600


def test_schedule_is_clamped():
    assert service.schedule({"schedule": "both", "interval_hours": 0.2}) == ("both", 1.0)
    assert service.schedule({"schedule": "weekly", "interval_hours": 99}) == ("startup", 48.0)


def run_service(monkeypatch, tmp_path, schedules):
    """Run the checker over a sequence of per-tick settings; each fake check succeeds and records itself."""
    monkeypatch.setattr(service, "SERVICE_LOCK", tmp_path / "service.lock")
    monkeypatch.setattr(service, "SERVICE_FILE", tmp_path / "service.json")
    monkeypatch.setattr(service.time, "sleep", lambda s: None)
    monkeypatch.setattr(runner, "setup_logging", lambda console=False: None)
    state = {"last_check": "2026-10-20T08:00"}                          # long overdue
    runs = []

    def fake_run(*a, **k):
        runs.append("check")
        state["last_check"] = datetime.now().isoformat(timespec="minutes")
        return 0

    monkeypatch.setattr(runner, "run", fake_run)
    configs = iter(schedules)
    monkeypatch.setattr(service, "load_config", lambda: next(configs))
    monkeypatch.setattr(service, "load_state", lambda: dict(state))
    return service.serve(max_ticks=len(schedules) - 1), runs   # settings are read once at start, then per tick


def test_both_checks_at_startup_then_waits_for_the_interval(monkeypatch, tmp_path):
    both = {"schedule": "both", "interval_hours": 6}
    code, runs = run_service(monkeypatch, tmp_path, [both, both, both, {"schedule": "startup"}])
    assert code == 0 and runs == ["check"]               # the next one is 6 hours away; then it stopped
    assert service.status()["running"] is False


def test_interval_only_runs_an_overdue_check_right_away(monkeypatch, tmp_path):
    every = {"schedule": "interval", "interval_hours": 6}
    code, runs = run_service(monkeypatch, tmp_path, [every, every, every, every])
    assert runs == ["check"]                              # no startup check, one overdue interval check
    assert service.status()["next_check"]                 # Settings can show when the next one is due


def test_alert_message_names_kind_drop_dates_and_booking_link():
    from airfare import report
    data = pages()
    bests = report.route_bests(data)
    targets = {"r": {"cheapest": {"ref": {"price": 125.0, "text": "£125"}}}}
    title, lines, book = runner.alert_message(data, "r", ["cheapest"], targets, bests, {}, "Book the direct one.", "en")
    assert title == "LOW PRICE ✈ Vilnius ⇄ London"
    assert lines[0].startswith("Cheapest: £118 (−5.6% vs £125) · ") and "Iberia + KLM, 1 stop" in lines[0]
    assert lines[1] == "Book the direct one." and book == "https://example.test/g"
    _, ru, _ = runner.alert_message(data, "r", ["cheapest"], targets, bests, {}, None, "ru")
    assert ru[0].startswith("Самый дешёвый: £118") and "1 пересадка" in ru[0]


def test_alert_from_best_value_only():
    data = pages()
    targets = {"r": {"best": {"ref": {"price": 160.0, "text": "£160"}}}}
    best = {"r": {"price": 150.0, "text": "£150, Fri 18 Dec 06:15, Ryanair, direct", "url": "https://example.test/s"}}
    title, lines, book = runner.alert_message(data, "r", ["best"], targets, {}, best, None, "en")
    assert lines[0].startswith("Best value: £150, Fri 18 Dec 06:15, Ryanair, direct (−6.2% vs £160)")
    assert book == "https://example.test/s"


def test_sticky_notification_has_buttons(monkeypatch, tmp_path):
    shown = []
    monkeypatch.setattr(notify.platform, "WINDOWS", True)        # the Windows toast (macOS, Linux: test_platform)
    monkeypatch.setattr(notify, "_show", lambda xml: shown.append(xml) or True)
    page = tmp_path / "latest.html"
    page.write_text("x")
    assert notify.alert("LOW PRICE ✈ R: 99 €", ["line & more", ""], [("Book now", "https://example.test/b?x=1&y=2"),
                                                                     ("Dashboard", page)], open_path=page)
    xml = shown[0]
    assert 'scenario="reminder"' in xml and "Notification.Reminder" in xml
    assert 'content="Book now"' in xml and "https://example.test/b?x=1&amp;y=2" in xml
    assert page.resolve().as_uri() in xml and 'arguments="dismiss"' in xml
    assert "line &amp; more" in xml and xml.count("<text>") == 2      # empty lines are dropped
