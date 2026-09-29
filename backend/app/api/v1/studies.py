"""M3 catchment studies: request → plan/split → assign → lane capture (offline sync) → roll-up."""

import json
import uuid
from datetime import date, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, require_roles
from app.core.errors import AppError, NotFound
from app.models import AreaReport, CatchmentStudy, Job, Property, Role, StudyLane, User, WorkChunk
from app.services import pipeline
from app.services import studies as svc

router = APIRouter(tags=["studies"])
managers = require_roles(Role.BDM, Role.SM)


class StudyIn(BaseModel):
    target_type: Literal["property", "area"]
    property_id: uuid.UUID | None = None
    report_id: uuid.UUID | None = None
    radius_m: int = Field(svc.DEFAULT_RADIUS_M, ge=200, le=1500)
    notes: str | None = Field(None, max_length=1000)
    due_date: date | None = None


@router.post("/studies", status_code=201)
def request_study(body: StudyIn, db: Session = Depends(get_db), user: User = Depends(require_roles(Role.BDM))):
    if body.target_type == "property":
        prop = db.get(Property, body.property_id) if body.property_id else None
        if prop is None:
            raise NotFound("Property", body.property_id)
        study = svc.create_study(db, target_type="property", requested_by=user.id, prop=prop,
                                 radius_m=body.radius_m, notes=body.notes, due_date=body.due_date)
        if prop.stage == "NEGOTIATION":
            pipeline.apply(db, prop, "CATCHMENT_STUDY", role=Role.BDM, actor_id=user.id,
                           reason=f"Requested {study.code}")
    else:
        report = db.get(AreaReport, body.report_id) if body.report_id else None
        if report is None:
            raise NotFound("Report", body.report_id)
        study = svc.create_study(db, target_type="area", requested_by=user.id, report=report,
                                 radius_m=body.radius_m, notes=body.notes, due_date=body.due_date)
    db.commit()
    return _detail(db, study, user)


@router.get("/studies")
def list_studies(status: str | None = None, property_id: uuid.UUID | None = None, report_id: uuid.UUID | None = None,
                 db: Session = Depends(get_db), user: User = Depends(require_roles(Role.BDM, Role.SM, Role.BDE))):
    stmt = select(CatchmentStudy).order_by(CatchmentStudy.created_at.desc()).limit(200)
    if status:
        stmt = stmt.where(CatchmentStudy.status == status)
    if property_id:
        stmt = stmt.where(CatchmentStudy.property_id == property_id)
    if report_id:
        stmt = stmt.where(CatchmentStudy.report_id == report_id)
    return [_summary(db, s) for s in db.scalars(stmt).all()]


