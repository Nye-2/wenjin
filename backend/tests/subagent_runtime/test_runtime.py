from __future__ import annotations

import asyncio
import itertools
from typing import Any

import pytest

from src.contracts.model_usage import (
    ModelCallTerminalOutcome,
    ModelUsage,
    ModelUsageReceipt,
)
from src.subagent_runtime.contracts import (
    SubagentAction,
    SubagentActionCheckpoint,
    SubagentBudget,
    SubagentContextRead,
    SubagentJobSpec,
    SubagentModelOutputError,
    SubagentModelTurn,
    SubagentStopReason,
    SubagentToolResult,
)
from src.subagent_runtime.runtime import SubagentRuntime, subagent_job_fingerprint

_RESPONSE_SEQUENCE = itertools.count(1)


def _usage_receipt(
    response_id: str | None = None,
    *,
    model_id: str = "gpt-5.6-sol",
) -> ModelUsageReceipt:
    return ModelUsageReceipt(
        model_id=model_id,
        provider_response_id=response_id or f"test-response-{next(_RESPONSE_SEQUENCE)}",
        usage=ModelUsage(input_tokens=10, output_tokens=5, total_tokens=15),
    )


def _model_turn(**values: Any) -> SubagentModelTurn:
    usage_receipt = values.pop("usage_receipt", _usage_receipt())
    return SubagentModelTurn(
        action=SubagentAction.model_validate(values),
        usage_receipt=usage_receipt,
    )


def _job(job_id: str = "sj_one", **overrides: Any) -> SubagentJobSpec:
    values: dict[str, Any] = {
        "job_id": job_id,
        "operation_id": "op-parent",
        "mission_id": "mission-1",
        "workspace_id": "workspace-1",
        "model_id": "gpt-5.6-sol",
        "reasoning_effort": "xhigh",
        "lease_owner": "worker-1",
        "lease_epoch": 1,
        "stage_id": "literature",
        "display_name": "文献猎手 · Lin",
        "role_label": "文献研究",
        "task_summary": "Find the strongest evidence",
        "objective": "Build an evidence-backed research position",
        "input_scope": {"query": "federated PEFT"},
        "allowed_tools": ("research.search",),
        "tool_input_schemas": {
            "research.search": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
                "additionalProperties": False,
            }
        },
        "exit_criteria": ("At least one verified source",),
    }
    values.update(overrides)
    return SubagentJobSpec(**values)


class _Ledger:
    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []
        self.progress_events: list[tuple[str, str, str, dict[str, object]]] = []
        self.usage_events: list[
            tuple[str, int, int, str, ModelUsageReceipt]
        ] = []
        self.model_call_events: list[tuple[str, int, int, str]] = []
        self.model_call_terminal_events: list[
            tuple[str, int, int, str, ModelCallTerminalOutcome]
        ] = []
        self.action_checkpoints: dict[str, list[SubagentActionCheckpoint]] = {}

    async def record_progress(self, job, *, phase, summary, payload_json=None) -> None:
        self.events.append((job.job_id, phase))
        self.progress_events.append(
            (job.job_id, phase, summary, dict(payload_json or {}))
        )

    async def record_model_usage(
        self,
        job,
        *,
        turn,
        attempt,
        model_call_id,
        usage_receipt,
    ) -> None:
        self.usage_events.append(
            (job.job_id, turn, attempt, model_call_id, usage_receipt)
        )

    async def record_model_call_started(
        self,
        job,
        *,
        turn,
        attempt,
        model_call_id,
    ) -> None:
        self.model_call_events.append(
            (job.job_id, turn, attempt, model_call_id)
        )

    async def record_model_call_terminal(
        self,
        job,
        *,
        turn,
        attempt,
        model_call_id,
        outcome,
        error_type,
        detail,
    ) -> None:
        del error_type, detail
        self.model_call_terminal_events.append(
            (job.job_id, turn, attempt, model_call_id, outcome)
        )

    async def record_model_usage_with_action(
        self,
        job,
        *,
        turn,
        attempt,
        model_call_id,
        usage_receipt,
        action,
    ) -> None:
        await self.record_model_usage(
            job,
            turn=turn,
            attempt=attempt,
            model_call_id=model_call_id,
            usage_receipt=usage_receipt,
        )
        self.action_checkpoints.setdefault(job.job_id, []).append(
            SubagentActionCheckpoint(
                job_id=job.job_id,
                operation_id=job.operation_id,
                turn=turn,
                job_fingerprint=subagent_job_fingerprint(job),
                action=action,
            )
        )

    async def load_action_checkpoints(self, job):
        return tuple(self.action_checkpoints.get(job.job_id, ()))


