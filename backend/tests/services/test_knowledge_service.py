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
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
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


class TestCrudCompatibility:
    async def test_create_commits_and_refreshes(self, service, mock_db):
        entry = await service.create(
            user_id="user1",
            category="context",
            content="test content",
            confidence=0.6,
        )
        mock_db.add.assert_called_once_with(entry)
        mock_db.commit.assert_awaited_once()
        mock_db.refresh.assert_awaited_once_with(entry)
        assert entry.category == KnowledgeCategory.CONTEXT

    async def test_get_returns_entry(self, service, mock_db):
        expected = UserKnowledge(
            user_id="user1",
            category=KnowledgeCategory.KNOWLEDGE,
            content="known fact",
            confidence=0.7,
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = expected
        mock_db.execute.return_value = mock_result

        result = await service.get("k-1")
        assert result is expected

    async def test_update_returns_none_when_missing(self, service):
        service.get = AsyncMock(return_value=None)
        result = await service.update("missing-id", content="new")
        assert result is None

    async def test_update_persists_changes(self, service, mock_db):
        entry = UserKnowledge(
            user_id="user1",
            category=KnowledgeCategory.CONTEXT,
            content="old",
            confidence=0.4,
            is_active=True,
        )
        service.get = AsyncMock(return_value=entry)

        result = await service.update("k-1", content="new", confidence=0.9, is_active=False)
        assert result is entry
        assert entry.content == "new"
        assert entry.confidence == 0.9
        assert entry.is_active is False
        mock_db.commit.assert_awaited_once()
        mock_db.refresh.assert_awaited_once_with(entry)

    async def test_deactivate_when_missing(self, service):
        service.get = AsyncMock(return_value=None)
        assert await service.deactivate("missing-id") is False

    async def test_deactivate_success(self, service, mock_db):
        entry = UserKnowledge(
            user_id="user1",
            category=KnowledgeCategory.CONTEXT,
            content="content",
            confidence=0.5,
            is_active=True,
        )
        service.get = AsyncMock(return_value=entry)
        assert await service.deactivate("k-1") is True
        assert entry.is_active is False
        mock_db.commit.assert_awaited_once()

    async def test_delete_when_missing(self, service):
        service.get = AsyncMock(return_value=None)
        assert await service.delete("missing-id") is False

    async def test_delete_success(self, service, mock_db):
        entry = UserKnowledge(
            user_id="user1",
            category=KnowledgeCategory.CONTEXT,
            content="content",
            confidence=0.5,
        )
        service.get = AsyncMock(return_value=entry)
        assert await service.delete("k-1") is True
        mock_db.delete.assert_awaited_once_with(entry)
        mock_db.commit.assert_awaited_once()
