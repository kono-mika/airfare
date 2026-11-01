"""The three filters per route. All data here is invented: the ZZ airport codes aren't airports, and the prices,
dates and flights are made up. (The real airports in the city-code tests only come from AirFare's own city list.)"""
import asyncio
import copy
import html
import json
import shutil
from datetime import date, datetime
from pathlib import Path

import pytest

from airfare import config, dashboard, extract, filters, historypage, migrate, pricelog, report, runner, serpapi, upgrade, urls, webui
from airfare.extract import Flight, Leg, ParsedPage
from airfare.results import PageResult

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_141 = Path(__file__).parent / "fixtures" / "data-1.4.1"
RATES = {"rates": {"EUR": 1.0, "RUB": 100.0, "GBP": 0.8}, "date": "2026-10-26", "source": "invented"}
WHEN = datetime(2026, 10, 26, 16, 0)
RULES = report.alert_rules(config.DEFAULT_CONFIG)
PAGE = {"key": "2027-03-12|", "route_id": "r", "route_name": "Invented route", "origin": "zza", "destination": "zzb",
        "depart": "2027-03-12", "return": None, "url": "https://example.test/invented"}


# ----- the three sources' feeds, invented, each with the same four trips ----------------------------------------
# a: direct, €100. b: 1 stop at ZZH, €200. c: 2 stops at ZZH and ZZJ, €300. d: 1 stop at ZZK, €400.

TRIPS = [("a", 100.0, []), ("b", 200.0, ["ZZH"]), ("c", 300.0, ["ZZH", "ZZJ"]), ("d", 400.0, ["ZZK"])]


def sky_feed(trips=TRIPS) -> dict:
    def place(code):
        return {"displayCode": code, "flightPlaceId": code}

    def leg(via):
        stops = ["ZZA", *via, "ZZB"]
        return {"origin": {"displayCode": "ZZA"}, "destination": {"displayCode": "ZZB"}, "durationInMinutes": 120 + 60 * len(via),
                "stopCount": len(via), "departure": "2027-03-12T08:00:00", "arrival": "2027-03-12T12:00:00",
                "carriers": {"marketing": [{"name": "Invented Air"}]},
                "segments": [{"origin": place(x), "destination": place(y)} for x, y in zip(stops, stops[1:])]}
    return {"itineraries": {"context": {"status": "complete", "totalResults": len(trips)},
                            "results": [{"id": fid, "price": {"raw": price, "formatted": f"€{price:.0f}"}, "legs": [leg(via)],
                                         "score": 1 - i / 10} for i, (fid, price, via) in enumerate(trips)]}}


def avia_feed(trips=TRIPS) -> list:
    legs, tickets = [], []
    for pos, (fid, price, via) in enumerate(trips, 1):
        stops = ["ZZA", *via, "ZZB"]
        first = len(legs)
        for k, (x, y) in enumerate(zip(stops, stops[1:])):
            legs.append({"origin": x, "destination": y, "local_departure_date_time": f"2027-03-12 0{8 + k}:00",
                         "local_arrival_date_time": f"2027-03-12 0{8 + k}:50", "departure_unix_timestamp": 1000 + k * 3600,
                         "arrival_unix_timestamp": 4000 + k * 3600, "operating_carrier_designator": {"carrier": "ZZ"}})
        tickets.append({"id": fid, "position": pos, "score": 0.5,
                        "segments": [{"flights": list(range(first, len(legs))), "transfers": []}],
                        "proposals": [{"price": {"value": price * 100, "currency_code": "RUB"}, "flight_terms": {}}]})
    return [{"chunk_id": "invented", "last_update_timestamp": 0, "tickets": tickets, "flight_legs": legs, "airlines": {},
             "meta": {"total_tickets_count": len(trips)}}]


def serp_body(trips=TRIPS) -> dict:
    def seg(x, y, k):
        return {"departure_airport": {"id": x, "time": f"2027-03-12 0{8 + k}:00"},
                "arrival_airport": {"id": y, "time": f"2027-03-12 0{8 + k}:50"},
                "duration": 50, "airline": "Invented Air", "flight_number": f"ZZ {100 + k}"}
    items = []
    for fid, price, via in trips:
        stops = ["ZZA", *via, "ZZB"]
        items.append({"flights": [seg(x, y, k) for k, (x, y) in enumerate(zip(stops, stops[1:]))],
                      "layovers": [{"id": code, "name": "Invented", "duration": 60} for code in via],
                      "total_duration": 100 + 60 * len(via), "price": price})
    return {"best_flights": items[:1], "other_flights": items[1:]}


def sky_page():
    return PageResult(page=dict(PAGE), status="ok", payloads=[sky_feed()], source="Skyscanner")


def avia_page():
    return PageResult(page=dict(PAGE), status="ok", payloads=[avia_feed()], source="Aviasales")


def serp_page():
    res = PageResult(page=dict(PAGE), status="ok", source="Google Flights")
    res.parsed = serpapi.parse(serp_body(), "EUR", False)
    return res


SOURCES = {"Skyscanner": sky_page, "Aviasales": avia_page, "Google Flights": serp_page}


def checked(make, chosen=None, currency="EUR"):
    """One page from a source, read and converted, with these filters applied as a check does."""
    res = make()
    if chosen:
        res.page["filters"] = chosen
    data = report.collect([res], currency, RATES)
    filters.apply(data, currency)
    return data


def prices(data):
    return [round(f.price) for f in data[0].parsed.flights]


# ----- connection airports from each source -------------------------------------------------------------------

@pytest.mark.parametrize("make", SOURCES.values(), ids=SOURCES.keys())
def test_each_source_reads_the_connection_airports(make):
    flights = checked(make)[0].parsed.flights
    assert [f.connections for f in flights] == [[], ["ZZH"], ["ZZH", "ZZJ"], ["ZZK"]]
    assert not any(f.connections_unknown for f in flights) and [f.max_stops for f in flights] == [0, 1, 2, 1]


