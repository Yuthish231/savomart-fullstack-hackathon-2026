"""Property onboarding: input sanity flags, duplicate detection, evaluation queueing."""

import uuid
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.jobs.queue import enqueue
from app.models import Property, PropertyEvaluation

PIN_GPS_MAX_M = 150
GPS_ACCURACY_WARN_M = 100
DUP_RADIUS_M = 50
DUP_NAME_SIMILARITY = 0.35

EVAL_STEPS = [("context", "Gathering data around the site"), ("assess", "Checking the site"),
              ("narrative", "Writing the summary")]


def in_region(db: Session, lat: float, lon: float) -> bool:
    return bool(db.scalar(text("""
        SELECT EXISTS (SELECT 1 FROM ref.boundary_sub
                        WHERE key = 'cma' AND ST_Intersects(geom, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)))
    """), {"lat": lat, "lon": lon}))


def find_duplicates(db: Session, lat: float, lon: float, name: str, landmark: str | None,
                    exclude: uuid.UUID | None = None) -> list[dict[str, Any]]:
    """Nearby properties that look like the same place: within 50 m and a similar name or
    landmark (trigram), or practically on top of each other (<15 m)."""
    rows = db.execute(text("""
        SELECT p.id, p.code, p.name, p.stage, p.landmark,
               round(ST_Distance(p.pin::geography, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography)) AS dist_m,
               greatest(similarity(lower(p.name), lower(CAST(:name AS text))),
                        similarity(lower(coalesce(p.landmark, '')), lower(coalesce(CAST(:landmark AS text), '')))) AS sim
          FROM app.property p
         WHERE ST_DWithin(p.pin::geography, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :r)
           AND (CAST(:exclude AS text) IS NULL OR p.id <> CAST(:exclude AS uuid))
         ORDER BY dist_m
    """), {"lat": lat, "lon": lon, "name": name or "", "landmark": landmark, "r": DUP_RADIUS_M,
           "exclude": str(exclude) if exclude else None}).all()
    return [dict(r._mapping) | {"id": str(r.id), "sim": round(float(r.sim), 2)}
            for r in rows if r.dist_m < 15 or r.sim >= DUP_NAME_SIMILARITY]


def compute_flags(db: Session, lat: float, lon: float, gps: dict[str, float] | None,
                  details: dict[str, Any], duplicates: list[dict[str, Any]],
                  confirmed_not_duplicate: bool) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    if gps and gps.get("lat") is not None:
        d = db.scalar(text("""
            SELECT ST_Distance(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                               ST_SetSRID(ST_MakePoint(:glon, :glat), 4326)::geography)
        """), {"lat": lat, "lon": lon, "glat": gps["lat"], "glon": gps["lon"]})
        if d > PIN_GPS_MAX_M:
            flags.append({"code": "PIN_GPS_MISMATCH", "severity": "high",
                          "message": f"Pin is {d:.0f} m from where the phone was when it was captured; "
                                     "check the pin is on the right building"})
        if (gps.get("accuracy") or 0) > GPS_ACCURACY_WARN_M:
            flags.append({"code": "GPS_WEAK", "severity": "low",
                          "message": f"Phone location was only accurate to about {gps['accuracy']:.0f} m"})
    else:
        flags.append({"code": "NO_GPS", "severity": "low",
                      "message": "Captured without a phone location fix; pin placed by hand"})
    if details.get("rent_monthly") is None:
        flags.append({"code": "RENT_MISSING", "severity": "low",
                      "message": "Rent not captured; evaluation uses the local band only"})
    if duplicates:
        top = duplicates[0]
        flags.append({"code": "DUPLICATE_SUSPECTED" if not confirmed_not_duplicate else "DUPLICATE_DISMISSED",
                      # Unresolved duplicates block "proceed": someone must confirm it is a new site.
                      "severity": "high" if not confirmed_not_duplicate else "low",
                      "message": (f"Looks like {top['code']} ({top['name']}, {top['dist_m']:.0f} m away)"
                                  + ("; executive confirmed it is a different property"
                                     if confirmed_not_duplicate else "")),
                      "related": top["id"]})
    return flags


def next_code(db: Session) -> str:
    n = db.scalar(text("SELECT nextval('app.property_code_seq')"))
    return f"SS-CHN-{n:04d}"


def queue_evaluation(db: Session, prop: Property, trigger: str, actor_id: uuid.UUID | None,
                     overrides: dict[str, Any] | None = None) -> PropertyEvaluation:
    version = (db.scalar(select(func.max(PropertyEvaluation.version))
                         .where(PropertyEvaluation.property_id == prop.id)) or 0) + 1
    ev = PropertyEvaluation(property_id=prop.id, version=version, trigger=trigger, status="queued")
    db.add(ev)
    db.flush()
    job = enqueue(db, "property_eval", {"evaluation_id": str(ev.id), "overrides": overrides or {}},
                  EVAL_STEPS, created_by=actor_id)
    db.flush()
    ev.job_id = job.id
    return ev


def assert_can_view(prop: Property, user) -> None:
    if user.role == "BDE" and prop.created_by != user.id:
        raise AppError("FORBIDDEN", "Executives can only see properties they onboarded", 403)
    if user.role not in ("BDM", "BDE", "SM"):
        raise AppError("FORBIDDEN", "Not available for your role", 403)
