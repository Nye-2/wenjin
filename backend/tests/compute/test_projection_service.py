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


class _FakeDataServiceClient:
    def __init__(
        self,
        *,
        compute_session: SimpleNamespace,
        execution: SimpleNamespace,
        nodes: list[SimpleNamespace] | None = None,
        capability: SimpleNamespace | None = None,
        db: _FakeDb | None = None,
    ) -> None:
        self.compute_session = compute_session
        self.execution = execution
        self.nodes = list(nodes or [])
        self.capability = capability
        self._db = db

    async def get_compute_session(self, compute_session_id: str) -> SimpleNamespace | None:
        if self.compute_session.id != compute_session_id:
            return None
        return self.compute_session

    async def get_execution(self, execution_id: str) -> SimpleNamespace | None:
        if self.execution.id != execution_id:
            return None
        return self.execution

    async def list_execution_nodes(self, execution_id: str) -> list[SimpleNamespace]:
        return [node for node in self.nodes if node.execution_id == execution_id]

    async def get_catalog_capability(
        self,
        *,
        capability_id: str,
        workspace_type: str,
    ) -> SimpleNamespace | None:
        _ = capability_id
        _ = workspace_type
        if self.capability is None:
            return None
        return self.capability

    async def get_prism_surface(self, workspace_id: str) -> SimpleNamespace | None:
        _ = workspace_id
        project_result = await self._db.execute(None) if hasattr(self, "_db") else None
        project = project_result.scalar_one_or_none() if project_result else None
        if project is None:
            return None
        documents = (await self._db.execute(None)).scalars().all()
        files = (await self._db.execute(None)).scalars().all()
        return SimpleNamespace(project=project, documents=documents, files=files)

    async def get_latex_project(self, project_id: str) -> SimpleNamespace | None:
        _ = project_id
        result = await self._db.execute(None)
        return result.scalar_one_or_none()

    async def list_review_items(self, **_kwargs: object) -> list[SimpleNamespace]:
        result = await self._db.execute(None)
        return result.scalars().all()

    async def list_provenance_links(self, **_kwargs: object) -> list[SimpleNamespace]:
        result = await self._db.execute(None)
        return result.scalars().all()

    async def list_prism_protected_scopes(self, project_id: str, *, limit: int = 200) -> list[SimpleNamespace]:
        _ = project_id
        _ = limit
        result = await self._db.execute(None)
        return result.scalars().all()

    async def list_room_decisions(self, workspace_id: str) -> list[SimpleNamespace]:
        _ = workspace_id
        await self._db.execute(None)
        return []

    async def list_room_memory_facts(self, *, workspace_id: str, limit: int = 15, category: str | None = None):
        _ = workspace_id
        _ = limit
        _ = category
        result = await self._db.execute(None)
        return result.scalars().all()

    async def list_executions(self, *, workspace_id: str, limit: int = 5, **_kwargs: object):
        _ = workspace_id
        _ = limit
        result = await self._db.execute(None)
        return result.scalars().all()


def _review_item(
    *,
    logical_key: str,
    path: str,
    latex_project_id: str,
    status: str = "pending",
    reason: str = "feature_proposal",
    payload: dict | None = None,
) -> SimpleNamespace:
    now = datetime.now(UTC)
    preview_json = {
        "logical_key": logical_key,
        "path": path,
        "reason": reason,
        **(payload or {}),
    }
    return SimpleNamespace(
        id=f"review-{logical_key}",
        batch_id=f"batch-{logical_key}",
        workspace_id="ws-1",
        source_item_id=logical_key,
        item_kind="file_change",
        target_domain="prism",
        target_kind="prism_file_change",
        target_ref_json={
            "latex_project_id": latex_project_id,
            "logical_key": logical_key,
            "file_path": path,
        },
        title=path,
        summary=reason,
        status=status,
        payload_json={"path": path, **(payload or {})},
        preview_json=preview_json,
        result_json=None,
        error_text=None,
        provenance_json={},
        sort_order=0,
        applied_at=now if status == "applied" else None,
        created_at=now,
        updated_at=now,
    )


