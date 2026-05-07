"""Spec §6.1 — POST /runs/{id}/pause and /runs/{id}/resume endpoints.

Cancel already exists at /runs/{id}/cancel and goes through RunManager.
Pause/resume are new and target the in-flight ParallelExecutor through
GlobalSubagentManager (Plan 1 Task 9 wired the registry).
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.gateway.routers import runs


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(runs.router)
    fake_user = MagicMock(id="user-1")
    app.dependency_overrides[runs.get_current_user] = lambda: fake_user
    return TestClient(app)


def test_pause_calls_manager(client, monkeypatch):
    called = MagicMock()
    monkeypatch.setattr(
        "src.subagents.manager.GlobalSubagentManager.pause_run",
        lambda self, run_id: called(run_id),
    )
    # Singleton must exist for the endpoint to call get_instance
    from src.subagents.manager import GlobalSubagentManager
    monkeypatch.setattr(
        GlobalSubagentManager, "get_instance",
        classmethod(lambda cls: object.__new__(GlobalSubagentManager)),
    )

    r = client.post("/runs/run-x/pause")
    assert r.status_code == 204
    called.assert_called_once_with("run-x")


def test_resume_calls_manager(client, monkeypatch):
    called = MagicMock()
    monkeypatch.setattr(
        "src.subagents.manager.GlobalSubagentManager.resume_run",
        lambda self, run_id: called(run_id),
    )
    from src.subagents.manager import GlobalSubagentManager
    monkeypatch.setattr(
        GlobalSubagentManager, "get_instance",
        classmethod(lambda cls: object.__new__(GlobalSubagentManager)),
    )

    r = client.post("/runs/run-x/resume")
    assert r.status_code == 204
    called.assert_called_once_with("run-x")


def test_pause_returns_204_even_when_run_unknown(client, monkeypatch):
    """The manager's pause_run is silent on unknown ids; HTTP layer mirrors that."""
    from src.subagents.manager import GlobalSubagentManager
    monkeypatch.setattr(
        GlobalSubagentManager, "get_instance",
        classmethod(lambda cls: object.__new__(GlobalSubagentManager)),
    )
    monkeypatch.setattr(
        GlobalSubagentManager, "pause_run",
        lambda self, run_id: None,
    )
    r = client.post("/runs/never-existed/pause")
    assert r.status_code == 204
