"""DataService-backed helpers for Compute session shell records."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.compute.events import publish_compute_session_event
from src.dataservice.execution_api import ComputeSessionProjection, ExecutionDataService


class ComputeSessionService:
    """Facade for the rebuildable compute work-plane shell."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._executions = ExecutionDataService(db)

    async def ensure_for_execution(
        self,
        *,
        execution_id: str,
        workspace_id: str,
        user_id: str,
        sandbox_session_id: str | None = None,
    ) -> ComputeSessionProjection:
        """Return the compute session bound to an execution, creating it if needed."""

        existing = await self._executions.get_compute_session_by_execution(execution_id)
        session, changed = await self._executions.ensure_compute_session(
            execution_id=execution_id,
            workspace_id=workspace_id,
            user_id=user_id,
            sandbox_session_id=sandbox_session_id,
        )
        if changed:
            event_type = "compute.updated" if existing is not None else "compute.created"
            await publish_compute_session_event(session, event_type=event_type)
        return session

    async def get_by_id(self, compute_session_id: str) -> ComputeSessionProjection | None:
        return await self._executions.get_compute_session(compute_session_id)

    async def get_by_execution_id(
        self,
        execution_id: str,
    ) -> ComputeSessionProjection | None:
        return await self._executions.get_compute_session_by_execution(execution_id)

    async def list_workspace_sessions(
        self,
        *,
        workspace_id: str,
        user_id: str,
        limit: int = 20,
    ) -> list[ComputeSessionProjection]:
        return await self._executions.list_compute_sessions(
            workspace_id=workspace_id,
            user_id=user_id,
            limit=limit,
        )

    async def touch_session(
        self,
        compute_session_id: str,
        *,
        ui_state_delta: dict[str, Any] | None = None,
    ) -> ComputeSessionProjection | None:
        """Bump updated_at and optionally merge ui_state_delta."""

        session = await self._executions.update_compute_session(
            compute_session_id,
            ui_state_delta=ui_state_delta or {},
        )
        if session is not None:
            await publish_compute_session_event(session, event_type="compute.updated")
        return session

    async def touch_session_by_execution(
        self,
        execution_id: str,
        *,
        ui_state_delta: dict[str, Any] | None = None,
    ) -> ComputeSessionProjection | None:
        """Bump updated_at for the compute session bound to an execution."""

        session = await self.get_by_execution_id(execution_id)
        if session is None:
            return None
        return await self.touch_session(
            session.id,
            ui_state_delta=ui_state_delta,
        )

    async def update_ui_state(
        self,
        compute_session_id: str,
        *,
        active_view: str | None = None,
        ui_state: dict[str, Any] | None = None,
    ) -> ComputeSessionProjection | None:
        session = await self._executions.update_compute_session(
            compute_session_id,
            active_view=active_view,
            ui_state=ui_state,
        )
        if session is not None:
            await publish_compute_session_event(session, event_type="compute.updated")
        return session
