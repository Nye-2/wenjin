from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import src.subagents.v2.types  # noqa: F401
from src.agents.contracts.task_brief import TaskBrief
from src.agents.harness.diff_tracker import build_harness_node_metadata_from_tool_calls
from src.agents.lead_agent.v2.runtime import LeadAgentRuntime
from src.subagents.v2.base import SubagentBase, SubagentContext, SubagentResult
from src.subagents.v2.registry import subagent


@subagent("team_harness_python_replan_fake")
class TeamHarnessPythonReplanFake(SubagentBase):
    calls: dict[str, int] = {}

    async def run(self, ctx: SubagentContext) -> SubagentResult:
        key = f"{ctx.execution_id}:{ctx.invocation['template_id']}"
        count = self.calls.get(key, 0) + 1
        self.calls[key] = count
        if count == 1:
            return SubagentResult(
                output={"summary": "script failed once and needs revision"},
                tool_calls=[_run_python_tool_call("python_exit_nonzero")],
                token_usage={"input": 1, "output": 1},
            )
        return SubagentResult(
            output={
                "summary": "script revised successfully",
                "received_replan_signals": ctx.inputs["team_blackboard"]["harness_replan_signals"],
            },
            tool_calls=[
                {
                    "name": "sandbox.run_python",
                    "status": "completed",
                    "execution_manifest": {
                        "schema": "wenjin.harness.run_python.execution_manifest.v1",
                        "sandbox_job_id": "job-fixed",
                        "sandbox_environment_id": "env-1",
                    },
                }
            ],
            token_usage={"input": 1, "output": 1},
        )


@subagent("team_harness_queue_timeout_fake")
class TeamHarnessQueueTimeoutFake(SubagentBase):
    async def run(self, ctx: SubagentContext) -> SubagentResult:
        return SubagentResult(
            output={"summary": "sandbox queue timed out"},
            tool_calls=[_run_python_tool_call("sandbox_queue_timeout")],
            token_usage={"input": 1, "output": 1},
        )


@subagent("team_harness_forbidden_fake")
class TeamHarnessForbiddenFake(SubagentBase):
    async def run(self, ctx: SubagentContext) -> SubagentResult:
        return SubagentResult(
            output={"summary": "tool was forbidden by policy"},
            tool_calls=[_run_python_tool_call("tool_forbidden")],
            token_usage={"input": 1, "output": 1},
        )


@subagent("team_harness_validation_replan_fake")
class TeamHarnessValidationReplanFake(SubagentBase):
    calls: dict[str, int] = {}

    async def run(self, ctx: SubagentContext) -> SubagentResult:
        key = f"{ctx.execution_id}:{ctx.invocation['template_id']}"
        count = self.calls.get(key, 0) + 1
        self.calls[key] = count
        if count == 1:
            return SubagentResult(
                output={"summary": "tool input schema failed and needs corrected args"},
                tool_calls=[_validation_tool_call()],
                token_usage={"input": 1, "output": 1},
            )
        return SubagentResult(
            output={
                "summary": "tool args revised successfully",
                "received_replan_signals": ctx.inputs["team_blackboard"]["harness_replan_signals"],
            },
            tool_calls=[
                {
                    "name": "sandbox.read_file",
                    "status": "completed",
                    "metadata": {},
                }
            ],
            token_usage={"input": 1, "output": 1},
        )


class HarnessReplanCatalogClient:
    def __init__(self, subagent_type: str) -> None:
        self.subagent_type = subagent_type

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def list_agent_templates(self, *, enabled_only: bool = True):
        from src.dataservice_client.contracts.catalog import AgentTemplatePayload

        return [
            AgentTemplatePayload(
                id="code_runner.v1",
                display_role="实验工程师",
                category="code",
                default_skills=["code-runner"],
                tool_affinity={"preferred": ["sandbox.run_python"], "can_request": []},
                risk_profile={"sandbox": "python_only"},
            )
        ]

    async def list_catalog_skills(self, *, enabled_only: bool = True):
        from src.dataservice_client.contracts.catalog import CapabilitySkillPayload

        return [
            CapabilitySkillPayload(
                id="code-runner",
                display_name="Code Runner",
                worker_type="code",
                subagent_type=self.subagent_type,
                prompt="Run and revise sandbox Python experiments.",
                config={"output_kind": "json"},
            )
        ]


def _capability() -> SimpleNamespace:
    return SimpleNamespace(
        id="sandbox_experiment",
        workspace_type="sci",
        display_name="Sandbox Experiment",
        runtime={"mode": "team_kernel", "allowed_tools": ["sandbox.run_python"]},
        graph_template={},
        definition_json={
            "mission": {"primary_surface": "rooms"},
            "team_policy": {
                "core_templates": ["code_runner.v1"],
                "optional_templates": [],
                "capability_tools": ["sandbox.run_python"],
                "capability_skills": ["code-runner"],
                "quality_pipeline": [],
                "limits": {
                    "max_iterations": 2,
                    "max_parallel_invocations": 1,
                    "max_invocations_total": 2,
                    "max_invocations_per_template": 2,
                },
            },
        },
    )


