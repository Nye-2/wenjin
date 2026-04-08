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
    "补充",
    "细化",
    "优化",
    "重写",
    "改写",
    "调整",
    "完善",
    "扩写",
    "更新",
    "重新",
    "执行",
    "run",
    "start",
    "generate",
    "draft",
    "review",
    "revise",
    "rewrite",
    "refine",
    "expand",
    "update",
)

_QUESTION_PHRASES = (
    "?",
    "？",
    "为什么",
    "为何",
    "如何",
    "怎么",
    "怎样",
    "什么",
    "是否",
    "吗",
    "么",
    "呢",
    "what",
    "why",
    "how",
    "which",
)

_ACTION_PATTERNS = (
    re.compile(
        r"(?:^|[\s,，。！!；;：:])写(?:摘要|引言|方法|实验|结果|讨论|结论|论文|全文|章节|大纲)",
        flags=re.IGNORECASE,
    ),
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


def _canonical_command_text(value: str | None) -> str:
    return _normalize_text(value).lower().rstrip("。！？!?，,；;：:")


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
    normalized = _normalize_text(message)
    lowered = _canonical_command_text(normalized)
    return any(token in lowered for token in _GENERIC_ACTION_WORDS) or any(
        pattern.search(normalized) for pattern in _ACTION_PATTERNS
    )


def message_looks_like_question(message: str) -> bool:
    """Return whether the message reads like a question rather than a command."""
    normalized = _normalize_text(message)
    if not normalized:
        return False

    lowered = normalized.lower()
    if any(token in normalized for token in ("?", "？")):
        return True

    if normalized.endswith(("吗", "么", "呢")):
        return True

    return any(token in lowered for token in _QUESTION_PHRASES)


def message_is_explicit_feature_command(message: str) -> bool:
    """Check whether the message is a concise feature command."""
    return _canonical_command_text(message) in _FEATURE_TRIGGER_ALIASES


def message_is_actionable_feature_request(message: str) -> bool:
    """Return whether a message should trigger deterministic feature execution."""
    canonical = _canonical_command_text(message)
    if not canonical:
        return False
    if message_is_explicit_feature_command(message):
        return True
    if message_looks_like_question(message):
        return False
    return message_has_action_intent(message)


def message_looks_like_topic_seed(message: str) -> bool:
    """Return whether the message looks like a topic seed for a selected skill."""
    normalized = _normalize_text(message)
    if not normalized:
        return False
    if message_looks_like_question(normalized):
        return False
    if message_is_actionable_feature_request(normalized):
        return False
    if len(normalized) > 72:
        return False
    if any(token in normalized for token in ("，", ",", "；", ";", "：", ":", "\n")):
        return False
    return True


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
    if not message_is_actionable_feature_request(message):
        return None

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


# ---------------------------------------------------------------------------
# Per-feature param resolver type.
# Each resolver has the same kwargs as resolve_feature_params minus feature_id.
# ---------------------------------------------------------------------------

_ParamResolverFn = Callable[..., Awaitable[tuple[dict[str, Any], str | None, str | None]]]
_PARAM_RESOLVERS: dict[str, _ParamResolverFn] = {}


def _resolver(feature_id: str) -> Callable[[_ParamResolverFn], _ParamResolverFn]:
    """Decorator: register an async param resolver for a feature."""
    def decorator(fn: _ParamResolverFn) -> _ParamResolverFn:
        _PARAM_RESOLVERS[feature_id] = fn
        return fn
    return decorator


@_resolver("deep_research")
async def _resolve_deep_research(
    *,
    params: dict[str, Any],
    workspace_type: str,
    workspace: Any,
    message: str,
    load_latest_draft_summary: Callable[[str], Awaitable[tuple[str | None, str | None]]],
) -> tuple[dict[str, Any], str | None, str | None]:
    next_params = dict(params)
    topic = extract_topic_from_message(message)
    workspace_name = str(getattr(workspace, "name", "") or "").strip()
    workspace_description = str(getattr(workspace, "description", "") or "").strip()
    query = topic or workspace_description or workspace_name
    if query:
        next_params.setdefault("topic", query)
    return next_params, None, None


@_resolver("literature_search")
async def _resolve_literature_search(
    *,
    params: dict[str, Any],
    workspace_type: str,
    workspace: Any,
    message: str,
    load_latest_draft_summary: Callable[[str], Awaitable[tuple[str | None, str | None]]],
) -> tuple[dict[str, Any], str | None, str | None]:
    next_params = dict(params)
    topic = extract_topic_from_message(message)
    workspace_name = str(getattr(workspace, "name", "") or "").strip()
    workspace_description = str(getattr(workspace, "description", "") or "").strip()
    query = topic or workspace_description or workspace_name
    if query:
        next_params.setdefault("query", query)
    return next_params, None, None


@_resolver("literature_review")
async def _resolve_literature_review(
    *,
    params: dict[str, Any],
    workspace_type: str,
    workspace: Any,
    message: str,
    load_latest_draft_summary: Callable[[str], Awaitable[tuple[str | None, str | None]]],
) -> tuple[dict[str, Any], str | None, str | None]:
    next_params = dict(params)
    topic = extract_topic_from_message(message)
    workspace_name = str(getattr(workspace, "name", "") or "").strip()
    workspace_description = str(getattr(workspace, "description", "") or "").strip()
    query = topic or workspace_description or workspace_name
    if query:
        next_params.setdefault("topic", query)
    if workspace_type == "thesis":
        next_params.setdefault("report_type", "literature_review")
    return next_params, None, None


@_resolver("literature_management")
async def _resolve_literature_management(
    *,
    params: dict[str, Any],
    workspace_type: str,
    workspace: Any,
    message: str,
    load_latest_draft_summary: Callable[[str], Awaitable[tuple[str | None, str | None]]],
) -> tuple[dict[str, Any], str | None, str | None]:
    next_params = dict(params)
    topic = extract_topic_from_message(message)
    workspace_name = str(getattr(workspace, "name", "") or "").strip()
    workspace_description = str(getattr(workspace, "description", "") or "").strip()
    next_params.setdefault(
        "topic",
        topic or workspace_description or workspace_name or "研究主题",
    )
    return next_params, None, None


@_resolver("paper_analysis")
async def _resolve_paper_analysis(
    *,
    params: dict[str, Any],
    workspace_type: str,
    workspace: Any,
    message: str,
    load_latest_draft_summary: Callable[[str], Awaitable[tuple[str | None, str | None]]],
) -> tuple[dict[str, Any], str | None, str | None]:
    next_params = dict(params)
    topic = extract_topic_from_message(message)
    workspace_name = str(getattr(workspace, "name", "") or "").strip()
    workspace_description = str(getattr(workspace, "description", "") or "").strip()
    next_params.setdefault("paper_title", topic or workspace_name or "未命名论文")
    if workspace_description:
        next_params.setdefault("paper_abstract", workspace_description)
    return next_params, None, None


@_resolver("writing")
async def _resolve_writing(
    *,
    params: dict[str, Any],
    workspace_type: str,
    workspace: Any,
    message: str,
    load_latest_draft_summary: Callable[[str], Awaitable[tuple[str | None, str | None]]],
) -> tuple[dict[str, Any], str | None, str | None]:
    next_params = dict(params)
    topic = extract_topic_from_message(message)
    workspace_name = str(getattr(workspace, "name", "") or "").strip()
    next_params.setdefault("paper_title", workspace_name or topic or "未命名论文")
    next_params.setdefault("section_type", extract_section_type(message) or "introduction")
    next_params.setdefault("target_words", extract_target_words(message) or 1200)
    return next_params, None, None


@_resolver("framework_outline")
async def _resolve_framework_outline(
    *,
    params: dict[str, Any],
    workspace_type: str,
    workspace: Any,
    message: str,
    load_latest_draft_summary: Callable[[str], Awaitable[tuple[str | None, str | None]]],
) -> tuple[dict[str, Any], str | None, str | None]:
    next_params = dict(params)
    topic = extract_topic_from_message(message)
    workspace_name = str(getattr(workspace, "name", "") or "").strip()
    workspace_description = str(getattr(workspace, "description", "") or "").strip()
    next_params.setdefault("paper_title", topic or workspace_name or "未命名论文")
    next_params.setdefault(
        "topic",
        topic or workspace_description or workspace_name or "研究主题",
    )
    next_params.setdefault("target_words", extract_target_words(message) or 6000)
    return next_params, None, None


@_resolver("thesis_writing")
async def _resolve_thesis_writing(
    *,
    params: dict[str, Any],
    workspace_type: str,
    workspace: Any,
    message: str,
    load_latest_draft_summary: Callable[[str], Awaitable[tuple[str | None, str | None]]],
) -> tuple[dict[str, Any], str | None, str | None]:
    next_params = dict(params)
    workspace_name = str(getattr(workspace, "name", "") or "").strip()
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
    return next_params, None, None


@_resolver("figure_generation")
async def _resolve_figure_generation(
    *,
    params: dict[str, Any],
    workspace_type: str,
    workspace: Any,
    message: str,
    load_latest_draft_summary: Callable[[str], Awaitable[tuple[str | None, str | None]]],
) -> tuple[dict[str, Any], str | None, str | None]:
    next_params = dict(params)
    topic = extract_topic_from_message(message)
    workspace_name = str(getattr(workspace, "name", "") or "").strip()
    workspace_description = str(getattr(workspace, "description", "") or "").strip()
    description = topic or workspace_description or ""
    if not description or description == workspace_name:
        return (
            next_params,
            '图表生成需要更具体的图意描述，例如\u201c系统架构图\u201d或\u201c实验结果柱状图\u201d。',
            None,
        )
    next_params.setdefault("description", description)
    next_params.setdefault("fig_type", "flowchart")
    return next_params, None, None


@_resolver("compile_export")
async def _resolve_compile_export(
    *,
    params: dict[str, Any],
    workspace_type: str,
    workspace: Any,
    message: str,
    load_latest_draft_summary: Callable[[str], Awaitable[tuple[str | None, str | None]]],
) -> tuple[dict[str, Any], str | None, str | None]:
    next_params = dict(params)
    next_params.setdefault("target", "pdf")
    return next_params, None, None


@_resolver("opening_research")
async def _resolve_opening_research(
    *,
    params: dict[str, Any],
    workspace_type: str,
    workspace: Any,
    message: str,
    load_latest_draft_summary: Callable[[str], Awaitable[tuple[str | None, str | None]]],
) -> tuple[dict[str, Any], str | None, str | None]:
    next_params = dict(params)
    topic = extract_topic_from_message(message)
    workspace_name = str(getattr(workspace, "name", "") or "").strip()
    workspace_description = str(getattr(workspace, "description", "") or "").strip()
    next_params.setdefault(
        "topic",
        topic or workspace_description or workspace_name or "研究主题",
    )
    next_params.setdefault("report_type", "opening_report")
    return next_params, None, None


@_resolver("peer_review")
async def _resolve_peer_review(
    *,
    params: dict[str, Any],
    workspace_type: str,
    workspace: Any,
    message: str,
    load_latest_draft_summary: Callable[[str], Awaitable[tuple[str | None, str | None]]],
) -> tuple[dict[str, Any], str | None, str | None]:
    next_params = dict(params)
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
    return next_params, None, None


@_resolver("journal_recommend")
async def _resolve_journal_recommend(
    *,
    params: dict[str, Any],
    workspace_type: str,
    workspace: Any,
    message: str,
    load_latest_draft_summary: Callable[[str], Awaitable[tuple[str | None, str | None]]],
) -> tuple[dict[str, Any], str | None, str | None]:
    next_params = dict(params)
    topic = extract_topic_from_message(message)
    workspace_name = str(getattr(workspace, "name", "") or "").strip()
    workspace_description = str(getattr(workspace, "description", "") or "").strip()
    title, excerpt = await load_latest_draft_summary(str(getattr(workspace, "id", "")))
    next_params.setdefault("paper_title", title or topic or workspace_name or "未命名论文")
    if excerpt:
        next_params.setdefault("abstract", excerpt)
    elif workspace_description:
        next_params.setdefault("abstract", workspace_description)
    if not next_params.get("abstract"):
        return next_params, "期刊推荐至少需要论文摘要或研究简介。", "framework_outline"
    return next_params, None, None


@_resolver("experiment_design")
async def _resolve_experiment_design(
    *,
    params: dict[str, Any],
    workspace_type: str,
    workspace: Any,
    message: str,
    load_latest_draft_summary: Callable[[str], Awaitable[tuple[str | None, str | None]]],
) -> tuple[dict[str, Any], str | None, str | None]:
    next_params = dict(params)
    topic = extract_topic_from_message(message)
    workspace_name = str(getattr(workspace, "name", "") or "").strip()
    workspace_description = str(getattr(workspace, "description", "") or "").strip()
    objective = topic or workspace_description or workspace_name
    if not objective:
        return next_params, "实验设计需要至少一个研究目标或任务主题。", None
    next_params.setdefault("topic", objective)
    next_params.setdefault("objective", objective)
    return next_params, None, None


@_resolver("proposal_outline")
async def _resolve_proposal_outline(
    *,
    params: dict[str, Any],
    workspace_type: str,
    workspace: Any,
    message: str,
    load_latest_draft_summary: Callable[[str], Awaitable[tuple[str | None, str | None]]],
) -> tuple[dict[str, Any], str | None, str | None]:
    next_params = dict(params)
    topic = extract_topic_from_message(message)
    workspace_name = str(getattr(workspace, "name", "") or "").strip()
    next_params.setdefault("topic", topic or workspace_name or "研究课题")
    next_params.setdefault("period_months", 24)
    return next_params, None, None


@_resolver("background_research")
async def _resolve_background_research(
    *,
    params: dict[str, Any],
    workspace_type: str,
    workspace: Any,
    message: str,
    load_latest_draft_summary: Callable[[str], Awaitable[tuple[str | None, str | None]]],
) -> tuple[dict[str, Any], str | None, str | None]:
    next_params = dict(params)
    topic = extract_topic_from_message(message)
    workspace_name = str(getattr(workspace, "name", "") or "").strip()
    workspace_description = str(getattr(workspace, "description", "") or "").strip()
    next_params.setdefault(
        "keywords",
        topic or workspace_name or workspace_description or "研究主题",
    )
    next_params.setdefault("industry_scope", workspace_description or "相关领域")
    next_params.setdefault("time_range", "近5年")
    return next_params, None, None


@_resolver("copyright_materials")
async def _resolve_copyright_materials(
    *,
    params: dict[str, Any],
    workspace_type: str,
    workspace: Any,
    message: str,
    load_latest_draft_summary: Callable[[str], Awaitable[tuple[str | None, str | None]]],
) -> tuple[dict[str, Any], str | None, str | None]:
    next_params = dict(params)
    workspace_name = str(getattr(workspace, "name", "") or "").strip()
    workspace_description = str(getattr(workspace, "description", "") or "").strip()
    next_params.setdefault("software_name", workspace_name or "待确认软件")
    next_params.setdefault("version", "V1.0")
    if workspace_description:
        next_params.setdefault("highlights", split_keywords(workspace_description))
    return next_params, None, None


@_resolver("technical_description")
async def _resolve_technical_description(
    *,
    params: dict[str, Any],
    workspace_type: str,
    workspace: Any,
    message: str,
    load_latest_draft_summary: Callable[[str], Awaitable[tuple[str | None, str | None]]],
) -> tuple[dict[str, Any], str | None, str | None]:
    next_params = dict(params)
    workspace_name = str(getattr(workspace, "name", "") or "").strip()
    next_params.setdefault("software_name", workspace_name or "待确认软件")
    next_params.setdefault("version", "V1.0")
    next_params.setdefault("deployment_architecture", "B/S架构")
    return next_params, None, None


@_resolver("patent_outline")
async def _resolve_patent_outline(
    *,
    params: dict[str, Any],
    workspace_type: str,
    workspace: Any,
    message: str,
    load_latest_draft_summary: Callable[[str], Awaitable[tuple[str | None, str | None]]],
) -> tuple[dict[str, Any], str | None, str | None]:
    next_params = dict(params)
    topic = extract_topic_from_message(message)
    workspace_name = str(getattr(workspace, "name", "") or "").strip()
    workspace_description = str(getattr(workspace, "description", "") or "").strip()
    innovation_description = topic or workspace_description or workspace_name
    if not innovation_description:
        return next_params, "专利框架至少需要一个创新点描述或发明主题。", None
    next_params.setdefault("innovation_description", innovation_description)
    discipline = str(getattr(workspace, "discipline", "") or "").strip()
    if discipline:
        next_params.setdefault("technical_field", discipline)
    if workspace_description:
        next_params.setdefault("application_scenario", workspace_description)
    return next_params, None, None


@_resolver("prior_art_search")
async def _resolve_prior_art_search(
    *,
    params: dict[str, Any],
    workspace_type: str,
    workspace: Any,
    message: str,
    load_latest_draft_summary: Callable[[str], Awaitable[tuple[str | None, str | None]]],
) -> tuple[dict[str, Any], str | None, str | None]:
    next_params = dict(params)
    topic = extract_topic_from_message(message)
    workspace_name = str(getattr(workspace, "name", "") or "").strip()
    workspace_description = str(getattr(workspace, "description", "") or "").strip()
    keyword_seed = topic or workspace_name or workspace_description
    keyword_list = split_keywords(keyword_seed)
    if not keyword_list:
        return next_params, "现有技术检索需要至少一个关键词或技术主题。", None
    next_params.setdefault("keywords", keyword_list)
    next_params.setdefault("time_range", "近5年")
    return next_params, None, None


async def resolve_feature_params(
    *,
    feature_id: str,
    params: dict[str, Any],
    workspace_type: str,
    workspace: Any,
    message: str,
    load_latest_draft_summary: Callable[[str], Awaitable[tuple[str | None, str | None]]],
) -> tuple[dict[str, Any], str | None, str | None]:
    """Resolve and fill params for a feature by dispatching to its registered resolver."""
    resolver = _PARAM_RESOLVERS.get(feature_id)
    if resolver is None:
        return params, None, None
    return await resolver(
        params=params,
        workspace_type=workspace_type,
        workspace=workspace,
        message=message,
        load_latest_draft_summary=load_latest_draft_summary,
    )
