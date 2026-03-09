"""Persistent memory system - LLM-driven fact extraction and context tracking."""

import json
import logging
import os
import re
from datetime import UTC, datetime
from pathlib import Path

_memory_cache: dict[str, dict] = {}
_memory_mtime: dict[str, float] = {}

logger = logging.getLogger(__name__)

DEFAULT_STORAGE_PATH = "backend/.academiagpt/memory.json"


def create_default_memory() -> dict:
    """Create a default empty memory structure."""
    return {
        "version": "1.0",
        "lastUpdated": datetime.now(UTC).isoformat(),
        "user": {
            "researchContext": {"summary": "", "updatedAt": ""},
            "writingPreferences": {"summary": "", "updatedAt": ""},
            "toolPreferences": {"summary": "", "updatedAt": ""},
        },
        "history": {
            "recentWorkspaces": {"summary": "", "updatedAt": ""},
            "completedResearch": {"summary": "", "updatedAt": ""},
        },
        "facts": [],
    }


def get_memory_data(storage_path: str | None = None) -> dict:
    """Get memory data with caching and file change detection."""
    path = storage_path or DEFAULT_STORAGE_PATH
    cache_key = path

    # Check cache validity via mtime
    if cache_key in _memory_cache:
        try:
            current_mtime = os.path.getmtime(path)
            if current_mtime == _memory_mtime.get(cache_key):
                return _memory_cache[cache_key]
        except OSError:
            pass

    # Load or create
    p = Path(path)
    if p.exists():
        data = json.loads(p.read_text())
    else:
        data = create_default_memory()
        p.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(p, data)

    _memory_cache[cache_key] = data
    try:
        _memory_mtime[cache_key] = os.path.getmtime(path)
    except OSError:
        pass

    return data


def reload_memory_data(storage_path: str | None = None) -> dict:
    """Force reload and clear cache."""
    path = storage_path or DEFAULT_STORAGE_PATH
    _memory_cache.pop(path, None)
    _memory_mtime.pop(path, None)
    return get_memory_data(storage_path=path)


def _atomic_write(path: Path, data: dict) -> None:
    """Write atomically via temp file + rename."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    tmp.replace(path)


class MemoryUpdater:
    """Updates memory from conversations using LLM extraction."""

    def __init__(self, storage_path: str | None = None, model_name: str | None = None):
        self._storage_path = storage_path or DEFAULT_STORAGE_PATH
        self._model_name = model_name

    def format_for_injection(self, max_facts: int = 15) -> str:
        """Format memory data for system prompt injection."""
        data = get_memory_data(storage_path=self._storage_path)

        parts = ["<memory>"]

        # User context
        for key in ["researchContext", "writingPreferences", "toolPreferences"]:
            ctx = data.get("user", {}).get(key, {})
            summary = ctx.get("summary", "")
            if summary:
                parts.append(f"[{key}] {summary}")

        # Facts (top N by confidence)
        facts = sorted(data.get("facts", []), key=lambda f: f.get("confidence", 0), reverse=True)
        for fact in facts[:max_facts]:
            parts.append(f"- {fact['content']}")

        parts.append("</memory>")
        return "\n".join(parts)

    async def update_from_messages(self, messages: list, thread_id: str | None = None) -> bool:
        """Update memory from a conversation (async LLM call).

        Returns True if extraction succeeded, False if LLM not configured or failed.
        """
        if not self._model_name:
            logger.debug("No model configured for memory extraction")
            return False

        try:
            conversation = self._format_conversation(messages)
            extraction = await self._run_extraction(conversation)
            if extraction:
                self._apply_extraction(extraction)
                return True
        except Exception as e:
            logger.warning(f"Memory extraction failed: {e}")

        return False

    def _format_conversation(self, messages: list) -> str:
        """Format messages for LLM extraction."""
        lines = []
        for msg in messages:
            role = getattr(msg, "type", "unknown")
            if role == "human":
                role = "User"
            elif role == "ai":
                role = "Assistant"
            content = getattr(msg, "content", str(msg))
            lines.append(f"{role}: {content}")
        return "\n".join(lines)

    async def _run_extraction(self, conversation: str) -> dict | None:
        """Run LLM extraction and parse JSON result."""
        try:
            from langchain_core.language_models.chat_models import BaseChatModel
            from langchain_core.messages import HumanMessage, SystemMessage

            from src.config import get_settings

            settings = get_settings()
            model_name = self._model_name or settings.model_name

            # Import the appropriate chat model based on provider
            if settings.provider == "openai":
                from langchain_openai import ChatOpenAI

                llm: BaseChatModel = ChatOpenAI(model=model_name, temperature=0)
            elif settings.provider == "anthropic":
                from langchain_anthropic import ChatAnthropic

                llm = ChatAnthropic(model=model_name, temperature=0)
            else:
                logger.warning(f"Unsupported provider for memory extraction: {settings.provider}")
                return None

            from src.agents.memory.prompts import MEMORY_EXTRACTION_PROMPT

            system_msg = SystemMessage(content=MEMORY_EXTRACTION_PROMPT)
            user_msg = HumanMessage(content=f"Conversation to analyze:\n\n{conversation}")

            response = await llm.ainvoke([system_msg, user_msg])
            content = response.content

            # Extract JSON from response (handle markdown code blocks)
            json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
            if json_match:
                content = json_match.group(1)

            return json.loads(content)

        except Exception as e:
            logger.warning(f"LLM extraction failed: {e}")
            return None

    def _apply_extraction(self, extraction: dict) -> None:
        """Apply extraction result to storage."""
        data = get_memory_data(storage_path=self._storage_path)
        today = datetime.now(UTC).isoformat()

        # Update user context fields
        user_extraction = extraction.get("user", {})
        for key in ["researchContext", "writingPreferences", "toolPreferences"]:
            if key in user_extraction:
                ctx = user_extraction[key]
                if ctx.get("summary"):
                    data["user"][key] = {
                        "summary": ctx["summary"],
                        "updatedAt": ctx.get("updatedAt", today),
                    }

        # Add new facts (avoid duplicates by content)
        existing_contents = {f.get("content") for f in data.get("facts", [])}
        for fact in extraction.get("facts", []):
            content = fact.get("content")
            if content and content not in existing_contents:
                data["facts"].append({
                    "id": f"fact-{len(data['facts']) + 1}",
                    "content": content,
                    "category": fact.get("category", "knowledge"),
                    "confidence": fact.get("confidence", 0.5),
                })
                existing_contents.add(content)

        data["lastUpdated"] = today
        _atomic_write(Path(self._storage_path), data)

        # Invalidate cache
        _memory_cache.pop(self._storage_path, None)
        _memory_mtime.pop(self._storage_path, None)
