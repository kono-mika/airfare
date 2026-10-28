import re
import sys
from datetime import date
from pathlib import Path

from airfare import i18n
from airfare.translations import T

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import i18n_keys  # noqa: E402


def test_every_interface_text_has_spanish_and_russian():
    assert i18n_keys.missing() == []


def test_translations_keep_their_placeholders_and_plural_forms():
    for english, versions in T.items():
        if english.startswith("html:"):
            continue
        wanted = set(re.findall(r"\{\w+\}", english))
        for lang, text in versions.items():
            assert set(re.findall(r"\{\w+\}", text)) == wanted, (lang, english)
            if "|" in english:
                assert text.count("|") == (2 if lang == "ru" else 1), (lang, english)


def test_plurals_and_dates():
    forms = "{n} stop|{n} stops"
    assert [i18n.trn(n, forms, "ru") for n in (1, 3, 5, 11, 21, 22)] == [
        "1 пересадка", "3 пересадки", "5 пересадок", "11 пересадок", "21 пересадка", "22 пересадки"]
    assert i18n.trn(2, forms, "es") == "2 escalas" and i18n.trn(1, forms, "en") == "1 stop"
    d = date(2026, 12, 18)
    assert (i18n.day(d, "en"), i18n.day(d, "es"), i18n.day(d, "ru")) == ("Fri 18 Dec", "vie 18 dic", "пт 18 дек")
    assert i18n.tr("Unknown text {x}", "ru", x=1) == "Unknown text 1"          # falls back to English


def test_server_errors_come_in_the_users_language():
    e = i18n.Problem("Route {i}: {problem}", i=2, problem="pick a departure date")
    assert str(e) == "Route 2: pick a departure date"
    assert e.text("es") == "Ruta 2: elige una fecha de salida"
