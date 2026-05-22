"""Workspace-aware read tools exposed to the lead agent."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from src.application.workspace_resolvers import resolve_workspace_type
from src.dataservice_client.provider import dataservice_client


class ListCapabilitiesInput(BaseModel):
    """Input for list_capabilities."""


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


def _capability_to_feature_dict(cap: Any) -> dict[str, Any]:
    """Build the per-feature payload from a Capability row.

    Returns id, name, description, icon, stages, color, followUpPrompt.
    Display metadata (icon/color/stages/follow_up_prompt) comes from ui_meta.
    """
    ui_meta = cap.ui_meta or {}
    stages_raw = ui_meta.get("stages") or []
    stages: list[dict[str, Any]] = []
    for stage in stages_raw:
        if isinstance(stage, Mapping):
            stages.append(
                {
                    "id": stage.get("id"),
                    "label": stage.get("label"),
                }
            )
    return {
        "id": cap.id,
        "name": cap.display_name,
        "description": cap.description,
        "icon": ui_meta.get("icon"),
        "stages": stages,
        "color": ui_meta.get("color"),
        "followUpPrompt": ui_meta.get("follow_up_prompt"),
    }


@tool("list_capabilities", args_schema=ListCapabilitiesInput)
async def list_capabilities_tool(
    config: RunnableConfig | None = None,
) -> str:
    """List available workspace capabilities for the current workspace."""
    runtime = _runtime_context(config)
    if runtime.workspace_id is None or runtime.user_id is None:
        return json.dumps({"error": "runtime_context_missing"}, ensure_ascii=False)

    async with dataservice_client() as client:
        workspace = await client.get_workspace(runtime.workspace_id)
        if workspace is None:
            return json.dumps({"error": "workspace_not_found"}, ensure_ascii=False)
        if not await client.workspace_has_active_membership(
            workspace_id=str(runtime.workspace_id),
            user_id=str(runtime.user_id),
        ):
            return json.dumps({"error": "workspace_not_found"}, ensure_ascii=False)

        workspace_type = resolve_workspace_type(workspace)

        capabilities = sorted(
            await client.list_catalog_capabilities(
                workspace_type=workspace_type,
                enabled_only=True,
            ),
            key=lambda c: ((c.ui_meta or {}).get("order", 0), c.id),
        )

        features: list[dict[str, Any]] = []
        for cap in capabilities:
            if (cap.dashboard_meta or {}).get("hidden") is True:
                continue
            features.append(_capability_to_feature_dict(cap))

        return json.dumps(
            {
                "workspace_id": str(workspace.id),
                "workspace_type": workspace_type,
                "features": features,
            },
            ensure_ascii=False,
        )


@tool("list_workspace_artifacts", args_schema=ListWorkspaceArtifactsInput)
async def list_workspace_artifacts_tool(
    limit: int = 8,
    config: RunnableConfig | None = None,
) -> str:
    """List recent artifacts produced inside the current workspace."""
    runtime = _runtime_context(config)
    if runtime.workspace_id is None or runtime.user_id is None:
        return json.dumps({"error": "runtime_context_missing"}, ensure_ascii=False)

    async with dataservice_client() as client:
        workspace = await client.get_workspace(runtime.workspace_id)
        if workspace is None:
            return json.dumps({"error": "workspace_not_found"}, ensure_ascii=False)
        if not await client.workspace_has_active_membership(
            workspace_id=str(runtime.workspace_id),
            user_id=str(runtime.user_id),
        ):
            return json.dumps({"error": "workspace_not_found"}, ensure_ascii=False)

        artifacts = await client.list_assets(
            workspace_id=runtime.workspace_id,
            asset_kind="artifact",
            limit=limit,
        )

        return json.dumps(
            {
                "workspace_id": runtime.workspace_id,
                "count": len(artifacts),
                "artifacts": [
                    {
                        "id": str(artifact.id),
                        "type": str(artifact.metadata_json.get("artifact_type") or artifact.asset_kind),
                        "title": artifact.title or artifact.name,
                        "created_at": (
                            artifact.created_at.isoformat() if artifact.created_at else None
                        ),
                    }
                    for artifact in artifacts
                ],
            },
            ensure_ascii=False,
        )
