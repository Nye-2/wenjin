"""Pure team-member input assembly for TeamKernel invocations."""

from __future__ import annotations

import re
from typing import Any

from src.agents.contracts.task_brief import TaskBrief
from src.agents.harness.research_task_eval import required_surfaces_from_capability_policy
from src.sandbox.workspace_layout import (
    is_workspace_internal_path,
    is_workspace_protected_path,
    is_workspace_readable_internal_output_ref,
)

from .contracts import TeamBlackboard

_MAX_TEXT_CHARS = 4000
_MAX_LIST_ITEMS = 30
_RUNTIME_RESEARCH_EVIDENCE_SURFACES = {
    "workflow_trace",
    "citation_strength",
    "experiment_interpretation",
    "paper_relevance",
    "statistical_robustness",
    "output_ref_reuse",
}
_RESEARCH_SURFACE_GUIDANCE = {
    "workflow_trace": (
        "Record completed tool activity through normal harness tools; "
        "do not summarize unsupported work."
    ),
    "output_ref_reuse": (
        "If a prior sandbox output ref is available, inspect it with "
        "sandbox.read_output_ref before rerunning expensive work."
    ),
    "experiment_interpretation": (
        "For experiments, return method, metric, verified result, limitation, "
        "artifact and dataset evidence aligned with reproducibility metadata."
    ),
    "citation_strength": (
        "For citation-sensitive work, return supported or verified source refs "
        "instead of weak prose-only support."
    ),
    "paper_relevance": (
        "For literature work, keep topic-aligned source or citation refs and "
        "flag off-topic candidates instead of mixing them into evidence."
    ),
    "statistical_robustness": (
        "For statistical work, include method, sample size, metric, passed "
        "robustness checks, limitations, artifact and dataset evidence."
    ),
}

_TASK_FOCUS_BY_TEMPLATE = {
    "research_planner.v1": "拆解任务目标、交付物、质量门和成员分工，形成可执行研究计划。",
    "research_scout.v1": "检索并筛选可支撑本任务的权威来源，输出可追溯来源表、Library-ready metadata、claim support 和缺口清单。",
    "literature_synthesizer.v1": "把检索结果和 Library sources 综合为主题矩阵、gap、related work 分组、claim-evidence-citation plan 和 contribution candidates。",
    "source_quality_auditor.v1": "审查来源权威性、元数据完整性、时效性、BibTeX readiness 和 claim-source 匹配风险。",
    "citation_auditor.v1": "核查引用计划、citation key、来源支撑强度和缺失文献风险。",
    "document_architect.v1": "把研究素材组织成可审阅文档结构、段落计划和后续写作任务。",
    "critical_reviewer.v1": "从审稿人视角检查证据、逻辑、过度主张、格式和可复现性风险。",
    "generalist_assistant.v1": "补位处理当前团队缺口，优先复用已有上下文并产出可审阅摘要。",
}


