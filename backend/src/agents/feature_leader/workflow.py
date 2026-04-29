"""Feature leader workflow planning helpers.

This module builds deterministic subagent workflow plans for complex features.
Execution is handled by :mod:`src.subagents.parallel`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.subagents.parallel import ExecutionPhase, PhasedPlan
from src.workspace_features.runtime_profiles import (
    FeatureRuntimeMode,
    FeatureRuntimeProfile,
    get_feature_runtime_profile,
)

_TEXT_FOCUS_KEYS = (
    "__thread_context_focus",
    "topic",
    "query",
    "paper_title",
    "innovation_description",
    "goal",
    "task",
    "question",
)

_MAX_FOCUS_CHARS = 240


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def _resolve_focus(payload: dict[str, Any], feature_id: str) -> str:
    params = payload.get("params")
    params = params if isinstance(params, dict) else {}

    for key in _TEXT_FOCUS_KEYS:
        normalized = _normalize_text(params.get(key))
        if normalized:
            return _truncate(normalized, _MAX_FOCUS_CHARS)

    workspace_name = _normalize_text(payload.get("workspace_name"))
    if workspace_name:
        return _truncate(f"{workspace_name} · {feature_id}", _MAX_FOCUS_CHARS)
    return feature_id


@dataclass(frozen=True, slots=True)
class FeatureWorkflowPlan:
    """Structured workflow plan for feature-domain subagent orchestration."""

    strategy: str
    phased_plan: PhasedPlan

    @property
    def phase_count(self) -> int:
        return len(self.phased_plan.phases)

    @property
    def task_count(self) -> int:
        return sum(len(phase.tasks) for phase in self.phased_plan.phases)


def _iter_subagent_types(plan: FeatureWorkflowPlan) -> tuple[str, ...]:
    subagent_types: list[str] = []
    for phase in plan.phased_plan.phases:
        for task in phase.tasks:
            subagent_type = _normalize_text(task.get("subagent_type"))
            subagent_types.append(subagent_type or "__missing__")
    return tuple(subagent_types)


def validate_workflow_plan_against_profile(
    plan: FeatureWorkflowPlan,
    profile: FeatureRuntimeProfile,
) -> FeatureWorkflowPlan:
    """Validate an agentic workflow plan against the feature runtime profile."""
    if profile.max_subagents > 0 and plan.task_count > profile.max_subagents:
        raise RuntimeError(
            "feature_runtime_profile_max_subagents_exceeded: "
            f"{profile.workspace_type}.{profile.feature_id} "
            f"declared max={profile.max_subagents}, planned={plan.task_count}"
        )

    if profile.allowed_subagents:
        allowed = set(profile.allowed_subagents)
        disallowed = sorted(set(_iter_subagent_types(plan)) - allowed)
        if disallowed:
            raise RuntimeError(
                "feature_runtime_profile_disallowed_subagents: "
                f"{profile.workspace_type}.{profile.feature_id} "
                f"disallowed={','.join(disallowed)}"
            )
    return plan


def _build_research_plan(*, feature_id: str, focus: str) -> FeatureWorkflowPlan:
    discovery_tasks = [
        {
            "subagent_type": "scout",
            "prompt": (
                f"围绕「{focus}」检索并筛选高相关学术资料。"
                "输出候选论文/专利条目与可信度说明，优先近五年。"
            ),
        },
        {
            "subagent_type": "trend_spotter",
            "prompt": (
                f"围绕「{focus}」提炼研究趋势与热点分支。"
                "输出趋势列表、代表工作与变化方向。"
            ),
        },
        {
            "subagent_type": "gap_miner",
            "prompt": (
                f"围绕「{focus}」识别尚未充分解决的问题。"
                "输出研究空白、潜在风险与可验证假设。"
            ),
        },
    ]
    synthesis_tasks = [
        {
            "subagent_type": "synthesizer",
            "prompt": (
                f"综合上一阶段关于「{focus}」的发现。"
                "输出结构化结论：关键证据、争议点、下一步研究路径。"
            ),
        },
    ]

    return FeatureWorkflowPlan(
        strategy=f"{feature_id}:research_discovery",
        phased_plan=PhasedPlan(
            phases=[
                ExecutionPhase(name="discovery", tasks=discovery_tasks),
                ExecutionPhase(
                    name="synthesis",
                    tasks=synthesis_tasks,
                    depends_on=["discovery"],
                ),
            ]
        ),
    )


def _build_writing_plan(*, feature_id: str, focus: str, action: str) -> FeatureWorkflowPlan:
    evidence_tasks = [
        {
            "subagent_type": "librarian",
            "prompt": (
                f"围绕写作目标「{focus}」准备证据清单与引用建议。"
                "输出支持论点所需的核心文献与证据不足项。"
            ),
        },
        {
            "subagent_type": "reviewer",
            "prompt": (
                f"从评审角度审查「{focus}」写作计划。"
                "输出逻辑风险、结构缺口与优先修正建议。"
            ),
        },
    ]
    drafting_tasks = [
        {
            "subagent_type": "thesis_writer" if feature_id == "thesis_writing" else "writer",
            "prompt": (
                f"基于前序证据与审查意见推进写作：{focus}。"
                f"当前动作: {action or 'default'}。"
                "输出可直接落稿的结构化文本草案。"
            ),
        },
    ]
    return FeatureWorkflowPlan(
        strategy=f"{feature_id}:writing_quality_loop",
        phased_plan=PhasedPlan(
            phases=[
                ExecutionPhase(name="evidence", tasks=evidence_tasks),
                ExecutionPhase(
                    name="drafting",
                    tasks=drafting_tasks,
                    depends_on=["evidence"],
                ),
            ]
        ),
    )


def _build_figure_plan(*, feature_id: str, focus: str) -> FeatureWorkflowPlan:
    plan_tasks = [
        {
            "subagent_type": "figure_planner",
            "prompt": (
                f"围绕「{focus}」规划图表方案。"
                "输出图表类型、布局、关键元素与可视化策略。"
            ),
        },
        {
            "subagent_type": "analyst",
            "prompt": (
                f"从可读性与论证完整性评估图表需求：{focus}。"
                "输出图表应承载的定量/定性信息与验证点。"
            ),
        },
    ]
    return FeatureWorkflowPlan(
        strategy=f"{feature_id}:figure_design_review",
        phased_plan=PhasedPlan(
            phases=[ExecutionPhase(name="figure_design", tasks=plan_tasks)]
        ),
    )


def build_dynamic_feature_workflow_plan(
    *,
    workspace_type: str,
    feature_id: str,
    payload: dict[str, Any],
) -> FeatureWorkflowPlan | None:
    """Build a dynamic subagent workflow plan for complex feature tasks."""
    profile = get_feature_runtime_profile(workspace_type, feature_id)
    if profile is None or profile.runtime_mode != FeatureRuntimeMode.COMPUTE_AGENTIC:
        return None

    focus = _resolve_focus(payload, feature_id)
    params = payload.get("params")
    params = params if isinstance(params, dict) else {}
    action = _normalize_text(params.get("action")).lower()

    plan: FeatureWorkflowPlan | None = None

    if feature_id in {"deep_research", "literature_search", "background_research", "prior_art_search"}:
        plan = _build_research_plan(feature_id=feature_id, focus=focus)

    elif feature_id in {"thesis_writing", "writing"}:
        if feature_id == "thesis_writing" and action == "review_section":
            # review_section is lightweight and should not trigger heavy subagent fanout.
            return None
        plan = _build_writing_plan(feature_id=feature_id, focus=focus, action=action)

    elif feature_id == "figure_generation":
        plan = _build_figure_plan(feature_id=feature_id, focus=focus)

    if plan is None:
        # Preserve explicit workspace_type for future strategy expansion.
        _ = workspace_type
        return None
    return validate_workflow_plan_against_profile(plan, profile)
