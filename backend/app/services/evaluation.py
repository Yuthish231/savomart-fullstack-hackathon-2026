"""Property evaluation (v1): public data around the pin + what the executive captured.

score = 60% location (the Area Fitness model applied to the ~1 km around the pin)
      + 40% site (explicit checks on size, floor, frontage, access, visibility, parking, rent)
Blockers force "reject"; otherwise >= 65 with no high risks is "proceed", else "review".
Pure functions below take plain dicts so they are unit-testable without a database.
"""

from dataclasses import asdict, dataclass
from typing import Any

import h3
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.area_analysis import cell_model_metrics
from app.services.scoring import score_metrics, subs_as_dicts

EVAL_VERSION = "v1"
LOCATION_WEIGHT, SITE_WEIGHT = 0.6, 0.4
CATCHMENT_K = 3  # ~1 km around the pin in res-9 cells
PROCEED_AT = 65.0
CANNIBALISATION_KM = 0.8
TARGET_SQFT = (1500, 4000)

FLOORS = {"ground": "Ground floor", "first": "First floor", "basement": "Basement", "upper": "Second floor or above"}
ACCESS = {"truck": "Truck can reach", "van": "Van / tempo only", "two_wheeler": "Two-wheelers only", "none": "No vehicle access"}
VISIBILITY = {"main_road": "Faces a main road", "side_street": "On a side street", "inside_lane": "Inside a lane"}
PROPERTY_TYPES = {"shop": "Shop", "showroom": "Showroom", "standalone": "Standalone building",
                  "mall_unit": "Mall unit", "other": "Other"}

# Data-quality flags that must be resolved before a property can be "proceed".
FLAG_SEVERITY = {"PIN_GPS_MISMATCH": "high", "DUPLICATE_SUSPECTED": "high", "DUPLICATE_DISMISSED": "low",
                 "GPS_WEAK": "low", "NO_GPS": "low"}
FLAGS_COVERED_BY_CHECKS = {"RENT_MISSING"}  # already reported by the rent check


@dataclass
class Check:
    key: str
    label: str
    weight: float
    value: str
    score: float | None  # None = unknown (not captured)
    status: str  # good|ok|poor|blocker|unknown
    note: str


def _band(v: float, bands: list[tuple[float, float, str]]) -> tuple[float, str]:
    for upper, score, status in bands:
        if v < upper:
            return score, status
    return bands[-1][1], bands[-1][2]


