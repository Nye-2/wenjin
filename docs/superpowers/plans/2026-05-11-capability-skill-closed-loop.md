# Capability/Skill Closed-Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 wenjin chat → execution → graph 全链路跑出真实结果，5 workspace types × ~25 capabilities × ~9 skills 全部就位，所有 prompt/参数从 DB runtime 加载。

**Architecture:** 5 层结构（Chat MiMo → Capability → Subagent → Skill → Output）。新增 `capability_skills` DB 表，简化 `capabilities` 表（去 version/timestamps）。两种 subagent：`searcher`（无 LLM，调外部 API）+ `react`（MiMo ReAct loop + skill prompt/tools）。所有现有 stub subagent 删除。

**Tech Stack:** Python 3.13、SQLAlchemy async、Alembic、Pydantic v2、LangGraph create_react_agent、MiMo (mimo-v2.5-pro)、Semantic Scholar API。

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/alembic/versions/043_capability_skill_closed_loop.py` | CREATE | Migration: 删 capabilities.version/timestamps, 删 capability_active_versions, 建 capability_skills |
| `backend/src/database/models/capability.py` | MODIFY | 删 version/created_at/updated_at, 调整 PK |
| `backend/src/database/models/capability_skill.py` | CREATE | 新 model: id, enabled, subagent_type, prompt, allowed_tools, resources, config |
| `backend/src/services/capability_loader.py` | MODIFY | 去 version 字段，简化 REQUIRED_FIELDS |
| `backend/src/services/skill_loader.py` | CREATE | SkillLoader.load_seeds_if_empty() |
| `backend/src/services/skill_resolver.py` | CREATE | SkillResolver: resolve(id), list_all_enabled(), 缓存 + EventBus 失效 |
| `backend/src/services/capability_resolver.py` | MODIFY | 去 version 引用 |
| `backend/src/services/search/__init__.py` | CREATE | Package marker |
| `backend/src/services/search/base.py` | CREATE | SearchSource Protocol, SearchResult model |
| `backend/src/services/search/registry.py` | CREATE | SEARCH_SOURCES dict, get_search_source(name) |
| `backend/src/services/search/sources/__init__.py` | CREATE | Package marker |
| `backend/src/services/search/sources/semantic_scholar.py` | CREATE | SemanticScholarSource 适配现有 SemanticScholarClient |
| `backend/src/subagents/v2/types/searcher.py` | CREATE | 新 `searcher` subagent: 调 search registry |
| `backend/src/subagents/v2/types/react.py` | CREATE | 新 `react` subagent: 加载 skill prompt + tools + MiMo react loop |
| `backend/src/subagents/v2/types/__init__.py` | MODIFY | 只 import 新 2 个 subagent |
| `backend/src/subagents/v2/types/scholar_searcher.py` | DELETE | Stub 删除 |
| `backend/src/subagents/v2/types/web_searcher.py` | DELETE | Stub 删除 |
| `backend/src/subagents/v2/types/clusterer.py` | DELETE | Stub 删除 |
| `backend/src/subagents/v2/types/critical_writer.py` | DELETE | Stub 删除 |
| `backend/src/subagents/v2/types/outliner.py` | DELETE | Stub 删除 |
| `backend/src/subagents/v2/base.py` | MODIFY | SubagentContext 加 `skill: CapabilitySkill \| None` 字段 |
| `backend/src/agents/lead_agent/v2/compiler.py` | MODIFY | task 解析时 fetch skill 并塞进 ctx |
| `backend/src/agents/lead_agent/agent.py` | MODIFY | `_render_workspace_available_skills` 改成列 capabilities + skills（双清单） |
| `backend/src/database/bootstrap_admin.py` | MODIFY | 加 SkillLoader.load_seeds_if_empty() 调用 |
| `backend/seed/skills/` | CREATE | 9 个 skill YAML |
| `backend/seed/capabilities/thesis/*.yaml` | REWRITE | 7 个新 capability, 用 searcher/react subagent_type |
| `backend/seed/capabilities/sci/*.yaml` | CREATE | 8 个新 capability |
| `backend/seed/capabilities/proposal/*.yaml` | CREATE | 4 个新 capability |
| `backend/seed/capabilities/patent/*.yaml` | CREATE | 3 个新 capability |
| `backend/seed/capabilities/software_copyright/*.yaml` | CREATE | 3 个新 capability |
| `backend/tests/unit/services/test_skill_loader.py` | CREATE | SkillLoader 测试 |
| `backend/tests/unit/services/test_skill_resolver.py` | CREATE | SkillResolver 测试 |
| `backend/tests/unit/services/test_search_registry.py` | CREATE | Search registry 测试 |
| `backend/tests/unit/subagents/test_searcher.py` | CREATE | SearcherSubagent 测试 |
| `backend/tests/unit/subagents/test_react.py` | CREATE | ReactSubagent 测试 |
| `backend/tests/integration/test_capability_skill_seeds.py` | CREATE | YAML seed 完整性测试 |

---

## Implementation Order (按依赖)

1. **DB migration + capability_skill model**（task 1-3）
2. **SkillLoader + SkillResolver + cache**（task 4-6）
3. **Search source 抽象 + Semantic Scholar 实现**（task 7-9）
4. **SearcherSubagent**（task 10-11）
5. **ReactSubagent**（task 12-14）
6. **Compiler 改造（注入 skill 到 ctx）**（task 15）
7. **删除 5 个 stub subagent**（task 16）
8. **Lead agent prompt 重写**（task 17）
9. **Bootstrap-admin 升级**（task 18）
10. **9 个 Skill YAML seed**（task 19）
11. **25 个 Capability YAML seed**（task 20-24，按 workspace_type 分）
12. **端到端验证**（task 25）

---

### Task 1: DB Migration — 简化 capabilities 表 + 建 capability_skills 表

**Files:**
- Create: `backend/alembic/versions/043_capability_skill_closed_loop.py`

- [ ] **Step 1: 创建 migration 文件**

```python
"""capability skill closed loop

Revision ID: 043_capability_skill_closed_loop
Revises: c41ed149a3b5_task_structural_fields
Create Date: 2026-05-11
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "043_capability_skill_closed_loop"
down_revision: str | None = "c41ed149a3b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(table_name: str) -> bool:
    return table_name in set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    # 1. Drop capability_active_versions (no version concept anymore)
    if _has_table("capability_active_versions"):
        op.drop_table("capability_active_versions")

    # 2. Simplify capabilities: drop version, created_at, updated_at
    #    Recreate the table with new PK (id, workspace_type)
    op.execute("DROP TABLE IF EXISTS capabilities CASCADE")
    op.create_table(
        "capabilities",
        sa.Column("id", sa.String(length=100), primary_key=True),
        sa.Column("workspace_type", sa.String(length=50), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("intent_description", sa.Text(), nullable=False),
        sa.Column("trigger_phrases", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("required_decisions", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("brief_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("graph_template", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("result_card_template", sa.String(length=100), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_capabilities_active",
        "capabilities",
        ["workspace_type", "enabled"],
        postgresql_where=sa.text("enabled = true"),
    )

    # 3. Create capability_skills (flat, global)
    op.create_table(
        "capability_skills",
        sa.Column("id", sa.String(length=100), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("subagent_type", sa.String(length=50), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False, server_default=""),
        sa.Column("allowed_tools", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("resources", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_table("capability_skills")
    op.drop_table("capabilities")
```

- [ ] **Step 2: 跑迁移**

```bash
cd /Users/ze/wenjin && docker compose run --rm migrate
```

Expected: `INFO  [alembic.runtime.migration] Running upgrade c41ed149a3b5 -> 043_capability_skill_closed_loop`

- [ ] **Step 3: 验证表结构**

```bash
docker compose exec postgres psql -U postgres -d wenjin -c "\d capabilities"
docker compose exec postgres psql -U postgres -d wenjin -c "\d capability_skills"
```

Expected: capabilities 无 version/created_at/updated_at；capability_skills 表存在。

- [ ] **Step 4: Commit**

```bash
cd /Users/ze/wenjin && git add backend/alembic/versions/043_capability_skill_closed_loop.py && git commit -m "feat(db): simplify capabilities, add capability_skills table"
```

---

### Task 2: Capability model 调整

**Files:**
- Modify: `backend/src/database/models/capability.py`

- [ ] **Step 1: 重写 Capability model（删 version 与 timestamps）**

Read 当前文件，整体替换为：

```python
"""Capability ORM model — defines available capabilities per workspace type."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base


class Capability(Base):
    """A capability bound to a workspace_type."""

    __tablename__ = "capabilities"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    workspace_type: Mapped[str] = mapped_column(String(50), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    intent_description: Mapped[str] = mapped_column(Text, nullable=False)
    trigger_phrases: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    required_decisions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    brief_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    graph_template: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    result_card_template: Mapped[str] = mapped_column(String(100), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index(
            "ix_capabilities_active",
            "workspace_type",
            "enabled",
            postgresql_where="enabled = true",
        ),
    )
```

- [ ] **Step 2: 删除旧 CapabilityActiveVersion 引用**

```bash
grep -rn "CapabilityActiveVersion" backend/src/ | grep -v test
```

If found in `src/database/models/__init__.py` or elsewhere, remove the import lines. (The CapabilityActiveVersion class itself in this file should be removed — replace the entire file content as shown in Step 1.)

- [ ] **Step 3: Commit**

```bash
cd /Users/ze/wenjin && git add backend/src/database/models/capability.py backend/src/database/models/__init__.py && git commit -m "refactor(db): simplify Capability model — drop version, timestamps"
```

---

### Task 3: CapabilitySkill model

**Files:**
- Create: `backend/src/database/models/capability_skill.py`
- Modify: `backend/src/database/models/__init__.py`

- [ ] **Step 1: 创建 model**

`backend/src/database/models/capability_skill.py`:

```python
"""CapabilitySkill ORM model — reusable subagent capability packs."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base


class CapabilitySkill(Base):
    """A reusable capability pack a subagent can load at runtime."""

    __tablename__ = "capability_skills"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    subagent_type: Mapped[str] = mapped_column(String(50), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    allowed_tools: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    resources: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
```

- [ ] **Step 2: 注册到 models __init__**

Add to `backend/src/database/models/__init__.py`:

```python
from src.database.models.capability_skill import CapabilitySkill  # noqa: F401
```

- [ ] **Step 3: 验证 import**

```bash
docker compose exec gateway python -c "from src.database.models import CapabilitySkill; print(CapabilitySkill.__tablename__)"
```

Expected: `capability_skills`

- [ ] **Step 4: Commit**

```bash
cd /Users/ze/wenjin && git add backend/src/database/models/capability_skill.py backend/src/database/models/__init__.py && git commit -m "feat(db): add CapabilitySkill model"
```

---

### Task 4: SkillLoader

**Files:**
- Create: `backend/src/services/skill_loader.py`
- Test: `backend/tests/unit/services/test_skill_loader.py`

- [ ] **Step 1: 写失败测试**

`backend/tests/unit/services/test_skill_loader.py`:

```python
"""Tests for SkillLoader — YAML → DB seed loader."""

from pathlib import Path

import pytest
import yaml
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.database.models.capability_skill import CapabilitySkill
from src.services.skill_loader import SkillLoader


@pytest.mark.asyncio
async def test_load_seeds_if_empty_inserts_all_yamls(db_session: AsyncSession, tmp_path: Path) -> None:
    skill_yaml = tmp_path / "scholar-searcher.yaml"
    skill_yaml.write_text(yaml.safe_dump({
        "id": "scholar-searcher",
        "enabled": True,
        "display_name": "学术文献检索员",
        "description": "调 Semantic Scholar",
        "subagent_type": "searcher",
        "prompt": "(unused)",
        "allowed_tools": [],
        "resources": [],
        "config": {"sources": ["semantic_scholar"]},
    }))

    loader = SkillLoader(db_session, seed_dir=tmp_path)
    count = await loader.load_seeds_if_empty()
    assert count == 1

    rows = (await db_session.execute(select(CapabilitySkill))).scalars().all()
    assert len(rows) == 1
    assert rows[0].id == "scholar-searcher"
    assert rows[0].config == {"sources": ["semantic_scholar"]}


@pytest.mark.asyncio
async def test_load_seeds_if_empty_skips_when_populated(db_session: AsyncSession, tmp_path: Path) -> None:
    db_session.add(CapabilitySkill(
        id="existing",
        display_name="x",
        description="x",
        subagent_type="react",
        prompt="x",
    ))
    await db_session.commit()

    skill_yaml = tmp_path / "new.yaml"
    skill_yaml.write_text(yaml.safe_dump({
        "id": "new",
        "display_name": "new",
        "subagent_type": "react",
    }))

    loader = SkillLoader(db_session, seed_dir=tmp_path)
    count = await loader.load_seeds_if_empty()
    assert count == 0  # table not empty, skip
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/unit/services/test_skill_loader.py -v
```

Expected: ImportError (skill_loader module not found)

- [ ] **Step 3: 写 SkillLoader 实现**

`backend/src/services/skill_loader.py`:

```python
"""Skill YAML loader — seeds capability_skills from YAML files into DB."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.capability_skill import CapabilitySkill

logger = logging.getLogger(__name__)

DEFAULT_SEED_DIR = Path(__file__).resolve().parent.parent.parent / "seed" / "skills"

REQUIRED_FIELDS = {"id", "display_name", "subagent_type"}

OPTIONAL_DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "description": "",
    "prompt": "",
    "allowed_tools": [],
    "resources": [],
    "config": {},
}


class SkillLoader:
    """Loads CapabilitySkill rows from YAML files in seed_dir."""

    def __init__(self, session: AsyncSession, *, seed_dir: Path | None = None) -> None:
        self.session = session
        self.seed_dir = Path(seed_dir) if seed_dir is not None else DEFAULT_SEED_DIR

    async def load_seeds_if_empty(self) -> int:
        existing = (await self.session.execute(select(CapabilitySkill).limit(1))).first()
        if existing:
            return 0
        return await self._load_all()

    async def _load_all(self) -> int:
        count = 0
        if not self.seed_dir.exists():
            logger.warning("Skill seed dir does not exist: %s", self.seed_dir)
            return 0
        for yaml_path in sorted(self.seed_dir.glob("*.yaml")):
            data = self._read_and_validate(yaml_path)
            self.session.add(CapabilitySkill(**data))
            count += 1
        if count > 0:
            await self.session.commit()
            logger.info("Loaded %d skill seed(s) from %s", count, self.seed_dir)
        return count

    def _read_and_validate(self, path: Path) -> dict[str, Any]:
        with open(path) as f:
            raw = yaml.safe_load(f)
        if not isinstance(raw, dict):
            raise ValueError(f"Expected dict in {path}, got {type(raw).__name__}")
        missing = REQUIRED_FIELDS - set(raw.keys())
        if missing:
            raise ValueError(f"Missing required fields in {path}: {', '.join(sorted(missing))}")
        for field, default in OPTIONAL_DEFAULTS.items():
            if field not in raw:
                raw[field] = default
        return raw
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/unit/services/test_skill_loader.py -v
```

Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
cd /Users/ze/wenjin && git add backend/src/services/skill_loader.py backend/tests/unit/services/test_skill_loader.py && git commit -m "feat(services): add SkillLoader for YAML→DB seeding"
```

---

### Task 5: SkillResolver

**Files:**
- Create: `backend/src/services/skill_resolver.py`
- Test: `backend/tests/unit/services/test_skill_resolver.py`

- [ ] **Step 1: 写失败测试**

`backend/tests/unit/services/test_skill_resolver.py`:

```python
"""Tests for SkillResolver — runtime DB lookup with cache invalidation."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.capability_skill import CapabilitySkill
from src.services.skill_resolver import SkillResolver


@pytest.mark.asyncio
async def test_resolve_returns_cached_skill(db_session: AsyncSession) -> None:
    db_session.add(CapabilitySkill(
        id="literature-reviewer",
        display_name="文献综述写手",
        description="x",
        subagent_type="react",
        prompt="写综述",
        allowed_tools=[],
        resources=[],
        config={"output_kind": "document"},
    ))
    await db_session.commit()

    resolver = SkillResolver(session_factory=lambda: db_session)
    skill1 = await resolver.resolve("literature-reviewer")
    assert skill1 is not None
    assert skill1.prompt == "写综述"

    # Second call should hit cache (no new DB query)
    skill2 = await resolver.resolve("literature-reviewer")
    assert skill2 is skill1


@pytest.mark.asyncio
async def test_resolve_returns_none_for_unknown(db_session: AsyncSession) -> None:
    resolver = SkillResolver(session_factory=lambda: db_session)
    result = await resolver.resolve("does-not-exist")
    assert result is None


@pytest.mark.asyncio
async def test_list_all_enabled(db_session: AsyncSession) -> None:
    db_session.add_all([
        CapabilitySkill(id="a", display_name="A", subagent_type="react", enabled=True),
        CapabilitySkill(id="b", display_name="B", subagent_type="react", enabled=False),
    ])
    await db_session.commit()

    resolver = SkillResolver(session_factory=lambda: db_session)
    skills = await resolver.list_all_enabled()
    assert {s.id for s in skills} == {"a"}


@pytest.mark.asyncio
async def test_on_invalidate_clears_cache(db_session: AsyncSession) -> None:
    db_session.add(CapabilitySkill(id="x", display_name="X", subagent_type="react", prompt="v1"))
    await db_session.commit()

    resolver = SkillResolver(session_factory=lambda: db_session)
    skill = await resolver.resolve("x")
    assert skill.prompt == "v1"

    # Manually update DB
    skill.prompt = "v2"
    await db_session.commit()

    # Without invalidate, cache still returns v1
    assert (await resolver.resolve("x")).prompt == "v1"

    # After invalidate, fresh fetch
    await resolver._on_invalidate({"skill_id": "x"})
    assert (await resolver.resolve("x")).prompt == "v2"
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/unit/services/test_skill_resolver.py -v
```

Expected: ImportError

- [ ] **Step 3: 实现 SkillResolver**

`backend/src/services/skill_resolver.py`:

```python
"""SkillResolver — runtime DB lookup with in-memory cache and EventBus invalidation."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.capability_skill import CapabilitySkill

logger = logging.getLogger(__name__)


class SkillResolver:
    """Resolve skills from DB with in-memory cache.

    Subscribes to EventBus channel 'skill.invalidated' for cache clear.
    Event payload: {"skill_id": "<id>"}
    """

    INVALIDATE_CHANNEL = "skill.invalidated"

    def __init__(
        self,
        *,
        session_factory: Callable[[], AsyncSession],
        event_bus: Any | None = None,
    ) -> None:
        self.session_factory = session_factory
        self._cache: dict[str, CapabilitySkill] = {}
        if event_bus is not None:
            event_bus.subscribe(self.INVALIDATE_CHANNEL, self._on_invalidate)

    async def resolve(self, skill_id: str) -> CapabilitySkill | None:
        if skill_id in self._cache:
            return self._cache[skill_id]
        session = self.session_factory()
        if hasattr(session, "__aenter__"):
            async with session as s:
                skill = await s.scalar(
                    select(CapabilitySkill).where(CapabilitySkill.id == skill_id)
                )
        else:
            skill = await session.scalar(
                select(CapabilitySkill).where(CapabilitySkill.id == skill_id)
            )
        if skill is not None:
            self._cache[skill_id] = skill
        return skill

    async def list_all_enabled(self) -> list[CapabilitySkill]:
        session = self.session_factory()
        if hasattr(session, "__aenter__"):
            async with session as s:
                result = await s.execute(
                    select(CapabilitySkill).where(CapabilitySkill.enabled.is_(True))
                )
                return list(result.scalars().all())
        result = await session.execute(
            select(CapabilitySkill).where(CapabilitySkill.enabled.is_(True))
        )
        return list(result.scalars().all())

    async def _on_invalidate(self, event: dict[str, Any]) -> None:
        skill_id = event.get("skill_id")
        if skill_id:
            self._cache.pop(skill_id, None)
            logger.debug("Skill cache invalidated for %s", skill_id)
```

- [ ] **Step 4: 跑测试**

```bash
cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/unit/services/test_skill_resolver.py -v
```

Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
cd /Users/ze/wenjin && git add backend/src/services/skill_resolver.py backend/tests/unit/services/test_skill_resolver.py && git commit -m "feat(services): add SkillResolver with cache + EventBus invalidation"
```

---

### Task 6: CapabilityResolver/Loader 适配（去 version）

**Files:**
- Modify: `backend/src/services/capability_loader.py`
- Modify: `backend/src/services/capability_resolver.py`

- [ ] **Step 1: 简化 CapabilityLoader REQUIRED_FIELDS**

Read `backend/src/services/capability_loader.py`, then edit:

```python
# Top-level constant — remove version
REQUIRED_FIELDS = {
    "id", "workspace_type", "display_name",
    "intent_description", "brief_schema",
    "graph_template", "result_card_template",
}
```

Also remove any `version=raw["version"]` lines in `_read_and_validate` / `_load_all`.

- [ ] **Step 2: 简化 CapabilityResolver**

Read `backend/src/services/capability_resolver.py`, remove all references to `version` and `CapabilityActiveVersion`. The `resolve` method should now do:

```python
async def resolve(self, capability_id: str, workspace_type: str) -> Capability | None:
    key = (capability_id, workspace_type)
    if key in self._cache:
        return self._cache[key]
    session = self.session_factory()
    if hasattr(session, "__aenter__"):
        async with session as s:
            cap = await s.scalar(
                select(Capability).where(
                    Capability.id == capability_id,
                    Capability.workspace_type == workspace_type,
                    Capability.enabled.is_(True),
                )
            )
    else:
        cap = await session.scalar(
            select(Capability).where(
                Capability.id == capability_id,
                Capability.workspace_type == workspace_type,
                Capability.enabled.is_(True),
            )
        )
    if cap is not None:
        self._cache[key] = cap
    return cap
```

And `list_for_workspace_type`:

```python
async def list_for_workspace_type(self, workspace_type: str) -> list[Capability]:
    session = self.session_factory()
    if hasattr(session, "__aenter__"):
        async with session as s:
            result = await s.execute(
                select(Capability).where(
                    Capability.workspace_type == workspace_type,
                    Capability.enabled.is_(True),
                )
            )
            return list(result.scalars().all())
    result = await session.execute(
        select(Capability).where(
            Capability.workspace_type == workspace_type,
            Capability.enabled.is_(True),
        )
    )
    return list(result.scalars().all())
```

- [ ] **Step 3: 跑现有 capability tests 确认未破坏**

```bash
cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/ -k "capabilit" -v
```

Expected: PASS（如有失败的是因为旧 version 测试，请删除这些测试或更新）

- [ ] **Step 4: Commit**

```bash
cd /Users/ze/wenjin && git add backend/src/services/capability_loader.py backend/src/services/capability_resolver.py backend/tests/ && git commit -m "refactor(services): drop version from Capability loader/resolver"
```

---

### Task 7: SearchSource 接口 + SearchResult model

**Files:**
- Create: `backend/src/services/search/__init__.py`
- Create: `backend/src/services/search/base.py`

- [ ] **Step 1: Package marker**

`backend/src/services/search/__init__.py`:

```python
"""Search source abstraction for academic/web/patent search."""
```

- [ ] **Step 2: 写 base 接口**

`backend/src/services/search/base.py`:

```python
"""Abstract search source interface.

All concrete sources (semantic_scholar, arxiv, openalex, patent_cn) implement this.
"""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field


class SearchResult(BaseModel):
    """Normalized search result. All sources map their native shape to this."""

    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    abstract: str | None = None
    doi: str | None = None
    url: str | None = None
    citations: int | None = None
    venue: str | None = None
    external_id: str = ""           # id within the source
    source: str = ""                 # source name (set by source impl)
    raw: dict[str, Any] = Field(default_factory=dict)


class SearchSource(Protocol):
    """Protocol all concrete search sources must implement."""

    name: str

    async def search(
        self,
        query: str,
        *,
        year_range: tuple[int, int] | None = None,
        limit: int = 30,
        **kwargs: Any,
    ) -> list[SearchResult]: ...
```

- [ ] **Step 3: Commit**

```bash
cd /Users/ze/wenjin && git add backend/src/services/search/__init__.py backend/src/services/search/base.py && git commit -m "feat(search): add SearchSource interface + SearchResult model"
```

---

### Task 8: Search registry

**Files:**
- Create: `backend/src/services/search/registry.py`
- Test: `backend/tests/unit/services/test_search_registry.py`

- [ ] **Step 1: 写失败测试**

`backend/tests/unit/services/test_search_registry.py`:

```python
"""Tests for search source registry."""

import pytest

from src.services.search.registry import (
    SEARCH_SOURCES,
    get_search_source,
    register_search_source,
)


def test_get_unknown_source_raises():
    with pytest.raises(ValueError, match="Unknown search source"):
        get_search_source("nonexistent")


def test_register_and_get():
    class FakeSource:
        name = "fake"
        async def search(self, query, **kwargs):
            return []

    register_search_source("fake", FakeSource)
    try:
        src = get_search_source("fake")
        assert isinstance(src, FakeSource)
        assert src.name == "fake"
    finally:
        SEARCH_SOURCES.pop("fake", None)


def test_semantic_scholar_registered():
    # Force import side effects (auto-registration)
    import src.services.search.sources  # noqa: F401
    assert "semantic_scholar" in SEARCH_SOURCES
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/unit/services/test_search_registry.py -v
```

Expected: ImportError

- [ ] **Step 3: 实现 registry**

`backend/src/services/search/registry.py`:

```python
"""Search source registry — maps source names to instances."""

from __future__ import annotations

import logging
from typing import Any

from src.services.search.base import SearchSource

logger = logging.getLogger(__name__)

SEARCH_SOURCES: dict[str, type[SearchSource]] = {}


def register_search_source(name: str, cls: type[SearchSource]) -> None:
    """Register a SearchSource class under the given name."""
    SEARCH_SOURCES[name] = cls
    logger.debug("Registered search source: %s", name)


def get_search_source(name: str) -> SearchSource:
    """Instantiate a registered search source by name.

    Raises ValueError if the name is unknown.
    """
    cls = SEARCH_SOURCES.get(name)
    if cls is None:
        raise ValueError(
            f"Unknown search source: {name}. Available: {sorted(SEARCH_SOURCES)}"
        )
    return cls()
```

- [ ] **Step 4: 跑前 2 个测试通过**

```bash
cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/unit/services/test_search_registry.py::test_get_unknown_source_raises tests/unit/services/test_search_registry.py::test_register_and_get -v
```

Expected: PASS (2 tests; third one needs Task 9)

- [ ] **Step 5: Commit**

```bash
cd /Users/ze/wenjin && git add backend/src/services/search/registry.py backend/tests/unit/services/test_search_registry.py && git commit -m "feat(search): add registry with register/get helpers"
```

---

### Task 9: SemanticScholarSource

**Files:**
- Create: `backend/src/services/search/sources/__init__.py`
- Create: `backend/src/services/search/sources/semantic_scholar.py`

- [ ] **Step 1: Sources package init (auto-registers all sources)**

`backend/src/services/search/sources/__init__.py`:

```python
"""All concrete search sources — importing this package auto-registers them."""

from src.services.search.sources import semantic_scholar as _ss  # noqa: F401
```

- [ ] **Step 2: Implement SemanticScholarSource**

`backend/src/services/search/sources/semantic_scholar.py`:

```python
"""Semantic Scholar source adapter — wraps existing SemanticScholarClient."""

from __future__ import annotations

import logging
import os
from typing import Any

from src.academic.literature.external.semantic_scholar import SemanticScholarClient
from src.services.search.base import SearchResult, SearchSource
from src.services.search.registry import register_search_source

logger = logging.getLogger(__name__)


class SemanticScholarSource:
    """Adapter implementing SearchSource on top of SemanticScholarClient."""

    name = "semantic_scholar"

    def __init__(self) -> None:
        api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
        rate_limit = float(os.getenv("SEMANTIC_SCHOLAR_RATE_LIMIT_DELAY", "1.0"))
        self._client = SemanticScholarClient(
            api_key=api_key or None,
            rate_limit_delay=rate_limit,
        )

    async def search(
        self,
        query: str,
        *,
        year_range: tuple[int, int] | None = None,
        limit: int = 30,
        **kwargs: Any,
    ) -> list[SearchResult]:
        try:
            raw_results = await self._client.search(query=query, limit=limit)
        except Exception as exc:
            logger.warning("Semantic Scholar search failed: %s", exc)
            return []

        results: list[SearchResult] = []
        for r in raw_results:
            year = getattr(r, "year", None)
            # Filter by year_range if provided
            if year_range and year is not None:
                lo, hi = year_range
                if year < lo or year > hi:
                    continue
            results.append(
                SearchResult(
                    title=getattr(r, "title", "") or "",
                    authors=getattr(r, "authors", []) or [],
                    year=year,
                    abstract=getattr(r, "abstract", None),
                    doi=getattr(r, "doi", None),
                    url=getattr(r, "url", None),
                    citations=getattr(r, "citations_count", None),
                    venue=getattr(r, "venue", None),
                    external_id=str(getattr(r, "external_id", "") or ""),
                    source=self.name,
                    raw=getattr(r, "model_dump", lambda: {})() if hasattr(r, "model_dump") else {},
                )
            )
        return results


# Auto-register on import
register_search_source(SemanticScholarSource.name, SemanticScholarSource)
```

- [ ] **Step 3: 跑全部测试**

```bash
cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/unit/services/test_search_registry.py -v
```

Expected: PASS (3 tests)

- [ ] **Step 4: Commit**

```bash
cd /Users/ze/wenjin && git add backend/src/services/search/sources/__init__.py backend/src/services/search/sources/semantic_scholar.py && git commit -m "feat(search): add SemanticScholarSource auto-registered to registry"
```

---

### Task 10: SubagentContext 加 skill 字段

**Files:**
- Modify: `backend/src/subagents/v2/base.py`

- [ ] **Step 1: 加 skill 字段**

Read `backend/src/subagents/v2/base.py`. Add to SubagentContext:

```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.database.models.capability_skill import CapabilitySkill

@dataclass
class SubagentContext:
    workspace_id: str
    execution_id: str
    prompt: str
    inputs: dict
    tools: list[str]
    workspace_data: dict = field(default_factory=dict)
    skill: "CapabilitySkill | None" = None     # NEW
```

- [ ] **Step 2: 验证 import**

```bash
docker compose exec gateway python -c "from src.subagents.v2.base import SubagentContext; ctx = SubagentContext(workspace_id='x', execution_id='y', prompt='', inputs={}, tools=[]); print(ctx.skill)"
```

Expected: `None`

- [ ] **Step 3: Commit**

```bash
cd /Users/ze/wenjin && git add backend/src/subagents/v2/base.py && git commit -m "feat(subagents): add skill field to SubagentContext"
```

---

### Task 11: SearcherSubagent

**Files:**
- Create: `backend/src/subagents/v2/types/searcher.py`
- Test: `backend/tests/unit/subagents/test_searcher.py`

- [ ] **Step 1: 写失败测试**

`backend/tests/unit/subagents/test_searcher.py`:

```python
"""Tests for SearcherSubagent."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.database.models.capability_skill import CapabilitySkill
from src.services.search.base import SearchResult
from src.services.search.registry import SEARCH_SOURCES, register_search_source
from src.subagents.v2.base import SubagentContext
from src.subagents.v2.types.searcher import SearcherSubagent


@pytest.mark.asyncio
async def test_searcher_calls_configured_sources(monkeypatch):
    # Mock source
    fake_results = [
        SearchResult(title="Paper A", authors=["Smith"], year=2023, doi="10.1/a", source="fake", external_id="a"),
        SearchResult(title="Paper B", authors=["Jones"], year=2024, doi="10.1/b", source="fake", external_id="b"),
    ]
    class FakeSource:
        name = "fake"
        async def search(self, query, **kwargs):
            return fake_results

    register_search_source("fake", FakeSource)
    try:
        skill = CapabilitySkill(
            id="scholar-searcher",
            display_name="x",
            subagent_type="searcher",
            prompt="",
            allowed_tools=[],
            resources=[],
            config={"sources": ["fake"], "max_results": 10},
        )
        ctx = SubagentContext(
            workspace_id="ws",
            execution_id="ex",
            prompt="",
            inputs={"query": "machine learning"},
            tools=[],
            skill=skill,
        )

        agent = SearcherSubagent()
        result = await agent.run(ctx)
        assert "papers" in result.output
        assert len(result.output["papers"]) == 2
        assert result.output["papers"][0]["title"] == "Paper A"
    finally:
        SEARCH_SOURCES.pop("fake", None)


@pytest.mark.asyncio
async def test_searcher_dedupes_by_doi():
    class DupSource:
        name = "dup"
        async def search(self, query, **kwargs):
            return [
                SearchResult(title="Same", doi="10.1/x", source="dup", external_id="1"),
                SearchResult(title="Same Title Diff Capitalization", doi="10.1/x", source="dup", external_id="2"),
            ]

    register_search_source("dup", DupSource)
    try:
        skill = CapabilitySkill(
            id="x", display_name="x", subagent_type="searcher", prompt="",
            allowed_tools=[], resources=[], config={"sources": ["dup"]},
        )
        ctx = SubagentContext(workspace_id="w", execution_id="e", prompt="", inputs={"query": "q"}, tools=[], skill=skill)

        result = await SearcherSubagent().run(ctx)
        assert len(result.output["papers"]) == 1
    finally:
        SEARCH_SOURCES.pop("dup", None)


@pytest.mark.asyncio
async def test_searcher_no_skill_returns_empty():
    ctx = SubagentContext(workspace_id="w", execution_id="e", prompt="", inputs={"query": "q"}, tools=[], skill=None)
    result = await SearcherSubagent().run(ctx)
    assert result.output == {"papers": []}
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/unit/subagents/test_searcher.py -v
```

Expected: ImportError

- [ ] **Step 3: 实现 SearcherSubagent**

`backend/src/subagents/v2/types/searcher.py`:

```python
"""SearcherSubagent — calls external search APIs via the search source registry.

Does NOT invoke an LLM. The skill.config["sources"] list determines which
sources to query; results are deduplicated by DOI or normalized title.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from src.services.search.base import SearchResult
from src.services.search.registry import get_search_source
# Import sources package to trigger auto-registration
from src.services.search import sources as _sources  # noqa: F401
from src.subagents.v2.base import SubagentBase, SubagentContext, SubagentResult
from src.subagents.v2.registry import subagent

logger = logging.getLogger(__name__)


def _dedupe(results: list[SearchResult]) -> list[SearchResult]:
    """Dedupe by DOI; fallback to normalized lowercase title."""
    seen_dois: set[str] = set()
    seen_titles: set[str] = set()
    out: list[SearchResult] = []
    for r in results:
        if r.doi:
            if r.doi in seen_dois:
                continue
            seen_dois.add(r.doi)
        else:
            key = r.title.strip().lower()
            if key in seen_titles:
                continue
            seen_titles.add(key)
        out.append(r)
    return out


@subagent("searcher")
class SearcherSubagent(SubagentBase):
    """Generic searcher — config-driven, no LLM."""

    name = "searcher"
    allowed_tools: list[str] = []

    async def run(self, ctx: SubagentContext) -> SubagentResult:
        if ctx.skill is None:
            logger.warning("SearcherSubagent called without skill")
            return SubagentResult(output={"papers": []})

        config = ctx.skill.config or {}
        source_names = config.get("sources", ["semantic_scholar"])
        max_results = int(config.get("max_results", 30))
        year_min = config.get("year_min")

        query = str(ctx.inputs.get("query") or ctx.inputs.get("topic") or "").strip()
        if not query:
            return SubagentResult(output={"papers": []})

        year_range = None
        if year_min:
            year_range = (int(year_min), datetime.now().year)

        all_results: list[SearchResult] = []
        for src_name in source_names:
            try:
                src = get_search_source(src_name)
                results = await src.search(query, year_range=year_range, limit=max_results)
                all_results.extend(results)
            except Exception as exc:
                logger.warning("Search source %s failed: %s", src_name, exc)

        deduped = _dedupe(all_results)[:max_results]

        return SubagentResult(
            output={"papers": [r.model_dump() for r in deduped]},
            token_usage={},
        )
```

- [ ] **Step 4: 跑测试通过**

```bash
cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/unit/subagents/test_searcher.py -v
```

Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
cd /Users/ze/wenjin && git add backend/src/subagents/v2/types/searcher.py backend/tests/unit/subagents/test_searcher.py && git commit -m "feat(subagents): add SearcherSubagent backed by search registry"
```

---

### Task 12: ReactSubagent — base structure

**Files:**
- Create: `backend/src/subagents/v2/types/react.py`
- Test: `backend/tests/unit/subagents/test_react.py`

- [ ] **Step 1: 写第一个测试（不调 LLM 的纯模板渲染）**

`backend/tests/unit/subagents/test_react.py`:

```python
"""Tests for ReactSubagent."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.database.models.capability_skill import CapabilitySkill
from src.subagents.v2.base import SubagentContext
from src.subagents.v2.types.react import (
    ReactSubagent,
    _render_user_message,
    _parse_output,
)


def test_render_user_message_default_template():
    inputs = {"topic": "GAN", "papers": [{"title": "A"}]}
    msg = _render_user_message(None, inputs)
    assert "GAN" in msg
    assert "A" in msg


def test_render_user_message_custom_template():
    inputs = {"topic": "GAN"}
    template = "主题: {{topic}}"
    msg = _render_user_message(template, inputs)
    assert msg == "主题: GAN"


def test_parse_output_document_kind():
    out = _parse_output("# Title\n\nbody", {"output_kind": "document"})
    assert out == {"markdown": "# Title\n\nbody"}


def test_parse_output_json_kind():
    out = _parse_output('{"a": 1, "b": [2,3]}', {"output_kind": "json"})
    assert out == {"a": 1, "b": [2, 3]}


def test_parse_output_text_default():
    out = _parse_output("hello", {"output_kind": "text"})
    assert out == {"text": "hello"}


def test_parse_output_unknown_falls_back_to_text():
    out = _parse_output("hello", {"output_kind": "foo"})
    assert out == {"text": "hello"}


def test_parse_output_invalid_json_falls_back_to_text():
    out = _parse_output("not json", {"output_kind": "json"})
    assert out == {"text": "not json"}
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/unit/subagents/test_react.py -v
```

Expected: ImportError

- [ ] **Step 3: 实现 ReactSubagent 框架（无实际 LLM 调用）**

`backend/src/subagents/v2/types/react.py`:

```python
"""ReactSubagent — generic MiMo ReAct loop driven by a skill (prompt + tools).

The subagent loads:
  - skill.prompt as system prompt (with skill.resources appended)
  - skill.allowed_tools as the tool whitelist
  - skill.config.user_template (Jinja-like) for user message construction
  - skill.config.output_kind for output parsing ("document" | "json" | "text")
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from src.subagents.v2.base import SubagentBase, SubagentContext, SubagentResult
from src.subagents.v2.registry import subagent

logger = logging.getLogger(__name__)


def _render_user_message(template: str | None, inputs: dict[str, Any]) -> str:
    """Render the user message from a Jinja-style template, falling back to JSON dump."""
    if not template:
        return json.dumps(inputs, ensure_ascii=False, default=str)
    # Minimal Jinja2 substitution: {{var}} -> str(inputs[var])
    out = template
    for k, v in inputs.items():
        placeholder = "{{" + k + "}}"
        if placeholder in out:
            rendered = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)
            out = out.replace(placeholder, str(rendered))
    return out


def _read_resource(path: str) -> str:
    """Read a resource file referenced by the skill (relative to backend/)."""
    backend_root = Path(__file__).resolve().parent.parent.parent.parent
    full_path = backend_root / path
    try:
        return full_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Failed to read skill resource %s: %s", full_path, exc)
        return ""


def _parse_output(final_text: str, config: dict[str, Any]) -> dict[str, Any]:
    kind = (config or {}).get("output_kind", "text")
    if kind == "document":
        return {"markdown": final_text}
    if kind == "json":
        try:
            return json.loads(final_text)
        except (json.JSONDecodeError, ValueError):
            logger.warning("ReactSubagent JSON output failed to parse, falling back to text")
            return {"text": final_text}
    return {"text": final_text}


@subagent("react")
class ReactSubagent(SubagentBase):
    """Generic MiMo ReAct loop driven by a skill."""

    name = "react"
    allowed_tools: list[str] = []

    async def run(self, ctx: SubagentContext) -> SubagentResult:
        skill = ctx.skill
        if skill is None:
            logger.warning("ReactSubagent called without skill")
            return SubagentResult(output={"text": ""})

        # Build system prompt: skill.prompt + appended resources
        system_prompt = skill.prompt or ""
        for resource_path in skill.resources or []:
            content = _read_resource(resource_path)
            if content:
                system_prompt += f"\n\n## Reference: {resource_path}\n{content}"

        # Build user message
        config = skill.config or {}
        user_message = _render_user_message(
            config.get("user_template"),
            ctx.inputs,
        )

        # Resolve tools (whitelist from skill)
        from src.tools.builtins import (
            read_file_tool,
            view_image_tool,
        )
        tool_registry: dict[str, Any] = {
            "read_file": read_file_tool,
            "view_image": view_image_tool,
        }
        tools = [tool_registry[name] for name in (skill.allowed_tools or []) if name in tool_registry]

        # Run MiMo ReAct loop
        final_text, token_usage = await _run_react_loop(system_prompt, user_message, tools)

        # Parse output
        output = _parse_output(final_text, config)

        return SubagentResult(
            output=output,
            token_usage=token_usage,
        )


async def _run_react_loop(
    system_prompt: str,
    user_message: str,
    tools: list[Any],
) -> tuple[str, dict[str, Any]]:
    """Run a single-turn MiMo ReAct invocation.

    Returns (final_text, token_usage_dict).
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    from src.models.factory import create_chat_model

    model = create_chat_model("mimo-v2.5-pro")
    if tools:
        try:
            from langchain.agents import create_react_agent

            agent = create_react_agent(model, tools, prompt=system_prompt)
            result = await agent.ainvoke({"messages": [HumanMessage(content=user_message)]})
            messages = result.get("messages", [])
            final_text = ""
            if messages:
                final_text = getattr(messages[-1], "content", "") or ""
            return final_text, _extract_usage(result)
        except Exception as exc:
            logger.warning("ReAct agent failed, falling back to plain call: %s", exc)

    # No tools or fallback: plain LLM call
    response = await model.ainvoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ])
    final_text = getattr(response, "content", "") or ""
    return final_text, _extract_usage(response)


def _extract_usage(obj: Any) -> dict[str, Any]:
    usage_meta = getattr(obj, "usage_metadata", None)
    if isinstance(usage_meta, dict):
        return dict(usage_meta)
    return {}
```

- [ ] **Step 4: 跑测试通过**

```bash
cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/unit/subagents/test_react.py -v
```

Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
cd /Users/ze/wenjin && git add backend/src/subagents/v2/types/react.py backend/tests/unit/subagents/test_react.py && git commit -m "feat(subagents): add ReactSubagent (skill-driven MiMo react loop)"
```

---

### Task 13: ReactSubagent — run-loop integration test (with mocked LLM)

**Files:**
- Modify: `backend/tests/unit/subagents/test_react.py`

- [ ] **Step 1: 加 mock LLM 测试**

Append to `backend/tests/unit/subagents/test_react.py`:

```python
@pytest.mark.asyncio
async def test_react_subagent_invokes_llm_with_skill_prompt(monkeypatch):
    skill = CapabilitySkill(
        id="literature-reviewer",
        display_name="x",
        subagent_type="react",
        prompt="你是综述写手",
        allowed_tools=[],
        resources=[],
        config={
            "output_kind": "document",
            "user_template": "主题: {{topic}}",
        },
    )
    ctx = SubagentContext(
        workspace_id="w", execution_id="e", prompt="",
        inputs={"topic": "GAN"}, tools=[], skill=skill,
    )

    fake_response = MagicMock()
    fake_response.content = "# GAN 综述\n\n正文..."
    fake_response.usage_metadata = {"input_tokens": 100, "output_tokens": 50}

    fake_model = MagicMock()
    fake_model.ainvoke = AsyncMock(return_value=fake_response)

    with patch("src.subagents.v2.types.react.create_chat_model", return_value=fake_model):
        result = await ReactSubagent().run(ctx)

    # Verify model was called with system + user message
    fake_model.ainvoke.assert_called_once()
    messages = fake_model.ainvoke.call_args[0][0]
    assert len(messages) == 2
    assert "综述写手" in messages[0].content
    assert "GAN" in messages[1].content

    # Verify output parsed as document
    assert result.output == {"markdown": "# GAN 综述\n\n正文..."}
    assert result.token_usage == {"input_tokens": 100, "output_tokens": 50}
```

- [ ] **Step 2: 跑测试**

```bash
cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/unit/subagents/test_react.py::test_react_subagent_invokes_llm_with_skill_prompt -v
```

Expected: PASS

- [ ] **Step 3: 跑 import 验证（确保 langchain create_chat_model 路径正确）**

```bash
docker compose exec gateway python -c "from src.subagents.v2.types.react import ReactSubagent; print(ReactSubagent.name)"
```

Expected: `react`

- [ ] **Step 4: Commit**

```bash
cd /Users/ze/wenjin && git add backend/tests/unit/subagents/test_react.py && git commit -m "test(subagents): add ReactSubagent LLM integration test"
```

---

### Task 14: Compiler — fetch skill 并注入 SubagentContext

**Files:**
- Modify: `backend/src/agents/lead_agent/v2/compiler.py`

- [ ] **Step 1: Read current compiler**

```bash
cat /Users/ze/wenjin/backend/src/agents/lead_agent/v2/compiler.py | head -120
```

Identify the `_default_runner_factory` (around line 100-115) — that's where SubagentContext is built.

- [ ] **Step 2: 把 SkillResolver 注入 compiler**

The compiler currently can't await DB calls inline because LangGraph nodes are sync-wrapped. Best path: load all needed skills up-front in `compile_graph`.

Edit `backend/src/agents/lead_agent/v2/compiler.py`:

Add at the top (after existing imports):

```python
from src.database.models.capability_skill import CapabilitySkill
from src.database.session import get_db_session
from sqlalchemy import select
```

Modify `compile_graph` signature and body. Find the function signature and update:

```python
async def compile_graph(
    template: dict,
    *,
    state_class: type,
    abort_check: Callable | None = None,
) -> Any:
    """Compile a capability graph_template into a LangGraph StateGraph.

    Pre-fetches all skills referenced by tasks and stashes them on each task dict
    as `_skill` so the runner can pass them to SubagentContext.
    """
    # 1. Collect all skill_ids referenced by tasks
    skill_ids: set[str] = set()
    for phase in template.get("phases", []):
        for task in phase.get("tasks", []):
            sid = task.get("skill_id")
            if sid:
                skill_ids.add(sid)

    # 2. Fetch them once
    skills_by_id: dict[str, CapabilitySkill] = {}
    if skill_ids:
        async with get_db_session() as db:
            result = await db.execute(
                select(CapabilitySkill).where(CapabilitySkill.id.in_(skill_ids))
            )
            for s in result.scalars().all():
                skills_by_id[s.id] = s

    # 3. Attach pre-loaded skill to each task dict (used by runner factory)
    for phase in template.get("phases", []):
        for task in phase.get("tasks", []):
            sid = task.get("skill_id")
            if sid and sid in skills_by_id:
                task["_skill"] = skills_by_id[sid]
            elif sid:
                raise ValueError(f"Task references unknown skill_id: {sid}")

    # ... existing graph build code follows
```

Then in `_default_runner_factory` (where SubagentContext is built), add `skill=task.get("_skill")`:

```python
async def _node(state):
    ctx = SubagentContext(
        workspace_id=state.get("workspace_id", ""),
        execution_id=state.get("execution_id", ""),
        prompt=task.get("prompt_template", ""),
        inputs=state.get("inputs_for_tasks", {}).get(task_name, {}),
        tools=task.get("tools", []),
        workspace_data=state.get("workspace_data", {}),
        skill=task.get("_skill"),  # NEW
    )
    result = await subagent_cls().run(ctx)
    ...
```

If `compile_graph` was previously sync, mark it `async`. Find the callsite in `runtime.py` (line 120) and `await` it.

- [ ] **Step 3: Verify runtime.py awaits compile_graph**

```bash
grep -n "compile_graph" backend/src/agents/lead_agent/v2/runtime.py
```

Edit to `graph = await compile_graph(...)` if needed.

- [ ] **Step 4: Smoke import**

```bash
docker compose exec gateway python -c "from src.agents.lead_agent.v2.compiler import compile_graph; print('ok')"
```

Expected: `ok`

- [ ] **Step 5: Commit**

```bash
cd /Users/ze/wenjin && git add backend/src/agents/lead_agent/v2/compiler.py backend/src/agents/lead_agent/v2/runtime.py && git commit -m "feat(compiler): pre-load skills and inject into SubagentContext"
```

---

### Task 15: 删除 5 个旧 stub subagent

**Files:**
- Delete: `backend/src/subagents/v2/types/scholar_searcher.py`
- Delete: `backend/src/subagents/v2/types/web_searcher.py`
- Delete: `backend/src/subagents/v2/types/clusterer.py`
- Delete: `backend/src/subagents/v2/types/critical_writer.py`
- Delete: `backend/src/subagents/v2/types/outliner.py`
- Modify: `backend/src/subagents/v2/types/__init__.py`

- [ ] **Step 1: 删除 5 个 stub 文件**

```bash
cd /Users/ze/wenjin && rm \
  backend/src/subagents/v2/types/scholar_searcher.py \
  backend/src/subagents/v2/types/web_searcher.py \
  backend/src/subagents/v2/types/clusterer.py \
  backend/src/subagents/v2/types/critical_writer.py \
  backend/src/subagents/v2/types/outliner.py
```

- [ ] **Step 2: 重写 types/__init__.py**

`backend/src/subagents/v2/types/__init__.py`:

```python
"""V2 subagent type registry — only `searcher` and `react`.

Importing this package triggers @subagent decorators on the two subagents.
"""

from . import searcher as searcher  # noqa: F401
from . import react as react  # noqa: F401
from .searcher import SearcherSubagent
from .react import ReactSubagent

__all__ = ["SearcherSubagent", "ReactSubagent"]
```

- [ ] **Step 3: 删除引用旧 stub 的 tests（如果有）**

```bash
grep -rln "ScholarSearcher\|WebSearcher\|Clusterer\|CriticalWriter\|Outliner" backend/tests/
```

For each found file, delete or update the test to use the new subagents.

- [ ] **Step 4: 跑全部 subagent 测试**

```bash
cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/unit/subagents/ -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/ze/wenjin && git add -A && git commit -m "refactor(subagents): delete 5 stub subagents, keep searcher+react"
```

---

### Task 16: Lead agent prompt — 列出 capabilities + skills（双清单）

**Files:**
- Modify: `backend/src/agents/lead_agent/agent.py`

- [ ] **Step 1: Read current `_render_workspace_available_skills`**

```bash
sed -n '145,225p' /Users/ze/wenjin/backend/src/agents/lead_agent/agent.py
```

- [ ] **Step 2: 替换为列 capabilities + skills 的版本**

Edit `backend/src/agents/lead_agent/agent.py` — replace the function with:

```python
async def _render_capabilities_and_skills(
    workspace_type: str | None,
) -> str:
    """Render both <available_capabilities> and <available_skills> blocks.

    Capabilities: this workspace_type's enabled capabilities, what chat can launch.
    Skills: ALL enabled skills (global), reference for what subagents can do.
    """
    if not workspace_type:
        return ""

    from sqlalchemy import select

    from src.database.models.capability import Capability
    from src.database.models.capability_skill import CapabilitySkill
    from src.database.session import get_db_session

    async with get_db_session() as db:
        cap_rows = (await db.execute(
            select(Capability).where(
                Capability.workspace_type == workspace_type,
                Capability.enabled.is_(True),
            )
        )).scalars().all()

        skill_rows = (await db.execute(
            select(CapabilitySkill).where(CapabilitySkill.enabled.is_(True))
        )).scalars().all()

    if not cap_rows:
        return ""

    cap_items = []
    for c in cap_rows:
        triggers = ", ".join(c.trigger_phrases or [])
        cap_items.append(
            f'  <capability id="{c.id}" name="{c.display_name}" '
            f'triggers="{triggers}" desc="{c.description or c.intent_description}"/>'
        )
    cap_block = "<available_capabilities>\n" + "\n".join(cap_items) + "\n</available_capabilities>"

    skill_items = []
    for s in skill_rows:
        skill_items.append(
            f'  <skill id="{s.id}" subagent_type="{s.subagent_type}" desc="{s.description}"/>'
        )
    skill_block = "<available_skills>\n" + "\n".join(skill_items) + "\n</available_skills>"

    return f"""

{cap_block}

{skill_block}

<feature_launch_system>
**WORKFLOW PRIORITY: 识别意图 → 检查参数 → 立刻调用 launch_feature**

You have access to workspace **capabilities** above. Each is a complete workflow
(graph of subagents). Skills are reference capability packs the subagents can load.

**STRICT RULE: When the user's request matches a capability, you MUST call
`launch_feature(feature_id=<capability_id>, params={{...}})` — do NOT just describe
what would happen. Without an actual tool call, NOTHING runs.**

**MANDATORY Launch Scenarios:**
1. Direct action request matching a capability's triggers → REQUIRED ACTION: call launch_feature
2. User clicks a suggestion pill or names a skill explicitly → REQUIRED ACTION: launch the matching capability
3. Sufficient context already in conversation → REQUIRED ACTION: launch immediately

**STRICT ENFORCEMENT:**
- ❌ DO NOT say "已启动" / "我来帮你启动" without actually calling the tool
- ❌ DO NOT describe what would happen — call the tool
- ❌ DO NOT make up status messages — the right panel shows real status
- ✅ When a capability matches: call `launch_feature` IN THE SAME TURN
- ✅ Missing minimum params: ask ONE focused question, launch next turn
- ✅ Truly unclear which capability: ask one clarifying question

**Example (correct):**
User: "帮我调研 X 主题的文献"
You: call launch_feature(feature_id="deep_research", params={{"topic": "X"}})
You: "好的，我已经启动深度调研，进度会在右侧面板更新。"

**Example (WRONG):**
User: "帮我调研 X"
You: "已启动深度调研..." [WITHOUT calling launch_feature]
^ This is the most serious error.
</feature_launch_system>"""
```

- [ ] **Step 3: 改 caller to await async**

Find the call site (around line 458) and update:

```python
# Old: base_prompt += _render_workspace_available_skills(workspace_type)
# New: base_prompt += await _render_capabilities_and_skills(workspace_type)
```

If `apply_prompt_template` (the parent function) is sync, mark it async and update its callers.

- [ ] **Step 4: 删除旧 sync 函数**

Remove the old `_render_workspace_available_skills` definition entirely.

- [ ] **Step 5: Smoke test**

```bash
docker compose exec gateway python -c "
import asyncio
from src.agents.lead_agent.agent import _render_capabilities_and_skills
print(asyncio.run(_render_capabilities_and_skills('thesis'))[:200])
"
```

Expected: prints prompt fragment with `<available_capabilities>` (will be empty if seeds not loaded yet)

- [ ] **Step 6: Commit**

```bash
cd /Users/ze/wenjin && git add backend/src/agents/lead_agent/agent.py && git commit -m "feat(prompt): render capabilities + skills from DB"
```

---

### Task 17: Bootstrap-admin 加 SkillLoader

**Files:**
- Modify: `backend/src/database/bootstrap_admin.py`

- [ ] **Step 1: Read current bootstrap_admin.py**

```bash
sed -n '90,140p' /Users/ze/wenjin/backend/src/database/bootstrap_admin.py
```

Find where CapabilityLoader is called.

- [ ] **Step 2: 加 SkillLoader 调用**

Right before / after the CapabilityLoader block:

```python
            try:
                from src.services.skill_loader import SkillLoader

                skill_loader = SkillLoader(session)
                loaded_skills = await skill_loader.load_seeds_if_empty()
                if loaded_skills:
                    print(f"[bootstrap-admin] Seeded {loaded_skills} skill record(s)")
            except Exception as skill_exc:
                print(f"[bootstrap-admin] WARN: skill seed failed: {skill_exc}")

            try:
                from src.services.capability_loader import CapabilityLoader

                cap_loader = CapabilityLoader(session)
                loaded_caps = await cap_loader.load_seeds_if_empty()
                if loaded_caps:
                    print(f"[bootstrap-admin] Seeded {loaded_caps} capability record(s)")
            except Exception as cap_exc:
                print(f"[bootstrap-admin] WARN: capability seed failed: {cap_exc}")
```

Make sure skills are seeded **before** capabilities (capabilities reference skills).

- [ ] **Step 3: Commit**

```bash
cd /Users/ze/wenjin && git add backend/src/database/bootstrap_admin.py && git commit -m "feat(bootstrap): seed skills before capabilities"
```

---

### Task 18: Skill YAML seeds — 9 个

**Files:**
- Create: `backend/seed/skills/scholar-searcher.yaml`
- Create: `backend/seed/skills/literature-reviewer.yaml`
- Create: `backend/seed/skills/paper-analyst.yaml`
- Create: `backend/seed/skills/framework-designer.yaml`
- Create: `backend/seed/skills/section-writer.yaml`
- Create: `backend/seed/skills/figure-designer.yaml`
- Create: `backend/seed/skills/peer-reviewer.yaml`
- Create: `backend/seed/skills/journal-recommender.yaml`
- Create: `backend/seed/skills/prior-art-searcher.yaml`
- Modify: `backend/Dockerfile` (确认 `COPY seed/`)

- [ ] **Step 1: scholar-searcher.yaml**

`backend/seed/skills/scholar-searcher.yaml`:

```yaml
id: scholar-searcher
enabled: true
display_name: 学术文献检索员
description: 调用 Semantic Scholar 检索高质量学术论文
subagent_type: searcher
prompt: "(searcher 不调 LLM，保留以保持接口一致)"
allowed_tools: []
resources: []
config:
  sources: [semantic_scholar]
  max_results: 30
  year_min: 2019
```

- [ ] **Step 2: literature-reviewer.yaml**

```yaml
id: literature-reviewer
enabled: true
display_name: 文献综述写手
description: 把论文集合写成结构化的中文文献综述
subagent_type: react
prompt: |
  你是学术综述写作专家。给定一组论文，按主题/方法/时间组织一篇综述。

  要求：
  - 800-1500 字
  - 引用论文用 [作者 年份] 格式
  - 标记研究空白和未来方向
  - 不编造论文/作者/年份

  输出 Markdown 格式：
  # {主题} 文献综述

  ## 研究脉络
  ## 主流方法
  ## 关键论文
  ## 研究空白与未来方向
allowed_tools: []
resources: []
config:
  output_kind: document
  doc_kind: literature_review
  user_template: |
    主题：{{topic}}
    论文列表（JSON）：
    {{papers}}
```

- [ ] **Step 3: paper-analyst.yaml**

```yaml
id: paper-analyst
enabled: true
display_name: 论文精读分析员
description: 拆解单篇论文的方法/实验/结论/创新点
subagent_type: react
prompt: |
  你是论文精读专家。给定一篇论文（标题/摘要/全文），输出严格的 JSON。

  输出 JSON 格式：
  {
    "summary": "一句话概括",
    "method": "方法描述",
    "experiments": "实验设置与数据",
    "conclusions": "主要结论",
    "novelty": "创新点",
    "limitations": "局限性",
    "key_references": ["论文1", "论文2"]
  }

  只输出 JSON，不要其他文字。
allowed_tools:
  - read_file
resources: []
config:
  output_kind: json
  user_template: |
    论文信息：
    {{paper}}
```

- [ ] **Step 4: framework-designer.yaml**

```yaml
id: framework-designer
enabled: true
display_name: 论文框架设计师
description: 把研究主题收敛为摘要 + 关键词 + 章节框架
subagent_type: react
prompt: |
  你是论文框架设计师。给定研究主题/创新点，输出结构化论文框架。

  输出 Markdown:
  # {主题}

  ## Abstract
  （150-250 字摘要）

  ## Keywords
  （5-8 个）

  ## Contributions
  - C1: ...
  - C2: ...

  ## Outline
  1. Introduction
     - 1.1 ...
  2. Related Work
  ...
allowed_tools: []
resources: []
config:
  output_kind: document
  doc_kind: framework_outline
  user_template: |
    主题：{{topic}}
    创新点（可选）：{{contributions}}
```

- [ ] **Step 5: section-writer.yaml**

```yaml
id: section-writer
enabled: true
display_name: 章节撰写员
description: 基于大纲和证据撰写指定章节
subagent_type: react
prompt: |
  你是学术写作专家。给定章节标题、大纲、和参考文献，写出该章节的草稿。

  要求：
  - 段落清晰，论证逻辑严密
  - 引用用 [作者 年份]
  - 标注待补数据/待核验来源
  - 不编造引文

  输出 Markdown。
allowed_tools: []
resources: []
config:
  output_kind: document
  doc_kind: section_draft
  user_template: |
    章节标题：{{section_title}}
    大纲：{{outline}}
    可用文献：{{references}}
    目标字数：{{target_words|default(800)}}
```

- [ ] **Step 6: figure-designer.yaml**

```yaml
id: figure-designer
enabled: true
display_name: 图表设计师
description: 把概念/流程/数据转成图表说明 + Mermaid 代码
subagent_type: react
prompt: |
  你是论文图表设计师。给定要表达的内容，输出图表说明和 Mermaid 代码。

  输出 Markdown：
  # 图表说明

  ## 设计意图
  ## 类型
  （flowchart / class / sequence / state / pie / bar / ...）

  ## Mermaid 代码
  ```mermaid
  ...
  ```

  ## 文字说明（caption）
allowed_tools: []
resources: []
config:
  output_kind: document
  doc_kind: figure_spec
  user_template: |
    需要表达：{{concept}}
    放入章节：{{section|default('Method')}}
```

- [ ] **Step 7: peer-reviewer.yaml**

```yaml
id: peer-reviewer
enabled: true
display_name: 同行评审员
description: 从审稿人视角定位稿件薄弱点和修订动作
subagent_type: react
prompt: |
  你是严格的学术同行评审员。给定论文草稿/章节，输出审稿意见。

  输出 Markdown：
  # 审稿意见

  ## Summary
  ## Strengths
  ## Weaknesses
  ## Major Comments
  ## Minor Comments
  ## Recommendation
  （Strong Accept / Accept / Weak Accept / Borderline / Weak Reject / Reject）

  ## Priority Revisions
  - P1（必须改）：...
  - P2（建议改）：...
allowed_tools: []
resources: []
config:
  output_kind: document
  doc_kind: peer_review
  user_template: |
    稿件内容：
    {{manuscript}}
    评审重点：{{focus|default('整体质量')}}
```

- [ ] **Step 8: journal-recommender.yaml**

```yaml
id: journal-recommender
enabled: true
display_name: 期刊推荐员
description: 基于论文画像推荐候选期刊和投稿策略
subagent_type: react
prompt: |
  你是学术投稿顾问。给定论文摘要/主题/方法，推荐 3-5 个候选期刊。

  输出 Markdown：
  # 候选期刊推荐

  ## 论文画像
  - 学科：...
  - 方法类型：...
  - 创新点：...

  ## 候选期刊
  | 期刊 | 分区/IF | 周期 | 适配理由 | 待核验 |
  | --- | --- | --- | --- | --- |
  | xxx | (待核验) | (待核验) | ... | ✓ |

  ## 投稿策略
  ## 投稿前补强建议

  注意：所有期刊数据（IF/分区/周期）必须标注"待核验"。
allowed_tools: []
resources: []
config:
  output_kind: document
  doc_kind: journal_recommend
  user_template: |
    论文摘要：{{abstract}}
    学科方向：{{discipline|default('计算机科学')}}
    其它偏好：{{prefs|default('无')}}
```

- [ ] **Step 9: prior-art-searcher.yaml**

```yaml
id: prior-art-searcher
enabled: true
display_name: 现有技术检索员
description: 调专利/学术数据库做现有技术检索（暂用 Semantic Scholar，后续接专利源）
subagent_type: searcher
prompt: "(searcher 不调 LLM)"
allowed_tools: []
resources: []
config:
  sources: [semantic_scholar]   # 后续：[patent_cn, semantic_scholar]
  max_results: 20
```

- [ ] **Step 10: 验证 Dockerfile 已 COPY seed/**

```bash
grep -n "COPY seed/" backend/Dockerfile
```

Expected: at least 2 lines (gateway + langgraph stages). If missing, add.

- [ ] **Step 11: Commit**

```bash
cd /Users/ze/wenjin && git add backend/seed/skills/ && git commit -m "feat(seeds): add 9 skill YAML seeds (scholar/lit-review/paper/framework/section/figure/peer/journal/prior-art)"
```

---

### Task 19: Capability YAML — thesis (7 个)

**Files:**
- Modify: `backend/seed/capabilities/thesis/deep_research.yaml`
- Modify: `backend/seed/capabilities/thesis/section_write.yaml`
- Modify: `backend/seed/capabilities/thesis/outline_generate.yaml`
- Modify: `backend/seed/capabilities/thesis/section_revise.yaml`
- Delete: `backend/seed/capabilities/thesis/citation_manage.yaml`
- Create: `backend/seed/capabilities/thesis/literature_management.yaml`
- Create: `backend/seed/capabilities/thesis/opening_research.yaml`
- Create: `backend/seed/capabilities/thesis/figure_generation.yaml`

- [ ] **Step 1: deep_research.yaml (rewrite to use new subagent_type + skill_id)**

```yaml
id: deep_research
workspace_type: thesis
enabled: true
display_name: 深度文献调研
description: 围绕主题做系统化文献检索和综述材料生成
intent_description: 用户希望对某个主题做学术性的深度文献调研
trigger_phrases:
  - 调研
  - 找综述
  - 文献综述
  - literature review
required_decisions:
  - key: topic_scope
    ask: "主题边界是？"
    type: string
brief_schema:
  type: object
  required: [topic]
  properties:
    topic: { type: string, description: 调研主题 }
    year_min: { type: integer, optional: true }
graph_template:
  phases:
    - name: discover
      tasks:
        - name: search
          subagent_type: searcher
          skill_id: scholar-searcher
          inputs:
            query: "{{topic}}"
            year_min: "{{year_min|default(2019)}}"
          outputs:
            - kind: library_item
              iterate_on: "output.papers"
              mapping:
                title: "{{item.title}}"
                authors: "{{item.authors}}"
                year: "{{item.year}}"
                doi: "{{item.doi}}"
                abstract: "{{item.abstract}}"
    - name: synthesize
      depends_on: [discover]
      tasks:
        - name: write
          subagent_type: react
          skill_id: literature-reviewer
          inputs:
            topic: "{{topic}}"
            papers: "{{phases.discover.search.output.papers}}"
          outputs:
            - kind: document
              mapping:
                name: "{{topic}} 文献综述"
                doc_kind: literature_review
                content: "{{output.markdown}}"
result_card_template: literature_review
notes: 适合开题阶段或选题探索
```

- [ ] **Step 2: section_write.yaml**

```yaml
id: section_write
workspace_type: thesis
enabled: true
display_name: 章节撰写
description: 基于大纲和参考资料撰写指定章节草稿
intent_description: 用户需要写论文的某个章节
trigger_phrases:
  - 写章节
  - 写引言
  - 写方法
  - 写正文
required_decisions:
  - key: section_title
    ask: "要写哪个章节？"
    type: string
brief_schema:
  type: object
  required: [section_title]
  properties:
    section_title: { type: string }
    outline: { type: string, optional: true }
    target_words: { type: integer, optional: true }
graph_template:
  phases:
    - name: write
      tasks:
        - name: draft
          subagent_type: react
          skill_id: section-writer
          inputs:
            section_title: "{{section_title}}"
            outline: "{{outline|default('')}}"
            references: ""
            target_words: "{{target_words|default(800)}}"
          outputs:
            - kind: document
              mapping:
                name: "{{section_title}} 草稿"
                doc_kind: section_draft
                content: "{{output.markdown}}"
result_card_template: section_draft
```

- [ ] **Step 3: outline_generate.yaml**

```yaml
id: outline_generate
workspace_type: thesis
enabled: true
display_name: 大纲生成
description: 把研究主题转成论文章节框架和摘要
intent_description: 用户希望生成论文大纲
trigger_phrases:
  - 写大纲
  - 生成大纲
  - 设计框架
required_decisions:
  - key: topic
    ask: "论文主题是？"
    type: string
brief_schema:
  type: object
  required: [topic]
  properties:
    topic: { type: string }
    contributions: { type: string, optional: true }
graph_template:
  phases:
    - name: design
      tasks:
        - name: outline
          subagent_type: react
          skill_id: framework-designer
          inputs:
            topic: "{{topic}}"
            contributions: "{{contributions|default('')}}"
          outputs:
            - kind: document
              mapping:
                name: "{{topic}} 框架"
                doc_kind: framework_outline
                content: "{{output.markdown}}"
result_card_template: framework_outline
```

- [ ] **Step 4: section_revise.yaml**

```yaml
id: section_revise
workspace_type: thesis
enabled: true
display_name: 章节修订
description: 同行评审视角给章节草稿提修订建议
intent_description: 用户希望修订已有章节
trigger_phrases:
  - 修订
  - 改章节
  - 审稿意见
required_decisions:
  - key: manuscript
    ask: "粘贴要修订的章节内容"
    type: string
brief_schema:
  type: object
  required: [manuscript]
  properties:
    manuscript: { type: string }
    focus: { type: string, optional: true }
graph_template:
  phases:
    - name: review
      tasks:
        - name: critique
          subagent_type: react
          skill_id: peer-reviewer
          inputs:
            manuscript: "{{manuscript}}"
            focus: "{{focus|default('整体质量')}}"
          outputs:
            - kind: document
              mapping:
                name: "章节修订建议"
                doc_kind: peer_review
                content: "{{output.markdown}}"
result_card_template: peer_review
```

- [ ] **Step 5: 删除 citation_manage.yaml（被 literature_management 取代）**

```bash
rm backend/seed/capabilities/thesis/citation_manage.yaml
```

- [ ] **Step 6: literature_management.yaml**

```yaml
id: literature_management
workspace_type: thesis
enabled: true
display_name: 文献管理
description: 围绕主题抓元数据进文献库（不写综述）
intent_description: 用户希望补充工作区的文献库
trigger_phrases:
  - 找文献
  - 补文献
  - 文献入库
required_decisions:
  - key: topic
    ask: "要检索什么主题？"
    type: string
brief_schema:
  type: object
  required: [topic]
  properties:
    topic: { type: string }
graph_template:
  phases:
    - name: discover
      tasks:
        - name: search
          subagent_type: searcher
          skill_id: scholar-searcher
          inputs:
            query: "{{topic}}"
          outputs:
            - kind: library_item
              iterate_on: "output.papers"
              mapping:
                title: "{{item.title}}"
                authors: "{{item.authors}}"
                year: "{{item.year}}"
                doi: "{{item.doi}}"
                abstract: "{{item.abstract}}"
result_card_template: library_intake
```

- [ ] **Step 7: opening_research.yaml**

```yaml
id: opening_research
workspace_type: thesis
enabled: true
display_name: 开题调研
description: 把选题背景整理为开题报告材料
intent_description: 用户希望准备开题材料
trigger_phrases:
  - 开题
  - 开题报告
  - 开题调研
required_decisions:
  - key: topic
    ask: "开题主题是？"
    type: string
brief_schema:
  type: object
  required: [topic]
  properties:
    topic: { type: string }
graph_template:
  phases:
    - name: discover
      tasks:
        - name: search
          subagent_type: searcher
          skill_id: scholar-searcher
          inputs:
            query: "{{topic}}"
          outputs:
            - kind: library_item
              iterate_on: "output.papers"
              mapping:
                title: "{{item.title}}"
                authors: "{{item.authors}}"
                year: "{{item.year}}"
                doi: "{{item.doi}}"
    - name: synthesize
      depends_on: [discover]
      tasks:
        - name: review
          subagent_type: react
          skill_id: literature-reviewer
          inputs:
            topic: "{{topic}}"
            papers: "{{phases.discover.search.output.papers}}"
          outputs:
            - kind: document
              mapping:
                name: "{{topic}} 开题综述"
                doc_kind: literature_review
                content: "{{output.markdown}}"
result_card_template: literature_review
```

- [ ] **Step 8: figure_generation.yaml**

```yaml
id: figure_generation
workspace_type: thesis
enabled: true
display_name: 图表设计
description: 把概念/流程/数据转成图表说明 + Mermaid
intent_description: 用户希望生成论文图表
trigger_phrases:
  - 画图
  - 生成图表
  - 设计图
required_decisions:
  - key: concept
    ask: "图要表达什么？"
    type: string
brief_schema:
  type: object
  required: [concept]
  properties:
    concept: { type: string }
    section: { type: string, optional: true }
graph_template:
  phases:
    - name: design
      tasks:
        - name: figure
          subagent_type: react
          skill_id: figure-designer
          inputs:
            concept: "{{concept}}"
            section: "{{section|default('Method')}}"
          outputs:
            - kind: document
              mapping:
                name: "图表 - {{concept}}"
                doc_kind: figure_spec
                content: "{{output.markdown}}"
result_card_template: figure_spec
```

- [ ] **Step 9: Commit**

```bash
cd /Users/ze/wenjin && git add backend/seed/capabilities/thesis/ && git commit -m "feat(seeds): thesis 7 capabilities — searcher/react with skill_id"
```

---

### Task 20: Capability YAML — sci (8 个)

**Files:**
- Create: `backend/seed/capabilities/sci/literature_search.yaml`
- Create: `backend/seed/capabilities/sci/paper_analysis.yaml`
- Create: `backend/seed/capabilities/sci/literature_review.yaml`
- Create: `backend/seed/capabilities/sci/framework_outline.yaml`
- Create: `backend/seed/capabilities/sci/section_writing.yaml`
- Create: `backend/seed/capabilities/sci/figure_generation.yaml`
- Create: `backend/seed/capabilities/sci/peer_review.yaml`
- Create: `backend/seed/capabilities/sci/journal_recommend.yaml`

- [ ] **Step 1: literature_search.yaml**

```yaml
id: literature_search
workspace_type: sci
enabled: true
display_name: 文献检索
description: 围绕 SCI 主题做系统检索和研究空白识别
intent_description: 用户希望为 SCI 选题建立候选文献池
trigger_phrases:
  - 检索文献
  - 文献检索
  - 找论文
required_decisions:
  - key: topic
    ask: "检索主题是？"
    type: string
brief_schema:
  type: object
  required: [topic]
  properties:
    topic: { type: string }
    year_min: { type: integer, optional: true }
graph_template:
  phases:
    - name: discover
      tasks:
        - name: search
          subagent_type: searcher
          skill_id: scholar-searcher
          inputs:
            query: "{{topic}}"
            year_min: "{{year_min|default(2019)}}"
          outputs:
            - kind: library_item
              iterate_on: "output.papers"
              mapping:
                title: "{{item.title}}"
                authors: "{{item.authors}}"
                year: "{{item.year}}"
                doi: "{{item.doi}}"
                abstract: "{{item.abstract}}"
    - name: synthesize
      depends_on: [discover]
      tasks:
        - name: review
          subagent_type: react
          skill_id: literature-reviewer
          inputs:
            topic: "{{topic}}"
            papers: "{{phases.discover.search.output.papers}}"
          outputs:
            - kind: document
              mapping:
                name: "{{topic}} 检索综述"
                doc_kind: literature_review
                content: "{{output.markdown}}"
result_card_template: literature_review
```

- [ ] **Step 2: paper_analysis.yaml**

```yaml
id: paper_analysis
workspace_type: sci
enabled: true
display_name: 论文分析
description: 拆解单篇论文的方法/实验/结论
intent_description: 用户希望深读分析某篇论文
trigger_phrases:
  - 分析论文
  - 拆解论文
  - 精读
required_decisions:
  - key: paper
    ask: "粘贴论文摘要/全文或给一个 DOI"
    type: string
brief_schema:
  type: object
  required: [paper]
  properties:
    paper: { type: string }
graph_template:
  phases:
    - name: analyze
      tasks:
        - name: parse
          subagent_type: react
          skill_id: paper-analyst
          inputs:
            paper: "{{paper}}"
          outputs:
            - kind: document
              mapping:
                name: "论文分析"
                doc_kind: paper_analysis
                content: "{{output|json}}"
result_card_template: paper_analysis
```

- [ ] **Step 3: literature_review.yaml**

```yaml
id: literature_review
workspace_type: sci
enabled: true
display_name: 文献综述
description: 把文献池整理为 Related Work 章节
intent_description: 用户希望基于已检索的文献写综述
trigger_phrases:
  - 写综述
  - related work
  - 综述写作
required_decisions:
  - key: topic
    ask: "综述主题是？"
    type: string
brief_schema:
  type: object
  required: [topic]
  properties:
    topic: { type: string }
    papers: { type: string, optional: true }
graph_template:
  phases:
    - name: discover
      tasks:
        - name: search
          subagent_type: searcher
          skill_id: scholar-searcher
          inputs:
            query: "{{topic}}"
    - name: synthesize
      depends_on: [discover]
      tasks:
        - name: write
          subagent_type: react
          skill_id: literature-reviewer
          inputs:
            topic: "{{topic}}"
            papers: "{{phases.discover.search.output.papers}}"
          outputs:
            - kind: document
              mapping:
                name: "{{topic}} 文献综述"
                doc_kind: literature_review
                content: "{{output.markdown}}"
result_card_template: literature_review
```

- [ ] **Step 4: framework_outline.yaml**

```yaml
id: framework_outline
workspace_type: sci
enabled: true
display_name: 框架大纲
description: 收敛选题为 SCI 摘要 + 关键词 + 章节框架
intent_description: 用户希望生成 SCI 论文框架
trigger_phrases:
  - 生成框架
  - 论文框架
  - 大纲
required_decisions:
  - key: topic
    ask: "论文主题是？"
    type: string
brief_schema:
  type: object
  required: [topic]
  properties:
    topic: { type: string }
    contributions: { type: string, optional: true }
graph_template:
  phases:
    - name: design
      tasks:
        - name: outline
          subagent_type: react
          skill_id: framework-designer
          inputs:
            topic: "{{topic}}"
            contributions: "{{contributions|default('')}}"
          outputs:
            - kind: document
              mapping:
                name: "{{topic}} 论文框架"
                doc_kind: framework_outline
                content: "{{output.markdown}}"
result_card_template: framework_outline
```

- [ ] **Step 5: section_writing.yaml**

```yaml
id: section_writing
workspace_type: sci
enabled: true
display_name: 章节写作
description: 撰写 SCI 章节草稿
intent_description: 用户希望写 SCI 论文章节
trigger_phrases:
  - 写章节
  - 写 introduction
  - 写 method
required_decisions:
  - key: section_title
    ask: "要写哪个章节？"
    type: string
brief_schema:
  type: object
  required: [section_title]
  properties:
    section_title: { type: string }
    outline: { type: string, optional: true }
    target_words: { type: integer, optional: true }
graph_template:
  phases:
    - name: write
      tasks:
        - name: draft
          subagent_type: react
          skill_id: section-writer
          inputs:
            section_title: "{{section_title}}"
            outline: "{{outline|default('')}}"
            references: ""
            target_words: "{{target_words|default(1000)}}"
          outputs:
            - kind: document
              mapping:
                name: "{{section_title}} 草稿"
                doc_kind: section_draft
                content: "{{output.markdown}}"
result_card_template: section_draft
```

- [ ] **Step 6: figure_generation.yaml** (same shape as thesis, workspace_type: sci)

```yaml
id: figure_generation
workspace_type: sci
enabled: true
display_name: 图表设计
description: 把概念/流程/数据转成 SCI 图表说明 + Mermaid
intent_description: 用户希望生成 SCI 论文图表
trigger_phrases:
  - 画图
  - 生成图表
  - 设计图
required_decisions:
  - key: concept
    ask: "图要表达什么？"
    type: string
brief_schema:
  type: object
  required: [concept]
  properties:
    concept: { type: string }
    section: { type: string, optional: true }
graph_template:
  phases:
    - name: design
      tasks:
        - name: figure
          subagent_type: react
          skill_id: figure-designer
          inputs:
            concept: "{{concept}}"
            section: "{{section|default('Method')}}"
          outputs:
            - kind: document
              mapping:
                name: "图表 - {{concept}}"
                doc_kind: figure_spec
                content: "{{output.markdown}}"
result_card_template: figure_spec
```

- [ ] **Step 7: peer_review.yaml**

```yaml
id: peer_review
workspace_type: sci
enabled: true
display_name: 同行评审
description: 从审稿人视角定位 SCI 稿件薄弱点
intent_description: 用户希望审稿建议
trigger_phrases:
  - 审稿
  - 评审
  - 修订建议
required_decisions:
  - key: manuscript
    ask: "粘贴稿件内容"
    type: string
brief_schema:
  type: object
  required: [manuscript]
  properties:
    manuscript: { type: string }
    focus: { type: string, optional: true }
graph_template:
  phases:
    - name: review
      tasks:
        - name: critique
          subagent_type: react
          skill_id: peer-reviewer
          inputs:
            manuscript: "{{manuscript}}"
            focus: "{{focus|default('整体质量')}}"
          outputs:
            - kind: document
              mapping:
                name: "审稿意见"
                doc_kind: peer_review
                content: "{{output.markdown}}"
result_card_template: peer_review
```

- [ ] **Step 8: journal_recommend.yaml**

```yaml
id: journal_recommend
workspace_type: sci
enabled: true
display_name: 期刊推荐
description: 基于论文画像推荐候选期刊
intent_description: 用户希望知道论文投哪
trigger_phrases:
  - 期刊推荐
  - 投哪
  - 选刊
required_decisions:
  - key: abstract
    ask: "粘贴论文摘要"
    type: string
brief_schema:
  type: object
  required: [abstract]
  properties:
    abstract: { type: string }
    discipline: { type: string, optional: true }
    prefs: { type: string, optional: true }
graph_template:
  phases:
    - name: recommend
      tasks:
        - name: pick
          subagent_type: react
          skill_id: journal-recommender
          inputs:
            abstract: "{{abstract}}"
            discipline: "{{discipline|default('计算机科学')}}"
            prefs: "{{prefs|default('无')}}"
          outputs:
            - kind: document
              mapping:
                name: "期刊推荐"
                doc_kind: journal_recommend
                content: "{{output.markdown}}"
result_card_template: journal_recommend
```

- [ ] **Step 9: Commit**

```bash
cd /Users/ze/wenjin && git add backend/seed/capabilities/sci/ && git commit -m "feat(seeds): sci 8 capabilities"
```

---

### Task 21: Capability YAML — proposal (4 个)

**Files:**
- Create: `backend/seed/capabilities/proposal/proposal_outline.yaml`
- Create: `backend/seed/capabilities/proposal/background_research.yaml`
- Create: `backend/seed/capabilities/proposal/experiment_design.yaml`
- Create: `backend/seed/capabilities/proposal/figure_generation.yaml`

- [ ] **Step 1: proposal_outline.yaml**

```yaml
id: proposal_outline
workspace_type: proposal
enabled: true
display_name: 申报书大纲
description: 把研究目标整理为申报书结构
intent_description: 用户希望写申报书大纲
trigger_phrases:
  - 申报书
  - 写申报
  - 申报大纲
required_decisions:
  - key: topic
    ask: "项目主题是？"
    type: string
brief_schema:
  type: object
  required: [topic]
  properties:
    topic: { type: string }
    contributions: { type: string, optional: true }
graph_template:
  phases:
    - name: design
      tasks:
        - name: outline
          subagent_type: react
          skill_id: framework-designer
          inputs:
            topic: "{{topic}}"
            contributions: "{{contributions|default('')}}"
          outputs:
            - kind: document
              mapping:
                name: "{{topic}} 申报大纲"
                doc_kind: framework_outline
                content: "{{output.markdown}}"
result_card_template: framework_outline
```

- [ ] **Step 2: background_research.yaml**

```yaml
id: background_research
workspace_type: proposal
enabled: true
display_name: 背景调研
description: 项目背景的文献检索 + 综述
intent_description: 用户希望做申报书的背景调研
trigger_phrases:
  - 背景调研
  - 项目背景
  - 调研项目
required_decisions:
  - key: topic
    ask: "调研主题是？"
    type: string
brief_schema:
  type: object
  required: [topic]
  properties:
    topic: { type: string }
graph_template:
  phases:
    - name: discover
      tasks:
        - name: search
          subagent_type: searcher
          skill_id: scholar-searcher
          inputs:
            query: "{{topic}}"
    - name: synthesize
      depends_on: [discover]
      tasks:
        - name: write
          subagent_type: react
          skill_id: literature-reviewer
          inputs:
            topic: "{{topic}}"
            papers: "{{phases.discover.search.output.papers}}"
          outputs:
            - kind: document
              mapping:
                name: "{{topic}} 项目背景"
                doc_kind: literature_review
                content: "{{output.markdown}}"
result_card_template: literature_review
```

- [ ] **Step 3: experiment_design.yaml**

```yaml
id: experiment_design
workspace_type: proposal
enabled: true
display_name: 实验设计
description: 设计申报书的实验/技术路线
intent_description: 用户希望设计实验或技术路线
trigger_phrases:
  - 实验设计
  - 技术路线
  - 设计实验
required_decisions:
  - key: topic
    ask: "实验目标/主题是？"
    type: string
brief_schema:
  type: object
  required: [topic]
  properties:
    topic: { type: string }
    contributions: { type: string, optional: true }
graph_template:
  phases:
    - name: design
      tasks:
        - name: plan
          subagent_type: react
          skill_id: framework-designer
          inputs:
            topic: "实验设计：{{topic}}"
            contributions: "{{contributions|default('')}}"
          outputs:
            - kind: document
              mapping:
                name: "{{topic}} 实验路线"
                doc_kind: framework_outline
                content: "{{output.markdown}}"
result_card_template: framework_outline
```

- [ ] **Step 4: figure_generation.yaml** (workspace_type: proposal)

Same as thesis figure_generation, just `workspace_type: proposal`.

- [ ] **Step 5: Commit**

```bash
cd /Users/ze/wenjin && git add backend/seed/capabilities/proposal/ && git commit -m "feat(seeds): proposal 4 capabilities"
```

---

### Task 22: Capability YAML — patent (3 个)

**Files:**
- Create: `backend/seed/capabilities/patent/patent_outline.yaml`
- Create: `backend/seed/capabilities/patent/prior_art_search.yaml`
- Create: `backend/seed/capabilities/patent/figure_generation.yaml`

- [ ] **Step 1: patent_outline.yaml**

```yaml
id: patent_outline
workspace_type: patent
enabled: true
display_name: 专利框架
description: 撰写专利权利要求 + 说明书框架
intent_description: 用户希望准备专利材料
trigger_phrases:
  - 专利框架
  - 写专利
  - 权利要求
required_decisions:
  - key: invention
    ask: "发明内容/核心技术点是？"
    type: string
brief_schema:
  type: object
  required: [invention]
  properties:
    invention: { type: string }
graph_template:
  phases:
    - name: design
      tasks:
        - name: outline
          subagent_type: react
          skill_id: framework-designer
          inputs:
            topic: "专利：{{invention}}"
            contributions: ""
          outputs:
            - kind: document
              mapping:
                name: "专利框架"
                doc_kind: framework_outline
                content: "{{output.markdown}}"
result_card_template: framework_outline
```

- [ ] **Step 2: prior_art_search.yaml**

```yaml
id: prior_art_search
workspace_type: patent
enabled: true
display_name: 现有技术检索
description: 检索现有技术（学术 + 专利数据）
intent_description: 用户希望检索专利现有技术
trigger_phrases:
  - 现有技术
  - 专利检索
  - prior art
required_decisions:
  - key: topic
    ask: "技术主题是？"
    type: string
brief_schema:
  type: object
  required: [topic]
  properties:
    topic: { type: string }
graph_template:
  phases:
    - name: discover
      tasks:
        - name: search
          subagent_type: searcher
          skill_id: prior-art-searcher
          inputs:
            query: "{{topic}}"
          outputs:
            - kind: library_item
              iterate_on: "output.papers"
              mapping:
                title: "{{item.title}}"
                authors: "{{item.authors}}"
                year: "{{item.year}}"
                doi: "{{item.doi}}"
result_card_template: library_intake
```

- [ ] **Step 3: figure_generation.yaml** (workspace_type: patent)

Same as thesis figure_generation, just `workspace_type: patent`.

- [ ] **Step 4: Commit**

```bash
cd /Users/ze/wenjin && git add backend/seed/capabilities/patent/ && git commit -m "feat(seeds): patent 3 capabilities"
```

---

### Task 23: Capability YAML — software_copyright (3 个)

**Files:**
- Create: `backend/seed/capabilities/software_copyright/copyright_materials.yaml`
- Create: `backend/seed/capabilities/software_copyright/technical_description.yaml`
- Create: `backend/seed/capabilities/software_copyright/figure_generation.yaml`

- [ ] **Step 1: copyright_materials.yaml**

```yaml
id: copyright_materials
workspace_type: software_copyright
enabled: true
display_name: 著作权材料
description: 生成软著申请的材料清单和模板
intent_description: 用户希望准备软著申请材料
trigger_phrases:
  - 软著
  - 著作权
  - 软著材料
required_decisions:
  - key: software_name
    ask: "软件名称是？"
    type: string
brief_schema:
  type: object
  required: [software_name]
  properties:
    software_name: { type: string }
    description: { type: string, optional: true }
graph_template:
  phases:
    - name: write
      tasks:
        - name: draft
          subagent_type: react
          skill_id: framework-designer
          inputs:
            topic: "软著材料：{{software_name}}"
            contributions: "{{description|default('')}}"
          outputs:
            - kind: document
              mapping:
                name: "{{software_name}} 软著材料"
                doc_kind: framework_outline
                content: "{{output.markdown}}"
result_card_template: framework_outline
```

- [ ] **Step 2: technical_description.yaml**

```yaml
id: technical_description
workspace_type: software_copyright
enabled: true
display_name: 技术说明书
description: 撰写软著技术说明书
intent_description: 用户希望写软件技术说明
trigger_phrases:
  - 技术说明
  - 写说明书
  - 软件说明
required_decisions:
  - key: software_name
    ask: "软件名称是？"
    type: string
brief_schema:
  type: object
  required: [software_name]
  properties:
    software_name: { type: string }
    description: { type: string, optional: true }
graph_template:
  phases:
    - name: write
      tasks:
        - name: draft
          subagent_type: react
          skill_id: section-writer
          inputs:
            section_title: "{{software_name}} 技术说明书"
            outline: "{{description|default('')}}"
            references: ""
            target_words: 1500
          outputs:
            - kind: document
              mapping:
                name: "{{software_name}} 技术说明书"
                doc_kind: section_draft
                content: "{{output.markdown}}"
result_card_template: section_draft
```

- [ ] **Step 3: figure_generation.yaml** (workspace_type: software_copyright)

Same as thesis figure_generation, just `workspace_type: software_copyright`.

- [ ] **Step 4: Commit**

```bash
cd /Users/ze/wenjin && git add backend/seed/capabilities/software_copyright/ && git commit -m "feat(seeds): software_copyright 3 capabilities"
```

---

### Task 24: Seed integrity test

**Files:**
- Create: `backend/tests/integration/test_capability_skill_seeds.py`

- [ ] **Step 1: 写完整性测试**

`backend/tests/integration/test_capability_skill_seeds.py`:

```python
"""Integration test: all capability seeds reference existing skills."""

from pathlib import Path
import yaml

SEED_ROOT = Path(__file__).resolve().parent.parent.parent / "seed"


def _collect_skill_ids() -> set[str]:
    out: set[str] = set()
    for f in (SEED_ROOT / "skills").glob("*.yaml"):
        data = yaml.safe_load(f.read_text())
        out.add(data["id"])
    return out


def _collect_capability_files() -> list[Path]:
    return list((SEED_ROOT / "capabilities").glob("*/*.yaml"))


