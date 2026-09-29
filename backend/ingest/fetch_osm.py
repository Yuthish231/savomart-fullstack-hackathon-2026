"""Fetch OSM features for the Chennai Metropolitan Area via Overpass (tiled, cached).

Usage (from backend/):  python -m ingest.fetch_osm
Raw responses land in data/raw/osm/ and are reused on later runs.
"""

import json

from ingest.common import CMA_BBOX, RAW, log, overpass, setup_logging, tiles

OSM_DIR = RAW / "osm"

POI_QUERY = """
[out:json][timeout:300];
(
  nwr["shop"]({bbox});
  nwr["amenity"~"^(school|college|university|kindergarten|hospital|clinic|doctors|pharmacy|bus_station|place_of_worship|marketplace|bank|restaurant|cafe|fast_food|cinema)$"]({bbox});
  nwr["office"]({bbox});
  node["highway"="bus_stop"]({bbox});
  nwr["railway"~"^(station|halt)$"]({bbox});
  nwr["public_transport"="station"]({bbox});
  nwr["leisure"="park"]({bbox});
);
out center tags;
"""

# Road network used for access scores and survey lanes. `out geom` keeps node ids too,
# which we need to split ways at intersections.
ROAD_QUERY = """
[out:json][timeout:300];
way["highway"~"^(motorway|trunk|primary|secondary|tertiary|motorway_link|trunk_link|primary_link|secondary_link|tertiary_link|unclassified|residential|living_street|service|pedestrian|road)$"]
   ["service"!~"^(parking_aisle|driveway|drive-through|emergency_access)$"]
   ["access"!~"^(private|no)$"]({bbox});
out geom;
"""

BUILDING_QUERY = """
[out:json][timeout:300];
way["building"]({bbox});
out center tags;
"""

JOBS = [
    ("poi", POI_QUERY, 2, 2),
    ("road", ROAD_QUERY, 3, 3),
    ("building", BUILDING_QUERY, 4, 4),
]


def bbox_str(b):
    return ",".join(f"{v:.5f}" for v in b)


def fetch_tile(query: str, path, bbox, depth: int = 0) -> dict:
    """Fetch one tile; if the servers keep timing out on it, split it into quarters."""
    if path.exists():
        return overpass("", path)  # cached
    try:
        return overpass(query.format(bbox=bbox_str(bbox)), path, attempts=3 if depth < 2 else 6)
    except RuntimeError:
        if depth >= 2:
            raise
        log.warning("tile %s too heavy; splitting into quarters", path.name)
        elements, seen, meta = [], set(), {}
        for i, j, sub in tiles(bbox, 2, 2):
            part = fetch_tile(query, path.with_name(f"{path.stem}.q{i}{j}.json.part"), sub, depth + 1)
            meta = {k: v for k, v in part.items() if k != "elements"}
            for el in part["elements"]:
                if (el["type"], el["id"]) not in seen:
                    seen.add((el["type"], el["id"]))
                    elements.append(el)
        data = {**meta, "elements": elements}
        path.write_text(json.dumps(data), encoding="utf-8")
        return data


def main() -> None:
    setup_logging()
    for kind, query, rows, cols in JOBS:
        total = 0
        for i, j, b in tiles(CMA_BBOX, rows, cols):
            path = OSM_DIR / f"{kind}_{i}_{j}.json"
            fresh = not path.exists()
            data = fetch_tile(query, path, b)
            n = len(data.get("elements", []))
            total += n
            log.info("%s tile %d,%d: %d elements%s", kind, i, j, n, "" if fresh else " (cached)")
        log.info("%s total: %d", kind, total)
    # Record the OSM snapshot timestamp for provenance.
    any_file = next(OSM_DIR.glob("poi_*.json"))
    ts = json.loads(any_file.read_text(encoding="utf-8"))["osm3s"]["timestamp_osm_base"]
    (OSM_DIR / "_snapshot.json").write_text(json.dumps({"timestamp_osm_base": ts}), encoding="utf-8")
    log.info("done; OSM base timestamp %s", ts)


if __name__ == "__main__":
    main()