def test_a_new_flight_has_no_connections_and_older_tests_keep_working():
    f = Flight("x", 1.0, "€1", [Leg("ZZA", "ZZB", "", "", 60, 0, "x")])
    assert f.connections == [] and not f.connections_unknown and f.marks == []
    assert Flight("y", 1.0, "€1", [Leg("ZZA", "ZZB", "", "", 60, 1, "x")]).connections_unknown      # a stop, nothing read
    assert Flight("z", 1.0, "€1", []).connections_unknown


def test_an_airport_change_counts_both_airports():
    raw = {"stopCount": 1, "segments": [
        {"origin": {"displayCode": "ZZA"}, "destination": {"displayCode": "ZZH"}},
        {"origin": {"displayCode": "ZZJ"}, "destination": {"displayCode": "ZZB"}}]}
    assert extract._leg_connections(raw) == ["ZZH", "ZZJ"]
    assert extract._leg_connections({"stopCount": 1, "segments": []}) == ["?"]


def test_the_return_direction_counts_too():
    feed = sky_feed([("a", 100.0, [])])
    back = sky_feed([("a", 100.0, ["ZZH"])])["itineraries"]["results"][0]["legs"][0]
    feed["itineraries"]["results"][0]["legs"].append(back)
    res = PageResult(page=dict(PAGE), status="ok", payloads=[feed], source="Skyscanner")
    assert prices(checked(lambda: res, {"max_stops": 0})) == []                  # direct out, one stop back
    res = PageResult(page=dict(PAGE), status="ok", payloads=[feed], source="Skyscanner")
    assert prices(checked(lambda: res, {"exclude_airports": ["ZZH"]})) == []


# ----- each filter alone, and together ------------------------------------------------------------------------

@pytest.mark.parametrize("make", SOURCES.values(), ids=SOURCES.keys())
@pytest.mark.parametrize("chosen, left, hidden", [
    ({"price_min": 150}, [200, 300, 400], {"price": 1}),
    ({"price_max": 300}, [100, 200, 300], {"price": 1}),            # the limits themselves count as inside
    ({"price_min": 200, "price_max": 300}, [200, 300], {"price": 2}),
    ({"max_stops": 0}, [100], {"transfers": 3}),
    ({"max_stops": 1}, [100, 200, 400], {"transfers": 1}),
    ({"max_stops": 2}, [100, 200, 300, 400], {}),
    ({"exclude_airports": ["ZZH"]}, [100, 400], {"airports": 2}),
    ({"exclude_airports": ["ZZJ", "ZZK"]}, [100, 200], {"airports": 2}),
    ({"price_max": 350, "max_stops": 1, "exclude_airports": ["ZZH"]}, [100], {"price": 1, "transfers": 1, "airports": 1}),
    ({"price_min": 500}, [], {"price": 4}),
])
def test_filters_alone_and_together_for_every_source(make, chosen, left, hidden):
    parsed = checked(make, chosen)[0].parsed
    assert [round(f.price) for f in parsed.flights] == left
    assert parsed.hidden == hidden
    kept = {f.id for f in parsed.flights}
    assert all(set(ids) <= kept for ids in parsed.picks.values())
    if left:
        assert all(parsed.picks[cat] for cat in ("best", "cheapest", "fastest"))


def test_the_source_order_of_best_survives():
    parsed = checked(serp_page, {"max_stops": 1})[0].parsed
    assert parsed.picks["best"][0] == parsed.flights[0].id
    body = serp_body()
    body["best_flights"], body["other_flights"] = body["other_flights"][2:], body["other_flights"][:2] + body["best_flights"]
    res = PageResult(page={**PAGE, "filters": {"exclude_airports": ["ZZH"]}}, status="ok", source="Google Flights")
    res.parsed = serpapi.parse(body, "EUR", False)
    data = report.collect([res], "EUR", RATES)
    filters.apply(data, "EUR")
    assert [next(f.price for f in data[0].parsed.flights if f.id == i) for i in data[0].parsed.picks["best"]] == [400.0, 100.0]


def test_a_price_range_is_compared_in_the_users_currency():
    assert prices(checked(avia_page, {"price_max": 250})) == [100, 200]     # Aviasales' rubles, converted to euros first


# ----- city codes ---------------------------------------------------------------------------------------------

def test_city_codes_expand_to_their_airports():
    assert filters.expand(["LOND"]) == set(urls.CITY_AIRPORTS["lond"].split(",")) == filters.expand(["LON"])
    assert filters.expand(["ZZH", "PARI"]) == {"ZZH", "CDG", "ORY", "BVA"}
    assert serpapi.CITY_AIRPORTS is urls.CITY_AIRPORTS and serpapi.airports("lond") == urls.CITY_AIRPORTS["lond"]
    data = checked(lambda: _via("LGW"), {"exclude_airports": ["LOND"]})
    assert prices(data) == [100] and data[0].parsed.hidden == {"airports": 1}


def _via(code):
    return PageResult(page=dict(PAGE), status="ok", payloads=[sky_feed([("a", 100.0, []), ("b", 200.0, [code])])], source="Skyscanner")


def test_codes_are_cleaned_and_bad_ones_refused():
    assert filters.clean_codes(" zzh, lond;ZZH  zzj ") == ["ZZH", "LOND", "ZZJ"]
    assert filters.clean_codes(["zzh"]) == ["ZZH"] and filters.clean_codes("") == [] and filters.clean_codes(None) == []
    assert filters.clean_codes("ZZHH") is None and filters.clean_codes("ZZ") is None and filters.clean_codes("12A") is None


# ----- what can't be judged -----------------------------------------------------------------------------------

def _no_segments():
    """Connections that can't be read: a stop the feed doesn't describe."""
    feed = sky_feed([("a", 100.0, []), ("b", 150.0, ["ZZH"]), ("c", 200.0, ["ZZK"])])
    feed["itineraries"]["results"][1]["legs"][0]["segments"] = []
    return PageResult(page=dict(PAGE), status="ok", payloads=[feed], source="Skyscanner")


