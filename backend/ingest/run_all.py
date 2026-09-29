"""Run the whole ingestion pipeline. Usage (from backend/):

    python -m ingest.fetch_osm     # slow, cached: downloads OSM tiles once
    python -m ingest.run_all       # loads and precomputes everything (re-runnable)
"""

import sys
import time

from app.core.db import SessionLocal
from ingest import boundaries, h3_grid, load_osm, opportunity, pincodes, population, rents, stores
from ingest.common import log, setup_logging

STEPS = [
    ("boundaries", boundaries.load),
    ("pincodes", pincodes.load),
    ("stores", stores.load),
    ("osm", load_osm.load),
    ("population", population.load),
    ("h3_grid", h3_grid.load),
    ("opportunity", opportunity.load),
    ("rents", rents.load),
]


def main(only: list[str] | None = None) -> None:
    setup_logging()
    for name, fn in STEPS:
        if only and name not in only:
            continue
        t0 = time.perf_counter()
        log.info("== %s", name)
        with SessionLocal() as db:
            fn(db)
            db.commit()
        log.info("== %s done in %.1fs", name, time.perf_counter() - t0)


if __name__ == "__main__":
    main(sys.argv[1:] or None)