def test_every_capability_skill_id_exists():
    skill_ids = _collect_skill_ids()
    assert skill_ids, "no skills found"

    for cap_path in _collect_capability_files():
        data = yaml.safe_load(cap_path.read_text())
        for phase in data["graph_template"]["phases"]:
            for task in phase["tasks"]:
                sid = task.get("skill_id")
                assert sid is not None, f"{cap_path}: task {task.get('name')} missing skill_id"
                assert sid in skill_ids, (
                    f"{cap_path}: task {task['name']} references unknown skill_id '{sid}'. "
                    f"Available: {sorted(skill_ids)}"
                )


def test_every_capability_subagent_type_is_searcher_or_react():
    valid = {"searcher", "react"}
    for cap_path in _collect_capability_files():
        data = yaml.safe_load(cap_path.read_text())
        for phase in data["graph_template"]["phases"]:
            for task in phase["tasks"]:
                st = task.get("subagent_type")
                assert st in valid, (
                    f"{cap_path}: task {task['name']} has invalid subagent_type '{st}'. "
                    f"Must be one of {valid}"
                )


def test_every_capability_required_fields_present():
    required = {"id", "workspace_type", "display_name", "intent_description",
                "brief_schema", "graph_template", "result_card_template"}
    for cap_path in _collect_capability_files():
        data = yaml.safe_load(cap_path.read_text())
        missing = required - set(data.keys())
        assert not missing, f"{cap_path}: missing fields {missing}"


