"""DataService review batch domain tests."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from src.dataservice.common.errors import DataServiceValidationError
from src.dataservice.domains.review.contracts import (
    ReviewBatchCreateCommand,
    ReviewItemCreateCommand,
    ReviewItemDecisionCommand,
    ReviewItemDeleteCommand,
    ReviewItemPatchCommand,
    ReviewItemTransitionCommand,
)
from src.dataservice.domains.review.registry import ReviewHandlerRegistry
from src.dataservice.domains.review.service import DataServiceReviewService


class FakeSession:
    def __init__(self) -> None:
        self.commit_count = 0
        self.flush_count = 0

    async def commit(self) -> None:
        self.commit_count += 1

    async def flush(self) -> None:
        self.flush_count += 1


def _record(values: dict[str, Any]) -> SimpleNamespace:
    now = datetime.now(UTC)
    defaults = {
        "created_at": now,
        "updated_at": now,
    }
    defaults.update(values)
    return SimpleNamespace(**defaults)


class FakeReviewRepository:
    def __init__(self) -> None:
        self.batches: dict[str, SimpleNamespace] = {}
        self.items: dict[str, SimpleNamespace] = {}
        self.action_logs: list[SimpleNamespace] = []

    def create_batch(self, values: dict[str, Any]) -> SimpleNamespace:
        batch_id = f"batch-{len(self.batches) + 1}"
        record = _record(
            {
                "id": batch_id,
                "schema_version": "review_batch.v1",
                "accepted_count": 0,
                "rejected_count": 0,
                "applied_count": 0,
                "failed_count": 0,
                **values,
            }
        )
        self.batches[batch_id] = record
        return record

    def create_item(self, values: dict[str, Any]) -> SimpleNamespace:
        item_id = f"item-{len(self.items) + 1}"
        record = _record(
            {
                "id": item_id,
                "result_json": None,
                "error_text": None,
                "applied_at": None,
                **values,
            }
        )
        self.items[item_id] = record
        return record

    def append_action_log(self, values: dict[str, Any]) -> SimpleNamespace:
        record = _record({"id": f"log-{len(self.action_logs) + 1}", **values})
        self.action_logs.append(record)
        return record

    async def get_batch(self, batch_id: str) -> SimpleNamespace | None:
        return self.batches.get(batch_id)

    async def get_item(self, item_id: str) -> SimpleNamespace | None:
        return self.items.get(item_id)

    async def delete_item(self, item: SimpleNamespace) -> None:
        self.items.pop(item.id, None)

    async def list_items(self, batch_id: str) -> list[SimpleNamespace]:
        return sorted(
            [item for item in self.items.values() if item.batch_id == batch_id],
            key=lambda item: (item.sort_order, item.created_at),
        )

    async def list_batches(
        self,
        *,
        workspace_id: str | None = None,
        execution_id: str | None = None,
        status: list[str] | None = None,
        limit: int = 50,
    ) -> list[SimpleNamespace]:
        records = list(self.batches.values())
        if workspace_id is not None:
            records = [record for record in records if record.workspace_id == workspace_id]
        if execution_id is not None:
            records = [record for record in records if record.execution_id == execution_id]
        if status is not None:
            records = [record for record in records if record.status in status]
        return records[:limit]


def _service(
    handlers: ReviewHandlerRegistry | None = None,
) -> tuple[DataServiceReviewService, FakeReviewRepository, FakeSession]:
    session = FakeSession()
    service = DataServiceReviewService(
        session,  # type: ignore[arg-type]
        autocommit=True,
        handlers=handlers,
    )
    repository = FakeReviewRepository()
    service.repository = repository  # type: ignore[assignment]
    return service, repository, session


def _batch_command(*, item_count: int = 2) -> ReviewBatchCreateCommand:
    return ReviewBatchCreateCommand(
        workspace_id="ws-1",
        execution_id="exec-1",
        source_type="result_card",
        source_id="card-1",
        review_kind="result_card_commit",
        title="Review generated manuscript updates",
        summary="Two staged document writes",
        payload_json={"surface": "prism"},
        items=[
            ReviewItemCreateCommand(
                source_item_id=f"card-item-{index}",
                item_kind="document_patch",
                target_domain="documents",
                target_kind="paragraph",
                target_ref_json={"document_id": "doc-1", "index": index},
                title=f"Patch {index}",
                summary="Apply paragraph patch",
                payload_json={"text": f"paragraph {index}"},
                preview_json={"diff": f"+ paragraph {index}"},
                provenance_json={"execution_id": "exec-1"},
                sort_order=index,
            )
            for index in range(item_count)
        ],
    )


@pytest.mark.asyncio
async def test_create_batch_creates_pending_batch_items_and_action_log() -> None:
    service, repository, session = _service()

    detail = await service.create_batch(_batch_command(item_count=2))

    assert detail.batch.status == "pending"
    assert detail.batch.item_count == 2
    assert detail.batch.payload_json == {"surface": "prism"}
    assert [item.status for item in detail.items] == ["pending", "pending"]
    assert [item.sort_order for item in detail.items] == [0, 1]
    assert [log.action for log in repository.action_logs] == ["batch.created"]
    assert repository.action_logs[0].status_to == "pending"
    assert session.flush_count == 1
    assert session.commit_count == 1


@pytest.mark.asyncio
async def test_item_decisions_transition_counts_and_batch_status() -> None:
    service, repository, _ = _service()
    detail = await service.create_batch(_batch_command(item_count=1))
    item_id = detail.items[0].id

    accepted = await service.set_item_decision(
        item_id,
        ReviewItemDecisionCommand(status="accepted", actor_id="user-1"),
    )
    rejected = await service.set_item_decision(
        item_id,
        ReviewItemDecisionCommand(status="rejected", actor_id="user-1"),
    )
    pending = await service.set_item_decision(
        item_id,
        ReviewItemDecisionCommand(status="pending", actor_id="user-1"),
    )

    assert accepted is not None and accepted.status == "accepted"
    assert rejected is not None and rejected.status == "rejected"
    assert pending is not None and pending.status == "pending"
    assert repository.batches[detail.batch.id].status == "pending"
    assert repository.batches[detail.batch.id].accepted_count == 0
    assert repository.batches[detail.batch.id].rejected_count == 0
    assert [log.action for log in repository.action_logs] == [
        "batch.created",
        "item.accepted",
        "item.rejected",
        "item.pending",
    ]


@pytest.mark.asyncio
async def test_patch_and_delete_item_update_canonical_batch_state() -> None:
    service, repository, session = _service()
    detail = await service.create_batch(_batch_command(item_count=1))
    item_id = detail.items[0].id

    patched = await service.patch_item(
        item_id,
        ReviewItemPatchCommand(
            title="Updated patch",
            payload_json={"text": "updated paragraph"},
            preview_json={"diff": "+ updated paragraph"},
        ),
    )
    deleted = await service.delete_item(
        item_id,
        ReviewItemDeleteCommand(actor_id="user-1", reason="content_matched"),
    )

    assert patched is not None
    assert patched.title == "Updated patch"
    assert patched.payload_json == {"text": "updated paragraph"}
    assert deleted is True
    assert repository.items == {}
    assert repository.batches[detail.batch.id].item_count == 0
    assert [log.action for log in repository.action_logs] == [
        "batch.created",
        "item.patched",
        "item.deleted",
    ]
    assert repository.action_logs[-1].item_id is None
    assert repository.action_logs[-1].payload_json["deleted_item_id"] == item_id
    assert session.commit_count == 3


@pytest.mark.asyncio
async def test_apply_item_uses_registered_handler_and_marks_batch_applied() -> None:
    registry = ReviewHandlerRegistry()

    async def apply_paragraph(item) -> dict[str, Any]:
        return {"document_id": item.target_ref_json["document_id"], "applied": True}

    registry.register(
        target_domain="documents",
        target_kind="paragraph",
        handler=apply_paragraph,
    )
    service, repository, session = _service(registry)
    detail = await service.create_batch(_batch_command(item_count=2))
    first_id, second_id = [item.id for item in detail.items]

    await service.set_item_decision(first_id, ReviewItemDecisionCommand(status="accepted"))
    await service.set_item_decision(second_id, ReviewItemDecisionCommand(status="accepted"))
    first = await service.apply_item(
        first_id,
        ReviewItemTransitionCommand(status="applied", actor_id="user-1"),
    )
    second = await service.apply_item(
        second_id,
        ReviewItemTransitionCommand(status="applied", actor_id="user-1"),
    )

    assert first is not None and first.result_json == {"document_id": "doc-1", "applied": True}
    assert second is not None and second.status == "applied"
    assert repository.batches[detail.batch.id].status == "applied"
    assert repository.batches[detail.batch.id].applied_count == 2
    assert repository.action_logs[-1].action == "item.applied"
    assert session.commit_count == 5


@pytest.mark.asyncio
async def test_apply_many_uses_one_transaction_for_all_target_handlers() -> None:
    registry = ReviewHandlerRegistry()
    applied_targets: list[dict[str, Any]] = []

    async def apply_paragraph(item) -> dict[str, Any]:
        applied_targets.append(dict(item.target_ref_json))
        return {"document_id": item.target_ref_json["document_id"], "applied": True}

    registry.register(
        target_domain="documents",
        target_kind="paragraph",
        handler=apply_paragraph,
    )
    service, repository, session = _service(registry)
    detail = await service.create_batch(_batch_command(item_count=2))
    session.commit_count = 0

    applied = await service.apply_many(
        [item.id for item in detail.items],
        ReviewItemTransitionCommand(status="applied", actor_id="user-1"),
    )

    assert [item.status for item in applied] == ["applied", "applied"]
    assert applied_targets == [
        {"document_id": "doc-1", "index": 0},
        {"document_id": "doc-1", "index": 1},
    ]
    assert repository.batches[detail.batch.id].status == "applied"
    assert [log.action for log in repository.action_logs] == [
        "batch.created",
        "item.applied",
        "item.applied",
    ]
    assert session.commit_count == 1


@pytest.mark.asyncio
async def test_batch_statuses_cover_rejected_partially_applied_and_failed() -> None:
    service, repository, _ = _service()

    rejected_detail = await service.create_batch(_batch_command(item_count=1))
    rejected_item = rejected_detail.items[0].id
    await service.set_item_decision(rejected_item, ReviewItemDecisionCommand(status="rejected"))
    assert repository.batches[rejected_detail.batch.id].status == "rejected"

    partial_detail = await service.create_batch(_batch_command(item_count=2))
    await service.apply_item(
        partial_detail.items[0].id,
        ReviewItemTransitionCommand(status="applied", result_json={"ok": True}),
    )
    assert repository.batches[partial_detail.batch.id].status == "partially_applied"

    failed_detail = await service.create_batch(_batch_command(item_count=1))
    failed_item = failed_detail.items[0].id
    failed = await service.apply_item(
        failed_item,
        ReviewItemTransitionCommand(status="failed", error_text="target write failed"),
    )
    assert failed is not None and failed.status == "failed"
    assert repository.batches[failed_detail.batch.id].status == "failed"


@pytest.mark.asyncio
async def test_revert_and_invalid_item_transitions_are_enforced() -> None:
    service, repository, _ = _service()
    detail = await service.create_batch(_batch_command(item_count=1))
    item_id = detail.items[0].id

    applied = await service.apply_item(
        item_id,
        ReviewItemTransitionCommand(status="applied", result_json={"ok": True}),
    )
    reverted = await service.apply_item(
        item_id,
        ReviewItemTransitionCommand(status="reverted", payload_json={"reason": "undo"}),
    )

    assert applied is not None and applied.status == "applied"
    assert reverted is not None and reverted.status == "reverted"
    assert repository.batches[detail.batch.id].status == "applied"
    assert repository.action_logs[-1].action == "item.reverted"

    with pytest.raises(DataServiceValidationError):
        await service.set_item_decision(
            item_id,
            ReviewItemDecisionCommand(status="accepted"),
        )
