"""Spec §6.1 — GlobalSubagentManager tracks active executors per run_id.

The manager keeps a registry: run_id -> ParallelExecutor, used by the
HTTP layer (Plan 1 Task 10) to deliver pause/resume/cancel signals to
the in-flight executor for that run.
"""
import asyncio

import pytest

from src.subagents.manager import GlobalSubagentManager
from src.subagents.parallel import ParallelExecutor


@pytest.fixture(autouse=True)
def _reset_manager_singleton():
    GlobalSubagentManager.reset()
    yield
    GlobalSubagentManager.reset()


def _make_manager() -> GlobalSubagentManager:
    """Bypass the full SubagentConfig — we only test executor registry."""
    mgr = GlobalSubagentManager.__new__(GlobalSubagentManager)
    mgr._executors = {}
    return mgr


def test_register_executor_stores_by_run_id():
    mgr = _make_manager()
    ex = ParallelExecutor(max_concurrent=2)
    mgr.register_executor("run-1", ex)
    assert mgr._executors["run-1"] is ex


def test_unregister_executor_removes_by_run_id():
    mgr = _make_manager()
    ex = ParallelExecutor(max_concurrent=2)
    mgr.register_executor("run-1", ex)
    mgr.unregister_executor("run-1")
    assert "run-1" not in mgr._executors


def test_unregister_unknown_run_is_silent():
    mgr = _make_manager()
    # No exception
    mgr.unregister_executor("never-registered")


def test_pause_run_calls_executor_pause():
    mgr = _make_manager()
    ex = ParallelExecutor(max_concurrent=2)
    mgr.register_executor("run-1", ex)
    mgr.pause_run("run-1")
    assert not ex._pause_event.is_set()


def test_resume_run_calls_executor_resume():
    mgr = _make_manager()
    ex = ParallelExecutor(max_concurrent=2)
    mgr.register_executor("run-1", ex)
    ex.pause()
    mgr.resume_run("run-1")
    assert ex._pause_event.is_set()


def test_cancel_run_calls_executor_cancel_and_unregisters():
    mgr = _make_manager()
    ex = ParallelExecutor(max_concurrent=2)
    mgr.register_executor("run-1", ex)
    mgr.cancel_run("run-1")
    assert ex._cancel_event.is_set()
    # cancel removes from registry — terminal action
    assert "run-1" not in mgr._executors


def test_pause_unknown_run_is_silent():
    mgr = _make_manager()
    # Spec §6.1 — controllers should not 500 on unknown run; just no-op.
    mgr.pause_run("never-registered")
    mgr.resume_run("never-registered")
    mgr.cancel_run("never-registered")


@pytest.mark.asyncio
async def test_native_harness_registers_and_unregisters_around_run_session(monkeypatch):
    """Spec §6.1 — NativeAgentHarness wires the executor into the manager
    for the duration of the run, so HTTP pause/cancel can reach it.
    """
    from src.agents.harness.native import NativeWenjinAgentHarness
    from src.agents.harness.contracts import AgentSessionRequest
    from src.subagents.parallel import PhaseResult, PhasedPlan, ExecutionPhase

    mgr = _make_manager()
    monkeypatch.setattr(GlobalSubagentManager, "get_instance", classmethod(lambda cls: mgr))

    captured = {"during": None, "after": None}

    async def fake_execute_plan(self, plan, *, context=None, phase_callback=None):
        # While running, the executor must be registered under its run_id
        captured["during"] = "run-x" in mgr._executors and mgr._executors["run-x"] is self
        return [PhaseResult(phase_name="p1", task_results=[])]

    monkeypatch.setattr(ParallelExecutor, "execute_plan", fake_execute_plan)

    harness = NativeWenjinAgentHarness()
    plan = PhasedPlan(phases=[ExecutionPhase(name="p1", tasks=[{"subagent_type": "x", "prompt": "y"}])])
    await harness.run_session(AgentSessionRequest(
        strategy="single",
        phased_plan=plan,
        context={"execution_session_id": "run-x"},
    ))

    captured["after"] = "run-x" in mgr._executors

    assert captured["during"] is True, "executor must be registered during run"
    assert captured["after"] is False, "executor must be unregistered after run"
