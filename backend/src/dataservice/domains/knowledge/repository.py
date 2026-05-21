"""Knowledge memory repository."""

from __future__ import annotations

from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.knowledge import KnowledgeCategory, UserKnowledge


class KnowledgeRepository:
    """DataService-owned persistence operations for user knowledge."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def normalize_category(category: Any) -> KnowledgeCategory:
        if isinstance(category, KnowledgeCategory):
            return category
        value = category.value if hasattr(category, "value") else str(category)
        return KnowledgeCategory(value)

    def create_entry(self, values: dict[str, Any]) -> UserKnowledge:
        entry = UserKnowledge(**values)
        self.session.add(entry)
        return entry

    async def get(self, knowledge_id: str) -> UserKnowledge | None:
        result = await self.session.execute(
            select(UserKnowledge).where(UserKnowledge.id == knowledge_id)
        )
        return result.scalar_one_or_none()

    async def list_by_user(
        self,
        *,
        user_id: str,
        category: Any | None = None,
        min_confidence: float | None = None,
        active_only: bool = True,
    ) -> list[UserKnowledge]:
        conditions = [UserKnowledge.user_id == user_id]
        if category is not None:
            conditions.append(UserKnowledge.category == self.normalize_category(category))
        if min_confidence is not None:
            conditions.append(UserKnowledge.confidence >= min_confidence)
        if active_only:
            conditions.append(UserKnowledge.is_active == True)  # noqa: E712

        result = await self.session.execute(
            select(UserKnowledge)
            .where(and_(*conditions))
            .order_by(UserKnowledge.confidence.desc(), UserKnowledge.updated_at.desc())
        )
        return list(result.scalars().all())

    async def list_active(
        self,
        *,
        user_id: str,
        workspace_context: str | None = None,
        include_global: bool = True,
        min_confidence: float = 0.5,
        limit: int = 20,
    ) -> list[UserKnowledge]:
        scope_condition = (
            or_(
                UserKnowledge.workspace_context == workspace_context,
                UserKnowledge.workspace_context.is_(None),
            )
            if workspace_context and include_global
            else UserKnowledge.workspace_context == workspace_context
            if workspace_context
            else UserKnowledge.workspace_context.is_(None)
        )
        result = await self.session.execute(
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
                (UserKnowledge.workspace_context == workspace_context).desc()
                if workspace_context
                else UserKnowledge.confidence.desc(),
                UserKnowledge.confidence.desc(),
            )
            .limit(limit)
        )
        return list(result.scalars().all())

    async def find_duplicate(
        self,
        *,
        user_id: str,
        category: Any,
        content: str,
        workspace_context: str | None,
    ) -> UserKnowledge | None:
        conditions = [
            UserKnowledge.user_id == user_id,
            UserKnowledge.category == self.normalize_category(category),
            UserKnowledge.content == content,
            UserKnowledge.is_active == True,  # noqa: E712
        ]
        if workspace_context is None:
            conditions.append(UserKnowledge.workspace_context.is_(None))
        else:
            conditions.append(UserKnowledge.workspace_context == workspace_context)
        result = await self.session.execute(select(UserKnowledge).where(and_(*conditions)))
        return result.scalar_one_or_none()

    async def list_low_confidence(
        self,
        *,
        user_id: str,
        threshold: float,
    ) -> list[UserKnowledge]:
        result = await self.session.execute(
            select(UserKnowledge).where(
                and_(
                    UserKnowledge.user_id == user_id,
                    UserKnowledge.is_active == True,  # noqa: E712
                    UserKnowledge.confidence < threshold,
                )
            )
        )
        return list(result.scalars().all())

    async def count_active(
        self,
        *,
        user_id: str,
        workspace_context: str | None = None,
        include_global: bool | None = None,
    ) -> int:
        conditions = [
            UserKnowledge.user_id == user_id,
            UserKnowledge.is_active == True,  # noqa: E712
        ]
        if workspace_context is not None:
            if include_global:
                conditions.append(
                    or_(
                        UserKnowledge.workspace_context == workspace_context,
                        UserKnowledge.workspace_context.is_(None),
                    )
                )
            else:
                conditions.append(UserKnowledge.workspace_context == workspace_context)
        elif include_global is False:
            conditions.append(UserKnowledge.workspace_context.is_(None))

        result = await self.session.execute(
            select(func.count()).select_from(UserKnowledge).where(and_(*conditions))
        )
        return int(result.scalar_one())
