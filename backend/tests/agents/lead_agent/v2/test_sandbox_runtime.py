import json
from unittest.mock import AsyncMock

import pytest

from src.agents.lead_agent.v2.sandbox_runtime import (
    SandboxCommandExecutionError,
    run_python_script,
    run_python_smoke_check,
)
from src.sandbox.base import CommandResult
from src.subagents.v2.base import SubagentContext
from src.subagents.v2.registry import REGISTRY
from src.subagents.v2.types.sandbox import SandboxPythonSubagent


class _FakeSandbox:
    def __init__(self, result: CommandResult) -> None:
        self.result = result
        self.commands: list[tuple[str, int]] = []
        self.files: dict[str, str] = {}

    async def execute_command(self, command: str, timeout: int = 300) -> CommandResult:
        self.commands.append((command, timeout))
        return self.result

    async def write_file(self, path: str, content: str, append: bool = False) -> None:
        self.files[path] = self.files.get(path, "") + content if append else content


class _FakeProvider:
    image = "fake-python:3.13"

    def __init__(self, result: CommandResult) -> None:
        self.sandbox = _FakeSandbox(result)
        self.acquired: list[str] = []
        self.released: list[_FakeSandbox] = []

    async def acquire(self, thread_id: str) -> _FakeSandbox:
        self.acquired.append(thread_id)
        return self.sandbox

    async def release(self, sandbox: _FakeSandbox) -> None:
        self.released.append(sandbox)


def _policy() -> dict:
    return {
        "mode": "required",
        "allowed_operations": ["run_python"],
        "resource_limits": {"cpu": 1, "memory_mb": 512, "timeout_seconds": 60},
    }


@pytest.mark.asyncio
async def test_run_python_smoke_check_uses_fixed_command_and_releases_sandbox() -> None:
    stdout = json.dumps(
        {
            "ok": True,
            "mean": 5,
            "python": "3.13.0",
            "engine": "lead_agent_docker_sandbox",
        }
    )
    provider = _FakeProvider(CommandResult(stdout=stdout, stderr="", exit_code=0))

    result = await run_python_smoke_check(
        workspace_id="ws-1",
        execution_id="exec-1",
        node_id="sandbox_validation__python_smoke",
        sandbox_policy=_policy(),
        provider=provider,
    )

    assert provider.acquired == ["exec-1-sandbox_validation__python_smoke"]
    assert provider.released == [provider.sandbox]
    [(command, timeout)] = provider.sandbox.commands
    assert timeout == 60
    assert "statistics.mean(data)" in command
    assert "lead_agent_docker_sandbox" in command
    assert result["status"] == "completed"
    assert result["mean"] == 5
    assert "LeadAgentRuntime / subagent node" in result["report_markdown"]


@pytest.mark.asyncio
async def test_run_python_smoke_check_rejects_policy_without_run_python() -> None:
    provider = _FakeProvider(CommandResult(stdout="", stderr="", exit_code=0))

    with pytest.raises(PermissionError):
        await run_python_smoke_check(
            workspace_id="ws-1",
            execution_id="exec-1",
            node_id="node",
            sandbox_policy={"mode": "none", "allowed_operations": []},
            provider=provider,
        )

    assert provider.acquired == []


@pytest.mark.asyncio
async def test_run_python_script_writes_script_and_returns_report() -> None:
    stdout = json.dumps({"ok": True, "metric": 0.42})
    provider = _FakeProvider(CommandResult(stdout=stdout, stderr="", exit_code=0))

    result = await run_python_script(
        workspace_id="ws-1",
        execution_id="exec-1",
        node_id="analysis_probe",
        sandbox_policy=_policy(),
        script="import json\nprint(json.dumps({'ok': True, 'metric': 0.42}))\n",
        script_name="analysis_probe.py",
        provider=provider,
    )

    assert provider.acquired == ["exec-1-analysis_probe"]
    assert provider.released == [provider.sandbox]
    assert provider.sandbox.files["/mnt/user-data/workspace/analysis_probe.py"].startswith("import json")
    [(command, timeout)] = provider.sandbox.commands
    assert command == "python /mnt/user-data/workspace/analysis_probe.py"
    assert timeout == 60
    assert result["status"] == "completed"
    assert result["operation"] == "python_script"
    assert result["parsed_stdout"] == {"ok": True, "metric": 0.42}
    assert result["script_hash"]
    assert "analysis_probe.py" in result["report_markdown"]


