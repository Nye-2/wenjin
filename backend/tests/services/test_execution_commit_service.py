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
    """Build a service with DataService-backed commit dependencies mocked."""
    execution_svc = MagicMock()
    execution_svc.get_by_id = AsyncMock(return_value=execution)

    dataservice = MagicMock()
    dataservice.create_source = AsyncMock(return_value=SimpleNamespace(id="lib-1"))
    dataservice.import_source = AsyncMock(
        return_value=SimpleNamespace(
            source=SimpleNamespace(id="lib-1"),
            created=True,
            external_ids=[],
        )
    )
    dataservice.register_asset = AsyncMock(return_value=SimpleNamespace(id="doc-1"))
    dataservice.stage_and_apply_room_candidates = AsyncMock(
        return_value=SimpleNamespace(
            review_batch_id="review-batch-1",
            counts={"memory": 1, "decisions": 1, "tasks": 1},
            item_results=[
                {"room": "memory", "record_id": "fact-1", "source_item_id": "out-mem"},
                {"room": "decisions", "record_id": "dec-1", "source_item_id": "out-dec"},
                {"room": "tasks", "record_id": "task-1", "source_item_id": "out-task"},
            ],
        )
    )
    dataservice.append_execution_event = AsyncMock(return_value=SimpleNamespace(id="run-event-1"))

    svc = ExecutionCommitService(
        execution_service=execution_svc,
        dataservice=dataservice,
        redis=redis,
        referral_first_task_callback=AsyncMock(),
    )

    mocks = {
        "execution": execution_svc,
        "dataservice": dataservice,
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
    """accept_all=True writes all rooms through DataService-backed commit paths."""
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

    mocks["dataservice"].import_source.assert_called_once()
    mocks["dataservice"].create_source.assert_not_called()
    mocks["dataservice"].register_asset.assert_called_once()
    mocks["dataservice"].stage_and_apply_room_candidates.assert_called_once()
    mocks["dataservice"].append_execution_event.assert_called_once()


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

    mocks["dataservice"].import_source.assert_called_once()
    mocks["dataservice"].create_source.assert_not_called()
    mocks["dataservice"].register_asset.assert_called_once()
    mocks["dataservice"].stage_and_apply_room_candidates.assert_not_called()
    # run_history must still be called
    mocks["dataservice"].append_execution_event.assert_called_once()


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

    assert result["room_targets"]["documents"] == [{"output_id": "out-doc", "item_id": "doc-1"}]
    assert result["room_targets"]["library"] == [{"output_id": "out-lib", "item_id": "lib-1"}]


@pytest.mark.asyncio
async def test_commit_returns_room_targets_for_room_candidates():
    """Memory/decision/task candidates return workspace room focus metadata."""
    outputs = _all_kinds_outputs()
    report = _make_report(outputs)
    execution = _make_execution(report)
    svc, mocks = _make_service(execution)

    result = await svc.commit_outputs(
        EXECUTION_ID,
        accepted_ids=["out-mem", "out-dec", "out-task"],
    )

    assert result["room_targets"]["memory"] == [{"output_id": "out-mem", "item_id": "fact-1"}]
    assert result["room_targets"]["decisions"] == [{"output_id": "out-dec", "item_id": "dec-1"}]
    assert result["room_targets"]["tasks"] == [{"output_id": "out-task", "item_id": "task-1"}]


@pytest.mark.asyncio
async def test_commit_empty_still_writes_run_history():
    """accept_all=False, accepted_ids=[] → no room writes, run_history.record called once."""
    outputs = _all_kinds_outputs()
    report = _make_report(outputs)
    execution = _make_execution(report)
    svc, mocks = _make_service(execution)

    result = await svc.commit_outputs(EXECUTION_ID, accept_all=False, accepted_ids=[])

    assert all(v == 0 for v in result["committed"].values())
    mocks["dataservice"].create_source.assert_not_called()
    mocks["dataservice"].import_source.assert_not_called()
    mocks["dataservice"].register_asset.assert_not_called()
    mocks["dataservice"].stage_and_apply_room_candidates.assert_not_called()
    mocks["dataservice"].append_execution_event.assert_called_once()


@pytest.mark.asyncio
async def test_commit_applies_output_overrides_before_room_writes():
    """Edited staged outputs are materialized with the override data."""
    outputs = [
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
                name="draft.md",
                doc_kind="draft",
                content="# Original",
            ),
        ),
    ]
    report = _make_report(outputs)
    execution = _make_execution(report)
    svc, mocks = _make_service(execution)

    await svc.commit_outputs(
        EXECUTION_ID,
        accept_all=True,
        output_overrides={
            "out-lib": {
                "data": {"title": "Edited Paper", "authors": ["Ada"], "year": 2026},
                "preview": "Edited Paper",
            },
            "out-doc": {
                "data": {"name": "edited.md", "doc_kind": "outline", "content": "# Edited"}
            },
        },
    )

    source_payload = mocks["dataservice"].import_source.call_args.args[0]
    assert source_payload.title == "Edited Paper"
    assert source_payload.authors_json == ["Ada"]
    assert source_payload.year == 2026

    asset_payload = mocks["dataservice"].register_asset.call_args.args[0]
    assert asset_payload.name == "edited.md"
    assert asset_payload.asset_kind == "outline"
    assert asset_payload.metadata_json["content"] == "# Edited"


