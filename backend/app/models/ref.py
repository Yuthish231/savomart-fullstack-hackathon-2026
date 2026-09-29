"""Reference data (schema `ref`): re-ingestable from public sources without touching app data."""

from datetime import datetime
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import BigInteger, Boolean, DateTime, Float, Index, Integer, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import REF, Base

MPOLY = Geometry("MULTIPOLYGON", srid=4326, spatial_index=False)
POLY = Geometry("POLYGON", srid=4326, spatial_index=False)
POINT = Geometry("POINT", srid=4326, spatial_index=False)
LINE = Geometry("LINESTRING", srid=4326, spatial_index=False)


def gist(table: str, col: str = "geom") -> Index:
    return Index(f"ix_{table}_{col}", col, postgresql_using="gist")


class Boundary(Base):
    """Named polygons: 'cma' (study region), 'gcc' (corporation), 'old_city' (pre-2011 limits)."""

    __tablename__ = "boundary"
    __table_args__ = (gist("boundary"), {"schema": REF})

    key: Mapped[str] = mapped_column(String(30), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    area_km2: Mapped[float] = mapped_column(Float, nullable=False)
    geom: Mapped[Any] = mapped_column(MPOLY, nullable=False)


class Ward(Base):
    __tablename__ = "ward"
    __table_args__ = (gist("ward"), {"schema": REF})

    ward_no: Mapped[int] = mapped_column(Integer, primary_key=True)
    zone_no: Mapped[str] = mapped_column(String(8), nullable=False)
    zone_name: Mapped[str] = mapped_column(String(60), nullable=False)
    is_old_city: Mapped[bool] = mapped_column(Boolean, nullable=False)
    area_km2: Mapped[float] = mapped_column(Float, nullable=False)
    pop_est: Mapped[float | None] = mapped_column(Float)
    geom: Mapped[Any] = mapped_column(MPOLY, nullable=False)


class Pincode(Base):
    __tablename__ = "pincode"
    __table_args__ = (gist("pincode"), {"schema": REF})

    pincode: Mapped[str] = mapped_column(String(6), primary_key=True)
    office_name: Mapped[str] = mapped_column(String(120), nullable=False)
    division: Mapped[str | None] = mapped_column(String(80))
    area_km2: Mapped[float] = mapped_column(Float, nullable=False)
    in_cma_share: Mapped[float] = mapped_column(Float, nullable=False)
    pop_est: Mapped[float | None] = mapped_column(Float)
    geom: Mapped[Any] = mapped_column(MPOLY, nullable=False)


class SavomartStore(Base):
    __tablename__ = "savomart_store"
    __table_args__ = (gist("savomart_store"), {"schema": REF})

    store_code: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    address: Mapped[str | None] = mapped_column(Text)
    zone: Mapped[str] = mapped_column(String(8), nullable=False)
    address_pincode: Mapped[str | None] = mapped_column(String(6))
    geo_pincode: Mapped[str | None] = mapped_column(String(6))
    is_operational: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    geom: Mapped[Any] = mapped_column(POINT, nullable=False)


class OsmPoi(Base):
    __tablename__ = "osm_poi"
    __table_args__ = (
        gist("osm_poi"),
        Index("ix_osm_poi_h3_r9", "h3_r9"),
        Index("ix_osm_poi_category", "category"),
        {"schema": REF},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    osm_type: Mapped[str] = mapped_column(String(1), nullable=False)
    osm_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str | None] = mapped_column(String(200))
    brand: Mapped[str | None] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    subcategory: Mapped[str] = mapped_column(String(40), nullable=False)
    footfall_weight: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    competitor_tier: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    h3_r9: Mapped[str] = mapped_column(String(16), nullable=False)
    geom: Mapped[Any] = mapped_column(POINT, nullable=False)


class OsmBuilding(Base):
    __tablename__ = "osm_building"
    __table_args__ = (gist("osm_building"), Index("ix_osm_building_h3_r9", "h3_r9"), {"schema": REF})

    osm_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    use_class: Mapped[str] = mapped_column(String(12), nullable=False)  # residential|unknown|non_res
    levels: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    res_weight: Mapped[float] = mapped_column(Float, nullable=False)
    pop_est: Mapped[float | None] = mapped_column(Float)
    h3_r9: Mapped[str] = mapped_column(String(16), nullable=False)
    geom: Mapped[Any] = mapped_column(POINT, nullable=False)


class LaneSegment(Base):
    """Road network split at intersections (and at most 250 m). Stable ids let catchment
    studies reuse each other's lane surveys by exact join."""

    __tablename__ = "lane_segment"
    __table_args__ = (gist("lane_segment"), Index("ix_lane_segment_h3_r9", "h3_r9"), {"schema": REF})

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    osm_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    highway: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str | None] = mapped_column(String(200))
    length_m: Mapped[float] = mapped_column(Float, nullable=False)
    is_surveyable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    start_node: Mapped[int] = mapped_column(BigInteger, nullable=False)
    end_node: Mapped[int] = mapped_column(BigInteger, nullable=False)
    h3_r9: Mapped[str] = mapped_column(String(16), nullable=False)
    geom: Mapped[Any] = mapped_column(LINE, nullable=False)


class H3Cell(Base):
    """Precomputed features per H3 res-9 cell (~0.1 km2) across the CMA."""

    __tablename__ = "h3_cell"
    __table_args__ = (gist("h3_cell"), Index("ix_h3_cell_r8", "h3_r8"), {"schema": REF})

    h3: Mapped[str] = mapped_column(String(16), primary_key=True)
    h3_r8: Mapped[str] = mapped_column(String(16), nullable=False)
    ward_no: Mapped[int | None] = mapped_column(Integer)
    pincode: Mapped[str | None] = mapped_column(String(6))
    in_gcc: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    area_km2: Mapped[float] = mapped_column(Float, nullable=False)
    pop_est: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    bldg_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    res_bldg_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    footfall_pts: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    comp_convenience: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    comp_supermarket: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    comp_organised: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retail_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    road_major_m: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    road_minor_m: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    nearest_store_m: Mapped[float | None] = mapped_column(Float)
    nearest_store_code: Mapped[str | None] = mapped_column(String(20))
    poi_counts: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    # Metrics over the cell's 2-ring neighbourhood (~2 km2): densities used for percentiles
    # and the city-wide opportunity map.
    nbhd: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    opportunity: Mapped[float | None] = mapped_column(Float)
    geom: Mapped[Any] = mapped_column(POLY, nullable=False)


class MetricStats(Base):
    """City-wide distribution (p0..p100) of each cell metric, for percentile scoring."""

    __tablename__ = "metric_stats"
    __table_args__ = {"schema": REF}

    metric: Mapped[str] = mapped_column(String(40), primary_key=True)
    breakpoints: Mapped[list[float]] = mapped_column(ARRAY(Float), nullable=False)
    n: Mapped[int] = mapped_column(Integer, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RentBandMock(Base):
    """MOCK: no public commercial-rent data exists. Generated per pincode by zone tier."""

    __tablename__ = "rent_band_mock"
    __table_args__ = {"schema": REF}

    pincode: Mapped[str] = mapped_column(String(6), primary_key=True)
    tier: Mapped[str] = mapped_column(String(12), nullable=False)
    rent_psf_min: Mapped[float] = mapped_column(Float, nullable=False)
    rent_psf_max: Mapped[float] = mapped_column(Float, nullable=False)
    is_mock: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