@router.get("/studies/{study_id}")
def get_study(study_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _detail(db, _get(db, study_id), user)


@router.get("/studies/{study_id}/lanes.geojson")
def study_lanes(study_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    rows = db.execute(text("""
        SELECT sl.lane_id AS id, sl.status, sl.chunk_id, c.label AS chunk, l.name, l.highway, sl.length_m,
               ST_AsGeoJSON(l.geom, 6) AS g
          FROM app.study_lane sl JOIN ref.lane_segment l ON l.id = sl.lane_id
          LEFT JOIN app.work_chunk c ON c.id = sl.chunk_id
         WHERE sl.study_id = :s
    """), {"s": study_id})
    feats = [{"type": "Feature", "geometry": json.loads(r.g),
              "properties": {k: (str(v) if k == "chunk_id" and v else v) for k, v in r._mapping.items() if k != "g"}}
             for r in rows]
    return {"type": "FeatureCollection", "features": feats}


class PlanIn(BaseModel):
    target_effort_m: float = Field(svc.splitter.TARGET_EFFORT_M, ge=500, le=10_000)


@router.post("/studies/{study_id}/plan")
def plan_study(study_id: uuid.UUID, body: PlanIn, db: Session = Depends(get_db),
               user: User = Depends(require_roles(Role.SM))):
    study = _get(db, study_id)
    svc.plan(db, study, user.id, body.target_effort_m)
    db.commit()
    return _detail(db, study, user)


class ChunkPatch(BaseModel):
    assignee_id: uuid.UUID | None


@router.patch("/chunks/{chunk_id}")
def assign_chunk(chunk_id: uuid.UUID, body: ChunkPatch, db: Session = Depends(get_db),
                 user: User = Depends(require_roles(Role.SM))):
    ch = db.get(WorkChunk, chunk_id)
    if ch is None:
        raise NotFound("Chunk", chunk_id)
    if body.assignee_id:
        se = db.get(User, body.assignee_id)
        if se is None or se.role != Role.SE:
            raise AppError("INVALID_ASSIGNEE", "Chunks go to Survey Executives", 422)
    ch.assignee_id = body.assignee_id
    if ch.status in ("unassigned", "assigned"):
        ch.status = "assigned" if body.assignee_id else "unassigned"
    db.commit()
    return _detail(db, db.get(CatchmentStudy, ch.study_id), user)


class CompleteIn(BaseModel):
    force_reason: str | None = Field(None, max_length=500)


@router.post("/studies/{study_id}/complete")
def complete_study(study_id: uuid.UUID, body: CompleteIn, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.SM))):
    study = _get(db, study_id)
    if study.status not in ("PLANNED", "IN_PROGRESS"):
        raise AppError("STUDY_NOT_OPEN", f"Study is {study.status.lower()}", 409)
    p = svc.progress(db, study.id)
    if p["closed_share"] < svc.COMPLETE_AT and not (body.force_reason or "").strip():
        raise AppError("STUDY_INCOMPLETE",
                       f"Only {p['closed_share']:.0%} of lanes are surveyed; {svc.COMPLETE_AT:.0%} needed "
                       "(or give a reason to close early)", 409, {"progress": p})
    if body.force_reason:
        study.notes = ((study.notes or "") + f"\nClosed early by {user.name}: {body.force_reason}").strip()
    svc.start_rollup(db, study, user.id)
    db.commit()
    return _detail(db, study, user)


class ResurveyIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


@router.post("/studies/{study_id}/resurvey")
def resurvey(study_id: uuid.UUID, body: ResurveyIn, db: Session = Depends(get_db),
             user: User = Depends(require_roles(Role.SM, Role.BDM))):
    """Override reuse: survey every lane again (e.g. the area changed since the earlier study)."""
    study = _get(db, study_id)
    if study.reuse_mode == "none":
        raise AppError("NOTHING_REUSED", "This study doesn't reuse earlier surveys", 409)
    if study.status in ("IN_PROGRESS", "COMPLETING"):
        raise AppError("STUDY_BUSY", "Can't change reuse while fieldwork or roll-up is running", 409)
    db.execute(text("UPDATE app.study_lane SET status = 'todo', reused_survey_id = NULL, chunk_id = NULL "
                    "WHERE study_id = :s AND status = 'reused'"), {"s": study.id})
    study.reuse_mode, study.reuse_coverage, study.reused_study_ids = "none", 0, []
    study.status, study.insight, study.insight_narrative, study.completed_at = "REQUESTED", None, None, None
    study.notes = ((study.notes or "") + f"\nReuse overridden by {user.name}: {body.reason}").strip()
    db.commit()
    return _detail(db, study, user)


# --- Survey executive side -------------------------------------------------------------------

@router.get("/chunks")
def my_chunks(db: Session = Depends(get_db), user: User = Depends(require_roles(Role.SE))):
    rows = db.execute(text("""
        SELECT c.id, c.label, c.status, c.effort_m, c.lane_count, s.id AS study_id, s.code, s.title, s.due_date,
               s.status AS study_status,
               count(sl.*) FILTER (WHERE sl.status IN ('done', 'skipped')) AS closed,
               count(sl.*) FILTER (WHERE sl.status = 'draft') AS drafts
          FROM app.work_chunk c JOIN app.catchment_study s ON s.id = c.study_id
          LEFT JOIN app.study_lane sl ON sl.chunk_id = c.id
         WHERE c.assignee_id = :u AND s.status IN ('PLANNED', 'IN_PROGRESS')
         GROUP BY c.id, s.id ORDER BY s.due_date NULLS LAST, s.code, c.label
    """), {"u": user.id})
    return [dict(r._mapping) for r in rows]


