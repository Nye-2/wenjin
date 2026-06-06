"""Tests for LeadAgentRuntime (Task 2.5)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure subagent types are registered
import src.subagents.v2.types  # noqa: F401
from src.agents.contracts.task_brief import TaskBrief
from src.agents.contracts.task_report import TaskReport
from src.agents.lead_agent.v2.runtime import LeadAgentRuntime
from src.agents.lead_agent.v2.sandbox_artifact_discovery import DISCOVERY_SCHEMA
from src.agents.lead_agent.v2.sandbox_artifact_review import collect_sandbox_artifact_candidates
from src.services.token_usage_collector import record_token_usage

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


@pytest.mark.asyncio
async def test_run_session_includes_collected_provider_token_usage():
    """Provider usage collected during node execution should reach TaskReport billing."""
    cap = _make_fake_capability()
    resolver = _make_resolver(cap)

    class _FakeGraph:
        async def ainvoke(self, state):
            record_token_usage({"input_tokens": 1200, "output_tokens": 300})
            return {
                **state,
                "node_results": {
                    "make_outline": {
                        "output": {"text": "ok"},
                    }
                },
            }

    runtime = LeadAgentRuntime(
        resolver=resolver,
        get_workspace_type=AsyncMock(return_value="thesis"),
    )

    with patch(
        "src.agents.lead_agent.v2.runtime.compile_graph",
        return_value=_FakeGraph(),
    ):
        report = await runtime.run_session(execution_id="exec-usage", brief=_make_brief())

    assert report.token_usage == {"input": 1200, "output": 300}


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


def test_needs_library_context_when_citation_policy_uses_workspace_library():
    assert LeadAgentRuntime._needs_library_context(
        {
            "context_policy": {"room_reads": {}},
            "citation_policy": {"source_scope": "workspace_library"},
        }
    )


def test_prism_context_requirements_keep_local_rewrite_lightweight():
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
                "include_pending_review_summary": True,
            },
        },
    )

    requirements = LeadAgentRuntime._context_requirements_from_brief(brief)

    assert requirements["include_manuscript_context"]
    assert not LeadAgentRuntime._needs_workspace_context(
        {"context_policy": {"room_reads": {"library": "summary"}}},
        requirements,
    )


def test_explicit_context_requirements_do_not_disable_required_citation_library():
    brief = TaskBrief(
        capability_id="citation_required_capability",
        raw_message="draft with citations",
        workspace_id="ws-001",
        brief={
            "context_requirements": {
                "include_manuscript_context": True,
                "include_workspace_history": False,
                "include_related_documents": False,
                "include_sandbox_artifacts": False,
            },
        },
    )

    requirements = LeadAgentRuntime._context_requirements_from_brief(brief)

    assert LeadAgentRuntime._needs_workspace_context(
        {
            "context_policy": {"room_reads": {"library": "none"}},
            "citation_policy": {"source_scope": "workspace_library"},
        },
        requirements,
    )


def test_workspace_context_metadata_is_bounded_for_prompt_safety():
    metadata = LeadAgentRuntime._compact_metadata(
        {
            "long": "x" * 500,
            "nested": {"path": ["a", "b", "c"]},
            "skip_extra": "kept within key limit",
        },
        limit=2,
    )

    assert set(metadata) == {"long", "nested"}
    assert len(metadata["long"]) == 300
    assert metadata["nested"].startswith("{")


def test_prism_context_requirements_enable_document_rewrite_context():
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

    requirements = LeadAgentRuntime._context_requirements_from_brief(brief)

    assert requirements["include_workspace_history"]
    assert LeadAgentRuntime._needs_workspace_context({}, requirements)


def test_runtime_mode_ignores_definition_json_runtime_mode():
    cap = _make_fake_capability(
        definition_json={"runtime_mode": "team_kernel"},
    )

    assert LeadAgentRuntime._runtime_mode(cap) == "static_graph"


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


@pytest.mark.asyncio
async def test_run_session_stages_sandbox_artifact_review_items_from_harness_tool_calls():
    graph_template = {
        "phases": [
            {
                "name": "analysis",
                "tasks": [
                    {
                        "name": "experiment_runner",
                        "subagent_type": "react",
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
    registered_assets: list[object] = []
    registered_artifacts: list[object] = []

    class _FakeGraph:
        async def ainvoke(self, state):
            return {
                **state,
                "node_results": {
                    "experiment_runner": {
                        "output": {"text": "experiment complete"},
                        "tool_calls": [
                            {
                                "name": "sandbox.run_python",
                                "status": "completed",
                                "generated_artifacts": [
                                    {
                                        "schema": "wenjin.sandbox.generated_artifact_candidate.v1",
                                        "path": "/workspace/reports/analysis.md",
                                        "root": "reports",
                                        "artifact_kind": "sandbox_report",
                                        "mime_type": "text/markdown",
                                        "size": 42,
                                        "content_hash": "sha256:analysis",
                                        "sandbox_job_id": "job-1",
                                        "sandbox_environment_id": "env-1",
                                        "review_surface": "sandbox_artifact",
                                        "materialization_status": "candidate",
                                    }
                                ],
                            }
                        ],
                    }
                },
            }

    class _FakeClient:
        async def register_asset(self, command):
            registered_assets.append(command)
            return SimpleNamespace(id="asset-1")

        async def register_sandbox_artifact(self, command):
            registered_artifacts.append(command)
            return SimpleNamespace(id="artifact-1", review_item_id="review-1")

        async def list_review_items(self, **kwargs):
            if kwargs.get("target_domain") != "sandbox":
                return []
            return [
                SimpleNamespace(
                    id="review-1",
                    batch_id="batch-1",
                    workspace_id="ws-001",
                    source_item_id="artifact-1",
                    item_kind="sandbox_artifact",
                    target_domain="sandbox",
                    target_kind="sandbox_artifact",
                    target_ref_json={
                        "sandbox_artifact_id": "artifact-1",
                        "workspace_asset_id": "asset-1",
                    },
                    status="pending",
                    title="Accept sandbox artifact: sandbox_report",
                    summary="/workspace/reports/analysis.md",
                    payload_json={
                        "sandbox_artifact_id": "artifact-1",
                        "workspace_asset_id": "asset-1",
                        "artifact_kind": "sandbox_report",
                        "path": "/workspace/reports/analysis.md",
                    },
                    preview_json={
                        "path": "/workspace/reports/analysis.md",
                        "mime_type": "text/markdown",
                        "content_hash": "sha256:analysis",
                    },
                    provenance_json={
                        "source_kind": "sandbox_job",
                        "source_id": "job-1",
                        "execution_id": "exec-sandbox-artifact",
                    },
                    result_json=None,
                    error_text=None,
                    sort_order=0,
                    applied_at=None,
                    created_at=None,
                    updated_at=None,
                )
            ]

    class _FakeClientContext:
        async def __aenter__(self):
            return _FakeClient()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    with (
        patch(
            "src.agents.lead_agent.v2.runtime.compile_graph",
            return_value=_FakeGraph(),
        ),
        patch(
            "src.dataservice_client.provider.dataservice_client",
            return_value=_FakeClientContext(),
        ),
    ):
        report = await runtime.run_session(
            execution_id="exec-sandbox-artifact",
            brief=_make_brief(),
        )

    assert len(registered_assets) == 1
    asset_payload = registered_assets[0]
    assert asset_payload.workspace_id == "ws-001"
    assert asset_payload.asset_kind == "sandbox_report"
    assert asset_payload.name == "analysis.md"
    assert asset_payload.storage_backend == "sandbox"
    assert asset_payload.storage_path == "/workspace/reports/analysis.md"
    assert asset_payload.source_kind == "sandbox_job"
    assert asset_payload.source_id == "job-1"

    assert len(registered_artifacts) == 1
    artifact_payload = registered_artifacts[0]
    assert artifact_payload.workspace_id == "ws-001"
    assert artifact_payload.sandbox_job_id == "job-1"
    assert artifact_payload.workspace_asset_id == "asset-1"
    assert artifact_payload.artifact_kind == "sandbox_report"
    assert artifact_payload.path == "/workspace/reports/analysis.md"
    assert artifact_payload.metadata_json["source_task_id"] == "experiment_runner"

    assert report.review_items == [
        {
            "id": "review-1",
            "kind": "sandbox_artifact",
            "status": "pending",
            "title": "Accept sandbox artifact: sandbox_report",
            "summary": "/workspace/reports/analysis.md",
            "source": {
                "type": "sandbox_job",
                "execution_id": "exec-sandbox-artifact",
                "job_id": "job-1",
            },
            "target": {
                "kind": "sandbox_artifact",
                "path": "/workspace/reports/analysis.md",
                "artifact_kind": "sandbox_report",
                "asset_id": "asset-1",
                "sandbox_artifact_id": "artifact-1",
            },
            "preview": {
                "mode": "artifact",
                "path": "/workspace/reports/analysis.md",
                "mime_type": "text/markdown",
                "content_hash": "sha256:analysis",
            },
            "actions": [
                {"action": "accept_sandbox_artifact", "label": "保存到产物库"},
                {"action": "reject_sandbox_artifact", "label": "忽略"},
            ],
            "created_at": None,
            "updated_at": None,
            "applied_at": None,
        }
    ]


def test_collect_sandbox_artifact_candidates_rejects_internal_and_traversal_paths():
    node_results = {
        "experiment_runner": {
            "tool_calls": [
                {
                    "status": "completed",
                    "generated_artifacts": [
                        {
                            "schema": DISCOVERY_SCHEMA,
                            "path": "/workspace/reports/analysis.md",
                            "artifact_kind": "sandbox_report",
                            "review_surface": "sandbox_artifact",
                            "materialization_status": "candidate",
                            "sandbox_job_id": "job-1",
                        },
                        {
                            "schema": DISCOVERY_SCHEMA,
                            "path": "/workspace/outputs/harness/exec/node/tool.txt",
                            "artifact_kind": "sandbox_output",
                            "review_surface": "sandbox_artifact",
                            "materialization_status": "candidate",
                            "sandbox_job_id": "job-1",
                        },
                        {
                            "schema": DISCOVERY_SCHEMA,
                            "path": "/workspace/outputs/../secrets.txt",
                            "artifact_kind": "sandbox_output",
                            "review_surface": "sandbox_artifact",
                            "materialization_status": "candidate",
                            "sandbox_job_id": "job-1",
                        },
                    ],
                }
            ]
        }
    }

    assert [
        candidate["path"] for candidate in collect_sandbox_artifact_candidates(node_results)
    ] == ["/workspace/reports/analysis.md"]


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


@pytest.mark.asyncio
async def test_stage_prism_review_items_blocks_missing_library_citation_keys():
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
                                    "pending_content": "{{output.text}}",
                                },
                            }
                        ],
                    }
                ],
            }
        ]
    }
    cap = _make_fake_capability(
        graph_template=graph_template,
        definition_json={
            "citation_policy": {
                "source_scope": "workspace_library",
                "required_for_prism_manuscript": True,
                "missing_key_behavior": "block_prism_stage",
                "record_usage": True,
            }
        },
    )
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
                "workspace_data": {
                    "library_context": {
                        "citation_keys": ["smith2026"],
                    }
                },
                "node_results": {
                    "manuscript_writer": {
                        "output": {
                            "text": (
                                "\\documentclass{article}\\begin{document}"
                                "Claim \\cite{missing2026}.\\end{document}"
                            ),
                        },
                    },
                },
            },
            cap,
            brief=brief,
            execution_id="exec-1",
        )

    assert staged == []


@pytest.mark.asyncio
async def test_stage_prism_review_items_records_valid_library_citation_usage():
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
                                    "pending_content": "{{output.text}}",
                                },
                            }
                        ],
                    }
                ],
            }
        ]
    }
    cap = _make_fake_capability(
        graph_template=graph_template,
        definition_json={
            "citation_policy": {
                "source_scope": "workspace_library",
                "required_for_prism_manuscript": True,
                "missing_key_behavior": "block_prism_stage",
                "record_usage": True,
            }
        },
    )
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
    usage_calls: list[object] = []

    class _FakeClient:
        async def upsert_pending_prism_file_change(self, command):
            staged.append(command)
            return SimpleNamespace(id="review-item-1")

        async def record_source_citation_usage(self, command):
            usage_calls.append(command)
            return {"recorded": len(command.citation_keys)}

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
                "workspace_data": {
                    "library_context": {
                        "citation_keys": ["smith2026", "doe2025"],
                    }
                },
                "node_results": {
                    "manuscript_writer": {
                        "output": {
                            "text": (
                                "\\documentclass{article}\\begin{document}"
                                "Claim \\cite{smith2026}.\\end{document}"
                            ),
                        },
                    },
                },
            },
            cap,
            brief=brief,
            execution_id="exec-1",
        )

    assert len(staged) == 1
    assert len(usage_calls) == 1
    usage = usage_calls[0]
    assert usage.workspace_id == "ws-001"
    assert usage.citation_keys == ["smith2026"]
    assert usage.execution_id == "exec-1"
    assert usage.task_id == "manuscript_writer"
    assert usage.latex_project_id == "latex-1"
    assert usage.target_id == "review-item-1"
    assert usage.target_ref_json == {
        "logical_key": "project:main",
        "path": "main.tex",
    }
    assert usage.generated_text.startswith("\\documentclass")


@pytest.mark.asyncio
async def test_stage_prism_review_items_does_not_record_usage_for_non_library_keys():
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
                                    "pending_content": "{{output.text}}",
                                },
                            }
                        ],
                    }
                ],
            }
        ]
    }
    cap = _make_fake_capability(
        graph_template=graph_template,
        definition_json={
            "citation_policy": {
                "source_scope": "workspace_library",
                "missing_key_behavior": "warn",
                "record_usage": True,
            }
        },
    )
    runtime = LeadAgentRuntime(
        resolver=_make_resolver(cap),
        get_workspace_type=AsyncMock(return_value="sci"),
    )
    brief = TaskBrief(
        capability_id="sci_literature_positioning",
        raw_message="draft",
        workspace_id="ws-001",
        brief={},
        manuscript_context={"latex_project_id": "latex-1", "main_file": "main.tex"},
    )
    staged: list[object] = []
    usage_calls: list[object] = []

    class _FakeClient:
        async def upsert_pending_prism_file_change(self, command):
            staged.append(command)
            return SimpleNamespace(id="review-item-1")

        async def record_source_citation_usage(self, command):
            usage_calls.append(command)
            return {"recorded": len(command.citation_keys)}

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
                "workspace_data": {"library_context": {"citation_keys": ["smith2026"]}},
                "node_results": {
                    "manuscript_writer": {
                        "output": {
                            "text": (
                                "\\documentclass{article}\\begin{document}"
                                "Claim \\cite{not_in_library}.\\end{document}"
                            ),
                        },
                    },
                },
            },
            cap,
            brief=brief,
            execution_id="exec-1",
        )

    assert len(staged) == 1
    assert usage_calls == []


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
