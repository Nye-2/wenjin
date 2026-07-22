from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from src.contracts.model_usage import ModelUsage, ModelUsageReceipt
from src.dataservice_client.contracts.mission import (
    MissionItemDraftPayload,
    MissionLeaseClaimPayload,
)
from src.mission_runtime.adapters import (
    MissionSandboxReceiptStore,
    MissionSubagentLedger,
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
from src.subagent_runtime.contracts import (
    SubagentAction,
    SubagentJobSpec,
    SubagentModelTurn,
    SubagentToolResult,
)

from .conftest import FakeQuality, ScriptedAgent, start_request


def _lease_claim(run, *, ttl_seconds: int) -> MissionLeaseClaimPayload:
    assert run.dispatch_owner is not None
    return MissionLeaseClaimPayload(
        worker_id="worker-1",
        dispatch_owner=run.dispatch_owner,
        dispatch_epoch=run.dispatch_epoch,
        expected_state_version=run.state_version,
        ttl_seconds=ttl_seconds,
    )


@pytest.mark.asyncio
async def test_subagent_model_ledger_replay_is_idempotent(runtime_factory) -> None:
    runtime, deps = runtime_factory(agent=ScriptedAgent([]))
    receipt = await runtime.start(start_request())
    initial = await deps["store"].get(receipt.mission_id)
    assert initial is not None
    claimed = await deps["store"].claim_lease(
        receipt.mission_id,
        _lease_claim(initial, ttl_seconds=240),
    )
    job = SubagentJobSpec(
        job_id="sj-ledger-idempotent",
        operation_id="op-ledger-idempotent",
        mission_id=receipt.mission_id,
        workspace_id=claimed.workspace_id,
        model_id=claimed.model_id,
        reasoning_effort=claimed.reasoning_effort,
        lease_owner="worker-1",
        lease_epoch=claimed.lease_epoch,
        display_name="计量核验员",
        role_label="计量核验",
        task_summary="Verify one model receipt",
        objective=claimed.objective,
    )
    model_call_id = "model-call:subagent:" + "a" * 64
    usage_receipt = ModelUsageReceipt(
        model_id=job.model_id,
        provider_response_id="worker-response-idempotent",
        usage=ModelUsage(input_tokens=20, output_tokens=5, total_tokens=25),
    )
    ledger = MissionSubagentLedger(deps["store"])

    for _ in range(2):
        await ledger.record_model_call_started(
            job,
            turn=1,
            attempt=1,
            model_call_id=model_call_id,
        )
        await ledger.record_model_usage(
            job,
            turn=1,
            attempt=1,
            model_call_id=model_call_id,
            usage_receipt=usage_receipt,
        )

    items = deps["store"].items[receipt.mission_id]
    assert len(
        [item for item in items if item.item_type == "model_call_started"]
    ) == 1
    assert len([item for item in items if item.item_type == "usage_receipt"]) == 1
    run = await deps["store"].get(receipt.mission_id)
    assert run is not None
    assert run.snapshot_json["resource_usage"]["model_calls"] == 1
    assert run.snapshot_json["resource_usage"]["total_tokens"] == 25


@pytest.mark.asyncio
async def test_subagent_action_checkpoint_is_atomic_with_usage_and_replayable(
    runtime_factory,
) -> None:
    runtime, deps = runtime_factory(agent=ScriptedAgent([]))
    receipt = await runtime.start(start_request())
    initial = await deps["store"].get(receipt.mission_id)
    assert initial is not None
    claimed = await deps["store"].claim_lease(
        receipt.mission_id,
        _lease_claim(initial, ttl_seconds=240),
    )
    job = SubagentJobSpec(
        job_id="sj-action-checkpoint",
        operation_id="op-action-checkpoint",
        mission_id=receipt.mission_id,
        workspace_id=claimed.workspace_id,
        model_id=claimed.model_id,
        reasoning_effort=claimed.reasoning_effort,
        lease_owner="worker-1",
        lease_epoch=claimed.lease_epoch,
        display_name="断点核验员",
        role_label="运行时核验",
        task_summary="Persist one action checkpoint",
        objective=claimed.objective,
    )
    action = SubagentAction(
        kind="complete",
        summary="checkpointed result",
        result_json={"summary": "checkpointed result"},
    )
    usage = ModelUsageReceipt(
        model_id=job.model_id,
        provider_response_id="checkpoint-response",
        usage=ModelUsage(input_tokens=20, output_tokens=5, total_tokens=25),
    )
    ledger = MissionSubagentLedger(deps["store"])
    model_call_id = "model-call:subagent:" + "d" * 64
    await ledger.record_model_call_started(
        job,
        turn=1,
        attempt=1,
        model_call_id=model_call_id,
    )
    for _ in range(2):
        await ledger.record_model_usage_with_action(
            job,
            turn=1,
            attempt=1,
            model_call_id=model_call_id,
            usage_receipt=usage,
            action=action,
        )

    recovered = await MissionSubagentLedger(
        deps["store"]
    ).load_action_checkpoints(job)
    checkpoint_items = [
        item
        for item in deps["store"].items[receipt.mission_id]
        if item.item_type == "subagent_action_checkpoint"
    ]

    assert len(checkpoint_items) == 1
    assert len(recovered) == 1
    assert recovered[0].turn == 1
    assert recovered[0].action == action


@pytest.mark.asyncio
async def test_subagent_terminal_identity_rejects_divergent_replay(
    runtime_factory,
) -> None:
    runtime, deps = runtime_factory(agent=ScriptedAgent([]))
    receipt = await runtime.start(start_request())
    initial = await deps["store"].get(receipt.mission_id)
    assert initial is not None
    claimed = await deps["store"].claim_lease(
        receipt.mission_id,
        _lease_claim(initial, ttl_seconds=240),
    )
    job = SubagentJobSpec(
        job_id="sj-terminal-identity",
        operation_id="op-terminal-identity",
        mission_id=receipt.mission_id,
        workspace_id=claimed.workspace_id,
        model_id=claimed.model_id,
        reasoning_effort=claimed.reasoning_effort,
        lease_owner="worker-1",
        lease_epoch=claimed.lease_epoch,
        display_name="终态核验员",
        role_label="终态核验",
        task_summary="Verify one terminal identity",
        objective=claimed.objective,
    )
    ledger = MissionSubagentLedger(deps["store"])

    await ledger.record_progress(
        job,
        phase="terminal",
        summary="first terminal",
        payload_json={"result": {"version": 1}},
    )
    with pytest.raises(RuntimeError, match="divergent durable content"):
        await ledger.record_progress(
            job,
            phase="terminal",
            summary="second terminal",
            payload_json={"result": {"version": 2}},
        )

    terminal_items = [
        item
        for item in deps["store"].items[receipt.mission_id]
        if item.item_type == "subagent_progress"
        and item.payload_json.get("lifecycle_phase") == "terminal"
    ]
    assert len(terminal_items) == 1
    assert terminal_items[0].payload_json["progress_id"] == (
        "subagent-terminal:sj-terminal-identity"
    )


class _CompletingWorkerModel:
    def __init__(self) -> None:
        self.calls = 0
        self.scopes: list[dict] = []
        self.tool_input_schemas: list[dict] = []
        self.context_budgets: list[int] = []
        self.tool_budgets: list[int] = []
        self.output_schemas: list[dict] = []

    async def next_action(self, job, steps, tool_results):
        self.calls += 1
        self.scopes.append(job.input_scope)
        self.tool_input_schemas.append(job.tool_input_schemas)
        self.context_budgets.append(job.budget.max_context_bytes)
        self.tool_budgets.append(job.budget.max_tool_steps)
        self.output_schemas.append(job.output_schema)
        return SubagentModelTurn(
            action=SubagentAction(
                kind="complete",
                summary="Facet evidence is ready",
                result_json={
                    "summary": "one verified facet",
                    "evidence_refs": [],
                    "artifact_refs": [],
                    "warnings": [],
                },
            ),
            usage_receipt=ModelUsageReceipt(
                model_id=job.model_id,
                provider_response_id=f"response:{job.job_id}:{self.calls}",
                usage=ModelUsage(
                    input_tokens=100,
                    output_tokens=25,
                    total_tokens=125,
                ),
            ),
        )


class _NoSubagentTools:
    def input_schemas(self, tool_ids):
        return {
            tool_id: {
                "type": "object",
                "properties": {"candidate_ref": {"type": "string"}},
                "required": ["candidate_ref"],
                "additionalProperties": False,
            }
            for tool_id in tool_ids
        }

    async def execute(self, request):
        raise AssertionError(f"unexpected subagent tool call: {request.tool_name}")


class _CandidateContextTools(_NoSubagentTools):
    async def execute(self, request):
        assert request.tool_name == "artifact.read_candidate"
        assert request.arguments == {"candidate_ref": "artifact-candidate:" + "1" * 64}
        return SubagentToolResult(
            status="completed",
            summary="artifact candidate loaded",
            payload_json={"preview_text": "candidate"},
            evidence_refs=("artifact-candidate:" + "1" * 64,),
        )


class _FailIfCalledWorkerModel:
    async def next_action(self, job, steps, tool_results):
        raise AssertionError(f"durable result was not adopted for {job.job_id}")


class _UnmeteredSuccessfulWorkerModel:
    async def next_action(self, job, steps, tool_results):
        del job, steps, tool_results
        return SimpleNamespace(
            action=SubagentAction(
                kind="complete",
                summary="Unmetered semantic result",
                result_json={"summary": "must not be accepted"},
            ),
            usage_receipt=None,
        )


class _AuditingWorkerModel(_CompletingWorkerModel):
    async def next_action(self, job, steps, tool_results):
        self.calls += 1
        self.output_schemas.append(job.output_schema)
        properties = job.output_schema["properties"]
        result = {
            "summary": "The supplied candidate was audited against the requested concern.",
            "evidence_refs": list(job.selected_refs),
            "artifact_refs": list(job.selected_refs),
            "warnings": [],
        }
        if "findings" in properties:
            result["findings"] = ["No unsupported claim was found in the bounded sample."]
        if "repair_actions" in properties:
            result["repair_actions"] = []
        if "reproducibility_findings" in properties:
            result["reproducibility_findings"] = []
        return SubagentModelTurn(
            action=SubagentAction(
                kind="complete",
                summary="Pinned audit is ready",
                result_json=result,
            ),
            usage_receipt=ModelUsageReceipt(
                model_id=job.model_id,
                provider_response_id=f"audit-response:{job.job_id}:{self.calls}",
                usage=ModelUsage(
                    input_tokens=100,
                    output_tokens=25,
                    total_tokens=125,
                ),
            ),
        )


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


def _audit_spawn_decision() -> MissionAgentDecision:
    return MissionAgentDecision(
        decision_id="decision-review-1",
        kind="subagent",
        operation_id="review-1",
        stage_id="problem_understanding",
        summary="Delegate one bounded candidate audit",
        payload_json={
            "task_summary": "Review the pending problem brief",
            "input_scope": {
                "display_name": "挑刺专家 · 清和",
                "role_label": "按需质量审计",
                "candidate_ref": "artifact-candidate:" + "1" * 64,
                "selected_refs": ["artifact-candidate:" + "1" * 64],
                "worker_skill_id": "quality-critic",
                "budget": {"max_context_bytes": 4_096, "max_tool_steps": 1},
            },
        },
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
    usage = [
        item
        for item in items
        if item.item_type == "usage_receipt"
        and item.producer == progress[0].producer
    ]
    assert len(usage) == 1
    assert usage[0].payload_json["job_id"] == progress[0].payload_json["job_id"]
    assert usage[0].payload_json["usage"]["total_tokens"] == 125
    started = next(
        item
        for item in items
        if item.item_type == "model_call_started"
        and item.producer == progress[0].producer
    )
    assert usage[0].operation_id == started.operation_id
    assert usage[0].payload_json["turn"] == started.payload_json["turn"] == 1
    assert usage[0].payload_json["attempt"] == started.payload_json["attempt"] == 1
    completed = next(item for item in items if item.item_type == "subagent_completed")
    assert completed.payload_json["jobs"][0]["display_name"] == "文献猎手 · Lin"
    assert "full_transcript" not in str(completed.payload_json)


@pytest.mark.asyncio
async def test_subagent_terminal_progress_ack_loss_adopts_durable_terminal(
    runtime_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _CompletingWorkerModel()
    runtime, deps = runtime_factory(
        agent=ScriptedAgent([_spawn_decision(), _complete_decision()])
    )
    runtime.subagents = MissionSubagentRuntimeAdapter(
        store=deps["store"],
        model=model,
        tools=_NoSubagentTools(),  # type: ignore[arg-type]
        monotonic_clock=deps["clock"].monotonic,
    )
    original_append = deps["store"].append_items
    terminal_ack_lost = False

    async def append_with_lost_terminal_ack(mission_id, command):
        nonlocal terminal_ack_lost
        result = await original_append(mission_id, command)
        if (
            not terminal_ack_lost
            and any(
                item.item_type == "subagent_progress"
                and item.payload_json.get("lifecycle_phase") == "terminal"
                for item in command.items
            )
        ):
            terminal_ack_lost = True
            raise RuntimeError("subagent terminal response ACK lost")
        return result

    monkeypatch.setattr(
        deps["store"],
        "append_items",
        append_with_lost_terminal_ack,
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
                            "quality_focus": [
                                "Return a bounded evidence brief"
                            ],
                        },
                        "allowed_tool_ids": [],
                    }
                },
            }
        )
    )

    telemetry = await runtime.run_slice(
        receipt.mission_id,
        worker_id="worker-1",
    )
    run = await deps["store"].get(receipt.mission_id)
    terminal_progress = [
        item
        for item in deps["store"].items[receipt.mission_id]
        if item.item_type == "subagent_progress"
        and item.payload_json.get("lifecycle_phase") == "terminal"
    ]
    parent_terminal = [
        item
        for item in deps["store"].items[receipt.mission_id]
        if item.item_type == "subagent_completed"
    ]

    assert terminal_ack_lost is True
    assert telemetry.outcome is MissionSliceOutcome.COMPLETED
    assert run is not None and run.status.value == "completed"
    assert run.active_subagent_count == 0
    assert model.calls == 1
    assert len(terminal_progress) == 1
    assert len(parent_terminal) == 1
    assert parent_terminal[0].phase.value == "completed"


