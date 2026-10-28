from datetime import datetime

from airfare import report

RATES = {"rates": {"EUR": 1.0, "GBP": 0.8, "RUB": 100.0}}


def rules(cheapest=5, fastest=3, best=3, **kw):
    cfg = {"alerts": {"cheapest": {"on": True, "drop": cheapest, "max": kw.pop("cheapest_max", None)},
                      "fastest": {"on": kw.pop("fastest_on", True), "drop": fastest, "max": None},
                      "best": {"on": True, "drop": best, "max": None}}, **kw}
    return report.alert_rules(cfg)


def rec(price, minutes=145, stops=0):
    return {"price": price, "price_text": f"€{price:.0f}", "currency": "EUR", "depart": "2027-03-12T16:00:00",
            "return": None, "airlines": "transavia", "stops": stops, "minutes": minutes, "source": "Skyscanner",
            "url": "https://example.test/x"}


def best(cheapest, fastest=None, fast_minutes=145):
    return {"name": "Barcelona", "best_pick": None, "cheapest": rec(cheapest, 2190, 2),
            "fastest": rec(fastest if fastest is not None else cheapest + 40, fast_minutes)}


def run(history, cheapest, fastest=None, best_value=None, alerted=None):
    bv = {"r": {"price": best_value, "text": f"€{best_value:.0f}", "stops": 0, "minutes": 280}} if best_value else {}
    return report.update_history(history, {"r": best(cheapest, fastest)}, datetime(2026, 10, 26, 16, 0), {}, bv,
                                 alerted=alerted, currency="EUR", rates=RATES)


def test_first_check_sets_a_reference_per_kind():
    h = run({}, 170.0, 212.0, best_value=212.0)
    refs = h["routes"]["r"]["alert_refs"]
    assert refs["cheapest"]["price"] == 170.0 and refs["fastest"]["price"] == 212.0 and refs["best"]["price"] == 212.0
    assert all(r["reason"] == "first check" for r in refs.values())
    t = report.alert_targets(h, ["r"], rules(), "EUR", RATES)["r"]
    assert t["cheapest"]["target"] == 161.0 and t["cheapest"]["target_text"] == "€161"    # 5% off, whole euros
    assert t["fastest"]["target"] == 205.0 and t["best"]["target"] == 205.0               # 3% off


def test_a_small_drop_on_a_comfortable_trip_alerts_on_its_own_threshold():
    h = run({}, 170.0, 212.0)
    t = report.alert_targets(h, ["r"], rules(cheapest=10, fastest=2), "EUR", RATES)
    hits = report.threshold_hits(t, {"r": best(169.0, 207.0)}, {})
    assert hits == {"r": ["fastest"]}                # €5 off the fast trip counts; €1 off the 36-hour one doesn't
    h = run(h, 169.0, 207.0, alerted=hits)
    refs = h["routes"]["r"]["alert_refs"]
    assert refs["fastest"]["price"] == 207.0 and refs["fastest"]["reason"] == "LOW PRICE alert"
    assert refs["cheapest"]["price"] == 170.0        # one kind's alert doesn't move another's reference


def test_slow_slide_alerts_once_it_adds_up():
    h = run({}, 178.0)
    for p in (175.0, 172.0):
        assert report.threshold_hits(report.alert_targets(h, ["r"], rules(), "EUR", RATES),
                                     {"r": best(p, 300.0)}, {}) == {}
        h = run(h, p, 300.0)
    t = report.alert_targets(h, ["r"], rules(), "EUR", RATES)
    assert report.threshold_hits(t, {"r": best(169.0, 300.0)}, {}) == {"r": ["cheapest"]}


def test_best_value_needs_a_comparable_trip():
    h = run({}, 178.0, 250.0, best_value=212.0)
    t = report.alert_targets(h, ["r"], rules(), "EUR", RATES)
    longer = {"r": {"price": 199.0, "text": "", "stops": 2, "minutes": 900}}
    same = {"r": {"price": 199.0, "text": "", "stops": 0, "minutes": 290}}
    assert report.threshold_hits(t, {"r": best(178.0, 250.0)}, longer) == {}
    assert report.threshold_hits(t, {"r": best(178.0, 250.0)}, same) == {"r": ["best"]}


