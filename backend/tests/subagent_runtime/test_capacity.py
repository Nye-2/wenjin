from __future__ import annotations

import asyncio

import pytest

from src.subagent_runtime.capacity import RedisSubagentCapacityLimiter
from src.subagent_runtime.contracts import SubagentJobSpec
from src.subagent_runtime.runtime import SubagentRuntime


def _job() -> SubagentJobSpec:
    return SubagentJobSpec(
        job_id="sj-capacity",
        operation_id="op-capacity",
        mission_id="mission-1",
        workspace_id="workspace-1",
        model_id="gpt-5.6-terra",
        reasoning_effort="xhigh",
        lease_owner="worker-1",
        lease_epoch=1,
        display_name="研究成员 · Lin",
        role_label="文献研究",
        task_summary="Inspect one bounded source",
        objective="Build a receipt-backed result",
    )


class _RedisConnection:
    def __init__(self, acquire_result: int) -> None:
        self.client = self
        self.acquire_result = acquire_result
        self.calls: list[tuple[object, ...]] = []

    async def eval(self, *args):
        self.calls.append(args)
        script = str(args[0])
        return 1 if "ZREM', KEYS[1]" in script else self.acquire_result


@pytest.mark.asyncio
async def test_redis_capacity_lease_is_tokenized_and_released() -> None:
    redis = _RedisConnection(acquire_result=1)
    limiter = RedisSubagentCapacityLimiter(
        redis,
        limit=4,
        lease_ttl_seconds=240,
    )

    token = await limiter.try_acquire(_job())
    assert token is not None and token.startswith("sj-capacity:")
    await limiter.release(token)

    assert redis.calls[0][3:5] == (4, 240_000)
    assert redis.calls[1][-1] == token


@pytest.mark.asyncio
async def test_saturated_global_capacity_defers_without_starting_a_job() -> None:
    class Model:
        async def next_action(self, job, steps, tool_results):
            raise AssertionError("capacity-deferred model call must not start")

    class Tools:
        async def execute(self, request):
            raise AssertionError("capacity-deferred tool call must not start")

    class Ledger:
        pass

    limiter = RedisSubagentCapacityLimiter(
        _RedisConnection(acquire_result=0),
        limit=4,
    )
    runtime = SubagentRuntime(
        model=Model(),
        tools=Tools(),
        ledger=Ledger(),  # type: ignore[arg-type]
        capacity=limiter,
    )

    result = await runtime.run_batch(
        (_job(),),
        deadline_monotonic=asyncio.get_running_loop().time() + 30,
    )

    assert result.results == ()
    assert result.pending_job_ids == ("sj-capacity",)
