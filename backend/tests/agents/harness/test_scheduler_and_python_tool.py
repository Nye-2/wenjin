from __future__ import annotations

import asyncio

import pytest

from src.agents.harness.contracts import HarnessPolicy, HarnessRunContext
from src.agents.harness.sandbox_execution_tools import SandboxExecutionTools
from src.agents.harness.scheduler import WorkspaceToolQueueTimeout, WorkspaceToolScheduler


def _ctx() -> HarnessRunContext:
    return HarnessRunContext(
        workspace_id="ws-1",
        user_id="user-1",
        execution_id="exec-1",
        node_id="node-1",
        invocation_id="invocation-1",
        workspace_type="sci",
        capability_id="capability-1",
        capability_policy={
            "sandbox_policy": {
                "mode": "required",
                "allowed_operations": ["run_python", "install_python_packages"],
                "allow_package_install": True,
                "resource_limits": {"timeout_seconds": 60},
            }
        },
    )


class _FakeRunner:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def run_python_script(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "status": "completed",
            "stdout": "{\"ok\": true}",
            "stderr": "",
            "parsed_stdout": {"ok": True},
            "sandbox_job_id": "job-1",
        }


@pytest.mark.asyncio
async def test_scheduler_serializes_same_workspace_calls() -> None:
    scheduler = WorkspaceToolScheduler()
    running = 0
    max_running = 0

    async def job() -> str:
        nonlocal running, max_running
        running += 1
        max_running = max(max_running, running)
        await asyncio.sleep(0.01)
        running -= 1
        return "ok"

    result = await asyncio.gather(
        scheduler.run("ws-1", job),
        scheduler.run("ws-1", job),
    )

    assert result == ["ok", "ok"]
    assert max_running == 1


@pytest.mark.asyncio
async def test_scheduler_times_out_when_workspace_queue_is_busy() -> None:
    scheduler = WorkspaceToolScheduler()
    release = asyncio.Event()

    async def blocker() -> str:
        await release.wait()
        return "done"

    task = asyncio.create_task(scheduler.run("ws-1", blocker))
    await asyncio.sleep(0)
    with pytest.raises(WorkspaceToolQueueTimeout):
        await scheduler.run("ws-1", lambda: asyncio.sleep(0), timeout_seconds=0.001)
    release.set()
    await task


@pytest.mark.asyncio
async def test_run_python_uses_existing_sandbox_job_runner_through_scheduler() -> None:
    runner = _FakeRunner()
    tool = SandboxExecutionTools(
        context=_ctx(),
        policy=HarnessPolicy(
            permissions=frozenset({"sandbox.run_python"}),
            allow_package_install=True,
        ),
        runner=runner,
        scheduler=WorkspaceToolScheduler(),
    )

    result = await tool.run_python(
        script="print({'ok': True})",
        script_name="analysis.py",
        dependency_hints=["pandas"],
    )

    assert result.structured_payload["sandbox_job_id"] == "job-1"
    assert result.structured_payload["parsed_stdout"] == {"ok": True}
    assert "completed" in result.preview_text
    [call] = runner.calls
    assert call["workspace_id"] == "ws-1"
    assert call["execution_id"] == "exec-1"
    assert call["node_id"] == "node-1"
    assert call["sandbox_policy"]["allowed_operations"] == ["run_python", "install_python_packages"]
    assert call["dependency_hints"] == ["pandas"]


@pytest.mark.asyncio
async def test_run_python_requires_explicit_permission() -> None:
    tool = SandboxExecutionTools(
        context=_ctx(),
        policy=HarnessPolicy(),
        runner=_FakeRunner(),
        scheduler=WorkspaceToolScheduler(),
    )

    with pytest.raises(PermissionError, match="run_python"):
        await tool.run_python(script="print('no')", script_name="analysis.py")
