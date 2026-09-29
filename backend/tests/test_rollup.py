import pytest

from app.services.rollup import ASSUMED_HH_SIZE, households, summarise


def lane(length, status="submitted", lane_status="done", **data):
    return {"length_m": length, "survey_status": status, "lane_status": lane_status, "data": data,
            "is_seed": False, "captured_at": "2026-09-29T10:00:00"}


def test_households_from_bucket_or_exact():
    assert households({"dwellings_bucket": "26-50"}) == 38
    assert households({"dwellings_exact": 12, "dwellings_bucket": "100+"}) == 12
    assert households({}) == 0


def test_extrapolates_unsurveyed_length_but_not_skipped():
    rows = [
        lane(100, dwellings_bucket="11-25", kiranas=1, condition="maintained", vehicles="mixed"),  # 18 hh
        lane(100, dwellings_bucket="26-50", kiranas=0, condition="new", vehicles="many_cars"),     # 38 hh
        lane(100, status="skipped", lane_status="skipped", skip_reason="gated"),
        lane(200, status=None, lane_status="todo"),  # not surveyed yet
    ]
    s = summarise(rows, area_km2=0.5, modelled_pop=500, osm_competitors=0)
    # 56 households over 200 m observed; residential length = 500 - 100 skipped = 400 m -> 112 hh
    assert s["households_observed"] == 56
    assert s["households_est"] == 112
    assert s["population_est"] == pytest.approx(112 * ASSUMED_HH_SIZE)
    assert s["coverage"] == pytest.approx(0.6)
    assert s["survey_vs_model"] == pytest.approx(112 * ASSUMED_HH_SIZE / 500 - 1, abs=1e-3)
    assert s["kiranas_observed"] == 1 and s["lanes_skipped"] == 1
    assert s["skip_reasons"] == {"gated": 1}


def test_affluence_index_bounds():
    rich = summarise([lane(100, dwellings_bucket="0-10", condition="new", vehicles="many_cars")], 1, 100, 0)
    poor = summarise([lane(100, dwellings_bucket="0-10", condition="dilapidated", vehicles="mostly_2w")], 1, 100, 0)
    assert rich["affluence_index"] == 100 and poor["affluence_index"] == 0


def test_no_observations_is_safe():
    s = summarise([lane(100, status=None, lane_status="todo")], 1, 100, 3)
    assert s["households_est"] == 0 and s["comp_per_10k"] is None and s["affluence_index"] is None