def _execution_namespace(**overrides):
    now = overrides.get("created_at") or datetime.now(UTC)
    return SimpleNamespace(
        id=overrides.get("id", "exec-1"),
        user_id=overrides.get("user_id", "user-1"),
        workspace_id=overrides.get("workspace_id", "ws-1"),
        thread_id=overrides.get("thread_id", "thread-1"),
        execution_type=overrides.get("execution_type", "feature"),
        feature_id=overrides.get("feature_id", "research_question_to_paper"),
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


def _node_namespace(**overrides):
    now = overrides.get("created_at") or datetime.now(UTC)
    return SimpleNamespace(
        id=overrides.get("id", "node-row-1"),
        execution_id=overrides.get("execution_id", "exec-1"),
        parent_node_id=overrides.get("parent_node_id"),
        node_id=overrides.get("node_id", "phase__task"),
        node_type=overrides.get("node_type", "react"),
        label=overrides.get("label", "Agent node"),
        status=overrides.get("status", "completed"),
        input_data=overrides.get("input_data"),
        output_data=overrides.get("output_data"),
        thinking=overrides.get("thinking"),
        tool_calls=overrides.get("tool_calls"),
        token_usage=overrides.get("token_usage"),
        node_metadata=overrides.get("node_metadata"),
        created_at=overrides.get("created_at", now),
        updated_at=overrides.get("updated_at", now),
        started_at=overrides.get("started_at"),
        completed_at=overrides.get("completed_at"),
    )


def _capability_record(runtime: dict) -> SimpleNamespace:
    sandbox_policy = dict(runtime.get("sandbox_policy") or {})
    if not sandbox_policy:
        sandbox_policy = {"mode": "none", "profiles": [], "allowed_operations": []}
    normalized_runtime = {
        "mode": runtime.get("mode", "compute_agentic"),
        "sandbox_policy": sandbox_policy,
        "review_gate": runtime.get("review_gate", {}),
        "allowed_paths": runtime.get("allowed_paths", []),
    }
    return SimpleNamespace(
        id="test_capability",
        workspace_type="sci",
        schema_version="capability.v2",
        display_name="Test Capability",
        runtime=normalized_runtime,
        definition_json={"sandbox_policy": sandbox_policy},
        ui_meta={},
        dashboard_meta={},
    )


def _prism_project_from_latex(project: SimpleNamespace) -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=f"prism-{project.id}",
        workspace_id=project.workspace_id,
        role="primary_manuscript",
        title=getattr(project, "name", "Prism Manuscript"),
        adapter_kind="latex",
        adapter_ref_id=project.id,
        status="active",
        settings_json={},
        adapter_metadata_json={
            "latex_project_id": project.id,
            "main_file": project.main_file,
        },
        trashed_at=None,
        created_at=now,
        updated_at=now,
    )


def _prism_document_from_latex(project: SimpleNamespace) -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=f"doc-{project.id}",
        workspace_id=project.workspace_id,
        project_id=f"prism-{project.id}",
        document_kind="manuscript",
        title=getattr(project, "name", "Prism Manuscript"),
        adapter_kind="latex",
        status="active",
        root_file_id=f"file-{project.id}-main",
        metadata_json={"main_file": project.main_file},
        created_at=now,
        updated_at=now,
    )


