"""Build the Firefox copy of the AirFare extension, extension-firefox/, from extension/.

    python tools/make_firefox.py                -> rewrites extension-firefox/ (run it after changing extension/)
    python tools/make_firefox.py --check        -> lists what is out of date (tests/test_firefox.py fails while any is)
    python tools/make_firefox.py --zip [--id ID] -> dist/airfare-firefox-<version>.zip to sign at addons.mozilla.org

Chrome, Edge, Brave and Opera load extension/ itself. Firefox needs its own manifest (an add-on id, an event page
instead of a service worker, no minimum Chrome version) and the browser.* namespace, whose calls return promises
instead of taking callbacks. Everything else, including which pages the extension may open, is the same code.
"""
from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "extension"
TARGET = ROOT / "extension-firefox"
# Ours, in the maintainer's own namespace, so it can't be a listed add-on's. addons.mozilla.org signs an id for one
# developer only: a copy signed by someone else needs an id of its own (--id).
GECKO_ID = "airfare-collector@kono-mika.github.io"
GECKO = {"id": GECKO_ID,
         # 140 is the first Firefox with the data consent key below; it already runs MAIN-world content scripts (128).
         "strict_min_version": "140.0",
         # Results go only to the AirFare app on this PC (127.0.0.1), never to the developer or anyone else.
         "data_collection_permissions": {"required": ["none"]}}
NOTE = "Built from extension/{name} by tools/make_firefox.py: change that file and run the tool again."


def manifest(chrome: dict, gecko_id: str = GECKO_ID) -> dict:
    out = {k: v for k, v in chrome.items() if k not in ("minimum_chrome_version", "background")}
    # Firefox match patterns can't name a port (bug 1362809): with one, the pattern matches nothing and the extension
    # can't reach AirFare. Without one, it covers every port of that host.
    out["host_permissions"] = [re.sub(r"^(\w+://[^/:]+):\d+/", r"\1/", p) for p in chrome["host_permissions"]]
    out["background"] = {"scripts": ["background.js"]}       # Firefox runs an event page, not a service worker
    out["browser_specific_settings"] = {"gecko": {**GECKO, "id": gecko_id}}
    return out


def background(js: str) -> str:
    # The one callback the Chrome code passes; browser.* calls answer with a promise instead.
    js = re.sub(r"\bchrome\.alarms\.get\(([^,()]+), \((\w*)\) =>", r"browser.alarms.get(\1).then((\2) =>", js)
    js = re.sub(r"\bchrome\.(?=[a-z])", "browser.", js)
    callback = re.search(r"\bbrowser\.\w+\.(?!on\w+\.addListener)\w+\([^()\n]*, \(\w*\) =>.*", js)
    if callback:
        raise SystemExit(f"extension/background.js passes a callback, which browser.* doesn't take: {callback[0]}\n"
                         "Use the promise the call returns, or teach tools/make_firefox.py to convert it.")
    return f"// {NOTE.format(name='background.js')}\n{js}"


def files(gecko_id: str = GECKO_ID) -> dict[str, str | bytes]:
    """Every file of the Firefox build, by its path inside extension-firefox/: text (with \\n line ends) or bytes."""
    chrome = json.loads((SOURCE / "manifest.json").read_text(encoding="utf-8"))
    text = {name: (SOURCE / name).read_text(encoding="utf-8")
            for name in ("background.js", "capture.js", "done.html", "done.js")}
    out: dict[str, str | bytes] = {
        "manifest.json": json.dumps(manifest(chrome, gecko_id), indent=2, ensure_ascii=False) + "\n",
        "background.js": background(text["background.js"]),
        "capture.js": text["capture.js"],
        # The page left open after a check names the browser it is in.
        "done.html": text["done.html"].replace("Chrome", "Firefox").replace(
            "<!doctype html>\n", f"<!doctype html>\n<!-- {NOTE.format(name='done.html')} -->\n", 1),
        "done.js": f"// {NOTE.format(name='done.js')}\n" + text["done.js"].replace("Chrome", "Firefox"),
    }
    for icon in sorted((SOURCE / "icons").glob("*.png")):
        out[f"icons/{icon.name}"] = icon.read_bytes()
    return out


def _same(path: Path, body: str | bytes) -> bool:
    if not path.is_file():
        return False
    if isinstance(body, bytes):
        return path.read_bytes() == body
    return path.read_bytes().replace(b"\r\n", b"\n") == body.encode("utf-8")   # git may check out \r\n


def stale() -> list[str]:
    """The files of extension-firefox/ that differ from a fresh build, or shouldn't be there."""
    want = files()
    have = {p.relative_to(TARGET).as_posix() for p in TARGET.rglob("*") if p.is_file()} if TARGET.exists() else set()
    return sorted({n for n, body in want.items() if not _same(TARGET / n, body)} | (have - set(want)))


def build() -> list[str]:
    changed = stale()
    want = files()
    newline = "\r\n" if b"\r\n" in (SOURCE / "background.js").read_bytes() else "\n"   # as extension/ has them
    for name in changed:
        path = TARGET / name
        if name not in want:
            path.unlink()
        elif isinstance(want[name], bytes):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(want[name])
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(want[name], encoding="utf-8", newline=newline)
    return changed


def make_zip(gecko_id: str = GECKO_ID) -> Path:
    """The upload for addons.mozilla.org: the build's files at the top of the zip, as AMO wants them."""
    want = files(gecko_id)
    version = json.loads(want["manifest.json"])["version"]
    out = ROOT / "dist" / f"airfare-firefox-{version}.zip"
    out.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, body in sorted(want.items()):
            z.writestr(name, body)
    return out


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--check" in args:
        out_of_date = stale()
        print("\n".join(out_of_date) or "extension-firefox is up to date")
        sys.exit(1 if out_of_date else 0)
    if "--zip" in args:
        gecko_id = args[args.index("--id") + 1] if "--id" in args else GECKO_ID
        if not re.fullmatch(r"[\w.+-]+@[\w.-]+", gecko_id):
            sys.exit("An add-on id looks like an email address, for example airfare-collector@yourname.example")
        print(make_zip(gecko_id))
    else:
        print("\n".join(f"wrote extension-firefox/{n}" for n in build()) or "extension-firefox is up to date")
