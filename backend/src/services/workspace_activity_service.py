"""Workspace activity aggregation service."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import Artifact, ChatThread, TaskRecord


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
            *await self._get_subagent_activity(
                workspace_id,
                [thread.id for thread in threads],
                user_id=user_id,
                limit=per_source_limit,
            ),
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
            .where(TaskRecord.payload["workspace_id"].as_string() == workspace_id)
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
        feature_id = payload.get("feature_id") if isinstance(payload, dict) else None
        title_id = str(feature_id or record.task_type or "task")
        occurred_at = record.completed_at or record.started_at or record.created_at

        summary = record.error or record.message or self._task_payload_summary(payload)

        return {
            "id": f"task:{record.id}",
            "kind": "feature_task",
            "workspace_id": workspace_id,
            "occurred_at": occurred_at,
            "title": self._humanize_identifier(title_id),
            "summary": summary,
            "status": record.status,
            "thread_id": str(payload.get("thread_id")) if payload.get("thread_id") else None,
            "task_id": str(record.id),
            "artifact_id": None,
            "feature_id": str(feature_id) if feature_id else None,
            "subagent_type": None,
            "metadata": {
                "task_type": record.task_type,
                "progress": record.progress,
                "action": (payload.get("params") or {}).get("action")
                if isinstance(payload.get("params"), dict)
                else None,
                "params": payload.get("params") if isinstance(payload.get("params"), dict) else None,
                "created_at": record.created_at.isoformat() if record.created_at else None,
                "started_at": record.started_at.isoformat() if record.started_at else None,
                "completed_at": record.completed_at.isoformat() if record.completed_at else None,
            },
        }

    def _task_payload_summary(self, payload: dict[str, Any]) -> str | None:
        """Extract a compact task summary from common payload shapes."""
        if not isinstance(payload, dict):
            return None

        params = payload.get("params")
        if isinstance(params, dict):
            for key in ("query", "topic", "paper_title", "title"):
                value = params.get(key)
                if isinstance(value, str) and value.strip():
                    return self._truncate_preview(value)

        for key in ("query", "topic", "message"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return self._truncate_preview(value)

        return None

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
                {
                    "id": f"chat:{thread.id}",
                    "kind": "chat_thread",
                    "workspace_id": str(thread.workspace_id),
                    "occurred_at": thread.updated_at,
                    "title": thread.title or "Chat session",
                    "summary": self._truncate_preview(last_message_content)
                    or f"{len(messages)} messages",
                    "status": None,
                    "thread_id": str(thread.id),
                    "task_id": None,
                    "artifact_id": None,
                    "feature_id": None,
                    "subagent_type": None,
                    "metadata": {
                        "skill": thread.skill,
                        "message_count": len(messages),
                        "last_message_role": last_message_role,
                    },
                }
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
            "title": artifact_title or self._humanize_identifier(artifact_type),
            "summary": self._truncate_preview(created_by_skill)
            if created_by_skill
            else self._humanize_identifier(artifact_type),
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
        thread_ids: Sequence[str],
        *,
        user_id: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        if not thread_ids:
            return []

        try:
            from src.subagents.manager import GlobalSubagentManager

            manager = GlobalSubagentManager.get_instance()
        except RuntimeError:
            return []

        items: list[dict[str, Any]] = []
        for thread_id in thread_ids:
            tasks = await manager.list_thread_tasks(thread_id, user_id=user_id, limit=limit)
            for task in tasks:
                created_at = task.get("created_at")
                if not isinstance(created_at, datetime):
                    continue

                subagent_type = task.get("subagent_type")
                summary = task.get("output_preview") or self._truncate_preview(task.get("prompt"))
                if task.get("error"):
                    summary = self._truncate_preview(task["error"])

                items.append(
                    {
                        "id": f"subagent:{task['task_id']}",
                        "kind": "subagent_task",
                        "workspace_id": workspace_id,
                        "occurred_at": created_at,
                        "title": self._humanize_identifier(subagent_type or "subagent"),
                        "summary": summary,
                        "status": task.get("status"),
                        "thread_id": task.get("thread_id"),
                        "task_id": task.get("task_id"),
                        "artifact_id": None,
                        "feature_id": None,
                        "subagent_type": subagent_type,
                        "metadata": {
                            "prompt": task.get("prompt"),
                        },
                    }
                )
        return items

    @staticmethod
    def _truncate_preview(content: str | None, limit: int = 120) -> str | None:
        """Collapse multi-line text into a short single-line preview."""
        normalized = " ".join((content or "").split())
        if not normalized:
            return None
        if len(normalized) <= limit:
            return normalized
        return normalized[: limit - 3].rstrip() + "..."

    @staticmethod
    def _humanize_identifier(identifier: str) -> str:
        """Convert machine-style identifiers into readable labels."""
        normalized = (identifier or "").strip().replace("-", " ").replace("_", " ")
        return normalized.title() if normalized else "Activity"
