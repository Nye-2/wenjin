from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.dataservice_client.errors import DataServiceClientError
from src.mission_runtime.adapters import (
    MissionItemOperationJournal,
    MissionToolOrchestratorAdapter,
)
from src.mission_runtime.contracts import MissionPortOutcomeStatus
from src.permission_runtime.authority import (
    permission_operation,
    permission_request_id,
)
from src.permission_runtime.contracts import PermissionContext
from src.tools.orchestrator import (
    ResearchToolOutcome,
    ToolCallerKind,
    ToolExecutionLimit,
    ToolOperation,
    ToolOutcomeStatus,
    ToolPolicy,
    VerificationStatus,
)


class _PolicyResolver:
    async def resolve(self, _mission, *, caller_kind, allowed_tools=None):
        assert caller_kind is ToolCallerKind.WORKSPACE_AGENT
        assert allowed_tools is None
        return ToolPolicy(
            policy_ref="policy@content-hash",
            allowed_tool_ids=("academic_visual.render_candidate",),
            allowed_network_profiles=("none", "academic_visual_scoped"),
            execution_limits=(
                ToolExecutionLimit(
                    tool_id="academic_visual.render_candidate",
                    descriptor_schema_hash="a" * 64,
                    descriptor_hash="b" * 64,
                    timeout_seconds=150,
                    max_attempts=1,
                ),
            ),
        )


class _CapturingOrchestrator:
    def __init__(self) -> None:
        self.context = None
        descriptor = SimpleNamespace(
            provenance_requirements=("workspace_scope", "mission_receipt"),
            network_profile="none",
        )
        self.catalog = SimpleNamespace(
            require=lambda _tool_id: SimpleNamespace(descriptor=descriptor)
        )

    async def invoke(self, tool_id, arguments, *, context, policy):
        _ = arguments, policy
        self.context = context
        return ResearchToolOutcome(
            operation_id="op-semantic",
            operation_key="a" * 64,
            producer=tool_id,
            tool_id=tool_id,
            tool_version="1.0.0",
            status=ToolOutcomeStatus.SUCCESS,
            observed_at=datetime.now(UTC),
            summary="prepared",
            verification_status=VerificationStatus.VERIFIED,
        )


class _PermissionPolicyResolver:
    async def resolve(self, _mission, *, caller_kind, allowed_tools=None):
        assert caller_kind is ToolCallerKind.WORKSPACE_AGENT
        assert allowed_tools is None
        return ToolPolicy(
            policy_ref="policy@content-hash",
            allowed_tool_ids=("sandbox.install_dependencies",),
            granted_permissions=("sandbox_compute",),
            allowed_network_profiles=("none", "package_index_only"),
            execution_limits=(
                ToolExecutionLimit(
                    tool_id="sandbox.install_dependencies",
                    descriptor_schema_hash="a" * 64,
                    descriptor_hash="b" * 64,
                    timeout_seconds=150,
                    max_attempts=1,
                ),
            ),
        )


class _PermissionOrchestrator(_CapturingOrchestrator):
    def __init__(self) -> None:
        super().__init__()
        descriptor = SimpleNamespace(
            provenance_requirements=("mission_permission", "sandbox_receipt"),
            network_profile="package_index_only",
        )
        self.catalog = SimpleNamespace(
            require=lambda _tool_id: SimpleNamespace(descriptor=descriptor)
        )


def _permission_request() -> SimpleNamespace:
    mission = SimpleNamespace(
        mission_id="mission-1",
        workspace_id="workspace-1",
        lease_epoch=4,
        model_id="gpt-5.6-terra",
        mission_policy_id="math_modeling",
        runtime_context_json={},
    )
    return SimpleNamespace(
        mission=mission,
        operation_id="install-command-1",
        tool_name="sandbox.install_dependencies",
        arguments={"packages": ["numpy==2.3.0"]},
        stage_id="solve",
        recent_items=[],
        deadline_monotonic=500.0,
    )


