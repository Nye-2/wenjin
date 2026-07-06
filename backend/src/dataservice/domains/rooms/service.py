"""Workspace rooms domain service."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.common.errors import DataServiceValidationError
from src.dataservice.domains.rooms.contracts import (
    DecisionProjection,
    DecisionSetCommand,
    WorkspaceTaskCreateCommand,
    WorkspaceTaskProjection,
    WorkspaceTaskUpdateCommand,
)
from src.dataservice.domains.rooms.projection import (
    decision_to_projection,
    workspace_task_to_projection,
)
from src.dataservice.domains.rooms.repository import RoomsRepository


class RoomsDataDomainService:
    """DataService-owned room operations for decisions and tasks."""

    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self.session = session
        self.autocommit = autocommit
        self.repository = RoomsRepository(session)

    async def set_decision(self, command: DecisionSetCommand) -> DecisionProjection:
        existing = await self._existing_decision_for_idempotent_source(command)
        if existing is not None:
            return decision_to_projection(existing)

        old = await self.repository.get_active_decision(workspace_id=command.workspace_id, key=command.key)
        record = self.repository.create_decision(
            {
                "workspace_id": command.workspace_id,
                "key": command.key,
                "value": command.value,
                "confidence": command.confidence,
                "source_message_id": command.source_message_id,
                "extracted_by": command.extracted_by,
                "source_review_batch_id": command.source_review_batch_id,
                "source_review_item_id": command.source_review_item_id,
            }
        )
        if old is not None:
            old.superseded_by = record.id
        await self._finish()
        return decision_to_projection(record)

    async def list_active_decisions(self, workspace_id: str) -> list[DecisionProjection]:
        records = await self.repository.list_active_decisions(workspace_id)
        return [decision_to_projection(record) for record in records]

    async def delete_decision(self, decision_id: str) -> bool:
        record = await self.repository.get_decision_by_id(decision_id)
        if record is None:
            return False
        record.deleted_at = datetime.now(UTC)
        await self._finish()
        return True

    async def soft_delete_decision(self, *, workspace_id: str, decision_id: str) -> bool:
        record = await self.repository.get_decision(workspace_id=workspace_id, decision_id=decision_id)
        if record is None:
            return False
        record.deleted_at = datetime.now(UTC)
        await self._finish()
        return True

    async def create_workspace_task(self, command: WorkspaceTaskCreateCommand) -> WorkspaceTaskProjection:
        existing = await self._existing_task_for_idempotent_source(command)
        if existing is not None:
            return workspace_task_to_projection(existing)

        record = self.repository.create_workspace_task(
            {
                "workspace_id": command.workspace_id,
                "title": command.title,
                "description": command.description,
                "status": command.status,
                "priority": command.priority,
                "related_execution_ids": list(command.related_execution_ids or []),
                "created_by": command.created_by,
                "source_review_batch_id": command.source_review_batch_id,
                "source_review_item_id": command.source_review_item_id,
            }
        )
        if command.status == "done":
            record.completed_at = datetime.now(UTC)
        await self._finish()
        return workspace_task_to_projection(record)

    async def list_workspace_tasks(
        self,
        *,
        workspace_id: str,
        status: str | None = None,
    ) -> list[WorkspaceTaskProjection]:
        return [
            workspace_task_to_projection(record)
            for record in await self.repository.list_workspace_tasks(workspace_id=workspace_id, status=status)
        ]

    async def update_workspace_task(
        self,
        *,
        workspace_id: str,
        task_id: str,
        command: WorkspaceTaskUpdateCommand,
    ) -> WorkspaceTaskProjection | None:
        record = await self.repository.get_workspace_task(workspace_id=workspace_id, task_id=task_id)
        if record is None:
            return None
        for field in ("title", "description", "status", "priority", "related_execution_ids"):
            value = getattr(command, field)
            if value is not None:
                setattr(record, field, list(value) if field == "related_execution_ids" else value)
        if command.status == "done" and record.completed_at is None:
            record.completed_at = datetime.now(UTC)
        record.updated_at = datetime.now(UTC)
        await self._finish()
        return workspace_task_to_projection(record)

    async def soft_delete_workspace_task(self, *, workspace_id: str, task_id: str) -> bool:
        record = await self.repository.get_workspace_task(workspace_id=workspace_id, task_id=task_id)
        if record is None:
            return False
        record.deleted_at = datetime.now(UTC)
        await self._finish()
        return True

    async def apply_review_item(self, item: Any) -> dict[str, Any]:
        target_kind = str(item.target_kind)
        payload = dict(item.payload_json or {})
        if target_kind == "decision":
            decision = await self.set_decision(
                DecisionSetCommand(
                    workspace_id=item.workspace_id,
                    key=payload["key"],
                    value=payload["value"],
                    extracted_by=payload.get("extracted_by") or f"review:{item.id}",
                    confidence=payload.get("confidence", 1.0),
                    source_review_batch_id=item.batch_id,
                    source_review_item_id=item.id,
                )
            )
            return {"room": "decisions", "record_id": decision.id, "key": decision.key}
        if target_kind == "workspace_task":
            task = await self.create_workspace_task(
                WorkspaceTaskCreateCommand(
                    workspace_id=item.workspace_id,
                    title=payload["title"],
                    description=payload.get("description"),
                    priority=payload.get("priority", 0),
                    related_execution_ids=list(payload.get("related_execution_ids") or []),
                    created_by=payload.get("created_by") or f"review:{item.id}",
                    source_review_batch_id=item.batch_id,
                    source_review_item_id=item.id,
                )
            )
            return {"room": "tasks", "record_id": task.id}
        raise DataServiceValidationError(
            "Unsupported room review item target",
            detail={"target_kind": target_kind},
        )

    async def _finish(self) -> None:
        if self.autocommit:
            await self.session.commit()
        else:
            await self.session.flush()

    async def _existing_decision_for_idempotent_source(
        self,
        command: DecisionSetCommand,
    ) -> Any | None:
        if command.source_review_batch_id and command.source_review_item_id:
            existing = await self.repository.get_decision_by_review_source(
                workspace_id=command.workspace_id,
                source_review_batch_id=command.source_review_batch_id,
                source_review_item_id=command.source_review_item_id,
            )
            if existing is not None:
                return existing
        if _is_execution_unit_provenance(command.extracted_by):
            return await self.repository.get_decision_by_extracted_by(
                workspace_id=command.workspace_id,
                key=command.key,
                extracted_by=command.extracted_by,
            )
        return None

    async def _existing_task_for_idempotent_source(
        self,
        command: WorkspaceTaskCreateCommand,
    ) -> Any | None:
        if command.source_review_batch_id and command.source_review_item_id:
            existing = await self.repository.get_workspace_task_by_review_source(
                workspace_id=command.workspace_id,
                source_review_batch_id=command.source_review_batch_id,
                source_review_item_id=command.source_review_item_id,
            )
            if existing is not None:
                return existing
        if _is_execution_unit_provenance(command.created_by):
            return await self.repository.get_workspace_task_by_created_by(
                workspace_id=command.workspace_id,
                title=command.title,
                created_by=command.created_by,
            )
        return None


def _is_execution_unit_provenance(value: str) -> bool:
    return value.startswith("execution:") and ":unit:" in value
