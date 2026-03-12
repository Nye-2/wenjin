# Thesis Workspace 全流程体验重设计 - 实现计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 thesis workspace 从聊天框模式改造为工具卡片式工作台，包含 6 个独立功能模块。

**Architecture:** 后端先改 registry/types/DB 基础层，再加 API 和 workflow 改造；前端从路由和共享组件开始，逐模块实现工作区页面。所有模块产出落 artifact，前端通过 registry 自动发现功能。

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy / Alembic / LangGraph (后端) | Next.js 16 / React 19 / Zustand 5 / Tailwind CSS / Radix UI / Lucide Icons (前端)

**Spec:** `docs/superpowers/specs/2026-03-12-thesis-workspace-redesign.md`

---

## Chunk 1: 后端基础层改动

### Task 1: 新增 Artifact 类型

**Files:**
- Modify: `backend/src/artifacts/types.py`
- Test: `backend/tests/artifacts/test_types.py`

- [ ] **Step 1: 写测试 — 验证新类型存在于枚举中**

```python
# backend/tests/artifacts/test_types.py
from src.artifacts.types import ArtifactType


def test_new_artifact_types_exist():
    assert ArtifactType.OPENING_REPORT == "opening_report"
    assert ArtifactType.FEASIBILITY_ANALYSIS == "feasibility_analysis"
    assert ArtifactType.THESIS_CHAPTER == "thesis_chapter"
    assert ArtifactType.GAP_ANALYSIS == "gap_analysis"


def test_all_thesis_artifact_types_present():
    """Verify all artifact types needed by thesis modules exist."""
    required = {
        "framework_outline", "thesis_chapter", "figure", "paper_draft",
        "opening_report", "feasibility_analysis", "literature_review",
        "research_ideas", "literature_search_results", "gap_analysis",
    }
    existing = {t.value for t in ArtifactType}
    assert required.issubset(existing), f"Missing: {required - existing}"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && uv run pytest tests/artifacts/test_types.py -v`
Expected: FAIL — `OPENING_REPORT`, `FEASIBILITY_ANALYSIS`, `THESIS_CHAPTER`, `GAP_ANALYSIS` 不存在

- [ ] **Step 3: 实现 — 在 ArtifactType 枚举中添加新类型**

```python
# backend/src/artifacts/types.py — 在 BACKGROUND_RESEARCH 后面追加:
    OPENING_REPORT = "opening_report"
    FEASIBILITY_ANALYSIS = "feasibility_analysis"
    THESIS_CHAPTER = "thesis_chapter"
    GAP_ANALYSIS = "gap_analysis"
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && uv run pytest tests/artifacts/test_types.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
cd /home/cjz/AcademiaGPT-V2 && git add backend/src/artifacts/types.py backend/tests/artifacts/test_types.py && git commit -m "feat: add thesis artifact types (opening_report, feasibility_analysis, thesis_chapter, gap_analysis)"
```

---

### Task 2: 更新 THESIS_FEATURES registry

**Files:**
- Modify: `backend/src/workspace_features/registry.py`
- Test: `backend/tests/workspace_features/test_registry.py`

- [ ] **Step 1: 写测试 — 验证新 registry 定义**

```python
# backend/tests/workspace_features/test_registry.py
from src.workspace_features.registry import (
    list_workspace_features,
    get_workspace_feature,
    get_workspace_feature_by_handler,
)


class TestThesisRegistryUpdate:
    def test_thesis_has_six_features(self):
        features = list_workspace_features("thesis")
        assert len(features) == 6

    def test_thesis_feature_ids(self):
        features = list_workspace_features("thesis")
        ids = [f.id for f in features]
        assert ids == [
            "deep_research",
            "literature_management",
            "opening_research",
            "thesis_writing",
            "figure_generation",
            "compile_export",
        ]

    def test_deep_research_feature_uses_skill_task_type(self):
        f = get_workspace_feature("thesis", "deep_research")
        assert f is not None
        assert f.task_type == "deep_research"
        assert f.handler_key == "thesis.deep_research"

    def test_thesis_writing_uses_thesis_generation_task_type(self):
        f = get_workspace_feature("thesis", "thesis_writing")
        assert f is not None
        assert f.task_type == "thesis_generation"
        assert f.handler_key == "thesis.thesis_writing"

    def test_literature_management_has_no_panel(self):
        f = get_workspace_feature("thesis", "literature_management")
        assert f is not None
        assert f.panel is None
        assert f.task_type == "workspace_feature"

    def test_all_handler_keys_unique(self):
        features = list_workspace_features("thesis")
        keys = [f.handler_key for f in features]
        assert len(keys) == len(set(keys))

    def test_old_thesis_features_removed(self):
        """Old feature IDs should no longer exist."""
        for old_id in ("outline", "literature", "chapter", "figure", "compile", "export"):
            assert get_workspace_feature("thesis", old_id) is None

    def test_old_handler_keys_removed(self):
        for old_key in ("thesis.outline", "thesis.literature", "thesis.chapter",
                         "thesis.figure", "thesis.compile", "thesis.export"):
            assert get_workspace_feature_by_handler(old_key) is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && uv run pytest tests/workspace_features/test_registry.py::TestThesisRegistryUpdate -v`
Expected: FAIL

- [ ] **Step 3: 实现 — 替换 THESIS_FEATURES**

替换 `backend/src/workspace_features/registry.py` 中的 `THESIS_FEATURES` 元组（约第 63-169 行），用 spec Section 10.2 中定义的 6 个新 feature 替换原有 6 个。完整代码见 spec。

关键改动：
- `deep_research`: `task_type="deep_research"`, `handler_key="thesis.deep_research"`
- `literature_management`: `panel=None`, `stages=()`
- `opening_research`: 新增
- `thesis_writing`: 合并原 outline + chapter, `task_type="thesis_generation"`
- `figure_generation`: 替代原 figure
- `compile_export`: 合并原 compile + export

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && uv run pytest tests/workspace_features/test_registry.py::TestThesisRegistryUpdate -v`
Expected: PASS

- [ ] **Step 5: 运行全量回归确认未破坏其他 workspace type**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && uv run pytest tests/ -q --ignore=tests/execution/test_latex_integration.py`
Expected: 全部通过（部分旧 thesis 测试可能因 feature ID 变化需要同步修改）

