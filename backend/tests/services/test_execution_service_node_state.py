from types import SimpleNamespace

import pytest

from src.services.execution_service import ExecutionService


class _FakeExecutionClient:
    def __init__(self) -> None:
        self.updated_payload = None
        self.record = SimpleNamespace(
            id="exec-team",
            node_states={},
        )

    async def get_execution(self, execution_id: str):
        assert execution_id == "exec-team"
        return self.record

    async def update_execution(self, execution_id: str, payload):
        assert execution_id == "exec-team"
        self.updated_payload = payload
        self.record.node_states = payload.node_states_json
        return self.record


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
