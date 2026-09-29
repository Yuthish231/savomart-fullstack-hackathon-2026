import pytest

from app.services.scoring import SPECS, grade, network_score, percentile, score_metrics

LINEAR = [float(i) for i in range(101)]  # p_k == k


def test_weights_sum_to_one():
    assert sum(s.weight for s in SPECS) == pytest.approx(1.0)


@pytest.mark.parametrize("value,expected", [(-5, 0), (0, 0), (37.5, 37.5), (100, 100), (250, 100)])
def test_percentile_interpolates(value, expected):
    assert percentile(value, LINEAR) == pytest.approx(expected)


def test_percentile_ties_take_mid_rank():
    # 40% of neighbourhoods have zero mapped competitors: zero is p20, not p0 (or p40).
    bps = [0.0] * 41 + [float(i) for i in range(1, 61)]
    assert percentile(0.0, bps) == 20.0
    assert percentile(-1.0, bps) == 0.0
    assert 40 <= percentile(0.5, bps) <= 41


@pytest.mark.parametrize(
    "km,lo,hi",
    [(0.3, 0, 10), (1.5, 20, 35), (3.0, 85, 85), (5.0, 100, 100), (15, 60, 80), (60, 45, 45)],
)
def test_network_band(km, lo, hi):
    assert lo <= network_score(km) <= hi


def test_network_band_penalises_cannibalisation_over_distance():
    assert network_score(0.5) < network_score(25) < network_score(5)


def _metrics(**kw):
    base = dict(pop_density=50, res_density=50, footfall_density=50, comp_per_10k=50,
                access_density=50, nearest_store_km=5.0)
    return {**base, **kw}


def test_score_is_weighted_sum_and_explained():
    stats = {s.metric: LINEAR for s in SPECS if s.metric}
    total, subs = score_metrics(_metrics(), stats)
    assert total == pytest.approx(sum(s.contribution for s in subs), abs=0.1)
    assert {s.key for s in subs} == {s.key for s in SPECS}
    comp = next(s for s in subs if s.key == "competition")
    assert comp.percentile == 50 and comp.score == 50  # inverted metric


def test_more_competition_lowers_score():
    stats = {s.metric: LINEAR for s in SPECS if s.metric}
    low, _ = score_metrics(_metrics(comp_per_10k=10), stats)
    high, _ = score_metrics(_metrics(comp_per_10k=90), stats)
    assert low > high


@pytest.mark.parametrize("score,g", [(80, "A"), (75, "A"), (60, "B"), (50, "C"), (10, "D")])
def test_grade(score, g):
    assert grade(score) == g
