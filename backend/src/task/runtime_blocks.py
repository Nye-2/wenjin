"""Helpers for structured task runtime UI blocks."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


_FEATURE_RUNTIME_CONFIG: dict[str, dict[str, Any]] = {
    "literature_search": {
        "title": "文献检索",
        "phases": [
            {"id": "prepare", "label": "准备检索", "description": "整理检索主题与上下文"},
            {"id": "retrieve", "label": "生成结果", "description": "调用模型整理候选文献与命中"},
            {"id": "finalize", "label": "整理产物", "description": "归档结果并生成 artifact"},
        ],
    },
    "paper_analysis": {
        "title": "论文分析",
        "phases": [
            {"id": "prepare", "label": "准备论文", "description": "加载论文标题、摘要与上下文"},
            {"id": "analyze", "label": "结构化分析", "description": "提炼方法、实验、结论和创新点"},
            {"id": "finalize", "label": "整理产物", "description": "封装分析结果并沉淀 artifact"},
        ],
    },
    "writing": {
        "title": "论文写作",
        "phases": [
            {"id": "prepare", "label": "准备上下文", "description": "加载章节要求与上下文产物"},
            {"id": "draft", "label": "生成草稿", "description": "调用模型撰写章节草稿"},
            {"id": "finalize", "label": "整理产物", "description": "整理大纲、参考和 draft artifact"},
        ],
    },
    "opening_research": {
        "title": "开题调研",
        "phases": [
            {"id": "research_status", "label": "研究现状", "description": "分析现有研究与文献背景"},
            {"id": "methodology", "label": "方法规划", "description": "规划可行的方法路线"},
            {"id": "report", "label": "生成报告", "description": "整合章节内容并输出报告"},
        ],
    },
    "background_research": {
        "title": "背景调研",
        "phases": [
            {"id": "scope", "label": "调研范围", "description": "确认主题、范围和时间窗口"},
            {"id": "research", "label": "背景分析", "description": "生成行业背景与研究现状"},
            {"id": "report", "label": "整理报告", "description": "封装章节与参考文献"},
        ],
    },
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
