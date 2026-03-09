"""Tests for persistent memory system."""

import json
import tempfile
from pathlib import Path

import pytest

from src.agents.memory.updater import (
    get_memory_data,
    reload_memory_data,
    MemoryUpdater,
    create_default_memory,
)


class TestMemoryData:
    def test_default_memory_structure(self):
        data = create_default_memory()
        assert "version" in data
        assert "user" in data
        assert "history" in data
        assert "facts" in data
        assert isinstance(data["facts"], list)

    def test_get_memory_creates_file(self, tmp_path):
        storage = str(tmp_path / "memory.json")
        data = get_memory_data(storage_path=storage)
        assert data is not None
        assert Path(storage).exists()

    def test_get_memory_reads_existing(self, tmp_path):
        storage = tmp_path / "memory.json"
        existing = create_default_memory()
        existing["facts"].append({"id": "f1", "content": "test fact", "category": "knowledge", "confidence": 0.9})
        storage.write_text(json.dumps(existing))

        data = get_memory_data(storage_path=str(storage))
        assert len(data["facts"]) == 1
        assert data["facts"][0]["content"] == "test fact"

    def test_reload_clears_cache(self, tmp_path):
        storage = str(tmp_path / "memory.json")
        data1 = get_memory_data(storage_path=storage)
        data2 = reload_memory_data(storage_path=storage)
        assert data2 is not None


class TestMemoryUpdater:
    def test_init(self):
        updater = MemoryUpdater()
        assert updater is not None

    def test_format_memory_for_injection(self, tmp_path):
        storage = tmp_path / "memory.json"
        mem = create_default_memory()
        mem["user"]["researchContext"] = {"summary": "Focuses on NLP", "updatedAt": "2026-03-09"}
        mem["facts"] = [
            {"id": "f1", "content": "User studies NLP", "category": "knowledge", "confidence": 0.95},
        ]
        storage.write_text(json.dumps(mem))

        updater = MemoryUpdater(storage_path=str(storage))
        injection = updater.format_for_injection()
        assert "NLP" in injection