@pytest.mark.asyncio
async def test_run_python_script_raises_billable_error_for_nonzero_exit() -> None:
    provider = _FakeProvider(CommandResult(stdout="", stderr="boom", exit_code=2))

    with pytest.raises(SandboxCommandExecutionError) as exc_info:
        await run_python_script(
            workspace_id="ws-1",
            execution_id="exec-1",
            node_id="analysis_probe",
            sandbox_policy=_policy(),
            script="raise SystemExit(2)\n",
            script_name="analysis_probe.py",
            provider=provider,
        )

    assert provider.released == [provider.sandbox]
    assert exc_info.value.output["status"] == "failed"
    assert exc_info.value.output["exit_code"] == 2
    assert "boom" in exc_info.value.output["report_markdown"]


@pytest.mark.asyncio
async def test_sandbox_python_subagent_runs_through_lead_runtime_context(monkeypatch) -> None:
    calls: list[dict] = []

    async def _fake_run_python_smoke_check(**kwargs):
        calls.append(kwargs)
        return {
            "status": "completed",
            "operation": "smoke_check",
            "mean": 5,
            "python": "3.13.0",
            "engine": "lead_agent_docker_sandbox",
            "stdout": "{}",
            "stderr": "",
            "exit_code": 0,
            "docker_image": "fake-python:3.13",
            "report_markdown": "ok",
        }

    monkeypatch.setattr(
        "src.subagents.v2.types.sandbox.run_python_smoke_check",
        _fake_run_python_smoke_check,
    )
    reservation_calls: list[dict] = []
    settlement_calls: list[dict] = []

    class _FakeCreditService:
        async def estimate_sandbox_reservation_credits(self, **kwargs):
            return 5

        async def estimate_sandbox_settlement_credits(self, **kwargs):
            return 1

        async def reserve_for_sandbox_operation(self, **kwargs):
            reservation_calls.append(kwargs)
            return type("Reservation", (), {"id": "reservation-1", "reserved_credits": 5})()

        async def settle_sandbox_reservation(self, **kwargs):
            settlement_calls.append(kwargs)
            return (
                type("Reservation", (), {"id": "reservation-1", "status": "settled"})(),
                type("Tx", (), {"id": "credit-tx-1", "balance_after": 9})(),
            )

    monkeypatch.setattr(
        "src.subagents.v2.types.sandbox.CreditService",
        lambda: _FakeCreditService(),
    )

    ctx = SubagentContext(
        workspace_id="ws-1",
        execution_id="exec-1",
        prompt="",
        inputs={"operation": "smoke_check", "node_id": "phase__node", "user_id": "user-1"},
        tools=[],
        capability_policy={"sandbox_policy": _policy()},
    )

    result = await SandboxPythonSubagent().run(ctx)

    assert calls[0]["workspace_id"] == "ws-1"
    assert calls[0]["execution_id"] == "exec-1"
    assert calls[0]["node_id"] == "phase__node"
    assert calls[0]["sandbox_policy"] == _policy()
    assert result.output["status"] == "completed"
    assert result.output["billing"]["transaction_id"] == "credit-tx-1"
    assert reservation_calls[0] == {
        "user_id": "user-1",
        "workspace_id": "ws-1",
        "execution_id": "exec-1",
        "node_id": "phase__node",
        "operation": "run_python",
        "estimated_credits": 5,
        "metadata": {"source": "sandbox_python_subagent"},
    }
    assert settlement_calls[0]["reservation_id"] == "reservation-1"
    assert settlement_calls[0]["operation"] == "run_python"
    assert result.tool_calls and result.tool_calls[0]["name"] == "sandbox.run_python"
    assert result.tool_calls[0]["billing"]["credits_charged"] == 1


