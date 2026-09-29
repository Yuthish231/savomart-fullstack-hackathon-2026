"""India Post delivery pincode boundaries (data.gov.in "All India Pincode Boundary"),
read from the GeoParquet mirror in yashveeeeeeer/india-geodata and clipped to the CMA."""

from collections import defaultdict

import pyarrow.parquet as pq
from shapely import wkb
from shapely.ops import unary_union
from sqlalchemy import text
from sqlalchemy.orm import Session

from ingest.boundaries import as_multi
from ingest.common import RAW, copy_rows, download, ewkt, log, register_source

URL = ("https://github.com/yashveeeeeeer/india-geodata/releases/download/"
       "postal%2Fboundaries/Datagov_Pincode_Boundaries.parquet")
MIN_SHARE_IN_CMA = 0.05  # ignore pincodes that only graze the region edge


def load(db: Session) -> None:
    path = download(URL, RAW / "pincodes" / "Datagov_Pincode_Boundaries.parquet")
    cma_wkb = db.scalar(text("SELECT ST_AsBinary(geom) FROM ref.boundary WHERE key = 'cma'"))
    cma = wkb.loads(bytes(cma_wkb))
    minx, miny, maxx, maxy = cma.bounds

    table = pq.read_table(path, columns=["Pincode", "Office_Name", "Division", "geometry"])
    parts: dict[str, list] = defaultdict(list)
    meta: dict[str, tuple[str, str]] = {}
    for row in table.to_pylist():
        g = wkb.loads(row["geometry"])
        bx0, by0, bx1, by1 = g.bounds
        if bx1 < minx or bx0 > maxx or by1 < miny or by0 > maxy:
            continue
        if not g.intersects(cma):
            continue
        pc = str(row["Pincode"]).strip()
        parts[pc].append(g)
        meta.setdefault(pc, ((row["Office_Name"] or "").strip(), (row["Division"] or "").strip()))

    rows = []
    for pc, geoms in parts.items():
        g = as_multi(unary_union(geoms))
        share = g.intersection(cma).area / g.area if g.area else 0
        if share < MIN_SHARE_IN_CMA:
            continue
        office, division = meta[pc]
        rows.append((pc, office.removesuffix(" S.O").removesuffix(" H.O").removesuffix(" B.O"),
                     division, 0, round(share, 3), ewkt(g)))

    db.execute(text("TRUNCATE ref.pincode"))
    n = copy_rows(db, "ref.pincode",
                  ["pincode", "office_name", "division", "area_km2", "in_cma_share", "geom"], rows)
    db.execute(text("UPDATE ref.pincode SET area_km2 = ST_Area(geom::geography) / 1e6"))
    log.info("pincodes in CMA: %d", n)
    register_source(
        db, "ogd_pincode_boundary", "All India Pincode Boundary (data.gov.in, India Post)",
        url="https://www.data.gov.in/catalog/all-india-pincode-boundary-geo-json",
        license="Government Open Data License - India", row_count=n,
        notes="Read from the GeoParquet mirror at github.com/yashveeeeeeer/india-geodata "
              "(release postal/boundaries). Kept pincodes with >=5% of their area inside the CMA.",
    )
