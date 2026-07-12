from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from src.dataservice_client.contracts.mission import MissionLeaseClaimPayload
from src.dataservice_client.errors import DataServiceClientError
from src.mission_runtime.contracts import (
    BillingOutcome,
    MissionAgentDecision,
    MissionPauseRequest,
    MissionPortOutcome,
    MissionPortOutcomeStatus,
    MissionSliceLimits,
    MissionSliceOutcome,
)
from src.mission_runtime.reconciler import MissionReconciler
from src.mission_runtime.runtime import MissionResumeRequestMismatchError

from .conftest import (
    FakeEvents,
    FakeMissionStore,
    FakeQuality,
    FakeTools,
    FakeWakeups,
    MutableClock,
    ScriptedAgent,
    SimulatedWorkerCrash,
    start_request,
)


def continue_decision(identifier: str) -> MissionAgentDecision:
    return MissionAgentDecision(
        decision_id=identifier,
        kind="continue",
        summary=f"continue {identifier}",
        snapshot_patch={"plan_summary": f"plan {identifier}"},
    )


def complete_decision(identifier: str = "complete-1") -> MissionAgentDecision:
    return MissionAgentDecision(
        decision_id=identifier,
        kind="complete",
        summary="Mission output is ready",
        payload_json={"output_refs": ["artifact://draft"]},
    )


def tool_decision(operation_id: str) -> MissionAgentDecision:
    return MissionAgentDecision(
        decision_id=f"decision-{operation_id}",
        kind="tool",
        operation_id=operation_id,
        summary="Run structured research tool",
        payload_json={"tool_name": "native_web_search", "arguments": {"query": "federated PEFT"}},
    )


@pytest.mark.asyncio
async def test_start_and_complete_mission(runtime_factory) -> None:
    runtime, deps = runtime_factory(agent=ScriptedAgent([complete_decision()]))

    receipt = await runtime.start(start_request())
    telemetry = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")

    run = await deps["store"].get(receipt.mission_id)
    assert receipt.created is True
    assert receipt.wakeup_published is True
    assert telemetry.outcome == MissionSliceOutcome.COMPLETED
    assert run is not None and run.status.value == "completed"
    assert run.lease_owner is None
    assert deps["billing"].settled == [receipt.mission_id]


@pytest.mark.asyncio
async def test_stage_guard_blocks_tool_before_prerequisites_pass(runtime_factory) -> None:
    tools = FakeTools()
    decision = tool_decision("guarded-tool").model_copy(update={"stage_id": "method"})
    runtime, deps = runtime_factory(
        agent=ScriptedAgent([decision, complete_decision()]),
        tools=tools,
        quality=FakeQuality(missing_prerequisites=("scope",)),
    )
    receipt = await runtime.start(
        start_request(runtime_context_json={"stage_contracts": {"method": {}}})
    )

    result = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")

    assert result.outcome == MissionSliceOutcome.COMPLETED
    assert tools.calls == []
    items = deps["store"].items[receipt.mission_id]
    assert any(
        item.item_type == "error"
        and "prerequisites" in str(item.payload_json.get("detail") or "")
        for item in items
    )


@pytest.mark.asyncio
async def test_long_mission_advances_through_multiple_bounded_slices(runtime_factory) -> None:
    limits = MissionSliceLimits(
        wall_time_seconds=10,
        shutdown_margin_seconds=1,
        lease_ttl_seconds=20,
        max_model_turns=1,
        max_tool_steps=4,
    )
    agent = ScriptedAgent(
        [
            continue_decision("plan-1"),
            continue_decision("plan-2"),
            complete_decision(),
        ]
    )
    runtime, deps = runtime_factory(agent=agent, limits=limits)
    receipt = await runtime.start(start_request())

    first = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    second = await runtime.run_slice(receipt.mission_id, worker_id="worker-2")
    third = await runtime.run_slice(receipt.mission_id, worker_id="worker-3")

    assert [first.outcome, second.outcome, third.outcome] == [
        MissionSliceOutcome.YIELDED,
        MissionSliceOutcome.YIELDED,
        MissionSliceOutcome.COMPLETED,
    ]
    assert first.model_turns == second.model_turns == third.model_turns == 1
    assert third.lease_epoch == 3
    checkpoints = [item for item in deps["store"].items[receipt.mission_id] if item.item_type == "context_checkpoint"]
    assert len(checkpoints) == 2


