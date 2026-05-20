"""Workspace projection helpers."""

from __future__ import annotations

from src.database.models.workspace import Workspace
from src.dataservice.domains.workspace.contracts import WorkspaceRecord
from src.dataservice.domains.workspace.service import DataServiceWorkspaceService


def workspace_to_record(workspace: Workspace) -> WorkspaceRecord:
    """Return canonical workspace projection."""
    return DataServiceWorkspaceService.to_record(workspace)
