"""Smoke-test job: proves the queue, step progress and partial-failure paths end to end."""

import time

from app.jobs.queue import JobContext
from app.jobs.registry import task
from app.llm.provider import LLMUnavailable, get_llm

PING_STEPS = [("warmup", "Warming up"), ("work", "Doing the work"), ("llm", "Asking the LLM")]


@task("ping")
def ping(ctx: JobContext) -> None:
    delay = float(ctx.payload.get("delay_s", 1.0))

    ctx.run_step("warmup", lambda: time.sleep(delay))

    def work() -> None:
        time.sleep(delay)
        if ctx.payload.get("fail_work"):
            raise RuntimeError("simulated failure")

    ctx.run_step("work", work)

    def llm() -> None:
        out = get_llm().complete_json(
            'Reply with JSON {"ok": true, "echo": <the word you were sent>}.', "chennai"
        )
        if out.get("ok") is not True:
            raise LLMUnavailable(f"unexpected reply {out}")
        ctx.job.result = {"llm_echo": out.get("echo")}

    ctx.run_step("llm", llm, optional=True)
