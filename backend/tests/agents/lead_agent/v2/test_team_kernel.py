from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import src.subagents.v2.types  # noqa: F401
from src.agents.contracts.task_brief import TaskBrief
from src.agents.lead_agent.v2.runtime import LeadAgentRuntime
from src.agents.lead_agent.v2.team.contracts import (
    AgentInvocation,
    AgentTemplate,
    CapabilityTeamPolicy,
)
from src.agents.lead_agent.v2.team.kernel import TeamKernelRuntime
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
        needs_library_context=lambda _policy: True,
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
                    "preferred": ["library_read", "document_read"],
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
    assert any(event["node_type"] == "agent_invocation" for event in node_events)


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
                "document_read",
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
                    "document_read",
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
        "document_read",
        "citation_parser",
        "artifact_create",
    }.issubset(set(synthesizer.tools))


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
