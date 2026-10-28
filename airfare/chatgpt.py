"""ChatGPT through the user's own ChatGPT account, with OpenAI's Codex app (the ChatGPT counterpart of the
Claude Code CLI AirFare uses for Claude). Checks then count against the ChatGPT plan, with no API key.

`codex exec` answers one prompt without any window; `codex exec resume <thread id>` continues the
conversation, which Codex keeps in its own folder (~/.codex). AirFare runs it in an empty folder of its own,
read-only, and asks it only to write its answer. Codex prints one JSON event per line: thread.started
carries the thread id, item.completed with an agent_message carries the answer, turn.completed the token
usage, and turn.failed or error events say what went wrong.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import platform
from .config import PROJECT_DIR

log = logging.getLogger(__name__)

# Codex's working folder for AirFare: empty and outside AirFare's data, so there is nothing for it to look at.
WORK_DIR = Path(tempfile.gettempdir()) / "airfare-chatgpt"
TIMEOUT = 15 * 60
MODEL_RE = re.compile(r"^[a-z0-9][a-z0-9.\-]{1,40}$")
THREAD_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")
SAFE_ARG = re.compile(r"^[\w.:\\/=~\-]+$")        # what may reach cmd.exe when Codex is only an npm .cmd shim
# Codex only answers and, for lookups, searches the web: its shell and command tools are off, so it can't read
# files or run anything, and so are its browser, computer, app and plugin tools. The user's own Codex settings
# (other tools or servers they set up) don't apply to AirFare's runs.
LOCKED = ("shell_tool", "unified_exec")
OPTIONAL_OFF = ("browser_use", "browser_use_external", "computer_use", "in_app_browser", "apps", "plugins")


class ChatGPTError(RuntimeError):
    pass


@dataclass
class Reply:
    text: str
    session_id: str
    context_tokens: int


def _native(shim: Path) -> Path | None:
    """The codex.exe an npm install's .cmd shim starts (running it directly keeps cmd.exe out of the way)."""
    for base in (shim.parent / "node_modules", shim.parent.parent):
        for pattern in ("@openai/codex-win32-*/vendor/*/bin/codex.exe",
                        "@openai/codex/node_modules/@openai/codex-win32-*/vendor/*/bin/codex.exe"):
            found = sorted(base.glob(pattern))
            if found:
                return found[0]
    return None


def codex_path() -> str | None:
    """codex.exe: on PATH, or where OpenAI's installer or npm put it (a AirFare started before the install
    doesn't see the new PATH yet). An npm .cmd shim is swapped for the program it starts when possible.
    On macOS and Linux: codex on PATH, in ~/.local/bin or Homebrew's folders, or where OpenAI's installer keeps it."""
    if not platform.WINDOWS:
        standalone = Path.home() / ".codex" / "packages" / "standalone" / "current" / "bin" / "codex"
        return next((str(c) for c in (platform.which("codex"), standalone) if c and Path(c).is_file()), None)
    local, home, appdata = (os.environ.get(v, "") for v in ("LOCALAPPDATA", "USERPROFILE", "APPDATA"))
    for candidate in (shutil.which("codex"),
                      Path(local) / "Programs" / "OpenAI" / "Codex" / "bin" / "codex.exe",
                      Path(home) / ".codex" / "packages" / "standalone" / "current" / "bin" / "codex.exe",
                      Path(appdata) / "npm" / "codex.cmd"):
        if candidate and Path(candidate).is_file():
            path = Path(candidate)
            if path.suffix.lower() in (".cmd", ".bat"):
                path = _native(path) or path
            return str(path)
    return None


def login_status() -> dict:
    """Whether the Codex app is installed and signed in (it says only that, never which account)."""
    exe = codex_path()
    if not exe:
        return {"installed": False, "logged_in": False}
    try:
        r = subprocess.run([exe, "login", "status"], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=30, creationflags=platform.NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"installed": True, "logged_in": False, "error": f"Couldn't ask the Codex app whether it's signed in: {e}"}
    return {"installed": True, "logged_in": r.returncode == 0}


def _console(title: str, command: str) -> None:
    subprocess.Popen(f'cmd /k "title {title} & {command}"', cwd=PROJECT_DIR, creationflags=subprocess.CREATE_NEW_CONSOLE)


def open_login_console() -> None:
    """A console window that runs Codex's own ChatGPT sign-in (it opens the browser)."""
    exe = codex_path()
    if not exe:
        raise ChatGPTError("The Codex app isn't installed yet")
    if not platform.WINDOWS:
        platform.open_terminal("AirFare: ChatGPT login", [exe, "login"], PROJECT_DIR)
        return
    _console("AirFare: ChatGPT login", f'"{exe}" login')


