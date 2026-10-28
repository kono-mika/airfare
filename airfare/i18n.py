"""AirFare's interface in English, Spanish and Russian.

Texts are written in English in the code and looked up here by that English text. Python pages call
tr()/trn(); the browser pages get the same dictionary (bundle()) and do the same in JavaScript, so the
language can change at any moment without losing anything typed. A text missing here shows in English.
"""
from __future__ import annotations

import re
from datetime import date, datetime

from . import platform

LANGS = {"en": "English", "es": "Español", "ru": "Русский"}
LANGUAGE_NAMES = {"en": "English", "es": "Spanish", "ru": "Russian"}     # for the analyst's instructions

_DAYS = {"en": ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
         "es": ("lun", "mar", "mié", "jue", "vie", "sáb", "dom"),
         "ru": ("пн", "вт", "ср", "чт", "пт", "сб", "вс")}
_MONTHS = {"en": ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
           "es": ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sept", "oct", "nov", "dic"),
           "ru": ("янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек")}


def norm(lang: str | None) -> str:
    return lang if lang in LANGS else "en"


def system_language() -> str:
    """The system's display language, if AirFare speaks it (used until a language is picked)."""
    return norm(platform.ui_language())


def _fill(text: str, kw: dict) -> str:
    return re.sub(r"\{(\w+)\}", lambda m: str(kw[m.group(1)]) if m.group(1) in kw else m.group(0), text)


def tr(text: str, lang: str | None, **kw) -> str:
    """text in lang, with {name} placeholders filled from kw."""
    lang = norm(lang)
    if lang != "en":
        text = (T.get(text) or {}).get(lang) or text
    return _fill(text, kw)


class Problem(ValueError):
    """A mistake in what the user entered, shown in their language:
    Problem("Route {i}: {problem}", i=2, problem="pick a departure date"). Text parameters are translated too."""

    def __init__(self, template: str, **params):
        self.template, self.params = template, params
        super().__init__(_fill(template, params))

    def text(self, lang: str | None) -> str:
        return tr(self.template, lang, **{k: tr(v, lang) if isinstance(v, str) else v for k, v in self.params.items()})


def plural_form(n: float, lang: str) -> int:
    """Which form of "one|few|many" to use: English and Spanish have two, Russian three."""
    n = abs(int(n)) if float(n).is_integer() else n
    if lang == "ru":
        if not isinstance(n, int):
            return 1
        if n % 10 == 1 and n % 100 != 11:
            return 0
        return 1 if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else 2
    return 0 if n == 1 else 1


def trn(n: float, forms: str, lang: str | None, **kw) -> str:
    """A count with its noun: trn(3, "{n} stop|{n} stops", "ru") -> "3 пересадки"."""
    lang = norm(lang)
    text = forms if lang == "en" else (T.get(forms) or {}).get(lang) or forms
    options = text.split("|")
    form = options[min(plural_form(n, lang), len(options) - 1)]
    return _fill(form, {"n": n if not float(n).is_integer() else int(n), **kw})


def day(d: date | datetime | None, lang: str | None, year: bool = False) -> str:
    """'Fri 12 Mar' / 'vie 12 mar' / 'пт 12 мар', with the year when asked."""
    if not d:
        return "?"
    lang = norm(lang)
    text = f"{_DAYS[lang][d.weekday()]} {d.day} {_MONTHS[lang][d.month - 1]}"
    return f"{text} {d.year}" if year else text


def short_day(d: date | datetime | None, lang: str | None) -> str:
    """'12 Mar'."""
    if not d:
        return "?"
    return f"{d.day} {_MONTHS[norm(lang)][d.month - 1]}"


def bundle() -> dict:
    """The dictionary for the browser pages: {"es": {english: spanish}, "ru": {...}}."""
    return {lang: {k: v[lang] for k, v in T.items() if v.get(lang)} for lang in ("es", "ru")}


from .translations import T  # noqa: E402  (English text -> {"es": ..., "ru": ...})
