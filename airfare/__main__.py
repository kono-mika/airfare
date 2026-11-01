"""AirFare command line: run | service | test-alert | setup | chat | login | doctor | link | migrate."""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from . import platform, runner
from .config import CONFIG_FILE, PROJECT_DIR, load_config, load_state


def _console_ok() -> bool:
    return bool(sys.stdout) and sys.stdout.isatty()


def cmd_run(args) -> int:
    cfg = load_config()
    if not cfg["routes"]:
        # First run: ask which flights to track before checking anything.
        from . import webui
        runner.setup_logging(args.verbose)
        webui.serve()
        return 0
    return runner.run(console=args.verbose or _console_ok())


def cmd_service(args) -> int:
    from . import service
    if not load_config()["routes"]:
        from . import webui
        runner.setup_logging(False)
        webui.serve()          # first run: ask which flights to track
        return 0
    return service.serve(skip_startup_check=args.skip_startup_check)


def cmd_test_alert(args) -> int:
    """Show what a LOW PRICE notification looks like, using the latest check's prices."""
    from . import notify
    from .config import REPORTS_DIR, load_history
    from .urls import plan_pages
    cfg, history = load_config(), load_history()
    pages, _ = plan_pages(cfg)
    if not pages:
        print("Add a route first (python -m airfare setup).")
        return 1
    rid, name = pages[0]["route_id"], pages[0]["route_name"]
    run = next((r for r in reversed(history.get("runs", [])) if (r.get("prices_by_route") or {}).get(rid)), {})
    prices = run.get("prices_by_route", {}).get(rid, {})
    best = min(prices.values(), key=lambda p: p["cheapest"], default=None) if prices else None
    from . import links, report
    from .i18n import tr
    ref = report.alert_refs(history.get("routes", {}).get(rid) or {}).get("cheapest") or {}
    title = f"LOW PRICE ✈ {name}: {best['text'] if best else '—'} (test)"
    if best and ref.get("text"):
        title = f"LOW PRICE ✈ {name}: {best['text']} vs {ref['text']} reference (test)"
    lines = ["This is a test of AirFare's LOW PRICE alert. It stays until you dismiss it.",
             run.get("take") or ""]
    lang = cfg.get("language")
    latest = links.for_dashboard(REPORTS_DIR / "latest.html")
    ok = notify.alert(title, lines, [(tr("Book now", lang), pages[0]["url"]), (tr("Dashboard", lang), latest)],
                      open_path=latest, dismiss=tr("Dismiss", lang))
    print("Test alert shown." if ok else "Couldn't show the notification; see data/logs/airfare.log.")
    return 0 if ok else 1


def cmd_setup(args) -> int:
    from . import webui
    runner.setup_logging(_console_ok())
    webui.serve(open_page=not args.no_open, page=args.page)
    return 0


def claude_cli() -> str:
    from .analyst import claude_command
    return claude_command()


def _console(cmd: list[str], env: dict | None = None) -> int:
    """Run an interactive command in its own console window (works from pythonw too). On macOS and Linux it
    runs in this terminal, or in a new terminal window when there is none."""
    if platform.WINDOWS:
        subprocess.Popen(cmd, cwd=PROJECT_DIR, env=env, creationflags=platform.NEW_CONSOLE)
        return 0
    if _console_ok() and sys.stdin and sys.stdin.isatty():
        return subprocess.call(cmd, cwd=PROJECT_DIR, env=env)
    platform.open_terminal("AirFare", cmd, PROJECT_DIR)
    return 0


