"""Tests for KnowledgeService DataService facade."""

from unittest.mock import AsyncMock

import pytest

from src.database.models.knowledge import KnowledgeCategory
from src.services.knowledge_service import KnowledgeService

pytestmark = pytest.mark.asyncio


@pytest.fixture
def dataservice():
    return AsyncMock()


@pytest.fixture
def service(dataservice):
    return KnowledgeService(dataservice=dataservice)


async def test_create_uses_dataservice_payload(service, dataservice):
    dataservice.create_knowledge_memory.return_value = {"id": "k-1"}

    result = await service.create(
        user_id="user1",
        category=KnowledgeCategory.CONTEXT,
        content="test content",
        confidence=0.6,
        workspace_context="ws-1",
    )

    assert result == {"id": "k-1"}
    command = dataservice.create_knowledge_memory.await_args.args[0]
    assert command.user_id == "user1"
    assert command.category == "context"
    assert command.content == "test content"
    assert command.workspace_context == "ws-1"


async def test_list_by_user_normalizes_category(service, dataservice):
    dataservice.list_user_knowledge_memory.return_value = []

    result = await service.list_by_user(
        "user1",
        category=KnowledgeCategory.PREFERENCE,
        min_confidence=0.7,
        active_only=False,
    )

    assert result == []
    dataservice.list_user_knowledge_memory.assert_awaited_once_with(
        user_id="user1",
        category="preference",
        min_confidence=0.7,
        active_only=False,
    )


async def test_update_delegates_without_gateway_commit(service, dataservice):
    dataservice.update_knowledge_memory.return_value = {"id": "k-1", "content": "new"}

    result = await service.update("k-1", content="new", confidence=0.9, is_active=False)

    assert result == {"id": "k-1", "content": "new"}
    command = dataservice.update_knowledge_memory.await_args.args[1]
    assert command.content == "new"
    assert command.confidence == 0.9
    assert command.is_active is False


async def test_delete_and_deactivate_delegate_to_dataservice(service, dataservice):
    dataservice.deactivate_knowledge_memory.return_value = True
    dataservice.delete_knowledge_memory.return_value = True

    assert await service.deactivate("k-1") is True
    assert await service.delete("k-1") is True

    dataservice.deactivate_knowledge_memory.assert_awaited_once_with("k-1")
    dataservice.delete_knowledge_memory.assert_awaited_once_with("k-1")


async def test_list_active_delegates_scope(service, dataservice):
    dataservice.list_active_knowledge_memory.return_value = []

    result = await service.list_active(
        "user1",
        workspace_context="ws-1",
        include_global=False,
        min_confidence=0.8,
        limit=5,
    )

    assert result == []
    dataservice.list_active_knowledge_memory.assert_awaited_once_with(
        user_id="user1",
        workspace_context="ws-1",
        include_global=False,
        min_confidence=0.8,
        limit=5,
    )


async def test_upsert_normalizes_category(service, dataservice):
    dataservice.upsert_knowledge_memory.return_value = {"id": "k-1"}

    await service.upsert(
        "user1",
        KnowledgeCategory.PREFERENCE,
        "Prefers APA",
        confidence=0.9,
        source="test",
    )

    command = dataservice.upsert_knowledge_memory.await_args.args[0]
    assert command.category == "preference"
    assert command.content == "Prefers APA"


async def test_archive_and_count_delegate(service, dataservice):
    dataservice.archive_low_confidence_knowledge_memory.return_value = 3
    dataservice.count_active_knowledge_memory.return_value = 42

    archived = await service.archive_low_confidence("user1", threshold=0.4)
    count = await service.count_active("user1", workspace_context="ws-1", include_global=False)

    assert archived == 3
    archive_command = dataservice.archive_low_confidence_knowledge_memory.await_args.kwargs["command"]
    assert archive_command.threshold == 0.4
    assert count == 42
    dataservice.count_active_knowledge_memory.assert_awaited_once_with(
        user_id="user1",
        workspace_context="ws-1",
        include_global=False,
    )
