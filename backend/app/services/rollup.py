"""Roll lane surveys (fresh + reused) up into catchment insights.

Households come from each lane's dwelling bucket (midpoint). Lanes not yet surveyed are
extrapolated by length, skipped lanes (gated, non-residential...) count as zero.
ASSUMED_HH_SIZE converts households to residents; it is an explicit, labelled assumption
used identically for surveyed and modelled figures, so their *ratio* doesn't depend on it.
"""

from collections import Counter
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import CatchmentStudy

DWELLING_MIDPOINT = {"0-10": 5, "11-25": 18, "26-50": 38, "51-100": 75, "100+": 130}
ASSUMED_HH_SIZE = 4.0
CONDITION = {"new": 3, "maintained": 2, "old": 1, "dilapidated": 0}
VEHICLES = {"many_cars": 2, "mixed": 1, "mostly_2w": 0}


def households(data: dict[str, Any]) -> float:
    if isinstance(data.get("dwellings_exact"), (int, float)):
        return float(data["dwellings_exact"])
    return float(DWELLING_MIDPOINT.get(data.get("dwellings_bucket") or "", 0))


def summarise(rows: list[dict[str, Any]], area_km2: float, modelled_pop: float, osm_competitors: int) -> dict[str, Any]:
    """rows: one per study lane with keys length_m, lane_status, survey_status, data, is_seed, captured_at."""
    total_len = sum(r["length_m"] for r in rows) or 1.0
    observed = [r for r in rows if r["survey_status"] == "submitted"]
    skipped = [r for r in rows if r["survey_status"] == "skipped"]
    obs_len = sum(r["length_m"] for r in observed)
    skip_len = sum(r["length_m"] for r in skipped)
    hh_seen = sum(households(r["data"]) for r in observed)
    # Extrapolate over lanes nobody has observed yet (excluding skipped, which have no homes).
    residential_len = max(total_len - skip_len, 1.0)
    hh_est = hh_seen * residential_len / obs_len if obs_len else 0.0
    pop_est = hh_est * ASSUMED_HH_SIZE
    kiranas = sum(int(r["data"].get("kiranas") or 0) for r in observed)
    chains = sum(1 for r in observed if r["data"].get("organised_present"))
    kiranas_est = kiranas * residential_len / obs_len if obs_len else 0.0
    affl = [
        (CONDITION.get(r["data"].get("condition"), 1.5) / 3 * 0.5 + VEHICLES.get(r["data"].get("vehicles"), 1) / 2 * 0.5)
        for r in observed
    ]
    share = lambda key: {k: round(v / len(observed), 3) for k, v in Counter(  # noqa: E731
        r["data"].get(key) or "unknown" for r in observed).items()} if observed else {}
    dates = sorted(str(r["captured_at"])[:10] for r in observed + skipped if r.get("captured_at"))
    comp_per_10k = (kiranas_est + 3 * chains) / max(pop_est, 2000.0) * 10_000 if obs_len else None
    return {
        "lanes_total": len(rows),
        "lanes_observed": len(observed),
        "lanes_skipped": len(skipped),
        "lanes_reused": sum(1 for r in rows if r["lane_status"] == "reused"),
        "coverage": round((obs_len + skip_len) / total_len, 3),
        "households_observed": round(hh_seen),
        "households_est": round(hh_est),
        "population_est": round(pop_est),
        "assumed_household_size": ASSUMED_HH_SIZE,
        "density_est": round(pop_est / area_km2, 1) if area_km2 else None,
        "modelled_population": round(modelled_pop),
        "survey_vs_model": round(pop_est / modelled_pop - 1, 3) if modelled_pop else None,
        "kiranas_observed": kiranas,
        "kiranas_est": round(kiranas_est),
        "lanes_with_organised_chain": chains,
        "osm_competitors": osm_competitors,
        "comp_per_10k": round(comp_per_10k, 2) if comp_per_10k is not None else None,
        "affluence_index": round(sum(affl) / len(affl) * 100) if affl else None,
        "housing_mix": share("housing_type"),
        "footfall_mix": share("footfall"),
        "delivery_access_mix": share("delivery_access"),
        "skip_reasons": dict(Counter(r["data"].get("skip_reason") or "other" for r in skipped)),
        "includes_seed_data": any(r.get("is_seed") for r in rows if r["survey_status"]),
        "captured_from": dates[0] if dates else None,
        "captured_to": dates[-1] if dates else None,
        "area_km2": round(area_km2, 3),
    }


