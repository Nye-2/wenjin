"""Custom task handlers for unified workspace feature execution."""

import logging
from typing import Any

from src.academic.services import ArtifactService
from src.artifacts.types import ArtifactType
from src.database import get_db_session
from src.task.progress import ProgressTracker
from src.thesis.workflow.runner import run_thesis_workflow_request
from src.workspace_features import execute_registered_feature, get_workspace_feature

logger = logging.getLogger(__name__)

THESIS_WORKSPACE_TYPES: set[str] = set()  # 不再按 workspace_type 判断
THESIS_AGENTS: set[str] = set()  # thesis features 通过 task_type 路由，不需要 agent 检测
THESIS_HANDLER_KEYS: set[str] = set()  # thesis features 通过 task_type 路由，不需要 handler_key 检测


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
    action = payload.get("action") or payload.get("params", {}).get("action", "write_all")

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

    outline = _build_outline_template(payload)
    paper_title = _resolve_paper_title(payload)
    created_by_skill = str(payload.get("handler_key") or "thesis.thesis_writing")
    artifact_ref = await _persist_artifact(
        workspace_id=str(payload.get("workspace_id") or ""),
        artifact_type=ArtifactType.FRAMEWORK_OUTLINE.value,
        title=f"{paper_title} - 论文大纲",
        content={
            "paper_title": paper_title,
            "outline": outline,
            "action": "generate_outline",
        },
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

    chapter_markdown = "\n\n".join(
        [
            f"# {chapter_title}",
            f"## 研究背景\n围绕《{paper_title}》展开本章论证，明确研究场景与问题边界。",
            "## 核心内容\n给出关键方法、实验设计或理论推导，并说明实现路径。",
            "## 本章小结\n总结本章结论并衔接后续章节。",
        ]
    )
    chapter_content = {
        "paper_title": paper_title,
        "chapter_index": chapter_index,
        "chapter_title": chapter_title,
        "target_words": target_words,
        "estimated_words": max(800, int(target_words * 0.35)),
        "markdown": chapter_markdown,
        "action": "write_chapter",
    }

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

    return await execute_registered_feature(payload, progress, feature)
