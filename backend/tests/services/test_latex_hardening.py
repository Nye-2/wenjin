"""Hardening tests for LaTeX projectization services."""

from __future__ import annotations

import shlex
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from src.gateway.routers.latex import (
    LatexCompileRequest,
    LatexUpdateProjectRequest,
    _candidate_risk_level,
    _collect_archive_upload_payload,
    _compute_candidate_signature,
    _compute_revert_signature,
    _is_reserved_upload_path,
    _normalize_upload_relative_path,
    _profiled_comment,
    _read_upload_bytes_with_limit,
)
from src.services.latex.compile_service import (
    LatexCompileService,
    get_latex_compile_history_retention,
    get_latex_compile_timeout_seconds,
)
from src.services.latex.engine_config import (
    get_default_latex_engine,
    get_supported_latex_engines,
)
from src.services.latex.paths import normalize_relative_path
from src.services.latex.project_service import (
    LatexProjectService,
    LatexTemplateNotFoundError,
    LatexTemplateUnavailableError,
)
from src.services.workspace_latex_projects import WorkspaceLatexProjectService


class _FakeMappings:
    def __init__(self, row: dict[str, object] | None) -> None:
        self._row = row

    def first(self) -> dict[str, object] | None:
        return self._row


class _FakeExecuteResult:
    def __init__(self, row: dict[str, object] | None) -> None:
        self._row = row

    def mappings(self) -> _FakeMappings:
        return _FakeMappings(self._row)


def test_get_default_latex_engine_uses_env_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WENJIN_LATEX_DEFAULT_COMPILER", "pdflatex")
    assert get_default_latex_engine() == "pdflatex"


def test_get_default_latex_engine_falls_back_on_invalid_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WENJIN_LATEX_DEFAULT_COMPILER", "not_supported")
    assert get_default_latex_engine() == "xelatex"


def test_compile_request_uses_runtime_default_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WENJIN_LATEX_DEFAULT_COMPILER", "pdflatex")
    assert LatexCompileRequest().engine == "pdflatex"


def test_get_supported_latex_engines_contains_expected_engines() -> None:
    engines = set(get_supported_latex_engines())
    assert engines == {"xelatex", "pdflatex"}


def test_compile_timeout_uses_default_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WENJIN_LATEX_COMPILE_TIMEOUT_SECONDS", raising=False)
    assert get_latex_compile_timeout_seconds() == 300


def test_compile_timeout_clamps_and_validates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WENJIN_LATEX_COMPILE_TIMEOUT_SECONDS", "15")
    assert get_latex_compile_timeout_seconds() == 30
    monkeypatch.setenv("WENJIN_LATEX_COMPILE_TIMEOUT_SECONDS", "2400")
    assert get_latex_compile_timeout_seconds() == 1800
    monkeypatch.setenv("WENJIN_LATEX_COMPILE_TIMEOUT_SECONDS", "bad-value")
    assert get_latex_compile_timeout_seconds() == 300


def test_profiled_comment_adds_strategy_guidance() -> None:
    base = "请增强表达"
    conservative = _profiled_comment(base, "conservative")
    balanced = _profiled_comment(base, "balanced")
    aggressive = _profiled_comment(base, "aggressive")
    assert "最小改动" in conservative
    assert "中等强度" in balanced
    assert "较大幅度重构" in aggressive
    assert base in conservative and base in balanced and base in aggressive


def test_candidate_risk_level_uses_flags_and_change_size() -> None:
    assert _candidate_risk_level(risk_flags=["citation_drop"], tokens_changed=10) == "high"
    assert _candidate_risk_level(risk_flags=[], tokens_changed=90) == "medium"
    assert _candidate_risk_level(risk_flags=[], tokens_changed=8) == "low"


def test_candidate_signature_is_stable_and_sensitive_to_inputs() -> None:
    first = _compute_candidate_signature(
        file_path="main.tex",
        candidate_id="cand-1",
        target_start=10,
        target_end=20,
        rewritten_text="updated text",
        base_file_hash="a" * 64,
        base_range_hash="b" * 64,
    )
    second = _compute_candidate_signature(
        file_path="main.tex",
        candidate_id="cand-1",
        target_start=10,
        target_end=20,
        rewritten_text="updated text",
        base_file_hash="a" * 64,
        base_range_hash="b" * 64,
    )
    changed = _compute_candidate_signature(
        file_path="main.tex",
        candidate_id="cand-2",
        target_start=10,
        target_end=20,
        rewritten_text="updated text",
        base_file_hash="a" * 64,
        base_range_hash="b" * 64,
    )
    assert first == second
    assert first != changed


