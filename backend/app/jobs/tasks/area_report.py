"""Area Fitness Report job: aggregate → score + hotspots → grounded narrative."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import text

from app.jobs.queue import JobContext
from app.jobs.registry import task
from app.llm import grounding
from app.llm.provider import LLMUnavailable, compact_facts, get_llm
from app.models import Area, AreaReport
from app.services import area_analysis as aa
from app.services.scoring import SCORING_VERSION, grade, score_metrics, subs_as_dicts

STEPS = [
    ("aggregate", "Gathering area data"),
    ("score", "Scoring and finding hotspots"),
    ("narrative", "Writing the summary"),
]

SYSTEM_PROMPT = """You are a retail expansion analyst for Savomart, a neighbourhood grocery chain in Chennai.
Write a short, decision-ready assessment of one area for a BD Manager.

Hard rules:
- Use ONLY the facts provided. Every number you write must be one of the fact values (you may round it).
- Never estimate, extrapolate or introduce outside numbers, rents, incomes or dates.
- Cite facts: each reason and risk lists the fact ids it relies on in "fact_ids".
- "scout_first" must reference hotspot ids from the provided hotspot list only.
- Plain English, specific, no marketing tone. Mention data caveats honestly.

Return JSON exactly in this shape:
{"headline": str, "summary": str (2-3 sentences),
 "reasons": [{"text": str, "fact_ids": [str]}] (2-4 items),
 "scout_first": [{"hotspot_id": str, "text": str}] (1-3 items),
 "risks": [{"text": str, "fact_ids": [str]}] (1-3 items),
 "caveats": [str] (0-2 items)}"""


def _report(ctx: JobContext) -> AreaReport:
    return ctx.db.get(AreaReport, uuid.UUID(ctx.payload["report_id"]))


@task("area_report")
def run(ctx: JobContext) -> None:
    report = _report(ctx)
    area = ctx.db.get(Area, report.area_id)
    report.status = "running"
    ctx.db.commit()

    def aggregate() -> None:
        r = _report(ctx)
        r.metrics = aa.aggregate(ctx.db, area.id, area.h3_cells)
        r.data_sources = [dict(x._mapping) | {"as_of": x.as_of.isoformat() if x.as_of else None}
                          for x in ctx.db.execute(text(
                              "SELECT id, key, name, as_of, is_mock FROM ref.data_source ORDER BY key"))]
        ctx.db.commit()

    def score() -> None:
        r = _report(ctx)
        stats = dict(ctx.db.execute(text("SELECT metric, breakpoints FROM ref.metric_stats")).all())
        total, subs = score_metrics(r.metrics["model"], stats)
        conf, reasons = aa.confidence(r.metrics)
        spots = aa.hotspots(ctx.db, area.h3_cells, stats)
        r.overall_score, r.grade = total, grade(total)
        r.sub_scores = subs_as_dicts(subs)
        r.confidence, r.confidence_reasons = conf, reasons
        r.hotspots = spots
        r.facts = aa.build_facts(area.name, r.metrics, total, r.sub_scores, conf, spots)
        # Deterministic narrative first, so the report is complete even if the LLM step fails.
        r.narrative = aa.template_narrative(area.name, total, r.sub_scores, spots, conf, reasons)
        r.narrative_source = "template"
        ctx.db.commit()

    def narrative() -> None:
        r = _report(ctx)
        llm = get_llm()
        hotspot_ids = {h["id"] for h in r.hotspots or []}
        hotspots = "\n".join(
            f"{h['id']}: rank {h['rank']}, score {h['score']}, near {h['near_road'] or 'unnamed streets'}, "
            f"{h['nearest_store_km']} km to Savomart, strong on {', '.join(s['label'] for s in h['strengths'])}"
            for h in r.hotspots or [])
        user = (f"Area: {area.name}\n\nFacts (id: label = value unit):\n{compact_facts(r.facts)}"
                f"\n\nHotspots:\n{hotspots}\n\nConfidence notes: {' '.join(r.confidence_reasons or [])}")
        prompt, last_violations = user, []
        for _ in range(2):  # one retry with the violations spelled out
            out = llm.complete_json(SYSTEM_PROMPT, prompt)
            result = grounding.check(out, r.facts, hotspot_ids,
                                     context_texts=[area.name, *(h.get("near_road") or "" for h in r.hotspots or [])])
            if result.ok:
                r.narrative, r.narrative_source, r.llm_model = out, "llm", llm.model
                ctx.db.commit()
                return
            last_violations = result.violations
            prompt = (user + "\n\nYour previous answer broke the rules: " + "; ".join(result.violations[:8])
                      + ". Rewrite it using only the provided fact values.")
        raise LLMUnavailable("Narrative failed grounding checks: " + "; ".join(last_violations[:3]))

    ctx.run_step("aggregate", aggregate)
    ctx.run_step("score", score)
    ctx.run_step("narrative", narrative, optional=True)

    r = _report(ctx)
    r.status = "partial" if ctx.optional_failures else "completed"
    if ctx.optional_failures:
        r.error = "AI summary unavailable; showing the rule-based summary instead."
    r.completed_at = datetime.now(UTC)
    ctx.db.commit()