def test_connections_unknown_stays_marked_and_doesnt_count_for_alerts():
    data = checked(_no_segments, {"exclude_airports": ["ZZK"]})
    parsed = data[0].parsed
    assert prices(data) == [100, 150] and parsed.hidden == {"airports": 1}
    unknown = parsed.flights[1]
    assert unknown.marks == [filters.CONNECTIONS_UNKNOWN] and not report.usable(unknown, RULES)
    assert report.usable(parsed.flights[0], RULES)
    doc = report.build_document(data, WHEN, 0, "EUR", RATES)
    assert "connections unknown" in doc and "ZZK" in doc
    # The only fare left can't be judged: nothing counts for alerts.
    only = checked(_no_segments, {"exclude_airports": ["ZZK"], "price_min": 120})
    assert report.route_bests(only, RULES)["r"]["cheapest"] is None
    assert report.route_bests(data, RULES)["r"]["cheapest"]["price"] == 100.0       # not the marked €150


def test_unknown_connections_only_matter_while_the_route_excludes_airports():
    assert checked(_no_segments)[0].parsed.flights[1].marks == []
    assert checked(_no_segments, {"max_stops": 1})[0].parsed.flights[1].marks == []


def test_a_known_excluded_airport_hides_a_fare_even_with_another_stop_unread():
    f = Flight("x", 1.0, "€1", [Leg("ZZA", "ZZB", "", "", 60, 2, "x")], connections=["ZZH", "?"])
    parsed = ParsedPage([f], {}, True, "€", 1, currency_code="EUR")
    filters.apply_page(parsed, {"exclude_airports": ["ZZH"]})
    assert parsed.flights == [] and parsed.hidden == {"airports": 1}


def test_a_price_that_couldnt_be_converted_stays_marked_and_doesnt_alert():
    data = checked(sky_page_in_rubles, {"price_max": 2})      # no exchange rate for ¥: never compared with the range
    parsed = data[0].parsed
    assert not parsed.comparable and len(parsed.flights) == 4 and not parsed.hidden
    assert all(f.marks == [filters.PRICE_UNKNOWN] and not report.usable(f, RULES) for f in parsed.flights)
    assert "price unknown" in report.build_document(data, WHEN, 0, "EUR", RATES)
    assert "r" not in report.route_bests(data, RULES)
    assert checked(sky_page_in_rubles)[0].parsed.flights[0].marks == []      # without a price range nothing is marked


def sky_page_in_rubles():
    feed = sky_feed()
    for raw in feed["itineraries"]["results"]:
        raw["price"]["formatted"] = f"¥{raw['price']['raw']:.0f}"
    return PageResult(page={**PAGE, "url": "https://www.skyscanner.jp/x"}, status="ok", payloads=[feed], source="Skyscanner")


def test_page_text_is_never_taken_as_matching():
    res = PageResult(page={**PAGE, "filters": {"exclude_airports": ["ZZH"]}}, status="ok", source="Skyscanner",
                     text="Invented fare €50 via ZZH")
    data = report.collect([res], "EUR", RATES)
    filters.apply(data, "EUR")
    doc = report.build_document(data, WHEN, 0, "EUR", RATES)
    assert "Invented fare €50" in doc and "connections unknown" in doc and "don't take them as matching" in doc
    assert report.route_bests(data, RULES) == {}


def test_hidden_fares_dont_come_back_through_the_page_text():
    res = sky_page()
    res.text = "Invented page text: €100 via nowhere"
    res.page["filters"] = {"price_min": 500}
    data = report.collect([res], "EUR", RATES)
    filters.apply(data, "EUR")
    doc = report.build_document(data, WHEN, 0, "EUR", RATES)
    assert "Invented page text" not in doc and "4 fares hidden by this route's filters (price 4)" in doc


# ----- everything downstream ----------------------------------------------------------------------------------

def _analyst(price):
    return {"routes": {"r": {"best_value": price, "best_value_text": f"€{price}, invented", "best_value_stops": 0,
                             "best_value_minutes": 120}}}


def test_downstream_only_sees_matching_fares():
    data = checked(sky_page, {"price_min": 150, "max_stops": 1, "exclude_airports": ["ZZK"]})
    assert prices(data) == [200] and data[0].parsed.hidden == {"price": 1, "transfers": 1, "airports": 1}

    bests = report.route_bests(data, RULES)["r"]
    assert bests["cheapest"]["price"] == bests["fastest"]["price"] == bests["best_pick"]["price"] == 200.0
    assert report.price_summary(data)["r"]["Skyscanner"]["cheapest"] == 200.0

    doc = report.build_document(data, WHEN, 0, "EUR", RATES)
    assert "€200" in doc and "€100" not in doc and "€300" not in doc and "€400" not in doc
    assert "3 fares hidden by this route's filters (price 1, transfers 1, airports 1)." in doc
    assert "This route's filters: price from €150; at most 1 transfer per direction; no transfers at ZZK." in doc

    rec = pricelog.records_from_check(data, WHEN)[0]
    assert rec["price"] == 200.0 and rec["filters"] == {"price_min": 150.0, "max_stops": 1, "exclude_airports": ["ZZK"], "currency": "EUR"}

    page = html.unescape(dashboard.build(data, {"runs": []}, {}, RULES, WHEN, "", False, {}, {}, "x.md", currency="EUR", rates=RATES))
    assert "€200" in page and "€100" not in page and "€400" not in page
    assert "3 fares hidden by this route's filters (price: 1, transfers: 1, airports: 1)" in page
    ru = html.unescape(dashboard.build(data, {"runs": []}, {}, RULES, WHEN, "", False, {}, {}, "x.md", lang="ru", currency="EUR", rates=RATES))
    assert "3 тарифа скрыто фильтрами этого маршрута (цена: 1, пересадки: 1, аэропорты: 1)" in ru


