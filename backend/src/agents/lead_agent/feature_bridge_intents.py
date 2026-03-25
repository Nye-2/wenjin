"""Intent parsing helpers for deterministic workspace feature bridge."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Any

from src.workspace_features import list_workspace_features

_FEATURE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "deep_research": ("deep research", "深度调研", "深度研究"),
    "literature_management": ("文献管理", "整理文献", "盘点文献", "organize literature"),
    "literature_search": ("文献检索", "检索文献", "search literature"),
    "paper_analysis": ("论文分析", "分析论文", "分析这篇论文", "paper analysis"),
    "writing": (
        "sci写作",
        "章节草稿",
        "写摘要",
        "写引言",
        "写方法",
        "写实验",
        "write abstract",
        "write introduction",
        "write methodology",
        "write experiments",
    ),
    "literature_review": ("文献综述", "literature review"),
    "framework_outline": ("大纲", "outline", "框架", "摘要与大纲"),
    "opening_research": ("开题调研", "开题报告", "opening research"),
    "thesis_writing": ("写论文", "写全文", "write thesis", "write paper", "章节"),
    "figure_generation": ("图表", "figure", "配图", "插图"),
    "compile_export": ("编译", "导出", "export pdf", "compile"),
    "peer_review": ("同行评审", "审稿", "peer review", "review this paper"),
    "journal_recommend": ("期刊推荐", "推荐期刊", "journal recommend"),
    "experiment_design": ("实验设计", "研究设计", "experiment design"),
    "proposal_outline": ("申报书大纲", "proposal outline", "立项大纲"),
    "background_research": ("背景调研", "background research"),
    "copyright_materials": ("软著材料", "材料清单", "著作权材料", "copyright materials"),
    "technical_description": ("技术说明书", "技术说明", "technical description"),
    "patent_outline": ("专利框架", "专利大纲", "权利要求", "patent outline"),
    "prior_art_search": ("现有技术检索", "专利检索", "prior art", "prior-art", "新颖性分析"),
}

_SCI_SECTION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "abstract": ("摘要", "abstract"),
    "introduction": ("引言", "introduction"),
    "related_work": ("相关工作", "related work"),
    "methodology": ("方法", "methodology", "method"),
    "experiments": ("实验", "experiments", "experiment"),
    "results": ("结果", "results"),
    "discussion": ("讨论", "discussion"),
    "conclusion": ("结论", "conclusion"),
}

_GENERIC_ACTION_WORDS = (
    "开始",
    "启动",
    "安排",
    "生成",
    "写",
    "执行",
    "run",
    "start",
    "generate",
    "draft",
    "review",
)

_FEATURE_TRIGGER_ALIASES: tuple[str, ...] = tuple(
    sorted(
        {
            alias.lower()
            for aliases in _FEATURE_KEYWORDS.values()
            for alias in aliases
        },
        key=len,
        reverse=True,
    )
)


def _normalize_text(value: str | None) -> str:
    return " ".join((value or "").strip().split())


def extract_target_words(message: str) -> int | None:
    """Parse target word count from the message."""
    match = re.search(r"(\d{3,6})\s*(?:字|words?)", message, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return None


def message_has_action_intent(message: str) -> bool:
    """Check whether the message sounds like a task trigger."""
    lowered = (message or "").lower()
    return any(token in lowered for token in _GENERIC_ACTION_WORDS)


def extract_topic_from_message(message: str) -> str | None:
    """Infer a topic or subject phrase from the message."""
    normalized = _normalize_text(message)
    if not normalized:
        return None

    patterns = (
        r"(?:关于|围绕|题目是|主题是|topic is)\s*[:：]?\s*(.+)$",
        r"(?:写|生成|启动|安排)\s*(.+?)(?:的|之)?(?:文献综述|大纲|论文|图表|同行评审|期刊推荐|实验设计)$",
    )
    for pattern in patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if match:
            candidate = _normalize_text(match.group(1))
            if candidate:
                return candidate

    lowered = normalized.lower()
    if message_has_action_intent(normalized) and any(
        alias in lowered for alias in _FEATURE_TRIGGER_ALIASES
    ):
        return None

    if len(normalized) <= 72:
        return normalized
    return None


def extract_chapter_title(message: str) -> str | None:
    """Infer thesis chapter title from the message."""
    normalized = _normalize_text(message)
    if not normalized:
        return None
    match = re.search(r"(?:章节|chapter)\s*[:：]?\s*(.+)$", normalized, flags=re.IGNORECASE)
    if match:
        title = _normalize_text(match.group(1))
        return title or None
    return None


def extract_section_type(message: str) -> str | None:
    """Infer SCI section type from the message."""
    lowered = (message or "").lower()
    for section_type, keywords in _SCI_SECTION_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return section_type
    return None


def split_keywords(value: str | None) -> list[str]:
    """Split a text field into short keyword candidates."""
    if not value:
        return []
    items = [
        item.strip()
        for item in re.split(r"[,，;；、\n]+", value)
        if item and item.strip()
    ]
    if items:
        return items[:5]
    normalized = _normalize_text(value)
    return [normalized] if normalized else []


def select_feature_by_message(
    workspace_type: str,
    message: str,
) -> tuple[str, dict[str, Any]] | None:
    """Resolve feature candidate from free-form chat message."""
    lowered = (message or "").lower()
    for feature in list_workspace_features(workspace_type):
        match_tokens = {
            feature.id.lower(),
            feature.name.lower(),
            *[keyword.lower() for keyword in _FEATURE_KEYWORDS.get(feature.id, ())],
        }
        if any(token and token in lowered for token in match_tokens):
            return feature.id, {}

    if workspace_type == "thesis":
        literature_review_tokens = {
            keyword.lower()
            for keyword in _FEATURE_KEYWORDS.get("literature_review", ())
        }
        if any(token in lowered for token in literature_review_tokens):
            return "opening_research", {"report_type": "literature_review"}

    if workspace_type == "proposal" and message_has_action_intent(message):
        if "实验" in lowered or "experiment" in lowered:
            return "experiment_design", {}
        if "背景" in lowered:
            return "background_research", {}
        if "大纲" in lowered or "outline" in lowered:
            return "proposal_outline", {}

    return None


async def resolve_feature_params(
    *,
    feature_id: str,
    params: dict[str, Any],
    workspace_type: str,
    workspace: Any,
    message: str,
    load_latest_draft_summary: Callable[[str], Awaitable[tuple[str | None, str | None]]],
) -> tuple[dict[str, Any], str | None, str | None]:
    """Fill default params and missing-info diagnostics for a feature intent."""
    next_params = dict(params)
    topic = extract_topic_from_message(message)
    workspace_name = str(getattr(workspace, "name", "") or "").strip()
    workspace_description = str(getattr(workspace, "description", "") or "").strip()

    if feature_id in {"deep_research", "literature_search", "literature_review"}:
        query = topic or workspace_description or workspace_name
        if query:
            if feature_id == "literature_search":
                next_params.setdefault("query", query)
            else:
                next_params.setdefault("topic", query)

    if feature_id == "literature_management":
        next_params.setdefault(
            "topic",
            topic or workspace_description or workspace_name or "研究主题",
        )

    if feature_id == "paper_analysis":
        next_params.setdefault("paper_title", topic or workspace_name or "未命名论文")
        if workspace_description:
            next_params.setdefault("paper_abstract", workspace_description)

    if feature_id == "writing":
        next_params.setdefault("paper_title", workspace_name or topic or "未命名论文")
        next_params.setdefault("section_type", extract_section_type(message) or "introduction")
        next_params.setdefault("target_words", extract_target_words(message) or 1200)

    if feature_id == "framework_outline":
        next_params.setdefault("paper_title", topic or workspace_name or "未命名论文")
        next_params.setdefault(
            "topic",
            topic or workspace_description or workspace_name or "研究主题",
        )
        next_params.setdefault("target_words", extract_target_words(message) or 6000)

    if feature_id == "thesis_writing":
        action = str(next_params.get("action") or "").strip().lower()
        if not action:
            lowered = message.lower()
            if "章节" in lowered or "chapter" in lowered:
                action = "write_chapter"
            elif "大纲" in lowered or "outline" in lowered:
                action = "generate_outline"
            else:
                action = "write_all"
            next_params["action"] = action
        next_params.setdefault("paper_title", workspace_name or "未命名论文")
        if action == "generate_outline":
            next_params.setdefault("target_words", extract_target_words(message) or 20000)
        elif action == "write_all":
            next_params.setdefault("target_words", extract_target_words(message) or 12000)
        elif action == "write_chapter":
            chapter_title = extract_chapter_title(message)
            if not chapter_title:
                return next_params, "要直接写章节，还需要告诉我章节标题。", None
            next_params["chapter_title"] = chapter_title
            next_params.setdefault("target_words", extract_target_words(message) or 2500)

    if feature_id == "figure_generation":
        description = topic or workspace_description or ""
        if not description or description == workspace_name:
            return (
                next_params,
                "图表生成需要更具体的图意描述，例如“系统架构图”或“实验结果柱状图”。",
                None,
            )
        next_params.setdefault("description", description)
        next_params.setdefault("fig_type", "flowchart")

    if feature_id == "compile_export":
        next_params.setdefault("target", "pdf")

    if feature_id == "opening_research":
        next_params.setdefault(
            "topic",
            topic or workspace_description or workspace_name or "研究主题",
        )
        next_params.setdefault("report_type", "opening_report")

    if feature_id == "peer_review":
        title, excerpt = await load_latest_draft_summary(str(getattr(workspace, "id", "")))
        if title:
            next_params.setdefault("paper_title", title)
        if excerpt:
            next_params.setdefault("manuscript_excerpt", excerpt)
        if not next_params.get("manuscript_excerpt"):
            return (
                next_params,
                "同行评审需要已有稿件内容。你可以先生成大纲/草稿，或者直接把要评审的文本贴给我。",
                "framework_outline",
            )

    if feature_id == "journal_recommend":
        title, excerpt = await load_latest_draft_summary(str(getattr(workspace, "id", "")))
        next_params.setdefault("paper_title", title or topic or workspace_name or "未命名论文")
        if excerpt:
            next_params.setdefault("abstract", excerpt)
        elif workspace_description:
            next_params.setdefault("abstract", workspace_description)
        if not next_params.get("abstract"):
            return next_params, "期刊推荐至少需要论文摘要或研究简介。", "framework_outline"

    if feature_id == "experiment_design":
        objective = topic or workspace_description or workspace_name
        if not objective:
            return next_params, "实验设计需要至少一个研究目标或任务主题。", None
        next_params.setdefault("topic", objective)
        next_params.setdefault("objective", objective)

    if feature_id == "proposal_outline":
        next_params.setdefault("topic", topic or workspace_name or "研究课题")
        next_params.setdefault("period_months", 24)

    if feature_id == "background_research":
        next_params.setdefault(
            "keywords",
            topic or workspace_name or workspace_description or "研究主题",
        )
        next_params.setdefault("industry_scope", workspace_description or "相关领域")
        next_params.setdefault("time_range", "近5年")

    if feature_id == "copyright_materials":
        next_params.setdefault("software_name", workspace_name or "待确认软件")
        next_params.setdefault("version", "V1.0")
        if workspace_description:
            next_params.setdefault("highlights", split_keywords(workspace_description))

    if feature_id == "technical_description":
        next_params.setdefault("software_name", workspace_name or "待确认软件")
        next_params.setdefault("version", "V1.0")
        next_params.setdefault("deployment_architecture", "B/S架构")

    if feature_id == "patent_outline":
        innovation_description = topic or workspace_description or workspace_name
        if not innovation_description:
            return next_params, "专利框架至少需要一个创新点描述或发明主题。", None
        next_params.setdefault("innovation_description", innovation_description)
        discipline = str(getattr(workspace, "discipline", "") or "").strip()
        if discipline:
            next_params.setdefault("technical_field", discipline)
        if workspace_description:
            next_params.setdefault("application_scenario", workspace_description)

    if feature_id == "prior_art_search":
        keyword_seed = topic or workspace_name or workspace_description
        keyword_list = split_keywords(keyword_seed)
        if not keyword_list:
            return next_params, "现有技术检索需要至少一个关键词或技术主题。", None
        next_params.setdefault("keywords", keyword_list)
        next_params.setdefault("time_range", "近5年")

    if feature_id == "literature_review" and workspace_type == "thesis":
        next_params.setdefault("report_type", "literature_review")

    return next_params, None, None
