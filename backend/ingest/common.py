"""Shared helpers for the ingestion pipeline: paths, HTTP with caching, provenance."""

import json
import logging
import time
from datetime import date
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import REPO_ROOT, get_settings

log = logging.getLogger("ingest")

RAW = REPO_ROOT / "data" / "raw"
SEED = REPO_ROOT / "data" / "seed"  # small, committed snapshots

# Chennai Metropolitan Area bounding box (south, west, north, east), from the CMA polygon.
CMA_BBOX = (12.85, 80.00, 13.30, 80.35)

UA = "savo-sitescout-hackathon/0.1 (+https://github.com/; data ingestion, cached, low volume)"

OVERPASS_MIRRORS = [
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]


def setup_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def download(url: str, dest: Path, *, headers: dict[str, str] | None = None) -> Path:
    """Download once; later runs reuse the cached file."""
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    log.info("downloading %s", url)
    with httpx.stream(
        "GET", url, headers={"User-Agent": UA, **(headers or {})}, timeout=300, follow_redirects=True
    ) as r:
        r.raise_for_status()
        tmp = dest.with_suffix(dest.suffix + ".part")
        with tmp.open("wb") as fh:
            for chunk in r.iter_bytes():
                fh.write(chunk)
    tmp.replace(dest)
    return dest


_preferred_mirror = 0


def _remember_mirror(url: str) -> None:
    """Stick with whichever mirror last answered; the main instance is often overloaded."""
    global _preferred_mirror
    _preferred_mirror = OVERPASS_MIRRORS.index(url)


def overpass(query: str, cache: Path, *, attempts: int = 6) -> dict[str, Any]:
    """Run an Overpass query with on-disk caching, mirror rotation and backoff."""
    if cache.exists() and cache.stat().st_size > 0:
        return json.loads(cache.read_text(encoding="utf-8"))
    cache.parent.mkdir(parents=True, exist_ok=True)
    last_err: Exception | None = None
    for i in range(attempts):
        url = OVERPASS_MIRRORS[(_preferred_mirror + i) % len(OVERPASS_MIRRORS)]
        try:
            r = httpx.post(url, data={"data": query}, headers={"User-Agent": UA}, timeout=400)
            if r.status_code in (429, 504):
                raise httpx.HTTPStatusError(f"busy {r.status_code}", request=r.request, response=r)
            r.raise_for_status()
            data = r.json()
            if "remark" in data and "runtime error" in data["remark"]:
                raise RuntimeError(data["remark"])
            cache.write_text(json.dumps(data), encoding="utf-8")
            _remember_mirror(url)
            return data
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            wait = 5 * (i + 1)
            log.warning("overpass %s failed (%s); retrying in %ss", url, str(exc)[:120], wait)
            time.sleep(wait)
    raise RuntimeError(f"Overpass failed after {attempts} attempts: {last_err}")


def tiles(bbox: tuple[float, float, float, float], rows: int, cols: int):
    s, w, n, e = bbox
    dlat, dlon = (n - s) / rows, (e - w) / cols
    for i in range(rows):
        for j in range(cols):
            yield i, j, (s + i * dlat, w + j * dlon, s + (i + 1) * dlat, w + (j + 1) * dlon)


def register_source(
    db: Session,
    key: str,
    name: str,
    *,
    url: str | None = None,
    license: str | None = None,
    as_of: date | None = None,
    is_mock: bool = False,
    row_count: int | None = None,
    notes: str | None = None,
) -> int:
    """Upsert a provenance row; reports cite these ids and as-of dates."""
    return db.execute(
        text(
            """
            INSERT INTO ref.data_source (key, name, url, license, as_of, is_mock, row_count, notes, fetched_at)
            VALUES (:key, :name, :url, :license, :as_of, :is_mock, :row_count, :notes, now())
            ON CONFLICT (key) DO UPDATE SET
              name = EXCLUDED.name, url = EXCLUDED.url, license = EXCLUDED.license,
              as_of = EXCLUDED.as_of, is_mock = EXCLUDED.is_mock, row_count = EXCLUDED.row_count,
              notes = EXCLUDED.notes, fetched_at = now()
            RETURNING id
            """
        ),
        dict(key=key, name=name, url=url, license=license, as_of=as_of, is_mock=is_mock,
             row_count=row_count, notes=notes),
    ).scalar_one()


def settings():
    return get_settings()


def copy_rows(db: Session, table: str, columns: list[str], rows) -> int:
    """Bulk load via COPY (geometry columns accept EWKT text). Returns rows written."""
    raw = db.connection().connection.driver_connection  # psycopg 3 connection
    n = 0
    with raw.cursor() as cur:
        with cur.copy(f"COPY {table} ({', '.join(columns)}) FROM STDIN") as cp:
            for row in rows:
                cp.write_row(row)
                n += 1
    return n


def ewkt(geom) -> str:
    return f"SRID=4326;{geom.wkt}"
