from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.permission_runtime import PermissionResolutionService
from src.permission_runtime.contracts import (
    PermissionContext,
    PermissionDecision,
)


def _context() -> PermissionContext:
    return PermissionContext(
        mission_id="mission-1",
        tool_name="sandbox.run",
        operation="install_dependencies",
        risk_level="medium",
        network_profile="package_proxy",
    )


def _membership() -> SimpleNamespace:
    return SimpleNamespace(require_active_member=AsyncMock())


@pytest.mark.asyncio
async def test_permission_resolution_resumes_the_durable_request() -> None:
    resumer = AsyncMock(
        return_value=SimpleNamespace(status=SimpleNamespace(value="planning"))
    )
    missions = SimpleNamespace(
        list_items=AsyncMock(return_value=[]),
        get=AsyncMock(
            return_value=SimpleNamespace(
                user_id="user-1",
                workspace_id="workspace-1",
                snapshot_json={
                    "pending_request": {
                        "request_id": "request-1",
                        "permission_context": _context().model_dump(mode="json"),
                    }
                },
            )
        ),
    )
    result = await PermissionResolutionService(
        missions=missions,
        membership=_membership(),
        resumer=SimpleNamespace(resume=resumer),
    ).resolve(
        "mission-1",
        request_id="request-1",
        decision=PermissionDecision.ALLOW_FOR_MISSION,
        actor_user_id="user-1",
    )
    assert result.resumed is True
    assert result.grant is not None
    assert result.grant.mission_id == "mission-1"
    assert result.grant.tool_name == "sandbox.run"
    resumer.assert_awaited_once_with(
        "mission-1",
        request_id="request-1",
        input_json=result.input_json,
        producer="permission_runtime",
    )


@pytest.mark.asyncio
async def test_permission_resume_rejects_wrong_request_id() -> None:
    missions = SimpleNamespace(
        list_items=AsyncMock(return_value=[]),
        get=AsyncMock(
            return_value=SimpleNamespace(
                user_id="user-1",
                workspace_id="workspace-1",
                snapshot_json={"pending_request": {"request_id": "request-1"}},
            )
        ),
    )
    with pytest.raises(ValueError, match="permission_request_mismatch"):
        await PermissionResolutionService(
            missions=missions,
            membership=_membership(),
            resumer=SimpleNamespace(resume=AsyncMock()),
        ).resolve(
            "mission-1",
            request_id="request-2",
            decision=PermissionDecision.REJECT,
            actor_user_id="user-1",
        )


@pytest.mark.asyncio
async def test_duplicate_permission_resolution_is_idempotent_after_restart() -> None:
    context = _context().model_dump(mode="json")
    missions = SimpleNamespace(
        list_items=AsyncMock(
            return_value=[
                SimpleNamespace(
                    operation_id="request-1",
                    payload_json={
                        "request_id": "request-1",
                        "decision": "allow_once",
                        "actor_user_id": "user-1",
                        "permission_context": context,
                    },
                )
            ]
        ),
        get=AsyncMock(
            return_value=SimpleNamespace(
                user_id="user-1", workspace_id="workspace-1"
            )
        ),
    )
    resumer = AsyncMock()
    result = await PermissionResolutionService(
        missions=missions,
        membership=_membership(),
        resumer=SimpleNamespace(resume=resumer),
    ).resolve(
        "mission-1",
        request_id="request-1",
        decision=PermissionDecision.ALLOW_ONCE,
        actor_user_id="user-1",
    )
    assert result.resumed is True
    missions.get.assert_awaited_once()
    resumer.assert_not_awaited()