def cmd_chat(args) -> int:
    cfg = load_config()
    provider = cfg.get("llm_provider") or "claude"
    if provider == "chatgpt":
        from . import chatgpt
        sid, exe = (load_state().get("chatgpt") or {}).get("session_id"), chatgpt.codex_path()
        if not (sid and exe):
            print("No ChatGPT conversation yet (or the Codex app isn't installed). The next check starts one.")
            return 1
        return _console([exe, "resume", sid])
    if provider == "openai":
        print("The OpenAI API conversation is stored in data/openai; there's no console chat for it.")
        return 1
    if provider == "none":
        print("No analyst is set up: AirFare's own rules pick the flights. Choose one in AirFare Settings to chat.")
        return 1
    if provider == "deepseek":
        from . import deepseek
        from .analyst import RULES
        sid = (load_state().get("deepseek") or {}).get("session_id")
        deepseek.chat(sid, cfg.get("deepseek_model") or deepseek.MODELS[0], cfg.get("deepseek_api_key") or "", RULES)
        return 0
    sid = load_state().get("session_id")
    if not sid:
        print("No Claude session yet. It is created by the first price check (python -m airfare run).")
        return 1
    key = analyst_claude_key(cfg)
    if key:
        # The chat must use the same key as the checks, or the CLI would ask for the account's session instead.
        return _console([claude_cli(), "--resume", sid], env={**os.environ, "ANTHROPIC_API_KEY": key})
    return _console([claude_cli(), "--resume", sid])


def analyst_claude_key(cfg: dict) -> str | None:
    from .analyst import claude_key
    return claude_key(cfg)


def open_login_console() -> None:
    """A console window titled AirFare that runs the Claude CLI's own login."""
    if not platform.WINDOWS:
        platform.open_terminal("AirFare: Claude login", [claude_cli(), "auth", "login"], PROJECT_DIR)
        return
    subprocess.Popen(f'cmd /k "title AirFare: Claude login & "{claude_cli()}" auth login"', cwd=PROJECT_DIR,
                     creationflags=subprocess.CREATE_NEW_CONSOLE)


def cmd_login(args) -> int:
    if not platform.WINDOWS and _console_ok() and sys.stdin and sys.stdin.isatty():
        return subprocess.call([claude_cli(), "auth", "login"], cwd=PROJECT_DIR)    # in this terminal
    open_login_console()
    return 0


def cmd_link(args) -> int:
    """An airfare: link (links.py): what AirFare's desktop entry runs on Linux, as AirFare.exe does on Windows.
    Any web page can offer such a link, so only these four names do anything, and nothing else from the link
    is used. Without a link (the app menu entry), Settings opens."""
    name = "settings"
    if args.url:
        text = args.url.strip().lower()
        if not text.startswith("airfare:"):
            return 2
        name = re.split(r"[/?#]", text[len("airfare:"):].strip("/"))[0]
    if name not in ("dashboard", "history", "settings", "start"):
        return 2
    # airfare:start only starts AirFare: the page that opened the link moves on by itself.
    return cmd_setup(argparse.Namespace(no_open=name == "start", page="settings" if name == "start" else name))


def cmd_migrate(args) -> int:
    """Back up and update the data folder (the install scripts run this; every other command does it too)."""
    from . import migrate
    try:
        result = migrate.at_start()
    except migrate.MigrationError as e:
        print(e)
        return 1
    found = result["from"]
    if result["newer"]:
        print(migrate.NEWER_MESSAGE.format(version=found["app"]) + ". Nothing was changed.")
    elif result["steps"]:
        print(f"Updated the data from AirFare {found['app']} to {result['to']['app']}."
              + (f" Backup: {result['backup']}" if result["backup"] else ""))
    else:
        print(f"The data is up to date (AirFare {result['to']['app']}, format {result['to']['schema']}).")
    return 0


def analyst_name(provider: str) -> str:
    return {"deepseek": "DeepSeek", "openai": "ChatGPT (OpenAI API key)", "chatgpt": "ChatGPT (ChatGPT account)",
            "none": "none (AirFare's own rules pick the cheapest and fastest flights)"}.get(provider, "Claude")


KEY_NAMES = {"serpapi_key": "SerpApi key", "deepseek_api_key": "DeepSeek API key",
             "openai_api_key": "OpenAI API key", "anthropic_api_key": "Anthropic API key"}


