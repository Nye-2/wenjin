"""Canonical user-memory runtime for long-term academic memory."""

from __future__ import annotations

import json
import logging
import math
import re
from collections import Counter
from typing import Any

from src.database.models.knowledge import KnowledgeCategory

logger = logging.getLogger(__name__)
_SIMILARITY_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")
_SIMILARITY_STOPWORDS = {"user", "assistant"}

KNOWLEDGE_EXTRACTION_PROMPT = """从以下对话中提取对未来协作有价值的学术相关知识点。返回 JSON 数组:
[
  {{
    "category": "preference | knowledge | context | behavior | goal",
    "content": "简洁但完整的描述（一到两句话，包含关键细节）",
    "confidence": 0.5-1.0
  }}
]

提取原则：
- 只提取明确表述或高度可推断的信息，不要猜测
- 优先提取对后续工作有指导价值的信息
- 合并相近的知识点，避免重复

各类别提取指引：
- preference（偏好）：引用格式（APA/IEEE/GB-T 等）、写作语言、排版要求、导师/评审的特殊要求、偏好的论文结构
- knowledge（知识）：用户的专业领域、掌握的方法论、熟悉的理论框架、专业术语使用习惯
- context（上下文）：当前研究的具体问题、进展阶段、遇到的困难、已完成的工作
- behavior（行为）：喜欢的交互方式（详细 vs 简洁）、是否需要中英对照、是否偏好先看大纲再写细节
- goal（目标）：论文投稿目标期刊、答辩时间、基金申请截止日期、预期成果

示例：
- {{"category": "preference", "content": "用户要求参考文献使用 IEEE 格式，且中英文文献分开排列", "confidence": 0.95}}
- {{"category": "context", "content": "用户正在研究基于 Transformer 的图像分割方法，目前在实验阶段", "confidence": 0.9}}
- {{"category": "goal", "content": "计划在 2026 年 6 月前完成硕士论文初稿", "confidence": 0.85}}

对话内容:
{conversation}

仅返回 JSON 数组，不要其他内容。"""


def _load_memory_config():
    """Load app memory config with safe defaults."""
    from src.config.config_loader import MemoryConfig, get_app_config

    try:
        app_config = get_app_config()
        memory_config = getattr(app_config, "memory", None)
        if memory_config is not None:
            return memory_config
    except Exception:
        logger.exception("Failed to load memory config, using defaults")
    return MemoryConfig()


def _coerce_confidence(value: Any, default: float = 0.7) -> float:
    """Parse and clamp confidence into [0.0, 1.0]."""
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = default
    return min(1.0, max(0.0, confidence))