def _call(cmd: list[str], prompt: str) -> subprocess.CompletedProcess:
    """Run Codex with the prompt on stdin. On timeout the whole process tree ends, not just its first process."""
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                         encoding="utf-8", errors="replace", cwd=WORK_DIR, **platform.tree_options())
    try:
        out, err = p.communicate(prompt, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        platform.kill_tree(p.pid)
        p.communicate()
        raise
    return subprocess.CompletedProcess(cmd, p.returncode, out, err)


def rules_id(system: str) -> str:
    """A short fingerprint of the rules: a conversation started under other rules starts afresh."""
    return hashlib.sha256(system.encode("utf-8")).hexdigest()[:12]


def parse_events(stdout: str) -> dict:
    """thread id, answer, usage and errors from Codex's JSON events (older versions named fields differently)."""
    out = {"thread_id": None, "messages": [], "usage": {}, "errors": []}
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = ev.get("type")
        if kind == "thread.started" and ev.get("thread_id"):
            out["thread_id"] = str(ev["thread_id"])
        elif kind == "item.completed":
            item = ev.get("item") or {}
            item_type = item.get("type") or item.get("item_type")
            if item_type in ("agent_message", "assistant_message") and isinstance(item.get("text"), str):
                out["messages"].append(item["text"])
        elif kind == "turn.completed":
            out["usage"] = ev.get("usage") or {}
        elif kind == "turn.failed":
            out["errors"].append(str((ev.get("error") or {}).get("message") or "the turn failed"))
        elif kind == "error" and ev.get("message") and not str(ev["message"]).startswith("Reconnecting"):
            out["errors"].append(str(ev["message"]))
    return out


def run(prompt: str, thread_id: str | None = None, model: str | None = None, web: bool = False,
        schema: dict | None = None, keep: bool = True) -> tuple[str, dict]:
    """One answer from Codex, continuing thread_id if given. Returns (answer, parsed events)."""
    exe = codex_path()
    if not exe:
        raise ChatGPTError("The Codex app isn't installed: install it with OpenAI's installer, then sign in to ChatGPT")
    if model and not MODEL_RE.match(model):
        raise ChatGPTError("Pick a ChatGPT model from the list")
    if thread_id and not THREAD_RE.match(thread_id):
        log.warning("ignoring a ChatGPT conversation id that doesn't look like one")
        thread_id = None
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    off = list(OPTIONAL_OFF)
    with tempfile.TemporaryDirectory(prefix="airfare-chatgpt-") as tmp:
        last = Path(tmp) / "answer.txt"
        schema_file = Path(tmp) / "schema.json"
        if schema and not thread_id:
            schema_file.write_text(json.dumps(schema), encoding="utf-8")
        while True:
            cmd = [exe, "exec"] + (["resume", thread_id] if thread_id else [])
            # Read-only, never asking, no shell: Codex answers (and searches the web for lookups), nothing else.
            cmd += ["--ignore-user-config", "--skip-git-repo-check", "--json", "-o", str(last),
                    "-c", "sandbox_mode=read-only", "-c", "approval_policy=never",
                    "-c", f"web_search={'live' if web else 'disabled'}"]
            for feature in (*LOCKED, *off):
                cmd += ["--disable", feature]
            if model:
                cmd += ["-m", model]
            if schema and not thread_id:
                cmd += ["--output-schema", str(schema_file)]
            if not keep:
                cmd += ["--ephemeral"]
            cmd += ["-"]                                       # the prompt comes on stdin
            if exe.lower().endswith((".cmd", ".bat")) and not all(SAFE_ARG.match(a) for a in cmd[1:]):
                # cmd.exe would read special characters in these folder names as commands.
                raise ChatGPTError("Install the Codex app with OpenAI's own installer, not npm, as AirFare Settings explains")
            try:
                r = _call(cmd, prompt)
            except subprocess.TimeoutExpired:
                raise ChatGPTError("ChatGPT didn't answer within 15 minutes") from None
            except OSError as e:
                raise ChatGPTError(f"Couldn't start the Codex app ({type(e).__name__})") from None
            # A newer Codex may have dropped one of the optional switches; the shell ones are never dropped.
            gone = re.search(r"Unknown feature flag: (\w+)", r.stdout + r.stderr)
            if r.returncode != 0 and gone and gone.group(1) in off:
                log.warning("this Codex has no %s feature; running without that switch", gone.group(1))
                off.remove(gone.group(1))
                continue
            break
        events = parse_events(r.stdout)
        answer = last.read_text(encoding="utf-8", errors="replace") if last.exists() else ""
    answer = answer.strip() or (events["messages"][-1] if events["messages"] else "")
    if r.returncode != 0 or not answer:
        detail = events["errors"][-1] if events["errors"] else (r.stderr.strip().splitlines() or ["no answer"])[-1]
        if "401" in detail or "not logged in" in detail.lower() or "unauthorized" in detail.lower():
            raise ChatGPTError("ChatGPT isn't signed in: press Log in to ChatGPT in AirFare Settings")
        raise ChatGPTError(f"ChatGPT: {detail[:200]}")
    return answer, events


def ask(prompt: str, system: str, thread_id: str | None, model: str | None = None) -> Reply:
    """One check: a new conversation starts with AirFare's rules; a continued one already has them."""
    try:
        text, events = run(prompt if thread_id else f"{system}\n\n---\n\n{prompt}", thread_id, model)
    except ChatGPTError as e:
        if not thread_id or "signed in" in str(e):
            raise
        log.warning("ChatGPT conversation %s couldn't continue (%s); starting a new one", thread_id, e)
        text, events = run(f"{system}\n\n---\n\n{prompt}", None, model)
        thread_id = None
    usage = events["usage"]
    total = int(usage.get("input_tokens") or 0) + int(usage.get("output_tokens") or 0)   # the thread's running total
    return Reply(text, events["thread_id"] or thread_id or "", total)
