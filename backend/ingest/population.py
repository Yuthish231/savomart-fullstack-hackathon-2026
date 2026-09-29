"""Census-anchored dasymetric population.

Census 2011 control totals (Primary Census Abstract, via census2011.co.in):
- Chennai (M Corp.), i.e. the pre-2011 city = our 'old_city' polygon: 4,646,732
- Chennai Urban Agglomeration total: 8,653,521, so the rest of the CMA gets 4,006,789

Within each zone, residents are spread over OSM buildings in proportion to their
residential weight (levels x residential likelihood, see categories.classify_building).
This is a 2011 baseline: scores use city percentiles, so relative density is what matters,
and ground surveys (M3) override it where they exist.
"""

from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from ingest.common import log, register_source

OLD_CITY_POP_2011 = 4_646_732
UA_POP_2011 = 8_653_521
REST_POP_2011 = UA_POP_2011 - OLD_CITY_POP_2011


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
    k_old = OLD_CITY_POP_2011 / totals[True]
    k_rest = REST_POP_2011 / totals[False]
    log.info("persons per residential weight unit: old city %.1f, rest of CMA %.1f", k_old, k_rest)

    db.execute(text("""
        UPDATE ref.osm_building b
           SET pop_est = b.res_weight * CASE WHEN z.old_city THEN :k_old ELSE :k_rest END
          FROM tmp_bzone z WHERE z.osm_id = b.osm_id
    """), {"k_old": k_old, "k_rest": k_rest})

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
