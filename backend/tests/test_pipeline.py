import uuid

import pytest

from app.core.errors import AppError
from app.models import Property, Role
from app.services import pipeline


class FakeDB:
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)


def prop(stage="EVALUATED"):
    return Property(id=uuid.uuid4(), stage=stage)


def test_happy_path_to_approval():
    db, p, bdm = FakeDB(), prop(), uuid.uuid4()
    for dst, reason in [("SHORTLISTED", None), ("SITE_VISIT", None), ("NEGOTIATION", "Owner flexible on rent"),
                        ("CATCHMENT_STUDY", None), ("FINAL_REVIEW", None), ("APPROVED", None)]:
        pipeline.apply(db, p, dst, role=Role.BDM, actor_id=bdm, reason=reason)
    assert p.stage == "APPROVED"
    assert [e.to_stage for e in db.added] == ["SHORTLISTED", "SITE_VISIT", "NEGOTIATION", "CATCHMENT_STUDY",
                                               "FINAL_REVIEW", "APPROVED"]
    assert all(e.actor_id == bdm and e.kind == "stage" for e in db.added)


def test_illegal_jump_is_rejected_with_allowed_moves():
    with pytest.raises(AppError) as e:
        pipeline.apply(FakeDB(), prop("EVALUATED"), "APPROVED", role=Role.BDM, actor_id=None)
    assert e.value.code == "PIPELINE_TRANSITION_NOT_ALLOWED"
    assert "SHORTLISTED" in e.value.details["allowed"]


def test_reject_requires_reason():
    with pytest.raises(AppError) as e:
        pipeline.apply(FakeDB(), prop("SHORTLISTED"), "REJECTED", role=Role.BDM, actor_id=None, reason="  ")
    assert e.value.code == "REASON_REQUIRED"


def test_executive_cannot_shortlist_but_can_report_own_visit():
    with pytest.raises(AppError) as e:
        pipeline.apply(FakeDB(), prop("EVALUATED"), "SHORTLISTED", role=Role.BDE, actor_id=None)
    assert e.value.code == "FORBIDDEN"
    p = prop("SITE_VISIT")
    pipeline.apply(FakeDB(), p, "NEGOTIATION", role=Role.BDE, actor_id=None, reason="Seen it; 22 ft frontage")
    assert p.stage == "NEGOTIATION"
    with pytest.raises(AppError):
        pipeline.apply(FakeDB(), prop("SITE_VISIT"), "NEGOTIATION", role=Role.BDE, actor_id=None,
                       reason="x", is_owner=False)


def test_hold_and_resume_returns_to_previous_stage():
    db, p = FakeDB(), prop("NEGOTIATION")
    pipeline.apply(db, p, "ON_HOLD", role=Role.BDM, actor_id=None, reason="Owner travelling")
    assert p.stage == "ON_HOLD" and p.stage_before_hold == "NEGOTIATION"
    pipeline.apply(db, p, "RESUME", role=Role.BDM, actor_id=None)
    assert p.stage == "NEGOTIATION" and p.stage_before_hold is None


def test_allowed_transitions_are_role_shaped():
    bdm = {t["to"] for t in pipeline.allowed_transitions("EVALUATED", Role.BDM)}
    bde = {t["to"] for t in pipeline.allowed_transitions("EVALUATED", Role.BDE)}
    assert {"SHORTLISTED", "REJECTED", "ON_HOLD"} <= bdm
    assert bde == set()
