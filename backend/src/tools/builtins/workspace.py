"""Workspace-aware read tools exposed to the lead agent."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from src.workspace_features.thread_catalog import (
    build_workspace_artifact_overview,
    build_workspace_feature_overview,
)


class ListWorkspaceFeaturesInput(BaseModel):
    """Input for list_workspace_features."""


class ListWorkspaceArtifactsInput(BaseModel):
    """Input for list_workspace_artifacts."""

    limit: int = Field(default=8, ge=1, le=20, description="Maximum artifact count to return")


def _normalize_optional_str(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


@dataclass(frozen=True, slots=True)
class _RuntimeContext:
    workspace_id: str | None
    user_id: str | None


def _runtime_configurable(config: RunnableConfig | None) -> Mapping[str, Any]:
    configurable = config.get("configurable", {}) if isinstance(config, Mapping) else {}
    return configurable if isinstance(configurable, Mapping) else {}


def _runtime_context(config: RunnableConfig | None) -> _RuntimeContext:
    configurable = _runtime_configurable(config)
    return _RuntimeContext(
        workspace_id=_normalize_optional_str(configurable.get("workspace_id")),
        user_id=_normalize_optional_str(configurable.get("user_id")),
    )


@tool("list_workspace_features", args_schema=ListWorkspaceFeaturesInput)
async def list_workspace_features_tool(
    config: RunnableConfig | None = None,
) -> str:
    """List available workspace features for the current workspace."""
    runtime = _runtime_context(config)
    if runtime.workspace_id is None or runtime.user_id is None:
        return json.dumps({"error": "runtime_context_missing"}, ensure_ascii=False)
    overview = await build_workspace_feature_overview(
        runtime.workspace_id,
        user_id=runtime.user_id,
    )
    if overview is None:
        return json.dumps({"error": "workspace_not_found"}, ensure_ascii=False)
    return json.dumps(overview, ensure_ascii=False)


@tool("list_workspace_artifacts", args_schema=ListWorkspaceArtifactsInput)
async def list_workspace_artifacts_tool(
    limit: int = 8,
    config: RunnableConfig | None = None,
) -> str:
    """List recent artifacts produced inside the current workspace."""
    runtime = _runtime_context(config)
    if runtime.workspace_id is None or runtime.user_id is None:
        return json.dumps({"error": "runtime_context_missing"}, ensure_ascii=False)
    artifacts = await build_workspace_artifact_overview(
        runtime.workspace_id,
        user_id=runtime.user_id,
        limit=limit,
    )
    if artifacts is None:
        return json.dumps({"error": "workspace_not_found"}, ensure_ascii=False)
    return json.dumps(
        {
            "workspace_id": runtime.workspace_id,
            "count": len(artifacts),
            "artifacts": artifacts,
        },
        ensure_ascii=False,
    )
