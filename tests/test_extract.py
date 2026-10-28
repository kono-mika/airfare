import copy
import json
from pathlib import Path

from airfare import extract

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "unified_search_partial.json").read_text(encoding="utf-8"))


def test_parses_real_partial_feed():
    page = extract.parse_payloads([FIXTURE])
    assert page is not None and not page.complete
    assert [f.price for f in page.flights] == [154.97, 173.04, 192.97]
    cheapest = page.flights[0]
    assert len(cheapest.legs) == 2
    assert cheapest.legs[0].origin == "VNO" and cheapest.legs[0].depart.startswith("2026-12-18")
    assert cheapest.legs[1].destination == "VNO" and cheapest.legs[1].depart.startswith("2026-12-27")
    assert page.picks["cheapest"] == [f.id for f in page.flights]          # all three, cheapest first
    assert len(page.picks["best"]) == 3 and len(page.picks["fastest"]) == 3
    assert page.currency == "£"


def test_top_picks_keep_three_per_category():
    flights = extract.parse_payloads([FIXTURE]).flights * 2   # 6 entries, ids repeat
    picks = extract.top_picks(flights)
    assert all(len(v) == 3 for v in picks.values())


def test_later_payload_wins_and_buckets_set_picks():
    later = copy.deepcopy(FIXTURE)
    it = later["itineraries"]
    it["context"]["status"] = "complete"
    it["results"][0]["price"]["raw"] = 99.0
    it["buckets"] = [{"id": "Best", "items": [it["results"][1], it["results"][0]]}]
    page = extract.parse_payloads([FIXTURE, later])
    assert page.complete
    assert page.flights[0].price == 99.0
    assert page.picks["best"] == [it["results"][1]["id"], it["results"][0]["id"]]   # Skyscanner's own order


def test_no_feed_returns_none():
    assert extract.parse_payloads([]) is None
    assert extract.parse_payloads([{"something": {}}]) is None


def test_flight_helpers():
    f = extract.parse_payloads([FIXTURE]).flights[0]
    assert f.minutes == sum(leg.minutes for leg in f.legs)
    assert f.max_stops == 0
    assert "Ryanair" in f.airlines
