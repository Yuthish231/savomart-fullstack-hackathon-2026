"""Savomart operational stores. Live API when STORES_API_TOKEN is set, else the committed snapshot.

Cleaning: keep zone == CHN; coordinates are authoritative. The address pincode is kept for
reference but the pincode we use is derived from the coordinates (they disagree for at
least one store, e.g. Thiruvanmiyur listed as 600068).
"""

import json
import re
from datetime import date

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from ingest.common import RAW, SEED, UA, copy_rows, log, register_source, settings

PIN_RE = re.compile(r"\b(6\d{5})\b")


def fetch() -> tuple[list[dict], str]:
    s = settings()
    if s.stores_api_token:
        try:
            r = httpx.get(s.stores_api_url, headers={"X-cron-token": s.stores_api_token, "User-Agent": UA},
                          timeout=30)
            r.raise_for_status()
            payload = r.json()
            (RAW / "stores.json").parent.mkdir(parents=True, exist_ok=True)
            (RAW / "stores.json").write_text(json.dumps(payload, indent=1), encoding="utf-8")
            return payload["data"], "live"
        except Exception as exc:  # noqa: BLE001
            log.warning("stores API failed (%s); falling back to snapshot", exc)
    payload = json.loads((SEED / "stores_chn_snapshot.json").read_text(encoding="utf-8"))
    return payload["data"], f"snapshot {payload['_fetched']}"


def load(db: Session) -> None:
    stores, origin = fetch()
    rows = []
    for st in stores:
        if st.get("zone") != "CHN" or not st.get("is_operational", True):
            continue
        geo = st["geocoordinates"]
        pins = PIN_RE.findall(st.get("address") or "")
        rows.append((st["store_code"], st["name"].strip(), st.get("address"), st["zone"],
                     pins[-1] if pins else None, True,
                     f"SRID=4326;POINT({geo['longitude']} {geo['latitude']})"))
    db.execute(text("TRUNCATE ref.savomart_store"))
    n = copy_rows(db, "ref.savomart_store",
                  ["store_code", "name", "address", "zone", "address_pincode", "is_operational", "geom"], rows)
    db.execute(text("""
        UPDATE ref.savomart_store s SET geo_pincode = p.pincode
          FROM ref.pincode p WHERE ST_Contains(p.geom, s.geom)
    """))
    mismatches = db.execute(text("""
        SELECT store_code, name, address_pincode, geo_pincode FROM ref.savomart_store
         WHERE address_pincode IS DISTINCT FROM geo_pincode
    """)).all()
    for m in mismatches:
        log.info("store %s (%s): address says %s, coordinates fall in %s", *m)
    log.info("Savomart Chennai stores: %d (%s)", n, origin)
    register_source(
        db, "savomart_stores", "Savomart Stores API (operational stores, zone CHN)",
        url=settings().stores_api_url.split("?")[0], license="Savomart internal",
        as_of=date.today() if origin == "live" else date(2026, 9, 28), row_count=n,
        notes=f"Source: {origin}. {len(mismatches)} store(s) with address pincode differing from coordinates.",
    )
