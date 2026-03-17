"""AcademicMemoryMiddleware -- loads and persists UserKnowledge."""

from __future__ import annotations

import json
import logging
from typing import Any

from src.database.models.knowledge import KnowledgeCategory

logger = logging.getLogger(__name__)

KNOWLEDGE_EXTRACTION_PROMPT = """从以下对话中提取学术相关知识点。返回 JSON 数组:
[
  {
    "category": "preference | knowledge | context | behavior | goal",
    "content": "简洁描述（一句话）",
    "confidence": 0.5-1.0
  }
]

仅提取明确或高度可推断的信息。不要猜测。不确定时不要提取。
category 说明:
- preference: 引用格式偏好、写作风格、语言偏好
- knowledge: 学科知识、专业术语
- context: 当前研究方向、进展状态
- behavior: 操作习惯
- goal: 研究目标、里程碑

对话内容:
{conversation}

仅返回 JSON 数组，不要其他内容。"""


def format_knowledge_for_prompt(knowledge_items: list[dict[str, Any]]) -> str:
    """Format UserKnowledge entries into system prompt injection."""
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
        content = item.get("content", "")
        conf = item.get("confidence", 0.7)
        if cat in sections:
            sections[cat].append(f"- {content} (置信度: {conf:.1f})")

    parts: list[str] = ["<academic_memory>"]
    label_map = {
        "preference": "用户偏好",
        "knowledge": "学科知识",
        "context": "研究上下文",
        "behavior": "行为习惯",
        "goal": "研究目标",
    }
    for cat, label in label_map.items():
        if sections[cat]:
            parts.append(f"\n{label}:")
            parts.extend(sections[cat])
    parts.append("</academic_memory>")
    return "\n".join(parts)


async def load_user_memory(
    user_id: str,
    workspace_id: str | None = None,
    *,
    limit: int = 20,
    min_confidence: float = 0.5,
) -> list[dict[str, Any]]:
    """Load active UserKnowledge from DB."""
    from src.database import get_db_session
    from src.services.knowledge_service import KnowledgeService

    try:
        async with get_db_session() as db:
            service = KnowledgeService(db)
            entries = await service.list_active(
                user_id,
                workspace_context=workspace_id,
                min_confidence=min_confidence,
                limit=limit,
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
                }
                for entry in entries
            ]
    except Exception:
        logger.exception("Failed to load user memory")
        return []


async def extract_and_persist_knowledge(
    user_id: str,
    conversation_text: str,
    *,
    workspace_context: str | None = None,
    source: str | None = None,
) -> int:
    """Extract knowledge from conversation via LLM and persist to DB.

    Returns count of entries persisted.
    """
    from src.database import get_db_session
    from src.services.knowledge_service import KnowledgeService

    try:
        from src.models.factory import create_chat_model

        model = create_chat_model("default", temperature=0.1)
        prompt = KNOWLEDGE_EXTRACTION_PROMPT.format(
            conversation=conversation_text[:4000],
        )
        response = await model.ainvoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)

        # Parse JSON array from response
        items = _parse_knowledge_json(content)
        if not items:
            return 0

        count = 0
        async with get_db_session() as db:
            service = KnowledgeService(db)
            for item in items:
                cat = item.get("category", "")
                text = item.get("content", "")
                conf = float(item.get("confidence", 0.7))
                if not text or conf < 0.5:
                    continue
                try:
                    KnowledgeCategory(cat)  # validate
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
        return count
    except Exception:
        logger.exception("Failed to extract knowledge")
        return 0


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
