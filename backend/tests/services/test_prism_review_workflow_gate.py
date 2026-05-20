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
)
from src.gateway.routers.latex_files import (
    apply_project_file_change,
    discard_project_file_change,
    preview_project_file_change,
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


class _FakeLatexRouterService:
    project = SimpleNamespace()
    files: dict[str, str] = {}
    update_calls: list[dict[str, object]] = []

    def __init__(self, db: object) -> None:
        _ = db

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

    async def mark_applied(self, item: SimpleNamespace, **kwargs: object) -> SimpleNamespace:
        item.status = "applied"
        item.preview_payload = {**item.preview_payload, **kwargs}
        return item

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

    async def mark_reverted(self, item: SimpleNamespace) -> SimpleNamespace:
        item.status = "reverted"
        return item


class _FakeReferenceUsageService:
    calls: list[dict[str, object]] = []

    def __init__(self, db: object) -> None:
        _ = db

    async def record_usage_by_citation_keys(self, **kwargs):
        self.calls.append(kwargs)
        return {"recorded": len(kwargs.get("citation_keys", []))}


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
    _FakeReferenceUsageService.calls = []


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
    pending_items = [item] if item is not None and item.status in {"pending", "deferred"} else []
    applied_items = [item] if item is not None and item.status == "applied" else []
    db = _FakeDb(
        [
            _Result(scalar=_compute_session(now)),
            _Result(scalar=_execution(now)),
            _Result(scalars=[_task(now)]),
            _Result(scalars=[]),
            _Result(scalar=project),
            _Result(scalars=pending_items),
            _Result(scalars=applied_items),
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
    return projection


@pytest.mark.asyncio
async def test_prism_review_projection_preview_apply_usage_and_revert_workflow_gate() -> None:
    _reset_router_state()

    projection = await _projection_for_project(_FakeLatexRouterService.project)

    assert projection["prism"]["status"] == "pending_changes"
    assert projection["review_gate"]["items"][0]["required"] is True
    assert projection["prism"]["file_changes"][0]["logical_key"] == "section:introduction"
    assert projection["prism"]["target_files"] == ["main.tex", "sections/introduction.tex"]

    user = SimpleNamespace(id="user-1")
    db = _FakeDb([_Result(scalars=["lovelace2026"])])
    with (
        patch(
            "src.gateway.routers.latex_files.LatexProjectService",
            _FakeLatexRouterService,
        ),
        patch(
            "src.gateway.routers.latex_files.PrismReviewService",
            _FakePrismReviewService,
        ),
        patch(
            "src.gateway.routers.latex_helpers.ReferenceUsageService",
            _FakeReferenceUsageService,
        ),
    ):
        preview = await preview_project_file_change(
            "latex-1",
            LatexFileChangeActionRequest(logical_key="section:introduction"),
            current_user=user,
            db=db,
        )
        applied = await apply_project_file_change(
            "latex-1",
            LatexFileChangeApplyRequest(
                logical_key="section:introduction",
                change_signature=preview.change_signature,
            ),
            current_user=user,
            db=db,
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
    assert _FakeReferenceUsageService.calls == [
        {
            "workspace_id": "ws-1",
            "citation_keys": ["lovelace2026"],
            "latex_project_id": "latex-1",
            "target_section": "sections/introduction.tex",
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
    ), patch(
        "src.gateway.routers.latex_files.PrismReviewService",
        _FakePrismReviewService,
    ):
        reverted = await revert_project_file_change(
            "latex-1",
            LatexFileChangeRevertRequest(
                logical_key="section:introduction",
                revert_signature=applied.undo.revert_signature,
            ),
            current_user=user,
            db=object(),
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
    with patch(
        "src.gateway.routers.latex_files.LatexProjectService",
        _FakeLatexRouterService,
    ), patch(
        "src.gateway.routers.latex_files.PrismReviewService",
        _FakePrismReviewService,
    ):
        discarded = await discard_project_file_change(
            "latex-1",
            LatexFileChangeActionRequest(logical_key="section:introduction"),
            current_user=user,
            db=object(),
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