def test_revert_signature_is_stable_and_sensitive_to_inputs() -> None:
    first = _compute_revert_signature(
        file_path="main.tex",
        candidate_id="cand-1",
        revert_start=12,
        revert_end=24,
        rewritten_text="new text",
        previous_text="old text",
        applied_file_hash="c" * 64,
    )
    second = _compute_revert_signature(
        file_path="main.tex",
        candidate_id="cand-1",
        revert_start=12,
        revert_end=24,
        rewritten_text="new text",
        previous_text="old text",
        applied_file_hash="c" * 64,
    )
    changed = _compute_revert_signature(
        file_path="main.tex",
        candidate_id="cand-1",
        revert_start=12,
        revert_end=24,
        rewritten_text="new text",
        previous_text="old text changed",
        applied_file_hash="c" * 64,
    )
    assert first == second
    assert first != changed


def test_compile_history_retention_uses_default_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("WENJIN_LATEX_COMPILE_HISTORY_RETENTION", raising=False)
    assert get_latex_compile_history_retention() == 60


def test_compile_history_retention_clamps_and_validates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WENJIN_LATEX_COMPILE_HISTORY_RETENTION", "3")
    assert get_latex_compile_history_retention() == 10
    monkeypatch.setenv("WENJIN_LATEX_COMPILE_HISTORY_RETENTION", "2000")
    assert get_latex_compile_history_retention() == 500
    monkeypatch.setenv("WENJIN_LATEX_COMPILE_HISTORY_RETENTION", "bad-value")
    assert get_latex_compile_history_retention() == 60


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
        LatexProjectService._ensure_user_path_allowed(".compile/cache.log")
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

    service = LatexProjectService(AsyncMock())
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

    service = LatexProjectService(AsyncMock())
    with pytest.raises(FileNotFoundError, match="missing.pdf"):
        service.resolve_blob_file(project, "missing.pdf")


def test_compile_build_command_quotes_shell_arguments() -> None:
    command = LatexCompileService._build_command(
        entry_file="chapter's/ma in'.tex",
        compiler="xelatex",
    )
    assert command[:2] == ["/bin/bash", "-lc"]
    script = command[2]

    quoted_dir = shlex.quote("chapter's")
    quoted_name = shlex.quote("ma in'.tex")
    quoted_stem = shlex.quote("ma in'")

    assert f"cd {quoted_dir}" in script
    assert (
        f"xelatex -interaction=nonstopmode -halt-on-error -file-line-error -synctex=1 {quoted_name}"
        in script
    )
    assert f"biber {quoted_stem}" in script
    assert f"bibtex {quoted_stem}" in script


def test_compile_build_command_normalizes_leading_slash_in_main_file() -> None:
    command = LatexCompileService._build_command(
        entry_file=normalize_relative_path("/main.tex"),
        compiler="xelatex",
    )
    script = command[2]
    assert "\ncd /\n" not in script
    assert "cd ." in script
    assert "xelatex -interaction=nonstopmode -halt-on-error -file-line-error -synctex=1 main.tex" in script


@pytest.mark.asyncio
async def test_compile_project_can_skip_history_record(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("WENJIN_LATEX_DATA_DIR", str(tmp_path))
    project = SimpleNamespace(id="proj-no-history", main_file="main.tex")
    project_dir = tmp_path / project.id
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "main.tex").write_text("\\documentclass{article}\\begin{document}x\\end{document}", encoding="utf-8")

    async def _fake_compile(
        self: LatexCompileService,
        mounted_project_dir: Path,
        *,
        entry_file: str,
        compiler: str,
    ) -> tuple[int, str, str, Path]:
        del self, entry_file, compiler
        pdf_path = mounted_project_dir / "main.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n")
        return 0, "", "", pdf_path

    db = AsyncMock()
    service = LatexCompileService(db)
    monkeypatch.setattr(LatexCompileService, "_run_compile_in_docker", _fake_compile)

    payload = await service.compile_project(project, engine="xelatex", record_history=False)
    assert payload["ok"] is True
    assert payload["history_id"] is None
    assert payload["pdf_endpoint"] is None
    db.add.assert_not_called()
    db.commit.assert_not_awaited()
    db.refresh.assert_not_awaited()


