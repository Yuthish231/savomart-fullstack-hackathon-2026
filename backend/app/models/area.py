import uuid
from datetime import datetime
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import APP, Base, Timestamps, UUIDPk


class Area(UUIDPk, Timestamps, Base):
    """A selected piece of Chennai. Every selection mode resolves to a polygon plus the
    H3 res-9 cells it covers, so scoring never cares how the area was picked."""

    __tablename__ = "area"
    __table_args__ = (Index("ix_area_geom", "geom", postgresql_using="gist"), {"schema": APP})

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    selection_type: Mapped[str] = mapped_column(String(12), nullable=False)  # pincode|locality|cells
    selection_input: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    h3_cells: Mapped[list[str]] = mapped_column(ARRAY(String(16)), nullable=False)
    area_km2: Mapped[float] = mapped_column(Float, nullable=False)
    geom: Mapped[Any] = mapped_column(
        Geometry("MULTIPOLYGON", srid=4326, spatial_index=False), nullable=False
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{APP}.user.id"), nullable=False
    )


class AreaReport(UUIDPk, Timestamps, Base):
    """Immutable snapshot of an Area Fitness analysis, stamped with the data it used."""

    __tablename__ = "area_report"
    __table_args__ = (Index("ix_area_report_area", "area_id"), {"schema": APP})

    area_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{APP}.area.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="queued")
    scoring_version: Mapped[str] = mapped_column(String(10), nullable=False)
    overall_score: Mapped[float | None] = mapped_column(Float)
    grade: Mapped[str | None] = mapped_column(String(2))
    confidence: Mapped[str | None] = mapped_column(String(8))
    confidence_reasons: Mapped[list[str] | None] = mapped_column(JSONB)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    sub_scores: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    hotspots: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    facts: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    narrative: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    narrative_source: Mapped[str | None] = mapped_column(String(10))  # llm|template
    llm_model: Mapped[str | None] = mapped_column(String(80))
    data_sources: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{APP}.job.id", ondelete="SET NULL")
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(f"{APP}.user.id"), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GeocodeCache(Base):
    """Nominatim responses, cached to respect its usage policy (and for speed)."""

    __tablename__ = "geocode_cache"
    __table_args__ = {"schema": APP}

    query: Mapped[str] = mapped_column(String(200), primary_key=True)
    response: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
