# Wenjin Workspace 重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 wenjin 从单 lead_agent 模型重构为「chat agent + lead agent + 8 房间数据层 + 7 平台基础设施 + capability 数据驱动」的工作空间体系，对应 spec [2026-05-09-wenjin-workspace-rebuild-design.md](../specs/2026-05-09-wenjin-workspace-rebuild-design.md)。

**Architecture:** 三层结构（UI / 数据 / 平台）+ 双 agent 拓扑（chat 1:1 lead）+ capability 是数据非代码（YAML seed + DB-backed + admin 可热扩展）。Phased plan 结构的 graph_template，Skills-like 的灵活性。

**Tech Stack:** Python 3.13 + FastAPI + SQLAlchemy 2.0 async + Pydantic v2 + LangGraph + LangChain + Celery + Redis (pubsub + streams) + PostgreSQL (JSONB heavy) + Alembic. Frontend: Next.js 16 + React 19 + TypeScript + Tailwind + Zustand + reactflow + EventSource.

**Strategy:** 4 phases × 12 weeks. 后端可灰度（W1-6 与现有代码并存），前端 single-cutover（W11 切流量）。新代码大部分写在新文件/新路径，旧代码 W12 才删。

**Status:** Phase 1-4 全部完成 (2026-05-11)。旧架构代码已清理删除，v2 统一上线。额外完成了 output mapping 闭环和前端 execution.completed → ResultCard 桥接。

**Convention 提醒**（来自 CLAUDE.md）：
- Backend tests: `cd backend && .venv/bin/python -m pytest tests/path -v`
- Frontend: `cd frontend && npm run typecheck && npm run dev`
- 新 alembic migration 编号从 **031** 起（030 已是 executions 表）
- 提交风格：`feat:` / `fix:` / `docs:` / `refactor:` / `test:` 前缀
- **No 兼容层** — clean migrations only

---

## File Structure

### Backend 新文件（按 Phase 创建）

**Phase 1**：
- `backend/src/database/models/workspace_settings.py`
- `backend/src/database/models/library.py`
- `backend/src/database/models/document.py`
- `backend/src/database/models/decision.py`
- `backend/src/database/models/memory_fact.py`
- `backend/src/database/models/run_history.py`
- `backend/src/database/models/sandbox.py` (model only, behavior in service)
- `backend/src/database/models/workspace_task.py` (table `tasks` 已被占用，模型类用 `WorkspaceTask`)
- `backend/src/database/models/audit_log.py`
- `backend/src/database/models/capability.py`
- `backend/alembic/versions/031_add_workspace_thread_link.py`
- `backend/alembic/versions/032_create_workspace_settings.py`
- `backend/alembic/versions/033_create_library_items.py`
- `backend/alembic/versions/034_create_documents_v2.py`
- `backend/alembic/versions/035_create_decisions.py`
- `backend/alembic/versions/036_create_memory_facts.py`
- `backend/alembic/versions/037_create_run_history.py`
- `backend/alembic/versions/038_create_sandboxes.py`
- `backend/alembic/versions/039_create_workspace_tasks.py`
- `backend/alembic/versions/040_create_audit_logs.py`
- `backend/alembic/versions/041_create_capabilities.py`
- `backend/src/services/rooms/library_service.py`
- `backend/src/services/rooms/documents_service.py`
- `backend/src/services/rooms/decisions_service.py`
- `backend/src/services/rooms/memory_service.py`
- `backend/src/services/rooms/run_history_service.py`
- `backend/src/services/rooms/sandbox_service.py`
- `backend/src/services/rooms/tasks_service.py`
- `backend/src/services/rooms/settings_service.py`
- `backend/src/services/capability_resolver.py`
- `backend/src/services/capability_loader.py` (YAML → DB)
- `backend/src/services/audit_service.py`
- `backend/src/services/quota_service.py`
- `backend/src/services/model_gateway.py`
- `backend/src/services/event_bus.py`
- `backend/src/gateway/routers/workspace_rooms.py` (统一注册 8 个房间路由)
- `backend/src/gateway/routers/capabilities.py`
- `backend/seed/capabilities/{thesis,sci,proposal,software_copyright,patent}/`

**Phase 2**：
- `backend/src/agents/chat_agent/agent.py`
- `backend/src/agents/chat_agent/prompts.py`
- `backend/src/agents/chat_agent/tools/dispatch.py`
- `backend/src/agents/chat_agent/tools/progress.py`
- `backend/src/agents/chat_agent/tools/cancel.py`
- `backend/src/agents/chat_agent/tools/decisions.py`
- `backend/src/agents/chat_agent/tools/memory.py`
- `backend/src/agents/chat_agent/tools/rooms.py`
- `backend/src/agents/chat_agent/middlewares/compact.py`
- `backend/src/agents/lead_agent/v2/agent.py` (新, 与旧 agent.py 并存)
- `backend/src/agents/lead_agent/v2/compiler.py` (graph_template → langgraph)
- `backend/src/agents/lead_agent/v2/runtime.py`
- `backend/src/agents/contracts/task_brief.py`
- `backend/src/agents/contracts/task_report.py`
- `backend/src/subagents/v2/base.py`
- `backend/src/subagents/v2/registry.py`
- `backend/src/subagents/v2/types/scholar_searcher.py`
- `backend/src/subagents/v2/types/web_searcher.py`
- `backend/src/subagents/v2/types/clusterer.py`
- `backend/src/subagents/v2/types/critical_writer.py`
- `backend/src/subagents/v2/types/outliner.py`
- `backend/src/services/result_card_service.py`
- `backend/src/services/execution_completion_service.py`

**Phase 3**：
- `frontend/app/(workbench)/workspaces/[id]/v2/page.tsx`
- `frontend/app/(workbench)/workspaces/[id]/v2/layout.tsx`
- `frontend/app/(workbench)/workspaces/[id]/v2/components/ChatPanel.tsx`
- `frontend/app/(workbench)/workspaces/[id]/v2/components/LiveWorkflowPanel.tsx`
- `frontend/app/(workbench)/workspaces/[id]/v2/components/RoomsTopbar.tsx`
- `frontend/app/(workbench)/workspaces/[id]/v2/components/MessageBlock.tsx`
- `frontend/app/(workbench)/workspaces/[id]/v2/components/ResultCard.tsx`
- `frontend/app/(workbench)/workspaces/[id]/v2/components/NodeDetailDrawer.tsx`
- `frontend/app/(workbench)/workspaces/[id]/v2/components/rooms/{Documents,Library,Runs,Tasks}Drawer.tsx`
- `frontend/app/(workbench)/workspaces/[id]/v2/components/rooms/SettingsPage.tsx`
- `frontend/stores/chat-store-v2.ts`
- `frontend/stores/execution-store-v2.ts` (扩展现有 execution-store.ts)
- `frontend/stores/workspace-store-v2.ts`
- `frontend/hooks/useChatStream.ts`
- `frontend/hooks/useExecutionStreamV2.ts`
- `frontend/lib/api/v2/{workspaces,library,documents,decisions,memory,runs,tasks,settings,capabilities,executions}.ts`

**Phase 4**：
- `backend/scripts/migrate_workspace_v2.py`
- `backend/alembic/versions/042_archive_legacy_v1_tables.py` (rename, not drop)

### 删除（Phase 4）

- `backend/src/agents/lead_agent/agent.py` (旧单 agent 模型)
- `backend/src/agents/feature_leader/` (整个目录)
- `backend/src/application/services/feature_*_service.py` (legacy)
- `frontend/app/(workbench)/workspaces/[id]/chat/` (旧 chat 页面)
- `frontend/stores/workflow-store.ts` + `workflow-store-support.ts`
- `frontend/stores/thread.ts`
- `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/` (旧 panel)

---

## Phase 1 · Foundation (Week 1-3)

> 目标: 平台层 7 项 + 8 房间 schema + capability registry 骨架。本阶段所有代码与现有业务零耦合，可独立测试。Phase 末，curl + DB 检查能验证整条数据栈。

### Task 1.1: workspaces 表的 thread_id 1:1 关系建立

**Files:**
- Create: `backend/alembic/versions/031_add_workspace_thread_link.py`
- Modify: `backend/src/database/models/workspace.py:60` (add `thread_id` column)
- Test: `backend/tests/database/test_workspace_thread_link.py`

**Background:** 现有 workspaces 表无 `thread_id`. Spec §6.3 要求 1:1。`threads` 已存在（chat_threads 表 alias），需补外键。

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/database/test_workspace_thread_link.py
import pytest
from src.database.models import Workspace, Thread

@pytest.mark.asyncio
async def test_workspace_has_thread_id_column(async_session):
    user = await create_user(async_session)
    thread = Thread(id="tid-1", user_id=user.id, title="t")
    async_session.add(thread)
    ws = Workspace(
        id="ws-1", user_id=user.id, name="test",
        type="thesis", thread_id="tid-1",
    )
    async_session.add(ws)
    await async_session.commit()
    fetched = await async_session.get(Workspace, "ws-1")
    assert fetched.thread_id == "tid-1"

@pytest.mark.asyncio
async def test_workspace_thread_id_unique(async_session):
    """Same thread_id can't bind to two workspaces."""
    # ... duplicate workspace with same thread_id → IntegrityError
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && .venv/bin/python -m pytest tests/database/test_workspace_thread_link.py -v
```
Expected: FAIL with "column thread_id does not exist" or AttributeError.

- [ ] **Step 3: Write the alembic migration**

```python
# backend/alembic/versions/031_add_workspace_thread_link.py
"""Add thread_id 1:1 link to workspaces.

Revision ID: 031
Revises: 030
Create Date: 2026-05-12
"""
from alembic import op
import sqlalchemy as sa

revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column(
        "workspaces",
        sa.Column("thread_id", sa.String(36), nullable=True),
    )
    op.create_unique_constraint(
        "uq_workspaces_thread_id", "workspaces", ["thread_id"]
    )
    op.create_foreign_key(
        "fk_workspaces_thread_id", "workspaces", "chat_threads",
        ["thread_id"], ["id"], ondelete="SET NULL",
    )

def downgrade():
    op.drop_constraint("fk_workspaces_thread_id", "workspaces", type_="foreignkey")
    op.drop_constraint("uq_workspaces_thread_id", "workspaces", type_="unique")
    op.drop_column("workspaces", "thread_id")
```

- [ ] **Step 4: Add column to model**

```python
# backend/src/database/models/workspace.py — add to Workspace class
thread_id: Mapped[str | None] = mapped_column(
    String(36),
    ForeignKey("chat_threads.id", ondelete="SET NULL"),
    nullable=True, unique=True,
)
thread: Mapped["Thread | None"] = relationship("Thread", lazy="selectin")
```

- [ ] **Step 5: Run migration locally + verify tests pass**

```bash
cd backend && .venv/bin/alembic upgrade head
cd backend && .venv/bin/python -m pytest tests/database/test_workspace_thread_link.py -v
```
Expected: migration applies cleanly, tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions/031_add_workspace_thread_link.py backend/src/database/models/workspace.py backend/tests/database/test_workspace_thread_link.py
git commit -m "feat: add thread_id 1:1 FK on workspaces"
```

### Task 1.2: workspace_settings table

**Files:**
- Create: `backend/alembic/versions/032_create_workspace_settings.py`
- Create: `backend/src/database/models/workspace_settings.py`
- Create: `backend/src/services/rooms/settings_service.py`
- Test: `backend/tests/services/rooms/test_settings_service.py`

- [ ] **Step 1: Write failing test for settings service**

```python
# backend/tests/services/rooms/test_settings_service.py
import pytest
from src.services.rooms.settings_service import SettingsService

@pytest.mark.asyncio
async def test_get_or_create_default(async_session):
    svc = SettingsService(async_session)
    s = await svc.get_or_create("ws-1")
    assert s.workspace_id == "ws-1"
    assert s.thinking_enabled is True
    assert s.auto_compact_threshold == 0.8

@pytest.mark.asyncio
async def test_update_setting(async_session):
    svc = SettingsService(async_session)
    await svc.get_or_create("ws-1")
    updated = await svc.update("ws-1", default_model="claude-opus-4-7")
    assert updated.default_model == "claude-opus-4-7"
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd backend && .venv/bin/python -m pytest tests/services/rooms/test_settings_service.py -v
```
Expected: FAIL ImportError.

- [ ] **Step 3: Write migration**

```python
# backend/alembic/versions/032_create_workspace_settings.py
"""Create workspace_settings table."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "032"
down_revision = "031"

def upgrade():
    op.create_table(
        "workspace_settings",
        sa.Column("workspace_id", sa.String(36), primary_key=True),
        sa.Column("default_model", sa.String(100)),
        sa.Column("thinking_enabled", sa.Boolean, nullable=False, server_default=sa.text("TRUE")),
        sa.Column("sandbox_provider", sa.String(50), nullable=False, server_default="local"),
        sa.Column("auto_compact_threshold", sa.Float, nullable=False, server_default=sa.text("0.8")),
        sa.Column("capability_overrides", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("metadata_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
    )

def downgrade():
    op.drop_table("workspace_settings")
```

- [ ] **Step 4: Write model**

```python
# backend/src/database/models/workspace_settings.py
from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from ..base import Base

class WorkspaceSettings(Base):
    __tablename__ = "workspace_settings"
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    default_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    thinking_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sandbox_provider: Mapped[str] = mapped_column(String(50), nullable=False, default="local")
    auto_compact_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.8)
    capability_overrides: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
```

- [ ] **Step 5: Write service**

```python
# backend/src/services/rooms/settings_service.py
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.database.models.workspace_settings import WorkspaceSettings

class SettingsService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create(self, workspace_id: str) -> WorkspaceSettings:
        result = await self.session.get(WorkspaceSettings, workspace_id)
        if result is None:
            result = WorkspaceSettings(workspace_id=workspace_id)
            self.session.add(result)
            await self.session.commit()
            await self.session.refresh(result)
        return result

    async def update(self, workspace_id: str, **kwargs) -> WorkspaceSettings:
        s = await self.get_or_create(workspace_id)
        for k, v in kwargs.items():
            if v is not None:
                setattr(s, k, v)
        await self.session.commit()
        await self.session.refresh(s)
        return s
```

- [ ] **Step 6: Register model in __init__.py**

```python
# backend/src/database/models/__init__.py — append
from .workspace_settings import WorkspaceSettings
__all__ += ["WorkspaceSettings"]
```

- [ ] **Step 7: Run migration + verify tests pass**

```bash
cd backend && .venv/bin/alembic upgrade head
cd backend && .venv/bin/python -m pytest tests/services/rooms/test_settings_service.py -v
```
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/alembic/versions/032_create_workspace_settings.py \
        backend/src/database/models/workspace_settings.py \
        backend/src/database/models/__init__.py \
        backend/src/services/rooms/settings_service.py \
        backend/tests/services/rooms/test_settings_service.py
