"""Load cached Overpass tiles into ref.osm_poi, ref.osm_building and ref.lane_segment.

Cleaning:
- Tiles overlap at edges: de-duplicate by (type, id).
- POIs mapped both as a node and as a building outline: keep one per (category, name) within 30 m.
- Everything is clipped to the CMA polygon.
- Roads are split at every intersection (a node shared by two or more ways) and then into
  pieces of at most 250 m, giving walkable survey units with stable ids "<way>:<seq>".
"""

import json
import math
from collections import Counter

import h3
from sqlalchemy import text
from sqlalchemy.orm import Session

from ingest.categories import MAJOR_ROADS, SURVEYABLE, classify, classify_building
from ingest.common import RAW, copy_rows, log, register_source

OSM_DIR = RAW / "osm"
H3_RES = 9
MAX_LANE_M = 250.0


def _elements(kind: str):
    seen: set[tuple[str, int]] = set()
    for path in sorted(OSM_DIR.glob(f"{kind}_*.json")):
        for el in json.loads(path.read_text(encoding="utf-8"))["elements"]:
            key = (el["type"], el["id"])
            if key in seen:
                continue
            seen.add(key)
            yield el


def _point(el) -> tuple[float, float] | None:
    if "lat" in el:
        return el["lat"], el["lon"]
    c = el.get("center")
    return (c["lat"], c["lon"]) if c else None


def _hav(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(h))


def _clip(db: Session, table: str) -> int:
    return db.execute(text(f"""
        DELETE FROM {table} t
         WHERE NOT EXISTS (SELECT 1 FROM ref.boundary_sub b
                            WHERE b.key = 'cma' AND ST_Intersects(b.geom, t.geom))
    """)).rowcount


def load_pois(db: Session) -> int:
    rows = []
    for el in _elements("poi"):
        tags = el.get("tags", {})
        c = classify(tags)
        pt = _point(el)
        if c is None or pt is None:
            continue
        rows.append((
            el["type"][0], el["id"], (tags.get("name") or tags.get("name:en") or "")[:200] or None,
            (tags.get("brand") or "")[:120] or None, c.category, c.subcategory[:40],
            c.footfall_weight, c.competitor_tier, h3.latlng_to_cell(pt[0], pt[1], H3_RES),
            f"SRID=4326;POINT({pt[1]} {pt[0]})",
        ))
    db.execute(text("TRUNCATE ref.osm_poi RESTART IDENTITY"))
    copy_rows(db, "ref.osm_poi", ["osm_type", "osm_id", "name", "brand", "category", "subcategory",
                                  "footfall_weight", "competitor_tier", "h3_r9", "geom"], rows)
    clipped = _clip(db, "ref.osm_poi")
    dupes = db.execute(text("""
        DELETE FROM ref.osm_poi a USING ref.osm_poi b
         WHERE a.id > b.id AND a.name IS NOT NULL AND a.category = b.category
           AND lower(a.name) = lower(b.name)
           AND ST_DWithin(a.geom::geography, b.geom::geography, 30)
    """)).rowcount
    n = db.scalar(text("SELECT count(*) FROM ref.osm_poi"))
    log.info("POIs: %d loaded (%d outside CMA, %d node/way duplicates removed)", n, clipped, dupes)
    for cat, cnt in db.execute(text("SELECT category, count(*) FROM ref.osm_poi GROUP BY 1 ORDER BY 2 DESC")):
        log.info("  %-10s %d", cat, cnt)
    return n


def load_buildings(db: Session) -> int:
    rows = []
    for el in _elements("building"):
        pt = _point(el)
        if pt is None:
            continue
        kind, use, levels, weight = classify_building(el.get("tags", {}))
        rows.append((el["id"], kind, use, levels, weight, h3.latlng_to_cell(pt[0], pt[1], H3_RES),
                     f"SRID=4326;POINT({pt[1]} {pt[0]})"))
    db.execute(text("TRUNCATE ref.osm_building"))
    copy_rows(db, "ref.osm_building",
              ["osm_id", "kind", "use_class", "levels", "res_weight", "h3_r9", "geom"], rows)
    clipped = _clip(db, "ref.osm_building")
    n = db.scalar(text("SELECT count(*) FROM ref.osm_building"))
    mix = dict(db.execute(text("SELECT use_class, count(*) FROM ref.osm_building GROUP BY 1")).all())
    log.info("buildings: %d loaded (%d outside CMA); use mix %s", n, clipped, mix)
    return n


