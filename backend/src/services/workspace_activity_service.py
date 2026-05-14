"""Workspace activity aggregation service."""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import Artifact, SubagentTaskRecord, TaskRecord, Thread
from src.services.thread_billing import (
    combine_token_usage,
    extract_persisted_message_usage,
    extract_persisted_metadata_usage,
    summarize_persisted_messages_usage,
)
from src.services.workspace_activity_contracts import (
    build_subagent_activity_item,
    build_task_activity_item,
    build_thread_activity_item,
    humanize_activity_identifier,
    summarize_task_payload,
    truncate_activity_preview,
)
from src.services.workspace_skill_labels import (
    get_workspace_type,
)


class WorkspaceActivityService:
    """Aggregate workspace activity across tasks, threads, subagents, and artifacts."""

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
        workspace_type = await get_workspace_type(self.db, workspace_id)
        threads = await self._get_recent_threads(workspace_id, limit=per_source_limit)

        items = [
            *await self._get_task_activity(workspace_id, limit=per_source_limit),
            *self._build_thread_activity(threads, workspace_type=workspace_type),
            *await self._get_artifact_activity(
                workspace_id,
                workspace_type=workspace_type,
                limit=per_source_limit,
            ),
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
    ) -> list[Thread]:
        result = await self.db.execute(
            select(Thread)
            .where(Thread.workspace_id == workspace_id)
            .order_by(Thread.updated_at.desc())
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
        execution_ids = {
            str(record.execution_id).strip()
            for record in records
            if getattr(record, "execution_id", None)
            and str(record.execution_id).strip()
        }
        task_usage_by_execution, subagent_count_by_execution = (
            await self._load_subagent_usage_by_execution(execution_ids)
        )
        return [
            self._task_record_to_activity(
                record,
                workspace_id,
                token_usage=task_usage_by_execution.get(
                    str(record.execution_id).strip()
                )
                if getattr(record, "execution_id", None)
                else None,
                subagent_count=subagent_count_by_execution.get(
                    str(record.execution_id).strip(),
                )
                if getattr(record, "execution_id", None)
                else None,
            )
            for record in records
        ]

    async def _load_subagent_usage_by_execution(
        self,
        execution_ids: set[str],
    ) -> tuple[dict[str, dict[str, int]], dict[str, int]]:
        """Aggregate persisted subagent usage grouped by execution."""
        if not execution_ids:
            return {}, {}

        result = await self.db.execute(
            select(SubagentTaskRecord).where(
                SubagentTaskRecord.execution_id.in_(sorted(execution_ids))
            )
        )
        records = list(result.scalars().all())
        usage_buckets: dict[str, list[Any]] = {}
        subagent_count_by_execution: dict[str, int] = {}
        for record in records:
            execution_id = str(record.execution_id or "").strip()
            if not execution_id:
                continue
            subagent_count_by_execution[execution_id] = (
                subagent_count_by_execution.get(execution_id, 0) + 1
            )
            metadata = (
                record.task_metadata if isinstance(record.task_metadata, dict) else {}
            )
            usage = extract_persisted_metadata_usage(metadata)
            if usage is not None:
                usage_buckets.setdefault(execution_id, []).append(usage)

        usage_by_execution: dict[str, dict[str, int]] = {}
        for execution_id, usages in usage_buckets.items():
            combined = combine_token_usage(usages)
            if combined is not None:
                usage_by_execution[execution_id] = combined.as_dict()

        return usage_by_execution, subagent_count_by_execution

    def _task_record_to_activity(
        self,
        record: TaskRecord,
        workspace_id: str,
        *,
        token_usage: dict[str, int] | None = None,
        subagent_count: int | None = None,
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
            token_usage=token_usage,
            subagent_count=subagent_count,
            occurred_at=occurred_at,
            created_at=record.created_at,
            started_at=record.started_at,
            completed_at=record.completed_at,
        )

    def _task_payload_summary(self, payload: dict[str, Any]) -> str | None:
        return summarize_task_payload(payload)

    def _build_thread_activity(
        self,
        threads: Sequence[Thread],
        *,
        workspace_type: str | None,
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
            last_message_usage = extract_persisted_message_usage(last_message)
            thread_usage = summarize_persisted_messages_usage(messages)
            items.append(
                build_thread_activity_item(
                    thread_id=str(thread.id),
                    workspace_id=(
                        str(thread.workspace_id)
                        if thread.workspace_id is not None
                        else None
                    ),
                    title=thread.title,
                    skill=thread.skill,
                    skill_name=None,
                    message_count=len(messages),
                    last_message_preview=truncate_activity_preview(last_message_content),
                    last_message_role=last_message_role,
                    last_message_token_usage=(
                        last_message_usage.as_dict() if last_message_usage is not None else None
                    ),
                    thread_token_usage=(
                        thread_usage.as_dict() if thread_usage is not None else None
                    ),
                    occurred_at=thread.updated_at,
                )
            )
        return items

    async def _get_artifact_activity(
        self,
        workspace_id: str,
        *,
        workspace_type: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        result = await self.db.execute(
            select(Artifact)
            .where(Artifact.workspace_id == workspace_id)
            .order_by(Artifact.created_at.desc())
            .limit(limit)
        )
        artifacts = list(result.scalars().all())
        return [
            self._artifact_to_activity(artifact, workspace_type=workspace_type)
            for artifact in artifacts
        ]

    def _artifact_to_activity(
        self,
        artifact: Artifact,
        *,
        workspace_type: str | None,
    ) -> dict[str, Any]:
        artifact_type = getattr(artifact, "type", "artifact")
        created_by_skill = getattr(artifact, "created_by_skill", None)
        created_by_skill_name = None
        artifact_title = getattr(artifact, "title", None)
        return {
            "id": f"artifact:{artifact.id}",
            "kind": "artifact",
            "workspace_id": str(artifact.workspace_id),
            "occurred_at": artifact.created_at,
            "title": artifact_title or humanize_activity_identifier(artifact_type),
            "summary": truncate_activity_preview(created_by_skill_name or created_by_skill)
            if (created_by_skill_name or created_by_skill)
            else humanize_activity_identifier(artifact_type),
            "status": artifact.status,
            "thread_id": None,
            "task_id": None,
            "artifact_id": str(artifact.id),
            "feature_id": None,
            "skill": None,
            "skill_name": None,
            "created_by_skill": created_by_skill,
            "created_by_skill_name": created_by_skill_name,
            "subagent_type": None,
            "metadata": {
                "artifact_type": artifact_type,
                "created_by_skill": created_by_skill,
                "created_by_skill_name": created_by_skill_name,
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
        raw_metadata = getattr(record, "task_metadata", None)
        metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
        usage = extract_persisted_metadata_usage(metadata)
        model_name = metadata.get("model_name")
        return build_subagent_activity_item(
            workspace_id=record.workspace_id,
            task_id=str(record.id),
            thread_id=str(record.thread_id),
            status=record.status,
            subagent_type=record.subagent_type,
            prompt=record.prompt,
            output_preview=record.output_preview,
            error=record.error,
            token_usage=usage.as_dict() if usage is not None else None,
            model_name=(
                str(model_name).strip()
                if isinstance(model_name, str) and model_name.strip()
                else None
            ),
            occurred_at=occurred_at,
            created_at=record.created_at,
            completed_at=record.completed_at,
        )
