"""The Python side of the extension protocol, with a fake extension polling from a thread."""
import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from airfare import extension

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "unified_search_partial.json").read_text(encoding="utf-8"))
# Not AirFare's real port: the extension in your everyday Chrome polls that one and would pick up test jobs.
TEST_PORT = 8796
BASE = f"http://127.0.0.1:{TEST_PORT}"


@pytest.fixture(autouse=True)
def private_port(monkeypatch):
    monkeypatch.setattr(extension, "PORT", TEST_PORT)
    monkeypatch.setattr(extension, "_remember_extension", lambda v: None)   # never touch the real state.json
PAGES = [{"key": "a", "route_id": "r", "route_name": "R", "url": "https://www.skyscanner.es/transporte/vuelos/lhr/bcn/270312/"},
         {"key": "b", "route_id": "r", "route_name": "R", "url": "https://www.skyscanner.es/transporte/vuelos/lhr/bcn/270313/"}]


def _post(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        return urllib.request.urlopen(req, timeout=5).status
    except urllib.error.HTTPError as e:
        return e.code


def fake_extension(reply, robots=None):
    def run():
        for _ in range(50):
            try:
                req = urllib.request.Request(BASE + "/job", headers={"X-AirFare-Extension": "test"})
                with urllib.request.urlopen(req, timeout=2) as r:
                    if r.status == 200:
                        job = json.loads(r.read())
                        break
            except OSError:
                pass
            time.sleep(0.1)
        else:
            return
        if robots is not None:
            robots.append(_post("/progress", {"id": "wrong", "event": "robot", "n": 0}))
        _post("/progress", {"id": job["id"], "event": "robot", "n": 0})
        _post("/results", {"id": job["id"], **reply(job)})
    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t


def test_collect_round_trip(monkeypatch, tmp_path):
    monkeypatch.setattr(extension, "chrome_running", lambda kind="chrome": True)
    monkeypatch.setattr(extension, "_remember_extension", lambda v: None)
    seen_jobs = []

    def reply(job):
        seen_jobs.append(job)
        return {"pages": [
            {"n": 0, "url": job["pages"][0]["url"], "payloads": [FIXTURE], "text": "€155", "seconds": 21.5},
            {"n": 1, "robot": True, "payloads": [], "text": ""},
        ]}

    robots = []
    calls = []
    fake_extension(reply, robots)
    results = extension.collect(PAGES, wait_seconds=1, on_robot=lambda p: calls.append(p), robot_seconds=0)
    job = seen_jobs[0]
    assert job["matches"] == ["https://www.skyscanner.es/*"] and len(job["pages"]) == 2
    assert results[0].status == "ok" and results[0].payloads == [FIXTURE] and results[0].source == "Skyscanner"
    assert results[1].status == "blocked"
    assert robots == [403]                    # progress for another job id is refused
    time.sleep(0.2)
    assert calls and calls[0]["key"] == "a"   # the robot notice reached AirFare


def test_collect_reports_extension_error(monkeypatch):
    monkeypatch.setattr(extension, "chrome_running", lambda kind="chrome": True)
    monkeypatch.setattr(extension, "_remember_extension", lambda v: None)
    fake_extension(lambda job: {"error": "windows.create failed"})
    results = extension.collect(PAGES, wait_seconds=1, robot_seconds=0)
    assert all(r.status == "error" and "windows.create failed" in r.note for r in results)


def test_collect_without_extension(monkeypatch):
    monkeypatch.setattr(extension, "chrome_running", lambda kind="chrome": True)
    monkeypatch.setattr(extension, "PICKUP_TIMEOUT", 1)
    results = extension.collect(PAGES[:1], wait_seconds=1, robot_seconds=0)
    assert results[0].status == "error" and "didn't respond" in results[0].note


def test_supported_hosts_cover_common_sites():
    hosts = extension.supported_hosts()
    assert "www.skyscanner.net" in hosts and "www.skyscanner.es" in hosts and "127.0.0.1" not in hosts


def test_extension_version_and_start_page():
    assert extension.latest_version() == json.loads((extension.EXTENSION_DIR / "manifest.json").read_text())["version"]
    page = extension.start_page("en").decode("utf-8")
    assert "<title>AirFare</title>" in page and "Your own tabs aren't touched" in page
    es = extension.start_page("es").decode("utf-8")
    assert '<html lang="es">' in es and "Comprobando precios" in es and "__" not in es


def test_extension_closes_only_its_own_tabs():
    js = (extension.EXTENSION_DIR / "background.js").read_text(encoding="utf-8")
    assert "chrome.windows.remove" not in js          # never closes a whole window
    assert "closeOwnTabs(opened, job)" in js


def test_job_server_answers_only_the_extension(monkeypatch):
    monkeypatch.setattr(extension, "chrome_running", lambda kind="chrome": True)
    monkeypatch.setattr(extension, "PICKUP_TIMEOUT", 3)
    codes = []

    def intruder():
        time.sleep(0.5)
        for headers in ({}, {"Host": "evil.example:%d" % TEST_PORT, "X-AirFare-Extension": "1"}):
            try:
                urllib.request.urlopen(urllib.request.Request(BASE + "/job", headers=headers), timeout=2)
                codes.append(200)
            except urllib.error.HTTPError as e:
                codes.append(e.code)
        req = urllib.request.Request(BASE + "/results", data=b'{"id": "x"}', method="POST",
                                     headers={"Content-Type": "text/plain"})
        try:
            urllib.request.urlopen(req, timeout=2)
        except urllib.error.HTTPError as e:
            codes.append(e.code)

    threading.Thread(target=intruder, daemon=True).start()
    results = extension.collect(PAGES[:1], wait_seconds=1, robot_seconds=0)
    assert codes == [403, 403, 415]                         # no header, foreign host, not JSON
    assert "didn't respond" in results[0].note              # nobody but the extension can take the job
