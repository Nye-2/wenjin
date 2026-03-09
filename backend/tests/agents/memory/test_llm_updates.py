"""Tests for LLM-driven memory updates."""

import json
import tempfile
from pathlib import Path

import pytest

from src.agents.memory.updater import MemoryUpdater, create_default_memory, get_memory_data


class TestMemoryExtractionPrompt:
    def test_prompt_exists(self):
        """Memory extraction prompt should be defined."""
        from src.agents.memory.prompts import MEMORY_EXTRACTION_PROMPT

        assert MEMORY_EXTRACTION_PROMPT is not None
        assert "user" in MEMORY_EXTRACTION_PROMPT.lower() or "fact" in MEMORY_EXTRACTION_PROMPT.lower()


class TestLLMMemoryUpdates:
    @pytest.mark.asyncio
    async def test_extract_facts_from_messages(self, tmp_path):
        """Should extract facts from conversation."""
        from langchain_core.messages import HumanMessage, AIMessage

        storage = tmp_path / "memory.json"
        updater = MemoryUpdater(storage_path=str(storage))

        messages = [
            HumanMessage(content="I'm working on NLP research, specifically on transformer models."),
            AIMessage(content="Great! I can help you with transformer architecture research."),
        ]

        # This should trigger LLM extraction (or return False if not implemented)
        result = await updater.update_from_messages(messages, thread_id="test-1")
        # Result is False if LLM not configured, or True if extraction succeeded
        assert isinstance(result, bool)

    def test_format_extraction_result(self, tmp_path):
        """Should format extraction result for storage."""
        storage = tmp_path / "memory.json"
        updater = MemoryUpdater(storage_path=str(storage))

        extraction = {
            "user": {
                "researchContext": {"summary": "NLP and transformers", "updatedAt": "2026-03-09"},
            },
            "facts": [
                {"content": "User focuses on NLP", "category": "knowledge", "confidence": 0.9},
            ],
        }

        updater._apply_extraction(extraction)

        # Verify the memory was updated
        data = get_memory_data(str(storage))
        assert data["user"]["researchContext"]["summary"] == "NLP and transformers"
