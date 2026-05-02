"""Persistence helpers for execution session aggregate state."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.base import generate_uuid
from src.database.models.execution_session import ExecutionSessionRecord
from src.services.execution_session_events import publish_execution_session_event

_UNSET = object()


def _normalize_str_list(values: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        normalized.append(item)
        seen.add(item)
    return normalized


def _normalize_action_list(
    values: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for value in values or []:
        if isinstance(value, dict):
            normalized.append(dict(value))
    return normalized


class ExecutionSessionService:
    """CRUD and lifecycle helpers for execution sessions."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_session(
        self,
        *,
        user_id: str,
        workspace_id: str,
        workspace_type: str,
        feature_id: str,
        thread_id: str | None,
        entry_skill_id: str | None,
        launch_source: str,
        launch_message: str | None,
        params: dict[str, Any] | None,
        commit: bool = True,
    ) -> ExecutionSessionRecord:
        now = datetime.now(UTC)
        session = ExecutionSessionRecord(
            id=generate_uuid(),
            user_id=user_id,
            workspace_id=workspace_id,
            workspace_type=workspace_type,
            feature_id=feature_id,
            thread_id=thread_id,
            entry_skill_id=entry_skill_id,
            launch_source=launch_source,
            launch_message=launch_message,
            status="launching",
            params=dict(params or {}),
            task_ids=[],
            artifact_ids=[],
            next_actions=[],
            created_at=now,
            updated_at=now,
        )
        self.db.add(session)
        if commit:
            await self.db.commit()
            await self.db.refresh(session)
            await publish_execution_session_event(session, event_type="execution.created")
        else:
            await self.db.flush()
        return session

    async def get_by_id(self, session_id: str) -> ExecutionSessionRecord | None:
        result = await self.db.execute(
            select(ExecutionSessionRecord).where(ExecutionSessionRecord.id == session_id)
        )
        return result.scalar_one_or_none()

    async def list_workspace_sessions(
        self,
        *,
        workspace_id: str,
        user_id: str,
        limit: int = 20,
    ) -> list[ExecutionSessionRecord]:
        result = await self.db.execute(
            select(ExecutionSessionRecord)
            .where(
                ExecutionSessionRecord.workspace_id == workspace_id,
                ExecutionSessionRecord.user_id == user_id,
            )
            .order_by(ExecutionSessionRecord.updated_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def delete_session(self, session_id: str, *, commit: bool = True) -> None:
        session = await self.get_by_id(session_id)
        if session is None:
            return
        await self.db.delete(session)
        if commit:
            await self.db.commit()

    async def update_session_record(
        self,
        session: ExecutionSessionRecord,
        *,
        commit: bool = True,
        status: str | None = None,
        thread_id: str | None = None,
        entry_skill_id: str | None = None,
        params: dict[str, Any] | None = None,
        primary_task_id: str | None = None,
        append_task_id: str | None = None,
        runtime_snapshot: dict[str, Any] | None = None,
        result_summary: str | None = None,
        artifact_ids: list[str] | None = None,
        next_actions: list[dict[str, Any]] | None = None,
        advisory_code: str | None | object = _UNSET,
        last_error: str | None | object = _UNSET,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> ExecutionSessionRecord | None:
        changed = False
        if status is not None and session.status != status:
            session.status = status
            changed = True
        if thread_id is not None and session.thread_id != thread_id:
            session.thread_id = thread_id
            changed = True
        if entry_skill_id is not None and session.entry_skill_id != entry_skill_id:
            session.entry_skill_id = entry_skill_id
            changed = True
        if params is not None:
            normalized_params = dict(params)
            if session.params != normalized_params:
                session.params = normalized_params
                changed = True
        if primary_task_id is not None and session.primary_task_id != primary_task_id:
            session.primary_task_id = primary_task_id
            changed = True
        if append_task_id is not None:
            next_task_ids = _normalize_str_list([*list(session.task_ids or []), append_task_id])
            if next_task_ids != list(session.task_ids or []):
                session.task_ids = next_task_ids
                changed = True
        if runtime_snapshot is not None and session.runtime_snapshot != runtime_snapshot:
            session.runtime_snapshot = dict(runtime_snapshot)
            changed = True
        if result_summary is not None and session.result_summary != result_summary:
            session.result_summary = result_summary
            changed = True
        if artifact_ids is not None:
            next_artifact_ids = _normalize_str_list(artifact_ids)
            if next_artifact_ids != list(session.artifact_ids or []):
                session.artifact_ids = next_artifact_ids
                changed = True
        if next_actions is not None:
            normalized_actions = _normalize_action_list(next_actions)
            if normalized_actions != list(session.next_actions or []):
                session.next_actions = normalized_actions
                changed = True
        if advisory_code is not _UNSET:
            normalized_advisory_code = (
                advisory_code
                if advisory_code is None or isinstance(advisory_code, str)
                else str(advisory_code)
            )
            if session.advisory_code != normalized_advisory_code:
                session.advisory_code = normalized_advisory_code
                changed = True
        if last_error is not _UNSET:
            normalized_last_error = (
                last_error
                if last_error is None or isinstance(last_error, str)
                else str(last_error)
            )
            if session.last_error != normalized_last_error:
                session.last_error = normalized_last_error
                changed = True
        if started_at is not None and session.started_at != started_at:
            session.started_at = started_at
            changed = True
        if completed_at is not None and session.completed_at != completed_at:
            session.completed_at = completed_at
            changed = True

        if not changed:
            return session

        session.updated_at = datetime.now(UTC)

        if commit:
            await self.db.commit()
            await self.db.refresh(session)
            event_type = "execution.updated"
            if session.status == "completed":
                event_type = "execution.completed"
            elif session.status in {"failed", "advisory"}:
                event_type = "execution.failed"
            await publish_execution_session_event(session, event_type=event_type)

            # Execution session is the SSOT for feature business state.
            # ComputeSession is a UI projection; when execution changes we
            # touch the compute session so the Compute Stage refreshes.
            # Deferred import to avoid circular dependency between
            # execution_session_service -> compute -> projection_service -> runtime_profiles -> registry.
            from src.compute.session_service import ComputeSessionService

            await ComputeSessionService(self.db).touch_session_by_execution(
                execution_session_id=session.id,
            )
        return session

    async def update_session(
        self,
        session_id: str,
        *,
        commit: bool = True,
        **updates: Any,
    ) -> ExecutionSessionRecord | None:
        session = await self.get_by_id(session_id)
        if session is None:
            return None
        return await self.update_session_record(session, commit=commit, **updates)