@pytest.mark.asyncio
async def test_commit_library_item_imports_verified_external_source():
    """Execution-backed Library writes preserve external search provenance."""
    outputs = [
        LibraryItemOutput(
            id="out-lib",
            preview="A verified paper",
            kind="library_item",
            data=LibraryItemData(
                title="Federated Fine-Tuning of Large Language Models",
                authors=["Ada Lovelace", "Grace Hopper"],
                year=2025,
                doi="10.1145/example",
                url="https://www.semanticscholar.org/paper/ss-paper-1",
                abstract="Verified external metadata.",
                venue="ICML",
                citation_count=42,
                source="semantic_scholar",
                external_id="ss-paper-1",
                metadata={"paperId": "ss-paper-1", "source": "semantic_scholar"},
            ),
        )
    ]
    report = _make_report(outputs)
    execution = _make_execution(report)
    svc, mocks = _make_service(execution)

    await svc.commit_outputs(EXECUTION_ID, accept_all=True)

    payload = mocks["dataservice"].import_source.call_args.args[0]
    assert payload.ingest_kind == "semantic_scholar"
    assert payload.evidence_level == "external_verified"
    assert payload.verified_at is not None
    assert payload.venue == "ICML"
    assert payload.citation_count == 42
    assert payload.external_ids[0].provider == "semantic_scholar"
    assert payload.external_ids[0].external_id == "ss-paper-1"
    mocks["dataservice"].create_source.assert_not_called()


@pytest.mark.asyncio
async def test_commit_rejects_override_for_unaccepted_output():
    """Overrides may only target outputs selected for this commit."""
    outputs = _all_kinds_outputs()
    report = _make_report(outputs)
    execution = _make_execution(report)
    svc, _mocks = _make_service(execution)

    with pytest.raises(ValueError, match="unaccepted output id"):
        await svc.commit_outputs(
            EXECUTION_ID,
            accepted_ids=["out-lib"],
            output_overrides={"out-doc": {"data": {"name": "edited.md"}}},
        )


@pytest.mark.asyncio
async def test_commit_rejects_unknown_override_output_id():
    """Unknown output ids in output_overrides fail fast."""
    outputs = _all_kinds_outputs()
    report = _make_report(outputs)
    execution = _make_execution(report)
    svc, _mocks = _make_service(execution)

    with pytest.raises(ValueError, match="unknown output id"):
        await svc.commit_outputs(
            EXECUTION_ID,
            accept_all=True,
            output_overrides={"missing": {"data": {"title": "Nope"}}},
        )


@pytest.mark.asyncio
async def test_commit_rejects_unsupported_override_fields():
    """Only the first-version editable fields can be overridden."""
    outputs = _all_kinds_outputs()
    report = _make_report(outputs)
    execution = _make_execution(report)
    svc, _mocks = _make_service(execution)

    with pytest.raises(ValueError, match="unsupported field"):
        await svc.commit_outputs(
            EXECUTION_ID,
            accept_all=True,
            output_overrides={"out-lib": {"data": {"library_status": "excluded"}}},
        )


@pytest.mark.asyncio
async def test_commit_rejects_unknown_accepted_id():
    """accepted_ids must refer to real staged outputs."""
    outputs = _all_kinds_outputs()
    report = _make_report(outputs)
    execution = _make_execution(report)
    svc, _mocks = _make_service(execution)

    with pytest.raises(ValueError, match="accepted_ids contains unknown"):
        await svc.commit_outputs(EXECUTION_ID, accepted_ids=["missing"])


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
    assert mocks["dataservice"].append_execution_event.call_count == 1

    # Second call with same key — should return cached, no additional writes
    result2 = await svc.commit_outputs(
        EXECUTION_ID,
        accept_all=True,
        idempotency_key="key-abc",
    )
    # Run-history event should still only have been called once (second call short-circuits)
    assert mocks["dataservice"].append_execution_event.call_count == 1
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
                "documents",
                "library",
                "memory",
                "decisions",
                "tasks",
                "runs",
                "references",
                "prism",
            ]
        },
    )
