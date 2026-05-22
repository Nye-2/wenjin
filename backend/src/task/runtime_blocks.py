"""Helpers for structured task runtime UI blocks."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from src.task.progress import emit_runtime_update, get_runtime_state

__all__ = [
    "emit_runtime_update",
    "get_runtime_state",
    "create_feature_runtime",
    "append_runtime_activity",
    "set_runtime_phase",
    "advance_runtime_phase",
    "upsert_runtime_block",
    "runtime_progress_for_phase",
    "emit_bound_runtime",
]

_MISSION_TITLES: dict[str, str] = {
    "idea_to_thesis_manuscript": "Idea 到论文全文",
    "thesis_research_pack": "论文研究包",
    "thesis_empirical_analysis": "论文实证分析",
    "thesis_revision_pass": "论文修订",
    "thesis_defense_pack": "答辩材料包",
    "thesis_reference_curation": "参考文献整理",
    "research_question_to_paper": "SCI 论文主稿",
    "sci_literature_positioning": "SCI 文献定位",
    "sci_empirical_package": "SCI 实证包",
    "sci_revision_for_journal": "SCI 期刊修订",
    "journal_submission_strategy": "投稿策略",
    "response_to_reviewers": "审稿回复",
    "reproducibility_audit": "可复现性审计",
    "idea_to_proposal_package": "申报书整包",
    "proposal_background_pack": "申报背景包",
    "technical_route_package": "技术路线包",
    "feasibility_and_risk_review": "可行性与风险评审",
    "proposal_polish_for_review": "申报书送审润色",
    "software_copyright_application_pack": "软著申请包",
    "software_technical_manual": "软件技术说明书",
    "software_evidence_pack": "软著证据包",
    "software_architecture_diagrams": "软件架构图",
    "invention_to_patent_draft": "专利初稿",
    "prior_art_and_novelty_pack": "现有技术与新颖性包",
    "claims_strategy": "权利要求策略",
    "embodiment_and_drawings": "实施例与附图",
    "office_action_response": "审查意见答复",
}

_MISSION_PHASES: list[dict[str, str]] = [
    {"id": "plan", "label": "规划任务", "description": "确认目标、约束、上下文和交付边界"},
    {"id": "execute", "label": "执行任务", "description": "调度技能与工具完成 mission 产出"},
    {"id": "review", "label": "整理审核", "description": "生成可审核结果并提交 Prism 或房间候选项"},
    {"id": "finalize", "label": "完成收口", "description": "沉淀执行记录、产物摘要和后续动作"},
]

_FEATURE_RUNTIME_CONFIG: dict[str, dict[str, Any]] = {
    mission_id: {"title": title, "phases": _MISSION_PHASES}
    for mission_id, title in _MISSION_TITLES.items()
}


def create_feature_runtime(feature_id: str, overview_entries: list[dict[str, str]]) -> dict[str, Any]:
    """Create an initial runtime state for a feature execution."""
    config = _FEATURE_RUNTIME_CONFIG[feature_id]
    phases = []
    for index, phase in enumerate(config["phases"]):
        phases.append(
            {
                **phase,
                "status": "running" if index == 0 else "pending",
                "progress": 0,
            }
        )

    return {
        "title": config["title"],
        "current_phase": config["phases"][0]["id"],
        "phases": phases,
        "blocks": [
            {
                "id": "overview",
                "kind": "metrics",
                "title": "执行配置",
                "entries": overview_entries,
            },
            {
                "id": "activity",
                "kind": "activity",
                "title": "执行日志",
                "items": [],
            },
        ],
        "updated_at": datetime.now(UTC).isoformat(),
    }


def append_runtime_activity(
    runtime: dict[str, Any],
    *,
    title: str,
    description: str,
    tone: str = "info",
) -> None:
    """Append a short activity event to the runtime state."""
    activity = next(
        (block for block in runtime.get("blocks", []) if block.get("id") == "activity"),
        None,
    )
    if activity is None:
        activity = {"id": "activity", "kind": "activity", "title": "执行日志", "items": []}
        runtime.setdefault("blocks", []).append(activity)
    items = activity.setdefault("items", [])
    items.append(
        {
            "title": title,
            "description": description,
            "tone": tone,
            "timestamp": datetime.now(UTC).isoformat(),
        }
    )
    if len(items) > 12:
        del items[:-12]


def set_runtime_phase(
    runtime: dict[str, Any],
    phase_id: str,
    *,
    status: str,
    progress: int,
) -> None:
    """Update a runtime phase in place."""
    for phase in runtime.get("phases", []):
        if phase.get("id") == phase_id:
            phase["status"] = status
            phase["progress"] = progress
            break
    runtime["current_phase"] = phase_id
    runtime["updated_at"] = datetime.now(UTC).isoformat()


def advance_runtime_phase(
    runtime: dict[str, Any],
    current_phase_id: str,
    next_phase_id: str | None,
) -> None:
    """Mark the current phase completed and optionally start the next one."""
    set_runtime_phase(runtime, current_phase_id, status="completed", progress=100)
    if next_phase_id is not None:
        set_runtime_phase(runtime, next_phase_id, status="running", progress=0)
        runtime["current_phase"] = next_phase_id


def upsert_runtime_block(runtime: dict[str, Any], block: dict[str, Any]) -> None:
    """Insert or replace a runtime block by id."""
    blocks = runtime.setdefault("blocks", [])
    for index, existing in enumerate(blocks):
        if existing.get("id") == block.get("id"):
            blocks[index] = block
            return
    blocks.append(block)


def runtime_progress_for_phase(runtime: dict[str, Any]) -> int:
    """Estimate overall progress from phase completion values."""
    phases = runtime.get("phases", [])
    if not phases:
        return 0
    return int(
        sum(int(phase.get("progress", 0) or 0) for phase in phases) / len(phases)
    )


async def emit_bound_runtime(
    *,
    message: str,
    current_phase: str,
    stage_transition: bool = False,
) -> None:
    """Emit the currently bound runtime state if available.

    Canonical single implementation; import as ``_emit_bound_runtime`` at call
    sites to preserve the existing internal naming convention::

        from src.task.runtime_blocks import emit_bound_runtime as _emit_bound_runtime
    """
    runtime = get_runtime_state()
    if runtime is None:
        return
    await emit_runtime_update(
        progress_value=max(runtime_progress_for_phase(runtime), 5),
        message=message,
        current_phase=current_phase,
        runtime=runtime,
        stage_transition=stage_transition,
    )
