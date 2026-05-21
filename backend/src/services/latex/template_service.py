"""Template catalog access for LaTeX projects."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.latex_api import LatexDataService


class LatexTemplateService:
    """Service for template catalog initialization and listing."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.data = LatexDataService(db)

    async def ensure_defaults(self) -> None:
        await self.data.ensure_default_templates()

    async def list_templates(self) -> list[object]:
        return await self.data.list_templates()
