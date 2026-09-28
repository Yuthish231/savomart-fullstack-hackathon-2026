import uuid
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import AppError, NotFound
from app.jobs.queue import enqueue, requeue
from app.jobs.tasks.demo import PING_STEPS
from app.models import DataSource, Job, JobStatus, User

router = APIRouter(tags=["system"])


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict[str, Any]:
    postgis = db.scalar(text("SELECT postgis_lib_version()"))
    return {
        "status": "ok",
        "postgis": postgis,
        "llm": {"model": get_settings().llm_model, "configured": bool(get_settings().llm_api_key)},
    }


class JobOut(BaseModel):
    id: uuid.UUID
    type: str
    status: str
    steps: list[dict[str, Any]]
    error: str | None
    attempts: int


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    job = db.get(Job, job_id)
    if job is None:
        raise NotFound("Job", job_id)
    return JobOut(
        id=job.id, type=job.type, status=job.status, steps=job.steps, error=job.error,
        attempts=job.attempts,
    )


@router.post("/jobs/{job_id}/retry", response_model=JobOut)
def retry_job(job_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    job = db.get(Job, job_id)
    if job is None:
        raise NotFound("Job", job_id)
    if job.status not in (JobStatus.FAILED, JobStatus.PARTIAL):
        raise AppError("JOB_NOT_RETRYABLE", f"Job is {job.status}, only failed or partial jobs can be retried", 409)
    requeue(db, job)
    db.commit()
    return get_job(job_id, db, _)


class PingIn(BaseModel):
    delay_s: float = 1.0
    fail_work: bool = False


@router.post("/jobs/ping", response_model=JobOut, status_code=202)
def ping_job(body: PingIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Demo-only smoke test for the worker, step progress and retry."""
    if not get_settings().demo_mode:
        raise AppError("DEMO_DISABLED", "Only available in demo mode", 403)
    job = enqueue(db, "ping", body.model_dump(), PING_STEPS, created_by=user.id)
    db.commit()
    return get_job(job.id, db, user)


class DataSourceOut(BaseModel):
    key: str
    name: str
    url: str | None
    license: str | None
    as_of: str | None
    fetched_at: str
    is_mock: bool
    row_count: int | None


@router.get("/ref/data-sources", response_model=list[DataSourceOut])
def data_sources(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    rows = db.scalars(select(DataSource).order_by(DataSource.key)).all()
    return [
        DataSourceOut(
            key=r.key, name=r.name, url=r.url, license=r.license,
            as_of=r.as_of.isoformat() if r.as_of else None,
            fetched_at=r.fetched_at.isoformat(), is_mock=r.is_mock, row_count=r.row_count,
        )
        for r in rows
    ]
