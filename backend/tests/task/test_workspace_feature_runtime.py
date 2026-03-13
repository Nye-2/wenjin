"""Runtime behavior tests for workspace feature execution."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.workspace_features.registry import WorkspaceFeatureDefinition
from src.workspace_features.runtime import execute_registered_feature


def _build_missing_feature_definition() -> WorkspaceFeatureDefinition:
    return WorkspaceFeatureDefinition(
        workspace_type="sci",
        id="missing_feature",
        name="Missing Feature",
        description="Feature without registered handler",
        icon="file",
        agent="writer",
        agent_label="Writer",
        handler_key="sci.missing_feature",
        task_type="workspace_feature",
        panel="editor_panel",
        stages=(),
        color="amber",
    )


@pytest.mark.asyncio
async def test_execute_registered_feature_raises_when_missing_handler_in_fail_mode(monkeypatch):
    """Fail mode should hard-fail when a handler is missing."""
    monkeypatch.setenv("WORKSPACE_FEATURE_MISSING_HANDLER_MODE", "fail")

    progress = SimpleNamespace(update=AsyncMock())
    payload = {
        "workspace_id": "ws-1",
        "workspace_type": "sci",
        "workspace_name": "SCI Workspace",
        "feature_id": "missing_feature",
        "feature_name": "Missing Feature",
    }

    with pytest.raises(
        RuntimeError,
        match="No concrete workspace feature handler registered: sci.missing_feature",
    ):
        await execute_registered_feature(
            payload=payload,
            progress=progress,
            feature=_build_missing_feature_definition(),
        )


@pytest.mark.asyncio
async def test_execute_registered_feature_uses_placeholder_in_placeholder_mode(monkeypatch):
    """Placeholder mode should keep scaffold behavior for missing handlers."""
    monkeypatch.setenv("WORKSPACE_FEATURE_MISSING_HANDLER_MODE", "placeholder")

    progress = SimpleNamespace(update=AsyncMock())
    payload = {
        "workspace_id": "ws-1",
        "workspace_type": "sci",
        "workspace_name": "SCI Workspace",
        "feature_id": "missing_feature",
        "feature_name": "Missing Feature",
    }

    result = await execute_registered_feature(
        payload=payload,
        progress=progress,
        feature=_build_missing_feature_definition(),
    )

    assert result["success"] is True
    assert result["handler_key"] == "sci.missing_feature"
    assert "routed through the unified task pipeline" in result["message"]
    assert progress.update.await_count == 2
