import json
from datetime import date
from pathlib import Path

from airfare import extract, report, runner, urls
from airfare.results import PageResult

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "aviasales_results.json").read_text(encoding="utf-8"))
TODAY = date(2026, 10, 26)


def test_search_links_follow_aviasales_format():
    page = {"origin": "bcn", "destination": "lond", "depart": "2027-03-15", "return": "2027-03-18", "adults": 1}
    assert urls.aviasales_url(page, TODAY) == "https://www.aviasales.ru/search/BCN1503LON18031"
    one_way = {**page, "return": None, "adults": 2, "cabin": "business"}
    assert urls.aviasales_url(one_way, TODAY) == "https://www.aviasales.ru/search/BCN1503LONc2"
    assert urls.aviasales_url({**page, "cabin": "premiumeconomy"}, TODAY).endswith("BCN1503LON1803w1")
    assert urls.aviasales_url({**page, "origin": "lhr", "destination": "mosc"}, TODAY).endswith("LHR1503MOW18031")


def test_no_link_when_aviasales_cant_tell_the_dates_or_airports():
    page = {"origin": "bcn", "destination": "lond", "depart": "2027-03-15", "return": None}
    assert urls.aviasales_url({**page, "depart": "2027-12-01"}, TODAY) is None      # its links carry no year
    assert urls.aviasales_url({**page, "origin": "bcnx"}, TODAY) is None
    assert urls.aviasales_url({**page, "depart": None}, TODAY) is None


def test_parses_the_results_feed():
    parsed = extract.parse_aviasales(FIXTURE)
    assert parsed.complete and parsed.currency_code == "RUB" and parsed.total_results == 1027
    assert len(parsed.flights) == 5                         # the cheapest ticket repeats one of the five
    cheapest = parsed.flights[0]
    assert cheapest.price == 87527.0 and cheapest.airlines == "Cathay Pacific"
    out, back = cheapest.legs
    assert (out.origin, out.destination, out.depart, out.stops, out.minutes) == ("MAD", "NRT", "2027-03-15T22:30:00", 1, 1440)
    assert back.origin == "NRT" and back.destination == "MAD"
    assert parsed.picks["best"][0] == "12f94caefb03374d1cde4c4d9981a813"     # Aviasales' own order
    assert "overnight layover" in parsed.flights[1].tags
    assert extract.parse_aviasales([{"itineraries": {}}]) is None            # not an Aviasales payload


def test_aviasales_pages_join_the_extension_job_and_convert(monkeypatch):
    sent = {}

    def fake_collect(pages, wait, on_robot, lang="en", browser="chrome", on_taken=None):
        sent["pages"], sent["lang"] = pages, lang
        return [PageResult(page=p, status="ok", payloads=FIXTURE if p["site"] == "Aviasales" else [],
                           source=p["site"]) for p in pages]
    monkeypatch.setattr(runner.extension, "collect", fake_collect)
    page = {"key": "k", "route_id": "r", "route_name": "R", "origin": "mad", "destination": "tyoa",
            "depart": "2027-03-15", "return": "2027-03-18", "adults": 1,
            "url": "https://www.skyscanner.net/transport/flights/mad/tyoa/270315/270318/"}
    import asyncio
    cfg = {"wait_seconds": 20, "concurrency": 2, "language": "ru"}
    results, held = asyncio.run(runner.collect_prices(cfg, [page, {**page, "key": "k2", "depart": "2028-01-01"}],
                                                      ["extension", "aviasales"]))
    sites = [p["site"] for p in sent["pages"]]        # each trip's pages together, so a limit leaves out whole trips
    assert sites == ["Skyscanner", "Aviasales", "Skyscanner"] and sent["lang"] == "ru" and held is None
    assert sent["pages"][1]["url"] == "https://www.aviasales.ru/search/MAD1503TYO18031"
    skipped = [r for r in results if r.status == "error"]
    assert len(skipped) == 1 and "within the coming year" in skipped[0].note
    data = report.collect(results, "EUR", {"rates": {"EUR": 1.0, "RUB": 100.0}})
    avia = next(d for d in data if d.result.source == "Aviasales" and d.result.status == "ok")
    assert avia.parsed.flights[0].price_text == "€875" and avia.parsed.flights[0].orig_text.endswith("₽")