def cmd_doctor(args) -> int:
    ok = True

    def line(good: bool, text: str):
        nonlocal ok
        ok &= good
        print(("  OK   " if good else "  !!   ") + text)

    print("AirFare doctor")
    from . import migrate, upgrade
    data = migrate.status()
    if data["newer"]:
        line(False, data["message"])
    setup = upgrade.mismatch()
    if setup:
        line(False, setup)
    from .extension import BROWSERS, browser_kind, chrome_path
    from .secrets import ACCOUNT
    cfg = load_config()
    for name in cfg.get("unreadable_keys") or []:
        line(False, f"The saved {KEY_NAMES[name]} can't be decrypted on {ACCOUNT} (config.json from another "
                    "PC or user). Enter it again in AirFare Settings")
    kind = browser_kind(cfg.get("browser"))
    line(chrome_path(kind) is not None, f"{BROWSERS[kind]['name']} is installed (the browser for the extension)")
    if not platform.WINDOWS:
        item = platform.login_item_path()
        line(item.exists(), f"Starts at login: {item}" if item.exists() else
             "AirFare doesn't start at login yet. Run install.sh again")

    provider = cfg.get("llm_provider") or "claude"
    print(f"  ..   Analyst: {analyst_name(provider)}")
    if provider == "chatgpt":
        from . import chatgpt
        status = chatgpt.login_status()
        line(status["installed"], "The Codex app (for ChatGPT) is installed" if status["installed"] else
             "The Codex app isn't installed. Install it with OpenAI's installer (AirFare Settings shows how)")
        if status["installed"]:
            line(status["logged_in"], "Signed in to ChatGPT" if status["logged_in"] else status.get("error") or
                 "Not signed in to ChatGPT. Open AirFare Settings and press 'Log in to ChatGPT'")
    elif provider == "openai":
        from . import openai_api
        key = cfg.get("openai_api_key")
        if not key:
            line(False, "No OpenAI API key. Add it in AirFare Settings (platform.openai.com)")
        else:
            try:
                openai_api.check_key(key)
                line(True, "OpenAI API key works")
            except openai_api.OpenAIError as e:
                line(False, f"OpenAI key problem: {e}")
    elif provider == "deepseek":
        from . import deepseek
        key = cfg.get("deepseek_api_key")
        if not key:
            line(False, "No DeepSeek API key. Add it in AirFare Settings (platform.deepseek.com)")
        else:
            try:
                b = deepseek.balance(key)
                line(b.get("available") is not False, f"DeepSeek key works: balance {b['balance']}"
                     + ("" if b.get("available") is not False else " (not enough credit for API calls)"))
            except deepseek.DeepSeekError as e:
                line(False, f"DeepSeek key problem: {e}")
    elif provider == "claude":
        cli = claude_cli()
        line(Path(cli).exists() or bool(shutil.which(cli)), f"Claude Code CLI found: {cli}")
        from .analyst import login_status
        status = login_status(cfg)
        if status.get("key"):
            line(status["logged_in"], "Anthropic accepts the API key" if status["logged_in"] else status.get("error") or
                 "Anthropic doesn't accept the API key. Add it again in AirFare Settings")
        else:
            line(status["logged_in"], "Claude is logged in" if status["logged_in"] else status.get("error") or
                 "Claude is NOT logged in. Open AirFare and press 'Log in to Claude' (or add an Anthropic API key)")

    line(bool(cfg["routes"]), f"{len(cfg['routes'])} route(s) in {CONFIG_FILE}" if cfg["routes"] else
         "No routes yet. Run:  python -m airfare setup")
    state = load_state()
    sources = cfg.get("sources") or []
    print(f"  ..   Price sources: {', '.join(sources) or 'none'}")
    if "extension" in sources or "aviasales" in sources:
        from .extension import extension_dir, latest_version
        browser, folder = BROWSERS[kind], extension_dir(kind)
        seen = state.get("extension_seen")
        load = (f"In {browser['page']}, press Load Temporary Add-on and pick {folder / 'manifest.json'}, or install "
                "the signed .xpi (README, Firefox)" if kind == "firefox" else f"Load unpacked in {browser['page']}: {folder}")
        line(bool(seen), f"The extension last reported in {seen.replace('T', ' ')}" if seen else
             f"The extension hasn't reported in yet. {load}")
        running, latest = state.get("extension_version"), latest_version(kind)
        if seen and running != latest:
            line(False, f"The browser runs extension v{running}, this folder has v{latest}: " +
                 ("load it again in about:debugging, or sign and install the new version" if kind == "firefox" else
                  f"click its reload arrow in {browser['page']}, or restart {browser['name']}"))
    if "serpapi" in sources:
        key = cfg.get("serpapi_key")
        if not key:
            line(False, "No SerpApi key. Add it in AirFare Settings (free at serpapi.com)")
        else:
            from . import serpapi
            try:
                acct = serpapi.account(key)
                line(True, f"SerpApi key works: {acct.get('total_searches_left')} searches left ({acct.get('plan_name')})")
            except serpapi.SerpApiError as e:
                line(False, f"SerpApi key problem: {e}")
    slot = state if provider == "claude" else (state.get(provider) or {})
    model = {"claude": cfg.get("model") or "account default", "deepseek": cfg.get("deepseek_model"),
             "openai": cfg.get("openai_model"), "chatgpt": cfg.get("chatgpt_model") or "account default"}.get(provider)
    if provider != "none":
        print(f"  ..   Conversation: {slot.get('session_id') or 'not created yet (the next check creates it)'}")
    if provider != "none" and slot.get("session_id"):
        print(f"  ..   Model {model}; this conversation has {slot.get('session_checks', '?')} "
              f"check(s), about {int(slot.get('context_tokens') or 0) // 1000}k tokens "
              f"(a fresh one starts before {cfg.get('session_max_k', 40)}k)")
    return 0 if ok else 1


