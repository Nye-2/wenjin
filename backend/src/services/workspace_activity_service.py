"""Workspace activity aggregation service."""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import Artifact, ChatThread, SubagentTaskRecord, TaskRecord
from src.services.workspace_activity_contracts import (
    build_chat_activity_item,
    build_subagent_activity_item,
    build_task_activity_item,
    humanize_activity_identifier,
    summarize_task_payload,
    truncate_activity_preview,
)


class WorkspaceActivityService:
    """Aggregate workspace activity across tasks, chat, subagents, and artifacts."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_activity(
        self,
        workspace_id: str,
        *,
        user_id: str | None = None,
        limit: int = 40,
    ) -> dict[str, Any]:
        """Build a unified recent activity feed for a workspace."""
        per_source_limit = max(limit, 20)
        threads = await self._get_recent_threads(workspace_id, limit=per_source_limit)

        items = [
            *await self._get_task_activity(workspace_id, limit=per_source_limit),
            *self._build_chat_activity(threads),
            *await self._get_artifact_activity(workspace_id, limit=per_source_limit),
            *await self._get_subagent_activity(workspace_id, limit=per_source_limit),
        ]
        items.sort(key=lambda item: item["occurred_at"], reverse=True)
        trimmed = items[:limit]
        return {
            "items": trimmed,
            "count": len(trimmed),
        }

    async def _get_recent_threads(
        self,
        workspace_id: str,
        *,
        limit: int,
    ) -> list[ChatThread]:
        result = await self.db.execute(
            select(ChatThread)
            .where(ChatThread.workspace_id == workspace_id)
            .order_by(ChatThread.updated_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def _get_task_activity(
        self,
        workspace_id: str,
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        result = await self.db.execute(
            select(TaskRecord)
            .where(TaskRecord.workspace_id == workspace_id)
            .order_by(
                func.coalesce(
                    TaskRecord.completed_at,
                    TaskRecord.started_at,
                    TaskRecord.created_at,
                ).desc()
            )
            .limit(limit)
        )
        records = list(result.scalars().all())
        return [self._task_record_to_activity(record, workspace_id) for record in records]

    def _task_record_to_activity(
        self,
        record: TaskRecord,
        workspace_id: str,
    ) -> dict[str, Any]:
        payload = record.payload or {}
        occurred_at = record.completed_at or record.started_at or record.created_at
        return build_task_activity_item(
            task_id=str(record.id),
            workspace_id=workspace_id,
            task_type=record.task_type,
            payload=payload if isinstance(payload, dict) else None,
            status=record.status,
            progress=record.progress,
            message=record.message,
            error=record.error,
            result=record.result if isinstance(record.result, dict) else record.result,
            occurred_at=occurred_at,
            created_at=record.created_at,
            started_at=record.started_at,
            completed_at=record.completed_at,
        )

    def _task_payload_summary(self, payload: dict[str, Any]) -> str | None:
        return summarize_task_payload(payload)

    def _build_chat_activity(
        self,
        threads: Sequence[ChatThread],
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for thread in threads:
            messages = thread.messages or []
            last_message = messages[-1] if messages else {}
            last_message_content = (
                last_message.get("content") if isinstance(last_message, dict) else None
            )
            last_message_role = (
                last_message.get("role") if isinstance(last_message, dict) else None
            )
            items.append(
                build_chat_activity_item(
                    thread_id=str(thread.id),
                    workspace_id=(
                        str(thread.workspace_id)
                        if thread.workspace_id is not None
                        else None
                    ),
                    title=thread.title,
                    skill=thread.skill,
                    message_count=len(messages),
                    last_message_preview=truncate_activity_preview(last_message_content),
                    last_message_role=last_message_role,
                    occurred_at=thread.updated_at,
                )
            )
        return items

    async def _get_artifact_activity(
        self,
        workspace_id: str,
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        result = await self.db.execute(
            select(Artifact)
            .where(Artifact.workspace_id == workspace_id)
            .order_by(Artifact.created_at.desc())
            .limit(limit)
        )
        artifacts = list(result.scalars().all())
        return [self._artifact_to_activity(artifact) for artifact in artifacts]

    def _artifact_to_activity(self, artifact: Artifact) -> dict[str, Any]:
        artifact_type = getattr(artifact, "type", "artifact")
        created_by_skill = getattr(artifact, "created_by_skill", None)
        artifact_title = getattr(artifact, "title", None)
        return {
            "id": f"artifact:{artifact.id}",
            "kind": "artifact",
            "workspace_id": str(artifact.workspace_id),
            "occurred_at": artifact.created_at,
            "title": artifact_title or humanize_activity_identifier(artifact_type),
            "summary": truncate_activity_preview(created_by_skill)
            if created_by_skill
            else humanize_activity_identifier(artifact_type),
            "status": artifact.status,
            "thread_id": None,
            "task_id": None,
            "artifact_id": str(artifact.id),
            "feature_id": None,
            "subagent_type": None,
            "metadata": {
                "artifact_type": artifact_type,
                "created_by_skill": created_by_skill,
                "version": getattr(artifact, "version", None),
            },
        }

    async def _get_subagent_activity(
        self,
        workspace_id: str,
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        result = await self.db.execute(
            select(SubagentTaskRecord)
            .where(SubagentTaskRecord.workspace_id == workspace_id)
            .order_by(
                func.coalesce(
                    SubagentTaskRecord.completed_at,
                    SubagentTaskRecord.updated_at,
                    SubagentTaskRecord.created_at,
                ).desc()
            )
            .limit(limit)
        )
        records = list(result.scalars().all())
        return [self._subagent_record_to_activity(record) for record in records]

    def _subagent_record_to_activity(self, record: SubagentTaskRecord) -> dict[str, Any]:
        occurred_at = record.completed_at or record.updated_at or record.created_at
        return build_subagent_activity_item(
            workspace_id=record.workspace_id,
            task_id=str(record.id),
            thread_id=str(record.thread_id),
            status=record.status,
            subagent_type=record.subagent_type,
            prompt=record.prompt,
            output_preview=record.output_preview,
            error=record.error,
            occurred_at=occurred_at,
            created_at=record.created_at,
            completed_at=record.completed_at,
        )
