"""What differs between Windows, macOS and Linux, in one place: file locks, process flags, the interpreter for
background processes, finding running programs, starting a browser, opening files and terminal windows,
desktop notifications on macOS and Linux, the display language, desktop entries and start-at-login.

Windows keeps what AirFare always did there (msvcrt locks, pythonw.exe, tasklist, the Startup folder shortcut
install.ps1 makes; its PowerShell toasts stay in notify.py). macOS and Linux use their own tools: fcntl locks,
pgrep, `open`/`xdg-open`, AppleScript or notify-send, a LaunchAgent or an XDG autostart entry. Linux here means
any freedesktop.org desktop (the other Unix-likes take the same path).
"""
from __future__ import annotations

import functools
import logging
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
from pathlib import Path

log = logging.getLogger(__name__)

WINDOWS = sys.platform == "win32"
MACOS = sys.platform == "darwin"
LINUX = not (WINDOWS or MACOS)

NAME = "AirFare"
# The LaunchAgent's label on macOS (the same name notifications use on Windows, see notify.APP_ID).
LABEL = "AirFare.FlightPrices"

if WINDOWS:
    import msvcrt
else:
    import fcntl

# ----- processes ------------------------------------------------------------------------------------------

# Windows: helper programs run without a console window, interactive ones in a new console, background
# processes apart from AirFare's own. The flags don't exist elsewhere, where Popen takes 0 for "none".
NO_WINDOW = subprocess.CREATE_NO_WINDOW if WINDOWS else 0
NEW_CONSOLE = subprocess.CREATE_NEW_CONSOLE if WINDOWS else 0
DETACHED = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP if WINDOWS else 0
# Extra places to look for programs: a LaunchAgent's PATH is only /usr/bin:/bin:/usr/sbin:/sbin, so Homebrew's
# and the usual per-user folders aren't on it.
EXTRA_PATH = () if WINDOWS else ("/opt/homebrew/bin", "/usr/local/bin", str(Path.home() / ".local" / "bin"))


def which(name: str) -> str | None:
    """A program on PATH, or in one of EXTRA_PATH's folders."""
    return shutil.which(name) or (shutil.which(name, path=os.pathsep.join(EXTRA_PATH)) if EXTRA_PATH else None)


def background_python() -> str:
    """The interpreter for AirFare's background processes: pythonw.exe on Windows (no console window), else
    this one."""
    if WINDOWS:
        pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        if os.path.exists(pythonw):
            return pythonw
    return sys.executable


def venv_python(root: Path) -> Path:
    """The Python in AirFare's own environment (made by install.ps1 or install.sh)."""
    return root / ".venv" / ("Scripts/python.exe" if WINDOWS else "bin/python")


def start_detached(cmd: list[str], cwd: Path) -> None:
    """Start a process that outlives this one and has no window or terminal of its own."""
    if WINDOWS:
        subprocess.Popen(cmd, cwd=cwd, creationflags=DETACHED)
    else:
        subprocess.Popen(cmd, cwd=cwd, start_new_session=True, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def tree_options() -> dict:
    """Popen options for a process whose whole tree kill_tree() can end later (and, on Windows, no window)."""
    return {"creationflags": NO_WINDOW} if WINDOWS else {"start_new_session": True}


def kill_tree(pid: int) -> None:
    """End a process started with tree_options() and every process it started."""
    if WINDOWS:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True, creationflags=NO_WINDOW)
        return
    try:
        os.killpg(pid, signal.SIGKILL)       # its own session, so its group id is its pid
    except (ProcessLookupError, PermissionError):
        pass


def running(process: str | tuple[str, ...]) -> bool:
    """Whether a program with this process name (or any of these names) is running for anyone on this computer."""
    names = (process,) if isinstance(process, str) else process
    for name in names:
        if WINDOWS:
            # tasklist answers in the console's code page; its "no tasks" message may hold letters ANSI can't decode.
            r = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {name}", "/NH"], capture_output=True, text=True,
                               encoding="oem", errors="replace", creationflags=NO_WINDOW)
            if name in r.stdout.lower():
                return True
            continue
        try:
            if subprocess.run(["pgrep", "-x", name], capture_output=True).returncode == 0:
                return True
        except OSError:                      # no pgrep (a very small Linux): AirFare starts the browser anyway
            return False
    return False


