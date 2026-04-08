# Workspace Template System Implementation Plan

> 归档说明: 本文档为历史阶段性计划快照，可能包含已过时路由、线程模型或状态描述。当前实现请以 `docs/product/workspace-current-state.md` 与相关当前契约文档为准。

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Allow users to upload writing templates (Word/LaTeX/text) via chat, which the system parses and applies to the entire writing pipeline (outline → writing → compilation).

**Architecture:** New `WorkspaceTemplate` DB model stores parsed template specs. Templates are uploaded via chat attachments (`kind="template"`), parsed by LLM into structured JSON, and injected into the system prompt via `WorkspaceContextMiddleware`. The compile_export feature uses the template's `latex_preamble` when available.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 (async), PostgreSQL JSONB, Alembic

---

### Task 1: Create WorkspaceTemplate database model

**Files:**
- Create: `backend/src/database/models/workspace_template.py`
- Modify: `backend/src/database/models/__init__.py`

**Step 1: Create the model file**

```python
"""Workspace template model for storing parsed writing templates."""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base, TimestampMixin, UUIDMixin


class WorkspaceTemplate(UUIDMixin, TimestampMixin, Base):
    """A parsed writing template attached to a workspace.

    Templates influence the entire writing pipeline: outline structure,
    content generation, and final compilation/export.
    """

    __tablename__ = "workspace_templates"

    workspace_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(
        String(32), nullable=False, default="thesis",
    )
    source_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="text",
    )
    source_file_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    structure: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    format_spec: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    content_guidelines: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    latex_preamble: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
```

**Step 2: Export in models __init__.py**

Add `WorkspaceTemplate` to the imports and `__all__` list in `backend/src/database/models/__init__.py`.

**Step 3: Commit**

```bash
git add backend/src/database/models/workspace_template.py backend/src/database/models/__init__.py
git commit -m "feat: add WorkspaceTemplate database model"
```

---

### Task 2: Create Alembic migration

**Files:**
- Create: `backend/alembic/versions/016_add_workspace_templates.py`

**Step 1: Create migration file**

Follow the existing migration pattern (check `015_drop_paper_chunk_embedding.py` for reference). The migration should:
1. Check if `workspace_templates` table already exists
2. Create the table with all columns
3. Create index on `workspace_id`

```python
"""Add workspace_templates table.

Revision ID: 016_add_workspace_templates
Revises: 015_drop_paper_chunk_embedding
"""

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "016_add_workspace_templates"
down_revision: Union[str, None] = "015_drop_paper_chunk_embedding"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def _table_names() -> set[str]:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return set(inspector.get_table_names())


def upgrade() -> None:
    if "workspace_templates" in _table_names():
        return

    op.create_table(
        "workspace_templates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(32), nullable=False, server_default="thesis"),
        sa.Column("source_type", sa.String(16), nullable=False, server_default="text"),
        sa.Column("source_file_path", sa.Text, nullable=True),
        sa.Column("structure", JSONB, nullable=True),
        sa.Column("format_spec", JSONB, nullable=True),
        sa.Column("content_guidelines", JSONB, nullable=True),
        sa.Column("latex_preamble", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("is_builtin", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_workspace_templates_workspace_id", "workspace_templates", ["workspace_id"])


def downgrade() -> None:
    if "workspace_templates" in _table_names():
        op.drop_index("ix_workspace_templates_workspace_id")
        op.drop_table("workspace_templates")
```

**Step 2: Commit**

```bash
git add backend/alembic/versions/016_add_workspace_templates.py
git commit -m "feat: add workspace_templates migration"
```

---

### Task 3: Create TemplateService

**Files:**
- Create: `backend/src/services/template_service.py`

**Step 1: Create the service**

```python
"""Template service for workspace template CRUD and parsing."""

from __future__ import annotations

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
        # Deactivate all
        await self.db.execute(
            update(WorkspaceTemplate)
            .where(
                WorkspaceTemplate.workspace_id == workspace_id,
                WorkspaceTemplate.is_active == True,
            )
            .values(is_active=False)
        )
        # Activate target
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

        import json
        text = content.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        return json.loads(text)
    except Exception:
        logger.exception("Failed to parse template content")
        return {}
```

**Step 2: Commit**

```bash
git add backend/src/services/template_service.py
git commit -m "feat: add TemplateService with CRUD and LLM-based template parsing"
```

