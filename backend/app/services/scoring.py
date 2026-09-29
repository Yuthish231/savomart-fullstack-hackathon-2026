"""Area Fitness scoring model (v1). Pure functions: deterministic, explainable, testable.

Every sub-score is 0-100. Density metrics are converted to *Chennai percentiles*: a score of
82 means "denser than 82% of Chennai's inhabited ~2 km2 neighbourhoods". The Savomart
network fit uses a distance band instead, because both too-close (cannibalisation) and
too-far (supply chain) are bad.
"""

from bisect import bisect_left
from dataclasses import asdict, dataclass

SCORING_VERSION = "v1"


@dataclass(frozen=True)
class SubScoreSpec:
    key: str
    label: str
    weight: float
    metric: str | None  # percentile metric in ref.metric_stats, None for banded scores
    higher_is_better: bool
    unit: str
    explain: str


SPECS: list[SubScoreSpec] = [
    SubScoreSpec("demand", "Demand", 0.25, "pop_density", True, "people/km²",
                 "Estimated residents per km² (Census 2011 baseline, spread over OSM buildings)"),
    SubScoreSpec("residential", "Residential fabric", 0.15, "res_density", True, "homes/km²",
                 "Residential buildings per km² from OpenStreetMap"),
    SubScoreSpec("footfall", "Footfall generators", 0.15, "footfall_density", True, "points/km²",
                 "Weighted schools, hospitals, offices, transit and markets per km²"),
    SubScoreSpec("competition", "Competition", 0.20, "comp_per_10k", False, "per 10k people",
                 "Grocery competitors per 10,000 residents (chains x3, supermarkets x2, kiranas x1), "
                 "including a ~500 m ring around the area"),
    SubScoreSpec("network", "Savomart network fit", 0.15, None, True, "km",
                 "Distance to the nearest Savomart store: under 2 km risks cannibalisation, "
                 "3-8 km is ideal, very far strains the supply chain"),
    SubScoreSpec("access", "Access", 0.10, "access_density", True, "road km/km²",
                 "Road length per km² (arterials count double lanes)"),
]
SPEC_BY_KEY = {s.key: s for s in SPECS}
assert abs(sum(s.weight for s in SPECS) - 1.0) < 1e-9

# (distance km, score) knots; linear in between.
NETWORK_BAND = [(0.0, 5), (1.0, 10), (2.0, 45), (3.0, 85), (4.0, 100), (8.0, 100),
                (12.0, 80), (20.0, 60), (40.0, 45)]


def percentile(value: float, breakpoints: list[float]) -> float:
    """Position of value within p0..p100 breakpoints, linearly interpolated, 0-100."""
    if value <= breakpoints[0]:
        return 0.0
    if value >= breakpoints[-1]:
        return 100.0
    i = bisect_left(breakpoints, value)
    lo, hi = breakpoints[i - 1], breakpoints[i]
    # Flat runs (many identical values, e.g. zero competitors) take the middle of the run.
    if hi == lo:
        j = i
        while j < len(breakpoints) and breakpoints[j] == hi:
            j += 1
        return float((i - 1 + j - 1) / 2)
    return (i - 1) + (value - lo) / (hi - lo)


def network_score(distance_km: float) -> float:
    for (d0, s0), (d1, s1) in zip(NETWORK_BAND, NETWORK_BAND[1:]):
        if distance_km <= d1:
            return s0 + (s1 - s0) * (distance_km - d0) / (d1 - d0)
    return float(NETWORK_BAND[-1][1])


def grade(score: float) -> str:
    return "A" if score >= 75 else "B" if score >= 60 else "C" if score >= 45 else "D"


@dataclass
class SubScore:
    key: str
    label: str
    weight: float
    raw_value: float
    unit: str
    percentile: float | None
    score: float
    contribution: float
    explain: str


def score_metrics(metrics: dict[str, float], stats: dict[str, list[float]]) -> tuple[float, list[SubScore]]:
    """metrics: pop_density, res_density, footfall_density, comp_per_10k, access_density,
    nearest_store_km. stats: metric -> p0..p100 breakpoints."""
    subs: list[SubScore] = []
    for spec in SPECS:
        if spec.metric is None:
            raw = metrics["nearest_store_km"]
            pct = None
            s = network_score(raw)
        else:
            raw = metrics[spec.metric]
            pct = percentile(raw, stats[spec.metric])
            s = pct if spec.higher_is_better else 100.0 - pct
        subs.append(SubScore(spec.key, spec.label, spec.weight, round(raw, 2), spec.unit,
                             None if pct is None else round(pct, 1), round(s, 1),
                             round(s * spec.weight, 2), spec.explain))
    total = round(sum(x.contribution for x in subs), 1)
    return total, subs


def subs_as_dicts(subs: list[SubScore]) -> list[dict]:
    return [asdict(s) for s in subs]
