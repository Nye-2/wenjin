from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.dataservice_client.contracts.mission import MissionLeaseClaimPayload
from src.mission_runtime.adapters import (
    MissionSandboxReceiptStore,
    MissionSubagentRuntimeAdapter,
)
from src.mission_runtime.contracts import (
    MissionAgentDecision,
    MissionSliceLimits,
    MissionSliceOutcome,
    StageQualityVerdict,
    SubagentExecutionRequest,
    SubagentFrozenContext,
)
from src.sandbox.base import SandboxReceiptState
from src.sandbox.contracts import (
    RunPythonInput,
    SandboxMissionProvenance,
    SandboxOperationRequest,
    SandboxOperationResult,
    SandboxOperationStatus,
    SandboxRetryDisposition,
    content_hash_bytes,
    sandbox_job_id,
)
from src.subagent_runtime.contracts import SubagentAction

from .conftest import FakeQuality, ScriptedAgent, start_request


class _CompletingWorkerModel:
    def __init__(self) -> None:
        self.calls = 0
        self.scopes: list[dict] = []

    async def next_action(self, job, steps, tool_results):
        self.calls += 1
        self.scopes.append(job.input_scope)
        return SubagentAction(
            kind="complete",
            summary="Facet evidence is ready",
            result_json={
                "summary": "one verified facet",
                "evidence_refs": [],
                "artifact_refs": [],
                "warnings": [],
            },
        )


class _NoSubagentTools:
    async def execute(self, request):
        raise AssertionError(f"unexpected subagent tool call: {request.tool_name}")


class _FailIfCalledWorkerModel:
    async def next_action(self, job, steps, tool_results):
        raise AssertionError(f"durable result was not adopted for {job.job_id}")


def _spawn_decision() -> MissionAgentDecision:
    return MissionAgentDecision(
        decision_id="decision-spawn-1",
        kind="subagent",
        operation_id="spawn-1",
        stage_id="literature",
        summary="Delegate one bounded literature facet",
        payload_json={
            "task_summary": "Map communication-efficient federated PEFT",
            "input_scope": {
                "display_name": "文献猎手 · Lin",
                "role_label": "文献研究",
                "query": "communication-efficient federated PEFT",
                "worker_skill_id": "research-scout",
            },
        },
    )


def _complete_decision() -> MissionAgentDecision:
    return MissionAgentDecision(
        decision_id="decision-complete-1",
        kind="complete",
        summary="Mission result is ready",
        payload_json={"output_refs": ["mission-item:subagent"]},
    )


@pytest.mark.asyncio
async def test_subagent_ledger_conflict_recovers_without_duplicate_job_or_effect(
    runtime_factory,
) -> None:
    model = _CompletingWorkerModel()
    agent = ScriptedAgent([_spawn_decision(), _complete_decision()])
    runtime, deps = runtime_factory(agent=agent)
    runtime.subagents = MissionSubagentRuntimeAdapter(
        store=deps["store"],
        model=model,
        tools=_NoSubagentTools(),  # type: ignore[arg-type]
        monotonic_clock=deps["clock"].monotonic,
    )
    receipt = await runtime.start(
        start_request(
            runtime_context_json={
                "tool_policy": {"allowed_tool_ids": []},
                "worker_skill_snapshots": {
                    "research-scout": {
                        "content_hash": "a" * 64,
                        "contract": {
                            "id": "research-scout",
                            "output_contract": {"type": "object"},
                            "quality_focus": ["Return a bounded evidence brief"],
                        },
                        "allowed_tool_ids": [],
                    }
                },
            }
        )
    )

    telemetry = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    run = await deps["store"].get(receipt.mission_id)
    items = deps["store"].items[receipt.mission_id]

    assert telemetry.outcome is MissionSliceOutcome.COMPLETED
    assert run is not None and run.status.value == "completed"
    assert run.active_subagent_count == 0
    assert model.calls == 1
    assert model.scopes == [{"query": "communication-efficient federated PEFT"}]
    assert len([item for item in items if item.item_type == "subagent_spawned"]) == 1
    assert len([item for item in items if item.item_type == "subagent_completed"]) == 1
    spawned = next(item for item in items if item.item_type == "subagent_spawned")
    assert spawned.payload_json["frozen_context"]["prior_output_briefs"]
    progress = [item for item in items if item.item_type == "subagent_progress"]
    assert [item.payload_json["lifecycle_phase"] for item in progress] == [
        "running",
        "terminal",
    ]
    completed = next(item for item in items if item.item_type == "subagent_completed")
    assert completed.payload_json["jobs"][0]["display_name"] == "文献猎手 · Lin"
    assert "full_transcript" not in str(completed.payload_json)


