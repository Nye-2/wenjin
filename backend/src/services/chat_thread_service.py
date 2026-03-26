"""Service layer for persisted chat threads."""

import copy
import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.middlewares.thread_data import delete_thread_directory
from src.database import ChatThread
from src.models.router import route_model, validate_requested_model

logger = logging.getLogger(__name__)


class ChatThreadAccessError(LookupError):
    """Raised when a thread exists but is not owned by the active user."""


class ChatThreadService:
    """CRUD and mutation helpers for chat threads."""

    def __init__(
        self,
        db: AsyncSession,
        model: type[ChatThread] = ChatThread,
    ) -> None:
        self.db = db
        self._model = model

    @staticmethod
    def _resolve_model(model: str | None) -> str:
        """Resolve model id through env-backed config without silent user fallback."""
        requested = validate_requested_model(
            model,
            allowed_categories=("tool", "gen"),
            require_tools=False,
        )
        return route_model(
            requested_model=requested,
            preferred_categories=("tool", "gen"),
            allowed_categories=("tool", "gen"),
            require_tools=False,
        )

    async def create_thread(
        self,
        *,
        user_id: str,
        workspace_id: str | None = None,
        title: str | None = None,
        model: str | None = None,
        skill: str | None = None,
    ) -> ChatThread:
        """Create and persist a new chat thread."""
        now = datetime.now(UTC)
        thread = self._model(
            user_id=user_id,
            workspace_id=workspace_id,
            title=title,
            model=self._resolve_model(model),
            skill=(skill or "").strip() or None,
            messages=[],
            created_at=now,
            updated_at=now,
        )
        self.db.add(thread)
        await self.db.commit()
        await self.db.refresh(thread)
        return thread

    async def get_by_id(self, thread_id: str) -> ChatThread | None:
        """Fetch a thread regardless of owner."""
        result = await self.db.execute(
            select(self._model).where(self._model.id == thread_id)
        )
        return result.scalar_one_or_none()

    async def get_thread(self, thread_id: str, user_id: str) -> ChatThread | None:
        """Fetch a thread owned by the active user."""
        thread = await self.get_by_id(thread_id)
        if not thread or thread.user_id != user_id:
            return None
        return thread

    async def get_or_create_thread(
        self,
        *,
        user_id: str,
        thread_id: str | None = None,
        workspace_id: str | None = None,
        model: str | None = None,
        skill: str | None = None,
        skill_explicit: bool = False,
    ) -> ChatThread:
        """Reuse an owned thread or create a new one."""
        resolved_model = self._resolve_model(model) if model and model.strip() else None
        resolved_skill = (skill or "").strip() or None if skill_explicit else None

        if thread_id:
            thread = await self.get_by_id(thread_id)
            if thread:
                if thread.user_id != user_id:
                    raise ChatThreadAccessError("Thread not found")
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
                    thread.updated_at = datetime.now(UTC)
                    await self.db.commit()
                    await self.db.refresh(thread)
                return thread

        return await self.create_thread(
            user_id=user_id,
            workspace_id=workspace_id,
            model=resolved_model,
            skill=resolved_skill,
        )

    async def add_message(
        self,
        thread: ChatThread,
        *,
        role: str,
        content: str,
        timestamp: datetime | None = None,
        blocks: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Append a message and persist JSON history safely."""
        resolved_timestamp = timestamp or datetime.now(UTC)
        message = {
            "role": role,
            "content": content,
            "timestamp": resolved_timestamp.isoformat(),
        }
        if isinstance(blocks, list) and blocks:
            message["blocks"] = [
                block
                for block in blocks
                if isinstance(block, Mapping)
            ]
        if isinstance(metadata, Mapping) and metadata:
            message["metadata"] = dict(metadata)
        messages = list(thread.messages or [])
        messages.append(message)
        thread.messages = messages
        thread.updated_at = resolved_timestamp
        await self.db.commit()
        await self.db.refresh(thread)
        return message

    async def update_attachment_extraction_state(
        self,
        thread: ChatThread,
        *,
        task_id: str,
        status: str,
        message: str | None = None,
        progress: int | None = None,
        current_step: str | None = None,
        error: str | None = None,
    ) -> bool:
        """Update extraction metadata for attachment(s) associated with a task."""
        resolved_task_id = task_id.strip()
        if not resolved_task_id:
            return False

        messages = copy.deepcopy(list(thread.messages or []))
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

        thread.messages = messages
        await self.db.commit()
        await self.db.refresh(thread)
        return True

    async def set_title_if_empty(self, thread: ChatThread, first_message: str) -> None:
        """Derive the thread title from the opening user message."""
        if thread.title or len(thread.messages or []) > 2:
            return

        thread.title = first_message[:50] + ("..." if len(first_message) > 50 else "")
        thread.updated_at = datetime.now(UTC)
        await self.db.commit()
        await self.db.refresh(thread)

    async def list_threads(
        self,
        *,
        user_id: str,
        workspace_id: str | None = None,
        limit: int = 20,
    ) -> list[ChatThread]:
        """List threads for a user ordered by most recently updated."""
        query = select(self._model).where(self._model.user_id == user_id)
        if workspace_id:
            query = query.where(self._model.workspace_id == workspace_id)

        result = await self.db.execute(
            query.order_by(self._model.updated_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def delete_thread(self, thread_id: str, user_id: str) -> bool:
        """Delete an owned thread."""
        thread = await self.get_thread(thread_id, user_id)
        if not thread:
            return False

        await self.db.delete(thread)
        await self.db.commit()
        try:
            delete_thread_directory(thread_id)
        except Exception:
            logger.warning(
                "Failed to delete local thread directory for %s",
                thread_id,
                exc_info=True,
            )
        return True
