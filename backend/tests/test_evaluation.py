import pytest

from app.services.evaluation import recommend, site_checks, site_score

BAND = {"min": 60.0, "max": 100.0}
GOOD = dict(carpet_sqft=2500, floor="ground", frontage_ft=25, delivery_access="truck",
            visibility="main_road", parking_2w=12, parking_4w=2, rent_monthly=200_000)


def by_key(checks):
    return {c.key: c for c in checks}


def test_good_site_scores_high():
    checks = site_checks(GOOD, BAND)
    assert site_score(checks) == pytest.approx(100)
    assert all(c.status == "good" for c in checks)


def test_blockers_detected():
    c = by_key(site_checks({**GOOD, "carpet_sqft": 600, "delivery_access": "none"}, BAND))
    assert c["size"].status == "blocker" and c["access"].status == "blocker"


def test_missing_rent_is_unknown_and_neutral():
    checks = site_checks({**GOOD, "rent_monthly": None}, BAND)
    rent = by_key(checks)["rent"]
    assert rent.status == "unknown" and rent.score is None
    assert 90 < site_score(checks) < 100  # neutral 50 on a 10% weight


@pytest.mark.parametrize("rent,status", [(50_000, "ok"), (100_000, "good"), (200_000, "good"), (300_000, "ok"), (500_000, "poor")])
def test_rent_against_band(rent, status):
    # 2,500 sq ft: 20 (suspiciously low), 40, 80, 120, 200 per sq ft against a 60-100 band
    assert by_key(site_checks({**GOOD, "rent_monthly": rent}, BAND))["rent"].status == status


def test_upper_floor_and_narrow_front_are_poor():
    c = by_key(site_checks({**GOOD, "floor": "first", "frontage_ft": 10}, BAND))
    assert c["floor"].status == "poor" and c["frontage"].status == "poor"


def test_recommendation_rules():
    assert recommend(90, ["size"], 0) == "reject"
    assert recommend(70, [], 0) == "proceed"
    assert recommend(70, [], 1) == "review"
    assert recommend(50, [], 0) == "review"
