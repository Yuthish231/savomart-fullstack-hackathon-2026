"""M2 properties: onboarding from the field, evaluation, pipeline moves, photos, timeline."""

import uuid
from datetime import date, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, require_roles
from app.core.errors import AppError, NotFound
from app.models import (PipelineEvent, Property, PropertyEvaluation, PropertyPhoto, Role, ScoutingTask, User)
from app.services import pipeline
from app.services import properties as svc
from app.services.evaluation import ACCESS, FLOORS, PROPERTY_TYPES, VISIBILITY
from app.storage.media import save_image

router = APIRouter(tags=["properties"])
field_or_manager = require_roles(Role.BDE, Role.BDM)
viewer = require_roles(Role.BDE, Role.BDM, Role.SM)


class Gps(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    accuracy: float | None = Field(None, ge=0)


class PropertyIn(BaseModel):
    name: str = Field(min_length=3, max_length=160)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    gps: Gps | None = None
    address: str | None = Field(None, max_length=400)
    landmark: str | None = Field(None, max_length=160)
    property_type: Literal["shop", "showroom", "standalone", "mall_unit", "other"] = "shop"
    floor: Literal["ground", "first", "basement", "upper"]
    carpet_sqft: float = Field(ge=50, le=50_000)
    frontage_ft: float | None = Field(None, ge=1, le=500)
    rent_monthly: float | None = Field(None, ge=1_000, le=10_000_000)
    deposit: float | None = Field(None, ge=0, le=100_000_000)
    lease_years: int | None = Field(None, ge=1, le=30)
    parking_2w: int | None = Field(None, ge=0, le=500)
    parking_4w: int | None = Field(None, ge=0, le=200)
    power_kw: float | None = Field(None, ge=0, le=1000)
    delivery_access: Literal["truck", "van", "two_wheeler", "none"] | None = None
    visibility: Literal["main_road", "side_street", "inside_lane"] | None = None
    landlord_name: str | None = Field(None, max_length=120)
    landlord_phone: str | None = Field(None, pattern=r"^[0-9+\- ]{8,16}$")
    available_from: date | None = None
    notes: str | None = Field(None, max_length=2000)
    scouting_task_id: uuid.UUID | None = None
    confirmed_not_duplicate: bool = False


DETAIL_KEYS = ["property_type", "floor", "frontage_ft", "deposit", "lease_years", "parking_2w", "parking_4w",
               "power_kw", "delivery_access", "visibility", "landlord_name", "landlord_phone", "available_from",
               "notes"]


def _details(body: PropertyIn) -> dict[str, Any]:
    d = body.model_dump(include=set(DETAIL_KEYS), mode="json")
    return {k: v for k, v in d.items() if v is not None}


class CheckIn(BaseModel):
    lat: float
    lon: float
    name: str = ""
    landmark: str | None = None


@router.post("/properties/check")
def precheck(body: CheckIn, db: Session = Depends(get_db), _: User = Depends(field_or_manager)):
    """Before submit: is the pin in Chennai, which pincode/rent band, any likely duplicates?"""
    inside = svc.in_region(db, body.lat, body.lon)
    band = db.execute(text("""
        SELECT p.pincode, p.office_name, r.rent_psf_min AS min, r.rent_psf_max AS max
          FROM ref.pincode p LEFT JOIN ref.rent_band_mock r USING (pincode)
         WHERE ST_Contains(p.geom, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)) ORDER BY p.area_km2 LIMIT 1
    """), {"lat": body.lat, "lon": body.lon}).first()
    return {
        "in_region": inside,
        "pincode": band.pincode if band else None,
        "locality": band.office_name if band else None,
        "rent_band": {"min": band.min, "max": band.max, "is_mock": True} if band and band.min else None,
        "duplicates": svc.find_duplicates(db, body.lat, body.lon, body.name, body.landmark) if inside else [],
    }


@router.post("/properties", status_code=201)
def create_property(body: PropertyIn, db: Session = Depends(get_db), user: User = Depends(field_or_manager)):
    if not svc.in_region(db, body.lat, body.lon):
        raise AppError("OUT_OF_REGION", "That pin is outside the Chennai Metropolitan Area. Check the location.", 422)
    if body.scouting_task_id:
        task = db.get(ScoutingTask, body.scouting_task_id)
        if task is None or (user.role == Role.BDE and task.assignee_id != user.id):
            raise AppError("INVALID_TASK", "That scouting task isn't assigned to you", 422)
        if task.status == "open":
            task.status = "in_progress"
    details = _details(body)
    dups = svc.find_duplicates(db, body.lat, body.lon, body.name, body.landmark)
    flags = svc.compute_flags(db, body.lat, body.lon, body.gps.model_dump() if body.gps else None,
                              {**details, "rent_monthly": body.rent_monthly}, dups, body.confirmed_not_duplicate)
    pincode = db.scalar(text("""SELECT pincode FROM ref.pincode
        WHERE ST_Contains(geom, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)) ORDER BY area_km2 LIMIT 1"""),
                        {"lat": body.lat, "lon": body.lon})
    prop = Property(
        code=svc.next_code(db), name=body.name.strip(), stage="SIGHTED", scouting_task_id=body.scouting_task_id,
        created_by=user.id, pin=f"SRID=4326;POINT({body.lon} {body.lat})",
        gps_fix=f"SRID=4326;POINT({body.gps.lon} {body.gps.lat})" if body.gps else None,
        gps_accuracy_m=body.gps.accuracy if body.gps else None, address=body.address, landmark=body.landmark,
        pincode=pincode, details=details, rent_monthly=body.rent_monthly, carpet_sqft=body.carpet_sqft,
        flags=flags,
        duplicate_of=uuid.UUID(dups[0]["id"]) if dups and not body.confirmed_not_duplicate else None,
    )
    db.add(prop)
    db.flush()
    pipeline.record(db, prop, "stage", user.id, from_stage=None, to_stage="SIGHTED",
                    data={"action": "Onboarded from the field", "flags": [f["code"] for f in flags]})
    svc.queue_evaluation(db, prop, "created", user.id)
    db.commit()
    return _detail(db, prop, user)


@router.patch("/properties/{prop_id}")
def edit_property(prop_id: uuid.UUID, body: PropertyIn, db: Session = Depends(get_db),
                  user: User = Depends(field_or_manager)):
    """Correct captured details (e.g. a wrong pin or missing rent). Triggers a new evaluation version."""
    prop = _get(db, prop_id)
    svc.assert_can_view(prop, user)
    if prop.stage in pipeline.TERMINAL:
        raise AppError("PROPERTY_CLOSED", "Approved or rejected properties can't be edited; reopen first", 409)
    if not svc.in_region(db, body.lat, body.lon):
        raise AppError("OUT_OF_REGION", "That pin is outside the Chennai Metropolitan Area", 422)
    before = {"lat": _latlon(db, prop)[0], "lon": _latlon(db, prop)[1], "rent_monthly": prop.rent_monthly,
              "carpet_sqft": prop.carpet_sqft, **prop.details}
    details = _details(body)
    dups = svc.find_duplicates(db, body.lat, body.lon, body.name, body.landmark, exclude=prop.id)
    prop.name, prop.address, prop.landmark = body.name.strip(), body.address, body.landmark
    prop.pin = f"SRID=4326;POINT({body.lon} {body.lat})"
    if body.gps:
        prop.gps_fix = f"SRID=4326;POINT({body.gps.lon} {body.gps.lat})"
        prop.gps_accuracy_m = body.gps.accuracy
    prop.details, prop.rent_monthly, prop.carpet_sqft = details, body.rent_monthly, body.carpet_sqft
    prop.flags = svc.compute_flags(db, body.lat, body.lon, body.gps.model_dump() if body.gps else None,
                                   {**details, "rent_monthly": body.rent_monthly}, dups, body.confirmed_not_duplicate)
    after = {"lat": body.lat, "lon": body.lon, "rent_monthly": body.rent_monthly, "carpet_sqft": body.carpet_sqft,
             **details}
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    pipeline.record(db, prop, "edit", user.id, data={"changed": changed})
    svc.queue_evaluation(db, prop, "edited", user.id)
    db.commit()
    return _detail(db, prop, user)


class PropertySummary(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    stage: str
    latest_score: float | None
    latest_recommendation: str | None
    flags: list[dict[str, Any]]
    pincode: str | None
    carpet_sqft: float | None
    rent_monthly: float | None
    created_by_name: str
    created_at: datetime
    updated_at: datetime
    lat: float
    lon: float
    cover_photo: str | None


@router.get("/properties", response_model=list[PropertySummary])
def list_properties(stage: str | None = None, db: Session = Depends(get_db), user: User = Depends(viewer)):
    rows = db.execute(text("""
        SELECT p.id, p.code, p.name, p.stage, p.latest_score, p.latest_recommendation, p.flags, p.pincode,
               p.carpet_sqft, p.rent_monthly, u.name AS created_by_name, p.created_at, p.updated_at,
               ST_Y(p.pin) AS lat, ST_X(p.pin) AS lon,
               (SELECT path FROM app.property_photo ph WHERE ph.property_id = p.id
                 ORDER BY (ph.kind = 'front') DESC, ph.created_at LIMIT 1) AS cover_photo
          FROM app.property p JOIN app."user" u ON u.id = p.created_by
         WHERE (CAST(:stage AS text) IS NULL OR p.stage = CAST(:stage AS text))
           AND (CAST(:mine AS text) IS NULL OR p.created_by = CAST(:mine AS uuid))
         ORDER BY p.updated_at DESC LIMIT 300
    """), {"stage": stage, "mine": str(user.id) if user.role == Role.BDE else None})
    return [PropertySummary(**r._mapping) for r in rows]


@router.get("/pipeline/stages")
def stages(_: User = Depends(get_current_user)):
    return [{"key": k, "label": label, "description": d} for k, label, d in pipeline.STAGES]


@router.get("/properties/{prop_id}")
def get_property(prop_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(viewer)):
    prop = _get(db, prop_id)
    svc.assert_can_view(prop, user)
    return _detail(db, prop, user)


@router.get("/properties/{prop_id}/evaluations")
def list_evaluations(prop_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(viewer)):
    prop = _get(db, prop_id)
    svc.assert_can_view(prop, user)
    evs = db.scalars(select(PropertyEvaluation).where(PropertyEvaluation.property_id == prop.id)
                     .order_by(PropertyEvaluation.version.desc())).all()
    return [{"id": e.id, "version": e.version, "trigger": e.trigger, "status": e.status, "score": e.score,
             "recommendation": e.recommendation, "created_at": e.created_at} for e in evs]


class TransitionIn(BaseModel):
    to: str
    reason: str | None = Field(None, max_length=1000)


@router.post("/properties/{prop_id}/transitions")
def transition(prop_id: uuid.UUID, body: TransitionIn, db: Session = Depends(get_db),
               user: User = Depends(field_or_manager)):
    prop = _get(db, prop_id)
    svc.assert_can_view(prop, user)
    if body.to == "CATCHMENT_STUDY" and prop.stage == "NEGOTIATION":
        from app.services import studies as study_svc  # local import: avoid a module cycle

        study = study_svc.create_study(db, target_type="property", requested_by=user.id, prop=prop,
                                       notes=body.reason)
        pipeline.apply(db, prop, "CATCHMENT_STUDY", role=user.role, actor_id=user.id,
                       reason=body.reason or f"Requested {study.code}", is_owner=prop.created_by == user.id)
        db.commit()
        return _detail(db, prop, user)
    pipeline.apply(db, prop, body.to, role=user.role, actor_id=user.id, reason=body.reason,
                   is_owner=prop.created_by == user.id)
    if prop.stage in ("REJECTED", "APPROVED") and prop.scouting_task_id:
        task = db.get(ScoutingTask, prop.scouting_task_id)
        if task and task.status == "in_progress":
            task.status = "done"
    db.commit()
    return _detail(db, prop, user)


class NoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


@router.post("/properties/{prop_id}/notes")
def add_note(prop_id: uuid.UUID, body: NoteIn, db: Session = Depends(get_db), user: User = Depends(viewer)):
    prop = _get(db, prop_id)
    svc.assert_can_view(prop, user)
    pipeline.record(db, prop, "note", user.id, reason=body.text.strip())
    db.commit()
    return _detail(db, prop, user)


@router.post("/properties/{prop_id}/reevaluate")
def reevaluate(prop_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_roles(Role.BDM))):
    prop = _get(db, prop_id)
    svc.queue_evaluation(db, prop, "manual", user.id)
    db.commit()
    return _detail(db, prop, user)


@router.post("/properties/{prop_id}/photos", status_code=201)
async def upload_photo(prop_id: uuid.UUID, kind: Literal["front", "interior", "street", "other"] = Form("other"),
                       file: UploadFile = File(...), db: Session = Depends(get_db),
                       user: User = Depends(field_or_manager)):
    prop = _get(db, prop_id)
    svc.assert_can_view(prop, user)
    path, size = save_image(f"properties/{prop.id}", await file.read(), file.content_type or "")
    db.add(PropertyPhoto(property_id=prop.id, kind=kind, path=path, size_bytes=size, uploaded_by=user.id))
    db.commit()
    return {"path": path, "kind": kind, "size_bytes": size}


# --- helpers ---------------------------------------------------------------------------------

def _get(db: Session, prop_id: uuid.UUID) -> Property:
    prop = db.get(Property, prop_id)
    if prop is None:
        raise NotFound("Property", prop_id)
    return prop


def _latlon(db: Session, prop: Property) -> tuple[float, float]:
    r = db.execute(text("SELECT ST_Y(pin), ST_X(pin) FROM app.property WHERE id = :i"), {"i": prop.id}).one()
    return float(r[0]), float(r[1])


def _eval_out(e: PropertyEvaluation | None, db: Session) -> dict[str, Any] | None:
    if e is None:
        return None
    job = None
    if e.job_id:
        j = db.execute(text("SELECT status, steps, error FROM app.job WHERE id = :i"), {"i": e.job_id}).first()
        job = dict(j._mapping) if j else None
    return {k: getattr(e, k) for k in (
        "id", "version", "trigger", "status", "score", "location_score", "site_score", "recommendation", "checks",
        "insights", "risks", "context", "facts", "narrative", "narrative_source", "llm_model", "error",
        "created_at", "completed_at")} | {"job": job}


def _detail(db: Session, prop: Property, user: User) -> dict[str, Any]:
    lat, lon = _latlon(db, prop)
    evs = db.scalars(select(PropertyEvaluation).where(PropertyEvaluation.property_id == prop.id)
                     .order_by(PropertyEvaluation.version.desc())).all()
    latest = evs[0] if evs else None
    last_done = next((e for e in evs if e.score is not None), None)
    prev_done = next((e for e in evs if e.score is not None and last_done and e.version < last_done.version), None)
    photos = db.scalars(select(PropertyPhoto).where(PropertyPhoto.property_id == prop.id)
                        .order_by(PropertyPhoto.created_at)).all()
    events = db.execute(text("""
        SELECT e.id, e.kind, e.from_stage, e.to_stage, e.reason, e.data, e.at, u.name AS actor, u.role AS actor_role
          FROM app.pipeline_event e LEFT JOIN app."user" u ON u.id = e.actor_id
         WHERE e.property_id = :i ORDER BY e.at DESC
    """), {"i": prop.id}).all()
    creator = db.get(User, prop.created_by)
    task = db.get(ScoutingTask, prop.scouting_task_id) if prop.scouting_task_id else None
    gps = None
    if prop.gps_fix is not None:
        g = db.execute(text("SELECT ST_Y(gps_fix), ST_X(gps_fix) FROM app.property WHERE id = :i"), {"i": prop.id}).one()
        gps = {"lat": g[0], "lon": g[1], "accuracy": prop.gps_accuracy_m}
    details = dict(prop.details)
    if user.role == Role.SM:  # landlord contact is only for the BD team
        details.pop("landlord_phone", None)
    return {
        "id": prop.id, "code": prop.code, "name": prop.name, "stage": prop.stage,
        "stage_label": pipeline.STAGE_LABEL[prop.stage], "stage_before_hold": prop.stage_before_hold,
        "lat": lat, "lon": lon, "gps": gps, "address": prop.address, "landmark": prop.landmark,
        "pincode": prop.pincode, "details": details, "rent_monthly": prop.rent_monthly,
        "carpet_sqft": prop.carpet_sqft, "flags": prop.flags, "duplicate_of": prop.duplicate_of,
        "latest_score": prop.latest_score, "latest_recommendation": prop.latest_recommendation,
        "previous_score": prev_done.score if prev_done else None,
        "created_by": {"id": creator.id, "name": creator.name}, "created_at": prop.created_at,
        "updated_at": prop.updated_at,
        "scouting_task": {"id": task.id, "title": task.title} if task else None,
        "evaluation": _eval_out(latest, db),
        "last_completed_evaluation": _eval_out(last_done, db) if last_done and latest and last_done.id != latest.id else None,
        "photos": [{"id": p.id, "kind": p.kind, "path": p.path} for p in photos],
        "events": [dict(e._mapping) for e in events],
        "studies": [dict(r._mapping) for r in db.execute(text("""
            SELECT id, code, status, reuse_mode, reuse_coverage, created_at, completed_at,
                   (insight ->> 'households_est')::int AS households_est
              FROM app.catchment_study WHERE property_id = :i ORDER BY created_at DESC
        """), {"i": prop.id})],
        "allowed_transitions": pipeline.allowed_transitions(prop.stage, user.role, prop.created_by == user.id)
        if user.role in (Role.BDM, Role.BDE) else [],
        "labels": {"floor": FLOORS, "delivery_access": ACCESS, "visibility": VISIBILITY,
                   "property_type": PROPERTY_TYPES},
    }
