"""Tests for compute projection assembly."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from src.compute.projection_service import ComputeProjectionService


class _ScalarResult:
    def __init__(self, values):
        self._values = list(values)

    def all(self):
        return list(self._values)


class _Result:
    def __init__(self, *, scalar=None, scalars=None):
        self._scalar = scalar
        self._scalars = scalars or []

    def scalar_one_or_none(self):
        return self._scalar

    def scalar(self):
        return self._scalar

    def scalars(self):
        return _ScalarResult(self._scalars)


class _FakeDb:
    def __init__(self, results):
        self._results = list(results)

    async def execute(self, _query):
        return self._results.pop(0)


def _execution_namespace(**overrides):
    now = overrides.get("created_at") or datetime.now(UTC)
    return SimpleNamespace(
        id=overrides.get("id", "exec-1"),
        user_id=overrides.get("user_id", "user-1"),
        workspace_id=overrides.get("workspace_id", "ws-1"),
        thread_id=overrides.get("thread_id", "thread-1"),
        execution_type=overrides.get("execution_type", "feature"),
        feature_id=overrides.get("feature_id", "framework_outline"),
        entry_skill_id=overrides.get("entry_skill_id"),
        workspace_type=overrides.get("workspace_type", "sci"),
        display_name=overrides.get("display_name"),
        status=overrides.get("status", "pending"),
        params=overrides.get("params", {}),
        result=overrides.get("result"),
        error=overrides.get("error"),
        result_summary=overrides.get("result_summary"),
        graph_structure=overrides.get("graph_structure"),
        node_states=overrides.get("node_states", {}),
        runtime_state=overrides.get("runtime_state"),
        progress=overrides.get("progress", 0),
        message=overrides.get("message"),
        artifact_ids=overrides.get("artifact_ids", []),
        next_actions=overrides.get("next_actions", []),
        advisory_code=overrides.get("advisory_code"),
        last_error=overrides.get("last_error"),
        parent_execution_id=overrides.get("parent_execution_id"),
        child_execution_ids=overrides.get("child_execution_ids", []),
        dispatch_mode=overrides.get("dispatch_mode"),
        worker_task_id=overrides.get("worker_task_id"),
        created_at=overrides.get("created_at", now),
        updated_at=overrides.get("updated_at", now),
        started_at=overrides.get("started_at"),
        completed_at=overrides.get("completed_at"),
    )


@pytest.mark.asyncio
async def test_compute_projection_aggregates_execution_task_and_subagents() -> None:
    now = datetime.now(UTC)
    compute_session = SimpleNamespace(
        id="compute-1",
        execution_id="exec-1",
        workspace_id="ws-1",
        user_id="user-1",
        sandbox_session_id="sandbox-1",
        active_view="overview",
        ui_state={},
        created_at=now,
        updated_at=now,
    )
    execution = _execution_namespace(
        id="exec-1",
        user_id="user-1",
        workspace_id="ws-1",
        thread_id="thread-1",
        workspace_type="sci",
        feature_id="framework_outline",
        entry_skill_id="framework-designer",
        status="pending",
        params={"topic": "agents"},
        message=None,
        runtime_state={
            "blocks": [
                {"id": "phase-1", "type": "phase"},
                {
                    "id": "activity",
                    "kind": "activity",
                    "items": [
                        {
                            "title": "渲染图表",
                            "description": "图表执行完成",
                            "tone": "success",
                            "timestamp": now.isoformat(),
                        }
                    ],
                },
            ]
        },
        result_summary=None,
        artifact_ids=["artifact-1"],
        next_actions=[{"kind": "review", "title": "检查输出"}],
        advisory_code="needs_review",
        last_error=None,
        created_at=now,
        updated_at=now,
        started_at=None,
        completed_at=None,
    )
    task = SimpleNamespace(
        id="task-1",
        execution_id="exec-1",
        task_type="workspace_feature",
        workspace_id="ws-1",
        feature_id="framework_outline",
        thread_id="thread-1",
        action=None,
        status="running",
        progress=40,
        message="生成中",
        result={
            "sandbox_path": "/mnt/user-data/execution/python_plot/run-1/output/plot.png",
            "render_data": {
                "file_url": "/api/threads/thread-1/artifacts/mnt/user-data/execution/python_plot/run-1/output/plot.png",
            },
            "data": {
                "latex_project_id": "latex-project-1",
                "prism_url": "/latex/latex-project-1",
                "main_file": "main.tex",
                "section_file": "sections/introduction.tex",
                "section_map": {"introduction": "sections/introduction.tex"},
                "compile_status": "success",
                "pdf_endpoint": "/api/latex/projects/latex-project-1/compile/history-1/pdf",
                "page_count": 8,
                "file_changes": [
                    {
                        "logical_key": "project:main",
                        "path": "main.tex",
                        "reason": "user_modified",
                    }
                ],
                "next_actions": [
                    {
                        "action": "open_prism",
                        "label": "在 WenjinPrism 中继续编辑",
                        "url": "/latex/latex-project-1",
                    }
                ],
            },
            "logs": "rendered plot",
            "compile_logs": "warning only",
        },
        error=None,
        runtime_state={"current_phase": "drafting"},
        created_at=now,
        started_at=now,
        completed_at=None,
    )
    subagent = SimpleNamespace(
        id="subagent-1",
        workspace_id="ws-1",
        thread_id="thread-1",
        execution_id="exec-1",
        user_id="user-1",
        subagent_type="scout",
        status="completed",
        prompt="search",
        output_preview="done",
        error=None,
        task_metadata={"workflow_phase": "discovery"},
        created_at=now,
        updated_at=now,
        completed_at=now,
    )
    latex_project = SimpleNamespace(
        id="latex-project-1",
        user_id="user-1",
        main_file="main.tex",
        llm_config={
            "metadata": {
                "file_changes": [
                    {
                        "logical_key": "project:main",
                        "path": "main.tex",
                        "reason": "user_modified",
                        "pending_content": "\\section{Generated}",
                    }
                ]
            }
        },
    )
    db = _FakeDb(
        [
            _Result(scalar=compute_session),
            _Result(scalar=execution),
            _Result(scalars=[task]),
            _Result(scalars=[subagent]),
            _Result(scalar=None),
            _Result(scalar=None),
            _Result(scalar=latex_project),
            _Result(
                scalar={
                    "mode": "compute_workflow",
                    "requires_sandbox": False,
                    "review_gate": {},
                    "allowed_paths": [],
                }
            ),
        ]
    )

    projection = await ComputeProjectionService(db).get_projection(
        compute_session_id="compute-1",
        user_id="user-1",
    )

    assert projection is not None
    assert projection["compute_session"]["id"] == "compute-1"
    assert projection["execution"]["id"] == "exec-1"
    assert projection["primary_task"]["task_id"] == "task-1"
    assert projection["runtime_blocks"][0] == {"id": "phase-1", "type": "phase"}
    assert projection["subagents"][0]["task_id"] == "subagent-1"
    assert projection["artifacts"]["ids"] == ["artifact-1"]
    assert projection["artifacts"]["count"] == 1
    assert projection["runtime_profile"]["runtime_mode"] == "compute_workflow"
    assert projection["runtime_profile"]["requires_sandbox"] is False
    assert projection["runtime_profile"]["review_gate"] is None
    assert projection["sandbox"]["session_id"] == "sandbox-1"
    assert projection["sandbox"]["status"] == "bound"
    assert projection["sandbox"]["required"] is False
    assert projection["sandbox"]["file_count"] == len(projection["files"])
    assert projection["sandbox"]["log_count"] == len(projection["logs"])
    assert projection["prism"]["status"] == "pending_changes"
    assert projection["prism"]["project_id"] == "latex-project-1"
    assert projection["prism"]["url"] == "/latex/latex-project-1"
    assert projection["prism"]["main_file"] == "main.tex"
    assert projection["prism"]["target_files"] == ["main.tex", "sections/introduction.tex"]
    assert projection["prism"]["compile"]["status"] == "success"
    assert projection["prism"]["compile"]["page_count"] == 8
    assert projection["prism"]["file_changes"] == [
        {
            "logical_key": "project:main",
            "path": "main.tex",
            "reason": "user_modified",
            "pending_content": "\\section{Generated}",
        }
    ]
    assert projection["prism"]["applied_file_changes"] == []
    assert {
        (item["kind"], item.get("artifact_id"), item.get("path"), item.get("url"))
        for item in projection["files"]
    } >= {
        ("artifact", "artifact-1", None, None),
        (
            "sandbox_file",
            None,
            "/mnt/user-data/execution/python_plot/run-1/output/plot.png",
            "/api/threads/thread-1/artifacts/mnt/user-data/execution/python_plot/run-1/output/plot.png",
        ),
        (
            "linked_file",
            None,
            None,
            "/api/threads/thread-1/artifacts/mnt/user-data/execution/python_plot/run-1/output/plot.png",
        ),
        ("prism_file", None, "main.tex", "/latex/latex-project-1"),
        ("prism_file", None, "sections/introduction.tex", "/latex/latex-project-1"),
    }
    assert any(item["title"] == "渲染图表" and item["level"] == "success" for item in projection["logs"])
    assert any(item["title"] == "logs" and item["message"] == "rendered plot" for item in projection["logs"])
    assert any(item["title"] == "compile_logs" and item["level"] == "warning" for item in projection["logs"])
    assert projection["review_gate"]["status"] == "awaiting_user"
    assert projection["review_gate"]["required"] is True
    assert projection["review_gate"]["policy"] is None
    assert projection["review_gate"]["next_actions"] == [{"kind": "review", "title": "检查输出"}]
    assert projection["review_gate"]["items"][0]["label"] == "检查输出"
    assert projection["review_gate"]["advisory_code"] == "needs_review"


@pytest.mark.asyncio
async def test_compute_projection_treats_open_prism_as_optional_review_action() -> None:
    now = datetime.now(UTC)
    compute_session = SimpleNamespace(
        id="compute-2",
        execution_id="exec-2",
        workspace_id="ws-1",
        user_id="user-1",
        sandbox_session_id=None,
        active_view="overview",
        ui_state={},
        created_at=now,
        updated_at=now,
    )
    execution = _execution_namespace(
        id="exec-2",
        user_id="user-1",
        workspace_id="ws-1",
        thread_id="thread-1",
        workspace_type="thesis",
        feature_id="thesis_writing",
        entry_skill_id="thesis-writer",
        status="completed",
        params={},
        message=None,
        runtime_state=None,
        result_summary="已同步到 Prism",
        artifact_ids=[],
        next_actions=[
            {
                "action": "open_prism",
                "label": "在 WenjinPrism 中继续编辑",
                "url": "/latex/latex-project-1",
            }
        ],
        advisory_code=None,
        last_error=None,
        created_at=now,
        updated_at=now,
        started_at=now,
        completed_at=now,
    )
    db = _FakeDb(
        [
            _Result(scalar=compute_session),
            _Result(scalar=execution),
            _Result(scalars=[]),
            _Result(scalars=[]),
            _Result(scalar=None),
            _Result(scalar=None),
            _Result(
                scalar={
                    "mode": "compute_workflow",
                    "requires_sandbox": False,
                    "review_gate": {},
                    "allowed_paths": [],
                }
            ),
        ]
    )

    projection = await ComputeProjectionService(db).get_projection(
        compute_session_id="compute-2",
        user_id="user-1",
    )

    assert projection is not None
    assert projection["review_gate"]["status"] == "advisory"
    assert projection["review_gate"]["required"] is False
    assert projection["review_gate"]["items"][0]["kind"] == "action"
    assert projection["review_gate"]["items"][0]["required"] is False


@pytest.mark.asyncio
async def test_compute_projection_exposes_runtime_profile_policy_for_agentic_sandbox_feature() -> None:
    now = datetime.now(UTC)
    compute_session = SimpleNamespace(
        id="compute-figure",
        execution_id="exec-figure",
        workspace_id="ws-1",
        user_id="user-1",
        sandbox_session_id=None,
        active_view="overview",
        ui_state={},
        created_at=now,
        updated_at=now,
    )
    execution = _execution_namespace(
        id="exec-figure",
        user_id="user-1",
        workspace_id="ws-1",
        thread_id="thread-1",
        workspace_type="proposal",
        feature_id="figure_generation",
        entry_skill_id="figure-designer",
        status="running",
        params={},
        message=None,
        runtime_state=None,
        result_summary=None,
        artifact_ids=[],
        next_actions=[],
        advisory_code=None,
        last_error=None,
        created_at=now,
        updated_at=now,
        started_at=now,
        completed_at=None,
    )
    db = _FakeDb(
        [
            _Result(scalar=compute_session),
            _Result(scalar=execution),
            _Result(scalars=[]),
            _Result(scalars=[]),
            _Result(scalar=None),
            _Result(scalar=None),
            _Result(
                scalar={
                    "mode": "compute_agentic",
                    "requires_sandbox": True,
                    "review_gate": {"kind": "artifact_preview"},
                    "allowed_paths": [],
                }
            ),
        ]
    )

    projection = await ComputeProjectionService(db).get_projection(
        compute_session_id="compute-figure",
        user_id="user-1",
    )

    assert projection is not None
    assert projection["runtime_profile"]["runtime_mode"] == "compute_agentic"
    assert projection["runtime_profile"]["requires_sandbox"] is True
    assert projection["runtime_profile"]["review_gate"] == "artifact_preview"
    assert projection["sandbox"]["status"] == "required"
    assert projection["sandbox"]["required"] is True
    assert projection["review_gate"]["status"] == "clear"
    assert projection["review_gate"]["policy"] == "artifact_preview"


@pytest.mark.asyncio
async def test_compute_projection_refreshes_resolved_prism_file_changes_from_project_metadata() -> None:
    now = datetime.now(UTC)
    compute_session = SimpleNamespace(
        id="compute-3",
        execution_id="exec-3",
        workspace_id="ws-1",
        user_id="user-1",
        sandbox_session_id=None,
        active_view="overview",
        ui_state={},
        created_at=now,
        updated_at=now,
    )
    execution = _execution_namespace(
        id="exec-3",
        user_id="user-1",
        workspace_id="ws-1",
        thread_id="thread-1",
        workspace_type="sci",
        feature_id="writing",
        entry_skill_id="sci-writer",
        status="completed",
        params={},
        message=None,
        result_summary=None,
        artifact_ids=[],
        next_actions=[],
        advisory_code=None,
        last_error=None,
        created_at=now,
        updated_at=now,
        started_at=now,
        completed_at=now,
    )
    task = SimpleNamespace(
        id="task-3",
        execution_id="exec-3",
        task_type="workspace_feature",
        workspace_id="ws-1",
        feature_id="writing",
        thread_id="thread-1",
        action=None,
        status="success",
        progress=100,
        message="完成",
        result={
            "data": {
                "latex_project_id": "latex-project-3",
                "main_file": "main.tex",
                "section_file": "sections/introduction.tex",
                "file_changes": [
                    {
                        "logical_key": "section:introduction",
                        "path": "sections/introduction.tex",
                        "reason": "user_modified",
                    }
                ],
            }
        },
        error=None,
        runtime_state=None,
        created_at=now,
        started_at=now,
        completed_at=now,
    )
    latex_project = SimpleNamespace(
        id="latex-project-3",
        user_id="user-1",
        main_file="main.tex",
        llm_config={
            "metadata": {
                "file_changes": [],
                "applied_file_changes": {
                    "section:introduction": {
                        "logical_key": "section:introduction",
                        "path": "sections/introduction.tex",
                        "previous_hash": "sha256:old",
                        "applied_hash": "sha256:new",
                        "revert_signature": "signature",
                    }
                },
            }
        },
    )
    db = _FakeDb(
        [
            _Result(scalar=compute_session),
            _Result(scalar=execution),
            _Result(scalars=[task]),
            _Result(scalars=[]),
            _Result(scalar=None),
            _Result(scalar=None),
            _Result(scalar=latex_project),
            _Result(
                scalar={
                    "mode": "compute_workflow",
                    "requires_sandbox": False,
                    "review_gate": {},
                    "allowed_paths": [],
                }
            ),
        ]
    )

    projection = await ComputeProjectionService(db).get_projection(
        compute_session_id="compute-3",
        user_id="user-1",
    )

    assert projection is not None
    assert projection["prism"]["status"] == "ready"
    assert projection["prism"]["file_changes"] == []
    assert projection["prism"]["applied_file_changes"] == [
        {
            "logical_key": "section:introduction",
            "path": "sections/introduction.tex",
            "previous_hash": "sha256:old",
            "applied_hash": "sha256:new",
            "revert_signature": "signature",
        }
    ]


@pytest.mark.asyncio
async def test_projection_prefers_workspace_owned_authoritative_prism_over_runtime_payload() -> None:
    now = datetime.now(UTC)
    compute_session = SimpleNamespace(
        id="compute-authoritative",
        execution_id="exec-authoritative",
        workspace_id="ws-1",
        user_id="user-1",
        sandbox_session_id=None,
        active_view="overview",
        ui_state={},
        created_at=now,
        updated_at=now,
    )
    execution = _execution_namespace(
        id="exec-authoritative",
        user_id="user-1",
        workspace_id="ws-1",
        thread_id="thread-1",
        workspace_type="sci",
        feature_id="writing",
        runtime_state={
            "latex_project_id": "latex-stale",
            "file_changes": [{"path": "sections/stale.tex"}],
        },
        created_at=now,
        updated_at=now,
    )
    authoritative_project = SimpleNamespace(
        id="latex-authoritative",
        user_id="user-1",
        workspace_id="ws-1",
        surface_role="primary_manuscript",
        main_file="main.tex",
        llm_config={
            "metadata": {
                "file_changes": [{"path": "sections/current.tex"}],
            }
        },
    )
    db = _FakeDb(
        [
            _Result(scalar=compute_session),
            _Result(scalar=execution),
            _Result(scalars=[]),
            _Result(scalars=[]),
            _Result(scalar=authoritative_project),
            _Result(scalar=authoritative_project),
            _Result(
                scalar={
                    "mode": "compute_workflow",
                    "requires_sandbox": False,
                    "review_gate": {},
                    "allowed_paths": [],
                }
            ),
        ]
    )

    projection = await ComputeProjectionService(db).get_projection(
        compute_session_id="compute-authoritative",
        user_id="user-1",
    )

    assert projection is not None
    assert projection["prism"]["project_id"] == "latex-authoritative"
    assert projection["prism"]["url"] == "/workspaces/ws-1/prism"
    assert projection["prism"]["status"] == "pending_changes"
    assert projection["prism"]["target_files"] == ["main.tex", "sections/current.tex"]
    assert projection["prism"]["file_changes"][0]["path"] == "sections/current.tex"
