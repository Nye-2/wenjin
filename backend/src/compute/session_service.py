"""Persistence helpers for ComputeSession records."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.compute.events import publish_compute_session_event
from src.database.base import generate_uuid
from src.database.models.compute_session import ComputeSessionRecord


class ComputeSessionService:
    """CRUD helpers for the compute work-plane shell."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def ensure_for_execution(
        self,
        *,
        execution_id: str,
        workspace_id: str,
        user_id: str,
        sandbox_session_id: str | None = None,
    ) -> ComputeSessionRecord:
        """Return the compute session bound to an execution, creating it if needed."""
        existing = await self.get_by_execution_id(execution_id)
        if existing is not None:
            if sandbox_session_id and existing.sandbox_session_id != sandbox_session_id:
                existing.sandbox_session_id = sandbox_session_id
                existing.updated_at = datetime.now(UTC)
                await self.db.commit()
                await self.db.refresh(existing)
                await publish_compute_session_event(existing, event_type="compute.updated")
            return existing

        now = datetime.now(UTC)
        session = ComputeSessionRecord(
            id=generate_uuid(),
            execution_id=execution_id,
            workspace_id=workspace_id,
            user_id=user_id,
            sandbox_session_id=sandbox_session_id,
            active_view="overview",
            ui_state={},
            created_at=now,
            updated_at=now,
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        await publish_compute_session_event(session, event_type="compute.created")
        return session

    async def get_by_id(self, compute_session_id: str) -> ComputeSessionRecord | None:
        result = await self.db.execute(
            select(ComputeSessionRecord).where(ComputeSessionRecord.id == compute_session_id)
        )
        return result.scalar_one_or_none()

    async def get_by_execution_id(
        self,
        execution_id: str,
    ) -> ComputeSessionRecord | None:
        result = await self.db.execute(
            select(ComputeSessionRecord).where(
                ComputeSessionRecord.execution_id == execution_id
            )
        )
        return result.scalar_one_or_none()

    async def list_workspace_sessions(
        self,
        *,
        workspace_id: str,
        user_id: str,
        limit: int = 20,
    ) -> list[ComputeSessionRecord]:
        result = await self.db.execute(
            select(ComputeSessionRecord)
            .where(
                ComputeSessionRecord.workspace_id == workspace_id,
                ComputeSessionRecord.user_id == user_id,
            )
            .order_by(ComputeSessionRecord.updated_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def touch_session(
        self,
        compute_session_id: str,
        *,
        ui_state_delta: dict[str, Any] | None = None,
    ) -> ComputeSessionRecord | None:
        """Bump updated_at and optionally merge ui_state_delta.

        Used when the bound execution changes (task progress,
        runtime blocks, etc.) so that the Compute Stage projection is
        refreshed without mutating ComputeSession business state.
        """
        session = await self.get_by_id(compute_session_id)
        if session is None:
            return None

        session.updated_at = datetime.now(UTC)
        if ui_state_delta:
            current_ui = dict(session.ui_state or {})
            current_ui.update(ui_state_delta)
            session.ui_state = current_ui

        await self.db.commit()
        await self.db.refresh(session)
        await publish_compute_session_event(session, event_type="compute.updated")
        return session

    async def touch_session_by_execution(
        self,
        execution_id: str,
        *,
        ui_state_delta: dict[str, Any] | None = None,
    ) -> ComputeSessionRecord | None:
        """Bump updated_at for the compute session bound to an execution."""
        session = await self.get_by_execution_id(execution_id)
        # Defensive: in mock test environments db.execute returns AsyncMock,
        # so scalar_one_or_none() may yield a coroutine instead of a record.
        if session is None or not isinstance(session, ComputeSessionRecord):
            return None
        return await self.touch_session(
            str(session.id),
            ui_state_delta=ui_state_delta,
        )

    async def update_ui_state(
        self,
        compute_session_id: str,
        *,
        active_view: str | None = None,
        ui_state: dict[str, Any] | None = None,
    ) -> ComputeSessionRecord | None:
        session = await self.get_by_id(compute_session_id)
        if session is None:
            return None

        changed = False
        if active_view is not None and active_view != session.active_view:
            session.active_view = active_view
            changed = True
        if ui_state is not None and ui_state != dict(session.ui_state or {}):
            session.ui_state = dict(ui_state)
            changed = True
        if not changed:
            return session

        session.updated_at = datetime.now(UTC)
        await self.db.commit()
        await self.db.refresh(session)
        await publish_compute_session_event(session, event_type="compute.updated")
        return session
