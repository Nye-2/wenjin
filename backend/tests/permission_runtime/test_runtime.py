from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.permission_runtime.contracts import (
    PermissionContext,
    PermissionDecision,
    PermissionDisposition,
    PermissionRequestType,
)
from src.permission_runtime.runtime import PermissionRuntime


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
async def test_permission_request_is_durable_and_restart_can_resume() -> None:
    missions = SimpleNamespace(
        pause=AsyncMock(),
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
        resume=AsyncMock(return_value=SimpleNamespace(mission=SimpleNamespace(status=SimpleNamespace(value="planning")))),
    )
    first_runtime = PermissionRuntime(missions=missions, membership=_membership())
    evaluation = await first_runtime.evaluate_or_pause(
        _context(),
        request_id="request-1",
        request_type=PermissionRequestType.EXTERNAL_DATA_ACCESS,
    )
    assert evaluation.disposition == PermissionDisposition.ASK
    pending = missions.pause.await_args.args[1].pending_request
    assert pending["request_id"] == "request-1"

    restarted_runtime = PermissionRuntime(missions=missions, membership=_membership())
    result = await restarted_runtime.resolve(
        "mission-1",
        request_id="request-1",
        decision=PermissionDecision.ALLOW_FOR_MISSION,
        actor_user_id="user-1",
    )
    assert result.resumed is True
    assert result.grant is not None
    restarted_runtime.validate_network_grant(
        result.grant,
        mission_id="mission-1",
        tool_name="sandbox.run",
        operation="install_dependencies",
        network_profile="package_proxy",
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
        await PermissionRuntime(missions=missions, membership=_membership()).resolve(
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
        resume=AsyncMock(),
    )
    result = await PermissionRuntime(missions=missions, membership=_membership()).resolve(
        "mission-1",
        request_id="request-1",
        decision=PermissionDecision.ALLOW_ONCE,
        actor_user_id="user-1",
    )
    assert result.resumed is True
    missions.get.assert_awaited_once()
    missions.resume.assert_not_awaited()
