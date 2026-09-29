"""MOCK commercial rent bands per pincode (INR per sq ft per month, ground-floor retail).

No public source for commercial rents exists, so this is clearly labelled mock data:
a tier from the pincode's distance to Chennai's central retail belt, plus a stable
per-pincode variation so neighbouring pincodes aren't identical.
"""

import hashlib

from sqlalchemy import text
from sqlalchemy.orm import Session

from ingest.common import copy_rows, log, register_source

# Roughly Nungambakkam / T. Nagar: the central retail belt.
CENTRE = (80.245, 13.055)
TIERS = [  # (max km from centre, tier, min, max)
    (5, "prime", 140, 240),
    (10, "central", 90, 150),
    (18, "suburban", 55, 95),
    (999, "peri-urban", 30, 60),
]


def load(db: Session) -> None:
    rows = []
    for pc, km in db.execute(text("""
        SELECT pincode,
               ST_Distance(ST_Centroid(geom)::geography,
                           ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography) / 1000
          FROM ref.pincode
    """), {"lon": CENTRE[0], "lat": CENTRE[1]}):
        tier, lo, hi = next((t, lo, hi) for mx, t, lo, hi in TIERS if km <= mx)
        jitter = 0.9 + (int(hashlib.md5(pc.encode()).hexdigest()[:4], 16) / 0xFFFF) * 0.2
        rows.append((pc, tier, round(lo * jitter), round(hi * jitter), True))
    db.execute(text("TRUNCATE ref.rent_band_mock"))
    n = copy_rows(db, "ref.rent_band_mock", ["pincode", "tier", "rent_psf_min", "rent_psf_max", "is_mock"], rows)
    log.info("MOCK rent bands: %d pincodes", n)
    register_source(
        db, "rent_band_mock", "MOCK commercial rent bands (generated)", is_mock=True, row_count=n,
        notes="No public commercial-rent source exists. Tiered by distance to the central retail "
              "belt with a stable per-pincode variation. Always shown with a MOCK badge.",
    )