- [ ] **Step 6: 修复因 registry 变化导致的旧测试失败**

检查 `tests/gateway/routers/test_features.py` 和 `tests/task/test_workspace_feature_handler.py`，将引用旧 thesis feature ID 的测试更新为新 ID。

- [ ] **Step 7: 提交**

```bash
cd /home/cjz/AcademiaGPT-V2 && git add backend/src/workspace_features/registry.py backend/tests/ && git commit -m "feat: replace THESIS_FEATURES with new 6-module design"
```

---

### Task 3: 更新 workspace_feature_handler 常量

**Files:**
- Modify: `backend/src/task/handlers/workspace_feature_handler.py`
- Test: `backend/tests/task/test_workspace_feature_handler.py`

- [ ] **Step 1: 写测试 — 验证常量更新**

```python
# 在 backend/tests/task/test_workspace_feature_handler.py 中添加:
from src.task.handlers.workspace_feature_handler import (
    THESIS_HANDLER_KEYS,
    THESIS_AGENTS,
    _is_thesis_payload,
)


class TestThesisPayloadDetection:
    def test_new_handler_keys(self):
        assert THESIS_HANDLER_KEYS == {
            "thesis.thesis_writing",
            "thesis.figure_generation",
            "thesis.compile_export",
            "thesis.opening_research",
        }

    def test_thesis_agents_only_thesis_writer(self):
        assert THESIS_AGENTS == {"thesis_writer"}

    def test_deep_research_not_detected_as_thesis(self):
        payload = {
            "workspace_type": "thesis",
            "agent": "deep_research",
            "handler_key": "thesis.deep_research",
        }
        assert not _is_thesis_payload(payload)

    def test_literature_management_not_detected_as_thesis(self):
        payload = {
            "workspace_type": "thesis",
            "agent": "librarian",
            "handler_key": "thesis.literature_management",
        }
        assert not _is_thesis_payload(payload)

    def test_thesis_writing_detected_as_thesis(self):
        payload = {
            "workspace_type": "thesis",
            "agent": "thesis_writer",
            "handler_key": "thesis.thesis_writing",
        }
        assert _is_thesis_payload(payload)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && uv run pytest tests/task/test_workspace_feature_handler.py::TestThesisPayloadDetection -v`
Expected: FAIL

- [ ] **Step 3: 实现 — 更新常量**

```python
# backend/src/task/handlers/workspace_feature_handler.py
# 替换第 12-21 行:

THESIS_WORKSPACE_TYPES: set[str] = set()  # 不再按 workspace_type 判断
THESIS_AGENTS = {"thesis_writer"}
THESIS_HANDLER_KEYS = {
    "thesis.thesis_writing",
    "thesis.figure_generation",
    "thesis.compile_export",
    "thesis.opening_research",
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && uv run pytest tests/task/test_workspace_feature_handler.py::TestThesisPayloadDetection -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
cd /home/cjz/AcademiaGPT-V2 && git add backend/src/task/handlers/workspace_feature_handler.py backend/tests/task/test_workspace_feature_handler.py && git commit -m "feat: update thesis handler constants for new 6-module design"
```

---

### Task 4: 新增 WorkspaceLiterature 数据模型 + Alembic 迁移

**Files:**
- Create: `backend/src/database/models/workspace_literature.py`
- Modify: `backend/src/database/models/__init__.py`
- Create: `backend/alembic/versions/004_add_workspace_literature_table.py`
- Test: `backend/tests/database/test_workspace_literature_model.py`

- [ ] **Step 1: 写测试 — 验证模型可导入且字段正确**

```python
# backend/tests/database/test_workspace_literature_model.py
from src.database.models.workspace_literature import WorkspaceLiterature


def test_workspace_literature_model_has_required_columns():
    columns = {c.name for c in WorkspaceLiterature.__table__.columns}
    required = {
        "id", "workspace_id", "title", "authors", "year", "citations",
        "venue", "quartile", "abstract", "doi", "source", "is_core",
        "created_at", "updated_at",
    }
    assert required.issubset(columns)


def test_workspace_literature_tablename():
    assert WorkspaceLiterature.__tablename__ == "workspace_literature"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && uv run pytest tests/database/test_workspace_literature_model.py -v`
Expected: FAIL — 模块不存在

- [ ] **Step 3: 实现 — 创建模型**

```python
# backend/src/database/models/workspace_literature.py
"""Workspace literature model for managing research references."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base
from src.database.mixins import UUIDMixin


class WorkspaceLiterature(Base, UUIDMixin):
    __tablename__ = "workspace_literature"

    workspace_id: Mapped[str] = mapped_column(
        String, ForeignKey("workspaces.id", ondelete="CASCADE"), index=True,
    )
    title: Mapped[str] = mapped_column(String(500))
    authors: Mapped[list] = mapped_column(JSONB, default=list)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    citations: Mapped[int | None] = mapped_column(Integer, nullable=True)
    venue: Mapped[str | None] = mapped_column(String(300), nullable=True)
    quartile: Mapped[str | None] = mapped_column(String(10), nullable=True)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    doi: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="manual")
    is_core: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )
```

- [ ] **Step 4: 在 `__init__.py` 中导出新模型**

在 `backend/src/database/models/__init__.py` 中添加:
```python
from src.database.models.workspace_literature import WorkspaceLiterature
```

- [ ] **Step 5: 创建 Alembic 迁移**

