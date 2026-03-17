"""Custom task handlers for unified workspace feature execution."""

import logging
from typing import Any

from src.academic.services import ArtifactService
from src.artifacts.types import ArtifactType
from src.database import get_db_session
from src.task.progress import ProgressTracker
from src.thesis.workflow.runner import run_thesis_workflow_request
from src.workspace_features import execute_registered_feature, get_workspace_feature
from src.workspace_features.services.thesis_writing_service import (
    build_chapter_payload,
    build_outline_payload,
)

logger = logging.getLogger(__name__)

THESIS_WORKSPACE_TYPES: set[str] = set()  # 不再按 workspace_type 判断
THESIS_AGENTS: set[str] = set()  # thesis features 通过 task_type 路由，不需要 agent 检测
THESIS_HANDLER_KEYS: set[str] = set()  # thesis features 通过 task_type 路由，不需要 handler_key 检测

_THESIS_WRITING_LANGGRAPH_ACTIONS = {
    "review_section",
    "revise_section",
    "review_and_revise",
}


def _is_thesis_payload(payload: dict[str, Any]) -> bool:
    """Determine whether a task payload should run the thesis workflow."""
    workspace_type = payload.get("workspace_type")
    agent = payload.get("agent")
    handler_key = payload.get("handler_key")
    return (
        workspace_type in THESIS_WORKSPACE_TYPES
        or agent in THESIS_AGENTS
        or handler_key in THESIS_HANDLER_KEYS
    )


def _normalize_progress(progress: float | int | None) -> int:
    """Convert workflow progress to an integer percentage."""
    if progress is None:
        return 0
    numeric = float(progress)
    if numeric <= 1:
        numeric *= 100
    return max(0, min(int(round(numeric)), 100))


def _build_thesis_request(payload: dict[str, Any]) -> dict[str, Any]:
    """Map a unified task payload to the thesis workflow request shape."""
    return {
        "workspace_id": payload.get("workspace_id", ""),
        "thread_id": payload.get("thread_id")
        or payload.get("task_id")
        or payload.get("workspace_id", ""),
        "paper_title": payload.get("paper_title")
        or payload.get("title")
        or payload.get("feature_name")
        or "未命名论文",
        "discipline": payload.get("discipline", "计算机科学"),
        "abstract_content": payload.get("abstract_content") or payload.get("abstract", ""),
        "framework_json": payload.get("framework_json") or payload.get("framework", {}),
        "enable_search": payload.get("enable_search", True),
        "enable_images": payload.get("enable_images", payload.get("feature_id") == "figure"),
    }


def _read_params(payload: dict[str, Any]) -> dict[str, Any]:
    params = payload.get("params")
    return params if isinstance(params, dict) else {}


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _resolve_paper_title(payload: dict[str, Any]) -> str:
    params = _read_params(payload)
    candidate = (
        params.get("paper_title")
        or payload.get("paper_title")
        or params.get("topic")
        or payload.get("title")
        or payload.get("workspace_name")
        or "未命名论文"
    )
    return str(candidate).strip() or "未命名论文"


def _normalize_outline(raw_outline: dict[str, Any]) -> dict[str, Any]:
    """Ensure outline payload matches frontend contract."""
    chapters = raw_outline.get("chapters")
    normalized_chapters: list[dict[str, Any]] = []
    if isinstance(chapters, list):
        for index, chapter in enumerate(chapters, start=1):
            if not isinstance(chapter, dict):
                continue
            normalized_chapters.append(
                {
                    "title": str(chapter.get("title") or f"第{index}章"),
                    "position": str(chapter.get("position") or "正文"),
                    "targetWords": _safe_int(chapter.get("targetWords"), 2500),
                    "keyPoints": (
                        chapter.get("keyPoints")
                        if isinstance(chapter.get("keyPoints"), list)
                        else []
                    ),
                    "sections": (
                        chapter.get("sections")
                        if isinstance(chapter.get("sections"), list)
                        else []
                    ),
                }
            )

    return {
        "abstract": str(raw_outline.get("abstract") or ""),
        "keywords": (
            raw_outline.get("keywords")
            if isinstance(raw_outline.get("keywords"), list)
            else []
        ),
        "chapters": normalized_chapters,
    }