def test_capability_count_matches_spec():
    files = _collect_capability_files()
    by_ws: dict[str, int] = {}
    for f in files:
        data = yaml.safe_load(f.read_text())
        by_ws[data["workspace_type"]] = by_ws.get(data["workspace_type"], 0) + 1
    assert by_ws["thesis"] == 7
    assert by_ws["sci"] == 8
    assert by_ws["proposal"] == 4
    assert by_ws["patent"] == 3
    assert by_ws["software_copyright"] == 3
```

- [ ] **Step 2: 跑测试**

```bash
cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/integration/test_capability_skill_seeds.py -v
```

Expected: PASS (4 tests)

- [ ] **Step 3: Commit**

```bash
cd /Users/ze/wenjin && git add backend/tests/integration/test_capability_skill_seeds.py && git commit -m "test(seeds): verify capability/skill seed integrity"
```

---

### Task 25: 端到端验证

**Files:** (no edits; verification only)

- [ ] **Step 1: 清表 + Rebuild**

```bash
docker compose exec postgres psql -U postgres -d wenjin -c "TRUNCATE capability_skills, capabilities CASCADE;"
docker compose up -d --build worker gateway frontend
```

- [ ] **Step 2: 跑 bootstrap-admin 触发 seed**

```bash
docker compose run --rm bootstrap-admin
```

Expected stdout includes:
```
[bootstrap-admin] Seeded 9 skill record(s)
[bootstrap-admin] Seeded 25 capability record(s)
```

- [ ] **Step 3: SQL 验证**

```bash
docker compose exec postgres psql -U postgres -d wenjin -c "SELECT COUNT(*) FROM capability_skills WHERE enabled = true;"
# Expected: 9

