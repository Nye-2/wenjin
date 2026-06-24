"""Shared feature launch context rules for launch / resume flows."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.application.intents.launch_text import (
    is_generic_feature_launch_text,
    normalize_inline_text,
)
from src.application.results import FeatureExecutionAdvisory

THREAD_ENTRY_SOURCES = {"thread", "tool", "automation"}

FEATURE_CONTEXT_REQUIREMENTS: dict[str, tuple[tuple[str, ...], ...]] = {
    "thesis_research_pack": (("goal", "topic", "query"),),
    "thesis_empirical_analysis": (("goal", "dataset_id", "source_artifact_id"),),
    "sci_literature_positioning": (("goal", "query", "topic", "keywords"),),
    "sci_empirical_package": (("goal", "dataset_id", "source_artifact_id"),),
    "proposal_background_pack": (("goal", "keywords", "topic", "query"),),
    "prior_art_and_novelty_pack": (("goal", "keywords", "query", "topic"),),
}

FEATURE_CONTEXT_FIELD_LABELS: dict[str, str] = {
    "goal": "任务目标",
    "topic": "研究主题",
    "query": "检索问题",
    "keywords": "关键词",
    "dataset_id": "数据集",
    "source_artifact_id": "来源材料",
    "existing_materials_summary": "已有材料",
    "data_assets": "数据或实验材料",
    "target_format": "目标格式",
    "target_journal": "目标期刊",
    "invention_title": "发明名称",
    "technical_problem": "技术问题",
    "software_name": "软件名称",
}

CONTEXT_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "goal_or_topic": ("goal", "topic", "query"),
    "topic": ("topic", "goal", "query"),
    "query": ("query", "topic", "goal"),
    "keywords": ("keywords", "query", "topic", "goal"),
    "data_assets": ("data_assets", "dataset_id", "source_artifact_id"),
    "existing_materials_summary": (
        "existing_materials_summary",
        "source_artifact_id",
        "context_artifact_ids",
        "data_assets",
    ),
}


def _as_mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def extract_capability_minimum_context(capability: Any) -> Mapping[str, Any] | None:
    """Read capability.routing.minimum_context from DB/domain objects.

    Runtime gating must follow the DataService capability contract instead of a
    parallel hard-coded list. The static requirements below remain only for
    legacy resume hydration.
    """
    routing = _as_mapping(getattr(capability, "routing", None))
    if routing and isinstance(routing.get("minimum_context"), Mapping):
        return routing["minimum_context"]

    definition = _as_mapping(getattr(capability, "definition_json", None))
    if definition:
        nested_routing = _as_mapping(definition.get("routing"))
        if nested_routing and isinstance(nested_routing.get("minimum_context"), Mapping):
            return nested_routing["minimum_context"]

    if isinstance(capability, Mapping):
        mapping_routing = _as_mapping(capability.get("routing"))
        if mapping_routing and isinstance(mapping_routing.get("minimum_context"), Mapping):
            return mapping_routing["minimum_context"]
        mapping_definition = _as_mapping(capability.get("definition_json"))
        if mapping_definition:
            nested_routing = _as_mapping(mapping_definition.get("routing"))
            if nested_routing and isinstance(nested_routing.get("minimum_context"), Mapping):
                return nested_routing["minimum_context"]

    return None


def _context_requirements_from_minimum_context(
    minimum_context: Mapping[str, Any] | None,
) -> tuple[tuple[str, ...], ...]:
    if not minimum_context:
        return ()

    groups: list[tuple[str, ...]] = []
    for field, requirement in minimum_context.items():
        if str(requirement).strip().lower() != "required":
            continue
        field_name = str(field).strip()
        if not field_name:
            continue
        groups.append(CONTEXT_FIELD_ALIASES.get(field_name, (field_name,)))
    return tuple(groups)


def is_value_present(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip()) and not is_generic_feature_launch_text(value)
    if isinstance(value, list):
        return any(is_value_present(item) for item in value)
    if isinstance(value, Mapping):
        return bool(value)
    return value is not None


def resolve_missing_context_fields(
    *,
    feature_id: str,
    params: Mapping[str, Any],
    launch_source: str,
    minimum_context: Mapping[str, Any] | None = None,
) -> list[str]:
    if launch_source not in THREAD_ENTRY_SOURCES:
        return []
    requirements = _context_requirements_from_minimum_context(minimum_context)
    if not requirements:
        return []

    missing: list[str] = []
    for group in requirements:
        if any(is_value_present(params.get(field)) for field in group):
            continue
        missing.append(group[0])
    return missing


def build_missing_context_advisory(
    *,
    feature_id: str,
    missing_fields: list[str],
    feature_name: str | None = None,
    clarification_prompt: str | None = None,
) -> FeatureExecutionAdvisory:
    missing_fields_str = "、".join(
        FEATURE_CONTEXT_FIELD_LABELS.get(field, field)
        for field in missing_fields
    )
    display_name = str(feature_name or feature_id).strip()
    prompt = (
        str(clarification_prompt).strip()
        if clarification_prompt and str(clarification_prompt).strip()
        else (
            f"继续执行「{display_name}」前，还需要你补充：{missing_fields_str}。"
            " 请直接回复补充信息，我会在当前执行会话继续。"
        )
    )
    return FeatureExecutionAdvisory(
        feature_id=feature_id,
        code="missing_params",
        message=prompt,
        context={
            "missing_fields": list(missing_fields),
            "prompt": prompt,
        },
    )


def resolve_resume_context_seed(
    *,
    params: Mapping[str, Any],
    launch_message: str | None,
) -> str:
    candidates: list[tuple[Any, bool]] = [
        (launch_message, False),
        (params.get("__thread_context_focus"), False),
        (params.get("__thread_context_digest"), True),
    ]
    for candidate, is_digest in candidates:
        normalized = normalize_inline_text(candidate)
        if not normalized or is_generic_feature_launch_text(normalized):
            continue
        if is_digest:
            for line in reversed(str(candidate).splitlines()):
                line_text = normalize_inline_text(line)
                if line_text.startswith("用户:"):
                    recovered = normalize_inline_text(line_text.removeprefix("用户:"))
                    if recovered and not is_generic_feature_launch_text(recovered):
                        normalized = recovered
                        break
        if len(normalized) > 280:
            return normalized[:279].rstrip() + "…"
        return normalized
    return ""


def hydrate_missing_context_params_from_resume_message(
    *,
    feature_id: str,
    params: Mapping[str, Any],
    launch_source: str,
    launch_message: str | None,
) -> dict[str, Any]:
    hydrated = dict(params)
    if launch_source not in THREAD_ENTRY_SOURCES:
        return hydrated
    requirements = FEATURE_CONTEXT_REQUIREMENTS.get(feature_id)
    if not requirements:
        return hydrated

    seed_text = resolve_resume_context_seed(
        params=hydrated,
        launch_message=launch_message,
    )
    if not seed_text:
        return hydrated

    for group in requirements:
        if any(is_value_present(hydrated.get(field)) for field in group):
            continue
        hydrated[group[0]] = seed_text
    return hydrated


def build_execution_launch_params(
    *,
    feature_id: str,
    params: Mapping[str, Any],
    workspace_id: str,
    launch_message: str | None = None,
) -> dict[str, Any]:
    """Build canonical ExecutionRecord.params for feature execution."""
    normalized_params = dict(params or {})
    explicit_raw_message = normalized_params.get("raw_message")

    # Some launch paths pass a TaskBrief-shaped object as params. Keep
    # TaskBrief.brief as the capability params themselves so runtime templates
    # can resolve {{topic}}, {{query}}, and {{goal}} consistently.
    nested_brief = normalized_params.get("brief")
    if isinstance(nested_brief, Mapping):
        wrapper_keys = {
            "brief",
            "capability_id",
            "decisions",
            "raw_message",
            "workspace_id",
            "manuscript_context",
        }
        if wrapper_keys.intersection(normalized_params):
            normalized_params = dict(nested_brief)

    raw_message = (
        str(launch_message or "").strip()
        or str(explicit_raw_message or "").strip()
        or str(
            normalized_params.get("query")
            or normalized_params.get("topic")
            or normalized_params.get("goal")
            or feature_id
        )
    )
    return {
        "brief": {
            "capability_id": feature_id,
            "brief": normalized_params,
            "raw_message": raw_message,
            "decisions": {},
            "workspace_id": workspace_id,
        }
    }
