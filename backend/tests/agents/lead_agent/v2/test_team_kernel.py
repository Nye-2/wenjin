import asyncio
from collections import Counter
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

import src.subagents.v2.types  # noqa: F401
from src.agents.contracts.task_brief import TaskBrief
from src.agents.lead_agent.v2.sandbox_runtime import SandboxCommandExecutionError
from src.agents.lead_agent.v2.runtime import LeadAgentRuntime
from src.agents.lead_agent.v2.team.contracts import (
    AgentInvocation,
    AgentTemplate,
    CapabilityTeamPolicy,
    TeamBlackboard,
    TeamLimits,
)
from src.agents.lead_agent.v2.team.kernel import (
    RecruitmentCandidate,
    TeamKernelRuntime,
    build_academic_harness_outputs,
)
from src.contracts.team_expert import sanitize_expert_report
from src.subagents.v2.base import SubagentBase, SubagentContext, SubagentResult
from src.subagents.v2.registry import subagent


@subagent("team_fake")
class TeamFakeSubagent(SubagentBase):
    async def run(self, ctx: SubagentContext) -> SubagentResult:
        return SubagentResult(
            output={
                "summary": f"{ctx.invocation['display_name']} handled {ctx.inputs['topic']}",
                "team_role": ctx.inputs["team_role"],
            },
            tool_calls=[
                {
                    "name": "team_fake.run",
                    "status": "completed",
                }
            ],
            token_usage={"input": 3, "output": 5},
        )


@subagent("team_event_publisher_fake")
class TeamEventPublisherFakeSubagent(SubagentBase):
    async def run(self, ctx: SubagentContext) -> SubagentResult:
        await ctx.publish_event(
            ctx.execution_id,
            "execution.team.fake_progress",
            {"invocation_id": ctx.invocation["id"]},
        )
        return SubagentResult(
            output={
                "summary": f"{ctx.invocation['display_name']} published progress",
                "team_role": ctx.inputs["team_role"],
            },
            token_usage={"input": 2, "output": 3},
        )


@subagent("team_sandbox_fake")
class TeamSandboxFakeSubagent(SubagentBase):
    async def run(self, ctx: SubagentContext) -> SubagentResult:
        return SubagentResult(
            output={
                "summary": f"{ctx.invocation['display_name']} updated workspace file",
                "team_role": ctx.inputs["team_role"],
            },
            tool_calls=[
                {
                    "name": "sandbox.write_file",
                    "status": "completed",
                    "file_changes": [
                        {
                            "path": "/workspace/main.tex",
                            "operation": "update",
                            "before_hash": "sha256:old",
                            "after_hash": "sha256:new",
                            "unified_diff": "--- a/workspace/main.tex\n+++ b/workspace/main.tex\n",
                        }
                    ],
                }
            ],
            token_usage={"input": 3, "output": 5},
        )


@subagent("team_sandbox_failure_fake")
class TeamSandboxFailureFakeSubagent(SubagentBase):
    async def run(self, ctx: SubagentContext) -> SubagentResult:
        return SubagentResult(
            output={
                "summary": f"{ctx.invocation['display_name']} recovered from one tool failure",
                "team_role": ctx.inputs["team_role"],
            },
            tool_calls=[
                {
                    "name": "sandbox.read_file",
                    "status": "failed",
                    "args": {"path": "/workspace/.env"},
                    "error": "HarnessPathError: protected path is not accessible: /workspace/.env",
                    "metadata": {
                        "recoverable_error": "HarnessPathError: protected path is not accessible: /workspace/.env",
                        "error_code": "tool_error",
                    },
                },
                {
                    "name": "sandbox.read_file",
                    "status": "completed",
                    "args": {"path": "/workspace/main/visible.txt"},
                },
            ],
            token_usage={"input": 3, "output": 5},
        )


@subagent("team_sandbox_python_fake")
class TeamSandboxPythonFakeSubagent(SubagentBase):
    async def run(self, ctx: SubagentContext) -> SubagentResult:
        return SubagentResult(
            output={
                "summary": f"{ctx.invocation['display_name']} ran sandbox Python",
                "team_role": ctx.inputs["team_role"],
            },
            tool_calls=[
                {
                    "name": "sandbox.run_python",
                    "status": "completed",
                    "recoverable_error": "python_exit_nonzero: exit_code=2",
                    "error_code": "python_exit_nonzero",
                    "execution_manifest": {
                        "schema": "wenjin.harness.run_python.execution_manifest.v1",
                        "sandbox_job_id": "job-team-1",
                        "sandbox_environment_id": "env-team-1",
                    },
                    "failure_classification": {
                        "schema": "wenjin.harness.run_python.failure_classification.v1",
                        "failure_code": "python_exit_nonzero",
                        "recoverable": True,
                    },
                    "generated_artifacts": [
                        {"path": "/workspace/reports/team-analysis.md"},
                    ],
                }
            ],
            token_usage={"input": 3, "output": 5},
        )


@subagent("team_failing")
class TeamFailingSubagent(SubagentBase):
    async def run(self, ctx: SubagentContext) -> SubagentResult:
        raise RuntimeError(f"{ctx.invocation['display_name']} failed")


@subagent("team_structured_sandbox_failure")
class TeamStructuredSandboxFailureSubagent(SubagentBase):
    async def run(self, ctx: SubagentContext) -> SubagentResult:
        raise SandboxCommandExecutionError(
            f"{ctx.invocation['display_name']} script failed",
            output={
                "status": "failed",
                "exit_code": 2,
                "billing": {
                    "type": "sandbox_operation_billing",
                    "credits_charged": 1,
                },
                "tool_calls": [
                    {
                        "name": "sandbox.run_python",
                        "status": "failed",
                        "exit_code": 2,
                        "metadata": {
                            "execution_lifecycle": {
                                "schema": "wenjin.harness.run_python.execution_lifecycle.v1",
                                "status": "failed",
                                "exit_code": 2,
                            },
                            "failure_classification": {
                                "schema": "wenjin.harness.run_python.failure_classification.v1",
                                "failure_code": "python_exit_nonzero",
                                "recoverable": True,
                            },
                        },
                        "billing": {
                            "type": "sandbox_operation_billing",
                            "credits_charged": 1,
                        },
                    }
                ],
            },
        )


@subagent("team_empty")
class TeamEmptySubagent(SubagentBase):
    async def run(self, ctx: SubagentContext) -> SubagentResult:
        return SubagentResult(output={"text": ""})


@subagent("team_hanging")
class TeamHangingSubagent(SubagentBase):
    async def run(self, ctx: SubagentContext) -> SubagentResult:
        await asyncio.sleep(10)
        return SubagentResult(output={"text": "too late"})


@subagent("team_schema_repair")
class TeamSchemaRepairSubagent(SubagentBase):
    calls: dict[str, int] = {}

    async def run(self, ctx: SubagentContext) -> SubagentResult:
        key = f"{ctx.execution_id}:{ctx.invocation['template_id']}"
        count = self.calls.get(key, 0) + 1
        self.calls[key] = count
        output = (
            {"summary": "first attempt misses required text"}
            if count == 1
            else {"text": f"{ctx.invocation['display_name']} repaired schema"}
        )
        return SubagentResult(
            output=output,
            tool_calls=[{"name": "team_schema_repair.run", "status": "completed"}],
            token_usage={"input": 1, "output": 1},
        )


@subagent("team_mapping_fake")
class TeamMappingFakeSubagent(SubagentBase):
    async def run(self, ctx: SubagentContext) -> SubagentResult:
        if ctx.invocation["template_id"] == "research_scout.v1":
            return SubagentResult(
                output={
                    "text": "source search completed",
                    "papers": [
                        {
                            "title": "Paper A",
                            "authors": ["Smith"],
                            "year": 2026,
                            "doi": "10.1/a",
                            "abstract": "A",
                        }
                    ],
                },
                token_usage={"input": 1, "output": 1},
            )
        return SubagentResult(
            output={"text": f"{ctx.invocation['display_name']} report"},
            token_usage={"input": 1, "output": 1},
        )


@subagent("team_capture")
class TeamCaptureSubagent(SubagentBase):
    contexts: list[SubagentContext] = []

    async def run(self, ctx: SubagentContext) -> SubagentResult:
        type(self).contexts.append(ctx)
        return SubagentResult(
            output={
                "text": f"{ctx.invocation['display_name']} captured",
                "quality_gates_checked": [],
            },
            tool_calls=[],
            token_usage={"input": 1, "output": 1},
        )


@subagent("team_sequential_capture")
class TeamSequentialCaptureSubagent(SubagentBase):
    contexts: list[SubagentContext] = []

    async def run(self, ctx: SubagentContext) -> SubagentResult:
        type(self).contexts.append(ctx)
        if ctx.invocation["template_id"] == "research_scout.v1":
            output = {
                "text": "search completed",
                "papers": [
                    {
                        "title": "Paper A",
                        "authors": ["Smith"],
                        "year": 2026,
                        "url": "https://example.test/paper-a",
                        "source": "semantic_scholar",
                        "abstract": "Evidence about federated LoRA.",
                    }
                ],
            }
        else:
            upstream = ctx.inputs.get("upstream_context") or {}
            evidence_items = upstream.get("evidence_items") if isinstance(upstream, dict) else []
            output = {
                "text": f"synthesized {len(evidence_items or [])} upstream evidence item(s)",
                "quality_gates_checked": [],
            }
        return SubagentResult(
            output=output,
            tool_calls=[],
            token_usage={"input": 1, "output": 1},
        )


@subagent("team_metadata_fake")
class TeamMetadataFakeSubagent(SubagentBase):
    async def run(self, ctx: SubagentContext) -> SubagentResult:
        invocation = ctx.invocation or {}
        return SubagentResult(
            output={"text": "metadata emitted"},
            metadata={
                "expert_snapshots": [
                    {
                        "snapshot_id": "snap-from-result",
                        "execution_id": ctx.execution_id,
                        "workspace_id": ctx.workspace_id,
                        "agent_invocation_id": invocation["id"],
                        "agent_template_id": invocation["template_id"],
                        "role_key": "research_scout",
                        "role_name": invocation["assigned_role"],
                        "status": "completed",
                        "update_kind": "finding",
                        "stage": {"label": "完成"},
                        "headline": "已形成文献发现",
                        "body": "已整理关键方向。",
                        "created_at": "2026-06-13T00:00:00Z",
                    }
                ]
            },
            token_usage={"input": 1, "output": 1},
        )


@subagent("team_streaming_metadata_fake")
class TeamStreamingMetadataFakeSubagent(SubagentBase):
    async def run(self, ctx: SubagentContext) -> SubagentResult:
        invocation = ctx.invocation or {}
        await ctx.emit_expert_snapshot(
            {
                "snapshot_id": "snap-from-stream",
                "execution_id": ctx.execution_id,
                "workspace_id": ctx.workspace_id,
                "agent_invocation_id": invocation["id"],
                "agent_template_id": invocation["template_id"],
                "role_key": "research_scout",
                "role_name": invocation["assigned_role"],
                "status": "running",
                "update_kind": "finding",
                "stage": {"label": "检索中"},
                "headline": "正在筛选候选文献",
                "body": "已找到第一批候选来源，正在去重和初筛。",
                "created_at": "2026-06-13T00:00:00Z",
            }
        )
        return SubagentResult(
            output={"text": "streaming metadata emitted"},
            metadata={
                "expert_snapshots": [
                    {
                        "snapshot_id": "snap-from-result",
                        "execution_id": ctx.execution_id,
                        "workspace_id": ctx.workspace_id,
                        "agent_invocation_id": invocation["id"],
                        "agent_template_id": invocation["template_id"],
                        "role_key": "research_scout",
                        "role_name": invocation["assigned_role"],
                        "status": "completed",
                        "update_kind": "output",
                        "stage": {"label": "完成"},
                        "headline": "已形成文献发现",
                        "body": "已整理关键方向。",
                        "created_at": "2026-06-13T00:00:01Z",
                    }
                ]
            },
            token_usage={"input": 1, "output": 1},
        )


@subagent("team_streaming_only_metadata_fake")
class TeamStreamingOnlyMetadataFakeSubagent(SubagentBase):
    async def run(self, ctx: SubagentContext) -> SubagentResult:
        invocation = ctx.invocation or {}
        await ctx.emit_expert_snapshot(
            {
                "snapshot_id": "snap-stream-only",
                "execution_id": ctx.execution_id,
                "workspace_id": ctx.workspace_id,
                "agent_invocation_id": invocation["id"],
                "agent_template_id": invocation["template_id"],
                "role_key": "research_scout",
                "role_name": invocation["assigned_role"],
                "status": "running",
                "update_kind": "finding",
                "stage": {"label": "筛选中"},
                "headline": "正在形成可引用线索",
                "body": "已筛掉低相关来源。",
                "created_at": "2026-06-13T00:00:00Z",
            }
        )
        return SubagentResult(
            output={"text": "streaming-only metadata emitted"},
            token_usage={"input": 1, "output": 1},
        )