def _build_outline_template(payload: dict[str, Any]) -> dict[str, Any]:
    """Build a deterministic minimal outline for generate_outline action."""
    title = _resolve_paper_title(payload)
    params = _read_params(payload)
    target_words = _safe_int(params.get("target_words"), 20000)
    chapter_targets = [0.12, 0.2, 0.24, 0.24, 0.2]
    chapter_titles = [
        "绪论",
        "相关工作与理论基础",
        "方法与系统设计",
        "实验与结果分析",
        "结论与展望",
    ]
    chapter_positions = [
        "研究背景与问题定义",
        "文献梳理与理论框架",
        "核心方法与实现细节",
        "实验设置、结果与讨论",
        "研究结论、局限与未来工作",
    ]

    chapters = []
    for idx, (ratio, chapter_title, position) in enumerate(
        zip(chapter_targets, chapter_titles, chapter_positions, strict=True)
    ):
        chapter_words = max(1000, int(target_words * ratio))
        chapters.append(
            {
                "title": chapter_title,
                "position": position,
                "targetWords": chapter_words,
                "keyPoints": [
                    f"{title}在{chapter_title}中的核心论点",
                    "本章与全文主线的衔接关系",
                ],
                "sections": [
                    f"{idx + 1}.1 研究问题与目标",
                    f"{idx + 1}.2 方法或论证展开",
                    f"{idx + 1}.3 小结",
                ],
            }
        )

    return _normalize_outline(
        {
            "abstract": f"本文围绕《{title}》展开研究，提出可执行的技术路线并验证其有效性。",
            "keywords": ["研究方法", "系统实现", "实验分析"],
            "chapters": chapters,
        }
    )


async def _persist_artifact(
    *,
    workspace_id: str,
    artifact_type: str,
    title: str,
    content: dict[str, Any],
    created_by_skill: str,
) -> dict[str, str]:
    """Persist one artifact and return lightweight reference."""
    async with get_db_session() as db:
        service = ArtifactService(db)
        artifact = await service.create(
            workspace_id=workspace_id,
            type=artifact_type,
            title=title,
            content=content,
            created_by_skill=created_by_skill,
        )
    return {
        "id": str(artifact.id),
        "type": artifact.type,
        "title": artifact.title or "",
    }


def _report_type_label(report_type: str) -> str:
    return {
        "opening_report": "开题报告",
        "literature_review": "文献综述",
        "feasibility_analysis": "可行性分析",
    }.get(report_type, "研究报告")


def _build_langgraph_artifact_drafts(
    feature_id: str,
    workspace_name: str,
    result: dict[str, Any],
) -> list[dict[str, Any]]:
    """Map LangGraph feature result to artifact drafts."""
    title_prefix = workspace_name or "未命名工作区"

    if feature_id == "literature_management":
        return [
            {
                "type": ArtifactType.LITERATURE_INVENTORY.value,
                "title": f"{title_prefix} - 文献管理盘点",
                "content": result,
            }
        ]

    if feature_id == "opening_research":
        report_type = str(result.get("report_type", "opening_report"))
        return [
            {
                "type": report_type,
                "title": f"{title_prefix} - {_report_type_label(report_type)}",
                "content": result,
            }
        ]

    if feature_id == "figure_generation":
        description = str(result.get("description") or "图表")
        return [
            {
                "type": ArtifactType.FIGURE.value,
                "title": f"{title_prefix} - {description}",
                "content": result,
            }
        ]

    if feature_id == "compile_export":
        return [
            {
                "type": ArtifactType.PAPER_DRAFT.value,
                "title": f"{title_prefix} - 编译预检结果",
                "content": result,
            }
        ]

    if feature_id == "deep_research":
        topic = str(result.get("topic") or title_prefix)
        drafts: list[dict[str, Any]] = []
        discovery = result.get("discovery")
        if isinstance(discovery, dict) and discovery:
            drafts.append(
                {
                    "type": ArtifactType.LITERATURE_REVIEW.value,
                    "title": f"{topic} - 深度调研综述",
                    "content": {
                        "topic": topic,
                        "discovery": discovery,
                        "cross_validation": result.get("cross_validation"),
                        "generation_mode": result.get("generation_mode"),
                    },
                }
            )
        gaps = result.get("gaps")
        if isinstance(gaps, list) and gaps:
            drafts.append(
                {
                    "type": ArtifactType.GAP_ANALYSIS.value,
                    "title": f"{topic} - 研究空白分析",
                    "content": {
                        "topic": topic,
                        "gaps": gaps,
                        "generation_mode": result.get("generation_mode"),
                    },
                }
            )
        ideas = result.get("ideas")
        if isinstance(ideas, list) and ideas:
            drafts.append(
                {
                    "type": ArtifactType.RESEARCH_IDEAS.value,
                    "title": f"{topic} - 研究构想",
                    "content": {
                        "topic": topic,
                        "ideas": ideas,
                        "cross_validation": result.get("cross_validation"),
                        "generation_mode": result.get("generation_mode"),
                    },
                }
            )
        return drafts

    return []


