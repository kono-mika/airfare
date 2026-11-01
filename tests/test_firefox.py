"""The extension in Opera and Firefox: the browser table, the Firefox build of the extension and its manifest, and
the page allow-list both builds share with AirFare's own check."""
import json
import re
import shutil
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

import pytest

from airfare import extension, platform, webui
from airfare.config import PROJECT_DIR

sys.path.insert(0, str(PROJECT_DIR / "tools"))
import make_firefox  # noqa: E402

CHROME_DIR, FIREFOX_DIR = PROJECT_DIR / "extension", PROJECT_DIR / "extension-firefox"
BUILDS = {"chrome": CHROME_DIR, "firefox": FIREFOX_DIR}


def _manifest(folder: Path) -> dict:
    return json.loads((folder / "manifest.json").read_text(encoding="utf-8"))


# ----- the browser table -----------------------------------------------------------------------

def test_every_browser_names_its_program_page_and_extension_folder():
    assert set(extension.BROWSERS) == {"chrome", "edge", "brave", "opera", "firefox"}
    for kind, b in extension.BROWSERS.items():
        names = (b["exe"],) if isinstance(b["exe"], str) else b["exe"]
        processes = (b["process"],) if isinstance(b["process"], str) else b["process"]
        assert b["name"] and names and processes, kind
        if platform.WINDOWS:
            assert all(n.endswith(".exe") for n in names), kind
            assert b["process"].endswith(".exe") and b["process"] == b["process"].lower(), kind
        elif platform.MACOS:
            assert all(".app/Contents/MacOS/" in n for n in names), kind
        else:
            assert all("/" not in n for n in names) and all(len(p) <= 15 for p in processes), kind   # commands, comm names
        assert (extension.extension_dir(kind) / "manifest.json").is_file(), kind
    assert {k for k, b in extension.BROWSERS.items() if b["folder"] == "extension-firefox"} == {"firefox"}
    opera, firefox = extension.BROWSERS["opera"], extension.BROWSERS["firefox"]
    assert opera["page"] == "opera://extensions" and firefox["page"] == "about:debugging#/runtime/this-firefox"
    if platform.WINDOWS:
        assert opera["process"] == "opera.exe" and firefox["process"] == "firefox.exe"
    assert extension.extension_dir("firefox") == FIREFOX_DIR and extension.extension_dir("opera") == CHROME_DIR
    assert extension.extension_dir("safari") == CHROME_DIR          # unknown browsers fall back to Chrome
    assert extension.latest_version("firefox") == _manifest(FIREFOX_DIR)["version"]


@pytest.mark.skipif(not platform.WINDOWS, reason="Windows program folders")
def test_the_first_program_that_exists_is_the_browser(monkeypatch, tmp_path):
    local, program_files = tmp_path / "Local", tmp_path / "Program Files"
    monkeypatch.setattr(extension, "_PROGRAM_DIRS", [program_files, local])
    assert extension.chrome_path("opera") is None and extension.installed_browsers()["firefox"] is False
    opera = local / "Programs" / "Opera" / "opera.exe"
    opera.parent.mkdir(parents=True)
    opera.touch()
    assert extension.chrome_path("opera") == opera
    (opera.parent / "launcher.exe").touch()                         # the launcher wins when both are there
    assert extension.chrome_path("opera") == opera.parent / "launcher.exe"
    firefox = program_files / "Mozilla Firefox" / "firefox.exe"
    firefox.parent.mkdir(parents=True)
    firefox.touch()
    assert extension.chrome_path("firefox") == firefox and extension.installed_browsers()["firefox"] is True


@pytest.mark.skipif(not platform.MACOS, reason="macOS app bundles")
def test_the_browser_is_its_app_bundle_on_macos(monkeypatch, tmp_path):
    monkeypatch.setattr(extension, "_PROGRAM_DIRS", [tmp_path / "Applications", tmp_path / "home" / "Applications"])
    assert extension.chrome_path("firefox") is None
    firefox = tmp_path / "home" / "Applications" / "Firefox.app" / "Contents" / "MacOS" / "firefox"
    firefox.parent.mkdir(parents=True)
    firefox.touch()
    assert extension.chrome_path("firefox") == firefox and extension.installed_browsers()["firefox"] is True


