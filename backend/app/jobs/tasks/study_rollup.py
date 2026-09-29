"""Catchment study roll-up: lane surveys → insight → property re-evaluation / area update."""

import json
import uuid
from datetime import UTC, datetime

from app.jobs.queue import JobContext
from app.jobs.registry import task
from app.llm import grounding
from app.llm.provider import LLMUnavailable, get_llm
from app.models import CatchmentStudy, Property
from app.services import pipeline, rollup
from app.services import properties as prop_svc

SYSTEM_PROMPT = """You are a retail analyst summarising a ground survey of the lanes around a candidate
grocery store site in Chennai for a BD Manager. Use ONLY the facts provided; every number you write must
be one of the fact values (rounding allowed). Cite fact ids for each reason and risk.
Return JSON: {"headline": str, "summary": str (2 sentences), "reasons": [{"text": str, "fact_ids": [str]}],
"risks": [{"text": str, "fact_ids": [str]}], "caveats": [str]}"""


def _study(ctx: JobContext) -> CatchmentStudy:
    return ctx.db.get(CatchmentStudy, uuid.UUID(ctx.payload["study_id"]))


@task("study_rollup")
def run(ctx: JobContext) -> None:
    def aggregate() -> None:
        s = _study(ctx)
        s.insight = rollup.gather(ctx.db, s)
        s.insight_narrative = rollup.template_narrative(s, s.insight) | {"source": "template"}
        ctx.db.commit()

    def narrative() -> None:
        s = _study(ctx)
        facts = rollup.build_facts(s, s.insight)
        llm = get_llm()
        user = json.dumps({"study": s.code, "facts": facts}, ensure_ascii=False)
        prompt = user
        for _ in range(2):
            out = llm.complete_json(SYSTEM_PROMPT, prompt)
            res = grounding.check(out, facts, set())
            if res.ok:
                s.insight_narrative = out | {"source": "llm", "model": llm.model}
                ctx.db.commit()
                return
            prompt = user + "\n\nYour previous answer broke the rules: " + "; ".join(res.violations[:8])
        raise LLMUnavailable("Insight narrative failed grounding checks")

    def apply() -> None:
        s = _study(ctx)
        s.status, s.completed_at = "COMPLETED", datetime.now(UTC)
        if s.property_id:
            prop = ctx.db.get(Property, s.property_id)
            pipeline.record(ctx.db, prop, "note", None, reason=f"Catchment study {s.code} completed",
                            data={"study_id": str(s.id), "households_est": s.insight.get("households_est"),
                                  "reuse_mode": s.reuse_mode})
            prop_svc.queue_evaluation(ctx.db, prop, "catchment", None, overrides=rollup.evaluation_overrides(s))
            if prop.stage == "CATCHMENT_STUDY":
                pipeline.apply(ctx.db, prop, "FINAL_REVIEW", role=pipeline.SYSTEM, actor_id=None)
        ctx.db.commit()

    ctx.run_step("aggregate", aggregate)
    ctx.run_step("narrative", narrative, optional=True)
    ctx.run_step("apply", apply)
