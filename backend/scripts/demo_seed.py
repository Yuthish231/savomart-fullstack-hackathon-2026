"""Build a coherent demo dataset on top of the ingested reference data.

Usage (from backend/, with the database migrated and personas seeded):
    python -m scripts.demo_seed --reset

Runs the real code paths (API handlers, services, job handlers) in-process, so the demo data is
exactly what the app would produce. Lane surveys for the completed study are SYNTHETIC: derived
from real OSM building density per lane plus plausible random attributes, and stored with
is_seed = true, which the UI shows as "Includes synthetic demo survey data".
"""

import argparse
import random
import shutil
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select, text

from app.api.v1 import areas as areas_api
from app.api.v1 import properties as props_api
from app.api.v1 import scouting as scout_api
from app.api.v1 import studies as studies_api
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.jobs.queue import claim
from app.jobs.worker import run_job
from app.models import AreaReport, CatchmentStudy, StudyLane, User, WorkChunk
from app.services import studies as study_svc

RNG = random.Random(2026)


def user(db, username: str) -> User:
    return db.scalar(select(User).where(User.username == username))


def drain() -> None:
    """Process every queued job in-process (a running worker may help; SKIP LOCKED keeps it safe)."""
    while True:
        with SessionLocal() as db:
            jid = claim(db, "demo-seed")
        if jid:
            run_job(jid)
            continue
        with SessionLocal() as db:
            busy = db.scalar(text("SELECT count(*) FROM app.job WHERE status IN ('queued', 'running')"))
        if not busy:
            return
        time.sleep(0.5)


def reset() -> None:
    with SessionLocal() as db:
        db.execute(text("""
            TRUNCATE app.lane_survey, app.study_lane, app.work_chunk, app.catchment_study, app.pipeline_event,
                     app.property_evaluation, app.property_photo, app.property, app.scouting_task,
                     app.area_report, app.area, app.job CASCADE
        """))
        db.execute(text("ALTER SEQUENCE app.property_code_seq RESTART"))
        db.execute(text("ALTER SEQUENCE app.study_code_seq RESTART"))
        db.commit()
    shutil.rmtree(Path(get_settings().media_dir) / "properties", ignore_errors=True)
    print("reset app data")


def report_for(pincode: str, bdm: User):
    with SessionLocal() as db:
        area = areas_api.create_area(areas_api.AreaIn(type="pincode", pincode=pincode), db, bdm)
        rep = areas_api.run_report(area.id, db, bdm)
    return rep.id


def offset(lat: float, lon: float, north_m: float, east_m: float) -> tuple[float, float]:
    return lat + north_m / 110_540, lon + east_m / 108_000


def create_property(username: str, **kw) -> str:
    with SessionLocal() as db:
        u = user(db, username)
        d = props_api.create_property(props_api.PropertyIn(**kw), db, u)
    return str(d["id"])


def move(prop_id: str, to: str, username: str, reason: str | None = None) -> None:
    with SessionLocal() as db:
        props_api.transition(uuid.UUID(prop_id), props_api.TransitionIn(to=to, reason=reason), db, user(db, username))


def synth_lane(n_buildings: int) -> tuple[str, dict]:
    if RNG.random() < 0.05:
        return "skipped", {"skip_reason": RNG.choice(["gated", "not_residential", "under_construction"])}
    bucket = ("0-10" if n_buildings < 3 else "11-25" if n_buildings < 8 else "26-50" if n_buildings < 18
              else "51-100" if n_buildings < 35 else "100+")
    pick = lambda opts: RNG.choices([o for o, _ in opts], [w for _, w in opts])[0]  # noqa: E731
    return "submitted", {
        "housing_type": pick([("apartments", 35), ("independent", 35), ("mixed", 25), ("commercial", 5)]),
        "dwellings_bucket": bucket,
        "kiranas": pick([(0, 80), (1, 16), (2, 4)]),
        "organised_present": RNG.random() < 0.02,
        "condition": pick([("maintained", 55), ("new", 15), ("old", 25), ("dilapidated", 5)]),
        "vehicles": pick([("mostly_2w", 45), ("mixed", 45), ("many_cars", 10)]),
        "footfall": pick([("low", 40), ("medium", 45), ("high", 15)]),
        "delivery_access": pick([("truck", 20), ("van", 55), ("two_wheeler", 25)]),
    }


def plan_and_assign(study_id, target_m: float) -> None:
    with SessionLocal() as db:
        sm = user(db, "sm.karthik")
        studies_api.plan_study(study_id, studies_api.PlanIn(target_effort_m=target_m), db, sm)
        ses = [user(db, u) for u in ("se.meena", "se.rahul", "se.farhan")]
        chunks = db.scalars(select(WorkChunk).where(WorkChunk.study_id == study_id).order_by(WorkChunk.label)).all()
        for i, ch in enumerate(chunks):
            studies_api.assign_chunk(ch.id, studies_api.ChunkPatch(assignee_id=ses[i % 3].id), db, sm)