def site_checks(d: dict[str, Any], rent_band: dict[str, Any] | None) -> list[Check]:
    checks: list[Check] = []
    sqft = d.get("carpet_sqft")
    if sqft is None:
        checks.append(Check("size", "Carpet area", 0.25, "not captured", None, "unknown", "Carpet area is needed"))
    else:
        s, st = _band(sqft, [(800, 0, "blocker"), (1200, 40, "poor"), (1500, 70, "ok"), (4000.01, 100, "good"),
                             (6000, 70, "ok"), (float("inf"), 40, "poor")])
        note = {"blocker": "Too small for a Savomart format",
                "good": "Within the 1,500-4,000 sq ft target",
                }.get(st, "Smaller than ideal" if sqft < TARGET_SQFT[0] else "Larger than needed; rent burden")
        checks.append(Check("size", "Carpet area", 0.25, f"{sqft:,.0f} sq ft", s, st, note))

    floor = d.get("floor")
    fs = {"ground": (100, "good", "Walk-in grocery trade needs street level"),
          "first": (40, "poor", "Upper floors lose most walk-in grocery trade"),
          "basement": (30, "poor", "Basements hurt visibility and deliveries"),
          "upper": (10, "poor", "Too high for daily grocery shopping")}
    if floor in fs:
        s, st, note = fs[floor]
        checks.append(Check("floor", "Floor", 0.15, FLOORS[floor], s, st, note))
    else:
        checks.append(Check("floor", "Floor", 0.15, "not captured", None, "unknown", "Floor not captured"))

    fr = d.get("frontage_ft")
    if fr is None:
        checks.append(Check("frontage", "Frontage", 0.15, "not captured", None, "unknown", "Frontage not measured"))
    else:
        s, st = _band(fr, [(12, 20, "poor"), (20, 55, "ok"), (25, 85, "good"), (float("inf"), 100, "good")])
        checks.append(Check("frontage", "Frontage", 0.15, f"{fr:g} ft", s, st,
                            "Wide shopfront, good visibility" if fr >= 20 else "Narrow shopfront limits display"))

    acc = d.get("delivery_access")
    accs = {"truck": (100, "good", "Supply trucks can unload at the door"),
            "van": (80, "good", "Vans can reach; fine for daily replenishment"),
            "two_wheeler": (30, "poor", "Stock must be carried in; slow, costly replenishment"),
            "none": (0, "blocker", "No vehicle can reach the store")}
    if acc in accs:
        s, st, note = accs[acc]
        checks.append(Check("access", "Delivery access", 0.15, ACCESS[acc], s, st, note))
    else:
        checks.append(Check("access", "Delivery access", 0.15, "not captured", None, "unknown", "Access not captured"))

    vis = d.get("visibility")
    viss = {"main_road": (100, "good", "Visible to passing traffic"), "side_street": (65, "ok", "Some passing trade"),
            "inside_lane": (25, "poor", "Hidden from passing trade")}
    if vis in viss:
        s, st, note = viss[vis]
        checks.append(Check("visibility", "Visibility", 0.10, VISIBILITY[vis], s, st, note))
    else:
        checks.append(Check("visibility", "Visibility", 0.10, "not captured", None, "unknown", "Visibility not captured"))

    p2, p4 = d.get("parking_2w"), d.get("parking_4w")
    if p2 is None and p4 is None:
        checks.append(Check("parking", "Parking", 0.10, "not captured", None, "unknown", "Parking not captured"))
    else:
        p2, p4 = p2 or 0, p4 or 0
        if p4 >= 2 or p2 >= 10:
            s, st, note = 100, "good", "Customers can stop easily"
        elif p2 >= 4:
            s, st, note = 70, "ok", "Some two-wheeler parking"
        elif p2 or p4:
            s, st, note = 50, "ok", "Very limited parking"
        else:
            s, st, note = 20, "poor", "No parking: customers must walk in"
        checks.append(Check("parking", "Parking", 0.10, f"{p2} two-wheeler, {p4} car", s, st, note))

    rent = d.get("rent_monthly")
    if rent is None or not sqft:
        checks.append(Check("rent", "Rent vs local band (MOCK)", 0.10, "not captured", None, "unknown",
                            "Rent missing: evaluation is incomplete"))
    elif rent_band is None:
        checks.append(Check("rent", "Rent vs local band (MOCK)", 0.10, f"Rs {rent / sqft:,.0f}/sq ft", None,
                            "unknown", "No rent band for this pincode"))
    else:
        psf = rent / sqft
        lo, hi = rent_band["min"], rent_band["max"]
        if psf < 0.5 * lo:
            s, st, note = 60, "ok", f"Far below the local band ({lo:.0f}-{hi:.0f}); verify the figure"
        elif psf <= hi:
            s, st, note = 100, "good", f"Within or below the local band ({lo:.0f}-{hi:.0f})"
        elif psf <= 1.5 * hi:
            s, st, note = 50, "ok", f"Above the local band ({lo:.0f}-{hi:.0f})"
        else:
            s, st, note = 20, "poor", f"Well above the local band ({lo:.0f}-{hi:.0f})"
        checks.append(Check("rent", "Rent vs local band (MOCK)", 0.10, f"Rs {psf:,.0f}/sq ft/month", s, st, note))
    return checks


def site_score(checks: list[Check]) -> float:
    """Weighted mean over captured checks; unknowns count as neutral 50 so gaps neither help nor hide."""
    return round(sum((c.score if c.score is not None else 50.0) * c.weight for c in checks)
                 / sum(c.weight for c in checks), 1)


MIN_SITE_FOR_PROCEED = 55.0  # a great location can't rescue an unsuitable unit
MAX_POOR_FOR_PROCEED = 1


def recommend(total: float, blockers: list[str], high_risks: int, site: float = 100.0, poor_checks: int = 0) -> str:
    if blockers:
        return "reject"
    if (total >= PROCEED_AT and high_risks == 0 and site >= MIN_SITE_FOR_PROCEED
            and poor_checks <= MAX_POOR_FOR_PROCEED):
        return "proceed"
    return "review"


# --- Public context around the pin ---------------------------------------------------------