async def _persist_langgraph_artifacts(
    feature_id: str,
    payload: dict[str, Any],
    result: dict[str, Any],
) -> list[dict[str, str]]:
    """Persist artifacts for LangGraph feature results."""
    workspace_id = str(payload.get("workspace_id") or "")
    if not workspace_id:
        return []

    drafts = _build_langgraph_artifact_drafts(
        feature_id,
        str(payload.get("workspace_name") or ""),
        result,
    )
    if not drafts:
        return []

    created_by_skill = str(payload.get("handler_key") or f"thesis.{feature_id}")
    try:
        async with get_db_session() as db:
            service = ArtifactService(db)
            refs: list[dict[str, str]] = []
            for draft in drafts:
                artifact = await service.create(
                    workspace_id=workspace_id,
                    type=str(draft["type"]),
                    title=str(draft["title"]),
                    content=draft["content"],
                    created_by_skill=created_by_skill,
                )
                refs.append(
                    {
                        "id": str(artifact.id),
                        "type": artifact.type,
                        "title": artifact.title or "",
                    }
                )
            return refs
    except Exception:
        logger.warning(
            "Failed to persist LangGraph artifacts for feature '%s'",
            feature_id,
            exc_info=True,
        )
        return []


async def execute_thesis_generation(
    payload: dict[str, Any],
    progress: ProgressTracker,
) -> dict[str, Any]:
    """Execute thesis generation on the unified task infrastructure.

    Supports action routing:
    - "generate_outline": Generate only the thesis outline
    - "write_chapter": Write a single chapter
    - "write_all" (default): Full thesis workflow
    """
    params = _read_params(payload)
    action = payload.get("action") or params.get("action", "write_all")

    # Review/revise actions route to thesis_writing LangGraph sub-graph.
    if str(action) in _THESIS_WRITING_LANGGRAPH_ACTIONS:
        langgraph_result = await _try_langgraph_execution(
            "thesis_writing", payload, progress
        )
        if langgraph_result is not None:
            _schedule_memory_extraction(payload, langgraph_result)
            return langgraph_result

    if action == "generate_outline":
        return await generate_outline_only(payload, progress)
    elif action == "write_chapter":
        return await write_single_chapter(payload, progress)
    else:
        # write_all: 走原有 thesis workflow
        request = _build_thesis_request(payload)

        async def on_update(update: dict[str, Any]) -> None:
            metadata = {
                "feature_id": payload.get("feature_id"),
                "feature_name": payload.get("feature_name"),
                "workspace_type": payload.get("workspace_type", "thesis"),
                "handler_key": payload.get("handler_key"),
                "current_phase": update.get("current_phase"),
                "sections_completed": update.get("sections_completed", 0),
                "sections_total": update.get("sections_total", 0),
                "latex_content": update.get("latex_content", ""),
                "bib_content": update.get("bib_content", ""),
                "pdf_path": update.get("pdf_path", ""),
            }
            await progress.update(
                _normalize_progress(update.get("progress")),
                update.get("message"),
                current_step=update.get("current_phase"),
                metadata=metadata,
            )

        result = await run_thesis_workflow_request(request, on_update=on_update)
        return {
            "feature_id": payload.get("feature_id"),
            "feature_name": payload.get("feature_name"),
            "workspace_type": payload.get("workspace_type", "thesis"),
            "handler_key": payload.get("handler_key"),
            **result,
        }


