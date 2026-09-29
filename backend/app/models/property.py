"""M2: scouting tasks, properties, photos, versioned evaluations and the pipeline audit trail."""

import uuid
from datetime import date, datetime
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import APP, Base, Timestamps, UUIDPk

def point(nullable: bool = False) -> Geometry:
    # A fresh type per column: GeoAlchemy2 stores nullability on the type object, so a shared
    # instance would make every column inherit the last one's NOT NULL.
    return Geometry("POINT", srid=4326, spatial_index=False, nullable=nullable)


def _user_fk(nullable: bool = False) -> Mapped[Any]:
    return mapped_column(UUID(as_uuid=True), ForeignKey(f"{APP}.user.id"), nullable=nullable)


class ScoutingTask(UUIDPk, Timestamps, Base):
    """A BD Manager directing an executive to scout a hotspot (or area) from an M1 report."""

    __tablename__ = "scouting_task"
    __table_args__ = (Index("ix_scouting_task_assignee", "assignee_id", "status"), {"schema": APP})

    report_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{APP}.area_report.id", ondelete="SET NULL"))
    area_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{APP}.area.id", ondelete="SET NULL"))
    hotspot_id: Mapped[str | None] = mapped_column(String(8))
    h3: Mapped[str | None] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    radius_m: Mapped[int] = mapped_column(Integer, nullable=False, default=500)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="open")  # open|in_progress|done|cancelled
    due_date: Mapped[date | None] = mapped_column(Date)
    assignee_id: Mapped[uuid.UUID] = _user_fk()
    assigned_by: Mapped[uuid.UUID] = _user_fk()


class Property(UUIDPk, Timestamps, Base):
    __tablename__ = "property"
    __table_args__ = (
        Index("ix_property_pin", "pin", postgresql_using="gist"),
        Index("ix_property_stage", "stage"),
        Index("ix_property_created_by", "created_by"),
        {"schema": APP},
    )

    code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    stage: Mapped[str] = mapped_column(String(20), nullable=False)
    stage_before_hold: Mapped[str | None] = mapped_column(String(20))
    scouting_task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{APP}.scouting_task.id", ondelete="SET NULL"))
    created_by: Mapped[uuid.UUID] = _user_fk()

    # Location: the pin the executive placed, plus the phone's own GPS fix for sanity checks.
    pin: Mapped[Any] = mapped_column(point(), nullable=False)
    # Optional[Any] collapses to Any, so nullability must be explicit here.
    gps_fix: Mapped[Any | None] = mapped_column(point(nullable=True), nullable=True)
    gps_accuracy_m: Mapped[float | None] = mapped_column(Float)
    address: Mapped[str | None] = mapped_column(Text)
    landmark: Mapped[str | None] = mapped_column(String(160))
    pincode: Mapped[str | None] = mapped_column(String(6))

    # Commercial and physical details (see schemas for allowed values).
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    rent_monthly: Mapped[float | None] = mapped_column(Float)
    carpet_sqft: Mapped[float | None] = mapped_column(Float)

    flags: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    duplicate_of: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{APP}.property.id", ondelete="SET NULL"))

    # Denormalised from the latest completed evaluation, for fast pipeline boards.
    latest_score: Mapped[float | None] = mapped_column(Float)
    latest_recommendation: Mapped[str | None] = mapped_column(String(10))
    latest_evaluation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class PropertyPhoto(UUIDPk, Timestamps, Base):
    __tablename__ = "property_photo"
    __table_args__ = (Index("ix_property_photo_property", "property_id"), {"schema": APP})

    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{APP}.property.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # front|interior|street|other
    path: Mapped[str] = mapped_column(String(300), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_by: Mapped[uuid.UUID] = _user_fk()


class PropertyEvaluation(UUIDPk, Timestamps, Base):
    """Append-only: a new version on submit, edit, catchment completion or manual re-run."""

    __tablename__ = "property_evaluation"
    __table_args__ = (Index("ix_property_evaluation_property", "property_id", "version"), {"schema": APP})

    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{APP}.property.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    trigger: Mapped[str] = mapped_column(String(12), nullable=False)  # created|edited|catchment|manual
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="queued")
    score: Mapped[float | None] = mapped_column(Float)
    location_score: Mapped[float | None] = mapped_column(Float)
    site_score: Mapped[float | None] = mapped_column(Float)
    recommendation: Mapped[str | None] = mapped_column(String(10))  # proceed|review|reject
    checks: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    insights: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    risks: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    context: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    inputs_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    facts: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    narrative: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    narrative_source: Mapped[str | None] = mapped_column(String(10))
    llm_model: Mapped[str | None] = mapped_column(String(80))
    error: Mapped[str | None] = mapped_column(Text)
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{APP}.job.id", ondelete="SET NULL"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PipelineEvent(UUIDPk, Base):
    """Insert-only audit trail: stage moves, evaluations, notes. Who did what, when, and why."""

    __tablename__ = "pipeline_event"
    __table_args__ = (Index("ix_pipeline_event_property", "property_id", "at"), {"schema": APP})

    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{APP}.property.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(12), nullable=False)  # stage|evaluation|note|edit
    from_stage: Mapped[str | None] = mapped_column(String(20))
    to_stage: Mapped[str | None] = mapped_column(String(20))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{APP}.user.id"))  # None = system
    reason: Mapped[str | None] = mapped_column(Text)
    data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