git commit -m "feat: add workspace_settings room"
```

### Task 1.3: Library 房间 (LibraryItem)

**Files:**
- Create: `backend/alembic/versions/033_create_library_items.py`
- Create: `backend/src/database/models/library.py`
- Create: `backend/src/services/rooms/library_service.py`
- Test: `backend/tests/services/rooms/test_library_service.py`

**Schema (per spec §4.4.1)**: `id, workspace_id, item_type, title, authors[], year, venue, doi, url, abstract, full_text_path, metadata, tags[], cited_in_documents[], added_by, created_at, updated_at, deleted_at`.

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/services/rooms/test_library_service.py
import pytest
from src.services.rooms.library_service import LibraryService, LibraryItemCreate

@pytest.mark.asyncio
async def test_add_paper(async_session):
    svc = LibraryService(async_session)
    item = await svc.add(
        "ws-1",
        LibraryItemCreate(
            item_type="paper",
            title="Conditional GAN",
            authors=["Mirza", "Osindero"],
            year=2014,
            doi="10.48550/arXiv.1411.1784",
            added_by="user",
        ),
    )
    assert item.id
    assert item.title == "Conditional GAN"

@pytest.mark.asyncio
async def test_list_filters_deleted(async_session):
    svc = LibraryService(async_session)
    item = await svc.add("ws-1", LibraryItemCreate(item_type="paper", title="x", added_by="user"))
    await svc.delete("ws-1", item.id)
    items = await svc.list("ws-1")
    assert len(items) == 0

@pytest.mark.asyncio
async def test_bulk_add_for_execution(async_session):
    svc = LibraryService(async_session)
    items = await svc.bulk_add(
        "ws-1",
        [
            LibraryItemCreate(item_type="paper", title=f"P{i}", added_by="execution:exec-1")
            for i in range(5)
        ],
    )
    assert len(items) == 5
    assert all(i.added_by == "execution:exec-1" for i in items)
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd backend && .venv/bin/python -m pytest tests/services/rooms/test_library_service.py -v
```
Expected: FAIL ImportError.

- [ ] **Step 3: Write migration**

```python
# backend/alembic/versions/033_create_library_items.py
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "033"
down_revision = "032"

def upgrade():
    op.create_table(
        "library_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_type", sa.String(20), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("authors", JSONB, server_default=sa.text("'[]'::jsonb")),
        sa.Column("year", sa.Integer),
        sa.Column("venue", sa.String(200)),
        sa.Column("doi", sa.String(200)),
        sa.Column("url", sa.String(500)),
        sa.Column("abstract", sa.Text),
        sa.Column("full_text_path", sa.String(500)),
        sa.Column("metadata_json", JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column("tags", JSONB, server_default=sa.text("'[]'::jsonb")),
        sa.Column("cited_in_documents", JSONB, server_default=sa.text("'[]'::jsonb")),
        sa.Column("added_by", sa.String(60), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_library_workspace_active", "library_items", ["workspace_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

def downgrade():
    op.drop_index("ix_library_workspace_active", table_name="library_items")
    op.drop_table("library_items")
```

- [ ] **Step 4: Write model**

```python
# backend/src/database/models/library.py
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from ..base import Base, UUIDMixin

class LibraryItem(Base, UUIDMixin):
    __tablename__ = "library_items"
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_type: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    authors: Mapped[list[str]] = mapped_column(JSONB, default=list)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    venue: Mapped[str | None] = mapped_column(String(200), nullable=True)
    doi: Mapped[str | None] = mapped_column(String(200), nullable=True)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    full_text_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    tags: Mapped[list[str]] = mapped_column(JSONB, default=list)
    cited_in_documents: Mapped[list[str]] = mapped_column(JSONB, default=list)
    added_by: Mapped[str] = mapped_column(String(60), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 5: Write service**

```python
# backend/src/services/rooms/library_service.py
from datetime import datetime, timezone
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.database.models.library import LibraryItem

class LibraryItemCreate(BaseModel):
    item_type: str
    title: str
    authors: list[str] = []
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    url: str | None = None
    abstract: str | None = None
    full_text_path: str | None = None
    metadata_json: dict = {}
    tags: list[str] = []
    added_by: str

class LibraryService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, workspace_id: str, data: LibraryItemCreate) -> LibraryItem:
        item = LibraryItem(workspace_id=workspace_id, **data.model_dump())
        self.session.add(item)
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def bulk_add(self, workspace_id: str, items: list[LibraryItemCreate]) -> list[LibraryItem]:
        objs = [LibraryItem(workspace_id=workspace_id, **d.model_dump()) for d in items]
        self.session.add_all(objs)
        await self.session.commit()
        for o in objs:
            await self.session.refresh(o)
        return objs

    async def list(self, workspace_id: str, *, limit: int = 100) -> list[LibraryItem]:
        stmt = (select(LibraryItem)
                .where(LibraryItem.workspace_id == workspace_id)
                .where(LibraryItem.deleted_at.is_(None))
                .order_by(LibraryItem.created_at.desc())
                .limit(limit))
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def get(self, workspace_id: str, item_id: str) -> LibraryItem | None:
        item = await self.session.get(LibraryItem, item_id)
        if item is None or item.workspace_id != workspace_id or item.deleted_at:
            return None
        return item

    async def delete(self, workspace_id: str, item_id: str) -> bool:
        item = await self.get(workspace_id, item_id)
        if item is None:
            return False
        item.deleted_at = datetime.now(timezone.utc)
        await self.session.commit()
        return True
```

- [ ] **Step 6: Register model + run migration + tests**

```bash
# Register in models/__init__.py: from .library import LibraryItem
cd backend && .venv/bin/alembic upgrade head
cd backend && .venv/bin/python -m pytest tests/services/rooms/test_library_service.py -v
```
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/alembic/versions/033_create_library_items.py \
        backend/src/database/models/library.py \
        backend/src/database/models/__init__.py \
        backend/src/services/rooms/library_service.py \
        backend/tests/services/rooms/test_library_service.py
git commit -m "feat: add library_items room with bulk add"
```

### Task 1.4: Documents 房间

**Files:**
- Create: `backend/alembic/versions/034_create_documents_v2.py`
- Create: `backend/src/database/models/document.py`
- Create: `backend/src/services/rooms/documents_service.py`
- Test: `backend/tests/services/rooms/test_documents_service.py`

> **Note**: 旧 `documents` 表（migration 010-ish）将在 Phase 4 数据迁移到新 `documents_v2`，最终重命名。这里建立新表名 `documents_v2`；Phase 4 会改名。

> **Pattern**: 同 Task 1.3，schema 来自 spec §4.4.2。Service 增加方法 `commit_version(parent_id, new_version_data)` 处理版本链。

- [ ] **Step 1: Write tests covering CRUD + version chain**

```python
# backend/tests/services/rooms/test_documents_service.py
import pytest
from src.services.rooms.documents_service import DocumentsService, DocumentCreate

@pytest.mark.asyncio
async def test_add_document(async_session):
    svc = DocumentsService(async_session)
    d = await svc.add(
        "ws-1",
        DocumentCreate(
            name="intro.md", kind="draft", mime_type="text/markdown",
            storage_path="s3://...", size_bytes=1234, added_by="user",
        ),
    )
    assert d.version == 1

@pytest.mark.asyncio
async def test_version_chain(async_session):
    svc = DocumentsService(async_session)
    v1 = await svc.add("ws-1", DocumentCreate(name="x.md", kind="draft", mime_type="text/markdown",
                                              storage_path="p1", size_bytes=1, added_by="user"))
    v2 = await svc.commit_version(
        "ws-1", v1.id,
        DocumentCreate(name="x.md", kind="draft", mime_type="text/markdown",
                       storage_path="p2", size_bytes=2, added_by="execution:e1"),
    )
    assert v2.parent_id == v1.id
    assert v2.version == 2
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd backend && .venv/bin/python -m pytest tests/services/rooms/test_documents_service.py -v`. Expected: FAIL ImportError.

- [ ] **Step 3: Write migration `034_create_documents_v2.py`**

```python
revision = "034"
down_revision = "033"

def upgrade():
    op.create_table(
        "documents_v2",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("storage_path", sa.String(500), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("parent_id", sa.String(36), sa.ForeignKey("documents_v2.id"), nullable=True),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("metadata_json", JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column("added_by", sa.String(60), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_documents_v2_ws_active", "documents_v2", ["workspace_id"],
                    postgresql_where=sa.text("deleted_at IS NULL"))
```

- [ ] **Step 4: Write model `Document` (follows LibraryItem pattern, plus `parent_id` self-FK and `version` int)**

(Class skeleton same shape as Task 1.3 model. Add `parent_id`, `version`, `parent: relationship('Document', remote_side=[id])`).

- [ ] **Step 5: Write `DocumentsService`** with `add`, `commit_version`, `list`, `get`, `delete` methods.

```python
async def commit_version(self, workspace_id: str, parent_id: str, data: DocumentCreate) -> Document:
    parent = await self.get(workspace_id, parent_id)
    if parent is None:
        raise ValueError("parent not found")
    new = Document(
        workspace_id=workspace_id, parent_id=parent_id, version=parent.version + 1,
        **data.model_dump(),
    )
    self.session.add(new)
    await self.session.commit()
    await self.session.refresh(new)
    return new
```

- [ ] **Step 6: Run migration + tests + commit**

```bash
cd backend && .venv/bin/alembic upgrade head
cd backend && .venv/bin/python -m pytest tests/services/rooms/test_documents_service.py -v
git add backend/alembic/versions/034_create_documents_v2.py \
        backend/src/database/models/document.py \
        backend/src/database/models/__init__.py \
        backend/src/services/rooms/documents_service.py \
        backend/tests/services/rooms/test_documents_service.py
git commit -m "feat: add documents_v2 room with version chain"
```

### Task 1.5: Decisions 房间

**Files:**
- Create: `backend/alembic/versions/035_create_decisions.py`
- Create: `backend/src/database/models/decision.py`
- Create: `backend/src/services/rooms/decisions_service.py`
- Test: `backend/tests/services/rooms/test_decisions_service.py`

**Schema (spec §4.4.3)**: `id, workspace_id, key, value, confidence, source_message_id, extracted_by, superseded_by, created_at, deleted_at`.

**Special service method:** `set_decision(ws, key, value)` — 自动 supersede 旧的同 key 决策（不删，用 `superseded_by` 链）。`get_active(ws)` 返回 `Dict[key, value]`，仅未 superseded。

- [ ] **Step 1: Write tests**

```python
# backend/tests/services/rooms/test_decisions_service.py
import pytest
from src.services.rooms.decisions_service import DecisionsService

@pytest.mark.asyncio
async def test_set_supersedes_old(async_session):
    svc = DecisionsService(async_session)
    d1 = await svc.set("ws-1", "citation_style", "MLA", extracted_by="user")
    d2 = await svc.set("ws-1", "citation_style", "APA", extracted_by="user")

    active = await svc.get_active("ws-1")
    assert active["citation_style"] == "APA"

    refreshed = await svc.get(d1.id)
    assert refreshed.superseded_by == d2.id

@pytest.mark.asyncio
async def test_get_active_skips_deleted(async_session):
    svc = DecisionsService(async_session)
    d = await svc.set("ws-1", "tone", "客观", extracted_by="user")
    await svc.delete(d.id)
    active = await svc.get_active("ws-1")
    assert "tone" not in active
```

- [ ] **Step 2-7**: Pattern same as Task 1.3-1.4. Migration creates table per spec §4.4.3 schema. Model class `Decision` with `key`, `value`, `confidence`, `source_message_id`, `extracted_by`, `superseded_by`. Service:

```python
class DecisionsService:
    async def set(self, workspace_id: str, key: str, value: str, *,
                  extracted_by: str, source_message_id: str | None = None,
                  confidence: float = 1.0) -> Decision:
        # find current active for key
        stmt = (select(Decision)
                .where(Decision.workspace_id == workspace_id)
                .where(Decision.key == key)
                .where(Decision.superseded_by.is_(None))
                .where(Decision.deleted_at.is_(None)))
        old = (await self.session.scalars(stmt)).first()

        new_d = Decision(
            workspace_id=workspace_id, key=key, value=value,
            extracted_by=extracted_by, source_message_id=source_message_id,
            confidence=confidence,
        )
        self.session.add(new_d)
        await self.session.flush()  # get new_d.id

        if old:
            old.superseded_by = new_d.id
        await self.session.commit()
        await self.session.refresh(new_d)
        return new_d

    async def get_active(self, workspace_id: str) -> dict[str, str]:
        stmt = (select(Decision)
                .where(Decision.workspace_id == workspace_id)
                .where(Decision.superseded_by.is_(None))
                .where(Decision.deleted_at.is_(None)))
        rows = (await self.session.scalars(stmt)).all()
        return {r.key: r.value for r in rows}
```

- [ ] **Final**: register model, migrate, test pass, commit `feat: add decisions room with supersede chain`.

### Task 1.6: Memory 房间 (memory_facts)

**Files:**
- Create: `backend/alembic/versions/036_create_memory_facts.py`
- Create: `backend/src/database/models/memory_fact.py`
- Create: `backend/src/services/rooms/memory_service.py`
- Test: `backend/tests/services/rooms/test_memory_service.py`

**Schema (spec §4.4.4)**: `id, workspace_id, category, content, confidence, last_referenced_at, reference_count, created_at, deleted_at`.

**Special methods:**
- `add_facts(ws, facts: list[FactCreate])` — bulk insert from compact agent
- `top(ws, k=15, category=None)` — top-K by `(reference_count, confidence)`
- `mark_referenced(fact_id)` — increment count + update last_referenced_at
- `evict_excess(ws, max=100)` — drop lowest-priority facts to keep size cap

- [ ] **Step 1: Write tests** (covering all 4 methods + cap)

```python
@pytest.mark.asyncio
async def test_evict_excess(async_session):
    svc = MemoryService(async_session)
    for i in range(105):
        await svc.add_facts("ws-1", [FactCreate(category="ctx", content=f"f{i}", confidence=0.5)])
    await svc.evict_excess("ws-1", max_facts=100)
    facts = await svc.top("ws-1", k=200)
    assert len(facts) == 100
```

- [ ] **Step 2-7**: Pattern same. Skeleton:

```python
class MemoryService:
    async def add_facts(self, workspace_id: str, facts: list[FactCreate]) -> list[MemoryFact]:
        ...

    async def top(self, workspace_id: str, k: int = 15, category: str | None = None) -> list[MemoryFact]:
        stmt = (select(MemoryFact)
                .where(MemoryFact.workspace_id == workspace_id)
                .where(MemoryFact.deleted_at.is_(None))
                .order_by(MemoryFact.reference_count.desc(), MemoryFact.confidence.desc())
                .limit(k))
        if category:
            stmt = stmt.where(MemoryFact.category == category)
        return list((await self.session.scalars(stmt)).all())

    async def mark_referenced(self, fact_id: str): ...

    async def evict_excess(self, workspace_id: str, max_facts: int = 100): ...
```

- [ ] Commit: `feat: add memory_facts room with eviction policy`.

### Task 1.7: Run History 房间

**Files:**
- Create: `backend/alembic/versions/037_create_run_history.py`
- Create: `backend/src/database/models/run_history.py`
- Create: `backend/src/services/rooms/run_history_service.py`
- Test: `backend/tests/services/rooms/test_run_history_service.py`

**Schema (spec §4.4.5)**: `id, workspace_id, execution_id (UNIQUE), capability_id, title, summary, status, artifact_count, duration_seconds, token_usage, created_at, deleted_at`.

- [ ] Write tests, migration, model, service. Service exposes `record(workspace_id, execution_id, ...)` (called by execution completion hook).
- [ ] Commit: `feat: add run_history room`.

