"""M3: catchment studies, their lanes, work chunks and lane surveys."""

import uuid
from datetime import date, datetime
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import APP, Base, Timestamps, UUIDPk


class CatchmentStudy(UUIDPk, Timestamps, Base):
    __tablename__ = "catchment_study"
    __table_args__ = (Index("ix_catchment_study_geom", "geom", postgresql_using="gist"),
                      Index("ix_catchment_study_status", "status"), {"schema": APP})

    code: Mapped[str] = mapped_column(String(12), unique=True, nullable=False)
    target_type: Mapped[str] = mapped_column(String(10), nullable=False)  # property|area
    property_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{APP}.property.id", ondelete="SET NULL"))
    report_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{APP}.area_report.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    # REQUESTED -> PLANNED -> IN_PROGRESS -> COMPLETING -> COMPLETED ; REUSED (no fieldwork needed)
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    radius_m: Mapped[int] = mapped_column(Integer, nullable=False)
    reuse_mode: Mapped[str] = mapped_column(String(8), nullable=False, default="none")  # none|partial|full
    reuse_coverage: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    reused_study_ids: Mapped[list[str]] = mapped_column(ARRAY(String(40)), nullable=False, default=list)
    total_length_m: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    due_date: Mapped[date | None] = mapped_column(Date)
    requested_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey(f"{APP}.user.id"), nullable=False)
    planned_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey(f"{APP}.user.id"))
    insight: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    insight_narrative: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey(f"{APP}.job.id", ondelete="SET NULL"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    geom: Mapped[Any] = mapped_column(Geometry("MULTIPOLYGON", srid=4326, spatial_index=False, nullable=False),
                                      nullable=False)


class WorkChunk(UUIDPk, Timestamps, Base):
    """A contiguous, non-overlapping bundle of lanes that one surveyor can walk."""

    __tablename__ = "work_chunk"
    __table_args__ = (Index("ix_work_chunk_study", "study_id"), Index("ix_work_chunk_assignee", "assignee_id"),
                      {"schema": APP})

    study_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{APP}.catchment_study.id", ondelete="CASCADE"), nullable=False)
    label: Mapped[str] = mapped_column(String(4), nullable=False)
    effort_m: Mapped[float] = mapped_column(Float, nullable=False)
    lane_count: Mapped[int] = mapped_column(Integer, nullable=False)
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey(f"{APP}.user.id"))
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="unassigned")  # unassigned|assigned|in_progress|done


class StudyLane(Base):
    """Which lane segments a study covers, their chunk and progress."""

    __tablename__ = "study_lane"
    __table_args__ = (Index("ix_study_lane_chunk", "chunk_id"), {"schema": APP})

    study_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{APP}.catchment_study.id", ondelete="CASCADE"), primary_key=True)
    lane_id: Mapped[str] = mapped_column(String(40), ForeignKey("ref.lane_segment.id"), primary_key=True)
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{APP}.work_chunk.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="todo")  # todo|draft|done|skipped|reused
    reused_survey_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    length_m: Mapped[float] = mapped_column(Float, nullable=False)


class LaneSurvey(UUIDPk, Timestamps, Base):
    """One surveyor's observation of one lane. Created on the phone (client_uuid) so offline
    retries are idempotent; `version` guards against silent overwrites."""

    __tablename__ = "lane_survey"
    __table_args__ = (
        UniqueConstraint("client_uuid", name="uq_lane_survey_client_uuid"),
        Index("ix_lane_survey_lane", "lane_id", "status"),
        Index("ix_lane_survey_study", "study_id"),
        {"schema": APP},
    )

    client_uuid: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    study_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{APP}.catchment_study.id", ondelete="CASCADE"), nullable=False)
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{APP}.work_chunk.id", ondelete="SET NULL"))
    lane_id: Mapped[str] = mapped_column(String(40), ForeignKey("ref.lane_segment.id"), nullable=False)
    surveyor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey(f"{APP}.user.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False)  # draft|submitted|skipped
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_seed: Mapped[bool] = mapped_column(default=False, nullable=False)  # synthetic demo data, labelled in UI
