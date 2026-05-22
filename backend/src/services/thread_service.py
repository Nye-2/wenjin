"""Service layer for persisted threads."""

import copy
import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.middlewares.thread_data import delete_thread_directory
from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.conversation import (
    ConversationMessageCreatePayload,
    ConversationMessagePayload,
    ConversationMessagesRebuildPayload,
    ConversationThreadCreatePayload,
    ConversationThreadPayload,
    ConversationThreadUpdatePayload,
)
from src.dataservice_client.provider import dataservice_client
from src.models.router import route_model, validate_requested_model
from src.services.workspace_skill_labels import (
    list_workspace_types,
)

logger = logging.getLogger(__name__)
_LAST_MESSAGE_PREVIEW_LIMIT = 120


def _truncate_message_preview(content: str | None, limit: int = _LAST_MESSAGE_PREVIEW_LIMIT) -> str | None:
    """Collapse message content into a short single-line preview."""
    normalized = " ".join((content or "").split())
    if not normalized:
        return None
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


class ThreadAccessError(LookupError):
    """Raised when a thread exists but is not owned by the active user."""


class ThreadService:
    """CRUD and mutation helpers for threads."""

    def __init__(
        self,
        db: AsyncSession,
        model: type[Any] | None = None,
        dataservice: AsyncDataServiceClient | None = None,
    ) -> None:
        self.db = db
        self._model = model
        self._dataservice = dataservice

    async def _with_client(self) -> AsyncDataServiceClient:
        if self._dataservice is None:
            raise RuntimeError("DataService client is only available inside helper contexts")
        return self._dataservice

    @staticmethod
    def _message_payload_to_bridge(message: ConversationMessagePayload) -> dict[str, Any]:
        result: dict[str, Any] = {
            "role": message.role,
            "content": message.content,
            "timestamp": message.timestamp.isoformat() if message.timestamp else None,
        }
        if message.metadata_json:
            result["metadata"] = dict(message.metadata_json)
        if message.blocks:
            result["blocks"] = [dict(block.payload_json) for block in message.blocks]
        return result

    async def _lock_thread_row(self, thread_id: str) -> None:
        """Lock and refresh a thread row to prevent lost summary updates."""
        if self._dataservice is not None:
            await self._dataservice.lock_conversation_thread(thread_id)
            return
        async with dataservice_client() as client:
            await client.lock_conversation_thread(thread_id)

    @staticmethod
    def _hydrate_thread_skill_metadata(
        thread: ConversationThreadPayload,
        *,
        workspace_type: str | None,
    ) -> ConversationThreadPayload:
        """Attach resolved workspace skill metadata to a thread object."""
        cast_thread: Any = thread
        cast_thread.workspace_type = workspace_type
        cast_thread.skill_name = None
        return thread

    async def _attach_workspace_skill_metadata(
        self,
        thread: ConversationThreadPayload | None,
        *,
        workspace_types: dict[str, str] | None = None,
    ) -> ConversationThreadPayload | None:
        """Attach resolved workspace skill metadata to a thread object."""
        if thread is None:
            return None
        workspace_id = str(thread.workspace_id).strip() if thread.workspace_id else None
        workspace_type = None
        if workspace_id and workspace_types is not None:
            workspace_type = workspace_types.get(workspace_id)
        if workspace_type is None and workspace_id:
            workspace_type = (await list_workspace_types(self.db, [workspace_id])).get(workspace_id)
        return self._hydrate_thread_skill_metadata(
            thread,
            workspace_type=workspace_type,
        )

    @staticmethod
    def _resolve_model(model: str | None) -> str:
        """Resolve model id through env-backed config without silent user fallback."""
        requested = validate_requested_model(
            model,
            allowed_categories=("llm"),
            require_tools=False,
        )
        resolved = route_model(
            requested_model=requested,
            preferred_categories=("llm",),
            allowed_categories=("llm",),
            require_tools=False,
        )
        return str(resolved)

    @classmethod
    def resolve_requested_model(cls, model: str | None) -> str | None:
        """Validate and resolve an optional requested model id."""
        if model is None or not model.strip():
            return None
        return cls._resolve_model(model)

    async def create_thread(
        self,
        *,
        user_id: str,
        workspace_id: str | None = None,
        title: str | None = None,
        model: str | None = None,
        skill: str | None = None,
    ) -> ConversationThreadPayload:
        """Create and persist a new thread."""
        now = datetime.now(UTC)
        command = ConversationThreadCreatePayload(
                user_id=user_id,
                workspace_id=workspace_id,
                title=title,
                model=self._resolve_model(model),
                skill=(skill or "").strip() or None,
                created_at=now,
                updated_at=now,
            )
        if self._dataservice is not None:
            thread = await self._dataservice.create_conversation_thread(command)
        else:
            async with dataservice_client() as client:
                thread = await client.create_conversation_thread(command)
        hydrated_thread = await self._attach_workspace_skill_metadata(thread)
        return hydrated_thread or thread

    async def get_by_id(self, thread_id: str) -> ConversationThreadPayload | None:
        """Fetch a thread regardless of owner."""
        if self._dataservice is not None:
            thread = await self._dataservice.get_conversation_thread(thread_id)
        else:
            async with dataservice_client() as client:
                thread = await client.get_conversation_thread(thread_id)
        return await self._attach_workspace_skill_metadata(
            thread,
        )

    async def get_thread(
        self,
        thread_id: str,
        user_id: str,
    ) -> ConversationThreadPayload | None:
        """Fetch a thread owned by the active user."""
        thread = await self.get_by_id(thread_id)
        if not thread or thread.user_id != user_id:
            return None
        return thread

    async def get_latest_workspace_thread(
        self,
        *,
        user_id: str,
        workspace_id: str,
    ) -> ConversationThreadPayload | None:
        """Fetch the most recently updated thread for a workspace owned by the user."""
        if self._dataservice is not None:
            thread = await self._dataservice.get_latest_workspace_conversation_thread(
                user_id=user_id,
                workspace_id=workspace_id,
            )
        else:
            async with dataservice_client() as client:
                thread = await client.get_latest_workspace_conversation_thread(
                    user_id=user_id,
                    workspace_id=workspace_id,
                )
        return await self._attach_workspace_skill_metadata(
            thread,
        )

    async def _persist_thread_fields(
        self,
        thread: ConversationThreadPayload,
        **fields: Any,
    ) -> ConversationThreadPayload:
        command = ConversationThreadUpdatePayload(**fields)
        if self._dataservice is not None:
            updated = await self._dataservice.update_conversation_thread(str(thread.id), command)
        else:
            async with dataservice_client() as client:
                updated = await client.update_conversation_thread(str(thread.id), command)
        if updated is None:
            return thread
        return await self._attach_workspace_skill_metadata(updated) or updated

    async def _replace_thread_messages(
        self,
        thread: ConversationThreadPayload,
        messages: list[dict[str, Any]],
    ) -> None:
        command = ConversationMessagesRebuildPayload(
            thread_id=str(thread.id),
            user_id=str(thread.user_id),
            workspace_id=thread.workspace_id,
            messages=messages,
        )
        if self._dataservice is not None:
            await self._dataservice.rebuild_conversation_messages(str(thread.id), command)
            return
        async with dataservice_client() as client:
            await client.rebuild_conversation_messages(str(thread.id), command)

    async def get_or_create_thread(
        self,
        *,
        user_id: str,
        thread_id: str | None = None,
        workspace_id: str | None = None,
        model: str | None = None,
        skill: str | None = None,
        skill_explicit: bool = False,
    ) -> ConversationThreadPayload:
        """Reuse an owned thread or create a new one."""
        resolved_model = self._resolve_model(model) if model and model.strip() else None
        resolved_skill = (skill or "").strip() or None if skill_explicit else None

        if thread_id:
            thread = await self.get_by_id(thread_id)
            if thread:
                if thread.user_id != user_id:
                    raise ThreadAccessError("Thread not found")
                needs_update = False
                if workspace_id and not thread.workspace_id:
                    thread.workspace_id = workspace_id
                    needs_update = True
                if resolved_model and thread.model != resolved_model:
                    thread.model = resolved_model
                    needs_update = True
                if skill_explicit and thread.skill != resolved_skill:
                    thread.skill = resolved_skill
                    needs_update = True
                if needs_update:
                    return await self._persist_thread_fields(
                        thread,
                        workspace_id=thread.workspace_id,
                        model=thread.model,
                        skill=thread.skill,
                        updated_at=datetime.now(UTC),
                    )
                return thread
            raise ThreadAccessError("Thread not found")

        if workspace_id:
            thread = await self.get_latest_workspace_thread(
                user_id=user_id,
                workspace_id=workspace_id,
            )
            if thread is not None:
                needs_update = False
                if resolved_model and thread.model != resolved_model:
                    thread.model = resolved_model
                    needs_update = True
                if skill_explicit and thread.skill != resolved_skill:
                    thread.skill = resolved_skill
                    needs_update = True
                if needs_update:
                    return await self._persist_thread_fields(
                        thread,
                        model=thread.model,
                        skill=thread.skill,
                        updated_at=datetime.now(UTC),
                    )
                return thread

        return await self.create_thread(
            user_id=user_id,
            workspace_id=workspace_id,
            model=resolved_model,
            skill=resolved_skill,
        )

    async def add_message(
        self,
        thread: ConversationThreadPayload,
        *,
        role: str,
        content: str,
        timestamp: datetime | None = None,
        blocks: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Append a message through the DataService conversation boundary."""
        await self._lock_thread_row(str(thread.id))
        resolved_timestamp = timestamp or datetime.now(UTC)
        message: dict[str, Any] = {
            "role": role,
            "content": content,
            "timestamp": resolved_timestamp.isoformat(),
        }
        if isinstance(blocks, list) and blocks:
            message["blocks"] = [block for block in blocks if isinstance(block, Mapping)]
        if isinstance(metadata, Mapping) and metadata:
            message["metadata"] = dict(metadata)
        sequence_index = max(int(thread.message_count or 0), 0)
        thread.message_count = sequence_index + 1
        normalized_role = str(role).strip()
        thread.last_message_role = normalized_role or None
        thread.last_message_preview = _truncate_message_preview(content)
        thread.updated_at = resolved_timestamp
        await self._persist_thread_fields(
            thread,
                message_count=thread.message_count,
                last_message_role=thread.last_message_role,
                last_message_preview=thread.last_message_preview,
                updated_at=thread.updated_at,
        )
        command = ConversationMessageCreatePayload(
            thread_id=str(thread.id),
            user_id=str(thread.user_id),
            workspace_id=thread.workspace_id,
            role=role,
            content=content,
            sequence_index=sequence_index,
            timestamp=resolved_timestamp,
            blocks=list(message.get("blocks") or []),
            metadata=dict(message.get("metadata") or {}),
        )
        if self._dataservice is not None:
            await self._dataservice.append_conversation_message(str(thread.id), command)
        else:
            async with dataservice_client() as client:
                await client.append_conversation_message(str(thread.id), command)
        return message

    async def update_attachment_extraction_state(
        self,
        thread: ConversationThreadPayload,
        *,
        task_id: str,
        status: str,
        message: str | None = None,
        progress: int | None = None,
        current_step: str | None = None,
        error: str | None = None,
        source_messages: list[dict[str, Any]] | None = None,
    ) -> bool:
        """Update extraction metadata for attachment(s) associated with a task."""
        resolved_task_id = task_id.strip()
        if not resolved_task_id:
            return False

        await self._lock_thread_row(str(thread.id))
        source = source_messages if source_messages is not None else await self.list_thread_messages(thread)
        messages = copy.deepcopy(list(source))
        changed = False

        for message_item in messages:
            if not isinstance(message_item, dict):
                continue
            metadata = message_item.get("metadata")
            if not isinstance(metadata, dict):
                continue
            attachments = metadata.get("attachments")
            if not isinstance(attachments, list):
                continue

            for attachment in attachments:
                if not isinstance(attachment, dict):
                    continue
                attachment_metadata = attachment.get("metadata")
                if not isinstance(attachment_metadata, dict):
                    continue
                extraction = attachment_metadata.get("extraction")
                if not isinstance(extraction, dict):
                    continue
                if extraction.get("task_id") != resolved_task_id:
                    continue

                extraction["status"] = status
                if message:
                    extraction["message"] = message
                if progress is not None:
                    extraction["progress"] = progress
                if current_step:
                    extraction["current_step"] = current_step
                elif current_step == "":
                    extraction.pop("current_step", None)
                if error:
                    extraction["error"] = error
                elif status == "success":
                    extraction.pop("error", None)
                changed = True

        if not changed:
            return False

        thread.updated_at = datetime.now(UTC)
        thread.message_count = len(messages)
        await self._persist_thread_fields(
            thread,
            message_count=thread.message_count,
            updated_at=thread.updated_at,
        )
        await self._replace_thread_messages(thread, messages)
        return True

    async def update_attachment_preprocess_state(
        self,
        thread: ConversationThreadPayload,
        *,
        task_id: str,
        status: str,
        preprocess: dict[str, Any] | None = None,
        message: str | None = None,
        progress: int | None = None,
        current_step: str | None = None,
        error: str | None = None,
        source_messages: list[dict[str, Any]] | None = None,
    ) -> bool:
        """Update preprocess metadata for attachment(s) associated with a task."""
        resolved_task_id = task_id.strip()
        if not resolved_task_id:
            return False

        await self._lock_thread_row(str(thread.id))
        source = source_messages if source_messages is not None else await self.list_thread_messages(thread)
        messages = copy.deepcopy(list(source))
        changed = False

        for message_item in messages:
            if not isinstance(message_item, dict):
                continue
            metadata = message_item.get("metadata")
            if not isinstance(metadata, dict):
                continue
            attachments = metadata.get("attachments")
            if not isinstance(attachments, list):
                continue

            for attachment in attachments:
                if not isinstance(attachment, dict):
                    continue
                attachment_metadata = attachment.get("metadata")
                if not isinstance(attachment_metadata, dict):
                    continue
                current_preprocess = attachment_metadata.get("preprocess")
                if not isinstance(current_preprocess, dict):
                    continue
                if current_preprocess.get("task_id") != resolved_task_id:
                    continue

                next_preprocess = dict(current_preprocess)
                if isinstance(preprocess, dict):
                    next_preprocess.update(preprocess)
                next_preprocess["task_id"] = resolved_task_id
                if status == "success" and isinstance(preprocess, dict):
                    next_preprocess["status"] = str(preprocess.get("status") or next_preprocess.get("status") or "succeeded")
                elif status:
                    next_preprocess["status"] = status
                if message:
                    next_preprocess["message"] = message
                if progress is not None:
                    next_preprocess["progress"] = progress
                if current_step:
                    next_preprocess["current_step"] = current_step
                elif current_step == "":
                    next_preprocess.pop("current_step", None)
                if error:
                    next_preprocess["error"] = error
                    next_preprocess["status"] = "failed"
                elif next_preprocess.get("status") == "succeeded":
                    next_preprocess.pop("error", None)

                attachment_metadata["preprocess"] = next_preprocess
                markdown_paths = next_preprocess.get("markdown_paths")
                if isinstance(markdown_paths, list) and markdown_paths:
                    attachment_metadata["preprocessed_markdown_paths"] = markdown_paths
                changed = True

        if not changed:
            return False

        thread.updated_at = datetime.now(UTC)
        thread.message_count = len(messages)
        await self._persist_thread_fields(
            thread,
            message_count=thread.message_count,
            updated_at=thread.updated_at,
        )
        await self._replace_thread_messages(thread, messages)
        return True

    async def compact_messages(
        self,
        thread: ConversationThreadPayload,
        *,
        summary: str,
        keep_messages: int,
        timestamp: datetime | None = None,
        source_messages: list[dict[str, Any]] | None = None,
    ) -> bool:
        """Persist a durable conversation summary plus the recent message tail."""
        normalized_summary = str(summary or "").strip()
        if not normalized_summary:
            return False

        await self._lock_thread_row(str(thread.id))
        source = source_messages if source_messages is not None else await self.list_thread_messages(thread)
        messages = list(source)
        keep_count = max(int(keep_messages or 0), 1)
        if len(messages) <= keep_count:
            return False

        resolved_timestamp = timestamp or datetime.now(UTC)
        kept_messages = messages[-keep_count:]
        compacted_count = len(messages) - len(kept_messages)
        summary_message: dict[str, Any] = {
            "role": "system",
            "content": (f"<conversation_summary>\n{normalized_summary}\n</conversation_summary>"),
            "timestamp": resolved_timestamp.isoformat(),
            "metadata": {
                "type": "thread_compaction",
                "compacted_message_count": compacted_count,
                "kept_message_count": len(kept_messages),
            },
        }

        next_messages = [summary_message] + kept_messages
        thread.message_count = len(next_messages)
        previous = next_messages[-1] if next_messages else None
        if isinstance(previous, Mapping):
            previous_role = str(previous.get("role") or "").strip()
            thread.last_message_role = previous_role or None
            thread.last_message_preview = _truncate_message_preview(str(previous.get("content") or ""))
        else:
            thread.last_message_role = None
            thread.last_message_preview = None
        thread.updated_at = resolved_timestamp
        await self._persist_thread_fields(
            thread,
            message_count=thread.message_count,
            last_message_role=thread.last_message_role,
            last_message_preview=thread.last_message_preview,
            updated_at=thread.updated_at,
        )
        await self._replace_thread_messages(thread, next_messages)
        return True

    async def set_title_if_empty(
        self,
        thread: ConversationThreadPayload,
        first_message: str,
    ) -> None:
        """Derive the thread title from the opening user message."""
        if thread.title or int(thread.message_count or 0) > 2:
            return

        thread.title = first_message[:50] + ("..." if len(first_message) > 50 else "")
        thread.updated_at = datetime.now(UTC)
        updated = await self._persist_thread_fields(
            thread,
            title=thread.title,
            updated_at=thread.updated_at,
        )
        thread.title = updated.title
        thread.updated_at = updated.updated_at

    async def rollback_last_user_message(
        self,
        thread: ConversationThreadPayload,
        *,
        expected_content: str | None = None,
        source_messages: list[dict[str, Any]] | None = None,
    ) -> bool:
        """Rollback the trailing user message when it matches expected content."""
        await self._lock_thread_row(str(thread.id))
        source = source_messages if source_messages is not None else await self.list_thread_messages(thread)
        messages = list(source)
        if not messages:
            return False

        last = messages[-1]
        if not isinstance(last, Mapping):
            return False
        if str(last.get("role") or "").strip() != "user":
            return False

        if expected_content is not None:
            if str(last.get("content") or "") != expected_content:
                return False

        messages.pop()
        thread.message_count = len(messages)
        previous = messages[-1] if messages else None
        if isinstance(previous, Mapping):
            previous_role = str(previous.get("role") or "").strip()
            thread.last_message_role = previous_role or None
            thread.last_message_preview = _truncate_message_preview(str(previous.get("content") or ""))
        else:
            thread.last_message_role = None
            thread.last_message_preview = None
        thread.updated_at = datetime.now(UTC)
        await self._persist_thread_fields(
            thread,
            message_count=thread.message_count,
            last_message_role=thread.last_message_role,
            last_message_preview=thread.last_message_preview,
            updated_at=thread.updated_at,
        )
        await self._replace_thread_messages(thread, messages)
        return True

    async def list_thread_messages(
        self,
        thread: ConversationThreadPayload,
    ) -> list[dict[str, Any]]:
        """Read thread messages from the DataService conversation projection."""
        if self._dataservice is not None:
            messages = await self._dataservice.list_conversation_messages(str(thread.id))
        else:
            async with dataservice_client() as client:
                messages = await client.list_conversation_messages(str(thread.id))
        return [self._message_payload_to_bridge(message) for message in messages]

    async def list_threads(
        self,
        *,
        user_id: str,
        workspace_id: str | None = None,
        limit: int = 20,
    ) -> list[ConversationThreadPayload]:
        """List threads for a user ordered by most recently updated."""
        if self._dataservice is not None:
            threads = await self._dataservice.list_conversation_threads(
                user_id=user_id,
                workspace_id=workspace_id,
                limit=limit,
            )
        else:
            async with dataservice_client() as client:
                threads = await client.list_conversation_threads(
                    user_id=user_id,
                    workspace_id=workspace_id,
                    limit=limit,
                )
        workspace_types = await list_workspace_types(
            self.db,
            [thread.workspace_id for thread in threads],
        )
        return [
            self._hydrate_thread_skill_metadata(
                thread,
                workspace_type=(workspace_types.get(str(thread.workspace_id)) if thread.workspace_id is not None else None),
            )
            for thread in threads
        ]

    async def delete_thread(self, thread_id: str, user_id: str) -> bool:
        """Delete an owned thread."""
        thread = await self.get_thread(thread_id, user_id)
        if not thread:
            return False

        if self._dataservice is not None:
            deleted = await self._dataservice.delete_conversation_thread(
                thread_id=thread_id,
                user_id=user_id,
            )
        else:
            async with dataservice_client() as client:
                deleted = await client.delete_conversation_thread(
                    thread_id=thread_id,
                    user_id=user_id,
                )
        if not deleted:
            return False
        try:
            delete_thread_directory(thread_id)
        except Exception:
            logger.warning(
                "Failed to delete local thread directory for %s",
                thread_id,
                exc_info=True,
            )
        return True
