"""Service layer for persisted chat threads."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import ChatThread
from src.models.router import route_model


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
        """Resolve model id through env-backed config with graceful fallback."""
        requested = (model or "").strip() or None
        try:
            return route_model(
                requested_model=requested,
                preferred_categories=("tool", "gen"),
                allowed_categories=("tool", "gen"),
                require_tools=False,
            )
        except Exception:
            if requested:
                return requested
            return "default"

    async def create_thread(
        self,
        *,
        user_id: str,
        workspace_id: str | None = None,
        title: str | None = None,
        model: str | None = None,
    ) -> ChatThread:
        """Create and persist a new chat thread."""
        now = datetime.now(timezone.utc)
        thread = self._model(
            user_id=user_id,
            workspace_id=workspace_id,
            title=title,
            model=self._resolve_model(model),
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
    ) -> ChatThread:
        """Reuse an owned thread or create a new one."""
        resolved_model = self._resolve_model(model) if model and model.strip() else None

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
                if needs_update:
                    thread.updated_at = datetime.now(timezone.utc)
                    await self.db.commit()
                    await self.db.refresh(thread)
                return thread

        return await self.create_thread(
            user_id=user_id,
            workspace_id=workspace_id,
            model=resolved_model,
        )

    async def add_message(
        self,
        thread: ChatThread,
        *,
        role: str,
        content: str,
        timestamp: datetime | None = None,
    ) -> dict[str, str]:
        """Append a message and persist JSON history safely."""
        resolved_timestamp = timestamp or datetime.now(timezone.utc)
        message = {
            "role": role,
            "content": content,
            "timestamp": resolved_timestamp.isoformat(),
        }
        messages = list(thread.messages or [])
        messages.append(message)
        thread.messages = messages
        thread.updated_at = resolved_timestamp
        await self.db.commit()
        await self.db.refresh(thread)
        return message

    async def set_title_if_empty(self, thread: ChatThread, first_message: str) -> None:
        """Derive the thread title from the opening user message."""
        if thread.title or len(thread.messages or []) > 2:
            return

        thread.title = first_message[:50] + ("..." if len(first_message) > 50 else "")
        thread.updated_at = datetime.now(timezone.utc)
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
        return True