```python
# backend/alembic/versions/004_add_workspace_literature_table.py
"""Add workspace_literature table.

Revision ID: 004
"""

revision = "004"
down_revision = "003"

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


def upgrade() -> None:
    op.create_table(
        "workspace_literature",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("workspace_id", sa.String(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("authors", JSONB(), nullable=False, server_default="[]"),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("citations", sa.Integer(), nullable=True),
        sa.Column("venue", sa.String(300), nullable=True),
        sa.Column("quartile", sa.String(10), nullable=True),
        sa.Column("abstract", sa.Text(), nullable=True),
        sa.Column("doi", sa.String(200), nullable=True),
        sa.Column("source", sa.String(50), nullable=False, server_default="manual"),
        sa.Column("is_core", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_workspace_literature_workspace_source", "workspace_literature", ["workspace_id", "source"])


def downgrade() -> None:
    op.drop_index("ix_workspace_literature_workspace_source")
    op.drop_table("workspace_literature")
```

- [ ] **Step 6: 运行测试确认通过**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && uv run pytest tests/database/test_workspace_literature_model.py -v`
Expected: PASS

- [ ] **Step 7: 提交**

```bash
cd /home/cjz/AcademiaGPT-V2 && git add backend/src/database/models/workspace_literature.py backend/src/database/models/__init__.py backend/alembic/versions/004_add_workspace_literature_table.py backend/tests/database/test_workspace_literature_model.py && git commit -m "feat: add workspace_literature table for reference management"
```

---

## Chunk 2: 后端 API 层

### Task 5: 文献管理 Service + Router

**Files:**
- Create: `backend/src/services/literature_service.py`
- Create: `backend/src/gateway/routers/literature.py`
- Modify: `backend/src/gateway/routers/__init__.py`
- Test: `backend/tests/gateway/routers/test_literature.py`

- [ ] **Step 1: 写测试 — 文献 CRUD 路由**

```python
# backend/tests/gateway/routers/test_literature.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.gateway.routers.literature import router


def create_mock_user(user_id="user-1"):
    user = MagicMock()
    user.id = user_id
    return user


def create_test_app(user, literature_service):
    from src.gateway.routers.auth import get_current_user
    from src.services.literature_service import get_literature_service

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_literature_service] = lambda: literature_service
    return TestClient(app)


class TestLiteratureRouter:
    def test_list_literature(self):
        svc = AsyncMock()
        svc.list_literature.return_value = {"items": [], "total": 0, "core_count": 0}
        client = create_test_app(create_mock_user(), svc)

        resp = client.get("/workspaces/ws-1/literature")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_create_literature(self):
        svc = AsyncMock()
        svc.create_literature.return_value = {
            "id": "lit-1", "title": "Test Paper", "authors": ["Author"],
            "source": "manual", "is_core": False,
        }
        client = create_test_app(create_mock_user(), svc)

        resp = client.post("/workspaces/ws-1/literature", json={
            "title": "Test Paper", "authors": ["Author"],
        })
        assert resp.status_code == 201
        assert resp.json()["id"] == "lit-1"

    def test_get_literature_count(self):
        svc = AsyncMock()
        svc.count_literature.return_value = {"total": 18, "core": 5}
        client = create_test_app(create_mock_user(), svc)

        resp = client.get("/workspaces/ws-1/literature/count")
        assert resp.status_code == 200
        assert resp.json()["total"] == 18

    def test_update_literature_core_flag(self):
        svc = AsyncMock()
        svc.update_literature.return_value = {"id": "lit-1", "is_core": True}
        client = create_test_app(create_mock_user(), svc)

        resp = client.patch("/workspaces/ws-1/literature/lit-1", json={"is_core": True})
        assert resp.status_code == 200

    def test_delete_literature(self):
        svc = AsyncMock()
        svc.delete_literature.return_value = True
        client = create_test_app(create_mock_user(), svc)

        resp = client.delete("/workspaces/ws-1/literature/lit-1")
        assert resp.status_code == 204

    def test_batch_import_literature(self):
        svc = AsyncMock()
        svc.batch_import.return_value = {"imported": 3}
        client = create_test_app(create_mock_user(), svc)

        resp = client.post("/workspaces/ws-1/literature/import", json={
            "source": "deep_research", "paper_ids": ["p1", "p2", "p3"],
        })
        assert resp.status_code == 200
        assert resp.json()["imported"] == 3
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && uv run pytest tests/gateway/routers/test_literature.py -v`
Expected: FAIL — 模块不存在

- [ ] **Step 3: 实现 LiteratureService**

创建 `backend/src/services/literature_service.py`，包含:
- `list_literature(workspace_id, source?, is_core?)` → 查询 `workspace_literature` 表
- `create_literature(workspace_id, data)` → 插入单条
- `batch_import(workspace_id, source, paper_ids)` → 批量插入（预留，暂返回 count）
- `update_literature(lit_id, data)` → PATCH 更新
- `delete_literature(lit_id)` → 删除
- `count_literature(workspace_id)` → 返回 `{total, core}`
- `get_literature_service()` → FastAPI Depends 注入

- [ ] **Step 4: 实现 Literature Router**

创建 `backend/src/gateway/routers/literature.py`，包含:
- `GET /workspaces/{id}/literature` → list
- `POST /workspaces/{id}/literature` → create (201)
- `POST /workspaces/{id}/literature/import` → batch import
- `PATCH /workspaces/{id}/literature/{lit_id}` → update
- `DELETE /workspaces/{id}/literature/{lit_id}` → delete (204)
- `GET /workspaces/{id}/literature/count` → count

- [ ] **Step 5: 在 `__init__.py` 中注册 router**

在 `backend/src/gateway/routers/__init__.py` 中添加 literature router。

- [ ] **Step 6: 运行测试确认通过**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && uv run pytest tests/gateway/routers/test_literature.py -v`
Expected: PASS

- [ ] **Step 7: 提交**

```bash
cd /home/cjz/AcademiaGPT-V2 && git add backend/src/services/literature_service.py backend/src/gateway/routers/literature.py backend/src/gateway/routers/__init__.py backend/tests/gateway/routers/test_literature.py && git commit -m "feat: add literature management CRUD API"
```

---

### Task 6: Dashboard 概览 API

**Files:**
- Create: `backend/src/services/dashboard_service.py`
- Modify: `backend/src/gateway/routers/workspaces.py`
- Test: `backend/tests/gateway/routers/test_dashboard.py`

