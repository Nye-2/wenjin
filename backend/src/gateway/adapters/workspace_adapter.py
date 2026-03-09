"""Adapter for bridging frontend API with workspace services.

This module provides the WorkspaceAdapter class that translates frontend API
requests into workspace service calls and formats responses for frontend consumption.
"""

import uuid
from typing import Any


class WorkspaceAdapter:
    """Adapter for workspace-related frontend API operations.

    This adapter bridges the frontend API with workspace management,
    providing methods to list, create, and retrieve workspaces.

    For testing purposes, this adapter uses in-memory storage instead of
    requiring a database connection. In production, it would integrate
    with the WorkspaceService.
    """

    def __init__(self) -> None:
        """Initialize the workspace adapter with in-memory storage."""
        self._workspaces: dict[str, dict[str, Any]] = {}

    async def list_workspaces(self, user_id: str) -> list[dict[str, Any]]:
        """List all workspaces for a user.

        Args:
            user_id: The ID of the user whose workspaces to list.

        Returns:
            List of workspace dictionaries for the user, each containing:
            - id: Unique workspace identifier
            - user_id: Owner's user ID
            - name: Workspace name
            - type: Workspace type (paper_type)
            - description: Workspace description
            - config: Workspace configuration
        """
        return [
            ws
            for ws in self._workspaces.values()
            if ws.get("user_id") == user_id
        ]

    async def create_workspace(
        self,
        user_id: str,
        name: str,
        paper_type: str,
        description: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new workspace.

        Args:
            user_id: The ID of the user creating the workspace.
            name: The name of the workspace.
            paper_type: The type of paper (e.g., "research_article", "thesis").
            description: Optional description of the workspace.
            config: Optional configuration dictionary.

        Returns:
            The created workspace dictionary containing:
            - id: Unique workspace identifier
            - user_id: Owner's user ID
            - name: Workspace name
            - type: Workspace type (paper_type)
            - description: Workspace description
            - config: Workspace configuration
        """
        workspace_id = str(uuid.uuid4())
        workspace: dict[str, Any] = {
            "id": workspace_id,
            "user_id": user_id,
            "name": name,
            "type": paper_type,
            "description": description,
            "config": config or {},
        }
        self._workspaces[workspace_id] = workspace
        return workspace

    async def get_workspace(self, workspace_id: str) -> dict[str, Any] | None:
        """Get a workspace by ID.

        Args:
            workspace_id: The unique identifier of the workspace.

        Returns:
            Workspace dictionary if found, None otherwise.
        """
        return self._workspaces.get(workspace_id)
