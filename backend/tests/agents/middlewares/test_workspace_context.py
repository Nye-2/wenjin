"""Tests for WorkspaceContextMiddleware."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.middlewares.workspace_context import WorkspaceContextMiddleware
from src.agents.thread_state import ThreadState


@pytest.fixture
def mock_workspace():
    """Create a mock workspace object."""
    workspace = MagicMock()
    workspace.id = "ws-123"
    workspace.type = MagicMock()
    workspace.type.value = "sci"
    workspace.discipline = "computer_science"
    workspace.config = {"citation_style": "APA", "language": "en"}
    return workspace


@pytest.fixture
def workspace_service(mock_workspace):
    """Create a mock workspace service."""
    service = MagicMock()
    service.get = AsyncMock(return_value=mock_workspace)
    return service


@pytest.fixture
def template_service():
    """Create a mock template service."""
    service = MagicMock()
    service.get_active = AsyncMock(return_value=None)
    return service


@pytest.fixture
def middleware(workspace_service):
    """Create WorkspaceContextMiddleware with mocked service."""
    template_service = MagicMock()
    template_service.get_active = AsyncMock(return_value=None)
    return WorkspaceContextMiddleware(workspace_service, template_service=template_service)


class TestWorkspaceContextMiddleware:
    """Tests for WorkspaceContextMiddleware."""

    @pytest.mark.asyncio
    async def test_loads_workspace_and_injects_all_fields(self, middleware, workspace_service):
        """Test that middleware loads workspace and injects type, discipline, and config."""
        state = ThreadState(messages=[], workspace_id="ws-123")
        config = {"configurable": {}}

        result = await middleware.before_model(state, config)

        # Verify service was called with correct ID
        workspace_service.get.assert_called_once_with("ws-123")

        # Verify all fields are injected
        assert result["workspace_type"] is not None
        assert result["workspace_type"].value == "sci"
        assert result["discipline"] == "computer_science"
        assert result["workspace_config"] == {"citation_style": "APA", "language": "en"}
        assert result["template_context"] is None

    @pytest.mark.asyncio
    async def test_loads_active_template_context(self, workspace_service):
        """Test that middleware loads active template through TemplateService."""
        template_service = MagicMock()
        template_service.get_active = AsyncMock(
            return_value=SimpleNamespace(
                name="SCI Template",
                structure={"sections": ["abstract"]},
                format_spec={"style": "ieee"},
                content_guidelines={"language": "en"},
            )
        )
        middleware = WorkspaceContextMiddleware(
            workspace_service,
            template_service=template_service,
        )

        result = await middleware.before_model(
            ThreadState(messages=[], workspace_id="ws-123"),
            {"configurable": {}},
        )

        template_service.get_active.assert_awaited_once_with("ws-123")
        assert result["template_context"] == {
            "name": "SCI Template",
            "structure": {"sections": ["abstract"]},
            "format_spec": {"style": "ieee"},
            "content_guidelines": {"language": "en"},
        }

    @pytest.mark.asyncio
    async def test_skips_loading_when_no_workspace_id(self, middleware, workspace_service):
        """Test middleware skips loading when workspace_id is not present."""
        state = ThreadState(messages=[])
        config = {"configurable": {}}

        result = await middleware.before_model(state, config)

        # Service should not be called
        workspace_service.get.assert_not_called()

        # State should be returned unchanged (no workspace fields)
        assert result.get("workspace_type") is None
        assert result.get("discipline") is None
        assert result.get("workspace_config") is None

    @pytest.mark.asyncio
    async def test_handles_workspace_not_found_gracefully(self, workspace_service):
        """Test middleware handles workspace not found gracefully."""
        # Configure service to return None (workspace not found)
        workspace_service.get = AsyncMock(return_value=None)
        template_service = MagicMock()
        template_service.get_active = AsyncMock(return_value=None)
        middleware = WorkspaceContextMiddleware(
            workspace_service,
            template_service=template_service,
        )

        state = ThreadState(messages=[], workspace_id="nonexistent-ws")
        config = {"configurable": {}}

        result = await middleware.before_model(state, config)

        # Service should be called
        workspace_service.get.assert_called_once_with("nonexistent-ws")

        # State should be returned unchanged when workspace not found
        assert result.get("workspace_type") is None
        assert result.get("discipline") is None
        assert result.get("workspace_config") is None

    @pytest.mark.asyncio
    async def test_preserves_existing_state_fields(self, middleware, workspace_service):
        """Test middleware returns partial updates and leaves merge to the pipeline."""
        state = ThreadState(
            messages=[],
            workspace_id="ws-123",
            cited_papers=["paper-1", "paper-2"],
            thread_data={"custom": "data"},
        )
        config = {"configurable": {}}

        result = await middleware.before_model(state, config)

        # Middleware should only return the fields it is responsible for.
        assert "cited_papers" not in result
        assert "thread_data" not in result

        # And workspace fields should be added
        assert result["workspace_type"] is not None
        assert result["discipline"] == "computer_science"
        assert result["workspace_config"] is not None

    @pytest.mark.asyncio
    async def test_handles_none_workspace_id(self, middleware, workspace_service):
        """Test middleware handles None workspace_id correctly."""
        state = ThreadState(messages=[], workspace_id=None)
        config = {"configurable": {}}

        result = await middleware.before_model(state, config)

        # Service should not be called
        workspace_service.get.assert_not_called()

        # State should be returned unchanged
        assert result.get("workspace_type") is None
        assert result.get("discipline") is None

    @pytest.mark.asyncio
    async def test_handles_empty_string_workspace_id(self, middleware, workspace_service):
        """Test middleware handles empty string workspace_id correctly."""
        state = ThreadState(messages=[], workspace_id="")
        config = {"configurable": {}}

        result = await middleware.before_model(state, config)

        # Service should not be called (empty string is falsy)
        workspace_service.get.assert_not_called()

        # State should be returned unchanged
        assert result.get("workspace_type") is None
        assert result.get("discipline") is None

    @pytest.mark.asyncio
    async def test_injects_correct_workspace_type_from_enum(self, workspace_service):
        """Test that workspace type enum is correctly passed through."""
        from src.database.models.workspace import WorkspaceType

        # Create mock with actual enum value
        mock_workspace = MagicMock()
        mock_workspace.type = WorkspaceType.THESIS
        mock_workspace.discipline = "physics"
        mock_workspace.config = {}

        workspace_service.get = AsyncMock(return_value=mock_workspace)
        template_service = MagicMock()
        template_service.get_active = AsyncMock(return_value=None)
        middleware = WorkspaceContextMiddleware(
            workspace_service,
            template_service=template_service,
        )

        state = ThreadState(messages=[], workspace_id="ws-thesis")
        config = {"configurable": {}}

        result = await middleware.before_model(state, config)

        assert result["workspace_type"] == WorkspaceType.THESIS
        assert result["discipline"] == "physics"
