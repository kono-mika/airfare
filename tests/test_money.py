import json
from datetime import datetime, timedelta

from airfare import extract, money

TABLE = {"rates": {"EUR": 1.0, "GBP": 0.84, "USD": 1.12, "RUB": 91.2, "CAD": 1.5}}


def test_detects_currencies_as_sites_print_them():
    assert money.detect("178 €") == "EUR" and money.detect("£155") == "GBP" and money.detect("8 148 ₽") == "RUB"
    assert money.detect("US$230") == "USD" and money.detect("$230") == "USD"
    assert money.detect("$230", "www.skyscanner.ca") == "CAD"                  # the site decides what "$" means
    assert money.detect("1 200 kr", "www.skyscanner.no") == "NOK"
    assert money.detect("230 PLN") == "PLN" and money.detect("230") is None


def test_formats_and_converts():
    assert money.fmt(214, "EUR") == "€214" and money.fmt(1234.6, "GBP") == "£1,235"
    assert money.fmt(8148, "RUB") == "8 148 ₽"
    assert round(money.convert(91.2, "RUB", "EUR", TABLE), 2) == 1.0
    assert round(money.convert(100, "GBP", "USD", TABLE), 2) == 133.33
    assert money.convert(100, "XXX", "EUR", TABLE) is None
    assert money.floor_price(161.5) == 161.0


def test_rates_are_cached_and_used_offline(monkeypatch, tmp_path):
    monkeypatch.setattr(money, "RATES_FILE", tmp_path / "rates.json")
    calls = []

    def fake_fetch():
        calls.append(1)
        return {"fetched": datetime.now().isoformat(timespec="minutes"), "date": "2026-10-26", "source": "test",
                "rates": {"EUR": 1.0, "RUB": 91.2}}
    monkeypatch.setattr(money, "fetch_rates", fake_fetch)
    assert money.rates()["rates"]["RUB"] == 91.2 and money.rates()["rates"]["RUB"] == 91.2
    assert len(calls) == 1                                   # the second call used the saved rates

    stale = json.loads((tmp_path / "rates.json").read_text())
    stale["fetched"] = (datetime.now() - timedelta(days=2)).isoformat(timespec="minutes")
    (tmp_path / "rates.json").write_text(json.dumps(stale))

    def offline():
        raise OSError("no network")
    monkeypatch.setattr(money, "fetch_rates", offline)
    assert money.rates()["rates"]["RUB"] == 91.2             # yesterday's rates beat none


def test_bad_rate_values_are_dropped():
    assert money._sane({"EUR": "1", "RUB": "-3", "GBP": "abc", "lower": 2, "USD": 1.1}) == {"EUR": 1.0, "USD": 1.1}


def test_a_page_is_converted_and_keeps_the_site_price():
    f = extract.Flight("a", 8148.0, "8 148 ₽", [])
    page = extract.ParsedPage([f], {}, True, "₽", 1, currency_code="RUB")
    extract.convert_page(page, "EUR", TABLE)
    assert f.price == 89.34 and f.price_text == "€89" and f.orig_text == "8 148 ₽"
    assert page.currency_code == "EUR" and page.comparable and "Prices converted from RUB to EUR" in page.note


def test_a_page_without_a_rate_is_left_alone_and_not_compared():
    f = extract.Flight("a", 100.0, "100 CHF", [])
    page = extract.ParsedPage([f], {}, True, "CHF", 1)
    extract.convert_page(page, "EUR", TABLE)
    assert not page.comparable and f.price == 100.0 and "no exchange rate" in page.note
