import pytest

from airfare import serpapi


def seg(dep, dep_t, arr, arr_t, airline, number, minutes):
    return {"departure_airport": {"name": dep, "id": dep, "time": dep_t},
            "arrival_airport": {"name": arr, "id": arr, "time": arr_t},
            "duration": minutes, "airline": airline, "flight_number": number}


BODY = {
    "search_metadata": {"google_flights_url": "https://www.google.com/travel/flights?x"},
    "best_flights": [
        {"flights": [seg("LHR", "2027-03-12 08:05", "BCN", "2027-03-12 10:40", "Transavia", "HV 6122", 155)],
         "total_duration": 155, "price": 142},
    ],
    "other_flights": [
        {"flights": [seg("LHR", "2027-03-12 06:00", "MAD", "2027-03-12 07:05", "Iberia", "IB 8901", 65),
                     seg("MAD", "2027-03-12 09:00", "AMS", "2027-03-12 11:35", "KLM", "KL 1702", 155)],
         "layovers": [{"duration": 115, "name": "Madrid", "id": "MAD", "overnight": False}],
         "total_duration": 335, "price": 118},
        {"flights": [seg("LHR", "2027-03-12 12:00", "BCN", "2027-03-12 14:30", "Transavia", "HV 6124", 150)]},
    ],
    "price_insights": {"lowest_price": 118, "price_level": "low", "typical_price_range": [130, 210]},
}


def test_parse_round_trip_results():
    page = serpapi.parse(BODY, "EUR", round_trip=True)
    assert [f.price for f in page.flights] == [118, 142]          # the item without a price is skipped
    cheap = page.flights[0]
    assert cheap.price_text == "€118"
    assert cheap.legs[0].origin == "LHR" and cheap.legs[0].destination == "AMS"
    assert cheap.legs[0].stops == 1 and cheap.legs[0].minutes == 335
    assert cheap.airlines == "Iberia + KLM"
    assert cheap.legs[0].depart == "2027-03-12T06:00:00"
    assert page.picks["best"] == [page.flights[1].id, cheap.id]       # Google's own order
    assert page.picks["cheapest"] == [cheap.id, page.flights[1].id]
    assert "round-trip totals" in page.note and "price level low" in page.note and "€130–€210" in page.note


def test_codeshare_duplicates_are_dropped():
    dup = {"flights": [seg("LHR", "2027-03-12 08:05", "BCN", "2027-03-12 10:40", "Transavia", "KL 9999", 155)],
           "total_duration": 155, "price": 142}
    body = {**BODY, "other_flights": BODY["other_flights"] + [dup]}
    assert len(serpapi.parse(body, "EUR", True).flights) == 2


def test_params_map_codes_and_classes():
    p = serpapi.params({"origin": "lhr", "destination": "lond", "depart": "2027-03-12", "return": "2027-03-15",
                        "adults": 2, "cabin": "business"}, "KEY", "eur")
    assert p["departure_id"] == "LHR" and p["arrival_id"].startswith("LHR,")
    assert p["type"] == 1 and p["return_date"] == "2027-03-15"
    assert p["travel_class"] == 3 and p["currency"] == "EUR" and p["adults"] == 2
    one_way = serpapi.params({"origin": "lhr", "destination": "bcn", "depart": "2027-03-12"}, "KEY", "EUR")
    assert one_way["type"] == 2 and "return_date" not in one_way


def test_unknown_city_code_is_explained():
    with pytest.raises(serpapi.SerpApiError, match="3-letter"):
        serpapi.airports("xyza")


def test_search_reports_api_errors(monkeypatch):
    def boom(url, timeout=90):
        raise serpapi.SerpApiError("Invalid API key.")
    monkeypatch.setattr(serpapi, "_get", boom)
    res = serpapi.search({"origin": "lhr", "destination": "bcn", "depart": "2027-03-12", "url": "u", "key": "k"},
                         "bad", "EUR")
    assert res.status == "error" and "Invalid API key" in res.note and res.source == "Google Flights"


def test_search_success_uses_google_link(monkeypatch):
    monkeypatch.setattr(serpapi, "_get", lambda url, timeout=90: BODY)
    res = serpapi.search({"origin": "lhr", "destination": "bcn", "depart": "2027-03-12", "return": "2027-03-15",
                          "url": "u", "key": "k"}, "KEY", "EUR")
    assert res.status == "ok" and res.page["url"].startswith("https://www.google.com/travel/flights")
    assert res.parsed.flights[0].price == 118