async def _run_until_terminal(
    runtime: SubagentRuntime,
    jobs: tuple[SubagentJobSpec, ...],
    *,
    deadline_monotonic: float,
):
    for _ in range(32):
        result = await runtime.run_batch(
            jobs,
            deadline_monotonic=deadline_monotonic,
        )
        if not result.pending_job_ids:
            return result
    raise AssertionError("subagent batch did not terminalize within its turn budget")


class _NoTools:
    async def execute(self, request):
        raise AssertionError(f"unexpected tool call: {request.tool_name}")


@pytest.mark.asyncio
async def test_worker_can_publish_a_bounded_milestone_before_completion() -> None:
    class Model:
        calls = 0

        async def next_action(self, job, steps, tool_results):
            del job, steps, tool_results
            self.calls += 1
            if self.calls == 1:
                return _model_turn(
                    kind="progress",
                    progress_kind="formula",
                    summary="已确认功率平衡式：P_风+P_光+P_购=P_负荷+P_制氢+P_制氨+P_售",
                )
            return _model_turn(
                kind="complete",
                summary="公式核验完成",
                result_json={"summary": "公式核验完成"},
            )

    ledger = _Ledger()
    runtime = SubagentRuntime(model=Model(), tools=_NoTools(), ledger=ledger)

    result = await _run_until_terminal(
        runtime,
        (_job(budget=SubagentBudget(max_turns=3, max_tool_steps=1)),),
        deadline_monotonic=asyncio.get_running_loop().time() + 2,
    )

    assert result.results[0].status.value == "completed"
    assert any(
        phase == "progress"
        and summary.startswith("已确认功率平衡式")
        and payload == {"status": "milestone", "progress_kind": "formula"}
        for _job_id, phase, summary, payload in ledger.progress_events
    )


def test_subagent_job_rejects_duplicate_selected_refs() -> None:
    ref = "artifact-candidate:" + "a" * 64

    with pytest.raises(ValueError, match="selected_refs must be unique"):
        _job(selected_refs=(ref, ref))


def test_selected_context_reads_do_not_consume_exploration_tool_budget() -> None:
    refs = ("source:1", "source:2")

    job = _job(
        selected_refs=refs,
        context_reads=tuple(
            SubagentContextRead(
                ref=ref,
                tool_name="research.search",
                arguments={"query": ref},
            )
            for ref in refs
        ),
        budget=SubagentBudget(max_turns=2, max_tool_steps=0),
    )

    assert len(job.context_reads) == 2
    assert job.budget.max_tool_steps == 0


@pytest.mark.asyncio
async def test_model_call_is_not_started_without_a_safe_completion_window() -> None:
    class Model:
        async def next_action(self, job, steps, tool_results):
            raise AssertionError("unsafe model call should not start")

    ledger = _Ledger()
    runtime = SubagentRuntime(
        model=Model(),
        tools=_NoTools(),
        ledger=ledger,
        model_call_timeout_seconds=10,
        model_call_completion_margin_seconds=15,
    )

    result = await runtime.run_batch(
        (_job(),),
        deadline_monotonic=asyncio.get_running_loop().time() + 20,
    )

    assert result.results == ()
    assert result.pending_job_ids == ("sj_one",)
    assert ledger.model_call_events == []


@pytest.mark.asyncio
async def test_tool_budget_reserves_a_final_synthesis_turn() -> None:
    class Model:
        calls = 0

        async def next_action(self, job, steps, tool_results):
            self.calls += 1
            if self.calls == 1:
                return _model_turn(
                    kind="tool",
                    summary="load one result",
                    tool_name="research.search",
                    arguments={"query": "bounded"},
                )
            assert any("Final synthesis turn" in step.summary for step in steps)
            return _model_turn(
                kind="complete",
                summary="synthesized",
                result_json={"summary": "synthesized"},
            )

    class Tools:
        calls = 0

        async def execute(self, request):
            self.calls += 1
            return SubagentToolResult(status="completed", summary="loaded")

    model = Model()
    tools = Tools()
    runtime = SubagentRuntime(model=model, tools=tools, ledger=_Ledger())

    result = await _run_until_terminal(
        runtime,
        (_job(budget=SubagentBudget(max_turns=3, max_tool_steps=1)),),
        deadline_monotonic=asyncio.get_running_loop().time() + 2,
    )

    assert result.results[0].status.value == "completed"
    assert result.results[0].tool_steps_used == 1
    assert model.calls == 2
    assert tools.calls == 1