- [ ] **Step 1: 写测试 — Dashboard 接口返回模块状态**

```python
# backend/tests/gateway/routers/test_dashboard.py
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient
from fastapi import FastAPI


def test_dashboard_returns_module_statuses():
    # Mock dashboard service 返回各模块状态
    svc = AsyncMock()
    svc.get_dashboard.return_value = {
        "modules": [
            {"id": "deep_research", "status": "not_started", "summary": {}},
            {"id": "literature", "status": "not_started", "summary": {"total": 0, "core": 0}},
            {"id": "opening_research", "status": "not_started", "summary": {}},
            {"id": "thesis_writing", "status": "not_started", "summary": {"outline_done": False}},
            {"id": "figure_generation", "status": "not_started", "summary": {"count": 0}},
            {"id": "compile_export", "status": "not_started", "summary": {}},
        ],
        "recent_artifacts": [],
    }
    # Setup test client with mocked dependencies
    # GET /workspaces/ws-1/dashboard
    # Assert 200 and 6 modules returned
```

- [ ] **Step 2: 运行测试确认失败**

- [ ] **Step 3: 实现 DashboardService**

创建 `backend/src/services/dashboard_service.py`:
- `get_dashboard(workspace_id)` → 按 spec Section 9.1 的数据源表聚合各模块状态
- 查询 `tasks` 表、`artifacts` 表、`workspace_literature` 表

- [ ] **Step 4: 在 workspaces router 中添加 dashboard 端点**

在 `backend/src/gateway/routers/workspaces.py` 中添加:
```python
@router.get("/workspaces/{workspace_id}/dashboard")
async def get_workspace_dashboard(workspace_id: str, ...):
```

- [ ] **Step 5: 运行测试确认通过**

- [ ] **Step 6: 提交**

```bash
cd /home/cjz/AcademiaGPT-V2 && git add backend/src/services/dashboard_service.py backend/src/gateway/routers/workspaces.py backend/tests/gateway/routers/test_dashboard.py && git commit -m "feat: add workspace dashboard overview API"
```

---

### Task 7: Thesis workflow action 路由

**Files:**
- Modify: `backend/src/task/handlers/workspace_feature_handler.py`
- Test: `backend/tests/task/test_workspace_feature_handler.py`

- [ ] **Step 1: 写测试 — execute_thesis_generation 支持 action 参数**

```python
# 在 test_workspace_feature_handler.py 中添加:
import pytest
from unittest.mock import AsyncMock, patch

from src.task.handlers.workspace_feature_handler import execute_thesis_generation


class TestThesisActionRouting:
    @pytest.mark.asyncio
    async def test_default_action_is_write_all(self):
        payload = {"workspace_id": "ws-1"}
        progress = AsyncMock()
        with patch("src.task.handlers.workspace_feature_handler.run_thesis_workflow_request") as mock_run:
            mock_run.return_value = {}
            await execute_thesis_generation(payload, progress)
            # Default should call the thesis workflow (write_all behavior)
            mock_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_outline_action(self):
        payload = {"workspace_id": "ws-1", "action": "generate_outline", "params": {"topic": "test"}}
        progress = AsyncMock()
        with patch("src.task.handlers.workspace_feature_handler.generate_outline_only") as mock_outline:
            mock_outline.return_value = {"message": "Outline generated"}
            result = await execute_thesis_generation(payload, progress)
            mock_outline.assert_called_once_with(payload, progress)

    @pytest.mark.asyncio
    async def test_write_chapter_action(self):
        payload = {"workspace_id": "ws-1", "action": "write_chapter", "params": {"chapter_index": 1}}
        progress = AsyncMock()
        with patch("src.task.handlers.workspace_feature_handler.write_single_chapter") as mock_ch:
            mock_ch.return_value = {"message": "Chapter written"}
            result = await execute_thesis_generation(payload, progress)
            mock_ch.assert_called_once_with(payload, progress)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && uv run pytest tests/task/test_workspace_feature_handler.py::TestThesisActionRouting -v`
Expected: FAIL

- [ ] **Step 3: 实现 — 在 execute_thesis_generation 中添加 action 路由**

```python
# backend/src/task/handlers/workspace_feature_handler.py
# 修改 execute_thesis_generation:

async def execute_thesis_generation(
    payload: dict[str, Any],
    progress: ProgressTracker,
) -> dict[str, Any]:
    action = payload.get("action") or payload.get("params", {}).get("action", "write_all")

    if action == "generate_outline":
        return await generate_outline_only(payload, progress)
    elif action == "write_chapter":
        return await write_single_chapter(payload, progress)
    else:
        # write_all: 走原有 thesis workflow
        request = _build_thesis_request(payload)
        # ... (保留原有逻辑)
```

- [ ] **Step 4: 实现 generate_outline_only 和 write_single_chapter 占位函数**

```python
async def generate_outline_only(
    payload: dict[str, Any],
    progress: ProgressTracker,
) -> dict[str, Any]:
    """Generate thesis outline without full workflow."""
    await progress.update(10, "收集 workspace 上下文")
    # TODO: 实现实际的大纲生成逻辑
    await progress.update(50, "生成论文大纲")
    await progress.update(100, "大纲生成完成")
    return {
        "feature_id": payload.get("feature_id"),
        "handler_key": payload.get("handler_key"),
        "message": "Outline generation placeholder",
        "refresh_targets": ["artifacts"],
    }


async def write_single_chapter(
    payload: dict[str, Any],
    progress: ProgressTracker,
) -> dict[str, Any]:
    """Write a single chapter by index."""
    chapter_index = payload.get("params", {}).get("chapter_index", 0)
    await progress.update(10, f"准备写作第 {chapter_index + 1} 章")
    # TODO: 实现实际的章节写作逻辑
    await progress.update(100, f"第 {chapter_index + 1} 章写作完成")
    return {
        "feature_id": payload.get("feature_id"),
        "handler_key": payload.get("handler_key"),
        "message": f"Chapter {chapter_index + 1} writing placeholder",
        "refresh_targets": ["artifacts"],
    }
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && uv run pytest tests/task/test_workspace_feature_handler.py::TestThesisActionRouting -v`
Expected: PASS

