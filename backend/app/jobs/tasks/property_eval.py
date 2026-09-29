"""Property evaluation job: context around the pin → site assessment → grounded narrative."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from shapely import wkb

from app.jobs.queue import JobContext
from app.jobs.registry import task
from app.llm import grounding
from app.llm.provider import LLMUnavailable, compact_facts, get_llm
from app.models import CatchmentStudy, Property, PropertyEvaluation
from app.services import evaluation as ev_svc
from app.services import pipeline, rollup

SYSTEM_PROMPT = """You are a retail real-estate analyst for Savomart, a neighbourhood grocery chain in Chennai.
Assess one candidate property for a BD Manager who must decide in 30 seconds.

Hard rules:
- Use ONLY the facts provided. Every number you write must be one of the fact values (you may round it).
- Do not invent rents, incomes, footfall counts, distances or dates.
- Each reason and risk lists the fact ids it relies on in "fact_ids" (use [] only for purely qualitative points
  taken from the provided insight/risk texts).
- Respect the provided recommendation; explain it, do not change it.

Return JSON exactly in this shape:
{"headline": str, "summary": str (2 sentences),
 "reasons": [{"text": str, "fact_ids": [str]}] (2-3 items),
 "risks": [{"text": str, "fact_ids": [str]}] (1-3 items),
 "next_step": str, "caveats": [str] (0-2 items)}"""


def _ev(ctx: JobContext) -> PropertyEvaluation:
    return ctx.db.get(PropertyEvaluation, uuid.UUID(ctx.payload["evaluation_id"]))


@task("property_eval")
def run(ctx: JobContext) -> None:
    ev = _ev(ctx)
    prop = ctx.db.get(Property, ev.property_id)
    ev.status = "running"
    ctx.db.commit()
    pin = wkb.loads(bytes(prop.pin.data))
    inputs = {**prop.details, "rent_monthly": prop.rent_monthly, "carpet_sqft": prop.carpet_sqft}

    overrides = ctx.payload.get("overrides") or None
    if overrides is None:  # re-runs keep the latest completed catchment study's ground truth
        study = ctx.db.scalar(select(CatchmentStudy).where(
            CatchmentStudy.property_id == prop.id, CatchmentStudy.status == "COMPLETED")
            .order_by(CatchmentStudy.completed_at.desc()).limit(1))
        overrides = rollup.evaluation_overrides(study) if study else None

    def context() -> None:
        e = _ev(ctx)
        e.context = ev_svc.gather_context(ctx.db, pin.y, pin.x, overrides)
        e.inputs_snapshot = inputs | {"flags": prop.flags, "lat": pin.y, "lon": pin.x}
        ctx.db.commit()

    def assess() -> None:
        e = _ev(ctx)
        a = ev_svc.assess(ctx.db, inputs, e.context, prop.flags)
        e.score, e.location_score, e.site_score = a["score"], a["location_score"], a["site_score"]
        e.recommendation = a["recommendation"]
        e.checks, e.insights, e.risks = a["checks"], a["insights"], a["risks"]
        e.context = {**e.context, "location_subs": a["location_subs"], "blockers": a["blockers"]}
        e.facts = ev_svc.build_facts(inputs, e.context, a)
        e.narrative, e.narrative_source = ev_svc.template_narrative(prop.name, a), "template"
        ctx.db.commit()

    def narrative() -> None:
        e = _ev(ctx)
        llm = get_llm()
        user = (f"Property: {prop.name}\nRecommendation: {e.recommendation}\n\n"
                f"Facts (id: label = value unit):\n{compact_facts(e.facts)}\n\n"
                "Insights:\n" + "\n".join(f"- {i['text']}" for i in e.insights or []) + "\n\n"
                "Risks:\n" + "\n".join(f"- {r['text']}" for r in e.risks or []))
        prompt, violations = user, []
        for _ in range(2):
            out = llm.complete_json(SYSTEM_PROMPT, prompt)
            res = grounding.check(out, e.facts, set(), context_texts=[prop.name, prop.code])
            if res.ok:
                e.narrative, e.narrative_source, e.llm_model = out, "llm", llm.model
                ctx.db.commit()
                return
            violations = res.violations
            prompt = user + "\n\nYour previous answer broke the rules: " + "; ".join(violations[:8])
        raise LLMUnavailable("Narrative failed grounding checks: " + "; ".join(violations[:3]))

    ctx.run_step("context", context)
    ctx.run_step("assess", assess)
    ctx.run_step("narrative", narrative, optional=True)

    e = _ev(ctx)
    prop = ctx.db.get(Property, e.property_id)
    prev = ctx.db.scalar(select(PropertyEvaluation).where(
        PropertyEvaluation.property_id == prop.id, PropertyEvaluation.version < e.version,
        PropertyEvaluation.score.is_not(None)).order_by(PropertyEvaluation.version.desc()).limit(1))
    e.status = "partial" if ctx.optional_failures else "completed"
    e.error = "AI summary unavailable; showing the rule-based summary." if ctx.optional_failures else None
    e.completed_at = datetime.now(UTC)
    prop.latest_score, prop.latest_recommendation, prop.latest_evaluation_id = e.score, e.recommendation, e.id
    pipeline.record(ctx.db, prop, "evaluation", None, data={
        "version": e.version, "trigger": e.trigger, "score": e.score, "recommendation": e.recommendation,
        "previous_score": prev.score if prev else None})
    if prop.stage == "SIGHTED":
        pipeline.apply(ctx.db, prop, "EVALUATED", role=pipeline.SYSTEM, actor_id=None)
    ctx.db.commit()
