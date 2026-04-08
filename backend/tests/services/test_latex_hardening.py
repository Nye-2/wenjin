"""Hardening tests for LaTeX projectization services."""

from __future__ import annotations

import shlex
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.gateway.routers.latex import (
    LatexCompileRequest,
    LatexUpdateProjectRequest,
    _normalize_upload_relative_path,
)
from src.services.latex.compile_service import (
    LatexCompileService,
    get_latex_compile_timeout_seconds,
)
from src.services.latex.engine_config import get_default_latex_engine
from src.services.latex.paths import normalize_relative_path
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
