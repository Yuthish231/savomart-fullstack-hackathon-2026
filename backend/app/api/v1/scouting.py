"""Scouting tasks (BD Manager directs executives to M1 hotspots) and the team directory."""

import uuid
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user, require_roles
from app.core.errors import AppError, NotFound
from app.models import Area, AreaReport, Role, ScoutingTask, User
from app.models.user import ROLE_LABELS

router = APIRouter(tags=["scouting"])


class TaskIn(BaseModel):
    report_id: uuid.UUID
    hotspot_id: str | None = None  # None = scout the whole area
    assignee_id: uuid.UUID
    note: str | None = Field(None, max_length=1000)
    due_date: date | None = None


class TaskOut(BaseModel):
    id: uuid.UUID
    title: str
    note: str | None
    lat: float
    lon: float
    radius_m: int
    status: str
    due_date: date | None
    report_id: uuid.UUID | None
    hotspot_id: str | None
    area_name: str | None
    assignee: dict
    assigned_by: dict
    properties_found: int
    created_at: datetime


@router.post("/scouting-tasks", response_model=TaskOut, status_code=201)
def create_task(body: TaskIn, db: Session = Depends(get_db), user: User = Depends(require_roles(Role.BDM))):
    report = db.get(AreaReport, body.report_id)
    if report is None:
        raise NotFound("Report", body.report_id)
    area = db.get(Area, report.area_id)
    assignee = db.get(User, body.assignee_id)
    if assignee is None or assignee.role != Role.BDE:
        raise AppError("INVALID_ASSIGNEE", "Scouting tasks go to BD Executives", 422)
    if body.hotspot_id:
        spot = next((h for h in report.hotspots or [] if h["id"] == body.hotspot_id), None)
        if spot is None:
            raise AppError("UNKNOWN_HOTSPOT", "That hotspot isn't in the report", 422)
        where = f" near {spot['near_road']}" if spot.get("near_road") else ""
        title = f"Hotspot {spot['rank']} in {area.name}{where}"
        lat, lon, radius, h3 = spot["lat"], spot["lon"], 500, spot["h3"]
    else:
        c = db.execute(text("SELECT ST_Y(ST_Centroid(geom)), ST_X(ST_Centroid(geom)) FROM app.area WHERE id = :i"),
                       {"i": area.id}).one()
        title, lat, lon, radius, h3 = f"Scout {area.name}", c[0], c[1], 1500, None
    task = ScoutingTask(report_id=report.id, area_id=area.id, hotspot_id=body.hotspot_id, h3=h3, title=title,
                        note=body.note, lat=lat, lon=lon, radius_m=radius, status="open", due_date=body.due_date,
                        assignee_id=assignee.id, assigned_by=user.id)
    db.add(task)
    db.commit()
    return _out(db, task)


@router.get("/scouting-tasks", response_model=list[TaskOut])
def list_tasks(report_id: uuid.UUID | None = None, include_closed: bool = False, db: Session = Depends(get_db),
               user: User = Depends(require_roles(Role.BDM, Role.BDE))):
    stmt = select(ScoutingTask).order_by(ScoutingTask.created_at.desc())
    if user.role == Role.BDE:
        stmt = stmt.where(ScoutingTask.assignee_id == user.id)
    if report_id:
        stmt = stmt.where(ScoutingTask.report_id == report_id)
    if not include_closed:
        stmt = stmt.where(ScoutingTask.status.in_(["open", "in_progress"]))
    return [_out(db, t) for t in db.scalars(stmt).all()]


class TaskPatch(BaseModel):
    status: Literal["open", "in_progress", "done", "cancelled"]


@router.patch("/scouting-tasks/{task_id}", response_model=TaskOut)
def update_task(task_id: uuid.UUID, body: TaskPatch, db: Session = Depends(get_db),
                user: User = Depends(require_roles(Role.BDM, Role.BDE))):
    task = db.get(ScoutingTask, task_id)
    if task is None:
        raise NotFound("Scouting task", task_id)
    if user.role == Role.BDE and (task.assignee_id != user.id or body.status == "cancelled"):
        raise AppError("FORBIDDEN", "Executives can update their own tasks (not cancel them)", 403)
    task.status = body.status
    db.commit()
    return _out(db, task)


def _out(db: Session, t: ScoutingTask) -> TaskOut:
    a, b = db.get(User, t.assignee_id), db.get(User, t.assigned_by)
    area = db.get(Area, t.area_id) if t.area_id else None
    n = db.scalar(text("SELECT count(*) FROM app.property WHERE scouting_task_id = :i"), {"i": t.id})
    return TaskOut(id=t.id, title=t.title, note=t.note, lat=t.lat, lon=t.lon, radius_m=t.radius_m, status=t.status,
                   due_date=t.due_date, report_id=t.report_id, hotspot_id=t.hotspot_id,
                   area_name=area.name if area else None, assignee={"id": a.id, "name": a.name},
                   assigned_by={"id": b.id, "name": b.name}, properties_found=n, created_at=t.created_at)


@router.get("/users")
def list_users(role: Role | None = None, db: Session = Depends(get_db),
               _: User = Depends(require_roles(Role.BDM, Role.SM))):
    """Team directory with current workload, for assignment dropdowns."""
    rows = db.execute(text("""
        SELECT u.id, u.name, u.role,
               (SELECT count(*) FROM app.scouting_task t
                 WHERE t.assignee_id = u.id AND t.status IN ('open', 'in_progress')) AS open_tasks
          FROM app."user" u
         WHERE u.is_active AND (CAST(:role AS text) IS NULL OR u.role = CAST(:role AS text))
         ORDER BY u.name
    """), {"role": role.value if role else None})
    return [dict(r._mapping) | {"role_label": ROLE_LABELS[Role(r.role)]} for r in rows]