@pytest.mark.skipif(not platform.LINUX, reason="Linux commands on PATH")
def test_the_browser_is_the_first_command_on_path_on_linux(monkeypatch, tmp_path):
    monkeypatch.setattr(extension.shutil, "which", lambda name: f"/snap/bin/{name}" if name == "chromium" else None)
    assert extension.chrome_path("chrome") == Path("/snap/bin/chromium") and extension.chrome_path("edge") is None


@pytest.mark.skipif(platform.WINDOWS, reason="macOS and Linux start the browser with platform.start_browser")
def test_the_browser_starts_with_the_start_page_on_mac_and_linux(monkeypatch, tmp_path):
    started = []
    monkeypatch.setattr(extension, "chrome_path", lambda kind="chrome": tmp_path / kind)
    monkeypatch.setattr(extension.platform, "start_browser", lambda exe, args: started.append((exe, args)))
    extension.start_chrome_minimized("http://127.0.0.1:1/start", "firefox")
    assert started == [(tmp_path / "firefox", ["--new-window", "http://127.0.0.1:1/start"])]


@pytest.mark.skipif(not platform.WINDOWS, reason="STARTUPINFO and window minimizing are Windows'")
def test_firefox_and_opera_get_their_first_window_minimized(monkeypatch, tmp_path):
    started, minimized = [], []
    done = threading.Event()
    monkeypatch.setattr(extension, "chrome_path", lambda kind="chrome": tmp_path / f"{kind}.exe")
    monkeypatch.setattr(extension.subprocess, "Popen", lambda args, **kw: started.append((args, kw["startupinfo"])))
    monkeypatch.setattr(extension, "minimize_when_shown", lambda process: (minimized.append(process), done.set()))
    extension.start_chrome_minimized("http://127.0.0.1:1/start", "chrome")
    extension.start_chrome_minimized("http://127.0.0.1:1/start", "firefox")
    assert done.wait(5) and minimized == ["firefox.exe"]            # Chrome honours the minimized start by itself
    assert [a[1:] for a, _ in started] == [["--new-window", "http://127.0.0.1:1/start"]] * 2
    assert all(si.wShowWindow == 7 for _, si in started)


@pytest.mark.skipif(not platform.WINDOWS, reason="window minimizing is Windows'")
def test_minimizing_leaves_other_programs_windows_alone():
    extension.minimize_when_shown("no-such-browser.exe", seconds=0.3)   # finds no window, touches none


def test_firefox_says_how_to_bring_a_temporary_add_on_back(monkeypatch):
    monkeypatch.setattr(extension, "PORT", 8782)     # no other test's port, nor the one your own browser polls
    monkeypatch.setattr(extension, "PICKUP_TIMEOUT", 1)
    monkeypatch.setattr(extension, "chrome_running", lambda kind="chrome": True)
    page = {"url": "https://www.aviasales.ru/search/LON0612BCN1", "site": "Aviasales"}
    note = extension.collect([page], wait_seconds=1, robot_seconds=0, browser="firefox")[0].note
    assert "about:debugging" in note and ".xpi" in note
    assert "extensions page" in extension.collect([page], wait_seconds=1, robot_seconds=0, browser="opera")[0].note
    start = extension.start_page("es", "Mozilla Firefox").decode("utf-8")
    assert "AirFare abrió Mozilla Firefox solo" in start and "Chrome" not in start


# ----- the Firefox build --------------------------------------------------------------------------

def test_the_firefox_build_is_up_to_date():
    assert make_firefox.stale() == [], "run: python tools/make_firefox.py"


def test_the_firefox_manifest_is_valid_for_firefox_and_addons_mozilla_org():
    chrome, firefox = _manifest(CHROME_DIR), _manifest(FIREFOX_DIR)
    assert firefox["manifest_version"] == 3
    assert {k: firefox[k] for k in ("name", "version", "description", "permissions", "icons")} == \
           {k: chrome[k] for k in ("name", "version", "description", "permissions", "icons")}
    gecko = firefox["browser_specific_settings"]["gecko"]
    assert re.fullmatch(r"[\w.+-]+@[\w.-]+\.[a-z]{2,}", gecko["id"]) and len(gecko["id"]) <= 255
    assert not gecko["id"].endswith(("@mozilla.org", "@mozilla.com", "@firefox.com"))   # ids AMO keeps for itself
    # 128 runs MAIN-world content scripts (capture.js); 140 knows the data consent key AMO requires.
    assert int(gecko["strict_min_version"].split(".")[0]) >= 140
    assert gecko["data_collection_permissions"] == {"required": ["none"]}
    assert firefox["background"] == {"scripts": ["background.js"]}               # an event page, no service worker
    assert "minimum_chrome_version" not in firefox
    assert all((FIREFOX_DIR / f).is_file() for f in [*firefox["background"]["scripts"], *firefox["icons"].values()])
    # Firefox match patterns can't name a port: without one they match every port of the host.
    assert not any(re.match(r"\w+://[^/]+:\d+/", p) for p in firefox["host_permissions"])
    assert firefox["host_permissions"] == [re.sub(r":\d+/", "/", p) for p in chrome["host_permissions"]]


