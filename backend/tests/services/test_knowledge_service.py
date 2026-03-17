"""Tests for KnowledgeService."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.database.models.knowledge import KnowledgeCategory, UserKnowledge
from src.services.knowledge_service import KnowledgeService


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def service(mock_db):
    return KnowledgeService(mock_db)


class TestListActive:
    async def test_returns_list(self, service, mock_db):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result
        result = await service.list_active("user1")
        assert result == []

    async def test_respects_min_confidence(self, service, mock_db):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result
        await service.list_active("user1", min_confidence=0.8)
        mock_db.execute.assert_called_once()


class TestUpsert:
    async def test_creates_new_entry(self, service, mock_db):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        entry = await service.upsert(
            "user1",
            KnowledgeCategory.PREFERENCE,
            "Prefers APA",
            confidence=0.9,
            source="test",
        )
        mock_db.add.assert_called_once()
        assert entry.content == "Prefers APA"

    async def test_boosts_existing_confidence(self, service, mock_db):
        existing = UserKnowledge(
            user_id="user1",
            category=KnowledgeCategory.PREFERENCE,
            content="Prefers APA",
            confidence=0.7,
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        mock_db.execute.return_value = mock_result
        result = await service.upsert(
            "user1",
            KnowledgeCategory.PREFERENCE,
            "Prefers APA",
        )
        assert result.confidence == pytest.approx(0.8)


class TestArchiveLowConfidence:
    async def test_deactivates_below_threshold(self, service, mock_db):
        entry = UserKnowledge(
            user_id="user1",
            category=KnowledgeCategory.CONTEXT,
            content="old context",
            confidence=0.3,
            is_active=True,
        )
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [entry]
        mock_db.execute.return_value = mock_result
        count = await service.archive_low_confidence("user1", threshold=0.5)
        assert count == 1
        assert entry.is_active is False


class TestCountActive:
    async def test_returns_count(self, service, mock_db):
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 42
        mock_db.execute.return_value = mock_result
        count = await service.count_active("user1")
        assert count == 42
