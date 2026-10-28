import json
from datetime import datetime
from pathlib import Path

from airfare import config, dashboard, report, serpapi
from airfare.results import PageResult
from test_serpapi import BODY

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "unified_search_partial.json").read_text(encoding="utf-8"))
PAGE = {"key": "2026-12-18|2026-12-27", "route_id": "r", "route_name": "Vilnius ⇄ London", "origin": "vno",
        "destination": "lond", "depart": "2026-12-18", "return": "2026-12-27", "url": "https://example.test/s"}
RATES = {"rates": {"EUR": 1.0, "GBP": 0.8, "USD": 1.1, "RUB": 100.0}, "date": "2026-10-26", "source": "test"}
WHEN = datetime(2026, 10, 26, 16, 0)
RULES = report.alert_rules(config.DEFAULT_CONFIG)


def pages(currency=None):
    sky = PageResult(page=PAGE, status="ok", payloads=[FIXTURE], source="Skyscanner")
    google = PageResult(page={**PAGE, "url": "https://example.test/g"}, status="ok", source="Google Flights")
    google.parsed = serpapi.parse(BODY, "GBP", True)
    return report.collect([sky, google], currency, RATES)


def history_for(data, currency="GBP"):
    history = report.update_history({}, report.route_bests(data, RULES), WHEN,
                                    {"prices_by_route": report.price_summary(data), "currency": currency},
                                    currency=currency, rates=RATES)
    history["runs"].insert(0, {"time": "2026-10-25T09:00", "currency": currency,
                               "prices_by_route": {"r": {"Skyscanner": {"cheapest": 180.0}}}})
    return history


def test_dashboard_shows_categories_trend_and_alert():
    data = pages("GBP")
    history = history_for(data)
    targets = report.alert_targets(history, ["r"], RULES, "GBP", RATES)
    summary = {"take": "Book the direct one.", "routes": {"r": {"best_value": 173.04,
                                                                 "best_value_text": "£173, Fri 18 Dec 06:15, Ryanair, direct"}}}
    page = dashboard.build(data, history, targets, RULES, WHEN, "LOW PRICE\n\n## Analysis\nok", True, summary,
                           {"r": ["cheapest"]}, "x-prices.md", currency="GBP", rates=RATES)
    assert page.startswith("<!doctype html>") and '<html lang="en">' in page
    assert "Low price" in page and "Book the direct one." in page
    # best, cheapest and fastest for each source: Skyscanner 3 flights × 3 lists, Google 2 flights × 3 lists
    assert page.count('class="flight"') == 3 * 3 + 2 * 3
    assert "Best (as ranked by Skyscanner)" in page and "Best (as ranked by Google Flights)" in page
    assert "<svg" in page and "polyline" in page          # two runs → a trend line
    assert "alert at £112" in page                        # 5% below the £118 reference, in whole pounds
    assert ">Fastest<" in page and 'class="kpi hit"' in page
    assert "return picked on Google Flights" in page
    assert "LOW PRICE" not in page.split("<details>")[1]  # the banner replaces the analyst's first line


def test_dashboard_in_russian_and_spanish():
    data = pages("GBP")
    ru = dashboard.build(data, {"runs": []}, {}, RULES, WHEN, "", False, {}, {}, "x.md", lang="ru", currency="GBP")
    assert '<html lang="ru">' in ru and "Самый дешёвый" in ru and "пт 18 дек" in ru and "Динамика цен" in ru
    assert 'href="latest-es.html" data-lang="es"' in ru            # its language links work opened from disk
    es = dashboard.build(data, {"runs": []}, {}, RULES, WHEN, "", False, {}, {}, "x.md", lang="es", currency="GBP")
    assert "Más barato" in es and "vie 18 dic" in es


def test_prices_are_converted_to_the_chosen_currency():
    data = pages("EUR")
    cheapest = min((f for pd in data for f in pd.parsed.flights), key=lambda f: f.price)
    assert cheapest.price_text == "€148" and cheapest.orig_text == "£118"
    page = dashboard.build(data, {"runs": []}, {}, RULES, WHEN, "", False, {}, {}, "x.md", currency="EUR", rates=RATES)
    assert "€148" in page and "on the site: £118" in page and "prices in EUR" in page


CREDIT = '<a href="https://www.exchangerate-api.com">Rates By Exchange Rate API</a>'


def test_dashboard_footer_credits_exchangerate_api_only_for_its_rates():
    data = pages("EUR")
    both = {**RATES, "source": "European Central Bank and open.er-api.com"}
    for lang in ("en", "es", "ru"):           # the provider's own wording, in English in every language
        page = dashboard.build(data, {"runs": []}, {}, RULES, WHEN, "", False, {}, {}, "x.md", lang=lang,
                               currency="EUR", rates=both)
        footer = page.split("<footer", 1)[1]
        assert CREDIT in footer and "European Central Bank and open.er-api.com" in footer
    ecb = dashboard.build(data, {"runs": []}, {}, RULES, WHEN, "", False, {}, {}, "x.md", currency="EUR",
                          rates={**RATES, "source": "European Central Bank"})
    assert "European Central Bank" in ecb.split("<footer", 1)[1] and "exchangerate-api" not in ecb


def test_dashboard_without_analyst_or_history():
    data = pages()
    page = dashboard.build(data, {"runs": []}, {}, RULES, WHEN, "", False, {}, {}, "x-prices.md")
    assert "couldn't analyse" in page and "trend appears after the next check" in page


def test_dashboard_shows_route_codes_and_brand():
    data = pages()
    page = dashboard.build(data, {"runs": []}, {}, RULES, WHEN, "", False, {}, {}, "x-prices.md")
    assert '<span class="iata">VNO</span>' in page and '<span class="iata">LOND</span>' in page
    assert 'class="logo"' in page and "Bahnschrift" in page