def _team_capability() -> SimpleNamespace:
    return SimpleNamespace(
        id="team_research",
        workspace_type="thesis",
        display_name="团队调研",
        runtime={
            "mode": "team_kernel",
            "allowed_tools": ["web_search", "library_read", "citation_parser"],
        },
        graph_template={},
        definition_json={
            "mission": {"primary_surface": "rooms"},
            "team_policy": {
                "core_templates": ["research_scout.v1", "critical_reviewer.v1"],
                "optional_templates": ["generalist_assistant.v1"],
                "recruitment_triggers": {
                    "overloaded_or_missing_specialist": ["generalist_assistant.v1"],
                },
                "capability_tools": ["web_search", "library_read", "citation_parser"],
                "capability_skills": ["research-scout", "citation-auditor", "review-critic"],
                "quality_pipeline": ["evidence_traceability", "critical_review"],
                "limits": {
                    "max_iterations": 2,
                    "max_parallel_invocations": 2,
                    "max_invocations_total": 4,
                },
            },
        },
    )


def _brief() -> TaskBrief:
    return TaskBrief(
        capability_id="team_research",
        raw_message="调研 transformer 在医学影像中的应用",
        workspace_id="ws-team",
        user_id="user-1",
        brief={"topic": "transformer medical imaging"},
    )


def _minimal_team_policy_without_invocations() -> CapabilityTeamPolicy:
    return CapabilityTeamPolicy(
        core_templates=[],
        optional_templates=[],
        capability_tools=[],
        capability_skills=[],
        quality_pipeline=[],
        limits=TeamLimits(
            max_iterations=1,
            max_parallel_invocations=1,
            max_invocations_total=1,
        ),
    )


def _team_runtime_for_unit_tests(
    *,
    publish_event=None,
    record_node_event=None,
) -> TeamKernelRuntime:
    return TeamKernelRuntime(
        publish_event=publish_event if publish_event is not None else AsyncMock(),
        record_node_event=record_node_event if record_node_event is not None else AsyncMock(),
        abort_check=AsyncMock(return_value=False),
        load_workspace_data=AsyncMock(return_value={}),
        needs_workspace_context=lambda _policy, _requirements: False,
        context_requirements_from_brief=lambda _brief: {},
        capability_policy_builder=lambda _capability: {},
        collect_policy_memory_outputs=lambda _capability, _brief, _outputs: [],
    )


def test_team_kernel_output_mapping_prefers_latest_successful_invocation() -> None:
    runtime = _team_runtime_for_unit_tests()
    invocations = [
        AgentInvocation(
            id="inv-1",
            template_id="writer.v1",
            display_name="Writer",
            assigned_role="writer",
            recruitment_reason="test",
            effective_skills=["writer"],
            iteration=1,
            status="succeeded",
            output_report={"text": "old"},
        ),
        AgentInvocation(
            id="inv-2",
            template_id="writer.v1",
            display_name="Writer",
            assigned_role="writer",
            recruitment_reason="test",
            effective_skills=["writer"],
            iteration=2,
            status="succeeded",
            output_report={"text": "new"},
        ),
    ]

    output = runtime._output_for_graph_task(
        {"skill_id": "writer", "agent_template_id": "writer.v1"},
        invocations,
    )

    assert output == {"text": "new"}