def test_parse_synctex_edit_output() -> None:
    output = (
        "SyncTeX result begin\n"
        "Input:/tmp/project/main.tex\n"
        "Line:42\n"
        "Column:7\n"
        "SyncTeX result end\n"
    )
    parsed = LatexCompileService._parse_synctex_edit_output(output)
    assert parsed == ("/tmp/project/main.tex", 42, 7)


def test_parse_synctex_view_output() -> None:
    output = (
        "SyncTeX result begin\n"
        "Page:3\n"
        "x:120.5\n"
        "y:240.75\n"
        "SyncTeX result end\n"
    )
    parsed = LatexCompileService._parse_synctex_view_output(output)
    assert parsed == (3, 120.5, 240.75)


def test_offset_line_column_roundtrip() -> None:
    content = "line1\nline2\nline3"
    offset = content.index("line3")
    line, column = LatexCompileService._offset_to_line_column(content, offset)
    assert (line, column) == (3, 1)
    rebuilt = LatexCompileService._line_column_to_offset(content, line, column)
    assert rebuilt == offset


@pytest.mark.asyncio
async def test_find_existing_project_scopes_by_workspace_and_owner() -> None:
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_FakeExecuteResult({"id": "proj-1"}))
    matched_project = SimpleNamespace(id="proj-1")
    db.get = AsyncMock(return_value=matched_project)

    service = WorkspaceLatexProjectService(db)
    found = await service._find_existing_project(
        "workspace-1",
        owner_user_id="user-1",
        template="sci_default",
    )

    assert found is matched_project
    statement, params = db.execute.await_args.args
    assert params["workspace_id"] == "workspace-1"
    assert params["owner_user_id"] == "user-1"
    assert params["template"] == "sci_default"
    assert "user_id = :owner_user_id" in str(statement)


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
    assert _is_reserved_upload_path("assets/.compile/cache.bin") is True
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
    db = AsyncMock()
    db.get = AsyncMock(return_value=None)
    service = LatexProjectService(db)

    with pytest.raises(LatexTemplateNotFoundError, match="Template not found"):
        await service._copy_template_if_available("missing-template", Path("/tmp"))


@pytest.mark.asyncio
async def test_copy_template_requires_available_assets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db = AsyncMock()
    db.get = AsyncMock(
        return_value=SimpleNamespace(
            template_path="missing-template-dir",
            main_file="main.tex",
        )
    )
    monkeypatch.setenv("WENJIN_LATEX_TEMPLATE_DIR", str(tmp_path))
    service = LatexProjectService(db)

    with pytest.raises(LatexTemplateUnavailableError, match="Template assets unavailable"):
        await service._copy_template_if_available("acl", tmp_path / "project")


@pytest.mark.asyncio
async def test_permanent_delete_removes_compile_runs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("WENJIN_LATEX_DATA_DIR", str(tmp_path))
    project_id = "proj-delete-1"
    project_dir = tmp_path / project_id
    compile_dir = tmp_path / "_compile_runs" / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    compile_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "main.tex").write_text("x", encoding="utf-8")
    (compile_dir / "run-1").mkdir(parents=True, exist_ok=True)

    db = AsyncMock()
    service = LatexProjectService(db)
    project = SimpleNamespace(id=project_id)

    await service.permanent_delete(project)

    assert not project_dir.exists()
    assert not compile_dir.exists()
    db.delete.assert_awaited_once_with(project)
    db.commit.assert_awaited_once()


def test_pick_preferred_tex_path_prioritizes_main_and_shallow_paths() -> None:
    assert LatexProjectService._pick_preferred_tex_path(
        ["chapters/intro.tex", "paper/main.tex", "appendix/a.tex"]
    ) == "paper/main.tex"
    assert LatexProjectService._pick_preferred_tex_path(
        ["sections/ch1.tex", "overview.tex", "sections/ch2.tex"]
    ) == "overview.tex"
