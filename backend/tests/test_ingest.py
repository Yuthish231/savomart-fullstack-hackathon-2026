import pytest

from ingest.categories import classify, classify_building
from ingest.load_osm import _hav, split_ways


def _way(wid, nodes, coords, highway="residential"):
    return {
        "id": wid,
        "nodes": nodes,
        "geometry": [{"lat": lat, "lon": lon} for lat, lon in coords],
        "tags": {"highway": highway},
    }


def test_split_at_shared_intersection_node():
    # Way 1 runs west-east through node 2; way 2 starts at node 2 heading north.
    w1 = _way(1, [1, 2, 3], [(13.0, 80.200), (13.0, 80.201), (13.0, 80.202)])
    w2 = _way(2, [2, 4], [(13.0, 80.201), (13.001, 80.201)])
    segs = list(split_ways([w1, w2]))
    ids = [s[0] for s in segs]
    assert ids == ["1:0", "1:1", "2:0"]
    # Way 1 is cut at node 2 and the pieces meet there, so the lane graph stays connected.
    assert segs[0][6] == 2 and segs[1][5] == 2


def test_long_way_split_into_pieces_under_limit():
    coords = [(13.0, 80.2 + i * 0.001) for i in range(8)]  # ~760 m, no intersections
    segs = list(split_ways([_way(7, list(range(100, 108)), coords)]))
    assert len(segs) >= 3
    assert all(s[4] <= 250 + 110 for s in segs)  # cut at the first vertex past 250 m
    total = sum(s[4] for s in segs)
    assert total == pytest.approx(_hav(coords[0], coords[-1]), rel=1e-3)
    # Consecutive pieces share their cut point.
    for a, b in zip(segs, segs[1:]):
        assert a[6] == b[5]


@pytest.mark.parametrize(
    "tags,category,tier",
    [
        ({"shop": "supermarket", "name": "Reliance Smart"}, "grocery", 3),
        ({"shop": "convenience", "brand": "More"}, "grocery", 3),
        ({"shop": "supermarket", "name": "Sri Balaji Supermarket"}, "grocery", 2),
        ({"shop": "supermarket", "name": "Niligiris"}, "grocery", 3),
        ({"shop": "supermarket", "name": "Nilgris Super Market"}, "grocery", 3),
        ({"shop": "supermarket", "name": "Grace Super Market"}, "grocery", 3),
        ({"shop": "department_store", "name": "Marks & Spencer"}, "retail", 0),
        ({"shop": "convenience", "name": "Murugan Stores"}, "grocery", 1),
        ({"shop": "supermarket", "name": "Savomart"}, "own_store", 0),
        ({"shop": "clothes"}, "retail", 0),
        ({"amenity": "school"}, "education", 0),
        ({"railway": "station", "name": "Guindy"}, "transit", 0),
    ],
)
def test_poi_classification(tags, category, tier):
    c = classify(tags)
    assert c is not None and c.category == category and c.competitor_tier == tier


def test_building_weights():
    assert classify_building({"building": "apartments"})[1:] == ("residential", 4, 4.0)
    # Floors are informational only: tagged too unevenly in Chennai to weight residents.
    assert classify_building({"building": "house", "building:levels": "2"})[3] == 1.0
    assert classify_building({"building": "commercial"})[3] == 0.0
    kind, use, levels, w = classify_building({"building": "yes"})
    assert use == "unknown" and 0 < w < 1


def test_density_ceiling_preserves_total_and_caps():
    from ingest.population import ceiling_factors

    pops = {"a": 1000.0, "b": 100.0, "c": 100.0, "d": 100.0}
    areas = dict.fromkeys(pops, 0.01)  # "a" is 100k/km2; cap 50k/km2 -> at most 500 per cell
    f = ceiling_factors(pops, areas, cap=50_000)
    new = {k: pops[k] * f[k] for k in pops}
    assert new["a"] == pytest.approx(500)
    assert sum(new.values()) == pytest.approx(sum(pops.values()))  # zone total preserved
    assert all(v <= 500 + 1e-6 for v in new.values())
    assert new["b"] == pytest.approx(new["c"])  # excess spread proportionally