def _parse_knowledge_json(text: str) -> list[dict[str, Any]]:
    """Parse JSON array from LLM response, handling markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(
            lines[1:-1] if lines[-1].strip() == "```" else lines[1:],
        )
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        pass
    return []


def _format_memory_line(content: str, confidence: float) -> str:
    return f"- {content} (置信度: {confidence:.1f})"


def _count_tokens(text: str) -> int:
    """Count prompt tokens using the same tokenizer family as thread models."""
    normalized = str(text or "").strip()
    if not normalized:
        return 0

    try:
        import tiktoken

        encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(normalized))
    except Exception:
        # Fallback keeps the system usable even if tokenizer loading fails.
        return max(1, len(normalized) // 4)


def _normalize_similarity_tokens(text: str) -> list[str]:
    """Normalize text into lightweight lexical tokens for relevance scoring."""
    normalized = str(text or "").lower()
    tokens: list[str] = []
    for token in _SIMILARITY_TOKEN_RE.findall(normalized):
        value = token.strip()
        if not value or value in _SIMILARITY_STOPWORDS:
            continue
        tokens.append(value)
    return tokens


def _similarity_score(current_context: str, content: str) -> float:
    """Compute a lightweight cosine similarity between current context and memory."""
    context_tokens = Counter(_normalize_similarity_tokens(current_context))
    content_tokens = Counter(_normalize_similarity_tokens(content))
    if not context_tokens or not content_tokens:
        return 0.0

    overlap = set(context_tokens) & set(content_tokens)
    if not overlap:
        return 0.0

    numerator = sum(context_tokens[token] * content_tokens[token] for token in overlap)
    context_norm = math.sqrt(sum(value * value for value in context_tokens.values()))
    content_norm = math.sqrt(sum(value * value for value in content_tokens.values()))
    if context_norm == 0 or content_norm == 0:
        return 0.0
    return numerator / (context_norm * content_norm)


def _rank_knowledge_items(
    knowledge_items: list[dict[str, Any]],
    *,
    current_context: str | None = None,
    workspace_id: str | None = None,
    similarity_weight: float = 0.6,
    confidence_weight: float = 0.4,
) -> list[dict[str, Any]]:
    """Rank memory items by workspace match, contextual similarity and confidence."""
    if not knowledge_items:
        return []

    normalized_similarity_weight = max(0.0, float(similarity_weight))
    normalized_confidence_weight = max(0.0, float(confidence_weight))
    total_weight = normalized_similarity_weight + normalized_confidence_weight
    if total_weight <= 0:
        normalized_similarity_weight = 0.6
        normalized_confidence_weight = 0.4
        total_weight = 1.0

    similarity_ratio = normalized_similarity_weight / total_weight
    confidence_ratio = normalized_confidence_weight / total_weight
    normalized_context = " ".join(str(current_context or "").split())

    def _score(item: dict[str, Any]) -> tuple[float, float, float]:
        confidence = _coerce_confidence(item.get("confidence", 0.7))
        similarity = (
            _similarity_score(normalized_context, str(item.get("content") or ""))
            if normalized_context
            else 0.0
        )
        workspace_match = (
            workspace_id is not None
            and item.get("workspace_context") == workspace_id
        )
        combined = similarity * similarity_ratio + confidence * confidence_ratio
        if workspace_match:
            combined += 0.15
        return (
            combined,
            similarity,
            confidence,
        )

    return sorted(
        knowledge_items,
        key=lambda item: _score(item),
        reverse=True,
    )


def format_knowledge_for_prompt(
    knowledge_items: list[dict[str, Any]],
    *,
    max_chars: int | None = None,
    max_tokens: int | None = None,
) -> str:
    """Format knowledge entries into a compact prompt block."""
    if not knowledge_items:
        return ""

    sections: dict[str, list[str]] = {
        "preference": [],
        "knowledge": [],
        "context": [],
        "behavior": [],
        "goal": [],
    }
    for item in knowledge_items:
        cat = item.get("category", "context")
        content = str(item.get("content", "")).strip()
        conf = _coerce_confidence(item.get("confidence", 0.7))
        if cat in sections and content:
            sections[cat].append(_format_memory_line(content, conf))

    label_map = {
        "preference": "用户偏好",
        "knowledge": "学科知识",
        "context": "研究上下文",
        "behavior": "行为习惯",
        "goal": "研究目标",
    }

    def _fits_budget(parts: list[str], candidate: str | None = None) -> bool:
        candidate_parts = [*parts]
        if candidate is not None:
            candidate_parts.append(candidate)
        candidate_parts.append("</academic_memory>")
        rendered = "\n".join(candidate_parts)
        if max_tokens is not None and _count_tokens(rendered) > max_tokens:
            return False
        if max_chars is not None and len(rendered) > max_chars:
            return False
        return True

    parts: list[str] = ["<academic_memory>"]
    truncated = False

    for cat, label in label_map.items():
        if not sections[cat]:
            continue

        header = f"\n{label}:"
        if not _fits_budget(parts, header):
            truncated = True
            break
        parts.append(header)

        for line in sections[cat]:
            if not _fits_budget(parts, line):
                truncated = True
                break
            parts.append(line)

        if truncated:
            break

    if truncated and _fits_budget(parts, "- ..."):
        parts.append("- ...")

    parts.append("</academic_memory>")
    return "\n".join(parts)


async def load_user_memory(
    user_id: str,
    workspace_id: str | None = None,
    *,
    limit: int | None = None,
    min_confidence: float | None = None,
) -> list[dict[str, Any]]:
    """Load active user memory entries from DB."""
    from src.database import get_db_session
    from src.services.knowledge_service import KnowledgeService

    config = _load_memory_config()
    effective_limit = limit or getattr(config, "max_facts", 20)
    effective_min_confidence = (
        min_confidence
        if min_confidence is not None
        else getattr(config, "fact_confidence_threshold", 0.7)
    )

    try:
        async with get_db_session() as db:
            service = KnowledgeService(db)
            entries = await service.list_active(
                user_id,
                workspace_context=workspace_id,
                min_confidence=effective_min_confidence,
                limit=effective_limit,
            )
            return [
                {
                    "category": (
                        entry.category.value
                        if hasattr(entry.category, "value")
                        else str(entry.category)
                    ),
                    "content": entry.content,
                    "confidence": entry.confidence,
                    "workspace_context": entry.workspace_context,
                }
                for entry in entries
            ]
    except Exception:
        logger.exception("Failed to load user memory")
        return []


async def build_memory_context(
    user_id: str | None,
    workspace_id: str | None = None,
    *,
    current_context: str | None = None,
) -> str:
    """Load and format user memory for prompt injection."""
    if not user_id:
        return ""

    config = _load_memory_config()
    if not getattr(config, "enabled", False):
        return ""
    if not getattr(config, "injection_enabled", True):
        return ""

    items = await load_user_memory(user_id, workspace_id)
    if not items:
        return ""

    ranked_items = _rank_knowledge_items(
        items,
        current_context=current_context,
        workspace_id=workspace_id,
        similarity_weight=float(getattr(config, "similarity_weight", 0.6) or 0.6),
        confidence_weight=float(getattr(config, "confidence_weight", 0.4) or 0.4),
    )
    max_tokens = max(64, int(getattr(config, "max_injection_tokens", 2000) or 2000))
    return format_knowledge_for_prompt(ranked_items, max_tokens=max_tokens)


async def _maybe_compact_memory(
    user_id: str,
    *,
    workspace_context: str | None = None,
) -> None:
    """Compact memory when active entries exceed the configured ceiling."""
    from src.database import get_db_session
    from src.services.knowledge_service import KnowledgeService
    from src.services.memory_compaction import compact_user_memory

    config = _load_memory_config()
    max_facts = int(getattr(config, "max_facts", 100) or 100)
    if max_facts <= 0:
        return

    try:
        async with get_db_session() as db:
            service = KnowledgeService(db)
            active_count = await service.count_active(user_id)
        if active_count <= max_facts:
            return
        await compact_user_memory(user_id, workspace_context=workspace_context)
    except Exception:
        logger.exception("Failed to compact user memory")


async def extract_and_persist_knowledge(
    user_id: str,
    conversation_text: str,
    *,
    workspace_context: str | None = None,
    source: str | None = None,
) -> int:
    """Extract knowledge from text via LLM and persist to DB."""
    from src.database import get_db_session
    from src.services.knowledge_service import KnowledgeService

    config = _load_memory_config()
    if not getattr(config, "enabled", False):
        return 0

    try:
        from src.models.factory import create_chat_model
        from src.models.router import route_model

        model_id = route_model(
            preferred_categories=("llm",),
            allowed_categories=("llm",),
            require_tools=False,
        )
        model = create_chat_model(model_id, temperature=0.1)
        prompt = KNOWLEDGE_EXTRACTION_PROMPT.format(
            conversation=conversation_text[:4000],
        )
        response = await model.ainvoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)

        items = _parse_knowledge_json(content)
        if not items:
            return 0

        threshold = float(getattr(config, "fact_confidence_threshold", 0.7))
        count = 0
        async with get_db_session() as db:
            service = KnowledgeService(db)
            for item in items:
                if not isinstance(item, dict):
                    continue
                cat = str(item.get("category", "")).strip()
                text = str(item.get("content", "")).strip()
                conf = _coerce_confidence(item.get("confidence", 0.7))
                if not text or conf < threshold:
                    continue
                try:
                    KnowledgeCategory(cat)
                except ValueError:
                    continue
                await service.upsert(
                    user_id,
                    cat,
                    text,
                    confidence=conf,
                    source=source,
                    workspace_context=workspace_context,
                )
                count += 1
            await db.commit()

        if count > 0:
            await _maybe_compact_memory(
                user_id,
                workspace_context=workspace_context,
            )
        return count
    except Exception:
        logger.exception("Failed to extract knowledge")
        return 0