def gather(db: Session, study: CatchmentStudy) -> dict[str, Any]:
    rows = [dict(r._mapping) for r in db.execute(text("""
        SELECT sl.lane_id, sl.length_m, sl.status AS lane_status,
               s.status AS survey_status, coalesce(s.data, '{}'::jsonb) AS data, s.is_seed, s.captured_at,
               s.study_id AS source_study
          FROM app.study_lane sl
          LEFT JOIN LATERAL (
                SELECT * FROM app.lane_survey ls
                 WHERE (sl.reused_survey_id IS NOT NULL AND ls.id = sl.reused_survey_id)
                    OR (sl.reused_survey_id IS NULL AND ls.study_id = sl.study_id AND ls.lane_id = sl.lane_id
                        AND ls.status IN ('submitted', 'skipped'))
                 ORDER BY ls.captured_at DESC LIMIT 1) s ON true
         WHERE sl.study_id = :id
    """), {"id": study.id})]
    geo = db.execute(text("""
        SELECT ST_Area(s.geom::geography) / 1e6 AS km2,
               (SELECT coalesce(sum(b.pop_est), 0) FROM ref.osm_building b WHERE ST_Intersects(s.geom, b.geom)) AS pop,
               (SELECT count(*) FROM ref.osm_poi p WHERE p.competitor_tier > 0 AND ST_Intersects(s.geom, p.geom)) AS comp
          FROM app.catchment_study s WHERE s.id = :id
    """), {"id": study.id}).one()
    out = summarise(rows, float(geo.km2), float(geo.pop), int(geo.comp))
    sources = sorted({str(r["source_study"]) for r in rows if r["source_study"]})
    out["source_studies"] = [dict(x._mapping) | {"id": str(x.id)} for x in db.execute(text(
        "SELECT id, code FROM app.catchment_study WHERE id = ANY(CAST(:ids AS uuid[]))"), {"ids": sources})]
    return out


def evaluation_overrides(study: CatchmentStudy) -> dict[str, Any] | None:
    """The survey covers a ~500 m circle but the evaluation looks at ~1 km, so we carry the
    survey/model *ratio* over (like for like) instead of the dense core's raw density."""
    ins = study.insight or {}
    if ins.get("survey_vs_model") is None or not ins.get("lanes_observed"):
        return None
    return {"demand_factor": round(1 + ins["survey_vs_model"], 3), "comp_per_10k": ins.get("comp_per_10k"),
            "source": f"catchment study {study.code} ({ins['lanes_observed']} lanes surveyed)",
            "study_id": str(study.id)}


def build_facts(study: CatchmentStudy, ins: dict[str, Any]) -> dict[str, dict[str, Any]]:
    f: dict[str, dict[str, Any]] = {}

    def add(fid, label, value, unit="", source="lane survey"):
        if value is not None:
            f[fid] = {"label": label, "value": value, "unit": unit, "source": source}

    add("lanes_total", "Lanes in the catchment", ins["lanes_total"], "lanes")
    add("lanes_observed", "Lanes surveyed", ins["lanes_observed"], "lanes")
    add("lanes_reused", "Lanes reused from earlier studies", ins["lanes_reused"], "lanes")
    add("coverage", "Share of lane length covered", ins["coverage"], "share")
    add("households_est", "Estimated households", ins["households_est"], "households")
    add("population_est", "Estimated residents", ins["population_est"], "people", "lane survey x assumed household size")
    add("assumed_household_size", "Assumed household size", ins["assumed_household_size"], "people", "assumption")
    add("modelled_population", "Modelled residents (Census 2011 baseline)", ins["modelled_population"], "people",
        "Census 2011 + OSM buildings")
    add("survey_vs_model", "Survey vs model difference", ins["survey_vs_model"], "share")
    add("kiranas_observed", "Kiranas counted", ins["kiranas_observed"], "shops")
    add("kiranas_est", "Kiranas estimated across the catchment", ins["kiranas_est"], "shops")
    add("osm_competitors", "Grocery shops mapped in OSM", ins["osm_competitors"], "shops", "OSM")
    add("lanes_with_organised_chain", "Lanes with an organised chain", ins["lanes_with_organised_chain"], "lanes")
    add("affluence_index", "Affluence index (building condition + vehicles)", ins["affluence_index"], "/100")
    return f


def template_narrative(study: CatchmentStudy, ins: dict[str, Any]) -> dict[str, Any]:
    diff = ins.get("survey_vs_model")
    diff_txt = (f"{abs(diff) * 100:.0f}% {'more' if diff > 0 else 'fewer'} residents than the Census-based model"
                if diff is not None else "no model comparison")
    shops = ins["kiranas_est"]
    return {
        "headline": f"{study.code}: about {ins['households_est']:,} households in the catchment ({diff_txt}).",
        "summary": (f"{ins['lanes_observed']} of {ins['lanes_total']} lanes observed"
                    + (f", {ins['lanes_reused']} reused from earlier studies" if ins["lanes_reused"] else "")
                    + f". Surveyors counted {ins['kiranas_observed']} kiranas (about {shops} across the catchment) "
                      f"against {ins['osm_competitors']} grocery shops mapped in OpenStreetMap."),
        "reasons": [{"text": f"Affluence index {ins['affluence_index']}/100 from building condition and vehicles.",
                     "fact_ids": ["affluence_index"]}] if ins.get("affluence_index") is not None else [],
        "risks": ([{"text": f"{ins['lanes_with_organised_chain']} lanes already have an organised chain.",
                    "fact_ids": ["lanes_with_organised_chain"]}] if ins["lanes_with_organised_chain"] else []),
        "caveats": [f"Residents = households x {ins['assumed_household_size']:g} (assumed household size)."]
        + (["Includes synthetic demo survey data."] if ins.get("includes_seed_data") else []),
    }
