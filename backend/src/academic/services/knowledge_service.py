"""User knowledge service for managing personalized knowledge."""


from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import UserKnowledge


class KnowledgeService:
    """Service for managing user knowledge."""

    def __init__(self, db: AsyncSession):
        """Initialize with database session.

        Args:
            db: AsyncSession for database operations
        """
        self.db = db

    async def create(
        self,
        user_id: str,
        category: str,
        content: str,
        confidence: float = 0.7,
        source: str | None = None,
        workspace_context: str | None = None,
    ) -> UserKnowledge:
        """Create a new knowledge entry.

        Args:
            user_id: User ID
            category: Knowledge category
            content: Knowledge content
            confidence: Confidence score (0.0-1.0)
            source: Source of knowledge
            workspace_context: Optional workspace context

        Returns:
            Created knowledge entry
        """
        knowledge = UserKnowledge(
            user_id=user_id,
            category=category,
            content=content,
            confidence=confidence,
            source=source,
            workspace_context=workspace_context,
        )
        self.db.add(knowledge)
        await self.db.commit()
        await self.db.refresh(knowledge)
        return knowledge

    async def get(self, knowledge_id: str) -> UserKnowledge | None:
        """Get knowledge by ID.

        Args:
            knowledge_id: Knowledge ID

        Returns:
            Knowledge if found, None otherwise
        """
        result = await self.db.execute(
            select(UserKnowledge).where(UserKnowledge.id == knowledge_id)
        )
        return result.scalar_one_or_none()

    async def list_by_user(
        self,
        user_id: str,
        category: str | None = None,
        min_confidence: float | None = None,
        active_only: bool = True,
    ) -> list[UserKnowledge]:
        """List knowledge entries for a user.

        Args:
            user_id: User ID
            category: Filter by category (optional)
            min_confidence: Minimum confidence threshold
            active_only: Only return active entries

        Returns:
            List of knowledge entries
        """
        conditions = [UserKnowledge.user_id == user_id]

        if category:
            conditions.append(UserKnowledge.category == category)
        if min_confidence is not None:
            conditions.append(UserKnowledge.confidence >= min_confidence)
        if active_only:
            conditions.append(UserKnowledge.is_active)

        result = await self.db.execute(
            select(UserKnowledge)
            .where(and_(*conditions))
            .order_by(UserKnowledge.confidence.desc(), UserKnowledge.updated_at.desc())
        )
        return list(result.scalars().all())

    async def update(
        self,
        knowledge_id: str,
        content: str | None = None,
        confidence: float | None = None,
        is_active: bool | None = None,
    ) -> UserKnowledge | None:
        """Update knowledge entry.

        Args:
            knowledge_id: Knowledge ID
            content: New content
            confidence: New confidence score
            is_active: New active status

        Returns:
            Updated knowledge if found, None otherwise
        """
        knowledge = await self.get(knowledge_id)
        if not knowledge:
            return None

        if content is not None:
            knowledge.content = content
        if confidence is not None:
            knowledge.confidence = confidence
        if is_active is not None:
            knowledge.is_active = is_active

        await self.db.commit()
        await self.db.refresh(knowledge)
        return knowledge

    async def deactivate(self, knowledge_id: str) -> bool:
        """Deactivate knowledge entry.

        Args:
            knowledge_id: Knowledge ID

        Returns:
            True if deactivated, False if not found
        """
        knowledge = await self.get(knowledge_id)
        if not knowledge:
            return False

        knowledge.is_active = False
        await self.db.commit()
        return True

    async def delete(self, knowledge_id: str) -> bool:
        """Delete knowledge entry.

        Args:
            knowledge_id: Knowledge ID

        Returns:
            True if deleted, False if not found
        """
        knowledge = await self.get(knowledge_id)
        if not knowledge:
            return False

        await self.db.delete(knowledge)
        await self.db.commit()
        return True
