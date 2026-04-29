"""Application-level workspace shape resolvers."""

from __future__ import annotations

from typing import Any


def resolve_workspace_type(workspace: Any) -> str:
    """Normalize workspace.type across enum and string shapes."""
    workspace_type = getattr(workspace, "type", None)
    if workspace_type is None:
        raise ValueError("Workspace type is not configured")
    resolved = workspace_type.value if hasattr(workspace_type, "value") else str(workspace_type)
    resolved = resolved.strip()
    if not resolved:
        raise ValueError("Workspace type is not configured")
    return resolved