@router.get("/chunks/{chunk_id}")
def chunk_detail(chunk_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ch = db.get(WorkChunk, chunk_id)
    if ch is None:
        raise NotFound("Chunk", chunk_id)
    if user.role == Role.SE and ch.assignee_id != user.id:
        raise AppError("FORBIDDEN", "This chunk is assigned to someone else", 403)
    study = db.get(CatchmentStudy, ch.study_id)
    rows = db.execute(text("""
        SELECT sl.lane_id AS id, sl.status, l.name, l.highway, sl.length_m,
               ST_AsGeoJSON(l.geom, 6) AS g,
               ls.client_uuid, ls.status AS survey_status, ls.data, ls.version, ls.captured_at
          FROM app.study_lane sl JOIN ref.lane_segment l ON l.id = sl.lane_id
          LEFT JOIN LATERAL (SELECT * FROM app.lane_survey x WHERE x.study_id = sl.study_id AND x.lane_id = sl.lane_id
                              ORDER BY x.synced_at DESC LIMIT 1) ls ON true
         WHERE sl.chunk_id = :c
         ORDER BY ST_X(ST_StartPoint(l.geom)), ST_Y(ST_StartPoint(l.geom))
    """), {"c": ch.id})
    lanes = []
    for r in rows:
        m = dict(r._mapping)
        geom = json.loads(m.pop("g"))
        m["survey"] = ({"client_uuid": str(m.pop("client_uuid")), "status": m.pop("survey_status"),
                        "data": m.pop("data"), "version": m.pop("version"), "captured_at": m.pop("captured_at")}
                       if m["client_uuid"] else None)
        for k in ("client_uuid", "survey_status", "data", "version", "captured_at"):
            m.pop(k, None)
        lanes.append({"type": "Feature", "geometry": geom, "properties": m})
    return {"chunk": {"id": ch.id, "label": ch.label, "status": ch.status, "effort_m": ch.effort_m,
                      "lane_count": ch.lane_count},
            "study": {"id": study.id, "code": study.code, "title": study.title, "status": study.status,
                      "due_date": study.due_date},
            "lanes": {"type": "FeatureCollection", "features": lanes}}


class LaneData(BaseModel):
    housing_type: Literal["independent", "apartments", "mixed", "informal", "commercial"] | None = None
    dwellings_bucket: Literal["0-10", "11-25", "26-50", "51-100", "100+"] | None = None
    dwellings_exact: int | None = Field(None, ge=0, le=2000)
    condition: Literal["new", "maintained", "old", "dilapidated"] | None = None
    vehicles: Literal["mostly_2w", "mixed", "many_cars"] | None = None
    kiranas: int | None = Field(None, ge=0, le=100)
    kirana_names: str | None = Field(None, max_length=300)
    organised_present: bool | None = None
    footfall: Literal["low", "medium", "high"] | None = None
    delivery_access: Literal["truck", "van", "two_wheeler", "none"] | None = None
    skip_reason: Literal["gated", "under_construction", "not_residential", "inaccessible", "other"] | None = None
    notes: str | None = Field(None, max_length=500)
    gps: dict[str, float] | None = None


class LaneSurveyIn(BaseModel):
    study_id: uuid.UUID
    lane_id: str
    status: Literal["draft", "submitted", "skipped"]
    data: LaneData
    base_version: int | None = None
    captured_at: datetime

    @model_validator(mode="after")
    def complete_enough(self):
        d = self.data
        if self.status == "submitted" and (not d.housing_type or (d.dwellings_bucket is None and d.dwellings_exact is None)
                                           or d.kiranas is None):
            raise ValueError("A submitted lane needs housing type, dwellings and kirana count")
        if self.status == "skipped" and not d.skip_reason:
            raise ValueError("A skipped lane needs a reason")
        return self


@router.put("/lane-surveys/{client_uuid}")
def put_lane_survey(client_uuid: uuid.UUID, body: LaneSurveyIn, db: Session = Depends(get_db),
                    user: User = Depends(require_roles(Role.SE, Role.SM))):
    """Idempotent: the phone retries the same client_uuid until it gets a 200."""
    study = _get(db, body.study_id)
    s, conflict = svc.save_survey(db, client_uuid=client_uuid, user=user, study=study, lane_id=body.lane_id,
                                  status=body.status, data=body.data.model_dump(exclude_none=True),
                                  base_version=body.base_version, captured_at=body.captured_at)
    if conflict:
        db.rollback()
        raise AppError("VERSION_CONFLICT", "This lane was changed on the server since your last sync", 409,
                       {"server": {"version": s.version, "status": s.status, "data": s.data}})
    db.commit()
    return {"client_uuid": str(client_uuid), "version": s.version, "status": s.status,
            "synced_at": s.synced_at.isoformat()}


# --- helpers ----------------------------------------------------------------------------------

def _get(db: Session, study_id: uuid.UUID) -> CatchmentStudy:
    s = db.get(CatchmentStudy, study_id)
    if s is None:
        raise NotFound("Study", study_id)
    return s


def _summary(db: Session, s: CatchmentStudy) -> dict[str, Any]:
    requester = db.get(User, s.requested_by)
    prop = db.get(Property, s.property_id) if s.property_id else None
    return {"id": s.id, "code": s.code, "title": s.title, "target_type": s.target_type, "status": s.status,
            "reuse_mode": s.reuse_mode, "reuse_coverage": s.reuse_coverage, "radius_m": s.radius_m,
            "due_date": s.due_date, "created_at": s.created_at, "completed_at": s.completed_at,
            "requested_by": requester.name if requester else None,
            "property": {"id": prop.id, "code": prop.code, "name": prop.name, "stage": prop.stage} if prop else None,
            "report_id": s.report_id, "progress": svc.progress(db, s.id),
            "households_est": (s.insight or {}).get("households_est")}


def _detail(db: Session, s: CatchmentStudy, user: User) -> dict[str, Any]:
    chunks = db.execute(text("""
        SELECT c.id, c.label, c.status, c.effort_m, c.lane_count, c.assignee_id, u.name AS assignee,
               (SELECT count(*) FROM app.study_lane sl WHERE sl.chunk_id = c.id AND sl.status IN ('done', 'skipped')) AS closed,
               (SELECT count(*) FROM app.study_lane sl WHERE sl.chunk_id = c.id AND sl.status = 'draft') AS drafts,
               (SELECT max(ls.synced_at) FROM app.lane_survey ls WHERE ls.chunk_id = c.id) AS last_sync
          FROM app.work_chunk c LEFT JOIN app."user" u ON u.id = c.assignee_id
         WHERE c.study_id = :s ORDER BY c.label
    """), {"s": s.id})
    job = db.get(Job, s.job_id) if s.job_id else None
    geom = json.loads(db.scalar(text("SELECT ST_AsGeoJSON(geom, 6) FROM app.catchment_study WHERE id = :i"),
                                {"i": s.id}))
    team = db.execute(text("""
        SELECT u.id, u.name,
               (SELECT count(*) FROM app.work_chunk c JOIN app.catchment_study st ON st.id = c.study_id
                 WHERE c.assignee_id = u.id AND c.status <> 'done' AND st.status IN ('PLANNED', 'IN_PROGRESS')) AS open_chunks
          FROM app."user" u WHERE u.role = 'SE' AND u.is_active ORDER BY u.name
    """)) if user.role == Role.SM else []
    return _summary(db, s) | {
        "notes": s.notes, "total_length_m": s.total_length_m,
        "reused_studies": [dict(x._mapping) | {"id": str(x.id)} for x in db.execute(text(
            "SELECT id, code, completed_at FROM app.catchment_study WHERE id = ANY(CAST(:ids AS uuid[]))"),
            {"ids": s.reused_study_ids})],
        "chunks": [dict(c._mapping) for c in chunks],
        "insight": s.insight, "insight_narrative": s.insight_narrative,
        "job": {"status": job.status, "steps": job.steps, "error": job.error} if job else None,
        "geometry": geom,
        "team": [dict(t._mapping) for t in team],
        "can_complete_at": svc.COMPLETE_AT,
    }