def _permission_receipt(decision: str) -> SimpleNamespace:
    request = _permission_request()
    context = PermissionContext(
        mission_id="mission-1",
        tool_name="sandbox.install_dependencies",
        operation=permission_operation(
            request.operation_id,
            request.arguments,
        ),
        risk_level="medium",
        network_profile="package_index_only",
    )
    return SimpleNamespace(
        seq=23,
        producer="permission_runtime",
        operation_id=permission_request_id(context),
        payload_json={
            "decision": decision,
            "permission_context": context.model_dump(mode="json"),
        },
    )


@pytest.mark.asyncio
async def test_workspace_tool_adapter_projects_server_semantic_provenance() -> None:
    orchestrator = _CapturingOrchestrator()
    adapter = MissionToolOrchestratorAdapter(
        store=SimpleNamespace(list_items=AsyncMock(return_value=[])),  # type: ignore[arg-type]
        orchestrator=orchestrator,  # type: ignore[arg-type]
        policy_resolver=_PolicyResolver(),  # type: ignore[arg-type]
    )
    mission = SimpleNamespace(
        mission_id="mission-1",
        workspace_id="workspace-1",
        lease_epoch=4,
        model_id="gpt-5.6-terra",
        mission_policy_id="sci_research",
        runtime_context_json={
            "policy_ref": "policy@content-hash",
            "policy_content_hash": "f" * 64,
            "mission_policy_snapshot": {"id": "sci_research", "version": 3},
            "tool_policy": {
                "policy_ref": "policy@content-hash",
                "allowed_tool_ids": ["academic_visual.render_candidate"],
            },
            "stage_contracts": {
                "visuals": {"contract_id": "sci.visuals", "version": 2}
            },
        },
    )
    source_item = SimpleNamespace(
        seq=19,
        operation_id="model-command-1",
        item_type="tool_call",
        payload_ref=None,
        payload_json={
            "reference_id": "/workspace/datasets/results.csv",
            "metadata": {"content_hash": "sha256:" + "d" * 64},
        },
    )
    request = SimpleNamespace(
        mission=mission,
        operation_id="model-command-1",
        tool_name="academic_visual.render_candidate",
        arguments={"brief": {}, "render": {}},
        stage_id="visuals",
        recent_items=[source_item],
        deadline_monotonic=500.0,
    )

    outcome = await adapter.execute(request)  # type: ignore[arg-type]

    assert outcome.summary == "prepared"
    assert orchestrator.context is not None
    assert orchestrator.context.deadline_monotonic == 500.0
    assert orchestrator.context.source_item_seq == 19
    assert orchestrator.context.input_refs == ("mission-item:19",)
    assert len(orchestrator.context.contract_hashes) == 4
    assert {
        item.ref: item.content_hash
        for item in orchestrator.context.content_hash_refs
    } == {
        "/workspace/datasets/results.csv": "sha256:" + "d" * 64,
    }


@pytest.mark.asyncio
async def test_permission_bound_tool_pauses_before_orchestrator_claim() -> None:
    orchestrator = _PermissionOrchestrator()
    adapter = MissionToolOrchestratorAdapter(
        store=SimpleNamespace(list_items=AsyncMock(return_value=[])),  # type: ignore[arg-type]
        orchestrator=orchestrator,  # type: ignore[arg-type]
        policy_resolver=_PermissionPolicyResolver(),  # type: ignore[arg-type]
    )

    outcome = await adapter.execute(_permission_request())  # type: ignore[arg-type]

    assert outcome.status is MissionPortOutcomeStatus.WAITING
    assert outcome.pause_request is not None
    assert outcome.pause_request.reason == "permission"
    assert orchestrator.context is None


@pytest.mark.asyncio
async def test_permission_bound_tool_binds_durable_receipt_to_operation() -> None:
    orchestrator = _PermissionOrchestrator()
    adapter = MissionToolOrchestratorAdapter(
        store=SimpleNamespace(
            list_items=AsyncMock(return_value=[_permission_receipt("allow_once")])
        ),  # type: ignore[arg-type]
        orchestrator=orchestrator,  # type: ignore[arg-type]
        policy_resolver=_PermissionPolicyResolver(),  # type: ignore[arg-type]
    )

    outcome = await adapter.execute(_permission_request())  # type: ignore[arg-type]

    assert outcome.status is MissionPortOutcomeStatus.COMPLETED
    assert orchestrator.context.permission_grant_ref == "mission-item:23"