---

### Task 4: Create templates API router

**Files:**
- Create: `backend/src/gateway/routers/templates.py`
- Modify: `backend/src/gateway/app.py`
- Modify: `backend/src/gateway/deps/__init__.py`
- Modify: `backend/src/gateway/deps/academic.py`

**Step 1: Add dependency injection**

In `deps/academic.py`, add:
```python
async def get_template_service(db: AsyncSession = Depends(get_db)) -> TemplateService:
    from src.services.template_service import TemplateService
    return TemplateService(db)
```

Export in `deps/__init__.py`.

**Step 2: Create the router**

```python
"""Templates router for workspace template management."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from src.academic.services.workspace_service import WorkspaceService
from src.services.template_service import TemplateService, parse_template_content
from src.database import User
from src.gateway.auth_dependencies import get_current_user
from src.gateway.deps import get_template_service, get_workspace_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["templates"])

TEMPLATE_EXTENSIONS = {".docx", ".tex", ".txt", ".md", ".cls", ".sty", ".markdown"}
MAX_TEMPLATE_SIZE = 10 * 1024 * 1024  # 10MB


class TemplateResponse(BaseModel):
    id: str
    name: str
    category: str
    sourceType: str
    structure: dict | None
    formatSpec: dict | None
    contentGuidelines: dict | None
    isActive: bool
    isBuiltin: bool


class TemplatesListResponse(BaseModel):
    templates: list[TemplateResponse]


def _to_response(t) -> TemplateResponse:
    return TemplateResponse(
        id=t.id,
        name=t.name,
        category=t.category,
        sourceType=t.source_type,
        structure=t.structure,
        formatSpec=t.format_spec,
        contentGuidelines=t.content_guidelines,
        isActive=t.is_active,
        isBuiltin=t.is_builtin,
    )


@router.get("/workspaces/{workspace_id}/templates", response_model=TemplatesListResponse)
async def list_templates(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    template_service: TemplateService = Depends(get_template_service),
):
    workspace = await workspace_service.get(workspace_id)
    if not workspace:
        raise HTTPException(404, "Workspace not found")
    if str(workspace.user_id) != str(current_user.id):
        raise HTTPException(403, "Access denied")
    templates = await template_service.list_by_workspace(workspace_id)
    return TemplatesListResponse(templates=[_to_response(t) for t in templates])


@router.get("/workspaces/{workspace_id}/templates/active", response_model=TemplateResponse | None)
async def get_active_template(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    template_service: TemplateService = Depends(get_template_service),
):
    workspace = await workspace_service.get(workspace_id)
    if not workspace:
        raise HTTPException(404, "Workspace not found")
    if str(workspace.user_id) != str(current_user.id):
        raise HTTPException(403, "Access denied")
    template = await template_service.get_active(workspace_id)
    return _to_response(template) if template else None


@router.post("/workspaces/{workspace_id}/templates/upload", response_model=TemplateResponse)
async def upload_template(
    workspace_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    template_service: TemplateService = Depends(get_template_service),
):
    workspace = await workspace_service.get(workspace_id)
    if not workspace:
        raise HTTPException(404, "Workspace not found")
    if str(workspace.user_id) != str(current_user.id):
        raise HTTPException(403, "Access denied")

    # Validate file
    import os
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in TEMPLATE_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type: {ext}")

    content_bytes = await file.read()
    if len(content_bytes) > MAX_TEMPLATE_SIZE:
        raise HTTPException(400, "File too large (max 10MB)")

    # Save file
    from src.config import get_data_dir
    template_dir = os.path.join(get_data_dir(), "workspace_uploads", workspace_id, "templates")
    os.makedirs(template_dir, exist_ok=True)
    file_path = os.path.join(template_dir, file.filename or "template" + ext)
    with open(file_path, "wb") as f:
        f.write(content_bytes)

    # Read text content for parsing
    file_content = ""
    if ext in (".txt", ".md", ".markdown", ".tex", ".cls", ".sty"):
        try:
            file_content = content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            file_content = content_bytes.decode("latin-1")
    elif ext == ".docx":
        try:
            import docx
            from io import BytesIO
            doc = docx.Document(BytesIO(content_bytes))
            file_content = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except Exception:
            file_content = ""

    # Parse with LLM
    parsed = await parse_template_content(file_content) if file_content else {}

    # Determine source_type and extract latex preamble
    source_type = ext.lstrip(".")
    if source_type in ("cls", "sty"):
        source_type = "latex"
    latex_preamble = None
    if ext in (".tex", ".cls", ".sty"):
        latex_preamble = file_content

    template = await template_service.create(
        workspace_id=workspace_id,
        name=parsed.get("name") or file.filename or "未命名模板",
        category=workspace.type,
        source_type=source_type,
        source_file_path=file_path,
        structure=parsed.get("structure"),
        format_spec=parsed.get("format_spec"),
        content_guidelines=parsed.get("content_guidelines"),
        latex_preamble=latex_preamble,
    )
    return _to_response(template)


@router.put("/workspaces/{workspace_id}/templates/{template_id}/activate", response_model=TemplateResponse)
async def activate_template(
    workspace_id: str,
    template_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    template_service: TemplateService = Depends(get_template_service),
):
    workspace = await workspace_service.get(workspace_id)
    if not workspace:
        raise HTTPException(404, "Workspace not found")
    if str(workspace.user_id) != str(current_user.id):
        raise HTTPException(403, "Access denied")
    template = await template_service.activate(template_id, workspace_id)
    if not template:
        raise HTTPException(404, "Template not found")
    return _to_response(template)


@router.delete("/workspaces/{workspace_id}/templates/{template_id}")
async def delete_template(
    workspace_id: str,
    template_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    template_service: TemplateService = Depends(get_template_service),
):
    workspace = await workspace_service.get(workspace_id)
    if not workspace:
        raise HTTPException(404, "Workspace not found")
    if str(workspace.user_id) != str(current_user.id):
        raise HTTPException(403, "Access denied")
    deleted = await template_service.delete(template_id)
    if not deleted:
        raise HTTPException(404, "Template not found")
    return {"status": "deleted"}
```

