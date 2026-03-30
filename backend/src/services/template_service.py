"""Template service for workspace template CRUD and parsing."""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.workspace_template import WorkspaceTemplate

logger = logging.getLogger(__name__)

TEMPLATE_PARSE_PROMPT = '''从以下模板文件中提取论文写作规范。返回 JSON（不要其他内容）：
{{
  "name": "模板名称（从内容推断）",
  "structure": {{
    "chapters": [
      {{"title": "章节标题", "level": 1, "required": true, "description": "章节要求说明", "suggested_word_count": "字数范围"}}
    ]
  }},
  "format_spec": {{
    "page_size": "纸张大小",
    "margins": {{"top": "上边距", "bottom": "下边距", "left": "左边距", "right": "右边距"}},
    "font_body": "正文字体",
    "font_heading": "标题字体",
    "line_spacing": 1.5,
    "bibliography_style": "引用格式"
  }},
  "content_guidelines": {{
    "abstract_word_limit": "摘要字数要求",
    "keywords_count": "关键词数量",
    "chapter_requirements": [{{"chapter": "章节名", "requirement": "具体要求"}}]
  }}
}}

如果某些信息在模板中未明确指定，对应字段返回 null。

模板内容：
{content}'''


class TemplateService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, template_id: str) -> WorkspaceTemplate | None:
        result = await self.db.execute(
            select(WorkspaceTemplate).where(WorkspaceTemplate.id == template_id)
        )
        return result.scalar_one_or_none()

    async def get_active(self, workspace_id: str) -> WorkspaceTemplate | None:
        result = await self.db.execute(
            select(WorkspaceTemplate)
            .where(
                WorkspaceTemplate.workspace_id == workspace_id,
                WorkspaceTemplate.is_active == True,
            )
            .order_by(WorkspaceTemplate.updated_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_by_workspace(self, workspace_id: str) -> list[WorkspaceTemplate]:
        result = await self.db.execute(
            select(WorkspaceTemplate)
            .where(WorkspaceTemplate.workspace_id == workspace_id)
            .order_by(WorkspaceTemplate.updated_at.desc())
        )
        return list(result.scalars().all())

    async def create(
        self,
        workspace_id: str,
        name: str,
        category: str,
        source_type: str,
        source_file_path: str | None = None,
        structure: dict | None = None,
        format_spec: dict | None = None,
        content_guidelines: dict | None = None,
        latex_preamble: str | None = None,
    ) -> WorkspaceTemplate:
        # Deactivate existing active templates
        await self.db.execute(
            update(WorkspaceTemplate)
            .where(
                WorkspaceTemplate.workspace_id == workspace_id,
                WorkspaceTemplate.is_active == True,
            )
            .values(is_active=False)
        )

        template = WorkspaceTemplate(
            workspace_id=workspace_id,
            name=name,
            category=category,
            source_type=source_type,
            source_file_path=source_file_path,
            structure=structure,
            format_spec=format_spec,
            content_guidelines=content_guidelines,
            latex_preamble=latex_preamble,
            is_active=True,
            is_builtin=False,
        )
        self.db.add(template)
        await self.db.commit()
        await self.db.refresh(template)
        return template

    async def activate(self, template_id: str, workspace_id: str) -> WorkspaceTemplate | None:
        await self.db.execute(
            update(WorkspaceTemplate)
            .where(
                WorkspaceTemplate.workspace_id == workspace_id,
                WorkspaceTemplate.is_active == True,
            )
            .values(is_active=False)
        )
        template = await self.get(template_id)
        if template and template.workspace_id == workspace_id:
            template.is_active = True
            await self.db.commit()
            await self.db.refresh(template)
        return template

    async def delete(self, template_id: str) -> bool:
        template = await self.get(template_id)
        if not template:
            return False
        await self.db.delete(template)
        await self.db.commit()
        return True


async def parse_template_content(file_content: str) -> dict[str, Any]:
    """Parse template file content using LLM to extract structured spec."""
    try:
        from src.models.factory import create_chat_model
        from src.models.router import route_model

        model_id = route_model(
            preferred_categories=("utility", "gen"),
            allowed_categories=("utility", "gen", "tool"),
            require_tools=False,
        )
        model = create_chat_model(model_id, temperature=0.1)
        prompt = TEMPLATE_PARSE_PROMPT.format(content=file_content[:8000])
        response = await model.ainvoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)

        text = content.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        return json.loads(text)
    except Exception:
        logger.exception("Failed to parse template content")
        return {}
