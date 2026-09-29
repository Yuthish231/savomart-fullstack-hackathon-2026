"""M1 Area Intelligence: select areas, run and read Area Fitness Reports."""

import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, require_roles
from app.core.errors import AppError, NotFound
from app.jobs.queue import enqueue, requeue
from app.jobs.tasks.area_report import STEPS as REPORT_STEPS
from app.models import Area, AreaReport, Job, JobStatus, Role, User
from app.services import areas as area_svc
from app.services.scoring import SCORING_VERSION

router = APIRouter(tags=["areas"])
bdm_only = require_roles(Role.BDM)


class AreaIn(BaseModel):
    type: Literal["pincode", "locality", "cells"]
    pincode: str | None = Field(None, pattern=r"^6\d{5}$")
    query: str | None = None
    place_id: str | None = None
    cells: list[str] | None = None


class AreaOut(BaseModel):
    id: uuid.UUID
    name: str
    selection_type: str
    selection_input: dict[str, Any]
    area_km2: float
    n_cells: int
    geometry: dict[str, Any]
    created_at: datetime


def _area_out(db: Session, a: Area) -> AreaOut:
    return AreaOut(id=a.id, name=a.name, selection_type=a.selection_type, selection_input=a.selection_input,
                   area_km2=a.area_km2, n_cells=len(a.h3_cells),
                   geometry=area_svc.get_area_geojson(db, a.id), created_at=a.created_at)


@router.get("/areas/localities")
def localities(q: str = Query(..., min_length=3, max_length=100), db: Session = Depends(get_db),
               _: User = Depends(bdm_only)) -> list[dict[str, Any]]:
    """Search localities (Nominatim, cached). Call on submit, not per keystroke."""
    return [{k: v for k, v in r.items() if k != "geojson"} | {"has_boundary": bool(r.get("geojson"))
             and r["geojson"].get("type") in ("Polygon", "MultiPolygon")}
            for r in area_svc.search_localities(db, q)]


@router.post("/areas", response_model=AreaOut, status_code=201)
def create_area(body: AreaIn, db: Session = Depends(get_db), user: User = Depends(bdm_only)):
    if body.type == "pincode":
        if not body.pincode:
            raise AppError("VALIDATION_ERROR", "pincode is required", 422)
        area = area_svc.from_pincode(db, body.pincode, user.id)
    elif body.type == "locality":
        if not (body.query and body.place_id):
            raise AppError("VALIDATION_ERROR", "query and place_id are required", 422)
        area = area_svc.from_locality(db, body.query, body.place_id, user.id)
    else:
        area = area_svc.from_cells(db, body.cells or [], user.id)
    db.commit()
    return _area_out(db, area)


@router.get("/areas/{area_id}", response_model=AreaOut)
def get_area(area_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    a = db.get(Area, area_id)
    if a is None:
        raise NotFound("Area", area_id)
    return _area_out(db, a)


# --- Reports -----------------------------------------------------------------------------

class ReportSummary(BaseModel):
    id: uuid.UUID
    area_id: uuid.UUID
    area_name: str
    selection_type: str
    area_km2: float
    status: str
    overall_score: float | None
    grade: str | None
    confidence: str | None
    created_at: datetime
    completed_at: datetime | None


class ReportOut(ReportSummary):
    scoring_version: str
    confidence_reasons: list[str] | None
    metrics: dict[str, Any] | None
    sub_scores: list[dict[str, Any]] | None
    hotspots: list[dict[str, Any]] | None
    facts: dict[str, Any] | None
    narrative: dict[str, Any] | None
    narrative_source: str | None
    llm_model: str | None
    data_sources: list[dict[str, Any]] | None
    error: str | None
    job: dict[str, Any] | None
    area_geometry: dict[str, Any]
    created_by_name: str


def _summary(r: AreaReport, a: Area) -> dict[str, Any]:
    return dict(id=r.id, area_id=a.id, area_name=a.name, selection_type=a.selection_type,
                area_km2=a.area_km2, status=r.status, overall_score=r.overall_score, grade=r.grade,
                confidence=r.confidence, created_at=r.created_at, completed_at=r.completed_at)


def _report_out(db: Session, r: AreaReport) -> ReportOut:
    a = db.get(Area, r.area_id)
    job = db.get(Job, r.job_id) if r.job_id else None
    author = db.get(User, r.created_by)
    return ReportOut(
        **_summary(r, a), scoring_version=r.scoring_version, confidence_reasons=r.confidence_reasons,
        metrics=r.metrics, sub_scores=r.sub_scores, hotspots=r.hotspots, facts=r.facts,
        narrative=r.narrative, narrative_source=r.narrative_source, llm_model=r.llm_model,
        data_sources=r.data_sources, error=r.error,
        job={"id": str(job.id), "status": job.status, "steps": job.steps, "error": job.error} if job else None,
        area_geometry=area_svc.get_area_geojson(db, a.id), created_by_name=author.name if author else "",
    )


@router.post("/areas/{area_id}/reports", response_model=ReportOut, status_code=202)
def run_report(area_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(bdm_only)):
    area = db.get(Area, area_id)
    if area is None:
        raise NotFound("Area", area_id)
    report = AreaReport(area_id=area.id, status="queued", scoring_version=SCORING_VERSION, created_by=user.id)
    db.add(report)
    db.flush()
    job = enqueue(db, "area_report", {"report_id": str(report.id)}, REPORT_STEPS, created_by=user.id)
    db.flush()
    report.job_id = job.id
    db.commit()
    return _report_out(db, report)


@router.get("/reports", response_model=list[ReportSummary])
def list_reports(area_id: uuid.UUID | None = None, db: Session = Depends(get_db),
                 _: User = Depends(require_roles(Role.BDM, Role.BDE, Role.SM))):
    stmt = (select(AreaReport, Area).join(Area, Area.id == AreaReport.area_id)
            .order_by(AreaReport.created_at.desc()).limit(100))
    if area_id:
        stmt = stmt.where(AreaReport.area_id == area_id)
    return [ReportSummary(**_summary(r, a)) for r, a in db.execute(stmt).all()]


@router.get("/reports/compare", response_model=list[ReportOut])
def compare_reports(ids: str = Query(..., description="comma-separated report ids (2-4)"),
                    db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    try:
        uids = [uuid.UUID(x) for x in ids.split(",") if x.strip()]
    except ValueError:
        raise AppError("VALIDATION_ERROR", "ids must be report UUIDs", 422)
    if not 2 <= len(uids) <= 4:
        raise AppError("VALIDATION_ERROR", "Compare 2 to 4 reports", 422)
    out = []
    for u in uids:
        r = db.get(AreaReport, u)
        if r is None:
            raise NotFound("Report", u)
        out.append(_report_out(db, r))
    return out


@router.get("/reports/{report_id}", response_model=ReportOut)
def get_report(report_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    r = db.get(AreaReport, report_id)
    if r is None:
        raise NotFound("Report", report_id)
    return _report_out(db, r)


@router.post("/reports/{report_id}/retry", response_model=ReportOut)
def retry_report(report_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(bdm_only)):
    r = db.get(AreaReport, report_id)
    if r is None:
        raise NotFound("Report", report_id)
    job = db.get(Job, r.job_id) if r.job_id else None
    if job is None or job.status not in (JobStatus.FAILED, JobStatus.PARTIAL):
        raise AppError("NOT_RETRYABLE", "Only failed or partially completed reports can be retried", 409)
    requeue(db, job)
    r.status, r.error = "queued", None
    db.commit()
    return _report_out(db, r)