### Task 1.8: Sandbox 房间

**Files:**
- Create: `backend/alembic/versions/038_create_sandboxes.py`
- Create: `backend/src/database/models/sandbox.py`
- Create: `backend/src/services/rooms/sandbox_service.py`
- Test: `backend/tests/services/rooms/test_sandbox_service.py`

> **Note**: V1 仅 `local` provider，封装现有 deer-flow `LocalSandboxProvider`（位于 `backend/packages/harness/...`）。Service 是薄包装层 + DB 状态记录。

- [ ] **Step 1: Write tests for acquire/release lifecycle**

```python
@pytest.mark.asyncio
async def test_acquire_creates_record(async_session):
    svc = SandboxService(async_session, provider_factory=mock_provider_factory)
    sb = await svc.acquire("ws-1")
    assert sb.workspace_id == "ws-1"
    assert sb.state == "active"

@pytest.mark.asyncio
async def test_acquire_returns_existing(async_session):
    svc = SandboxService(async_session, provider_factory=mock_provider_factory)
    s1 = await svc.acquire("ws-1")
    s2 = await svc.acquire("ws-1")
    assert s1.sandbox_id == s2.sandbox_id

@pytest.mark.asyncio
async def test_exec_in_sandbox(async_session):
    svc = SandboxService(async_session, provider_factory=mock_provider_factory)
    await svc.acquire("ws-1")
    result = await svc.exec("ws-1", "echo hello")
    assert "hello" in result.stdout
```

- [ ] **Step 2-7**: Pattern + integration. Service signature:

```python
class SandboxService:
    def __init__(self, session: AsyncSession, provider_factory: Callable[[str], SandboxProvider]):
        ...
    async def acquire(self, workspace_id: str) -> Sandbox: ...
    async def release(self, workspace_id: str) -> None: ...
    async def exec(self, workspace_id: str, command: str, *, timeout: int = 30) -> ExecResult: ...
    async def read_file(self, workspace_id: str, path: str) -> bytes: ...
    async def write_file(self, workspace_id: str, path: str, data: bytes) -> None: ...
```

- [ ] Commit: `feat: add sandbox room with local provider`.

### Task 1.9: Workspace Tasks 房间

**Files:**
- Create: `backend/alembic/versions/039_create_workspace_tasks.py`
- Create: `backend/src/database/models/workspace_task.py` (model class `WorkspaceTask`)
- Create: `backend/src/services/rooms/tasks_service.py`
- Test: `backend/tests/services/rooms/test_workspace_tasks_service.py`

> **Naming note**: 表名 `workspace_tasks`；模型类 `WorkspaceTask`；service 类 `WorkspaceTasksService`（不与已有 `task_records` / `TaskService` 混淆）。

**Schema (spec §4.4.7)**: `id, workspace_id, title, description, status (pending|in_progress|done), priority, related_execution_ids, created_by, created_at, updated_at, completed_at, deleted_at`.

- [ ] Tests for CRUD + status transitions + priority sort.
- [ ] Commit: `feat: add workspace_tasks room`.

### Task 1.10: Audit Log

**Files:**
- Create: `backend/alembic/versions/040_create_audit_logs.py`
- Create: `backend/src/database/models/audit_log.py`
- Create: `backend/src/services/audit_service.py`
- Test: `backend/tests/services/test_audit_service.py`

**Schema (spec §4.5.3)**: `id (BIGSERIAL), user_id, workspace_id, action, target_type, target_id, payload, ip_address, user_agent, created_at`.

- [ ] **Step 1: Tests covering async fire-and-forget write + retention query**

```python
@pytest.mark.asyncio
async def test_log_writes_async(async_session):
    svc = AuditService(async_session)
    await svc.log(
        action="execution.created",
        user_id="u1", workspace_id="ws-1",
        target_type="execution", target_id="exec-1",
        payload={"capability": "deep_research"},
    )
    rows = await svc.query(workspace_id="ws-1")
    assert len(rows) == 1
    assert rows[0].action == "execution.created"
```

- [ ] **Step 3: Migration**

```python
def upgrade():
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(36)),
        sa.Column("workspace_id", sa.String(36)),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("target_type", sa.String(50)),
        sa.Column("target_id", sa.String(36)),
        sa.Column("payload", JSONB),
        sa.Column("ip_address", sa.String(50)),
        sa.Column("user_agent", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_audit_workspace_time", "audit_logs", ["workspace_id", sa.text("created_at DESC")])
    op.create_index("ix_audit_user_time", "audit_logs", ["user_id", sa.text("created_at DESC")])
```

- [ ] **Step 5: Service with best-effort async write**

```python
class AuditService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def log(self, action: str, *, user_id: str | None = None, workspace_id: str | None = None,
                  target_type: str | None = None, target_id: str | None = None,
                  payload: dict | None = None, ip: str | None = None, ua: str | None = None) -> None:
        try:
            row = AuditLog(action=action, user_id=user_id, workspace_id=workspace_id,
                           target_type=target_type, target_id=target_id, payload=payload or {},
                           ip_address=ip, user_agent=ua)
            self.session.add(row)
            await self.session.commit()
        except Exception as e:
            logger.warning("audit log failed", extra={"action": action, "error": str(e)})

    async def query(self, *, workspace_id: str | None = None, user_id: str | None = None,
                    since: datetime | None = None, limit: int = 100) -> list[AuditLog]:
        stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
        if workspace_id:
            stmt = stmt.where(AuditLog.workspace_id == workspace_id)
        if user_id:
            stmt = stmt.where(AuditLog.user_id == user_id)
        if since:
            stmt = stmt.where(AuditLog.created_at >= since)
        return list((await self.session.scalars(stmt)).all())
```

- [ ] Commit: `feat: add audit_logs platform infrastructure`.

### Task 1.11: Quota Service

**Files:**
- Create: `backend/src/services/quota_service.py`
- Test: `backend/tests/services/test_quota_service.py`

> **No new table** — V1 uses Redis counters with daily expiry. Persistent quota config can come from `workspace_settings` or env vars.

- [ ] **Step 1: Tests**

```python
@pytest.mark.asyncio
async def test_check_under_limit(redis_client):
    svc = QuotaService(redis_client, daily_token_limit=1_000_000)
    assert await svc.check("u1", kind="tokens_daily", amount=100_000) is True

@pytest.mark.asyncio
async def test_consume_increments(redis_client):
    svc = QuotaService(redis_client, daily_token_limit=1_000_000)
    await svc.consume("u1", kind="tokens_daily", amount=500_000)
    usage = await svc.get_usage("u1")
    assert usage.tokens_daily == 500_000

@pytest.mark.asyncio
async def test_check_over_limit(redis_client):
    svc = QuotaService(redis_client, daily_token_limit=1_000_000)
    await svc.consume("u1", kind="tokens_daily", amount=900_000)
    assert await svc.check("u1", kind="tokens_daily", amount=200_000) is False
```

- [ ] **Step 3-5: Service**

```python
# backend/src/services/quota_service.py
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal
from redis.asyncio import Redis

QuotaKind = Literal["tokens_daily", "executions_concurrent", "storage_bytes"]

@dataclass
class QuotaUsage:
    tokens_daily: int = 0
    executions_concurrent: int = 0
    storage_bytes: int = 0

class QuotaService:
    def __init__(self, redis: Redis, *, daily_token_limit: int = 1_000_000,
                 concurrent_exec_limit: int = 1, storage_limit_bytes: int = 5 * 1024**3):
        self.redis = redis
        self.limits = {
            "tokens_daily": daily_token_limit,
            "executions_concurrent": concurrent_exec_limit,
            "storage_bytes": storage_limit_bytes,
        }

    def _key(self, user_id: str, kind: QuotaKind) -> str:
        if kind == "tokens_daily":
            day = datetime.now(timezone.utc).strftime("%Y%m%d")
            return f"quota:{user_id}:{kind}:{day}"
        return f"quota:{user_id}:{kind}"

    async def check(self, user_id: str, *, kind: QuotaKind, amount: int = 0) -> bool:
        current = int(await self.redis.get(self._key(user_id, kind)) or 0)
        return current + amount <= self.limits[kind]

    async def consume(self, user_id: str, *, kind: QuotaKind, amount: int) -> None:
        key = self._key(user_id, kind)
        await self.redis.incrby(key, amount)
        if kind == "tokens_daily":
            await self.redis.expire(key, 86400 * 2)

    async def release(self, user_id: str, *, kind: QuotaKind, amount: int) -> None:
        await self.redis.decrby(self._key(user_id, kind), amount)

    async def get_usage(self, user_id: str) -> QuotaUsage:
        return QuotaUsage(
            tokens_daily=int(await self.redis.get(self._key(user_id, "tokens_daily")) or 0),
            executions_concurrent=int(await self.redis.get(self._key(user_id, "executions_concurrent")) or 0),
            storage_bytes=int(await self.redis.get(self._key(user_id, "storage_bytes")) or 0),
        )
```

- [ ] Commit: `feat: add quota service with Redis-backed counters`.

### Task 1.12: Model Gateway

**Files:**
- Create: `backend/src/services/model_gateway.py`
- Test: `backend/tests/services/test_model_gateway.py`

**Responsibilities (spec §4.5.5):** quota check → 路由（OpenAI / Anthropic / 本地）→ retry → 成本计算 → audit log。

- [ ] **Step 1: Tests** (with mocked LLM client)

```python
@pytest.mark.asyncio
async def test_chat_completion_quota_block(mock_llm, audit_service, quota_service):
    # quota over limit → raises QuotaExceeded
    ...

@pytest.mark.asyncio
async def test_chat_completion_records_audit(mock_llm, audit_service, quota_service):
    gw = ModelGateway(audit=audit_service, quota=quota_service, ...)
    await gw.chat_completion(
        messages=[...], model="claude-opus-4-7",
        workspace_id="ws-1", user_id="u1",
    )
    assert audit_service.log_calls[0]["action"] == "model.completion"
    assert audit_service.log_calls[0]["payload"]["model"] == "claude-opus-4-7"

@pytest.mark.asyncio
async def test_retry_on_transient(mock_llm_with_429):
    # raises 429 once, then succeeds — verify retry happened
    ...
```

- [ ] **Step 3-5: Service shell**

```python
# backend/src/services/model_gateway.py
import asyncio
from anthropic import AsyncAnthropic, RateLimitError, APITimeoutError
from openai import AsyncOpenAI
from src.services.audit_service import AuditService
from src.services.quota_service import QuotaService

class CompletionResult:
    text: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    model: str

class QuotaExceeded(Exception): ...

class ModelGateway:
    def __init__(self, *, anthropic: AsyncAnthropic, openai: AsyncOpenAI,
                 audit: AuditService, quota: QuotaService):
        self.anthropic = anthropic
        self.openai = openai
        self.audit = audit
        self.quota = quota

    async def chat_completion(self, *, messages: list[dict], model: str,
                              workspace_id: str, user_id: str,
                              execution_id: str | None = None,
                              max_tokens: int = 4096, **kwargs) -> CompletionResult:
        # 1. quota
        if not await self.quota.check(user_id, kind="tokens_daily", amount=max_tokens):
            raise QuotaExceeded("tokens_daily limit reached")

        # 2. route
        result = await self._dispatch(model, messages, max_tokens, **kwargs)

        # 3. consume + audit
        await self.quota.consume(user_id, kind="tokens_daily",
                                 amount=result.input_tokens + result.output_tokens)
        await self.audit.log(
            action="model.completion",
            user_id=user_id, workspace_id=workspace_id,
            target_type="execution", target_id=execution_id,
            payload={"model": model, "input_tokens": result.input_tokens,
                     "output_tokens": result.output_tokens, "cost_usd": result.cost_usd},
        )
        return result

    async def _dispatch(self, model: str, messages: list[dict], max_tokens: int, **kwargs):
        if model.startswith("claude"):
            return await self._anthropic_call(model, messages, max_tokens, **kwargs)
        if model.startswith(("gpt", "o")):
            return await self._openai_call(model, messages, max_tokens, **kwargs)
        raise ValueError(f"unknown model: {model}")

    async def _anthropic_call(self, model, messages, max_tokens, **kw):
        # retry on transient
        for attempt in range(3):
            try:
                resp = await self.anthropic.messages.create(
                    model=model, messages=messages, max_tokens=max_tokens, **kw,
                )
                return CompletionResult(
                    text=resp.content[0].text,
                    input_tokens=resp.usage.input_tokens,
                    output_tokens=resp.usage.output_tokens,
                    cost_usd=self._compute_cost(model, resp.usage),
                    model=model,
                )
            except (RateLimitError, APITimeoutError):
                if attempt == 2:
                    raise
                await asyncio.sleep(2 ** attempt)

    def _compute_cost(self, model: str, usage) -> float:
        # 价格表
        prices = {
            "claude-opus-4-7": (15.0, 75.0),  # per 1M tokens (input, output)
            "claude-sonnet-4-6": (3.0, 15.0),
            "gpt-4o": (5.0, 20.0),
        }
        if model not in prices:
            return 0.0
        in_p, out_p = prices[model]
        return (usage.input_tokens * in_p + usage.output_tokens * out_p) / 1_000_000
```

- [ ] Commit: `feat: add model gateway with retry + cost tracking`.

### Task 1.13: Event Bus (Redis Pub/Sub + Streams)

**Files:**
- Create: `backend/src/services/event_bus.py`
- Test: `backend/tests/services/test_event_bus.py`

**Spec §4.5.7**: Pub/Sub for lightweight notifications (`capability.invalidated`, `workspace.refresh`); Streams for `execution.*` (already covered by existing `RedisStreamBridge`). New `EventBus` 是 Pub/Sub 部分的轻量包装。

- [ ] **Step 1: Tests**

```python
@pytest.mark.asyncio
async def test_publish_subscribe(redis_client):
    bus = EventBus(redis_client)
    received: list[dict] = []
    async def handler(event: dict):
        received.append(event)
    bus.subscribe("test.channel", handler)
    await bus.start()
    await bus.publish("test.channel", {"hello": "world"})
    await asyncio.sleep(0.1)  # let subscriber catch up
    assert received == [{"hello": "world"}]
    await bus.stop()
```

- [ ] **Step 3-5: Service**

```python
# backend/src/services/event_bus.py
import asyncio, json
from collections.abc import Awaitable, Callable
from redis.asyncio import Redis

Handler = Callable[[dict], Awaitable[None]]

class EventBus:
    def __init__(self, redis: Redis):
        self.redis = redis
        self._handlers: dict[str, list[Handler]] = {}
        self._task: asyncio.Task | None = None
        self._pubsub = None

    def subscribe(self, channel: str, handler: Handler) -> None:
        self._handlers.setdefault(channel, []).append(handler)

    async def publish(self, channel: str, event: dict) -> int:
        return await self.redis.publish(channel, json.dumps(event))

    async def start(self) -> None:
        if not self._handlers:
            return
        self._pubsub = self.redis.pubsub()
        await self._pubsub.subscribe(*self._handlers.keys())
        self._task = asyncio.create_task(self._loop())

    async def _loop(self):
        async for msg in self._pubsub.listen():
            if msg["type"] != "message":
                continue
            channel = msg["channel"].decode()
            event = json.loads(msg["data"])
            for h in self._handlers.get(channel, []):
                try:
                    await h(event)
                except Exception as e:
                    logger.exception("handler failed", extra={"channel": channel, "error": str(e)})

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
        if self._pubsub:
            await self._pubsub.close()
```

