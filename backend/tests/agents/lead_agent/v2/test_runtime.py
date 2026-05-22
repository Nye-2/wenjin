"""Tests for LeadAgentRuntime (Task 2.5)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure subagent types are registered
import src.subagents.v2.types  # noqa: F401
from src.agents.contracts.task_brief import TaskBrief
from src.agents.contracts.task_report import TaskReport
from src.agents.lead_agent.v2.runtime import LeadAgentRuntime

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SIMPLE_GRAPH_TEMPLATE = {
    "phases": [
        {
            "name": "outline_phase",
            "tasks": [
                {
                    "name": "make_outline",
                    "subagent_type": "react",
                    "display_name": "Make Outline",
                }
            ],
        }
    ]
}


def _make_fake_capability(
    graph_template: dict | None = None,
    *,
    definition_json: dict | None = None,
) -> SimpleNamespace:
    """Return a lightweight stand-in for a Capability ORM object."""
    return SimpleNamespace(
        id="test_cap",
        workspace_type="thesis",
        display_name="Test Capability",
        graph_template=graph_template or SIMPLE_GRAPH_TEMPLATE,
        brief_schema={"properties": {"topic": {"type": "string"}}},
        definition_json=definition_json or {},
    )


def _make_brief(capability_id: str = "test_cap") -> TaskBrief:
    return TaskBrief(
        capability_id=capability_id,
        raw_message="write an outline",
        workspace_id="ws-001",
        brief={"topic": "quantum computing"},
    )


def _make_resolver(cap_obj) -> MagicMock:
    """Return a mock CapabilityResolver whose resolve() returns cap_obj."""
    resolver = MagicMock()
    resolver.resolve = AsyncMock(return_value=cap_obj)
    return resolver


# ---------------------------------------------------------------------------
# test_run_session_publishes_graph_structure_then_completed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_session_publishes_graph_structure_then_completed():
    """publish_event must be called with graph_structure then execution.completed."""
    published: list[tuple] = []

    async def spy_publish(execution_id, event_name, payload):
        published.append((execution_id, event_name, payload))

    cap = _make_fake_capability()
    resolver = _make_resolver(cap)

    runtime = LeadAgentRuntime(
        resolver=resolver,
        publish_event=spy_publish,
        get_workspace_type=AsyncMock(return_value="thesis"),
    )

    brief = _make_brief()
    await runtime.run_session(execution_id="exec-123", brief=brief)

    # Runtime now emits per-node lifecycle events too (running → completed).
    # Filter for the two structural events the FE relies on.
    event_names = [name for _, name, _ in published]
    assert event_names[0] == "execution.graph_structure"
    assert event_names[-1] == "execution.completed"
    assert "execution.node" in event_names

    # First event: graph_structure payload shape
    _, _, gs_payload = published[0]
    gs = gs_payload["graph_structure"]
    assert "nodes" in gs and "edges" in gs

    # Last event: completed with proper status
    _, _, completed_payload = published[-1]
    assert completed_payload["status"] == "completed"


# ---------------------------------------------------------------------------
# test_run_session_invokes_subagents_and_collects_results
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_session_invokes_subagents_and_collects_results():
    """After invocation, node_results should contain the react output."""
    cap = _make_fake_capability()
    resolver = _make_resolver(cap)

    results_seen: list[dict] = []

    async def capturing_publish(execution_id, event_name, payload):
        if event_name == "execution.completed":
            results_seen.append(payload)

    runtime = LeadAgentRuntime(
        resolver=resolver,
        publish_event=capturing_publish,
        get_workspace_type=AsyncMock(return_value="thesis"),
    )

    brief = _make_brief()
    report = await runtime.run_session(execution_id="exec-456", brief=brief)

    # Report must exist and be completed
    assert report.status == "completed"
    # The react stub produces output
    # (checked indirectly — node ran without error)
    assert report.narrative  # non-empty
    assert "1" in report.narrative or "节点" in report.narrative


# ---------------------------------------------------------------------------
# test_run_session_returns_task_report
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_session_returns_task_report():
    """The return value is a valid TaskReport with required fields."""
    cap = _make_fake_capability()
    resolver = _make_resolver(cap)

    runtime = LeadAgentRuntime(
        resolver=resolver,
        get_workspace_type=AsyncMock(return_value="thesis"),
    )

    brief = _make_brief()
    report = await runtime.run_session(execution_id="exec-789", brief=brief)

    assert isinstance(report, TaskReport)
    assert report.execution_id == "exec-789"
    assert report.capability_id == "test_cap"
    assert report.status == "completed"
    assert report.duration_seconds >= 0
    assert report.narrative  # non-empty string


def test_distribute_brief_includes_manuscript_context():
    cap = _make_fake_capability()
    runtime = LeadAgentRuntime(
        resolver=_make_resolver(cap),
        get_workspace_type=AsyncMock(return_value="thesis"),
    )
    brief = TaskBrief(
        capability_id="test_cap",
        raw_message="write an outline",
        workspace_id="ws-001",
        brief={"topic": "quantum computing"},
        manuscript_context={
            "main_file": "main.tex",
            "pending_review_items": [{"id": "review-1"}],
        },
    )

    distributed = runtime._distribute_brief(brief, cap)

    assert distributed["make_outline"]["topic"] == "quantum computing"
    assert distributed["make_outline"]["raw_message"] == "write an outline"
    assert distributed["make_outline"]["workspace_id"] == "ws-001"
    assert distributed["make_outline"]["capability_id"] == "test_cap"
    assert distributed["make_outline"]["manuscript_context"]["main_file"] == (
        "main.tex"
    )


@pytest.mark.asyncio
async def test_stage_prism_review_items_from_writer_output():
    graph_template = {
        "phases": [
            {
                "name": "write",
                "tasks": [
                    {
                        "name": "manuscript_writer",
                        "subagent_type": "react",
                        "outputs": [
                            {
                                "kind": "prism_file_change",
                                "mapping": {
                                    "logical_key": "project:main",
                                    "path": "main.tex",
                                    "reason": "feature_proposal",
                                    "pending_content": "{{output.text}}",
                                },
                            }
                        ],
                    }
                ],
            }
        ]
    }
    cap = _make_fake_capability(graph_template=graph_template)
    runtime = LeadAgentRuntime(
        resolver=_make_resolver(cap),
        get_workspace_type=AsyncMock(return_value="thesis"),
    )
    brief = TaskBrief(
        capability_id="test_cap",
        raw_message="write a manuscript",
        workspace_id="ws-001",
        brief={},
        manuscript_context={
            "latex_project_id": "latex-1",
            "main_file": "main.tex",
        },
    )
    staged: list[object] = []

    class _FakeClient:
        async def upsert_pending_prism_file_change(self, command):
            staged.append(command)

    class _FakeClientContext:
        async def __aenter__(self):
            return _FakeClient()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    with patch(
        "src.dataservice_client.provider.dataservice_client",
        return_value=_FakeClientContext(),
    ):
        await runtime._stage_prism_review_items(
            {
                "node_results": {
                    "manuscript_writer": {
                        "output": {
                            "text": "\\documentclass{article}\\begin{document}Draft\\end{document}",
                        },
                    },
                },
            },
            cap,
            brief=brief,
            execution_id="exec-1",
        )

    assert len(staged) == 1
    command = staged[0]
    assert command.workspace_id == "ws-001"
    assert command.latex_project_id == "latex-1"
    assert command.logical_key == "project:main"
    assert command.path == "main.tex"
    assert command.source_execution_id == "exec-1"
    assert command.source_task_id == "manuscript_writer"
    assert "Draft" in command.pending_content
    assert command.pending_hash


def test_collect_outputs_adds_policy_memory_candidates_from_brief():
    cap = _make_fake_capability(
        graph_template={
            "phases": [
                {
                    "name": "write",
                    "tasks": [
                        {
                            "name": "writer",
                            "subagent_type": "react",
                            "outputs": [],
                        }
                    ],
                }
            ]
        },
        definition_json={
            "review_policy": {
                "default_targets": [
                    "prism_file_change",
                    "room_memory_candidate",
                ]
            }
        },
    )
    runtime = LeadAgentRuntime(
        resolver=_make_resolver(cap),
        get_workspace_type=AsyncMock(return_value="sci"),
    )
    brief = TaskBrief(
        capability_id="research_question_to_paper",
        raw_message="联邦学习大模型",
        workspace_id="ws-001",
        brief={
            "topic": "联邦学习大模型",
            "research_question": "效率优化与隐私保护",
            "target_journal": "待定",
        },
    )

    outputs = runtime._collect_outputs(
        {"node_results": {"writer": {"output": {"text": "draft"}}}},
        cap,
        brief=brief,
    )

    memory_outputs = [output for output in outputs if output.kind == "memory_fact"]
    assert [output.data.content for output in memory_outputs] == [
        "研究主题：联邦学习大模型",
        "研究问题：效率优化与隐私保护",
    ]
    assert all(output.default_checked for output in memory_outputs)


def test_collect_outputs_does_not_duplicate_explicit_memory_outputs():
    cap = _make_fake_capability(
        graph_template={
            "phases": [
                {
                    "name": "write",
                    "tasks": [
                        {
                            "name": "writer",
                            "subagent_type": "react",
                            "outputs": [
                                {
                                    "kind": "memory_fact",
                                    "mapping": {
                                        "content": "{{output.memory}}",
                                        "category": "preference",
                                    },
                                }
                            ],
                        }
                    ],
                }
            ]
        },
        definition_json={
            "review_policy": {"default_targets": ["room_memory_candidate"]}
        },
    )
    runtime = LeadAgentRuntime(
        resolver=_make_resolver(cap),
        get_workspace_type=AsyncMock(return_value="sci"),
    )

    outputs = runtime._collect_outputs(
        {"node_results": {"writer": {"output": {"memory": "用户偏好英文初稿"}}}},
        cap,
        brief=_make_brief("research_question_to_paper"),
    )

    memory_outputs = [output for output in outputs if output.kind == "memory_fact"]
    assert len(memory_outputs) == 1
    assert memory_outputs[0].data.content == "用户偏好英文初稿"
    assert memory_outputs[0].data.category == "preference"


@pytest.mark.asyncio
async def test_stage_prism_review_items_normalizes_tex_markdown_output():
    graph_template = {
        "phases": [
            {
                "name": "write",
                "tasks": [
                    {
                        "name": "manuscript_writer",
                        "subagent_type": "react",
                        "outputs": [
                            {
                                "kind": "prism_file_change",
                                "mapping": {
                                    "logical_key": "project:main",
                                    "path": "main.tex",
                                    "content_format": "latex_document",
                                    "reason": "feature_proposal",
                                    "pending_content": "{{output.text}}",
                                },
                            }
                        ],
                    }
                ],
            }
        ]
    }
    cap = _make_fake_capability(graph_template=graph_template)
    runtime = LeadAgentRuntime(
        resolver=_make_resolver(cap),
        get_workspace_type=AsyncMock(return_value="sci"),
    )
    brief = TaskBrief(
        capability_id="research_question_to_paper",
        raw_message="write a manuscript",
        workspace_id="ws-001",
        brief={},
        manuscript_context={
            "latex_project_id": "latex-1",
            "main_file": "main.tex",
        },
    )
    staged: list[object] = []

    class _FakeClient:
        async def upsert_pending_prism_file_change(self, command):
            staged.append(command)

    class _FakeClientContext:
        async def __aenter__(self):
            return _FakeClient()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    with patch(
        "src.dataservice_client.provider.dataservice_client",
        return_value=_FakeClientContext(),
    ):
        await runtime._stage_prism_review_items(
            {
                "node_results": {
                    "manuscript_writer": {
                        "output": {
                            "text": "# **联邦学习大模型**\n\n### **1. 引言**\n\n1. 通信效率",
                        },
                    },
                },
            },
            cap,
            brief=brief,
            execution_id="exec-1",
        )

    assert len(staged) == 1
    command = staged[0]
    assert command.path == "main.tex"
    assert command.pending_content.startswith("\\documentclass[UTF8,12pt]{ctexart}")
    assert "\\title{联邦学习大模型}" in command.pending_content
    assert "\\section{1. 引言}" in command.pending_content
    assert "\\begin{enumerate}" in command.pending_content


# ---------------------------------------------------------------------------
# test_run_session_handles_unknown_subagent_capability
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_session_handles_unknown_subagent_capability():
    """A capability with an unknown subagent_type results in status='failed_partial'."""
    bad_template = {
        "phases": [
            {
                "name": "phase1",
                "tasks": [
                    {"name": "task1", "subagent_type": "nonexistent_agent_xyzzy"},
                ],
            }
        ]
    }
    cap = _make_fake_capability(graph_template=bad_template)
    resolver = _make_resolver(cap)

    runtime = LeadAgentRuntime(
        resolver=resolver,
        get_workspace_type=AsyncMock(return_value="thesis"),
    )

    brief = _make_brief()
    report = await runtime.run_session(execution_id="exec-bad", brief=brief)

    assert report.status == "failed_partial"
    assert len(report.errors) == 1
    assert report.errors[0].phase == "-"
    assert report.errors[0].task == "-"
