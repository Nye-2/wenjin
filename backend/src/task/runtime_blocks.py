"""Helpers for structured task runtime UI blocks."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from src.task.progress import emit_runtime_update, get_runtime_state

_FEATURE_RUNTIME_CONFIG: dict[str, dict[str, Any]] = {
    "deep_research": {
        "title": "深度调研",
        "phases": [
            {"id": "discovery", "label": "发现文献", "description": "并行检索经典文献、近期工作与研究趋势"},
            {"id": "gap_mining", "label": "挖掘空白", "description": "识别研究空白与可切入的问题空间"},
            {"id": "synthesis", "label": "综合创意", "description": "生成候选方向、研究创意和后续建议"},
            {"id": "cross_validation", "label": "交叉验证", "description": "检查发现与创意的一致性和可信度"},
            {"id": "finalize", "label": "整理产物", "description": "封装深度调研报告并写入 artifact"},
        ],
    },
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
    "literature_review": {
        "title": "文献综述",
        "phases": [
            {"id": "prepare", "label": "整理主题", "description": "确认主题、学科与上下文 artifact"},
            {"id": "synthesize", "label": "综合综述", "description": "归纳 key papers、研究空白与章节结构"},
            {"id": "finalize", "label": "整理产物", "description": "封装文献综述 artifact"},
        ],
    },
    "framework_outline": {
        "title": "框架与摘要",
        "phases": [
            {"id": "prepare", "label": "整理输入", "description": "确认题目、主题与上下文 artifact"},
            {"id": "outline", "label": "生成框架", "description": "生成摘要、关键词和章节结构"},
            {"id": "finalize", "label": "整理产物", "description": "封装框架 artifact"},
        ],
    },
    "peer_review": {
        "title": "同行评审",
        "phases": [
            {"id": "prepare", "label": "读取稿件", "description": "加载论文标题与待审内容"},
            {"id": "review", "label": "评审分析", "description": "识别 strengths、weaknesses 与 revision actions"},
            {"id": "finalize", "label": "整理产物", "description": "封装评审 artifact"},
        ],
    },
    "journal_recommend": {
        "title": "期刊推荐",
        "phases": [
            {"id": "prepare", "label": "提炼画像", "description": "确认论文标题、摘要和学科领域"},
            {"id": "match", "label": "匹配期刊", "description": "生成候选期刊、fit 和投稿建议"},
            {"id": "finalize", "label": "整理产物", "description": "封装推荐摘要 artifact"},
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
    "experiment_design": {
        "title": "实验设计",
        "phases": [
            {"id": "hypothesis", "label": "明确假设", "description": "确认研究目标与核心假设"},
            {"id": "variables", "label": "设计变量", "description": "生成变量、流程与实验方案"},
            {"id": "evaluation", "label": "规划评估", "description": "整理评估指标、风险与验证路径"},
            {"id": "finalize", "label": "整理产物", "description": "封装实验设计 artifact"},
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
    "thesis_writing_full": {
        "title": "全文写作",
        "phases": [
            {"id": "prepare", "label": "准备参数", "description": "确认标题、字数与上下文"},
            {"id": "outline", "label": "生成大纲", "description": "规划章节结构与写作顺序"},
            {"id": "draft", "label": "批量写作", "description": "按章节生成全文草稿"},
            {"id": "finalize", "label": "整理产物", "description": "落库大纲与章节 artifact"},
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
