"""Area Fitness analysis: aggregate precomputed H3 features over an area, score them,
pick scouting hotspots, and assemble the fact table the narrative must stay within."""

from typing import Any

import h3
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.scoring import SPEC_BY_KEY, grade, score_metrics, subs_as_dicts

COMP_RING_K = 2  # ~500-700 m ring of res-9 cells around the area for competition
HOTSPOT_MIN_SPACING = 3  # H3 grid distance between hotspots (~0.6 km+)
MAX_HOTSPOTS = 5
INHABITED_MIN_DENSITY = 500.0


def _ring(cells: list[str], k: int) -> list[str]:
    ring: set[str] = set()
    for c in cells:
        ring.update(h3.grid_disk(c, k))
    return list(ring - set(cells))


def cell_model_metrics(db: Session, cells: list[str], ring: list[str]) -> dict[str, float]:
    """Scoring-model inputs (same definitions as the city percentile tables) for a set of
    res-9 cells plus a competition ring. Shared by area reports and property evaluations."""
    a = db.execute(text("""
        SELECT sum(area_km2) AS area_km2, coalesce(sum(pop_est), 0) AS pop,
               coalesce(sum(res_bldg_count), 0) AS res, coalesce(sum(footfall_pts), 0) AS foot,
               coalesce(sum(comp_convenience + 2 * comp_supermarket + 3 * comp_organised), 0) AS comp_w,
               coalesce(sum(road_major_m), 0) AS major, coalesce(sum(road_minor_m), 0) AS minor
          FROM ref.h3_cell WHERE h3 = ANY(:cells)
    """), {"cells": cells}).one()
    r = db.execute(text("""
        SELECT coalesce(sum(pop_est), 0) AS pop,
               coalesce(sum(comp_convenience + 2 * comp_supermarket + 3 * comp_organised), 0) AS comp_w
          FROM ref.h3_cell WHERE h3 = ANY(:ring)
    """), {"ring": ring}).one()
    area = float(a.area_km2 or 0) or 0.001
    return {
        "area_km2": round(area, 3),
        "population": round(float(a.pop)),
        "pop_density": round(float(a.pop) / area, 1),
        "res_density": round(float(a.res) / area, 1),
        "footfall_density": round(float(a.foot) / area, 2),
        "comp_per_10k": round((float(a.comp_w) + float(r.comp_w)) / max(float(a.pop) + float(r.pop), 2000.0)
                              * 10_000, 2),
        "access_density": round((float(a.major) + 0.5 * float(a.minor)) / 1000 / area, 2),
    }


