from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import src.subagents.v2.types  # noqa: F401
from src.agents.contracts.task_brief import TaskBrief
from src.agents.lead_agent.v2.runtime import LeadAgentRuntime
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