@pytest.mark.asyncio
async def test_model_cannot_start_a_tool_after_the_parent_deadline() -> None:
    class Clock:
        value = 100.0

        def __call__(self) -> float:
            return self.value

    clock = Clock()

    class Model:
        async def next_action(self, job, steps, tool_results):
            del job, steps, tool_results
            clock.value = 111.0
            return _model_turn(
                kind="tool",
                summary="too late",
                tool_name="research.search",
                arguments={"query": "late"},
            )

    class Tools:
        calls = 0

        async def execute(self, request):
            del request
            self.calls += 1
            return SubagentToolResult(status="completed", summary="unexpected")

    tools = Tools()
    runtime = SubagentRuntime(
        model=Model(),
        tools=tools,
        ledger=_Ledger(),
        monotonic_clock=clock,
    )

    result = await runtime.run_batch((_job(),), deadline_monotonic=110.0)

    assert result.results == ()
    assert result.pending_job_ids == ("sj_one",)
    assert tools.calls == 0


@pytest.mark.asyncio
async def test_parallel_jobs_are_bounded_and_keep_isolated_context() -> None:
    class Model:
        def __init__(self) -> None:
            self.active = 0
            self.max_active = 0
            self.scopes: list[dict[str, Any]] = []

        async def next_action(self, job, steps, tool_results):
            self.scopes.append(job.input_scope)
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            await asyncio.sleep(0.01)
            self.active -= 1
            return _model_turn(
                kind="complete",
                summary=f"completed {job.job_id}",
                result_json={"summary": job.task_summary},
            )

    model = Model()
    runtime = SubagentRuntime(
        model=model,
        tools=_NoTools(),
        ledger=_Ledger(),
        max_concurrency=2,
    )
    jobs = tuple(
        _job(
            f"sj_{index}",
            task_summary=f"facet {index}",
            input_scope={"facet": index},
        )
        for index in range(4)
    )

    result = await runtime.run_batch(
        jobs,
        deadline_monotonic=asyncio.get_running_loop().time() + 2,
    )

    assert len(result.results) == 4
    assert model.max_active == 2
    assert model.scopes == [{"facet": 0}, {"facet": 1}, {"facet": 2}, {"facet": 3}]
    assert all("messages" not in scope for scope in model.scopes)


@pytest.mark.asyncio
async def test_each_successful_model_turn_records_its_measured_usage_before_action() -> None:
    class Model:
        async def next_action(self, job, steps, tool_results):
            return SubagentModelTurn(
                action=SubagentAction(
                    kind="complete",
                    summary="done",
                    result_json={"summary": "measured result"},
                ),
                usage_receipt=ModelUsageReceipt(
                    model_id=job.model_id,
                    provider_response_id="response-1",
                    usage=ModelUsage(
                        input_tokens=120,
                        cached_input_tokens=40,
                        output_tokens=30,
                        reasoning_tokens=10,
                        total_tokens=150,
                    ),
                ),
            )

    ledger = _Ledger()
    runtime = SubagentRuntime(model=Model(), tools=_NoTools(), ledger=ledger)

    result = await runtime.run_batch(
        (_job(),),
        deadline_monotonic=asyncio.get_running_loop().time() + 2,
    )

    assert result.results[0].status.value == "completed"
    assert len(ledger.usage_events) == 1
    job_id, turn, attempt, model_call_id, usage_receipt = ledger.usage_events[0]
    assert (job_id, turn, attempt) == ("sj_one", 1, 1)
    assert usage_receipt.usage.total_tokens == 150
    assert ledger.model_call_events == [
        ("sj_one", 1, 1, model_call_id)
    ]