def start_browser(exe: Path, args: list[str]) -> None:
    """Start a browser on macOS or Linux. On macOS it opens behind the window in use (open -g); there and on
    Linux the window can't be started minimized, so it shows normally. (Windows: see extension.py.)"""
    app = next((p for p in exe.parents if p.suffix == ".app"), None) if MACOS else None
    cmd = ["open", "-g", "-a", str(app), "--args", *args] if app else [str(exe), *args]
    start_detached(cmd, Path.home())


def open_path(path: Path | str) -> None:
    """Open a file or folder in its usual program (a folder in Explorer, Finder or the file manager)."""
    if WINDOWS:
        os.startfile(path)
    else:
        start_detached(["open" if MACOS else "xdg-open", str(path)], Path.home())


class NoTerminal(ValueError):
    """No terminal program to open a window in. (A ValueError, so Settings shows its message as it is.)"""


def open_terminal(title: str, argv: list[str], cwd: Path) -> None:
    """Run an interactive command in a new terminal window on macOS or Linux, which stays open afterwards so
    its last words can be read. (Windows uses cmd /k in a new console: see the callers.)"""
    command = (f"printf '\\033]0;%s\\007' {shlex.quote(title)}; cd {shlex.quote(str(cwd))} && {shlex.join(argv)}; "
               "echo; printf 'Press Enter to close this window. '; read _")
    if MACOS:
        subprocess.Popen(["osascript", "-e", "on run argv", "-e", 'tell application "Terminal"', "-e", "activate",
                          "-e", "do script (item 1 of argv)", "-e", "end tell", "-e", "end run", command],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    for program, flag in (("x-terminal-emulator", "-e"), ("gnome-terminal", "--"), ("konsole", "-e"),
                          ("xfce4-terminal", "-x"), ("mate-terminal", "-x"), ("kitty", None), ("alacritty", "-e"),
                          ("xterm", "-e")):
        exe = shutil.which(program)
        if exe:
            start_detached([exe, *([flag] if flag else []), "sh", "-c", command], cwd)
            return
    raise NoTerminal(f"No terminal program found. Run this in a terminal instead: {shlex.join(argv)}")


# ----- file locks -----------------------------------------------------------------------------------------

class FileLock:
    """A lock on one file that every process sees (also a second one in the same process). The system
    releases it if the process dies, so a crashed check never leaves AirFare locked."""

    def __init__(self, path: Path):
        self.path = path
        self.f = None

    def acquire(self) -> bool:
        f = open(self.path, "w")
        try:
            if WINDOWS:
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            f.close()
            return False
        self.f = f
        return True

    def release(self) -> None:
        if self.f:
            try:
                if WINDOWS:
                    self.f.seek(0)
                    msvcrt.locking(self.f.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(self.f.fileno(), fcntl.LOCK_UN)
            finally:
                self.f.close()
                self.f = None


# ----- notifications (macOS and Linux; Windows toasts are in notify.py) ------------------------------------

def _plain(text: str, limit: int = 300) -> str:
    return re.sub(r"[\x00-\x1f\x7f]+", " ", str(text)).strip()[:limit]


@functools.lru_cache(maxsize=None)
def _notify_send_actions() -> bool:
    """Whether this notify-send can show buttons and say which one was clicked (libnotify 0.7.10 and later)."""
    try:
        r = subprocess.run(["notify-send", "--help"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return "--action" in r.stdout


# Waits for the notification (notify-send --wait prints the action clicked) and opens what that action names.
# The targets come in as environment variables, so nothing from the notification ever runs as a command.
_CLICK_SCRIPT = """c=$(notify-send "$@") || exit 0
case "$c" in default) t=$T_default;; b0) t=$T_b0;; b1) t=$T_b1;; b2) t=$T_b2;; *) exit 0;; esac
[ -n "$t" ] && exec xdg-open "$t"
"""


def notify(title: str, lines: list[str], click: str | None = None, buttons: list[tuple[str, str]] = (),
           urgent: bool = False, icon: Path | None = None) -> bool:
    """A desktop notification on macOS or Linux. `click` and the buttons are URIs to open.

    Linux (notify-send): a click opens `click`, and the buttons show as buttons, when notify-send can report
    clicks (libnotify 0.7.10+); an urgent one stays until dismissed. Older notify-send shows the text only.
    macOS: terminal-notifier, when installed (brew install terminal-notifier), opens `click` on a click;
    otherwise AppleScript shows the text only (a click there can't open anything). There are no buttons on
    macOS: the dashboard a click opens has the same links."""
    title, body = _plain(title), "\n".join(_plain(l) for l in lines if l)
    try:
        if MACOS:
            notifier = which("terminal-notifier")
            if notifier:
                cmd = [notifier, "-title", NAME, "-subtitle", title, "-message", body or title, "-group", NAME]
                cmd += (["-open", click] if click else []) + (["-sound", "default"] if urgent else [])
            else:
                script = ["on run argv", "display notification (item 2 of argv) with title (item 1 of argv)"
                          + (' sound name "Glass"' if urgent else ""), "end run"]
                cmd = ["osascript", *[a for line in script for a in ("-e", line)], title, body or " "]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                log.warning("notification failed: %s", (r.stderr or r.stdout).strip()[:300])
            return r.returncode == 0
        # notify-send reads simple markup in the body (& < > would break it); the summary is plain text.
        args = [f"--app-name={NAME}", *([f"--icon={icon}"] if icon and icon.exists() else []),
                *(["--urgency=critical"] if urgent else [])]
        text = [title, body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")]
        targets = {"default": click, **{f"b{i}": uri for i, (_, uri) in enumerate(buttons[:3])}}
        if any(targets.values()) and _notify_send_actions():
            actions = [f"--action={key}={label}" for key, label in
                       [("default", "Open"), *((f"b{i}", _plain(lbl, 40)) for i, (lbl, _) in enumerate(buttons[:3]))]
                       if targets.get(key)]
            env = {**os.environ, **{f"T_{k}": v for k, v in targets.items() if v}}
            subprocess.Popen(["sh", "-c", _CLICK_SCRIPT, "sh", *args, *actions, "--wait", "--", *text], env=env,
                             start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
            return True
        r = subprocess.run(["notify-send", *args, "--", *text], capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            log.warning("notification failed: %s", (r.stderr or r.stdout).strip()[:300])
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired) as e:
        log.warning("notification failed (%s): %s", "notify-send" if LINUX else "osascript", e)
        return False


# ----- display language -----------------------------------------------------------------------------------

def ui_language() -> str:
    """The two-letter code of the user's display language ("" when unknown)."""
    if WINDOWS:
        try:
            import ctypes
            primary = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
        except (AttributeError, OSError):
            return ""
        return {0x09: "en", 0x0A: "es", 0x19: "ru"}.get(primary, "")
    if MACOS:
        mac = _mac_language()
        if mac:
            return mac
    # The variables gettext reads, in its order; then whatever locale Python was started with.
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = (os.environ.get(var) or "").split(":")[0]
        if value and value not in ("C", "POSIX") and not value.startswith("C."):
            return value[:2].lower()
    import locale
    value = locale.getlocale()[0] or ""
    return value[:2].lower() if value not in ("C", "POSIX") else ""


@functools.lru_cache(maxsize=None)
def _mac_language() -> str:
    """The first language in System Settings → General → Language & Region (LaunchAgents have no LANG)."""
    try:
        out = subprocess.run(["defaults", "read", "-g", "AppleLanguages"], capture_output=True, text=True,
                             timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""
    m = re.search(r'"?([A-Za-z]{2})[-_A-Za-z]*"?\s*[,)\n]', out.replace("(", "", 1))
    return m.group(1).lower() if m else ""


# ----- desktop entries and start-at-login ------------------------------------------------------------------

def _data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


def _config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")


def exec_arg(arg: str) -> str:
    """One argument for a desktop entry's Exec key (freedesktop.org Desktop Entry spec, "The Exec key")."""
    if re.fullmatch(r"[\w/.,:+=@-]+", arg):
        return arg
    quoted = '"' + re.sub(r'(["`$\\])', r"\\\1", arg) + '"'
    return quoted.replace("\\", "\\\\").replace("%", "%%")      # the string escapes come on top of the quoting


def desktop_entry(name: str, comment: str, args: list[str], root: Path, extra: dict | None = None) -> str:
    def value(text: str) -> str:
        return str(text).replace("\\", "\\\\").replace("\n", "\\n")
    fields = {"Type": "Application", "Version": "1.5", "Name": name, "Comment": comment,
              "Exec": " ".join(exec_arg(a) if a not in ("%u", "%U") else a for a in args), "Path": value(root),
              "Icon": value(root / "assets" / "airfare-256.png"), "Terminal": "false", **(extra or {})}
    return "[Desktop Entry]\n" + "".join(f"{k}={v}\n" for k, v in fields.items())


def app_entry_path() -> Path:
    """Where AirFare's own entry in the app menu or Applications goes (Linux: also its airfare: link handler)."""
    if MACOS:
        return Path.home() / "Applications" / f"{NAME}.app"
    if LINUX:
        return _data_home() / "applications" / "airfare.desktop"
    return Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / f"{NAME}.lnk"


def add_app_entry(root: Path) -> Path:
    """AirFare in the app menu (Linux, a desktop entry that also opens airfare: links) or in ~/Applications
    (macOS, a small AppleScript app that opens Settings). Windows: install.ps1 makes the Start menu shortcut."""
    path = app_entry_path()
    python = venv_python(root)
    if LINUX:
        text = desktop_entry(NAME, "AirFare: flights, settings and prices", [str(python), "-m", "airfare", "link", "%u"],
                             root, {"Categories": "Utility;Network;", "MimeType": "x-scheme-handler/airfare;",
                                    "StartupNotify": "false"})
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        return path
    if MACOS:
        def lit(text) -> str:                # an AppleScript string literal
            return '"' + str(text).replace("\\", "\\\\").replace('"', '\\"') + '"'
        script = (f"do shell script \"cd \" & quoted form of {lit(root)} & \" && \" & quoted form of {lit(python)} & "
                  "\" -m airfare setup > /dev/null 2>&1 &\"")
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["osacompile", "-o", str(path), "-e", script], check=True, capture_output=True, timeout=60)
        icon = path / "Contents" / "Resources" / "applet.icns"
        png = root / "assets" / "airfare-256.png"
        if png.exists():                     # AirFare's icon instead of the AppleScript one, when sips can convert it
            subprocess.run(["sips", "-s", "format", "icns", str(png), "--out", str(icon)], capture_output=True, timeout=60)
            subprocess.run(["touch", str(path)], capture_output=True)
        return path
    raise NotImplementedError("install.ps1 makes AirFare's shortcuts on Windows")


def login_item_path() -> Path:
    """Where the entry that starts AirFare's background checker at login lives."""
    if MACOS:
        return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
    if LINUX:
        return _config_home() / "autostart" / "airfare.desktop"
    return Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / f"{NAME}.lnk"


def add_login_item(root: Path) -> Path:
    """Start `python -m airfare service` at every login: a LaunchAgent on macOS, an XDG autostart entry on Linux.
    It first runs at the next login, like the Startup shortcut install.ps1 makes on Windows."""
    path = login_item_path()
    python = venv_python(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if MACOS:
        import plistlib
        plist = {"Label": LABEL, "ProgramArguments": [str(python), "-m", "airfare", "service"],
                 "WorkingDirectory": str(root), "RunAtLoad": True, "ProcessType": "Interactive",
                 "LimitLoadToSessionType": "Aqua"}   # the signed-in desktop session: notifications, browser, tray
        path.write_bytes(plistlib.dumps(plist))
        return path
    if LINUX:
        path.write_text(desktop_entry(NAME, "AirFare: checks flight prices at login and on its schedule",
                                      [str(python), "-m", "airfare", "service"], root,
                                      {"NoDisplay": "true", "X-GNOME-Autostart-enabled": "true"}), encoding="utf-8")
        return path
    raise NotImplementedError("install.ps1 makes the Startup shortcut on Windows")


def remove_login_item() -> None:
    path = login_item_path()
    if MACOS and path.exists():
        subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"], capture_output=True)
    path.unlink(missing_ok=True)
