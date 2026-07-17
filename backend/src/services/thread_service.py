"""Service layer for persisted threads."""

import logging
from datetime import UTC, datetime
from typing import Any

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.conversation import (
    ConversationAttachmentStatePatchPayload,
    ConversationMessagePayload,
    ConversationThreadCreatePayload,
    ConversationThreadPayload,
    ConversationThreadUpdatePayload,
)
from src.dataservice_client.provider import dataservice_client
from src.models.router import route_model, validate_requested_model
from src.services.thread_data_paths import delete_thread_directory
from src.services.workspace_skill_labels import (
    list_workspace_types,
)

logger = logging.getLogger(__name__)


class ThreadAccessError(LookupError):
    """Raised when a thread exists but is not owned by the active user."""


class ThreadService:
    """CRUD and mutation helpers for threads."""

    def __init__(
        self,
        *,
        dataservice: AsyncDataServiceClient | None = None,
    ) -> None:
        self._dataservice = dataservice

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

    @staticmethod
    def _hydrate_thread_workspace_metadata(
        thread: ConversationThreadPayload,
        *,
        workspace_type: str | None,
    ) -> ConversationThreadPayload:
        """Attach resolved workspace metadata to a thread object."""
        cast_thread: Any = thread
        cast_thread.workspace_type = workspace_type
        return thread

    async def _attach_workspace_skill_metadata(
        self,
        thread: ConversationThreadPayload | None,
        *,
        workspace_types: dict[str, str] | None = None,
    ) -> ConversationThreadPayload | None:
        """Attach resolved workspace metadata to a thread object."""
        if thread is None:
            return None
        workspace_id = str(thread.workspace_id).strip() if thread.workspace_id else None
        workspace_type = None
        if workspace_id and workspace_types is not None:
            workspace_type = workspace_types.get(workspace_id)
        if workspace_type is None and workspace_id:
            workspace_type = (
                await list_workspace_types(
                    [workspace_id],
                    dataservice=self._dataservice,
                )
            ).get(workspace_id)
        return self._hydrate_thread_workspace_metadata(
            thread,
            workspace_type=workspace_type,
        )

    @staticmethod
    def _resolve_model(model: str | None) -> str:
        """Resolve model id through env-backed config without silent user fallback."""
        requested = validate_requested_model(
            model,
            allowed_categories=("llm",),
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
    ) -> ConversationThreadPayload:
        """Create and persist a new thread."""
        now = datetime.now(UTC)
        command = ConversationThreadCreatePayload(
                user_id=user_id,
                workspace_id=workspace_id,
                title=title,
                model=self._resolve_model(model),
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

    async def get_or_create_thread(
        self,
        *,
        user_id: str,
        thread_id: str | None = None,
        workspace_id: str | None = None,
        model: str | None = None,
    ) -> ConversationThreadPayload:
        """Reuse an owned thread or create a new one."""
        resolved_model = self._resolve_model(model) if model and model.strip() else None

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
                if needs_update:
                    return await self._persist_thread_fields(
                        thread,
                        workspace_id=thread.workspace_id,
                        model=thread.model,
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
                if needs_update:
                    return await self._persist_thread_fields(
                        thread,
                        model=thread.model,
                        updated_at=datetime.now(UTC),
                    )
                return thread

        return await self.create_thread(
            user_id=user_id,
            workspace_id=workspace_id,
            model=resolved_model,
        )

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
    ) -> bool:
        """Atomically update extraction metadata for a task attachment."""
        if not task_id.strip():
            return False
        command = ConversationAttachmentStatePatchPayload(
            thread_id=str(thread.id),
            task_id=task_id.strip(),
            state_key="extraction",
            status=status,
            message=message,
            progress=progress,
            current_step=current_step,
            error=error,
        )
        if self._dataservice is not None:
            return await self._dataservice.patch_conversation_attachment_state(
                str(thread.id), command
            )
        async with dataservice_client() as client:
            return await client.patch_conversation_attachment_state(
                str(thread.id), command
            )

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
    ) -> bool:
        """Atomically update preprocess metadata for a task attachment."""
        if not task_id.strip():
            return False
        command = ConversationAttachmentStatePatchPayload(
            thread_id=str(thread.id),
            task_id=task_id.strip(),
            state_key="preprocess",
            status=status,
            state_patch=dict(preprocess or {}),
            message=message,
            progress=progress,
            current_step=current_step,
            error=error,
        )
        if self._dataservice is not None:
            return await self._dataservice.patch_conversation_attachment_state(
                str(thread.id), command
            )
        async with dataservice_client() as client:
            return await client.patch_conversation_attachment_state(
                str(thread.id), command
            )

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
            [thread.workspace_id for thread in threads],
            dataservice=self._dataservice,
        )
        return [
            self._hydrate_thread_workspace_metadata(
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