def _brief() -> TaskBrief:
    return TaskBrief(
        capability_id="sandbox_experiment",
        raw_message="run experiment",
        workspace_id="ws-1",
        user_id="user-1",
        brief={"topic": "federated LLM"},
    )


def _run_python_tool_call(failure_code: str) -> dict:
    return {
        "name": "sandbox.run_python",
        "status": "completed",
        "recoverable_error": f"{failure_code}: bounded failure",
        "error_code": failure_code,
        "execution_manifest": {
            "schema": "wenjin.harness.run_python.execution_manifest.v1",
            "sandbox_job_id": f"job-{failure_code}",
            "sandbox_environment_id": "env-1",
        },
        "failure_classification": {
            "schema": "wenjin.harness.run_python.failure_classification.v1",
            "failure_code": failure_code,
            "recoverable": failure_code in {"python_exit_nonzero", "sandbox_queue_timeout"},
        },
    }


def _validation_tool_call() -> dict:
    return {
        "name": "sandbox.read_file",
        "status": "failed",
        "error": "ValidationError: tool input validation failed",
        "metadata": {
            "recoverable_error": "ValidationError: tool input validation failed",
            "error_code": "tool_input_validation",
        },
    }


@pytest.mark.asyncio
async def test_python_exit_nonzero_replan_signal_revises_code_agent_once(monkeypatch) -> None:
    TeamHarnessPythonReplanFake.calls.clear()
    published: list[tuple[str, str, dict]] = []

    async def publish(execution_id, event_name, payload):
        published.append((execution_id, event_name, payload))

    monkeypatch.setattr(
        "src.agents.lead_agent.v2.team.kernel.dataservice_client",
        lambda: HarnessReplanCatalogClient("team_harness_python_replan_fake"),
    )
    resolver = AsyncMock()
    resolver.resolve = AsyncMock(return_value=_capability())
    runtime = LeadAgentRuntime(
        resolver=resolver,
        publish_event=publish,
        get_workspace_type=AsyncMock(return_value="sci"),
    )

    report = await runtime.run_session(execution_id="exec-harness-replan-python", brief=_brief())

    invocations = [
        payload["invocation"]
        for _, event_name, payload in published
        if event_name == "execution.team.invocation" and payload["invocation"]["status"] != "running"
    ]
    gates = [
        payload["quality_gate"]
        for _, event_name, payload in published
        if event_name == "execution.team.quality_gate"
    ]
    assert report.status == "completed"
    assert [item["iteration"] for item in invocations] == [1, 2]
    assert invocations[1]["output_report"]["received_replan_signals"][0]["failure_codes"] == [
        "python_exit_nonzero"
    ]
    assert any(
        gate["gate_id"] == "harness_replan_signal"
        and gate["next_action"] == "revise_existing"
        and gate["suggested_recruits"][0]["template_id"] == "code_runner.v1"
        for gate in gates
    )


@pytest.mark.asyncio
async def test_tool_input_validation_replan_signal_revises_same_agent_once(monkeypatch) -> None:
    TeamHarnessValidationReplanFake.calls.clear()
    published: list[tuple[str, str, dict]] = []

    async def publish(execution_id, event_name, payload):
        published.append((execution_id, event_name, payload))

    monkeypatch.setattr(
        "src.agents.lead_agent.v2.team.kernel.dataservice_client",
        lambda: HarnessReplanCatalogClient("team_harness_validation_replan_fake"),
    )
    resolver = AsyncMock()
    resolver.resolve = AsyncMock(return_value=_capability())
    runtime = LeadAgentRuntime(
        resolver=resolver,
        publish_event=publish,
        get_workspace_type=AsyncMock(return_value="sci"),
    )

    report = await runtime.run_session(execution_id="exec-harness-replan-validation", brief=_brief())

    invocations = [
        payload["invocation"]
        for _, event_name, payload in published
        if event_name == "execution.team.invocation" and payload["invocation"]["status"] != "running"
    ]
    gates = [
        payload["quality_gate"]
        for _, event_name, payload in published
        if event_name == "execution.team.quality_gate"
    ]
    assert report.status == "completed"
    assert [item["iteration"] for item in invocations] == [1, 2]
    assert invocations[1]["output_report"]["received_replan_signals"][0]["failure_codes"] == [
        "tool_input_validation"
    ]
    assert any(
        gate["gate_id"] == "harness_replan_signal"
        and gate["next_action"] == "revise_existing"
        and gate["findings"][0]["recommended_action"] == "revise_tool_call_args"
        and gate["suggested_recruits"][0]["template_id"] == "code_runner.v1"
        for gate in gates
    )


