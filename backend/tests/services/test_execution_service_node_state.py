from types import SimpleNamespace

import pytest

from src.services.execution_service import ExecutionService


class _FakeExecutionClient:
    def __init__(self) -> None:
        self.updated_payload = None
        self.lease_claims = []
        self.lease_heartbeats = []
        self.record = SimpleNamespace(
            id="exec-team",
            graph_structure={
                "nodes": [{"id": "research_scout.v1__1", "label": "文献检索员", "phase": "research"}],
                "edges": [],
            },
            node_states={},
        )
        self.node_records = []

    async def get_execution(self, execution_id: str):
        assert execution_id == "exec-team"
        return self.record

    async def update_execution(self, execution_id: str, payload):
        assert execution_id == "exec-team"
        self.updated_payload = payload
        self.record.node_states = payload.node_states_json
        return self.record

    async def list_execution_nodes(self, execution_id: str):
        assert execution_id == "exec-team"
        return self.node_records

    async def list_executions(self, **kwargs):
        _ = kwargs
        return [self.record]

    async def list_execution_nodes_by_execution_ids(self, execution_ids: list[str]):
        assert execution_ids == ["exec-team"]
        return self.node_records

    async def claim_execution_lease(self, execution_id: str, payload):
        self.lease_claims.append((execution_id, payload))
        return {"status": "claimed", "execution": self.record}

    async def heartbeat_execution_lease(self, execution_id: str, payload):
        self.lease_heartbeats.append((execution_id, payload))
        return {"status": "heartbeat", "execution": self.record}


@pytest.mark.asyncio
async def test_update_node_state_persists_team_node_metadata() -> None:
    client = _FakeExecutionClient()
    service = ExecutionService(dataservice=client)  # type: ignore[arg-type]

    await service.update_node_state(
        "exec-team",
        "research_scout.v1__1",
        status="completed",
        node_type="agent_invocation",
        label="文献检索员",
        node_metadata={
            "team": True,
            "template_id": "research_scout.v1",
            "display_name": "文献检索员",
            "effective_tools": ["web_search", "library_read"],
            "effective_skills": ["literature_search.v1"],
        },
    )

    assert client.updated_payload is not None
    assert client.updated_payload.node_states_json == {
        "research_scout.v1__1": {
            "status": "completed",
            "node_type": "agent_invocation",
            "label": "文献检索员",
            "node_metadata": {
                "team": True,
                "template_id": "research_scout.v1",
                "display_name": "文献检索员",
                "effective_tools": ["web_search", "library_read"],
                "effective_skills": ["literature_search.v1"],
            },
        }
    }


@pytest.mark.asyncio
async def test_execution_service_forwards_worker_lease_calls() -> None:
    client = _FakeExecutionClient()
    service = ExecutionService(dataservice=client)  # type: ignore[arg-type]

    claim = await service.claim_execution_lease(
        execution_id="exec-team",
        worker_id="worker-1",
        ttl_seconds=90,
    )
    heartbeat = await service.heartbeat_execution_lease(
        execution_id="exec-team",
        worker_id="worker-1",
        ttl_seconds=120,
    )

    assert claim["status"] == "claimed"
    assert heartbeat["status"] == "heartbeat"
    assert client.lease_claims[0][0] == "exec-team"
    assert client.lease_claims[0][1].worker_id == "worker-1"
    assert client.lease_claims[0][1].ttl_seconds == 90
    assert client.lease_heartbeats[0][0] == "exec-team"
    assert client.lease_heartbeats[0][1].worker_id == "worker-1"
    assert client.lease_heartbeats[0][1].ttl_seconds == 120


@pytest.mark.asyncio
async def test_get_execution_graph_uses_execution_node_records() -> None:
    client = _FakeExecutionClient()
    client.record.node_states = {"research_scout.v1__1": {"status": "failed"}}
    client.node_records = [
        SimpleNamespace(
            node_id="research_scout.v1__1",
            node_type="agent_invocation",
            label="实时文献检索员",
            status="completed",
            input_data={"query": "agent swarm"},
            output_data={"papers": 6},
            thinking="检索完成",
            tool_calls=[{"name": "library_search"}],
            token_usage={"input": 10, "output": 20},
            node_metadata={"team": True},
            started_at=None,
            completed_at=None,
        )
    ]
    service = ExecutionService(dataservice=client)  # type: ignore[arg-type]

    graph = await service.get_execution_graph("exec-team")

    assert graph["nodes"] == [
        {
            "id": "research_scout.v1__1",
            "label": "实时文献检索员",
            "phase": "research",
            "status": "completed",
            "node_type": "agent_invocation",
            "input": {"query": "agent swarm"},
            "output": {"papers": 6},
            "thinking": "检索完成",
            "tool_calls": [{"name": "library_search"}],
            "token_usage": {"input": 10, "output": 20},
            "node_metadata": {"team": True},
            "started_at": None,
            "completed_at": None,
        }
    ]
    assert graph["edges"] == []


@pytest.mark.asyncio
async def test_get_by_id_hydrates_node_states_from_execution_node_records() -> None:
    client = _FakeExecutionClient()
    client.record.node_states = {
        "research_scout.v1__1": {"status": "failed", "label": "缓存文献检索员"}
    }
    client.node_records = [
        SimpleNamespace(
            node_id="research_planner.v1__1",
            node_type="agent_invocation",
            label="研究规划师",
            status="completed",
            input_data=None,
            output_data={"text": "planned"},
            thinking=None,
            tool_calls=[],
            token_usage=None,
            node_metadata={"team": True, "template_id": "research_planner.v1"},
            started_at=None,
            completed_at=None,
        ),
        SimpleNamespace(
            node_id="research_scout.v1__1",
            node_type="agent_invocation",
            label="文献检索员",
            status="failed",
            input_data=None,
            output_data=None,
            thinking=None,
            tool_calls=[],
            token_usage=None,
            node_metadata={"team": True, "template_id": "research_scout.v1"},
            started_at=None,
            completed_at=None,
        ),
    ]
    service = ExecutionService(dataservice=client)  # type: ignore[arg-type]

    record = await service.get_by_id("exec-team")

    assert record.node_states["research_planner.v1__1"]["label"] == "研究规划师"
    assert record.node_states["research_scout.v1__1"]["label"] == "文献检索员"


@pytest.mark.asyncio
async def test_list_executions_hydrates_node_states_from_execution_node_records() -> None:
    client = _FakeExecutionClient()
    client.record.node_states = {}
    client.node_records = [
        SimpleNamespace(
            node_id="literature_synthesizer.v1__1",
            node_type="agent_invocation",
            label="文献综合专家",
            status="failed",
            input_data=None,
            output_data=None,
            thinking=None,
            tool_calls=[],
            token_usage=None,
            node_metadata={"team": True, "template_id": "literature_synthesizer.v1"},
            started_at=None,
            completed_at=None,
        )
    ]
    service = ExecutionService(dataservice=client)  # type: ignore[arg-type]

    records = await service.list_executions(workspace_id="ws-team")

    assert records[0].node_states == {
        "literature_synthesizer.v1__1": {
            "status": "failed",
            "node_type": "agent_invocation",
            "input": None,
            "output": None,
            "thinking": None,
            "tool_calls": [],
            "token_usage": None,
            "node_metadata": {
                "team": True,
                "template_id": "literature_synthesizer.v1",
            },
            "started_at": None,
            "completed_at": None,
            "label": "文献综合专家",
        }
    }
