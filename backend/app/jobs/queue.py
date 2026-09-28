"""Postgres-backed job queue: enqueue, claim, checkpointed steps."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models import Job, JobStatus


def _now() -> str:
    return datetime.now(UTC).isoformat()


def enqueue(
    db: Session,
    job_type: str,
    payload: dict[str, Any],
    steps: list[tuple[str, str]],
    created_by: uuid.UUID | None = None,
) -> Job:
    """Adds a job to the session; the caller commits it together with its domain row."""
    job = Job(
        type=job_type,
        status=JobStatus.QUEUED,
        payload=payload,
        steps=[{"name": n, "label": label, "status": "pending"} for n, label in steps],
        created_by=created_by,
    )
    db.add(job)
    return job


_CLAIM_SQL = text(
    """
    UPDATE app.job
       SET status = 'running', locked_by = :worker, heartbeat_at = now(),
           attempts = attempts + 1, updated_at = now()
     WHERE id = (
            SELECT id FROM app.job
             WHERE status = 'queued' AND run_after <= now()
             ORDER BY created_at
             FOR UPDATE SKIP LOCKED
             LIMIT 1)
    RETURNING id
    """
)

_REAP_SQL = text(
    """
    UPDATE app.job
       SET status = 'queued', locked_by = NULL, updated_at = now()
     WHERE status = 'running' AND heartbeat_at < now() - make_interval(secs => :stale_s)
    RETURNING id
    """
)


def claim(db: Session, worker_id: str) -> uuid.UUID | None:
    job_id = db.scalar(_CLAIM_SQL, {"worker": worker_id})
    db.commit()
    return job_id


def reap_stale(db: Session, stale_s: int = 120) -> list[uuid.UUID]:
    ids = list(db.scalars(_REAP_SQL, {"stale_s": stale_s}))
    db.commit()
    return ids


def requeue(db: Session, job: Job) -> None:
    """Manual retry: finished steps keep status 'done' and are skipped on the next run."""
    for step in job.steps:
        if step["status"] in ("failed", "running", "skipped"):
            step["status"] = "pending"
            step.pop("error", None)
    flag_modified(job, "steps")
    job.status = JobStatus.QUEUED
    job.error = None
    job.attempts = 0
    job.run_after = datetime.now(UTC)


class StepFailed(Exception):
    pass


class JobContext:
    """Handed to task handlers. `run_step` persists progress after every step so the
    UI can show it live, and a retry resumes from the first unfinished step."""

    def __init__(self, db: Session, job: Job) -> None:
        self.db = db
        self.job = job
        self.payload = job.payload
        self.optional_failures: list[str] = []

    def _step(self, name: str) -> dict[str, Any]:
        for s in self.job.steps:
            if s["name"] == name:
                return s
        raise KeyError(f"Job {self.job.type} has no step {name!r}")

    def _save(self) -> None:
        flag_modified(self.job, "steps")
        self.db.commit()

    def run_step(self, name: str, fn: Callable[[], Any], *, optional: bool = False) -> Any:
        step = self._step(name)
        if step["status"] == "done":
            return None
        step.update(status="running", started_at=_now())
        step.pop("error", None)
        self._save()
        try:
            out = fn()
        except Exception as exc:
            self.db.rollback()
            step = self._step(name)
            step.update(status="failed", finished_at=_now(), error=str(exc)[:500])
            self._save()
            if optional:
                self.optional_failures.append(name)
                return None
            raise StepFailed(f"{step.get('label', name)} failed: {exc}") from exc
        step.update(status="done", finished_at=_now())
        self._save()
        return out