@pytest.mark.asyncio
async def test_stale_worker_cannot_write_after_lease_takeover(runtime_factory) -> None:
    clock = MutableClock()
    store = FakeMissionStore(clock)
    limits = MissionSliceLimits(
        wall_time_seconds=1,
        shutdown_margin_seconds=1,
        lease_ttl_seconds=6,
        max_model_turns=2,
        max_tool_steps=2,
    )

    async def takeover(_context: Any) -> MissionAgentDecision:
        clock.advance(7)
        current = await store.get(receipt.mission_id)
        assert current is not None
        await store.claim_lease(
            receipt.mission_id,
            MissionLeaseClaimPayload(
                worker_id="worker-new",
                expected_state_version=current.state_version,
                ttl_seconds=6,
            ),
        )
        return complete_decision()

    runtime, deps = runtime_factory(
        agent=ScriptedAgent([takeover]),
        clock=clock,
        store=store,
        limits=limits,
    )
    receipt = await runtime.start(start_request())

    telemetry = await runtime.run_slice(receipt.mission_id, worker_id="worker-old")
    run = await store.get(receipt.mission_id)

    assert telemetry.outcome == MissionSliceOutcome.YIELDED
    assert telemetry.reason == "lease_fence_lost"
    assert run is not None and run.lease_owner == "worker-new"
    assert run.status.value == "running"
    assert deps["agent"].contexts


@pytest.mark.asyncio
async def test_event_publish_failure_never_rolls_back_mission(runtime_factory) -> None:
    events = FakeEvents(fail=True)
    runtime, deps = runtime_factory(
        agent=ScriptedAgent([complete_decision()]),
        events=events,
    )

    receipt = await runtime.start(start_request())
    result = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")

    run = await deps["store"].get(receipt.mission_id)
    assert result.outcome == MissionSliceOutcome.COMPLETED
    assert run is not None and run.status.value == "completed"
    assert events.events == []


@pytest.mark.asyncio
async def test_dropped_continuation_is_recovered_by_reconciler(runtime_factory) -> None:
    failed_wakeups = FakeWakeups(fail=True)
    limits = MissionSliceLimits(
        wall_time_seconds=10,
        shutdown_margin_seconds=1,
        lease_ttl_seconds=20,
        max_model_turns=1,
        max_tool_steps=2,
    )
    runtime, deps = runtime_factory(
        agent=ScriptedAgent([continue_decision("plan-1")]),
        wakeups=failed_wakeups,
        limits=limits,
    )
    receipt = await runtime.start(start_request())
    yielded = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    due = await deps["store"].get(receipt.mission_id)

    recovered_wakeups = FakeWakeups()
    reconciler = MissionReconciler(
        store=deps["store"],
        wakeups=recovered_wakeups,
        events=deps["events"],
        clock=deps["clock"],
    )
    published = await reconciler.reconcile_once(worker_id="reconciler-1")

    assert yielded.outcome == MissionSliceOutcome.YIELDED
    assert yielded.continuation_published is False
    assert due is not None and due.next_wakeup_at is not None
    assert published == [receipt.mission_id]
    assert recovered_wakeups.published == [(receipt.mission_id, None)]


@pytest.mark.asyncio
async def test_reconciler_publish_failure_releases_dispatch_and_expiry_republishes(runtime_factory) -> None:
    runtime, deps = runtime_factory(agent=ScriptedAgent([]), wakeups=FakeWakeups(fail=True))
    receipt = await runtime.start(start_request())
    failed = MissionReconciler(
        store=deps["store"], wakeups=FakeWakeups(fail=True),
        events=deps["events"], clock=deps["clock"], lease_ttl_seconds=5,
    )
    assert await failed.reconcile_once(worker_id="reconciler-a") == []

    wakeups = FakeWakeups()
    healthy = MissionReconciler(
        store=deps["store"], wakeups=wakeups,
        events=deps["events"], clock=deps["clock"], lease_ttl_seconds=5,
    )
    assert await healthy.reconcile_once(worker_id="reconciler-b") == [receipt.mission_id]
    assert await healthy.reconcile_once(worker_id="reconciler-c") == []
    deps["clock"].advance(6)
    assert await healthy.reconcile_once(worker_id="reconciler-c") == [receipt.mission_id]


