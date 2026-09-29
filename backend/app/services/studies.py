"""Catchment studies: geometry, lane selection, lane-level reuse, planning, survey capture."""

import string
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.jobs.queue import enqueue
from app.models import AreaReport, CatchmentStudy, LaneSurvey, Property, StudyLane, WorkChunk
from app.services import splitter

DEFAULT_RADIUS_M = 500        # ~6-7 minute walk: a neighbourhood grocery's core catchment
FRESH_DAYS = 180              # older lane surveys are not reused
AGEING_DAYS = 90              # reused but flagged as ageing
FULL_REUSE_AT = 0.8           # >= 80% of lane length already surveyed: no new fieldwork
COMPLETE_AT = 0.9             # share of lanes done/skipped/reused before a study can close
AREA_HOTSPOTS = 3             # area studies sample the top hotspots, not the whole area

ROLLUP_STEPS = [("aggregate", "Rolling up lane surveys"), ("narrative", "Writing the insight"),
                ("apply", "Updating the property / area")]


def next_code(db: Session) -> str:
    n = db.scalar(text("SELECT nextval('app.study_code_seq')"))
    return f"CS-{n:04d}"


def _geom_for_property(db: Session, prop: Property, radius: int) -> str:
    return db.scalar(text("""
        SELECT ST_AsEWKT(ST_Multi(ST_Buffer(pin::geography, :r)::geometry)) FROM app.property WHERE id = :id
    """), {"id": prop.id, "r": radius})


def _geom_for_report(db: Session, report: AreaReport, radius: int) -> str:
    spots = (report.hotspots or [])[:AREA_HOTSPOTS]
    if not spots:
        raise AppError("NO_HOTSPOTS", "This report has no hotspots to survey around", 422)
    pts = ", ".join(f"ST_SetSRID(ST_MakePoint({h['lon']}, {h['lat']}), 4326)" for h in spots)
    return db.scalar(text(f"""
        SELECT ST_AsEWKT(ST_Multi(ST_CollectionExtract(ST_Intersection(
                 ST_Union(ARRAY(SELECT ST_Buffer(p::geography, :r)::geometry FROM unnest(ARRAY[{pts}]) AS p)),
                 (SELECT geom FROM app.area WHERE id = :area)), 3)))
    """), {"r": radius, "area": report.area_id})


def lanes_in(db: Session, study_id: uuid.UUID) -> list[dict[str, Any]]:
    """Surveyable lane segments whose midpoint lies in the study area."""
    return [dict(r._mapping) for r in db.execute(text("""
        SELECT l.id, l.length_m, l.highway, l.start_node, l.end_node,
               ST_Y(ST_LineInterpolatePoint(l.geom, 0.5)) AS lat, ST_X(ST_LineInterpolatePoint(l.geom, 0.5)) AS lon
          FROM ref.lane_segment l, app.catchment_study s
         WHERE s.id = :id AND l.is_surveyable
           AND ST_Intersects(s.geom, ST_LineInterpolatePoint(l.geom, 0.5))
    """), {"id": study_id})]


def reusable_surveys(db: Session, lane_ids: list[str], exclude_study: uuid.UUID) -> dict[str, dict[str, Any]]:
    """Latest completed observation per lane from other studies, if fresh enough."""
    rows = db.execute(text("""
        SELECT DISTINCT ON (ls.lane_id) ls.lane_id, ls.id, ls.study_id, ls.captured_at,
               extract(day FROM now() - ls.captured_at) AS age_days
          FROM app.lane_survey ls
         WHERE ls.lane_id = ANY(:lanes) AND ls.study_id <> :sid AND ls.status IN ('submitted', 'skipped')
           AND ls.captured_at >= now() - make_interval(days => :fresh)
         ORDER BY ls.lane_id, ls.captured_at DESC
    """), {"lanes": lane_ids, "sid": exclude_study, "fresh": FRESH_DAYS})
    return {r.lane_id: dict(r._mapping) for r in rows}


