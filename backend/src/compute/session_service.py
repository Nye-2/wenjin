"""DataService-backed helpers for Compute session shell records."""

from __future__ import annotations

from typing import Any

from src.compute.events import publish_compute_session_event
from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.execution import (
    ComputeSessionEnsurePayload,
    ComputeSessionPayload,
    ComputeSessionUpdatePayload,
)
from src.dataservice_client.provider import dataservice_client


class ComputeSessionService:
    """Facade for the rebuildable compute work-plane shell."""

    def __init__(
        self,
        *,
        dataservice: AsyncDataServiceClient | None = None,
    ) -> None:
        self._dataservice = dataservice

    async def ensure_for_execution(
        self,
        *,
        execution_id: str,
        workspace_id: str,
        user_id: str,
        sandbox_session_id: str | None = None,
    ) -> ComputeSessionPayload:
        """Return the compute session bound to an execution, creating it if needed."""

        existing = await self.get_by_execution_id(execution_id)
        command = ComputeSessionEnsurePayload(
            execution_id=execution_id,
            workspace_id=workspace_id,
            user_id=user_id,
            sandbox_session_id=sandbox_session_id,
        )
        if self._dataservice is not None:
            session, changed = await self._dataservice.ensure_compute_session(command)
        else:
            async with dataservice_client() as client:
                session, changed = await client.ensure_compute_session(command)
        if changed:
            event_type = "compute.updated" if existing is not None else "compute.created"
            await publish_compute_session_event(session, event_type=event_type)
        return session

    async def get_by_id(self, compute_session_id: str) -> ComputeSessionPayload | None:
        if self._dataservice is not None:
            return await self._dataservice.get_compute_session(compute_session_id)
        async with dataservice_client() as client:
            return await client.get_compute_session(compute_session_id)

    async def get_by_execution_id(
        self,
        execution_id: str,
    ) -> ComputeSessionPayload | None:
        if self._dataservice is not None:
            return await self._dataservice.get_compute_session_by_execution(execution_id)
        async with dataservice_client() as client:
            return await client.get_compute_session_by_execution(execution_id)

    async def list_workspace_sessions(
        self,
        *,
        workspace_id: str,
        user_id: str,
        limit: int = 20,
    ) -> list[ComputeSessionPayload]:
        if self._dataservice is not None:
            return await self._dataservice.list_compute_sessions(
                workspace_id=workspace_id,
                user_id=user_id,
                limit=limit,
            )
        async with dataservice_client() as client:
            return await client.list_compute_sessions(
                workspace_id=workspace_id,
                user_id=user_id,
                limit=limit,
            )

    async def touch_session(
        self,
        compute_session_id: str,
        *,
        ui_state_delta: dict[str, Any] | None = None,
    ) -> ComputeSessionPayload | None:
        """Bump updated_at and optionally merge ui_state_delta."""

        command = ComputeSessionUpdatePayload(ui_state_delta=ui_state_delta or {})
        if self._dataservice is not None:
            session = await self._dataservice.update_compute_session(compute_session_id, command)
        else:
            async with dataservice_client() as client:
                session = await client.update_compute_session(compute_session_id, command)
        if session is not None:
            await publish_compute_session_event(session, event_type="compute.updated")
        return session

    async def touch_session_by_execution(
        self,
        execution_id: str,
        *,
        ui_state_delta: dict[str, Any] | None = None,
    ) -> ComputeSessionPayload | None:
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
    ) -> ComputeSessionPayload | None:
        command = ComputeSessionUpdatePayload(active_view=active_view, ui_state=ui_state)
        if self._dataservice is not None:
            session = await self._dataservice.update_compute_session(compute_session_id, command)
        else:
            async with dataservice_client() as client:
                session = await client.update_compute_session(compute_session_id, command)
        if session is not None:
            await publish_compute_session_event(session, event_type="compute.updated")
        return session
