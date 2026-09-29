"""City-wide opportunity surface: score every inhabited H3 cell's neighbourhood with the
same model the Area Fitness Report uses, so the heatmap and reports never disagree."""

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.scoring import score_metrics
from ingest.common import copy_rows, log
from ingest.h3_grid import INHABITED_MIN_DENSITY


def load(db: Session) -> None:
    stats = dict(db.execute(text("SELECT metric, breakpoints FROM ref.metric_stats")).all())
    rows = db.execute(text("SELECT h3, nbhd, nearest_store_m FROM ref.h3_cell")).all()
    out = []
    for h, nb, dist in rows:
        if not nb or nb["pop_density"] < INHABITED_MIN_DENSITY:
            out.append((h, None))
            continue
        total, _ = score_metrics({**nb, "nearest_store_km": (dist or 0) / 1000}, stats)
        out.append((h, total))
    db.execute(text("DROP TABLE IF EXISTS tmp_opp"))
    db.execute(text("CREATE TEMP TABLE tmp_opp (h3 text PRIMARY KEY, score double precision)"))
    copy_rows(db, "tmp_opp", ["h3", "score"], out)
    db.execute(text("UPDATE ref.h3_cell c SET opportunity = t.score FROM tmp_opp t WHERE t.h3 = c.h3"))
    scored = [s for _, s in out if s is not None]
    log.info("opportunity scored for %d inhabited cells (min %.0f, median %.0f, max %.0f)",
             len(scored), min(scored), sorted(scored)[len(scored) // 2], max(scored))
