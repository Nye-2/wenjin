"""Tests for the execution node-detail endpoint (GET /executions/{id}/nodes/{node_id})."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.gateway.routers.executions import router

# ---------------------------------------------------------------------------
# Test app factory — overrides DataService + auth so we don't need real services
# ---------------------------------------------------------------------------


class _FakeUser:
    """Minimal user stand-in with a string-compatible .id."""
    id = "user-1"


def _build_record(data: dict[str, Any]) -> MagicMock:
    """Build a mock ExecutionRecord from a plain dict."""
    record = MagicMock()
    record.id = data.get("id", "exec-1")
    record.user_id = data.get("user_id", "user-1")
    record.graph_structure = data.get("graph_structure")
    record.node_states = data.get("node_states", {})
    return record


def _build_node(data: dict[str, Any]) -> SimpleNamespace:
    """Build a mock ExecutionNodePayload from a plain dict."""
    return SimpleNamespace(
        id=data.get("id", "node-row-1"),
        execution_id=data.get("execution_id", "exec-1"),
        node_id=data.get("node_id", "node-1"),
        node_type=data.get("node_type", "subagent"),
        label=data.get("label"),
        parent_node_id=data.get("parent_node_id"),
        status=data.get("status", "pending"),
        input_data=data.get("input_data"),
        output_data=data.get("output_data"),
        thinking=data.get("thinking"),
        tool_calls=data.get("tool_calls"),
        token_usage=data.get("token_usage"),
        node_metadata=data.get("node_metadata"),
        started_at=data.get("started_at"),
        completed_at=data.get("completed_at"),
    )


@pytest.fixture()
def client_factory():
    """Return a factory that builds a TestClient with mocked dependencies.

    Usage::

        client = client_factory(execution_record={...})
        resp = client.get("/executions/exec-1/nodes/node-1")

    Pass ``None`` for *execution_record* to simulate a missing execution.
    """
    from src.gateway.auth_dependencies import get_current_user
    from src.gateway.deps.core import get_dataservice_client

    patchers: list = []

    def _factory(
        execution_record: dict[str, Any] | None,
        execution_node: dict[str, Any] | None = None,
    ) -> TestClient:
        app = FastAPI()
        app.include_router(router)

        # Build mock record
        record = _build_record(execution_record) if execution_record is not None else None
        node = _build_node(execution_node) if execution_node is not None else None

        # Override auth
        app.dependency_overrides[get_current_user] = lambda: _FakeUser()

        # Override DataService + ExecutionService
        app.dependency_overrides[get_dataservice_client] = lambda: object()

        svc_mock = MagicMock()
        svc_mock.get_by_id = AsyncMock(return_value=record)
        svc_mock.find_node_by_node_id = AsyncMock(return_value=node)
        patcher = patch(
            "src.gateway.routers.executions.ExecutionService",
            return_value=svc_mock,
        )
        patcher.start()
        patchers.append(patcher)

        return TestClient(app)

    yield _factory

    for p in patchers:
        p.stop()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_get_node_detail_returns_node_info(client_factory):
    """Happy path: execution exists with node in graph_structure and execution_nodes."""
    record = {
        "id": "exec-1",
        "user_id": "user-1",
        "graph_structure": {
            "nodes": [
                {"id": "node-1", "label": "Search", "phase_index": 0},
                {"id": "node-2", "label": "Analyze", "phase_index": 1},
            ],
            "edges": [{"from": "node-1", "to": "node-2"}],
        },
        "node_states": {
            "node-1": {
                "status": "failed",
                "output": {"stale": True},
            },
        },
    }
    node = {
        "node_id": "node-1",
        "label": "Runtime Search",
        "status": "completed",
        "input_data": {"query": "machine learning"},
        "output_data": {"results_count": 15},
        "thinking": "Searching for relevant papers...",
        "tool_calls": [{"name": "scholar_search", "args": {"query": "ml"}, "result": "15 found"}],
        "token_usage": {"input": 150, "output": 200},
        "started_at": datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
        "completed_at": datetime(2026, 1, 1, 0, 1, tzinfo=UTC),
    }

    client = client_factory(record, node)
    resp = client.get("/executions/exec-1/nodes/node-1")

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "node-1"
    assert data["label"] == "Runtime Search"
    assert data["status"] == "completed"
    assert data["phase_index"] == 0
    assert data["input"] == {"query": "machine learning"}
    assert data["output"] == {"results_count": 15}
    assert data["thinking"] == "Searching for relevant papers..."
    assert len(data["tools"]) == 1
    assert data["token_usage"] == {"input": 150, "output": 200}
    assert data["started_at"] == "2026-01-01T00:00:00+00:00"
    assert data["completed_at"] == "2026-01-01T00:01:00+00:00"


def test_get_node_detail_returns_pending_defaults(client_factory):
    """Node exists in graph_structure but has no state — defaults apply."""
    record = {
        "id": "exec-1",
        "user_id": "user-1",
        "graph_structure": {
            "nodes": [{"id": "node-1", "label": "Search"}],
            "edges": [],
        },
        "node_states": {},
    }

    client = client_factory(record)
    resp = client.get("/executions/exec-1/nodes/node-1")

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "node-1"
    assert data["label"] == "Search"
    assert data["status"] == "pending"
    assert data["input"] is None
    assert data["output"] is None


def test_get_node_detail_execution_not_found(client_factory):
    """Execution does not exist → 404."""
    client = client_factory(None)
    resp = client.get("/executions/nonexistent/nodes/node-1")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Execution not found"


def test_get_node_detail_node_not_found(client_factory):
    """Execution exists but node_id is in neither graph_structure nor execution_nodes."""
    record = {
        "id": "exec-1",
        "user_id": "user-1",
        "graph_structure": {
            "nodes": [{"id": "node-1", "label": "Search"}],
            "edges": [],
        },
        "node_states": {},
    }

    client = client_factory(record)
    resp = client.get("/executions/exec-1/nodes/node-999")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Node not found"


def test_get_node_detail_user_mismatch(client_factory):
    """Execution belongs to a different user → 404 (not found)."""
    record = {
        "id": "exec-1",
        "user_id": "other-user",
        "graph_structure": {"nodes": [], "edges": []},
        "node_states": {},
    }

    client = client_factory(record)
    resp = client.get("/executions/exec-1/nodes/node-1")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Execution not found"
