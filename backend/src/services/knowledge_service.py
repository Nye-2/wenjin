"""CRUD service for UserKnowledge persistence."""

from __future__ import annotations

import logging

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.knowledge import KnowledgeCategory, UserKnowledge

logger = logging.getLogger(__name__)


class KnowledgeService:
    """Manages UserKnowledge lifecycle."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_active(
        self,
        user_id: str,
        *,
        workspace_context: str | None = None,
        min_confidence: float = 0.5,
        limit: int = 20,
    ) -> list[UserKnowledge]:
        """Return active knowledge ordered by confidence desc.

        Workspace-specific entries appear first, then global entries.
        """
        stmt = (
            select(UserKnowledge)
            .where(
                and_(
                    UserKnowledge.user_id == user_id,
                    UserKnowledge.is_active == True,  # noqa: E712
                    UserKnowledge.confidence >= min_confidence,
                )
            )
            .order_by(
                # workspace-specific first
                (UserKnowledge.workspace_context == workspace_context).desc()
                if workspace_context
                else UserKnowledge.confidence.desc(),
                UserKnowledge.confidence.desc(),
            )
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def upsert(
        self,
        user_id: str,
        category: KnowledgeCategory | str,
        content: str,
        *,
        confidence: float = 0.7,
        source: str | None = None,
        workspace_context: str | None = None,
    ) -> UserKnowledge:
        """Insert or update (boost confidence if duplicate content)."""
        if isinstance(category, str):
            category = KnowledgeCategory(category)

        # Check for existing similar entry
        stmt = select(UserKnowledge).where(
            and_(
                UserKnowledge.user_id == user_id,
                UserKnowledge.category == category,
                UserKnowledge.content == content,
                UserKnowledge.is_active == True,  # noqa: E712
            )
        )
        result = await self._db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            existing.boost_confidence(0.1)
            existing.source = source or existing.source
            await self._db.flush()
            return existing

        entry = UserKnowledge(
            user_id=user_id,
            category=category,
            content=content,
            confidence=confidence,
            source=source,
            workspace_context=workspace_context,
        )
        self._db.add(entry)
        await self._db.flush()
        return entry

    async def archive_low_confidence(
        self,
        user_id: str,
        threshold: float = 0.5,
    ) -> int:
        """Deactivate entries below threshold. Returns count."""
        stmt = (
            select(UserKnowledge)
            .where(
                and_(
                    UserKnowledge.user_id == user_id,
                    UserKnowledge.is_active == True,  # noqa: E712
                    UserKnowledge.confidence < threshold,
                )
            )
        )
        result = await self._db.execute(stmt)
        entries = result.scalars().all()
        for entry in entries:
            entry.is_active = False
        await self._db.flush()
        return len(entries)

    async def count_active(self, user_id: str) -> int:
        """Count active knowledge entries for a user."""
        stmt = select(func.count()).select_from(UserKnowledge).where(
            and_(
                UserKnowledge.user_id == user_id,
                UserKnowledge.is_active == True,  # noqa: E712
            )
        )
        result = await self._db.execute(stmt)
        return result.scalar_one()