- [ ] **Step 6: 全量回归**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && uv run pytest -q --ignore=tests/execution/test_latex_integration.py`
Expected: 全部通过

- [ ] **Step 7: 提交**

```bash
cd /home/cjz/AcademiaGPT-V2 && git add backend/src/task/handlers/workspace_feature_handler.py backend/tests/task/test_workspace_feature_handler.py && git commit -m "feat: add action routing to thesis workflow (outline/chapter/all)"
```

---

### Task 8: 文献不足检测

**Files:**
- Modify: `backend/src/gateway/routers/features.py`
- Modify: `backend/tests/gateway/routers/test_features.py`

- [ ] **Step 1: 写测试 — 文献不足时返回 warning**

```python
# 在 test_features.py 中添加:

class TestLiteratureInsufficientWarning:
    def test_thesis_writing_warns_when_literature_insufficient(self):
        # Mock workspace service, literature count = 2
        # POST /workspaces/ws-1/features/thesis_writing/execute
        # params: {"action": "write_chapter", "chapter_index": 0}
        # Assert response has warning="literature_insufficient"
        pass
```

- [ ] **Step 2: 实现 — 在 execute_feature 中添加文献检测**

在 `features.py` 的 `execute_feature` 中，当 `feature_id == "thesis_writing"` 且 `action in ("write_chapter", "write_all")` 时，查询文献数量并在不足时返回 warning。

- [ ] **Step 3: 运行测试确认通过 + 全量回归**

- [ ] **Step 4: 提交**

```bash
cd /home/cjz/AcademiaGPT-V2 && git add backend/src/gateway/routers/features.py backend/tests/gateway/routers/test_features.py && git commit -m "feat: add literature insufficiency check for thesis writing"
```

---

## Chunk 3: 前端基础层

### Task 9: 新增前端 API 函数

**Files:**
- Modify: `frontend/lib/api.ts`

- [ ] **Step 1: 在 api.ts 中添加新的 API 函数**

```typescript
// Dashboard
export async function getWorkspaceDashboard(workspaceId: string) {
  const { data } = await api.get(`/workspaces/${workspaceId}/dashboard`);
  return data;
}

// Literature CRUD
export async function listLiterature(workspaceId: string, params?: { source?: string; is_core?: boolean }) {
  const { data } = await api.get(`/workspaces/${workspaceId}/literature`, { params });
  return data;
}

export async function createLiterature(workspaceId: string, body: { title: string; authors: string[]; year?: number; doi?: string; source?: string }) {
  const { data } = await api.post(`/workspaces/${workspaceId}/literature`, body);
  return data;
}

export async function importLiterature(workspaceId: string, body: { source: string; paper_ids: string[] }) {
  const { data } = await api.post(`/workspaces/${workspaceId}/literature/import`, body);
  return data;
}

export async function updateLiterature(workspaceId: string, litId: string, body: { is_core?: boolean }) {
  const { data } = await api.patch(`/workspaces/${workspaceId}/literature/${litId}`, body);
  return data;
}

export async function deleteLiterature(workspaceId: string, litId: string) {
  await api.delete(`/workspaces/${workspaceId}/literature/${litId}`);
}

export async function getLiteratureCount(workspaceId: string) {
  const { data } = await api.get(`/workspaces/${workspaceId}/literature/count`);
  return data as { total: number; core: number };
}
```

- [ ] **Step 2: 提交**

```bash
cd /home/cjz/AcademiaGPT-V2 && git add frontend/lib/api.ts && git commit -m "feat: add dashboard and literature API functions"
```

---

### Task 10: 新增前端 Stores

**Files:**
- Create: `frontend/stores/dashboard.ts`
- Create: `frontend/stores/literature.ts`
- Create: `frontend/stores/thesis-writing.ts`

- [ ] **Step 1: 创建 Dashboard store**

```typescript
// frontend/stores/dashboard.ts
import { create } from 'zustand';
import { getWorkspaceDashboard } from '@/lib/api';

export interface ModuleStatus {
  id: string;
  status: 'not_started' | 'in_progress' | 'completed';
  summary: Record<string, unknown>;
}

interface DashboardState {
  modules: ModuleStatus[];
  recentArtifacts: Array<{ id: string; type: string; title: string | null; created_at: string }>;
  isLoading: boolean;
  error: string | null;
  fetchDashboard: (workspaceId: string) => Promise<void>;
}

export const useDashboardStore = create<DashboardState>((set) => ({
  modules: [],
  recentArtifacts: [],
  isLoading: false,
  error: null,
  fetchDashboard: async (workspaceId) => {
    set({ isLoading: true, error: null });
    try {
      const data = await getWorkspaceDashboard(workspaceId);
      set({ modules: data.modules, recentArtifacts: data.recent_artifacts, isLoading: false });
    } catch (e: unknown) {
      set({ error: (e as Error).message, isLoading: false });
    }
  },
}));
```

- [ ] **Step 2: 创建 Literature store**

```typescript
// frontend/stores/literature.ts
import { create } from 'zustand';
import { listLiterature, createLiterature, updateLiterature, deleteLiterature, importLiterature } from '@/lib/api';

export interface Literature {
  id: string;
  title: string;
  authors: string[];
  year: number | null;
  citations: number | null;
  venue: string | null;
  quartile: string | null;
  abstract: string | null;
  doi: string | null;
  source: string;
  is_core: boolean;
  created_at: string;
}

interface LiteratureState {
  items: Literature[];
  total: number;
  coreCount: number;
  isLoading: boolean;
  error: string | null;
  fetchLiterature: (workspaceId: string, filters?: { source?: string; is_core?: boolean }) => Promise<void>;
  addLiterature: (workspaceId: string, data: Partial<Literature>) => Promise<void>;
  toggleCore: (workspaceId: string, litId: string, isCore: boolean) => Promise<void>;
  removeLiterature: (workspaceId: string, litId: string) => Promise<void>;
  importFromDeepResearch: (workspaceId: string, paperIds: string[]) => Promise<void>;
}

