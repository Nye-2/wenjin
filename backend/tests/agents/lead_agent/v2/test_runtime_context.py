"""Tests for Lead Agent runtime context assembly."""

from __future__ import annotations

from src.agents.contracts.task_brief import TaskBrief
from src.agents.lead_agent.v2.runtime_context import RuntimeContextAssembler


def test_context_assembler_keeps_local_prism_rewrite_lightweight() -> None:
    brief = TaskBrief(
        capability_id="prism_selection_optimize",
        raw_message="Prism 局部改稿",
        workspace_id="ws-001",
        brief={
            "context_requirements": {
                "include_manuscript_context": True,
                "include_workspace_history": False,
                "include_related_documents": False,
                "include_sandbox_artifacts": False,
                "include_pending_review_summary": False,
            },
        },
    )

    requirements = RuntimeContextAssembler.context_requirements_from_brief(brief)

    assert requirements["include_manuscript_context"]
    assert not RuntimeContextAssembler.needs_workspace_context(
        {"context_policy": {"room_reads": {"library": "summary"}}},
        requirements,
    )


def test_context_assembler_loads_document_prism_rewrite_context() -> None:
    brief = TaskBrief(
        capability_id="prism_selection_optimize",
        raw_message="Prism 全文改稿",
        workspace_id="ws-001",
        brief={
            "context_requirements": {
                "include_manuscript_context": True,
                "include_workspace_history": True,
                "include_related_documents": True,
                "include_sandbox_artifacts": True,
                "include_pending_review_summary": True,
            },
        },
    )

    requirements = RuntimeContextAssembler.context_requirements_from_brief(brief)

    assert requirements["include_workspace_history"]
    assert RuntimeContextAssembler.needs_workspace_context({}, requirements)