def create_study(db: Session, *, target_type: str, requested_by: uuid.UUID, prop: Property | None = None,
                 report: AreaReport | None = None, radius_m: int = DEFAULT_RADIUS_M, notes: str | None = None,
                 due_date=None) -> CatchmentStudy:
    if target_type == "property":
        active = db.scalar(select(CatchmentStudy).where(
            CatchmentStudy.property_id == prop.id,
            CatchmentStudy.status.in_(["REQUESTED", "PLANNED", "IN_PROGRESS", "COMPLETING"])))
        if active:
            raise AppError("STUDY_EXISTS", f"{active.code} is already open for this property", 409)
        geom, title = _geom_for_property(db, prop, radius_m), f"{prop.code} · {prop.name}"
    else:
        geom = _geom_for_report(db, report, radius_m)
        area_name = db.scalar(text("SELECT name FROM app.area WHERE id = :i"), {"i": report.area_id})
        title = f"Area · {area_name} (top {AREA_HOTSPOTS} hotspots)"
    study = CatchmentStudy(code=next_code(db), target_type=target_type, property_id=prop.id if prop else None,
                           report_id=report.id if report else None, title=title, status="REQUESTED",
                           radius_m=radius_m, notes=notes, due_date=due_date, requested_by=requested_by, geom=geom)
    db.add(study)
    db.flush()
    lanes = lanes_in(db, study.id)
    if not lanes:
        raise AppError("NO_LANES", "No surveyable lanes found in that catchment", 422)
    reuse = reusable_surveys(db, [ln["id"] for ln in lanes], study.id)
    total = sum(ln["length_m"] for ln in lanes)
    reused_len = sum(ln["length_m"] for ln in lanes if ln["id"] in reuse)
    for ln in lanes:
        r = reuse.get(ln["id"])
        db.add(StudyLane(study_id=study.id, lane_id=ln["id"], length_m=ln["length_m"],
                         status="reused" if r else "todo", reused_survey_id=r["id"] if r else None))
    study.total_length_m = round(total, 1)
    study.reuse_coverage = round(reused_len / total, 3) if total else 0
    study.reused_study_ids = sorted({str(r["study_id"]) for r in reuse.values()})
    # full: no new fieldwork; partial: only the lanes nobody has surveyed recently go to the field
    study.reuse_mode = ("full" if study.reuse_coverage >= FULL_REUSE_AT
                        else "partial" if reused_len > 0 else "none")
    if study.reuse_mode == "full":
        start_rollup(db, study, requested_by)
    db.flush()
    return study


def plan(db: Session, study: CatchmentStudy, planner: uuid.UUID, target_effort_m: float) -> list[WorkChunk]:
    if study.status not in ("REQUESTED", "PLANNED"):
        raise AppError("STUDY_STARTED", "Fieldwork has started; chunks can't be re-split", 409)
    db.execute(text("UPDATE app.study_lane SET chunk_id = NULL WHERE study_id = :s"), {"s": study.id})
    db.execute(delete(WorkChunk).where(WorkChunk.study_id == study.id))
    rows = db.execute(text("""
        SELECT l.id, l.length_m, l.highway, l.start_node, l.end_node,
               ST_Y(ST_LineInterpolatePoint(l.geom, 0.5)) AS lat, ST_X(ST_LineInterpolatePoint(l.geom, 0.5)) AS lon
          FROM app.study_lane sl JOIN ref.lane_segment l ON l.id = sl.lane_id
         WHERE sl.study_id = :s AND sl.status = 'todo'
    """), {"s": study.id}).all()
    if not rows:
        raise AppError("NOTHING_TO_SURVEY", "All lanes are covered by existing surveys", 409)
    lat0, lon0 = rows[0].lat, rows[0].lon
    lanes = []
    for r in rows:
        x, y = splitter.to_local_xy(r.lat, r.lon, lat0, lon0)
        lanes.append(splitter.Lane(r.id, r.length_m, r.highway, r.start_node, r.end_node, x, y))
    # Streets that aren't study lanes (arterials, and lanes just outside the clipped circle) still
    # connect the lanes a surveyor walks; treat them as connectors so chunks stay contiguous.
    connectors = [(r.start_node, r.end_node) for r in db.execute(text("""
        SELECT l.start_node, l.end_node FROM ref.lane_segment l, app.catchment_study s
         WHERE s.id = :s AND ST_Intersects(l.geom, ST_Buffer(s.geom::geography, 250)::geometry)
           AND NOT EXISTS (SELECT 1 FROM app.study_lane sl WHERE sl.study_id = s.id AND sl.lane_id = l.id)
    """), {"s": study.id})]
    chunks = splitter.split(lanes, target_effort_m, connectors=connectors)
    # Label chunks west-to-east so A, B, C read naturally on the map.
    by_id = {ln.id: ln for ln in lanes}
    chunks.sort(key=lambda c: sum(by_id[i].x for i in c) / len(c))
    out = []
    for i, ids in enumerate(chunks):
        ch = WorkChunk(study_id=study.id, label=string.ascii_uppercase[i], lane_count=len(ids),
                       effort_m=round(sum(by_id[x].effort for x in ids), 1), status="unassigned")
        db.add(ch)
        db.flush()
        db.execute(text("UPDATE app.study_lane SET chunk_id = :c WHERE study_id = :s AND lane_id = ANY(:ids)"),
                   {"c": ch.id, "s": study.id, "ids": ids})
        out.append(ch)
    study.status, study.planned_by = "PLANNED", planner
    return out


