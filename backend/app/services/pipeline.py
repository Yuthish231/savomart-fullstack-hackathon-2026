"""Property pipeline: a declarative state machine plus an insert-only audit trail.

Stages mirror how a BD team actually moves a site: first sighting, desk evaluation,
shortlist, physical visit, commercial negotiation, catchment study, final sign-off.
REJECTED and ON_HOLD can be reached from any active stage and always need a reason.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import PipelineEvent, Property, Role

STAGES: list[tuple[str, str, str]] = [
    # key, label, what it means for the team
    ("SIGHTED", "Sighted", "Onboarded from the field; automatic evaluation running"),
    ("EVALUATED", "Evaluated", "Desk evaluation ready for the BD Manager"),
    ("SHORTLISTED", "Shortlisted", "Worth a closer look"),
    ("SITE_VISIT", "Site visit", "Executive asked to visit and verify on the ground"),
    ("NEGOTIATION", "Negotiation", "Visit done; commercial terms under discussion"),
    ("CATCHMENT_STUDY", "Catchment study", "Survey team checking the surrounding lanes"),
    ("FINAL_REVIEW", "Final review", "All evidence in; awaiting sign-off"),
    ("APPROVED", "Approved", "Go ahead with this site"),
    ("ON_HOLD", "On hold", "Paused; can be resumed"),
    ("REJECTED", "Rejected", "Not pursuing this site"),
]
STAGE_LABEL = {k: label for k, label, _ in STAGES}
ACTIVE = {"EVALUATED", "SHORTLISTED", "SITE_VISIT", "NEGOTIATION", "CATCHMENT_STUDY", "FINAL_REVIEW"}
TERMINAL = {"APPROVED", "REJECTED"}

SYSTEM = "SYSTEM"  # pseudo-role for automatic moves (evaluation done, study complete)


@dataclass(frozen=True)
class Transition:
    src: str
    dst: str
    roles: frozenset[str]
    label: str
    reason_required: bool = False
    owner_only_for_bde: bool = True  # a BD Executive may only move their own properties


def _t(src, dst, roles, label, reason=False):
    return Transition(src, dst, frozenset(roles), label, reason)


TRANSITIONS: list[Transition] = [
    _t("SIGHTED", "EVALUATED", {SYSTEM}, "Evaluation completed"),
    _t("EVALUATED", "SHORTLISTED", {Role.BDM}, "Shortlist"),
    _t("SHORTLISTED", "SITE_VISIT", {Role.BDM}, "Ask executive to visit"),
    _t("SITE_VISIT", "NEGOTIATION", {Role.BDM, Role.BDE}, "Visit done, start negotiation", reason=True),
    _t("NEGOTIATION", "CATCHMENT_STUDY", {Role.BDM}, "Request catchment study"),
    _t("NEGOTIATION", "FINAL_REVIEW", {Role.BDM}, "Skip study (existing data suffices)", reason=True),
    _t("CATCHMENT_STUDY", "FINAL_REVIEW", {SYSTEM, Role.BDM}, "Study complete, final review"),
    _t("FINAL_REVIEW", "APPROVED", {Role.BDM}, "Approve site"),
    _t("REJECTED", "EVALUATED", {Role.BDM}, "Reopen", reason=True),
    *[_t(s, "REJECTED", {Role.BDM}, "Reject", reason=True) for s in sorted(ACTIVE)],
    *[_t(s, "ON_HOLD", {Role.BDM}, "Put on hold", reason=True) for s in sorted(ACTIVE)],
]
# Resuming from hold returns to wherever the property was (see apply()).
RESUME = Transition("ON_HOLD", "*", frozenset({Role.BDM}), "Resume")


def allowed_transitions(stage: str, role: str, is_owner: bool = True) -> list[dict[str, Any]]:
    out = [
        {"to": t.dst, "label": t.label, "reason_required": t.reason_required}
        for t in TRANSITIONS
        if t.src == stage and role in t.roles and (role != Role.BDE or is_owner)
    ]
    if stage == "ON_HOLD" and role in RESUME.roles:
        out.append({"to": "RESUME", "label": RESUME.label, "reason_required": False})
    return out


def _find(src: str, dst: str) -> Transition | None:
    if src == "ON_HOLD" and dst == "RESUME":
        return RESUME
    return next((t for t in TRANSITIONS if t.src == src and t.dst == dst), None)


def record(db: Session, prop: Property, kind: str, actor_id: uuid.UUID | None, *,
           from_stage: str | None = None, to_stage: str | None = None,
           reason: str | None = None, data: dict | None = None) -> PipelineEvent:
    ev = PipelineEvent(property_id=prop.id, kind=kind, from_stage=from_stage, to_stage=to_stage,
                       actor_id=actor_id, reason=reason, data=data, at=datetime.now(UTC))
    db.add(ev)
    return ev


def apply(db: Session, prop: Property, dst: str, *, role: str, actor_id: uuid.UUID | None,
          reason: str | None = None, is_owner: bool = True) -> PipelineEvent:
    """Validate and apply a stage move; the stage change and its audit event share a transaction."""
    t = _find(prop.stage, dst)
    if t is None:
        raise AppError("PIPELINE_TRANSITION_NOT_ALLOWED",
                       f"Can't move from {STAGE_LABEL.get(prop.stage, prop.stage)} to "
                       f"{STAGE_LABEL.get(dst, dst)}", 409,
                       {"from": prop.stage, "to": dst,
                        "allowed": [x["to"] for x in allowed_transitions(prop.stage, role, is_owner)]})
    if role not in t.roles:
        raise AppError("FORBIDDEN", f"A {role} can't do '{t.label}'", 403)
    if role == Role.BDE and not is_owner:
        raise AppError("FORBIDDEN", "Executives can only update their own properties", 403)
    reason = (reason or "").strip() or None
    if t.reason_required and not reason:
        raise AppError("REASON_REQUIRED", f"Please give a reason for '{t.label}'", 422)

    src = prop.stage
    if t is RESUME:
        dst = prop.stage_before_hold or "EVALUATED"
        prop.stage_before_hold = None
    elif dst == "ON_HOLD":
        prop.stage_before_hold = src
    prop.stage = dst
    return record(db, prop, "stage", actor_id, from_stage=src, to_stage=dst, reason=reason,
                  data={"action": t.label})