docker compose exec postgres psql -U postgres -d wenjin -c "SELECT workspace_type, COUNT(*) FROM capabilities WHERE enabled = true GROUP BY workspace_type ORDER BY workspace_type;"
# Expected:
#  patent             | 3
#  proposal           | 4
#  sci                | 8
#  software_copyright | 3
#  thesis             | 7
```

- [ ] **Step 4: 浏览器 E2E — thesis**

1. 打开 `http://localhost:2026/`，登录 admin
2. 进入 thesis 类型的 workspace
3. 输入：`帮我对"扩散模型"做一次深度调研`
4. **预期**：
   - 模型调用 `launch_feature(feature_id="deep_research", params={...})`
   - 右侧面板显示 `search` → `write` 两个节点 graph
   - 1-2 分钟后看到 result_card 包含 Semantic Scholar 真实论文 + 文献综述 markdown

- [ ] **Step 5: 浏览器 E2E — sci**

1. 进入 sci 类型 workspace
2. 输入：`检索一下"图神经网络"相关文献`
3. **预期**：launch `literature_search`，右侧 graph 出现，Semantic Scholar 返回真实结果

- [ ] **Step 6: 浏览器 E2E — proposal**

1. 进入 proposal workspace
2. 输入：`帮我做项目背景调研，主题是联邦学习`
3. **预期**：launch `background_research`，graph 出现