def aggregate(db: Session, area_id, cells: list[str]) -> dict[str, Any]:
    q = lambda sql, **kw: db.execute(text(sql), kw)  # noqa: E731
    a = q("""
        SELECT sum(area_km2) AS area_km2, sum(pop_est) AS pop, sum(bldg_count) AS bldg,
               sum(res_bldg_count) AS res_bldg, sum(footfall_pts) AS footfall,
               sum(comp_convenience) AS c1, sum(comp_supermarket) AS c2, sum(comp_organised) AS c3,
               sum(retail_count) AS retail, sum(road_major_m) AS road_major, sum(road_minor_m) AS road_minor,
               count(*) AS n_cells,
               count(*) FILTER (WHERE bldg_count > 0) AS cells_with_bldg,
               count(*) FILTER (WHERE road_minor_m > 200) AS cells_with_roads
          FROM ref.h3_cell WHERE h3 = ANY(:cells)
    """, cells=cells).one()._mapping
    ring = _ring(cells, COMP_RING_K)
    r = q("""
        SELECT coalesce(sum(pop_est), 0) AS pop,
               coalesce(sum(comp_convenience + 2 * comp_supermarket + 3 * comp_organised), 0) AS comp_w,
               coalesce(sum(comp_convenience + comp_supermarket + comp_organised), 0) AS comp_n
          FROM ref.h3_cell WHERE h3 = ANY(:ring)
    """, ring=ring).one()._mapping

    nearest = q("""
        SELECT s.store_code, s.name,
               ST_Distance(s.geom::geography, ST_Centroid(a.geom)::geography) AS dist_m
          FROM app.area a, ref.savomart_store s
         WHERE a.id = :id ORDER BY s.geom <-> ST_Centroid(a.geom) LIMIT 1
    """, id=area_id).one()._mapping
    stores_near = [dict(x._mapping) for x in q("""
        SELECT s.store_code, s.name, round(ST_Distance(s.geom::geography, a.geom::geography)) AS dist_m
          FROM app.area a, ref.savomart_store s
         WHERE a.id = :id AND ST_DWithin(s.geom::geography, a.geom::geography, 3000)
         ORDER BY 3
    """, id=area_id)]
    categories = dict(q("""
        SELECT category, count(*) FROM ref.osm_poi WHERE h3_r9 = ANY(:cells) GROUP BY 1
    """, cells=cells).all())
    chains = [dict(x._mapping) for x in q("""
        SELECT coalesce(brand, name) AS name, count(*) AS n FROM ref.osm_poi
         WHERE competitor_tier = 3 AND h3_r9 = ANY(:cells)
         GROUP BY 1 ORDER BY 2 DESC LIMIT 6
    """, cells=cells + ring)]
    transit = [x[0] for x in q("""
        SELECT DISTINCT name FROM ref.osm_poi
         WHERE category = 'transit' AND subcategory IN ('rail', 'metro') AND name IS NOT NULL
           AND h3_r9 = ANY(:cells) LIMIT 5
    """, cells=cells)]

    area_km2 = float(a["area_km2"] or 0) or 0.001
    pop = float(a["pop"] or 0)
    comp_w_area = float(a["c1"] or 0) + 2 * float(a["c2"] or 0) + 3 * float(a["c3"] or 0)
    comp_pop = pop + float(r["pop"])
    return {
        "area_km2": round(area_km2, 2),
        "n_cells": a["n_cells"],
        "population": round(pop),
        "buildings": int(a["bldg"] or 0),
        "residential_buildings": int(a["res_bldg"] or 0),
        "footfall_points": round(float(a["footfall"] or 0), 1),
        "competitors": {"kirana_convenience": int(a["c1"] or 0), "supermarket": int(a["c2"] or 0),
                        "organised_chain": int(a["c3"] or 0)},
        "competitors_in_ring": int(r["comp_n"]),
        "retail_shops": int(a["retail"] or 0),
        "road_major_km": round(float(a["road_major"] or 0) / 1000, 2),
        "road_minor_km": round(float(a["road_minor"] or 0) / 1000, 2),
        "poi_by_category": categories,
        "organised_chains_nearby": chains,
        "rail_metro_stations": transit,
        "nearest_store": {"code": nearest["store_code"], "name": nearest["name"],
                          "distance_km": round(float(nearest["dist_m"]) / 1000, 2)},
        "savomart_stores_within_3km": stores_near,
        "coverage": {"cells_with_buildings": a["cells_with_bldg"], "cells_with_roads": a["cells_with_roads"]},
        # Model inputs (same definitions as the city percentile tables).
        "model": {
            "pop_density": round(pop / area_km2, 1),
            "res_density": round(float(a["res_bldg"] or 0) / area_km2, 1),
            "footfall_density": round(float(a["footfall"] or 0) / area_km2, 2),
            "comp_per_10k": round((comp_w_area + float(r["comp_w"])) / max(comp_pop, 2000.0) * 10_000, 2),
            "access_density": round((float(a["road_major"] or 0) + 0.5 * float(a["road_minor"] or 0))
                                    / 1000 / area_km2, 2),
            "nearest_store_km": round(float(nearest["dist_m"]) / 1000, 2),
        },
    }


def confidence(m: dict[str, Any]) -> tuple[str, list[str]]:
    reasons = ["Population is a Census 2011 baseline spread over OSM buildings, not a current count."]
    cov = m["coverage"]
    mapped_share = cov["cells_with_buildings"] / max(cov["cells_with_roads"], 1)
    level = "High"
    if mapped_share < 0.5:
        level = "Low"
        reasons.append(f"Buildings are mapped in only {mapped_share:.0%} of the streets' cells; "
                       "OpenStreetMap coverage here is thin, so demand may be understated.")
    elif mapped_share < 0.8:
        level = "Medium"
        reasons.append(f"Buildings are mapped in {mapped_share:.0%} of cells with streets; some blocks may be missing.")
    if m["population"] < 3000:
        level = "Low" if level != "High" else "Medium"
        reasons.append("Few residents in the selection, so small data gaps move the score a lot.")
    if sum(m["competitors"].values()) + m["competitors_in_ring"] == 0:
        reasons.append("No grocery shops are mapped nearby; OSM often misses kiranas, so a ground survey would confirm.")
        level = "Medium" if level == "High" else level
    return level, reasons


def hotspots(db: Session, cells: list[str], stats: dict[str, list[float]]) -> list[dict[str, Any]]:
    rows = db.execute(text("""
        SELECT h3, opportunity, nbhd, nearest_store_m, pop_est,
               ST_Y(ST_Centroid(geom)) AS lat, ST_X(ST_Centroid(geom)) AS lon
          FROM ref.h3_cell
         WHERE h3 = ANY(:cells) AND opportunity IS NOT NULL
         ORDER BY opportunity DESC
    """), {"cells": cells}).all()
    picked = []
    for r in rows:
        if any(h3.grid_distance(r.h3, p.h3) < HOTSPOT_MIN_SPACING for p in picked):
            continue
        picked.append(r)
        if len(picked) >= MAX_HOTSPOTS:
            break
    out = []
    for i, r in enumerate(picked, start=1):
        _, subs = score_metrics({**r.nbhd, "nearest_store_km": r.nearest_store_m / 1000}, stats)
        top = sorted((s for s in subs), key=lambda s: s.score, reverse=True)[:2]
        road = db.execute(text("""
            SELECT name, highway FROM ref.lane_segment
             WHERE name IS NOT NULL AND ST_DWithin(geom::geography, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, 400)
             ORDER BY (highway IN ('primary','secondary','trunk','tertiary')) DESC,
                      geom <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)
             LIMIT 1
        """), {"lat": r.lat, "lon": r.lon}).first()
        out.append({
            "id": f"h{i}",
            "rank": i,
            "h3": r.h3,
            "lat": round(r.lat, 6),
            "lon": round(r.lon, 6),
            "score": round(r.opportunity, 1),
            "near_road": road.name if road else None,
            "nearest_store_km": round(r.nearest_store_m / 1000, 2),
            "neighbourhood_population": r.nbhd.get("pop"),
            "strengths": [{"key": s.key, "label": s.label, "score": s.score} for s in top],
        })
    return out