def test_the_best_value_pick_has_to_pass_the_filters():
    data = checked(sky_page, {"max_stops": 0})
    assert runner._best_values(_analyst(100), "EUR", data, RULES)["r"]["excluded"] is False
    assert runner._best_values(_analyst(400), "EUR", data, RULES) == {}          # hidden: as good as not captured
    page = dashboard.build(data, {"runs": []}, {}, RULES, WHEN, "", False, _analyst(400), {}, "x.md", currency="EUR", rates=RATES)
    assert "€400" not in page
    # A kept fare that couldn't be judged can be picked, but never alerts.
    unknown = checked(_no_segments, {"exclude_airports": ["ZZK"]})
    assert runner._best_values(_analyst(150), "EUR", unknown, RULES)["r"]["excluded"] is True


def test_when_every_fare_is_hidden_the_check_still_says_why():
    data = checked(sky_page, {"price_min": 500})
    assert data[0].parsed.flights == [] and pricelog.records_from_check(data, WHEN) == []
    assert report.route_bests(data, RULES) == {} and report.price_summary(data) == {}
    page = html.unescape(dashboard.build(data, {"runs": []}, {}, RULES, WHEN, "", False, {}, {}, "x.md", currency="EUR", rates=RATES))
    assert "No fares match this route's filters." in page and "4 fares hidden" in page


def test_the_analysts_rules_stay_the_same_and_filters_come_in_the_document():
    from airfare import analyst
    assert "filter" not in analyst.RULES.replace("alert filters", "").lower() and "max_stops" not in analyst.RULES
    data = checked(sky_page, {"max_stops": 0})
    assert "This route's filters: direct flights only." in report.build_document(data, WHEN, 0, "EUR", RATES)


# ----- a whole check ------------------------------------------------------------------------------------------

@pytest.fixture
def whole_check(tmp_path, monkeypatch):
    """runner.run_check with the sources, the network and the files faked: returns what it saved, per check."""
    saved = {"records": [], "toasts": [], "alerts": [], "history": {"routes": {}, "runs": []}, "pages": None}

    async def collect(cfg, pages, sources, automatic=False):
        return [PageResult(page=dict(p), status="ok", payloads=[sky_feed()], source="Skyscanner") for p in pages], None

    def dashboard_written(cfg, data, *rest):
        saved["pages"] = data
        return tmp_path / "latest.html"

    monkeypatch.setattr(runner, "collect_prices", collect)
    monkeypatch.setattr(runner, "wait_for_network", lambda host, limit=0: True)
    monkeypatch.setattr(runner.money, "rates", lambda refresh=True: RATES)
    monkeypatch.setattr(runner.pricelog, "add", lambda records: saved["records"].extend(records))
    monkeypatch.setattr(runner, "write_history_page", lambda cfg: None)
    monkeypatch.setattr(runner, "load_history", lambda: saved["history"])
    monkeypatch.setattr(runner, "save_history", lambda history: saved.update(history=history))
    monkeypatch.setattr(runner.cleanup, "automatic", lambda cfg: None)
    monkeypatch.setattr(runner.notify, "toast", lambda *a, **k: saved["toasts"].append(a))
    monkeypatch.setattr(runner, "send_alerts", lambda data, hits, *a: saved["alerts"].append(hits) or True)
    monkeypatch.setattr(runner, "_write_dashboard", dashboard_written)
    monkeypatch.setattr(runner.links, "for_dashboard", lambda path: path)
    monkeypatch.setattr(runner, "REPORTS_DIR", tmp_path)

    def check(**route):
        future = date.today().replace(year=date.today().year + 1).isoformat()
        cfg = {**config.DEFAULT_CONFIG, "sources": ["serpapi"], "serpapi_key": "invented", "llm_provider": "none", "currency": "EUR",
               "routes": [{**_route(depart_from=future), **route}]}
        monkeypatch.setattr(runner, "load_config", lambda: cfg)
        assert asyncio.run(runner.run_check()) == 0
        return saved
    return check


def test_a_whole_check_applies_the_filters_and_restarts_the_references(whole_check, tmp_path):
    saved = whole_check()
    assert [r["price"] for r in saved["records"]] == [100.0] and "filters" not in saved["records"][0]
    assert saved["history"]["routes"]["r"]["alert_refs"]["cheapest"]["price"] == 100.0
    assert saved["alerts"] == []

    # €100 is hidden now: the next check starts from what's left, and doesn't alert on it.
    saved = whole_check(price_min=150, max_stops=1, exclude_airports=["ZZK"])
    assert [r["price"] for r in saved["records"]] == [100.0, 200.0] and saved["records"][1]["filters"]["max_stops"] == 1
    h = saved["history"]["routes"]["r"]
    assert h["alert_refs"]["cheapest"]["price"] == 200.0 and h["alert_refs"]["cheapest"]["reason"] == "first check"
    assert h["all_time_low"]["price"] == 200.0 and h["filters"]["price_min"] == 150.0
    assert [f.price for f in saved["pages"][0].parsed.flights] == [200.0]
    document = sorted(tmp_path.glob("*-prices.md"))[-1].read_text(encoding="utf-8")
    assert "This route's filters: price from €150" in document and "| €100 |" not in document
    assert saved["alerts"] == []

    saved = whole_check(price_min=150, max_stops=1, exclude_airports=["ZZK"])          # the same filters: same references
    assert saved["history"]["routes"]["r"]["alert_refs"]["cheapest"]["set"] == h["alert_refs"]["cheapest"]["set"]


def test_a_check_where_every_fare_is_hidden_read_prices_all_the_same(whole_check):
    saved = whole_check(price_min=5000)
    assert saved["records"] == [] and saved["toasts"] == [] and saved["pages"][0].parsed.hidden == {"price": 4}
    assert config.load_state()["last_check"]                 # the schedule counts it as a check that read prices


