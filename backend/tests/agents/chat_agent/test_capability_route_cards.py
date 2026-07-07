"""Chat Agent capability route-card rendering tests."""

from src.agents.chat_agent.agent import (
    _build_capability_routing_prompt,
    _render_workspace_capability_route_cards,
)


def _capability(
    *,
    capability_id: str = "sci_literature_positioning",
    tier: str = "primary",
) -> dict:
    return {
        "id": capability_id,
        "display_name": "文献定位与创新点",
        "tier": tier,
        "description": "建立相关工作、gap 和 contribution positioning",
        "intent_description": "建立相关工作、gap 和 contribution positioning",
        "trigger_phrases": ["文献定位与创新点"],
        "routing": {
            "when_to_use": ["用户需要整理文献、gap 和创新点"],
            "not_for": ["概念解释", "短句润色"],
            "user_intents": ["找研究空白"],
            "positive_examples": ["联邦学习结合大模型有什么创新点？"],
            "negative_examples": ["联邦学习是什么？"],
            "minimum_context": {"goal_or_topic": "required"},
            "ambiguity": {"overlaps_with": ["research_question_to_paper"]},
            "user_guidance": {
                "launch_intro": "我会让文献专家先整理相关工作、gap 和可用论断。",
            },
        },
        "definition_json": {
            "display": {"entry_tier": tier},
            "mission": {
                "primary_surface": "prism",
                "user_promise": "建立相关工作、gap 和 contribution positioning",
            },
            "graph_template": {
                "phases": [
                    {
                        "name": "internal_phase",
                        "tasks": [{"name": "raw_task"}],
                    }
                ]
            },
        },
    }


def test_renders_compact_route_cards_without_graph_template() -> None:
    rendered = _render_workspace_capability_route_cards([_capability()])

    assert "<capability_route_card" in rendered
    assert 'id="sci_literature_positioning"' in rendered
    assert 'when="用户需要整理文献、gap 和创新点"' in rendered
    assert 'not_for="概念解释；短句润色"' in rendered
    assert 'minimum_context="goal_or_topic"' in rendered
    assert "我会让文献专家先整理相关工作、gap 和可用论断。" in rendered
    assert "graph_template" not in rendered
    assert "internal_phase" not in rendered
    assert "<capability " not in rendered
    assert "triggers=" not in rendered


def test_skips_hidden_capability_route_cards() -> None:
    rendered = _render_workspace_capability_route_cards(
        [
            _capability(capability_id="visible", tier="primary"),
            _capability(capability_id="internal_sandbox_smoke", tier="hidden"),
        ],
    )

    assert 'id="visible"' in rendered
    assert "internal_sandbox_smoke" not in rendered


def test_empty_visible_capabilities_render_no_feature_prompt() -> None:
    rendered = _render_workspace_capability_route_cards(
        [_capability(capability_id="internal_sandbox_smoke", tier="hidden")],
    )

    assert rendered == ""


def test_visible_capability_without_routing_is_not_keyword_fallback() -> None:
    capability = _capability(capability_id="admin_capability_without_routing")
    capability["routing"] = {}

    rendered = _render_workspace_capability_route_cards([capability])

    assert rendered == ""
    assert "trigger_phrases" not in rendered
    assert "文献定位与创新点" not in rendered


def test_capability_routing_prompt_tells_model_to_reuse_recent_context() -> None:
    prompt = _build_capability_routing_prompt("<available_capabilities />")

    assert "recent user turns" in prompt
    assert "workspace context" in prompt
    assert "uploaded material summaries" in prompt
    assert "active mission summaries" in prompt


def test_capability_routing_prompt_allows_short_plan_before_launch() -> None:
    prompt = _build_capability_routing_prompt("<available_capabilities />")

    assert "你打算怎么做" in prompt
    assert "short editable plan" in prompt
    assert "when the user confirms" in prompt


def test_capability_routing_prompt_forbids_exposing_route_card_internals() -> None:
    prompt = _build_capability_routing_prompt("<available_capabilities />")

    assert "DO NOT expose capability id" in prompt
    assert "route-card internals" in prompt
    assert "internal workflow labels" in prompt


def test_capability_routing_prompt_says_right_panel_cards_are_not_the_ui_model() -> None:
    prompt = _build_capability_routing_prompt("<available_capabilities />")

    assert "right-panel capability cards are internal" in prompt
    assert "Do not ask the user to click a capability card" in prompt