async def generate_outline_only(
    payload: dict[str, Any],
    progress: ProgressTracker,
) -> dict[str, Any]:
    """Generate thesis outline without full workflow."""
    await progress.update(10, "收集 workspace 上下文")
    await progress.update(55, "生成论文大纲")

    params = _read_params(payload)
    paper_title = _resolve_paper_title(payload)
    target_words = _safe_int(params.get("target_words"), 20000)

    outline_payload = build_outline_payload(
        paper_title=paper_title,
        target_words=target_words,
    )
    outline = outline_payload["outline"]

    created_by_skill = str(payload.get("handler_key") or "thesis.thesis_writing")
    artifact_ref = await _persist_artifact(
        workspace_id=str(payload.get("workspace_id") or ""),
        artifact_type=ArtifactType.FRAMEWORK_OUTLINE.value,
        title=f"{paper_title} - 论文大纲",
        content=outline_payload,
        created_by_skill=created_by_skill,
    )

    await progress.update(100, "大纲生成完成")
    return {
        "feature_id": payload.get("feature_id"),
        "feature_name": payload.get("feature_name"),
        "workspace_type": payload.get("workspace_type", "thesis"),
        "handler_key": payload.get("handler_key"),
        "message": "大纲已生成",
        "outline": outline,
        "artifacts": [artifact_ref],
        "refresh_targets": ["artifacts"],
    }


async def write_single_chapter(
    payload: dict[str, Any],
    progress: ProgressTracker,
) -> dict[str, Any]:
    """Write a single chapter by index."""
    params = _read_params(payload)
    chapter_index = max(0, _safe_int(params.get("chapter_index"), 0))
    chapter_title = str(
        params.get("chapter_title")
        or f"第{chapter_index + 1}章"
    )
    paper_title = _resolve_paper_title(payload)
    target_words = max(500, _safe_int(params.get("target_words"), 2500))

    await progress.update(10, f"准备写作第 {chapter_index + 1} 章")
    await progress.update(45, f"组织第 {chapter_index + 1} 章结构")

    chapter_content = build_chapter_payload(
        paper_title=paper_title,
        chapter_index=chapter_index,
        chapter_title=chapter_title,
        target_words=target_words,
    )

    created_by_skill = str(payload.get("handler_key") or "thesis.thesis_writing")
    artifact_ref = await _persist_artifact(
        workspace_id=str(payload.get("workspace_id") or ""),
        artifact_type=ArtifactType.THESIS_CHAPTER.value,
        title=f"{paper_title} - {chapter_title}",
        content=chapter_content,
        created_by_skill=created_by_skill,
    )

    await progress.update(100, f"第 {chapter_index + 1} 章写作完成")
    return {
        "feature_id": payload.get("feature_id"),
        "feature_name": payload.get("feature_name"),
        "workspace_type": payload.get("workspace_type", "thesis"),
        "handler_key": payload.get("handler_key"),
        "message": f"第 {chapter_index + 1} 章已生成",
        "chapter": {
            "index": chapter_index,
            "title": chapter_title,
            "target_words": target_words,
        },
        "artifacts": [artifact_ref],
        "refresh_targets": ["artifacts"],
    }


async def execute_workspace_feature(
    payload: dict[str, Any],
    progress: ProgressTracker,
) -> dict[str, Any]:
    """Execute a workspace feature using the registry-defined handler key."""
    if _is_thesis_payload(payload):
        return await execute_thesis_generation(payload, progress)

    workspace_type = str(payload.get("workspace_type") or "")
    feature_id = str(payload.get("feature_id") or "")
    feature = get_workspace_feature(workspace_type, feature_id)
    if not feature:
        raise ValueError(
            f"Unknown workspace feature '{feature_id}' for workspace type '{workspace_type}'"
        )

    # Try LangGraph sub-graph for thesis workspace features
    if workspace_type == "thesis":
        langgraph_result = await _try_langgraph_execution(
            feature_id, payload, progress
        )
        if langgraph_result is not None:
            # Trigger async memory extraction (fire-and-forget)
            _schedule_memory_extraction(payload, langgraph_result)
            return langgraph_result

    result = await execute_registered_feature(payload, progress, feature)

    # Trigger async memory extraction for successful handler results too
    if workspace_type == "thesis":
        _schedule_memory_extraction(payload, result)

    return result


