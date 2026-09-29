"""Census-anchored dasymetric population.

Census 2011 control totals (Primary Census Abstract, via census2011.co.in):
- Chennai (M Corp.), i.e. the pre-2011 city = our 'old_city' polygon: 4,646,732
- Chennai Urban Agglomeration total: 8,653,521, so the rest of the CMA gets 4,006,789

Within each zone, residents are spread over OSM buildings in proportion to their
residential weight (residential likelihood x apartment factor, see categories.classify_building;
generic buildings on industrial/commercial/campus land are down-weighted), then capped at
DENSITY_CAP people/km2 per cell with the excess redistributed within the zone.
This is a 2011 baseline: scores use city percentiles, so relative density is what matters,
and ground surveys (M3) override it where they exist.
"""

from collections import defaultdict
from datetime import date

import h3
from sqlalchemy import text
from sqlalchemy.orm import Session

from ingest.common import copy_rows, log, register_source

OLD_CITY_POP_2011 = 4_646_732
UA_POP_2011 = 8_653_521
REST_POP_2011 = UA_POP_2011 - OLD_CITY_POP_2011
# Ceiling per ~0.1 km2 cell. Over-mapped commercial cores (thousands of tiny generic
# "building=yes" shops) would otherwise absorb residents; the excess stays in the same zone.
DENSITY_CAP = 60_000.0


def ceiling_factors(pops: dict[str, float], areas: dict[str, float], cap: float) -> dict[str, float]:
    """Cap each cell at `cap` people/km2 and redistribute the excess proportionally over the
    uncapped cells of the same zone (repeat until nothing exceeds the cap). Returns a
    multiplicative factor per cell; the zone total is preserved."""
    new = dict(pops)
    capped: set[str] = set()
    for _ in range(50):
        over = {c for c, p in new.items() if c not in capped and p > cap * areas[c]}
        if not over:
            break
        excess = sum(new[c] - cap * areas[c] for c in over)
        for c in over:
            new[c] = cap * areas[c]
        capped |= over
        free = [c for c in new if c not in capped]
        base = sum(new[c] for c in free)
        if base <= 0:
            break
        for c in free:
            new[c] *= (base + excess) / base
    return {c: (new[c] / pops[c] if pops[c] else 1.0) for c in pops}


def _apply_density_ceiling(db: Session) -> None:
    rows = db.execute(text("""
        SELECT z.old_city, b.h3_r9, sum(b.pop_est) FROM ref.osm_building b
          JOIN tmp_bzone z ON z.osm_id = b.osm_id GROUP BY 1, 2
    """)).all()
    zones: dict[bool, dict[str, float]] = defaultdict(dict)
    for old_city, cell, pop in rows:
        zones[old_city][cell] = float(pop or 0)
    out, n_capped = [], 0
    for old_city, pops in zones.items():
        areas = {c: h3.cell_area(c, "km^2") for c in pops}
        f = ceiling_factors(pops, areas, DENSITY_CAP)
        n_capped += sum(1 for v in f.values() if v < 0.999)
        out += [(old_city, c, v) for c, v in f.items() if abs(v - 1) > 1e-6]
    db.execute(text("DROP TABLE IF EXISTS tmp_factor"))
    db.execute(text("CREATE TEMP TABLE tmp_factor (old_city boolean, h3 text, f double precision)"))
    copy_rows(db, "tmp_factor", ["old_city", "h3", "f"], out)
    db.execute(text("""
        UPDATE ref.osm_building b SET pop_est = b.pop_est * t.f
          FROM tmp_bzone z, tmp_factor t
         WHERE z.osm_id = b.osm_id AND t.old_city = z.old_city AND t.h3 = b.h3_r9
    """))
    log.info("density ceiling %s/km2: %d cells capped, excess redistributed within their zone",
             f"{DENSITY_CAP:,.0f}", n_capped)


def load(db: Session) -> None:
    db.execute(text("DROP TABLE IF EXISTS tmp_bzone"))
    db.execute(text("""
        CREATE TEMP TABLE tmp_bzone AS
        SELECT b.osm_id, b.res_weight,
               EXISTS (SELECT 1 FROM ref.boundary_sub s
                        WHERE s.key = 'old_city' AND ST_Intersects(s.geom, b.geom)) AS old_city
          FROM ref.osm_building b
    """))
    totals = dict(db.execute(text(
        "SELECT old_city, sum(res_weight) FROM tmp_bzone GROUP BY old_city")).all())
    for zone, name in ((True, "old city"), (False, "rest of CMA")):
        if not totals.get(zone):
            log.warning("no buildings loaded in the %s: its population cannot be allocated "
                        "(is the OSM building download complete?)", name)
    k_old = OLD_CITY_POP_2011 / totals[True] if totals.get(True) else 0.0
    k_rest = REST_POP_2011 / totals[False] if totals.get(False) else 0.0
    log.info("persons per residential weight unit: old city %.1f, rest of CMA %.1f", k_old, k_rest)

    db.execute(text("""
        UPDATE ref.osm_building b
           SET pop_est = b.res_weight * CASE WHEN z.old_city THEN :k_old ELSE :k_rest END
          FROM tmp_bzone z WHERE z.osm_id = b.osm_id
    """), {"k_old": k_old, "k_rest": k_rest})
    _apply_density_ceiling(db)

    db.execute(text("""
        UPDATE ref.ward w SET pop_est = coalesce(s.pop, 0)
          FROM (SELECT w2.ward_no, sum(b.pop_est) AS pop
                  FROM ref.ward w2 JOIN ref.osm_building b ON ST_Intersects(w2.geom, b.geom)
                 GROUP BY w2.ward_no) s
         WHERE s.ward_no = w.ward_no
    """))
    db.execute(text("""
        UPDATE ref.pincode p SET pop_est = coalesce(s.pop, 0)
          FROM (SELECT p2.pincode, sum(b.pop_est) AS pop
                  FROM ref.pincode p2 JOIN ref.osm_building b ON ST_Intersects(p2.geom, b.geom)
                 GROUP BY p2.pincode) s
         WHERE s.pincode = p.pincode
    """))
    total = db.scalar(text("SELECT round(sum(pop_est)) FROM ref.osm_building"))
    gcc = db.scalar(text("SELECT round(sum(pop_est)) FROM ref.ward"))
    log.info("population allocated: %s total, %s inside GCC wards", f"{total:,.0f}", f"{gcc:,.0f}")

    register_source(
        db, "census_2011", "Census of India 2011: Chennai (M Corp.) and Chennai UA population",
        url="https://www.census2011.co.in/census/metropolitan/435-chennai.html",
        license="Census of India (public)", as_of=date(2011, 3, 1), row_count=2,
        notes="Control totals 4,646,732 (old city) and 8,653,521 (UA), distributed over OSM "
              "buildings by residential weight (dasymetric). 2011 baseline, not a current count.",
    )