def test_zero_percent_means_any_drop():
    h = run({}, 178.0)
    t = report.alert_targets(h, ["r"], rules(cheapest=0), "EUR", RATES)
    assert report.threshold_hits(t, {"r": best(177.99, 300.0)}, {}) == {"r": ["cheapest"]}
    assert report.threshold_hits(t, {"r": best(178.0, 300.0)}, {}) == {}
    assert "below its reference €178" in report.previous_records(h, ["r"], t, rules(cheapest=0))


def test_price_ceiling_alerts_from_the_first_check_then_only_when_cheaper():
    r = rules(cheapest_max=180)
    t = report.alert_targets({}, ["r"], r, "EUR", RATES)
    assert t["r"]["cheapest"]["max_text"] == "€180" and t["r"]["cheapest"]["ref"] is None
    hits = report.threshold_hits(t, {"r": best(175.0)}, {})
    assert hits == {"r": ["cheapest"]}
    h = run({}, 175.0, alerted=hits)
    t = report.alert_targets(h, ["r"], r, "EUR", RATES)
    assert report.threshold_hits(t, {"r": best(175.0)}, {}) == {}          # same price: already told
    assert report.threshold_hits(t, {"r": best(174.0)}, {}) == {"r": ["cheapest"]}


def test_kinds_switched_off_never_alert():
    h = run({}, 170.0, 212.0)
    t = report.alert_targets(h, ["r"], rules(fastest_on=False), "EUR", RATES)
    assert "fastest" not in t["r"]
    assert report.threshold_hits(t, {"r": best(170.0, 150.0)}, {}) == {}


def test_references_follow_a_currency_change():
    h = run({}, 170.0, 212.0)
    t = report.alert_targets(h, ["r"], rules(), "GBP", RATES)["r"]["cheapest"]
    assert t["ref"]["price"] == 136.0 and t["ref"]["text"] == "£136" and t["target"] == 129.0


def test_history_from_before_alert_kinds_is_migrated():
    old = {"routes": {"r": {"name": "Barcelona", "alert_ref": {"cheapest": 178.0, "cheapest_text": "178 €",
                                                               "best_value": 211.0, "set": "2026-10-26T16:37",
                                                               "reason": "first check"}}}}
    t = report.alert_targets(old, ["r"], rules(), "EUR", RATES)["r"]
    assert t["cheapest"]["ref"]["price"] == 178.0 and t["cheapest"]["target"] == 169.0
    assert t["best"]["ref"]["price"] == 211.0 and "fastest" not in t     # fastest starts at the next check
    h = run(old, 175.0, 230.0)
    refs = h["routes"]["r"]["alert_refs"]
    assert refs["cheapest"]["price"] == 178.0 and refs["fastest"]["price"] == 230.0 and "alert_ref" not in h["routes"]["r"]
    text = report.previous_records(h, ["r"], report.alert_targets(h, ["r"], rules(), "EUR", RATES), rules())
    assert "€169 or less" in text and "fastest:" in text


def test_filters_leave_out_long_and_self_transfer_trips():
    from airfare.results import PageResult
    from airfare.extract import Flight, Leg, ParsedPage
    long = Flight("a", 150.0, "€150", [Leg("LHR", "BCN", "2027-03-12T06:00", "2027-03-13T18:00", 2160, 2, "x")])
    selfx = Flight("b", 160.0, "€160", [Leg("LHR", "BCN", "2027-03-12T06:00", "2027-03-12T12:00", 360, 1, "y")],
                   self_transfer=True)
    fine = Flight("c", 190.0, "€190", [Leg("LHR", "BCN", "2027-03-12T16:00", "2027-03-12T18:25", 145, 0, "z")])
    parsed = ParsedPage([long, selfx, fine], {"best": ["c"]}, True, "€", 3, currency_code="EUR")
    page = {"route_id": "r", "route_name": "R", "key": "k", "depart": "2027-03-12", "url": "u"}
    data = [report.PageData(PageResult(page=page, status="ok"), parsed)]
    assert report.route_bests(data, rules())["r"]["cheapest"]["price"] == 150.0
    b = report.route_bests(data, rules(alert_max_hours=20, alert_no_self_transfer=True))["r"]
    assert b["cheapest"]["price"] == 190.0 and b["fastest"]["price"] == 190.0


def test_new_route_is_baseline():
    text = report.previous_records({}, ["r"], {}, rules())
    assert "no earlier prices" in text
