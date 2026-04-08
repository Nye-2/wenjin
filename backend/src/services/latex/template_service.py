"""Template catalog access for LaTeX projects."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.latex_template import LatexTemplate

_DEFAULT_TEMPLATES: list[dict[str, object]] = [
    {
        "id": "acl",
        "label": "ACL",
        "main_file": "main.tex",
        "category": "academic",
        "description": "ACL conference template",
        "description_en": "ACL conference template",
        "tags": ["ACL", "NLP"],
        "author": "WenjinPrism",
        "featured": True,
        "template_path": "acl",
    },
    {
        "id": "cvpr",
        "label": "CVPR",
        "main_file": "main.tex",
        "category": "academic",
        "description": "CVPR conference template",
        "description_en": "CVPR conference template",
        "tags": ["CVPR", "Computer Vision"],
        "author": "WenjinPrism",
        "featured": True,
        "template_path": "cvpr",
    },
    {
        "id": "neurips",
        "label": "NeurIPS",
        "main_file": "main.tex",
        "category": "academic",
        "description": "NeurIPS conference template",
        "description_en": "NeurIPS conference template",
        "tags": ["NeurIPS", "Machine Learning"],
        "author": "WenjinPrism",
        "featured": True,
        "template_path": "neurips",
    },
    {
        "id": "icml",
        "label": "ICML",
        "main_file": "main.tex",
        "category": "academic",
        "description": "ICML conference template",
        "description_en": "ICML conference template",
        "tags": ["ICML", "Machine Learning"],
        "author": "WenjinPrism",
        "featured": True,
        "template_path": "icml",
    },
]


class LatexTemplateService:
    """Service for template catalog initialization and listing."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def ensure_defaults(self) -> None:
        found = (await self.db.execute(select(LatexTemplate.id).limit(1))).scalar_one_or_none()
        if found is not None:
            return
        for payload in _DEFAULT_TEMPLATES:
            self.db.add(LatexTemplate(**payload))
        await self.db.commit()

    async def list_templates(self) -> list[LatexTemplate]:
        await self.ensure_defaults()
        result = await self.db.execute(
            select(LatexTemplate).order_by(
                LatexTemplate.featured.desc(),
                LatexTemplate.id.asc(),
            )
        )
        return list(result.scalars().all())