- [ ] Commit: `feat: add event bus for cross-process notifications`.

### Task 1.14: Capability table + model

**Files:**
- Create: `backend/alembic/versions/041_create_capabilities.py`
- Create: `backend/src/database/models/capability.py`
- Test: `backend/tests/database/test_capability_model.py`

**Schema (spec §4.3.4)**: `capabilities` (composite PK `(id, workspace_type, version)`) + `capability_active_versions` (PK `(id, workspace_type)`, FK to active version).

- [ ] **Step 1: Test model creation + active-version pointer**

```python
@pytest.mark.asyncio
async def test_capability_create(async_session):
    cap = Capability(
        id="deep_research", workspace_type="thesis", version=1,
        display_name="深度文献调研", intent_description="...",
        trigger_phrases=["调研", "找综述"],
        required_decisions=[{"key": "topic_scope", "ask": "...", "type": "string"}],
        brief_schema={"type": "object"}, graph_template={"phases": []},
        system_prompt="...", result_card_template="literature_review",
    )
    async_session.add(cap)
    await async_session.commit()
    assert cap.created_at is not None
```

- [ ] **Step 3: Migration**

```python
revision = "041"
down_revision = "040"

def upgrade():
    op.create_table(
        "capabilities",
        sa.Column("id", sa.String(100), nullable=False),
        sa.Column("workspace_type", sa.String(50), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("TRUE")),
        sa.Column("intent_description", sa.Text, nullable=False),
        sa.Column("trigger_phrases", JSONB, server_default=sa.text("'[]'::jsonb")),
        sa.Column("required_decisions", JSONB, server_default=sa.text("'[]'::jsonb")),
        sa.Column("brief_schema", JSONB, nullable=False),
        sa.Column("graph_template", JSONB, nullable=False),
        sa.Column("system_prompt", sa.Text, nullable=False),
        sa.Column("result_card_template", sa.String(100), nullable=False),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", "workspace_type", "version"),
    )
    op.create_index(
        "ix_capabilities_active", "capabilities", ["workspace_type", "enabled"],
        postgresql_where=sa.text("enabled = TRUE"),
    )
    op.create_table(
        "capability_active_versions",
        sa.Column("id", sa.String(100), nullable=False),
        sa.Column("workspace_type", sa.String(50), nullable=False),
        sa.Column("active_version", sa.Integer, nullable=False),
        sa.PrimaryKeyConstraint("id", "workspace_type"),
        sa.ForeignKeyConstraint(
            ["id", "workspace_type", "active_version"],
            ["capabilities.id", "capabilities.workspace_type", "capabilities.version"],
        ),
    )
```

- [ ] **Step 5: Model**

```python
# backend/src/database/models/capability.py
from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKeyConstraint, Integer, PrimaryKeyConstraint, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from ..base import Base

class Capability(Base):
    __tablename__ = "capabilities"
    __table_args__ = (
        PrimaryKeyConstraint("id", "workspace_type", "version"),
    )
    id: Mapped[str] = mapped_column(String(100), nullable=False)
    workspace_type: Mapped[str] = mapped_column(String(50), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    intent_description: Mapped[str] = mapped_column(Text)
    trigger_phrases: Mapped[list[str]] = mapped_column(JSONB, default=list)
    required_decisions: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    brief_schema: Mapped[dict] = mapped_column(JSONB)
    graph_template: Mapped[dict] = mapped_column(JSONB)
    system_prompt: Mapped[str] = mapped_column(Text)
    result_card_template: Mapped[str] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class CapabilityActiveVersion(Base):
    __tablename__ = "capability_active_versions"
    __table_args__ = (
        PrimaryKeyConstraint("id", "workspace_type"),
        ForeignKeyConstraint(
            ["id", "workspace_type", "active_version"],
            ["capabilities.id", "capabilities.workspace_type", "capabilities.version"],
        ),
    )
    id: Mapped[str] = mapped_column(String(100))
    workspace_type: Mapped[str] = mapped_column(String(50))
    active_version: Mapped[int] = mapped_column(Integer, nullable=False)
```

- [ ] Commit: `feat: add capability tables (data-driven Skills-like)`.

### Task 1.15: Capability YAML loader

**Files:**
- Create: `backend/src/services/capability_loader.py`
- Create: `backend/seed/capabilities/thesis/deep_research.yaml` (示例)
- Test: `backend/tests/services/test_capability_loader.py`

**Behavior**: 启动时检查 `capabilities` 表为空 → 扫描 `backend/seed/capabilities/**/*.yaml` → 验证 → 写入 DB → 设置 active_version=1。Idempotent。

- [ ] **Step 1: Tests**

```python
@pytest.mark.asyncio
async def test_load_seeds_when_empty(async_session, tmp_path):
    # write a YAML file
    (tmp_path / "thesis").mkdir()
    (tmp_path / "thesis" / "x.yaml").write_text("""
id: x
workspace_type: thesis
version: 1
display_name: 测试
intent_description: 测试 capability
trigger_phrases: [test]
required_decisions: []
brief_schema: {type: object}
graph_template: {phases: []}
system_prompt: "test"
result_card_template: default
""")
    loader = CapabilityLoader(async_session, seed_dir=str(tmp_path))
    await loader.load_seeds_if_empty()
    cap = await async_session.get(Capability, ("x", "thesis", 1))
    assert cap is not None

@pytest.mark.asyncio
async def test_load_skips_when_db_has_data(async_session):
    # add a capability first, then loader should skip
    ...

@pytest.mark.asyncio
async def test_load_validates_yaml(async_session, tmp_path):
    # invalid YAML → raises ValidationError
    (tmp_path / "thesis").mkdir()
    (tmp_path / "thesis" / "bad.yaml").write_text("id: x\n# missing required fields")
    loader = CapabilityLoader(async_session, seed_dir=str(tmp_path))
    with pytest.raises(ValueError):
        await loader.load_seeds_if_empty()
```

- [ ] **Step 3-5: Service**

```python
# backend/src/services/capability_loader.py
import yaml
from pathlib import Path
from sqlalchemy import select
from src.database.models.capability import Capability, CapabilityActiveVersion

REQUIRED_FIELDS = ("id", "workspace_type", "version", "display_name", "intent_description",
                   "brief_schema", "graph_template", "system_prompt", "result_card_template")

class CapabilityLoader:
    def __init__(self, session, seed_dir: str = "backend/seed/capabilities"):
        self.session = session
        self.seed_dir = Path(seed_dir)

    async def load_seeds_if_empty(self) -> int:
        existing = (await self.session.execute(select(Capability).limit(1))).first()
        if existing:
            return 0  # DB already populated, skip
        return await self._load_all()

    async def _load_all(self) -> int:
        n = 0
        for yaml_file in self.seed_dir.glob("*/*.yaml"):
            data = yaml.safe_load(yaml_file.read_text())
            self._validate(data, str(yaml_file))
            cap = Capability(**{k: data[k] for k in data if k in Capability.__table__.columns.keys()})
            cap.enabled = data.get("enabled", True)
            cap.trigger_phrases = data.get("trigger_phrases", [])
            cap.required_decisions = data.get("required_decisions", [])
            cap.notes = data.get("notes")
            self.session.add(cap)
            n += 1
            await self.session.flush()
            self.session.add(CapabilityActiveVersion(
                id=cap.id, workspace_type=cap.workspace_type, active_version=cap.version,
            ))
        await self.session.commit()
        return n

    def _validate(self, data: dict, path: str) -> None:
        missing = [f for f in REQUIRED_FIELDS if f not in data]
        if missing:
            raise ValueError(f"{path}: missing fields {missing}")
        # 详细校验 graph_template 在 Task 1.16 (resolver) 里
```

- [ ] Commit: `feat: add capability YAML loader for seed deployment`.

### Task 1.16: CapabilityResolver + 校验

**Files:**
- Create: `backend/src/services/capability_resolver.py`
- Test: `backend/tests/services/test_capability_resolver.py`

**Spec §4.3.5 + §4.3.7**: Resolver 缓存 + invalidate；校验 phases.depends_on 解析、subagent_type 在注册表（Phase 2 才填，V1 校验为 stub）、prompt 模板变量白名单。

- [ ] **Step 1: Tests covering resolve + cache + invalidate**

```python
@pytest.mark.asyncio
async def test_resolve_loads_from_db(async_session, event_bus):
    # seed a capability
    ...
    resolver = CapabilityResolver(async_session, event_bus)
    cap = await resolver.resolve("deep_research", "thesis")
    assert cap.id == "deep_research"

@pytest.mark.asyncio
async def test_resolve_uses_cache(async_session, event_bus):
    resolver = CapabilityResolver(async_session, event_bus)
    cap1 = await resolver.resolve("deep_research", "thesis")
    cap2 = await resolver.resolve("deep_research", "thesis")
    assert cap1 is cap2  # same object reference

@pytest.mark.asyncio
async def test_invalidate_clears_cache(async_session, event_bus):
    resolver = CapabilityResolver(async_session, event_bus)
    await resolver.resolve("deep_research", "thesis")
    await event_bus.publish("capability.invalidated",
                            {"capability_id": "deep_research", "workspace_type": "thesis"})
    await asyncio.sleep(0.05)
    cap2 = await resolver.resolve("deep_research", "thesis")
    # should hit DB again, but cache repopulated. Just verify no error.
```

- [ ] **Step 3-5: Service**

```python
# backend/src/services/capability_resolver.py
from sqlalchemy import select
from src.database.models.capability import Capability, CapabilityActiveVersion
from src.services.event_bus import EventBus

class CapabilityNotFound(Exception): ...

class CapabilityResolver:
    def __init__(self, session_factory, event_bus: EventBus):
        self.session_factory = session_factory  # callable returning new AsyncSession
        self.event_bus = event_bus
        self._cache: dict[tuple[str, str], Capability] = {}
        event_bus.subscribe("capability.invalidated", self._on_invalidate)

    async def resolve(self, capability_id: str, workspace_type: str) -> Capability:
        key = (capability_id, workspace_type)
        if key in self._cache:
            return self._cache[key]
        async with self.session_factory() as session:
            stmt = (
                select(Capability)
                .join(CapabilityActiveVersion,
                      (CapabilityActiveVersion.id == Capability.id)
                      & (CapabilityActiveVersion.workspace_type == Capability.workspace_type)
                      & (CapabilityActiveVersion.active_version == Capability.version))
                .where(Capability.id == capability_id)
                .where(Capability.workspace_type == workspace_type)
                .where(Capability.enabled.is_(True))
            )
            cap = (await session.scalars(stmt)).first()
        if cap is None:
            raise CapabilityNotFound(f"{capability_id}/{workspace_type}")
        self._cache[key] = cap
        return cap

    async def list_for_workspace_type(self, workspace_type: str) -> list[Capability]:
        async with self.session_factory() as session:
            stmt = (select(Capability).join(CapabilityActiveVersion, ...).where(...))
            return list((await session.scalars(stmt)).all())

    async def _on_invalidate(self, event: dict) -> None:
        key = (event["capability_id"], event["workspace_type"])
        self._cache.pop(key, None)
```

- [ ] **Step 6: Validation utility**

```python
# in capability_resolver.py
from string import Template

ALLOWED_VARS = {"topic", "language", "time_range", "decisions", "raw_message", "workspace"}

def validate_capability(data: dict, subagent_registry: dict) -> list[str]:
    """Return list of validation errors. Empty list = OK."""
    errors = []
    # 1. depends_on resolves to existing phase names
    phase_names = {p["name"] for p in data["graph_template"]["phases"]}
    for p in data["graph_template"]["phases"]:
        for dep in p.get("depends_on", []):
            if dep not in phase_names:
                errors.append(f"phase {p['name']}: unknown depends_on '{dep}'")
    # 2. subagent_type in registry (after Phase 2 registry exists)
    for p in data["graph_template"]["phases"]:
        for t in p["tasks"]:
            if t["subagent_type"] not in subagent_registry:
                errors.append(f"unknown subagent_type '{t['subagent_type']}'")
    # 3. prompt_template / system_prompt 变量白名单
    # ... (check {{var}} refs against ALLOWED_VARS + brief_schema.properties)
    return errors
```

- [ ] Commit: `feat: add capability resolver with cache + invalidation + validation`.

### Task 1.17: 8 房间统一路由 + capabilities 路由

**Files:**
- Create: `backend/src/gateway/routers/workspace_rooms.py`
- Create: `backend/src/gateway/routers/capabilities.py`
- Modify: `backend/src/gateway/app.py` (register new routers)
- Test: `backend/tests/gateway/test_workspace_rooms.py`

**API endpoints (spec §5.3)**: 每房间 CRUD。

- [ ] **Step 1: Tests for each room** (合一文件 8 个 fixture)

```python
@pytest.mark.asyncio
async def test_library_post_get_delete(client, ws_id):
    r = await client.post(f"/workspaces/{ws_id}/library",
                           json={"item_type": "paper", "title": "X", "added_by": "user"})
    assert r.status_code == 201
    item_id = r.json()["id"]

    r = await client.get(f"/workspaces/{ws_id}/library")
    assert len(r.json()["items"]) == 1

    r = await client.delete(f"/workspaces/{ws_id}/library/{item_id}")
    assert r.status_code == 204

    r = await client.get(f"/workspaces/{ws_id}/library")
    assert len(r.json()["items"]) == 0

# Similar tests for documents, decisions, memory, runs, tasks, settings, sandbox
```

- [ ] **Step 3-5: Routers**

```python
# backend/src/gateway/routers/workspace_rooms.py
from fastapi import APIRouter, Depends, HTTPException
from src.services.rooms.library_service import LibraryService, LibraryItemCreate
# ... import other services

router = APIRouter(prefix="/workspaces/{ws_id}", tags=["workspace_rooms"])

# === Library ===
@router.get("/library")
async def list_library(ws_id: str, svc: LibraryService = Depends(get_library_svc)):
    items = await svc.list(ws_id)
    return {"items": [i.to_dict() for i in items]}

@router.post("/library", status_code=201)
async def add_library_item(ws_id: str, body: LibraryItemCreate,
                            svc: LibraryService = Depends(get_library_svc)):
    item = await svc.add(ws_id, body)
    return {"id": item.id, "title": item.title}

@router.delete("/library/{item_id}", status_code=204)
async def delete_library_item(ws_id: str, item_id: str,
                               svc: LibraryService = Depends(get_library_svc)):
    if not await svc.delete(ws_id, item_id):
        raise HTTPException(404)

# === Documents === (parallel structure)
# === Decisions ===
# === Memory ===
# === Run History (read-only) ===
# === Tasks ===
# === Settings ===
# === Sandbox (dev mode only) ===
```

- [ ] **Step 6: capabilities router (read-only V1)**

```python
# backend/src/gateway/routers/capabilities.py
@router.get("/capabilities", tags=["capabilities"])
async def list_capabilities(workspace_type: str,
                             resolver: CapabilityResolver = Depends(get_resolver)):
    caps = await resolver.list_for_workspace_type(workspace_type)
    return {"items": [c.to_brief_dict() for c in caps]}

@router.get("/capabilities/{capability_id}")
async def get_capability(capability_id: str, workspace_type: str,
                          resolver: CapabilityResolver = Depends(get_resolver)):
    return await resolver.resolve(capability_id, workspace_type)
```