# ----- filters off --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("make", SOURCES.values(), ids=SOURCES.keys())
def test_filters_off_gives_the_same_results_as_before(make):
    plain = report.collect([make()], "EUR", RATES)
    before = copy.deepcopy(plain[0].parsed)
    doc = report.build_document(plain, WHEN, 0, "EUR", RATES)
    recs = pricelog.records_from_check(plain, WHEN)
    filters.apply(plain, "EUR")
    assert plain[0].parsed == before and "filters" not in plain[0].page
    assert report.build_document(plain, WHEN, 0, "EUR", RATES) == doc
    assert "filter" not in doc.lower() and "hidden" not in doc
    after = pricelog.records_from_check(plain, WHEN)
    assert [{k: v for k, v in r.items() if k != "id"} for r in after] == [{k: v for k, v in r.items() if k != "id"} for r in recs]
    assert "filters" not in after[0] and "marks" not in after[0]
    page = dashboard.build(plain, {"runs": []}, {}, RULES, WHEN, "", False, {}, {}, "x.md", currency="EUR", rates=RATES)
    assert "hidden by" not in page


def test_damaged_or_empty_filter_fields_count_as_no_filter():
    assert filters.normal(None) == {} and filters.normal({}) == {}
    assert filters.normal({"price_min": None, "price_max": "", "max_stops": None, "exclude_airports": []}) == {}
    assert filters.normal({"price_min": -5, "price_max": True, "max_stops": 7, "exclude_airports": ["not a code"]}) == {}
    assert filters.normal({"max_stops": False}) == {} and filters.normal("nonsense") == {}
    assert filters.normal({"price_max": 300, "max_stops": 0, "exclude_airports": ["zzk", "zzh"]}) == {
        "price_max": 300.0, "max_stops": 0, "exclude_airports": ["ZZH", "ZZK"]}


# ----- the sources' own filters -------------------------------------------------------------------------------

SERP = {"origin": "zza", "destination": "zzb", "depart": "2027-03-12"}


def test_serpapi_gets_google_flights_own_filters():
    p = serpapi.params({**SERP, "filters": {"price_max": 299.5, "max_stops": 0, "exclude_airports": ["ZZH", "LOND"]}}, "KEY", "EUR")
    assert p["stops"] == 1 and p["max_price"] == 300                      # 1 means nonstop only in SerpApi's codes
    assert p["exclude_conns"].split(",") == sorted({"ZZH", *urls.CITY_AIRPORTS["lond"].split(",")})
    assert serpapi.params({**SERP, "filters": {"max_stops": 1}}, "KEY", "EUR")["stops"] == 2
    assert serpapi.params({**SERP, "filters": {"max_stops": 2}}, "KEY", "EUR")["stops"] == 3


def test_serpapi_without_filters_asks_what_it_always_did():
    p = serpapi.params(SERP, "KEY", "EUR")
    assert not {"stops", "max_price", "exclude_conns"} & set(p)
    assert serpapi.params({**SERP, "filters": {"price_min": 100}}, "KEY", "EUR") == p    # Google has no minimum price


def test_a_filtered_search_that_finds_nothing_says_the_filters_may_be_why(monkeypatch):
    monkeypatch.setattr(serpapi, "_get", lambda url, timeout=90: {})
    res = serpapi.search({**SERP, "url": "u", "key": "k", "filters": {"max_stops": 0}}, "KEY", "EUR")
    assert res.status == "no_results" and "this route's filters" in res.note


def _route(**kw):
    return {"id": "r", "origin": "zza", "destination": "zzb", "trip": "oneway", "depart_from": "2027-03-12", **kw}


def test_direct_only_prefers_directs_on_skyscanner_and_nothing_else_changes_the_links():
    today = date(2026, 10, 26)
    plain = urls.route_pages(_route(), "www.skyscanner.net", today)[0]["url"]
    assert "preferdirects=false" in plain
    assert urls.route_pages(_route(max_stops=1, price_max=300, exclude_airports=["ZZH"]), "www.skyscanner.net", today)[0]["url"] == plain
    direct = urls.route_pages(_route(max_stops=0), "www.skyscanner.net", today)[0]["url"]
    assert direct == plain.replace("preferdirects=false", "preferdirects=true")
    page = {"origin": "zza", "destination": "zzb", "depart": "2027-03-12", "filters": {"max_stops": 0}}
    assert urls.aviasales_url(page, today) == urls.aviasales_url({k: v for k, v in page.items() if k != "filters"}, today)


def test_prefer_direct_flights_keeps_its_meaning_and_never_becomes_direct_only():
    today = date(2026, 10, 26)
    cfg = {"domain": "www.skyscanner.net", "max_pages": 20, "routes": [_route(direct_only=True)]}
    page = urls.plan_pages(cfg, today)[0][0]
    assert "preferdirects=true" in page["url"] and page["direct_only"] is True and "filters" not in page
    data = report.collect([PageResult(page={**PAGE, **page}, status="ok", payloads=[sky_feed()], source="Skyscanner")], "EUR", RATES)
    filters.apply(data, "EUR")
    assert prices(data) == [100, 200, 300, 400]


def test_pages_carry_their_routes_filters_and_the_extension_doesnt_see_them():
    cfg = {"domain": "www.skyscanner.net", "max_pages": 20, "routes": [_route(price_max=300, max_stops=None, exclude_airports=[])]}
    page = urls.plan_pages(cfg, date(2026, 10, 26))[0][0]
    assert page["filters"] == {"price_max": 300}
    source = (ROOT / "airfare" / "extension.py").read_text(encoding="utf-8")
    assert '{"n": i, "url": p["url"], "site": p.get("site") or "Skyscanner"}' in source


# ----- Settings: the route's identity, its references, saving ----------------------------------------------------

FORM = {"sources": ["extension"], "routes": [_route(name="Invented", adults=1, price_max="300", max_stops="1", exclude_airports="zzh, lond")]}


def test_the_form_saves_filters_and_clears_them(monkeypatch):
    monkeypatch.setattr(webui, "load_config", lambda: dict(config.DEFAULT_CONFIG))
    route = webui.clean_config(FORM)["routes"][0]
    assert (route["price_min"], route["price_max"], route["max_stops"], route["exclude_airports"]) == (None, 300.0, 1, ["ZZH", "LOND"])
    empty = webui.clean_config({**FORM, "routes": [_route(price_max="", max_stops="", exclude_airports="")]})["routes"][0]
    assert (empty["price_min"], empty["price_max"], empty["max_stops"], empty["exclude_airports"]) == (None, None, None, [])
    direct = webui.clean_config({**FORM, "routes": [_route(max_stops=0)]})["routes"][0]
    assert direct["max_stops"] == 0 and direct["direct_only"] is False
    box = webui.clean_config({**FORM, "routes": [_route(direct_only=True)]})["routes"][0]
    assert box["direct_only"] is True and box["max_stops"] is None        # the old box never turns into Direct only


