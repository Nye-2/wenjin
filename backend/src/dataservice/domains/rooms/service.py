"""Workspace rooms domain service."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.domains.mission.write_authority import assert_active_mission_write
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
        await assert_active_mission_write(
            self.session,
            authority=command.mission_write_authority,
            workspace_id=command.workspace_id,
            mission_id=command.source_mission_id,
            mission_commit_id=command.source_mission_commit_id,
            required=command.source_mission_id is not None,
        )
        existing = await self._existing_decision_for_idempotent_source(command)
        if existing is not None:
            return decision_to_projection(existing)

        await self.repository.lock_workspace_for_update(command.workspace_id)
        existing = await self._existing_decision_for_idempotent_source(command)
        if existing is not None:
            await self._finish()
            return decision_to_projection(existing)

        old = await self.repository.get_active_decision(workspace_id=command.workspace_id, key=command.key)
        replacement_fence = datetime.now(UTC) if old is not None else None
        record = self.repository.create_decision(
            {
                "workspace_id": command.workspace_id,
                "key": command.key,
                "value": command.value,
                "confidence": command.confidence,
                "source_message_id": command.source_message_id,
                "extracted_by": command.extracted_by,
                "source_mission_id": command.source_mission_id,
                "source_mission_item_seq": command.source_mission_item_seq,
                "source_mission_commit_id": command.source_mission_commit_id,
                "deleted_at": replacement_fence,
            }
        )
        if old is not None:
            # Keep the replacement outside the active partial index until the
            # prior row points at an already-persisted successor.
            await self.session.flush()
            old.superseded_by = record.id
            await self.session.flush()
            record.deleted_at = None
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
        await assert_active_mission_write(
            self.session,
            authority=command.mission_write_authority,
            workspace_id=command.workspace_id,
            mission_id=command.source_mission_id,
            mission_commit_id=command.source_mission_commit_id,
            required=command.source_mission_id is not None,
        )
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
                "related_mission_ids": list(command.related_mission_ids or []),
                "created_by": command.created_by,
                "source_mission_id": command.source_mission_id,
                "source_mission_item_seq": command.source_mission_item_seq,
                "source_mission_commit_id": command.source_mission_commit_id,
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
        return [workspace_task_to_projection(record) for record in await self.repository.list_workspace_tasks(workspace_id=workspace_id, status=status)]

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
        for field in ("title", "description", "status", "priority", "related_mission_ids"):
            value = getattr(command, field)
            if value is not None:
                setattr(record, field, list(value) if field == "related_mission_ids" else value)
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

    async def _finish(self) -> None:
        if self.autocommit:
            await self.session.commit()
        else:
            await self.session.flush()

    async def _existing_decision_for_idempotent_source(
        self,
        command: DecisionSetCommand,
    ) -> Any | None:
        if command.source_mission_commit_id:
            existing = await self.repository.get_decision_by_mission_commit(
                workspace_id=command.workspace_id,
                source_mission_commit_id=command.source_mission_commit_id,
            )
            if existing is not None:
                return existing
        return None

    async def _existing_task_for_idempotent_source(
        self,
        command: WorkspaceTaskCreateCommand,
    ) -> Any | None:
        if command.source_mission_commit_id:
            existing = await self.repository.get_workspace_task_by_mission_commit(
                workspace_id=command.workspace_id,
                source_mission_commit_id=command.source_mission_commit_id,
            )
            if existing is not None:
                return existing
        return None
