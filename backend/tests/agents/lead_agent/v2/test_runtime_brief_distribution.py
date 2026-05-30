from src.agents.contracts.task_brief import TaskBrief
from src.agents.lead_agent.v2.runtime import LeadAgentRuntime


def test_distribute_brief_flattens_nested_brief_payload():
    cap = type(
        "Cap",
        (),
        {
            "graph_template": {
                "phases": [
                    {
                        "name": "mission_execution",
                        "tasks": [{"name": "research_scout"}],
                    }
                ]
            }
        },
    )()
    brief = TaskBrief(
        capability_id="sci_literature_positioning",
        workspace_id="workspace-1",
        user_id="user-1",
        raw_message="find papers",
        brief={
            "brief": {"topic": "federated LoRA"},
            "raw_message": "find papers about federated LoRA",
        },
    )

    distributed = LeadAgentRuntime(resolver=None)._distribute_brief(brief, cap)

    assert distributed["research_scout"]["topic"] == "federated LoRA"
    assert distributed["research_scout"]["raw_message"] == "find papers about federated LoRA"
    assert distributed["research_scout"]["workspace_id"] == "workspace-1"
    assert distributed["research_scout"]["user_id"] == "user-1"
