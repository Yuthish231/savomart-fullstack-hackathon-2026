import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import APP, Base, Timestamps, UUIDPk


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"  # core output present, an optional step (e.g. LLM) failed
    FAILED = "failed"


TERMINAL = {JobStatus.COMPLETED, JobStatus.PARTIAL, JobStatus.FAILED}


class Job(UUIDPk, Timestamps, Base):
    """Postgres-backed job queue row. Workers claim with FOR UPDATE SKIP LOCKED."""

    __tablename__ = "job"
    __table_args__ = (
        Index(
            "ix_job_queued",
            "run_after",
            postgresql_where=text("status = 'queued'"),
        ),
        {"schema": APP},
    )

    type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default=JobStatus.QUEUED)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    # [{"name": "aggregate", "label": "Gathering data", "status": "pending|running|done|failed|skipped",
    #   "started_at": ..., "finished_at": ..., "error": ...}]
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(default=3, nullable=False)
    run_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    locked_by: Mapped[str | None] = mapped_column(String(64))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{APP}.user.id", ondelete="SET NULL")
    )