def seed_surveys(study_id, share: float, only_labels: set[str] | None = None) -> int:
    """Synthetic observations for `share` of each chunk's lanes (flagged is_seed)."""
    n = 0
    with SessionLocal() as db:
        study = db.get(CatchmentStudy, study_id)
        density = dict(db.execute(text("""
            SELECT sl.lane_id, (SELECT count(*) FROM ref.osm_building b WHERE ST_DWithin(b.geom, l.geom, 0.00025))
              FROM app.study_lane sl JOIN ref.lane_segment l ON l.id = sl.lane_id WHERE sl.study_id = :s
        """), {"s": study_id}).all())
        chunks = db.scalars(select(WorkChunk).where(WorkChunk.study_id == study_id)).all()
        for ch in chunks:
            if only_labels and ch.label not in only_labels:
                continue
            se = db.get(User, ch.assignee_id)
            lanes = db.scalars(select(StudyLane).where(StudyLane.chunk_id == ch.id).order_by(StudyLane.lane_id)).all()
            for sl in lanes[: round(len(lanes) * share)]:
                status, data = synth_lane(density.get(sl.lane_id, 0))
                when = datetime.now(UTC) - timedelta(hours=RNG.uniform(2, 40))
                study_svc.save_survey(db, client_uuid=uuid.uuid4(), user=se, study=study, lane_id=sl.lane_id,
                                      status=status, data=data, base_version=None, captured_at=when, is_seed=True)
                n += 1
        db.commit()
    return n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="wipe app data (keeps users and reference data)")
    args = ap.parse_args()
    if args.reset:
        reset()

    with SessionLocal() as db:
        bdm = user(db, "bdm.priya")
        arjun, divya = user(db, "bde.arjun"), user(db, "bde.divya")

    # M1: area reports
    reps = {pc: report_for(pc, bdm) for pc in ("600042", "600040", "600041", "600017")}
    drain()
    with SessionLocal() as db:
        for pc, rid in reps.items():
            r = db.get(AreaReport, rid)
            print(f"report {pc}: {r.overall_score} {r.grade} ({r.status})")
        vel = db.get(AreaReport, reps["600042"]).hotspots
        ann = db.get(AreaReport, reps["600040"]).hotspots

    # M2: scouting tasks from hotspots
    with SessionLocal() as db:
        t1 = scout_api.create_task(scout_api.TaskIn(report_id=reps["600042"], hotspot_id=vel[0]["id"], assignee_id=arjun.id,
                                                    note="Ground-floor shops on the main road, 1,500+ sq ft"), db, bdm).id
        t2 = scout_api.create_task(scout_api.TaskIn(report_id=reps["600042"], hotspot_id=vel[1]["id"], assignee_id=divya.id,
                                                    note="Check the stretch near the bus stop"), db, bdm).id
        t3 = scout_api.create_task(scout_api.TaskIn(report_id=reps["600040"], hotspot_id=ann[0]["id"], assignee_id=arjun.id,
                                                    note="Corner units preferred"), db, bdm).id
        scout_api.create_task(scout_api.TaskIn(report_id=reps["600040"], hotspot_id=ann[1]["id"], assignee_id=divya.id,
                                               note="New task: scout this afternoon"), db, bdm)

    base = dict(property_type="shop", floor="ground", frontage_ft=24, parking_2w=10, parking_4w=1,
                delivery_access="van", visibility="main_road", lease_years=9, landlord_name="Demo landlord")
    la, lo = offset(vel[0]["lat"], vel[0]["lon"], 25, 15)
    p1 = create_property("bde.arjun", name="Sri Venkateswara Complex, ground floor", lat=la, lon=lo,
                         gps={"lat": la + 0.0002, "lon": lo, "accuracy": 9}, landmark="Near the TNHB junction",
                         carpet_sqft=2400, rent_monthly=235000, scouting_task_id=str(t1), **base)
    la6, lo6 = offset(la, lo, 90, 60)
    p6 = create_property("bde.arjun", name="Lakshmi Towers retail unit", lat=la6, lon=lo6,
                         gps={"lat": la6, "lon": lo6, "accuracy": 12}, landmark="Two blocks from Sri Venkateswara Complex",
                         carpet_sqft=1900, rent_monthly=190000, scouting_task_id=str(t1), **base)
    la2, lo2 = offset(vel[1]["lat"], vel[1]["lon"], -20, 10)
    p2 = create_property("bde.divya", name="Balaji Arcade ground floor", lat=la2, lon=lo2,
                         gps={"lat": la2, "lon": lo2, "accuracy": 15}, landmark="Opp. bus stop",
                         carpet_sqft=1800, rent_monthly=172000, scouting_task_id=str(t2), **(base | {"delivery_access": "truck"}))
    create_property("bde.arjun", name="Balaji Arcade", lat=la2 + 0.00004, lon=lo2, landmark="Opp. bus stop",
                    carpet_sqft=1750, rent_monthly=None, **base)  # likely duplicate of p2, no GPS, no rent
    la3, lo3 = offset(ann[0]["lat"], ann[0]["lon"], 15, -20)
    p3 = create_property("bde.arjun", name="Anna Nagar 2nd Avenue corner unit", lat=la3, lon=lo3,
                         gps={"lat": la3, "lon": lo3, "accuracy": 8}, landmark="Corner of 2nd Avenue",
                         carpet_sqft=3200, rent_monthly=390000, scouting_task_id=str(t3),
                         **(base | {"frontage_ft": 32, "parking_4w": 3, "delivery_access": "truck"}))
    la4, lo4 = offset(12.973889, 80.263194, 350, -250)  # ~430 m from Savomart Kaveri Nagar, Thiruvanmiyur
    create_property("bde.divya", name="Kamaraj Salai shop", lat=la4, lon=lo4, gps={"lat": la4, "lon": lo4, "accuracy": 10},
                    carpet_sqft=2000, rent_monthly=180000, **base)
    la7, lo7 = 13.0405, 80.2337  # T. Nagar
    create_property("bde.divya", name="Usman Road first-floor unit", lat=la7, lon=lo7, gps={"lat": la7, "lon": lo7, "accuracy": 20},
                    carpet_sqft=950, rent_monthly=210000, **(base | {"floor": "first", "frontage_ft": 12, "visibility": "side_street",
                                                                     "delivery_access": "two_wheeler", "parking_2w": 2, "parking_4w": 0}))
    drain()

    # Pipeline history
    move(p1, "SHORTLISTED", "bdm.priya")
    move(p1, "SITE_VISIT", "bdm.priya", "Please confirm frontage and loading access")
    move(p1, "NEGOTIATION", "bde.arjun", "Visited: 24 ft frontage, vans can unload at the side lane; owner open to 9 years")
    move(p1, "CATCHMENT_STUDY", "bdm.priya", "Terms look viable; confirm the catchment before committing")
    move(p6, "SHORTLISTED", "bdm.priya")
    move(p6, "SITE_VISIT", "bdm.priya")
    move(p6, "NEGOTIATION", "bde.arjun", "Visited: smaller than Sri Venkateswara but cheaper; keep as backup")
    move(p2, "SHORTLISTED", "bdm.priya", "Strong location, truck access")
    move(p3, "SHORTLISTED", "bdm.priya")
    move(p3, "SITE_VISIT", "bdm.priya", "Check the corner visibility at peak hours")

    # M3: completed study for p1 (synthetic surveys), then roll-up + re-evaluation
    with SessionLocal() as db:
        st1 = db.scalar(select(CatchmentStudy).where(CatchmentStudy.property_id == uuid.UUID(p1))).id
    plan_and_assign(st1, 3000)
    print("CS-0001 synthetic lanes:", seed_surveys(st1, 1.0))
    with SessionLocal() as db:
        studies_api.complete_study(st1, studies_api.CompleteIn(), db, user(db, "sm.karthik"))
    drain()

    # M3: area study for Anna Nagar in progress (for the surveyor demo)
    with SessionLocal() as db:
        st2 = studies_api.request_study(studies_api.StudyIn(target_type="area", report_id=reps["600040"], radius_m=300,
                                                            notes="Ground-truth the top Anna Nagar hotspots"), db, bdm)["id"]
    plan_and_assign(st2, 3000)
    print("CS-0002 synthetic lanes (partial):", seed_surveys(st2, 0.5, only_labels={"A", "C"}))
    drain()

    with SessionLocal() as db:
        for r in db.execute(text("SELECT code, name, stage, latest_score, latest_recommendation FROM app.property ORDER BY code")):
            print(f"  {r.code} {r.stage:<16} {r.latest_score!s:<6} {r.latest_recommendation!s:<8} {r.name}")
        for r in db.execute(text("SELECT code, status, reuse_mode FROM app.catchment_study ORDER BY code")):
            print(f"  {r.code} {r.status} reuse={r.reuse_mode}")
    print("demo data ready. Try: BDM -> Pipeline -> Lakshmi Towers -> 'Request catchment study' (reuses CS-0001).")


if __name__ == "__main__":
    main()
