from src.agents.contracts.task_brief import TaskBrief
from src.agents.lead_agent.v2.team.contracts import TeamBlackboard
from src.agents.lead_agent.v2.team.member_context import build_team_member_context


def test_research_scout_context_derives_query_from_raw_message() -> None:
    payload = build_team_member_context(
        brief=TaskBrief(
            capability_id="sci_literature_positioning",
            workspace_id="ws-1",
            raw_message="联邦学习结合大模型 (Federated Learning combined with Large Language Models)",
            brief={},
        ),
        capability_name="文献定位与创新点",
        template_id="research_scout.v1",
        display_role="文献检索员",
        blackboard=TeamBlackboard(mission_summary="文献定位与创新点"),
    )

    assert payload["query"] == "Federated Learning combined with Large Language Models"
    assert payload["raw_message"].startswith("联邦学习")
    assert payload["task_focus"]
    assert payload["workspace_id"] == "ws-1"
    assert payload["capability_id"] == "sci_literature_positioning"
    assert payload["team_role"] == "文献检索员"


def test_member_context_preserves_explicit_query_and_filters_internal_refs() -> None:
    payload = build_team_member_context(
        brief=TaskBrief(
            capability_id="sci_literature_positioning",
            workspace_id="ws-1",
            raw_message="use my query",
            brief={
                "query": "privacy preserving LLM fine tuning",
                "topic": "federated LLM",
                "source_refs": [
                    "/workspace/reports/visible.md",
                    "/workspace/outputs/harness/exec/node/raw.log",
                    "/workspace/.wenjin/manifest.json",
                ],
            },
        ),
        capability_name="文献定位与创新点",
        template_id="literature_synthesizer.v1",
        display_role="文献综合专家",
        blackboard=TeamBlackboard(
            mission_summary="文献定位与创新点",
            latest_leader_summary="检索到 federated LLM 来源。",
        ),
    )

    assert payload["query"] == "privacy preserving LLM fine tuning"
    assert payload["topic"] == "federated LLM"
    assert payload["upstream_context"]["latest_leader_summary"] == "检索到 federated LLM 来源。"
    assert "/workspace/reports/visible.md" in payload["source_refs"]
    assert all("/workspace/outputs/harness" not in ref for ref in payload["source_refs"])
    assert all("/workspace/.wenjin" not in ref for ref in payload["source_refs"])