@pytest.mark.parametrize("bad", [{"price_min": "cheap"}, {"price_min": "300", "price_max": "200"}, {"price_max": "-1"},
                                 {"exclude_airports": "not valid"}])
def test_the_form_refuses_filters_that_make_no_sense(monkeypatch, bad):
    monkeypatch.setattr(webui, "load_config", lambda: dict(config.DEFAULT_CONFIG))
    with pytest.raises(webui.Problem, match="Route 1"):
        webui.clean_config({**FORM, "routes": [_route(**bad)]})
    problems = {}
    assert webui.clean_config({**FORM, "routes": [_route(**bad)]}, problems)["routes"] == [] and problems["r"]


def test_changing_filters_keeps_the_route_id(monkeypatch):
    old = _route(name="Invented", adults=1, cabin="economy", children=[])
    monkeypatch.setattr(webui, "load_config", lambda: {**config.DEFAULT_CONFIG, "routes": [old]})
    assert webui._trip(old) == webui._trip({**old, "price_max": 1, "max_stops": 0, "exclude_airports": ["ZZH"]})
    saved = webui.clean_config({**FORM, "routes": [{**old, "price_max": "300", "max_stops": "0"}]}, renew_ids=True)
    assert saved["routes"][0]["id"] == "r"
    other = webui.clean_config({**FORM, "routes": [{**old, "cabin": "business", "max_stops": "0"}]}, renew_ids=True)
    assert other["routes"][0]["id"] != "r"                   # another search still gets its own id


def test_a_price_range_follows_a_currency_change_without_restarting_the_references(monkeypatch):
    old = _route(price_min=100.0, price_max=300.0)
    monkeypatch.setattr(webui, "load_config", lambda: {**config.DEFAULT_CONFIG, "currency": "EUR", "routes": [old]})
    monkeypatch.setattr(webui.money, "rates", lambda: RATES)
    route = webui.clean_config({"sources": ["extension"], "currency": "RUB", "routes": [{**old}]})["routes"][0]
    assert route["price_min"] == 10000 and route["price_max"] == 30000
    assert filters.changed_routes([old], [route], "EUR", "RUB") == []
    assert filters.changed_routes([old], [{**route, "price_min": None}], "EUR", "RUB") == [{**route, "price_min": None}]


def history_with_references():
    return {"routes": {"r": {"name": "Invented", "alert_refs": {"cheapest": {"price": 100.0, "text": "€100", "currency": "EUR"}},
                             "alert_ref": {"cheapest": 90.0}, "all_time_low": {"price": 100.0}, "last": {"checked": "x"}}},
            "runs": [{"time": "2026-10-25T09:00"}]}


def test_changing_filters_restarts_the_references_from_the_next_check():
    history = history_with_references()
    route = _route(max_stops=0)
    assert filters.restart_references(history, [route], "EUR") == ["r"]
    h = history["routes"]["r"]
    assert report.alert_refs(h) == {} and "all_time_low" not in h and "last" not in h
    assert h["name"] == "Invented" and h["filters"] == {"max_stops": 0} and history["runs"]    # the rest stays

    targets = report.alert_targets(history, ["r"], RULES, "EUR", RATES)
    assert "no earlier prices" in report.previous_records(history, ["r"], targets, RULES, "EUR", RATES)
    data = checked(sky_page, {"max_stops": 0})
    bests = report.route_bests(data, RULES)
    assert report.threshold_hits(targets, bests, {}) == {}               # the next check is a baseline, not an alert
    report.update_history(history, bests, WHEN, {}, currency="EUR", rates=RATES)
    assert h["alert_refs"]["cheapest"]["price"] == 100.0 and h["alert_refs"]["cheapest"]["reason"] == "first check"
    assert h["filters"] == {"max_stops": 0}

    # The same filters at the next check change nothing; other ones, or none, restart again.
    assert filters.restart_references(history, [route], "EUR") == [] and h["alert_refs"]
    assert filters.restart_references(history, [_route(max_stops=1)], "EUR") == ["r"] and "alert_refs" not in h
    assert filters.restart_references(history, [_route()], "EUR") == ["r"] and "filters" not in h
    assert filters.restart_references(history, [_route()], "EUR") == []


def test_routes_without_filters_keep_their_references_untouched():
    history = history_with_references()
    before = copy.deepcopy(history)
    assert filters.restart_references(history, [_route(), {"id": "new", "origin": "zzc"}], "EUR") == []
    assert history == before


def test_a_new_route_with_filters_gets_its_references_from_its_first_check():
    history = {"routes": {}}
    assert filters.restart_references(history, [_route(name="Invented", max_stops=0)], "EUR") == ["r"]
    assert history["routes"]["r"] == {"name": "Invented", "filters": {"max_stops": 0}}
    assert filters.restart_references(history, [_route(name="Invented", max_stops=0)], "EUR") == []


def test_a_currency_change_alone_doesnt_restart_the_references():
    history = history_with_references()
    filters.restart_references(history, [_route(price_max=300.0)], "EUR")
    report.update_history(history, report.route_bests(checked(sky_page, {"price_max": 300.0}), RULES), WHEN, {},
                          currency="EUR", rates=RATES)
    assert filters.restart_references(history, [_route(price_max=30000)], "RUB") == []
    assert history["routes"]["r"]["alert_refs"] and history["routes"]["r"]["filters"]["currency"] == "RUB"


def test_settings_says_so_when_saving():
    source = (ROOT / "airfare" / "static" / "index.html").read_text(encoding="utf-8")
    assert source.count("filters_changed") == 2 and "their alert references restart from the next check" in source
    before = [_route(max_stops=0), _route(id="s")]
    assert filters.changed_routes(before, [_route(max_stops=1), _route(id="s"), _route(id="new", max_stops=0)], "EUR", "EUR") == [_route(max_stops=1)]


