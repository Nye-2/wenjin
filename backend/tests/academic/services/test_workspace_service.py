"""Tests for WorkspaceService DataService facade."""

import uuid
from unittest.mock import AsyncMock

import pytest

from src.academic.services.workspace_service import WorkspaceService
from src.database import WorkspaceType
from src.dataservice_client.contracts.workspace import WorkspacePayload


def _workspace_payload(
    workspace_id: str = "workspace-1",
    *,
    workspace_type: str = "thesis",
    name: str = "Workspace",
) -> WorkspacePayload:
    return WorkspacePayload(
        id=workspace_id,
        created_by_user_id="user-1",
        name=name,
        workspace_type=workspace_type,
        settings_json={"rollout": {"thread_cockpit_enabled": True}},
        active_thread_id=None,
    )


@pytest.fixture
def dataservice():
    return AsyncMock()


@pytest.fixture
def service(dataservice):
    return WorkspaceService(dataservice=dataservice)


class TestCreateWorkspace:
    @pytest.fixture
    def sample_user_id(self):
        return str(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_create_workspace_with_required_fields(self, service, dataservice, sample_user_id):
        dataservice.create_workspace.return_value = _workspace_payload(workspace_type="sci")

        workspace = await service.create(
            user_id=sample_user_id,
            name="Test Workspace",
            type="sci",
        )

        assert workspace.type == "sci"
        command = dataservice.create_workspace.await_args.args[0]
        assert command.created_by_user_id == sample_user_id
        assert command.name == "Test Workspace"
        assert command.workspace_type == "sci"

    @pytest.mark.asyncio
    async def test_create_workspace_with_all_fields(self, service, dataservice, sample_user_id):
        dataservice.create_workspace.return_value = _workspace_payload(
            workspace_type="thesis",
            name="Full Workspace",
        )

        await service.create(
            user_id=sample_user_id,
            name="Full Workspace",
            type="thesis",
            description="A test workspace",
            config={"setting1": "value1"},
        )

        command = dataservice.create_workspace.await_args.args[0]
        assert command.description == "A test workspace"
        assert command.settings_json == {"setting1": "value1"}

    @pytest.mark.asyncio
    async def test_create_workspace_with_enum_type(self, service, dataservice, sample_user_id):
        dataservice.create_workspace.return_value = _workspace_payload(workspace_type="patent")

        await service.create(
            user_id=sample_user_id,
            name="Enum Workspace",
            type=WorkspaceType.PATENT,
        )

        command = dataservice.create_workspace.await_args.args[0]
        assert command.workspace_type == "patent"

    @pytest.mark.asyncio
    async def test_create_workspace_with_invalid_type_raises_error(self, service, sample_user_id):
        with pytest.raises(ValueError, match="Invalid workspace type"):
            await service.create(
                user_id=sample_user_id,
                name="Invalid Workspace",
                type="invalid_type",
            )

    def test_with_rollout_defaults(self):
        config = WorkspaceService._with_rollout_defaults("proposal", None)
        assert config["rollout"]["thread_cockpit_enabled"] is True


class TestGetWorkspace:
    @pytest.mark.asyncio
    async def test_get_workspace_found(self, service, dataservice):
        expected = _workspace_payload("workspace-1")
        dataservice.get_workspace.return_value = expected

        result = await service.get("workspace-1")

        assert result == expected
        dataservice.get_workspace.assert_awaited_once_with("workspace-1")

    @pytest.mark.asyncio
    async def test_get_workspace_not_found(self, service, dataservice):
        dataservice.get_workspace.return_value = None
        assert await service.get("missing") is None


class TestListByUser:
    @pytest.mark.asyncio
    async def test_list_by_user_returns_workspaces(self, service, dataservice):
        dataservice.list_workspaces.return_value = [
            _workspace_payload("workspace-1"),
            _workspace_payload("workspace-2"),
        ]

        result = await service.list_by_user("user-1")

        assert len(result) == 2
        dataservice.list_workspaces.assert_awaited_once_with(member_user_id="user-1")

    @pytest.mark.asyncio
    async def test_has_active_membership(self, service, dataservice):
        dataservice.workspace_has_active_membership.return_value = True

        result = await service.has_active_membership(workspace_id="workspace-1", user_id="user-1")

        assert result is True
        dataservice.workspace_has_active_membership.assert_awaited_once_with(
            workspace_id="workspace-1",
            user_id="user-1",
        )


class TestUpdateWorkspace:
    @pytest.mark.asyncio
    async def test_update_workspace_name(self, service, dataservice):
        dataservice.update_workspace.return_value = _workspace_payload(name="New Name")

        result = await service.update("workspace-1", name="New Name")

        assert result is not None and result.name == "New Name"
        command = dataservice.update_workspace.await_args.args[1]
        assert command.name == "New Name"
        assert command.model_fields_set == {"name"}

    @pytest.mark.asyncio
    async def test_update_workspace_multiple_fields(self, service, dataservice):
        dataservice.update_workspace.return_value = _workspace_payload(name="New Name")

        await service.update(
            "workspace-1",
            name="New Name",
            description="New description",
        )

        command = dataservice.update_workspace.await_args.args[1]
        assert command.name == "New Name"
        assert command.description == "New description"

    @pytest.mark.asyncio
    async def test_update_workspace_with_type_string(self, service, dataservice):
        dataservice.update_workspace.return_value = _workspace_payload(workspace_type="thesis")

        await service.update("workspace-1", type="thesis")

        command = dataservice.update_workspace.await_args.args[1]
        assert command.workspace_type == "thesis"

    @pytest.mark.asyncio
    async def test_update_workspace_invalid_type_raises_error(self, service):
        with pytest.raises(ValueError, match="Invalid workspace type"):
            await service.update("workspace-1", type="invalid_type")

    @pytest.mark.asyncio
    async def test_update_workspace_not_found(self, service, dataservice):
        dataservice.update_workspace.return_value = None
        assert await service.update("missing", name="New Name") is None

    @pytest.mark.asyncio
    async def test_update_workspace_config(self, service, dataservice):
        dataservice.update_workspace.return_value = _workspace_payload()
        new_config = {"setting1": "value1", "setting2": "value2"}

        await service.update("workspace-1", config=new_config)

        command = dataservice.update_workspace.await_args.args[1]
        assert command.settings_json == new_config


class TestDeleteWorkspace:
    @pytest.mark.asyncio
    async def test_delete_workspace_found(self, service, dataservice):
        dataservice.delete_workspace.return_value = True
        assert await service.delete("workspace-1") is True

    @pytest.mark.asyncio
    async def test_delete_workspace_not_found(self, service, dataservice):
        dataservice.delete_workspace.return_value = False
        assert await service.delete("missing") is False


class TestWorkspaceTypeValidation:
    @pytest.mark.asyncio
    async def test_all_valid_workspace_types(self, service, dataservice):
        valid_types = [
            "sci",
            "thesis",
            "proposal",
            "software_copyright",
            "patent",
        ]
        dataservice.create_workspace.side_effect = [
            _workspace_payload(workspace_type=workspace_type) for workspace_type in valid_types
        ]

        for type_value in valid_types:
            await service.create(
                user_id="user-1",
                name=f"Workspace {type_value}",
                type=type_value,
            )

        observed_types = [
            call.args[0].workspace_type for call in dataservice.create_workspace.await_args_list
        ]
        assert observed_types == valid_types