@pytest.mark.asyncio
async def test_rejected_permission_fails_without_reopening_same_pause() -> None:
    orchestrator = _PermissionOrchestrator()
    adapter = MissionToolOrchestratorAdapter(
        store=SimpleNamespace(
            list_items=AsyncMock(return_value=[_permission_receipt("reject")])
        ),  # type: ignore[arg-type]
        orchestrator=orchestrator,  # type: ignore[arg-type]
        policy_resolver=_PermissionPolicyResolver(),  # type: ignore[arg-type]
    )

    outcome = await adapter.execute(_permission_request())  # type: ignore[arg-type]

    assert outcome.status is MissionPortOutcomeStatus.FAILED
    assert outcome.pause_request is None
    assert orchestrator.context is None


@pytest.mark.asyncio
async def test_operation_journal_rejects_terminal_from_superseded_claim_token() -> None:
    outcome = ResearchToolOutcome(
        operation_id="op-stale",
        operation_key="b" * 64,
        producer="workspace_agent",
        tool_id="workspace.read_input",
        tool_version="1.0.0",
        status=ToolOutcomeStatus.SUCCESS,
        observed_at=datetime.now(UTC),
        summary="stale completion",
        verification_status=VerificationStatus.VERIFIED,
    )

    class _Store:
        async def finish_operation(self, _mission_id, _command):
            return SimpleNamespace(
                finalized=False,
                receipt=SimpleNamespace(
                    claim_token="new-claim-token-" + "n" * 32,
                    claimant="op-new-attempt",
                    receipt_json={"outcome": outcome.model_dump(mode="json")},
                ),
            )

    journal = MissionItemOperationJournal(  # type: ignore[arg-type]
        _Store(),
        operation_ttl_seconds=180,
    )
    accepted = await journal.record_terminal(
        ToolOperation(
            mission_id="mission-1",
            operation_id="op-stale",
            operation_key="b" * 64,
            command_id="command-1",
            stage_id="stage-1",
            caller_id="workspace_agent",
            caller_kind=ToolCallerKind.WORKSPACE_AGENT,
            tool_id="workspace.read_input",
            tool_version="1.0.0",
            descriptor_schema_hash="c" * 64,
            args_hash="d" * 64,
            policy_snapshot_ref="policy@hash",
            lease_epoch=2,
            attempt=1,
        ),
        outcome,
        claim_token="old-claim-token-" + "o" * 32,
    )

    assert accepted is False


@pytest.mark.asyncio
async def test_operation_journal_maps_claim_fence_conflict_to_rejection() -> None:
    class _Store:
        async def finish_operation(self, _mission_id, _command):
            raise DataServiceClientError(
                "operation claim fence",
                status_code=409,
            )

    outcome = ResearchToolOutcome(
        operation_id="op-stale",
        operation_key="e" * 64,
        producer="workspace_agent",
        tool_id="workspace.read_input",
        tool_version="1.0.0",
        status=ToolOutcomeStatus.SUCCESS,
        observed_at=datetime.now(UTC),
        summary="stale completion",
        verification_status=VerificationStatus.VERIFIED,
    )
    operation = ToolOperation(
        mission_id="mission-1",
        operation_id="op-stale",
        operation_key="e" * 64,
        command_id="command-1",
        stage_id="stage-1",
        caller_id="workspace_agent",
        caller_kind=ToolCallerKind.WORKSPACE_AGENT,
        tool_id="workspace.read_input",
        tool_version="1.0.0",
        descriptor_schema_hash="f" * 64,
        args_hash="a" * 64,
        policy_snapshot_ref="policy@hash",
        lease_epoch=2,
        attempt=1,
    )

    accepted = await MissionItemOperationJournal(  # type: ignore[arg-type]
        _Store(),
        operation_ttl_seconds=180,
    ).record_terminal(
        operation,
        outcome,
        claim_token="old-claim-token-" + "o" * 32,
    )

    assert accepted is False
