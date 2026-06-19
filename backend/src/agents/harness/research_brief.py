"""Structured academic task brief for TeamKernel runs."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

_MAX_TEXT = 700
_MAX_SHORT_TEXT = 220


class ResearchBriefKnownInputV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    summary: str


class ResearchBriefMissingInputV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    reason: str
    ask_user_when_blocking: bool = False


class ResearchBriefPerspectiveV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    perspective_id: str
    label: str
    questions: list[str] = Field(default_factory=list)


class ResearchBriefSearchPlanV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seed_queries: list[str] = Field(default_factory=list)
    source_policy: str | None = None
    stop_rules: list[str] = Field(default_factory=list)


class ResearchBriefQualityContractV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unsupported_claim_policy: Literal["mark_insufficient_evidence", "warn", "block"] = (
        "mark_insufficient_evidence"
    )
    citation_policy: str = "all literature claims must reference source keys"
    artifact_policy: str = "numeric or figure claims must reference artifacts when present"


class ResearchBriefTargetVenueV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    field: str | None = None
    quality_bar: str | None = None


class ResearchBriefV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["wenjin.research_brief.v1"] = "wenjin.research_brief.v1"
    brief_id: str
    workspace_id: str
    execution_id: str
    workspace_type: str
    capability_id: str
    user_objective: str
    research_topic: str | None = None
    target_output: str | None = None
    target_venue: ResearchBriefTargetVenueV1 | None = None
    known_inputs: list[ResearchBriefKnownInputV1] = Field(default_factory=list)
    missing_inputs: list[ResearchBriefMissingInputV1] = Field(default_factory=list)
    perspectives: list[ResearchBriefPerspectiveV1] = Field(default_factory=list)
    search_plan: ResearchBriefSearchPlanV1 = Field(default_factory=ResearchBriefSearchPlanV1)
    quality_contract: ResearchBriefQualityContractV1 = Field(default_factory=ResearchBriefQualityContractV1)
    handoff_notes: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class ResearchBriefDeltaV1(BaseModel):
    """Bounded expert-proposed update to the run brief."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["wenjin.research_brief_delta.v1"] = "wenjin.research_brief_delta.v1"
    perspectives: list[ResearchBriefPerspectiveV1] = Field(default_factory=list)
    missing_inputs: list[ResearchBriefMissingInputV1] = Field(default_factory=list)
    search_plan: ResearchBriefSearchPlanV1 | None = None
    handoff_notes: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


def build_research_brief(
    *,
    execution_id: str,
    workspace_id: str,
    workspace_type: str,
    capability_id: str,
    user_objective: str,
    workspace_map: dict[str, Any] | None = None,
    capability_metadata: dict[str, Any] | None = None,
) -> ResearchBriefV1:
    """Build a conservative run brief from launch context and workspace hints."""

    workspace_map = workspace_map if isinstance(workspace_map, dict) else {}
    capability_metadata = capability_metadata if isinstance(capability_metadata, dict) else {}
    topic_hints = _bounded_strings(workspace_map.get("topic_hints"), limit=6, max_chars=80)
    open_questions = _bounded_strings(workspace_map.get("open_questions"), limit=5, max_chars=180)
    target_output = _clean_text(capability_metadata.get("name") or capability_metadata.get("capability_name"))
    known_inputs = [
        ResearchBriefKnownInputV1(kind="user_objective", summary=_truncate(user_objective, _MAX_SHORT_TEXT))
    ]
    missing_inputs = [
        ResearchBriefMissingInputV1(key="workspace_open_question", reason=question)
        for question in open_questions
    ]
    return ResearchBriefV1(
        brief_id=f"brief-{execution_id}",
        workspace_id=workspace_id,
        execution_id=execution_id,
        workspace_type=workspace_type,
        capability_id=capability_id,
        user_objective=_truncate(user_objective, _MAX_TEXT),
        research_topic=" / ".join(topic_hints) if topic_hints else None,
        target_output=target_output or None,
        known_inputs=known_inputs,
        missing_inputs=missing_inputs,
        search_plan=ResearchBriefSearchPlanV1(
            seed_queries=topic_hints[:3],
            source_policy="prefer verified scholarly sources with stable source keys",
            stop_rules=[
                "stop when each core perspective has enough direct evidence",
                "stop when new searches only return duplicates or weakly related sources",
            ],
        ),
    )