@pytest.mark.asyncio
async def test_command_arriving_during_model_turn_is_applied_at_next_safe_boundary(
    runtime_factory,
) -> None:
    clock = MutableClock()
    store = FakeMissionStore(clock)
    observed_command_contexts: list[int] = []

    async def concurrent_command(_context: Any) -> MissionAgentDecision:
        await store.append_command(
            receipt.mission_id,
            command_id="steer-1",
            command_type="correction",
            summary="Focus on Non-IID evaluation",
            payload_json={"constraint": "Non-IID"},
        )
        return continue_decision("stale-decision")

    def finish_after_command(context: Any) -> MissionAgentDecision:
        observed_command_contexts.append(len(context.pending_commands))
        return complete_decision()

    runtime, deps = runtime_factory(
        agent=ScriptedAgent([concurrent_command, finish_after_command]),
        clock=clock,
        store=store,
    )
    receipt = await runtime.start(start_request())

    result = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    run = await store.get(receipt.mission_id)

    assert result.outcome == MissionSliceOutcome.COMPLETED
    assert run is not None
    assert run.last_applied_command_seq == run.last_command_seq
    assert observed_command_contexts == [1]
    summaries = [item.summary for item in store.items[receipt.mission_id]]
    assert "continue stale-decision" not in summaries
    assert deps["agent"].contexts[0].pending_commands == []


@pytest.mark.asyncio
async def test_cancel_is_terminal_and_future_delivery_is_noop(runtime_factory) -> None:
    agent = ScriptedAgent([complete_decision()])
    runtime, deps = runtime_factory(agent=agent)
    receipt = await runtime.start(start_request())

    cancelled = await runtime.cancel(
        receipt.mission_id,
        request_id="cancel-1",
        reason="User changed direction",
    )
    replay = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")

    assert cancelled.status.value == "cancelled"
    assert replay.outcome == MissionSliceOutcome.TERMINAL
    assert replay.reason == "mission_already_terminal"
    assert agent.contexts == []
    assert deps["billing"].settled == [receipt.mission_id]


@pytest.mark.asyncio
async def test_cancel_during_model_turn_stops_stale_driver_before_dispatch(
    runtime_factory,
) -> None:
    async def cancel_during_turn(_context: Any) -> MissionAgentDecision:
        await runtime.cancel(
            receipt.mission_id,
            request_id="cancel-concurrent",
            reason="Stop now",
        )
        return tool_decision("must-not-run")

    tools = FakeTools()
    runtime, deps = runtime_factory(
        agent=ScriptedAgent([cancel_during_turn]),
        tools=tools,
    )
    receipt = await runtime.start(start_request())

    result = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    run = await deps["store"].get(receipt.mission_id)

    assert result.outcome == MissionSliceOutcome.TERMINAL
    assert result.reason == "mission_became_terminal_during_slice"
    assert run is not None and run.status.value == "cancelled"
    assert tools.calls == []


@pytest.mark.asyncio
async def test_terminal_mission_cannot_resume(runtime_factory) -> None:
    runtime, _deps = runtime_factory(agent=ScriptedAgent([complete_decision()]))
    receipt = await runtime.start(start_request())
    await runtime.run_slice(receipt.mission_id, worker_id="worker-1")

    with pytest.raises(DataServiceClientError):
        await runtime.resume(
            receipt.mission_id,
            request_id="resume-after-complete",
            input_json={"continue": True},
        )


