"""DataService workspace domain tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.database.models.workspace import WorkspaceType
from src.database.models.workspace_settings import WorkspaceSettings
from src.dataservice.common.errors import DataServiceConflictError
from src.dataservice.domains.workspace.contracts import WorkspaceCreateCommand
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
