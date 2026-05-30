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
                "core_templates": ["research_scholar.v1", "critical_reviewer.v1"],
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
                id="research_scholar.v1",
                display_role="文献专家",
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
        "research_scholar.v1",
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