@pytest.mark.asyncio
async def test_subagent_receives_canonical_input_schema_for_each_allowed_tool(
    runtime_factory,
) -> None:
    model = _CompletingWorkerModel()
    runtime, deps = runtime_factory(agent=ScriptedAgent([_audit_spawn_decision(), _complete_decision()]))
    runtime.subagents = MissionSubagentRuntimeAdapter(
        store=deps["store"],
        model=model,
        tools=_CandidateContextTools(),  # type: ignore[arg-type]
        monotonic_clock=deps["clock"].monotonic,
    )
    receipt = await runtime.start(
        start_request(
            runtime_context_json={
                "tool_policy": {"allowed_tool_ids": ["artifact.read_candidate"]},
                "worker_skill_snapshots": {
                    "quality-critic": {
                        "content_hash": "b" * 64,
                        "contract": {
                            "id": "quality-critic",
                            "output_contract": {"type": "object"},
                            "quality_focus": ["Return a bounded diagnostic audit"],
                        },
                        "allowed_tool_ids": ["artifact.read_candidate"],
                    }
                },
            }
        )
    )

    telemetry = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")

    assert telemetry.outcome is MissionSliceOutcome.COMPLETED
    assert model.tool_input_schemas == [
        {
            "artifact.read_candidate": {
                "type": "object",
                "properties": {"candidate_ref": {"type": "string"}},
                "required": ["candidate_ref"],
                "additionalProperties": False,
            }
        }
    ]
    assert model.context_budgets == [24_000]
    assert model.tool_budgets == [8]


