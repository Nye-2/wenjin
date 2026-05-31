from types import SimpleNamespace

import pytest

from src.services.execution_service import ExecutionService


class _FakeExecutionClient:
    def __init__(self) -> None:
        self.updated_payload = None
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
