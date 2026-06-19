"""Compact long-task research state for academic harness runs."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ResearchStateV1(BaseModel):
    schema_version: Literal["wenjin.research_state.v1"] = "wenjin.research_state.v1"
    execution_id: str
    goal: str
    decisions: list[dict[str, Any]] = Field(default_factory=list)
    claims: list[dict[str, Any]] = Field(default_factory=list)
    evidence_index: list[dict[str, Any]] = Field(default_factory=list)
    artifact_index: list[dict[str, Any]] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    quality_state: list[dict[str, Any]] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


def compact_research_state(
    *,
    execution_id: str,
    goal: str,
    expert_reports: list[dict[str, Any]],
    quality_state: list[dict[str, Any]],
    decisions: list[dict[str, Any]] | None = None,
    next_actions: list[str] | None = None,
) -> ResearchStateV1:
    """Build a bounded state map from expert reports without replaying transcripts."""

    claims: list[dict[str, Any]] = []
    evidence_index: list[dict[str, Any]] = []
    artifact_index: list[dict[str, Any]] = []
    open_questions: list[str] = []
    accumulated_next_actions: list[str] = []
    for report in expert_reports:
        if not isinstance(report, dict):
            continue
        claims.extend(_dict_items(report.get("claims"), id_key="claim_id"))
        evidence_index.extend(_dict_items(report.get("evidence"), id_key="evidence_id"))
        artifact_index.extend(_dict_items(report.get("artifacts"), id_key="artifact_id"))
        open_questions.extend(_string_items(report.get("uncertainties")))
        accumulated_next_actions.extend(_string_items(report.get("next_actions")))
    return ResearchStateV1(
        execution_id=execution_id,
        goal=goal,
        decisions=decisions or [],
        claims=_dedupe_by_key(claims, "claim_id"),
        evidence_index=_dedupe_by_key(evidence_index, "evidence_id"),
        artifact_index=_dedupe_by_key(artifact_index, "artifact_id"),
        open_questions=_dedupe_strings(open_questions),
        quality_state=quality_state,
        next_actions=_dedupe_strings([*(next_actions or []), *accumulated_next_actions]),
    )


def _dict_items(value: Any, *, id_key: str) -> list[dict[str, Any]]:
    if not isinstance(value, list | tuple):
        return []
    return [item for item in value if isinstance(item, dict) and item.get(id_key)]


def _string_items(value: Any) -> list[str]:
    if not isinstance(value, list | tuple | set | frozenset):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _dedupe_by_key(items: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        item_key = str(item.get(key) or "").strip()
        if not item_key or item_key in seen:
            continue
        result.append(item)
        seen.add(item_key)
    return result


def _dedupe_strings(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item in seen:
            continue
        result.append(item)
        seen.add(item)
    return result