def test_settings_has_the_three_filters_under_cabin_and_the_help_line():
    source = (ROOT / "airfare" / "static" / "index.html").read_text(encoding="utf-8")
    cabin = source.index('data-k="cabin"')
    for field in ('data-k="price_min"', 'data-k="price_max"', 'data-k="max_stops"', 'data-k="exclude_airports"'):
        assert source.index(field) > cabin
    assert source.count("A route's filters hide fares everywhere") == 1
    page = webui.settings_page("ru")
    assert '"html:price-from": "От"' in page and "Диапазон цен" in page and '"Direct only": "Только прямые"' in page


# ----- saving never brings back a cleared filter ----------------------------------------------------------------

def test_save_config_never_brings_back_a_filter_the_user_cleared(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    (tmp_path / "config.json").write_text(json.dumps({"routes": [
        {"id": "r", "origin": "zza", "price_min": 100, "price_max": 300, "max_stops": 0, "exclude_airports": ["ZZH"], "future_field": "kept"}]}),
        encoding="utf-8")
    assert set(urls.FILTER_FIELDS) <= set(config.ROUTE_FIELDS)
    config.save_config({**config.DEFAULT_CONFIG, "routes": [{"id": "r", "origin": "zza"}]})
    stored = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))["routes"][0]
    assert stored == {"id": "r", "origin": "zza", "future_field": "kept"}


# ----- price history ---------------------------------------------------------------------------------------------

@pytest.fixture
def store(monkeypatch, tmp_path):
    monkeypatch.setattr(pricelog, "LOG_FILE", tmp_path / "price_history.json")
    monkeypatch.setattr(pricelog, "RESEARCH_FILE", tmp_path / "price_research.json")


def test_new_records_carry_their_filters_and_old_ones_stay_untouched(store, tmp_path):
    old = [json.loads(json.dumps(r)) for r in json.loads((FIXTURE_141 / "price_history.json").read_text(encoding="utf-8"))]
    (tmp_path / "price_history.json").write_text(json.dumps(old), encoding="utf-8")
    data = checked(sky_page, {"price_max": 300, "max_stops": 2})
    pricelog.add(pricelog.records_from_check(data, WHEN))
    stored = pricelog.load()
    assert stored[:-1] == old and all("filters" not in r for r in stored[:-1])
    assert stored[-1]["filters"] == {"price_max": 300.0, "max_stops": 2, "currency": "EUR"}


def test_a_record_of_a_fare_that_couldnt_be_judged_says_so():
    data = checked(_no_segments, {"exclude_airports": ["ZZK"], "price_min": 120})
    assert pricelog.records_from_check(data, WHEN)[0]["marks"] == ["connections unknown"]


def test_the_history_page_marks_records_under_other_filters_and_the_csv_has_them(store):
    cfg = {**config.DEFAULT_CONFIG, "routes": [_route(price_max=300.0)], "currency": "EUR"}
    route = historypage.routes_info(cfg, [])[0]
    assert route["filters"] == {"price_max": 300.0, "currency": "EUR"}
    assert historypage.routes_info({**cfg, "routes": [_route()]}, [])[0]["filters"] == {}
    page = historypage.build(cfg, served=False)
    for piece in ("otherFilters(x, r)", "filterMark(x, r)", '"url", "filters"]', "filterText(x.filters)"):
        assert piece in page


