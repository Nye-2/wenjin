from src.subagents.v2.base import SubagentContext
from src.subagents.v2.types.react import _react_model_id, _resolve_tools


def test_react_resolves_business_tools_from_workspace_context() -> None:
    ctx = SubagentContext(
        workspace_id="ws-1",
        execution_id="exec-1",
        prompt="",
        inputs={"raw_message": "test"},
        tools=[
            "library_read",
            "prism_file_read",
            "workspace_memory_read",
            "prism_read",
            "citation_parser",
            "artifact_create",
        ],
        workspace_data={
            "library": {"items": [{"title": "Paper A", "citation_key": "paper_a_2026"}]},
            "prism_files": [{"name": "notes.md", "excerpt": "method notes"}],
            "workspace_memory": {"content_markdown": "prefer conservative claims"},
            "prism": {"outline": ["Introduction"]},
        },
        capability_policy={},
        skill=None,
    )

    resolved = _resolve_tools(ctx.tools, ctx)

    assert {tool.name for tool in resolved} == {
        "library_read",
        "prism_file_read",
        "workspace_memory_read",
        "prism_read",
        "citation_parser",
        "artifact_create",
    }


def test_react_model_id_uses_context_input_model(monkeypatch) -> None:
    selected: list[str | None] = []

    def _fake_route_writing_model(*, requested_model: str | None = None) -> str:
        selected.append(requested_model)
        return requested_model or "default-model"

    monkeypatch.setattr(
        "src.subagents.v2.types.react.route_writing_model",
        _fake_route_writing_model,
    )
    ctx = SubagentContext(
        workspace_id="ws-1",
        execution_id="exec-1",
        prompt="",
        inputs={"model_id": "gpt-5.3-codex-spark"},
        tools=[],
    )

    assert _react_model_id(ctx) == "gpt-5.3-codex-spark"
    assert selected == ["gpt-5.3-codex-spark"]


def test_react_model_id_falls_back_through_router(monkeypatch) -> None:
    selected: list[str | None] = []

    def _fake_route_writing_model(*, requested_model: str | None = None) -> str:
        selected.append(requested_model)
        return requested_model or "default-model"

    monkeypatch.setattr(
        "src.subagents.v2.types.react.route_writing_model",
        _fake_route_writing_model,
    )
    ctx = SubagentContext(
        workspace_id="ws-1",
        execution_id="exec-1",
        prompt="",
        inputs={},
        tools=[],
    )

    assert _react_model_id(ctx) == "default-model"
    assert selected == [None]
