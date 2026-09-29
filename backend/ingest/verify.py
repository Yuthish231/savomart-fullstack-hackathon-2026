"""Data-quality report for the loaded reference data. Usage: python -m ingest.verify

Checks that fail print "FAIL" so a broken ingest is obvious; the rest is context.
"""

from sqlalchemy import text

from app.core.db import SessionLocal
from ingest.population import OLD_CITY_POP_2011, UA_POP_2011


def main() -> None:
    ok = True

    def check(cond: bool, msg: str) -> None:
        nonlocal ok
        ok &= cond
        print(f"  [{'ok' if cond else 'FAIL'}] {msg}")

    with SessionLocal() as db:
        q = lambda sql, **kw: db.execute(text(sql), kw)  # noqa: E731

        print("Sources")
        for r in q("SELECT key, row_count, as_of, is_mock FROM ref.data_source ORDER BY key"):
            print(f"  {r.key:<22} rows={r.row_count!s:<8} as_of={r.as_of}  {'MOCK' if r.is_mock else ''}")

        print("Boundaries")
        areas = dict(q("SELECT key, area_km2 FROM ref.boundary").all())
        check(1150 < areas.get("cma", 0) < 1230, f"CMA area {areas.get('cma', 0):.0f} km2 (official 1,189)")
        check(410 < areas.get("gcc", 0) < 440, f"GCC area {areas.get('gcc', 0):.0f} km2 (official 426)")
        check(165 < areas.get("old_city", 0) < 180, f"old city {areas.get('old_city', 0):.0f} km2 (historic 174)")

        print("Population (dasymetric, Census 2011 baseline)")
        total = q("SELECT sum(pop_est) FROM ref.osm_building").scalar() or 0
        old = q("""SELECT sum(b.pop_est) FROM ref.osm_building b JOIN ref.boundary_sub s
                    ON s.key = 'old_city' AND ST_Intersects(s.geom, b.geom)""").scalar() or 0
        check(abs(total - UA_POP_2011) < 1000, f"total {total:,.0f} vs control {UA_POP_2011:,}")
        check(abs(old - OLD_CITY_POP_2011) < 1000, f"old city {old:,.0f} vs control {OLD_CITY_POP_2011:,}")
        cells = q("SELECT sum(pop_est) FROM ref.h3_cell").scalar() or 0
        check(cells > 0.97 * total, f"H3 cells capture {cells / max(total, 1):.1%} of population")
        print("  densest pincodes (people per km2):")
        for r in q("""SELECT pincode, office_name, round(pop_est / area_km2) AS d, round(pop_est) AS p
                        FROM ref.pincode WHERE in_cma_share > 0.5 ORDER BY d DESC LIMIT 5"""):
            print(f"    {r.pincode} {r.office_name:<22} {r.d:>8,.0f}/km2  pop {r.p:,.0f}")

        print("POIs and competition")
        comp = dict(q("SELECT competitor_tier, count(*) FROM ref.osm_poi WHERE competitor_tier > 0 GROUP BY 1").all())
        check(sum(comp.values()) > 200, f"grocery competitors by tier {dict(sorted(comp.items()))}")
        own = q("SELECT count(*) FROM ref.osm_poi WHERE category = 'own_store'").scalar()
        print(f"  Savomart outlets already mapped in OSM: {own} (excluded from competition)")

        print("Roads and lanes")
        n, km, surv = q("""SELECT count(*), sum(length_m) / 1000,
                                  count(*) FILTER (WHERE is_surveyable) FROM ref.lane_segment""").one()
        check(n > 50_000, f"{n:,} lane segments, {km:,.0f} km, {surv:,} surveyable")
        long_ = q("SELECT count(*) FROM ref.lane_segment WHERE length_m > 400").scalar()
        check(long_ < 0.01 * n, f"{long_} segments longer than 400 m")

        print("H3 grid")
        c = q("""SELECT count(*) AS n, count(*) FILTER (WHERE pop_est > 0) AS populated,
                        count(*) FILTER (WHERE nearest_store_m IS NULL) AS no_store,
                        count(*) FILTER (WHERE nbhd = '{}'::jsonb) AS no_nbhd FROM ref.h3_cell""").one()
        check(c.no_store == 0 and c.no_nbhd == 0, f"{c.n:,} cells, {c.populated:,} populated, all with store distance and neighbourhood")
        for r in q("SELECT metric, n, breakpoints[11] AS p10, breakpoints[51] AS p50, breakpoints[91] AS p90 FROM ref.metric_stats ORDER BY metric"):
            print(f"    {r.metric:<17} n={r.n:<6} p10={r.p10:<10.1f} p50={r.p50:<10.1f} p90={r.p90:.1f}")

        print("Stores")
        for r in q("""SELECT name, address_pincode, geo_pincode FROM ref.savomart_store
                       WHERE address_pincode IS DISTINCT FROM geo_pincode"""):
            print(f"  note: {r.name}: address pincode {r.address_pincode}, coordinates in {r.geo_pincode}")

    print("\nRESULT:", "all checks passed" if ok else "SOME CHECKS FAILED")


if __name__ == "__main__":
    main()