def _prism_file_from_latex(project: SimpleNamespace, path: str | None = None) -> SimpleNamespace:
    now = datetime.now(UTC)
    file_path = path or project.main_file
    return SimpleNamespace(
        id=f"file-{project.id}-{file_path}",
        workspace_id=project.workspace_id,
        document_id=f"doc-{project.id}",
        path=file_path,
        file_role="main" if file_path == project.main_file else "generated",
        mime_type="text/x-tex",
        current_version_id=None,
        content_hash=None,
        sort_order=0,
        metadata_json={},
        deleted_at=None,
        created_at=now,
        updated_at=now,
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
    execution_result = {
        "sandbox_path": "/mnt/user-data/execution/python_plot/run-1/output/plot.png",
        "render_data": {
            "file_url": "/api/threads/thread-1/artifacts/mnt/user-data/execution/python_plot/run-1/output/plot.png",
        },
        "data": {
            "latex_project_id": "latex-project-1",
            "main_file": "main.tex",
            "section_file": "sections/introduction.tex",
            "section_map": {"introduction": "sections/introduction.tex"},
            "compile_status": "success",
            "pdf_endpoint": "/api/prism/latex-adapter/projects/latex-project-1/compile/history-1/pdf",
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
                }
            ],
        },
        "logs": "rendered plot",
        "compile_logs": "warning only",
    }
    execution = _execution_namespace(
        id="exec-1",
        user_id="user-1",
        workspace_id="ws-1",
        thread_id="thread-1",
        workspace_type="sci",
        feature_id="research_question_to_paper",
        entry_skill_id="manuscript-architect",
        status="pending",
        params={"topic": "agents"},
        message="生成中",
        result=execution_result,
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
    subagent_node = _node_namespace(
        id="subagent-node-1",
        execution_id="exec-1",
        node_id="discovery__search",
        node_type="scout",
        label="Search",
        status="completed",
        input_data={"prompt": "search"},
        output_data={"summary": "done"},
        node_metadata={"workflow_phase": "discovery"},
        created_at=now,
        updated_at=now,
        completed_at=now,
    )
    latex_project = SimpleNamespace(
        id="latex-project-1",
        user_id="user-1",
        workspace_id="ws-1",
        surface_role="primary_manuscript",
        main_file="main.tex",
        llm_config={
            "metadata": {
                "section_map": {"introduction": "sections/introduction.tex"},
            }
        },
    )
    db = _FakeDb(
        [
            _Result(scalar=_prism_project_from_latex(latex_project)),
            _Result(scalars=[_prism_document_from_latex(latex_project)]),
            _Result(scalars=[_prism_file_from_latex(latex_project)]),
            _Result(scalar=latex_project),
            _Result(
                scalars=[
                    _review_item(
                        logical_key="project:main",
                        path="main.tex",
                        latex_project_id="latex-project-1",
                        reason="user_modified",
                        payload={"pending_content": "\\section{Generated}"},
                    )
                ]
            ),
            _Result(scalars=[]),
            _Result(scalars=[]),
            _Result(scalars=[]),
            _Result(scalars=[]),
            _Result(scalars=[]),
            _Result(scalars=[]),
            _Result(scalars=[]),
        ]
    )
    dataservice = _FakeDataServiceClient(
        compute_session=compute_session,
        execution=execution,
        nodes=[subagent_node],
        capability=_capability_record({
            "mode": "compute_workflow",
            "sandbox_policy": {"mode": "none", "profiles": [], "allowed_operations": []},
            "review_gate": {},
            "allowed_paths": [],
        }),
        db=db,
    )

    projection = await ComputeProjectionService(dataservice=dataservice).get_projection(
        compute_session_id="compute-1",
        user_id="user-1",
    )

    assert projection is not None
    assert projection["compute_session"]["id"] == "compute-1"
    assert projection["execution"]["id"] == "exec-1"
    assert projection["primary_task"]["task_id"] == "exec-1"
    assert projection["runtime_blocks"][0] == {"id": "phase-1", "type": "phase"}
    assert projection["subagents"][0]["task_id"] == "subagent-node-1"
    assert projection["subagents"][0]["node_id"] == "discovery__search"
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
    assert projection["prism"]["url"] == "/workspaces/ws-1/prism"
    assert projection["prism"]["main_file"] == "main.tex"
    assert projection["prism"]["target_files"] == ["main.tex", "sections/introduction.tex"]
    assert projection["prism"]["compile"] == {}
    assert projection["prism"]["file_changes"][0]["logical_key"] == "project:main"
    assert projection["prism"]["file_changes"][0]["path"] == "main.tex"
    assert projection["prism"]["file_changes"][0]["pending_content"] == "\\section{Generated}"
    assert projection["prism"]["applied_file_changes"] == []
    assert projection["prism"]["items"][0]["logical_key"] == "project:main"
    assert projection["prism"]["items"][0]["target"]["file_path"] == "main.tex"
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
            ("prism_file", None, "main.tex", "/workspaces/ws-1/prism"),
            ("prism_file", None, "sections/introduction.tex", "/workspaces/ws-1/prism"),
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
        feature_id="idea_to_thesis_manuscript",
        entry_skill_id="manuscript-writer",
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
            _Result(scalar=None),
        ]
    )
    dataservice = _FakeDataServiceClient(
        compute_session=compute_session,
        execution=execution,
        capability=_capability_record({
            "mode": "compute_workflow",
            "sandbox_policy": {"mode": "none", "profiles": [], "allowed_operations": []},
            "review_gate": {},
            "allowed_paths": [],
        }),
        db=db,
    )

    projection = await ComputeProjectionService(dataservice=dataservice).get_projection(
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
        feature_id="technical_route_package",
        entry_skill_id="evidence-analyst",
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
            _Result(scalar=None),
        ]
    )
    dataservice = _FakeDataServiceClient(
        compute_session=compute_session,
        execution=execution,
        capability=_capability_record({
            "mode": "compute_agentic",
            "sandbox_policy": {"mode": "required", "profiles": ["analysis"], "allowed_operations": ["run_python"]},
            "review_gate": {"kind": "artifact_preview"},
            "allowed_paths": [],
        }),
        db=db,
    )

    projection = await ComputeProjectionService(dataservice=dataservice).get_projection(
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
async def test_compute_projection_refreshes_resolved_prism_file_changes_from_review_db() -> None:
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
        feature_id="research_question_to_paper",
        entry_skill_id="manuscript-writer",
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
        feature_id="research_question_to_paper",
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
    execution.result = task.result
    latex_project = SimpleNamespace(
        id="latex-project-3",
        user_id="user-1",
        workspace_id="ws-1",
        surface_role="primary_manuscript",
        main_file="main.tex",
        llm_config={"metadata": {}},
    )
    db = _FakeDb(
        [
            _Result(scalar=_prism_project_from_latex(latex_project)),
            _Result(scalars=[_prism_document_from_latex(latex_project)]),
            _Result(scalars=[_prism_file_from_latex(latex_project)]),
            _Result(scalar=latex_project),
            _Result(scalars=[]),
            _Result(
                scalars=[
                    _review_item(
                        logical_key="section:introduction",
                        path="sections/introduction.tex",
                        latex_project_id="latex-project-3",
                        status="applied",
                        payload={
                            "previous_hash": "sha256:old",
                            "applied_hash": "sha256:new",
                            "revert_signature": "signature",
                        },
                    )
                ]
            ),
            _Result(scalars=[]),
            _Result(scalars=[]),
            _Result(scalars=[]),
            _Result(scalars=[]),
            _Result(scalars=[]),
            _Result(scalars=[]),
        ]
    )
    dataservice = _FakeDataServiceClient(
        compute_session=compute_session,
        execution=execution,
        capability=_capability_record({
            "mode": "compute_workflow",
            "sandbox_policy": {"mode": "none", "profiles": [], "allowed_operations": []},
            "review_gate": {},
            "allowed_paths": [],
        }),
        db=db,
    )

    projection = await ComputeProjectionService(dataservice=dataservice).get_projection(
        compute_session_id="compute-3",
        user_id="user-1",
    )

    assert projection is not None
    assert projection["prism"]["status"] == "ready"
    assert projection["prism"]["file_changes"] == []
    assert projection["prism"]["applied_file_changes"][0]["logical_key"] == "section:introduction"
    assert projection["prism"]["applied_file_changes"][0]["path"] == "sections/introduction.tex"
    assert projection["prism"]["applied_file_changes"][0]["previous_hash"] == "sha256:old"
    assert projection["prism"]["applied_file_changes"][0]["applied_hash"] == "sha256:new"


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
        feature_id="research_question_to_paper",
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
        llm_config={"metadata": {}},
    )
    db = _FakeDb(
        [
            _Result(scalar=_prism_project_from_latex(authoritative_project)),
            _Result(scalars=[_prism_document_from_latex(authoritative_project)]),
            _Result(
                scalars=[
                    _prism_file_from_latex(authoritative_project),
                    _prism_file_from_latex(authoritative_project, "sections/current.tex"),
                ]
            ),
            _Result(scalar=authoritative_project),
            _Result(
                scalars=[
                    _review_item(
                        logical_key="section:current",
                        path="sections/current.tex",
                        latex_project_id="latex-authoritative",
                    )
                ]
            ),
            _Result(scalars=[]),
            _Result(scalars=[]),
            _Result(scalars=[]),
            _Result(scalars=[]),
            _Result(scalars=[]),
            _Result(scalars=[]),
            _Result(scalars=[]),
        ]
    )
    dataservice = _FakeDataServiceClient(
        compute_session=compute_session,
        execution=execution,
        capability=_capability_record({
            "mode": "compute_workflow",
            "sandbox_policy": {"mode": "none", "profiles": [], "allowed_operations": []},
            "review_gate": {},
            "allowed_paths": [],
        }),
        db=db,
    )

    projection = await ComputeProjectionService(dataservice=dataservice).get_projection(
        compute_session_id="compute-authoritative",
        user_id="user-1",
    )

    assert projection is not None
    assert projection["prism"]["project_id"] == "latex-authoritative"
    assert projection["prism"]["url"] == "/workspaces/ws-1/prism"
    assert projection["prism"]["status"] == "pending_changes"
    assert projection["prism"]["target_files"] == ["main.tex", "sections/current.tex"]
    assert projection["prism"]["file_changes"][0]["path"] == "sections/current.tex"
    assert projection["prism"]["items"][0]["title"] == "sections/current.tex"
