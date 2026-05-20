"""Tests for direct workspace-owned Prism routing."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.gateway.routers import latex


def test_legacy_latex_project_page_route_is_not_registered() -> None:
    app = FastAPI()
    app.include_router(latex.router)
    client = TestClient(app)

    response = client.get("/latex/latex-1", follow_redirects=False)

    assert response.status_code == 404
    assert "location" not in response.headers
