from __future__ import annotations

import asyncio

import pytest

from src.agents.harness.contracts import HarnessPolicy, HarnessRunContext
from src.agents.harness.sandbox_execution_tools import SandboxExecutionTools
from src.agents.harness.scheduler import WorkspaceToolQueueTimeout, WorkspaceToolScheduler


def _ctx(publish_event=None) -> HarnessRunContext:
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
        publish_event=publish_event,
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


class _AuditedRunner:
    async def run_python_script(self, **kwargs):
        return {
            "status": "completed",
            "stdout": "{\"ok\": true}",
            "stderr": "",
            "parsed_stdout": {"ok": True},
            "sandbox_job_id": "job-1",
            "command_audit": {
                "verdict": "pass",
                "risk_level": "low",
                "reasons": [],
                "command": {
                    "argv": [
                        "/workspace/.wenjin/env/python/bin/python",
                        "/workspace/scripts/analysis.py",
                    ],
                    "shell_command": None,
                    "cwd": "/workspace",
                    "env": {},
                    "network_profile": "none",
                    "timeout_seconds": None,
                    "output_bytes_cap": None,
                },
            },
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
async def test_run_python_sanitizes_script_name_before_runner_boundary() -> None:
    runner = _FakeRunner()
    tool = SandboxExecutionTools(
        context=_ctx(),
        policy=HarnessPolicy(permissions=frozenset({"sandbox.run_python"})),
        runner=runner,
        scheduler=WorkspaceToolScheduler(),
    )

    await tool.run_python(
        script="print('ok')",
        script_name="../../bad script",
    )

    [call] = runner.calls
    assert call["script_name"] == ".._.._bad_script.py"


@pytest.mark.asyncio
async def test_run_python_propagates_externalized_output_refs() -> None:
    class ExternalizedRunner:
        async def run_python_script(self, **kwargs):
            return {
                "status": "completed",
                "stdout": "Total output lines: 30\n\nrow 001\n\n[Full sandbox.run_python.stdout output saved to /workspace/outputs/harness/exec-1/node-1/node-1/sandbox.run_python.stdout.txt]\n\nrow 030",
                "stderr": "",
                "parsed_stdout": {},
                "sandbox_job_id": "job-1",
                "stdout_externalized": True,
                "output_refs": [
                    "/workspace/outputs/harness/exec-1/node-1/node-1/sandbox.run_python.stdout.txt"
                ],
            }

    tool = SandboxExecutionTools(
        context=_ctx(),
        policy=HarnessPolicy(
            permissions=frozenset({"sandbox.run_python"}),
            allow_package_install=True,
        ),
        runner=ExternalizedRunner(),
        scheduler=WorkspaceToolScheduler(),
    )

    result = await tool.run_python(script="print('large')", script_name="analysis.py")

    assert result.externalized
    assert result.truncated
    assert result.output_refs == (
        "/workspace/outputs/harness/exec-1/node-1/node-1/sandbox.run_python.stdout.txt",
    )


@pytest.mark.asyncio
async def test_run_python_publishes_command_audit_event() -> None:
    events: list[tuple[str, str, dict]] = []

    async def publish_event(execution_id: str, event_type: str, payload: dict) -> None:
        events.append((execution_id, event_type, payload))

    tool = SandboxExecutionTools(
        context=_ctx(publish_event=publish_event),
        policy=HarnessPolicy(
            permissions=frozenset({"sandbox.run_python"}),
            allow_package_install=True,
        ),
        runner=_AuditedRunner(),
        scheduler=WorkspaceToolScheduler(),
    )

    result = await tool.run_python(script="print({'ok': True})", script_name="analysis.py")

    assert result.structured_payload["command_audit"]["verdict"] == "pass"
    audit_events = [event for event in events if event[1] == "execution.harness.command_audit"]
    assert audit_events
    _, _, payload = audit_events[-1]
    assert payload["visibility"] == "team_visible"
    assert payload["sequence_kind"] == "audit"
    assert payload["payload"]["name"] == "sandbox.run_python"
    assert payload["payload"]["sandbox_job_id"] == "job-1"
    assert payload["payload"]["command_audit"]["risk_level"] == "low"


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