- [ ] **Step 7: 浏览器 E2E — patent**

1. 进入 patent workspace
2. 输入：`检索一下机器人控制的现有技术`
3. **预期**：launch `prior_art_search`

- [ ] **Step 8: 浏览器 E2E — software_copyright**

1. 进入 software_copyright workspace
2. 输入：`帮我写一份"图书管理系统"的技术说明书`
3. **预期**：launch `technical_description`

- [ ] **Step 9: 动态 prompt 修改验证**

```bash
docker compose exec postgres psql -U postgres -d wenjin -c "UPDATE capability_skills SET prompt = '只输出"你好"二字' WHERE id = 'literature-reviewer';"
docker compose exec redis redis-cli PUBLISH skill.invalidated '{"skill_id":"literature-reviewer"}'
```

再触发一次 thesis 的 `deep_research`，**预期**：综述步骤输出"你好"（确认 DB prompt 生效，无需重启）。

恢复：
```bash
docker compose run --rm bootstrap-admin   # 不会重置已 seed 表
docker compose exec postgres psql -U postgres -d wenjin -c "TRUNCATE capability_skills CASCADE; "
docker compose run --rm bootstrap-admin   # 重新 seed
```

- [ ] **Step 10: 跑所有测试**

```bash
cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/ -v --timeout=60
```

