"""Swappable LLM provider.

Any OpenAI-compatible endpoint works (Groq, OpenAI, Ollama, vLLM...) by changing
LLM_BASE_URL / LLM_MODEL / LLM_API_KEY. With no key configured we fall back to
NullProvider, and callers use their deterministic template narrative instead.
"""

import json
import logging
import re
import time
from functools import lru_cache
from typing import Any, Protocol

from app.core.config import get_settings

log = logging.getLogger(__name__)


class LLMUnavailable(Exception):
    """No provider configured, the call failed, or the output was not valid JSON."""


class LLMProvider(Protocol):
    name: str
    model: str

    def complete_json(self, system: str, user: str, *, temperature: float = 0.2) -> dict[str, Any]:
        ...


class NullProvider:
    name = "none"
    model = "template"

    def complete_json(self, system: str, user: str, *, temperature: float = 0.2) -> dict[str, Any]:
        raise LLMUnavailable("No LLM configured (LLM_API_KEY is empty)")


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_json_object(raw: str) -> dict[str, Any]:
    """Models occasionally wrap JSON in fences or add a preamble; recover the object."""
    cleaned = _FENCE.sub("", raw.strip())
    try:
        obj = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise LLMUnavailable("Model did not return JSON")
        try:
            obj = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise LLMUnavailable(f"Model returned malformed JSON: {exc}") from exc
    if not isinstance(obj, dict):
        raise LLMUnavailable("Model returned JSON that is not an object")
    return obj


class OpenAICompatibleProvider:
    name = "openai-compatible"

    def __init__(self, base_url: str, api_key: str, model: str, timeout_s: float,
                 max_tokens: int = 1500, reasoning_effort: str = "", rate_limit_wait_s: float = 90) -> None:
        from openai import OpenAI

        self.model = model
        self.max_tokens = max_tokens
        self.reasoning_effort = reasoning_effort
        self.rate_limit_wait_s = rate_limit_wait_s
        # Retries are handled below so rate limits can wait as long as the provider asks.
        self._client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout_s, max_retries=0)

    def _create(self, system: str, user: str, temperature: float):
        extra = {"reasoning_effort": self.reasoning_effort} if self.reasoning_effort else None
        return self._client.chat.completions.create(
            model=self.model,
            temperature=temperature,
            max_tokens=self.max_tokens,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            extra_body=extra,
        )

    def complete_json(self, system: str, user: str, *, temperature: float = 0.2) -> dict[str, Any]:
        from openai import APIConnectionError, APITimeoutError, InternalServerError, RateLimitError

        started = time.perf_counter()
        waited, attempt = 0.0, 0
        while True:
            attempt += 1
            try:
                resp = self._create(system, user, temperature)
                break
            except RateLimitError as exc:
                # Free tiers limit tokens per minute: wait as long as the provider says, then retry.
                wait = _retry_after_s(exc)
                if waited + wait > self.rate_limit_wait_s:
                    raise LLMUnavailable(f"LLM rate limit: still limited after waiting {waited:.0f}s") from exc
                log.warning("llm rate limited (attempt %d); waiting %.1fs", attempt, wait)
                time.sleep(wait)
                waited += wait
            except (APIConnectionError, APITimeoutError, InternalServerError) as exc:
                if attempt >= 3:
                    raise LLMUnavailable(f"LLM call failed: {exc}") from exc
                time.sleep(2 * attempt)
            except Exception as exc:  # auth, bad request: retrying won't help
                raise LLMUnavailable(f"LLM call failed: {exc}") from exc
        content = resp.choices[0].message.content or ""
        usage = getattr(resp, "usage", None)
        log.info(
            "llm_call model=%s latency_ms=%d prompt_tokens=%s completion_tokens=%s",
            self.model,
            (time.perf_counter() - started) * 1000,
            getattr(usage, "prompt_tokens", None),
            getattr(usage, "completion_tokens", None),
        )
        return parse_json_object(content)


def _retry_after_s(exc: Exception) -> float:
    """Seconds to wait from a 429: `retry-after` header, else Groq's token-reset hint, else 5 s."""
    headers = getattr(getattr(exc, "response", None), "headers", None) or {}
    ra = headers.get("retry-after")
    if ra:
        try:
            return max(1.0, float(ra))
        except ValueError:
            pass
    reset = headers.get("x-ratelimit-reset-tokens") or ""  # e.g. "7.66s", "720ms", "1m2s"
    m = re.fullmatch(r"(?:(\d+)m)?(?:([\d.]+)s)?(?:([\d.]+)ms)?", reset.strip())
    if m and any(m.groups()):
        mins, secs, ms = (float(g) if g else 0.0 for g in m.groups())
        return max(1.0, mins * 60 + secs + ms / 1000 + 0.5)
    return 5.0


def compact_facts(facts: dict[str, dict[str, Any]]) -> str:
    """Facts as short `id: label = value unit` lines: far fewer tokens than the JSON form,
    which matters on free tiers limited by tokens per minute."""
    lines = []
    for fid, f in facts.items():
        unit = f.get("unit") or ""
        lines.append(f"{fid}: {f.get('label', fid)} = {f.get('value')}{(' ' + unit) if unit else ''}")
    return "\n".join(lines)


@lru_cache
def get_llm() -> LLMProvider:
    s = get_settings()
    if not s.llm_api_key:
        return NullProvider()
    return OpenAICompatibleProvider(s.llm_base_url, s.llm_api_key, s.llm_model, s.llm_timeout_s,
                                    max_tokens=s.llm_max_tokens, reasoning_effort=s.llm_reasoning_effort,
                                    rate_limit_wait_s=s.llm_rate_limit_wait_s)
