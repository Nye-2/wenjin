"""Workspace activity aggregation service."""

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.asset import WorkspaceAssetPayload
from src.dataservice_client.contracts.conversation import (
    ConversationMessagePayload,
    ConversationThreadPayload,
)
from src.dataservice_client.contracts.execution import ExecutionNodePayload, ExecutionPayload
from src.dataservice_client.contracts.review import ReviewItemPayload
from src.dataservice_client.provider import dataservice_client
from src.services.thread_billing import (
    combine_token_usage,
    extract_persisted_message_usage,
    extract_persisted_metadata_usage,
    normalize_token_usage,
    summarize_persisted_messages_usage,
)
from src.services.workspace_activity_contracts import (
    build_prism_review_activity_item,
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


def _artifact_metadata(artifact: WorkspaceAssetPayload | Any) -> dict[str, Any]:
    metadata = getattr(artifact, "metadata_json", None)
    return dict(metadata) if isinstance(metadata, dict) else {}


def _message_to_activity_dict(message: ConversationMessagePayload | dict[str, Any]) -> dict[str, Any]:
    if isinstance(message, dict):
        return message
    return {
        "role": message.role,
        "content": message.content,
        "metadata": dict(message.metadata_json or {}),
        "timestamp": message.timestamp,
    }


class WorkspaceActivityService:
    """Aggregate workspace activity across tasks, threads, subagents, and artifacts."""

    def __init__(
        self,
        db: AsyncSession | None = None,
        *,
        dataservice: AsyncDataServiceClient | None = None,
    ) -> None:
        self.db = db
        self._dataservice = dataservice

    @asynccontextmanager
    async def _client(self) -> AsyncIterator[AsyncDataServiceClient]:
        if self._dataservice is not None:
            yield self._dataservice
            return
        async with dataservice_client() as client:
            yield client

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
            *await self._get_prism_review_activity(
                workspace_id,
                limit=per_source_limit,
            ),
            *await self._build_thread_activity(threads, workspace_type=workspace_type),
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
    ) -> list[ConversationThreadPayload]:
        async with self._client() as client:
            return await client.list_workspace_conversation_thread_summaries(
                workspace_id=workspace_id,
                limit=limit,
            )

    async def _get_task_activity(
        self,
        workspace_id: str,
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        async with self._client() as client:
            records = await client.list_executions(workspace_id=workspace_id, limit=limit)
        execution_ids = {
            str(record.id).strip()
            for record in records
            if str(record.id or "").strip()
        }
        task_usage_by_execution, subagent_count_by_execution = (
            await self._load_subagent_usage_by_execution(execution_ids)
        )
        return [
            self._task_record_to_activity(
                record,
                workspace_id,
                token_usage=task_usage_by_execution.get(
                    str(record.id).strip()
                ),
                subagent_count=subagent_count_by_execution.get(
                    str(record.id).strip(),
                ),
            )
            for record in records
        ]

    async def _get_prism_review_activity(
        self,
        workspace_id: str,
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        async with self._client() as client:
            items = await client.list_review_items(
                workspace_id=workspace_id,
                target_domain="prism",
                limit=limit,
            )
        return [
            self._prism_review_record_to_activity(record)
            for record in items
        ]

    def _prism_review_record_to_activity(
        self,
        record: ReviewItemPayload,
    ) -> dict[str, Any]:
        occurred_at = record.applied_at or record.updated_at or record.created_at
        target_ref = dict(record.target_ref_json or {})
        payload = dict(record.payload_json or {})
        preview = dict(record.preview_json or {})
        provenance = dict(record.provenance_json or {})
        logical_key = (
            target_ref.get("logical_key")
            or payload.get("logical_key")
            or preview.get("logical_key")
            or record.source_item_id
            or record.id
        )
        target_file_path = (
            target_ref.get("file_path")
            or target_ref.get("path")
            or payload.get("path")
            or preview.get("path")
        )
        latex_project_id = (
            target_ref.get("latex_project_id")
            or target_ref.get("project_id")
            or payload.get("latex_project_id")
            or payload.get("project_id")
            or ""
        )
        return build_prism_review_activity_item(
            review_item_id=str(record.id),
            workspace_id=str(record.workspace_id),
            latex_project_id=str(latex_project_id),
            logical_key=str(logical_key),
            title=record.title,
            summary=record.summary,
            status=record.status,
            source_execution_id=provenance.get("execution_id") or payload.get("source_execution_id"),
            source_task_id=provenance.get("task_id") or payload.get("source_task_id"),
            target_kind=record.target_kind,
            target_file_path=str(target_file_path) if target_file_path else None,
            target_room=target_ref.get("room"),
            target_item_id=target_ref.get("item_id"),
            occurred_at=occurred_at,
            created_at=record.created_at,
            updated_at=record.updated_at,
            applied_at=record.applied_at,
        )

    async def _load_subagent_usage_by_execution(
        self,
        execution_ids: set[str],
    ) -> tuple[dict[str, dict[str, int]], dict[str, int]]:
        """Aggregate persisted subagent usage grouped by execution."""
        if not execution_ids:
            return {}, {}

        async with self._client() as client:
            records = await client.list_execution_nodes_by_execution_ids(
                sorted(execution_ids)
            )
        usage_buckets: dict[str, list[Any]] = {}
        subagent_count_by_execution: dict[str, int] = {}
        for record in records:
            execution_id = str(record.execution_id or "").strip()
            if not execution_id:
                continue
            subagent_count_by_execution[execution_id] = (
                subagent_count_by_execution.get(execution_id, 0) + 1
            )
            usage = self._node_token_usage(record)
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
        record: ExecutionPayload,
        workspace_id: str,
        *,
        token_usage: dict[str, int] | None = None,
        subagent_count: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "feature_id": record.capability_id,
            "thread_id": record.thread_id,
            "skill_id": record.entry_skill_id,
            "params": dict(record.task_brief_json or {}),
        }
        occurred_at = record.completed_at or record.started_at or record.created_at
        return build_task_activity_item(
            task_id=str(record.id),
            workspace_id=workspace_id,
            task_type=record.execution_type,
            payload=payload,
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

    async def _build_thread_activity(
        self,
        threads: Sequence[ConversationThreadPayload],
        *,
        workspace_type: str | None,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for thread in threads:
            async with self._client() as client:
                raw_messages = await client.list_conversation_messages(str(thread.id))
            messages = [_message_to_activity_dict(message) for message in raw_messages]
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
        async with self._client() as client:
            artifacts = await client.list_assets(
                workspace_id=workspace_id,
                include_deleted=False,
                limit=limit,
            )
        return [
            self._artifact_to_activity(artifact, workspace_type=workspace_type)
            for artifact in artifacts
        ]

    def _artifact_to_activity(
        self,
        artifact: Any,
        *,
        workspace_type: str | None,
    ) -> dict[str, Any]:
        metadata = _artifact_metadata(artifact)
        artifact_type = (
            metadata.get("artifact_type")
            or metadata.get("legacy_kind")
            or getattr(artifact, "asset_kind", None)
            or getattr(artifact, "type", "artifact")
        )
        created_by_skill = (
            metadata.get("created_by_skill")
            or metadata.get("skill_name")
            or getattr(artifact, "created_by_skill", None)
            or getattr(artifact, "created_by", None)
        )
        created_by_skill_name = None
        artifact_title = getattr(artifact, "title", None) or getattr(artifact, "name", None)
        status = metadata.get("status") or getattr(artifact, "status", None) or "available"
        return {
            "id": f"artifact:{artifact.id}",
            "kind": "artifact",
            "workspace_id": str(artifact.workspace_id),
            "occurred_at": artifact.created_at,
            "title": artifact_title or humanize_activity_identifier(artifact_type),
            "summary": truncate_activity_preview(created_by_skill_name or created_by_skill)
            if (created_by_skill_name or created_by_skill)
            else humanize_activity_identifier(artifact_type),
            "status": status,
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
                "asset_kind": getattr(artifact, "asset_kind", None),
                "source_kind": getattr(artifact, "source_kind", None),
                "source_id": getattr(artifact, "source_id", None),
                "created_by_skill": created_by_skill,
                "created_by_skill_name": created_by_skill_name,
                "version": metadata.get("version") or getattr(artifact, "version", None),
            },
        }

    async def _get_subagent_activity(
        self,
        workspace_id: str,
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        async with self._client() as client:
            executions = await client.list_executions(
                workspace_id=workspace_id,
                limit=max(limit, 20),
            )
        execution_by_id = {record.id: record for record in executions}
        async with self._client() as client:
            records = await client.list_execution_nodes_by_execution_ids(
                list(execution_by_id)
            )
        records.sort(
            key=lambda record: record.completed_at or record.updated_at or record.created_at,
            reverse=True,
        )
        return [
            self._subagent_record_to_activity(record, execution_by_id.get(record.execution_id))
            for record in records[:limit]
        ]

    def _subagent_record_to_activity(
        self,
        record: ExecutionNodePayload,
        execution: ExecutionPayload | None = None,
    ) -> dict[str, Any]:
        occurred_at = record.completed_at or record.updated_at or record.created_at
        raw_metadata = getattr(record, "node_metadata", None)
        metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
        usage = self._node_token_usage(record)
        output_data = record.output_data if isinstance(record.output_data, dict) else {}
        input_data = record.input_data if isinstance(record.input_data, dict) else {}
        model_name = metadata.get("model_name") or output_data.get("model_name")
        prompt = input_data.get("prompt") or input_data.get("input_prompt")
        output_preview = (
            output_data.get("output_preview")
            or output_data.get("summary")
            or output_data.get("message")
        )
        error = output_data.get("error")
        return build_subagent_activity_item(
            workspace_id=execution.workspace_id if execution else "",
            task_id=str(record.id),
            thread_id=str(execution.thread_id) if execution and execution.thread_id else None,
            status=record.status,
            subagent_type=record.node_type,
            prompt=str(prompt) if prompt is not None else None,
            output_preview=str(output_preview) if output_preview is not None else None,
            error=str(error) if error is not None else None,
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

    @staticmethod
    def _node_token_usage(record: ExecutionNodePayload) -> Any | None:
        usage = normalize_token_usage(record.token_usage)
        if usage is not None:
            return usage
        metadata = record.node_metadata if isinstance(record.node_metadata, dict) else {}
        usage = extract_persisted_metadata_usage(metadata)
        if usage is not None:
            return usage
        output_data = record.output_data if isinstance(record.output_data, dict) else {}
        return normalize_token_usage(output_data.get("token_usage"))