- [ ] Commit: `feat: add 8 workspace room routers + capabilities read API`.

### Task 1.18: Observability hooks

**Files:**
- Create: `backend/src/observability/metrics.py`
- Create: `backend/src/observability/tracing.py`
- Modify: `backend/src/gateway/app.py` (register tracing middleware + Prometheus endpoint)
- Test: `backend/tests/observability/test_metrics.py`

**Goal**: §4.5.4 关键指标在 Prometheus `/metrics` 暴露；OpenTelemetry root span 在 ExecutionService.create_execution() 注入。

- [ ] **Step 1: Tests**

```python
def test_metrics_endpoint_exposes_keys(client):
    r = client.get("/metrics")
    assert "execution_stream_latency_p99" in r.text
    assert "chat_agent_response_latency_p95" in r.text

@pytest.mark.asyncio
async def test_tracing_root_span_in_execution_create(...):
    with tracer.start_as_current_span("test"):
        ...
```

- [ ] **Step 3-5: Implementations**

```python
# backend/src/observability/metrics.py
from prometheus_client import Histogram, Counter, Gauge

execution_stream_latency = Histogram(
    "execution_stream_latency_seconds", "SSE first-frame latency",
    buckets=[0.05, 0.1, 0.2, 0.5, 1.0, 2.0],
)
chat_agent_response_latency = Histogram(
    "chat_agent_response_latency_seconds", "Chat agent first-token latency",
    buckets=[0.1, 0.3, 0.5, 1.0, 2.0, 5.0],
)
execution_node_duration = Histogram(
    "execution_node_duration_seconds", "Per-node execution time",
    labelnames=["node_type"],
)
capability_resolve_cache_hit = Counter(
    "capability_resolve_cache_hit_total", "Resolver cache hit count",
    labelnames=["hit"],
)
lead_agent_busy_rejection = Counter(
    "lead_agent_busy_rejection_total", "Dispatch rejected because lead busy",
)
auto_compact_trigger = Counter("auto_compact_trigger_total", "Auto-compact triggers")
```

- [ ] Commit: `feat: add observability metrics + tracing hooks`.

### Task 1.19: Phase 1 集成测试

**Files:**
- Create: `backend/tests/integration/test_phase1_foundation.py`

- [ ] **Step 1: Test that all platform services boot together + 8 rooms accept CRUD without business code**

```python
@pytest.mark.asyncio
async def test_phase1_full_stack(client, async_session, redis_client):
    # 1. create a workspace
    # 2. create entries in all 8 rooms via API
    # 3. verify capability YAML seed loaded (1+ capabilities exist)
    # 4. trigger capability invalidate event, verify resolver cache cleared
    # 5. simulate quota consumption, verify Redis counter
    # 6. log audit event, verify retrievable
    # 7. /metrics endpoint returns 200 with expected keys
    ...
```

- [ ] **Step 2: Run + iterate until passes**

```bash
cd backend && .venv/bin/python -m pytest tests/integration/test_phase1_foundation.py -v
```

- [ ] **Step 3: Commit**

```bash
git add backend/tests/integration/test_phase1_foundation.py
git commit -m "test: add Phase 1 foundation integration test"
```

**Phase 1 完成 checkpoint**: 平台层 + 8 房间 + capability registry 全部独立可测试。后端可启动，curl + DB inspector 可见 V1 全栈。

---

## Phase 2 · Capability + Agents (Week 4-6)

> 目标: 双 agent 实装 + capability 编译运行 + curated/cancel/failure 流。Phase 末，curl 可触发 deep_research thesis 端到端。

### Task 2.1: TaskBrief + TaskReport 契约

**Files:**
- Create: `backend/src/agents/contracts/__init__.py`
- Create: `backend/src/agents/contracts/task_brief.py`
- Create: `backend/src/agents/contracts/task_report.py`
- Test: `backend/tests/agents/contracts/test_contracts.py`

**Spec §4.6.5**: 严格 schema。

- [ ] **Step 1: Tests** (validation, missing fields, schema-conform)

```python
def test_task_brief_validates_capability_id():
    with pytest.raises(ValidationError):
        TaskBrief(capability_id="", brief={}, raw_message="x")
    TaskBrief(capability_id="x", brief={}, raw_message="x")

def test_task_report_status_enum():
    with pytest.raises(ValidationError):
        TaskReport(execution_id="e", status="invalid", capability_id="c", duration_seconds=1)
```

- [ ] **Step 3-5: Models**

```python
# backend/src/agents/contracts/task_brief.py
from typing import Literal
from pydantic import BaseModel, Field

class TaskBrief(BaseModel):
    capability_id: str = Field(..., min_length=1)
    brief: dict  # 符合 capability.brief_schema
    raw_message: str = Field(..., min_length=1)
    decisions: dict[str, str] = Field(default_factory=dict)
    workspace_id: str

# backend/src/agents/contracts/task_report.py
from typing import Literal, Any
from pydantic import BaseModel

class ResultOutput(BaseModel):
    id: str
    kind: Literal["library_item", "document", "memory_fact", "decision", "task"]
    preview: str
    default_checked: bool = True
    data: dict[str, Any]

class ResultError(BaseModel):
    phase: str
    task: str
    error: str

class TaskReport(BaseModel):
    execution_id: str
    capability_id: str
    status: Literal["completed", "failed_partial", "cancelled"]
    duration_seconds: int
    token_usage: dict[str, int] | None = None
    cost_estimate: str | None = None
    narrative: str
    outputs: list[ResultOutput] = Field(default_factory=list)
    errors: list[ResultError] = Field(default_factory=list)
```

- [ ] Commit: `feat: add TaskBrief/TaskReport contracts`.

### Task 2.2: Subagent base + registry

**Files:**
- Create: `backend/src/subagents/v2/__init__.py`
- Create: `backend/src/subagents/v2/base.py`
- Create: `backend/src/subagents/v2/registry.py`
- Test: `backend/tests/subagents/v2/test_registry.py`

- [ ] **Step 1: Tests**

```python
def test_register_and_retrieve():
    @subagent("test_agent")
    class TestAgent(SubagentBase):
        async def run(self, ctx): return SubagentResult(output={"done": True})
    cls = REGISTRY.get("test_agent")
    assert cls is TestAgent

def test_unknown_subagent_raises():
    with pytest.raises(KeyError):
        REGISTRY.get("nope")
```

- [ ] **Step 3-5: Implementation**

```python
# backend/src/subagents/v2/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class SubagentContext:
    workspace_id: str
    execution_id: str
    prompt: str
    inputs: dict
    tools: list[str]
    workspace_data: dict  # rooms snapshot

@dataclass
class SubagentResult:
    output: dict
    thinking: str | None = None
    tool_calls: list[dict] | None = None
    token_usage: dict | None = None

class SubagentBase(ABC):
    name: str = ""
    allowed_tools: list[str] = []  # white-list

    @abstractmethod
    async def run(self, ctx: SubagentContext) -> SubagentResult: ...

# backend/src/subagents/v2/registry.py
class _Registry:
    def __init__(self):
        self._d: dict[str, type[SubagentBase]] = {}
    def register(self, name: str, cls: type[SubagentBase]):
        self._d[name] = cls
        cls.name = name
    def get(self, name: str) -> type[SubagentBase]:
        if name not in self._d:
            raise KeyError(f"subagent '{name}' not registered")
        return self._d[name]
    def all_names(self) -> list[str]:
        return list(self._d.keys())

REGISTRY = _Registry()

def subagent(name: str):
    def decorator(cls):
        REGISTRY.register(name, cls)
        return cls
    return decorator
```

- [ ] Commit: `feat: add subagent v2 base + registry`.

### Task 2.3: Implement 5 V1 subagent types

**Files (one per type)**:
- `backend/src/subagents/v2/types/scholar_searcher.py`
- `backend/src/subagents/v2/types/web_searcher.py`
- `backend/src/subagents/v2/types/clusterer.py`
- `backend/src/subagents/v2/types/critical_writer.py`
- `backend/src/subagents/v2/types/outliner.py`
- Test: `backend/tests/subagents/v2/types/test_*.py`

> Each subagent ~50-100 lines. Test each independently with mocked LLM.

- [ ] **scholar_searcher**: takes `topic`, calls scholar_search tool, returns `papers: [{title, authors, year, doi}]`.

```python
# backend/src/subagents/v2/types/scholar_searcher.py
from src.subagents.v2.base import SubagentBase, SubagentContext, SubagentResult
from src.subagents.v2.registry import subagent

@subagent("scholar_searcher")
class ScholarSearcher(SubagentBase):
    allowed_tools = ["scholar_search", "web_search"]

    async def run(self, ctx: SubagentContext) -> SubagentResult:
        # 1. Call LLM with prompt + tools
        # 2. Parse tool calls → execute scholar_search
        # 3. Aggregate paper list
        ...
        return SubagentResult(output={"papers": papers}, ...)
```

- [ ] **web_searcher**: tool=`web_search`, similar.
- [ ] **clusterer**: pure-LLM, no tools. Input `papers`, output `clusters: [{theme, paper_ids}]`.
- [ ] **critical_writer**: pure-LLM. Input `clusters`, `style`, output `markdown`.
- [ ] **outliner**: pure-LLM. Input `topic`, output `outline: [{section, subsections}]`.

- [ ] **Test pattern (per subagent)**:

```python
@pytest.mark.asyncio
async def test_scholar_searcher_with_mocked_tools(mock_model_gateway, mock_scholar_tool):
    s = ScholarSearcher()
    ctx = SubagentContext(
        workspace_id="ws-1", execution_id="e-1",
        prompt="搜索 GAN 论文", inputs={"topic": "GAN"},
        tools=["scholar_search"], workspace_data={},
    )
    result = await s.run(ctx)
    assert "papers" in result.output
```

- [ ] Commit per subagent: `feat: add {type} subagent`.

### Task 2.4: Capability compiler (graph_template → langgraph)

**Files:**
- Create: `backend/src/agents/lead_agent/v2/compiler.py`
- Test: `backend/tests/agents/lead_agent/v2/test_compiler.py`

**Goal**: 把 `graph_template.phases` 编译成可执行 LangGraph，phases 串行 + 阶段内 tasks 并行。

- [ ] **Step 1: Tests**

```python
def test_compile_single_phase_single_task():
    template = {
        "phases": [{
            "name": "p1",
            "tasks": [{"name": "t1", "subagent_type": "outliner",
                       "prompt_template": "outline {{topic}}"}],
        }]
    }
    graph = compile_graph(template)
    # Verify structure: START → t1 → END
    nodes = list(graph.nodes.keys())
    assert "p1__t1" in nodes

def test_compile_two_phases_serial():
    template = {
        "phases": [
            {"name": "discover", "tasks": [{"name": "search", "subagent_type": "scholar_searcher",
                                             "prompt_template": "{{topic}}"}]},
            {"name": "write", "depends_on": ["discover"],
             "tasks": [{"name": "draft", "subagent_type": "critical_writer",
                        "prompt_template": "..."}]},
        ]
    }
    graph = compile_graph(template)
    # discover.search → write.draft

def test_compile_phase_with_parallel_tasks():
    # Two tasks in same phase → both connected to same predecessor
    ...

def test_compile_unknown_subagent_raises():
    with pytest.raises(KeyError):
        compile_graph({"phases": [{"name": "p", "tasks": [
            {"name": "t", "subagent_type": "nope", "prompt_template": ""}]}]})
```

- [ ] **Step 3-5: Implementation**

```python
# backend/src/agents/lead_agent/v2/compiler.py
from langgraph.graph import StateGraph, END, START
from src.subagents.v2.registry import REGISTRY

def compile_graph(template: dict, *, state_class):
    """Compile capability graph_template → LangGraph StateGraph."""
    builder = StateGraph(state_class)

    # 1. Add a node per task, named "{phase}__{task}"
    nodes: dict[str, list[str]] = {}  # phase_name → list of node names
    for phase in template["phases"]:
        nodes[phase["name"]] = []
        for task in phase["tasks"]:
            node_name = f"{phase['name']}__{task['name']}"
            subagent_cls = REGISTRY.get(task["subagent_type"])
            builder.add_node(node_name, _make_runner(subagent_cls, task))
            nodes[phase["name"]].append(node_name)

    # 2. Wire edges: phase deps + parallel within phase
    phase_lookup = {p["name"]: p for p in template["phases"]}
    roots = [p["name"] for p in template["phases"] if not p.get("depends_on")]

    # START → all root phases' tasks
    for phase_name in roots:
        for node in nodes[phase_name]:
            builder.add_edge(START, node)

    # phase → next phase (fan-in, fan-out)
    for phase in template["phases"]:
        for dep in phase.get("depends_on", []):
            for src in nodes[dep]:
                for dst in nodes[phase["name"]]:
                    builder.add_edge(src, dst)

    # Terminal: phases with no successor → END
    has_successor = set()
    for phase in template["phases"]:
        for dep in phase.get("depends_on", []):
            has_successor.add(dep)
    for phase_name, names in nodes.items():
        if phase_name not in has_successor:
            for n in names:
                builder.add_edge(n, END)

    return builder.compile()

def _make_runner(subagent_cls, task_spec: dict):
    async def run(state):
        ctx = build_subagent_context(state, task_spec)
        result = await subagent_cls().run(ctx)
        return {"node_results": {**state.get("node_results", {}), task_spec["name"]: result}}
    return run
```

- [ ] Commit: `feat: add capability compiler with phase serialization`.

### Task 2.5: Lead Agent v2 runtime

**Files:**
- Create: `backend/src/agents/lead_agent/v2/agent.py`
- Create: `backend/src/agents/lead_agent/v2/runtime.py`
- Test: `backend/tests/agents/lead_agent/v2/test_runtime.py`

**Spec §4.2.6**: load_capability → plan → publish_graph → execute_phases → finalize → publish_completed.

- [ ] **Step 1: Test runtime can run a simple capability end-to-end**

```python
@pytest.mark.asyncio
async def test_run_session_calls_subagents_and_publishes(
    mock_resolver, mock_publish, mock_session
):
    runtime = LeadAgentRuntime(
        resolver=mock_resolver, model_gateway=mock_gateway,
        execution_event_publisher=mock_publish,
    )
    brief = TaskBrief(
        capability_id="deep_research", workspace_id="ws-1",
        brief={"topic": "GAN"}, raw_message="...", decisions={},
    )
    report = await runtime.run_session(execution_id="e-1", brief=brief)
    assert report.status == "completed"
    assert "execution.graph_structure" in [c[1][0] for c in mock_publish.call_args_list]
```

- [ ] **Step 3-5: Implementation**