@pytest.mark.asyncio
async def test_sandbox_python_subagent_settles_user_code_failure(monkeypatch) -> None:
    async def _fake_run_python_script(**kwargs):
        raise SandboxCommandExecutionError(
            "script failed",
            output={"status": "failed", "exit_code": 1},
        )

    monkeypatch.setattr(
        "src.subagents.v2.types.sandbox.run_python_script",
        _fake_run_python_script,
    )
    fake_credit_service = type(
        "CreditServiceStub",
        (),
        {
            "estimate_sandbox_reservation_credits": AsyncMock(return_value=5),
            "estimate_sandbox_settlement_credits": AsyncMock(return_value=1),
            "reserve_for_sandbox_operation": AsyncMock(
                return_value=type("Reservation", (), {"id": "reservation-2", "reserved_credits": 5})()
            ),
            "settle_sandbox_reservation": AsyncMock(
                return_value=(
                    type("Reservation", (), {"id": "reservation-2", "status": "settled"})(),
                    type("Tx", (), {"id": "credit-tx-2", "balance_after": 9})(),
                )
            ),
            "release_reservation": AsyncMock(),
        },
    )()
    monkeypatch.setattr(
        "src.subagents.v2.types.sandbox.CreditService",
        lambda: fake_credit_service,
    )

    ctx = SubagentContext(
        workspace_id="ws-1",
        execution_id="exec-1",
        prompt="",
        inputs={
            "operation": "python_script",
            "node_id": "phase__probe",
            "user_id": "user-1",
            "script": "raise SystemExit(1)",
        },
        tools=[],
        capability_policy={"sandbox_policy": _policy()},
    )

    with pytest.raises(SandboxCommandExecutionError):
        await SandboxPythonSubagent().run(ctx)

    fake_credit_service.settle_sandbox_reservation.assert_awaited_once()
    fake_credit_service.release_reservation.assert_not_awaited()


@pytest.mark.asyncio
async def test_sandbox_python_subagent_requires_user_id_for_billing() -> None:
    ctx = SubagentContext(
        workspace_id="ws-1",
        execution_id="exec-1",
        prompt="",
        inputs={"operation": "smoke_check", "node_id": "phase__node"},
        tools=[],
        capability_policy={"sandbox_policy": _policy()},
    )

    with pytest.raises(ValueError, match="sandbox billing requires user_id"):
        await SandboxPythonSubagent().run(ctx)


@pytest.mark.asyncio
async def test_sandbox_python_subagent_runs_declared_python_script(monkeypatch) -> None:
    calls: list[dict] = []

    async def _fake_run_python_script(**kwargs):
        calls.append(kwargs)
        return {
            "status": "completed",
            "operation": "python_script",
            "stdout": "{}",
            "stderr": "",
            "exit_code": 0,
            "docker_image": "fake-python:3.13",
            "script_hash": "hash-1",
            "report_markdown": "script ok",
        }

    monkeypatch.setattr(
        "src.subagents.v2.types.sandbox.run_python_script",
        _fake_run_python_script,
    )
    monkeypatch.setattr(
        "src.subagents.v2.types.sandbox.CreditService",
        lambda: type(
            "CreditServiceStub",
            (),
            {
                "estimate_sandbox_reservation_credits": AsyncMock(return_value=5),
                "estimate_sandbox_settlement_credits": AsyncMock(return_value=1),
                "reserve_for_sandbox_operation": AsyncMock(
                    return_value=type("Reservation", (), {"id": "reservation-2", "reserved_credits": 5})()
                ),
                "settle_sandbox_reservation": AsyncMock(
                    return_value=(
                        type("Reservation", (), {"id": "reservation-2", "status": "settled"})(),
                        type("Tx", (), {"id": "credit-tx-2", "balance_after": 9})(),
                    )
                ),
            },
        )(),
    )

    ctx = SubagentContext(
        workspace_id="ws-1",
        execution_id="exec-1",
        prompt="",
        inputs={
            "operation": "python_script",
            "node_id": "phase__probe",
            "user_id": "user-1",
            "script": "print('ok')",
            "script_name": "probe.py",
        },
        tools=[],
        capability_policy={"sandbox_policy": _policy()},
    )

    result = await SandboxPythonSubagent().run(ctx)

    assert calls[0]["workspace_id"] == "ws-1"
    assert calls[0]["execution_id"] == "exec-1"
    assert calls[0]["node_id"] == "phase__probe"
    assert calls[0]["script"] == "print('ok')"
    assert calls[0]["script_name"] == "probe.py"
    assert result.output["operation"] == "python_script"
    assert result.tool_calls and result.tool_calls[0]["args"]["operation"] == "python_script"


def test_sandbox_python_subagent_is_registered() -> None:
    assert REGISTRY.get("sandbox_python") is SandboxPythonSubagent