def test_the_firefox_background_uses_promises_and_reads_the_page_like_chrome():
    chrome = (CHROME_DIR / "background.js").read_text(encoding="utf-8")
    firefox = (FIREFOX_DIR / "background.js").read_text(encoding="utf-8")
    assert "chrome." not in firefox and 'browser.alarms.get("airfare-poll").then(' in firefox
    assert re.sub(r"\bchrome\.", "browser.", chrome.replace('.get("airfare-poll", (a) =>', '.get("airfare-poll").then((a) =>')) \
        in firefox                                                    # nothing else differs
    assert 'world: "MAIN"' in firefox and "closeOwnTabs(opened, job)" in firefox and "windows.remove" not in firefox
    assert (FIREFOX_DIR / "capture.js").read_text(encoding="utf-8") == (CHROME_DIR / "capture.js").read_text(encoding="utf-8")
    assert "Chrome" not in (FIREFOX_DIR / "done.js").read_text(encoding="utf-8")
    with pytest.raises(SystemExit, match="callback"):
        make_firefox.background('chrome.tabs.query({}, (tabs) => done(tabs));')


def test_the_upload_zip_has_the_files_at_its_top(monkeypatch, tmp_path):
    monkeypatch.setattr(make_firefox, "ROOT", tmp_path)
    import zipfile
    with zipfile.ZipFile(make_firefox.make_zip("airfare-collector@someone.example")) as z:
        names = set(z.namelist())
        manifest = json.loads(z.read("manifest.json"))
    assert {"manifest.json", "background.js", "capture.js", "done.html", "icons/icon128.png"} <= names
    assert manifest["browser_specific_settings"]["gecko"]["id"] == "airfare-collector@someone.example"


# ----- the page allow-list both builds share --------------------------------------------------

URLS = [
    "https://www.skyscanner.net/transport/flights/lond/bcn/261206/?adultsv2=1",
    "https://www.skyscanner.es/transporte/vuelos/mad/lhr/270312/270320/",
    "https://www.aviasales.ru/search/LON0612BCN1",
    "https://www.aviasales.ru/search/LON0612BCN1/extra",            # not a search page
    "https://www.skyscanner.net/flights/",                           # not a search page
    "https://www.skyscanner.net/transport/flights/lond/bcn/2612/",   # date too short
    "http://www.skyscanner.net/transport/flights/lond/bcn/261206/",  # not https
    "https://evil.example/transport/flights/lond/bcn/261206/",       # not one of its sites
    "https://user:pw@www.skyscanner.net/transport/flights/lond/bcn/261206/",
    "https://www.skyscanner.net.evil.example/transport/flights/lond/bcn/261206/",
    "not a url",
]


def _js_regex(js: str, name: str) -> re.Pattern:
    body, flags = re.search(rf"const {name} = /(.+)/([a-z]*);", js).groups()
    return re.compile(body, re.I if "i" in flags else 0)


def _js_ours(url: str, js: str, sites: list[str]) -> bool:
    """background.js's validJob() check for one page, in Python, with the regexes read from the build."""
    u = urlparse(url)
    host = (u.hostname or "") + (f":{u.port}" if u.port else "")
    search = _js_regex(js, "AVIASALES_SEARCH" if "aviasales" in host else "SKYSCANNER_SEARCH")
    return (u.scheme == "https" and not u.username and not u.password and f"https://{host}/*" in sites
            and bool(search.search(u.path)))


