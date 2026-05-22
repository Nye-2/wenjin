"""Tests for the ArtifactService DataService facade."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from src.academic.services.artifact_service import ArtifactService
from src.dataservice_client.contracts.asset import LegacyArtifactPayload


def _make_db_session():
    db = AsyncMock()
    db.execute = AsyncMock()
    return db


def _projection(**overrides) -> LegacyArtifactPayload:
    now = datetime.now(UTC)
    return LegacyArtifactPayload(
        id=overrides.get("id", "artifact-1"),
        workspace_id=overrides.get("workspace_id", "ws-1"),
        type=overrides.get("type", "research_idea"),
        title=overrides.get("title", "My Research"),
        content=overrides.get("content", {"body": "test"}),
        created_by_skill=overrides.get("created_by_skill"),
        parent_artifact_id=overrides.get("parent_artifact_id"),
        version=overrides.get("version", 1),
        status=overrides.get("status", "draft"),
        created_at=overrides.get("created_at", now),
        updated_at=overrides.get("updated_at", now),
    )


@pytest.mark.asyncio
async def test_create_delegates_to_dataservice_legacy_artifact_command() -> None:
    db = _make_db_session()
    dataservice = AsyncMock()
    service = ArtifactService(db, dataservice=dataservice)
    expected = _projection(id="artifact-new")
    dataservice.create_legacy_artifact.return_value = expected

    result = await service.create(
        workspace_id="ws-1",
        type="research_idea",
        content={"body": "test"},
        title="My Research",
        created_by_skill="deep_research",
        parent_artifact_id="parent-1",
    )

    command = dataservice.create_legacy_artifact.await_args.args[0]
    assert command.workspace_id == "ws-1"
    assert command.artifact_type == "research_idea"
    assert command.content == {"body": "test"}
    assert command.title == "My Research"
    assert command.created_by_skill == "deep_research"
    assert command.parent_artifact_id == "parent-1"
    assert result == expected
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_find_latest_and_list_versions_delegate_to_dataservice() -> None:
    dataservice = AsyncMock()
    service = ArtifactService(_make_db_session(), dataservice=dataservice)
    latest = _projection(id="latest", version=5)
    versions = [
        _projection(id="v3", version=3),
        _projection(id="v2", version=2),
    ]
    dataservice.find_latest_legacy_artifact.return_value = latest
    dataservice.list_legacy_artifact_versions.return_value = versions

    found = await service._find_latest_version("ws-1", "research_idea", "My Research")
    listed = await service.list_versions("ws-1", "research_idea", "My Research")

    assert found == latest
    assert listed == versions
    dataservice.find_latest_legacy_artifact.assert_awaited_once_with(
        workspace_id="ws-1",
        artifact_type="research_idea",
        title="My Research",
    )
    dataservice.list_legacy_artifact_versions.assert_awaited_once_with(
        workspace_id="ws-1",
        artifact_type="research_idea",
        title="My Research",
    )


@pytest.mark.asyncio
async def test_crud_and_lineage_delegate_to_dataservice() -> None:
    dataservice = AsyncMock()
    service = ArtifactService(_make_db_session(), dataservice=dataservice)
    artifact = _projection(id="artifact-1")
    lineage = [_projection(id="root"), artifact]
    dataservice.get_legacy_artifact.return_value = artifact
    dataservice.list_legacy_artifacts.return_value = [artifact]
    dataservice.update_legacy_artifact.return_value = artifact
    dataservice.delete_legacy_artifact.return_value = True
    dataservice.get_legacy_artifact_lineage.return_value = lineage

    assert await service.get("artifact-1") == artifact
    assert await service.list_by_workspace("ws-1", type="research_idea") == [artifact]
    assert await service.list_by_type("ws-1", "research_idea") == [artifact]
    assert await service.update("artifact-1", title="Updated") == artifact
    assert await service.delete("artifact-1") is True
    assert await service.get_lineage("artifact-1") == lineage

    dataservice.list_legacy_artifacts.assert_any_await(
        workspace_id="ws-1",
        artifact_type="research_idea",
        status=None,
        limit=50,
        offset=0,
    )
    update_command = dataservice.update_legacy_artifact.await_args.args[1]
    assert update_command.title == "Updated"