@pytest.mark.asyncio
async def test_budget_limit_yields_only_after_checkpoint_and_lease_release(
    runtime_factory,
) -> None:
    limits = MissionSliceLimits(
        wall_time_seconds=10,
        shutdown_margin_seconds=1,
        lease_ttl_seconds=20,
        max_model_turns=1,
        max_tool_steps=2,
    )
    runtime, deps = runtime_factory(
        agent=ScriptedAgent([continue_decision("plan-1")]),
        limits=limits,
    )
    receipt = await runtime.start(start_request())

    result = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    run = await deps["store"].get(receipt.mission_id)

    assert result.outcome == MissionSliceOutcome.YIELDED
    assert run is not None and run.lease_owner is None
    assert run.next_wakeup_at is not None
    assert run.context_checkpoint_ref is not None
    checkpoint = deps["store"].items[receipt.mission_id][-1]
    assert checkpoint.item_type == "context_checkpoint"
    assert checkpoint.payload_json["version"] == 2
    assert checkpoint.payload_json["objective"] == run.objective
    assert checkpoint.payload_json["recent_decisions"][0]["type"] == "plan"


@pytest.mark.asyncio
async def test_duplicate_operation_id_does_not_repeat_tool_effect(runtime_factory) -> None:
    tools = FakeTools()
    runtime, deps = runtime_factory(
        agent=ScriptedAgent(
            [
                tool_decision("search-1"),
                tool_decision("search-1"),
                complete_decision(),
            ]
        ),
        tools=tools,
    )
    receipt = await runtime.start(start_request())

    result = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")

    assert result.outcome == MissionSliceOutcome.COMPLETED
    assert tools.calls == ["search-1"]
    assert tools.effects == {"search-1"}
    run = await deps["store"].get(receipt.mission_id)
    assert run is not None and run.status.value == "completed"


@pytest.mark.asyncio
async def test_crash_recovery_reuses_inflight_operation_id_after_higher_epoch(
    runtime_factory,
) -> None:
    clock = MutableClock()
    store = FakeMissionStore(clock)
    tools = FakeTools()
    tools.crash_once.add("search-crash")
    limits = MissionSliceLimits(
        wall_time_seconds=10,
        shutdown_margin_seconds=1,
        lease_ttl_seconds=20,
        max_model_turns=4,
        max_tool_steps=4,
    )
    runtime, deps = runtime_factory(
        agent=ScriptedAgent([tool_decision("search-crash"), complete_decision()]),
        clock=clock,
        store=store,
        tools=tools,
        limits=limits,
    )
    receipt = await runtime.start(start_request())

    with pytest.raises(SimulatedWorkerCrash):
        await runtime.run_slice(receipt.mission_id, worker_id="worker-crashed")
    crashed = await store.get(receipt.mission_id)
    assert crashed is not None and crashed.lease_owner == "worker-crashed"

    clock.advance(21)
    recovered = await runtime.run_slice(receipt.mission_id, worker_id="worker-recovery")

    assert recovered.outcome == MissionSliceOutcome.COMPLETED
    assert recovered.lease_epoch == 2
    assert tools.calls == ["search-crash", "search-crash"]
    assert tools.effects == {"search-crash"}
    terminal = await deps["store"].get(receipt.mission_id)
    assert terminal is not None and terminal.status.value == "completed"


@pytest.mark.asyncio
async def test_billing_pause_uses_waiting_status_and_can_resume(runtime_factory) -> None:
    pause = MissionPauseRequest(
        request_id="budget-1",
        reason="budget",
        summary="Confirm mission credit use",
        pending_request={"credits": 8},
    )
    runtime, deps = runtime_factory(agent=ScriptedAgent([complete_decision()]))
    deps["billing"].reservation_outcome = BillingOutcome(
        allowed=False,
        pause_request=pause,
        summary="Credits need confirmation",
    )
    receipt = await runtime.start(start_request())

    waiting = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    run = await deps["store"].get(receipt.mission_id)

    assert waiting.outcome == MissionSliceOutcome.WAITING
    assert run is not None and run.status.value == "waiting"
    assert run.snapshot_json["waiting_reason"] == "budget"
    assert run.lease_owner is None