def _starting(cmd: str, check_install: bool) -> int | None:
    """Before a command reads anything: the setup matches the code, and the data folder is up to date
    (migrate.py). An exit code when the command can't go on."""
    from . import migrate, upgrade
    problem = upgrade.mismatch() if check_install and cmd not in ("migrate", "doctor") else None
    if problem:
        upgrade.note(problem)
        if sys.stderr:
            print(problem, file=sys.stderr)
        return 4
    if cmd in ("migrate", "login"):
        return None
    try:
        migrate.at_start()
    except migrate.MigrationError as e:
        if sys.stderr:
            print(e, file=sys.stderr)
        return 1
    return None


def main(argv=None, check_install: bool = False) -> int:
    p = argparse.ArgumentParser(prog="airfare", description=__doc__)
    sub = p.add_subparsers(dest="cmd")
    r = sub.add_parser("run", help="check prices once, now")
    r.add_argument("-v", "--verbose", action="store_true", help="log to the console too")
    sv = sub.add_parser("service", help="background checker on the Settings schedule (what the startup shortcut runs)")
    sv.add_argument("--skip-startup-check", action="store_true", help="don't check right away, only on the interval")
    sub.add_parser("test-alert", help="show a sample LOW PRICE notification")
    s = sub.add_parser("setup", help="open the settings form")
    s.add_argument("--no-open", action="store_true", help="start the server without opening a browser tab")
    s.add_argument("--page", choices=["settings", "dashboard", "history"], default="settings",
                   help="the page to open (default: settings)")
    sub.add_parser("chat", help="continue the analyst's conversation (Claude or DeepSeek) in a console")
    sub.add_parser("login", help="log the bundled Claude Code CLI in to your Claude account")
    sub.add_parser("doctor", help="check the browser, the analyst's login and settings")
    lk = sub.add_parser("link", help="open an airfare: link (what AirFare's desktop entry runs on Linux)")
    lk.add_argument("url", nargs="?", help="airfare:dashboard, airfare:history, airfare:settings or airfare:start")
    sub.add_parser("migrate", help="back up and update the data folder after an update (the install scripts run it)")
    for stream in (sys.stdout, sys.stderr):
        if stream and hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")   # route names and prices may not fit the console code page
    args = p.parse_args(argv)
    handlers = {"run": cmd_run, "service": cmd_service, "test-alert": cmd_test_alert, "setup": cmd_setup,
                "chat": cmd_chat, "login": cmd_login, "doctor": cmd_doctor, "link": cmd_link, "migrate": cmd_migrate}
    if not args.cmd:
        p.print_help()
        return 0
    stop = _starting(args.cmd, check_install)
    if stop is not None:
        return stop
    return handlers[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main(check_install=True))       # python -m airfare: also check that the setup matches the code