def build_facts(area_name: str, m: dict[str, Any], total: float, subs: list[dict], conf: str,
                spots: list[dict]) -> dict[str, dict[str, Any]]:
    f: dict[str, dict[str, Any]] = {}

    def add(fid, label, value, unit="", source="derived"):
        f[fid] = {"label": label, "value": value, "unit": unit, "source": source}

    add("area_name", "Area", area_name)
    add("overall_score", "Overall fit score", total, "/100", "SiteScout model v1")
    add("grade", "Grade", grade(total), "", "SiteScout model v1")
    add("confidence", "Confidence", conf)
    add("area_km2", "Area size", m["area_km2"], "km²", "selection")
    add("population", "Estimated residents", m["population"], "people", "Census 2011 + OSM buildings")
    add("residential_buildings", "Residential buildings", m["residential_buildings"], "buildings", "OSM")
    add("competitors_total", "Grocery competitors in area", sum(m["competitors"].values()), "shops", "OSM")
    add("organised_chains", "Organised chain outlets in area", m["competitors"]["organised_chain"], "shops", "OSM")
    add("supermarkets", "Independent supermarkets in area", m["competitors"]["supermarket"], "shops", "OSM")
    add("kiranas", "Kirana / convenience shops in area", m["competitors"]["kirana_convenience"], "shops", "OSM")
    add("competitors_ring", "Grocery competitors in the ~500 m ring", m["competitors_in_ring"], "shops", "OSM")
    add("nearest_store_km", f"Distance to nearest Savomart ({m['nearest_store']['name']})",
        m["nearest_store"]["distance_km"], "km", "Savomart Stores API")
    add("stores_within_3km", "Savomart stores within 3 km", len(m["savomart_stores_within_3km"]), "stores",
        "Savomart Stores API")
    for s in subs:
        add(f"sub_{s['key']}", f"{s['label']} sub-score", s["score"], "/100", "SiteScout model v1")
        add(f"raw_{s['key']}", f"{s['label']} raw value", s["raw_value"], s["unit"], "derived")
        if s["percentile"] is not None:
            add(f"pct_{s['key']}", f"{s['label']} Chennai percentile", s["percentile"], "percentile", "derived")
    for h in spots:
        add(f"{h['id']}_score", f"Hotspot {h['rank']} score", h["score"], "/100", "SiteScout model v1")
        add(f"{h['id']}_store_km", f"Hotspot {h['rank']} distance to nearest Savomart", h["nearest_store_km"], "km",
            "Savomart Stores API")
    return f


def template_narrative(area_name: str, total: float, subs: list[dict], spots: list[dict],
                       conf: str, conf_reasons: list[str]) -> dict[str, Any]:
    ranked = sorted(subs, key=lambda s: s["score"], reverse=True)
    best, worst = ranked[:2], ranked[-1]
    g = grade(total)
    verdict = {"A": "a strong fit", "B": "a good fit", "C": "a mixed fit", "D": "a weak fit"}[g]
    return {
        "headline": f"{area_name} is {verdict} for a Savomart store (grade {g}, {total:.0f}/100).",
        "summary": (f"Strongest signals: {best[0]['label'].lower()} ({best[0]['score']:.0f}/100) and "
                    f"{best[1]['label'].lower()} ({best[1]['score']:.0f}/100). Weakest: "
                    f"{worst['label'].lower()} ({worst['score']:.0f}/100). Confidence is {conf.lower()}."),
        "reasons": [{"text": f"{s['label']}: {s['score']:.0f}/100. {SPEC_BY_KEY[s['key']].explain}.",
                     "fact_ids": [f"sub_{s['key']}"]} for s in best],
        "scout_first": [
            {"hotspot_id": h["id"],
             "text": f"Hotspot {h['rank']}" + (f" near {h['near_road']}" if h["near_road"] else "")
                     + f": scores {h['score']:.0f}, {h['nearest_store_km']:.1f} km from the nearest Savomart."}
            for h in spots[:3]
        ],
        "risks": [{"text": f"{worst['label']} is the weakest signal ({worst['score']:.0f}/100).",
                   "fact_ids": [f"sub_{worst['key']}"]}],
        "caveats": conf_reasons,
    }