def progress(db: Session, study_id: uuid.UUID) -> dict[str, Any]:
    r = db.execute(text("""
        SELECT count(*) AS lanes,
               count(*) FILTER (WHERE status = 'done') AS done,
               count(*) FILTER (WHERE status = 'skipped') AS skipped,
               count(*) FILTER (WHERE status = 'reused') AS reused,
               count(*) FILTER (WHERE status = 'draft') AS draft,
               coalesce(sum(length_m) FILTER (WHERE status IN ('done', 'skipped', 'reused')), 0) AS closed_m,
               coalesce(sum(length_m), 0) AS total_m
          FROM app.study_lane WHERE study_id = :s
    """), {"s": study_id}).one()._mapping
    d = dict(r)
    d["closed_share"] = round((d["done"] + d["skipped"] + d["reused"]) / d["lanes"], 3) if d["lanes"] else 0
    return d


def save_survey(db: Session, *, client_uuid: uuid.UUID, user, study: CatchmentStudy, lane_id: str,
                status: str, data: dict[str, Any], base_version: int | None, captured_at: datetime,
                is_seed: bool = False) -> tuple[LaneSurvey, bool]:
    """Idempotent upsert keyed by the phone-generated client_uuid. Returns (survey, conflict)."""
    sl = db.get(StudyLane, (study.id, lane_id))
    if sl is None:
        raise AppError("LANE_NOT_IN_STUDY", "That lane isn't part of this study", 422)
    if sl.status == "reused":
        raise AppError("LANE_REUSED", "This lane is covered by an earlier survey", 409)
    chunk = db.get(WorkChunk, sl.chunk_id) if sl.chunk_id else None
    if user.role == "SE" and (chunk is None or chunk.assignee_id != user.id):
        raise AppError("FORBIDDEN", "This lane isn't in one of your assigned chunks", 403)
    if study.status not in ("PLANNED", "IN_PROGRESS"):
        raise AppError("STUDY_CLOSED", f"Study is {study.status.lower()}; captures are closed", 409)

    now = datetime.now(UTC)
    s = db.scalar(select(LaneSurvey).where(LaneSurvey.client_uuid == client_uuid))
    conflict = False
    if s is None:
        # A different device may already hold this lane (reassignment): newest capture wins,
        # but the older one is kept for audit.
        s = LaneSurvey(client_uuid=client_uuid, study_id=study.id, chunk_id=sl.chunk_id, lane_id=lane_id,
                       surveyor_id=user.id, status=status, data=data, version=1, captured_at=captured_at,
                       synced_at=now, is_seed=is_seed)
        db.add(s)
    else:
        if base_version is not None and base_version < s.version:
            conflict = True  # someone changed it since this device last synced
            return s, conflict
        s.status, s.data, s.captured_at, s.synced_at = status, data, captured_at, now
        s.version += 1
    sl.status = {"draft": "draft", "submitted": "done", "skipped": "skipped"}[status]
    if chunk and chunk.status in ("assigned", "unassigned"):
        chunk.status = "in_progress"
    if study.status == "PLANNED":
        study.status = "IN_PROGRESS"
    db.flush()
    if chunk:
        left = db.scalar(text("""SELECT count(*) FROM app.study_lane
                                 WHERE chunk_id = :c AND status IN ('todo', 'draft')"""), {"c": chunk.id})
        chunk.status = "done" if left == 0 else "in_progress"
    return s, conflict


def start_rollup(db: Session, study: CatchmentStudy, actor: uuid.UUID | None) -> None:
    study.status = "COMPLETING"
    job = enqueue(db, "study_rollup", {"study_id": str(study.id)}, ROLLUP_STEPS, created_by=actor)
    db.flush()
    study.job_id = job.id