export const useLiteratureStore = create<LiteratureState>((set, get) => ({
  items: [],
  total: 0,
  coreCount: 0,
  isLoading: false,
  error: null,
  fetchLiterature: async (workspaceId, filters) => {
    set({ isLoading: true });
    try {
      const data = await listLiterature(workspaceId, filters);
      set({ items: data.items, total: data.total, coreCount: data.core_count, isLoading: false });
    } catch (e: unknown) {
      set({ error: (e as Error).message, isLoading: false });
    }
  },
  addLiterature: async (workspaceId, data) => {
    await createLiterature(workspaceId, data as Parameters<typeof createLiterature>[1]);
    await get().fetchLiterature(workspaceId);
  },
  toggleCore: async (workspaceId, litId, isCore) => {
    await updateLiterature(workspaceId, litId, { is_core: isCore });
    await get().fetchLiterature(workspaceId);
  },
  removeLiterature: async (workspaceId, litId) => {
    await deleteLiterature(workspaceId, litId);
    await get().fetchLiterature(workspaceId);
  },
  importFromDeepResearch: async (workspaceId, paperIds) => {
    await importLiterature(workspaceId, { source: 'deep_research', paper_ids: paperIds });
    await get().fetchLiterature(workspaceId);
  },
}));
```

- [ ] **Step 3: 创建 Thesis Writing store**

```typescript
// frontend/stores/thesis-writing.ts
import { create } from 'zustand';

export interface ChapterStatus {
  index: number;
  title: string;
  targetWords: number;
  currentWords: number;
  status: 'pending' | 'generating' | 'completed' | 'edited' | 'failed';
}

export interface OutlineData {
  abstract: string;
  keywords: string[];
  chapters: Array<{
    title: string;
    position: string;
    targetWords: number;
    keyPoints: string[];
    sections: string[];
  }>;
}

interface ThesisWritingState {
  currentStep: 1 | 2;
  outline: OutlineData | null;
  chapters: ChapterStatus[];
  currentChapterIndex: number;
  setStep: (step: 1 | 2) => void;
  setOutline: (outline: OutlineData) => void;
  setChapters: (chapters: ChapterStatus[]) => void;
  setCurrentChapter: (index: number) => void;
  updateChapterStatus: (index: number, status: ChapterStatus['status'], words?: number) => void;
}

export const useThesisWritingStore = create<ThesisWritingState>((set) => ({
  currentStep: 1,
  outline: null,
  chapters: [],
  currentChapterIndex: 0,
  setStep: (step) => set({ currentStep: step }),
  setOutline: (outline) => set({ outline }),
  setChapters: (chapters) => set({ chapters }),
  setCurrentChapter: (index) => set({ currentChapterIndex: index }),
  updateChapterStatus: (index, status, words) =>
    set((state) => ({
      chapters: state.chapters.map((ch) =>
        ch.index === index ? { ...ch, status, currentWords: words ?? ch.currentWords } : ch
      ),
    })),
}));
```

- [ ] **Step 4: 提交**

```bash
cd /home/cjz/AcademiaGPT-V2 && git add frontend/stores/dashboard.ts frontend/stores/literature.ts frontend/stores/thesis-writing.ts && git commit -m "feat: add dashboard, literature, thesis-writing stores"
```

---

### Task 11: ModuleCard 共享组件

**Files:**
- Create: `frontend/app/(workbench)/workspaces/[id]/components/ModuleCard.tsx`

- [ ] **Step 1: 创建 ModuleCard 组件**

```typescript
// frontend/app/(workbench)/workspaces/[id]/components/ModuleCard.tsx
'use client';

import { useRouter } from 'next/navigation';
import { type LucideIcon, FlaskConical, BookOpen, Search, PenTool, BarChart3, FileText } from 'lucide-react';
import type { ModuleStatus } from '@/stores/dashboard';

const iconMap: Record<string, LucideIcon> = {
  flask: FlaskConical,
  book: BookOpen,
  search: Search,
  pen: PenTool,
  chart: BarChart3,
  file: FileText,
};

const colorMap: Record<string, { bg: string; border: string; text: string }> = {
  blue: { bg: 'bg-blue-50', border: 'border-blue-200', text: 'text-blue-700' },
  emerald: { bg: 'bg-emerald-50', border: 'border-emerald-200', text: 'text-emerald-700' },
  amber: { bg: 'bg-amber-50', border: 'border-amber-200', text: 'text-amber-700' },
  purple: { bg: 'bg-purple-50', border: 'border-purple-200', text: 'text-purple-700' },
  rose: { bg: 'bg-rose-50', border: 'border-rose-200', text: 'text-rose-700' },
  cyan: { bg: 'bg-cyan-50', border: 'border-cyan-200', text: 'text-cyan-700' },
};

interface ModuleCardProps {
  workspaceId: string;
  feature: {
    id: string;
    name: string;
    description: string;
    icon: string;
    color?: string;
    panel?: string | null;
  };
  moduleStatus?: ModuleStatus;
  route: string;
}

export function ModuleCard({ workspaceId, feature, moduleStatus, route }: ModuleCardProps) {
  const router = useRouter();
  const Icon = iconMap[feature.icon] || FileText;
  const colors = colorMap[feature.color || 'blue'];
  const status = moduleStatus?.status || 'not_started';

  const actionLabel = feature.panel === null
    ? '管理 →'
    : status === 'completed' ? '查看结果 →'
    : status === 'in_progress' ? '继续 →'
    : '开始 →';

  return (
    <button
      onClick={() => router.push(`/workspaces/${workspaceId}/${route}`)}
      className={`${colors.bg} ${colors.border} border rounded-xl p-5 text-left hover:shadow-md transition-shadow cursor-pointer w-full`}
    >
      <div className="flex items-center gap-2 mb-2">
        <Icon className={`w-5 h-5 ${colors.text}`} />
        <h3 className="font-semibold text-[var(--text-primary)]">{feature.name}</h3>
      </div>
      <p className="text-sm text-[var(--text-secondary)] mb-3">{feature.description}</p>
      <div className="flex items-center justify-between">
        <span className="text-xs text-[var(--text-muted)]">
          {renderSummary(feature.id, moduleStatus?.summary)}
        </span>
        <span className={`text-xs font-medium ${colors.text}`}>{actionLabel}</span>
      </div>
    </button>
  );
}

