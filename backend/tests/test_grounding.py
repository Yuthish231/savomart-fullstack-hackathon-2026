from app.llm.grounding import check

FACTS = {
    "pop": {"label": "Residents", "value": 48213, "unit": "people"},
    "pop_density": {"label": "Density", "value": 18234.6, "unit": "people/km²"},
    "store_km": {"label": "Nearest Savomart", "value": 4.37, "unit": "km"},
    "comp_share": {"label": "Organised share", "value": 0.42, "unit": "share"},
    "grade": {"label": "Grade", "value": "B", "unit": ""},
}
HOTSPOTS = {"h1", "h2"}


def out(**kw):
    base = {"headline": "", "summary": "", "reasons": [], "scout_first": [], "risks": [], "caveats": []}
    return {**base, **kw}


def test_accepts_rounded_and_reformatted_numbers():
    o = out(
        summary="About 48,213 residents (48.2k, roughly 0.48 lakh) at 18,235 per km²; "
        "the nearest store is 4.4 km away and organised chains hold 42% of competition. "
        "Census 2011 baseline.",
        reasons=[{"text": "Dense: 18.2k people/km²", "fact_ids": ["pop_density"]}],
        scout_first=[{"hotspot_id": "h1", "text": "Start with hotspot 1"}],
    )
    r = check(o, FACTS, HOTSPOTS)
    assert r.ok, r.violations


def test_rejects_invented_numbers():
    o = out(summary="Around 75,000 residents and 12 competing supermarkets.")
    r = check(o, FACTS, HOTSPOTS)
    assert not r.ok
    assert any("75,000" in v for v in r.violations)
    assert any("12" in v for v in r.violations)


def test_rejects_unknown_fact_and_hotspot_ids():
    o = out(
        reasons=[{"text": "Great area", "fact_ids": ["made_up"]}],
        scout_first=[{"hotspot_id": "h9", "text": "Go here"}],
    )
    r = check(o, FACTS, HOTSPOTS)
    assert not r.ok and len(r.violations) == 2


def test_small_counts_and_ids_are_not_data_claims():
    o = out(summary="Three strengths and 2 risks; see the top 3 hotspots.",
            scout_first=[{"hotspot_id": "h2", "text": "Second pick"}])
    assert check(o, FACTS, HOTSPOTS).ok
