"""DataService workspace domain tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

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
    assert any(isinstance(item, WorkspaceMembership) for item in session.added)
    assert any(isinstance(item, WorkspaceSettings) for item in session.added)
    session.commit.assert_awaited_once()


def test_workspace_rollout_defaults_do_not_override_explicit_value() -> None:
    settings = with_rollout_defaults(
        WorkspaceType.SCI,
        {"rollout": {"thread_cockpit_enabled": False}},
    )

    assert settings["rollout"]["thread_cockpit_enabled"] is False


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
    assert record.workspace_id == "ws-1"
    assert record.capability_overrides == {}
    session.commit.assert_awaited_once()


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