def test_team_kernel_output_mapping_prefers_latest_completion_with_same_iteration() -> None:
    runtime = _team_runtime_for_unit_tests()
    invocations = [
        AgentInvocation(
            id="z-old",
            template_id="writer.v1",
            display_name="Writer",
            assigned_role="writer",
            recruitment_reason="test",
            effective_skills=["writer"],
            iteration=2,
            status="succeeded",
            output_report={"text": "old"},
            completed_at=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        AgentInvocation(
            id="a-new",
            template_id="writer.v1",
            display_name="Writer",
            assigned_role="writer",
            recruitment_reason="test",
            effective_skills=["writer"],
            iteration=2,
            status="succeeded",
            output_report={"text": "new"},
            completed_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
    ]

    output = runtime._output_for_graph_task(
        {"skill_id": "writer", "agent_template_id": "writer.v1"},
        invocations,
    )

    assert output == {"text": "new"}


@pytest.mark.asyncio
async def test_team_kernel_record_invocation_failure_does_not_fail_invocation(monkeypatch):
    async def failing_record_node_event(**kwargs):
        raise RuntimeError("record failed")

    runtime = _team_runtime_for_unit_tests(record_node_event=failing_record_node_event)
    invocation = AgentInvocation(
        id="inv-1",
        execution_id="exec-1",
        iteration=1,
        template_id="writer.v1",
        display_name="Writer",
        assigned_role="writer",
        recruitment_reason="test",
        status="succeeded",
        output_report={"text": "done"},
    )

    await runtime._safe_record_invocation(invocation, status="succeeded")


@pytest.mark.asyncio
async def test_team_kernel_run_invocation_sets_completed_at() -> None:
    runtime = _team_runtime_for_unit_tests()
    invocation = AgentInvocation(
        id="inv-completed",
        execution_id="exec-1",
        iteration=1,
        template_id="writer.v1",
        display_name="Writer",
        assigned_role="writer",
        recruitment_reason="test",
        effective_skills=["writer"],
        input_brief={
            "workspace_id": "ws-1",
            "topic": "completion timestamps",
            "team_role": "writer",
        },
    )

    await runtime._run_invocation(
        invocation=invocation,
        template=AgentTemplate(
            id="writer.v1",
            display_role="Writer",
            category="writing",
        ),
        capability_policy={},
        workspace_data={},
        blackboard=TeamBlackboard(),
        skill_records={"writer": SimpleNamespace(subagent_type="team_fake")},
        skill_load_error=None,
    )

    assert invocation.status == "succeeded"
    assert isinstance(invocation.completed_at, datetime)


@pytest.mark.asyncio
async def test_team_kernel_failed_invocation_preserves_structured_exception_tool_calls() -> None:
    recorded: list[dict[str, Any]] = []

    async def record_node_event(**kwargs):
        recorded.append(kwargs)

    runtime = _team_runtime_for_unit_tests(record_node_event=record_node_event)
    invocation = AgentInvocation(
        id="inv-structured-failure",
        execution_id="exec-1",
        iteration=1,
        template_id="runner.v1",
        display_name="Runner",
        assigned_role="runner",
        recruitment_reason="test",
        effective_skills=["runner"],
        input_brief={
            "workspace_id": "ws-1",
            "topic": "script failure metadata",
            "team_role": "runner",
        },
    )

    await runtime._run_invocation(
        invocation=invocation,
        template=AgentTemplate(
            id="runner.v1",
            display_role="Runner",
            category="analysis",
        ),
        capability_policy={},
        workspace_data={},
        blackboard=TeamBlackboard(),
        skill_records={"runner": SimpleNamespace(subagent_type="team_structured_sandbox_failure")},
        skill_load_error=None,
    )

    assert invocation.status == "failed"
    assert invocation.error == {"message": "Runner script failed"}
    assert invocation.output_report["status"] == "failed"
    assert invocation.tool_calls[0]["name"] == "sandbox.run_python"
    assert invocation.tool_calls[0]["metadata"]["failure_classification"]["failure_code"] == (
        "python_exit_nonzero"
    )
    assert recorded[-1]["status"] == "failed"
    assert recorded[-1]["tool_calls"] == invocation.tool_calls
    assert recorded[-1]["node_metadata"]["harness"]["replan_signals"][0]["failure_codes"] == [
        "python_exit_nonzero"
    ]


@pytest.mark.asyncio
async def test_team_kernel_subagent_publish_failure_does_not_fail_invocation() -> None:
    async def failing_publish_event(
        _execution_id: str,
        _event_name: str,
        _payload: dict[str, Any],
    ) -> None:
        raise RuntimeError("publish failed")

    runtime = _team_runtime_for_unit_tests(publish_event=failing_publish_event)
    invocation = AgentInvocation(
        id="inv-publish",
        execution_id="exec-1",
        iteration=1,
        template_id="publisher.v1",
        display_name="Publisher",
        assigned_role="publisher",
        recruitment_reason="test",
        effective_skills=["publisher"],
        input_brief={
            "workspace_id": "ws-1",
            "topic": "publish side effects",
            "team_role": "publisher",
        },
    )

    await runtime._run_invocation(
        invocation=invocation,
        template=AgentTemplate(
            id="publisher.v1",
            display_role="Publisher",
            category="research",
        ),
        capability_policy={},
        workspace_data={},
        blackboard=TeamBlackboard(),
        skill_records={"publisher": SimpleNamespace(subagent_type="team_event_publisher_fake")},
        skill_load_error=None,
    )

    assert invocation.status == "succeeded"
    assert invocation.output_report == {
        "summary": "Publisher published progress",
        "team_role": "publisher",
    }
    assert isinstance(invocation.completed_at, datetime)


@pytest.mark.asyncio
async def test_team_kernel_snapshot_record_failure_still_publishes_snapshot_event() -> None:
    published: list[str] = []

    async def failing_record_node_event(**kwargs):
        raise RuntimeError("record failed")

    async def publish_event(_execution_id: str, event_name: str, _payload: dict[str, Any]) -> None:
        published.append(event_name)

    runtime = _team_runtime_for_unit_tests(
        publish_event=publish_event,
        record_node_event=failing_record_node_event,
    )
    invocation = AgentInvocation(
        id="inv-snapshot",
        execution_id="exec-1",
        iteration=1,
        template_id="streaming.v1",
        display_name="Streamer",
        assigned_role="streamer",
        recruitment_reason="test",
        effective_skills=["streamer"],
        input_brief={"workspace_id": "ws-1", "topic": "streaming snapshots"},
    )

    await runtime._run_invocation(
        invocation=invocation,
        template=AgentTemplate(
            id="streaming.v1",
            display_role="Streamer",
            category="research",
        ),
        capability_policy={},
        workspace_data={},
        blackboard=TeamBlackboard(),
        skill_records={"streamer": SimpleNamespace(subagent_type="team_streaming_only_metadata_fake")},
        skill_load_error=None,
    )

    assert "execution.team.expert_snapshot" in published


@pytest.mark.asyncio
async def test_team_kernel_quality_gate_publish_failure_does_not_fail_evaluation() -> None:
    async def failing_publish_event(
        _execution_id: str,
        _event_name: str,
        _payload: dict[str, Any],
    ) -> None:
        raise RuntimeError("publish failed")

    runtime = _team_runtime_for_unit_tests(publish_event=failing_publish_event)
    invocation = AgentInvocation(
        id="inv-quality",
        execution_id="exec-1",
        iteration=1,
        template_id="writer.v1",
        display_name="Writer",
        assigned_role="writer",
        recruitment_reason="test",
        status="succeeded",
        output_report={"text": "done"},
    )

    gates = await runtime._evaluate_quality_gates(
        execution_id="exec-1",
        team_policy=CapabilityTeamPolicy(
            quality_pipeline=["team_output_available"],
            limits=TeamLimits(max_iterations=1, max_parallel_invocations=1, max_invocations_total=1),
        ),
        capability_policy={},
        counts=Counter({"writer.v1": 1}),
        invocations=[invocation],
        latest_invocations=[invocation],
        blackboard=TeamBlackboard(),
        workspace_data={},
    )

    assert gates


@pytest.mark.asyncio
async def test_team_kernel_passes_capability_policy_and_user_to_workspace_loader(
    monkeypatch,
) -> None:
    captured: dict[str, Any] = {}

    async def load_workspace_data(workspace_id: str, **kwargs: Any) -> dict[str, Any]:
        captured["workspace_id"] = workspace_id
        captured.update(kwargs)
        return {"library_context": {"allowed_citation_keys": ["smith2024"]}}

    runtime = TeamKernelRuntime(
        publish_event=AsyncMock(),
        record_node_event=AsyncMock(),
        abort_check=AsyncMock(return_value=False),
        load_workspace_data=load_workspace_data,
        needs_workspace_context=lambda policy, requirements: True,
        context_requirements_from_brief=lambda brief: {"include_related_documents": True},
        capability_policy_builder=lambda capability: {
            "citation_policy": {"source_scope": "workspace_library"},
            "context_policy": {"room_reads": {"library": True}},
        },
        collect_policy_memory_outputs=lambda capability, brief, outputs: [],
    )

    monkeypatch.setattr(runtime, "_load_templates", AsyncMock(return_value={}))
    monkeypatch.setattr(
        "src.agents.lead_agent.v2.team.kernel.build_capability_team_policy",
        lambda capability, templates: _minimal_team_policy_without_invocations(),
    )

    report = await runtime.run(
        execution_id="exec-1",
        brief=TaskBrief(
            capability_id="sci_literature_positioning",
            raw_message="position this topic",
            workspace_id="ws-1",
            user_id="user-1",
            brief={"topic": "LLM agents"},
        ),
        capability=SimpleNamespace(
            id="sci_literature_positioning",
            display_name="SCI 文献定位",
        ),
        started_at=datetime.now(UTC),
    )

    assert report.status in {"completed", "failed_partial"}
    assert captured["workspace_id"] == "ws-1"
    assert captured["user_id"] == "user-1"
    assert captured["capability_policy"]["citation_policy"]["source_scope"] == "workspace_library"
    assert captured["context_requirements"]["include_related_documents"] is True


def test_team_panel_graph_keeps_member_templates_out_of_progress_steps() -> None:
    runtime = LeadAgentRuntime(
        resolver=AsyncMock(),
        publish_event=AsyncMock(),
        get_workspace_type=AsyncMock(return_value="thesis"),
    )

    graph = runtime._to_team_panel_graph(_team_capability())

    assert graph["mode"] == "team_kernel"
    assert [node["id"] for node in graph["nodes"]] == [
        "team_prepare",
        "team_recruit",
        "team_dispatch",
        "team_quality_gate",
        "team_finish",
    ]
    assert all(node["subagent_type"] != "agent_template" for node in graph["nodes"])


def test_team_kernel_quality_contract_includes_workspace_source_allowlist() -> None:
    runtime = TeamKernelRuntime(
        publish_event=AsyncMock(),
        record_node_event=AsyncMock(),
        abort_check=AsyncMock(return_value=False),
        load_workspace_data=AsyncMock(return_value={}),
        needs_workspace_context=lambda _policy, _requirements: True,
        context_requirements_from_brief=lambda _brief: {},
        capability_policy_builder=lambda _capability: {},
        collect_policy_memory_outputs=lambda _capability, _brief, _outputs: [],
    )
    invocation = AgentInvocation(
        id="team.1.research_scout_v1.1",
        iteration=1,
        template_id="research_scout.v1",
        display_name="文献检索员",
        assigned_role="文献检索员",
        recruitment_reason="test",
        input_brief={},
    )

    runtime._inject_quality_contracts(
        capability=_team_capability(),
        templates={
            "research_scout.v1": AgentTemplate(
                id="research_scout.v1",
                display_role="文献检索员",
                category="research",
            )
        },
        team_policy=CapabilityTeamPolicy(core_templates=["research_scout.v1"]),
        skill_records={},
        workspace_data={
            "library_context": {"citation_keys": ["smith2026"]},
            "related_documents": [{"id": "source-1", "citation_key": "smith2026"}],
        },
        invocations=[invocation],
    )

    assert invocation.input_brief["quality_contract"]["allowed_citation_keys"] == [
        "smith2026"
    ]
    assert invocation.input_brief["quality_contract"]["allowed_source_ids"] == ["source-1"]


def test_team_kernel_applies_capability_profile_override_when_building_batch() -> None:
    runtime = TeamKernelRuntime(
        publish_event=AsyncMock(),
        record_node_event=AsyncMock(),
        abort_check=AsyncMock(return_value=False),
        load_workspace_data=AsyncMock(return_value={}),
        needs_workspace_context=lambda _policy, _requirements: True,
        context_requirements_from_brief=lambda _brief: {},
        capability_policy_builder=lambda _capability: {},
        collect_policy_memory_outputs=lambda _capability, _brief, _outputs: [],
    )
    capability = _team_capability()
    template = AgentTemplate(
        id="literature_synthesizer.v1",
        display_role="文献综合专家",
        category="research",
        expert_profile={
            "public_name": "文献专家",
            "role_title": "文献综合专家",
            "status_phrases": {"running": "整理文献中"},
        },
    )

    batch = runtime._build_invocation_batch(
        execution_id="exec-1",
        brief=_brief(),
        capability=capability,
        templates={"literature_synthesizer.v1": template},
        team_policy=CapabilityTeamPolicy(
            core_templates=["literature_synthesizer.v1"],
            template_profile_overrides={
                "literature_synthesizer.v1": {
                    "public_name": "综述姐 Athena",
                    "status_phrases": {"running": "织主题矩阵中"},
                }
            },
        ),
        capability_policy={},
        blackboard=TeamBlackboard(),
        counts=Counter(),
        iteration=1,
        recruits=[
            RecruitmentCandidate(
                template_id="literature_synthesizer.v1",
                reason="core",
            )
        ],
    )

    assert batch[0].display_name == "综述姐 Athena"
    assert batch[0].expert_profile["status_phrases"]["running"] == "织主题矩阵中"


@pytest.mark.asyncio
async def test_record_invocation_persists_expert_snapshot_and_preview_items() -> None:
    record_node_event = AsyncMock()
    runtime = TeamKernelRuntime(
        publish_event=AsyncMock(),
        record_node_event=record_node_event,
        abort_check=AsyncMock(return_value=False),
        load_workspace_data=AsyncMock(return_value={}),
        needs_workspace_context=lambda _policy, _requirements: True,
        context_requirements_from_brief=lambda _brief: {},
        capability_policy_builder=lambda _capability: {},
        collect_policy_memory_outputs=lambda _capability, _brief, _outputs: [],
    )
    invocation = AgentInvocation(
        id="team.1.research_scout_v1.1",
        execution_id="exec-1",
        iteration=1,
        template_id="research_scout.v1",
        display_name="文献猎手 Nora",
        assigned_role="文献检索专家",
        recruitment_reason="core",
        input_brief={},
        expert_profile={
            "public_name": "文献猎手 Nora",
            "role_title": "文献检索专家",
            "avatar_label": "文",
            "status_phrases": {"completed": "文献线索已整理"},
        },
        expert_snapshots=[
            {
                "snapshot_id": "snap-1",
                "execution_id": "exec-1",
                "workspace_id": "ws-1",
                "agent_invocation_id": "team.1.research_scout_v1.1",
                "agent_template_id": "research_scout.v1",
                "role_key": "research_scout",
                "role_name": "文献检索专家",
                "status": "completed",
                "update_kind": "finding",
                "stage": {"label": "检索完成"},
                "headline": "找到 12 篇候选文献",
                "body": "token=secret-value 已筛出隐私保护方向。",
                "created_at": "2026-06-13T00:00:00Z",
            }
        ],
        expert_preview_items=[
            {
                "preview_item_id": "preview-1",
                "execution_id": "exec-1",
                "workspace_id": "ws-1",
                "owner_agent_invocation_id": "team.1.research_scout_v1.1",
                "owner_role_name": "文献检索专家",
                "title": "候选文献列表",
                "kind": "literature_list",
                "summary": "12 篇候选文献。",
                "status": "ready",
                "created_at": "2026-06-13T00:00:00Z",
            }
        ],
    )

    await runtime._record_invocation(invocation, status="succeeded")

    metadata = record_node_event.await_args.kwargs["node_metadata"]
    harness = metadata["harness"]
    assert harness["expert_snapshots"][0]["body"] == "[redacted] 已筛出隐私保护方向。"
    assert harness["expert_preview_items"][0]["title"] == "候选文献列表"
    assert metadata["expert_profile"]["public_name"] == "文献猎手 Nora"


@pytest.mark.asyncio
async def test_record_invocation_generates_synthetic_expert_snapshot_when_missing() -> None:
    record_node_event = AsyncMock()
    runtime = TeamKernelRuntime(
        publish_event=AsyncMock(),
        record_node_event=record_node_event,
        abort_check=AsyncMock(return_value=False),
        load_workspace_data=AsyncMock(return_value={}),
        needs_workspace_context=lambda _policy, _requirements: True,
        context_requirements_from_brief=lambda _brief: {},
        capability_policy_builder=lambda _capability: {},
        collect_policy_memory_outputs=lambda _capability, _brief, _outputs: [],
    )
    invocation = AgentInvocation(
        id="team.1.research_scout_v1.1",
        execution_id="exec-1",
        iteration=1,
        template_id="research_scout.v1",
        display_name="文献猎手 Nora",
        assigned_role="文献检索专家",
        recruitment_reason="core",
        input_brief={},
        expert_profile={
            "public_name": "文献猎手 Nora",
            "role_title": "文献检索专家",
            "avatar_label": "文",
            "status_phrases": {"running": "扫文献雷达中"},
        },
    )

    await runtime._record_invocation(invocation, status="running")

    snapshot = record_node_event.await_args.kwargs["node_metadata"]["harness"]["expert_snapshots"][0]
    assert snapshot["status"] == "running"
    assert snapshot["headline"] == "扫文献雷达中"
    assert snapshot["agent_invocation_id"] == invocation.id


@pytest.mark.asyncio
async def test_record_invocation_skips_invalid_expert_metadata() -> None:
    record_node_event = AsyncMock()
    runtime = TeamKernelRuntime(
        publish_event=AsyncMock(),
        record_node_event=record_node_event,
        abort_check=AsyncMock(return_value=False),
        load_workspace_data=AsyncMock(return_value={}),
        needs_workspace_context=lambda _policy, _requirements: True,
        context_requirements_from_brief=lambda _brief: {},
        capability_policy_builder=lambda _capability: {},
        collect_policy_memory_outputs=lambda _capability, _brief, _outputs: [],
    )
    invocation = AgentInvocation(
        id="team.1.research_scout_v1.1",
        execution_id="exec-1",
        iteration=1,
        template_id="research_scout.v1",
        display_name="文献猎手 Nora",
        assigned_role="文献检索专家",
        recruitment_reason="core",
        input_brief={"workspace_id": "ws-1"},
        expert_snapshots=[
            {
                "snapshot_id": "broken",
                "execution_id": "exec-1",
                "workspace_id": "ws-1",
                "agent_invocation_id": "team.1.research_scout_v1.1",
                "agent_template_id": "research_scout.v1",
                "role_key": "research_scout",
                "role_name": "文献检索专家",
                "status": "not-a-status",
                "update_kind": "finding",
                "stage": "bad-shape",
                "headline": "bad",
                "body": "bad",
                "created_at": "2026-06-13T00:00:00Z",
            }
        ],
        expert_preview_items=[
            {
                "preview_item_id": "broken-preview",
                "execution_id": "exec-1",
                "workspace_id": "ws-1",
                "owner_agent_invocation_id": "team.1.research_scout_v1.1",
                "owner_role_name": "文献检索专家",
                "title": "bad",
                "kind": "not-a-kind",
                "summary": "bad",
                "status": "ready",
                "created_at": "2026-06-13T00:00:00Z",
            }
        ],
    )

    await runtime._record_invocation(invocation, status="succeeded")

    harness = record_node_event.await_args.kwargs["node_metadata"]["harness"]
    assert harness["expert_snapshots"][0]["snapshot_id"].startswith(invocation.id)
    assert "expert_preview_items" not in harness


def test_result_preview_item_id_ignores_invalid_preview_items() -> None:
    invocation = AgentInvocation(
        id="team.1.research_scout_v1.1",
        execution_id="exec-1",
        iteration=1,
        template_id="research_scout.v1",
        display_name="文献猎手 Nora",
        assigned_role="文献检索专家",
        recruitment_reason="core",
        status="succeeded",
        expert_preview_items=[
            {
                "preview_item_id": "broken-preview",
                "execution_id": "exec-1",
                "workspace_id": "ws-1",
                "owner_agent_invocation_id": "team.1.research_scout_v1.1",
                "owner_role_name": "文献检索专家",
                "title": "bad",
                "kind": "not-a-kind",
                "summary": "bad",
                "status": "ready",
                "created_at": "2026-06-13T00:00:00Z",
            }
        ],
    )

    assert TeamKernelRuntime._result_preview_item_id([invocation]) is None


@pytest.mark.asyncio
async def test_run_invocation_persists_subagent_result_expert_metadata() -> None:
    node_events: list[dict] = []

    async def record_node_event(**kwargs):
        node_events.append(kwargs)

    runtime = TeamKernelRuntime(
        publish_event=AsyncMock(),
        record_node_event=record_node_event,
        abort_check=AsyncMock(return_value=False),
        load_workspace_data=AsyncMock(return_value={}),
        needs_workspace_context=lambda _policy, _requirements: True,
        context_requirements_from_brief=lambda _brief: {},
        capability_policy_builder=lambda _capability: {},
        collect_policy_memory_outputs=lambda _capability, _brief, _outputs: [],
    )
    invocation = AgentInvocation(
        id="team.1.research_scout_v1.1",
        execution_id="exec-1",
        iteration=1,
        template_id="research_scout.v1",
        display_name="文献猎手 Nora",
        assigned_role="文献检索专家",
        recruitment_reason="core",
        input_brief={"workspace_id": "ws-1"},
        effective_skills=["metadata-skill"],
    )

    await runtime._run_invocation(
        invocation=invocation,
        template=AgentTemplate(
            id="research_scout.v1",
            display_role="文献检索员",
            category="research",
            persona_prompt="research",
        ),
        capability_policy={},
        workspace_data={},
        blackboard=TeamBlackboard(),
        skill_records={"metadata-skill": SimpleNamespace(subagent_type="team_metadata_fake")},
        skill_load_error=None,
    )

    completed = [event for event in node_events if event["status"] == "completed"][-1]
    snapshots = completed["node_metadata"]["harness"]["expert_snapshots"]
    result_snapshot = next(
        snapshot for snapshot in snapshots if snapshot["snapshot_id"] == "snap-from-result"
    )
    assert result_snapshot["headline"] == "已形成文献发现"


@pytest.mark.asyncio
async def test_run_invocation_keeps_streamed_expert_snapshots_in_final_node_metadata() -> None:
    node_events: list[dict] = []

    async def record_node_event(**kwargs):
        node_events.append(kwargs)

    runtime = TeamKernelRuntime(
        publish_event=AsyncMock(),
        record_node_event=record_node_event,
        abort_check=AsyncMock(return_value=False),
        load_workspace_data=AsyncMock(return_value={}),
        needs_workspace_context=lambda _policy, _requirements: True,
        context_requirements_from_brief=lambda _brief: {},
        capability_policy_builder=lambda _capability: {},
        collect_policy_memory_outputs=lambda _capability, _brief, _outputs: [],
    )
    invocation = AgentInvocation(
        id="team.1.research_scout_v1.1",
        execution_id="exec-1",
        iteration=1,
        template_id="research_scout.v1",
        display_name="文献猎手 Nora",
        assigned_role="文献检索专家",
        recruitment_reason="core",
        input_brief={"workspace_id": "ws-1"},
        effective_skills=["streaming-metadata-skill"],
    )

    await runtime._run_invocation(
        invocation=invocation,
        template=AgentTemplate(
            id="research_scout.v1",
            display_role="文献检索员",
            category="research",
            persona_prompt="research",
        ),
        capability_policy={},
        workspace_data={},
        blackboard=TeamBlackboard(),
        skill_records={
            "streaming-metadata-skill": SimpleNamespace(
                subagent_type="team_streaming_metadata_fake",
            ),
        },
        skill_load_error=None,
    )

    running_events = [event for event in node_events if event["status"] == "running"]
    assert any(
        snapshot["snapshot_id"] == "snap-from-stream"
        for event in running_events
        for snapshot in event["node_metadata"]["harness"]["expert_snapshots"]
    )

    completed = [event for event in node_events if event["status"] == "completed"][-1]
    snapshot_ids = [
        snapshot["snapshot_id"]
        for snapshot in completed["node_metadata"]["harness"]["expert_snapshots"]
    ]
    assert "snap-from-stream" in snapshot_ids
    assert "snap-from-result" in snapshot_ids


@pytest.mark.asyncio
async def test_run_invocation_keeps_streamed_snapshots_when_result_metadata_is_empty() -> None:
    node_events: list[dict] = []
    invocation_events: list[dict] = []

    async def record_node_event(**kwargs):
        node_events.append(kwargs)

    async def publish_event(_execution_id: str, event_type: str, payload: dict):
        if event_type == "execution.team.invocation":
            invocation_events.append(payload)

    runtime = TeamKernelRuntime(
        publish_event=publish_event,
        record_node_event=record_node_event,
        abort_check=AsyncMock(return_value=False),
        load_workspace_data=AsyncMock(return_value={}),
        needs_workspace_context=lambda _policy, _requirements: True,
        context_requirements_from_brief=lambda _brief: {},
        capability_policy_builder=lambda _capability: {},
        collect_policy_memory_outputs=lambda _capability, _brief, _outputs: [],
    )
    invocation = AgentInvocation(
        id="team.1.research_scout_v1.1",
        execution_id="exec-1",
        iteration=1,
        template_id="research_scout.v1",
        display_name="文献猎手 Nora",
        assigned_role="文献检索专家",
        recruitment_reason="core",
        input_brief={"workspace_id": "ws-1"},
        effective_skills=["streaming-only-metadata-skill"],
    )

    await runtime._run_invocation(
        invocation=invocation,
        template=AgentTemplate(
            id="research_scout.v1",
            display_role="文献检索员",
            category="research",
            persona_prompt="research",
        ),
        capability_policy={},
        workspace_data={},
        blackboard=TeamBlackboard(),
        skill_records={
            "streaming-only-metadata-skill": SimpleNamespace(
                subagent_type="team_streaming_only_metadata_fake",
            ),
        },
        skill_load_error=None,
    )

    completed = [event for event in node_events if event["status"] == "completed"][-1]
    completed_snapshot_ids = [
        snapshot["snapshot_id"]
        for snapshot in completed["node_metadata"]["harness"]["expert_snapshots"]
    ]
    assert "snap-stream-only" in completed_snapshot_ids
    assert any(
        snapshot["snapshot_id"] == "snap-stream-only"
        for payload in invocation_events
        for snapshot in payload["invocation"]["expert_snapshots"]
    )


@pytest.mark.asyncio
async def test_streamed_expert_snapshot_recording_failure_does_not_fail_invocation() -> None:
    node_events: list[dict] = []

    async def record_node_event(**kwargs):
        snapshot_ids = [
            snapshot.get("snapshot_id")
            for snapshot in kwargs.get("node_metadata", {})
            .get("harness", {})
            .get("expert_snapshots", [])
            if isinstance(snapshot, dict)
        ]
        if kwargs.get("status") == "running" and "snap-from-stream" in snapshot_ids:
            raise RuntimeError("transient node recorder failure")
        node_events.append(kwargs)

    runtime = TeamKernelRuntime(
        publish_event=AsyncMock(),
        record_node_event=record_node_event,
        abort_check=AsyncMock(return_value=False),
        load_workspace_data=AsyncMock(return_value={}),
        needs_workspace_context=lambda _policy, _requirements: True,
        context_requirements_from_brief=lambda _brief: {},
        capability_policy_builder=lambda _capability: {},
        collect_policy_memory_outputs=lambda _capability, _brief, _outputs: [],
    )
    invocation = AgentInvocation(
        id="team.1.research_scout_v1.1",
        execution_id="exec-1",
        iteration=1,
        template_id="research_scout.v1",
        display_name="文献猎手 Nora",
        assigned_role="文献检索专家",
        recruitment_reason="core",
        input_brief={"workspace_id": "ws-1"},
        effective_skills=["streaming-metadata-skill"],
    )

    await runtime._run_invocation(
        invocation=invocation,
        template=AgentTemplate(
            id="research_scout.v1",
            display_role="文献检索员",
            category="research",
            persona_prompt="research",
        ),
        capability_policy={},
        workspace_data={},
        blackboard=TeamBlackboard(),
        skill_records={
            "streaming-metadata-skill": SimpleNamespace(
                subagent_type="team_streaming_metadata_fake",
            ),
        },
        skill_load_error=None,
    )

    assert invocation.status == "succeeded"
    assert any(event["status"] == "completed" for event in node_events)


@pytest.mark.asyncio
async def test_run_invocation_marks_hanging_subagent_failed_on_timeout() -> None:
    runtime = TeamKernelRuntime(
        publish_event=AsyncMock(),
        record_node_event=AsyncMock(),
        abort_check=AsyncMock(return_value=False),
        load_workspace_data=AsyncMock(return_value={}),
        needs_workspace_context=lambda _policy, _requirements: False,
        context_requirements_from_brief=lambda _brief: {},
        capability_policy_builder=lambda _capability: {},
        collect_policy_memory_outputs=lambda _capability, _brief, _outputs: [],
    )
    invocation = AgentInvocation(
        id="team.1.hanging_v1.1",
        iteration=1,
        template_id="hanging.v1",
        display_name="卡住专家",
        assigned_role="测试专家",
        recruitment_reason="test",
        input_brief={"workspace_id": "ws-1"},
        effective_skills=["hanging-skill"],
    )

    with patch(
        "src.agents.lead_agent.v2.team.kernel._invocation_timeout_seconds",
        return_value=0.01,
    ):
        await runtime._run_invocation(
            invocation=invocation,
            template=AgentTemplate(
                id="hanging.v1",
                display_role="测试专家",
                category="test",
                persona_prompt="hang",
            ),
            capability_policy={},
            workspace_data={},
            blackboard=TeamBlackboard(),
            skill_records={
                "hanging-skill": SimpleNamespace(
                    subagent_type="team_hanging",
                    config={},
                ),
            },
            skill_load_error=None,
        )

    assert invocation.status == "failed"
    assert "timed out" in invocation.error["message"]


class FakeTeamCatalogClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def list_agent_templates(self, *, enabled_only: bool = True):
        from src.dataservice_client.contracts.catalog import AgentTemplatePayload

        return [
            AgentTemplatePayload(
                id="research_scout.v1",
                display_role="文献检索员",
                category="research",
                default_skills=["research-scout", "citation-auditor"],
                tool_affinity={
                    "preferred": ["web_search", "library_read"],
                    "can_request": ["citation_parser"],
                },
                risk_profile={"room_write": "staged_only"},
            ),
            AgentTemplatePayload(
                id="critical_reviewer.v1",
                display_role="质量审稿人",
                category="review",
                default_skills=["review-critic"],
                tool_affinity={"preferred": ["library_read"], "can_request": []},
                risk_profile={"room_write": "staged_only"},
            ),
            AgentTemplatePayload(
                id="generalist_assistant.v1",
                display_role="综合助理",
                category="generalist",
                default_skills=["review-critic"],
                tool_affinity={"preferred": [], "can_request": []},
                risk_profile={"room_write": "staged_only"},
            ),
        ]

    async def list_catalog_skills(self, *, enabled_only: bool = True):
        from src.dataservice_client.contracts.catalog import CapabilitySkillPayload

        return [
            CapabilitySkillPayload(
                id="research-scout",
                display_name="Research Scout",
                worker_type="research",
                subagent_type="team_fake",
                prompt="Summarize research evidence as JSON.",
                config={"output_kind": "json"},
            ),
            CapabilitySkillPayload(
                id="citation-auditor",
                display_name="Citation Auditor",
                worker_type="research",
                subagent_type="team_fake",
                prompt="Audit citations.",
                config={"output_kind": "json"},
            ),
            CapabilitySkillPayload(
                id="review-critic",
                display_name="Review Critic",
                worker_type="review",
                subagent_type="team_fake",
                prompt="Review risks.",
                config={"output_kind": "json"},
            ),
        ]


class CountingTeamCatalogClient(FakeTeamCatalogClient):
    skill_list_calls = 0

    async def list_catalog_skills(self, *, enabled_only: bool = True):
        type(self).skill_list_calls += 1
        return await super().list_catalog_skills(enabled_only=enabled_only)


class FakeCriticalReviewerFailingTeamCatalogClient(FakeTeamCatalogClient):
    async def list_agent_templates(self, *, enabled_only: bool = True):
        records = await super().list_agent_templates(enabled_only=enabled_only)
        for record in records:
            if record.id == "critical_reviewer.v1":
                record.default_skills = ["failing-review-critic"]
        return records

    async def list_catalog_skills(self, *, enabled_only: bool = True):
        from src.dataservice_client.contracts.catalog import CapabilitySkillPayload

        records = await super().list_catalog_skills(enabled_only=enabled_only)
        return [
            *records,
            CapabilitySkillPayload(
                id="failing-review-critic",
                display_name="Failing Review Critic",
                worker_type="review",
                subagent_type="team_failing",
                prompt="Fail this reviewer.",
                config={"output_kind": "json"},
            ),
        ]


class FailingAndEmptyTeamCatalogClient(FakeTeamCatalogClient):
    async def list_agent_templates(self, *, enabled_only: bool = True):
        records = await super().list_agent_templates(enabled_only=enabled_only)
        for record in records:
            if record.id == "research_scout.v1":
                record.default_skills = ["failing-research-scout"]
            if record.id == "critical_reviewer.v1":
                record.default_skills = ["empty-review-critic"]
        return records

    async def list_catalog_skills(self, *, enabled_only: bool = True):
        from src.dataservice_client.contracts.catalog import CapabilitySkillPayload

        return [
            CapabilitySkillPayload(
                id="failing-research-scout",
                display_name="Failing Research Scout",
                worker_type="research",
                subagent_type="team_failing",
                prompt="Fail this scout.",
                config={"output_kind": "json"},
            ),
            CapabilitySkillPayload(
                id="empty-review-critic",
                display_name="Empty Review Critic",
                worker_type="review",
                subagent_type="team_empty",
                prompt="Return empty output.",
                config={"output_kind": "json"},
            ),
        ]


class SandboxEvidenceReplayTeamCatalogClient(FakeTeamCatalogClient):
    async def list_agent_templates(self, *, enabled_only: bool = True):
        records = await super().list_agent_templates(enabled_only=enabled_only)
        for record in records:
            if record.id == "research_scout.v1":
                record.default_skills = ["sandbox-writer"]
            if record.id == "critical_reviewer.v1":
                record.default_skills = ["failing-review-critic"]
            if record.id == "generalist_assistant.v1":
                record.default_skills = ["generalist-capture"]
        return records

    async def list_catalog_skills(self, *, enabled_only: bool = True):
        from src.dataservice_client.contracts.catalog import CapabilitySkillPayload

        return [
            CapabilitySkillPayload(
                id="sandbox-writer",
                display_name="Sandbox Writer",
                worker_type="research",
                subagent_type="team_sandbox_fake",
                prompt="Write sandbox evidence.",
                config={"output_kind": "json"},
            ),
            CapabilitySkillPayload(
                id="failing-review-critic",
                display_name="Failing Review Critic",
                worker_type="review",
                subagent_type="team_failing",
                prompt="Fail this reviewer.",
                config={"output_kind": "json"},
            ),
            CapabilitySkillPayload(
                id="generalist-capture",
                display_name="Generalist Capture",
                worker_type="generalist",
                subagent_type="team_capture",
                prompt="Capture context.",
                config={"output_kind": "json"},
            ),
        ]


class CapturingQualityGateRuntimeStateClient(FakeCriticalReviewerFailingTeamCatalogClient):
    runtime_state_updates: list[dict] = []

    async def get_execution(self, execution_id: str):
        return SimpleNamespace(runtime_state_json={"existing_key": "preserved"})

    async def update_execution(self, execution_id: str, command):
        type(self).runtime_state_updates.append(command.model_dump(mode="json"))
        return SimpleNamespace(runtime_state_json=command.runtime_state_json)


class CapturingCancelledEpisodeClient(FakeTeamCatalogClient):
    runtime_state_updates: list[dict] = []

    async def get_execution(self, execution_id: str):
        return SimpleNamespace(runtime_state_json={})

    async def update_execution(self, execution_id: str, command):
        type(self).runtime_state_updates.append(command.model_dump(mode="json"))
        return SimpleNamespace(runtime_state_json=command.runtime_state_json)


class CountingGeneralistNewSkillCatalogClient(FakeCriticalReviewerFailingTeamCatalogClient):
    skill_list_calls = 0

    async def list_agent_templates(self, *, enabled_only: bool = True):
        records = await super().list_agent_templates(enabled_only=enabled_only)
        for record in records:
            if record.id == "generalist_assistant.v1":
                record.default_skills = ["generalist-helper"]
        return records

    async def list_catalog_skills(self, *, enabled_only: bool = True):
        from src.dataservice_client.contracts.catalog import CapabilitySkillPayload

        type(self).skill_list_calls += 1
        records = await super().list_catalog_skills(enabled_only=enabled_only)
        return [
            *records,
            CapabilitySkillPayload(
                id="generalist-helper",
                display_name="Generalist Helper",
                worker_type="generalist",
                subagent_type="team_fake",
                prompt="Fill team gaps.",
                config={"output_kind": "json"},
            ),
        ]


class FakeSkillCatalogFailingClient(FakeTeamCatalogClient):
    async def list_catalog_skills(self, *, enabled_only: bool = True):
        raise RuntimeError("skill catalog unavailable")


class SchemaRequiredTeamCatalogClient(FakeTeamCatalogClient):
    async def list_catalog_skills(self, *, enabled_only: bool = True):
        from src.dataservice_client.contracts.catalog import CapabilitySkillPayload

        records = await super().list_catalog_skills(enabled_only=enabled_only)
        return [
            CapabilitySkillPayload(
                id=record.id,
                display_name=record.display_name,
                worker_type=record.worker_type,
                subagent_type=record.subagent_type,
                prompt=record.prompt,
                config=record.config,
                skill_json={
                    "schema_version": "capability_skill.v2",
                    "id": record.id,
                    "io_contract": {
                        "output_schema": {
                            "type": "object",
                            "required": ["text"],
                            "properties": {"text": {"type": "string"}},
                        }
                    },
                    "quality_gates": [],
                },
            )
            for record in records
        ]


class SchemaRepairTeamCatalogClient(SchemaRequiredTeamCatalogClient):
    async def list_catalog_skills(self, *, enabled_only: bool = True):
        from src.dataservice_client.contracts.catalog import CapabilitySkillPayload

        records = await super().list_catalog_skills(enabled_only=enabled_only)
        return [
            CapabilitySkillPayload(
                id=record.id,
                display_name=record.display_name,
                worker_type=record.worker_type,
                subagent_type="team_schema_repair",
                prompt=record.prompt,
                config=record.config,
                skill_json=record.skill_json,
            )
            for record in records
        ]


class MappingTeamCatalogClient(FakeTeamCatalogClient):
    async def list_catalog_skills(self, *, enabled_only: bool = True):
        from src.dataservice_client.contracts.catalog import CapabilitySkillPayload

        records = await super().list_catalog_skills(enabled_only=enabled_only)
        return [
            CapabilitySkillPayload(
                id=record.id,
                display_name=record.display_name,
                worker_type=record.worker_type,
                subagent_type="team_mapping_fake",
                prompt=record.prompt,
                config=record.config,
            )
            for record in records
        ]


class SciLiteratureTeamCatalogClient(FakeTeamCatalogClient):
    async def list_agent_templates(self, *, enabled_only: bool = True):
        from src.dataservice_client.contracts.catalog import AgentTemplatePayload

        return [
            AgentTemplatePayload(
                id="research_scout.v1",
                display_role="文献检索员",
                category="research",
                default_skills=["research-scout"],
                tool_affinity={
                    "preferred": ["web_search", "library_read"],
                    "can_request": ["citation_parser"],
                },
                risk_profile={"room_write": "staged_only"},
            ),
            AgentTemplatePayload(
                id="literature_synthesizer.v1",
                display_role="文献综合专家",
                category="research",
                default_skills=["literature-synthesizer"],
                tool_affinity={
                    "preferred": ["library_read", "prism_file_read"],
                    "can_request": ["citation_parser", "artifact_create"],
                },
                risk_profile={"room_write": "staged_only"},
            ),
        ]

    async def list_catalog_skills(self, *, enabled_only: bool = True):
        from src.dataservice_client.contracts.catalog import CapabilitySkillPayload

        return [
            CapabilitySkillPayload(
                id="research-scout",
                display_name="Research Scout",
                worker_type="research",
                subagent_type="team_capture",
                prompt="Capture research scout context.",
                config={"output_kind": "json"},
            ),
            CapabilitySkillPayload(
                id="literature-synthesizer",
                display_name="Literature Synthesizer",
                worker_type="research",
                subagent_type="team_capture",
                prompt="Capture synthesizer context.",
                config={"output_kind": "json"},
            ),
        ]


class SequentialSciLiteratureTeamCatalogClient(SciLiteratureTeamCatalogClient):
    async def list_catalog_skills(self, *, enabled_only: bool = True):
        from src.dataservice_client.contracts.catalog import CapabilitySkillPayload

        return [
            CapabilitySkillPayload(
                id="research-scout",
                display_name="Research Scout",
                worker_type="research",
                subagent_type="team_sequential_capture",
                prompt="Capture research scout context.",
                config={"output_kind": "json"},
            ),
            CapabilitySkillPayload(
                id="literature-synthesizer",
                display_name="Literature Synthesizer",
                worker_type="research",
                subagent_type="team_sequential_capture",
                prompt="Capture synthesizer context.",
                config={"output_kind": "json"},
            ),
        ]


class SandboxToolTeamCatalogClient(FakeTeamCatalogClient):
    async def list_catalog_skills(self, *, enabled_only: bool = True):
        from src.dataservice_client.contracts.catalog import CapabilitySkillPayload

        records = await super().list_catalog_skills(enabled_only=enabled_only)
        return [
            CapabilitySkillPayload(
                id=record.id,
                display_name=record.display_name,
                worker_type=record.worker_type,
                subagent_type="team_sandbox_fake",
                prompt=record.prompt,
                config=record.config,
            )
            for record in records
        ]


class SandboxToolFailureTeamCatalogClient(FakeTeamCatalogClient):
    async def list_catalog_skills(self, *, enabled_only: bool = True):
        from src.dataservice_client.contracts.catalog import CapabilitySkillPayload

        records = await super().list_catalog_skills(enabled_only=enabled_only)
        return [
            CapabilitySkillPayload(
                id=record.id,
                display_name=record.display_name,
                worker_type=record.worker_type,
                subagent_type="team_sandbox_failure_fake",
                prompt=record.prompt,
                config=record.config,
            )
            for record in records
        ]


class SandboxPythonTeamCatalogClient(FakeTeamCatalogClient):
    async def list_catalog_skills(self, *, enabled_only: bool = True):
        from src.dataservice_client.contracts.catalog import CapabilitySkillPayload

        records = await super().list_catalog_skills(enabled_only=enabled_only)
        return [
            CapabilitySkillPayload(
                id=record.id,
                display_name=record.display_name,
                worker_type=record.worker_type,
                subagent_type="team_sandbox_python_fake",
                prompt=record.prompt,
                config=record.config,
            )
            for record in records
        ]


class FakeFailingTeamCatalogClient(FakeTeamCatalogClient):
    async def list_catalog_skills(self, *, enabled_only: bool = True):
        from src.dataservice_client.contracts.catalog import CapabilitySkillPayload

        records = await super().list_catalog_skills(enabled_only=enabled_only)
        return [
            (
                CapabilitySkillPayload(
                    id=record.id,
                    display_name=record.display_name,
                    worker_type=record.worker_type,
                    subagent_type="team_failing",
                    prompt=record.prompt,
                    config=record.config,
                )
                if record.id == "review-critic"
                else record
            )
            for record in records
        ]


class FakeAbortRedis:
    async def get(self, key: str) -> bytes:
        return b"1"


@pytest.mark.asyncio
async def test_team_kernel_runtime_publishes_team_events_and_report(monkeypatch) -> None:
    published: list[tuple[str, str, dict]] = []
    node_events: list[dict] = []

    async def publish(execution_id, event_name, payload):
        published.append((execution_id, event_name, payload))

    async def record_node_event(**kwargs):
        node_events.append(kwargs)

    monkeypatch.setattr(
        "src.agents.lead_agent.v2.team.kernel.dataservice_client",
        lambda: FakeTeamCatalogClient(),
    )

    cap = _team_capability()
    resolver = AsyncMock()
    resolver.resolve = AsyncMock(return_value=cap)
    runtime = LeadAgentRuntime(
        resolver=resolver,
        publish_event=publish,
        get_workspace_type=AsyncMock(return_value="thesis"),
        record_node_event=record_node_event,
    )

    report = await runtime.run_session(execution_id="exec-team", brief=_brief())

    event_names = [event_name for _, event_name, _ in published]
    assert event_names[0] == "execution.graph_structure"
    assert "execution.team.invocation" in event_names
    assert "execution.team.quality_gate" in event_names
    assert event_names[-1] == "execution.completed"
    assert report.status == "completed"
    assert "团队调研" in report.narrative
    assert report.token_usage == {"input": 6, "output": 10}
    assert report.preview_item_id is not None
    assert published[-1][2]["preview_item_id"] == report.preview_item_id
    assert any(event["node_type"] == "agent_invocation" for event in node_events)
    completed_agent_nodes = [
        event
        for event in node_events
        if event["node_type"] == "agent_invocation" and event["status"] == "completed"
    ]
    assert any(
        event["node_metadata"]["harness"].get("expert_preview_items")
        for event in completed_agent_nodes
    )


@pytest.mark.asyncio
async def test_team_kernel_runtime_records_harness_file_change_summary(monkeypatch) -> None:
    node_events: list[dict] = []

    async def record_node_event(**kwargs):
        node_events.append(kwargs)

    monkeypatch.setattr(
        "src.agents.lead_agent.v2.team.kernel.dataservice_client",
        lambda: SandboxToolTeamCatalogClient(),
    )

    cap = _team_capability()
    resolver = AsyncMock()
    resolver.resolve = AsyncMock(return_value=cap)
    runtime = LeadAgentRuntime(
        resolver=resolver,
        publish_event=AsyncMock(),
        get_workspace_type=AsyncMock(return_value="thesis"),
        record_node_event=record_node_event,
    )

    report = await runtime.run_session(execution_id="exec-team-sandbox-summary", brief=_brief())

    completed_events = [
        event
        for event in node_events
        if event["node_type"] == "agent_invocation" and event["status"] == "completed"
    ]
    summaries = [
        event["node_metadata"]["harness"]["file_change_summary"]
        for event in completed_events
        if event["node_metadata"].get("harness")
    ]
    assert report.status == "completed"
    assert summaries
    assert summaries[0]["schema"] == "wenjin.harness.file_change_summary.v1"
    assert summaries[0]["changed_paths"] == ["/workspace/main.tex"]
    assert summaries[0]["changes"][0]["after_hash"] == "sha256:new"


@pytest.mark.asyncio
async def test_team_kernel_runtime_records_harness_tool_failure_summary(monkeypatch) -> None:
    node_events: list[dict] = []

    async def record_node_event(**kwargs):
        node_events.append(kwargs)

    monkeypatch.setattr(
        "src.agents.lead_agent.v2.team.kernel.dataservice_client",
        lambda: SandboxToolFailureTeamCatalogClient(),
    )

    cap = _team_capability()
    resolver = AsyncMock()
    resolver.resolve = AsyncMock(return_value=cap)
    runtime = LeadAgentRuntime(
        resolver=resolver,
        publish_event=AsyncMock(),
        get_workspace_type=AsyncMock(return_value="thesis"),
        record_node_event=record_node_event,
    )

    report = await runtime.run_session(execution_id="exec-team-sandbox-failure-summary", brief=_brief())

    completed_events = [
        event
        for event in node_events
        if event["node_type"] == "agent_invocation" and event["status"] == "completed"
    ]
    summaries = [
        event["node_metadata"]["harness"]["tool_failure_summary"]
        for event in completed_events
        if event["node_metadata"].get("harness")
    ]
    assert report.status == "completed"
    assert summaries
    assert summaries[0]["schema"] == "wenjin.harness.tool_failure_summary.v1"
    assert summaries[0]["failed_tools"] == ["sandbox.read_file"]
    assert summaries[0]["failures"][0]["error_code"] == "tool_error"


@pytest.mark.asyncio
async def test_team_kernel_runtime_records_harness_sandbox_execution_summary(monkeypatch) -> None:
    node_events: list[dict] = []

    async def record_node_event(**kwargs):
        node_events.append(kwargs)

    monkeypatch.setattr(
        "src.agents.lead_agent.v2.team.kernel.dataservice_client",
        lambda: SandboxPythonTeamCatalogClient(),
    )

    cap = _team_capability()
    resolver = AsyncMock()
    resolver.resolve = AsyncMock(return_value=cap)
    runtime = LeadAgentRuntime(
        resolver=resolver,
        publish_event=AsyncMock(),
        get_workspace_type=AsyncMock(return_value="thesis"),
        record_node_event=record_node_event,
    )

    report = await runtime.run_session(execution_id="exec-team-sandbox-execution-summary", brief=_brief())

    completed_events = [
        event
        for event in node_events
        if event["node_type"] == "agent_invocation" and event["status"] == "completed"
    ]
    summaries = [
        event["node_metadata"]["harness"]["sandbox_execution_summary"]
        for event in completed_events
        if event["node_metadata"].get("harness")
    ]
    assert report.status == "completed"
    assert summaries
    assert summaries[0]["schema"] == "wenjin.harness.sandbox_execution_summary.v1"
    assert summaries[0]["python_runs"] == 1
    assert summaries[0]["failed_python_runs"] == 1
    assert summaries[0]["recoverable_failures"] == 1
    assert summaries[0]["sandbox_job_ids"] == ["job-team-1"]
    assert summaries[0]["sandbox_environment_ids"] == ["env-team-1"]
    assert summaries[0]["failure_codes"] == ["python_exit_nonzero"]
    assert summaries[0]["generated_artifact_count"] == 1


@pytest.mark.asyncio
async def test_team_kernel_runtime_records_harness_run_journal_summary(monkeypatch) -> None:
    node_events: list[dict] = []

    async def record_node_event(**kwargs):
        node_events.append(kwargs)

    monkeypatch.setattr(
        "src.agents.lead_agent.v2.team.kernel.dataservice_client",
        lambda: SandboxPythonTeamCatalogClient(),
    )

    cap = _team_capability()
    resolver = AsyncMock()
    resolver.resolve = AsyncMock(return_value=cap)
    runtime = LeadAgentRuntime(
        resolver=resolver,
        publish_event=AsyncMock(),
        get_workspace_type=AsyncMock(return_value="thesis"),
        record_node_event=record_node_event,
    )

    report = await runtime.run_session(execution_id="exec-team-run-journal-summary", brief=_brief())

    completed_events = [
        event
        for event in node_events
        if event["node_type"] == "agent_invocation" and event["status"] == "completed"
    ]
    summaries = [
        event["node_metadata"]["harness"]["run_journal_summary"]
        for event in completed_events
        if event["node_metadata"].get("harness")
    ]
    assert report.status == "completed"
    assert summaries
    assert summaries[0]["schema"] == "wenjin.harness.run_journal_summary.v1"
    assert summaries[0]["latest_phase"] == "tool_completed"
    assert summaries[0]["summary"] == "实验需要修订"
    assert summaries[0]["tool_call_count"] == 1
    assert summaries[0]["artifact_count"] == 1


@pytest.mark.asyncio
async def test_team_kernel_runtime_batches_skill_catalog_loads(monkeypatch) -> None:
    CountingTeamCatalogClient.skill_list_calls = 0
    monkeypatch.setattr(
        "src.agents.lead_agent.v2.team.kernel.dataservice_client",
        lambda: CountingTeamCatalogClient(),
    )

    cap = _team_capability()
    resolver = AsyncMock()
    resolver.resolve = AsyncMock(return_value=cap)
    runtime = LeadAgentRuntime(
        resolver=resolver,
        publish_event=AsyncMock(),
        get_workspace_type=AsyncMock(return_value="thesis"),
    )

    report = await runtime.run_session(execution_id="exec-team-skill-cache", brief=_brief())

    assert report.status == "completed"
    assert CountingTeamCatalogClient.skill_list_calls == 1


@pytest.mark.asyncio
async def test_team_kernel_runtime_injects_quality_contract_into_member_brief(monkeypatch) -> None:
    node_events: list[dict] = []

    async def record_node_event(**kwargs):
        node_events.append(kwargs)

    monkeypatch.setattr(
        "src.agents.lead_agent.v2.team.kernel.dataservice_client",
        lambda: FakeTeamCatalogClient(),
    )

    cap = _team_capability()
    resolver = AsyncMock()
    resolver.resolve = AsyncMock(return_value=cap)
    runtime = LeadAgentRuntime(
        resolver=resolver,
        publish_event=AsyncMock(),
        get_workspace_type=AsyncMock(return_value="thesis"),
        record_node_event=record_node_event,
    )

    report = await runtime.run_session(execution_id="exec-team-quality-contract", brief=_brief())

    running_events = [
        event
        for event in node_events
        if event["node_type"] == "agent_invocation" and event["status"] == "running"
    ]
    assert report.status == "completed"
    assert running_events
    for event in running_events:
        contract = event["input_data"]["quality_contract"]
        assert contract["schema_version"] == "resolved_quality_contract.v1"
        assert contract["template_id"] in {
            "research_scout.v1",
            "critical_reviewer.v1",
        }
        assert contract["quality_gates"] == [
            "evidence_traceability",
            "critical_review",
        ]


@pytest.mark.asyncio
async def test_team_kernel_runtime_batches_all_core_members_across_parallel_limit(monkeypatch) -> None:
    published: list[tuple[str, str, dict]] = []

    async def publish(execution_id, event_name, payload):
        published.append((execution_id, event_name, payload))

    monkeypatch.setattr(
        "src.agents.lead_agent.v2.team.kernel.dataservice_client",
        lambda: FakeTeamCatalogClient(),
    )

    cap = _team_capability()
    cap.definition_json["team_policy"]["core_templates"].append("generalist_assistant.v1")
    cap.definition_json["team_policy"]["optional_templates"] = []
    cap.definition_json["team_policy"]["limits"]["max_parallel_invocations"] = 2
    cap.definition_json["team_policy"]["limits"]["max_invocations_total"] = 3
    resolver = AsyncMock()
    resolver.resolve = AsyncMock(return_value=cap)
    runtime = LeadAgentRuntime(
        resolver=resolver,
        publish_event=publish,
        get_workspace_type=AsyncMock(return_value="thesis"),
    )

    report = await runtime.run_session(execution_id="exec-team-core-batches", brief=_brief())

    invocations = [
        payload["invocation"]
        for _, event_name, payload in published
        if event_name == "execution.team.invocation"
    ]
    completed_by_id = {item["id"]: item for item in invocations if item["status"] != "running"}

    assert report.status == "completed"
    assert len(completed_by_id) == 3
    assert any(
        item["template_id"] == "generalist_assistant.v1"
        for item in completed_by_id.values()
    )
    assert all(item["iteration"] == 1 for item in completed_by_id.values())


@pytest.mark.asyncio
async def test_team_kernel_runtime_stops_when_template_policy_invalid(monkeypatch) -> None:
    cap = _team_capability()
    cap.definition_json["team_policy"]["core_templates"] = ["missing_template.v1"]
    resolver = AsyncMock()
    resolver.resolve = AsyncMock(return_value=cap)

    class EmptyTeamCatalogClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def list_agent_templates(self, *, enabled_only: bool = True):
            return []

    monkeypatch.setattr(
        "src.agents.lead_agent.v2.team.kernel.dataservice_client",
        lambda: EmptyTeamCatalogClient(),
    )

    runtime = LeadAgentRuntime(
        resolver=resolver,
        get_workspace_type=AsyncMock(return_value="thesis"),
    )

    report = await runtime.run_session(execution_id="exec-team-invalid", brief=_brief())

    assert report.status == "failed_partial"
    assert report.errors
    assert "unknown agent template" in report.errors[0].error


@pytest.mark.asyncio
async def test_team_kernel_runtime_records_cancelled_invocations(monkeypatch) -> None:
    published: list[tuple[str, str, dict]] = []
    node_events: list[dict] = []
    CapturingCancelledEpisodeClient.runtime_state_updates.clear()

    async def publish(execution_id, event_name, payload):
        published.append((execution_id, event_name, payload))

    async def record_node_event(**kwargs):
        node_events.append(kwargs)

    monkeypatch.setattr(
        "src.agents.lead_agent.v2.team.kernel.dataservice_client",
        lambda: CapturingCancelledEpisodeClient(),
    )

    cap = _team_capability()
    resolver = AsyncMock()
    resolver.resolve = AsyncMock(return_value=cap)
    runtime = LeadAgentRuntime(
        resolver=resolver,
        publish_event=publish,
        get_workspace_type=AsyncMock(return_value="thesis"),
        record_node_event=record_node_event,
        redis=FakeAbortRedis(),
    )

    report = await runtime.run_session(execution_id="exec-team-cancelled", brief=_brief())

    node_statuses = [event["status"] for event in node_events if event["node_type"] == "agent_invocation"]
    invocation_statuses = [
        payload["invocation"]["status"]
        for _, event_name, payload in published
        if event_name == "execution.team.invocation"
    ]
    assert report.status == "cancelled"
    assert "cancelled" in node_statuses
    assert "cancelled" in invocation_statuses
    runtime_state = CapturingCancelledEpisodeClient.runtime_state_updates[-1]["runtime_state_json"]
    assert runtime_state["harness_episode"]["status"] == "finished"
    assert runtime_state["harness_episode"]["stop_reason"] == "cancelled"


@pytest.mark.asyncio
async def test_team_kernel_runtime_marks_failed_member_as_partial(monkeypatch) -> None:
    node_events: list[dict] = []

    async def record_node_event(**kwargs):
        node_events.append(kwargs)

    monkeypatch.setattr(
        "src.agents.lead_agent.v2.team.kernel.dataservice_client",
        lambda: FakeFailingTeamCatalogClient(),
    )

    cap = _team_capability()
    resolver = AsyncMock()
    resolver.resolve = AsyncMock(return_value=cap)
    runtime = LeadAgentRuntime(
        resolver=resolver,
        publish_event=AsyncMock(),
        get_workspace_type=AsyncMock(return_value="thesis"),
        record_node_event=record_node_event,
    )

    report = await runtime.run_session(execution_id="exec-team-failed", brief=_brief())

    assert report.status == "failed_partial"
    assert report.errors
    assert any(event["status"] == "failed" for event in node_events)


@pytest.mark.asyncio
async def test_team_kernel_runtime_records_skill_catalog_failure_as_member_failures(monkeypatch) -> None:
    node_events: list[dict] = []

    async def record_node_event(**kwargs):
        node_events.append(kwargs)

    monkeypatch.setattr(
        "src.agents.lead_agent.v2.team.kernel.dataservice_client",
        lambda: FakeSkillCatalogFailingClient(),
    )

    cap = _team_capability()
    resolver = AsyncMock()
    resolver.resolve = AsyncMock(return_value=cap)
    runtime = LeadAgentRuntime(
        resolver=resolver,
        publish_event=AsyncMock(),
        get_workspace_type=AsyncMock(return_value="thesis"),
        record_node_event=record_node_event,
    )

    report = await runtime.run_session(execution_id="exec-team-skill-load-fails", brief=_brief())

    assert report.status == "failed_partial"
    assert report.errors
    assert all(error.task != "team_kernel" for error in report.errors)
    assert any(event["status"] == "failed" for event in node_events)
    assert any(event["error"] == "skill catalog unavailable" for event in node_events)


@pytest.mark.asyncio
async def test_team_kernel_runtime_supplies_query_and_business_tools_to_sci_literature_team(monkeypatch) -> None:
    TeamCaptureSubagent.contexts = []

    monkeypatch.setattr(
        "src.agents.lead_agent.v2.team.kernel.dataservice_client",
        lambda: SciLiteratureTeamCatalogClient(),
    )

    cap = SimpleNamespace(
        id="sci_literature_positioning",
        workspace_type="sci",
        display_name="文献定位与创新点",
        runtime={
            "mode": "team_kernel",
            "allowed_tools": [
                "web_search",
                "library_read",
                "prism_file_read",
                "citation_parser",
                "artifact_create",
            ],
        },
        graph_template={},
        definition_json={
            "mission": {"primary_surface": "prism"},
            "team_policy": {
                "core_templates": ["research_scout.v1", "literature_synthesizer.v1"],
                "optional_templates": [],
                "recruitment_triggers": {},
                "capability_tools": [
                    "web_search",
                    "library_read",
                    "prism_file_read",
                    "citation_parser",
                    "artifact_create",
                ],
                "capability_skills": ["research-scout", "literature-synthesizer"],
                "quality_pipeline": [],
                "limits": {
                    "max_iterations": 1,
                    "max_parallel_invocations": 2,
                    "max_invocations_total": 2,
                },
            },
        },
    )
    resolver = AsyncMock()
    resolver.resolve = AsyncMock(return_value=cap)
    runtime = LeadAgentRuntime(
        resolver=resolver,
        publish_event=AsyncMock(),
        get_workspace_type=AsyncMock(return_value="sci"),
    )

    report = await runtime.run_session(
        execution_id="exec-sci-literature-context",
        brief=TaskBrief(
            capability_id="sci_literature_positioning",
            raw_message="联邦学习结合大模型 (Federated Learning combined with Large Language Models)",
            workspace_id="ws-sci",
            user_id="user-1",
            brief={},
        ),
    )

    contexts_by_template = {
        ctx.invocation["template_id"]: ctx
        for ctx in TeamCaptureSubagent.contexts
    }
    scout = contexts_by_template["research_scout.v1"]
    synthesizer = contexts_by_template["literature_synthesizer.v1"]
    assert report.status == "completed"
    assert scout.inputs["query"] == "Federated Learning combined with Large Language Models"
    assert scout.inputs["task_focus"]
    assert {
        "library_read",
        "prism_file_read",
        "citation_parser",
        "artifact_create",
    }.issubset(set(synthesizer.tools))


@pytest.mark.asyncio
async def test_team_kernel_core_phase_respects_graph_dependencies_for_upstream_context(monkeypatch) -> None:
    TeamSequentialCaptureSubagent.contexts = []

    monkeypatch.setattr(
        "src.agents.lead_agent.v2.team.kernel.dataservice_client",
        lambda: SequentialSciLiteratureTeamCatalogClient(),
    )

    cap = SimpleNamespace(
        id="sci_literature_positioning",
        workspace_type="sci",
        display_name="文献定位与创新点",
        runtime={"mode": "team_kernel", "allowed_tools": ["web_search", "library_read"]},
        graph_template={
            "phases": [
                {
                    "name": "step_01_research_scout",
                    "tasks": [{"name": "research_scout", "skill_id": "research-scout"}],
                },
                {
                    "name": "step_02_literature_synthesizer",
                    "depends_on": ["step_01_research_scout"],
                    "tasks": [
                        {
                            "name": "literature_synthesizer",
                            "skill_id": "literature-synthesizer",
                        }
                    ],
                },
            ]
        },
        definition_json={
            "mission": {"primary_surface": "prism"},
            "team_policy": {
                "core_templates": ["research_scout.v1", "literature_synthesizer.v1"],
                "optional_templates": [],
                "recruitment_triggers": {},
                "capability_tools": ["web_search", "library_read"],
                "capability_skills": ["research-scout", "literature-synthesizer"],
                "quality_pipeline": [],
                "limits": {
                    "max_iterations": 1,
                    "max_parallel_invocations": 2,
                    "max_invocations_total": 2,
                },
            },
        },
    )
    resolver = AsyncMock()
    resolver.resolve = AsyncMock(return_value=cap)
    runtime = LeadAgentRuntime(
        resolver=resolver,
        publish_event=AsyncMock(),
        get_workspace_type=AsyncMock(return_value="sci"),
    )

    report = await runtime.run_session(
        execution_id="exec-sci-literature-sequential",
        brief=TaskBrief(
            capability_id="sci_literature_positioning",
            raw_message="Federated LoRA fine-tuning LLMs",
            workspace_id="ws-sci",
            user_id="user-1",
            brief={"topic": "Federated LoRA fine-tuning LLMs"},
        ),
    )

    assert report.status == "completed"
    assert [
        ctx.invocation["template_id"]
        for ctx in TeamSequentialCaptureSubagent.contexts
    ] == ["research_scout.v1", "literature_synthesizer.v1"]
    synthesizer = TeamSequentialCaptureSubagent.contexts[-1]
    upstream_context = synthesizer.inputs["upstream_context"]
    evidence = upstream_context["evidence_items"][0]
    assert evidence["kind"] == "source_search_results"
    assert evidence["papers"][0]["title"] == "Paper A"


@pytest.mark.asyncio
async def test_team_kernel_runtime_recruits_optional_member_after_failed_core(monkeypatch) -> None:
    published: list[tuple[str, str, dict]] = []
    node_events: list[dict] = []

    async def publish(execution_id, event_name, payload):
        published.append((execution_id, event_name, payload))

    async def record_node_event(**kwargs):
        node_events.append(kwargs)

    monkeypatch.setattr(
        "src.agents.lead_agent.v2.team.kernel.dataservice_client",
        lambda: FakeCriticalReviewerFailingTeamCatalogClient(),
    )

    cap = _team_capability()
    cap.definition_json["team_policy"]["capability_skills"].append("failing-review-critic")
    resolver = AsyncMock()
    resolver.resolve = AsyncMock(return_value=cap)
    runtime = LeadAgentRuntime(
        resolver=resolver,
        publish_event=publish,
        get_workspace_type=AsyncMock(return_value="thesis"),
        record_node_event=record_node_event,
    )

    report = await runtime.run_session(execution_id="exec-team-recruit", brief=_brief())

    invocations = [
        payload["invocation"]
        for _, event_name, payload in published
        if event_name == "execution.team.invocation"
    ]
    completed_by_id = {item["id"]: item for item in invocations if item["status"] != "running"}
    quality_gates = [
        payload["quality_gate"]
        for _, event_name, payload in published
        if event_name == "execution.team.quality_gate"
    ]

    generalist = [
        item
        for item in completed_by_id.values()
        if item["template_id"] == "generalist_assistant.v1"
    ]
    assert report.status == "failed_partial"
    assert generalist
    assert generalist[0]["iteration"] == 2
    assert "quality gate requested" in generalist[0]["recruitment_reason"]
    assert any(gate["next_action"] == "recruit_more" for gate in quality_gates)
    assert any(
        recruit["template_id"] == "generalist_assistant.v1"
        for gate in quality_gates
        for recruit in gate["suggested_recruits"]
    )
    assert any(
        event["node_metadata"]["template_id"] == "generalist_assistant.v1"
        for event in node_events
    )


@pytest.mark.asyncio
async def test_team_kernel_failed_partial_does_not_surface_empty_or_policy_memory_outputs(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.agents.lead_agent.v2.team.kernel.dataservice_client",
        lambda: FailingAndEmptyTeamCatalogClient(),
    )

    cap = _team_capability()
    cap.definition_json["review_policy"] = {
        "default_targets": ["room_memory_candidate"],
    }
    cap.definition_json["team_policy"]["optional_templates"] = []
    cap.definition_json["team_policy"]["recruitment_triggers"] = {}
    cap.definition_json["team_policy"]["quality_pipeline"] = []
    cap.definition_json["team_policy"]["capability_skills"] = [
        "failing-research-scout",
        "empty-review-critic",
    ]
    resolver = AsyncMock()
    resolver.resolve = AsyncMock(return_value=cap)
    runtime = LeadAgentRuntime(
        resolver=resolver,
        publish_event=AsyncMock(),
        get_workspace_type=AsyncMock(return_value="thesis"),
    )

    report = await runtime.run_session(execution_id="exec-team-empty-partial", brief=_brief())

    assert report.status == "failed_partial"
    assert report.outputs == []
    assert "未能完成" in report.narrative
    assert not report.narrative.startswith("完成 ")


@pytest.mark.asyncio
async def test_team_kernel_replays_current_harness_evidence_to_recruited_members(monkeypatch) -> None:
    TeamCaptureSubagent.contexts = []
    monkeypatch.setattr(
        "src.agents.lead_agent.v2.team.kernel.dataservice_client",
        lambda: SandboxEvidenceReplayTeamCatalogClient(),
    )

    cap = _team_capability()
    cap.definition_json["team_policy"]["capability_skills"].extend(
        ["sandbox-writer", "failing-review-critic", "generalist-capture"]
    )
    resolver = AsyncMock()
    resolver.resolve = AsyncMock(return_value=cap)
    runtime = LeadAgentRuntime(
        resolver=resolver,
        publish_event=AsyncMock(),
        get_workspace_type=AsyncMock(return_value="thesis"),
    )

    report = await runtime.run_session(execution_id="exec-team-harness-replay", brief=_brief())

    assert report.status == "failed_partial"
    captured = [
        ctx
        for ctx in TeamCaptureSubagent.contexts
        if ctx.invocation["template_id"] == "generalist_assistant.v1"
    ]
    assert captured
    recent = captured[0].workspace_data["recent_executions"]
    assert recent[0]["node_metadata"]["harness"]["file_change_summary"]["changed_paths"] == [
        "/workspace/main.tex"
    ]
    assert recent[0]["display_name"] == "文献检索员"


@pytest.mark.asyncio
async def test_team_kernel_runtime_persists_quality_gates_to_runtime_state(monkeypatch) -> None:
    CapturingQualityGateRuntimeStateClient.runtime_state_updates = []

    monkeypatch.setattr(
        "src.agents.lead_agent.v2.team.kernel.dataservice_client",
        lambda: CapturingQualityGateRuntimeStateClient(),
    )

    cap = _team_capability()
    cap.definition_json["team_policy"]["capability_skills"].append("failing-review-critic")
    resolver = AsyncMock()
    resolver.resolve = AsyncMock(return_value=cap)
    runtime = LeadAgentRuntime(
        resolver=resolver,
        publish_event=AsyncMock(),
        get_workspace_type=AsyncMock(return_value="thesis"),
    )

    report = await runtime.run_session(execution_id="exec-team-quality-state", brief=_brief())

    assert report.status == "failed_partial"
    assert CapturingQualityGateRuntimeStateClient.runtime_state_updates
    latest_runtime_state = CapturingQualityGateRuntimeStateClient.runtime_state_updates[-1][
        "runtime_state_json"
    ]
    assert latest_runtime_state["existing_key"] == "preserved"
    assert latest_runtime_state["quality_gates"]
    assert {
        gate["gate_id"]
        for gate in latest_runtime_state["quality_gates"]
    } >= {
        "critical_review",
        "evidence_traceability",
    }


@pytest.mark.asyncio
async def test_team_kernel_runtime_revises_existing_member_after_schema_gate(monkeypatch) -> None:
    published: list[tuple[str, str, dict]] = []

    async def publish(execution_id, event_name, payload):
        published.append((execution_id, event_name, payload))

    monkeypatch.setattr(
        "src.agents.lead_agent.v2.team.kernel.dataservice_client",
        lambda: SchemaRequiredTeamCatalogClient(),
    )

    cap = _team_capability()
    cap.definition_json["team_policy"]["limits"]["max_iterations"] = 2
    cap.definition_json["team_policy"]["limits"]["max_invocations_total"] = 4
    resolver = AsyncMock()
    resolver.resolve = AsyncMock(return_value=cap)
    runtime = LeadAgentRuntime(
        resolver=resolver,
        publish_event=publish,
        get_workspace_type=AsyncMock(return_value="thesis"),
    )

    report = await runtime.run_session(execution_id="exec-team-schema-revise", brief=_brief())

    invocations = [
        payload["invocation"]
        for _, event_name, payload in published
        if event_name == "execution.team.invocation"
    ]
    completed_by_id = {item["id"]: item for item in invocations if item["status"] != "running"}
    quality_gates = [
        payload["quality_gate"]
        for _, event_name, payload in published
        if event_name == "execution.team.quality_gate"
    ]

    assert report.status == "failed_partial"
    assert any(
        item["template_id"] == "research_scout.v1" and item["iteration"] == 2
        for item in completed_by_id.values()
    )
    assert any(
        gate["gate_id"] == "output_schema_min_shape"
        and gate["next_action"] == "revise_existing"
        for gate in quality_gates
    )


@pytest.mark.asyncio
async def test_team_kernel_runtime_resolves_graph_declared_outputs(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.agents.lead_agent.v2.team.kernel.dataservice_client",
        lambda: MappingTeamCatalogClient(),
    )

    cap = _team_capability()
    cap.graph_template = {
        "phases": [
            {
                "name": "step_01_research_scout",
                "tasks": [
                    {
                        "name": "research_scout",
                        "subagent_type": "searcher",
                        "skill_id": "research-scout",
                        "outputs": [
                            {
                                "kind": "library_item",
                                "iterate_on": "output.papers",
                                "default_checked": True,
                                "mapping": {
                                    "title": "{{item.title}}",
                                    "authors": "{{item.authors}}",
                                    "year": "{{item.year}}",
                                    "doi": "{{item.doi}}",
                                    "abstract": "{{item.abstract}}",
                                },
                            }
                        ],
                    }
                ],
            },
            {
                "name": "step_02_final_report",
                "tasks": [
                    {
                        "name": "source_quality_auditor",
                        "subagent_type": "react",
                        "skill_id": "source-quality-auditor",
                        "outputs": [
                            {
                                "kind": "document",
                                "default_checked": True,
                                "mapping": {
                                    "name": "文献定位与创新点.md",
                                    "doc_kind": "review_report",
                                    "content": "{{output.text}}",
                                },
                            }
                        ],
                    }
                ],
            },
        ]
    }
    resolver = AsyncMock()
    resolver.resolve = AsyncMock(return_value=cap)
    runtime = LeadAgentRuntime(
        resolver=resolver,
        publish_event=AsyncMock(),
        get_workspace_type=AsyncMock(return_value="thesis"),
    )

    report = await runtime.run_session(execution_id="exec-team-output-map", brief=_brief())

    assert report.status == "completed"
    assert any(output.kind == "library_item" for output in report.outputs)
    library_output = next(output for output in report.outputs if output.kind == "library_item")
    assert library_output.data.title == "Paper A"
    document_output = next(
        output
        for output in report.outputs
        if output.kind == "document" and output.data.name == "文献定位与创新点.md"
    )
    assert "文献检索员" in document_output.data.content


@pytest.mark.asyncio
async def test_team_kernel_runtime_does_not_fail_report_after_successful_revision(monkeypatch) -> None:
    TeamSchemaRepairSubagent.calls = {}
    published: list[tuple[str, str, dict]] = []

    async def publish(execution_id, event_name, payload):
        published.append((execution_id, event_name, payload))

    monkeypatch.setattr(
        "src.agents.lead_agent.v2.team.kernel.dataservice_client",
        lambda: SchemaRepairTeamCatalogClient(),
    )

    cap = _team_capability()
    cap.definition_json["team_policy"]["limits"]["max_iterations"] = 2
    cap.definition_json["team_policy"]["limits"]["max_invocations_total"] = 4
    resolver = AsyncMock()
    resolver.resolve = AsyncMock(return_value=cap)
    runtime = LeadAgentRuntime(
        resolver=resolver,
        publish_event=publish,
        get_workspace_type=AsyncMock(return_value="thesis"),
    )

    report = await runtime.run_session(execution_id="exec-team-schema-repaired", brief=_brief())

    quality_gates = [
        payload["quality_gate"]
        for _, event_name, payload in published
        if event_name == "execution.team.quality_gate"
    ]
    assert report.status == "completed"
    assert not report.errors
    assert any(
        gate["gate_id"] == "output_schema_min_shape"
        and gate["next_action"] == "revise_existing"
        for gate in quality_gates
    )


@pytest.mark.asyncio
async def test_team_kernel_runtime_loads_skill_catalog_once_across_dynamic_recruitment(monkeypatch) -> None:
    CountingGeneralistNewSkillCatalogClient.skill_list_calls = 0
    monkeypatch.setattr(
        "src.agents.lead_agent.v2.team.kernel.dataservice_client",
        lambda: CountingGeneralistNewSkillCatalogClient(),
    )

    cap = _team_capability()
    cap.definition_json["team_policy"]["capability_skills"].extend(
        ["failing-review-critic", "generalist-helper"]
    )
    resolver = AsyncMock()
    resolver.resolve = AsyncMock(return_value=cap)
    runtime = LeadAgentRuntime(
        resolver=resolver,
        publish_event=AsyncMock(),
        get_workspace_type=AsyncMock(return_value="thesis"),
    )

    report = await runtime.run_session(execution_id="exec-team-skill-catalog-once", brief=_brief())

    assert report.status == "failed_partial"
    assert CountingGeneralistNewSkillCatalogClient.skill_list_calls == 1


@pytest.mark.asyncio
async def test_team_kernel_runtime_recruits_after_failed_core_in_earlier_batch(monkeypatch) -> None:
    published: list[tuple[str, str, dict]] = []

    async def publish(execution_id, event_name, payload):
        published.append((execution_id, event_name, payload))

    monkeypatch.setattr(
        "src.agents.lead_agent.v2.team.kernel.dataservice_client",
        lambda: FakeCriticalReviewerFailingTeamCatalogClient(),
    )

    cap = _team_capability()
    cap.definition_json["team_policy"]["core_templates"] = [
        "critical_reviewer.v1",
        "research_scout.v1",
    ]
    cap.definition_json["team_policy"]["capability_skills"].append("failing-review-critic")
    cap.definition_json["team_policy"]["limits"]["max_parallel_invocations"] = 1
    cap.definition_json["team_policy"]["limits"]["max_invocations_total"] = 3
    resolver = AsyncMock()
    resolver.resolve = AsyncMock(return_value=cap)
    runtime = LeadAgentRuntime(
        resolver=resolver,
        publish_event=publish,
        get_workspace_type=AsyncMock(return_value="thesis"),
    )

    report = await runtime.run_session(execution_id="exec-team-earlier-failure", brief=_brief())

    invocations = [
        payload["invocation"]
        for _, event_name, payload in published
        if event_name == "execution.team.invocation"
    ]
    completed_by_id = {item["id"]: item for item in invocations if item["status"] != "running"}

    assert report.status == "failed_partial"
    assert any(
        item["template_id"] == "generalist_assistant.v1"
        for item in completed_by_id.values()
    )


@pytest.mark.asyncio
async def test_team_kernel_runtime_respects_total_invocation_limit_before_recruiting(monkeypatch) -> None:
    published: list[tuple[str, str, dict]] = []

    async def publish(execution_id, event_name, payload):
        published.append((execution_id, event_name, payload))

    monkeypatch.setattr(
        "src.agents.lead_agent.v2.team.kernel.dataservice_client",
        lambda: FakeCriticalReviewerFailingTeamCatalogClient(),
    )

    cap = _team_capability()
    cap.definition_json["team_policy"]["capability_skills"].append("failing-review-critic")
    cap.definition_json["team_policy"]["limits"]["max_invocations_total"] = 2
    resolver = AsyncMock()
    resolver.resolve = AsyncMock(return_value=cap)
    runtime = LeadAgentRuntime(
        resolver=resolver,
        publish_event=publish,
        get_workspace_type=AsyncMock(return_value="thesis"),
    )

    report = await runtime.run_session(execution_id="exec-team-total-limit", brief=_brief())

    invocations = [
        payload["invocation"]
        for _, event_name, payload in published
        if event_name == "execution.team.invocation"
    ]
    completed_by_id = {item["id"]: item for item in invocations if item["status"] != "running"}
    quality_gates = [
        payload["quality_gate"]
        for _, event_name, payload in published
        if event_name == "execution.team.quality_gate"
    ]

    assert report.status == "failed_partial"
    assert len(completed_by_id) == 2
    assert all(
        item["template_id"] != "generalist_assistant.v1"
        for item in completed_by_id.values()
    )
    assert all(gate["next_action"] != "recruit_more" for gate in quality_gates)
    assert all(not gate["suggested_recruits"] for gate in quality_gates)


@pytest.mark.asyncio
async def test_team_kernel_runtime_caps_repeated_optional_recruits(monkeypatch) -> None:
    published: list[tuple[str, str, dict]] = []

    async def publish(execution_id, event_name, payload):
        published.append((execution_id, event_name, payload))

    monkeypatch.setattr(
        "src.agents.lead_agent.v2.team.kernel.dataservice_client",
        lambda: FakeFailingTeamCatalogClient(),
    )

    cap = _team_capability()
    cap.definition_json["team_policy"]["limits"]["max_iterations"] = 3
    cap.definition_json["team_policy"]["limits"]["max_invocations_per_template"] = 1
    cap.definition_json["team_policy"]["limits"]["max_invocations_total"] = 4
    resolver = AsyncMock()
    resolver.resolve = AsyncMock(return_value=cap)
    runtime = LeadAgentRuntime(
        resolver=resolver,
        publish_event=publish,
        get_workspace_type=AsyncMock(return_value="thesis"),
    )

    report = await runtime.run_session(execution_id="exec-team-template-limit", brief=_brief())

    invocations = [
        payload["invocation"]
        for _, event_name, payload in published
        if event_name == "execution.team.invocation"
    ]
    completed_by_id = {item["id"]: item for item in invocations if item["status"] != "running"}
    generalist_invocations = [
        item
        for item in completed_by_id.values()
        if item["template_id"] == "generalist_assistant.v1"
    ]

    assert report.status == "failed_partial"
    assert len(generalist_invocations) == 1


def test_build_academic_harness_outputs_attaches_review_packet_and_research_state() -> None:
    report = sanitize_expert_report(
        {
            "schema_version": "wenjin.expert_report.v1",
            "expert_id": "literature_synthesizer.v1",
            "skill_id": "literature-synthesizer",
            "task_focus": "Synthesize literature.",
            "summary": "Found one supported direction.",
            "claims": [
                {
                    "claim_id": "claim-1",
                    "text": "FedLoRA reduces communication.",
                    "support_level": "supported",
                    "evidence_ids": ["ev-1"],
                    "citation_keys": ["smith2025"],
                    "limitations": [],
                }
            ],
            "evidence": [
                {
                    "evidence_id": "ev-1",
                    "source_type": "library_reference",
                    "source_id": "source-1",
                    "citation_key": "smith2025",
                    "relevance": "high",
                    "risk": "low",
                    "bounded_excerpt": "communication reduction",
                    "used_for": ["claim-1"],
                }
            ],
            "artifacts": [],
            "quality_gates_checked": ["citation_strength"],
            "uncertainties": [],
            "next_actions": [],
        }
    )

    packet, research_state = build_academic_harness_outputs(
        execution_id="exec-1",
        capability_id="sci_literature_positioning",
        capability_name="文献定位与创新点",
        expert_reports=[report],
        completion_status="complete",
        quality_state=[{"surface": "citation_strength", "status": "pass"}],
        research_brief={"brief_id": "brief-1", "user_objective": "找 FedLLM 创新点"},
        workspace_map_summary={"topic_hints": ["FedLLM"], "library": {"source_count": 1}},
    )

    assert packet.items[0].claim_refs == ["claim-1"]
    assert research_state.research_brief == {"brief_id": "brief-1", "user_objective": "找 FedLLM 创新点"}
    assert research_state.workspace_map_summary["topic_hints"] == ["FedLLM"]
    assert research_state.claims[0]["claim_id"] == "claim-1"
