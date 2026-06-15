"""Deterministic route/UX checks for Chat Agent capability routing guidance."""

from src.agents.chat_agent.agent import _render_workspace_capability_route_cards


def _sci_literature_capability() -> dict:
    return {
        "id": "sci_literature_positioning",
        "display_name": "文献定位与创新点",
        "tier": "primary",
        "intent_description": "建立相关工作、gap 和 contribution positioning",
        "routing": {
            "when_to_use": [
                "用户需要围绕研究主题整理文献、gap、创新点或相关工作定位",
            ],
            "not_for": ["概念解释", "直接完整写 SCI 初稿"],
            "positive_examples": [
                "联邦学习结合大模型有什么创新点？",
                "帮我整理这个方向的研究空白和相关工作",
            ],
            "negative_examples": ["联邦学习是什么？", "帮我写 SCI"],
            "minimum_context": {"goal_or_topic": "required"},
            "ambiguity": {"overlaps_with": ["research_question_to_paper"]},
            "user_guidance": {
                "launch_intro": "我会让文献专家先整理相关工作、gap 和可用论断。",
                "lightweight_answer_hint": "这个问题我可以先直接解释，不需要启动团队任务。",
            },
        },
        "definition_json": {
            "display": {"entry_tier": "primary"},
            "mission": {"primary_surface": "prism"},
        },
    }


def _sci_paper_capability() -> dict:
    return {
        "id": "research_question_to_paper",
        "display_name": "问题到 SCI 初稿",
        "tier": "primary",
        "intent_description": "根据 research question、材料和目标期刊生成或更新 SCI manuscript",
        "routing": {
            "when_to_use": ["用户需要从研究问题进入 SCI 初稿写作"],
            "not_for": ["只做文献 gap 定位", "只解释概念"],
            "positive_examples": ["帮我写一篇 agent memory 的 SCI"],
            "negative_examples": ["agent memory 是什么意思？"],
            "minimum_context": {"goal_or_topic": "required"},
            "ambiguity": {"overlaps_with": ["sci_literature_positioning"]},
            "user_guidance": {
                "launch_intro": "我会让论文团队先搭结构和证据链。",
            },
        },
        "definition_json": {
            "display": {"entry_tier": "primary"},
            "mission": {"primary_surface": "prism"},
        },
    }


def _routing_prompt() -> str:
    return _render_workspace_capability_route_cards(
        [_sci_literature_capability(), _sci_paper_capability()],
    )


def test_routing_prompt_declares_four_user_experience_modes() -> None:
    prompt = _routing_prompt()

    assert "answer_in_chat" in prompt
    assert "ask_clarification" in prompt
    assert "offer_choices" in prompt
    assert "launch_feature" in prompt


def test_routing_prompt_guides_clear_launch_without_keyword_dependency() -> None:
    prompt = _routing_prompt()

    assert "联邦学习结合大模型有什么创新点？" in prompt
    assert "研究空白和相关工作" in prompt
    assert "我会让文献专家先整理相关工作、gap 和可用论断。" in prompt
    assert "trigger_phrases" not in prompt
    assert "triggers=" not in prompt


def test_routing_prompt_guides_lightweight_chat_and_one_question() -> None:
    prompt = _routing_prompt()

    assert "联邦学习是什么？" in prompt
    assert "这个问题我可以先直接解释，不需要启动团队任务。" in prompt
    assert "one useful question" in prompt
    assert "不要列清单" in prompt


def test_routing_prompt_guides_ambiguity_as_two_natural_choices() -> None:
    prompt = _routing_prompt()

    assert "two natural choices" in prompt
    assert "先找研究空白" in prompt
    assert "直接进入初稿" in prompt
    assert "route confidence" not in prompt
