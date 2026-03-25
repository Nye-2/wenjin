"""Workspace-aware tools exposed to the lead agent."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from src.agents.lead_agent.feature_bridge import (
    build_workspace_artifact_overview,
    build_workspace_feature_overview,
    execute_workspace_feature_request,
)


class ListWorkspaceFeaturesInput(BaseModel):
    """Input for list_workspace_features."""

    workspace_id: str = Field(description="Current workspace id")


class ListWorkspaceArtifactsInput(BaseModel):
    """Input for list_workspace_artifacts."""

    workspace_id: str = Field(description="Current workspace id")
    limit: int = Field(default=8, ge=1, le=20, description="Maximum artifact count to return")


class RunWorkspaceFeatureInput(BaseModel):
    """Input for run_workspace_feature."""

    workspace_id: str = Field(description="Current workspace id")
    thread_id: str = Field(description="Current chat thread id")
    user_id: str = Field(description="Current authenticated user id")
    feature_id: str = Field(description="Workspace feature id to execute")
    params: dict[str, Any] = Field(default_factory=dict, description="Structured feature params")


@tool("list_workspace_features", args_schema=ListWorkspaceFeaturesInput)
async def list_workspace_features_tool(workspace_id: str) -> str:
    """List available workspace features for the current workspace."""
    overview = await build_workspace_feature_overview(workspace_id)
    if overview is None:
        return json.dumps({"error": "workspace_not_found"}, ensure_ascii=False)
    return json.dumps(overview, ensure_ascii=False)


@tool("list_workspace_artifacts", args_schema=ListWorkspaceArtifactsInput)
async def list_workspace_artifacts_tool(workspace_id: str, limit: int = 8) -> str:
    """List recent artifacts produced inside the current workspace."""
    artifacts = await build_workspace_artifact_overview(workspace_id, limit=limit)
    return json.dumps(
        {"workspace_id": workspace_id, "count": len(artifacts), "artifacts": artifacts},
        ensure_ascii=False,
    )


@tool("run_workspace_feature", args_schema=RunWorkspaceFeatureInput)
async def run_workspace_feature_tool(
    workspace_id: str,
    thread_id: str,
    user_id: str,
    feature_id: str,
    params: dict[str, Any] | None = None,
) -> str:
    """Run a canonical workspace feature and return structured execution metadata."""
    reply = await execute_workspace_feature_request(
        workspace_id=workspace_id,
        thread_id=thread_id,
        user_id=user_id,
        feature_id=feature_id,
        params=params,
    )
    if reply is None:
        return json.dumps(
            {"error": "feature_execution_unavailable", "feature_id": feature_id},
            ensure_ascii=False,
        )
    return json.dumps(
        {
            "content": reply.content,
            "blocks": reply.blocks,
            "metadata": reply.metadata,
        },
        ensure_ascii=False,
    )