**Step 3: Register router in app.py**

Add `templates` to the import line and add `app.include_router(templates.router, prefix="/api", tags=["templates"])`.

**Step 4: Commit**

```bash
git add backend/src/gateway/routers/templates.py backend/src/gateway/app.py \
  backend/src/gateway/deps/__init__.py backend/src/gateway/deps/academic.py
git commit -m "feat: add templates API with upload, list, activate, delete endpoints"
```

---

### Task 5: Inject template context into system prompt

**Files:**
- Modify: `backend/src/agents/thread_state.py`
- Modify: `backend/src/agents/middlewares/workspace_context.py`
- Modify: `backend/src/agents/lead_agent/agent.py`

**Step 1: Add template_context to ThreadState**

In `thread_state.py`, add to the ThreadState TypedDict:
```python
template_context: NotRequired[dict[str, Any] | None]
```

And initialize it in `create_thread_state`:
```python
"template_context": payload.get("template_context"),
```

**Step 2: Load template in WorkspaceContextMiddleware**

In `workspace_context.py`, after loading workspace data, also load the active template:

```python
# After existing workspace loading logic:
template_dict = None
try:
    from src.services.template_service import TemplateService
    template_service = TemplateService(self._get_db_session())
    # Use a lightweight query approach instead
    from src.database import get_db_session
    async with get_db_session() as db:
        ts = TemplateService(db)
        active_template = await ts.get_active(workspace_id)
        if active_template:
            template_dict = {
                "name": active_template.name,
                "structure": active_template.structure,
                "format_spec": active_template.format_spec,
                "content_guidelines": active_template.content_guidelines,
            }
except Exception:
    logger.warning("Failed to load workspace template")

# Add to return dict:
updates["template_context"] = template_dict
```

NOTE: The exact integration depends on how the middleware gets its DB session. Read the current middleware code and adapt accordingly — the middleware may already have a DB session from its service dependency.

**Step 3: Inject into system prompt**

In `apply_prompt_template` in `agent.py`, after the discipline_norms section, add:

```python
    # Add template context
    template_context = state.get("template_context")
    if template_context:
        base_prompt += f"\n\n## 写作模板规范\n\n当前工作区已配置写作模板：{template_context.get('name', '自定义模板')}"

        structure = template_context.get("structure")
        if structure and isinstance(structure, dict):
            chapters = structure.get("chapters", [])
            if chapters:
                base_prompt += "\n\n### 章节结构要求"
                for ch in chapters:
                    title = ch.get("title", "")
                    desc = ch.get("description", "")
                    wc = ch.get("suggested_word_count", "")
                    required = "必需" if ch.get("required") else "可选"
                    line = f"\n- {title} ({required})"
                    if desc:
                        line += f"：{desc}"
                    if wc:
                        line += f" [{wc}字]"
                    base_prompt += line

        format_spec = template_context.get("format_spec")
        if format_spec and isinstance(format_spec, dict):
            base_prompt += "\n\n### 排版格式"
            for key, value in format_spec.items():
                if value:
                    label = key.replace("_", " ").title()
                    base_prompt += f"\n- {label}: {value}"

        content_guidelines = template_context.get("content_guidelines")
        if content_guidelines and isinstance(content_guidelines, dict):
            base_prompt += "\n\n### 内容要求"
            for key, value in content_guidelines.items():
                if value:
                    label = key.replace("_", " ").title()
                    if isinstance(value, list):
                        for item in value:
                            if isinstance(item, dict):
                                base_prompt += f"\n- {item.get('chapter', '')}: {item.get('requirement', '')}"
                    else:
                        base_prompt += f"\n- {label}: {value}"

        base_prompt += "\n\n请严格按照以上模板规范生成内容。"
```

**Step 4: Commit**

```bash
git add backend/src/agents/thread_state.py \
  backend/src/agents/middlewares/workspace_context.py \
  backend/src/agents/lead_agent/agent.py
git commit -m "feat: inject workspace template context into system prompt"
```

---

### Task 6: Integrate template with compile_export

**Files:**
- Modify: `backend/src/workspace_features/services/thesis_feature_service.py`
- Modify: `backend/src/thesis/latex_template.py`

**Step 1: Update compile flow to use template's latex_preamble**

In `thesis_feature_service.py`, in the `build_compile_payload` function, before calling `get_template()`, check if the workspace has an active template with `latex_preamble`:

```python
# Load workspace template if available
template_preamble = None
try:
    from src.database import get_db_session
    from src.services.template_service import TemplateService
    async with get_db_session() as db:
        ts = TemplateService(db)
        active_template = await ts.get_active(workspace_id)
        if active_template and active_template.latex_preamble:
            template_preamble = active_template.latex_preamble
except Exception:
    logger.warning("Failed to load template for compilation")

# Use template preamble or default
if template_preamble:
    latex_template = template_preamble
else:
    latex_template = get_template(output_language)
```

**Step 2: Commit**

```bash
git add backend/src/workspace_features/services/thesis_feature_service.py
git commit -m "feat: use workspace template latex_preamble for compilation when available"
```

---

### Task 7: Add frontend template types and API

**Files:**
- Modify: `frontend/lib/api/types.ts`
- Modify: `frontend/lib/api/workspace.ts`

**Step 1: Add TypeScript types**

```typescript
export interface WorkspaceTemplate {
  id: string;
  name: string;
  category: string;
  sourceType: string;
  structure: Record<string, unknown> | null;
  formatSpec: Record<string, unknown> | null;
  contentGuidelines: Record<string, unknown> | null;
  isActive: boolean;
  isBuiltin: boolean;
}
```

**Step 2: Add API functions**

```typescript
export async function getWorkspaceTemplates(workspaceId: string): Promise<{ templates: WorkspaceTemplate[] }> {
  const response = await api.get(`/workspaces/${workspaceId}/templates`);
  return response.data;
}

export async function getActiveTemplate(workspaceId: string): Promise<WorkspaceTemplate | null> {
  const response = await api.get(`/workspaces/${workspaceId}/templates/active`);
  return response.data;
}

export async function uploadTemplate(workspaceId: string, file: File): Promise<WorkspaceTemplate> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await api.post(`/workspaces/${workspaceId}/templates/upload`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
}

export async function deleteTemplate(workspaceId: string, templateId: string): Promise<void> {
  await api.delete(`/workspaces/${workspaceId}/templates/${templateId}`);
}
```

**Step 3: Commit**

```bash
git add frontend/lib/api/types.ts frontend/lib/api/workspace.ts
git commit -m "feat: add frontend template types and API functions"
```

---

### Task 8: Build verification

**Step 1:** `cd frontend && npx tsc --noEmit`
**Step 2:** `cd frontend && npx next build`
**Step 3:** Fix any errors
**Step 4:** Final commit if needed
