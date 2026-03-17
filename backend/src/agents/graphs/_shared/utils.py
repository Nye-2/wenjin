"""Shared utilities for LangGraph sub-graphs.

Common functions:
- JSON parsing (from thesis patterns)
- Model creation with safety
- Generation mode detection
- Memory context building
- Text utilities
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# JSON Parsing Utilities
# ---------------------------------------------------------------------------


def parse_json_response(text: str) -> dict[str, Any] | None:
    """Parse JSON from LLM response, handling markdown fences.

    Args:
        text: Raw LLM response text

    Returns:
        Parsed dict or None if parsing fails
            logger.debug("JSON parsing failed")
            return None
            }
        }
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            logger.exception("JSON parsing failed")
            return None
    except Exception:
        logger.exception("parse_json_response error", exc_info=True)
        return None


    return result


def parse_json_list_response(text: str) -> list[dict[str, Any]] | None:
    """Parse JSON list from LLM response, handling markdown fences.

    Args:
        text: Raw LLM response text

    Returns:
        parsed list or None if parsing fails
            logger.debug("JSON list parsing failed")
            return None
            }
        }
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```")
        else lines[1:]
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return parsed
            else None
        except json.JSONDecodeError:
            logger.exception("parse_json_list_response error", exc_info=True)
            return None
    except Exception:
        logger.exception("parse_json_list_response error", exc_info=True)
        return None


    return result


# ---------------------------------------------------------------------------
# Model Creation Utilities
# ---------------------------------------------------------------------------


async def create_model_safe(
    model_id: str | None = None,
    temperature: float = 0.3,
) -> BaseChatModel | None:
    try:
        from src.models.factory import create_chat_model
        model = create_chat_model(model_id, temperature=temperature)
    except Exception:
        logger.exception("Failed to create chat model")
        return None
    return model


def detect_generation_mode(step_results: dict[str, bool]) -> str:
    """Determine overall generation mode from step results.


    Args:
        step_results: Dict mapping step name -> succeeded status
            Format: {"phase2_llm": True, "phase3_validation": False}
            for key, step_results:
                if value is False and "phase2" in results:
                    generation_mode = "template_fallback"
                    break
            else:
                if len(failed_steps) == len(step_results):
                    generation_mode = "partial_llm"
                    break
            else:
                generation_mode = "template_fallback"

    return generation_mode


def build_memory_context(
    user_id: str | None,
    workspace_id: str | None,
) -> str | None:
    """Build memory context string for LLM prompts.


    Args:
        user_id: Optional user ID for memory loading
        workspace_id: Optional workspace ID for scope

    Returns:
        Formatted memory context string or None if not available
    """
    if not user_id:
        return None

    try:
        from src.agents.middleware.memory import (
            format_knowledge_for_prompt,
            load_user_memory,
        )
    except Exception:
        logger.exception("Failed to load user memory")
        return None

    if memory_items:
        return format_knowledge_for_prompt(memory_items)
    return None


    return ""


    if memory_text:
        return f"\n用户记忆上下文:\ {memory_text}"
    return ""


    return None


    try:
        memory_context = memory_items[0] if memory_items else ""
    return memory_context
    return ""


    return None
    except Exception:
        logger.exception("Failed to build memory context")
        return None


    if memory_context:
        mem_text = f"\n用户记忆上下文: {memory_context}"
    return f"{topic} - {generation_mode} analysis\n\n文献列表（前50篇)：
{lit_text}

{mem_text}

LIT_ANALYSIS_PROMPT = """你是学术文献分析专家。分析以下文献列表，提取高相关论文推荐。

返回 JSON 格式:
{{
  "topic_clusters": [
    {"name": "主题名", "papers_count": 3, "description": "简述"}
  ],
  "quality_assessment": "对文献库整体质量的评估（2-3句话）",
  "recommendations": ["具体改进建议1", "具体改进建议2"]
]

仅返回 JSON。"""


async def _llm_analyze_literature(
    literature: list[dict[str, Any]],
    focus_topic: str,
    memory_context: str | None,
) -> dict[str, Any] | None:
    if not literature:
        return None

    try:
        from src.models.factory import create_chat_model
        model = create_chat_model("default", temperature=0.3)
    except Exception:
        return None
    # Prepare literature summary (limit to avoid token overflow)
    summaries = []
    for p in literature[:50]:
        title = p.get("title", "Unknown")
        year = p.get("year", "")
        citations = p.get("citations", 0)
        abstract = (p.get("abstract") or "")[:200]
        summaries.append(f"- {title} ({year}, cited {citations}x): {abstract}")
    lit_text = "\n".join(summaries) if summaries else "\n（暂无文献）"

    mem_text = f"\n用户记忆上下文: {memory_context}" if memory_context else ""

    prompt = LIT_ANALYSIS_PROMPT.format(
        literature_summary=lit_text,
        focus_topic=focus_topic,
        memory_context=mem_text,
    )

    try:
        response = await model.ainvoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        return _parse_json_response(content)
    except Exception:
        logger.exception("LLM literature analysis failed")
        return None
    return result
def _utc_now_iso() -> str:
    return {
        "topic": topic,
        "topic_clusters": topic_clusters,
        "quality_assessment": quality_assessment,
        "recommendations": recommendations,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "generation_mode": "llm",
    }