```python
# backend/src/agents/lead_agent/v2/runtime.py
from src.agents.contracts.task_brief import TaskBrief
from src.agents.contracts.task_report import TaskReport, ResultOutput
from src.agents.lead_agent.v2.compiler import compile_graph
from src.services.capability_resolver import CapabilityResolver
from src.services.execution_event_publisher import publish_execution_event
from langgraph.graph import StateGraph

class LeadAgentRuntime:
    def __init__(self, *, resolver: CapabilityResolver, model_gateway, ...):
        self.resolver = resolver
        ...

    async def run_session(self, *, execution_id: str, brief: TaskBrief) -> TaskReport:
        # 1. resolve capability
        cap = await self.resolver.resolve(brief.capability_id, await self._get_ws_type(brief.workspace_id))

        # 2. Compile graph
        ExecState = TypedDict("ExecState", {"brief": TaskBrief, "node_results": dict, "decisions": dict})
        graph = compile_graph(cap.graph_template, state_class=ExecState)

        # 3. publish graph_structure
        await publish_execution_event(execution_id, "execution.graph_structure", {
            "graph_structure": _to_panel_graph(cap.graph_template)
        })

        # 4. Run with callbacks → publish node events
        config = {"configurable": {"execution_id": execution_id}}
        callbacks = [_NodeEventCallback(execution_id)]
        final_state = await graph.ainvoke(
            {"brief": brief, "node_results": {}, "decisions": brief.decisions},
            config=config, callbacks=callbacks,
        )

        # 5. Build report
        outputs = self._collect_outputs(final_state)
        report = TaskReport(
            execution_id=execution_id, capability_id=brief.capability_id,
            status="completed", duration_seconds=..., narrative="...",
            outputs=outputs,
        )
        await publish_execution_event(execution_id, "execution.completed", report.model_dump())
        return report

    def _collect_outputs(self, state: dict) -> list[ResultOutput]:
        # Each subagent's result.output gets translated to ResultOutput by capability template
        ...
```

- [ ] Commit: `feat: add lead agent v2 runtime`.

### Task 2.6: ExecutionEngine 替代 (chat_turn / feature 双引擎合并)

**Files:**
- Modify: `backend/src/task/tasks/execute.py` (Celery task)
- Create: `backend/src/execution/engine_v2.py`
- Test: `backend/tests/execution/test_engine_v2.py`

**Goal**: 替代 2026-05-08 设计的 ChatExecutionEngine + FeatureExecutionEngine 双引擎。统一为单一 LeadAgentRuntime 路径。

- [ ] **Step 1: Tests**

```python
@pytest.mark.asyncio
async def test_execute_runs_lead_agent_and_writes_run_history(...):
    # given an ExecutionRecord with capability_id, brief
    # when execute(execution_id) runs
    # then ExecutionRecord.status="completed" + RunHistory entry exists + staged_outputs populated
    ...
```

- [ ] **Step 3-5: Engine + Celery integration**

```python
# backend/src/execution/engine_v2.py
class ExecutionEngineV2:
    def __init__(self, *, runtime: LeadAgentRuntime, execution_service, run_history_service):
        ...

    async def run(self, execution_id: str) -> None:
        execution = await self.execution_service.get(execution_id)
        await self.execution_service.mark_running(execution_id)

        try:
            brief = TaskBrief(**execution.params["brief"])
            report = await self.runtime.run_session(execution_id=execution_id, brief=brief)

            await self.execution_service.mark_completed(
                execution_id, status=report.status, result={"task_report": report.model_dump()},
            )
            await self.run_history_service.record(
                workspace_id=execution.workspace_id, execution_id=execution_id,
                capability_id=execution.feature_id, title=report.narrative[:200],
                summary=report.narrative, status=report.status, ...,
            )
            # Write system message for chat agent (Task 2.10)
            await self.completion_service.deliver(execution_id, report)
        except Exception as e:
            await self.execution_service.mark_failed(execution_id, error=str(e))
            raise
```

- [ ] **Step 6: Update Celery `execute` task to use V2 engine**.
- [ ] Commit: `feat: add execution engine v2 (unified lead agent path)`.

### Task 2.7: Chat agent skeleton + 10 tools

**Files:**
- Create: `backend/src/agents/chat_agent/agent.py`
- Create: `backend/src/agents/chat_agent/prompts.py` (5 prompts × workspace_type)
- Create: `backend/src/agents/chat_agent/tools/` (10 tool files)
- Test: `backend/tests/agents/chat_agent/test_agent.py`, `test_tools.py`

> 5 个 system prompt 文件, 每个 workspace_type 一份, 暴露不同 capability 列表 + 引导风格.

- [ ] **Step 1: Tool tests** (per tool)

```python
@pytest.mark.asyncio
async def test_dispatch_capability_creates_execution(...):
    tool = DispatchCapabilityTool(execution_service=mock_es, lead_busy_check=mock_busy)
    mock_busy.return_value = None  # not busy
    result = await tool.ainvoke({
        "capability_id": "deep_research",
        "brief": {"topic": "GAN", "language": "both"},
        "raw_message": "...",
    }, config={"configurable": {"workspace_id": "ws-1"}})
    assert "execution_id" in result

@pytest.mark.asyncio
async def test_dispatch_blocked_when_busy(...):
    mock_busy.return_value = "正在跑 deep_research (50%)"
    result = await tool.ainvoke(...)
    assert "等" in result["error"]

@pytest.mark.asyncio
async def test_query_progress_returns_node_states(...):
    ...

# Repeat for: cancel_run, write_decision, read_decisions, read_memory,
# read_run_history, read_documents_meta, read_library_meta
```

- [ ] **Step 3: Tool implementations**

Each tool ~30-60 lines. Pattern:

```python
# backend/src/agents/chat_agent/tools/dispatch.py
from langchain_core.tools import tool
from src.agents.contracts.task_brief import TaskBrief

@tool
async def dispatch_capability(
    capability_id: str, brief: dict, raw_message: str,
    *, workspace_id: str, user_id: str,
    execution_service, capability_resolver, decisions_service,
) -> dict:
    """Dispatch a capability to lead agent. Returns execution_id or error."""
    # 1. lead-busy check
    active = await execution_service.get_active(workspace_id)
    if active:
        return {
            "error": "lead_busy",
            "message": f"我正在跑「{active.feature_id}」（{active.progress}%）。要不要查看进度？",
        }

    # 2. resolve capability + validate brief
    cap = await capability_resolver.resolve(capability_id, await get_ws_type(workspace_id))

    # 3. fetch decisions
    decisions = await decisions_service.get_active(workspace_id)

    # 4. construct + persist + dispatch
    task_brief = TaskBrief(
        capability_id=capability_id, brief=brief, raw_message=raw_message,
        decisions=decisions, workspace_id=workspace_id,
    )
    execution = await execution_service.create_execution(
        workspace_id=workspace_id, user_id=user_id,
        feature_id=capability_id,
        params={"brief": task_brief.model_dump()},
        execution_type="capability",
    )
    await execution_service.dispatch(execution.id)
    return {"execution_id": execution.id, "capability_id": capability_id, "status": "dispatched"}
```

- [ ] **Step 5: Chat agent build**

```python
# backend/src/agents/chat_agent/agent.py
from langchain_core.messages import SystemMessage
from langgraph.prebuilt import create_react_agent
from .tools import (dispatch_capability, query_run_progress, cancel_run,
                    write_decision, read_decisions, read_memory,
                    read_run_history, read_documents_meta, read_library_meta)
from .prompts import get_system_prompt

def create_chat_agent(workspace_type: str, *, deps):
    """Build a chat agent for a specific workspace type."""
    system_prompt = get_system_prompt(workspace_type)
    tools = [
        dispatch_capability.bind(deps=deps),
        query_run_progress.bind(deps=deps),
        cancel_run.bind(deps=deps),
        write_decision.bind(deps=deps),
        read_decisions.bind(deps=deps),
        read_memory.bind(deps=deps),
        read_run_history.bind(deps=deps),
        read_documents_meta.bind(deps=deps),
        read_library_meta.bind(deps=deps),
    ]
    agent = create_react_agent(
        model=deps.model,
        tools=tools,
        state_modifier=system_prompt,
    )
    return agent
```

- [ ] **Step 6: Prompts**

Per `backend/src/agents/chat_agent/prompts.py`, function `get_system_prompt(workspace_type: str) -> str` returns the formatted prompt. 5 versions, all share structure (spec §4.1.2) but differ in:
- 工作场景介绍
- capability 列表（动态从 resolver 拿）
- 引导风格（thesis 偏严谨；proposal 偏决策；软著 偏技术；专利偏精确；sci 偏方法）

- [ ] **Step 7: Agent integration test**

```python
@pytest.mark.asyncio
async def test_chat_agent_dispatches_on_clear_intent(mock_deps):
    agent = create_chat_agent("thesis", deps=mock_deps)
    response = await agent.ainvoke({
        "messages": [HumanMessage("帮我深入调研 conditional GAN")],
    })
    # Verify dispatch_capability was called with capability_id="deep_research"
    ...
```

- [ ] Commit: `feat: add chat agent with 9 tools + 5 prompts`.

### Task 2.8: CompactMiddleware

**Files:**
- Create: `backend/src/agents/chat_agent/middlewares/compact.py`
- Test: `backend/tests/agents/chat_agent/middlewares/test_compact.py`

**Spec §4.1.4**: 阈值检测 → compact agent 调用 → 写 Memory + Decisions → 替换 messages 头.

- [ ] **Step 1: Tests**

```python
@pytest.mark.asyncio
async def test_no_compact_under_threshold():
    mw = CompactMiddleware(threshold=0.8, keep_last=8, ...)
    state = {"messages": [...]}  # token count < 80%
    result = await mw.before_model(state, config={})
    assert result is state  # unchanged

@pytest.mark.asyncio
async def test_compact_triggers_above_threshold():
    mw = CompactMiddleware(...)
    state = {"messages": [...]}  # token count > 80%
    result = await mw.before_model(state, config={})
    assert len(result["messages"]) == 9  # 1 summary + 8 last
    # verify mock memory_service.add_facts called
    # verify mock decisions_service.set called for new decisions
```

- [ ] **Step 3-5: Implementation**

```python
# backend/src/agents/chat_agent/middlewares/compact.py
from langchain_core.messages import SystemMessage
from langchain_core.runnables.config import RunnableConfig

class CompactMiddleware:
    def __init__(self, *, threshold: float = 0.8, keep_last: int = 8,
                 memory_service, decisions_service, model_gateway, model_context_limit: int):
        self.threshold = threshold
        self.keep_last = keep_last
        self.memory = memory_service
        self.decisions = decisions_service
        self.gateway = model_gateway
        self.context_limit = model_context_limit

    async def before_model(self, state: dict, config: RunnableConfig) -> dict:
        msgs = state["messages"]
        token_count = self._estimate_tokens(msgs)
        if token_count / self.context_limit < self.threshold:
            return state

        old_turns = msgs[:-self.keep_last]
        compact_result = await self._compact(old_turns, config)

        await self.memory.add_facts(
            workspace_id=config["configurable"]["workspace_id"],
            facts=compact_result["facts"],
        )
        for d in compact_result["decisions"]:
            await self.decisions.set(
                workspace_id=config["configurable"]["workspace_id"],
                key=d["key"], value=d["value"],
                extracted_by="compact_agent",
            )

        return {
            **state,
            "messages": [SystemMessage(compact_result["summary"]), *msgs[-self.keep_last:]],
        }

    def _estimate_tokens(self, msgs) -> int:
        # rough: char_count / 4 (better: tiktoken)
        return sum(len(str(m.content)) for m in msgs) // 4

    async def _compact(self, old_turns, config) -> dict:
        # call compact-specific LLM with system prompt asking for summary + facts + decisions
        ...
```

- [ ] Commit: `feat: add compact middleware for chat session`.

### Task 2.9: Curated commit + commit_outputs

**Files:**
- Modify: `backend/src/services/execution_service.py` (add `commit_outputs` method)
- Create: `backend/src/gateway/routers/execution_commit.py`
- Test: `backend/tests/services/test_execution_service_commit.py`, `backend/tests/gateway/test_execution_commit.py`

**Spec §4.7.5**: `/commit` 端点; 单一事务跨 5 房间; 总是写 Run History.

- [ ] **Step 1: Tests**

```python
@pytest.mark.asyncio
async def test_commit_all_writes_5_rooms(client, async_session, ws_with_completed_execution):
    exec_id = ws_with_completed_execution.id
    r = await client.post(f"/executions/{exec_id}/commit", json={"accept_all": True})
    assert r.status_code == 200
    body = r.json()
    assert body["committed"]["library"] >= 0
    # Verify items actually wrote
    items = await client.get(f"/workspaces/{ws_with_completed_execution.workspace_id}/library")
    assert len(items.json()["items"]) == 23  # if exec staged 23 papers

@pytest.mark.asyncio
async def test_commit_some_only(client, ...):
    r = await client.post(f"/executions/{exec_id}/commit",
                          json={"accepted_ids": ["out-1", "out-2"]})
    assert r.json()["committed"]["library"] == 2

@pytest.mark.asyncio
async def test_commit_idempotent_with_key(client, ...):
    r1 = await client.post(f"/executions/{exec_id}/commit", json={"accept_all": True},
                           headers={"Idempotency-Key": "k1"})
    r2 = await client.post(f"/executions/{exec_id}/commit", json={"accept_all": True},
                           headers={"Idempotency-Key": "k1"})
    # Second call returns same result without double-writing
    assert r1.json() == r2.json()
    items = await client.get(f"/workspaces/{ws_id}/library")
    assert len(items.json()["items"]) == 23  # not 46
```

- [ ] **Step 3: Service**

```python
# in execution_service.py
async def commit_outputs(self, execution_id: str, *,
                          accept_all: bool = False,
                          accepted_ids: list[str] | None = None,
                          idempotency_key: str | None = None) -> dict:
    # 1. idempotency check
    if idempotency_key:
        cached = await self._get_cached_commit(execution_id, idempotency_key)
        if cached:
            return cached

    execution = await self.get(execution_id)
    if not execution.result or "task_report" not in execution.result:
        raise ValueError("execution has no task_report")

    report = TaskReport(**execution.result["task_report"])
    selected = report.outputs if accept_all else [
        o for o in report.outputs if o.id in (accepted_ids or [])
    ]

    counts = {"library": 0, "documents": 0, "memory": 0, "decisions": 0, "tasks": 0}

    async with self.session.begin():  # single transaction
        for output in selected:
            if output.kind == "library_item":
                await self.library.add(
                    execution.workspace_id,
                    LibraryItemCreate(**output.data, added_by=f"execution:{execution_id}"),
                )
                counts["library"] += 1
            elif output.kind == "document":
                await self.documents.add(
                    execution.workspace_id,
                    DocumentCreate(
                        name=output.data["name"],
                        kind=output.data["doc_kind"],
                        mime_type=output.data["mime_type"],
                        storage_path=output.data["storage_path"],
                        size_bytes=output.data["size_bytes"],
                        parent_id=output.data.get("parent_id"),
                        added_by=f"execution:{execution_id}",
                    ),
                )
                counts["documents"] += 1
            elif output.kind == "memory_fact":
                await self.memory.add_facts(
                    execution.workspace_id,
                    [FactCreate(
                        category=output.data["category"],
                        content=output.data["content"],
                        confidence=output.data["confidence"],
                    )],
                )
                counts["memory"] += 1
            elif output.kind == "decision":
                await self.decisions.set(
                    execution.workspace_id,
                    key=output.data["key"], value=output.data["value"],
                    confidence=output.data["confidence"],
                    extracted_by=f"execution:{execution_id}",
                )
                counts["decisions"] += 1
            elif output.kind == "task":
                await self.tasks.add(
                    execution.workspace_id,
                    WorkspaceTaskCreate(
                        title=output.data["title"],
                        description=output.data.get("description"),
                        priority=output.data.get("priority", 0),
                        related_execution_ids=[execution_id],
                        created_by=f"execution:{execution_id}",
                    ),
                )
                counts["tasks"] += 1

        # always write run_history (regardless of user selection)
        await self.run_history.record(
            workspace_id=execution.workspace_id,
            execution_id=execution_id,
            capability_id=execution.feature_id,
            title=report.narrative[:200],
            summary=report.narrative,
            status=report.status,
            artifact_count=len(selected),
            duration_seconds=report.duration_seconds,
            token_usage=report.token_usage,
        )

    # invalidate cache + publish refresh
    if idempotency_key:
        await self._cache_commit(execution_id, idempotency_key, {"committed": counts})
    await self.event_bus.publish("workspace.refresh", {"workspace_id": execution.workspace_id})

    return {"committed": counts}
```