@pytest.mark.asyncio
async def test_duplicate_job_shares_one_inflight_effect_and_terminal_result() -> None:
    class Model:
        calls = 0

        async def next_action(self, job, steps, tool_results):
            self.calls += 1
            await asyncio.sleep(0.01)
            return _model_turn(kind="complete", summary="done", result_json={"value": 1})

    model = Model()
    runtime = SubagentRuntime(model=model, tools=_NoTools(), ledger=_Ledger())
    job = _job()
    deadline = asyncio.get_running_loop().time() + 2

    first, second = await asyncio.gather(
        runtime.run_batch((job,), deadline_monotonic=deadline),
        runtime.run_batch((job,), deadline_monotonic=deadline),
    )

    assert model.calls == 1
    assert first.results[0] == second.results[0]

    with pytest.raises(RuntimeError, match="different semantic request"):
        await runtime.run_batch(
            (_job(input_scope={"query": "a different task"}),),
            deadline_monotonic=deadline,
        )


@pytest.mark.asyncio
async def test_transient_model_failure_retries_without_losing_worker_context() -> None:
    class RateLimitError(Exception):
        status_code = 429
        usage_not_incurred = True

    class Model:
        calls = 0

        async def next_action(self, job, steps, tool_results):
            self.calls += 1
            if self.calls == 1:
                raise RateLimitError("provider busy")
            return _model_turn(
                kind="complete",
                summary="done",
                result_json={"summary": "Audit completed from retained context."},
            )

    delays: list[float] = []

    async def sleep(delay: float) -> None:
        delays.append(delay)

    model = Model()
    ledger = _Ledger()
    runtime = SubagentRuntime(
        model=model,
        tools=_NoTools(),
        ledger=ledger,
        sleep=sleep,
    )

    result = await runtime.run_batch(
        (_job(),),
        deadline_monotonic=asyncio.get_running_loop().time() + 300,
    )

    assert model.calls == 2
    assert len(delays) == 1
    assert delays[0] >= 45
    assert result.results[0].result_json == {
        "summary": "Audit completed from retained context."
    }
    assert ("sj_one", "progress") in ledger.events
    assert len(ledger.model_call_terminal_events) == 1
    assert ledger.model_call_terminal_events[0][-1] is (
        ModelCallTerminalOutcome.FAILED
    )


@pytest.mark.asyncio
async def test_unknown_model_failure_records_unresolved_terminal_without_retry() -> None:
    class Model:
        calls = 0

        async def next_action(self, job, steps, tool_results):
            del job, steps, tool_results
            self.calls += 1
            raise TimeoutError("provider response state is unknown")

    model = Model()
    ledger = _Ledger()
    runtime = SubagentRuntime(model=model, tools=_NoTools(), ledger=ledger)

    result = await runtime.run_batch(
        (_job(),),
        deadline_monotonic=asyncio.get_running_loop().time() + 2,
    )

    assert model.calls == 1
    assert result.results[0].status.value == "failed"
    assert result.results[0].stop_reason.value == "model_error"
    assert ledger.usage_events == []
    assert len(ledger.model_call_terminal_events) == 1
    assert ledger.model_call_terminal_events[0][-1] is (
        ModelCallTerminalOutcome.UNRESOLVED
    )


@pytest.mark.asyncio
async def test_cancelling_parent_batch_reaps_inflight_subagent_task() -> None:
    started = asyncio.Event()
    cancelled = asyncio.Event()

    class Model:
        async def next_action(self, job, steps, tool_results):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

    runtime = SubagentRuntime(model=Model(), tools=_NoTools(), ledger=_Ledger())
    batch = asyncio.create_task(
        runtime.run_batch(
            (_job(),),
            deadline_monotonic=asyncio.get_running_loop().time() + 30,
        )
    )
    await asyncio.wait_for(started.wait(), timeout=1)

    batch.cancel()
    with pytest.raises(asyncio.CancelledError):
        await batch

    await asyncio.wait_for(cancelled.wait(), timeout=1)
    assert runtime._active == {}


