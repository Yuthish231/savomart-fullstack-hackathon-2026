"""Resolve a map selection (pincode, locality, grid cells) into an Area polygon + H3 cells."""

import json
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import h3
import httpx
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.models import Area, GeocodeCache

NOMINATIM = "https://nominatim.openstreetmap.org/search"
CMA_VIEWBOX = "80.00,13.30,80.35,12.85"  # left,top,right,bottom
POINT_BUFFER_M = 1200  # when Nominatim only knows a point for a locality
MAX_AREA_KM2 = 60.0

_nominatim_lock = threading.Lock()
_last_call = 0.0


def search_localities(db: Session, query: str) -> list[dict[str, Any]]:
    """Nominatim search inside the CMA. Cached for 30 days; at most 1 request/second."""
    global _last_call
    q = " ".join(query.lower().split())[:200]
    if len(q) < 3:
        raise AppError("QUERY_TOO_SHORT", "Type at least 3 characters to search a locality", 422)
    cached = db.get(GeocodeCache, q)
    if cached and cached.fetched_at > datetime.now(UTC) - timedelta(days=30):
        return cached.response
    with _nominatim_lock:
        wait = 1.0 - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        try:
            r = httpx.get(
                NOMINATIM,
                params={
                    "q": q if "chennai" in q else f"{q}, Chennai", "format": "jsonv2",
                    "polygon_geojson": 1, "polygon_threshold": 0.0003, "viewbox": CMA_VIEWBOX,
                    "bounded": 1, "limit": 6, "countrycodes": "in",
                },
                headers={"User-Agent": get_settings().nominatim_user_agent},
                timeout=15,
            )
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise AppError("GEOCODER_UNAVAILABLE", "Locality search is unavailable right now; "
                           "try selecting by pincode or grid cells.", 503) from exc
        finally:
            _last_call = time.monotonic()
    results = [
        {
            "place_id": str(it["place_id"]),
            "name": it.get("name") or it["display_name"].split(",")[0],
            "display_name": it["display_name"],
            "type": it.get("type"),
            "lat": float(it["lat"]),
            "lon": float(it["lon"]),
            "geojson": it.get("geojson"),
        }
        for it in r.json()
    ]
    if cached:
        cached.response, cached.fetched_at = results, datetime.now(UTC)
    else:
        db.add(GeocodeCache(query=q, response=results, fetched_at=datetime.now(UTC)))
    db.commit()
    return results


def _finish(db: Session, name: str, sel_type: str, sel_input: dict, geom_sql: str, params: dict,
            user_id: uuid.UUID) -> Area:
    """Clip the candidate geometry to the CMA, find covered H3 cells, persist the Area."""
    row = db.execute(text(f"""
        WITH g AS (
            SELECT ST_Multi(ST_CollectionExtract(ST_MakeValid(
                     ST_Intersection(({geom_sql}), (SELECT geom FROM ref.boundary WHERE key = 'cma'))), 3)) AS geom
        )
        SELECT ST_AsEWKT(g.geom) AS ewkt, ST_Area(g.geom::geography) / 1e6 AS km2,
               ARRAY(SELECT c.h3 FROM ref.h3_cell c
                      WHERE ST_Intersects(g.geom, ST_Centroid(c.geom))) AS cells
          FROM g
    """), params).one()
    if not row.cells or row.km2 < 0.05:
        raise AppError("AREA_OUTSIDE_REGION", "That selection falls outside the Chennai Metropolitan Area.", 422)
    if row.km2 > MAX_AREA_KM2:
        raise AppError("AREA_TOO_LARGE", f"Selection is {row.km2:.0f} km²; pick up to {MAX_AREA_KM2:.0f} km² "
                       "so hotspots stay meaningful.", 422)
    area = Area(name=name, selection_type=sel_type, selection_input=sel_input, h3_cells=row.cells,
                area_km2=round(row.km2, 3), geom=row.ewkt, created_by=user_id)
    db.add(area)
    db.flush()
    return area


def from_pincode(db: Session, pincode: str, user_id: uuid.UUID) -> Area:
    p = db.execute(text("SELECT pincode, office_name FROM ref.pincode WHERE pincode = :p"), {"p": pincode}).first()
    if p is None:
        raise AppError("UNKNOWN_PINCODE", f"Pincode {pincode} is not in the Chennai region", 422)
    return _finish(db, f"{p.pincode} · {p.office_name}", "pincode", {"pincode": pincode},
                   "SELECT geom FROM ref.pincode WHERE pincode = :p", {"p": pincode}, user_id)


def from_locality(db: Session, query: str, place_id: str, user_id: uuid.UUID) -> Area:
    match = next((r for r in search_localities(db, query) if r["place_id"] == place_id), None)
    if match is None:
        raise AppError("UNKNOWN_PLACE", "That locality result has expired; search again.", 422)
    gj = match.get("geojson")
    if gj and gj.get("type") in ("Polygon", "MultiPolygon"):
        geom_sql = "SELECT ST_SetSRID(ST_GeomFromGeoJSON(:gj), 4326)"
        params: dict[str, Any] = {"gj": json.dumps(gj)}
        how = "OSM boundary"
    else:
        geom_sql = ("SELECT ST_Buffer(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :r)::geometry")
        params = {"lon": match["lon"], "lat": match["lat"], "r": POINT_BUFFER_M}
        how = f"{POINT_BUFFER_M / 1000:.1f} km around the locality point"
    return _finish(db, match["name"], "locality",
                   {"query": query, "place_id": place_id, "display_name": match["display_name"], "shape": how},
                   geom_sql, params, user_id)


def from_cells(db: Session, cells_r8: list[str], user_id: uuid.UUID) -> Area:
    cells_r8 = sorted({c for c in cells_r8 if h3.is_valid_cell(c) and h3.get_resolution(c) == 8})
    if not cells_r8:
        raise AppError("NO_CELLS", "Pick at least one grid cell", 422)
    if len(cells_r8) > 60:
        raise AppError("AREA_TOO_LARGE", "Pick at most 60 grid cells", 422)
    polys = []
    for c in cells_r8:
        ring = [(lng, lat) for lat, lng in h3.cell_to_boundary(c)]
        ring.append(ring[0])
        polys.append("((" + ", ".join(f"{x} {y}" for x, y in ring) + "))")
    wkt = "MULTIPOLYGON(" + ", ".join(polys) + ")"
    name = f"{len(cells_r8)} grid cell{'s' if len(cells_r8) > 1 else ''}"
    near = db.execute(text("""
        SELECT p.office_name FROM ref.pincode p
         WHERE ST_Intersects(p.geom, ST_SetSRID(ST_GeomFromText(:w), 4326))
         ORDER BY ST_Area(ST_Intersection(p.geom, ST_SetSRID(ST_GeomFromText(:w), 4326))) DESC LIMIT 1
    """), {"w": wkt}).scalar()
    if near:
        name += f" near {near}"
    return _finish(db, name, "cells", {"cells_r8": cells_r8},
                   "SELECT ST_UnaryUnion(ST_SetSRID(ST_GeomFromText(:w), 4326))", {"w": wkt}, user_id)


def get_area_geojson(db: Session, area_id: uuid.UUID) -> dict:
    return json.loads(db.scalar(text("SELECT ST_AsGeoJSON(geom, 6) FROM app.area WHERE id = :i"), {"i": area_id}))


def latest_by_user(db: Session, user_id: uuid.UUID, limit: int = 20) -> list[Area]:
    return list(db.scalars(select(Area).where(Area.created_by == user_id)
                           .order_by(Area.created_at.desc()).limit(limit)))
