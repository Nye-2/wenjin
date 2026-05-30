"""Memory compaction — merge, deduplicate, and archive stale knowledge."""

from __future__ import annotations

import json
import logging
from typing import Any, cast

from src.dataservice_client.contracts.knowledge import (
    KNOWLEDGE_CATEGORY_CONTEXT,
    KNOWLEDGE_CATEGORY_PREFERENCE,
    normalize_knowledge_category,
)
from src.dataservice_client.provider import dataservice_client
from src.services.knowledge_service import KnowledgeService

logger = logging.getLogger(__name__)

COMPACT_PROMPT = """你是问津的长期记忆压缩系统。将以下用户知识条目合并、去重、归纳为更精炼且可长期使用的集合。

当前知识条目:
{entries_json}

要求:
1. 合并语义相似的条目，保留高置信度值和关键限定条件
2. 将多个相关上下文条目归纳为一条阶段性摘要，但不要丢失当前研究方向、目标和约束
3. 移除一次性任务状态、过时条目、重复条目和明显矛盾的低置信度条目
4. 保留所有偏好类条目（这些通常不过时）；如果偏好互相冲突，保留最新且更具体的一条
5. 不新增输入中没有的信息，不推测用户身份、机构、成果或截止日期

返回 JSON:
{{
  "compacted": [
    {{"category": "...", "content": "...", "confidence": 0.0-1.0}}
  ],
  "summary": "一段话描述用户当前研究进度全景"
}}

仅返回有效 JSON，不要 Markdown 代码块、注释或其他内容。"""


def _coerce_confidence(value: Any, default: float = 0.7) -> float:
    """Parse and clamp confidence into [0.0, 1.0]."""
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = default
    return min(1.0, max(0.0, confidence))


def _load_memory_config() -> Any:
    """Load memory config without coupling compaction to runtime service code."""
    try:
        from src.config.config_loader import MemoryConfig, get_app_config

        return getattr(get_app_config(), "memory", None) or MemoryConfig()
    except Exception:
        logger.exception("Failed to load memory config for compaction")
        from src.config.config_loader import MemoryConfig

        return MemoryConfig()


def _normalize_compacted_items(raw_items: Any) -> list[dict[str, Any]]:
    """Validate and normalize LLM-produced compacted memory items."""
    if not isinstance(raw_items, list):
        return []

    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        cat = str(item.get("category", "")).strip()
        text = str(item.get("content", "")).strip()
        if not text:
            continue
        try:
            category = normalize_knowledge_category(cat)
        except ValueError:
            continue
        key = (category, text)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(
            {
                "category": category,
                "content": text,
                "confidence": _coerce_confidence(item.get("confidence", 0.7)),
            }
        )
    return normalized


def _with_preserved_preferences(
    entries: list[Any],
    compacted_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Preserve preference memory deterministically instead of trusting the LLM."""
    result = list(compacted_items)
    seen = {
        (item["category"], item["content"])
        for item in result
    }
    for entry in entries:
        if normalize_knowledge_category(entry.category) != KNOWLEDGE_CATEGORY_PREFERENCE:
            continue
        key = (KNOWLEDGE_CATEGORY_PREFERENCE, entry.content)
        if key in seen:
            continue
        seen.add(key)
        result.append(
            {
                "category": KNOWLEDGE_CATEGORY_PREFERENCE,
                "content": entry.content,
                "confidence": _coerce_confidence(entry.confidence),
            }
        )
    return result


async def compact_user_memory(
    user_id: str,
    *,
    workspace_context: str | None = None,
) -> dict[str, Any]:
    """Compact user memory entries.

    Returns:
        {"compacted_count": int, "archived_count": int, "summary": str}
    """
    config = _load_memory_config()
    max_facts = max(10, int(getattr(config, "max_facts", 100) or 100))
    read_limit = max(100, max_facts * 2)

    async with dataservice_client() as client:
        service = KnowledgeService(dataservice=client)
        entries = await service.list_active(
            user_id,
            workspace_context=workspace_context,
            include_global=False,
            min_confidence=0.0,
            limit=read_limit,
        )

        if len(entries) < 10:
            return {"compacted_count": 0, "archived_count": 0, "summary": ""}

        # Prepare entries for LLM
        entries_data = [
            {
                "category": (
                    e.category.value
                    if hasattr(e.category, "value")
                    else str(e.category)
                ),
                "content": e.content,
                "confidence": e.confidence,
            }
            for e in entries
        ]

        try:
            from src.models.factory import create_chat_model
            from src.models.router import route_model

            model_id = route_model(
                requested_model=getattr(config, "model_name", None),
                preferred_categories=("llm",),
                allowed_categories=("llm",),
                require_tools=False,
            )
            model = create_chat_model(model_id, temperature=0.1)
            prompt = COMPACT_PROMPT.format(
                entries_json=json.dumps(entries_data, ensure_ascii=False)
            )
            response = await model.ainvoke(prompt)
            content = response.content if hasattr(response, "content") else str(response)
            result = _parse_compact_result(cast(str, content))
        except Exception:
            logger.exception("LLM compaction failed")
            raise

        compacted_items = _with_preserved_preferences(
            entries,
            _normalize_compacted_items(result.get("compacted", [])),
        )
        summary = str(result.get("summary") or "").strip()
        if not compacted_items and len(summary) < 20:
            logger.warning(
                "Skipping memory compaction for user %s scope=%s because LLM "
                "returned no valid compacted items and no useful summary",
                user_id,
                workspace_context,
            )
            return {
                "compacted_count": 0,
                "archived_count": 0,
                "summary": "",
                "skipped_reason": "empty_compaction_result",
            }

        # Deactivate all current entries through DataService.
        for entry in entries:
            await service.update(entry.id, is_active=False)

        # Write compacted entries
        count = 0
        for item in compacted_items:
            await service.upsert(
                user_id,
                item["category"],
                item["content"],
                confidence=item["confidence"],
                source="compaction",
                workspace_context=workspace_context,
            )
            count += 1

        # Add compaction summary
        if summary:
            await service.upsert(
                user_id,
                KNOWLEDGE_CATEGORY_CONTEXT,
                summary,
                confidence=0.9,
                source="compaction_summary",
                workspace_context=workspace_context,
            )

        return {
            "compacted_count": count,
            "archived_count": len(entries),
            "summary": summary,
        }


def _parse_compact_result(text: str) -> dict[str, Any]:
    """Parse LLM compaction response."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    return {"compacted": [], "summary": ""}
