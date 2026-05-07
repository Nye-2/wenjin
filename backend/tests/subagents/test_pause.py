"""Spec §6.1 — pause/resume/cancel hooks on ParallelExecutor.

Pause is a phase-boundary signal: the executor finishes the current phase
naturally, then waits at the next dependency-resolved phase until resume()
or cancel() is called. cancel() sets a flag that converts the next pause
check into an asyncio.CancelledError.
"""
import asyncio

import pytest

from src.subagents.parallel import (
    ExecutionPhase,
    ParallelExecutor,
    PhaseResult,
    PhasedPlan,
)


@pytest.mark.asyncio
async def test_initial_state_unpaused_and_uncancelled():
    ex = ParallelExecutor(max_concurrent=2)
    assert ex._pause_event.is_set()
    assert not ex._cancel_event.is_set()


@pytest.mark.asyncio
async def test_pause_clears_event_resume_sets_it():
    ex = ParallelExecutor(max_concurrent=2)

    ex.pause()
    assert not ex._pause_event.is_set()

    ex.resume()
    assert ex._pause_event.is_set()


@pytest.mark.asyncio
async def test_cancel_sets_cancel_event_and_releases_pause():
    ex = ParallelExecutor(max_concurrent=2)
    ex.pause()
    ex.cancel()
    assert ex._cancel_event.is_set()
    # cancel must also release the pause so any waiters can wake and raise
    assert ex._pause_event.is_set()


@pytest.mark.asyncio
async def test_wait_if_paused_returns_immediately_when_unpaused():
    ex = ParallelExecutor(max_concurrent=2)
    await asyncio.wait_for(ex._wait_if_paused(), timeout=0.5)


@pytest.mark.asyncio
async def test_wait_if_paused_blocks_until_resume():
    ex = ParallelExecutor(max_concurrent=2)
    ex.pause()

    waiter = asyncio.create_task(ex._wait_if_paused())
    await asyncio.sleep(0.05)
    assert not waiter.done(), "waiter should be blocked while paused"

    ex.resume()
    await asyncio.wait_for(waiter, timeout=1.0)


@pytest.mark.asyncio
async def test_wait_if_paused_raises_when_cancelled():
    ex = ParallelExecutor(max_concurrent=2)
    ex.cancel()
    with pytest.raises(asyncio.CancelledError):
        await ex._wait_if_paused()


@pytest.mark.asyncio
async def test_cancel_during_pause_wakes_waiter_and_raises():
    ex = ParallelExecutor(max_concurrent=2)
    ex.pause()

    waiter = asyncio.create_task(ex._wait_if_paused())
    await asyncio.sleep(0.05)
    assert not waiter.done()

    ex.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(waiter, timeout=1.0)


@pytest.mark.asyncio
async def test_execute_plan_calls_wait_if_paused_per_phase(monkeypatch):
    """Pause check happens at every phase boundary in execute_plan."""
    ex = ParallelExecutor(max_concurrent=2)

    calls: list[str] = []
    orig = ex._wait_if_paused

    async def tracked():
        calls.append("checked")
        await orig()

    monkeypatch.setattr(ex, "_wait_if_paused", tracked)

    async def fake_phase(phase, idx, ctx):
        return PhaseResult(phase_name=phase.name, task_results=[])

    monkeypatch.setattr(ex, "_execute_phase", fake_phase)

    plan = PhasedPlan(phases=[
        ExecutionPhase(name="p1", tasks=[{"subagent_type": "x", "prompt": "a"}]),
        ExecutionPhase(name="p2", tasks=[{"subagent_type": "x", "prompt": "b"}], depends_on=["p1"]),
    ])

    await ex.execute_plan(plan)
    assert len(calls) == 2, f"expected 1 check per phase, got {len(calls)}"


@pytest.mark.asyncio
async def test_pause_blocks_execute_plan_at_next_phase(monkeypatch):
    """Calling pause() mid-run causes execute_plan to wait at next phase boundary."""
    ex = ParallelExecutor(max_concurrent=2)

    phase_started: list[str] = []

    async def fake_phase(phase, idx, ctx):
        phase_started.append(phase.name)
        return PhaseResult(phase_name=phase.name, task_results=[])

    monkeypatch.setattr(ex, "_execute_phase", fake_phase)

    plan = PhasedPlan(phases=[
        ExecutionPhase(name="p1", tasks=[{"subagent_type": "x", "prompt": "a"}]),
        ExecutionPhase(name="p2", tasks=[{"subagent_type": "x", "prompt": "b"}], depends_on=["p1"]),
    ])

    ex.pause()
    runner = asyncio.create_task(ex.execute_plan(plan))
    await asyncio.sleep(0.1)
    assert phase_started == [], "no phase should run while paused at the boundary"
    assert not runner.done()

    ex.resume()
    results = await asyncio.wait_for(runner, timeout=2.0)
    assert phase_started == ["p1", "p2"]
    assert len(results) == 2
