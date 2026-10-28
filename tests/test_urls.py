from datetime import date

from airfare import urls

TODAY = date(2026, 10, 26)


def route(**kw):
    base = {"id": "r1", "origin": "VNO", "destination": "lond", "trip": "return",
            "depart_from": "2026-12-18", "depart_to": "2026-12-19",
            "return_from": "2026-12-27", "return_to": "2026-12-28",
            "adults": 2, "cabin": "business", "direct_only": True}
    base.update(kw)
    return base


def test_build_url_return():
    url = urls.build_url("www.skyscanner.net", "VNO", "LOND", date(2026, 12, 18), date(2026, 12, 27),
                         adults=2, cabin="business", direct_only=True)
    assert url.startswith("https://www.skyscanner.net/transport/flights/vno/lond/261218/261227/?")
    assert "adultsv2=2" in url and "cabinclass=business" in url
    assert "preferdirects=true" in url and "rtn=1" in url


def test_build_url_one_way():
    url = urls.build_url("www.skyscanner.lt", "vno", "bcn", date(2026, 12, 5))
    assert "/transport/flights/vno/bcn/261205/?" in url and "rtn=0" in url


def test_parse_url_roundtrip():
    url = urls.build_url("www.skyscanner.net", "vno", "lond", date(2026, 12, 18), date(2026, 12, 27))
    assert urls.parse_url(url) == {"origin": "vno", "destination": "lond", "depart": "2026-12-18",
                                   "return": "2026-12-27", "adults": 1, "cabin": "economy"}
    assert urls.parse_url("https://www.skyscanner.net/transport/flights/vno/bcn/261205?rtn=0")["return"] is None
    assert urls.parse_url("https://www.skyscanner.net/") is None


def test_parse_localized_url():
    url = ("https://www.skyscanner.es/transporte/vuelos/mad/ber/270312/270315/"
           "?adultsv2=2&cabinclass=business&rtn=1")
    assert urls.parse_url(url) == {"origin": "mad", "destination": "ber", "depart": "2027-03-12",
                                   "return": "2027-03-15", "adults": 2, "cabin": "business"}


def test_a_pasted_link_keeps_its_travellers_and_cabin_for_the_other_sources():
    route = {"id": "r", "enabled": True, "manual_pages": [
        {"key": None, "url": "https://www.skyscanner.net/transport/flights/lhr/bcn/270312/?adultsv2=2&cabinclass=business"}]}
    pages, _ = urls.plan_pages({"domain": "www.skyscanner.net", "max_pages": 5, "routes": [route]}, date(2026, 10, 26))
    assert pages[0]["adults"] == 2 and pages[0]["cabin"] == "business"
    assert urls.aviasales_url(pages[0], date(2026, 10, 26)) == "https://www.aviasales.ru/search/LHR1203BCNc2"


def test_date_span():
    assert urls.date_span("2026-12-18", None) == [date(2026, 12, 18)]
    assert len(urls.date_span("2026-12-20", "2026-12-18")) == 3
    assert urls.date_span("", "") == []


def test_route_pages_combinations():
    pages = urls.route_pages(route(), "www.skyscanner.net", TODAY)
    assert [(p["depart"], p["return"]) for p in pages] == [
        ("2026-12-18", "2026-12-27"), ("2026-12-18", "2026-12-28"),
        ("2026-12-19", "2026-12-27"), ("2026-12-19", "2026-12-28"),
    ]
    assert all(p["source"] == "auto" for p in pages)


def test_route_pages_skips_return_before_departure_and_past_dates():
    r = route(depart_from="2026-10-20", depart_to="2026-10-28", return_from="2026-10-27", return_to="2026-10-27")
    pages = urls.route_pages(r, "www.skyscanner.net", TODAY)
    assert [(p["depart"], p["return"]) for p in pages] == [("2026-10-26", "2026-10-27"), ("2026-10-27", "2026-10-27")]


def test_manual_page_replaces_generated_one():
    manual = "https://www.skyscanner.net/transport/flights/vno/stn/261218/261227/?rtn=1"
    r = route(manual_pages=[{"key": "2026-12-18|2026-12-27", "url": manual}])
    pages = urls.route_pages(r, "www.skyscanner.net", TODAY)
    p = next(p for p in pages if p["key"] == "2026-12-18|2026-12-27")
    assert p["url"] == manual and p["source"] == "manual"
    assert len(pages) == 4


def test_link_only_route():
    r = {"id": "r2", "manual_pages": [{"url": "https://www.skyscanner.net/transport/flights/vno/bcn/261205/"}]}
    pages = urls.route_pages(r, "www.skyscanner.net", TODAY)
    assert len(pages) == 1 and pages[0]["depart"] == "2026-12-05"


def test_plan_pages_caps_fairly():
    cfg = {"domain": "www.skyscanner.net", "max_pages": 3, "routes": [
        route(id="a"),
        route(id="b", trip="oneway", depart_from="2026-11-01", depart_to="2026-11-10"),
        route(id="c", enabled=False),
    ]}
    pages, left_out = urls.plan_pages(cfg, TODAY)
    assert [p["route_id"] for p in pages] == ["a", "b", "a"]
    assert left_out == 4 + 10 - 3