@pytest.mark.asyncio
async def test_one_fatal_job_reaps_all_batch_siblings() -> None:
    sibling_started = asyncio.Event()
    sibling_cancelled = asyncio.Event()

    class FatalWorker(BaseException):
        pass

    class Model:
        async def next_action(self, job, steps, tool_results):
            del steps, tool_results
            if job.job_id == "sj_fatal":
                await sibling_started.wait()
                raise FatalWorker("simulated worker process loss")
            sibling_started.set()
            try:
                await asyncio.Event().wait()
            finally:
                sibling_cancelled.set()

    runtime = SubagentRuntime(
        model=Model(),
        tools=_NoTools(),
        ledger=_Ledger(),
        max_concurrency=2,
    )

    with pytest.raises(FatalWorker):
        await runtime.run_batch(
            (_job("sj_fatal"), _job("sj_sibling")),
            deadline_monotonic=asyncio.get_running_loop().time() + 30,
        )

    await asyncio.wait_for(sibling_cancelled.wait(), timeout=1)
    assert runtime._active == {}


@pytest.mark.asyncio
async def test_failed_batch_does_not_cancel_job_shared_with_another_batch() -> None:
    shared_started = asyncio.Event()
    allow_fatal = asyncio.Event()
    release_shared = asyncio.Event()
    shared_cancelled = asyncio.Event()

    class FatalWorker(BaseException):
        pass

    class Model:
        shared_calls = 0

        async def next_action(self, job, steps, tool_results):
            del steps, tool_results
            if job.job_id == "sj_fatal":
                await allow_fatal.wait()
                raise FatalWorker("simulated worker process loss")
            self.shared_calls += 1
            shared_started.set()
            try:
                await release_shared.wait()
            except asyncio.CancelledError:
                shared_cancelled.set()
                raise
            return _model_turn(
                kind="complete",
                summary="shared work completed",
                result_json={"value": 1},
            )

    model = Model()
    runtime = SubagentRuntime(
        model=model,
        tools=_NoTools(),
        ledger=_Ledger(),
        max_concurrency=2,
    )
    deadline = asyncio.get_running_loop().time() + 30
    failing_batch = asyncio.create_task(
        runtime.run_batch(
            (_job("sj_fatal"), _job("sj_shared")),
            deadline_monotonic=deadline,
        )
    )
    await asyncio.wait_for(shared_started.wait(), timeout=1)
    surviving_batch = asyncio.create_task(
        runtime.run_batch(
            (_job("sj_shared"),),
            deadline_monotonic=deadline,
        )
    )
    for _ in range(20):
        if runtime._active_waiters.get("sj_shared") == 2:
            break
        await asyncio.sleep(0)
    assert runtime._active_waiters.get("sj_shared") == 2

    allow_fatal.set()
    with pytest.raises(FatalWorker):
        await failing_batch

    assert not shared_cancelled.is_set()
    assert not surviving_batch.done()
    release_shared.set()
    result = await surviving_batch

    assert result.results[0].status.value == "completed"
    assert model.shared_calls == 1
    assert runtime._active == {}
    assert runtime._active_waiters == {}


@pytest.mark.asyncio
async def test_completed_result_uses_structured_summary_as_user_facing_brief() -> None:
    class Model:
        async def next_action(self, job, steps, tool_results):
            return _model_turn(
                kind="complete",
                summary="review complete } garbage provider residue",
                result_json={"summary": "The independent review passed."},
            )

    runtime = SubagentRuntime(model=Model(), tools=_NoTools(), ledger=_Ledger())
    result = await runtime.run_batch(
        (_job(),),
        deadline_monotonic=asyncio.get_running_loop().time() + 2,
    )

    assert result.results[0].result_brief == "The independent review passed."


@pytest.mark.asyncio
async def test_malformed_structured_model_output_retries_within_turn_budget() -> None:
    class Model:
        calls = 0

        async def next_action(self, job, steps, tool_results):
            self.calls += 1
            if self.calls == 1:
                raise SubagentModelOutputError(
                    "invalid provider frame",
                    usage_receipt=_usage_receipt("malformed-response"),
                )
            assert any("Structured worker response" in step.summary for step in steps)
            return _model_turn(
                kind="complete",
                summary="recovered",
                result_json={"summary": "recovered result"},
            )

    ledger = _Ledger()
    model = Model()
    runtime = SubagentRuntime(model=model, tools=_NoTools(), ledger=ledger)
    result = await runtime.run_batch(
        (_job(),),
        deadline_monotonic=asyncio.get_running_loop().time() + 2,
    )

    assert model.calls == 2
    assert result.results[0].status.value == "completed"
    assert result.results[0].turns_used == 2
    assert ("sj_one", "progress") in ledger.events
    assert [event[1:3] for event in ledger.usage_events] == [(1, 1), (2, 1)]
    assert [event[3] for event in ledger.usage_events] == [
        event[3] for event in ledger.model_call_events
    ]


