"""Tests for ExecutionCommitService (Task 2.9)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.contracts.task_report import (
    DecisionData,
    DecisionOutput,
    DocumentData,
    DocumentOutput,
    LibraryItemData,
    LibraryItemOutput,
    MemoryFactData,
    MemoryFactOutput,
    TaskData,
    TaskOutput,
    TaskReport,
)
from src.services.execution_commit_service import ExecutionCommitService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

EXECUTION_ID = "exec-commit-1"
WORKSPACE_ID = "ws-commit-1"


def _make_report(outputs: list | None = None) -> TaskReport:
    return TaskReport(
        execution_id=EXECUTION_ID,
        capability_id="cap-1",
        status="completed",
        duration_seconds=10,
        narrative="Test narrative for commit",
        outputs=outputs or [],
    )


def _make_execution(report: TaskReport, workspace_id: str = WORKSPACE_ID) -> SimpleNamespace:
    return SimpleNamespace(
        id=EXECUTION_ID,
        workspace_id=workspace_id,
        user_id="user-1",
        feature_id="feat-1",
        result={"task_report": report.model_dump(mode="json")},
        status="completed",
    )


def _make_service(
    execution: SimpleNamespace | None = None,
    *,
    redis=None,
) -> tuple[ExecutionCommitService, dict[str, AsyncMock]]:
    """Build a service with all room services mocked."""
    execution_svc = MagicMock()
    execution_svc.get_by_id = AsyncMock(return_value=execution)

    library_svc = MagicMock()
    library_svc.add = AsyncMock(return_value=SimpleNamespace(id="lib-1"))

    documents_svc = MagicMock()
    documents_svc.add = AsyncMock(return_value=SimpleNamespace(id="doc-1"))

    decisions_svc = MagicMock()
    decisions_svc.set = AsyncMock(return_value=SimpleNamespace(id="dec-1"))

    memory_svc = MagicMock()
    memory_svc.add_facts = AsyncMock(return_value=[SimpleNamespace(id="fact-1")])

    tasks_svc = MagicMock()
    tasks_svc.add = AsyncMock(return_value=SimpleNamespace(id="task-1"))

    run_history_svc = MagicMock()
    run_history_svc.record = AsyncMock(return_value=SimpleNamespace(id="run-1"))

    event_bus = MagicMock()
    event_bus.publish = AsyncMock(return_value=1)

    svc = ExecutionCommitService(
        execution_service=execution_svc,
        library_service=library_svc,
        documents_service=documents_svc,
        decisions_service=decisions_svc,
        memory_service=memory_svc,
        workspace_tasks_service=tasks_svc,
        run_history_service=run_history_svc,
        redis=redis,
    )

    mocks = {
        "execution": execution_svc,
        "library": library_svc,
        "documents": documents_svc,
        "decisions": decisions_svc,
        "memory": memory_svc,
        "tasks": tasks_svc,
        "run_history": run_history_svc,
    }
    return svc, mocks


def _all_kinds_outputs() -> list:
    return [
        LibraryItemOutput(
            id="out-lib",
            preview="A paper",
            kind="library_item",
            data=LibraryItemData(title="Paper A", authors=["Author 1"], year=2024),
        ),
        DocumentOutput(
            id="out-doc",
            preview="A doc",
            kind="document",
            data=DocumentData(
                name="thesis.pdf",
                mime_type="application/pdf",
                storage_path="/storage/thesis.pdf",
                size_bytes=1024,
            ),
        ),
        MemoryFactOutput(
            id="out-mem",
            preview="A fact",
            kind="memory_fact",
            data=MemoryFactData(content="Key finding", category="research"),
        ),
        DecisionOutput(
            id="out-dec",
            preview="A decision",
            kind="decision",
            data=DecisionData(key="approach", value="qualitative"),
        ),
        TaskOutput(
            id="out-task",
            preview="A task",
            kind="task",
            data=TaskData(title="Write chapter 2"),
        ),
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_commit_all_writes_all_kinds():
    """accept_all=True → all 5 room services called once + run_history.record called."""
    outputs = _all_kinds_outputs()
    report = _make_report(outputs)
    execution = _make_execution(report)
    svc, mocks = _make_service(execution)

    result = await svc.commit_outputs(EXECUTION_ID, accept_all=True)

    assert result["committed"]["library"] == 1
    assert result["committed"]["documents"] == 1
    assert result["committed"]["memory"] == 1
    assert result["committed"]["decisions"] == 1
    assert result["committed"]["tasks"] == 1

    mocks["library"].add.assert_called_once()
    mocks["documents"].add.assert_called_once()
    mocks["memory"].add_facts.assert_called_once()
    mocks["decisions"].set.assert_called_once()
    mocks["tasks"].add.assert_called_once()
    mocks["run_history"].record.assert_called_once()


@pytest.mark.asyncio
async def test_commit_some_only():
    """accepted_ids=[out-lib, out-doc] → only those 2 written."""
    outputs = _all_kinds_outputs()
    report = _make_report(outputs)
    execution = _make_execution(report)
    svc, mocks = _make_service(execution)

    result = await svc.commit_outputs(
        EXECUTION_ID,
        accepted_ids=["out-lib", "out-doc"],
    )

    assert result["committed"]["library"] == 1
    assert result["committed"]["documents"] == 1
    assert result["committed"]["memory"] == 0
    assert result["committed"]["decisions"] == 0
    assert result["committed"]["tasks"] == 0

    mocks["library"].add.assert_called_once()
    mocks["documents"].add.assert_called_once()
    mocks["memory"].add_facts.assert_not_called()
    mocks["decisions"].set.assert_not_called()
    mocks["tasks"].add.assert_not_called()
    # run_history must still be called
    mocks["run_history"].record.assert_called_once()


@pytest.mark.asyncio
async def test_commit_returns_room_targets_for_committed_items():
    """Committed document/library outputs return room focus metadata."""
    outputs = _all_kinds_outputs()
    report = _make_report(outputs)
    execution = _make_execution(report)
    svc, mocks = _make_service(execution)

    result = await svc.commit_outputs(
        EXECUTION_ID,
        accepted_ids=["out-lib", "out-doc"],
    )

    assert result["room_targets"] == {
        "documents": [{"output_id": "out-doc", "item_id": "doc-1"}],
        "library": [{"output_id": "out-lib", "item_id": "lib-1"}],
    }


@pytest.mark.asyncio
async def test_commit_empty_still_writes_run_history():
    """accept_all=False, accepted_ids=[] → no room writes, run_history.record called once."""
    outputs = _all_kinds_outputs()
    report = _make_report(outputs)
    execution = _make_execution(report)
    svc, mocks = _make_service(execution)

    result = await svc.commit_outputs(EXECUTION_ID, accept_all=False, accepted_ids=[])

    assert all(v == 0 for v in result["committed"].values())
    mocks["library"].add.assert_not_called()
    mocks["documents"].add.assert_not_called()
    mocks["memory"].add_facts.assert_not_called()
    mocks["decisions"].set.assert_not_called()
    mocks["tasks"].add.assert_not_called()
    mocks["run_history"].record.assert_called_once()


@pytest.mark.asyncio
async def test_commit_idempotent_with_key():
    """Same idempotency_key → second call returns cached result, services called only once."""
    outputs = _all_kinds_outputs()
    report = _make_report(outputs)
    execution = _make_execution(report)

    # Set up a simple in-memory Redis mock
    store: dict[str, str] = {}

    redis_mock = MagicMock()

    async def mock_get(key: str) -> str | None:
        return store.get(key)

    async def mock_set(key: str, value: str, ex: int | None = None) -> None:
        store[key] = value

    redis_mock.get = mock_get
    redis_mock.set = mock_set

    svc, mocks = _make_service(execution, redis=redis_mock)

    # First call — should write everything
    result1 = await svc.commit_outputs(
        EXECUTION_ID,
        accept_all=True,
        idempotency_key="key-abc",
    )
    assert mocks["run_history"].record.call_count == 1

    # Second call with same key — should return cached, no additional writes
    result2 = await svc.commit_outputs(
        EXECUTION_ID,
        accept_all=True,
        idempotency_key="key-abc",
    )
    # run_history should still only have been called once (second call short-circuits)
    assert mocks["run_history"].record.call_count == 1
    assert result1 == result2


@pytest.mark.asyncio
async def test_commit_raises_on_missing_execution():
    """execution_service.get_by_id returns None → ValueError raised."""
    svc, mocks = _make_service(execution=None)

    with pytest.raises(ValueError, match="not found"):
        await svc.commit_outputs(EXECUTION_ID, accept_all=True)


@pytest.mark.asyncio
async def test_commit_raises_on_no_task_report():
    """Execution exists but has no task_report in result → ValueError."""
    execution = SimpleNamespace(
        id=EXECUTION_ID,
        workspace_id=WORKSPACE_ID,
        user_id="user-1",
        feature_id=None,
        result={"something_else": {}},
        status="completed",
    )
    svc, mocks = _make_service(execution)

    with pytest.raises(ValueError, match="no task_report"):
        await svc.commit_outputs(EXECUTION_ID, accept_all=True)


@pytest.mark.asyncio
async def test_commit_publishes_refresh_event():
    """After successful commit, canonical workspace.refresh is published."""
    report = _make_report([])
    execution = _make_execution(report)
    svc, mocks = _make_service(execution)

    with patch("src.services.execution_commit_service.publish_workspace_event", new=AsyncMock()) as publish_refresh:
        await svc.commit_outputs(EXECUTION_ID, accept_all=True)

    publish_refresh.assert_awaited_once_with(
        WORKSPACE_ID,
        "workspace.refresh",
        {
            "refresh_targets": [
                "activity",
                "artifacts",
                "dashboard",
                "references",
            ]
        },
    )
