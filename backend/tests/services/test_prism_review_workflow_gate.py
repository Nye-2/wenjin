"""Workflow gate for Prism pending-review write contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.compute.projection_service import ComputeProjectionService
from src.gateway.contracts.latex import (
    LatexFileChangeActionRequest,
    LatexFileChangeApplyRequest,
    LatexFileChangeRevertRequest,
    LatexProtectedSectionRequest,
)
from src.gateway.routers.latex_files import (
    apply_project_file_change,
    discard_project_file_change,
    preview_project_file_change,
    protect_project_section,
    revert_project_file_change,
)


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
    def __init__(self, results=()):
        self._results = list(results)
        self.execute_calls = []

    async def execute(self, query):
        self.execute_calls.append(query)
        return self._results.pop(0)


class _FakeDataServiceClient:
    def __init__(
        self,
        *,
        compute_session: SimpleNamespace,
        execution: SimpleNamespace,
        capability: SimpleNamespace,
    ) -> None:
        self.compute_session = compute_session
        self.execution = execution
        self.capability = capability

    async def get_compute_session(self, compute_session_id: str) -> SimpleNamespace | None:
        if self.compute_session.id != compute_session_id:
            return None
        return self.compute_session

    async def get_execution(self, execution_id: str) -> SimpleNamespace | None:
        if self.execution.id != execution_id:
            return None
        return self.execution

    async def get_latex_project(self, project_id: str) -> SimpleNamespace | None:
        project = _FakeLatexRouterService.project
        if project.id != project_id:
            return None
        return project

    async def list_execution_nodes(self, execution_id: str) -> list[SimpleNamespace]:
        _ = execution_id
        return []

    async def get_catalog_capability(
        self,
        *,
        capability_id: str,
        workspace_type: str,
    ) -> SimpleNamespace | None:
        _ = capability_id
        _ = workspace_type
        return self.capability

    async def get_prism_surface(self, workspace_id: str) -> SimpleNamespace | None:
        project = _FakeLatexRouterService.project
        if getattr(project, "workspace_id", None) != workspace_id:
            return None
        return SimpleNamespace(
            project=_prism_project_from_latex(project),
            documents=[_prism_document_from_latex(project)],
            files=[
                _prism_file_from_latex(project),
                _prism_file_from_latex(project, "sections/introduction.tex"),
            ],
        )

    async def list_prism_protected_scopes(self, project_id: str, *, limit: int = 200):
        _ = project_id
        _ = limit
        return [
            SimpleNamespace(
                id=f"protected-{index}",
                workspace_id=scope.get("workspace_id", "ws-1"),
                project_id=f"prism-{_FakeLatexRouterService.project.id}",
                document_id=None,
                file_id=None,
                file_path=scope.get("file_path", "main.tex"),
                section_key=scope.get("section_key", ""),
                scope=scope.get("scope", ""),
                reason=scope.get("reason"),
                source=scope.get("source", "manual"),
                metadata_json=dict(scope.get("metadata_json") or {}),
            )
            for index, scope in enumerate(_FakePrismReviewService.protected)
        ]

    async def list_review_items(
        self,
        *,
        workspace_id: str | None = None,
        project_id: str | None = None,
        target_domain: str | None = None,
        target_kind: str | None = None,
        status: list[str] | None = None,
        review_type: str | None = None,
        limit: int = 100,
    ):
        _ = workspace_id
        _ = project_id
        _ = target_domain
        _ = target_kind
        _ = review_type
        _ = limit
        item = _FakePrismReviewService.review_item
        if item is None:
            return []
        if status is not None and item.status not in set(status):
            return []
        return [
            _canonical_review_item(
                item,
                project=_FakeLatexRouterService.project,
                now=datetime.now(UTC),
            )
        ]

    async def find_prism_file_change(
        self,
        *,
        workspace_id: str,
        latex_project_id: str,
        logical_key: str,
        statuses: list[str] | tuple[str, ...] | None = None,
    ):
        _ = workspace_id
        _ = latex_project_id
        item = _FakePrismReviewService.review_item
        if item is None or item.logical_key != logical_key:
            return None
        if statuses is not None and item.status not in set(statuses):
            return None
        return _canonical_review_item(
            item,
            project=_FakeLatexRouterService.project,
            now=datetime.now(UTC),
        )

    async def list_provenance_links(self, **kwargs):
        _ = kwargs
        return []

    async def list_room_decisions(self, workspace_id: str):
        _ = workspace_id
        return []

    async def list_room_memory_facts(self, *, workspace_id: str, limit: int = 5):
        _ = workspace_id
        _ = limit
        return []

    async def list_executions(self, *, workspace_id: str, limit: int = 5):
        _ = workspace_id
        _ = limit
        return []


class _FakeCommitDb:
    committed = False

    async def commit(self) -> None:
        self.committed = True


class _FakeLatexRouterService:
    project = SimpleNamespace()
    files: dict[str, str] = {}
    update_calls: list[dict[str, object]] = []

    def __init__(self, *args: object, **kwargs: object) -> None:
        _ = args
        _ = kwargs

    async def get_owned(self, project_id: str, user_id: str) -> object | None:
        if project_id == "latex-1" and user_id == "user-1":
            return self.project
        return None

    def read_text_file(self, project: object, path: str) -> str:
        _ = project
        if path not in self.files:
            raise FileNotFoundError(path)
        return self.files[path]

    async def write_text_file(self, project: object, path: str, content: str) -> None:
        _ = project
        self.files[path] = content

    async def update_llm_config(self, project: object, llm_config: dict[str, object]) -> object:
        project.llm_config = llm_config
        self.update_calls.append(llm_config)
        return project


class _FakePrismReviewService:
    review_item: SimpleNamespace | None = None
    protected: list[dict[str, object]] = []

    def __init__(self, db: object) -> None:
        _ = db

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    @classmethod
    def reset(cls) -> None:
        cls.review_item = SimpleNamespace(
            id="review-introduction",
            logical_key="section:introduction",
            target_file_path="sections/introduction.tex",
            summary="feature_proposal",
            status="pending",
            preview_payload={
                "logical_key": "section:introduction",
                "path": "sections/introduction.tex",
                "reason": "feature_proposal",
                "pending_content": r"Generated claim \cite{lovelace2026}.",
            },
        )
        cls.protected = []

    async def get_review_item(
        self,
        project: object,
        *,
        logical_key: str,
        statuses: tuple[str, ...] | None = None,
    ) -> SimpleNamespace | None:
        _ = project
        item = self.review_item
        if item is None or item.logical_key != logical_key:
            return None
        if statuses and item.status not in statuses:
            return None
        return item

    async def find_file_change(
        self,
        *,
        workspace_id: str,
        latex_project_id: str,
        logical_key: str,
        statuses: tuple[str, ...] | None = None,
    ) -> SimpleNamespace | None:
        _ = workspace_id
        _ = latex_project_id
        item = self.review_item
        if item is None or item.logical_key != logical_key:
            return None
        if statuses and item.status not in statuses:
            return None
        return item

    async def find_prism_file_change(
        self,
        *,
        workspace_id: str,
        latex_project_id: str,
        logical_key: str,
        statuses: list[str] | tuple[str, ...] | None = None,
    ):
        _ = workspace_id
        _ = latex_project_id
        item = self.review_item
        if item is None or item.logical_key != logical_key:
            return None
        if statuses is not None and item.status not in set(statuses):
            return None
        return _canonical_review_item(
            item,
            project=_FakeLatexRouterService.project,
            now=datetime.now(UTC),
        )

    async def mark_applied(self, item: SimpleNamespace, **kwargs: object) -> SimpleNamespace:
        item.status = "applied"
        item.preview_payload = {**item.preview_payload, **kwargs}
        return item

    async def mark_applied_file_change(
        self,
        item_id: str,
        **kwargs: object,
    ) -> SimpleNamespace | None:
        item = self.review_item
        if item is None or item.id != item_id:
            return None
        item.status = "applied"
        item.preview_payload = {**item.preview_payload, **kwargs}
        item.result_json = dict(kwargs)
        return item

    async def mark_prism_file_change_applied(self, item_id: str, payload) -> SimpleNamespace | None:
        return await self.mark_applied_file_change(
            item_id,
            previous_content=payload.previous_content,
            previous_hash=payload.previous_hash,
            applied_hash=payload.applied_hash,
            revert_signature=payload.revert_signature,
        )

    async def mark_rejected(
        self,
        item: SimpleNamespace,
        *,
        protect_section: bool,
        reason: str | None = None,
    ) -> SimpleNamespace:
        item.status = "rejected"
        item.summary = reason or item.summary
        if protect_section:
            self.protected.append(
                {
                    "logical_key": item.logical_key,
                    "path": item.target_file_path,
                    "reason": item.summary,
                }
            )
        return item

    async def mark_rejected_file_change(
        self,
        item_id: str,
        *,
        reason: str | None = None,
    ) -> SimpleNamespace | None:
        item = self.review_item
        if item is None or item.id != item_id:
            return None
        item.status = "rejected"
        item.summary = reason or item.summary
        return item

    async def mark_prism_file_change_rejected(self, item_id: str, payload) -> SimpleNamespace | None:
        return await self.mark_rejected_file_change(item_id, reason=payload.reason)

    async def mark_reverted(self, item: SimpleNamespace) -> SimpleNamespace:
        item.status = "reverted"
        return item

    async def mark_reverted_file_change(
        self,
        item_id: str,
    ) -> SimpleNamespace | None:
        item = self.review_item
        if item is None or item.id != item_id:
            return None
        item.status = "reverted"
        return item

    async def mark_prism_file_change_reverted(self, item_id: str) -> SimpleNamespace | None:
        return await self.mark_reverted_file_change(item_id)

    async def upsert_protected_section(self, **kwargs: object) -> None:
        if kwargs.get("source") == "review_reject":
            self.protected.append(
                {
                    "logical_key": kwargs.get("section_key"),
                    "path": kwargs.get("file_path"),
                    "reason": kwargs.get("reason"),
                }
            )
            return
        self.protected.append(dict(kwargs))

    async def upsert_latex_protected_scope(self, **kwargs: object) -> SimpleNamespace:
        if kwargs.get("source") == "review_reject":
            self.protected.append(
                {
                    "logical_key": kwargs.get("section_key"),
                    "path": kwargs.get("file_path"),
                    "reason": kwargs.get("reason"),
                }
            )
        else:
            self.protected.append(dict(kwargs))
        return SimpleNamespace(id="protected-1", **kwargs)

    async def upsert_latex_prism_protected_scope(self, payload) -> SimpleNamespace:
        return await self.upsert_latex_protected_scope(**payload.model_dump())

    async def record_source_citation_usage(self, command):
        _FakeSourceDataService.calls.append(
            {
                "workspace_id": command.workspace_id,
                "citation_keys": command.citation_keys,
                "latex_project_id": command.latex_project_id,
                "target_id": command.target_id,
                "target_section": command.target_section,
                "target_ref_json": command.target_ref_json,
                "generated_text": command.generated_text,
                "usage_type": command.usage_type,
                "accepted_status": command.accepted_status,
            }
        )
        return {"recorded": len(command.citation_keys)}


class _FakeSourceDataService:
    calls: list[dict[str, object]] = []

    def __init__(self, db: object) -> None:
        _ = db

    async def record_citation_usage(self, command):
        self.calls.append(
            {
                "workspace_id": command.workspace_id,
                "citation_keys": command.citation_keys,
                "latex_project_id": command.latex_project_id,
                "target_id": command.target_id,
                "target_section": command.target_section,
                "target_ref_json": command.target_ref_json,
                "generated_text": command.generated_text,
                "usage_type": command.usage_type,
                "accepted_status": command.accepted_status,
            }
        )
        return {"recorded": len(command.citation_keys)}


def _reset_router_state() -> None:
    _FakePrismReviewService.reset()
    _FakeLatexRouterService.project = SimpleNamespace(
        id="latex-1",
        user_id="user-1",
        workspace_id="ws-1",
        surface_role="primary_manuscript",
        main_file="main.tex",
        llm_config={
            "workspace_id": "ws-1",
            "metadata": {
                "managed_files": {
                    "section:introduction": {
                        "path": "sections/introduction.tex",
                        "content_hash": "old-hash",
                        "protected": False,
                    }
                },
            },
        },
    )
    _FakeLatexRouterService.files = {
        "sections/introduction.tex": "Current introduction.",
    }
    _FakeLatexRouterService.update_calls = []
    _FakeSourceDataService.calls = []


def _compute_session(now: datetime) -> SimpleNamespace:
    return SimpleNamespace(
        id="compute-1",
        execution_id="exec-1",
        workspace_id="ws-1",
        user_id="user-1",
        sandbox_session_id=None,
        active_view="overview",
        ui_state={},
        created_at=now,
        updated_at=now,
    )


def _execution(now: datetime) -> SimpleNamespace:
    return SimpleNamespace(
        id="exec-1",
        user_id="user-1",
        workspace_id="ws-1",
        thread_id="thread-1",
        execution_type="feature",
        workspace_type="thesis",
        feature_id="thesis_writing",
        entry_skill_id="thesis-writer",
        display_name="论文写作",
        status="completed",
        params={},
        result=None,
        error=None,
        graph_structure=None,
        node_states={},
        progress=100,
        message=None,
        runtime_state=None,
        result_summary="写作结果已进入 Prism 待确认区",
        artifact_ids=[],
        next_actions=[
            {
                "action": "preview_prism_changes",
                "label": "预览待确认修改",
                "project_id": "latex-1",
            }
        ],
        advisory_code=None,
        last_error=None,
        parent_execution_id=None,
        child_execution_ids=[],
        dispatch_mode=None,
        worker_task_id=None,
        created_at=now,
        updated_at=now,
        started_at=now,
        completed_at=now,
    )


def _capability_record(runtime: dict[str, object]) -> SimpleNamespace:
    return SimpleNamespace(
        id="thesis_writing",
        workspace_type="thesis",
        display_name="论文写作",
        runtime=runtime,
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


def _task(now: datetime) -> SimpleNamespace:
    return SimpleNamespace(
        id="task-1",
        execution_id="exec-1",
        task_type="workspace_feature",
        workspace_id="ws-1",
        feature_id="thesis_writing",
        thread_id="thread-1",
        action=None,
        status="success",
        progress=100,
        message="完成",
        result={
            "data": {
                "latex_project_id": "latex-1",
                "main_file": "main.tex",
                "section_file": "sections/introduction.tex",
                "file_changes": [
                    {
                        "logical_key": "section:introduction",
                        "path": "sections/introduction.tex",
                        "reason": "feature_proposal",
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


async def _projection_for_project(project: SimpleNamespace) -> dict[str, object]:
    now = datetime.now(UTC)
    item = _FakePrismReviewService.review_item
    projected_item = _canonical_review_item(item, project=project, now=now) if item else None
    pending_items = [
        projected_item
    ] if projected_item is not None and projected_item.status in {"pending", "accepted"} else []
    applied_items = [
        projected_item
    ] if projected_item is not None and projected_item.status == "applied" else []
    execution = _execution(now)
    execution.result = _task(now).result
    db = _FakeDb(
        [
            _Result(scalar=_prism_project_from_latex(project)),
            _Result(scalars=[_prism_document_from_latex(project)]),
            _Result(
                scalars=[
                    _prism_file_from_latex(project),
                    _prism_file_from_latex(project, "sections/introduction.tex"),
                ]
            ),
            _Result(scalar=project),
            _Result(scalars=pending_items),
            _Result(scalars=applied_items),
            _Result(scalars=[]),
            _Result(scalars=[]),
            _Result(scalars=[]),
            _Result(scalars=[]),
            _Result(scalars=[]),
            _Result(scalars=[]),
        ]
    )
    dataservice = _FakeDataServiceClient(
        compute_session=_compute_session(now),
        execution=execution,
        capability=_capability_record({
            "mode": "compute_workflow",
            "requires_sandbox": False,
            "review_gate": {},
            "allowed_paths": [],
        }),
    )
    projection = await ComputeProjectionService(db, dataservice=dataservice).get_projection(
        compute_session_id="compute-1",
        user_id="user-1",
    )
    assert projection is not None
    return projection


def _canonical_review_item(
    item: SimpleNamespace,
    *,
    project: SimpleNamespace,
    now: datetime,
) -> SimpleNamespace:
    preview = dict(item.preview_payload or {})
    return SimpleNamespace(
        id=item.id,
        batch_id="batch-review-introduction",
        workspace_id=project.workspace_id,
        source_item_id=item.logical_key,
        item_kind="file_change",
        target_domain="prism",
        target_kind="prism_file_change",
        target_ref_json={
            "latex_project_id": project.id,
            "logical_key": item.logical_key,
            "file_path": item.target_file_path,
        },
        title=item.target_file_path,
        summary=item.summary,
        status=item.status,
        payload_json=preview,
        preview_json=preview,
        result_json=None,
        error_text=None,
        provenance_json={},
        sort_order=0,
        applied_at=getattr(item, "applied_at", None),
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_prism_review_projection_preview_apply_usage_and_revert_workflow_gate() -> None:
    _reset_router_state()

    projection = await _projection_for_project(_FakeLatexRouterService.project)

    assert projection["prism"]["status"] == "pending_changes"
    assert projection["review_gate"]["items"][0]["required"] is True
    assert projection["prism"]["file_changes"][0]["logical_key"] == "section:introduction"
    assert projection["prism"]["target_files"] == ["main.tex", "sections/introduction.tex"]

    user = SimpleNamespace(id="user-1")
    db = _FakeDb()
    dataservice = _FakePrismReviewService(db)
    with patch(
        "src.gateway.routers.latex_files.LatexProjectService",
        _FakeLatexRouterService,
    ):
        preview = await preview_project_file_change(
            "latex-1",
            LatexFileChangeActionRequest(logical_key="section:introduction"),
            current_user=user,
            dataservice=dataservice,
        )
        applied = await apply_project_file_change(
            "latex-1",
            LatexFileChangeApplyRequest(
                logical_key="section:introduction",
                change_signature=preview.change_signature,
            ),
            current_user=user,
            dataservice=dataservice,
        )

    assert applied.applied is True
    assert _FakeLatexRouterService.files["sections/introduction.tex"] == (
        r"Generated claim \cite{lovelace2026}."
    )
    metadata = _FakeLatexRouterService.project.llm_config["metadata"]
    assert "file_changes" not in metadata
    assert "applied_file_changes" not in metadata
    assert _FakePrismReviewService.review_item.status == "applied"
    assert _FakePrismReviewService.review_item.preview_payload["revert_signature"] == (
        applied.undo.revert_signature
    )
    assert _FakeSourceDataService.calls == [
        {
            "workspace_id": "ws-1",
            "citation_keys": ["lovelace2026"],
            "latex_project_id": "latex-1",
            "target_id": "latex-1",
            "target_section": "sections/introduction.tex",
            "target_ref_json": {"file_path": "sections/introduction.tex"},
            "generated_text": r"Generated claim \cite{lovelace2026}.",
            "usage_type": "citation_only",
            "accepted_status": "accepted",
        }
    ]

    applied_projection = await _projection_for_project(_FakeLatexRouterService.project)
    assert applied_projection["prism"]["status"] == "ready"
    assert applied_projection["prism"]["file_changes"] == []
    assert applied_projection["prism"]["applied_file_changes"][0]["logical_key"] == (
        "section:introduction"
    )

    with patch(
        "src.gateway.routers.latex_files.LatexProjectService",
        _FakeLatexRouterService,
    ):
        reverted = await revert_project_file_change(
            "latex-1",
            LatexFileChangeRevertRequest(
                logical_key="section:introduction",
                revert_signature=applied.undo.revert_signature,
            ),
            current_user=user,
            dataservice=_FakePrismReviewService(object()),
        )

    assert reverted.reverted is True
    assert _FakeLatexRouterService.files["sections/introduction.tex"] == "Current introduction."
    reverted_metadata = _FakeLatexRouterService.project.llm_config["metadata"]
    assert reverted_metadata["managed_files"]["section:introduction"]["protected"] is True
    assert "applied_file_changes" not in reverted_metadata
    assert _FakePrismReviewService.review_item.status == "reverted"


@pytest.mark.asyncio
async def test_prism_review_discard_protects_user_content_and_clears_pending_projection() -> None:
    _reset_router_state()

    user = SimpleNamespace(id="user-1")
    dataservice = _FakePrismReviewService(_FakeCommitDb())
    with patch(
        "src.gateway.routers.latex_files.LatexProjectService",
        _FakeLatexRouterService,
    ):
        discarded = await discard_project_file_change(
            "latex-1",
            LatexFileChangeActionRequest(logical_key="section:introduction"),
            current_user=user,
            dataservice=dataservice,
        )

    assert discarded.discarded is True
    metadata = _FakeLatexRouterService.project.llm_config["metadata"]
    assert metadata["managed_files"]["section:introduction"]["protected"] is True
    assert _FakePrismReviewService.review_item.status == "rejected"
    assert _FakePrismReviewService.protected == [
        {
            "logical_key": "section:introduction",
            "path": "sections/introduction.tex",
            "reason": "user_protected",
        }
    ]

    projection = await _projection_for_project(_FakeLatexRouterService.project)
    assert projection["prism"]["status"] == "ready"
    assert projection["prism"]["file_changes"] == []


@pytest.mark.asyncio
async def test_manual_prism_protection_uses_canonical_protected_section() -> None:
    _reset_router_state()
    user = SimpleNamespace(id="user-1")
    db = _FakeCommitDb()
    dataservice = _FakePrismReviewService(db)

    with patch(
        "src.gateway.routers.latex_files.LatexProjectService",
        _FakeLatexRouterService,
    ):
        response = await protect_project_section(
            "latex-1",
            LatexProtectedSectionRequest(
                path="sections/introduction.tex",
                scope="file",
                reason="user_manual_protect",
            ),
            current_user=user,
            dataservice=dataservice,
        )

    assert response.protected is True
    assert _FakePrismReviewService.protected == [
        {
            "workspace_id": "ws-1",
            "latex_project_id": "latex-1",
            "file_path": "sections/introduction.tex",
            "section_key": "",
            "scope": "file",
            "reason": "user_manual_protect",
            "source": "manual_edit",
            "metadata_json": {},
        }
    ]
