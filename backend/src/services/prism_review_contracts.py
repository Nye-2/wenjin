"""Shared bounded contracts for Prism review items."""

from __future__ import annotations

from typing import Any

PRISM_ACADEMIC_STYLE_CONTRACT_SCHEMA = "wenjin.prism.academic_style_contract.v1"
PRISM_ACADEMIC_STYLE_DELTA_SCHEMA = "wenjin.prism.academic_style_delta.v1"

_ACADEMIC_STYLE_CONTRACT_STRING_FIELDS = {
    "target_path",
    "basis",
    "risk",
}
_ACADEMIC_STYLE_CONTRACT_INT_FIELDS = {
    "academic_style_score",
    "signal_count",
    "anti_pattern_count",
    "citation_key_count",
}
_ACADEMIC_STYLE_DELTA_INT_FIELDS = {
    "baseline_academic_style_score",
    "pending_academic_style_score",
    "score_delta",
}


def sanitize_academic_style_contract_for_storage(value: Any) -> dict[str, Any]:
    """Allowlist and bound an upstream academic-style contract for persistence."""

    if not isinstance(value, dict) or not value:
        return {}
    result: dict[str, Any] = {}
    for key in _ACADEMIC_STYLE_CONTRACT_STRING_FIELDS:
        if key in value:
            text = _bounded_string(value.get(key), limit=120)
            if text:
                result[key] = text
    for key in _ACADEMIC_STYLE_CONTRACT_INT_FIELDS:
        if key in value:
            upper = 5 if key == "academic_style_score" else 50
            result[key] = _bounded_int(value.get(key), upper=upper)
    if "signals" in value:
        result["signals"] = _bounded_string_list(value.get("signals"))
    if "anti_patterns" in value:
        result["anti_patterns"] = _bounded_string_list(value.get("anti_patterns"))
    raw_delta = value.get("style_delta")
    if isinstance(raw_delta, dict) and raw_delta:
        delta: dict[str, Any] = {}
        for key in _ACADEMIC_STYLE_DELTA_INT_FIELDS:
            if key in raw_delta:
                if key == "score_delta":
                    delta[key] = _bounded_signed_int(raw_delta.get(key))
                else:
                    delta[key] = _bounded_int(raw_delta.get(key), upper=5)
        if "improves_academic_style" in raw_delta:
            delta["improves_academic_style"] = raw_delta.get("improves_academic_style") is True
        if delta:
            delta["schema"] = PRISM_ACADEMIC_STYLE_DELTA_SCHEMA
            result["style_delta"] = delta
    if result:
        result["schema"] = PRISM_ACADEMIC_STYLE_CONTRACT_SCHEMA
    return result


def sanitize_academic_style_contract_for_projection(
    value: dict[str, object],
    *,
    target_path: str,
) -> dict[str, object]:
    """Normalize an upstream academic-style contract for review projection."""

    risk = str(value.get("risk") or "medium").strip().lower()
    if risk not in {"low", "medium", "high"}:
        risk = "medium"
    signals = _bounded_contract_string_list(value.get("signals"))
    anti_patterns = _bounded_contract_string_list(value.get("anti_patterns"))
    score = min(_nonnegative_int(value.get("academic_style_score")), 5)
    result: dict[str, object] = {
        "schema": PRISM_ACADEMIC_STYLE_CONTRACT_SCHEMA,
        "target_path": str(value.get("target_path") or target_path),
        "basis": str(value.get("basis") or "upstream_contract")[:80],
        "risk": risk,
        "academic_style_score": score,
        "signal_count": len(signals),
        "anti_pattern_count": len(anti_patterns),
        "citation_key_count": _bounded_count(value.get("citation_key_count"), limit=50),
        "signals": signals,
        "anti_patterns": anti_patterns,
    }
    style_delta = sanitize_academic_style_delta_for_projection(value, pending_score=score)
    if style_delta:
        result["style_delta"] = style_delta
    return result


def sanitize_academic_style_delta_for_projection(
    value: dict[str, object],
    *,
    pending_score: int,
) -> dict[str, object]:
    """Recompute a bounded Prism academic-style delta for review projection."""

    raw_delta = value.get("style_delta")
    source = dict(raw_delta) if isinstance(raw_delta, dict) else value
    if "baseline_academic_style_score" not in source:
        return {}
    baseline_score = min(_nonnegative_int(source.get("baseline_academic_style_score")), 5)
    score_delta = pending_score - baseline_score
    return {
        "schema": PRISM_ACADEMIC_STYLE_DELTA_SCHEMA,
        "baseline_academic_style_score": baseline_score,
        "pending_academic_style_score": pending_score,
        "score_delta": score_delta,
        "improves_academic_style": score_delta > 0,
    }


def is_valid_academic_style_delta_contract(
    style_delta: dict[str, Any],
    *,
    pending_score: int,
) -> bool:
    """Return whether a Prism academic-style delta is canonical and positive."""

    if style_delta.get("schema") != PRISM_ACADEMIC_STYLE_DELTA_SCHEMA:
        return False
    baseline_score = min(_nonnegative_int(style_delta.get("baseline_academic_style_score")), 5)
    delta_pending_score = min(_nonnegative_int(style_delta.get("pending_academic_style_score")), 5)
    score_delta = _signed_int(style_delta.get("score_delta"))
    expected_delta = pending_score - baseline_score
    return (
        style_delta.get("improves_academic_style") is True
        and delta_pending_score == pending_score
        and score_delta == expected_delta
        and score_delta > 0
    )


def _bounded_string(value: Any, *, limit: int = 120) -> str:
    return str(value or "").strip()[:limit]


def _bounded_string_list(value: Any, *, limit: int = 10) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = _bounded_string(item, limit=80)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
        if len(result) >= limit:
            break
    return result


def _bounded_int(value: Any, *, lower: int = 0, upper: int = 50) -> int:
    if isinstance(value, bool):
        return lower
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return lower
    return max(lower, min(parsed, upper))


def _bounded_signed_int(value: Any, *, lower: int = -5, upper: int = 5) -> int:
    if isinstance(value, bool):
        return 0
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(lower, min(parsed, upper))


def _bounded_contract_string_list(value: object) -> list[str]:
    raw = value if isinstance(value, list | tuple | set | frozenset) else []
    result: list[str] = []
    for item in list(raw)[:10]:
        text = str(item or "").strip()[:80]
        if text and text not in result:
            result.append(text)
    return result


def _bounded_count(value: object, *, limit: int) -> int:
    return min(_nonnegative_int(value), max(limit, 0))


def _nonnegative_int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(value, 0)
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        return 0
    return max(parsed, 0)


def _signed_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