def test_history_marking_runs_the_same_in_the_browser_code(store):
    """filterText, otherFilters and the CSV column, run for real when Node.js is available."""
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js isn't installed")
    import subprocess
    source = historypage.PAGE
    start = source.index("// The filters a record was taken under")
    end = source.index("function setDates(r)")
    script = """
const D = {currency: "EUR", sign: "€", sign_after: false, texts: {}};
const t = (s, p) => String(s).replace(/\\{(\\w+)\\}/g, (m, k) => (p && k in p ? p[k] : m));
const tn = (n, forms, p) => t(forms.split("|")[n === 1 ? 0 : 1], {n, ...p});
const esc = s => String(s);
function money(v) { return D.sign + Math.round(v); }
""" + source[start:end] + """
const route = {active: true, filters: {price_max: 300, currency: "EUR"}};
console.log(JSON.stringify({
  same: otherFilters({filters: {price_max: 300, currency: "EUR"}}, route),
  old: otherFilters({}, route),
  other: otherFilters({filters: {price_max: 200, currency: "EUR"}}, route),
  stops: otherFilters({filters: {price_max: 300, currency: "EUR", max_stops: 0}}, route),
  converted: otherFilters({filters: {price_max: 30000, currency: "RUB"}}, route),
  gone: otherFilters({filters: {max_stops: 0}}, {active: false, filters: {}}),
  none: otherFilters({}, {active: true, filters: {}}),
  text: filterText({price_min: 100, price_max: 300, currency: "EUR", max_stops: 1, exclude_airports: ["ZZH", "ZZK"]}),
  rub: filterText({price_max: 30000, currency: "RUB", max_stops: 0}),
  mark: filterMark({filters: {max_stops: 0}}, route),
  bare: filterMark({}, route),
}));
"""
    out = subprocess.run([node, "-"], input=script, capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stderr
    got = json.loads(out.stdout)
    assert got["same"] is False and got["old"] is True and got["other"] is True and got["stops"] is True
    assert got["converted"] is False and got["gone"] is False and got["none"] is False
    assert got["text"] == "€100–€300, up to 1 transfer, not via ZZH, ZZK"
    assert got["rub"] == "up to 30000 RUB, direct only"
    assert "taken under other filters: direct only" in got["mark"] and "taken without filters" in got["bare"]


# ----- the invented 1.4.1 data -----------------------------------------------------------------------------------

@pytest.fixture
def data_141(tmp_path, monkeypatch):
    folder = tmp_path / "data"
    shutil.copytree(FIXTURE_141, folder, ignore=shutil.ignore_patterns("README.txt"))
    monkeypatch.setattr(migrate, "DATA_DIR", folder)
    monkeypatch.setattr(config, "CONFIG_FILE", folder / "config.json")
    return folder


def test_the_1_4_1_data_loads_with_no_filters(data_141):
    migrate.ensure(data_141)
    assert migrate.SCHEMA == 2                               # new optional fields need no migration step
    cfg = config.load_config()
    assert all(filters.normal(r) == {} for r in cfg["routes"])
    direct = next(r for r in cfg["routes"] if r["id"] == "fx02cd")
    assert direct["direct_only"] is True and filters.normal(direct) == {}      # an old true never becomes Direct only
    pages, _ = urls.plan_pages({**cfg, "routes": [{**r, "enabled": True} for r in cfg["routes"]]}, date(2026, 10, 26))
    assert pages and all("filters" not in p for p in pages)

    history = json.loads((data_141 / "history.json").read_text(encoding="utf-8"))
    before = copy.deepcopy(history)
    assert filters.restart_references(history, cfg["routes"], cfg["currency"]) == [] and history == before

    records = json.loads((data_141 / "price_history.json").read_text(encoding="utf-8"))
    assert all("filters" not in r for r in records)
    assert historypage.routes_info(cfg, records)[0]["filters"] == {}


def test_a_saved_1_4_1_route_keeps_its_id_and_gains_empty_filters(data_141):
    migrate.ensure(data_141)
    form = config.load_config()
    form["llm_provider"] = "none"
    saved = webui.clean_config(form, renew_ids=True)
    assert [r["id"] for r in saved["routes"]] == ["fx01ab", "fx02cd"]
    assert all(r["price_min"] is None and r["price_max"] is None and r["max_stops"] is None and r["exclude_airports"] == []
               for r in saved["routes"])
    assert filters.changed_routes(form["routes"], saved["routes"], "EUR", "EUR") == []


# ----- from the review of the safe-updates work ------------------------------------------------------------------

def test_the_stop_also_shows_a_notification_on_macos_and_linux(monkeypatch, tmp_path):
    shown = []
    monkeypatch.setattr(upgrade.platform, "notify", lambda title, lines, **kw: shown.append((title, lines)) or True)
    monkeypatch.setattr(upgrade, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(upgrade.platform, "WINDOWS", False)
    upgrade.tell_desktop()
    assert shown == [("AirFare", ["Run sh install.sh in the AirFare folder to finish the update"])]
    (tmp_path / "config.json").write_text(json.dumps({"language": "es"}), encoding="utf-8")
    upgrade.tell_desktop()
    assert "Ejecuta sh install.sh" in shown[1][1][0]
    shown.clear()
    monkeypatch.setattr(upgrade.platform, "WINDOWS", True)
    upgrade.tell_desktop()
    assert shown == []                                       # AirFare.exe finishes the update itself there


def test_the_stop_has_its_own_exit_code_and_calls_the_notification(monkeypatch, capsys):
    from airfare import __main__ as cli
    told = []
    monkeypatch.setattr(upgrade, "mismatch", lambda *a, **k: "invented mismatch")
    monkeypatch.setattr(upgrade, "note", lambda text: None)
    monkeypatch.setattr(upgrade, "tell_desktop", lambda: told.append(1))
    assert cli.main(["run"], check_install=True) == upgrade.UNFINISHED
    assert told == [1] and upgrade.UNFINISHED not in (0, 1, 2, 3, runner.HELD)


@pytest.mark.parametrize("script, kept", [("install.ps1", "data\\backups"), ("install.sh", "data/backups")])
def test_after_the_migration_the_scripts_dont_say_the_data_is_untouched(script, kept):
    text = (ROOT / script).read_text(encoding="utf-8")
    migrate_at, finish_at = text.index("airfare migrate"), text.index("airfare.upgrade finish")
    changed = text.index("untouched", migrate_at + 80)
    assert migrate_at < changed < finish_at
    assert f"Your data is kept and backed up in {kept}" in text[changed:finish_at]
    assert "Finishing the setup failed. $untouched" in text[finish_at:]
    assert "Your data is untouched" in text[:migrate_at]


@pytest.mark.parametrize("system", ["WINDOWS", "MACOS"])
def test_a_file_renamed_only_by_capitals_is_never_deleted(tmp_path, monkeypatch, system):
    for flag in ("WINDOWS", "MACOS"):
        monkeypatch.setattr(upgrade.platform, flag, flag == system)
    listed = ["airfare/__init__.py", "airfare/Renamed.py", "airfare/Static/Page.html"]
    # The old version's capitals on disk; on a folder that tells capitals apart, the new names exist as well.
    for name in ["airfare/__init__.py", "airfare/renamed.py", "airfare/static/page.html", "airfare/retired.py", *listed]:
        path = tmp_path / name
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("invented", encoding="utf-8")
    (tmp_path / "MANIFEST.txt").write_text("\n".join(listed) + "\n", encoding="utf-8")
    removed = upgrade.remove_leftovers(tmp_path, data=tmp_path / "data")
    assert removed == ["airfare/retired.py"]
    assert (tmp_path / "airfare" / "renamed.py").exists() and (tmp_path / "airfare" / "static" / "page.html").exists()


def test_capitals_still_count_where_folders_tell_them_apart(tmp_path, monkeypatch):
    probe = tmp_path / "CaseProbe"
    probe.write_text("x", encoding="utf-8")
    if (tmp_path / "caseprobe").exists():
        pytest.skip("this folder doesn't tell capitals apart")
    monkeypatch.setattr(upgrade.platform, "WINDOWS", False)
    monkeypatch.setattr(upgrade.platform, "MACOS", False)
    for name in ("airfare/__init__.py", "airfare/Renamed.py", "airfare/renamed.py"):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("invented", encoding="utf-8")
    (tmp_path / "MANIFEST.txt").write_text("airfare/__init__.py\nairfare/Renamed.py\n", encoding="utf-8")
    assert upgrade.remove_leftovers(tmp_path, data=tmp_path / "data") == ["airfare/renamed.py"]