@pytest.mark.asyncio
async def test_sandbox_queue_timeout_replan_signal_does_not_loop(monkeypatch) -> None:
    published: list[tuple[str, str, dict]] = []

    async def publish(execution_id, event_name, payload):
        published.append((execution_id, event_name, payload))

    monkeypatch.setattr(
        "src.agents.lead_agent.v2.team.kernel.dataservice_client",
        lambda: HarnessReplanCatalogClient("team_harness_queue_timeout_fake"),
    )
    resolver = AsyncMock()
    resolver.resolve = AsyncMock(return_value=_capability())
    runtime = LeadAgentRuntime(
        resolver=resolver,
        publish_event=publish,
        get_workspace_type=AsyncMock(return_value="sci"),
    )

    report = await runtime.run_session(execution_id="exec-harness-replan-queue", brief=_brief())

    invocations = [
        payload["invocation"]
        for _, event_name, payload in published
        if event_name == "execution.team.invocation" and payload["invocation"]["status"] != "running"
    ]
    gates = [
        payload["quality_gate"]
        for _, event_name, payload in published
        if event_name == "execution.team.quality_gate"
    ]
    assert report.status == "completed"
    assert len(invocations) == 1
    assert any(
        gate["gate_id"] == "harness_replan_signal"
        and gate["next_action"] == "stop_with_warning"
        and gate["suggested_recruits"] == []
        for gate in gates
    )


@pytest.mark.asyncio
async def test_tool_forbidden_replan_signal_does_not_recruit_same_forbidden_tool(monkeypatch) -> None:
    published: list[tuple[str, str, dict]] = []

    async def publish(execution_id, event_name, payload):
        published.append((execution_id, event_name, payload))

    monkeypatch.setattr(
        "src.agents.lead_agent.v2.team.kernel.dataservice_client",
        lambda: HarnessReplanCatalogClient("team_harness_forbidden_fake"),
    )
    resolver = AsyncMock()
    resolver.resolve = AsyncMock(return_value=_capability())
    runtime = LeadAgentRuntime(
        resolver=resolver,
        publish_event=publish,
        get_workspace_type=AsyncMock(return_value="sci"),
    )

    await runtime.run_session(execution_id="exec-harness-replan-forbidden", brief=_brief())

    invocations = [
        payload["invocation"]
        for _, event_name, payload in published
        if event_name == "execution.team.invocation" and payload["invocation"]["status"] != "running"
    ]
    gates = [
        payload["quality_gate"]
        for _, event_name, payload in published
        if event_name == "execution.team.quality_gate"
    ]
    assert len(invocations) == 1
    assert any(
        gate["gate_id"] == "harness_replan_signal"
        and gate["next_action"] == "stop_with_warning"
        and gate["suggested_recruits"] == []
        and gate["findings"][0]["recommended_action"] == "revise_policy_or_stop"
        for gate in gates
    )


def test_harness_node_metadata_includes_replan_signals() -> None:
    metadata = build_harness_node_metadata_from_tool_calls(
        [_run_python_tool_call("python_exit_nonzero")]
    )

    signal = metadata["harness"]["replan_signals"][0]
    assert signal == {
        "schema": "wenjin.harness.replan_signal.v1",
        "trigger": "recoverable_tool_failure",
        "failure_codes": ["python_exit_nonzero"],
        "recommended_action": "revise_script_or_recruit_code_agent",
        "max_extra_iterations": 1,
    }


def test_harness_node_metadata_includes_tool_input_validation_replan_signal() -> None:
    metadata = build_harness_node_metadata_from_tool_calls([_validation_tool_call()])

    signal = metadata["harness"]["replan_signals"][0]
    assert signal == {
        "schema": "wenjin.harness.replan_signal.v1",
        "trigger": "recoverable_tool_input_validation",
        "failure_codes": ["tool_input_validation"],
        "recommended_action": "revise_tool_call_args",
        "max_extra_iterations": 1,
    }


def test_harness_node_metadata_dedupes_replan_signals_from_duplicate_failures() -> None:
    metadata = build_harness_node_metadata_from_tool_calls(
        [
            _run_python_tool_call("python_exit_nonzero"),
            _run_python_tool_call("python_exit_nonzero"),
        ]
    )

    signals = metadata["harness"]["replan_signals"]
    assert len(signals) == 1
    assert signals[0]["failure_codes"] == ["python_exit_nonzero"]
    assert signals[0]["max_extra_iterations"] == 1


def test_harness_node_metadata_marks_queue_timeout_non_iterative() -> None:
    metadata = build_harness_node_metadata_from_tool_calls(
        [_run_python_tool_call("sandbox_queue_timeout")]
    )

    signal = metadata["harness"]["replan_signals"][0]
    assert signal["recommended_action"] == "wait_or_stop"
    assert signal["max_extra_iterations"] == 0
