"""Collect Skyscanner and Aviasales pages through the AirFare extension in the user's everyday browser.

AirFare serves one job on 127.0.0.1:8766. The extension checks for a job once a minute, opens the
pages in a minimized window, and posts back the results feed each page loaded.
"""
from __future__ import annotations

import json
import logging
import os
import re
import secrets
import shutil
import subprocess
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from . import brand, platform
from .i18n import tr
from .results import EXTRA_WAIT, ROBOT_WAIT, PageResult, classify
from .config import PROJECT_DIR, load_state, save_state

log = logging.getLogger(__name__)

PORT = 8766
EXTENSION_DIR = PROJECT_DIR / "extension"
PICKUP_TIMEOUT = 100      # the extension polls every minute; allow for Chrome starting up too
# The browsers the extension can run in (Settings → Price sources), where each keeps its program (the first of those
# named that exists), the page that loads extensions, and the folder it loads: the Chromium ones take extension/
# as it is, Firefox its own build of it (tools/make_firefox.py). "minimize" marks those that show their first window
# normally even when started minimized (Firefox and Opera do): AirFare minimizes its start page's window itself
# (on Windows; see start_chrome_minimized for macOS and Linux).
BROWSERS = {
    "chrome": {"name": "Google Chrome", "exe": r"Google\Chrome\Application\chrome.exe", "process": "chrome.exe",
               "page": "chrome://extensions", "folder": "extension"},
    "edge": {"name": "Microsoft Edge", "exe": r"Microsoft\Edge\Application\msedge.exe", "process": "msedge.exe",
             "page": "edge://extensions", "folder": "extension"},
    "brave": {"name": "Brave", "exe": r"BraveSoftware\Brave-Browser\Application\brave.exe", "process": "brave.exe",
              "page": "brave://extensions", "folder": "extension"},
    "opera": {"name": "Opera", "exe": (r"Programs\Opera\launcher.exe", r"Programs\Opera\opera.exe", r"Opera\launcher.exe",
                                       r"Opera\opera.exe"), "process": "opera.exe",
              "page": "opera://extensions", "folder": "extension", "minimize": True},
    "firefox": {"name": "Mozilla Firefox", "exe": r"Mozilla Firefox\firefox.exe", "process": "firefox.exe",
                "page": "about:debugging#/runtime/this-firefox", "folder": "extension-firefox", "minimize": True},
}
if platform.WINDOWS:
    _PROGRAM_DIRS = [Path(os.environ[var]) for var in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA") if os.environ.get(var)]
elif platform.MACOS:
    # The app bundles in /Applications (or ~/Applications), and the names their processes run under.
    _PROGRAM_DIRS = [Path("/Applications"), Path.home() / "Applications"]
    for kind, app, process in (("chrome", "Google Chrome", "Google Chrome"), ("edge", "Microsoft Edge", "Microsoft Edge"),
                               ("brave", "Brave Browser", "Brave Browser"), ("opera", "Opera", "Opera"),
                               ("firefox", "Firefox", "firefox")):
        BROWSERS[kind].update(exe=f"{app}.app/Contents/MacOS/{process}", process=process)
else:
    # Commands on PATH (packages, Snap and Flatpak exports alike), and the names their processes run under (Linux
    # keeps at most 15 characters of a name).
    _PROGRAM_DIRS = []
    for kind, commands, processes in (
            ("chrome", ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"), ("chrome", "chromium")),
            ("edge", ("microsoft-edge", "microsoft-edge-stable"), ("msedge",)),
            ("brave", ("brave-browser", "brave"), ("brave",)),
            ("opera", ("opera",), ("opera",)),
            ("firefox", ("firefox", "firefox-esr"), ("firefox", "firefox-esr", "firefox-bin"))):
        BROWSERS[kind].update(exe=commands, process=processes)


def browser_kind(kind: str | None) -> str:
    return kind if kind in BROWSERS else "chrome"


def extension_dir(kind: str = "chrome") -> Path:
    """The folder this browser loads the extension from."""
    return PROJECT_DIR / BROWSERS[browser_kind(kind)]["folder"]

# Shown in the window AirFare opens when it has to start Chrome. The extension closes it after the check
# unless it is Chrome's only window (see extension/background.js); then it says the check is done.
START_TITLE = "AirFare"     # the window that shows it is the one to minimize in browsers that start it normally
START_PAGE = f"""<!doctype html><html lang="__LANG__"><head><meta charset="utf-8"><title>{START_TITLE}</title>
<link rel="icon" href="{brand.FAVICON}"><style>{brand.TOKENS_CSS}
body {{ margin:0; min-height:100vh; display:grid; place-items:center; background:var(--paper); color:var(--ink);
  font:16px/1.55 var(--text); border-top:6px solid; border-image:var(--stripe) 1; }}
main {{ max-width:520px; padding:32px 24px; text-align:center; }}
.sky {{ width:100%; color:var(--muted); }} h1 {{ font:600 26px var(--display); margin:8px 0 6px; }}
p {{ color:var(--muted); margin:0; }}
</style></head><body><main>{brand.SKY_SVG}
<h1 id="t">__TITLE__</h1>
<p id="s">__TEXT__</p></main>
<script type="application/json" id="done">__DONE__</script>
<script>
const done = () => {{
  const d = JSON.parse(document.getElementById("done").textContent);
  document.title = "AirFare: " + d[0];
  document.getElementById("t").textContent = d[0];
  document.getElementById("s").textContent = d[1];
}};
setInterval(() => fetch("/start?ping", {{cache: "no-store"}}).catch(done), 4000);
</script></body></html>"""


def start_page(lang: str, browser: str = "Google Chrome") -> bytes:
    done = [tr("Price check done", lang),
            tr("AirFare opened {browser} only for its price check and has closed its own tabs. If {browser} offers to "
               "restore your previous tabs, you can do it in this window. Otherwise, close it.", lang, browser=browser)]
    page = START_PAGE.replace("__LANG__", lang).replace("__TITLE__", tr("Checking flight prices", lang))
    page = page.replace("__TEXT__", tr("AirFare opened this window for its price check. Your own tabs aren't touched, "
                                       "and this window closes by itself when the check is done.", lang))
    return page.replace("__DONE__", json.dumps(done, ensure_ascii=False).replace("<", "\\u003c")).encode("utf-8")


def _manifest() -> dict:
    return json.loads((EXTENSION_DIR / "manifest.json").read_text(encoding="utf-8"))


# The only pages the extension may open: search results on its own sites (manifest.json). Skyscanner
# searches are /<localized>/<localized>/<from>/<to>/<yymmdd>[/<yymmdd>]/, Aviasales ones /search/<code>.
SEARCH_PATH = {"skyscanner": re.compile(r"^/[^/]+/[^/]+/[a-z0-9]{2,8}/[a-z0-9]{2,8}/\d{6}(?:/\d{6})?(?:/|$)", re.I),
               "aviasales": re.compile(r"^/search/[A-Za-z0-9]{6,40}$")}


def allowed(url: str) -> bool:
    """Whether the extension may open this page (background.js checks the same thing on its side)."""
    u = urlparse(url or "")
    if u.scheme != "https" or f"https://{u.netloc}/*" not in _manifest()["host_permissions"]:
        return False
    return bool(SEARCH_PATH["aviasales" if "aviasales" in u.netloc else "skyscanner"].match(u.path))


def supported_hosts() -> list[str]:
    return [urlparse(p.replace("*", "x")).hostname for p in _manifest()["host_permissions"] if "skyscanner" in p]


def latest_version(kind: str = "chrome") -> str:
    """The extension version in this AirFare folder; the browser may still run an older copy until it reloads it."""
    return json.loads((extension_dir(kind) / "manifest.json").read_text(encoding="utf-8"))["version"]


def chrome_path(kind: str = "chrome") -> Path | None:
    """Where the browser's program is, or None when it isn't installed."""
    exe = BROWSERS[browser_kind(kind)]["exe"]
    names = (exe,) if isinstance(exe, str) else exe
    if platform.LINUX:
        return next((Path(p) for p in map(shutil.which, names) if p), None)
    return next((p for p in (d / name for name in names for d in _PROGRAM_DIRS) if p.exists()), None)


def installed_browsers() -> dict[str, bool]:
    return {kind: chrome_path(kind) is not None for kind in BROWSERS}


def chrome_running(kind: str = "chrome") -> bool:
    return platform.running(BROWSERS[browser_kind(kind)]["process"])


def start_chrome_minimized(url: str, kind: str = "chrome") -> None:
    """Start the user's browser minimized and unfocused (Chrome quits at once if started without a window).
    macOS starts it behind the window in use and Linux in a normal window: neither can start one minimized."""
    exe = chrome_path(kind)
    if not exe:
        raise ExtensionError(f"{BROWSERS[browser_kind(kind)]['name']} is not installed")
    if not platform.WINDOWS:
        platform.start_browser(exe, ["--new-window", url])
        return
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 7   # SW_SHOWMINNOACTIVE
    subprocess.Popen([str(exe), "--new-window", url], startupinfo=si)
    browser = BROWSERS[browser_kind(kind)]
    if browser.get("minimize"):
        threading.Thread(target=minimize_when_shown, args=(browser["process"],), daemon=True).start()


def _pids(process: str) -> set[int]:
    r = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {process}", "/FO", "CSV", "/NH"], capture_output=True,
                       text=True, encoding="oem", errors="replace", creationflags=platform.NO_WINDOW)
    return {int(row.split('","')[1]) for row in r.stdout.splitlines() if row.count('","') >= 2}


def minimize_when_shown(process: str, title: str = START_TITLE, seconds: float = 20) -> None:
    """Minimize the window a just-started browser shows AirFare's start page in, once its title says so, giving
    focus back if it took it. Every other window is left alone: the extension's own (robot checks come up in it)
    and any the browser restores."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32")      # its own copy: the types set here don't change ctypes.windll.user32
    for name, args in {"GetWindowThreadProcessId": [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)],
                       "IsWindowVisible": [wintypes.HWND], "IsIconic": [wintypes.HWND],
                       "GetWindowTextW": [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int],
                       "GetWindow": [wintypes.HWND, wintypes.UINT], "ShowWindow": [wintypes.HWND, ctypes.c_int]}.items():
        getattr(user32, name).argtypes = args
    user32.GetWindow.restype = user32.GetForegroundWindow.restype = wintypes.HWND
    done: set[int] = set()
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        pids, shown = _pids(process), []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def each(hwnd, _):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            # Visible top-level windows with no owner (4 = GW_OWNER): the browser's own, not its dialogs.
            if pid.value in pids and hwnd not in done and user32.IsWindowVisible(hwnd) and \
                    not user32.GetWindow(hwnd, 4) and not user32.IsIconic(hwnd):
                text = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(hwnd, text, 256)
                if text.value.startswith(title):
                    shown.append(hwnd)
            return True

        user32.EnumWindows(each, 0)
        for hwnd in shown:
            done.add(hwnd)
            # SW_MINIMIZE hands focus back to the window below; SW_SHOWMINNOACTIVE leaves focus where it is.
            user32.ShowWindow(hwnd, 6 if hwnd == user32.GetForegroundWindow() else 7)
            log.info("minimized the %s window with the start page", process)
        time.sleep(0.2)


class ExtensionError(RuntimeError):
    pass


class _JobServer(ThreadingHTTPServer):
    daemon_threads = True
    # On Windows, SO_REUSEADDR lets a second server bind the same port; elsewhere it only lets a new server take
    # the port while the last one's connections close (without it, a check right after another would fail).
    allow_reuse_address = not platform.WINDOWS


class _Job:
    def __init__(self, pages: list[dict], wait_seconds: int, robot_seconds: int, on_robot, lang: str = "en",
                 browser: str = "Google Chrome", on_taken=None):
        self.id = secrets.token_hex(12)
        self.pages = pages
        self.on_robot = on_robot
        self.on_taken = on_taken
        self.lang = lang
        self.browser = browser
        origins = sorted({f"{urlparse(p['url']).scheme}://{urlparse(p['url']).netloc}/*" for p in pages})
        self.payload = {
            "id": self.id,
            "lang": lang,
            "pages": [{"n": i, "url": p["url"], "site": p.get("site") or "Skyscanner"} for i, p in enumerate(pages)],
            "matches": origins,
            "wait_seconds": wait_seconds,
            "extra_seconds": EXTRA_WAIT,
            "robot_seconds": robot_seconds,
        }
        self.taken = threading.Event()
        self._taking = threading.Lock()
        self.done = threading.Event()
        self.results: list[dict] = []
        self.error: str | None = None
        self.extension_version: str | None = None

    def take(self) -> bool:
        """Hand the job over once: False if it was already taken. on_taken (the limits' page count) runs first,
        and if it fails the job isn't handed over, so no page opens uncounted."""
        with self._taking:
            if self.taken.is_set():
                return False
            if self.on_taken:
                self.on_taken()
            self.taken.set()
            return True


def _handler(job: _Job):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            log.debug("extension server: " + fmt, *args)

        def _reply(self, status: int, body: bytes = b"", ctype: str = "application/json"):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _ours(self) -> bool:
            """Only requests addressed to 127.0.0.1: a web page whose domain points here (DNS rebinding)
            can't read the job or post made-up results."""
            if (self.headers.get("Host") or "").lower() == f"127.0.0.1:{self.server.server_port}":
                return True
            self._reply(403)
            return False

        def do_GET(self):
            if not self._ours():
                return
            if self.path.startswith("/start"):
                return self._reply(200, start_page(job.lang, job.browser), "text/html; charset=utf-8")
            if self.path == "/job":
                # Only the extension sends this header; a plain fetch from a web page can't take the job.
                if not self.headers.get("X-AirFare-Extension"):
                    return self._reply(403)
                job.extension_version = self.headers.get("X-AirFare-Extension") or job.extension_version
                try:
                    if not job.take():
                        return self._reply(204)
                except Exception:
                    log.exception("couldn't count the job's pages; not handing it over")
                    return self._reply(503)
                log.info("extension %s picked up the job", job.extension_version)
                return self._reply(200, json.dumps(job.payload).encode())
            self._reply(404)

        def do_POST(self):
            # JSON only: web pages can't send that cross-site without a preflight, which this server refuses.
            if not self._ours():
                return
            if not (self.headers.get("Content-Type") or "").startswith("application/json"):
                return self._reply(415)
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            except json.JSONDecodeError:
                return self._reply(400)
            if body.get("id") != job.id:
                return self._reply(403)
            if self.path == "/progress":
                if body.get("event") == "robot" and job.on_robot:
                    n = body.get("n")
                    page = job.pages[n] if isinstance(n, int) and 0 <= n < len(job.pages) else {}
                    threading.Thread(target=job.on_robot, args=(page,), daemon=True).start()
                return self._reply(200, b"{}")
            if self.path == "/results":
                job.results = body.get("pages") or []
                job.error = body.get("error")
                job.done.set()
                return self._reply(200, b"{}")
            self._reply(404)

    return Handler


def _to_result(page: dict, raw: dict | None) -> PageResult:
    site = page.get("site") or "Skyscanner"
    res = PageResult(page=page, source=site)
    if raw is None:
        res.status, res.note = "error", "the extension returned nothing for this page"
        return res
    if raw.get("error"):
        res.status, res.note = "error", str(raw["error"])[:200]
        return res
    # Skyscanner sends objects, Aviasales lists of result chunks.
    res.payloads = [p for p in raw.get("payloads") or [] if isinstance(p, (dict, list))]
    res.text = raw.get("text") or ""
    res.final_url = raw.get("url") or ""
    res.seconds = float(raw.get("seconds") or 0)
    if raw.get("robot"):
        res.status, res.note = "blocked", f"{site} robot check was not solved"
    else:
        classify(res)
    return res


def collect(pages: list[dict], wait_seconds: int = 20, on_robot=None, robot_seconds: int = ROBOT_WAIT,
            lang: str = "en", browser: str = "chrome", on_taken=None) -> list[PageResult]:
    """Have the extension (in Chrome, Edge, Brave, Opera or Firefox) open the pages (each names its "site") and
    return what each one showed. on_taken runs when the extension takes the job, before it opens anything."""
    if not pages:
        return []
    kind = browser_kind(browser)
    job = _Job(pages, wait_seconds, robot_seconds, on_robot, lang, BROWSERS[kind]["name"], on_taken)
    try:
        server = _JobServer(("127.0.0.1", PORT), _handler(job))
    except OSError:
        return _all_failed(pages, f"port {PORT} is in use, so the extension can't be reached")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    started = time.monotonic()
    try:
        if not chrome_running(kind):
            log.info("%s isn't running; starting it minimized for the extension", BROWSERS[kind]["name"])
            start_chrome_minimized(f"http://127.0.0.1:{PORT}/start", kind)
        if not job.taken.wait(PICKUP_TIMEOUT):
            return _all_failed(pages, "the AirFare add-on didn't respond (Firefox removes an add-on loaded in "
                                      "about:debugging when it restarts: load it again, or install the signed .xpi)"
                               if kind == "firefox" else "the AirFare extension didn't respond (is it installed and "
                                                         "enabled on your browser's extensions page?)")
        _remember_extension(job.extension_version)
        if not job.done.wait(wait_seconds + EXTRA_WAIT + max(robot_seconds, 0) + 90):
            return _all_failed(pages, "the AirFare extension started but didn't finish in time")
        if job.error:
            return _all_failed(pages, f"the AirFare extension failed: {job.error[:150]}")
    finally:
        server.shutdown()
        server.server_close()
    by_n = {r.get("n"): r for r in job.results if isinstance(r, dict)}
    results = [_to_result(p, by_n.get(i)) for i, p in enumerate(pages)]
    log.info("extension collected %d pages in %.0fs", len(results), time.monotonic() - started)
    return results


def _all_failed(pages: list[dict], note: str) -> list[PageResult]:
    log.error("extension: %s", note)
    return [PageResult(page=p, status="error", note=note, source=p.get("site") or "Skyscanner") for p in pages]


def _remember_extension(version: str | None) -> None:
    state = load_state()
    state["extension_seen"] = datetime.now().isoformat(timespec="minutes")
    state["extension_version"] = version
    save_state(state)
