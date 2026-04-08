"""Literature navigation tools for workspace-scoped retrieval."""

from __future__ import annotations

import json

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from src.academic.literature.index_service import IndexService
from src.database import get_db_session


class ListWorkspaceLiteratureTocInput(BaseModel):
    """Input for listing workspace TOC summary."""

    workspace_id: str = Field(description="Workspace id")


class SearchWorkspaceLiteratureInput(BaseModel):
    """Input for searching sections inside a workspace."""

    workspace_id: str = Field(description="Workspace id")
    query: str = Field(description="Search query for section title/content")
    limit: int = Field(default=8, ge=1, le=20, description="Maximum matches")


class ReadWorkspaceLiteratureSectionInput(BaseModel):
    """Input for reading one paper section."""

    paper_id: str = Field(description="Paper id")
    section_path: str | None = Field(
        default=None,
        description="Section path such as 1 or 2.3.1",
    )
    section_title: str | None = Field(
        default=None,
        description="Section title fuzzy match when path is unknown",
    )
    workspace_id: str | None = Field(
        default=None,
        description="Optional workspace scope for disambiguation",
    )


@tool("list_workspace_literature_toc", args_schema=ListWorkspaceLiteratureTocInput)
async def list_workspace_literature_toc_tool(workspace_id: str) -> str:
    """List TOC summary for all papers in a workspace."""
    async with get_db_session() as db:
        index_service = IndexService(db)
        summary = await index_service.get_workspace_toc_summary(workspace_id)
    return summary or "该工作区暂无可用文献目录。"


@tool("search_workspace_literature", args_schema=SearchWorkspaceLiteratureInput)
async def search_workspace_literature_tool(
    workspace_id: str,
    query: str,
    limit: int = 8,
) -> str:
    """Search paper sections by title/content in one workspace."""
    async with get_db_session() as db:
        index_service = IndexService(db)
        records = await index_service.search_workspace_sections(
            workspace_id,
            query,
            limit=limit,
        )
    return json.dumps(
        {
            "workspace_id": workspace_id,
            "query": query,
            "count": len(records),
            "results": records,
        },
        ensure_ascii=False,
    )


@tool(
    "read_workspace_literature_section",
    args_schema=ReadWorkspaceLiteratureSectionInput,
)
async def read_workspace_literature_section_tool(
    paper_id: str,
    section_path: str | None = None,
    section_title: str | None = None,
    workspace_id: str | None = None,
) -> str:
    """Read one section content by section_path or section_title."""
    normalized_path = str(section_path or "").strip()
    normalized_title = str(section_title or "").strip()
    if not normalized_path and not normalized_title:
        return "请至少提供 section_path 或 section_title。"

    async with get_db_session() as db:
        index_service = IndexService(db)
        if normalized_path:
            section = await index_service.get_paper_section(
                paper_id=paper_id,
                section_path=normalized_path,
                workspace_id=workspace_id,
            )
        else:
            section = await index_service.get_paper_section_by_title(
                paper_id=paper_id,
                section_title=normalized_title,
                workspace_id=workspace_id,
            )

    if not section:
        return "未找到对应章节。"

    title = str(section.get("title") or normalized_path or normalized_title)
    content = str(section.get("content") or "")
    if not content.strip():
        return f"章节《{title}》暂无可读取内容。"
    return f"## {title}\n\n{content}"
