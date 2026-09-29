"""Precompute H3 res-9 features for every cell in the CMA and city-wide percentile tables.

Per cell: population, buildings, footfall points, grocery competition by tier, road length,
nearest Savomart store. Per cell neighbourhood (the cell plus 2 rings, ~2 km2, about the
size of a locality): densities used for percentile scoring and the opportunity map.
"""

import json

import h3
import numpy as np
from shapely import wkb
from shapely.geometry import mapping
from sqlalchemy import text
from sqlalchemy.orm import Session

from ingest.categories import MAJOR_ROADS
from ingest.common import copy_rows, log

RES = 9
NBHD_K = 2
# A neighbourhood counts as "inhabited" (and enters the city distribution) above this density.
INHABITED_MIN_DENSITY = 500.0

# Metrics whose city distributions we store. Keep in sync with app.services.scoring.
NBHD_METRICS = ["pop_density", "res_density", "footfall_density", "comp_per_10k", "access_density"]


def _cell_poly_wkt(cell: str) -> str:
    ring = [(lng, lat) for lat, lng in h3.cell_to_boundary(cell)]
    ring.append(ring[0])
    return "POLYGON((" + ", ".join(f"{x} {y}" for x, y in ring) + "))"


def build_cells(db: Session) -> int:
    cma = wkb.loads(bytes(db.scalar(text("SELECT ST_AsBinary(geom) FROM ref.boundary WHERE key='cma'"))))
    cells = h3.geo_to_cells(mapping(cma), RES)
    db.execute(text("TRUNCATE ref.h3_cell"))
    rows = ((c, h3.cell_to_parent(c, 8), h3.cell_area(c, "km^2"), f"SRID=4326;{_cell_poly_wkt(c)}")
            for c in cells)
    return copy_rows(db, "ref.h3_cell", ["h3", "h3_r8", "area_km2", "geom"], rows)


def aggregate(db: Session) -> None:
    db.execute(text("""
        UPDATE ref.h3_cell c SET pop_est = s.pop, bldg_count = s.n,
               res_bldg_count = s.n_res
          FROM (SELECT h3_r9, sum(pop_est) AS pop, count(*) AS n,
                       count(*) FILTER (WHERE use_class = 'residential'
                                        OR (use_class = 'unknown' AND res_weight > 0)) AS n_res
                  FROM ref.osm_building GROUP BY h3_r9) s
         WHERE c.h3 = s.h3_r9
    """))
    db.execute(text("""
        UPDATE ref.h3_cell c SET
               footfall_pts = s.footfall,
               comp_convenience = s.c1, comp_supermarket = s.c2, comp_organised = s.c3,
               retail_count = s.retail, poi_counts = s.counts
          FROM (SELECT h3_r9,
                       sum(footfall_weight) AS footfall,
                       count(*) FILTER (WHERE competitor_tier = 1) AS c1,
                       count(*) FILTER (WHERE competitor_tier = 2) AS c2,
                       count(*) FILTER (WHERE competitor_tier = 3) AS c3,
                       count(*) FILTER (WHERE category = 'retail') AS retail,
                       jsonb_object_agg(category, n) AS counts
                  FROM (SELECT h3_r9, category, competitor_tier, footfall_weight,
                               count(*) OVER (PARTITION BY h3_r9, category) AS n
                          FROM ref.osm_poi) p
                 GROUP BY h3_r9) s
         WHERE c.h3 = s.h3_r9
    """))
    db.execute(text("""
        UPDATE ref.h3_cell c SET road_major_m = s.major, road_minor_m = s.minor
          FROM (SELECT h3_r9,
                       sum(length_m) FILTER (WHERE highway = ANY(:major)) AS major,
                       sum(length_m) FILTER (WHERE highway <> ALL(:major)) AS minor
                  FROM ref.lane_segment GROUP BY h3_r9) s
         WHERE c.h3 = s.h3_r9
    """), {"major": sorted(MAJOR_ROADS)})
    db.execute(text("UPDATE ref.h3_cell SET road_major_m = coalesce(road_major_m, 0), "
                    "road_minor_m = coalesce(road_minor_m, 0)"))
    db.execute(text("""
        UPDATE ref.h3_cell c SET ward_no = w.ward_no, in_gcc = true
          FROM ref.ward w WHERE ST_Contains(w.geom, ST_Centroid(c.geom))
    """))
    db.execute(text("""
        UPDATE ref.h3_cell c SET pincode = p.pincode
          FROM ref.pincode p WHERE ST_Contains(p.geom, ST_Centroid(c.geom))
    """))
    db.execute(text("""
        UPDATE ref.h3_cell c SET nearest_store_m = s.dist, nearest_store_code = s.store_code
          FROM ref.h3_cell c2
          CROSS JOIN LATERAL (
                SELECT st.store_code,
                       ST_Distance(st.geom::geography, ST_Centroid(c2.geom)::geography) AS dist
                  FROM ref.savomart_store st
                 ORDER BY st.geom <-> ST_Centroid(c2.geom) LIMIT 1) s
         WHERE c.h3 = c2.h3
    """))