def gather_context(db: Session, lat: float, lon: float, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    pt = {"lat": lat, "lon": lon}
    center = h3.latlng_to_cell(lat, lon, 9)
    cells = list(h3.grid_disk(center, CATCHMENT_K))
    ring = list(set(h3.grid_disk(center, CATCHMENT_K + 2)) - set(cells))
    model = cell_model_metrics(db, cells, ring)
    near = db.execute(text("""
        SELECT store_code, name,
               ST_Distance(geom::geography, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography) AS d
          FROM ref.savomart_store ORDER BY geom <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326) LIMIT 3
    """), pt).all()
    competitors = [dict(r._mapping) for r in db.execute(text("""
        SELECT coalesce(name, initcap(replace(subcategory, '_', ' '))) AS name, competitor_tier AS tier,
               round(ST_Distance(geom::geography, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography)) AS dist_m
          FROM ref.osm_poi
         WHERE competitor_tier > 0
           AND ST_DWithin(geom::geography, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, 500)
         ORDER BY 3
    """), pt)]
    road = db.execute(text("""
        SELECT name, highway,
               round(ST_Distance(geom::geography, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography)) AS dist_m
          FROM ref.lane_segment
         WHERE ST_DWithin(geom::geography, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, 60)
         ORDER BY geom <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326) LIMIT 1
    """), pt).first()
    band = db.execute(text("""
        SELECT r.pincode, r.tier, r.rent_psf_min AS min, r.rent_psf_max AS max
          FROM ref.pincode p JOIN ref.rent_band_mock r USING (pincode)
         WHERE ST_Contains(p.geom, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326))
         ORDER BY p.area_km2 LIMIT 1
    """), pt).first()
    footfall = [dict(r._mapping) for r in db.execute(text("""
        SELECT category, count(*) AS n FROM ref.osm_poi
         WHERE footfall_weight >= 1 AND category NOT IN ('grocery', 'own_store')
           AND ST_DWithin(geom::geography, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, 500)
         GROUP BY 1 ORDER BY 2 DESC
    """), pt)]

    ctx = {
        "model": {**model, "nearest_store_km": round(near[0].d / 1000, 2)},
        "population_1km": model["population"],
        "population_source": "Census 2011 baseline + OSM buildings",
        "nearest_stores": [{"code": r.store_code, "name": r.name, "distance_km": round(r.d / 1000, 2)} for r in near],
        "competitors_500m": competitors,
        "frontage_road": dict(road._mapping) if road else None,
        "rent_band": ({"pincode": band.pincode, "tier": band.tier, "min": band.min, "max": band.max, "is_mock": True}
                      if band else None),
        "footfall_500m": footfall,
    }
    if overrides:  # ground truth from a completed catchment study (M3) replaces modelled values
        ctx["overrides"] = overrides
        m = ctx["model"]
        ctx["modelled"] = {"pop_density": m["pop_density"], "comp_per_10k": m["comp_per_10k"]}
        if overrides.get("demand_factor"):
            m["pop_density"] = round(m["pop_density"] * overrides["demand_factor"], 1)
            ctx["population_1km"] = round(ctx["population_1km"] * overrides["demand_factor"])
            ctx["population_source"] = overrides.get("source", "catchment survey")
        if overrides.get("comp_per_10k") is not None:
            # OSM under-maps kiranas; never let the survey *lower* competition below what's mapped.
            m["comp_per_10k"] = max(m["comp_per_10k"], overrides["comp_per_10k"])
    return ctx


def assess(db: Session, details: dict[str, Any], ctx: dict[str, Any], flags: list[dict[str, Any]]) -> dict[str, Any]:
    stats = dict(db.execute(text("SELECT metric, breakpoints FROM ref.metric_stats")).all())
    loc_total, subs = score_metrics(ctx["model"], stats)
    checks = site_checks(details, ctx["rent_band"])
    site = site_score(checks)
    total = round(LOCATION_WEIGHT * loc_total + SITE_WEIGHT * site, 1)
    subs_d = subs_as_dicts(subs)

    insights: list[dict[str, Any]] = []
    risks: list[dict[str, Any]] = []
    blockers: list[str] = []

    for s in sorted(subs_d, key=lambda x: -x["score"]):
        if s["score"] >= 70 and s["key"] != "network":
            insights.append({"code": f"LOC_{s['key'].upper()}", "text": f"{s['label']} around the site is strong "
                             f"({s['score']:.0f}/100)", "fact_ids": [f"loc_{s['key']}"]})
    pop = ctx["population_1km"]
    insights.append({"code": "CATCHMENT_POP", "text": f"About {pop:,} residents live within ~1 km "
                     f"({ctx['population_source']})", "fact_ids": ["population_1km"]})
    modelled = ctx.get("modelled")
    if modelled:
        m = ctx["model"]
        change = m["pop_density"] / modelled["pop_density"] - 1 if modelled["pop_density"] else 0
        item = {"code": "SURVEY_DEMAND", "fact_ids": ["population_1km"],
                "text": f"Ground survey puts density at {m['pop_density']:,.0f}/km² vs {modelled['pop_density']:,.0f} "
                        f"modelled ({change:+.0%}), from {ctx['population_source']}"}
        (insights if change >= 0 else risks).append(item if change >= 0 else {**item, "severity": "medium"})
        if m["comp_per_10k"] > modelled["comp_per_10k"] * 1.2:
            risks.append({"code": "SURVEY_COMPETITION", "severity": "medium", "fact_ids": [],
                          "text": "Surveyors found more grocery shops than OpenStreetMap shows; "
                                  "competition is higher than the desk estimate"})
    road = ctx["frontage_road"]
    if road and road["highway"] in ("primary", "secondary", "trunk", "tertiary"):
        insights.append({"code": "ARTERIAL_FRONTAGE", "text": f"Fronts {road['name'] or 'a ' + road['highway'] + ' road'}"
                         f", an arterial with passing traffic", "fact_ids": []})
    for c in checks:
        if c.status == "good":
            insights.append({"code": f"SITE_{c.key.upper()}", "text": f"{c.label}: {c.value}. {c.note}",
                             "fact_ids": [f"check_{c.key}"]})
        elif c.status == "blocker":
            blockers.append(c.key)
            risks.append({"code": f"BLOCKER_{c.key.upper()}", "severity": "high",
                          "text": f"{c.label}: {c.value}. {c.note}", "fact_ids": [f"check_{c.key}"]})
        elif c.status == "poor":
            risks.append({"code": f"SITE_{c.key.upper()}", "severity": "medium",
                          "text": f"{c.label}: {c.value}. {c.note}", "fact_ids": [f"check_{c.key}"]})
        elif c.status == "unknown":
            risks.append({"code": f"MISSING_{c.key.upper()}", "severity": "low",
                          "text": c.note, "fact_ids": []})

    nearest = ctx["nearest_stores"][0]
    if nearest["distance_km"] < CANNIBALISATION_KM:
        blockers.append("cannibalisation")
        risks.append({"code": "CANNIBALISATION", "severity": "high",
                      "text": f"Only {nearest['distance_km']} km from Savomart {nearest['name']}: would split its customers",
                      "fact_ids": ["nearest_store_km"]})
    elif nearest["distance_km"] < 2.0:
        risks.append({"code": "NEAR_OWN_STORE", "severity": "medium",
                      "text": f"{nearest['distance_km']} km from Savomart {nearest['name']}: catchments overlap",
                      "fact_ids": ["nearest_store_km"]})

    chains = [c for c in ctx["competitors_500m"] if c["tier"] == 3]
    if chains:
        risks.append({"code": "CHAIN_NEARBY", "severity": "medium",
                      "text": f"{len(chains)} organised chain outlet(s) within 500 m, nearest {chains[0]['name']} "
                              f"at {chains[0]['dist_m']:.0f} m", "fact_ids": ["chains_500m"]})
    elif not ctx["competitors_500m"]:
        insights.append({"code": "NO_MAPPED_COMPETITION", "text": "No grocery competitors mapped within 500 m "
                         "(OSM may miss kiranas; confirm on the visit)", "fact_ids": ["competitors_500m"]})

    for f in flags:
        if f["code"] in FLAGS_COVERED_BY_CHECKS:
            continue
        # Severity comes from current policy, not what was stored at capture time.
        sev = FLAG_SEVERITY.get(f["code"], f.get("severity", "medium"))
        risks.append({"code": f["code"], "severity": sev, "text": f["message"], "fact_ids": []})

    high = sum(1 for r in risks if r["severity"] == "high")
    poor = sum(1 for c in checks if c.status == "poor")
    rec = recommend(total, blockers, high, site, poor)
    if rec == "review" and not high and poor > MAX_POOR_FOR_PROCEED:
        risks.append({"code": "WEAK_SITE", "severity": "medium", "fact_ids": ["site_score"],
                      "text": f"{poor} site checks are poor: a strong location doesn't make up for an unsuitable unit"})
    sev_order = {"high": 0, "medium": 1, "low": 2}
    risks.sort(key=lambda r: sev_order.get(r["severity"], 3))
    return {
        "score": total, "location_score": loc_total, "site_score": site, "recommendation": rec,
        "location_subs": subs_d, "checks": [asdict(c) for c in checks], "insights": insights[:6],
        "risks": risks, "blockers": blockers,
    }


def build_facts(details: dict[str, Any], ctx: dict[str, Any], a: dict[str, Any]) -> dict[str, dict[str, Any]]:
    f: dict[str, dict[str, Any]] = {}

    def add(fid, label, value, unit="", source="derived"):
        f[fid] = {"label": label, "value": value, "unit": unit, "source": source}

    add("score", "Overall property score", a["score"], "/100", "SiteScout evaluation v1")
    add("location_score", "Location score", a["location_score"], "/100", "SiteScout model v1")
    add("site_score", "Site score", a["site_score"], "/100", "SiteScout evaluation v1")
    add("recommendation", "Recommendation", a["recommendation"])
    add("population_1km", "Residents within ~1 km", ctx["population_1km"], "people", ctx["population_source"])
    add("nearest_store_km", f"Distance to Savomart {ctx['nearest_stores'][0]['name']}",
        ctx["nearest_stores"][0]["distance_km"], "km", "Savomart Stores API")
    add("competitors_500m", "Grocery competitors within 500 m", len(ctx["competitors_500m"]), "shops", "OSM")
    add("chains_500m", "Organised chain outlets within 500 m",
        sum(1 for c in ctx["competitors_500m"] if c["tier"] == 3), "shops", "OSM")
    if details.get("carpet_sqft"):
        add("carpet_sqft", "Carpet area", details["carpet_sqft"], "sq ft", "field capture")
    if details.get("rent_monthly"):
        add("rent_monthly", "Monthly rent", details["rent_monthly"], "INR", "field capture")
        if details.get("carpet_sqft"):
            add("rent_psf", "Rent per sq ft", round(details["rent_monthly"] / details["carpet_sqft"]), "INR/sq ft",
                "field capture")
    if ctx["rent_band"]:
        add("rent_band_min", "Local rent band low (MOCK)", ctx["rent_band"]["min"], "INR/sq ft", "MOCK")
        add("rent_band_max", "Local rent band high (MOCK)", ctx["rent_band"]["max"], "INR/sq ft", "MOCK")
    for s in a["location_subs"]:
        add(f"loc_{s['key']}", f"Location: {s['label']}", s["score"], "/100", "SiteScout model v1")
    for c in a["checks"]:
        if c["score"] is not None:
            add(f"check_{c['key']}", f"Site: {c['label']}", c["score"], "/100", "SiteScout evaluation v1")
    return f


def template_narrative(name: str, a: dict[str, Any]) -> dict[str, Any]:
    rec_text = {"proceed": "worth pursuing", "review": "worth a closer look before deciding",
                "reject": "not suitable as captured"}[a["recommendation"]]
    top_risk = a["risks"][0]["text"] if a["risks"] else "No material risks found."
    return {
        "headline": f"{name}: {a['score']:.0f}/100, {rec_text}.",
        "summary": (f"Location scores {a['location_score']:.0f}/100 and the site itself {a['site_score']:.0f}/100. "
                    f"Main concern: {top_risk}"),
        "reasons": [{"text": i["text"], "fact_ids": i["fact_ids"]} for i in a["insights"][:3]],
        "risks": [{"text": r["text"], "fact_ids": r["fact_ids"]} for r in a["risks"][:3]],
        "next_step": {"proceed": "Shortlist and schedule a site visit.",
                      "review": "Resolve the listed risks (visit or call the landlord), then decide.",
                      "reject": "Reject, or ask the executive to correct the captured details if they were wrong."
                      }[a["recommendation"]],
        "caveats": [],
    }
