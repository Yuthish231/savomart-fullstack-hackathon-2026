"""Reference layers for the map: pincodes, Savomart stores, wards, H3 grid."""

import json
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.errors import AppError, NotFound
from app.models import User

router = APIRouter(prefix="/ref", tags=["reference"])


def feature_collection(rows, geom_key: str = "geometry") -> dict[str, Any]:
    feats = []
    for r in rows:
        props = dict(r._mapping)
        geom = json.loads(props.pop(geom_key))
        feats.append({"type": "Feature", "geometry": geom, "properties": props})
    return {"type": "FeatureCollection", "features": feats}


@router.get("/stores")
def stores(db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> dict[str, Any]:
    rows = db.execute(text("""
        SELECT store_code, name, address, geo_pincode AS pincode, ST_AsGeoJSON(geom, 6) AS geometry
          FROM ref.savomart_store ORDER BY name
    """))
    return feature_collection(rows)


class PincodeOut(BaseModel):
    pincode: str
    office_name: str
    area_km2: float
    pop_est: float | None
    in_cma_share: float


@router.get("/pincodes", response_model=list[PincodeOut])
def search_pincodes(
    q: str = Query("", max_length=40),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    rows = db.execute(text("""
        SELECT pincode, office_name, round(area_km2::numeric, 2)::float AS area_km2,
               round(pop_est)::float AS pop_est, in_cma_share
          FROM ref.pincode
         WHERE :q = '' OR pincode LIKE :q || '%' OR office_name ILIKE '%' || :q || '%'
         ORDER BY (pincode LIKE :q || '%') DESC, office_name
         LIMIT 50
    """), {"q": q.strip()})
    return [PincodeOut(**r._mapping) for r in rows]


@router.get("/pincodes.geojson")
def pincodes_geojson(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """All CMA pincode polygons, simplified (~20 m) for the map layer."""
    rows = db.execute(text("""
        SELECT pincode, office_name, round(pop_est)::float AS pop_est,
               ST_AsGeoJSON(ST_SimplifyPreserveTopology(geom, 0.0002), 5) AS geometry
          FROM ref.pincode
    """))
    return feature_collection(rows)


@router.get("/pincodes/{pincode}")
def pincode_detail(pincode: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    row = db.execute(text("""
        SELECT pincode, office_name, division, area_km2, pop_est, in_cma_share,
               ST_AsGeoJSON(geom, 6) AS geometry
          FROM ref.pincode WHERE pincode = :pc
    """), {"pc": pincode}).first()
    if row is None:
        raise NotFound("Pincode", pincode)
    return feature_collection([row])["features"][0]


@router.get("/wards.geojson")
def wards_geojson(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    rows = db.execute(text("""
        SELECT ward_no, zone_name, is_old_city, round(pop_est)::float AS pop_est,
               ST_AsGeoJSON(ST_SimplifyPreserveTopology(geom, 0.0002), 5) AS geometry
          FROM ref.ward
    """))
    return feature_collection(rows)


class OpportunityCell(BaseModel):
    h3: str
    score: float
    pop: float
    nearest_store_km: float


@router.get("/opportunity", response_model=list[OpportunityCell])
def opportunity(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """City-wide opportunity surface at H3 res 8 (~0.7 km2): population-weighted mean of the
    res-9 neighbourhood scores. Same model as the Area Fitness Report."""
    rows = db.execute(text("""
        SELECT h3_r8 AS h3,
               round((sum(opportunity * greatest(pop_est, 1)) / sum(greatest(pop_est, 1)))::numeric, 1)::float AS score,
               round(sum(pop_est))::float AS pop,
               round((min(nearest_store_m) / 1000)::numeric, 2)::float AS nearest_store_km
          FROM ref.h3_cell
         WHERE opportunity IS NOT NULL
         GROUP BY h3_r8
    """))
    return [OpportunityCell(**r._mapping) for r in rows]


@router.get("/region")
def region(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """The CMA outline, for masking and the map's max bounds."""
    row = db.execute(text("""
        SELECT key, name, ST_AsGeoJSON(ST_SimplifyPreserveTopology(geom, 0.0005), 5) AS geometry
          FROM ref.boundary WHERE key = 'cma'
    """)).first()
    if row is None:
        raise AppError("NO_REFERENCE_DATA", "Reference data not loaded. Run the ingestion pipeline.", 503)
    return feature_collection([row])["features"][0]
