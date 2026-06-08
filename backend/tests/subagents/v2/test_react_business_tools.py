from src.subagents.v2.base import SubagentContext
from src.subagents.v2.types.react import _resolve_tools


def test_react_resolves_business_tools_from_workspace_context() -> None:
    ctx = SubagentContext(
        workspace_id="ws-1",
        execution_id="exec-1",
        prompt="",
        inputs={"raw_message": "test"},
        tools=[
            "library_read",
            "document_read",
            "memory_read",
            "prism_read",
            "citation_parser",
            "artifact_create",
        ],
        workspace_data={
            "library": {"items": [{"title": "Paper A", "citation_key": "paper_a_2026"}]},
            "documents": [{"name": "notes.md", "excerpt": "method notes"}],
            "memory": [{"text": "prefer conservative claims"}],
            "prism": {"outline": ["Introduction"]},
        },
        capability_policy={},
        skill=None,
    )

    resolved = _resolve_tools(ctx.tools, ctx)

    assert {tool.name for tool in resolved} == {
        "library_read",
        "document_read",
        "memory_read",
        "prism_read",
        "citation_parser",
        "artifact_create",
    }
