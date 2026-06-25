from src.agents.harness.research_brief import (
    ResearchBriefV1,
    build_research_brief,
    summarize_research_brief,
)


def test_research_brief_preserves_objective_perspectives_and_stop_rules() -> None:
    brief = ResearchBriefV1(
        brief_id="brief-1",
        workspace_id="ws-1",
        execution_id="exec-1",
        workspace_type="sci",
        capability_id="sci_literature_positioning",
        user_objective="围绕联邦大模型微调寻找 AAAI 级创新点",
        research_topic="Federated fine-tuning of large language models",
        target_output="文献图谱、gap 分析、创新点候选",
        target_venue={"name": "AAAI", "quality_bar": "top-tier conference"},
        known_inputs=[{"kind": "user_message", "summary": "用户关注 FedLLM + LoRA。"}],
        missing_inputs=[{"key": "dataset", "reason": "实验可行性还未知。"}],
        perspectives=[
            {
                "perspective_id": "p-communication",
                "label": "通信效率",
                "questions": ["现有 FedLoRA 如何降低通信？"],
            }
        ],
        search_plan={
            "seed_queries": ["federated learning LLM fine-tuning LoRA"],
            "stop_rules": ["连续两轮只产生重复来源时停止"],
        },
    )

    payload = brief.model_dump()

    assert payload["schema_version"] == "wenjin.research_brief.v1"
    assert brief.perspectives[0].label == "通信效率"
    assert brief.search_plan.stop_rules == ["连续两轮只产生重复来源时停止"]


def test_build_research_brief_uses_workspace_map_hints_without_inventing_inputs() -> None:
    brief = build_research_brief(
        execution_id="exec-1",
        workspace_id="ws-1",
        workspace_type="sci",
        capability_id="research_question_to_paper",
        user_objective="写一篇联邦学习结合大模型的 SCI 论文",
        workspace_map={
            "topic_hints": ["federated learning", "large language models"],
            "open_questions": ["是否已有目标数据集？"],
        },
        capability_metadata={"name": "问题到 SCI 初稿"},
    )

    assert brief.research_topic == "federated learning / large language models"
    assert brief.target_output == "问题到 SCI 初稿"
    assert brief.missing_inputs[0].key == "workspace_open_question"
    assert "目标数据集" in brief.missing_inputs[0].reason


def test_summarize_research_brief_is_bounded_and_user_readable() -> None:
    brief = build_research_brief(
        execution_id="exec-1",
        workspace_id="ws-1",
        workspace_type="sci",
        capability_id="sci_literature_positioning",
        user_objective="联邦大模型 " * 80,
        workspace_map={"topic_hints": ["FedLLM", "LoRA"]},
        capability_metadata={"name": "文献定位与创新点"},
    )

    summary = summarize_research_brief(brief)

    assert "研究目标：" in summary
    assert "FedLLM / LoRA" in summary
    assert len(summary) <= 900

