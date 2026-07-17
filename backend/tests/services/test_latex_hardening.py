"""Hardening tests for LaTeX projectization services."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from src.gateway.routers.latex import (
    LatexUpdateProjectRequest,
    _collect_archive_upload_payload,
    _is_reserved_upload_path,
    _normalize_upload_relative_path,
    _read_upload_bytes_with_limit,
)
from src.services.latex.paths import normalize_relative_path
from src.services.latex.project_service import (
    LatexProjectService,
    LatexTemplateNotFoundError,
    LatexTemplateUnavailableError,
)
from src.services.workspace_latex_projects import WorkspaceLatexProjectService


class _FakeLatexProjectFiles:
    def __init__(self, files: dict[str, str]) -> None:
        self.files = dict(files)
        self.writes: list[tuple[str, str]] = []

    def read_text_file(self, project: object, path: str) -> str:
        _ = project
        if path not in self.files:
            raise FileNotFoundError(path)
        return self.files[path]

    async def write_text_file(self, project: object, path: str, content: str) -> None:
        _ = project
        self.files[path] = content
        self.writes.append((path, content))


class _FakePrismReviewService:
    review_item: SimpleNamespace | None = None
    pending_changes: list[dict[str, object]] = []
    cleared: list[str] = []
    protected: list[dict[str, object]] = []

    def __init__(self, db: object, *, autocommit: bool = True) -> None:
        _ = db
        _ = autocommit

    @classmethod
    def reset(cls) -> None:
        cls.review_item = SimpleNamespace(
            id="review-project-main",
            logical_key="project:main",
            target_file_path="main.tex",
            summary="feature_proposal",
            status="pending",
            preview_payload={
                "logical_key": "project:main",
                "path": "main.tex",
                "reason": "feature_proposal",
                "pending_content": "\\section{Generated}\n",
            },
        )
        cls.pending_changes = []
        cls.cleared = []
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

    async def upsert_pending_file_change(
        self,
        project: object | None = None,
        **kwargs: object,
    ) -> SimpleNamespace:
        _ = project
        kwargs.setdefault("source_task_id", None)
        self.pending_changes.append(dict(kwargs))
        self.review_item = SimpleNamespace(
            id=f"review-{kwargs['logical_key']}",
            logical_key=kwargs["logical_key"],
            target_file_path=kwargs["path"],
            summary=kwargs["reason"],
            status="pending",
            preview_payload={
                "logical_key": kwargs["logical_key"],
                "path": kwargs["path"],
                "reason": kwargs["reason"],
                "pending_content": kwargs["pending_content"],
                "pending_hash": kwargs["pending_hash"],
                "current_hash": kwargs["current_hash"],
            },
        )
        return self.review_item

    async def clear_review_item(self, project: object, *, logical_key: str) -> None:
        _ = project
        self.cleared.append(logical_key)
        if self.review_item is not None and self.review_item.logical_key == logical_key:
            self.review_item = None

    async def clear_pending_file_change(
        self,
        *,
        workspace_id: str,
        latex_project_id: str,
        logical_key: str,
    ) -> bool:
        _ = workspace_id
        _ = latex_project_id
        self.cleared.append(logical_key)
        if self.review_item is not None and self.review_item.logical_key == logical_key:
            self.review_item = None
            return True
        return False

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

    async def upsert_protected_section(self, **kwargs: object) -> None:
        self.protected.append(
            {
                "logical_key": kwargs.get("section_key"),
                "path": kwargs.get("file_path"),
                "reason": kwargs.get("reason"),
            }
        )

    async def upsert_latex_protected_scope(self, **kwargs: object) -> SimpleNamespace:
        self.protected.append(
            {
                "logical_key": kwargs.get("section_key"),
                "path": kwargs.get("file_path"),
                "reason": kwargs.get("reason"),
            }
        )
        return SimpleNamespace(id="protected-1", **kwargs)

    async def find_prism_file_change(
        self,
        *,
        workspace_id: str,
        latex_project_id: str,
        logical_key: str,
        statuses: list[str] | None = None,
    ) -> SimpleNamespace | None:
        return await self.find_file_change(
            workspace_id=workspace_id,
            latex_project_id=latex_project_id,
            logical_key=logical_key,
            statuses=tuple(statuses or ()),
        )

    async def mark_prism_file_change_applied(
        self,
        item_id: str,
        payload: object,
    ) -> SimpleNamespace | None:
        return await self.mark_applied_file_change(
            item_id,
            **payload.model_dump(mode="json"),
        )

    async def mark_prism_file_change_rejected(
        self,
        item_id: str,
        payload: object,
    ) -> SimpleNamespace | None:
        return await self.mark_rejected_file_change(
            item_id,
            reason=payload.reason,
        )

    async def mark_prism_file_change_reverted(self, item_id: str) -> SimpleNamespace | None:
        return await self.mark_reverted_file_change(item_id)

    async def upsert_latex_prism_protected_scope(self, payload: object) -> SimpleNamespace:
        return await self.upsert_latex_protected_scope(**payload.model_dump(mode="json"))

    async def upsert_pending_prism_file_change(self, payload: object) -> SimpleNamespace:
        return await self.upsert_pending_file_change(**payload.model_dump(mode="json"))

    async def clear_pending_prism_file_change(self, payload: object) -> bool:
        return await self.clear_pending_file_change(**payload.model_dump(mode="json"))


def test_update_project_request_ignores_llm_config_mass_assignment() -> None:
    request = LatexUpdateProjectRequest.model_validate(
        {
            "name": "safe-name",
            "llm_config": {"workspace_id": "ws-1"},
        }
    )
    assert request.model_dump(exclude_unset=True) == {"name": "safe-name"}


def test_normalize_relative_path_rejects_control_characters() -> None:
    with pytest.raises(ValueError, match="control characters"):
        normalize_relative_path("notes/main.tex\n")


def test_normalize_relative_path_rejects_invalid_segments() -> None:
    with pytest.raises(ValueError, match="invalid segments"):
        normalize_relative_path("./main.tex")


def test_normalize_relative_path_canonicalizes_redundant_separators() -> None:
    assert normalize_relative_path(" sections//chapter1///main.tex ") == "sections/chapter1/main.tex"


def test_project_service_rejects_reserved_paths() -> None:
    with pytest.raises(ValueError, match="reserved"):
        LatexProjectService._ensure_user_path_allowed("project.json")
    with pytest.raises(ValueError, match="reserved"):
        LatexProjectService._ensure_user_path_allowed("assets/__pycache__/x.pyc")
    LatexProjectService._ensure_user_path_allowed("sections/intro.tex")


def test_project_service_resolve_blob_file_returns_path_and_media_type(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WENJIN_LATEX_DATA_DIR", str(tmp_path))
    project = SimpleNamespace(id="proj-blob")
    blob_file = tmp_path / project.id / "figures" / "plot.png"
    blob_file.parent.mkdir(parents=True, exist_ok=True)
    blob_file.write_bytes(b"\x89PNG\r\n\x1a\n")

    service = LatexProjectService()
    resolved_path, media_type = service.resolve_blob_file(project, "figures/plot.png")

    assert resolved_path == blob_file.resolve()
    assert media_type == "image/png"


def test_project_service_resolve_blob_file_raises_for_missing_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WENJIN_LATEX_DATA_DIR", str(tmp_path))
    project = SimpleNamespace(id="proj-blob-missing")
    (tmp_path / project.id).mkdir(parents=True, exist_ok=True)

    service = LatexProjectService()
    with pytest.raises(FileNotFoundError, match="missing.pdf"):
        service.resolve_blob_file(project, "missing.pdf")


@pytest.mark.asyncio
async def test_find_existing_project_scopes_by_workspace_and_owner() -> None:
    matched_project = SimpleNamespace(id="proj-1")

    class _FakeLatexClient:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        async def get_workspace_primary_latex_project(self, **kwargs: object) -> object:
            self.calls.append(dict(kwargs))
            return matched_project

    client = _FakeLatexClient()
    service = WorkspaceLatexProjectService(dataservice=client)  # type: ignore[arg-type]
    found = await service._find_existing_project(
        "workspace-1",
        owner_user_id="user-1",
        template="sci_default",
    )

    assert found is matched_project
    assert client.calls == [
        {
            "workspace_id": "workspace-1",
            "owner_user_id": "user-1",
            "template": "sci_default",
        }
    ]


def test_latex_default_project_files_use_refs_bib(tmp_path) -> None:
    """New Prism/LaTeX projects use refs.bib as the only BibTeX SSOT."""
    LatexProjectService._write_default_files(tmp_path)

    assert (tmp_path / "refs.bib").exists()
    assert not (tmp_path / "references.bib").exists()


def test_workspace_main_tex_uses_refs_bibliography() -> None:
    """Workspace-generated manuscript templates point at refs.bib."""
    service = WorkspaceLatexProjectService()

    main_tex = service._build_sci_main_tex(
        paper_title="Federated LLM Fine-Tuning",
        section_map={"introduction": "sections/introduction.tex"},
        keywords=["federated learning", "large language models"],
    )

    assert "\\bibliography{refs}" in main_tex
    assert "\\bibliography{references}" not in main_tex


@pytest.mark.asyncio
async def test_bridge_write_preserves_existing_file_for_mission_review() -> None:
    _FakePrismReviewService.reset()
    service = WorkspaceLatexProjectService(dataservice=_FakePrismReviewService(object()),  # type: ignore[arg-type]
    )
    fake_files = _FakeLatexProjectFiles({"main.tex": "old"})
    service.project_service = fake_files  # type: ignore[assignment]
    metadata = {
        "managed_files": {
            "project:main": {
                "path": "main.tex",
                "content_hash": WorkspaceLatexProjectService._content_hash("old"),
                "protected": False,
            }
        },
    }

    await service._safe_bridge_write(
        SimpleNamespace(id="project-1", workspace_id="workspace-1", surface_role="primary_manuscript"),
        workspace_id="workspace-1",
        relative_path="main.tex",
        content="new",
        logical_key="project:main",
        metadata=metadata,
    )

    assert fake_files.writes == []
    assert fake_files.files["main.tex"] == "old"
    assert "file_changes" not in metadata
    assert _FakePrismReviewService.pending_changes == []
    assert metadata["managed_files"]["project:main"] == {
        "path": "main.tex",
        "content_hash": WorkspaceLatexProjectService._content_hash("old"),
        "protected": True,
    }


@pytest.mark.asyncio
async def test_bridge_write_seeds_missing_file_without_legacy_review_state() -> None:
    _FakePrismReviewService.reset()
    service = WorkspaceLatexProjectService(dataservice=_FakePrismReviewService(object()),  # type: ignore[arg-type]
    )
    fake_files = _FakeLatexProjectFiles({})
    service.project_service = fake_files  # type: ignore[assignment]
    metadata = {
        "managed_files": {},
    }

    await service._safe_bridge_write(
        SimpleNamespace(id="project-1", workspace_id="workspace-1", surface_role="primary_manuscript"),
        workspace_id="workspace-1",
        relative_path="sections/introduction.tex",
        content="fresh",
        logical_key="section:introduction",
        metadata=metadata,
    )

    assert fake_files.writes == [("sections/introduction.tex", "fresh")]
    assert "file_changes" not in metadata
    assert _FakePrismReviewService.cleared == []
    assert metadata["managed_files"]["section:introduction"] == {
        "path": "sections/introduction.tex",
        "content_hash": WorkspaceLatexProjectService._content_hash("fresh"),
        "protected": False,
    }



def test_upload_path_normalization_avoids_duplicate_base_prefix() -> None:
    assert _normalize_upload_relative_path("image.png", "assets") == "assets/image.png"
    assert _normalize_upload_relative_path("assets/image.png", "assets") == "assets/image.png"
    assert _normalize_upload_relative_path("nested/figure.png", "") == "nested/figure.png"


def test_upload_path_normalization_rejects_invalid_segments() -> None:
    with pytest.raises(ValueError, match="invalid segments"):
        _normalize_upload_relative_path("../figure.png", "")


def test_reserved_upload_path_blocks_project_meta_and_runtime_dirs() -> None:
    assert _is_reserved_upload_path("project.json") is True
    assert _is_reserved_upload_path(".git/config") is True
    assert _is_reserved_upload_path("assets/__pycache__/cache.bin") is True
    assert _is_reserved_upload_path("sections/intro.tex") is False


def test_archive_upload_payload_skips_reserved_files_and_normalizes_paths() -> None:
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("paper/main.tex", "\\documentclass{article}")
        archive.writestr("paper/project.json", "{}")
        archive.writestr("paper/assets/fig.png", b"\x89PNG")

    files, folders, skipped = _collect_archive_upload_payload(
        buffer.getvalue(),
        base_path="imports",
    )
    file_paths = [path for path, _ in files]
    assert "imports/main.tex" in file_paths
    assert "imports/assets/fig.png" in file_paths
    assert "imports/project.json" not in file_paths
    assert "imports/project.json" in skipped
    assert "imports/assets" in folders


def test_archive_upload_payload_can_preserve_top_level_folder() -> None:
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("paper/main.tex", "\\documentclass{article}")
        archive.writestr("paper/assets/fig.png", b"\x89PNG")

    files, folders, _ = _collect_archive_upload_payload(
        buffer.getvalue(),
        base_path="imports",
        strip_root=False,
    )
    file_paths = [path for path, _ in files]
    assert "imports/paper/main.tex" in file_paths
    assert "imports/paper/assets/fig.png" in file_paths
    assert "imports/paper" in folders
    assert "imports/paper/assets" in folders


def test_archive_upload_payload_rejects_invalid_archive() -> None:
    with pytest.raises(ValueError, match="Invalid ZIP archive"):
        _collect_archive_upload_payload(b"not-a-zip", base_path=None)


@pytest.mark.asyncio
async def test_archive_upload_reader_rejects_oversized_payload() -> None:
    class _FakeUpload:
        def __init__(self) -> None:
            self.filename = "archive.zip"
            self._chunks = [b"1234", b"5678", b"9", b""]

        async def read(self, _size: int) -> bytes:
            return self._chunks.pop(0)

    with pytest.raises(HTTPException) as exc_info:
        await _read_upload_bytes_with_limit(
            _FakeUpload(),
            max_size_bytes=8,
        )

    assert exc_info.value.status_code == 413
    assert "Archive file too large" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_archive_upload_reader_collects_chunks_within_limit() -> None:
    class _FakeUpload:
        def __init__(self) -> None:
            self.filename = "archive.zip"
            self._chunks = [b"abc", b"def", b""]

        async def read(self, _size: int) -> bytes:
            return self._chunks.pop(0)

    payload = await _read_upload_bytes_with_limit(
        _FakeUpload(),
        max_size_bytes=8,
    )

    assert payload == b"abcdef"


@pytest.mark.asyncio
async def test_copy_template_requires_existing_template() -> None:
    dataservice = MagicMock()
    dataservice.get_latex_template = AsyncMock(return_value=None)
    service = LatexProjectService(dataservice=dataservice)

    with pytest.raises(LatexTemplateNotFoundError, match="Template not found"):
        await service._copy_template_if_available("missing-template", Path("/tmp"))


@pytest.mark.asyncio
async def test_copy_template_requires_available_assets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dataservice = MagicMock()
    dataservice.get_latex_template = AsyncMock(
        return_value=SimpleNamespace(
            template_path="missing-template-dir",
            main_file="main.tex",
        )
    )
    monkeypatch.setenv("WENJIN_LATEX_TEMPLATE_DIR", str(tmp_path))
    service = LatexProjectService(dataservice=dataservice)

    with pytest.raises(LatexTemplateUnavailableError, match="Template assets unavailable"):
        await service._copy_template_if_available("acl", tmp_path / "project")


def test_pick_preferred_tex_path_prioritizes_main_and_shallow_paths() -> None:
    assert LatexProjectService._pick_preferred_tex_path(
        ["chapters/intro.tex", "paper/main.tex", "appendix/a.tex"]
    ) == "paper/main.tex"
    assert LatexProjectService._pick_preferred_tex_path(
        ["sections/ch1.tex", "overview.tex", "sections/ch2.tex"]
    ) == "overview.tex"
