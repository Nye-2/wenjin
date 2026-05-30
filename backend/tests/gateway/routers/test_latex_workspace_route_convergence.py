"""Tests for direct workspace-owned Prism routing."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.gateway.auth_dependencies import get_current_user
from src.gateway.deps.core import get_dataservice_client
from src.gateway.routers import latex
from src.gateway.routers import latex_compile as latex_compile_module


def test_legacy_latex_project_page_route_is_not_registered() -> None:
    app = FastAPI()
    app.include_router(latex.router)
    client = TestClient(app)

    response = client.get("/latex/latex-1", follow_redirects=False)

    assert response.status_code == 404
    assert "location" not in response.headers


def test_workspace_prism_compile_blocks_invalid_citations(monkeypatch) -> None:
    """Workspace-bound Prism compile validates refs before invoking LaTeX."""

    async def _current_user():
        return SimpleNamespace(id="user-1")

    class FakeProjectService:
        def __init__(self, *args, **kwargs):
            pass

        async def get_owned(self, project_id: str, user_id: str):
            return SimpleNamespace(
                id=project_id,
                main_file="main.tex",
                llm_config={"workspace_id": "workspace-1"},
            )

        def read_text_file(self, project, relative_path: str) -> str:
            assert relative_path == "main.tex"
            return r"Missing citation \cite{missing2026}."

    class FakeSourceBibliographyService:
        def __init__(self, *args, **kwargs):
            pass

        async def validate_citations(self, *, workspace_id: str, latex_content: str):
            assert workspace_id == "workspace-1"
            assert "missing2026" in latex_content
            return {
                "valid": False,
                "missing_keys": ["missing2026"],
                "unverified_keys": [],
                "citation_keys": ["missing2026"],
            }

    compile_project = AsyncMock(return_value={})

    class FakeCompileService:
        def __init__(self, *args, **kwargs):
            pass

        async def compile_project(self, *args, **kwargs):
            return await compile_project(*args, **kwargs)

    monkeypatch.setattr(latex_compile_module, "LatexProjectService", FakeProjectService)
    monkeypatch.setattr(latex_compile_module, "LatexCompileService", FakeCompileService)
    monkeypatch.setattr(
        latex_compile_module,
        "SourceBibliographyService",
        FakeSourceBibliographyService,
        raising=False,
    )

    app = FastAPI()
    app.include_router(latex.router)
    app.dependency_overrides[get_current_user] = _current_user
    app.dependency_overrides[get_dataservice_client] = lambda: object()
    client = TestClient(app)

    response = client.post("/prism/latex-adapter/projects/project-1/compile", json={})

    assert response.status_code == 400
    assert response.json()["detail"]["missing_keys"] == ["missing2026"]
    compile_project.assert_not_awaited()
