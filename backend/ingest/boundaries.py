"""CMA region, GCC wards and the pre-2011 'old city' (DataMeet Municipal_Spatial_Data, CC BY 4.0).

The 2011 expansion carved 107 of GCC's 200 wards out of the old 155-ward city; those 107
are exactly the wards in zones IV, V, VI, VIII, IX, X and XIII. We use that union as the
footprint of Census 2011 "Chennai (M Corp.)" for population control totals.
"""

import json

from shapely.geometry import MultiPolygon, shape
from shapely.validation import make_valid
from sqlalchemy import text
from sqlalchemy.orm import Session

from ingest.common import RAW, copy_rows, download, ewkt, log, register_source

BASE = "https://raw.githubusercontent.com/datameet/Municipal_Spatial_Data/master/Chennai"
OLD_CITY_ZONES = {"IV", "V", "VI", "VIII", "IX", "X", "XIII"}


def as_multi(geom) -> MultiPolygon:
    g = make_valid(geom)
    if g.geom_type == "Polygon":
        return MultiPolygon([g])
    if g.geom_type == "MultiPolygon":
        return g
    polys = [p for p in getattr(g, "geoms", []) if p.geom_type in ("Polygon", "MultiPolygon")]
    out = []
    for p in polys:
        out.extend(p.geoms if p.geom_type == "MultiPolygon" else [p])
    return MultiPolygon(out)


def load(db: Session) -> None:
    wards_f = download(f"{BASE}/Wards.geojson", RAW / "boundaries" / "Wards.geojson")
    cma_f = download(f"{BASE}/CMA.geojson", RAW / "boundaries" / "CMA.geojson")

    db.execute(text("TRUNCATE ref.boundary, ref.ward"))

    cma = json.loads(cma_f.read_text(encoding="utf-8"))["features"][0]
    copy_rows(db, "ref.boundary", ["key", "name", "area_km2", "geom"],
              [("cma", "Chennai Metropolitan Area", 0, ewkt(as_multi(shape(cma["geometry"]))))])

    rows = []
    for f in json.loads(wards_f.read_text(encoding="utf-8"))["features"]:
        p = f["properties"]
        if p["Zone_No"] == "-":  # St. Thomas Mount cantonment: not a GCC ward
            continue
        rows.append((p["Ward_No"], p["Zone_No"], p["Zone_Name"].title(),
                     p["Zone_No"] in OLD_CITY_ZONES, 0, ewkt(as_multi(shape(f["geometry"])))))
    copy_rows(db, "ref.ward", ["ward_no", "zone_no", "zone_name", "is_old_city", "area_km2", "geom"], rows)

    db.execute(text("""
        INSERT INTO ref.boundary (key, name, area_km2, geom)
        SELECT 'gcc', 'Greater Chennai Corporation (200 wards)', 0, ST_Multi(ST_Union(geom)) FROM ref.ward
        UNION ALL
        SELECT 'old_city', 'Chennai (pre-2011 corporation limits)', 0, ST_Multi(ST_Union(geom))
          FROM ref.ward WHERE is_old_city
    """))
    db.execute(text("UPDATE ref.ward SET area_km2 = ST_Area(geom::geography) / 1e6"))
    db.execute(text("UPDATE ref.boundary SET area_km2 = ST_Area(geom::geography) / 1e6"))

    # Subdivided copies make point-in-polygon tests over 380k buildings fast.
    db.execute(text("DROP TABLE IF EXISTS ref.boundary_sub"))
    db.execute(text("""
        CREATE TABLE ref.boundary_sub AS
        SELECT key, ST_Subdivide(geom, 128) AS geom FROM ref.boundary
    """))
    db.execute(text("CREATE INDEX ix_boundary_sub_geom ON ref.boundary_sub USING gist (geom)"))

    for key, area in db.execute(text("SELECT key, round(area_km2::numeric, 1) FROM ref.boundary ORDER BY key")):
        log.info("boundary %s: %s km2", key, area)
    register_source(
        db, "datameet_chennai", "DataMeet Municipal Spatial Data: Chennai wards and CMA boundary",
        url="https://github.com/datameet/Municipal_Spatial_Data/tree/master/Chennai",
        license="CC BY 4.0", row_count=len(rows),
        notes="200 GCC wards (post-2011 delimitation) and the 1,189 km2 CMA polygon.",
    )