@pytest.mark.asyncio
async def test_permission_pause_resume_matches_request_and_restores_inflight_tool(
    runtime_factory,
) -> None:
    class PausingTool:
        def __init__(self) -> None:
            self.requests: list[Any] = []

        async def execute(self, request: Any) -> MissionPortOutcome:
            self.requests.append(request)
            if len(self.requests) == 1:
                return MissionPortOutcome(
                    status=MissionPortOutcomeStatus.WAITING,
                    summary="External source access needs confirmation",
                    pause_request=MissionPauseRequest(
                        request_id="permission-1",
                        reason="permission",
                        summary="Confirm external source access",
                        pending_request={"tool_name": request.tool_name},
                    ),
                )
            assert any(item.item_type == "resume_input" and item.operation_id == "permission-1" for item in request.recent_items)
            return MissionPortOutcome(
                status=MissionPortOutcomeStatus.COMPLETED,
                summary="External source access completed",
                payload_json={"source_ref": "source://1"},
            )

    tools = PausingTool()
    runtime, deps = runtime_factory(
        agent=ScriptedAgent([tool_decision("search-permission"), complete_decision()]),
        tools=tools,
    )
    receipt = await runtime.start(start_request())

    waiting = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    with pytest.raises(MissionResumeRequestMismatchError):
        await runtime.resume(
            receipt.mission_id,
            request_id="wrong-request",
            input_json={"decision": "allow_once"},
        )
    resumed = await runtime.resume(
        receipt.mission_id,
        request_id="permission-1",
        input_json={"decision": "allow_once"},
    )
    replay = await runtime.resume(
        receipt.mission_id,
        request_id="permission-1",
        input_json={"decision": "allow_once"},
    )
    completed = await runtime.run_slice(receipt.mission_id, worker_id="worker-2")

    assert waiting.outcome == MissionSliceOutcome.WAITING
    assert resumed.state_version == replay.state_version
    assert completed.outcome == MissionSliceOutcome.COMPLETED
    assert len(tools.requests) == 2
    resume_items = [item for item in deps["store"].items[receipt.mission_id] if item.item_type == "resume_input"]
    assert len(resume_items) == 1


@pytest.mark.asyncio
async def test_completed_mission_can_retain_pending_review_items(runtime_factory) -> None:
    review_decision = MissionAgentDecision(
        decision_id="review-decision-1",
        kind="review",
        operation_id="review-op-1",
        summary="Stage one draft is reviewable",
        payload_json={"candidate_ref": "artifact://draft"},
    )
    runtime, deps = runtime_factory(agent=ScriptedAgent([review_decision, complete_decision()]))
    receipt = await runtime.start(start_request())

    result = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    run = await deps["store"].get(receipt.mission_id)

    assert result.outcome == MissionSliceOutcome.COMPLETED
    assert run is not None and run.status.value == "completed"
    assert run.pending_review_count == 1
    manifests = run.snapshot_json["review_candidate_manifests"]
    manifest = next(iter(manifests.values()))
    assert manifest["target_kind"] == "document"
    assert len(manifest["preview_hash"]) == 64


@pytest.mark.asyncio
async def test_transient_model_timeout_yields_with_backoff_without_failing(runtime_factory) -> None:
    def timeout(_context):
        raise TimeoutError("provider read timed out")

    runtime, deps = runtime_factory(agent=ScriptedAgent([timeout]))
    receipt = await runtime.start(start_request())
    wakeups_after_start = len(deps["wakeups"].published)

    result = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    run = await deps["store"].get(receipt.mission_id)

    assert result.outcome == MissionSliceOutcome.YIELDED
    assert run is not None and run.status.value == "running"
    assert run.next_wakeup_at == deps["clock"].now() + timedelta(seconds=5)
    assert len(deps["wakeups"].published) == wakeups_after_start + 1
    assert deps["wakeups"].delays[-1] == 5
    assert result.continuation_published is True
    assert run.snapshot_json["loop_guard"] == {
        "consecutive_failures": 0,
        "transient_failures": 1,
    }
    error = next(
        item for item in deps["store"].items[receipt.mission_id] if item.item_type == "error"
    )
    assert error.payload_json["recoverable"] is True
