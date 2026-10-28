"""List the interface texts AirFare translates, and the ones still missing in Spanish or Russian.

    python tools/i18n_keys.py            -> prints the missing ones (tests/test_i18n.py fails while any are)

Texts are found where the code marks them: tr()/trn()/Problem() calls in airfare/*.py, t()/tn()/say() calls
and data-i18n attributes in the pages, plus the few English texts kept in tables (tab names, kinds, tags).
"""
from __future__ import annotations

import ast
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PY_CALLS = {"tr": 0, "trn": 1, "Problem": 0}
JS_CALL = re.compile(r"""\b(?:(?:t|say)\(|tn\([^,()]+,)\s*("(?:[^"\\]|\\.)*")""")
JS_TASK = re.compile(r"""startTask\("[^"]+",\s*("(?:[^"\\]|\\.)*")""")


def _python_keys() -> set[str]:
    keys = set()
    for f in (ROOT / "airfare").glob("*.py"):
        if f.name == "translations.py":
            continue
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
                pos = PY_CALLS.get(name)
                if pos is not None and len(node.args) > pos and isinstance(node.args[pos], ast.Constant) \
                        and isinstance(node.args[pos].value, str):
                    keys.add(node.args[pos].value)
    return keys


class _Marked(HTMLParser):
    """Texts of elements marked data-i18n, and data-i18n-html / -ph / -title keys."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.keys, self.html_keys, self._open = set(), set(), []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "data-i18n-html" in a:
            self.html_keys.add(a["data-i18n-html"])
        for k in ("data-i18n-ph", "data-i18n-title"):
            if a.get(k):
                self.keys.add(a[k])
        if "data-i18n" in a:
            self._open.append([tag, ""])

    def handle_endtag(self, tag):
        if self._open and self._open[-1][0] == tag:
            self.keys.add(re.sub(r"\s+", " ", self._open.pop()[1]).strip())

    def handle_data(self, data):
        for item in self._open:
            item[1] += data


def _page_keys(text: str) -> tuple[set[str], set[str]]:
    parser = _Marked()
    parser.feed(text)
    keys = set(parser.keys)
    for m in [*JS_CALL.finditer(text), *JS_TASK.finditer(text)]:
        keys.add(ast.literal_eval(m.group(1)))
    return keys, parser.html_keys


def all_keys() -> tuple[set[str], set[str]]:
    from airfare import brand, dashboard, historypage
    keys = _python_keys()
    html_keys: set[str] = set()
    pages = [f.read_text(encoding="utf-8") for f in sorted((ROOT / "airfare" / "static").glob("*.html"))]
    for text in (*pages, historypage.PAGE):
        k, h = _page_keys(text)
        keys |= k
        html_keys |= h
    keys |= set(brand.NAV_TEXTS.values()) | {label for _, label, _ in brand.PAGES}
    keys |= set(dashboard.KIND_LABELS.values()) | set(dashboard.TAGS.values())
    keys |= {"Check finished.", "Nothing to check: add a route with future dates.", "Another check is already running.",
             "The check failed; see the log.", "Nothing was checked: the limits hold Skyscanner and Aviasales for now.", "check", "test", "browser", "lookup", "Account default",
             "Add a DeepSeek API key in Settings to use DeepSeek."}
    # Messages the server sends that pages translate when they show them.
    for name in ("check_answer", "verify_source"):
        src = ast.get_source_segment((ROOT / "airfare" / "research.py").read_text(encoding="utf-8"),
                                     next(n for n in ast.parse((ROOT / "airfare" / "research.py").read_text(encoding="utf-8")).body
                                          if isinstance(n, ast.FunctionDef) and n.name == name))
        keys |= {s for s in re.findall(r'return "([^"]+)"', src)}
    for m in re.finditer(r'problem = "([^"]+)"', (ROOT / "airfare" / "webui.py").read_text(encoding="utf-8")):
        keys.add(m.group(1))
        keys.add(m.group(1)[0].upper() + m.group(1)[1:])       # as a route card shows it
    keys |= {f"{label}: the price drop (%)" for label in ("Cheapest", "Fastest", "Best value")}
    keys |= {f"{label}: the price limit" for label in ("Cheapest", "Fastest", "Best value")}
    keys |= {"The longest trip for alerts (hours)"}
    # Notes sources and the server attach to results and replies, which the pages translate when shown.
    keys |= {"No SerpApi key yet", "No DeepSeek key yet", "AirFare was updated. Close this tab and open AirFare Settings again.",
             "Aviasales needs 3-letter airport or city codes and dates within the coming year",
             "page loaded but no flight results were found", "no prices found on the page",
             "the AirFare extension didn't respond (is it installed and enabled on your browser's extensions page?)",
             "the AirFare add-on didn't respond (Firefox removes an add-on loaded in about:debugging when it restarts: "
             "load it again, or install the signed .xpi)",
             "the AirFare extension started but didn't finish in time",
             "this link isn't a search results page on a site the extension covers", "No OpenAI key yet",
             "Install the Codex app and sign in to ChatGPT in Settings to use your ChatGPT account.",
             "Add an OpenAI API key in Settings to use ChatGPT through the API.",
             "Add an Anthropic API key in Settings, or switch Claude to your Claude account.", "No Anthropic key yet",
             "Anthropic doesn't accept the saved API key: {e}",
             # chatgpt.ChatGPTError messages the server shows in the user's language
             "The Codex app isn't installed: install it with OpenAI's installer, then sign in to ChatGPT",
             "The Codex app isn't installed yet", "ChatGPT isn't signed in: press Log in to ChatGPT in AirFare Settings",
             "Install the Codex app with OpenAI's own installer, not npm, as AirFare Settings explains"}
    keys.discard("")
    return {k for k in keys if re.search(r"[A-Za-z]", k)}, html_keys


def missing() -> list[str]:
    from airfare.translations import T
    keys, html_keys = all_keys()
    out = []
    for k in sorted(keys | html_keys):
        entry = T.get(k) or {}
        for lang in ("es", "ru"):
            if not entry.get(lang):
                out.append(f"{lang}: {k}")
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    gone = missing()
    print("\n".join(gone) or "every text has its Spanish and Russian version")