@pytest.mark.parametrize("build", BUILDS)
def test_both_builds_open_exactly_the_pages_airfare_allows(build):
    js = (BUILDS[build] / "background.js").read_text(encoding="utf-8")
    sites = [p for p in _manifest(BUILDS[build])["host_permissions"] if p.startswith("https://")]
    assert sites == [p for p in _manifest(CHROME_DIR)["host_permissions"] if p.startswith("https://")]
    for url in URLS:
        assert _js_ours(url, js, sites) == extension.allowed(url), url
    def shared(text):                                               # from the SITES list to the end of validJob()
        start = text.index("const SITES")
        return re.sub(r"\b(chrome|browser)\.", "API.", text[start:text.index("\n}\n", start) + 3])
    assert shared(js) == shared((CHROME_DIR / "background.js").read_text(encoding="utf-8"))   # the same validJob


@pytest.mark.skipif(not shutil.which("node"), reason="needs Node.js to run the extension's own code")
@pytest.mark.parametrize("build", BUILDS)
def test_both_builds_validjob_agrees_with_airfare_when_run(build, tmp_path):
    # Nothing in the run waits on anything: no AirFare port (fetch fails at once), no timers, no stdin (a child
    # holding the test runner's stdin pipe could hang on Windows), and the answer goes to a file before an
    # explicit exit, so the result never depends on how fast the machine is. The timeout only guards a hang.
    folder = BUILDS[build]
    answer = tmp_path / "answer.json"
    stub = """const manifest = %s;
const api = {runtime: {getManifest: () => manifest, onInstalled: {addListener() {}}, onStartup: {addListener() {}}},
             alarms: {onAlarm: {addListener() {}}, get: () => Promise.resolve({}), create() {}}};
globalThis.chrome = api; globalThis.browser = api;
globalThis.fetch = () => Promise.reject(new Error("no network in this test"));
globalThis.setTimeout = globalThis.setInterval = () => { throw new Error("no timers in this test"); };
""" % (folder / "manifest.json").read_text(encoding="utf-8")
    check = ("\nrequire('fs').writeFileSync(%s, JSON.stringify(%s.map((url) => "
             "validJob({id: 'x', pages: [{url}], matches: []}))));\nprocess.exit(0);\n") % \
            (json.dumps(str(answer)), json.dumps(URLS))
    script = tmp_path / "check.js"
    script.write_text(stub + (folder / "background.js").read_text(encoding="utf-8") + check, encoding="utf-8")
    log = tmp_path / "node.log"
    with open(log, "wb") as out:
        code = subprocess.run(["node", str(script)], stdin=subprocess.DEVNULL, stdout=out, stderr=out,
                              timeout=600).returncode
    assert code == 0, log.read_text(encoding="utf-8", errors="replace")
    assert json.loads(answer.read_text(encoding="utf-8")) == [extension.allowed(u) for u in URLS]


# ----- Settings ---------------------------------------------------------------------------------

def test_settings_show_each_browsers_folder_and_open_it(monkeypatch):
    port = 8781
    opened = []
    monkeypatch.setattr(webui.platform, "open_path", lambda path: opened.append(Path(path)))
    server = webui.Server(port)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        headers = {"X-AirFare": "1", "Content-Type": "application/json"}
        with urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}/api/state", headers=headers),
                                    timeout=10) as r:
            browsers = json.loads(r.read())["browsers"]
        assert browsers["firefox"]["folder"] == str(FIREFOX_DIR) and browsers["opera"]["folder"] == str(CHROME_DIR)
        assert browsers["firefox"]["page"].startswith("about:debugging") and browsers["firefox"]["latest"]
        for kind in ("firefox", "opera"):
            req = urllib.request.Request(f"http://127.0.0.1:{port}/api/extension-folder", method="POST",
                                         data=json.dumps({"browser": kind}).encode(), headers=headers)
            urllib.request.urlopen(req, timeout=10).close()
        assert opened == [FIREFOX_DIR, CHROME_DIR]
    finally:
        server.shutdown()
        server.server_close()
    page = webui.settings_page("ru")
    assert 'data-ext="firefox"' in page and "Загрузить временное дополнение" in page


def test_settings_accept_opera_and_firefox(monkeypatch):
    from airfare import config
    monkeypatch.setattr(webui, "load_config", lambda: dict(config.DEFAULT_CONFIG))
    route = {"id": "r1", "origin": "lhr", "destination": "bcn", "trip": "oneway", "depart_from": "2027-03-12"}
    for kind in ("opera", "firefox"):
        assert webui.clean_config({"sources": ["extension"], "browser": kind, "routes": [route]})["browser"] == kind
    with pytest.raises(webui.Problem, match="Opera or Firefox"):
        webui.clean_config({"sources": ["extension"], "browser": "safari", "routes": [route]})
