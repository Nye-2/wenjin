"""Memory compaction — merge, deduplicate, and archive stale knowledge."""

from __future__ import annotations

import json
import logging
from typing import Any

from src.database.models.knowledge import KnowledgeCategory

logger = logging.getLogger(__name__)

COMPACT_PROMPT = """你是一个记忆压缩系统。将以下用户知识条目合并、去重、归纳为更精炼的集合。

当前知识条目:
{entries_json}

要求:
1. 合并语义相似的条目，保留高置信度值
2. 将多个相关上下文条目归纳为一条阶段性摘要
3. 移除过时或矛盾的条目
4. 保留所有偏好类条目（这些通常不过时）

返回 JSON:
{{
  "compacted": [
    {{"category": "...", "content": "...", "confidence": 0.0-1.0}}
  ],
  "summary": "一段话描述用户当前研究进度全景"
}}

仅返回 JSON，不要其他内容。"""


def _coerce_confidence(value: Any, default: float = 0.7) -> float:
    """Parse and clamp confidence into [0.0, 1.0]."""
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = default
    return min(1.0, max(0.0, confidence))


async def compact_user_memory(
    user_id: str,
    *,
    workspace_context: str | None = None,
) -> dict[str, Any]:
    """Compact user memory entries.

    Returns:
        {"compacted_count": int, "archived_count": int, "summary": str}
    """
    from src.database import get_db_session
    from src.services.knowledge_service import KnowledgeService

    async with get_db_session() as db:
        service = KnowledgeService(db)
        entries = await service.list_active(user_id, min_confidence=0.0, limit=100)

        if len(entries) < 10:
            return {"compacted_count": 0, "archived_count": 0, "summary": ""}

        # Prepare entries for LLM
        entries_data = [
            {"category": e.category.value if hasattr(e.category, "value") else str(e.category),
             "content": e.content,
             "confidence": e.confidence}
            for e in entries
        ]

        try:
            from src.models.factory import create_chat_model
            from src.models.router import route_model

            model_id = route_model(
                preferred_categories=("llm",),
                allowed_categories=("llm",),
                require_tools=False,
            )
            model = create_chat_model(model_id, temperature=0.1)
            prompt = COMPACT_PROMPT.format(entries_json=json.dumps(entries_data, ensure_ascii=False))
            response = await model.ainvoke(prompt)
            content = response.content if hasattr(response, "content") else str(response)
            result = _parse_compact_result(content)
        except Exception:
            logger.exception("LLM compaction failed")
            raise

        # Deactivate all current entries
        for entry in entries:
            entry.is_active = False
        await db.flush()

        # Write compacted entries
        compacted_items = result.get("compacted", [])
        count = 0
        for item in compacted_items:
            if not isinstance(item, dict):
                continue
            cat = str(item.get("category", "")).strip()
            text = str(item.get("content", "")).strip()
            conf = _coerce_confidence(item.get("confidence", 0.7))
            if not text:
                continue
            try:
                KnowledgeCategory(cat)
            except ValueError:
                continue
            await service.upsert(
                user_id, cat, text,
                confidence=conf,
                source="compaction",
                workspace_context=workspace_context,
            )
            count += 1

        # Add compaction summary
        summary = result.get("summary", "")
        if summary:
            await service.upsert(
                user_id,
                KnowledgeCategory.CONTEXT,
                summary,
                confidence=0.9,
                source="compaction_summary",
                workspace_context=workspace_context,
            )

        await db.commit()
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
