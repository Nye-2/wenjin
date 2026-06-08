from __future__ import annotations

import json

import pytest

from src.agents.harness.business_tools import build_business_langchain_tools
from src.subagents.v2.base import SubagentContext


def _ctx() -> SubagentContext:
    return SubagentContext(
        workspace_id="ws-1",
        execution_id="exec-1",
        prompt="",
        inputs={"raw_message": "federated LLM"},
        tools=[
            "library_read",
            "document_read",
            "memory_read",
            "prism_read",
            "citation_parser",
            "artifact_create",
        ],
        workspace_data={
            "library": {
                "items": [
                    {
                        "title": "Federated Large Language Models",
                        "citation_key": "smith2026federated",
                        "year": 2026,
                        "venue": "Journal A",
                        "path": "/workspace/reports/source.md",
                    },
                    {
                        "title": "Internal Trace",
                        "citation_key": "internal_trace",
                        "path": "/workspace/outputs/harness/exec/node/stdout.txt",
                    },
                ]
            },
            "documents": [
                {
                    "name": "notes.md",
                    "excerpt": "Federated learning notes",
                    "path": "/workspace/main/notes.md",
                },
                {
                    "name": "secret.md",
                    "excerpt": "hidden",
                    "path": "/workspace/.wenjin/cache/secret.md",
                },
            ],
            "memory": [
                {"text": "Prefer conservative claims.", "path": "/workspace/reports/memory.md"},
            ],
            "prism": {
                "outline": ["Introduction", "Related Work"],
                "protected_sections": [{"label": "Methods", "path": "/workspace/main/main.tex"}],
                "full_text": "this should not be returned by prism_read",
            },
        },
        capability_policy={},
        skill=None,
    )


def _ctx_with_records(records: list[dict]) -> SubagentContext:
    ctx = _ctx()
    ctx.workspace_data["_harness_tool_records"] = records
    return ctx


@pytest.mark.asyncio
async def test_library_read_returns_bounded_public_sources() -> None:
    [tool] = build_business_langchain_tools(_ctx(), ["library_read"])

    raw = await tool.ainvoke({"query": "federated", "limit": 5})
    payload = json.loads(raw)

    assert payload["payload"]["returned"] == 1
    assert payload["payload"]["items"][0]["citation_key"] == "smith2026federated"
    assert "/workspace/outputs/harness" not in raw
    assert payload["truncated"] is False


@pytest.mark.asyncio
async def test_library_read_drops_records_that_point_to_internal_paths() -> None:
    [tool] = build_business_langchain_tools(_ctx(), ["library_read"])

    raw = await tool.ainvoke({"limit": 5})

    assert "smith2026federated" in raw
    assert "internal_trace" not in raw


@pytest.mark.asyncio
async def test_business_tool_call_is_recorded_for_node_evidence() -> None:
    records: list[dict] = []
    [tool] = build_business_langchain_tools(_ctx_with_records(records), ["library_read"])

    raw = await tool.ainvoke({"query": "federated", "limit": 5})

    assert records
    assert records[-1]["name"] == "library_read"
    assert records[-1]["status"] == "completed"
    assert records[-1]["args"] == {"query": "federated", "limit": 5}
    assert records[-1]["result_preview"] == raw[:500]


@pytest.mark.asyncio
async def test_artifact_create_returns_staged_payload_without_committing_rooms() -> None:
    [tool] = build_business_langchain_tools(_ctx(), ["artifact_create"])

    raw = await tool.ainvoke(
        {
            "title": "Literature positioning report",
            "markdown": "# Report\n\nClaim-evidence plan.",
            "kind": "review_report",
        }
    )
    payload = json.loads(raw)

    staged = payload["payload"]["staged_artifact"]
    assert staged["title"] == "Literature positioning report"
    assert staged["kind"] == "review_report"
    assert staged["status"] == "staged_for_review"
    assert staged["materialized"] is False