@pytest.mark.asyncio
async def test_on_demand_critic_uses_pinned_schema_without_stage_authority(
    runtime_factory,
) -> None:
    model = _AuditingWorkerModel()
    runtime, deps = runtime_factory(agent=ScriptedAgent([]))
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
                "stage_contracts": {
                    "problem_understanding": {
                        "schema_version": "stage_acceptance_contract.v2",
                        "contract_id": "math.problem_understanding",
                        "version": 1,
                        "mission_policy_id": "sci_research",
                        "workspace_type": "sci",
                        "stage_id": "problem_understanding",
                        "stage_goal": "Understand the supplied problem.",
                        "minimum_criteria": [
                            {
                                "criterion_id": "question_inventory",
                                "description": "Every requested question is identified.",
                            }
                        ],
                        "allowed_actions_if_failed": [
                            "revise_existing",
                            "stop_execution",
                        ],
                        "advance_condition": "The inventory passes.",
                        "stop_condition": "The problem cannot be parsed.",
                    }
                },
                "worker_skill_snapshots": {
                    "quality-critic": {
                        "content_hash": "b" * 64,
                        "contract": {
                            "id": "quality-critic",
                            "output_contract": {
                                "type": "object",
                                "required": [
                                    "summary",
                                    "evidence_refs",
                                    "artifact_refs",
                                    "warnings",
                                    "findings",
                                    "repair_actions",
                                ],
                                "properties": {
                                    "summary": {"type": "string"},
                                    "evidence_refs": {"type": "array"},
                                    "artifact_refs": {"type": "array"},
                                    "warnings": {"type": "array"},
                                    "findings": {"type": "array", "items": {"type": "string"}},
                                    "repair_actions": {"type": "array", "items": {"type": "string"}},
                                },
                            },
                            "quality_focus": ["Return a bounded review"],
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
        _lease_claim(current, ttl_seconds=120),
    )

    outcome = await runtime.subagents.run(
        SubagentExecutionRequest(
            mission=claimed,
            operation_id="specialized-review",
            task_summary="Review the problem inventory",
            stage_id="problem_understanding",
            input_scope={
                "display_name": "挑刺专家 · 清和",
                "role_label": "按需质量审计",
                "worker_skill_id": "quality-critic",
                "selected_refs": [],
            },
            frozen_context=SubagentFrozenContext(),
            deadline_monotonic=deps["clock"].monotonic() + 30,
        )
    )

    assert outcome.status.value == "completed"
    schema = model.output_schemas[0]
    assert set(schema["required"]) == {
        "summary",
        "evidence_refs",
        "artifact_refs",
        "warnings",
        "findings",
        "repair_actions",
    }
    assert set(schema["properties"]) == set(schema["required"])


@pytest.mark.asyncio
async def test_domain_auditor_schema_is_not_mutated_by_stage_contract(
    runtime_factory,
) -> None:
    model = _AuditingWorkerModel()
    runtime, deps = runtime_factory(agent=ScriptedAgent([]))
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
                "stage_contracts": {
                    "validation": {
                        "schema_version": "stage_acceptance_contract.v2",
                        "contract_id": "math.validation",
                        "version": 1,
                        "mission_policy_id": "sci_research",
                        "workspace_type": "sci",
                        "stage_id": "validation",
                        "stage_goal": "Validate reproducibility.",
                        "minimum_criteria": [
                            {
                                "criterion_id": "reproducible",
                                "description": "The result can be reproduced.",
                            }
                        ],
                        "allowed_actions_if_failed": [
                            "revise_existing",
                            "stop_execution",
                        ],
                        "advance_condition": "The result is reproducible.",
                        "stop_condition": "The result cannot be reproduced.",
                    }
                },
                "worker_skill_snapshots": {
                    "reproducibility-auditor": {
                        "content_hash": "c" * 64,
                        "contract": {
                            "id": "reproducibility-auditor",
                            "output_contract": {
                                "type": "object",
                                "required": [
                                    "summary",
                                    "evidence_refs",
                                    "artifact_refs",
                                    "warnings",
                                ],
                                "properties": {
                                    "summary": {"type": "string"},
                                    "evidence_refs": {"type": "array"},
                                    "artifact_refs": {"type": "array"},
                                    "warnings": {"type": "array"},
                                    "reproducibility_findings": {"type": "array"},
                                },
                            },
                            "quality_focus": ["Verify rerun instructions"],
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
        _lease_claim(current, ttl_seconds=120),
    )

    outcome = await runtime.subagents.run(
        SubagentExecutionRequest(
            mission=claimed,
            operation_id="reproducibility-review",
            task_summary="Review reproducibility",
            stage_id="validation",
            input_scope={
                "display_name": "复现审计员",
                "role_label": "复现审计",
                "worker_skill_id": "reproducibility-auditor",
                "selected_refs": [],
            },
            frozen_context=SubagentFrozenContext(),
            deadline_monotonic=deps["clock"].monotonic() + 30,
        )
    )

    assert outcome.status.value == "completed"
    schema = model.output_schemas[0]
    assert schema["required"] == [
        "summary",
        "evidence_refs",
        "artifact_refs",
        "warnings",
    ]
    assert set(schema["properties"]) == {
        "summary",
        "evidence_refs",
        "artifact_refs",
        "warnings",
        "reproducibility_findings",
    }


@pytest.mark.asyncio
async def test_subagent_context_budget_expands_to_fit_frozen_checkpoint(
    runtime_factory,
) -> None:
    model = _CompletingWorkerModel()
    runtime, deps = runtime_factory(agent=ScriptedAgent([]))
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
    current = await deps["store"].get(receipt.mission_id)
    assert current is not None
    claimed = await deps["store"].claim_lease(
        receipt.mission_id,
        _lease_claim(current, ttl_seconds=120),
    )

    outcome = await runtime.subagents.run(
        SubagentExecutionRequest(
            mission=claimed,
            operation_id="large-frozen-context",
            task_summary="Review the bounded parent checkpoint",
            input_scope={
                "display_name": "上下文复核员",
                "role_label": "研究复核",
                "worker_skill_id": "research-scout",
                "budget": {"max_context_bytes": 4_096},
            },
            frozen_context=SubagentFrozenContext(
                context_checkpoint={"brief": "问" * 30_000},
            ),
            deadline_monotonic=deps["clock"].monotonic() + 30,
        )
    )

    assert outcome.status.value == "completed"
    assert model.context_budgets[0] > 24_000


@pytest.mark.asyncio
async def test_subagent_semantic_success_without_usage_fails_closed(
    runtime_factory,
) -> None:
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
        _lease_claim(current, ttl_seconds=120),
    )
    adapter = MissionSubagentRuntimeAdapter(
        store=deps["store"],
        model=_UnmeteredSuccessfulWorkerModel(),  # type: ignore[arg-type]
        tools=_NoSubagentTools(),  # type: ignore[arg-type]
        monotonic_clock=deps["clock"].monotonic,
    )

    outcome = await adapter.run(
        SubagentExecutionRequest(
            mission=claimed,
            operation_id="unmetered-subagent",
            task_summary="Return one bounded result",
            input_scope={
                "display_name": "计量核验员",
                "role_label": "计量核验",
                "worker_skill_id": "research-scout",
            },
            frozen_context=SubagentFrozenContext(),
            deadline_monotonic=deps["clock"].monotonic() + 30,
        )
    )

    assert outcome.status.value == "failed"
    assert outcome.payload_json["jobs"][0]["stop_reason"] == "model_error"
    assert not any(
        item.item_type == "usage_receipt"
        for item in deps["store"].items[receipt.mission_id]
    )


@pytest.mark.asyncio
async def test_subagent_recovery_adopts_terminal_before_recomputing_budget(
    runtime_factory,
) -> None:
    runtime, deps = runtime_factory(agent=ScriptedAgent([]))
    receipt = await runtime.start(
        start_request(
            runtime_context_json={
                "mission_policy_snapshot": {
                    "execution_budget": {
                        "max_model_calls": 2,
                        "max_tool_operations": 10,
                        "max_subagent_jobs": 2,
                        "stop_after_total_tokens": 10_000,
                    }
                },
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
        _lease_claim(current, ttl_seconds=120),
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
    deps["store"].seed_items(
        receipt.mission_id,
        [
            MissionItemDraftPayload(
                item_type="subagent_progress",
                operation_id=request.operation_id,
                phase="progress",
                producer="prior-subagent-history",
                summary=f"prior progress {index}",
                payload_json={
                    "job_id": f"prior-job-{index}",
                    "lifecycle_phase": "progress",
                },
            )
            for index in range(100)
        ],
    )

    first = await first_runtime.run(request)
    latest = await deps["store"].get(receipt.mission_id)
    assert latest is not None
    assert latest.snapshot_json["resource_usage"]["model_calls"] == 1
    terminal = next(
        item
        for item in reversed(deps["store"].items[receipt.mission_id])
        if item.item_type == "subagent_progress"
        and item.payload_json.get("lifecycle_phase") == "terminal"
    )
    assert terminal.payload_json["frozen_budget"]["max_turns"] == 2
    restarted_runtime = MissionSubagentRuntimeAdapter(
        store=deps["store"],
        model=_FailIfCalledWorkerModel(),
        tools=_NoSubagentTools(),  # type: ignore[arg-type]
        monotonic_clock=deps["clock"].monotonic,
    )
    adopted = await restarted_runtime.run(
        request.model_copy(
            update={
                "mission": latest.model_copy(
                    update={
                        "snapshot_json": {
                            **latest.snapshot_json,
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
            heartbeat_interval_seconds=2,
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
        _lease_claim(current, ttl_seconds=120),
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
