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

from ingest.categories import SURVEYABLE, UNKNOWN_RES_SHARE, classify, classify_building
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


# Residential share for generic ("building=yes") structures inside non-residential land.
# Commercial/retail keeps some residents: shop-houses with homes above are common in Chennai.
LANDUSE_RES_SHARE = {
    "industrial": 0.0, "port": 0.0, "railway": 0.0, "military": 0.0, "aerodrome": 0.0,
    "depot": 0.0, "garages": 0.0, "cemetery": 0.0,
    "institutional": 0.1, "education": 0.1, "religious": 0.1, "university": 0.1, "college": 0.1,
    "school": 0.1, "hospital": 0.1, "marketplace": 0.1,
    "commercial": 0.25, "retail": 0.25,
}


def _landuse_kind(tags: dict) -> str | None:
    if tags.get("aeroway") == "aerodrome":
        return "aerodrome"
    for key in ("landuse", "amenity"):
        if tags.get(key) in LANDUSE_RES_SHARE:
            return tags[key]
    if "industrial" in tags:
        return "industrial"
    return None


def _polygons(el) -> list:
    from shapely.geometry import LineString, Polygon
    from shapely.ops import polygonize

    if el["type"] == "way":
        pts = [(g["lon"], g["lat"]) for g in el.get("geometry", [])]
        if len(pts) >= 4 and pts[0] == pts[-1]:
            poly = Polygon(pts)
            return [poly] if poly.is_valid and poly.area > 0 else [poly.buffer(0)]
        return []
    lines = [LineString([(g["lon"], g["lat"]) for g in m["geometry"]])
             for m in el.get("members", []) if m.get("role") == "outer" and len(m.get("geometry", [])) >= 2]
    return [p for p in polygonize(lines) if p.area > 0]


def load_landuse(db: Session) -> int:
    """Non-residential land polygons, then down-weight generic buildings that sit inside them."""
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS ref.landuse_nonres (
            id bigserial PRIMARY KEY, osm_type char(1), osm_id bigint, kind text,
            res_share double precision, geom geometry(Polygon, 4326))
    """))
    db.execute(text("CREATE INDEX IF NOT EXISTS ix_landuse_nonres_geom ON ref.landuse_nonres USING gist (geom)"))
    db.execute(text("TRUNCATE ref.landuse_nonres RESTART IDENTITY"))
    rows = []
    for el in _elements("landuse"):
        kind = _landuse_kind(el.get("tags", {}))
        if kind is None:
            continue
        for poly in _polygons(el):
            for p in getattr(poly, "geoms", [poly]):
                if p.geom_type == "Polygon" and not p.is_empty:
                    rows.append((el["type"][0], el["id"], kind, LANDUSE_RES_SHARE[kind], f"SRID=4326;{p.wkt}"))
    copy_rows(db, "ref.landuse_nonres", ["osm_type", "osm_id", "kind", "res_share", "geom"], rows)
    changed = db.execute(text("""
        UPDATE ref.osm_building b
           SET res_weight = b.res_weight * l.share / :unknown_share, use_class = 'non_res_land'
          FROM (SELECT b2.osm_id, min(l.res_share) AS share
                  FROM ref.osm_building b2
                  JOIN ref.landuse_nonres l ON ST_Intersects(l.geom, b2.geom)
                 WHERE b2.use_class = 'unknown'
                 GROUP BY b2.osm_id) l
         WHERE b.osm_id = l.osm_id
    """), {"unknown_share": UNKNOWN_RES_SHARE}).rowcount
    km2 = db.scalar(text("SELECT round((sum(ST_Area(geom::geography)) / 1e6)::numeric, 1) FROM ref.landuse_nonres"))
    log.info("non-residential land: %d polygons, %s km2; %d generic buildings down-weighted", len(rows), km2, changed)
    return len(rows)


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
    # OSM snapshot time, taken from the tiles themselves (oldest tile wins).
    snap = min(json.loads(p.read_text(encoding="utf-8"))["osm3s"]["timestamp_osm_base"]
               for p in OSM_DIR.glob("poi_*.json"))
    n_poi = load_pois(db)
    n_bldg = load_buildings(db)
    n_land = load_landuse(db)
    n_lane = load_lanes(db)
    as_of = snap[:10]
    common = dict(url="https://www.openstreetmap.org", license="ODbL 1.0 (c) OpenStreetMap contributors",
                  as_of=as_of)
    register_source(db, "osm_poi", "OpenStreetMap points of interest (via Overpass)", row_count=n_poi,
                    notes=f"OSM base {snap}. Shops, education, health, transit, offices, worship, parks.",
                    **common)
    register_source(db, "osm_building", "OpenStreetMap buildings (via Overpass)", row_count=n_bldg,
                    notes=f"OSM base {snap}. Centroids with building type and levels.", **common)
    register_source(db, "osm_landuse", "OpenStreetMap non-residential land use (via Overpass)",
                    row_count=n_land,
                    notes=f"OSM base {snap}. Industrial, port, rail, airport, campuses, commercial zones: "
                          "generic buildings inside get a reduced residential share.", **common)
    register_source(db, "osm_road", "OpenStreetMap road network (via Overpass)", row_count=n_lane,
                    notes=f"OSM base {snap}. Split into lane segments at intersections, max 250 m.",
                    **common)
