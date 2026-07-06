"""DataService workspace domain tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from src.database.models.workspace import WorkspaceType
from src.database.models.workspace_settings import WorkspaceSettings
from src.dataservice.common.errors import DataServiceConflictError
from src.dataservice.domains.workspace.contracts import WorkspaceCreateCommand, WorkspaceSettingsUpdateCommand
from src.dataservice.domains.workspace.models import WorkspaceMembership
from src.dataservice.domains.workspace.policies import with_rollout_defaults
from src.dataservice.domains.workspace.service import DataServiceWorkspaceService


class FakeSession:
    def __init__(self) -> None:
        self.added: list[Any] = []
        self.flush = AsyncMock()
        self.commit = AsyncMock()
        self.refresh = AsyncMock()

    def add(self, value: Any) -> None:
        self.added.append(value)


def _settings_row(workspace_id: str = "ws-1") -> WorkspaceSettings:
    return WorkspaceSettings(
        workspace_id=workspace_id,
        thinking_enabled=True,
        sandbox_provider="local",
        auto_compact_threshold=0.8,
        capability_overrides={},
        settings_json={},
        metadata_json={},
    )


@pytest.mark.asyncio
async def test_create_workspace_creates_owner_membership_and_settings() -> None:
    session = FakeSession()
    service = DataServiceWorkspaceService(session)  # type: ignore[arg-type]

    workspace = await service.create_workspace(
        WorkspaceCreateCommand(
            created_by_user_id="user-1",
            name="Workspace",
            workspace_type=WorkspaceType.THESIS,
            settings_json={"language": "zh"},
        )
    )

    assert workspace.user_id == "user-1"
    assert workspace.type == WorkspaceType.THESIS
    assert workspace.config["language"] == "zh"
    assert workspace.config["rollout"]["thread_cockpit_enabled"] is True
    assert workspace.config["write_mode"] == "auto_draft"
    assert any(isinstance(item, WorkspaceMembership) for item in session.added)
    assert any(isinstance(item, WorkspaceSettings) for item in session.added)
    session.commit.assert_awaited_once()


def test_workspace_rollout_defaults_do_not_override_explicit_value() -> None:
    settings = with_rollout_defaults(
        WorkspaceType.SCI,
        {"rollout": {"thread_cockpit_enabled": False}},
    )

    assert settings["rollout"]["thread_cockpit_enabled"] is False


def test_workspace_membership_model_indexes_active_owner_lookup() -> None:
    indexes = {index.name: tuple(column.name for column in index.columns) for index in WorkspaceMembership.__table__.indexes}

    assert indexes["ix_workspace_memberships_workspace_role_status"] == ("workspace_id", "role", "status")


@pytest.mark.asyncio
async def test_active_thread_must_belong_to_workspace() -> None:
    session = FakeSession()
    service = DataServiceWorkspaceService(session)  # type: ignore[arg-type]
    workspace = type("WorkspaceLike", (), {"id": "ws-1", "thread_id": None})()
    thread = type("ThreadLike", (), {"workspace_id": "ws-2"})()
    service.repository.get_thread = AsyncMock(return_value=thread)  # type: ignore[method-assign]

    with pytest.raises(DataServiceConflictError):
        await service.set_active_thread(workspace, "thread-1")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_get_or_create_workspace_settings_creates_default_record() -> None:
    session = FakeSession()
    service = DataServiceWorkspaceService(session)  # type: ignore[arg-type]
    settings = _settings_row()
    service.repository.get_workspace_settings = AsyncMock(return_value=None)  # type: ignore[method-assign]
    service.repository.create_workspace_settings_from_values = MagicMock(return_value=settings)  # type: ignore[method-assign]

    record = await service.get_or_create_workspace_settings("ws-1")

    values = service.repository.create_workspace_settings_from_values.call_args.kwargs["values"]  # type: ignore[attr-defined]
    assert values["thinking_enabled"] is True
    assert values["sandbox_provider"] == "local"
    assert values["settings_json"]["write_mode"] == "auto_draft"
    assert record.workspace_id == "ws-1"
    assert record.capability_overrides == {}
    assert record.write_mode == "auto_draft"
    assert record.settings_json["write_mode"] == "auto_draft"
    session.commit.assert_awaited_once()


def test_workspace_settings_record_projects_missing_write_mode_default() -> None:
    settings = _settings_row()

    record = DataServiceWorkspaceService.to_settings_record(settings)

    assert record.write_mode == "auto_draft"
    assert record.settings_json["write_mode"] == "auto_draft"


@pytest.mark.asyncio
async def test_update_workspace_settings_returns_projection() -> None:
    session = FakeSession()
    service = DataServiceWorkspaceService(session)  # type: ignore[arg-type]
    settings = _settings_row()
    service.repository.get_workspace_settings = AsyncMock(return_value=settings)  # type: ignore[method-assign]

    record = await service.update_workspace_settings(
        "ws-1",
        command=WorkspaceSettingsUpdateCommand(
            default_model="mimo-v2.5-pro",
            thinking_enabled=False,
            capability_overrides={"cap": {"enabled": False}},
        ),
    )

    assert record is not None
    assert record.default_model == "mimo-v2.5-pro"
    assert record.thinking_enabled is False
    assert record.capability_overrides == {"cap": {"enabled": False}}
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_workspace_settings_write_mode_preserves_settings_json_keys() -> None:
    session = FakeSession()
    service = DataServiceWorkspaceService(session)  # type: ignore[arg-type]
    settings = _settings_row()
    settings.settings_json = {"language": "zh", "rollout": {"thread_cockpit_enabled": False}}
    service.repository.get_workspace_settings = AsyncMock(return_value=settings)  # type: ignore[method-assign]

    record = await service.update_workspace_settings(
        "ws-1",
        command=WorkspaceSettingsUpdateCommand(write_mode="strict_review"),
    )

    assert record is not None
    assert settings.settings_json == {
        "language": "zh",
        "rollout": {"thread_cockpit_enabled": False},
        "write_mode": "strict_review",
    }
    assert record.write_mode == "strict_review"
    session.commit.assert_awaited_once()


def test_workspace_settings_update_rejects_invalid_write_mode() -> None:
    with pytest.raises(ValidationError):
        WorkspaceSettingsUpdateCommand(write_mode="review_everything")


def test_workspace_settings_update_trims_write_mode() -> None:
    command = WorkspaceSettingsUpdateCommand(write_mode=" ask_workspace_write ")

    assert command.write_mode == "ask_workspace_write"


@pytest.mark.asyncio
async def test_update_workspace_settings_write_mode_null_does_not_overwrite_existing_mode() -> None:
    session = FakeSession()
    service = DataServiceWorkspaceService(session)  # type: ignore[arg-type]
    settings = _settings_row()
    settings.settings_json = {"write_mode": "strict_review", "language": "zh"}
    service.repository.get_workspace_settings = AsyncMock(return_value=settings)  # type: ignore[method-assign]

    record = await service.update_workspace_settings(
        "ws-1",
        command=WorkspaceSettingsUpdateCommand(write_mode=None),
    )

    assert record is not None
    assert settings.settings_json == {"write_mode": "strict_review", "language": "zh"}
    assert record.write_mode == "strict_review"
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_workspace_stats_for_member_aggregates_workspace_projection() -> None:
    session = FakeSession()
    service = DataServiceWorkspaceService(session)  # type: ignore[arg-type]
    now = datetime.now(UTC)
    service.repository.list_workspaces_for_member = AsyncMock(  # type: ignore[method-assign]
        return_value=[
            SimpleNamespace(type=WorkspaceType.THESIS, created_at=now),
            SimpleNamespace(type=WorkspaceType.SCI, created_at=now - timedelta(days=1)),
            SimpleNamespace(type=WorkspaceType.SCI, created_at=now - timedelta(days=9)),
        ]
    )

    stats = await service.get_workspace_stats_for_member("user-1")

    assert stats.total == 3
    assert stats.by_type == {"thesis": 1, "sci": 2}
    assert stats.created_last_7d == 2


@pytest.mark.asyncio
async def test_lock_workspace_for_update_delegates_to_repository() -> None:
    session = FakeSession()
    service = DataServiceWorkspaceService(session)  # type: ignore[arg-type]
    service.repository.lock_workspace_for_update = AsyncMock()  # type: ignore[method-assign]

    await service.lock_workspace_for_update("ws-1")

    service.repository.lock_workspace_for_update.assert_awaited_once_with("ws-1")  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_get_admin_workspace_stats_aggregates_membership_projection() -> None:
    session = FakeSession()
    service = DataServiceWorkspaceService(session)  # type: ignore[arg-type]
    service.repository.count_workspaces_by_type = AsyncMock(  # type: ignore[method-assign]
        return_value=[(WorkspaceType.THESIS, 2), ("sci", 1)]
    )
    service.repository.count_active_members_with_workspaces = AsyncMock(return_value=2)  # type: ignore[method-assign]

    stats = await service.get_admin_workspace_stats()

    assert stats.total == 3
    assert stats.by_type == {"thesis": 2, "sci": 1}
    assert stats.users_with_workspaces == 2


@pytest.mark.asyncio
async def test_count_workspaces_by_member_ids_delegates_to_repository() -> None:
    session = FakeSession()
    service = DataServiceWorkspaceService(session)  # type: ignore[arg-type]
    service.repository.count_workspaces_by_member_ids = AsyncMock(  # type: ignore[method-assign]
        return_value={"user-1": 2}
    )

    counts = await service.count_workspaces_by_member_ids(["user-1"])

    assert counts == {"user-1": 2}
    service.repository.count_workspaces_by_member_ids.assert_awaited_once_with(["user-1"])  # type: ignore[attr-defined]