function renderSummary(moduleId: string, summary?: Record<string, unknown>): string {
  if (!summary) return '未开始';
  switch (moduleId) {
    case 'deep_research':
      return summary.ideas_count ? `${summary.ideas_count} 个研究创意` : '未开始';
    case 'literature':
      return summary.total ? `${summary.total} 篇文献` : '暂无文献';
    case 'thesis_writing':
      return summary.outline_done ? `大纲已完成` : '未开始';
    default:
      return '未开始';
  }
}
```

- [ ] **Step 2: 提交**

```bash
cd /home/cjz/AcademiaGPT-V2 && git add frontend/app/\(workbench\)/workspaces/\[id\]/components/ModuleCard.tsx && git commit -m "feat: add ModuleCard shared component"
```

---

### Task 12: Workspace 首页改造为卡片仪表盘

**Files:**
- Modify: `frontend/app/(workbench)/workspaces/[id]/page.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/components/RecentArtifacts.tsx`

- [ ] **Step 1: 创建 RecentArtifacts 组件**

显示最近产出的 artifact 列表，复用 KnowledgePanel 中的 icon/color 映射逻辑。

- [ ] **Step 2: 改造 workspace page.tsx**

将现有的三栏布局（KnowledgePanel + ChatPanel + LiteraturePanel）替换为卡片仪表盘布局：
- 顶栏：workspace 名称、学科、描述
- 3 列网格：6 个 ModuleCard
- 底部：RecentArtifacts 列表

保留原有组件文件不删除（其他 workspace type 可能仍在使用），但 thesis workspace 不再渲染它们。

- [ ] **Step 3: 前端构建验证**

Run: `cd /home/cjz/AcademiaGPT-V2/frontend && npm run build`
Expected: 构建通过

- [ ] **Step 4: 提交**

```bash
cd /home/cjz/AcademiaGPT-V2 && git add frontend/app/\(workbench\)/workspaces/\[id\]/ && git commit -m "feat: redesign thesis workspace homepage as card dashboard"
```

---

### Task 13: 创建 6 个子路由页面骨架

**Files:**
- Create: `frontend/app/(workbench)/workspaces/[id]/deep-research/page.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/literature/page.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/opening-research/page.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/thesis-writing/page.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/figure-generation/page.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/compile-export/page.tsx`

- [ ] **Step 1: 为每个模块创建最小可运行的页面**

每个页面包含:
- `'use client'` 指令
- 顶栏：返回按钮 + 模块名称
- 主工作区：占位内容

- [ ] **Step 2: 前端构建验证**

Run: `cd /home/cjz/AcademiaGPT-V2/frontend && npm run build`
Expected: 构建通过

- [ ] **Step 3: 提交**

```bash
cd /home/cjz/AcademiaGPT-V2 && git add frontend/app/\(workbench\)/workspaces/\[id\]/ && git commit -m "feat: add 6 module sub-route page skeletons"
```

---

## Chunk 4: 前端模块实现

### Task 14: Deep Research 工作区

**Files:**
- Modify: `frontend/app/(workbench)/workspaces/[id]/deep-research/page.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/components/AgentThoughtStream.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/components/LiteratureInjectionPanel.tsx`

- [ ] **Step 1: 实现 AgentThoughtStream 组件**

深色背景终端风格面板，显示 Agent 工作过程。接收 `entries: {agent: string, type: 'thinking'|'action'|'result', content: string}[]` 作为 props。

- [ ] **Step 2: 实现 LiteratureInjectionPanel 组件**

弹窗组件，显示 Deep Research 发现的论文列表。预留接口:
```typescript
interface LiteratureInjectionPanelProps {
  papers: DeepResearchPaper[];
  onConfirm: (selectedIds: string[]) => void;
  onCancel: () => void;
}
```
支持全选/取消全选、排序、摘要展开/折叠。

- [ ] **Step 3: 实现 Deep Research 工作区页面**

三个 UI 状态（未开始 → 生成中 → 已完成）：
- 未开始：输入表单 + 全宽主工作区
- 生成中：进度条 + AgentThoughtStream + 侧边结果面板
- 已完成：最终报告 + 结果面板 Tab 切换 + 文献注入按钮

与后端对接：通过 `executeWorkspaceFeature` 提交 task，使用 `getTaskStatus` 轮询进度。

- [ ] **Step 4: 前端构建验证**

- [ ] **Step 5: 提交**

```bash
cd /home/cjz/AcademiaGPT-V2 && git add frontend/app/\(workbench\)/workspaces/\[id\]/ && git commit -m "feat: implement Deep Research work area with agent thought stream"
```

---

### Task 15: 文献管理工作区

**Files:**
- Modify: `frontend/app/(workbench)/workspaces/[id]/literature/page.tsx`

- [ ] **Step 1: 实现文献管理页面**

- 统计栏：总数、核心文献数、来源分布
- 筛选栏：搜索框 + 来源/分区/年份 filter
- 文献卡片列表：标题、作者、年份、引用数、分区、来源标签、核心标记星号
- 添加文献按钮 → 弹窗（手动输入、DOI 导入）
- 使用 `useLiteratureStore` 管理状态

- [ ] **Step 2: 前端构建验证 + 提交**

```bash
cd /home/cjz/AcademiaGPT-V2 && git add frontend/app/\(workbench\)/workspaces/\[id\]/literature/ && git commit -m "feat: implement literature management work area"
```

---

### Task 16: 开题调研工作区

**Files:**
- Modify: `frontend/app/(workbench)/workspaces/[id]/opening-research/page.tsx`

- [ ] **Step 1: 实现开题调研页面**

左侧 320px 输入区 + 中央 flex:1 内容区：
- 输入表单：研究主题(必填)、研究创意(可选下拉)、报告类型(radio)
- 上下文预览：使用的 DR 创意/文献
- 中央区：空状态引导 → 生成中流式输出 → 完成后 Markdown 渲染 + 操作栏
- 通过 task 执行，产出为 artifact

- [ ] **Step 2: 前端构建验证 + 提交**

```bash
cd /home/cjz/AcademiaGPT-V2 && git add frontend/app/\(workbench\)/workspaces/\[id\]/opening-research/ && git commit -m "feat: implement opening research work area"
```

---

### Task 17: 论文写作工作区（最核心）

**Files:**
- Modify: `frontend/app/(workbench)/workspaces/[id]/thesis-writing/page.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/components/OutlineEditor.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/components/ChapterNav.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/components/ChapterEditor.tsx`
- Create: `frontend/app/(workbench)/workspaces/[id]/components/LiteratureInsufficiencyDialog.tsx`

- [ ] **Step 1: 实现 LiteratureInsufficiencyDialog**

弹窗组件，提示文献不足：
- 显示当前文献数和推荐数
- 三个按钮：前往文献管理 / 启动 Deep Research / 仍然继续
- 跳转时携带 `?from=thesis-writing&reason=insufficient` query 参数

- [ ] **Step 2: 实现 OutlineEditor**

可视化大纲编辑器：
- 摘要区（可编辑）
- 章节大纲列表（可折叠/展开）
- 编辑态：标题、定位、目标字数、核心论点、小节
- [重新生成大纲] [确认大纲，进入全文写作 →] 按钮

- [ ] **Step 3: 实现 ChapterNav**

左侧章节导航：
- 章节列表 + 状态图标（✅ 🔄 ⏳ ✏️）
- 字数进度条
- 生成控制：启用 AI 配图 / 生成当前章节 / 生成全部

- [ ] **Step 4: 实现 ChapterEditor**

中央 Markdown 编辑器：
- 章节标题 + 工具栏（AI续写、重写、插入引用）
- Markdown 编辑区域（使用 textarea 或集成 markdown 编辑器）
- 底部：字数 / 引用数 / 状态

- [ ] **Step 5: 组装 thesis-writing 页面**

进入逻辑：
1. 检测是否已有大纲 artifact
2. 有大纲 → 弹窗选择（使用已有/编辑/重新生成）
3. 无大纲 → 直接 Step 1

Step 1：大纲规划 → 左侧输入 + 中央 OutlineEditor
Step 2：全文写作 → ChapterNav + ChapterEditor
顶部步骤条指示当前阶段。

使用 `useThesisWritingStore` 管理状态。
在调用写作 API 前检查文献数量，不足时显示 LiteratureInsufficiencyDialog。

- [ ] **Step 6: 前端构建验证**

Run: `cd /home/cjz/AcademiaGPT-V2/frontend && npm run build`
Expected: 构建通过

- [ ] **Step 7: 提交**

```bash
cd /home/cjz/AcademiaGPT-V2 && git add frontend/app/\(workbench\)/workspaces/\[id\]/ && git commit -m "feat: implement thesis writing work area with outline editor and chapter system"
```

---

### Task 18: 图表生成 + 编译导出工作区

**Files:**
- Modify: `frontend/app/(workbench)/workspaces/[id]/figure-generation/page.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/compile-export/page.tsx`

- [ ] **Step 1: 实现图表生成页面**

左侧 320px 配置区 + 中央预览区：
- 图表类型选择（流程图/数据可视化/概念图）
- 文本描述输入
- 关联章节下拉
- 中央：图表渲染预览（SVG/PNG）
- 已生成图表历史列表

- [ ] **Step 2: 实现编译导出页面**

左侧 280px 配置区 + 中央预览区：
- 论文完成度：各章节状态列表
- 编译选项：LaTeX 模板、编译器选择、参考文献格式
- 中央：PDF 预览（iframe）
- 多格式导出按钮

- [ ] **Step 3: 前端构建验证**

Run: `cd /home/cjz/AcademiaGPT-V2/frontend && npm run build`
Expected: 构建通过

- [ ] **Step 4: 提交**

```bash
cd /home/cjz/AcademiaGPT-V2 && git add frontend/app/\(workbench\)/workspaces/\[id\]/ && git commit -m "feat: implement figure generation and compile export work areas"
```

---

### Task 19: KnowledgePanel 新增 artifact 类型映射

**Files:**
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/KnowledgePanel.tsx`

