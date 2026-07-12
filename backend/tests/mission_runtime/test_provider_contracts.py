from __future__ import annotations

from langchain_core.messages import AIMessage

from src.mission_runtime.adapters import _parse_subagent_action, _subagent_action_tool


def test_subagent_provider_action_decodes_open_objects() -> None:
    action = _parse_subagent_action(
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "subagent_step",
                    "args": {
                        "kind": "tool",
                        "summary": "Search the pinned source",
                        "tool_name": "research.search",
                        "arguments_json": '{"query":"federated LoRA"}',
                        "result_json": "{}",
                        "partial_result_json": "{}",
                        "stop_reason": None,
                    },
                    "id": "worker-frame-1",
                }
            ],
        )
    )

    assert action.arguments == {"query": "federated LoRA"}
    assert action.result_json == {}


def test_subagent_provider_schema_has_no_open_objects_or_defaults() -> None:
    schema = _subagent_action_tool()["function"]["parameters"]

    def assert_strict(node: object) -> None:
        if isinstance(node, dict):
            if isinstance(node.get("properties"), dict):
                assert node.get("additionalProperties") is False
                assert set(node["required"]) == set(node["properties"])
            assert "default" not in node
            for value in node.values():
                assert_strict(value)
        elif isinstance(node, list):
            for value in node:
                assert_strict(value)

    assert_strict(schema)