@pytest.mark.asyncio
async def test_selected_context_is_hydrated_before_the_first_model_turn() -> None:
    class Model:
        calls = 0

        async def next_action(self, job, steps, tool_results):
            self.calls += 1
            assert len(tool_results) == 1
            assert tool_results[0].payload_json == {"body": "pinned source"}
            assert any("Load selected context" in step.summary for step in steps)
            return _model_turn(
                kind="complete",
                summary="review complete",
                result_json={"summary": "review complete"},
            )

    class Tools:
        calls = 0

        async def execute(self, request):
            self.calls += 1
            assert request.tool_name == "research.search"
            assert request.arguments == {"query": "federated PEFT"}
            return SubagentToolResult(
                status="completed",
                summary="selected source loaded",
                payload_json={"body": "pinned source"},
                evidence_refs=("source:1",),
            )

    model = Model()
    tools = Tools()
    runtime = SubagentRuntime(model=model, tools=tools, ledger=_Ledger())
    result = await runtime.run_batch(
        (
            _job(
                selected_refs=("source:1",),
                context_reads=(
                    SubagentContextRead(
                        ref="source:1",
                        tool_name="research.search",
                        arguments={"query": "federated PEFT"},
                    ),
                ),
            ),
        ),
        deadline_monotonic=asyncio.get_running_loop().time() + 2,
    )

    assert model.calls == 1
    assert tools.calls == 1
    assert result.results[0].status.value == "completed"
    assert result.results[0].tool_steps_used == 1
    assert result.results[0].evidence_refs == ("source:1",)


@pytest.mark.asyncio
async def test_completed_result_retries_unverified_references() -> None:
    class Model:
        calls = 0

        async def next_action(self, job, steps, tool_results):
            self.calls += 1
            if self.calls == 1:
                return _model_turn(
                    kind="complete",
                    summary="review complete",
                    result_json={
                        "summary": "review complete",
                        "evidence_refs": ["source:fabricated"],
                    },
                )
            assert any("not returned by its tools" in step.summary for step in steps)
            return _model_turn(
                kind="complete",
                summary="review repaired",
                result_json={
                    "summary": "review repaired",
                    "evidence_refs": ["source:1"],
                },
            )

    class Tools:
        async def execute(self, request):
            return SubagentToolResult(
                status="completed",
                summary="selected source loaded",
                evidence_refs=("source:1",),
            )

    model = Model()
    runtime = SubagentRuntime(model=model, tools=Tools(), ledger=_Ledger())
    result = await _run_until_terminal(
        runtime,
        (
            _job(
                selected_refs=("source:1",),
                context_reads=(
                    SubagentContextRead(
                        ref="source:1",
                        tool_name="research.search",
                        arguments={"query": "federated PEFT"},
                    ),
                ),
            ),
        ),
        deadline_monotonic=asyncio.get_running_loop().time() + 2,
    )

    assert model.calls == 2
    assert result.results[0].status.value == "completed"
    assert result.results[0].result_json["evidence_refs"] == ["source:1"]


@pytest.mark.asyncio
async def test_completed_result_keeps_evidence_and_artifact_receipts_typed() -> None:
    class Model:
        calls = 0

        async def next_action(self, job, steps, tool_results):
            self.calls += 1
            field = "evidence_refs" if self.calls == 1 else "artifact_refs"
            return _model_turn(
                kind="complete",
                summary="candidate inspected",
                result_json={
                    "summary": "candidate inspected",
                    field: ["sandbox-artifact:" + "b" * 64],
                },
            )

    class Tools:
        async def execute(self, request):
            return SubagentToolResult(
                status="completed",
                summary="artifact loaded",
                artifact_refs=("sandbox-artifact:" + "b" * 64,),
            )

    model = Model()
    runtime = SubagentRuntime(model=model, tools=Tools(), ledger=_Ledger())
    result = await _run_until_terminal(
        runtime,
        (
            _job(
                selected_refs=("sandbox-artifact:" + "b" * 64,),
                context_reads=(
                    SubagentContextRead(
                        ref="sandbox-artifact:" + "b" * 64,
                        tool_name="research.search",
                        arguments={"query": "artifact"},
                    ),
                ),
            ),
        ),
        deadline_monotonic=asyncio.get_running_loop().time() + 2,
    )

    assert model.calls == 2
    assert result.results[0].status.value == "completed"
    assert result.results[0].result_json["artifact_refs"] == [
        "sandbox-artifact:" + "b" * 64
    ]