_GRAPHS_LOADED = False


def _ensure_graphs_loaded() -> None:
    """Import feature graph modules so @register_feature_graph decorators run."""
    global _GRAPHS_LOADED
    if _GRAPHS_LOADED:
        return
    try:
        import src.agents.graphs.thesis.literature_management  # noqa: F401
        import src.agents.graphs.thesis.opening_research  # noqa: F401
        import src.agents.graphs.thesis.figure_generation  # noqa: F401
        import src.agents.graphs.thesis.compile_export  # noqa: F401
        import src.agents.graphs.thesis.thesis_writing  # noqa: F401
        import src.agents.graphs.thesis.deep_research  # noqa: F401
    except ImportError:
        logger.debug("Some thesis feature graphs could not be loaded")
        return
    _GRAPHS_LOADED = True


async def _try_langgraph_execution(
    feature_id: str,
    payload: dict[str, Any],
    progress: ProgressTracker,
) -> dict[str, Any] | None:
    """Attempt LangGraph sub-graph execution. Returns None on failure (fallback to handler)."""
    _ensure_graphs_loaded()

    try:
        from src.agents.thesis_lead_agent import (
            _FEATURE_GRAPH_REGISTRY,
            execute_thesis_feature_graph,
        )
    except ImportError:
        logger.debug("LangGraph thesis agent not available")
        return None

    if feature_id not in _FEATURE_GRAPH_REGISTRY:
        return None

    user_id = payload.get("user_id") or payload.get("created_by")

    try:
        await progress.update(5, "启动 LangGraph 增强处理")
        result = await execute_thesis_feature_graph(
            feature_id,
            payload,
            user_id=str(user_id) if user_id else None,
        )
        artifacts = await _persist_langgraph_artifacts(feature_id, payload, result)

        # Wrap result in standard feature response format
        wrapped = {
            "success": True,
            "feature_id": feature_id,
            "feature_name": payload.get("feature_name", feature_id),
            "workspace_type": "thesis",
            "handler_key": payload.get("handler_key", f"thesis.{feature_id}"),
            "generation_mode": result.get("generation_mode", "llm"),
            "message": f"{feature_id} 已通过 LangGraph 增强完成",
            "data": result,
            "artifacts": artifacts,
            "refresh_targets": ["artifacts"],
        }
        await progress.update(100, "LangGraph 增强处理完成")
        return wrapped
    except Exception:
        logger.warning(
            "LangGraph execution failed for feature '%s', falling back to handler",
            feature_id,
            exc_info=True,
        )
        return None


def _schedule_memory_extraction(payload: dict[str, Any], result: dict[str, Any]) -> None:
    """Schedule async memory extraction (fire-and-forget)."""
    import asyncio

    user_id = payload.get("user_id") or payload.get("created_by")
    if not user_id:
        return

    workspace_id = payload.get("workspace_id")
    feature_id = payload.get("feature_id", "")

    # Build a brief conversation summary from the interaction
    summary_parts = [
        f"Feature: {feature_id}",
        f"Result mode: {result.get('generation_mode', 'unknown')}",
    ]
    message = result.get("message", "")
    if message:
        summary_parts.append(f"Output: {message}")

    conversation_text = "; ".join(summary_parts)

    async def _extract():
        try:
            from src.agents.middleware.memory import extract_and_persist_knowledge
            await extract_and_persist_knowledge(
                str(user_id),
                conversation_text,
                workspace_context=str(workspace_id) if workspace_id else None,
                source=f"feature:{feature_id}",
            )
        except Exception:
            logger.debug("Memory extraction failed for feature %s", feature_id)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_extract())
    except RuntimeError:
        pass  # No running loop, skip