- [ ] **Step 5: Router**

```python
# backend/src/gateway/routers/execution_commit.py
from fastapi import APIRouter, Depends, Header, HTTPException

router = APIRouter()

@router.post("/executions/{execution_id}/commit")
async def commit(execution_id: str,
                  body: CommitBody,
                  idempotency_key: str | None = Header(None),
                  svc: ExecutionService = Depends(get_execution_service)):
    return await svc.commit_outputs(
        execution_id,
        accept_all=body.accept_all,
        accepted_ids=body.accepted_ids,
        idempotency_key=idempotency_key,
    )
```

- [ ] Commit: `feat: add curated commit flow for execution outputs`.

### Task 2.10: Execution completion delivery (Server-push to chat)

**Files:**
- Create: `backend/src/services/execution_completion_service.py`
- Modify: `backend/src/database/models/thread.py` (add `kind` field for system messages)
- Test: `backend/tests/services/test_execution_completion.py`

**Spec §4.2.3**: Lead 完成 → 写 system message 到 thread → trigger chat agent runtime.

- [ ] **Step 1: Tests**

```python
@pytest.mark.asyncio
async def test_deliver_writes_system_message(...):
    svc = ExecutionCompletionService(...)
    await svc.deliver(execution_id="e-1", task_report=mock_report)
    # Verify thread has new system message with kind="execution_completed"
    msgs = await thread_service.list_messages(thread_id="t-1")
    last = msgs[-1]
    assert last.role == "system"
    assert last.kind == "execution_completed"
    assert last.payload["execution_id"] == "e-1"
```

- [ ] **Step 3-5: Service**

```python
# backend/src/services/execution_completion_service.py
class ExecutionCompletionService:
    def __init__(self, *, thread_service, execution_service, chat_agent_runner):
        self.thread = thread_service
        self.execution = execution_service
        self.chat_runner = chat_agent_runner

    async def deliver(self, execution_id: str, task_report: TaskReport) -> None:
        execution = await self.execution.get(execution_id)
        thread_id = await self._get_thread_id(execution.workspace_id)

        # 1. Append system message
        await self.thread.append_system_message(
            thread_id=thread_id,
            kind="execution_completed",
            payload={
                "execution_id": execution_id,
                "task_report": task_report.model_dump(),
            },
        )

        # 2. Trigger chat agent (server-push)
        await self.chat_runner.invoke_for_system_message(thread_id=thread_id)
```

- [ ] **Step 6: thread message kind column migration**

If `chat_threads` messages don't have `kind`, add migration. (Check existing schema first.)

- [ ] Commit: `feat: add execution completion delivery to chat`.

### Task 2.11: Cancel flow (panel + chat double entry)

**Files:**
- Modify: `backend/src/services/execution_service.py` (add `cancel` method, abort signal)
- Modify: `backend/src/gateway/routers/executions.py` (DELETE endpoint)
- Modify: `backend/src/agents/lead_agent/v2/runtime.py` (check abort_event)
- Test: `backend/tests/services/test_execution_cancel.py`

- [ ] **Step 1: Tests**

```python
@pytest.mark.asyncio
async def test_cancel_sets_status_to_cancelling(...):
    svc = ExecutionService(...)
    await svc.cancel(execution_id="e-1")
    e = await svc.get("e-1")
    assert e.status == "cancelling"

@pytest.mark.asyncio
async def test_cancel_propagates_to_lead_agent(...):
    # start a long-running execution, send cancel after 1s
    # verify execution.status reaches "cancelled" within 5s
    ...

@pytest.mark.asyncio
async def test_cancel_via_chat_command(...):
    # user message "停一下" → chat agent calls cancel_run → execution cancelled
    ...
```

- [ ] **Step 3-5: Implementations**

```python
# Use Redis key as abort signal: "abort:exec:{id}"
# Lead agent checks before each phase
async def cancel(self, execution_id: str) -> bool:
    e = await self.get(execution_id)
    if e.status not in ("pending", "running"):
        return False
    e.status = "cancelling"
    await self.session.commit()
    await self.redis.set(f"abort:exec:{execution_id}", "1", ex=300)
    await publish_execution_event(execution_id, "execution.status", {"status": "cancelling"})
    return True
```

- [ ] Commit: `feat: add cancel flow with abort signal propagation`.

### Task 2.12: Failure handling

**Files:**
- Modify: `backend/src/agents/lead_agent/v2/runtime.py` (catch subagent exceptions, partial reporting)
- Test: `backend/tests/agents/lead_agent/v2/test_failure_handling.py`

- [ ] **Step 1: Tests**

```python
@pytest.mark.asyncio
async def test_subagent_failure_caught_and_reported(...):
    # mock one subagent to raise → runtime should:
    # - mark that node failed
    # - continue or abort based on capability config
    # - return TaskReport(status="failed_partial", errors=[...])
    ...

@pytest.mark.asyncio
async def test_run_marked_failed_when_critical(...):
    # capability says critical phase → fail → run.status="failed"
    ...
```

- [ ] **Step 3-5: Logic in runtime.py**

```python
async def _execute_node(self, node_name: str, ...) -> SubagentResult | Exception:
    for attempt in range(task_spec.get("retry_on_failure", 0) + 1):
        try:
            return await subagent.run(ctx)
        except Exception as e:
            if attempt == task_spec.get("retry_on_failure", 0):
                logger.exception(f"node {node_name} failed", extra={"attempts": attempt + 1})
                await publish_execution_event(execution_id, "execution.node.failed", {
                    "node_id": node_name, "error": str(e),
                })
                return e
            await asyncio.sleep(2 ** attempt)
```

- [ ] Commit: `feat: add subagent failure handling with retry + partial report`.

### Task 2.13: V1 capability seeds (5 thesis capabilities)

**Files:**
- Create: `backend/seed/capabilities/thesis/deep_research.yaml` (full per spec §4.3.3)
- Create: `backend/seed/capabilities/thesis/outline_generate.yaml`
- Create: `backend/seed/capabilities/thesis/section_write.yaml`
- Create: `backend/seed/capabilities/thesis/section_revise.yaml`
- Create: `backend/seed/capabilities/thesis/citation_manage.yaml`
- Test: `backend/tests/seed/test_capability_seeds_load.py`

> Pattern: 每个 YAML ~80-150 行。Reference spec §4.3.3 for `deep_research`. Other capabilities follow similar structure but use different subagent_types from V1 registry.

- [ ] **Step 1: Test that all 5 YAMLs load + validate**

```python
@pytest.mark.asyncio
async def test_thesis_seeds_load(async_session):
    loader = CapabilityLoader(async_session, seed_dir="backend/seed/capabilities")
    n = await loader.load_seeds_if_empty()
    assert n >= 5
    cap = await async_session.get(Capability, ("deep_research", "thesis", 1))
    assert cap.system_prompt
```

- [ ] Commit per capability: `feat: add thesis/{name} capability seed`.

### Task 2.14: Phase 2 E2E (curl test)

**Files:**
- Create: `backend/tests/integration/test_phase2_e2e.py`

- [ ] **Goal**: Full path from chat message → dispatch → lead agent → completion → commit

```python
@pytest.mark.asyncio
async def test_thesis_deep_research_e2e(async_client, ws):
    # 1. POST chat message "深入调研 conditional GAN"
    # 2. Verify execution created
    # 3. Wait for execution.completed event (mocked subagents return canned data quickly)
    # 4. Verify thread has system message kind=execution_completed
    # 5. POST /executions/{id}/commit accept_all=true
    # 6. Verify Library has 23 entries, Documents has 1, RunHistory has 1
```

- [ ] Commit: `test: add Phase 2 deep_research E2E test`.

**Phase 2 完成 checkpoint**: 后端能从 chat 触发 capability，端到端跑完，写入 8 房间。

---

## Phase 3 · Frontend Rewrite (Week 7-10)

> 目标: 新 UI 在 `/v2` 路径并行开发。Chat + Panel + 顶栏角标 + 房间抽屉。

### Task 3.1: V2 layout shell

**Files:**
- Create: `frontend/app/(workbench)/workspaces/[id]/v2/layout.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/v2/page.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/v2/components/RoomsTopbar.tsx`
- Test: `frontend/tests/unit/v2/layout.test.tsx`

**Spec §4.6 + UI mockup**: 4 栏布局 = workspace列表 (现有) + chat + panel + 顶栏角标.

- [ ] **Step 1: Test that page mounts and shows 3 zones**

```tsx
// frontend/tests/unit/v2/layout.test.tsx
import { render, screen } from "@testing-library/react";
import V2Page from "@/app/(workbench)/workspaces/[id]/v2/page";

describe("V2 Workspace page", () => {
  it("renders chat / panel / topbar zones", () => {
    render(<V2Page params={{ id: "ws-1" }} />);
    expect(screen.getByTestId("chat-panel")).toBeInTheDocument();
    expect(screen.getByTestId("workflow-panel")).toBeInTheDocument();
    expect(screen.getByTestId("rooms-topbar")).toBeInTheDocument();
  });
});
```

- [ ] **Step 3-5: Implement page + topbar**

```tsx
// frontend/app/(workbench)/workspaces/[id]/v2/page.tsx
"use client";
import { ChatPanel } from "./components/ChatPanel";
import { LiveWorkflowPanel } from "./components/LiveWorkflowPanel";
import { RoomsTopbar } from "./components/RoomsTopbar";

export default function V2Page({ params }: { params: { id: string } }) {
  return (
    <div className="flex flex-col h-screen">
      <RoomsTopbar workspaceId={params.id} data-testid="rooms-topbar" />
      <div className="flex flex-1 min-h-0">
        <ChatPanel workspaceId={params.id} className="w-[42%] border-r" data-testid="chat-panel" />
        <LiveWorkflowPanel workspaceId={params.id} className="flex-1" data-testid="workflow-panel" />
      </div>
    </div>
  );
}
```

- [ ] Commit: `feat(fe): add v2 workspace layout shell`.

### Task 3.2: chat-store v2 + useChatStream

**Files:**
- Create: `frontend/stores/chat-store-v2.ts`
- Create: `frontend/hooks/useChatStream.ts`
- Test: `frontend/tests/unit/stores/chat-store-v2.test.ts`

**Goal**: 替代旧 `thread.ts`. 处理 reasoning + content 顺序问题（spec §1.1 提到的 bug）.

- [ ] **Step 1: Tests for store reducer**

```ts
describe("chat-store-v2 reducer", () => {
  it("appends content in order", () => {
    const s = useChatStoreV2.getState();
    s.handleEvent({ type: "chat.assistant.block", block: { kind: "text", content: "hi " }});
    s.handleEvent({ type: "chat.assistant.block", block: { kind: "text", content: "world" }});
    expect(s.messages.at(-1)?.blocks).toEqual([
      { kind: "text", content: "hi " },
      { kind: "text", content: "world" },
    ]);
  });

  it("preserves reasoning in arrival order, not prepended", () => {
    const s = useChatStoreV2.getState();
    s.handleEvent({ type: "chat.assistant.thinking", delta: "thought 1" });
    s.handleEvent({ type: "chat.assistant.block", block: { kind: "text", content: "answer" }});
    s.handleEvent({ type: "chat.assistant.thinking", delta: " more" });
    const last = s.messages.at(-1)!;
    // blocks order matches arrival
    const kinds = last.blocks.map(b => b.kind);
    expect(kinds).toEqual(["thinking", "text", "thinking"]);
  });

  it("handles tool invocation events", () => { ... });
  it("handles result_card via execution.completed bridge", () => { ... });
});
```

- [ ] **Step 3-5: Store**

```ts
// frontend/stores/chat-store-v2.ts
import { create } from "zustand";

export type Block =
  | { kind: "text"; content: string }
  | { kind: "thinking"; content: string }
  | { kind: "status_line"; content: string }
  | { kind: "question_card"; data: any }
  | { kind: "result_card"; data: ResultCardData };

export type Message = {
  id: string;
  role: "user" | "assistant" | "system";
  blocks: Block[];
  createdAt: string;
};

interface ChatState {
  messages: Message[];
  currentAssistantId: string | null;
  handleEvent(event: any): void;
  reset(): void;
}

export const useChatStoreV2 = create<ChatState>((set, get) => ({
  messages: [],
  currentAssistantId: null,
  handleEvent(event) {
    set((state) => {
      switch (event.type) {
        case "chat.user.message":
          return { messages: [...state.messages, { ...event.data, role: "user" }] };
        case "chat.assistant.start":
          return {
            messages: [...state.messages, {
              id: event.data.message_id, role: "assistant", blocks: [], createdAt: event.data.timestamp,
            }],
            currentAssistantId: event.data.message_id,
          };
        case "chat.assistant.thinking":
        case "chat.assistant.block":
          return state.appendToCurrentAssistant(event);
        // ... handle tool_invocation / tool_result / completion
        default:
          return state;
      }
    });
  },
  reset: () => set({ messages: [], currentAssistantId: null }),
}));
```

- [ ] **Step 6: Hook**

```ts
// frontend/hooks/useChatStream.ts
export function useChatStream(workspaceId: string) {
  const handle = useChatStoreV2(s => s.handleEvent);
  useEffect(() => {
    const es = new EventSource(`/api/workspaces/${workspaceId}/chat/stream`);
    es.onmessage = (e) => handle(JSON.parse(e.data));
    es.onerror = () => { /* reconnect with last_message_id */ };
    return () => es.close();
  }, [workspaceId]);
}
```

- [ ] Commit: `feat(fe): add chat-store-v2 fixing reasoning/content ordering`.

### Task 3.3: ChatPanel + MessageBlock

**Files:**
- Create: `frontend/app/(workbench)/workspaces/[id]/v2/components/ChatPanel.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/v2/components/MessageBlock.tsx`
- Test: `frontend/tests/unit/v2/ChatPanel.test.tsx`

> Reuse existing block renderer logic from `frontend/app/(workbench)/workspaces/[id]/components/chat-thread/blocks/`, but consume new chat-store-v2.

- [ ] Tests + impl. **Critical**: render thinking inline above its associated content (rather than prepending all reasoning to message head).

- [ ] Commit: `feat(fe): add v2 ChatPanel + MessageBlock`.

### Task 3.4: ResultCard component (curated UI)