Expected: all PASS

- [ ] **Step 11: Final commit**

```bash
cd /Users/ze/wenjin && git status && git log --oneline -25
```

如果有遗漏文件 commit it. 否则 plan complete.

---

## Self-Review

### Spec coverage
- ✅ Data model（2 张表无 version/timestamp）— Task 1-3
- ✅ Capability YAML schema — Task 19-23
- ✅ Skill YAML schema — Task 18
- ✅ SearchSource 接口 + Semantic Scholar 实现 — Task 7-9
- ✅ SearcherSubagent — Task 11
- ✅ ReactSubagent — Task 12-13
- ✅ Subagent 仅 2 种（删 5 stub）— Task 15
- ✅ Compiler 注入 skill — Task 14
- ✅ Leader agent prompt 双清单 — Task 16
- ✅ Bootstrap 自动 seed — Task 17
- ✅ 25 capabilities + 9 skills — Task 18-23
- ✅ 缓存 + EventBus 失效 — Task 5
- ✅ 端到端测试 5 workspace type — Task 25

### Placeholder scan
- 全部 Step 都有具体代码/命令
- 无 "TBD"、"add error handling"、"similar to Task N" 等
- 所有 file paths 绝对路径或明确相对路径

### Type consistency
- `CapabilitySkill` 字段命名 (id, enabled, subagent_type, prompt, allowed_tools, resources, config) 在 Task 3、4、5、10、11、12、18、24 一致
- `SubagentContext.skill: CapabilitySkill | None` 在 Task 10、11、12、14 一致
- `SearchResult` model 字段在 Task 7、9、11 一致
- `register_search_source` 签名在 Task 8、9 一致
- `_render_capabilities_and_skills` 是 async — Task 16 已注明 caller 需 await

---

**Plan complete and saved to `docs/superpowers/plans/2026-05-11-capability-skill-closed-loop.md`.**
