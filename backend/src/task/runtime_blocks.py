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
    "proposal_outline": {
        "title": "申报书大纲",
        "phases": [
            {"id": "scope", "label": "项目范围", "description": "确认主题、类型与周期"},
            {"id": "outline", "label": "生成大纲", "description": "生成章节结构、里程碑与风险"},
            {"id": "finalize", "label": "整理产物", "description": "封装大纲 artifact"},
        ],
    },
    "patent_outline": {
        "title": "专利框架",
        "phases": [
            {"id": "scope", "label": "创新输入", "description": "确认创新点、场景与实施方式"},
            {"id": "draft", "label": "生成框架", "description": "生成说明书结构和权利要求草案"},
            {"id": "finalize", "label": "整理产物", "description": "封装专利框架 artifact"},
        ],
    },
    "prior_art_search": {
        "title": "现有技术检索",
        "phases": [
            {"id": "scope", "label": "检索范围", "description": "确认关键词、IPC 和时间范围"},
            {"id": "analysis", "label": "风险分析", "description": "比较现有技术并识别新颖性风险"},
            {"id": "finalize", "label": "整理产物", "description": "输出检索报告 artifact"},
        ],
    },
    "copyright_materials": {
        "title": "软著材料",
        "phases": [
            {"id": "profile", "label": "软件画像", "description": "确认软件信息和亮点"},
            {"id": "materials", "label": "生成清单", "description": "生成申请材料和校验清单"},
            {"id": "finalize", "label": "整理产物", "description": "封装材料 artifact"},
        ],
    },
    "technical_description": {
        "title": "技术说明书",
        "phases": [
            {"id": "profile", "label": "技术画像", "description": "确认软件架构和模块信息"},
            {"id": "write", "label": "生成说明书", "description": "生成说明书章节内容"},
            {"id": "finalize", "label": "整理产物", "description": "封装说明书 artifact"},
        ],
    },
    "figure_generation": {
        "title": "图表生成",
        "phases": [
            {"id": "plan", "label": "规划图表", "description": "确认图表类型与章节上下文"},
            {"id": "render", "label": "生成图表", "description": "生成源码、提示词或渲染结果"},
            {"id": "finalize", "label": "整理产物", "description": "封装图表 artifact"},
        ],
    },
    "compile_export": {
        "title": "编译导出",
        "phases": [
            {"id": "review", "label": "一致性检查", "description": "检查章节一致性并生成摘要"},
            {"id": "compile", "label": "编译导出", "description": "生成 LaTeX、BibTeX 和 PDF"},
            {"id": "finalize", "label": "整理产物", "description": "封装编译结果 artifact"},
        ],
    },
    "literature_management": {
        "title": "文献管理",
        "phases": [
            {"id": "collect", "label": "加载文献", "description": "统计工作区已有文献"},
            {"id": "analyze", "label": "智能盘点", "description": "聚类主题并评估文献质量"},
            {"id": "finalize", "label": "整理产物", "description": "封装文献盘点 artifact"},
        ],
    },
    "thesis_writing_outline": {
        "title": "论文大纲",
        "phases": [
            {"id": "prepare", "label": "准备参数", "description": "确认标题、字数与上下文"},
            {"id": "outline", "label": "生成大纲", "description": "生成章节结构与写作顺序"},
            {"id": "finalize", "label": "整理产物", "description": "封装大纲 artifact"},
        ],
    },
    "thesis_writing_chapter": {
        "title": "章节写作",
        "phases": [
            {"id": "prepare", "label": "准备章节", "description": "确认章节标题与目标字数"},
            {"id": "draft", "label": "生成章节", "description": "撰写章节正文内容"},
            {"id": "finalize", "label": "整理产物", "description": "封装章节 artifact"},
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
