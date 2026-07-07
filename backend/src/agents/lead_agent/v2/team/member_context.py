"""Pure team-member input assembly for TeamKernel invocations."""

from __future__ import annotations

import re
from typing import Any

from src.agents.contracts.task_brief import TaskBrief
from src.agents.harness.research_eval_surfaces import required_surfaces_from_capability_policy
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
    "experiment_reproducibility",
    "figure_data_consistency",
    "claim_evidence_alignment",
    "review_packet_completeness",
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
    "claim_evidence_alignment": (
        "For every claim you want the team to reuse, return claim ids linked "
        "to concrete evidence ids or mark the claim as weak."
    ),
    "experiment_reproducibility": (
        "For experiment artifacts, include source script, dataset paths, "
        "artifact path, sandbox environment, and content hash when available."
    ),
    "figure_data_consistency": (
        "For figures, keep the figure purpose, source data, generation script "
        "or prompt, caption, and unsupported-claim risk together."
    ),
    "review_packet_completeness": (
        "Return outputs as reviewable candidates with title, summary, "
        "provenance, risk, and commitability."
    ),
}

_TASK_FOCUS_BY_TEMPLATE = {
    "research_planner.v1": "拆解任务目标、交付物、质量门和成员分工，形成可执行研究计划。",
    "research_scout.v1": "检索并筛选可支撑本任务的权威来源，输出可追溯来源表、Library-ready metadata、claim support 和缺口清单。",
    "literature_synthesizer.v1": "把检索结果和 Library sources 综合为主题矩阵、gap、related work 分组、claim-evidence-citation plan 和 contribution candidates。",
    "methodologist.v1": "规划研究方法、实验设计、评估指标、可行性边界和方法学风险。",
    "evidence_analyst.v1": "分析数据、实验结果、指标、限制和 artifact evidence，形成可复核的证据链。",
    "figure_table_engineer.v1": "把结果与证据转化为图表、表格、caption 和呈现建议。",
    "document_architect.v1": "把研究素材组织成可审阅文档结构、段落计划和后续写作任务。",
    "manuscript_writer.v1": "基于已确认结构、证据和引用计划撰写或改写正文，保持学术表达和可追溯边界。",
    "citation_auditor.v1": "核查引用计划、citation key、来源支撑强度和缺失文献风险。",
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
    research_state: dict[str, Any] | None = None,
    research_brief: dict[str, Any] | None = None,
    workspace_map_summary: dict[str, Any] | None = None,
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
    research_state_projection = project_research_state_for_member_context(research_state)
    if research_state_projection:
        payload["research_state"] = research_state_projection
    research_brief_projection = project_research_brief_for_member_context(research_brief)
    if research_brief_projection:
        payload["research_brief"] = research_brief_projection
    workspace_map_projection = project_workspace_map_for_member_context(workspace_map_summary)
    if workspace_map_projection:
        payload["workspace_map_summary"] = workspace_map_projection
    research_requirements = _research_evidence_requirements(capability_policy)
    if research_requirements:
        payload["research_evidence_requirements"] = research_requirements
    methodology_contract = _methodology_contract(capability_policy)
    if methodology_contract:
        payload["methodology_contract"] = methodology_contract
    return payload


def project_research_state_for_member_context(
    research_state: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Bound compact research state for a member prompt."""

    if not isinstance(research_state, dict):
        return None
    return {
        "schema_version": research_state.get("schema_version"),
        "execution_id": research_state.get("execution_id"),
        "goal": research_state.get("goal"),
        "research_brief": _sanitize_payload(research_state.get("research_brief") or {}),
        "workspace_map_summary": _sanitize_payload(research_state.get("workspace_map_summary") or {}),
        "claims": _sanitize_payload(list(research_state.get("claims") or [])[:30]),
        "claim_inventory": _sanitize_payload(list(research_state.get("claim_inventory") or [])[:40]),
        "evidence_index": _sanitize_payload(list(research_state.get("evidence_index") or [])[:60]),
        "evidence_packet": _sanitize_payload(list(research_state.get("evidence_packet") or [])[:80]),
        "artifact_index": _sanitize_payload(list(research_state.get("artifact_index") or [])[:30]),
        "open_questions": _string_list(research_state.get("open_questions"))[:20],
        "unresolved_blockers": _string_list(research_state.get("unresolved_blockers"))[:20],
        "quality_state": _sanitize_payload(list(research_state.get("quality_state") or [])[:20]),
        "next_actions": _string_list(research_state.get("next_actions"))[:20],
    }


def project_research_brief_for_member_context(
    research_brief: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(research_brief, dict):
        return None
    return {
        "schema_version": research_brief.get("schema_version"),
        "brief_id": research_brief.get("brief_id"),
        "research_topic": _compact_text(research_brief.get("research_topic") or ""),
        "target_output": _compact_text(research_brief.get("target_output") or ""),
        "user_objective": _compact_text(research_brief.get("user_objective") or ""),
        "known_inputs": _sanitize_payload(list(research_brief.get("known_inputs") or [])[:10]),
        "missing_inputs": _sanitize_payload(list(research_brief.get("missing_inputs") or [])[:10]),
        "perspectives": _sanitize_payload(list(research_brief.get("perspectives") or [])[:8]),
        "search_plan": _sanitize_payload(research_brief.get("search_plan") or {}),
        "quality_contract": _sanitize_payload(research_brief.get("quality_contract") or {}),
    }


def project_workspace_map_for_member_context(
    workspace_map_summary: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(workspace_map_summary, dict):
        return None
    return {
        "schema_version": workspace_map_summary.get("schema_version"),
        "topic_hints": _string_list(workspace_map_summary.get("topic_hints"))[:10],
        "library": _sanitize_payload(workspace_map_summary.get("library") or {}),
        "manuscript": _sanitize_payload(workspace_map_summary.get("manuscript") or {}),
        "experiments": _sanitize_payload(workspace_map_summary.get("experiments") or {}),
        "open_questions": _string_list(workspace_map_summary.get("open_questions"))[:8],
    }


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


def _methodology_contract(
    capability_policy: dict[str, Any] | None,
) -> dict[str, Any] | None:
    policy = capability_policy if isinstance(capability_policy, dict) else {}
    methodology = policy.get("methodology")
    if not isinstance(methodology, dict):
        return None
    archetype = _compact_text(methodology.get("archetype") or "")
    stages = _methodology_stages(methodology.get("stages"))
    claim_policy = _methodology_claim_policy(methodology.get("claim_policy"))
    retrieval_policy = _methodology_retrieval_policy(methodology.get("retrieval_policy"))
    completion_gates = _string_list(methodology.get("completion_gates"))[:_MAX_LIST_ITEMS]
    if (
        (not archetype or archetype == "none")
        and not stages
        and not claim_policy
        and not retrieval_policy
        and not completion_gates
    ):
        return None
    result: dict[str, Any] = {
        "schema": "wenjin.team.methodology_contract.v1",
        "archetype": archetype or "none",
    }
    if stages:
        result["stages"] = stages
    if claim_policy:
        result["claim_policy"] = claim_policy
    if retrieval_policy:
        result["retrieval_policy"] = retrieval_policy
    if completion_gates:
        result["completion_gates"] = completion_gates
    return result


def _methodology_stages(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list | tuple):
        return []
    stages: list[dict[str, Any]] = []
    for item in value[:_MAX_LIST_ITEMS]:
        if not isinstance(item, dict):
            continue
        stage_id = _compact_text(item.get("id") or "")
        purpose = _compact_text(item.get("purpose") or "")
        if not stage_id or not purpose:
            continue
        stage: dict[str, Any] = {
            "id": stage_id,
            "purpose": purpose,
        }
        required_artifacts = _string_list(item.get("required_artifacts"))[:_MAX_LIST_ITEMS]
        if required_artifacts:
            stage["required_artifacts"] = required_artifacts
        user_checkpoint = _compact_text(item.get("user_checkpoint") or "")
        if user_checkpoint and user_checkpoint != "none":
            stage["user_checkpoint"] = user_checkpoint
        quality_surfaces = _string_list(item.get("quality_surfaces"))[:_MAX_LIST_ITEMS]
        if quality_surfaces:
            stage["quality_surfaces"] = quality_surfaces
        stages.append(stage)
    return stages


def _methodology_claim_policy(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, Any] = {}
    mode = _compact_text(value.get("mode") or "")
    if mode and mode != "none":
        result["mode"] = mode
    for key in (
        "extraction_artifact",
        "verification_artifact",
        "unsupported_claim_behavior",
    ):
        text = _compact_text(value.get(key) or "")
        if text:
            result[key] = text
    return result


def _methodology_retrieval_policy(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, Any] = {}
    escalation = _string_list(value.get("escalation"))[:_MAX_LIST_ITEMS]
    if escalation:
        result["escalation"] = escalation
    for key in ("prefer_workspace_library", "require_import_before_citation"):
        if isinstance(value.get(key), bool):
            result[key] = value[key]
    return result


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
