"""Public in-process review API for DataService."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.domains.review.contracts import (
    ReviewBatchCreateCommand,
    ReviewBatchDetailProjection,
    ReviewBatchProjection,
    ReviewItemDecisionCommand,
    ReviewItemDeleteCommand,
    ReviewItemPatchCommand,
    ReviewItemProjection,
    ReviewItemTransitionCommand,
)
from src.dataservice.domains.review.registry import ReviewApplyHandler, ReviewHandlerRegistry
from src.dataservice.domains.review.service import DataServiceReviewService


class ReviewDataService:
    """Review batch API exposed by DataService to runtime modules."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        autocommit: bool = True,
        handlers: ReviewHandlerRegistry | None = None,
    ) -> None:
        self._handlers = handlers or ReviewHandlerRegistry()
        self._domain = DataServiceReviewService(
            session,
            autocommit=autocommit,
            handlers=self._handlers,
        )

    def register_handler(
        self,
        *,
        target_domain: str,
        target_kind: str,
        handler: ReviewApplyHandler,
    ) -> None:
        self._handlers.register(
            target_domain=target_domain,
            target_kind=target_kind,
            handler=handler,
        )

    async def create_batch(self, command: ReviewBatchCreateCommand) -> ReviewBatchDetailProjection:
        return await self._domain.create_batch(command)

    async def create_batch_record(
        self,
        *,
        workspace_id: str,
        execution_id: str | None = None,
        source_type: str,
        source_id: str | None = None,
        review_kind: str,
        title: str,
        summary: str | None = None,
        payload_json: dict[str, Any] | None = None,
        items: list[dict[str, Any]] | None = None,
    ) -> ReviewBatchDetailProjection:
        return await self._domain.create_batch(
            ReviewBatchCreateCommand(
                workspace_id=workspace_id,
                execution_id=execution_id,
                source_type=source_type,
                source_id=source_id,
                review_kind=review_kind,
                title=title,
                summary=summary,
                payload_json=dict(payload_json or {}),
                items=list(items or []),
            )
        )

    async def get_batch(self, batch_id: str) -> ReviewBatchDetailProjection | None:
        return await self._domain.get_batch(batch_id)

    async def get_item(self, item_id: str) -> ReviewItemProjection | None:
        return await self._domain.get_item(item_id)

    async def list_batches(
        self,
        *,
        workspace_id: str | None = None,
        execution_id: str | None = None,
        status: list[str] | None = None,
        limit: int = 50,
    ) -> list[ReviewBatchProjection]:
        return await self._domain.list_batches(
            workspace_id=workspace_id,
            execution_id=execution_id,
            status=status,
            limit=limit,
        )

    async def list_items(
        self,
        *,
        workspace_id: str | None = None,
        execution_id: str | None = None,
        target_domain: str | None = None,
        target_kind: str | None = None,
        status: list[str] | None = None,
        limit: int = 50,
    ) -> list[ReviewItemProjection]:
        return await self._domain.list_items(
            workspace_id=workspace_id,
            execution_id=execution_id,
            target_domain=target_domain,
            target_kind=target_kind,
            status=status,
            limit=limit,
        )

    async def set_item_decision(
        self,
        item_id: str,
        command: ReviewItemDecisionCommand,
    ) -> ReviewItemProjection | None:
        return await self._domain.set_item_decision(item_id, command)

    async def patch_item(
        self,
        item_id: str,
        command: ReviewItemPatchCommand,
    ) -> ReviewItemProjection | None:
        return await self._domain.patch_item(item_id, command)

    async def decide_item(
        self,
        item_id: str,
        *,
        status: str,
        actor_id: str | None = None,
        payload_json: dict[str, Any] | None = None,
    ) -> ReviewItemProjection | None:
        return await self._domain.set_item_decision(
            item_id,
            ReviewItemDecisionCommand(
                status=status,
                actor_id=actor_id,
                payload_json=dict(payload_json or {}),
            ),
        )

    async def transition_item(
        self,
        item_id: str,
        command: ReviewItemTransitionCommand,
    ) -> ReviewItemProjection | None:
        return await self._domain.apply_item(item_id, command)

    async def delete_item(
        self,
        item_id: str,
        *,
        actor_id: str | None = None,
        reason: str | None = None,
        payload_json: dict[str, Any] | None = None,
    ) -> bool:
        return await self._domain.delete_item(
            item_id,
            ReviewItemDeleteCommand(
                actor_id=actor_id,
                reason=reason,
                payload_json=dict(payload_json or {}),
            ),
        )

    async def apply_item(
        self,
        item_id: str,
        *,
        actor_id: str | None = None,
        result_json: dict[str, Any] | None = None,
        payload_json: dict[str, Any] | None = None,
    ) -> ReviewItemProjection | None:
        return await self._domain.apply_item(
            item_id,
            ReviewItemTransitionCommand(
                status="applied",
                actor_id=actor_id,
                result_json=result_json,
                payload_json=dict(payload_json or {}),
            ),
        )

    async def apply_many(
        self,
        item_ids: list[str],
        *,
        actor_id: str | None = None,
        result_json: dict[str, Any] | None = None,
        payload_json: dict[str, Any] | None = None,
    ) -> list[ReviewItemProjection]:
        return await self._domain.apply_many(
            item_ids,
            ReviewItemTransitionCommand(
                status="applied",
                actor_id=actor_id,
                result_json=result_json,
                payload_json=dict(payload_json or {}),
            ),
        )