@pytest.mark.asyncio
async def test_invalid_partial_result_is_not_marked_usable() -> None:
    class Model:
        calls = 0

        async def next_action(self, job, steps, tool_results):
            self.calls += 1
            if self.calls == 1:
                return _model_turn(
                    kind="tool",
                    tool_name="research.search",
                    arguments={"query": "federated PEFT"},
                    summary="list available evidence",
                    partial_result_json={"listed_documents": []},
                )
            raise RuntimeError("provider unavailable")

    class Tools:
        async def execute(self, request):
            return SubagentToolResult(
                status="completed",
                summary="evidence list loaded",
            )

    output_schema = {
        "type": "object",
        "required": ["verdict", "criterion_ids"],
        "properties": {
            "verdict": {"type": "string"},
            "criterion_ids": {"type": "array"},
        },
    }
    runtime = SubagentRuntime(model=Model(), tools=Tools(), ledger=_Ledger())
    result = await _run_until_terminal(
        runtime,
        (_job(output_schema=output_schema),),
        deadline_monotonic=asyncio.get_running_loop().time() + 2,
    )

    job_result = result.results[0]
    assert job_result.status.value == "failed"
    assert job_result.partial_result_available is False
    assert "partial_result_contract_invalid" in job_result.warnings


@pytest.mark.asyncio
async def test_partial_result_rejects_malformed_receipt_refs_without_schema_help() -> None:
    class Model:
        calls = 0

        async def next_action(self, job, steps, tool_results):
            del job, steps
            self.calls += 1
            if not tool_results:
                return _model_turn(
                    kind="tool",
                    tool_name="research.search",
                    arguments={"query": "federated PEFT"},
                    summary="load a receipt-backed source",
                )
            return _model_turn(
                kind="stop",
                summary="return the bounded partial result",
                stop_reason=SubagentStopReason.PARTIAL_RESULT_AVAILABLE,
                partial_result_json={
                    "evidence_refs": ["source:actual", 7],
                    "artifact_refs": "artifact:not-an-array",
                },
            )

    class Tools:
        async def execute(self, request):
            del request
            return SubagentToolResult(
                status="completed",
                summary="source loaded",
                evidence_refs=("source:actual",),
            )

    runtime = SubagentRuntime(model=Model(), tools=Tools(), ledger=_Ledger())
    result = await _run_until_terminal(
        runtime,
        (_job(),),
        deadline_monotonic=asyncio.get_running_loop().time() + 2,
    )

    job_result = result.results[0]
    assert job_result.status.value == "failed"
    assert job_result.partial_result_available is False
    assert "partial_result_refs_unverified" in job_result.warnings


@pytest.mark.asyncio
async def test_tool_failure_is_typed_and_model_can_return_safe_partial_output() -> None:
    class Model:
        async def next_action(self, job, steps, tool_results):
            if not tool_results:
                return _model_turn(
                    kind="tool",
                    tool_name="research.search",
                    arguments={"bad": object()},
                    summary="search evidence",
                    partial_result_json={"draft": "safe partial"},
                )
            return _model_turn(
                kind="stop",
                summary="Search arguments need repair",
                stop_reason=SubagentStopReason.MALFORMED_TOOL_ARGUMENTS,
                partial_result_json={"draft": "safe partial"},
            )

    class Tools:
        async def execute(self, request):
            return SubagentToolResult(
                status="failed",
                summary="Arguments did not match the strict schema",
                error_type="malformed_tool_arguments",
                recoverable=True,
            )

    ledger = _Ledger()
    runtime = SubagentRuntime(model=Model(), tools=Tools(), ledger=ledger)
    result = await _run_until_terminal(
        runtime,
        (_job(),),
        deadline_monotonic=asyncio.get_running_loop().time() + 2,
    )
    job_result = result.results[0]

    assert job_result.status.value == "completed"
    assert job_result.stop_reason is SubagentStopReason.MALFORMED_TOOL_ARGUMENTS
    assert job_result.partial_result_available is True
    assert job_result.result_json == {"draft": "safe partial"}
    assert ("sj_one", "progress") in ledger.events


