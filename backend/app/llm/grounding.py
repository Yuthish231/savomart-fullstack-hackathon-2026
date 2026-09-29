"""Keep LLM narratives grounded: every number in the output must come from the facts we
supplied, and every cited fact / hotspot id must exist.

Facts are {id: {"label", "value", "unit", "source"}}. The model may round (1,234 → 1.2k,
0.456 → 46%) but not invent: a number is accepted if it matches some fact value under a
small set of display transformations, within rounding tolerance.
"""

import re
from dataclasses import dataclass, field
from typing import Any

# 1,234.5 | 12.5 | 1.2k | 3 lakh | 45% | 2.4 km
_NUM = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{2,3})+|\d+(?:\.\d+)?)\s*(k|lakh|lakhs|l|%)?(?![\w])", re.I)

# Numbers that carry no data claim and are always allowed.
ALWAYS_ALLOWED = {2011.0}  # the census year we cite
SMALL_ORDINAL_MAX = 5  # "top 3 hotspots", "2 reasons" style counts


@dataclass
class GroundingResult:
    ok: bool
    violations: list[str] = field(default_factory=list)


def _candidates(v: float) -> list[float]:
    """Ways a fact value may legitimately appear in prose."""
    out = [v, round(v), round(v, 1), round(v, 2)]
    if abs(v) >= 1000:
        out += [round(v / 1000, 1), round(v / 1000), round(v / 100_000, 1), round(v / 100_000, 2)]
    if 0 < abs(v) <= 1:
        out += [round(v * 100), round(v * 100, 1)]  # share → percent
    if abs(v) >= 100:  # metres → km
        out += [round(v / 1000, 1), round(v / 1000, 2)]
    return out


def _parse(token: str, suffix: str | None) -> float:
    x = float(token.replace(",", ""))
    s = (suffix or "").lower()
    if s == "k":
        x *= 1000
    elif s in ("lakh", "lakhs", "l"):
        x *= 100_000
    return x


def _matches(x: float, allowed: list[float], raw: float) -> bool:
    for a in allowed:
        tol = max(0.051, abs(a) * 0.015)
        if abs(x - a) <= tol or abs(raw - a) <= tol:
            return True
    return False


def _texts(obj: Any) -> list[str]:
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        return [t for k, v in obj.items() if k not in ("fact_ids", "hotspot_id") for t in _texts(v)]
    if isinstance(obj, list):
        return [t for v in obj for t in _texts(v)]
    return []


def _numbers_in(text: str) -> list[float]:
    return [float(m.group(1).replace(",", "")) for m in _NUM.finditer(text or "")]


def check(output: dict[str, Any], facts: dict[str, dict[str, Any]], hotspot_ids: set[str],
          extra_allowed: set[float] | None = None, context_texts: list[str] | None = None) -> GroundingResult:
    """context_texts: names the model may legitimately repeat (area name with its pincode, etc.)."""
    allowed: list[float] = [*ALWAYS_ALLOWED, *(extra_allowed or set())]
    # Numbers that are part of a fact's own label ("the ~500 m ring") or of names we supplied.
    for f in facts.values():
        allowed += _numbers_in(str(f.get("label", "")))
    for t in context_texts or []:
        allowed += _numbers_in(t)
    for f in facts.values():
        v = f.get("value")
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            allowed += _candidates(float(v))

    violations: list[str] = []
    for text in _texts(output):
        for m in _NUM.finditer(text):
            raw = float(m.group(1).replace(",", ""))
            x = _parse(m.group(1), m.group(2))
            if m.group(2) is None and raw.is_integer() and 0 <= raw <= SMALL_ORDINAL_MAX:
                continue
            if not _matches(x, allowed, raw):
                violations.append(f"number '{m.group(0).strip()}' in \"{text[:80]}\" is not in the facts")

    for section in ("reasons", "risks"):
        for item in output.get(section) or []:
            for fid in item.get("fact_ids") or []:
                if fid not in facts:
                    violations.append(f"unknown fact id '{fid}'")
    for item in output.get("scout_first") or []:
        hid = str(item.get("hotspot_id", ""))
        if hid not in hotspot_ids:
            violations.append(f"unknown hotspot id '{hid}'")
    return GroundingResult(ok=not violations, violations=violations)