def split_ways(ways: list[dict]):
    """Yield lane segments: (id, way_id, highway, name, length_m, start_node, end_node, coords)."""
    node_uses = Counter()
    for w in ways:
        nodes = w["nodes"]
        node_uses.update(nodes)
        node_uses.update([nodes[0], nodes[-1]])  # endpoints always split

    for w in ways:
        nodes, geom = w["nodes"], w["geometry"]
        if len(nodes) != len(geom) or len(nodes) < 2:
            continue
        tags = w.get("tags", {})
        hw, name = tags.get("highway", "road"), (tags.get("name") or tags.get("name:en") or None)
        pieces, start = [], 0
        for i in range(1, len(nodes)):
            if node_uses[nodes[i]] >= 2 or i == len(nodes) - 1:
                pieces.append((start, i))
                start = i
        seq = 0
        for a, b in pieces:
            pts = [(g["lat"], g["lon"]) for g in geom[a : b + 1]]
            ids = nodes[a : b + 1]
            # Further cut pieces longer than MAX_LANE_M at vertices (synthetic node ids).
            chunk_pts, chunk_start_id, acc = [pts[0]], ids[0], 0.0
            for k in range(1, len(pts)):
                acc += _hav(pts[k - 1], pts[k])
                chunk_pts.append(pts[k])
                last = k == len(pts) - 1
                if acc >= MAX_LANE_M or last:
                    end_id = ids[k] if last else -(w["id"] * 1000 + seq + 1)
                    yield (f"{w['id']}:{seq}", w["id"], hw, name, acc, chunk_start_id, end_id, chunk_pts)
                    seq += 1
                    chunk_pts, chunk_start_id, acc = [pts[k]], end_id, 0.0


def load_lanes(db: Session) -> int:
    ways = [el for el in _elements("road") if el["type"] == "way" and "geometry" in el]
    rows = []
    for sid, wid, hw, name, length, s_node, e_node, pts in split_ways(ways):
        if length < 5:
            continue
        mid = pts[len(pts) // 2]
        wkt = "LINESTRING(" + ", ".join(f"{lon} {lat}" for lat, lon in pts) + ")"
        rows.append((sid, wid, hw[:30], (name or "")[:200] or None, round(length, 1),
                     hw in SURVEYABLE, s_node, e_node, h3.latlng_to_cell(mid[0], mid[1], H3_RES),
                     f"SRID=4326;{wkt}"))
    db.execute(text("TRUNCATE ref.lane_segment"))
    copy_rows(db, "ref.lane_segment", ["id", "osm_id", "highway", "name", "length_m", "is_surveyable",
                                       "start_node", "end_node", "h3_r9", "geom"], rows)
    clipped = _clip(db, "ref.lane_segment")
    n, km, surv = db.execute(text("""
        SELECT count(*), sum(length_m) / 1000, count(*) FILTER (WHERE is_surveyable)
          FROM ref.lane_segment
    """)).one()
    log.info("lane segments: %d (%.0f km road network, %d surveyable; %d outside CMA dropped)",
             n, km, surv, clipped)
    return n


def load(db: Session) -> None:
    snap = json.loads((OSM_DIR / "_snapshot.json").read_text(encoding="utf-8"))["timestamp_osm_base"]
    n_poi = load_pois(db)
    n_bldg = load_buildings(db)
    n_lane = load_lanes(db)
    as_of = snap[:10]
    common = dict(url="https://www.openstreetmap.org", license="ODbL 1.0 (c) OpenStreetMap contributors",
                  as_of=as_of)
    register_source(db, "osm_poi", "OpenStreetMap points of interest (via Overpass)", row_count=n_poi,
                    notes=f"OSM base {snap}. Shops, education, health, transit, offices, worship, parks.",
                    **common)
    register_source(db, "osm_building", "OpenStreetMap buildings (via Overpass)", row_count=n_bldg,
                    notes=f"OSM base {snap}. Centroids with building type and levels.", **common)
    register_source(db, "osm_road", "OpenStreetMap road network (via Overpass)", row_count=n_lane,
                    notes=f"OSM base {snap}. Split into lane segments at intersections, max 250 m.",
                    **common)
