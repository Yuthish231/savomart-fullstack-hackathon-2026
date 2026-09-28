"""Job worker. Run with: python -m app.jobs.worker

Claims one job at a time (FOR UPDATE SKIP LOCKED, so several workers can run safely),
heartbeats while it works, and re-queues jobs whose worker died.
"""

import logging
import os
import socket
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

import app.jobs.tasks  # noqa: F401  (registers handlers)
from app.core.db import SessionLocal
from app.jobs.queue import JobContext, StepFailed, claim, reap_stale
from app.jobs.registry import get_handler
from app.models import Job, JobStatus

log = logging.getLogger("worker")

POLL_S = 1.0
HEARTBEAT_S = 10
STALE_S = 120


def _heartbeat(job_id: uuid.UUID, stop: threading.Event) -> None:
    while not stop.wait(HEARTBEAT_S):
        with SessionLocal() as db:
            db.execute(
                text("UPDATE app.job SET heartbeat_at = now() WHERE id = :id"), {"id": job_id}
            )
            db.commit()


def run_job(job_id: uuid.UUID) -> None:
    stop = threading.Event()
    hb = threading.Thread(target=_heartbeat, args=(job_id, stop), daemon=True)
    hb.start()
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        handler = get_handler(job.type)
        if handler is None:
            job.status, job.error = JobStatus.FAILED, f"No handler for job type {job.type!r}"
            db.commit()
            return
        ctx = JobContext(db, job)
        try:
            handler(ctx)
        except Exception as exc:
            db.rollback()
            job = db.get(Job, job_id)
            job.error = str(exc)[:1000]
            if job.attempts < job.max_attempts and not isinstance(exc, StepFailed):
                # Unexpected crash: back off and retry. Step failures surface to the user
                # immediately; they can press Retry.
                job.status = JobStatus.QUEUED
                job.run_after = datetime.now(UTC) + timedelta(seconds=5 * 2**job.attempts)
            else:
                job.status = JobStatus.FAILED
            job.locked_by = None
            db.commit()
            log.warning("job %s (%s) failed: %s", job_id, job.type, exc)
            return
        job.status = JobStatus.PARTIAL if ctx.optional_failures else JobStatus.COMPLETED
        job.locked_by = None
        db.commit()
        log.info("job %s (%s) -> %s", job_id, job.type, job.status)
    finally:
        stop.set()
        db.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    log.info("worker %s started", worker_id)
    last_reap = 0.0
    while True:
        try:
            with SessionLocal() as db:
                if time.monotonic() - last_reap > 30:
                    if reaped := reap_stale(db, STALE_S):
                        log.warning("re-queued stale jobs: %s", reaped)
                    last_reap = time.monotonic()
                job_id = claim(db, worker_id)
            if job_id is None:
                time.sleep(POLL_S)
                continue
            run_job(job_id)
        except KeyboardInterrupt:
            log.info("worker stopping")
            return
        except Exception:
            log.exception("worker loop error; backing off")
            time.sleep(5)


if __name__ == "__main__":
    main()