- [ ] **Step 1: 在 KnowledgePanel 中添加新 artifact 类型的 icon/color**

```typescript
// 在现有 iconMap 中补充:
opening_report: { icon: ClipboardList, color: 'text-amber-500' },
feasibility_analysis: { icon: CheckCircle, color: 'text-green-500' },
thesis_chapter: { icon: FileText, color: 'text-purple-500' },
gap_analysis: { icon: Target, color: 'text-red-500' },
```

- [ ] **Step 2: 提交**

```bash
cd /home/cjz/AcademiaGPT-V2 && git add frontend/app/\(workbench\)/workspaces/\[id\]/components/KnowledgePanel.tsx && git commit -m "feat: add new artifact type icons to KnowledgePanel"
```

---

### Task 20: 最终集成验证

- [ ] **Step 1: 后端全量测试**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && uv run pytest -q --ignore=tests/execution/test_latex_integration.py`
Expected: 全部通过

- [ ] **Step 2: 前端构建验证**

Run: `cd /home/cjz/AcademiaGPT-V2/frontend && npm run build`
Expected: 构建通过

- [ ] **Step 3: 确认所有改动已提交**

Run: `cd /home/cjz/AcademiaGPT-V2 && git status`
Expected: 工作区干净

- [ ] **Step 4: 运行 git log 确认提交历史合理**

Run: `cd /home/cjz/AcademiaGPT-V2 && git log --oneline -20`
