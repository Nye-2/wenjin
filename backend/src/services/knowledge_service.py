"""CRUD service for UserKnowledge persistence."""

from __future__ import annotations

import logging

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.knowledge import KnowledgeCategory, UserKnowledge

logger = logging.getLogger(__name__)


class KnowledgeService:
    """Canonical service for UserKnowledge lifecycle."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        # Expose a consistent service session attribute used across service classes.
        self.db = db

    @staticmethod
    def _normalize_category(category: KnowledgeCategory | str) -> KnowledgeCategory:
        """Coerce string category into enum for consistent DB writes."""
        if isinstance(category, str):
            return KnowledgeCategory(category)
        return category

    async def create(
        self,
        user_id: str,
        category: KnowledgeCategory | str,
        content: str,
        confidence: float = 0.7,
        source: str | None = None,
        workspace_context: str | None = None,
    ) -> UserKnowledge:
        """Create a new knowledge entry (CRUD style API)."""
        entry = UserKnowledge(
            user_id=user_id,
            category=self._normalize_category(category),
            content=content,
            confidence=confidence,
            source=source,
            workspace_context=workspace_context,
        )
        self._db.add(entry)
        await self._db.commit()
        await self._db.refresh(entry)
        return entry

    async def get(self, knowledge_id: str) -> UserKnowledge | None:
        """Get knowledge by ID."""
        stmt = select(UserKnowledge).where(UserKnowledge.id == knowledge_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_user(
        self,
        user_id: str,
        category: KnowledgeCategory | str | None = None,
        min_confidence: float | None = None,
        active_only: bool = True,
    ) -> list[UserKnowledge]:
        """List knowledge entries for a user (CRUD style API)."""
        conditions = [UserKnowledge.user_id == user_id]

        if category is not None:
            conditions.append(UserKnowledge.category == self._normalize_category(category))
        if min_confidence is not None:
            conditions.append(UserKnowledge.confidence >= min_confidence)
        if active_only:
            conditions.append(UserKnowledge.is_active == True)  # noqa: E712

        stmt = (
            select(UserKnowledge)
            .where(and_(*conditions))
            .order_by(UserKnowledge.confidence.desc(), UserKnowledge.updated_at.desc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def update(
        self,
        knowledge_id: str,
        content: str | None = None,
        confidence: float | None = None,
        is_active: bool | None = None,
    ) -> UserKnowledge | None:
        """Update a knowledge entry (CRUD style API)."""
        entry = await self.get(knowledge_id)
        if not entry:
            return None

        if content is not None:
            entry.content = content
        if confidence is not None:
            entry.confidence = confidence
        if is_active is not None:
            entry.is_active = is_active

        await self._db.commit()
        await self._db.refresh(entry)
        return entry

    async def deactivate(self, knowledge_id: str) -> bool:
        """Deactivate a knowledge entry."""
        entry = await self.get(knowledge_id)
        if not entry:
            return False

        entry.is_active = False
        await self._db.commit()
        return True

    async def delete(self, knowledge_id: str) -> bool:
        """Delete a knowledge entry."""
        entry = await self.get(knowledge_id)
        if not entry:
            return False

        await self._db.delete(entry)
        await self._db.commit()
        return True

    async def list_active(
        self,
        user_id: str,
        *,
        workspace_context: str | None = None,
        min_confidence: float = 0.5,
        limit: int = 20,
    ) -> list[UserKnowledge]:
        """Return active knowledge ordered by confidence desc.

        Retrieval rules:
        - with workspace_context: include current-workspace + global entries
        - without workspace_context: include global entries only
        Entries are ordered by workspace match first (when applicable), then confidence.
        """
        scope_condition = (
            or_(
                UserKnowledge.workspace_context == workspace_context,
                UserKnowledge.workspace_context.is_(None),
            )
            if workspace_context
            else UserKnowledge.workspace_context.is_(None)
        )
        stmt = (
            select(UserKnowledge)
            .where(
                and_(
                    UserKnowledge.user_id == user_id,
                    UserKnowledge.is_active == True,  # noqa: E712
                    UserKnowledge.confidence >= min_confidence,
                    scope_condition,
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
        normalized_category = self._normalize_category(category)

        # Check for existing similar entry
        conditions = [
            UserKnowledge.user_id == user_id,
            UserKnowledge.category == normalized_category,
            UserKnowledge.content == content,
            UserKnowledge.is_active == True,  # noqa: E712
        ]
        if workspace_context is None:
            conditions.append(UserKnowledge.workspace_context.is_(None))
        else:
            conditions.append(UserKnowledge.workspace_context == workspace_context)

        stmt = select(UserKnowledge).where(and_(*conditions))
        result = await self._db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            existing.boost_confidence(0.1)
            existing.source = source or existing.source
            await self._db.flush()
            return existing

        entry = UserKnowledge(
            user_id=user_id,
            category=normalized_category,
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
