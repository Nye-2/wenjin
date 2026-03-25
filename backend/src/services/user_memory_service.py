"""Canonical user-memory runtime for long-term academic memory."""

from __future__ import annotations

import json
import logging
from typing import Any

from src.database.models.knowledge import KnowledgeCategory

logger = logging.getLogger(__name__)

KNOWLEDGE_EXTRACTION_PROMPT = """从以下对话中提取学术相关知识点。返回 JSON 数组:
[
  {{
    "category": "preference | knowledge | context | behavior | goal",
    "content": "简洁描述（一句话）",
    "confidence": 0.5-1.0
  }}
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


def format_knowledge_for_prompt(
    knowledge_items: list[dict[str, Any]],
    *,
    max_chars: int | None = None,
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

    parts: list[str] = ["<academic_memory>"]
    current_chars = len(parts[0]) + len("</academic_memory>")
    truncated = False

    for cat, label in label_map.items():
        if not sections[cat]:
            continue

        header = f"\n{label}:"
        if max_chars is not None and current_chars + len(header) > max_chars:
            truncated = True
            break
        parts.append(header)
        current_chars += len(header)

        for line in sections[cat]:
            if max_chars is not None and current_chars + len(line) + 1 > max_chars:
                truncated = True
                break
            parts.append(line)
            current_chars += len(line) + 1

        if truncated:
            break

    if truncated:
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
    effective_limit = limit or min(getattr(config, "max_facts", 100), 20)
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

    max_chars = max(400, int(getattr(config, "max_injection_tokens", 2000)) * 4)
    return format_knowledge_for_prompt(items, max_chars=max_chars)


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

        try:
            model_id = route_model(
                preferred_categories=("utility", "gen", "tool"),
                allowed_categories=("utility", "gen", "tool"),
                require_tools=False,
            )
        except Exception:
            model_id = "default"
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