def build_team_member_context(
    *,
    brief: TaskBrief,
    capability_name: str,
    template_id: str,
    display_role: str,
    blackboard: TeamBlackboard,
    capability_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build bounded input for a recruited team member.

    The helper is pure: callers pass already-loaded data, and it returns the
    member input payload without touching DataService or sandbox state.
    """

    payload = _sanitize_payload(dict(brief.brief or {}))
    raw_message = _first_nonempty(payload.get("raw_message"), brief.raw_message)
    if raw_message:
        payload["raw_message"] = _compact_text(raw_message)
    payload.setdefault("workspace_id", brief.workspace_id)
    payload.setdefault("capability_id", brief.capability_id)
    if brief.user_id:
        payload.setdefault("user_id", brief.user_id)
    payload["team_role"] = display_role
    payload["team_blackboard"] = blackboard.model_dump(mode="json")
    payload["capability_name"] = capability_name or brief.capability_id
    payload.setdefault("task_focus", _task_focus(template_id, display_role))

    query = _derive_query(payload, raw_message)
    if query:
        payload["query"] = query
    topic = _compact_text(payload.get("topic") or "")
    if topic:
        payload["topic"] = topic
    upstream_context = _upstream_context(blackboard)
    if upstream_context:
        payload["upstream_context"] = upstream_context
    research_requirements = _research_evidence_requirements(capability_policy)
    if research_requirements:
        payload["research_evidence_requirements"] = research_requirements
    return payload


def _derive_query(payload: dict[str, Any], raw_message: Any) -> str:
    explicit_query = _compact_text(payload.get("query") or "")
    if explicit_query:
        return explicit_query
    topic = _compact_text(payload.get("topic") or "")
    if topic:
        return topic
    goal = _compact_text(payload.get("goal") or "")
    if goal:
        return goal
    return _academic_query_from_raw_message(raw_message)


def _academic_query_from_raw_message(raw_message: Any) -> str:
    text = _compact_text(raw_message or "")
    if not text:
        return ""
    ascii_spans = re.findall(r"[A-Za-z0-9][A-Za-z0-9\s+/#&.,:;()'’_-]*", text)
    english = " ".join(span.strip(" ,.;:()'’_-") for span in ascii_spans if span.strip(" ,.;:()'’_-"))
    if english:
        return _compact_query(english)
    return _compact_query(text)


def _compact_query(text: str) -> str:
    value = re.sub(r"[/,_:;()'’\"“”]+", " ", str(text or ""))
    value = re.sub(r"\s+", " ", value).strip()
    return value[:240]


def _upstream_context(blackboard: TeamBlackboard) -> dict[str, Any]:
    context: dict[str, Any] = {}
    if blackboard.latest_leader_summary:
        context["latest_leader_summary"] = _compact_text(blackboard.latest_leader_summary)
    quality_repair_context = _quality_repair_context(blackboard)
    if quality_repair_context:
        context["quality_repair_context"] = quality_repair_context
    for field in (
        "confirmed_findings",
        "evidence_items",
        "citation_gaps",
        "experiment_gaps",
        "data_gaps",
        "writing_risks",
        "format_risks",
        "pending_decisions",
        "harness_replan_signals",
    ):
        value = _sanitize_payload(getattr(blackboard, field, []))
        if value:
            context[field] = value
    return context


def _task_focus(template_id: str, display_role: str) -> str:
    return _TASK_FOCUS_BY_TEMPLATE.get(
        template_id,
        f"以{display_role}身份处理当前任务，复用团队上下文并返回可审阅结果。",
    )


def _research_evidence_requirements(
    capability_policy: dict[str, Any] | None,
) -> dict[str, Any] | None:
    surfaces = list(required_surfaces_from_capability_policy(capability_policy, default=()))
    if not surfaces:
        return None
    runtime_surfaces = [
        surface for surface in surfaces if surface in _RUNTIME_RESEARCH_EVIDENCE_SURFACES
    ]
    guidance: list[str] = []
    for surface in surfaces:
        item = _RESEARCH_SURFACE_GUIDANCE.get(surface)
        if item and item not in guidance:
            guidance.append(item)
    return {
        "schema": "wenjin.team.research_evidence_requirements.v1",
        "quality_gate": "research_evidence_required",
        "required_surfaces": surfaces,
        "runtime_enforced_surfaces": runtime_surfaces,
        "guidance": guidance[:10],
    }


def _quality_repair_context(blackboard: TeamBlackboard) -> dict[str, Any] | None:
    source_gates: list[str] = []
    missing_research_surfaces: list[str] = []
    safe_output_refs: list[str] = []
    required_actions: list[str] = []
    for gate in blackboard.quality_gate_history:
        if not isinstance(gate, dict) or gate.get("status") != "fail":
            continue
        gate_id = _compact_text(gate.get("gate_id") or "")
        for fix in gate.get("required_fixes") or []:
            if not isinstance(fix, dict):
                continue
            repair_context = fix.get("repair_context")
            if not isinstance(repair_context, dict):
                continue
            _append_unique(source_gates, gate_id)
            for source_gate in _string_list(repair_context.get("source_gates")):
                _append_unique(source_gates, source_gate)
            for surface in _string_list(repair_context.get("missing_research_surfaces")):
                _append_unique(missing_research_surfaces, surface)
            for ref in _string_list(repair_context.get("safe_output_refs")):
                if is_workspace_readable_internal_output_ref(ref):
                    _append_unique(safe_output_refs, ref)
            for action in _string_list(repair_context.get("required_actions")):
                _append_unique(required_actions, _compact_text(action))
    if not source_gates and not missing_research_surfaces and not safe_output_refs and not required_actions:
        return None
    return {
        "schema": "wenjin.team.quality_repair_context.v1",
        "source_gates": source_gates[:10],
        "missing_research_surfaces": missing_research_surfaces[:20],
        "safe_output_refs": safe_output_refs[:10],
        "required_actions": required_actions[:10],
    }


def _sanitize_payload(value: Any) -> Any:
    if isinstance(value, dict):
        if _dict_has_blocked_ref(value):
            return None
        result: dict[str, Any] = {}
        for key, item in value.items():
            sanitized = _sanitize_payload(item)
            if sanitized is not None:
                result[str(key)] = sanitized
        return result
    if isinstance(value, list | tuple):
        result = []
        for item in value[:_MAX_LIST_ITEMS]:
            sanitized = _sanitize_payload(item)
            if sanitized is not None:
                result.append(sanitized)
        return result
    if isinstance(value, str):
        if _blocked_workspace_ref(value):
            return None
        return _compact_text(value)
    return value


def _blocked_workspace_ref(value: str) -> bool:
    text = str(value or "").strip()
    if not text.startswith("/workspace"):
        return False
    return is_workspace_internal_path(text) or is_workspace_protected_path(text)


def _dict_has_blocked_ref(value: dict[str, Any]) -> bool:
    for item in value.values():
        if isinstance(item, str) and _blocked_workspace_ref(item):
            return True
    return False


def _compact_text(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) <= _MAX_TEXT_CHARS:
        return text
    return f"{text[: _MAX_TEXT_CHARS - 3]}..."


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list | tuple):
        result: list[str] = []
        for item in value[:_MAX_LIST_ITEMS]:
            text = str(item or "").strip()
            if text:
                result.append(text)
        return result
    return []


def _append_unique(items: list[str], value: str) -> None:
    text = str(value or "").strip()
    if text and text not in items:
        items.append(text)