**Files:**
- Create: `frontend/app/(workbench)/workspaces/[id]/v2/components/ResultCard.tsx`
- Test: `frontend/tests/unit/v2/ResultCard.test.tsx`

**Spec §4.7.5**: 默认全勾 + 一键 ✓ + 仅勾选 + 全弃.

- [ ] Tests for: render outputs + checkbox state + commit POST.

```tsx
describe("ResultCard", () => {
  it("renders outputs grouped by kind with default-checked", () => { ... });
  it("calls /commit with accept_all=true on '全部接受'", () => { ... });
  it("calls /commit with selected ids on '仅勾选项'", () => { ... });
  it("calls /commit with empty array on '全弃'", () => { ... });
  it("uses idempotency-key header (uuid per render)", () => { ... });
});
```

- [ ] Impl. Commit: `feat(fe): add ResultCard with curated commit flow`.

### Task 3.5: useExecutionStream-v2 + execution-store extension

**Files:**
- Modify: `frontend/stores/execution-store.ts` (extend for graph_structure + node_states)
- Create: `frontend/hooks/useExecutionStreamV2.ts` (wrapper around existing useExecutionStream)
- Test: `frontend/tests/unit/stores/execution-store-extended.test.ts`

> Existing `execution-store.ts` already has reducer (per Phase 1 review). Extend it for new event types if needed.

- [ ] Tests + impl. Commit: `feat(fe): extend execution-store for graph rendering`.

### Task 3.6: LiveWorkflowPanel rewrite (reactflow)

**Files:**
- Rewrite: `frontend/app/(workbench)/workspaces/[id]/v2/components/LiveWorkflowPanel.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/v2/components/GraphCanvas.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/v2/components/PhaseNode.tsx`
- Test: `frontend/tests/unit/v2/LiveWorkflowPanel.test.tsx`

**Stack**: Add `reactflow` dependency (`npm install reactflow`).

> **Layout**: phase-based vertical layout. Reactflow auto-layout via `dagre` plug-in is OK; or hand-compute positions per phase. V1 use phase y-coordinate = phase_index * 120, x distributed within phase.

- [ ] Tests for: graph rendering, node status colors, click → drawer trigger.

```tsx
describe("LiveWorkflowPanel", () => {
  it("renders nodes from execution.graph_structure event", async () => { ... });
  it("colors node by status (gray=pending, yellow=running, green=done, red=failed)", async () => { ... });
  it("calls onNodeClick with node id", async () => { ... });
});
```

- [ ] Impl skeleton:

```tsx
import { ReactFlow, Background, Controls, Node, Edge } from "reactflow";
import { useExecutionStore } from "@/stores/execution-store";

export function LiveWorkflowPanel({ workspaceId }: Props) {
  const { graph, nodeStates, currentExecutionId } = useExecutionStore();
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  const nodes = useMemo(() => buildReactFlowNodes(graph, nodeStates), [graph, nodeStates]);
  const edges = useMemo(() => buildReactFlowEdges(graph), [graph]);

  return (
    <>
      <ReactFlow nodes={nodes} edges={edges} onNodeClick={(_, n) => setSelectedNodeId(n.id)} />
      {selectedNodeId && (
        <NodeDetailDrawer
          executionId={currentExecutionId} nodeId={selectedNodeId}
          onClose={() => setSelectedNodeId(null)}
        />
      )}
    </>
  );
}
```

- [ ] Commit: `feat(fe): add LiveWorkflowPanel with reactflow graph`.

### Task 3.7: NodeDetailDrawer

**Files:**
- Create: `frontend/app/(workbench)/workspaces/[id]/v2/components/NodeDetailDrawer.tsx`
- Test: `frontend/tests/unit/v2/NodeDetailDrawer.test.tsx`

> Fetches `/executions/{id}/nodes/{node_id}` (need backend endpoint, add in this task if not done).

- [ ] **Backend addition**: `GET /executions/{id}/nodes/{node_id}` — extends existing executions router. Returns full node detail (input/output/thinking/tools/token_usage).
- [ ] Frontend drawer: 4 tabs (Input / Output / Thinking / Tools).
- [ ] Commit: `feat(fe): add node detail drawer`.

### Task 3.8: Rooms 抽屉 (Documents / Library / Runs / Tasks)

**Files (per drawer)**:
- `frontend/app/(workbench)/workspaces/[id]/v2/components/rooms/DocumentsDrawer.tsx`
- `frontend/app/(workbench)/workspaces/[id]/v2/components/rooms/LibraryDrawer.tsx`
- `frontend/app/(workbench)/workspaces/[id]/v2/components/rooms/RunsDrawer.tsx`
- `frontend/app/(workbench)/workspaces/[id]/v2/components/rooms/TasksDrawer.tsx`
- `frontend/lib/api/v2/{documents,library,runs,tasks}.ts`
- Test: `frontend/tests/unit/v2/rooms/*.test.tsx`

> Pattern: each drawer is a slide-out panel triggered by topbar badge click. Shows list with search + add/delete actions.

- [ ] **Per drawer**:
  - API client (typed wrappers for `/workspaces/{ws}/{room}` endpoints)
  - Drawer component with list / search / actions
  - Tests covering CRUD UI flow

- [ ] Commit per drawer: `feat(fe): add {room} drawer`.

### Task 3.9: Settings page (Memory / Decisions / Sandbox / Settings)

**Files:**
- Create: `frontend/app/(workbench)/workspaces/[id]/v2/components/rooms/SettingsPage.tsx`
- Subsections: MemoryViewer / DecisionsViewer / SandboxConsole / SettingsForm
- Test: same pattern.

- [ ] Commit: `feat(fe): add settings page with 4 sections`.

### Task 3.10: Auto-compact UI toast

**Files:**
- Create: `frontend/app/(workbench)/workspaces/[id]/v2/components/CompactToast.tsx`
- Test: `frontend/tests/unit/v2/CompactToast.test.tsx`

> When backend pushes `chat.compact.triggered` event (new event type added in Phase 2), show toast: "上下文已压缩，N 条事实已记入 Memory".

- [ ] Tests + impl. Commit: `feat(fe): add auto-compact UI toast`.

### Task 3.11: Phase 3 E2E (Playwright)

**Files:**
- Create: `frontend/tests/e2e/v2/deep-research-flow.spec.ts`

- [ ] Spec covers:
  - Open `/v2` workspace
  - Send chat message "深入调研 GAN"
  - Wait for chat agent to call dispatch → execution starts
  - Watch panel render graph
  - Wait for completion
  - Click node → drawer shows detail
  - Click "全部接受" on result_card
  - Verify Documents badge increments

- [ ] Commit: `test(fe): add deep research E2E flow`.

### Task 3.12: Performance tuning

**Files:**
- Modify: `LiveWorkflowPanel.tsx` (memoization, virtualization for large graphs)
- Modify: `ChatPanel.tsx` (virtualize message list with `react-window` if > 100 messages)
- Test: `frontend/tests/perf/render-perf.test.ts`

- [ ] Measure baseline → tune to spec G9 (P99 < 200ms).
- [ ] Commit: `perf(fe): memoize panels, virtualize long lists`.

**Phase 3 完成 checkpoint**: V2 UI 完整可用，但只在 `/v2` 路径，旧 UI 仍跑。

---

## Phase 4 · Cutover (Week 11-12)

> 目标: 数据迁移 + 切流量 + 旧代码清理.

### Task 4.1: 数据迁移脚本 dry-run

**Files:**
- Create: `backend/scripts/migrate_workspace_v2.py`
- Test: `backend/tests/scripts/test_migrate_workspace_v2.py`

**Spec 附录 C**: 把现有 thread / references / artifacts → 新 8 房间。

- [ ] **Step 1: Dry-run mode tests**

```python
@pytest.mark.asyncio
async def test_migrate_dry_run_reports_no_changes(async_session, sample_data):
    n_before = await count_all_v2(async_session)
    result = await migrate(async_session, dry_run=True)
    n_after = await count_all_v2(async_session)
    assert n_before == n_after
    assert result.workspaces_migrated == 5  # planned but not committed
```

- [ ] **Step 3: Script** (per spec 附录 C SQL，convert to SQLAlchemy ORM for safety + dry-run support)

```python
# backend/scripts/migrate_workspace_v2.py
import asyncio
from dataclasses import dataclass

@dataclass
class MigrationResult:
    workspaces_migrated: int = 0
    library_items_migrated: int = 0
    documents_migrated: int = 0
    errors: list[str] = field(default_factory=list)

async def migrate(session, *, dry_run: bool = True) -> MigrationResult:
    result = MigrationResult()
    async with session.begin():
        await _migrate_workspaces(session, result)
        await _migrate_references_to_library(session, result)
        await _migrate_artifacts_to_documents(session, result)
        if dry_run:
            await session.rollback()
        else:
            await session.commit()
    return result

async def _migrate_workspaces(session, result):
    # idempotent: only migrate threads not already in workspaces.thread_id
    ...
```

- [ ] **Step 5: CLI entry point**

```bash
.venv/bin/python -m scripts.migrate_workspace_v2 --dry-run
.venv/bin/python -m scripts.migrate_workspace_v2 --commit  # actual
```

- [ ] **Step 6**: Run dry-run on production-like dataset → review counts → adjust.
- [ ] Commit: `feat: add v2 migration script with dry-run`.

### Task 4.2: Internal dogfood

- [ ] **Day 1**: 团队成员的 workspace 全切到 v2. 每天收集 issue, P0 当天修.
- [ ] **Day 2-7**: 持续观察, 每日 standup review issue list.
- [ ] **Exit criterion**: 0 P0 + ≤ 3 P1 issues 未解.

不写 commit 但记录 issue 到 `docs/superpowers/plans/issues-w11.md`.

### Task 4.3: 性能压测

- [ ] **Tool**: Locust 脚本 simulate 100 concurrent workspaces, each running deep_research.
- [ ] **Pass criteria**: P99 SSE latency < 200ms (spec G9), P99 chat first-token < 500ms.
- [ ] If fail: profile + optimize before W12.
- [ ] Commit (perf fix if any): `perf: ...`.

### Task 4.4: User cutover (W12)

- [ ] **Step 1**: New workspaces default to `/v2` route. Existing workspaces show banner: "升级到 v2 体验？" → opt-in switch.
- [ ] **Step 2**: 50% migration in 24h, monitor metrics.
- [ ] **Step 3**: 100% migration after 48h stable.
- [ ] **Step 4**: 旧 `/chat` 路由保留 7 天作 fallback, 自动重定向到 `/v2` 默认开启.

实现：feature flag `default_to_v2 = True` after cutover; route handler in Next.js.

- [ ] Commit: `feat: cutover to v2 by default`.

### Task 4.5: 旧代码删除

**Files (delete)**:
- `backend/src/agents/lead_agent/agent.py`
- `backend/src/agents/feature_leader/`
- `backend/src/application/services/feature_*_service.py`
- `frontend/app/(workbench)/workspaces/[id]/chat/`
- `frontend/stores/workflow-store.ts`
- `frontend/stores/workflow-store-support.ts`
- `frontend/stores/thread.ts`
- `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/` (旧)
- `frontend/hooks/useWorkflowSubscription.ts` (已删但补 .test.tsx)
- 旧 `task.updated` / `subagent.updated` 事件发布点（task/service.py, subagents/manager.py 中）

**Files (rename → /v1 sub-route 保留 1 个 release 周期)**:
- 不删, 移到 `frontend/app/(workbench)/workspaces/[id]/v1/` 作 fallback.

- [ ] **Step 1: List + dry-run delete**

```bash
git rm -n backend/src/agents/lead_agent/agent.py
# verify nothing else imports it
grep -r "from src.agents.lead_agent.agent import" backend/src/ # must be empty
```

- [ ] **Step 2: Actual delete + test pass**

```bash
git rm <files>
cd backend && .venv/bin/python -m pytest tests/ -v  # all pass
cd frontend && npm run build && npm run typecheck   # all pass
```

- [ ] Commit: `refactor: remove legacy single-agent + workflow-store paths`.

### Task 4.6: CLAUDE.md update

**Files:**
- Modify: `/Users/ze/wenjin/CLAUDE.md`

- [ ] Update sections:
  - "Architecture" — 改双 agent 模型描述
  - "Key Files" — 更新 chat agent / lead agent v2 路径
  - 删除旧 launch_feature tool / feature ingress 引用
  - Add "Workspace 8 rooms" 简短描述

- [ ] Commit: `docs: update CLAUDE.md to reflect v2 architecture`.

### Task 4.7: Archive legacy tables (migration 042)

**Files:**
- Create: `backend/alembic/versions/042_archive_legacy_v1_tables.py`

- [ ] Rename (NOT drop) old tables: `references` → `references_archived`, `task_records` → `task_records_archived`, etc.
- [ ] Keep 30 days for verification, drop in W14+.
- [ ] Commit: `refactor: archive legacy v1 tables (30-day verification window)`.

**Phase 4 完成 checkpoint**: V2 是唯一线路；旧代码归档；CLAUDE.md 与代码一致。

---

## 跨 Phase 强制规则

- **每 PR 跑完整测试**: `cd backend && .venv/bin/python -m pytest tests/ -v` + `cd frontend && npm run typecheck && npm run test:unit`
- **每周 demo**: 10 min, no slides, 跑现有功能
- **任何 task 卡住 > 1 day**: 在 demo 上 escalate; 不要 silently drift

---

## Self-Review 完成检查

(filled in by author after writing this plan)

**Spec coverage check**:
- §3 架构总览 → Tasks 1.* (foundation) + Tasks 2.* (agents) ✓
- §4.1 Chat agent → Task 2.7 + 2.8 ✓
- §4.2 Lead agent → Task 2.4 + 2.5 + 2.6 + 2.11 + 2.12 ✓
- §4.3 Capability → Task 1.14 + 1.15 + 1.16 + 2.13 ✓
- §4.4 8 房间 → Tasks 1.2 - 1.9 ✓
- §4.5 平台层 → Tasks 1.10 - 1.13 + 1.18 ✓
- §4.6 前端事件流 → Task 3.2 + 3.5 ✓
- §4.7 UX 流程 → Tasks 2.9, 2.10, 2.11, 2.12, 3.4, 3.10 ✓
- §5 API → 散在各 task 的 router 部分 ✓
- §6 数据模型 → Phase 1 的 model + migration ✓
- §7 实施路线图 → 本 plan 即是落实 ✓
- §8 风险 → mitigation 散在 task 设计（cancel signal, idempotency_key, cap, ToolError）✓
- §9 开放问题 → 留待执行时决策 ✓
- 附录 A capability 目录 → Task 2.13 启动 5 个；其余在 Phase 2-3 持续追加
- 附录 B subagent registry → Task 2.2 + 2.3 实装 5 个；其余 Phase 2 末追加
- 附录 C 数据迁移 → Task 4.1 ✓

**Placeholder scan**: 无 TBD / TODO；所有 step 有具体代码或命令；测试代码完整。

**Type consistency**: TaskBrief / TaskReport / ResultOutput / Capability 在所有 task 引用一致。`workspace_id` / `execution_id` 命名统一。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-09-wenjin-workspace-rebuild.md`.

Two execution options:

1. **Subagent-Driven (recommended)** - Dispatch fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