@pytest.mark.asyncio
async def test_duplicate_successful_tool_request_is_skipped_without_spending_budget() -> None:
    class Model:
        calls = 0

        async def next_action(self, job, steps, tool_results):
            self.calls += 1
            if self.calls <= 2:
                return _model_turn(
                    kind="tool",
                    tool_name="research.search",
                    arguments={"query": "federated PEFT"},
                    summary="read the same evidence",
                )
            assert any(step.kind == "progress" and "Duplicate" in step.summary for step in steps)
            return _model_turn(
                kind="complete",
                summary="review complete",
                result_json={"summary": "one reviewed result"},
            )

    class Tools:
        calls = 0

        async def execute(self, request):
            self.calls += 1
            return SubagentToolResult(
                status="completed",
                summary="evidence loaded",
                payload_json={"body": "review this once"},
            )

    model = Model()
    tools = Tools()
    runtime = SubagentRuntime(model=model, tools=tools, ledger=_Ledger())
    result = await _run_until_terminal(
        runtime,
        (_job(budget=SubagentBudget(max_turns=3, max_tool_steps=1)),),
        deadline_monotonic=asyncio.get_running_loop().time() + 2,
    )

    job_result = result.results[0]
    assert job_result.status.value == "completed"
    assert job_result.tool_steps_used == 1
    assert tools.calls == 2
    assert model.calls == 3


def test_context_contract_rejects_parent_transcript_and_recursive_depth() -> None:
    with pytest.raises(ValueError, match="forbidden parent context"):
        _job(input_scope={"full_transcript": ["secret parent context"]})
    with pytest.raises(ValueError):
        _job(depth=2)


@pytest.mark.asyncio
async def test_nested_output_contract_is_validated_and_repaired() -> None:
    class Model:
        calls = 0

        async def next_action(self, job, steps, tool_results):
            del job, tool_results
            self.calls += 1
            if self.calls == 1:
                return _model_turn(
                    kind="complete",
                    summary="incomplete table",
                    result_json={"rows": [{"value": 1}]},
                )
            assert any("Pinned output contract validation failed" in step.summary for step in steps)
            return _model_turn(
                kind="complete",
                summary="complete table",
                result_json={"rows": [{"value": 1}, {"value": 2}]},
            )

    model = Model()
    runtime = SubagentRuntime(model=model, tools=_NoTools(), ledger=_Ledger())
    result = await _run_until_terminal(
        runtime,
        (
            _job(
                output_schema={
                    "type": "object",
                    "properties": {
                        "rows": {
                            "type": "array",
                            "minItems": 2,
                            "items": {
                                "type": "object",
                                "properties": {"value": {"type": "number"}},
                                "required": ["value"],
                                "additionalProperties": False,
                            },
                        }
                    },
                    "required": ["rows"],
                    "additionalProperties": False,
                },
                budget=SubagentBudget(max_turns=2),
            ),
        ),
        deadline_monotonic=asyncio.get_running_loop().time() + 2,
    )

    assert model.calls == 2
    assert result.results[0].status.value == "completed"
    assert len(result.results[0].result_json["rows"]) == 2


@pytest.mark.asyncio
async def test_oversized_inline_result_fails_without_fake_externalization() -> None:
    class Model:
        async def next_action(self, job, steps, tool_results):
            del job, steps, tool_results
            return _model_turn(
                kind="complete",
                summary="oversized",
                result_json={"summary": "x" * 2_000},
            )

    runtime = SubagentRuntime(model=Model(), tools=_NoTools(), ledger=_Ledger())
    result = await runtime.run_batch(
        (_job(budget=SubagentBudget(max_result_bytes=1_024)),),
        deadline_monotonic=asyncio.get_running_loop().time() + 2,
    )

    job_result = result.results[0]
    assert job_result.status.value == "failed"
    assert job_result.stop_reason is SubagentStopReason.TOKEN_CAPPED
    assert job_result.partial_result_available is False
    assert "externalization_required" not in job_result.result_json
