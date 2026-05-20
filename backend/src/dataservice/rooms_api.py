"""Public in-process rooms API for DataService."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.domains.review.contracts import ReviewBatchCreateCommand, ReviewItemCreateCommand
from src.dataservice.domains.review.registry import ReviewHandlerRegistry
from src.dataservice.domains.review.service import DataServiceReviewService
from src.dataservice.domains.rooms.contracts import (
    DecisionProjection,
    DecisionSetCommand,
    MemoryFactCreateCommand,
    MemoryFactProjection,
    RoomCandidateApplyResult,
    RoomCandidateCommand,
    WorkspaceTaskCreateCommand,
    WorkspaceTaskProjection,
    WorkspaceTaskUpdateCommand,
)
from src.dataservice.domains.rooms.review_handler import build_room_review_handler
from src.dataservice.domains.rooms.service import RoomsDataDomainService


class RoomsDataService:
    """Rooms API exposed by DataService to runtime modules."""

    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self.session = session
        self.autocommit = autocommit
        self._domain = RoomsDataDomainService(session, autocommit=autocommit)

    async def set_decision(self, command: DecisionSetCommand) -> DecisionProjection:
        return await self._domain.set_decision(command)

    async def list_active_decisions(self, workspace_id: str) -> dict[str, str]:
        return await self._domain.list_active_decisions(workspace_id)

    async def delete_decision(self, decision_id: str) -> bool:
        return await self._domain.delete_decision(decision_id)

    async def add_memory_facts(
        self,
        commands: list[MemoryFactCreateCommand],
    ) -> list[MemoryFactProjection]:
        return await self._domain.add_memory_facts(commands)

    async def list_memory_facts(
        self,
        *,
        workspace_id: str,
        limit: int = 15,
        category: str | None = None,
    ) -> list[MemoryFactProjection]:
        return await self._domain.list_memory_facts(
            workspace_id=workspace_id,
            limit=limit,
            category=category,
        )

    async def mark_memory_fact_referenced(self, fact_id: str) -> MemoryFactProjection | None:
        return await self._domain.mark_memory_fact_referenced(fact_id)

    async def evict_excess_memory_facts(self, workspace_id: str, max_count: int = 100) -> int:
        return await self._domain.evict_excess_memory_facts(workspace_id, max_count=max_count)

    async def soft_delete_memory_fact(self, *, workspace_id: str, fact_id: str) -> bool:
        return await self._domain.soft_delete_memory_fact(workspace_id=workspace_id, fact_id=fact_id)

    async def create_workspace_task(self, command: WorkspaceTaskCreateCommand) -> WorkspaceTaskProjection:
        return await self._domain.create_workspace_task(command)

    async def list_workspace_tasks(
        self,
        *,
        workspace_id: str,
        status: str | None = None,
    ) -> list[WorkspaceTaskProjection]:
        return await self._domain.list_workspace_tasks(workspace_id=workspace_id, status=status)

    async def update_workspace_task(
        self,
        *,
        workspace_id: str,
        task_id: str,
        command: WorkspaceTaskUpdateCommand,
    ) -> WorkspaceTaskProjection | None:
        return await self._domain.update_workspace_task(
            workspace_id=workspace_id,
            task_id=task_id,
            command=command,
        )

    async def soft_delete_workspace_task(self, *, workspace_id: str, task_id: str) -> bool:
        return await self._domain.soft_delete_workspace_task(workspace_id=workspace_id, task_id=task_id)

    async def stage_and_apply_candidates(
        self,
        *,
        workspace_id: str,
        execution_id: str,
        candidates: list[RoomCandidateCommand],
        actor_id: str | None = None,
    ) -> RoomCandidateApplyResult:
        if not candidates:
            return RoomCandidateApplyResult(review_batch_id=None, counts=_empty_counts(), item_results=[])

        handler_domain = RoomsDataDomainService(self.session, autocommit=False)
        handlers = ReviewHandlerRegistry()
        handler = build_room_review_handler(handler_domain)
        for target_kind in ("decision", "memory_fact", "workspace_task"):
            handlers.register(target_domain="rooms", target_kind=target_kind, handler=handler)
        review_service = DataServiceReviewService(
            self.session,
            autocommit=self.autocommit,
            handlers=handlers,
        )
        detail = await review_service.create_batch(
            ReviewBatchCreateCommand(
                workspace_id=workspace_id,
                execution_id=execution_id,
                source_type="execution_commit",
                source_id=execution_id,
                review_kind="room_write",
                title="Apply accepted room outputs",
                summary=f"{len(candidates)} accepted room output(s)",
                items=[
                    ReviewItemCreateCommand(
                        source_item_id=candidate.source_item_id,
                        item_kind="room_write",
                        target_domain="rooms",
                        target_kind=candidate.target_kind,
                        title=candidate.title,
                        summary=candidate.summary,
                        payload_json=dict(candidate.payload_json or {}),
                        preview_json=dict(candidate.preview_json or {}),
                        provenance_json=dict(candidate.provenance_json or {}),
                        sort_order=index,
                    )
                    for index, candidate in enumerate(candidates)
                ],
            )
        )
        applied_items = await review_service.apply_many(
            [item.id for item in detail.items],
            command=_review_transition_command(actor_id=actor_id),
        )
        item_results: list[dict[str, Any]] = []
        counts = _empty_counts()
        for applied in applied_items:
            if applied is None or not applied.result_json:
                continue
            result = dict(applied.result_json)
            item_results.append({"review_item_id": applied.id, **result})
            room = result.get("room")
            if room in counts:
                counts[room] += 1
        return RoomCandidateApplyResult(
            review_batch_id=detail.batch.id,
            counts=counts,
            item_results=item_results,
        )


def _empty_counts() -> dict[str, int]:
    return {"memory": 0, "decisions": 0, "tasks": 0}


def _review_transition_command(*, actor_id: str | None) -> Any:
    from src.dataservice.domains.review.contracts import ReviewItemTransitionCommand

    return ReviewItemTransitionCommand(status="applied", actor_id=actor_id)
