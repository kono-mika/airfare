"""Build the AirFare zip to set it up on another PC: the app and its install guides, and nothing of yours.

    python tools/make_portable.py          ->  dist/AirFare.zip

Only listed files go in (never data/, .venv/, logs, caches or tests). Before zipping, every file is searched
for this PC's API keys, Claude and DeepSeek session ids, Claude account, routes and airport codes, user name,
computer name and folder paths; the build stops if any appear, naming only the kind of data found.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from airfare import __version__, brand  # noqa: E402
from airfare.config import DATA_DIR, load_config  # noqa: E402

import markdown  # noqa: E402

INCLUDE = {
    ".": ["AirFare.exe", "install.ps1", "uninstall.ps1", "install.sh", "uninstall.sh", "requirements.txt", "README.md",
          "LICENSE"],
    "airfare": ["*.py", "static/*.html"],
    "extension": ["manifest.json", "*.js", "*.html", "icons/*.png"],
    "extension-firefox": ["manifest.json", "*.js", "*.html", "icons/*.png"],
    "tools": ["make_firefox.py"],          # makes the Firefox add-on's upload for signing (README, Firefox)
    "assets": ["airfare.ico", "airfare-256.png"],
    "launcher": ["AirFare.cs", "build.ps1"],
}
# Install guide per language: source in docs/, page in the zip, and the language's own name for the switcher.
GUIDES = {"en": ("INSTALL_EN.md", "Install-EN.html", "English"),
          "es": ("INSTALL_ES.md", "Install-ES.html", "Español"),
          "ru": ("INSTALL_RU.md", "Install-RU.html", "Русский")}

GUIDE_PAGE = """<!doctype html><html lang="{lang}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>
<link rel="icon" href="__FAVICON__"><style>/*TOKENS*/
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--paper); color:var(--ink); font:16px/1.6 var(--text); }}
body::before {{ content:""; display:block; height:6px; background:var(--stripe); }}
main {{ max-width:720px; margin:0 auto; padding:28px 20px 64px; }}
.top {{ display:flex; justify-content:space-between; align-items:center; gap:12px; }}
.brand {{ display:flex; align-items:center; gap:10px; font:600 22px var(--display); }} .brand .logo {{ width:36px; height:36px; }}
.sky {{ width:100%; max-width:520px; color:var(--muted); display:block; margin:12px 0 4px; }}
h1 {{ font:600 32px/1.15 var(--display); margin:8px 0 12px; }}
h2 {{ font:600 21px/1.25 var(--display); margin:34px 0 8px; padding-top:18px; border-top:1px solid var(--line); }}
a {{ color:var(--sky); }} li {{ margin:4px 0; }} strong {{ font-weight:600; }}
.langs {{ display:flex; gap:14px; font-size:15px; }} .langs b {{ font-weight:600; }}
code {{ background:var(--soft); border-radius:5px; padding:1px 6px; font:14px Consolas,"Cascadia Mono",monospace; }}
@media print {{ body::before, .sky {{ display:none; }} }}
</style></head><body><main>
<div class="top"><div class="brand"><!--LOGO-->AirFare</div><nav class="langs">{langs}</nav></div>
<!--SKY-->
{body}
</main></body></html>"""


def _json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def secrets() -> tuple[dict[str, str], set[str]]:
    """What would identify this PC or its owner, as {text: kind}, plus the owner's airport codes.

    API keys, Claude and DeepSeek session ids (state, history, conversation files), the Claude account
    (email, organisation), route names and pasted links, and the user, computer and folder names.
    """
    found: dict[str, str] = {}

    def add(value, kind: str, shortest: int = 4):
        if isinstance(value, str) and len(value.strip()) >= shortest:
            found.setdefault(value.strip(), kind)

    def walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if re.search(r"key|token|secret", k, re.I):
                    add(v, "an API key", 8)
                elif re.search(r"session_id|conversation", k, re.I):
                    add(v, "an analyst session id", 8)
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    data = DATA_DIR                      # wherever this PC keeps it (AIRFARE_DATA can move it)
    cfg = load_config()                  # read as AirFare reads it: the API keys decrypted (secrets.py)
    walk(cfg)
    for name in ("state.json", "history.json", "price_research.json"):
        walk(_json(data / name))
    # Earlier conversations: state.json keeps their ids under previous_sessions.
    for slot in [(_json(data / "state.json") or {})] + [v for v in (_json(data / "state.json") or {}).values() if isinstance(v, dict)]:
        for old in slot.get("previous_sessions") or []:
            if isinstance(old, dict):
                add(old.get("id"), "an analyst session id", 8)
    # Routes that live on only as an earlier tab on the dashboard.
    for route in ((_json(data / "dashboard.json") or {}).get("routes") or {}).values():
        if isinstance(route, dict):
            add(route.get("name"), "a route name")
    for folder in ("deepseek", "openai"):              # the API analysts' stored conversations
        for f in (data / folder).glob("*.json"):
            add(f.stem, "an analyst session id", 8)
            walk(_json(f))
    codes = set()
    for route in cfg.get("routes") or []:
        add(route.get("name"), "a route name")
        codes.update(c.lower() for c in (route.get("origin"), route.get("destination")) if c)
        for page in route.get("manual_pages") or []:
            add(page.get("url"), "a route link")
    # Routes deleted from Settings still live on in the price history.
    for route in ((_json(data / "history.json") or {}).get("routes") or {}).values():
        if isinstance(route, dict):
            add(route.get("name"), "a route name")
    for record in _json(data / "price_history.json") or []:
        if isinstance(record, dict):
            add(record.get("route_name"), "a route name")
            add(record.get("url"), "a route link", 12)
            codes.update(str(c).lower() for c in (record.get("origin"), record.get("destination")) if c)
    try:
        from airfare.analyst import claude_command
        account = json.loads(subprocess.run([claude_command(), "auth", "status"], capture_output=True, text=True,
                                            encoding="utf-8", errors="replace", timeout=30).stdout or "{}")
        for k in ("email", "orgId", "orgName"):
            add(account.get(k), "the Claude account")
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    for name in ("USERNAME", "COMPUTERNAME", "USERDOMAIN", "USERPROFILE"):
        add(os.environ.get(name), "this PC's user or computer name", 3)
    home = Path.home()
    for value in (str(home), home.name, str(ROOT), ROOT.as_posix()):
        add(value, "this PC's user or computer name", 3)
    return found, codes


def collect() -> list[tuple[Path, str]]:
    files = []
    for folder, patterns in INCLUDE.items():
        base = ROOT / folder
        for pattern in patterns:
            matches = sorted(base.glob(pattern))
            if not matches:
                raise SystemExit(f"missing: {folder}/{pattern}")
            files += [(m, m.relative_to(ROOT).as_posix()) for m in matches if m.is_file()]
    return files


def guides() -> dict[str, str]:
    out = {}
    for lang, (source, target, _) in GUIDES.items():
        text = (ROOT / "docs" / source).read_text(encoding="utf-8")
        title = text.splitlines()[0].lstrip("# ").strip()
        langs = " ".join(f"<b>{name}</b>" if other == lang else f'<a href="{page}" lang="{other}">{name}</a>'
                         for other, (_, page, name) in GUIDES.items())
        out[target] = brand.fill(GUIDE_PAGE.format(lang=lang, title=title, body=markdown.markdown(text), langs=langs))
    return out


TEXT_FILES = (".py", ".js", ".html", ".md", ".json", ".ps1", ".sh", ".cs", ".txt")


def leaks(name: str, blob: bytes, needles: dict[str, str], codes: set[str]) -> list[str]:
    """What personal data a file holds, by kind only: the report never repeats a key or id."""
    hits = set()
    # As text in any alphabet (casefold, not just A-Z), and as UTF-16 the way Windows programs store strings.
    texts = [blob.decode("utf-8", "replace").casefold(), blob.decode("utf-16-le", "replace").casefold(),
             blob[1:].decode("utf-16-le", "replace").casefold()]
    for value, kind in needles.items():
        if any(value.casefold() in text for text in texts):
            hits.add(kind)
    if name.endswith(TEXT_FILES):
        hits.update(f"your airport code {c.upper()}" for c in codes if re.search(rf"\b{re.escape(c)}\b", texts[0]))
    return sorted(hits)


def main() -> None:
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                    str(ROOT / "launcher" / "build.ps1")], check=True)
    files = collect()
    pages = guides()
    needles, codes = secrets()
    problems = []
    for path, name in files:
        problems += [f"{name}: contains {hit}" for hit in leaks(name, path.read_bytes(), needles, codes)]
    for name, text in pages.items():
        problems += [f"{name}: contains {hit}" for hit in leaks(name, text.encode("utf-8"), needles, codes)]
    if problems:
        raise SystemExit("Not built: personal data found\n  " + "\n  ".join(problems))

    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    zip_path = dist / "AirFare.zip"           # the name the install guides use
    zip_path.unlink(missing_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for path, name in files:
            if name.endswith(".sh"):
                # Runnable on macOS and Linux as unzipped: Unix line endings and the executable bit.
                info = zipfile.ZipInfo.from_file(path, f"AirFare/{name}")
                info.external_attr = 0o100755 << 16
                z.writestr(info, path.read_bytes().replace(b"\r\n", b"\n"), zipfile.ZIP_DEFLATED)
            else:
                z.write(path, f"AirFare/{name}")
        for name, text in pages.items():
            z.writestr(f"AirFare/{name}", text)
    copy = dist / "guides"
    shutil.rmtree(copy, ignore_errors=True)
    copy.mkdir()
    for name, text in pages.items():
        (copy / name).write_text(text, encoding="utf-8")
    print(f"{zip_path}  (AirFare {__version__}, {len(files) + len(pages)} files, {zip_path.stat().st_size // 1024} KB)")
    kinds = sorted(set(needles.values()))
    print(f"checked every file for {len(needles)} personal strings ({', '.join(kinds)}) and "
          f"{len(codes)} airport codes of yours: none found")


if __name__ == "__main__":
    main()
