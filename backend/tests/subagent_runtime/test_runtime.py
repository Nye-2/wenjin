from __future__ import annotations

import asyncio
from typing import Any

import pytest

from src.subagent_runtime.contracts import (
    SubagentAction,
    SubagentBudget,
    SubagentJobSpec,
    SubagentStopReason,
    SubagentToolResult,
)
from src.subagent_runtime.runtime import SubagentRuntime


def _job(job_id: str = "sj_one", **overrides: Any) -> SubagentJobSpec:
    values: dict[str, Any] = {
        "job_id": job_id,
        "operation_id": "op-parent",
        "mission_id": "mission-1",
        "workspace_id": "workspace-1",
        "model_id": "gpt-5.6-sol",
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

    async def record_progress(self, job, *, phase, summary, payload_json=None) -> None:
        self.events.append((job.job_id, phase))


class _NoTools:
    async def execute(self, request):
        raise AssertionError(f"unexpected tool call: {request.tool_name}")


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
            return SubagentAction(
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
async def test_duplicate_job_shares_one_inflight_effect_and_terminal_result() -> None:
    class Model:
        calls = 0

        async def next_action(self, job, steps, tool_results):
            self.calls += 1
            await asyncio.sleep(0.01)
            return SubagentAction(kind="complete", summary="done", result_json={"value": 1})

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
async def test_tool_failure_is_typed_and_model_can_return_safe_partial_output() -> None:
    class Model:
        async def next_action(self, job, steps, tool_results):
            if not tool_results:
                return SubagentAction(
                    kind="tool",
                    tool_name="research.search",
                    arguments={"bad": object()},
                    summary="search evidence",
                    partial_result_json={"draft": "safe partial"},
                )
            return SubagentAction(
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
    result = await runtime.run_batch(
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
                return SubagentAction(
                    kind="tool",
                    tool_name="research.search",
                    arguments={"query": "federated PEFT"},
                    summary="read the same evidence",
                )
            assert any(step.kind == "progress" and "Duplicate" in step.summary for step in steps)
            return SubagentAction(
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
    result = await runtime.run_batch(
        (_job(budget=SubagentBudget(max_turns=3, max_tool_steps=1)),),
        deadline_monotonic=asyncio.get_running_loop().time() + 2,
    )

    job_result = result.results[0]
    assert job_result.status.value == "completed"
    assert job_result.tool_steps_used == 1
    assert tools.calls == 1
    assert model.calls == 3


def test_context_contract_rejects_parent_transcript_and_recursive_depth() -> None:
    with pytest.raises(ValueError, match="forbidden parent context"):
        _job(input_scope={"full_transcript": ["secret parent context"]})
    with pytest.raises(ValueError):
        _job(depth=2)