def summarize_research_brief(brief: ResearchBriefV1 | dict[str, Any] | None) -> str:
    """Return a bounded member-context summary."""

    if brief is None:
        return ""
    if isinstance(brief, dict):
        try:
            brief = ResearchBriefV1.model_validate(brief)
        except Exception:  # noqa: BLE001 - corrupted runtime state should not break member context.
            return ""
    pieces = [f"研究目标：{_truncate(brief.user_objective, 220)}"]
    if brief.research_topic:
        pieces.append(f"主题线索：{_truncate(brief.research_topic, 160)}")
    if brief.target_output:
        pieces.append(f"目标产出：{_truncate(brief.target_output, 120)}")
    if brief.perspectives:
        labels = "、".join(item.label for item in brief.perspectives[:5] if item.label)
        if labels:
            pieces.append(f"视角：{labels}")
    if brief.missing_inputs:
        missing = "；".join(item.reason for item in brief.missing_inputs[:3] if item.reason)
        if missing:
            pieces.append(f"待确认：{missing}")
    return _truncate(" | ".join(pieces), 900)


def sanitize_research_brief_delta(value: Any) -> ResearchBriefDeltaV1 | None:
    if not isinstance(value, dict):
        return None
    data = {
        "schema_version": "wenjin.research_brief_delta.v1",
        "perspectives": _sanitize_perspectives(value.get("perspectives"), limit=8),
        "missing_inputs": _sanitize_missing_inputs(value.get("missing_inputs"), limit=8),
        "search_plan": _sanitize_search_plan(value.get("search_plan")),
        "handoff_notes": _bounded_strings(value.get("handoff_notes"), limit=8, max_chars=180),
        "risks": _bounded_strings(value.get("risks"), limit=8, max_chars=180),
    }
    return ResearchBriefDeltaV1.model_validate(data)


def _sanitize_perspectives(value: Any, *, limit: int) -> list[dict[str, Any]]:
    if not isinstance(value, list | tuple):
        return []
    result: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        perspective_id = _clean_text(item.get("perspective_id"))
        label = _clean_text(item.get("label"))
        if not perspective_id or not label:
            continue
        result.append(
            {
                "perspective_id": _truncate(perspective_id, 80),
                "label": _truncate(label, 80),
                "questions": _bounded_strings(item.get("questions"), limit=8, max_chars=180),
            }
        )
        if len(result) >= limit:
            break
    return result


def _sanitize_missing_inputs(value: Any, *, limit: int) -> list[dict[str, Any]]:
    if not isinstance(value, list | tuple):
        return []
    result: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        key = _clean_text(item.get("key"))
        reason = _clean_text(item.get("reason"))
        if not key or not reason:
            continue
        result.append(
            {
                "key": _truncate(key, 80),
                "reason": _truncate(reason, 220),
                "ask_user_when_blocking": item.get("ask_user_when_blocking") is True,
            }
        )
        if len(result) >= limit:
            break
    return result


def _sanitize_search_plan(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {
        "seed_queries": _bounded_strings(value.get("seed_queries"), limit=12, max_chars=120),
        "source_policy": _optional_truncated(value.get("source_policy"), 220),
        "stop_rules": _bounded_strings(value.get("stop_rules"), limit=8, max_chars=180),
    }


def _bounded_strings(value: Any, *, limit: int, max_chars: int) -> list[str]:
    if not isinstance(value, list | tuple | set | frozenset):
        return []
    result: list[str] = []
    for item in value:
        text = _truncate(_clean_text(item), max_chars)
        if text:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _optional_truncated(value: Any, max_chars: int) -> str | None:
    text = _truncate(_clean_text(value), max_chars)
    return text or None


def _truncate(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    if max_chars <= 3:
        return value[:max_chars]
    return value[: max_chars - 3].rstrip() + "..."
