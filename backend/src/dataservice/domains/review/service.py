"""Review batch domain service."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.common.errors import DataServiceValidationError
from src.dataservice.domains.review.contracts import (
    ReviewBatchCreateCommand,
    ReviewBatchDetailProjection,
    ReviewBatchProjection,
    ReviewItemDecisionCommand,
    ReviewItemProjection,
    ReviewItemTransitionCommand,
)
from src.dataservice.domains.review.projection import (
    batch_to_projection,
    item_to_projection,
)
from src.dataservice.domains.review.registry import ReviewHandlerRegistry
from src.dataservice.domains.review.repository import ReviewRepository


class DataServiceReviewService:
    """DataService-owned review batch operations."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        autocommit: bool = True,
        handlers: ReviewHandlerRegistry | None = None,
    ) -> None:
        self.session = session
        self.autocommit = autocommit
        self.repository = ReviewRepository(session)
        self.handlers = handlers or ReviewHandlerRegistry()

    async def create_batch(
        self,
        command: ReviewBatchCreateCommand,
    ) -> ReviewBatchDetailProjection:
        batch = self.repository.create_batch(
            {
                "workspace_id": command.workspace_id,
                "execution_id": command.execution_id,
                "source_type": command.source_type,
                "source_id": command.source_id,
                "review_kind": command.review_kind,
                "status": "pending",
                "title": command.title,
                "summary": command.summary,
                "item_count": len(command.items),
                "payload_json": dict(command.payload_json or {}),
            }
        )
        items = [
            self.repository.create_item(
                {
                    "batch_id": batch.id,
                    "workspace_id": command.workspace_id,
                    "source_item_id": item.source_item_id,
                    "item_kind": item.item_kind,
                    "target_domain": item.target_domain,
                    "target_kind": item.target_kind,
                    "target_ref_json": dict(item.target_ref_json or {}),
                    "status": "pending",
                    "title": item.title,
                    "summary": item.summary,
                    "payload_json": dict(item.payload_json or {}),
                    "preview_json": dict(item.preview_json or {}),
                    "provenance_json": dict(item.provenance_json or {}),
                    "sort_order": item.sort_order,
                }
            )
            for item in command.items
        ]
        self._recompute_batch(batch, items)
        self.repository.append_action_log(
            {
                "batch_id": batch.id,
                "item_id": None,
                "workspace_id": batch.workspace_id,
                "action": "batch.created",
                "actor_id": None,
                "status_from": None,
                "status_to": batch.status,
                "payload_json": {"item_count": len(items)},
            }
        )
        await self._finish()
        return ReviewBatchDetailProjection(
            batch=batch_to_projection(batch),
            items=[item_to_projection(item) for item in items],
        )

    async def get_batch(self, batch_id: str) -> ReviewBatchDetailProjection | None:
        batch = await self.repository.get_batch(batch_id)
        if batch is None:
            return None
        items = await self.repository.list_items(batch_id)
        return ReviewBatchDetailProjection(
            batch=batch_to_projection(batch),
            items=[item_to_projection(item) for item in items],
        )

    async def list_batches(
        self,
        *,
        workspace_id: str | None = None,
        execution_id: str | None = None,
        status: list[str] | None = None,
        limit: int = 50,
    ) -> list[ReviewBatchProjection]:
        return [
            batch_to_projection(record)
            for record in await self.repository.list_batches(
                workspace_id=workspace_id,
                execution_id=execution_id,
                status=status,
                limit=limit,
            )
        ]

    async def set_item_decision(
        self,
        item_id: str,
        command: ReviewItemDecisionCommand,
    ) -> ReviewItemProjection | None:
        item = await self.repository.get_item(item_id)
        if item is None:
            return None
        self._ensure_item_status(item.status, {"pending", "accepted", "rejected"})
        before = item.status
        item.status = command.status
        item.updated_at = datetime.now(UTC)
        batch = await self._refresh_batch(item.batch_id)
        self.repository.append_action_log(
            {
                "batch_id": item.batch_id,
                "item_id": item.id,
                "workspace_id": item.workspace_id,
                "action": f"item.{command.status}",
                "actor_id": command.actor_id,
                "status_from": before,
                "status_to": item.status,
                "payload_json": dict(command.payload_json or {}),
            }
        )
        if batch is not None:
            batch.updated_at = datetime.now(UTC)
        await self._finish()
        return item_to_projection(item)

    async def apply_item(
        self,
        item_id: str,
        command: ReviewItemTransitionCommand,
    ) -> ReviewItemProjection | None:
        item = await self.repository.get_item(item_id)
        if item is None:
            return None
        if command.status == "applied":
            self._ensure_item_status(item.status, {"pending", "accepted"})
            handler = self.handlers.get(
                target_domain=item.target_domain,
                target_kind=item.target_kind,
            )
            handler_result = None
            if handler is not None:
                handler_result = await handler(item_to_projection(item))
            result_json = command.result_json or handler_result
        elif command.status == "reverted":
            self._ensure_item_status(item.status, {"applied"})
            result_json = command.result_json
        else:
            self._ensure_item_status(item.status, {"pending", "accepted", "applied"})
            result_json = command.result_json

        before = item.status
        item.status = command.status
        item.result_json = result_json
        item.error_text = command.error_text
        item.updated_at = datetime.now(UTC)
        if command.status == "applied":
            item.applied_at = item.updated_at

        batch = await self._refresh_batch(item.batch_id)
        self.repository.append_action_log(
            {
                "batch_id": item.batch_id,
                "item_id": item.id,
                "workspace_id": item.workspace_id,
                "action": f"item.{command.status}",
                "actor_id": command.actor_id,
                "status_from": before,
                "status_to": item.status,
                "payload_json": dict(command.payload_json or {}),
            }
        )
        if batch is not None:
            batch.updated_at = datetime.now(UTC)
        await self._finish()
        return item_to_projection(item)

    async def apply_many(
        self,
        item_ids: list[str],
        command: ReviewItemTransitionCommand,
    ) -> list[ReviewItemProjection]:
        """Apply multiple review items using the registered target handlers."""

        applied: list[ReviewItemProjection] = []
        for item_id in item_ids:
            item = await self.apply_item(item_id, command)
            if item is not None:
                applied.append(item)
        return applied

    async def _refresh_batch(self, batch_id: str):
        batch = await self.repository.get_batch(batch_id)
        if batch is None:
            return None
        items = await self.repository.list_items(batch_id)
        self._recompute_batch(batch, items)
        return batch

    @staticmethod
    def _recompute_batch(batch, items) -> None:
        item_count = len(items)
        accepted_count = sum(1 for item in items if item.status == "accepted")
        rejected_count = sum(1 for item in items if item.status == "rejected")
        applied_count = sum(1 for item in items if item.status == "applied")
        failed_count = sum(1 for item in items if item.status == "failed")
        reverted_count = sum(1 for item in items if item.status == "reverted")
        batch.item_count = item_count
        batch.accepted_count = accepted_count
        batch.rejected_count = rejected_count
        batch.applied_count = applied_count
        batch.failed_count = failed_count
        if item_count == 0:
            batch.status = "pending"
        elif failed_count == item_count:
            batch.status = "failed"
        elif applied_count == item_count or applied_count + reverted_count == item_count:
            batch.status = "applied"
        elif rejected_count == item_count:
            batch.status = "rejected"
        elif applied_count > 0 or failed_count > 0 or reverted_count > 0:
            batch.status = "partially_applied"
        else:
            batch.status = "pending"

    @staticmethod
    def _ensure_item_status(current: str, allowed: set[str]) -> None:
        if current not in allowed:
            raise DataServiceValidationError(
                f"Invalid review item transition from {current}",
                detail={"current_status": current, "allowed_status": sorted(allowed)},
            )

    async def _finish(self) -> None:
        if self.autocommit:
            await self.session.commit()
        else:
            await self.session.flush()