@pytest.mark.asyncio
async def test_fresh_subagent_runtime_adopts_durable_terminal_result(runtime_factory) -> None:
    runtime, deps = runtime_factory(agent=ScriptedAgent([]))
    receipt = await runtime.start(
        start_request(
            runtime_context_json={
                "tool_policy": {"allowed_tool_ids": []},
                "worker_skill_snapshots": {
                    "research-scout": {
                        "content_hash": "a" * 64,
                        "contract": {
                            "id": "research-scout",
                            "output_contract": {"type": "object"},
                            "quality_focus": ["Return a bounded evidence brief"],
                        },
                        "allowed_tool_ids": [],
                    }
                },
            }
        )
    )
    current = await deps["store"].get(receipt.mission_id)
    assert current is not None
    claimed = await deps["store"].claim_lease(
        receipt.mission_id,
        MissionLeaseClaimPayload(
            worker_id="worker-1",
            expected_state_version=current.state_version,
            ttl_seconds=120,
        ),
    )
    request = SubagentExecutionRequest(
        mission=claimed,
        operation_id="restart-safe-subagent",
        task_summary="Map communication-efficient federated PEFT",
        stage_id="literature",
        input_scope={
            "display_name": "文献猎手 · Lin",
            "role_label": "文献研究",
            "query": "communication-efficient federated PEFT",
            "worker_skill_id": "research-scout",
        },
        frozen_context=SubagentFrozenContext(
            context_checkpoint_ref="mission-item:checkpoint-1",
            context_checkpoint={"stage": "literature"},
            prior_output_briefs=("Pinned parent brief",),
        ),
        deadline_monotonic=deps["clock"].monotonic() + 30,
    )
    first_model = _CompletingWorkerModel()
    first_runtime = MissionSubagentRuntimeAdapter(
        store=deps["store"],
        model=first_model,
        tools=_NoSubagentTools(),  # type: ignore[arg-type]
        monotonic_clock=deps["clock"].monotonic,
    )

    first = await first_runtime.run(request)
    restarted_runtime = MissionSubagentRuntimeAdapter(
        store=deps["store"],
        model=_FailIfCalledWorkerModel(),
        tools=_NoSubagentTools(),  # type: ignore[arg-type]
        monotonic_clock=deps["clock"].monotonic,
    )
    adopted = await restarted_runtime.run(
        request.model_copy(
            update={
                "mission": claimed.model_copy(
                    update={
                        "snapshot_json": {
                            **claimed.snapshot_json,
                            "context_checkpoint_summary": {"stage": "changed later"},
                        }
                    }
                )
            }
        )
    )

    assert first_model.calls == 1
    assert adopted == first


@pytest.mark.asyncio
async def test_quality_revise_keeps_stage_running_and_records_repair_direction(
    runtime_factory,
) -> None:
    decision = MissionAgentDecision(
        decision_id="decision-quality-1",
        kind="quality",
        operation_id="quality-1",
        stage_id="research_question",
        summary="Evaluate the research question stage",
        payload_json={"candidate_refs": ["mission-item:12"]},
    )
    runtime, deps = runtime_factory(
        agent=ScriptedAgent([decision]),
        quality=FakeQuality(StageQualityVerdict.REVISE),
        limits=MissionSliceLimits(
            wall_time_seconds=10,
            shutdown_margin_seconds=1,
            lease_ttl_seconds=20,
            max_model_turns=1,
            max_tool_steps=4,
        ),
    )
    receipt = await runtime.start(start_request())

    telemetry = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    run = await deps["store"].get(receipt.mission_id)
    quality_items = [item for item in deps["store"].items[receipt.mission_id] if item.item_type == "quality_check"]

    assert telemetry.outcome is MissionSliceOutcome.YIELDED
    assert run is not None and run.status.value == "running"
    assert run.snapshot_json["next_actions"] == ["revise_current_stage"]
    assert quality_items[-1].payload_json["verdict"] == "revise"


@pytest.mark.asyncio
async def test_sandbox_terminal_receipt_is_adopted_from_mission_items(
    runtime_factory,
) -> None:
    runtime, deps = runtime_factory(agent=ScriptedAgent([]))
    receipt = await runtime.start(start_request())
    current = await deps["store"].get(receipt.mission_id)
    assert current is not None
    claimed = await deps["store"].claim_lease(
        receipt.mission_id,
        MissionLeaseClaimPayload(
            worker_id="worker-1",
            expected_state_version=current.state_version,
            ttl_seconds=120,
        ),
    )
    operation_input = RunPythonInput(script="print('ok')\n")
    request = SandboxOperationRequest.build(
        provenance=SandboxMissionProvenance(
            workspace_id=claimed.workspace_id,
            mission_id=claimed.mission_id,
            mission_item_seq=1,
            subagent_id="sj_receipt",
            lease_epoch=claimed.lease_epoch,
        ),
        operation_input=operation_input,
        image_digest=f"sha256:{'a' * 64}",
        input_hashes={"script": content_hash_bytes(operation_input.script.encode())},
    )
    job_id = sandbox_job_id(request.operation_key)
    store = MissionSandboxReceiptStore(deps["store"])

    first = await store.claim(request, sandbox_job_id=job_id)
    now = datetime.now(UTC)
    result = SandboxOperationResult(
        operation_key=request.operation_key,
        sandbox_job_id=job_id,
        provenance=request.provenance,
        operation=request.operation_input.kind,
        image_digest=request.image_digest,
        policy_version=request.policy_version,
        command_schema_version=request.command_schema_version,
        status=SandboxOperationStatus.SUCCEEDED,
        retry_disposition=SandboxRetryDisposition.REUSE_RECEIPT,
        exit_code=0,
        started_at=now,
        finished_at=now,
    )
    await store.finalize(result)

    restarted_store = MissionSandboxReceiptStore(deps["store"])
    durable = await restarted_store.get(claimed.mission_id, request.operation_key)
    inspected = await restarted_store.inspect(
        claimed.mission_id,
        request.operation_key,
    )
    adopted = await restarted_store.claim(request, sandbox_job_id=job_id)

    assert first.acquired is True
    assert adopted.state is SandboxReceiptState.TERMINAL
    assert adopted.acquired is False
    assert adopted.existing_result == result
    assert durable == result
    assert inspected is not None
    assert inspected.existing_result == result