def neighbourhoods(db: Session) -> None:
    rows = db.execute(text("""
        SELECT h3, area_km2, pop_est, res_bldg_count, footfall_pts,
               comp_convenience + 2 * comp_supermarket + 3 * comp_organised AS comp_w,
               road_major_m, road_minor_m
          FROM ref.h3_cell
    """)).all()
    cell = {r[0]: r[1:] for r in rows}
    out: dict[str, dict] = {}
    for c in cell:
        area = pop = res = foot = comp = major = minor = 0.0
        for n in h3.grid_disk(c, NBHD_K):
            v = cell.get(n)
            if v is None:
                continue
            area += v[0]; pop += v[1]; res += v[2]; foot += v[3]; comp += v[4]; major += v[5]; minor += v[6]
        out[c] = {
            "pop": round(pop),
            "area_km2": round(area, 3),
            "pop_density": round(pop / area, 1),
            "res_density": round(res / area, 1),
            "footfall_density": round(foot / area, 2),
            "comp_weighted": comp,
            # Floor population so near-empty neighbourhoods don't explode the ratio.
            "comp_per_10k": round(comp / max(pop, 2000.0) * 10_000, 2),
            "access_density": round((major + 0.5 * minor) / 1000 / area, 2),
        }

    db.execute(text("DROP TABLE IF EXISTS tmp_nbhd"))
    db.execute(text("CREATE TEMP TABLE tmp_nbhd (h3 text PRIMARY KEY, nbhd jsonb)"))
    copy_rows(db, "tmp_nbhd", ["h3", "nbhd"], ((c, json.dumps(v)) for c, v in out.items()))
    db.execute(text("UPDATE ref.h3_cell c SET nbhd = t.nbhd FROM tmp_nbhd t WHERE t.h3 = c.h3"))

    inhabited = [v for v in out.values() if v["pop_density"] >= INHABITED_MIN_DENSITY]
    db.execute(text("TRUNCATE ref.metric_stats"))
    for m in NBHD_METRICS:
        vals = np.array([v[m] for v in inhabited], dtype=float)
        bps = [float(x) for x in np.percentile(vals, list(range(101)))]
        db.execute(text("INSERT INTO ref.metric_stats (metric, breakpoints, n) VALUES (:m, :b, :n)"),
                   {"m": m, "b": bps, "n": len(vals)})
        log.info("  %-17s p10=%-9.1f p50=%-9.1f p90=%-9.1f (n=%d)", m, bps[10], bps[50], bps[90], len(vals))


def load(db: Session) -> None:
    n = build_cells(db)
    log.info("H3 res-%d cells in CMA: %d", RES, n)
    aggregate(db)
    neighbourhoods(db)
    s = db.execute(text("""
        SELECT round(sum(pop_est)), count(*) FILTER (WHERE pop_est > 0),
               round(avg(nearest_store_m)) FROM ref.h3_cell
    """)).one()
    log.info("cells: population %s, %d populated, mean distance to a Savomart store %s m",
             f"{s[0]:,.0f}", s[1], s[2])
