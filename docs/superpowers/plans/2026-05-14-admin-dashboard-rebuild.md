# Admin Dashboard Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the admin dashboard with sidebar IA, capability/skill YAML editor, credit grant automation, 4-panel analytics, and clean up v1 dead code from incomplete migrations.

**Architecture:** 5 sequential phases (~6 weeks single-developer). P1 cleans dead code and converges schema. P2 migrates current admin page into a sidebar layout with sub-routes. P3/P4/P5 are independent and can parallelize: P3 adds Capability/Skill YAML management, P4 adds credit grant rules and redeem codes, P5 adds analytics panels.

**Tech Stack:** Backend — Python 3.13, FastAPI, SQLAlchemy async, Pydantic v2, Alembic, croniter, Redis pub/sub (EventBus), Celery. Frontend — Next.js 16, React 19, TypeScript, Tailwind, Zustand, @monaco-editor/react, Recharts. Tests — pytest (asyncio_mode=auto), vitest, Playwright.

**Spec:** [docs/superpowers/specs/2026-05-14-admin-dashboard-rebuild-design.md](../specs/2026-05-14-admin-dashboard-rebuild-design.md)

---

## Phase 1 — Cleanup + Schema Convergence

**Goal:** Remove `feature_leader`, `workspace_features`, `agents/graphs/`, dead frontend file `execution-presenters.ts`, vestigial field `result_card_template`; add `ui_meta` to Capability; wire the real EventBus in gateway.

**Pre-conditions:** All Phase 1 tasks operate on the current state. Run `git status` first — if there's uncommitted WIP touching any of these paths, stash or commit before starting.

### Task 1.1: Snapshot WorkspaceFeatureDefinition data

**Files:**
- Create: `backend/scripts/migrate_workspace_features_to_seed_yaml.py`
- Read: `backend/src/workspace_features/registry.py`

- [ ] **Step 1: Read the registry to confirm 25 features exist**

Run: `grep -c "WorkspaceFeatureDefinition(" backend/src/workspace_features/registry.py`
Expected: 25 (matches count of capability YAMLs)

- [ ] **Step 2: Write the ETL script**

```python
"""One-off ETL: pull icon/color/stages/follow_up_prompt from WorkspaceFeatureDefinition
and merge into corresponding capability seed YAMLs (matched by id).

Run once during Phase 1 of admin dashboard rebuild. Idempotent.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SEED_DIR = ROOT / "seed" / "capabilities"

sys.path.insert(0, str(ROOT / "src"))
from workspace_features.registry import (
    THESIS_FEATURES,
    SCI_FEATURES,
    PROPOSAL_FEATURES,
    SOFTWARE_COPYRIGHT_FEATURES,
    PATENT_FEATURES,
)

ALL = (
    *THESIS_FEATURES,
    *SCI_FEATURES,
    *PROPOSAL_FEATURES,
    *SOFTWARE_COPYRIGHT_FEATURES,
    *PATENT_FEATURES,
)


def build_ui_meta(feature) -> dict:
    return {
        "icon": feature.icon,
        "color": feature.color or "purple",
        "order": 0,
        "stages": [{"id": s.id, "label": s.label} for s in feature.stages],
        "follow_up_prompt": feature.follow_up_prompt,
    }


def main() -> int:
    updated = 0
    skipped = 0
    for feature in ALL:
        seed_path = SEED_DIR / feature.workspace_type / f"{feature.id}.yaml"
        if not seed_path.exists():
            print(f"SKIP (no seed): {feature.workspace_type}/{feature.id}")
            skipped += 1
            continue
        with seed_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if data.get("id") != feature.id:
            print(f"WARN id mismatch in {seed_path}: yaml.id={data.get('id')} feature.id={feature.id}")
        data["ui_meta"] = build_ui_meta(feature)
        for i, f in enumerate(ALL):
            if f.workspace_type == feature.workspace_type:
                if f.id == feature.id:
                    data["ui_meta"]["order"] = i
                    break
        with seed_path.open("w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh, sort_keys=False, allow_unicode=True)
        print(f"OK: {feature.workspace_type}/{feature.id}")
        updated += 1
    print(f"\nUpdated: {updated}  Skipped: {skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Run the ETL**

Run: `cd backend && .venv/bin/python scripts/migrate_workspace_features_to_seed_yaml.py`
Expected: `Updated: 25  Skipped: 0` (assuming all features have corresponding seeds; if any SKIP shown, hand-merge that one)

- [ ] **Step 4: Verify ui_meta blocks in seed YAMLs**

Run: `grep -l "ui_meta:" backend/seed/capabilities/**/*.yaml | wc -l`
Expected: 25

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/migrate_workspace_features_to_seed_yaml.py backend/seed/capabilities/
git commit -m "chore(seeds): inject ui_meta from WorkspaceFeatureDefinition into capability YAMLs"
```

### Task 1.2: Migration 049 — add `ui_meta` column

**Files:**
- Create: `backend/alembic/versions/049_capability_add_ui_meta.py`

- [ ] **Step 1: Write the migration**

```python
"""Add ui_meta JSONB column to capabilities.

Revision ID: 049_capability_add_ui_meta
Revises: 048_drop_execution_sessions_legacy
Create Date: 2026-05-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "049_capability_add_ui_meta"
down_revision: str | None = "048_drop_execution_sessions_legacy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "capabilities",
        sa.Column("ui_meta", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )


def downgrade() -> None:
    op.drop_column("capabilities", "ui_meta")
```

- [ ] **Step 2: Run the migration**

Run: `cd backend && .venv/bin/alembic upgrade head`
Expected: `Running upgrade 048_drop_execution_sessions_legacy -> 049_capability_add_ui_meta, Add ui_meta JSONB column to capabilities`

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/049_capability_add_ui_meta.py
git commit -m "feat(db): add ui_meta column to capabilities"
```

### Task 1.3: Migration 050 — drop `result_card_template`

**Files:**
- Create: `backend/alembic/versions/050_capability_drop_result_card_template.py`

- [ ] **Step 1: Write the migration**

```python
"""Drop vestigial result_card_template from capabilities.

Field was never consumed end-to-end: frontend ResultCard renders by output.kind,
not template name. See spec §2.2 and decisions table.

Revision ID: 050_capability_drop_result_card_template
Revises: 049_capability_add_ui_meta
Create Date: 2026-05-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "050_capability_drop_result_card_template"
down_revision: str | None = "049_capability_add_ui_meta"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("capabilities", "result_card_template")


def downgrade() -> None:
    op.add_column(
        "capabilities",
        sa.Column("result_card_template", sa.String(length=100), nullable=False, server_default=""),
    )
```

- [ ] **Step 2: Strip the field from 25 seed YAMLs**

Run: `cd backend && sed -i '' '/^result_card_template:/d' seed/capabilities/*/*.yaml`
Then verify: `grep -c "result_card_template" seed/capabilities/*/*.yaml | grep -v ":0" | wc -l`
Expected: 0 (no file still contains the field)

- [ ] **Step 3: Run the migration**

Run: `cd backend && .venv/bin/alembic upgrade head`
Expected: upgrade applies, column dropped

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/050_capability_drop_result_card_template.py backend/seed/capabilities/
git commit -m "feat(db): drop vestigial result_card_template column + seed cleanup"
```

### Task 1.4: Capability ORM — add `ui_meta`, drop `result_card_template`

**Files:**
- Modify: `backend/src/database/models/capability.py`

- [ ] **Step 1: Update the ORM**

```python
"""Capability ORM model — defines available capabilities per workspace type."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


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
    ui_meta: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index(
            "ix_capabilities_active",
            "workspace_type",
            "enabled",
            postgresql_where="enabled = true",
        ),
    )

    def __repr__(self) -> str:
        return f"<Capability(id={self.id!r}, workspace_type={self.workspace_type!r})>"
```

- [ ] **Step 2: Run model imports check**

Run: `cd backend && .venv/bin/python -c "from src.database.models.capability import Capability; print(Capability.__table__.columns.keys())"`
Expected: list includes `ui_meta`, excludes `result_card_template`

- [ ] **Step 3: Commit**

```bash
git add backend/src/database/models/capability.py
git commit -m "feat(models): Capability adds ui_meta, drops result_card_template"
```

### Task 1.5: capability_loader — handle ui_meta, drop result_card_template

**Files:**
- Modify: `backend/src/services/capability_loader.py`
- Modify: `backend/tests/services/test_capability_loader.py`

- [ ] **Step 1: Update REQUIRED_FIELDS and OPTIONAL_DEFAULTS**

In [backend/src/services/capability_loader.py](../../backend/src/services/capability_loader.py), replace the existing `REQUIRED_FIELDS` and `OPTIONAL_DEFAULTS` constants:

```python
REQUIRED_FIELDS = {
    "id",
    "workspace_type",
    "display_name",
    "intent_description",
    "brief_schema",
    "graph_template",
    "ui_meta",
}

OPTIONAL_DEFAULTS = {
    "enabled": True,
    "description": "",
    "trigger_phrases": [],
    "required_decisions": [],
    "notes": None,
}
```

Also search the file for any reference to `result_card_template` (e.g., in `to_orm_kwargs`, `from_orm`, etc.) and delete those lines; add `ui_meta` to the field list wherever the field tuple is enumerated.

- [ ] **Step 2: Add test for ui_meta loading**

Append to `backend/tests/services/test_capability_loader.py`:

```python
@pytest.mark.asyncio
async def test_loads_ui_meta_from_yaml(tmp_path, mock_session):
    yaml_text = """
id: test_cap
workspace_type: thesis
display_name: 测试
intent_description: test intent
brief_schema: {type: object}
graph_template: {phases: []}
ui_meta:
  icon: search
  color: purple
  order: 0
  stages:
    - {id: s1, label: 第一步}
  follow_up_prompt: 继续吧
"""
    (tmp_path / "thesis").mkdir()
    (tmp_path / "thesis" / "test_cap.yaml").write_text(yaml_text)
    loader = CapabilityLoader(session=mock_session, seed_dir=tmp_path)
    capabilities = await loader.load_all()
    assert len(capabilities) == 1
    cap = capabilities[0]
    assert cap.ui_meta == {
        "icon": "search",
        "color": "purple",
        "order": 0,
        "stages": [{"id": "s1", "label": "第一步"}],
        "follow_up_prompt": "继续吧",
    }
```

- [ ] **Step 3: Run loader tests**

Run: `cd backend && .venv/bin/python -m pytest tests/services/test_capability_loader.py -v`
Expected: PASS (including new ui_meta test). If any test still references `result_card_template`, fix it.

- [ ] **Step 4: Commit**

```bash
git add backend/src/services/capability_loader.py backend/tests/services/test_capability_loader.py
git commit -m "feat(loader): handle ui_meta field; remove result_card_template"
```

### Task 1.6: Delete `workspace_features/` directory

**Files:**
- Delete: `backend/src/workspace_features/`

- [ ] **Step 1: Confirm no live importers outside dead code**

Run: `grep -rn "from src.workspace_features\|import workspace_features" backend/src --include="*.py" | grep -v __pycache__ | grep -v "feature_leader/" | grep -v "agents/graphs/"`
Expected: only `backend/src/agents/chat_agent/agent.py:544, 571` lines mentioning `list_workspace_features_tool` (handled in Task 1.9) and the dead `feature_leader`/`graphs` paths (handled in Tasks 1.7/1.8). If anything else appears, stop and audit.

- [ ] **Step 2: Delete the directory**

Run: `git rm -rf backend/src/workspace_features/`

- [ ] **Step 3: Remove pyc cache**

Run: `find backend -name "*.pyc" -path "*workspace_features*" -delete`

- [ ] **Step 4: Commit (deferred)**

Don't commit yet — Tasks 1.7-1.10 will produce a single coherent "delete dead code" commit at Task 1.11.

### Task 1.7: Delete `feature_leader/` directory

**Files:**
- Delete: `backend/src/agents/feature_leader/`

- [ ] **Step 1: Confirm zero external callers**

Run: `grep -rn "FeatureLeaderRuntime\|execute_feature_graph\|get_feature_leader_runtime" backend/src --include="*.py" | grep -v __pycache__ | grep -v "feature_leader/" | grep -v "agents/graphs/"`
Expected: empty output

- [ ] **Step 2: Delete**

Run: `git rm -rf backend/src/agents/feature_leader/`

- [ ] **Step 3: Remove pyc cache**

Run: `find backend -name "*.pyc" -path "*feature_leader*" -delete`

### Task 1.8: Delete `agents/graphs/` directory

**Files:**
- Delete: `backend/src/agents/graphs/`

- [ ] **Step 1: Confirm no external callers**

Run: `grep -rn "from src.agents.graphs\|import src.agents.graphs" backend/src --include="*.py" | grep -v __pycache__ | grep -v "feature_leader/" | grep -v "agents/graphs/"`
Expected: empty

- [ ] **Step 2: Delete**

Run: `git rm -rf backend/src/agents/graphs/`

- [ ] **Step 3: Remove pyc cache**

Run: `find backend -name "*.pyc" -path "*agents/graphs*" -delete`

### Task 1.9: chat_agent — swap `list_workspace_features_tool` → `list_capabilities_tool`

**Files:**
- Modify: `backend/src/agents/chat_agent/agent.py`
- Create: `backend/src/agents/chat_agent/tools/list_capabilities.py`
- Modify: `backend/src/agents/chat_agent/tools/__init__.py` (if it exists)

- [ ] **Step 1: Find current tool definition**

Run: `grep -rn "list_workspace_features_tool\|def list_workspace_features" backend/src/agents/chat_agent --include="*.py"`
Locate where the tool is defined and where it's imported.

- [ ] **Step 2: Create new `list_capabilities_tool`**

```python
"""Tool: list capabilities available in a workspace.

Replaces the old list_workspace_features_tool. Reads from DB capabilities table
(filtered by workspace_type, enabled=true), returns id + display_name + description.
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import tool
from sqlalchemy import select

from src.database import Capability, get_db_session


@tool
async def list_capabilities_tool(workspace_type: str) -> list[dict[str, Any]]:
    """List enabled capabilities for a workspace type.

    Args:
        workspace_type: e.g., "thesis", "sci", "proposal", "software_copyright", "patent".

    Returns:
        List of {id, display_name, description, intent_description} dicts.
    """
    async with get_db_session() as db:
        result = await db.execute(
            select(Capability)
            .where(Capability.workspace_type == workspace_type)
            .where(Capability.enabled == True)  # noqa: E712
            .order_by(Capability.ui_meta["order"].astext.cast_to(Capability.ui_meta.type.python_type)),
        )
        capabilities = result.scalars().all()
        return [
            {
                "id": c.id,
                "display_name": c.display_name,
                "description": c.description,
                "intent_description": c.intent_description,
            }
            for c in capabilities
        ]
```

(If the ordering cast in SQLAlchemy proves brittle, fall back to Python-side sort by `c.ui_meta.get("order", 0)` after fetching.)

- [ ] **Step 3: Update chat_agent imports**

In `backend/src/agents/chat_agent/agent.py`, find lines 544 and 571 (or current equivalents — line numbers may drift). Replace both `list_workspace_features_tool` references with `list_capabilities_tool`. Update import statement at the top accordingly:

```python
# old:
# from src.workspace_features import list_workspace_features  # delete
# new:
from src.agents.chat_agent.tools.list_capabilities import list_capabilities_tool
```

- [ ] **Step 4: Update chat_agent prompts referring to "feature"**

Run: `grep -n "feature\|features" backend/src/agents/chat_agent/prompts/*.py`
Review each hit. Where the prompt instructs the agent to "list features" or "pick a feature", change to "list capabilities" / "pick a capability". Keep changes minimal — only rename, not restructure.

- [ ] **Step 5: Update chat_agent tests**

Run: `grep -l "list_workspace_features_tool\|list_workspace_features" backend/tests --include="*.py" -r`
Update each test file: rename mock references; if a test asserts on tool name strings, update to `"list_capabilities_tool"`.

- [ ] **Step 6: Run chat_agent tests**

Run: `cd backend && .venv/bin/python -m pytest tests/agents/chat_agent/ -v`
Expected: PASS

### Task 1.10: Drop `/workspaces/{id}/features` endpoint

**Files:**
- Modify: `backend/src/gateway/routers/workspaces.py`
- Modify: `backend/src/gateway/routers/workspaces_contracts.py`
- Modify: `frontend/lib/api/workspace.ts`

- [ ] **Step 1: Delete the endpoint**

In `backend/src/gateway/routers/workspaces.py`, find lines 267-291 (the `list_workspace_features_catalog` function decorated with `@router.get("/{workspace_id}/features", ...)`) and delete the whole function. Also remove the `WorkspaceFeaturesResponse` import on line 26 and the `list_workspace_features` / `get_workspace_feature` imports on line 47.

- [ ] **Step 2: Delete the response model**

In `backend/src/gateway/routers/workspaces_contracts.py`, find `class WorkspaceFeaturesResponse` (~line 134) and delete it and any related models that reference it.

- [ ] **Step 3: Delete frontend API call**

In `frontend/lib/api/workspace.ts` (~line 365), find `getWorkspaceFeatures` (or similar) that calls `/features`. Delete the function and any TypeScript types that only it uses.

- [ ] **Step 4: Run tests**

Run: `cd backend && .venv/bin/python -m pytest tests/gateway/ -v -k "workspace"`
Expected: PASS (any test referencing the deleted endpoint must be updated or deleted)

### Task 1.11: capabilities router — serialize ui_meta + real EventBus

**Files:**
- Modify: `backend/src/gateway/routers/capabilities.py`

- [ ] **Step 1: Write the failing test**

In `backend/tests/gateway/test_capabilities_router.py` (create file if missing), add:

```python
@pytest.mark.asyncio
async def test_capabilities_endpoint_includes_ui_meta(client, seed_capability_with_ui_meta):
    resp = await client.get("/capabilities?workspace_type=thesis")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) > 0
    assert "ui_meta" in items[0]
    assert items[0]["ui_meta"]["icon"]
```

(Add `seed_capability_with_ui_meta` fixture in `tests/gateway/conftest.py` that inserts one Capability row with a known ui_meta dict.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/gateway/test_capabilities_router.py::test_capabilities_endpoint_includes_ui_meta -v`
Expected: FAIL — `ui_meta` key not in response.

- [ ] **Step 3: Update serialization helper**

In `backend/src/gateway/routers/capabilities.py`, find `_capability_to_dict` (~line 68). Replace with:

```python
def _capability_to_dict(cap: Any) -> dict[str, Any]:
    """Convert a Capability ORM row to a plain dict for API responses."""
    return {
        "id": cap.id,
        "workspace_type": cap.workspace_type,
        "enabled": cap.enabled,
        "display_name": cap.display_name,
        "description": cap.description,
        "intent_description": cap.intent_description,
        "trigger_phrases": cap.trigger_phrases,
        "required_decisions": cap.required_decisions,
        "brief_schema": cap.brief_schema,
        "graph_template": cap.graph_template,
        "ui_meta": cap.ui_meta,
        "notes": cap.notes,
    }
```

- [ ] **Step 4: Replace `_NoOpEventBus` with real bus**

In the same file, find `_get_resolver` (~line 30) and replace its body:

```python
async def _get_resolver(request: Request) -> "CapabilityResolver":
    from src.services.capability_resolver import CapabilityResolver

    if not hasattr(request.app.state, "capability_resolver"):
        from src.academic.cache.redis_client import redis_client
        from src.database import get_db_session
        from src.services.event_bus import EventBus

        if redis_client._client is None:
            await redis_client.connect()

        resolver = CapabilityResolver(
            session_factory=get_db_session,
            event_bus=EventBus(redis_client.client),
        )
        request.app.state.capability_resolver = resolver

    return request.app.state.capability_resolver
```

Delete the `_NoOpEventBus` inner class entirely.

- [ ] **Step 5: Run tests**

Run: `cd backend && .venv/bin/python -m pytest tests/gateway/test_capabilities_router.py -v`
Expected: PASS

### Task 1.12: admin_capability_service — invalidate-event skeleton

**Files:**
- Create: `backend/src/services/admin_capability_service.py`
- Create: `backend/tests/services/test_admin_capability_service.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for admin_capability_service invalidate-event publishing."""
from unittest.mock import AsyncMock

import pytest

from src.services.admin_capability_service import AdminCapabilityService


@pytest.mark.asyncio
async def test_publish_invalidate_event_includes_id_and_type():
    bus = AsyncMock()
    service = AdminCapabilityService(db=AsyncMock(), event_bus=bus)
    await service.publish_invalidation("deep_research", "thesis")
    bus.publish.assert_awaited_once_with(
        "capability.invalidated",
        {"id": "deep_research", "workspace_type": "thesis"},
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/services/test_admin_capability_service.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Write the skeleton**

```python
"""Admin service for capability mutations. Full CRUD implemented in Phase 3.

Phase 1 ships only the invalidate-event surface, so Tasks 1.11 and later
can publish from minimal scaffolding without dragging the YAML editor in.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.services.event_bus import EventBus


class AdminCapabilityService:
    def __init__(self, db: AsyncSession, event_bus: EventBus) -> None:
        self.db = db
        self.event_bus = event_bus

    async def publish_invalidation(self, capability_id: str, workspace_type: str) -> None:
        await self.event_bus.publish(
            "capability.invalidated",
            {"id": capability_id, "workspace_type": workspace_type},
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/services/test_admin_capability_service.py -v`
Expected: PASS

### Task 1.13: Delete `execution-presenters.ts` and its test

**Files:**
- Delete: `frontend/lib/execution-presenters.ts`
- Delete: `frontend/tests/unit/lib/execution-presenters.test.ts`

- [ ] **Step 1: Confirm zero production callers**

Run: `grep -rn "buildExecutionPanelSession\|buildExecutionCurrentTask" frontend --include="*.ts" --include="*.tsx" | grep -v execution-presenters`
Expected: empty (only tests reference these symbols, and we're deleting those too)

- [ ] **Step 2: Delete both files**

Run: `git rm frontend/lib/execution-presenters.ts frontend/tests/unit/lib/execution-presenters.test.ts`

### Task 1.14: Frontend type rename — WorkspaceFeature → Capability

**Files:**
- Modify: `frontend/lib/api/types.ts`

- [ ] **Step 1: Update the type definition**

Find `WorkspaceFeature` interface in [frontend/lib/api/types.ts](../../frontend/lib/api/types.ts) (~line 880). Replace:

```typescript
export interface WorkspaceCapability {
  id: string;
  name: string;
  description: string;
  icon: string;
  color: string | null;
  stages: { id: string; label: string }[];
  followUpPrompt: string | null;
}

export type WorkspaceFeature = WorkspaceCapability;
```

Keeping `WorkspaceFeature` as a type alias for one release lets us delete imports in callers one-by-one without breaking compilation. Final removal happens at Task 1.16.

- [ ] **Step 2: Run typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS

- [ ] **Step 3: Commit (deferred)**

Commit with Task 1.16.

### Task 1.15: Migrate 5 frontend production files

**Files:**
- Modify: `frontend/app/(workbench)/workspaces/[id]/page.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/LiveWorkflowPanel.tsx`
- Modify: `frontend/stores/features.ts`
- Modify: `frontend/lib/workspace-thread-entry.ts`
- Modify: `frontend/lib/api/workspace.ts`

- [ ] **Step 1: Update `frontend/stores/features.ts`**

Replace `WorkspaceFeature` imports with `WorkspaceCapability`. Replace `agent`/`agentLabel`/`panel` field reads (if any) with removals — these fields are gone. Update store names from `features` → `capabilities` only where natural (variable rename can ride along but is not mandatory; do NOT rewrite store API contract since other components consume `features` array name).

For each occurrence of `feature.agent`, `feature.agentLabel`, `feature.panel`, delete that read — the rendering logic that depended on it was dead anyway.

- [ ] **Step 2: Update `frontend/app/(workbench)/workspaces/[id]/page.tsx`**

Line 16 import: `WorkspaceFeature` → `WorkspaceCapability`.
Line 39 state typing: `useState<WorkspaceFeature[]>` → `useState<WorkspaceCapability[]>`.
Line 57 `.map((c) => ({...}))`: the mapping currently constructs WorkspaceFeature shape from `data.items` (which is the capabilities API response). Update the map to construct WorkspaceCapability:

```typescript
const mapped: WorkspaceCapability[] = (data.items ?? []).map((c: any) => ({
  id: c.id,
  name: c.display_name,
  description: c.description,
  icon: c.ui_meta?.icon ?? "circle",
  color: c.ui_meta?.color ?? null,
  stages: c.ui_meta?.stages ?? [],
  followUpPrompt: c.ui_meta?.follow_up_prompt ?? null,
}));
```

Line 66 (initial state with `agentLabel: ""` and similar dead fields): delete those entries.

- [ ] **Step 3: Update `LiveWorkflowPanel.tsx`**

Replace `WorkspaceFeature` type with `WorkspaceCapability`. Remove any prop accesses to `agent` / `agentLabel` / `panel` — they no longer exist on the type.

- [ ] **Step 4: Update `workspace-thread-entry.ts`**

Line 88 type alias `Pick<WorkspaceFeature, "name" | "description">` → `Pick<WorkspaceCapability, "name" | "description">`.

- [ ] **Step 5: Update `frontend/lib/api/workspace.ts`**

Line 365 (or wherever `getWorkspaceFeatures` was defined and exported): the function should already have been deleted in Task 1.10 step 3. If any leftover `WorkspaceFeature` references remain in type annotations, update them.

- [ ] **Step 6: Run typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS

- [ ] **Step 7: Run frontend unit tests**

Run: `cd frontend && npx vitest run`
Expected: PASS

### Task 1.16: Remove `WorkspaceFeature` alias + final imports cleanup

**Files:**
- Modify: `frontend/lib/api/types.ts`

- [ ] **Step 1: Delete the alias**

Remove the line `export type WorkspaceFeature = WorkspaceCapability;` from `frontend/lib/api/types.ts`.

- [ ] **Step 2: Confirm zero remaining usages**

Run: `grep -rn "WorkspaceFeature" frontend --include="*.ts" --include="*.tsx" | grep -v node_modules`
Expected: empty

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS

- [ ] **Step 4: Commit Phase 1 frontend changes**

```bash
git add frontend/
git commit -m "refactor(frontend): rename WorkspaceFeature → WorkspaceCapability, drop dead fields"
```

### Task 1.17: Delete legacy product docs

**Files:**
- Delete: `docs/product/workspace-feature-catalog.md`
- Delete: `docs/product/frontend-feature-plugin-contract.md`

- [ ] **Step 1: Delete the docs**

Run: `git rm -f docs/product/workspace-feature-catalog.md docs/product/frontend-feature-plugin-contract.md 2>/dev/null || true`

(If the files are already gone from the working tree per git status, this is a no-op.)

- [ ] **Step 2: Commit dead code cleanup**

```bash
git add backend/src/workspace_features backend/src/agents/feature_leader backend/src/agents/graphs
git rm -r backend/src/workspace_features backend/src/agents/feature_leader backend/src/agents/graphs 2>/dev/null || true
git add backend/src/agents/chat_agent/agent.py backend/src/agents/chat_agent/tools/list_capabilities.py
git add backend/src/gateway/routers/workspaces.py backend/src/gateway/routers/workspaces_contracts.py
git add backend/src/gateway/routers/capabilities.py
git add backend/src/services/admin_capability_service.py
git add backend/tests/services/test_admin_capability_service.py
git add docs/product/
git commit -m "refactor: delete workspace_features / feature_leader / agents.graphs dead code"
```

### Task 1.18: End-to-end validation

**Files:** none

- [ ] **Step 1: Run full backend test suite**

Run: `cd backend && .venv/bin/python -m pytest tests/ -v --tb=short`
Expected: PASS. If anything still references deleted modules, fix in-line.

- [ ] **Step 2: Run frontend unit tests**

Run: `cd frontend && npx vitest run`
Expected: PASS

- [ ] **Step 3: Run frontend typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS

- [ ] **Step 4: Verify EventBus pub/sub across processes**

Manual test:
1. In one terminal: `cd backend && .venv/bin/python -c "import asyncio; from src.academic.cache.redis_client import redis_client; from src.services.event_bus import EventBus; async def main(): await redis_client.connect(); bus = EventBus(redis_client.client); async def handler(e): print('GOT', e); bus.subscribe('capability.invalidated', handler); await asyncio.sleep(60); asyncio.run(main())"`
2. In another terminal: `cd backend && .venv/bin/python -c "import asyncio; from src.academic.cache.redis_client import redis_client; from src.services.event_bus import EventBus; async def main(): await redis_client.connect(); bus = EventBus(redis_client.client); await bus.publish('capability.invalidated', {'id': 'test', 'workspace_type': 'thesis'}); asyncio.run(main())"`
3. Expected: terminal 1 prints `GOT {'id': 'test', 'workspace_type': 'thesis'}` within 1-2 seconds.

If pub/sub doesn't work, the spec's risk #1 has materialized — investigate Redis connectivity / channel naming before Phase 3.

- [ ] **Step 5: Run e2e golden path**

Run: `cd frontend && npx playwright test tests/e2e/golden-path.spec.ts`
Expected: PASS (user can send a message and receive a response without errors)

- [ ] **Step 6: Final P1 commit**

If anything was missed in earlier commits:

```bash
git status
# Review remaining changes; commit them with a meaningful message.
```

---

## Phase 2 — Admin IA Migration

**Goal:** Wrap the existing admin functionality in a sidebar layout with sub-routes. No new business features — pure structural reorganization of [frontend/app/dashboard/admin/page.tsx](../../frontend/app/dashboard/admin/page.tsx) (1869 lines) into 7 focused pages.

**Pre-conditions:** Phase 1 merged. The existing single page is the reference; do not break behavior during migration.

### Task 2.1: Admin layout shell

**Files:**
- Create: `frontend/app/dashboard/admin/layout.tsx`
- Create: `frontend/app/dashboard/admin/hooks/use-admin-auth.ts`

- [ ] **Step 1: Write the auth hook**

```typescript
"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/stores/auth";

export function useAdminAuth() {
  const router = useRouter();
  const { user, isAuthenticated, isLoading } = useAuthStore();

  useEffect(() => {
    if (isLoading) return;
    if (!isAuthenticated) {
      router.push("/login");
      return;
    }
    if (user?.role !== "admin") {
      router.push("/dashboard/me");
    }
  }, [isLoading, isAuthenticated, user?.role, router]);

  return {
    user,
    isAuthenticated,
    isLoading,
    isAdmin: user?.role === "admin",
  };
}
```

- [ ] **Step 2: Write the layout**

```typescript
"use client";

import { Loader2 } from "lucide-react";

import { Header } from "@/components/layout/header";
import { AdminSidebar } from "./components/AdminSidebar";
import { useAdminAuth } from "./hooks/use-admin-auth";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const { isLoading, isAuthenticated, isAdmin } = useAdminAuth();

  if (isLoading) {
    return (
      <main className="min-h-screen flex items-center justify-center bg-[var(--bg-base)]">
        <Loader2 className="w-8 h-8 animate-spin text-[var(--accent-primary)]" />
      </main>
    );
  }

  if (!isAuthenticated || !isAdmin) {
    return null;
  }

  return (
    <div className="min-h-screen bg-[var(--bg-base)]">
      <Header />
      <div className="flex pt-16">
        <AdminSidebar />
        <main className="flex-1 min-w-0 px-4 py-6 lg:px-8">{children}</main>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Commit (sidebar stub follows in 2.2)**

Don't commit yet — AdminSidebar doesn't exist; the layout would fail to import. Continue to Task 2.2.

### Task 2.2: AdminSidebar + AdminPageHeader

**Files:**
- Create: `frontend/app/dashboard/admin/components/AdminSidebar.tsx`
- Create: `frontend/app/dashboard/admin/components/AdminPageHeader.tsx`

- [ ] **Step 1: Write AdminSidebar**

```typescript
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3, ClipboardList, Coins, CreditCard, FolderOpen,
  Layers, LayoutDashboard, ScrollText, Settings, ShieldCheck, Users, Wrench,
} from "lucide-react";

const TOP: Array<{ href: string; label: string; icon: React.ComponentType<{ className?: string }> }> = [
  { href: "/dashboard/admin", label: "概览", icon: LayoutDashboard },
  { href: "/dashboard/admin/users", label: "用户管理", icon: Users },
];

const CREDIT_GROUP = {
  label: "积分中心",
  icon: Coins,
  children: [
    { href: "/dashboard/admin/credits", label: "流水" },
    { href: "/dashboard/admin/credits/rules", label: "发放规则" },
    { href: "/dashboard/admin/credits/redeem-codes", label: "兑换码" },
  ],
};

const BUSINESS: Array<{ href: string; label: string; icon: React.ComponentType<{ className?: string }> }> = [
  { href: "/dashboard/admin/capabilities", label: "Capability", icon: Layers },
  { href: "/dashboard/admin/skills", label: "Skill", icon: Wrench },
  { href: "/dashboard/admin/analytics", label: "数据分析", icon: BarChart3 },
];

const SYSTEM: Array<{ href: string; label: string; icon: React.ComponentType<{ className?: string }> }> = [
  { href: "/dashboard/admin/mcp", label: "MCP 配置", icon: Settings },
  { href: "/dashboard/admin/release-gate", label: "发布门禁", icon: ShieldCheck },
  { href: "/dashboard/admin/logs", label: "操作日志", icon: ScrollText },
];

export function AdminSidebar() {
  const pathname = usePathname() ?? "";

  const isActive = (href: string) => {
    if (href === "/dashboard/admin") return pathname === href;
    return pathname.startsWith(href);
  };

  return (
    <aside className="w-60 shrink-0 border-r border-[var(--border-default)] bg-[var(--bg-surface)] min-h-[calc(100vh-4rem)] hidden lg:block">
      <nav className="flex flex-col gap-1 p-4 text-sm">
        {TOP.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={`flex items-center gap-2 rounded-lg px-3 py-2 transition-colors ${
              isActive(href)
                ? "bg-[var(--accent-primary)]/10 text-[var(--accent-primary)] font-medium"
                : "text-[var(--text-secondary)] hover:bg-[var(--bg-elevated)]"
            }`}
          >
            <Icon className="w-4 h-4" />
            {label}
          </Link>
        ))}

        <div className="mt-2">
          <div className="flex items-center gap-2 px-3 py-2 text-[var(--text-muted)] text-xs uppercase tracking-wide">
            <CREDIT_GROUP.icon className="w-4 h-4" />
            {CREDIT_GROUP.label}
          </div>
          <div className="ml-4 flex flex-col gap-1">
            {CREDIT_GROUP.children.map((child) => (
              <Link
                key={child.href}
                href={child.href}
                className={`rounded-lg px-3 py-1.5 transition-colors ${
                  isActive(child.href)
                    ? "bg-[var(--accent-primary)]/10 text-[var(--accent-primary)] font-medium"
                    : "text-[var(--text-secondary)] hover:bg-[var(--bg-elevated)]"
                }`}
              >
                {child.label}
              </Link>
            ))}
          </div>
        </div>

        {BUSINESS.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={`flex items-center gap-2 rounded-lg px-3 py-2 transition-colors ${
              isActive(href)
                ? "bg-[var(--accent-primary)]/10 text-[var(--accent-primary)] font-medium"
                : "text-[var(--text-secondary)] hover:bg-[var(--bg-elevated)]"
            }`}
          >
            <Icon className="w-4 h-4" />
            {label}
          </Link>
        ))}

        <div className="my-2 border-t border-[var(--border-default)]" />

        {SYSTEM.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={`flex items-center gap-2 rounded-lg px-3 py-2 transition-colors ${
              isActive(href)
                ? "bg-[var(--accent-primary)]/10 text-[var(--accent-primary)] font-medium"
                : "text-[var(--text-secondary)] hover:bg-[var(--bg-elevated)]"
            }`}
          >
            <Icon className="w-4 h-4" />
            {label}
          </Link>
        ))}
      </nav>
    </aside>
  );
}
```

- [ ] **Step 2: Write AdminPageHeader**

```typescript
"use client";

import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";

export function AdminPageHeader({
  title,
  description,
  onRefresh,
  isRefreshing,
  actions,
}: {
  title: string;
  description?: string;
  onRefresh?: () => void;
  isRefreshing?: boolean;
  actions?: React.ReactNode;
}) {
  return (
    <div className="route-card rounded-[1.75rem] p-6 flex flex-col md:flex-row md:items-center md:justify-between gap-3 mb-6">
      <div>
        <h1 className="text-2xl font-bold text-[var(--text-primary)]">{title}</h1>
        {description && (
          <p className="text-[var(--text-secondary)] text-sm mt-1">{description}</p>
        )}
      </div>
      <div className="flex items-center gap-2">
        {actions}
        {onRefresh && (
          <Button variant="outline" size="sm" onClick={onRefresh} disabled={isRefreshing}>
            <RefreshCw className={`w-4 h-4 mr-1 ${isRefreshing ? "animate-spin" : ""}`} />
            刷新
          </Button>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS (layout + sidebar + header all valid; no consumers yet so no broken imports)

- [ ] **Step 4: Commit**

```bash
git add frontend/app/dashboard/admin/layout.tsx frontend/app/dashboard/admin/hooks frontend/app/dashboard/admin/components
git commit -m "feat(admin): layout shell with sidebar + page header"
```

### Task 2.3: Migrate Users page

**Files:**
- Create: `frontend/app/dashboard/admin/users/page.tsx`
- Create: `frontend/app/dashboard/admin/components/CreditAdjustDialog.tsx`
- Read (source): `frontend/app/dashboard/admin/page.tsx:1211-1465`, `1802-1866`

- [ ] **Step 1: Extract CreditAdjustDialog**

Copy lines 1802-1866 (`<Dialog>` + form + `submitCreditDialog`) and lines 506-563 (state + submit handler) from the old [page.tsx](../../frontend/app/dashboard/admin/page.tsx) into a new component:

```typescript
"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { adminDeductCredits, adminGrantCredits, type AdminUserItem } from "@/lib/api";

type Mode = "grant" | "deduct";

interface Props {
  mode: Mode | null;
  user: AdminUserItem | null;
  onClose: (refresh: boolean) => void;
}

function parseErrorMessage(error: unknown, fallback: string): string {
  if (error && typeof error === "object" && "response" in error) {
    const responseData = (error as { response?: { data?: unknown } }).response?.data;
    if (responseData && typeof responseData === "object" && "detail" in responseData) {
      const detail = (responseData as { detail?: unknown }).detail;
      if (typeof detail === "string" && detail.trim()) return detail;
    }
  }
  if (error instanceof Error && error.message.trim()) return error.message;
  return fallback;
}

export function CreditAdjustDialog({ mode, user, onClose }: Props) {
  const [amount, setAmount] = useState("100");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  if (!mode || !user) return null;

  const submit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const value = Number(amount);
    if (!Number.isFinite(value) || !Number.isInteger(value) || value <= 0) {
      setError("积分数量必须是正整数");
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const finalDescription = description.trim() || (mode === "grant" ? "管理员发放积分" : "管理员扣除积分");
      if (mode === "grant") {
        await adminGrantCredits({ user_id: user.id, amount: value, description: finalDescription });
      } else {
        await adminDeductCredits({ user_id: user.id, amount: value, description: finalDescription });
      }
      onClose(true);
    } catch (err) {
      setError(parseErrorMessage(err, "积分操作失败"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose(false); }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{mode === "grant" ? "发放积分" : "扣除积分"}</DialogTitle>
          <DialogDescription>目标用户：{user.email}</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="credit-amount">积分数量（正整数）</Label>
            <Input id="credit-amount" type="number" min={1} step={1} value={amount} onChange={(e) => setAmount(e.target.value)} disabled={loading} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="credit-description">原因说明</Label>
            <Input id="credit-description" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="请输入原因" maxLength={500} disabled={loading} />
          </div>
          {error && <div className="text-sm text-red-600 bg-red-500/10 border border-red-500/20 rounded-lg p-2">{error}</div>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onClose(false)} disabled={loading}>取消</Button>
            <Button type="submit" disabled={loading}>
              {loading && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
              {mode === "grant" ? "确认发放" : "确认扣除"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 2: Write users/page.tsx**

Move lines 1211-1465 of old page.tsx into this new page. Replace inline auth + reload nonce with local state. Wire CreditAdjustDialog from step 1. The structure:

```typescript
"use client";

import { useEffect, useState } from "react";
import { Download, Loader2 } from "lucide-react";

import { AdminPageHeader } from "../components/AdminPageHeader";
import { CreditAdjustDialog } from "../components/CreditAdjustDialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  listAdminUsers, updateAdminUserRole, updateAdminUserStatus,
  type AdminUserItem,
} from "@/lib/api";

// ... (full table + filters + pagination + export CSV)
```

(Use the source page.tsx lines 1211-1465 as a 1:1 port — keep behavior identical. Replace `usersPage` / `usersTotal` etc. as local state. Replace `runUserAction` with a local helper that calls the API then sets `reloadNonce` to force refetch.)

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS

- [ ] **Step 4: Manual smoke test**

Run: `cd frontend && npm run dev` and navigate to `/dashboard/admin/users`. Verify:
- Table loads with users
- Filters work (keyword, role, status)
- Pagination works
- Grant / deduct dialogs open and submit
- CSV export downloads

- [ ] **Step 5: Commit**

```bash
git add frontend/app/dashboard/admin/users frontend/app/dashboard/admin/components/CreditAdjustDialog.tsx
git commit -m "feat(admin): migrate users page to sub-route"
```

### Task 2.4: Migrate Credits ledger page

**Files:**
- Create: `frontend/app/dashboard/admin/credits/page.tsx`
- Read (source): `frontend/app/dashboard/admin/page.tsx:1467-1638`

- [ ] **Step 1: Port the credit ledger section**

Move lines 1467-1638 verbatim into `credits/page.tsx`. State management is local (page, pageSize, typeFilter, userIdFilter). Use AdminPageHeader. Export CSV button unchanged.

- [ ] **Step 2: Typecheck + manual smoke test**

Run: `cd frontend && npm run typecheck`
Manual test: navigate to `/dashboard/admin/credits`, verify ledger loads, filter by type/user, export CSV.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/dashboard/admin/credits/page.tsx
git commit -m "feat(admin): migrate credits ledger page to sub-route"
```

### Task 2.5: Migrate MCP config page

**Files:**
- Create: `frontend/app/dashboard/admin/mcp/page.tsx`
- Read (source): `frontend/app/dashboard/admin/page.tsx:1043-1209`

- [ ] **Step 1: Port the MCP section**

Move the MCP block (`mcpDraft`, `mcpDraftBaseline`, `mcpServerEntries`, `formatMcpDraft`, `restoreMcpDraft`, `saveMcpDraft` + JSX) into `mcp/page.tsx`. Use AdminPageHeader.

- [ ] **Step 2: Typecheck + smoke test**

Manual: navigate to `/dashboard/admin/mcp`, verify JSON loads, edit + save round-trip works.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/dashboard/admin/mcp
git commit -m "feat(admin): migrate MCP config page to sub-route"
```

### Task 2.6: Migrate Release Gate page

**Files:**
- Create: `frontend/app/dashboard/admin/release-gate/page.tsx`
- Read (source): `frontend/app/dashboard/admin/page.tsx:786-1041`

- [ ] **Step 1: Port the release gate section**

Move the release gate block (`releaseGateReport`, `runReleaseGate`, `exportReleaseGateJSON`, `coreChecks`, `extendedChecks`, JSX) into `release-gate/page.tsx`. Use AdminPageHeader.

- [ ] **Step 2: Smoke test**

Manual: navigate to `/dashboard/admin/release-gate`, run core gate, verify report renders.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/dashboard/admin/release-gate
git commit -m "feat(admin): migrate release gate page to sub-route"
```

### Task 2.7: Migrate Logs page

**Files:**
- Create: `frontend/app/dashboard/admin/logs/page.tsx`
- Read (source): `frontend/app/dashboard/admin/page.tsx:1640-1799`

- [ ] **Step 1: Port admin logs section**

Move the logs block (`adminLogs`, `logTargetUserIdInput`, filter form, table, pagination) into `logs/page.tsx`.

- [ ] **Step 2: Smoke test + commit**

Manual: navigate to `/dashboard/admin/logs`, filter by action / target user, export CSV.

```bash
git add frontend/app/dashboard/admin/logs
git commit -m "feat(admin): migrate operation logs page to sub-route"
```

### Task 2.8: Replace overview page with slim version

**Files:**
- Modify: `frontend/app/dashboard/admin/page.tsx`

- [ ] **Step 1: Replace the 1869-line file**

Overwrite [frontend/app/dashboard/admin/page.tsx](../../frontend/app/dashboard/admin/page.tsx) with a focused overview page:

```typescript
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { BarChart3, Coins, CreditCard, FolderOpen, Gauge, TriangleAlert, Users } from "lucide-react";

import { AdminPageHeader } from "./components/AdminPageHeader";
import { getAdminDashboard, type AdminDashboardData } from "@/lib/api";

function parseErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim()) return error.message;
  return fallback;
}

export default function AdminOverviewPage() {
  const [dashboard, setDashboard] = useState<AdminDashboardData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadNonce, setReloadNonce] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);
    getAdminDashboard()
      .then((data) => { if (!cancelled) setDashboard(data); })
      .catch((err) => { if (!cancelled) setError(parseErrorMessage(err, "加载概览失败")); })
      .finally(() => { if (!cancelled) setIsLoading(false); });
    return () => { cancelled = true; };
  }, [reloadNonce]);

  const overdraftUsers = dashboard?.summary.credits.overdraft_users ?? 0;
  const hasOverdraft = overdraftUsers > 0;
  const tokenUsage = dashboard?.summary.token_usage;

  return (
    <>
      <AdminPageHeader
        title="管理总览"
        description="用户、任务、积分与系统配置的运行概览。"
        onRefresh={() => setReloadNonce((v) => v + 1)}
        isRefreshing={isLoading}
      />

      {error && (
        <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-600 flex items-center gap-2 mb-4">
          <TriangleAlert className="w-4 h-4" />
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 mb-6">
        <SummaryCard
          icon={<Users className="w-5 h-5 text-[var(--accent-primary)]" />}
          label="总用户数"
          value={dashboard?.summary.users.total ?? 0}
          hint={`活跃 ${dashboard?.summary.users.active ?? 0} / 管理员 ${dashboard?.summary.users.admins ?? 0}`}
        />
        <SummaryCard
          icon={<FolderOpen className="w-5 h-5 text-[var(--accent-primary)]" />}
          label="工作空间"
          value={dashboard?.summary.workspaces.total ?? 0}
          hint={`任务运行中 ${dashboard?.summary.tasks.running ?? 0}`}
        />
        <SummaryCard
          icon={<CreditCard className="w-5 h-5 text-[var(--accent-primary)]" />}
          label="积分余额池"
          value={dashboard?.summary.credits.in_circulation ?? 0}
          hint={`发放 ${dashboard?.summary.credits.total_issued ?? 0} / 消费 ${dashboard?.summary.credits.total_spent ?? 0}`}
          variant={hasOverdraft ? "danger" : "default"}
        />
        <SummaryCard
          icon={<TriangleAlert className="w-5 h-5 text-[var(--accent-primary)]" />}
          label="透支用户"
          value={overdraftUsers}
          hint={`累计透支 ${dashboard?.summary.credits.overdraft_credits_total ?? 0} 积分`}
          variant={hasOverdraft ? "danger" : "default"}
        />
        <SummaryCard
          icon={<TriangleAlert className="w-5 h-5 text-[var(--accent-primary)]" />}
          label="24h 失败任务"
          value={dashboard?.summary.tasks.failed_last_24h ?? 0}
          hint={`全量任务 ${dashboard?.summary.tasks.total ?? 0}`}
        />
        <SummaryCard
          icon={<Gauge className="w-5 h-5 text-[var(--accent-primary)]" />}
          label="Token 用量"
          value={tokenUsage?.thread.total_tokens ?? 0}
          hint="thread tokens（累计）"
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <AnalyticsEntryCard href="/dashboard/admin/analytics#user-growth" title="用户增长 / 活跃" icon={<Users className="w-5 h-5" />} />
        <AnalyticsEntryCard href="/dashboard/admin/analytics#capability-usage" title="Capability 热点" icon={<BarChart3 className="w-5 h-5" />} />
        <AnalyticsEntryCard href="/dashboard/admin/analytics#credits-tokens" title="积分 / Token 趋势" icon={<Coins className="w-5 h-5" />} />
        <AnalyticsEntryCard href="/dashboard/admin/analytics#workspaces-tasks" title="Workspace / 任务" icon={<FolderOpen className="w-5 h-5" />} />
      </div>
    </>
  );
}

function SummaryCard({
  icon, label, value, hint, variant = "default",
}: { icon: React.ReactNode; label: string; value: number; hint: string; variant?: "default" | "danger" }) {
  const isDanger = variant === "danger";
  return (
    <div className={`rounded-2xl border p-5 ${isDanger ? "border-rose-500/30 bg-rose-500/10" : "route-card"}`}>
      <div className="flex items-center justify-between">
        <span className="text-sm text-[var(--text-secondary)]">{label}</span>
        {icon}
      </div>
      <div className={`mt-3 text-3xl font-bold ${isDanger ? "text-rose-600" : "text-[var(--text-primary)]"}`}>
        {value.toLocaleString()}
      </div>
      <div className="mt-1 text-xs text-[var(--text-muted)]">{hint}</div>
    </div>
  );
}

function AnalyticsEntryCard({ href, title, icon }: { href: string; title: string; icon: React.ReactNode }) {
  return (
    <Link href={href} className="route-card rounded-2xl p-5 flex items-center gap-3 hover:bg-[var(--bg-elevated)] transition-colors">
      <div className="text-[var(--accent-primary)]">{icon}</div>
      <div className="text-sm font-medium text-[var(--text-primary)]">{title}</div>
    </Link>
  );
}
```

- [ ] **Step 2: Smoke test**

Run dev server, navigate to `/dashboard/admin` — confirm overview renders, refresh works, all 4 analytics entry cards link correctly (analytics page itself doesn't exist yet; they'll 404 until P5 ships — that's fine).

- [ ] **Step 3: Commit**

```bash
git add frontend/app/dashboard/admin/page.tsx
git commit -m "feat(admin): slim overview page; remove 1700-line monolith"
```

### Task 2.9: e2e route smoke test

**Files:**
- Create: `frontend/tests/e2e/admin-routes.spec.ts`

- [ ] **Step 1: Write the e2e test**

```typescript
import { test, expect } from "@playwright/test";

test.describe("admin routes", () => {
  test("sidebar navigates between admin pages", async ({ page, baseURL }) => {
    await page.goto(`${baseURL}/login`);
    await page.fill('input[name="email"]', process.env.ADMIN_EMAIL!);
    await page.fill('input[name="password"]', process.env.ADMIN_PASSWORD!);
    await page.click('button[type="submit"]');
    await page.waitForURL(/dashboard/);

    await page.goto(`${baseURL}/dashboard/admin`);
    await expect(page.locator("h1")).toContainText("管理总览");

    await page.click('a[href="/dashboard/admin/users"]');
    await expect(page).toHaveURL(/admin\/users/);
    await expect(page.locator("h1")).toContainText("用户管理");

    await page.click('a[href="/dashboard/admin/credits"]');
    await expect(page).toHaveURL(/admin\/credits$/);

    await page.click('a[href="/dashboard/admin/mcp"]');
    await expect(page).toHaveURL(/admin\/mcp/);

    await page.click('a[href="/dashboard/admin/release-gate"]');
    await expect(page).toHaveURL(/admin\/release-gate/);

    await page.click('a[href="/dashboard/admin/logs"]');
    await expect(page).toHaveURL(/admin\/logs/);
  });
});
```

- [ ] **Step 2: Run e2e**

Run: `cd frontend && ADMIN_EMAIL=... ADMIN_PASSWORD=... npx playwright test tests/e2e/admin-routes.spec.ts`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/tests/e2e/admin-routes.spec.ts
git commit -m "test(admin): e2e route smoke test for sidebar navigation"
```

---

## Phase 3 — Capability / Skill Management

**Goal:** Admin can list/create/edit/delete/toggle capabilities and skills via YAML editor with live syntax + Pydantic schema validation + cross-ref validation. Save triggers EventBus invalidation. Every mutation writes an AdminLog. Import-from-seed and export-to-zip endpoints provide DB ↔ seed YAML sync.

**Pre-conditions:** Phases 1 and 2 merged. The real EventBus is wired in gateway.

### Task 3.1: Pydantic schema models

**Files:**
- Create: `backend/src/services/capability_schema.py`
- Create: `backend/tests/services/test_capability_schema.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for capability/skill YAML schema validation."""

import pytest
from pydantic import ValidationError

from src.services.capability_schema import (
    CapabilityYamlModel,
    CapabilitySkillYamlModel,
    UIMetaModel,
)


class TestUIMeta:
    def test_minimal_valid(self):
        m = UIMetaModel(icon="search", color="purple")
        assert m.order == 0
        assert m.stages == []
        assert m.follow_up_prompt is None

    def test_with_stages(self):
        m = UIMetaModel(
            icon="search", color="purple",
            stages=[{"id": "s1", "label": "step 1"}],
        )
        assert len(m.stages) == 1
        assert m.stages[0].id == "s1"


class TestCapabilityYaml:
    def test_minimal_valid(self):
        m = CapabilityYamlModel(
            id="test_cap",
            workspace_type="thesis",
            display_name="Test",
            intent_description="test",
            brief_schema={"type": "object"},
            graph_template={"phases": []},
            ui_meta={"icon": "search", "color": "purple"},
        )
        assert m.enabled is True
        assert m.trigger_phrases == []

    def test_missing_required_field_fails(self):
        with pytest.raises(ValidationError):
            CapabilityYamlModel(
                id="x", workspace_type="thesis", display_name="X",
                intent_description="x", brief_schema={}, graph_template={},
                # ui_meta missing
            )

    def test_required_decision_type_validated(self):
        with pytest.raises(ValidationError):
            CapabilityYamlModel(
                id="x", workspace_type="thesis", display_name="X",
                intent_description="x", brief_schema={}, graph_template={},
                ui_meta={"icon": "x", "color": "x"},
                required_decisions=[{"key": "k", "ask": "?", "type": "object"}],  # invalid
            )


class TestCapabilitySkillYaml:
    def test_minimal_valid(self):
        m = CapabilitySkillYamlModel(
            id="test-skill",
            display_name="Test Skill",
            subagent_type="react",
        )
        assert m.enabled is True
        assert m.prompt == ""
        assert m.allowed_tools == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/services/test_capability_schema.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Write the Pydantic models**

```python
"""Pydantic schema models for capability / capability_skill YAMLs.

These models drive admin save-time validation. Cross-reference checks (skill_id
existence, subagent_type in registry) live in the service layer because they
require DB / registry lookups; this module is pure data validation.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class UIMetaStage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    label: str


class UIMetaModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    icon: str
    color: str
    order: int = 0
    stages: list[UIMetaStage] = Field(default_factory=list)
    follow_up_prompt: str | None = None


class RequiredDecisionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    ask: str
    type: Literal["string", "number", "boolean"]


class GraphTaskOutputModel(BaseModel):
    model_config = ConfigDict(extra="allow")
    kind: str
    iterate_on: str | None = None
    mapping: dict[str, Any] = Field(default_factory=dict)


class GraphTaskModel(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str
    subagent_type: str
    skill_id: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: list[GraphTaskOutputModel] = Field(default_factory=list)


class GraphPhaseModel(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str
    tasks: list[GraphTaskModel]


class GraphTemplateModel(BaseModel):
    model_config = ConfigDict(extra="allow")
    phases: list[GraphPhaseModel]


class CapabilityYamlModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    workspace_type: str
    enabled: bool = True
    display_name: str
    description: str = ""
    intent_description: str
    trigger_phrases: list[str] = Field(default_factory=list)
    required_decisions: list[RequiredDecisionModel] = Field(default_factory=list)
    brief_schema: dict[str, Any]
    graph_template: GraphTemplateModel
    ui_meta: UIMetaModel
    notes: str | None = None


class CapabilitySkillYamlModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    enabled: bool = True
    display_name: str
    description: str = ""
    subagent_type: str
    prompt: str = ""
    allowed_tools: list[str] = Field(default_factory=list)
    resources: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd backend && .venv/bin/python -m pytest tests/services/test_capability_schema.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/services/capability_schema.py backend/tests/services/test_capability_schema.py
git commit -m "feat(schema): Pydantic models for capability/skill YAML"
```

### Task 3.2: Cross-reference validator

**Files:**
- Modify: `backend/src/services/capability_schema.py` (append CrossRefValidator)
- Create: `backend/tests/services/test_cross_ref_validator.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for cross-reference validation across capability + skill + registry."""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.capability_schema import CrossRefValidator, CapabilityYamlModel


def _make_capability_yaml(skill_ids: list[str], subagent_types: list[str]) -> CapabilityYamlModel:
    return CapabilityYamlModel(
        id="x", workspace_type="thesis", display_name="X",
        intent_description="x", brief_schema={}, ui_meta={"icon": "x", "color": "x"},
        graph_template={
            "phases": [
                {
                    "name": "p",
                    "tasks": [
                        {"name": f"t{i}", "subagent_type": st, "skill_id": sid}
                        for i, (st, sid) in enumerate(zip(subagent_types, skill_ids))
                    ],
                }
            ],
        },
    )


@pytest.mark.asyncio
async def test_skill_id_missing_fails(monkeypatch):
    db = AsyncMock(spec=AsyncSession)

    async def fake_existing_skill_ids(_db, _ids):
        return set()  # no skills exist

    monkeypatch.setattr(CrossRefValidator, "_existing_skill_ids", staticmethod(fake_existing_skill_ids))

    monkeypatch.setattr(CrossRefValidator, "_registry_subagent_types", staticmethod(lambda: {"react"}))

    cap = _make_capability_yaml(skill_ids=["literature-reviewer"], subagent_types=["react"])
    errors = await CrossRefValidator(db).validate_capability(cap)
    assert any("literature-reviewer" in e for e in errors)


@pytest.mark.asyncio
async def test_subagent_type_unknown_fails(monkeypatch):
    db = AsyncMock(spec=AsyncSession)

    async def fake_existing(_db, ids):
        return set(ids)

    monkeypatch.setattr(CrossRefValidator, "_existing_skill_ids", staticmethod(fake_existing))
    monkeypatch.setattr(CrossRefValidator, "_registry_subagent_types", staticmethod(lambda: {"react"}))

    cap = _make_capability_yaml(skill_ids=["any-skill"], subagent_types=["nonexistent"])
    errors = await CrossRefValidator(db).validate_capability(cap)
    assert any("nonexistent" in e for e in errors)


@pytest.mark.asyncio
async def test_skill_subagent_type_validated(monkeypatch):
    from src.services.capability_schema import CapabilitySkillYamlModel
    db = AsyncMock(spec=AsyncSession)
    monkeypatch.setattr(CrossRefValidator, "_registry_subagent_types", staticmethod(lambda: {"react"}))

    skill = CapabilitySkillYamlModel(
        id="x", display_name="X", subagent_type="bogus",
    )
    errors = await CrossRefValidator(db).validate_skill(skill)
    assert any("bogus" in e for e in errors)
```

- [ ] **Step 2: Run tests to verify they fail**

Expected: FAIL — `CrossRefValidator` not exported.

- [ ] **Step 3: Append validator to `capability_schema.py`**

```python
class CrossRefValidator:
    """Validates cross-references that require DB / registry lookups.

    Pure-data validation lives in the Pydantic models. This class adds:
    - skill_id references resolve to an existing capability_skill row
    - subagent_type values exist in the v2 subagent registry
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def validate_capability(self, cap: CapabilityYamlModel) -> list[str]:
        errors: list[str] = []

        skill_ids = {
            t.skill_id
            for phase in cap.graph_template.phases
            for t in phase.tasks
            if t.skill_id is not None
        }
        if skill_ids:
            existing = await self._existing_skill_ids(self.db, skill_ids)
            for sid in skill_ids - existing:
                errors.append(f"skill_id '{sid}' not found in capability_skills table")

        subagent_types = {
            t.subagent_type
            for phase in cap.graph_template.phases
            for t in phase.tasks
        }
        registry_types = self._registry_subagent_types()
        for st in subagent_types - registry_types:
            errors.append(f"subagent_type '{st}' not in v2 subagent registry")

        return errors

    async def validate_skill(self, skill: CapabilitySkillYamlModel) -> list[str]:
        errors: list[str] = []
        registry_types = self._registry_subagent_types()
        if skill.subagent_type not in registry_types:
            errors.append(f"subagent_type '{skill.subagent_type}' not in v2 subagent registry")
        return errors

    @staticmethod
    async def _existing_skill_ids(db: AsyncSession, ids: set[str]) -> set[str]:
        from sqlalchemy import select
        from src.database import CapabilitySkill

        result = await db.execute(
            select(CapabilitySkill.id).where(CapabilitySkill.id.in_(ids))
        )
        return {row[0] for row in result.all()}

    @staticmethod
    def _registry_subagent_types() -> set[str]:
        from src.subagents.v2.registry import REGISTRY
        return set(REGISTRY.keys())
```

(If `REGISTRY` isn't named that, replace with the actual registry export — check `backend/src/subagents/v2/registry.py`.)

- [ ] **Step 4: Run tests to verify pass**

Run: `cd backend && .venv/bin/python -m pytest tests/services/test_cross_ref_validator.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/services/capability_schema.py backend/tests/services/test_cross_ref_validator.py
git commit -m "feat(schema): cross-reference validator for skill_id + subagent_type"
```

### Task 3.3: AdminCapabilityService — full CRUD

**Files:**
- Modify: `backend/src/services/admin_capability_service.py`
- Create: `backend/tests/services/test_admin_capability_service_crud.py`

- [ ] **Step 1: Write failing test for `create`**

```python
"""Tests for AdminCapabilityService CRUD operations."""

from unittest.mock import AsyncMock

import pytest

from src.services.admin_capability_service import AdminCapabilityService

SAMPLE_YAML = """
id: test_cap
workspace_type: thesis
display_name: 测试能力
intent_description: 测试用
brief_schema:
  type: object
graph_template:
  phases:
    - name: phase1
      tasks:
        - name: t1
          subagent_type: react
ui_meta:
  icon: search
  color: purple
"""


@pytest.mark.asyncio
async def test_create_persists_capability(real_async_db):
    bus = AsyncMock()
    service = AdminCapabilityService(db=real_async_db, event_bus=bus)
    cap = await service.create(yaml_text=SAMPLE_YAML, admin_id="admin-uuid")
    assert cap.id == "test_cap"
    assert cap.workspace_type == "thesis"
    assert cap.ui_meta["icon"] == "search"
    bus.publish.assert_awaited_once_with(
        "capability.invalidated",
        {"id": "test_cap", "workspace_type": "thesis"},
    )


@pytest.mark.asyncio
async def test_create_with_invalid_yaml_raises(real_async_db):
    bus = AsyncMock()
    service = AdminCapabilityService(db=real_async_db, event_bus=bus)
    with pytest.raises(ValueError, match="yaml"):
        await service.create(yaml_text="!!!not yaml{{{", admin_id="admin-uuid")
    bus.publish.assert_not_called()


@pytest.mark.asyncio
async def test_update_writes_admin_log_with_diff(real_async_db, seed_capability):
    bus = AsyncMock()
    service = AdminCapabilityService(db=real_async_db, event_bus=bus)
    updated_yaml = SAMPLE_YAML.replace("测试能力", "更新后的名字")
    await service.update(
        capability_id=seed_capability.id,
        workspace_type=seed_capability.workspace_type,
        yaml_text=updated_yaml,
        admin_id="admin-uuid",
    )

    from sqlalchemy import select
    from src.database import AdminLog
    result = await real_async_db.execute(
        select(AdminLog).where(AdminLog.action == "capability_update").order_by(AdminLog.created_at.desc())
    )
    log = result.scalars().first()
    assert log is not None
    assert log.details["capability_id"] == seed_capability.id
    assert "yaml_before_sha256" in log.details
    assert "yaml_after_sha256" in log.details
    assert log.details["yaml_before_sha256"] != log.details["yaml_after_sha256"]


@pytest.mark.asyncio
async def test_delete_publishes_invalidation(real_async_db, seed_capability):
    bus = AsyncMock()
    service = AdminCapabilityService(db=real_async_db, event_bus=bus)
    await service.delete(
        capability_id=seed_capability.id,
        workspace_type=seed_capability.workspace_type,
        admin_id="admin-uuid",
    )
    bus.publish.assert_awaited_once_with(
        "capability.invalidated",
        {"id": seed_capability.id, "workspace_type": seed_capability.workspace_type},
    )


@pytest.mark.asyncio
async def test_validate_returns_errors_without_writing(real_async_db):
    bus = AsyncMock()
    service = AdminCapabilityService(db=real_async_db, event_bus=bus)
    bad_yaml = SAMPLE_YAML.replace("subagent_type: react", "subagent_type: nonexistent")
    errors = await service.validate(yaml_text=bad_yaml)
    assert any("nonexistent" in e for e in errors)
    bus.publish.assert_not_called()
```

(Define `real_async_db` and `seed_capability` fixtures in `backend/tests/services/conftest.py` if they don't exist — see [backend/tests/conftest.py](../../backend/tests/conftest.py) for patterns.)

- [ ] **Step 2: Run to verify FAIL**

Run: `cd backend && .venv/bin/python -m pytest tests/services/test_admin_capability_service_crud.py -v`
Expected: FAIL — methods don't exist on AdminCapabilityService.

- [ ] **Step 3: Implement full service**

Replace `backend/src/services/admin_capability_service.py` with the full implementation:

```python
"""Admin service for capability mutations.

Owns: list / get / create / update / delete / toggle / validate.
Publishes capability.invalidated EventBus events.
Writes AdminLog audit entries with sha256 + diff_fields.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from typing import Any

import yaml
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import AdminLog, Capability
from src.services.capability_schema import CapabilityYamlModel, CrossRefValidator
from src.services.event_bus import EventBus

logger = logging.getLogger(__name__)

INVALIDATE_CHANNEL = "capability.invalidated"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _diff_fields(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    changed: list[str] = []
    for key in set(before) | set(after):
        if before.get(key) != after.get(key):
            changed.append(key)
    return sorted(changed)


def _yaml_to_orm_kwargs(model: CapabilityYamlModel) -> dict[str, Any]:
    return {
        "id": model.id,
        "workspace_type": model.workspace_type,
        "enabled": model.enabled,
        "display_name": model.display_name,
        "description": model.description,
        "intent_description": model.intent_description,
        "trigger_phrases": list(model.trigger_phrases),
        "required_decisions": [d.model_dump() for d in model.required_decisions],
        "brief_schema": model.brief_schema,
        "graph_template": model.graph_template.model_dump(),
        "ui_meta": model.ui_meta.model_dump(),
        "notes": model.notes,
    }


def _orm_to_yaml_dict(cap: Capability) -> dict[str, Any]:
    return {
        "id": cap.id,
        "workspace_type": cap.workspace_type,
        "enabled": cap.enabled,
        "display_name": cap.display_name,
        "description": cap.description,
        "intent_description": cap.intent_description,
        "trigger_phrases": cap.trigger_phrases,
        "required_decisions": cap.required_decisions,
        "brief_schema": cap.brief_schema,
        "graph_template": cap.graph_template,
        "ui_meta": cap.ui_meta,
        "notes": cap.notes,
    }


class AdminCapabilityService:
    def __init__(self, db: AsyncSession, event_bus: EventBus) -> None:
        self.db = db
        self.event_bus = event_bus
        self.validator = CrossRefValidator(db)

    async def list_all(self) -> list[Capability]:
        result = await self.db.execute(
            select(Capability).order_by(Capability.workspace_type, Capability.id)
        )
        return list(result.scalars().all())

    async def get(self, capability_id: str, workspace_type: str) -> Capability | None:
        result = await self.db.execute(
            select(Capability).where(
                Capability.id == capability_id,
                Capability.workspace_type == workspace_type,
            )
        )
        return result.scalars().first()

    async def validate(self, yaml_text: str) -> list[str]:
        try:
            data = yaml.safe_load(yaml_text)
        except yaml.YAMLError as e:
            return [f"yaml parse error: {e}"]
        try:
            model = CapabilityYamlModel(**data)
        except ValidationError as e:
            return [f"schema: {err['loc']}: {err['msg']}" for err in e.errors()]
        return await self.validator.validate_capability(model)

    async def create(self, yaml_text: str, admin_id: str) -> Capability:
        try:
            data = yaml.safe_load(yaml_text)
        except yaml.YAMLError as e:
            raise ValueError(f"yaml parse error: {e}") from e
        try:
            model = CapabilityYamlModel(**data)
        except ValidationError as e:
            raise ValueError(f"schema validation failed: {e.errors()}") from e
        errors = await self.validator.validate_capability(model)
        if errors:
            raise ValueError(f"cross-ref validation failed: {errors}")

        existing = await self.get(model.id, model.workspace_type)
        if existing is not None:
            raise ValueError(f"capability {model.id} for {model.workspace_type} already exists")

        cap = Capability(**_yaml_to_orm_kwargs(model))
        self.db.add(cap)

        self.db.add(
            AdminLog(
                action="capability_create",
                admin_id=admin_id,
                target_user_id=None,
                details={
                    "capability_id": model.id,
                    "workspace_type": model.workspace_type,
                    "yaml_after_sha256": _sha256(yaml_text),
                },
            )
        )
        await self.db.commit()
        await self.event_bus.publish(
            INVALIDATE_CHANNEL,
            {"id": model.id, "workspace_type": model.workspace_type},
        )
        return cap

    async def update(
        self, capability_id: str, workspace_type: str, yaml_text: str, admin_id: str
    ) -> Capability:
        try:
            data = yaml.safe_load(yaml_text)
        except yaml.YAMLError as e:
            raise ValueError(f"yaml parse error: {e}") from e
        try:
            model = CapabilityYamlModel(**data)
        except ValidationError as e:
            raise ValueError(f"schema validation failed: {e.errors()}") from e
        if model.id != capability_id or model.workspace_type != workspace_type:
            raise ValueError("yaml id/workspace_type must match URL path")
        errors = await self.validator.validate_capability(model)
        if errors:
            raise ValueError(f"cross-ref validation failed: {errors}")

        cap = await self.get(capability_id, workspace_type)
        if cap is None:
            raise ValueError(f"capability {capability_id} not found")

        before_dict = _orm_to_yaml_dict(cap)
        before_yaml = yaml.safe_dump(before_dict, sort_keys=False, allow_unicode=True)
        after_kwargs = _yaml_to_orm_kwargs(model)
        for k, v in after_kwargs.items():
            if k in ("id", "workspace_type"):
                continue
            setattr(cap, k, v)

        self.db.add(
            AdminLog(
                action="capability_update",
                admin_id=admin_id,
                target_user_id=None,
                details={
                    "capability_id": model.id,
                    "workspace_type": model.workspace_type,
                    "yaml_before_sha256": _sha256(before_yaml),
                    "yaml_after_sha256": _sha256(yaml_text),
                    "diff_fields": _diff_fields(before_dict, _orm_to_yaml_dict(cap)),
                },
            )
        )
        await self.db.commit()
        await self.event_bus.publish(
            INVALIDATE_CHANNEL,
            {"id": model.id, "workspace_type": model.workspace_type},
        )
        return cap

    async def delete(self, capability_id: str, workspace_type: str, admin_id: str) -> None:
        cap = await self.get(capability_id, workspace_type)
        if cap is None:
            raise ValueError("not found")
        before_yaml = yaml.safe_dump(_orm_to_yaml_dict(cap), sort_keys=False, allow_unicode=True)
        await self.db.delete(cap)
        self.db.add(
            AdminLog(
                action="capability_delete",
                admin_id=admin_id,
                target_user_id=None,
                details={
                    "capability_id": capability_id,
                    "workspace_type": workspace_type,
                    "yaml_before_sha256": _sha256(before_yaml),
                },
            )
        )
        await self.db.commit()
        await self.event_bus.publish(
            INVALIDATE_CHANNEL,
            {"id": capability_id, "workspace_type": workspace_type},
        )

    async def toggle(self, capability_id: str, workspace_type: str, admin_id: str) -> Capability:
        cap = await self.get(capability_id, workspace_type)
        if cap is None:
            raise ValueError("not found")
        previous = cap.enabled
        cap.enabled = not previous
        self.db.add(
            AdminLog(
                action="capability_toggle",
                admin_id=admin_id,
                target_user_id=None,
                details={
                    "capability_id": capability_id,
                    "workspace_type": workspace_type,
                    "enabled_before": previous,
                    "enabled_after": cap.enabled,
                },
            )
        )
        await self.db.commit()
        await self.event_bus.publish(
            INVALIDATE_CHANNEL,
            {"id": capability_id, "workspace_type": workspace_type},
        )
        return cap

    async def publish_invalidation(self, capability_id: str, workspace_type: str) -> None:
        await self.event_bus.publish(
            INVALIDATE_CHANNEL,
            {"id": capability_id, "workspace_type": workspace_type},
        )

    def to_yaml_text(self, cap: Capability) -> str:
        return yaml.safe_dump(_orm_to_yaml_dict(cap), sort_keys=False, allow_unicode=True)
```

- [ ] **Step 4: Run tests to verify PASS**

Run: `cd backend && .venv/bin/python -m pytest tests/services/test_admin_capability_service_crud.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/services/admin_capability_service.py backend/tests/services/test_admin_capability_service_crud.py
git commit -m "feat(admin): AdminCapabilityService full CRUD + AdminLog + EventBus"
```

### Task 3.4: AdminSkillService

**Files:**
- Create: `backend/src/services/admin_skill_service.py`
- Create: `backend/tests/services/test_admin_skill_service.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for AdminSkillService CRUD."""
import pytest

from src.services.admin_skill_service import AdminSkillService

SAMPLE_SKILL_YAML = """
id: test-skill
display_name: Test Skill
description: Test
subagent_type: react
prompt: |
  You are a test agent.
allowed_tools: []
resources: []
config: {}
"""


@pytest.mark.asyncio
async def test_create_skill_persists(real_async_db):
    service = AdminSkillService(db=real_async_db)
    skill = await service.create(yaml_text=SAMPLE_SKILL_YAML, admin_id="admin-uuid")
    assert skill.id == "test-skill"
    assert skill.subagent_type == "react"


@pytest.mark.asyncio
async def test_invalid_subagent_type_fails(real_async_db):
    service = AdminSkillService(db=real_async_db)
    bad = SAMPLE_SKILL_YAML.replace("subagent_type: react", "subagent_type: bogus_type")
    with pytest.raises(ValueError, match="bogus_type"):
        await service.create(yaml_text=bad, admin_id="admin-uuid")
```

- [ ] **Step 2: Write the service**

```python
"""Admin service for capability_skill mutations.

No EventBus channel because CapabilitySkill has no resolver cache today.
Reintroduce subscription when a skill cache is added.
"""

from __future__ import annotations

import hashlib
from typing import Any

import yaml
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import AdminLog, CapabilitySkill
from src.services.capability_schema import CapabilitySkillYamlModel, CrossRefValidator


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _yaml_to_orm(model: CapabilitySkillYamlModel) -> dict[str, Any]:
    return {
        "id": model.id,
        "enabled": model.enabled,
        "display_name": model.display_name,
        "description": model.description,
        "subagent_type": model.subagent_type,
        "prompt": model.prompt,
        "allowed_tools": list(model.allowed_tools),
        "resources": list(model.resources),
        "config": dict(model.config),
    }


def _orm_to_yaml_dict(skill: CapabilitySkill) -> dict[str, Any]:
    return {
        "id": skill.id, "enabled": skill.enabled, "display_name": skill.display_name,
        "description": skill.description, "subagent_type": skill.subagent_type,
        "prompt": skill.prompt, "allowed_tools": skill.allowed_tools,
        "resources": skill.resources, "config": skill.config,
    }


class AdminSkillService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.validator = CrossRefValidator(db)

    async def list_all(self) -> list[CapabilitySkill]:
        result = await self.db.execute(select(CapabilitySkill).order_by(CapabilitySkill.id))
        return list(result.scalars().all())

    async def get(self, skill_id: str) -> CapabilitySkill | None:
        result = await self.db.execute(
            select(CapabilitySkill).where(CapabilitySkill.id == skill_id)
        )
        return result.scalars().first()

    async def validate(self, yaml_text: str) -> list[str]:
        try:
            data = yaml.safe_load(yaml_text)
        except yaml.YAMLError as e:
            return [f"yaml parse error: {e}"]
        try:
            model = CapabilitySkillYamlModel(**data)
        except ValidationError as e:
            return [f"schema: {err['loc']}: {err['msg']}" for err in e.errors()]
        return await self.validator.validate_skill(model)

    async def create(self, yaml_text: str, admin_id: str) -> CapabilitySkill:
        errors = await self.validate(yaml_text)
        if errors:
            raise ValueError(f"validation failed: {errors}")
        data = yaml.safe_load(yaml_text)
        model = CapabilitySkillYamlModel(**data)
        if await self.get(model.id):
            raise ValueError(f"skill {model.id} already exists")
        skill = CapabilitySkill(**_yaml_to_orm(model))
        self.db.add(skill)
        self.db.add(AdminLog(
            action="skill_create", admin_id=admin_id, target_user_id=None,
            details={"skill_id": model.id, "yaml_after_sha256": _sha256(yaml_text)},
        ))
        await self.db.commit()
        return skill

    async def update(self, skill_id: str, yaml_text: str, admin_id: str) -> CapabilitySkill:
        errors = await self.validate(yaml_text)
        if errors:
            raise ValueError(f"validation failed: {errors}")
        data = yaml.safe_load(yaml_text)
        model = CapabilitySkillYamlModel(**data)
        if model.id != skill_id:
            raise ValueError("yaml id must match URL path")
        skill = await self.get(skill_id)
        if skill is None:
            raise ValueError("not found")
        before_yaml = yaml.safe_dump(_orm_to_yaml_dict(skill), sort_keys=False, allow_unicode=True)
        for k, v in _yaml_to_orm(model).items():
            if k == "id":
                continue
            setattr(skill, k, v)
        self.db.add(AdminLog(
            action="skill_update", admin_id=admin_id, target_user_id=None,
            details={
                "skill_id": skill_id,
                "yaml_before_sha256": _sha256(before_yaml),
                "yaml_after_sha256": _sha256(yaml_text),
            },
        ))
        await self.db.commit()
        return skill

    async def delete(self, skill_id: str, admin_id: str) -> None:
        skill = await self.get(skill_id)
        if skill is None:
            raise ValueError("not found")
        before_yaml = yaml.safe_dump(_orm_to_yaml_dict(skill), sort_keys=False, allow_unicode=True)
        await self.db.delete(skill)
        self.db.add(AdminLog(
            action="skill_delete", admin_id=admin_id, target_user_id=None,
            details={"skill_id": skill_id, "yaml_before_sha256": _sha256(before_yaml)},
        ))
        await self.db.commit()

    async def toggle(self, skill_id: str, admin_id: str) -> CapabilitySkill:
        skill = await self.get(skill_id)
        if skill is None:
            raise ValueError("not found")
        previous = skill.enabled
        skill.enabled = not previous
        self.db.add(AdminLog(
            action="skill_toggle", admin_id=admin_id, target_user_id=None,
            details={"skill_id": skill_id, "enabled_before": previous, "enabled_after": skill.enabled},
        ))
        await self.db.commit()
        return skill

    def to_yaml_text(self, skill: CapabilitySkill) -> str:
        return yaml.safe_dump(_orm_to_yaml_dict(skill), sort_keys=False, allow_unicode=True)
```

- [ ] **Step 3: Run tests + commit**

Run: `cd backend && .venv/bin/python -m pytest tests/services/test_admin_skill_service.py -v`
Expected: PASS

```bash
git add backend/src/services/admin_skill_service.py backend/tests/services/test_admin_skill_service.py
git commit -m "feat(admin): AdminSkillService CRUD"
```

### Task 3.5: Admin routers (capabilities + skills)

**Files:**
- Create: `backend/src/gateway/routers/admin_capabilities.py`
- Create: `backend/src/gateway/routers/admin_skills.py`
- Modify: `backend/src/gateway/main.py` (or wherever routers are registered)

- [ ] **Step 1: Write `admin_capabilities.py` router**

```python
"""Admin capability management endpoints."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status

from src.database import User, get_db_session
from src.gateway.auth_dependencies import get_current_admin
from src.services.admin_capability_service import AdminCapabilityService
from src.services.capability_loader import CapabilityLoader, DEFAULT_SEED_DIR

router = APIRouter(prefix="/admin/capabilities", tags=["admin", "capabilities"])


async def _service(request: Request) -> AdminCapabilityService:
    from src.academic.cache.redis_client import redis_client
    from src.services.event_bus import EventBus

    if redis_client._client is None:
        await redis_client.connect()
    async with get_db_session() as db:
        yield AdminCapabilityService(db=db, event_bus=EventBus(redis_client.client))


def _to_dict(cap) -> dict[str, Any]:
    return {
        "id": cap.id, "workspace_type": cap.workspace_type, "enabled": cap.enabled,
        "display_name": cap.display_name, "description": cap.description,
        "ui_meta": cap.ui_meta,
    }


@router.get("")
async def list_capabilities(
    service: AdminCapabilityService = Depends(_service),
    _admin: User = Depends(get_current_admin),
) -> dict[str, Any]:
    items = await service.list_all()
    grouped: dict[str, list[dict[str, Any]]] = {}
    for cap in items:
        grouped.setdefault(cap.workspace_type, []).append(_to_dict(cap))
    return {"groups": grouped, "total": len(items)}


@router.get("/{capability_id}")
async def get_capability(
    capability_id: str,
    workspace_type: str,
    service: AdminCapabilityService = Depends(_service),
    _admin: User = Depends(get_current_admin),
) -> dict[str, Any]:
    cap = await service.get(capability_id, workspace_type)
    if cap is None:
        raise HTTPException(404, "capability not found")
    return {
        "yaml": service.to_yaml_text(cap),
        "updated_at": getattr(cap, "updated_at", None),
    }


@router.post("/validate")
async def validate_capability(
    payload: dict = Body(...),
    service: AdminCapabilityService = Depends(_service),
    _admin: User = Depends(get_current_admin),
) -> dict[str, Any]:
    errors = await service.validate(payload.get("yaml", ""))
    return {"valid": not errors, "errors": errors}


@router.post("")
async def create_capability(
    payload: dict = Body(...),
    service: AdminCapabilityService = Depends(_service),
    admin: User = Depends(get_current_admin),
) -> dict[str, Any]:
    try:
        cap = await service.create(yaml_text=payload["yaml"], admin_id=admin.id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return _to_dict(cap)


@router.put("/{capability_id}")
async def update_capability(
    capability_id: str,
    workspace_type: str,
    payload: dict = Body(...),
    service: AdminCapabilityService = Depends(_service),
    admin: User = Depends(get_current_admin),
) -> dict[str, Any]:
    try:
        cap = await service.update(
            capability_id=capability_id,
            workspace_type=workspace_type,
            yaml_text=payload["yaml"],
            admin_id=admin.id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return _to_dict(cap)


@router.delete("/{capability_id}")
async def delete_capability(
    capability_id: str,
    workspace_type: str,
    service: AdminCapabilityService = Depends(_service),
    admin: User = Depends(get_current_admin),
) -> Response:
    try:
        await service.delete(capability_id, workspace_type, admin_id=admin.id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{capability_id}/toggle")
async def toggle_capability(
    capability_id: str,
    workspace_type: str,
    service: AdminCapabilityService = Depends(_service),
    admin: User = Depends(get_current_admin),
) -> dict[str, Any]:
    cap = await service.toggle(capability_id, workspace_type, admin_id=admin.id)
    return _to_dict(cap)


@router.post("/import-from-seed")
async def import_from_seed(
    service: AdminCapabilityService = Depends(_service),
    admin: User = Depends(get_current_admin),
) -> dict[str, Any]:
    async with get_db_session() as db:
        loader = CapabilityLoader(session=db, seed_dir=DEFAULT_SEED_DIR)
        loaded = await loader.load_all(overwrite=True)
    return {"loaded": [{"id": c.id, "workspace_type": c.workspace_type} for c in loaded]}


@router.get("/export")
async def export_zip(
    service: AdminCapabilityService = Depends(_service),
    _admin: User = Depends(get_current_admin),
) -> Response:
    items = await service.list_all()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for cap in items:
            path = f"capabilities/{cap.workspace_type}/{cap.id}.yaml"
            zf.writestr(path, service.to_yaml_text(cap))
    buf.seek(0)
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="capabilities.zip"'},
    )
```

(`get_current_admin` may not exist — check `backend/src/gateway/auth_dependencies.py`. If absent, define it as `get_current_user` + role check, or add a thin wrapper there.)

- [ ] **Step 2: Write `admin_skills.py` router**

Mirror structure of admin_capabilities.py but for skills. Endpoints: GET `/admin/skills`, GET `/admin/skills/{id}`, POST `/admin/skills`, PUT `/admin/skills/{id}`, DELETE `/admin/skills/{id}`, POST `/admin/skills/{id}/toggle`, POST `/admin/skills/validate`. Add import-from-seed reading `backend/seed/skills/*.yaml` and export.zip producing `skills/*.yaml`.

- [ ] **Step 3: Register routers**

In the FastAPI app initialization (search for `app.include_router(`), add:

```python
from src.gateway.routers.admin_capabilities import router as admin_capabilities_router
from src.gateway.routers.admin_skills import router as admin_skills_router

app.include_router(admin_capabilities_router)
app.include_router(admin_skills_router)
```

- [ ] **Step 4: Smoke test endpoints**

Run: `cd backend && .venv/bin/python -m pytest tests/gateway/ -v -k "admin_capabilit"` (or add a new test file if needed)

Manual quick check:

```bash
curl -X POST http://localhost:8000/admin/capabilities/validate \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"yaml": "id: x\nworkspace_type: thesis"}'
```

Expected: `{"valid": false, "errors": [...]}` listing missing required fields.

- [ ] **Step 5: Commit**

```bash
git add backend/src/gateway/routers/admin_capabilities.py backend/src/gateway/routers/admin_skills.py backend/src/gateway/main.py
git commit -m "feat(admin): capability + skill management routers"
```

### Task 3.6: Frontend API client

**Files:**
- Create: `frontend/lib/api/admin-capabilities.ts`
- Create: `frontend/lib/api/admin-skills.ts`

- [ ] **Step 1: Write `admin-capabilities.ts`**

```typescript
import { authorizedFetch } from "@/lib/api/client";

export interface AdminCapabilitySummary {
  id: string;
  workspace_type: string;
  enabled: boolean;
  display_name: string;
  description: string;
  ui_meta: { icon: string; color: string; order: number };
}

export interface AdminCapabilityListResponse {
  groups: Record<string, AdminCapabilitySummary[]>;
  total: number;
}

export interface AdminCapabilityDetail {
  yaml: string;
  updated_at: string | null;
}

export interface ValidateResponse {
  valid: boolean;
  errors: string[];
}

export async function listAdminCapabilities(): Promise<AdminCapabilityListResponse> {
  return authorizedFetch("/admin/capabilities");
}

export async function getAdminCapability(id: string, workspaceType: string): Promise<AdminCapabilityDetail> {
  return authorizedFetch(`/admin/capabilities/${id}?workspace_type=${encodeURIComponent(workspaceType)}`);
}

export async function validateAdminCapability(yamlText: string): Promise<ValidateResponse> {
  return authorizedFetch("/admin/capabilities/validate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ yaml: yamlText }),
  });
}

export async function createAdminCapability(yamlText: string): Promise<AdminCapabilitySummary> {
  return authorizedFetch("/admin/capabilities", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ yaml: yamlText }),
  });
}

export async function updateAdminCapability(id: string, workspaceType: string, yamlText: string): Promise<AdminCapabilitySummary> {
  return authorizedFetch(`/admin/capabilities/${id}?workspace_type=${encodeURIComponent(workspaceType)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ yaml: yamlText }),
  });
}

export async function deleteAdminCapability(id: string, workspaceType: string): Promise<void> {
  await authorizedFetch(`/admin/capabilities/${id}?workspace_type=${encodeURIComponent(workspaceType)}`, {
    method: "DELETE",
  });
}

export async function toggleAdminCapability(id: string, workspaceType: string): Promise<AdminCapabilitySummary> {
  return authorizedFetch(`/admin/capabilities/${id}/toggle?workspace_type=${encodeURIComponent(workspaceType)}`, {
    method: "POST",
  });
}

export async function importCapabilitiesFromSeed(): Promise<{ loaded: Array<{ id: string; workspace_type: string }> }> {
  return authorizedFetch("/admin/capabilities/import-from-seed", { method: "POST" });
}
```

- [ ] **Step 2: Write `admin-skills.ts`**

Mirror admin-capabilities.ts: types `AdminSkillSummary` / `AdminSkillDetail`, methods `listAdminSkills`, `getAdminSkill`, `validateAdminSkill`, `createAdminSkill`, `updateAdminSkill`, `deleteAdminSkill`, `toggleAdminSkill`, `importSkillsFromSeed`.

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/api/admin-capabilities.ts frontend/lib/api/admin-skills.ts
git commit -m "feat(frontend): admin capability/skill API client"
```

### Task 3.7: Capability list page

**Files:**
- Create: `frontend/app/dashboard/admin/capabilities/page.tsx`

- [ ] **Step 1: Install Monaco**

Run: `cd frontend && npm i @monaco-editor/react js-yaml`
Run: `cd frontend && npm i -D @types/js-yaml`

- [ ] **Step 2: Write the list page**

```typescript
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Download, Loader2, Plus, RefreshCw, Upload } from "lucide-react";

import { AdminPageHeader } from "../components/AdminPageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  importCapabilitiesFromSeed,
  listAdminCapabilities,
  toggleAdminCapability,
  type AdminCapabilitySummary,
} from "@/lib/api/admin-capabilities";

const WS_LABEL: Record<string, string> = {
  thesis: "论文",
  sci: "SCI",
  proposal: "开题",
  software_copyright: "软著",
  patent: "专利",
};

export default function CapabilityListPage() {
  const [groups, setGroups] = useState<Record<string, AdminCapabilitySummary[]>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [keyword, setKeyword] = useState("");
  const [reloadNonce, setReloadNonce] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    listAdminCapabilities()
      .then((res) => { if (!cancelled) setGroups(res.groups); })
      .finally(() => { if (!cancelled) setIsLoading(false); });
    return () => { cancelled = true; };
  }, [reloadNonce]);

  const handleToggle = async (item: AdminCapabilitySummary) => {
    await toggleAdminCapability(item.id, item.workspace_type);
    setReloadNonce((v) => v + 1);
  };

  const handleImport = async () => {
    if (!confirm("从 seed 文件覆盖式重新灌入所有 capability？\n该操作会覆盖 DB 中的修改。")) return;
    await importCapabilitiesFromSeed();
    setReloadNonce((v) => v + 1);
  };

  const filter = keyword.trim().toLowerCase();
  const filterMatch = (item: AdminCapabilitySummary) =>
    !filter || item.id.toLowerCase().includes(filter) || item.display_name.toLowerCase().includes(filter);

  return (
    <>
      <AdminPageHeader
        title="Capability 管理"
        description={`共 ${Object.values(groups).flat().length} 个`}
        actions={
          <>
            <Button variant="outline" size="sm" onClick={handleImport}>
              <Upload className="w-4 h-4 mr-1" /> 从 seed 灌入
            </Button>
            <Button variant="outline" size="sm" asChild>
              <a href="/admin/capabilities/export" download>
                <Download className="w-4 h-4 mr-1" /> 导出 zip
              </a>
            </Button>
            <Button size="sm" asChild>
              <Link href="/dashboard/admin/capabilities/new"><Plus className="w-4 h-4 mr-1" />新建</Link>
            </Button>
          </>
        }
        onRefresh={() => setReloadNonce((v) => v + 1)}
        isRefreshing={isLoading}
      />

      <div className="route-card rounded-2xl p-5">
        <Input
          placeholder="搜索 id 或 display_name"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          className="max-w-md mb-4"
        />

        {isLoading ? (
          <div className="flex items-center gap-2 text-[var(--text-muted)] text-sm py-6">
            <Loader2 className="w-4 h-4 animate-spin" /> 加载中
          </div>
        ) : (
          <div className="space-y-6">
            {Object.entries(groups).map(([wsType, items]) => {
              const filtered = items.filter(filterMatch);
              if (filtered.length === 0) return null;
              return (
                <details key={wsType} open className="rounded-xl border border-[var(--border-default)]">
                  <summary className="cursor-pointer list-none px-4 py-3 font-medium text-[var(--text-primary)]">
                    {WS_LABEL[wsType] ?? wsType} · {wsType}  ·  {filtered.length} 个
                  </summary>
                  <table className="w-full text-sm">
                    <tbody>
                      {filtered.map((item) => (
                        <tr key={item.id} className="border-t border-[var(--border-default)]/50">
                          <td className="px-4 py-2 w-10">
                            <button
                              onClick={() => handleToggle(item)}
                              className={`inline-flex w-2.5 h-2.5 rounded-full ${
                                item.enabled ? "bg-emerald-500" : "bg-slate-400"
                              }`}
                              title={item.enabled ? "已启用，点击禁用" : "已禁用，点击启用"}
                            />
                          </td>
                          <td className="px-4 py-2 font-mono text-xs text-[var(--text-secondary)]">{item.id}</td>
                          <td className="px-4 py-2 text-[var(--text-primary)]">{item.display_name}</td>
                          <td className="px-4 py-2 text-right">
                            <Link
                              href={`/dashboard/admin/capabilities/${encodeURIComponent(item.id)}?workspace_type=${item.workspace_type}`}
                              className="text-sm text-[var(--accent-primary)] hover:underline"
                            >
                              编辑
                            </Link>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </details>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}
```

- [ ] **Step 3: Smoke test**

Manual: navigate to `/dashboard/admin/capabilities`, verify list groups by workspace_type, search filters, toggle works.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/dashboard/admin/capabilities/page.tsx frontend/package.json frontend/package-lock.json
git commit -m "feat(admin): capability list page"
```

### Task 3.8: Capability YAML editor page

**Files:**
- Create: `frontend/app/dashboard/admin/capabilities/[id]/page.tsx`
- Create: `frontend/app/dashboard/admin/capabilities/new/page.tsx`
- Create: `frontend/app/dashboard/admin/components/YamlEditor.tsx`

- [ ] **Step 1: Write shared YamlEditor component**

```typescript
"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useRef, useState } from "react";

const MonacoEditor = dynamic(() => import("@monaco-editor/react").then((m) => m.default), { ssr: false });

interface Props {
  initialValue: string;
  onChange: (value: string) => void;
  onValidate: (yamlText: string) => Promise<string[]>;
  height?: string;
}

export function YamlEditor({ initialValue, onChange, onValidate, height = "600px" }: Props) {
  const [value, setValue] = useState(initialValue);
  const [errors, setErrors] = useState<string[]>([]);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      const errs = await onValidate(value);
      setErrors(errs);
    }, 400);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [value, onValidate]);

  const handleChange = (v: string | undefined) => {
    const next = v ?? "";
    setValue(next);
    onChange(next);
  };

  return (
    <div className="space-y-2">
      <div className="rounded-xl border border-[var(--border-default)] overflow-hidden">
        <MonacoEditor
          height={height}
          defaultLanguage="yaml"
          value={value}
          onChange={handleChange}
          options={{
            minimap: { enabled: false },
            fontSize: 13,
            lineNumbers: "on",
            wordWrap: "on",
            tabSize: 2,
            scrollBeyondLastLine: false,
          }}
          theme="vs-dark"
        />
      </div>
      {errors.length > 0 ? (
        <div className="rounded-lg border border-rose-300/40 bg-rose-500/10 p-3 space-y-1">
          {errors.map((err, i) => (
            <div key={i} className="text-xs text-rose-700 font-mono">⚠️ {err}</div>
          ))}
        </div>
      ) : (
        <div className="text-xs text-emerald-600">✅ 语法 OK / schema 通过</div>
      )}
    </div>
  );
}

export function useYamlEditorState(initial: string) {
  return useState(initial);
}
```

- [ ] **Step 2: Write edit page `[id]/page.tsx`**

```typescript
"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, Loader2 } from "lucide-react";

import { YamlEditor } from "../../components/YamlEditor";
import { Button } from "@/components/ui/button";
import {
  deleteAdminCapability, getAdminCapability, updateAdminCapability,
  validateAdminCapability,
} from "@/lib/api/admin-capabilities";

export default function CapabilityEditPage({ params }: { params: { id: string } }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const workspaceType = searchParams.get("workspace_type") ?? "";

  const [yamlText, setYamlText] = useState("");
  const [originalYaml, setOriginalYaml] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    if (!workspaceType) return;
    setIsLoading(true);
    getAdminCapability(params.id, workspaceType)
      .then((res) => {
        setYamlText(res.yaml);
        setOriginalYaml(res.yaml);
      })
      .finally(() => setIsLoading(false));
  }, [params.id, workspaceType]);

  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (yamlText !== originalYaml) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [yamlText, originalYaml]);

  const handleValidate = async (text: string) => {
    const res = await validateAdminCapability(text);
    setErrors(res.errors);
    return res.errors;
  };

  const handleSave = async () => {
    setIsSaving(true);
    setSaveError(null);
    try {
      await updateAdminCapability(params.id, workspaceType, yamlText);
      setOriginalYaml(yamlText);
      router.push("/dashboard/admin/capabilities");
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm(`确认删除 capability "${params.id}"？此操作不可恢复。`)) return;
    await deleteAdminCapability(params.id, workspaceType);
    router.push("/dashboard/admin/capabilities");
  };

  if (isLoading) {
    return <div className="flex items-center justify-center py-20"><Loader2 className="w-6 h-6 animate-spin" /></div>;
  }

  const isDirty = yamlText !== originalYaml;
  const canSave = !isSaving && isDirty && errors.length === 0;

  return (
    <>
      <div className="route-card rounded-[1.75rem] p-6 mb-6 flex flex-col md:flex-row md:items-center md:justify-between gap-3">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={() => router.push("/dashboard/admin/capabilities")}>
            <ArrowLeft className="w-4 h-4" />
          </Button>
          <div>
            <h1 className="text-xl font-bold text-[var(--text-primary)]">
              {params.id} <span className="text-sm text-[var(--text-muted)]">/ {workspaceType}</span>
            </h1>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => router.push("/dashboard/admin/capabilities")} disabled={isSaving}>
            取消
          </Button>
          <Button variant="destructive" size="sm" onClick={handleDelete} disabled={isSaving}>
            删除
          </Button>
          <Button size="sm" onClick={handleSave} disabled={!canSave}>
            {isSaving && <Loader2 className="w-4 h-4 mr-1 animate-spin" />}
            保存
          </Button>
        </div>
      </div>

      {saveError && (
        <div className="mb-4 rounded-lg border border-rose-300/40 bg-rose-500/10 p-3 text-sm text-rose-700">
          {saveError}
        </div>
      )}

      <YamlEditor
        initialValue={yamlText}
        onChange={setYamlText}
        onValidate={handleValidate}
        height="640px"
      />
    </>
  );
}
```

- [ ] **Step 3: Write create page `new/page.tsx`**

```typescript
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Loader2 } from "lucide-react";

import { YamlEditor } from "../../components/YamlEditor";
import { Button } from "@/components/ui/button";
import { createAdminCapability, validateAdminCapability } from "@/lib/api/admin-capabilities";

const TEMPLATE_YAML = `id: new_capability
workspace_type: thesis
display_name: 新能力
description: 简短描述
intent_description: 用户希望做什么
trigger_phrases: []
required_decisions: []
brief_schema:
  type: object
  properties: {}
  required: []
graph_template:
  phases:
    - name: phase1
      tasks:
        - name: t1
          subagent_type: react
          skill_id: null
          inputs: {}
          outputs: []
ui_meta:
  icon: search
  color: purple
  order: 0
  stages: []
  follow_up_prompt: null
notes: null
`;

export default function CapabilityCreatePage() {
  const router = useRouter();
  const [yamlText, setYamlText] = useState(TEMPLATE_YAML);
  const [errors, setErrors] = useState<string[]>([]);
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const handleValidate = async (text: string) => {
    const res = await validateAdminCapability(text);
    setErrors(res.errors);
    return res.errors;
  };

  const handleSave = async () => {
    setIsSaving(true);
    setSaveError(null);
    try {
      await createAdminCapability(yamlText);
      router.push("/dashboard/admin/capabilities");
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "创建失败");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <>
      <div className="route-card rounded-[1.75rem] p-6 mb-6 flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={() => router.push("/dashboard/admin/capabilities")}>
            <ArrowLeft className="w-4 h-4" />
          </Button>
          <h1 className="text-xl font-bold">新建 Capability</h1>
        </div>
        <Button size="sm" onClick={handleSave} disabled={isSaving || errors.length > 0}>
          {isSaving && <Loader2 className="w-4 h-4 mr-1 animate-spin" />}
          创建
        </Button>
      </div>

      {saveError && (
        <div className="mb-4 rounded-lg border border-rose-300/40 bg-rose-500/10 p-3 text-sm text-rose-700">
          {saveError}
        </div>
      )}

      <YamlEditor
        initialValue={TEMPLATE_YAML}
        onChange={setYamlText}
        onValidate={handleValidate}
        height="640px"
      />
    </>
  );
}
```

- [ ] **Step 4: Smoke test**

Manual:
1. Navigate to `/dashboard/admin/capabilities`, click a capability → edit page loads YAML
2. Edit a field with valid change → save → returns to list, change persists
3. Edit with invalid YAML (delete a required field) → save button disabled
4. Click "New" → template loads, fill in, save → new capability appears in list
5. Refresh page mid-edit → browser blocks navigation with unsaved changes warning

- [ ] **Step 5: Commit**

```bash
git add frontend/app/dashboard/admin/capabilities frontend/app/dashboard/admin/components/YamlEditor.tsx
git commit -m "feat(admin): capability YAML editor (Monaco + live validation)"
```

### Task 3.9: Skill list + edit pages

**Files:**
- Create: `frontend/app/dashboard/admin/skills/page.tsx`
- Create: `frontend/app/dashboard/admin/skills/[id]/page.tsx`
- Create: `frontend/app/dashboard/admin/skills/new/page.tsx`

- [ ] **Step 1: Mirror capability pages for skills**

The 3 skill pages are structurally identical to capability pages with two simplifications:
1. No workspace_type composite PK — URL is `/skills/{id}` (no query param)
2. No groupings in list page (skills are flat)

Copy the 3 capability page files to skills/ paths and adjust:
- Replace `listAdminCapabilities` → `listAdminSkills`
- Replace `updateAdminCapability(id, workspaceType, yaml)` → `updateAdminSkill(id, yaml)` (one less arg)
- Replace `getAdminCapability(id, workspaceType)` → `getAdminSkill(id)`
- Drop the `workspace_type` query param and `details` open/close grouping
- Update TEMPLATE_YAML to skill shape:

```yaml
id: new-skill
display_name: 新技能
description: 简短描述
subagent_type: react
prompt: |
  你是一个助手。
allowed_tools: []
resources: []
config: {}
```

- [ ] **Step 2: Smoke test + commit**

Manual: navigate to `/dashboard/admin/skills`, edit one skill, save round-trips.

```bash
git add frontend/app/dashboard/admin/skills
git commit -m "feat(admin): skill list + YAML editor pages"
```

---

## Phase 4 — Credit Grant Rules + Redeem Codes

**Goal:** 4 new tables (rules, redeem_codes, redemptions, referrals); rule triggers wired into register flow + first-task event; celery beat for periodic rules; atomic redemption flow; admin frontend for rules + codes.

**Pre-conditions:** Phase 2 merged (admin IA exists). Independent of Phase 3 / Phase 5.

### Task 4.1: Migration 051 — 4 new tables + 2 enum values

**Files:**
- Create: `backend/alembic/versions/051_credit_grant_rules_and_redeem_codes.py`

- [ ] **Step 1: Write the migration**

```python
"""Credit grant rules + redeem codes + redemptions + referrals.

Revision ID: 051_credit_grant_rules_and_redeem_codes
Revises: 050_capability_drop_result_card_template
Create Date: 2026-05-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "051_credit_grant_rules_and_redeem_codes"
down_revision: str | None = "050_capability_drop_result_card_template"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE credit_transaction_type ADD VALUE IF NOT EXISTS 'referral_bonus'")
    op.execute("ALTER TYPE credit_transaction_type ADD VALUE IF NOT EXISTS 'redeem_code'")

    op.create_table(
        "credit_grant_rules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column(
            "rule_type",
            sa.Enum(
                "registration_bonus", "referral_referrer", "referral_referred", "periodic",
                name="credit_grant_rule_type",
            ),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("config", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by_admin_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("idx_credit_grant_rules_type_enabled", "credit_grant_rules", ["rule_type", "enabled"])

    op.create_table(
        "credit_redeem_codes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code", sa.String(20), nullable=False, unique=True),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("use_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("per_user_limit", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("batch_id", sa.String(36), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by_admin_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("idx_redeem_codes_batch", "credit_redeem_codes", ["batch_id"])

    op.create_table(
        "credit_redemptions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code_id", sa.String(36), sa.ForeignKey("credit_redeem_codes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("transaction_id", sa.String(36), sa.ForeignKey("credit_transactions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_redemption_code_user", "credit_redemptions", ["code_id", "user_id"])

    op.create_table(
        "referrals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("referrer_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("referee_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("referrer_credited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("referee_credited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("referee_first_task_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("referrals")
    op.drop_table("credit_redemptions")
    op.drop_index("idx_redeem_codes_batch", "credit_redeem_codes")
    op.drop_table("credit_redeem_codes")
    op.drop_index("idx_credit_grant_rules_type_enabled", "credit_grant_rules")
    op.drop_table("credit_grant_rules")
    op.execute("DROP TYPE IF EXISTS credit_grant_rule_type")
    # NOTE: PG cannot drop enum values; leave referral_bonus / redeem_code in place.
```

- [ ] **Step 2: Run upgrade**

Run: `cd backend && .venv/bin/alembic upgrade head`
Expected: 4 tables created.

- [ ] **Step 3: Verify schema**

Run: `cd backend && .venv/bin/python -c "
import asyncio
from sqlalchemy import inspect
from src.database import async_engine

async def main():
    async with async_engine.connect() as conn:
        tables = await conn.run_sync(lambda c: inspect(c).get_table_names())
        for t in ('credit_grant_rules','credit_redeem_codes','credit_redemptions','referrals'):
            print(t, t in tables)

asyncio.run(main())
"`

Expected: each table prints `True`.

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/051_credit_grant_rules_and_redeem_codes.py
git commit -m "feat(db): credit grant rules, redeem codes, redemptions, referrals tables"
```

### Task 4.2: ORM models

**Files:**
- Create: `backend/src/database/models/credit_grant_rule.py`
- Create: `backend/src/database/models/credit_redeem_code.py`
- Create: `backend/src/database/models/credit_redemption.py`
- Create: `backend/src/database/models/referral.py`
- Modify: `backend/src/database/models/credit.py` (add 2 enum values)
- Modify: `backend/src/database/models/__init__.py` (export new models)

- [ ] **Step 1: Add enum values**

In [backend/src/database/models/credit.py](../../backend/src/database/models/credit.py), find `class CreditTransactionType`:

```python
class CreditTransactionType(StrEnum):
    ADMIN_GRANT = "admin_grant"
    ADMIN_DEDUCT = "admin_deduct"
    WORKFLOW_CONSUME = "workflow_consume"
    THREAD_TOKEN_CONSUME = "thread_token_consume"
    REGISTRATION_BONUS = "registration_bonus"
    REFUND = "refund"
    REFERRAL_BONUS = "referral_bonus"
    REDEEM_CODE = "redeem_code"
```

- [ ] **Step 2: Write `credit_grant_rule.py`**

```python
"""CreditGrantRule ORM model — admin-configured auto-grant rules."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, Boolean, func
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, UUIDMixin


class CreditGrantRuleType(StrEnum):
    REGISTRATION_BONUS = "registration_bonus"
    REFERRAL_REFERRER = "referral_referrer"
    REFERRAL_REFERRED = "referral_referred"
    PERIODIC = "periodic"


class CreditGrantRule(Base, UUIDMixin):
    __tablename__ = "credit_grant_rules"
    __table_args__ = (Index("idx_credit_grant_rules_type_enabled", "rule_type", "enabled"),)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    rule_type: Mapped[CreditGrantRuleType] = mapped_column(
        SQLEnum(
            CreditGrantRuleType,
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
            name="credit_grant_rule_type",
        ),
        nullable=False,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    created_by_admin_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
```

- [ ] **Step 3: Write `credit_redeem_code.py`**

```python
"""CreditRedeemCode ORM model — admin-issued redemption codes."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, UUIDMixin


class CreditRedeemCode(Base, UUIDMixin):
    __tablename__ = "credit_redeem_codes"
    __table_args__ = (Index("idx_redeem_codes_batch", "batch_id"),)

    code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True, index=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    max_uses: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    use_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    per_user_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    batch_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_by_admin_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
```

- [ ] **Step 4: Write `credit_redemption.py`**

```python
"""CreditRedemption ORM model — per-user redemption ledger."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, UUIDMixin


class CreditRedemption(Base, UUIDMixin):
    __tablename__ = "credit_redemptions"
    __table_args__ = (Index("idx_redemption_code_user", "code_id", "user_id"),)

    code_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("credit_redeem_codes.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    transaction_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("credit_transactions.id", ondelete="SET NULL"), nullable=True
    )
    redeemed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
```

- [ ] **Step 5: Write `referral.py`**

```python
"""Referral ORM model — invitation relationship."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, UUIDMixin


class Referral(Base, UUIDMixin):
    __tablename__ = "referrals"

    referrer_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    referee_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    referrer_credited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    referee_credited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    referee_first_task_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
```

- [ ] **Step 6: Update __init__.py exports**

In [backend/src/database/models/__init__.py](../../backend/src/database/models/__init__.py), add (alphabetical):

```python
from .credit_grant_rule import CreditGrantRule, CreditGrantRuleType
from .credit_redeem_code import CreditRedeemCode
from .credit_redemption import CreditRedemption
from .referral import Referral
```

Also update the `__all__` list with these names.

- [ ] **Step 7: Verify model imports**

Run: `cd backend && .venv/bin/python -c "from src.database import CreditGrantRule, CreditRedeemCode, CreditRedemption, Referral, CreditGrantRuleType; print('OK')"`
Expected: `OK`

- [ ] **Step 8: Commit**

```bash
git add backend/src/database/models/
git commit -m "feat(models): 4 credit-rules+codes+redemptions+referrals ORMs"
```

### Task 4.3: Code generation helper

**Files:**
- Create: `backend/src/services/redeem_code_generator.py`
- Create: `backend/tests/services/test_redeem_code_generator.py`

- [ ] **Step 1: Write failing test**

```python
"""Tests for redeem code generator."""

import re

from src.services.redeem_code_generator import generate_code, ALPHABET


def test_format_is_four_groups_of_four():
    code = generate_code()
    assert re.match(r"^[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}$", code), code


def test_uses_only_safe_alphabet():
    for _ in range(50):
        code = generate_code()
        for ch in code.replace("-", ""):
            assert ch in ALPHABET, f"forbidden char {ch} in {code}"


def test_high_entropy():
    """No two codes from 1000 generations should collide (probabilistic, but virtually certain)."""
    codes = {generate_code() for _ in range(1000)}
    assert len(codes) == 1000
```

- [ ] **Step 2: Run to verify FAIL**

Expected: module not found.

- [ ] **Step 3: Implement**

```python
"""Random redeem code generator.

Format: 4 groups of 4 chars separated by dashes (16 chars + 3 separators).
Alphabet excludes confusable characters (I/1/O/0/l), giving 32 safe chars.
Entropy: 32^16 ≈ 2^80 → collisions practically impossible.

Persistence layer enforces UNIQUE constraint; rare collisions are retried by callers.
"""

from __future__ import annotations

import secrets

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_code() -> str:
    chunks = ["".join(secrets.choice(ALPHABET) for _ in range(4)) for _ in range(4)]
    return "-".join(chunks)
```

- [ ] **Step 4: Run to verify PASS**

Run: `cd backend && .venv/bin/python -m pytest tests/services/test_redeem_code_generator.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/services/redeem_code_generator.py backend/tests/services/test_redeem_code_generator.py
git commit -m "feat(redeem): code generator (confusable-safe alphabet)"
```

### Task 4.4: CreditGrantRuleService — CRUD + Pydantic config validation

**Files:**
- Create: `backend/src/services/credit_grant_rule_service.py`
- Create: `backend/tests/services/test_credit_grant_rule_service.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for CreditGrantRuleService."""
import pytest

from src.database import CreditGrantRuleType
from src.services.credit_grant_rule_service import (
    CreditGrantRuleService,
    RegistrationConfig, ReferralConfig, PeriodicConfig,
)


@pytest.mark.asyncio
async def test_create_registration_rule(real_async_db):
    service = CreditGrantRuleService(db=real_async_db)
    rule = await service.create(
        name="新人 200 积分",
        rule_type=CreditGrantRuleType.REGISTRATION_BONUS,
        amount=200,
        config={},
        admin_id="admin-uuid",
    )
    assert rule.amount == 200


@pytest.mark.asyncio
async def test_create_periodic_requires_cron(real_async_db):
    service = CreditGrantRuleService(db=real_async_db)
    with pytest.raises(ValueError, match="cron"):
        await service.create(
            name="周一 50 积分",
            rule_type=CreditGrantRuleType.PERIODIC,
            amount=50,
            config={},  # missing cron
            admin_id="admin-uuid",
        )


@pytest.mark.asyncio
async def test_create_periodic_invalid_cron_rejected(real_async_db):
    service = CreditGrantRuleService(db=real_async_db)
    with pytest.raises(ValueError, match="cron"):
        await service.create(
            name="坏 cron",
            rule_type=CreditGrantRuleType.PERIODIC,
            amount=50,
            config={"cron": "not a cron"},
            admin_id="admin-uuid",
        )


@pytest.mark.asyncio
async def test_referral_referrer_defaults_on_first_task(real_async_db):
    service = CreditGrantRuleService(db=real_async_db)
    rule = await service.create(
        name="邀请者 100 积分",
        rule_type=CreditGrantRuleType.REFERRAL_REFERRER,
        amount=100,
        config={},
        admin_id="admin-uuid",
    )
    assert rule.config["trigger"] == "on_first_task"
```

- [ ] **Step 2: Implement service**

```python
"""CreditGrantRuleService — admin CRUD with discriminated-union config validation."""

from __future__ import annotations

from typing import Any, Literal

from croniter import croniter
from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import AdminLog, CreditGrantRule, CreditGrantRuleType


class RegistrationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReferralConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trigger: Literal["on_signup", "on_first_task"] = "on_first_task"


class ReferredConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trigger: Literal["on_signup"] = "on_signup"


class TargetFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")
    active_within_days: int | None = None
    role: Literal["user", "admin"] | None = None


class PeriodicConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cron: str
    target_filter: TargetFilter = TargetFilter()

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        if not croniter.is_valid(self.cron):
            raise ValueError(f"invalid cron expression: {self.cron!r}")


CONFIG_MODELS: dict[CreditGrantRuleType, type[BaseModel]] = {
    CreditGrantRuleType.REGISTRATION_BONUS: RegistrationConfig,
    CreditGrantRuleType.REFERRAL_REFERRER: ReferralConfig,
    CreditGrantRuleType.REFERRAL_REFERRED: ReferredConfig,
    CreditGrantRuleType.PERIODIC: PeriodicConfig,
}


def _validated_config(rule_type: CreditGrantRuleType, raw: dict[str, Any]) -> dict[str, Any]:
    model_cls = CONFIG_MODELS[rule_type]
    try:
        model = model_cls(**raw)
    except (ValidationError, ValueError) as e:
        raise ValueError(f"config invalid for {rule_type}: {e}") from e
    return model.model_dump()


class CreditGrantRuleService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_all(self) -> list[CreditGrantRule]:
        result = await self.db.execute(select(CreditGrantRule).order_by(CreditGrantRule.created_at))
        return list(result.scalars().all())

    async def get(self, rule_id: str) -> CreditGrantRule | None:
        result = await self.db.execute(select(CreditGrantRule).where(CreditGrantRule.id == rule_id))
        return result.scalars().first()

    async def create(
        self, *, name: str, rule_type: CreditGrantRuleType, amount: int,
        config: dict[str, Any], description: str | None = None, admin_id: str,
    ) -> CreditGrantRule:
        if amount <= 0:
            raise ValueError("amount must be > 0")
        config = _validated_config(rule_type, config or {})

        rule = CreditGrantRule(
            name=name, rule_type=rule_type, amount=amount,
            description=description, config=config, enabled=True,
            created_by_admin_id=admin_id,
        )
        self.db.add(rule)
        self.db.add(AdminLog(
            action="credit_rule_create", admin_id=admin_id, target_user_id=None,
            details={"rule_id": rule.id, "rule_type": rule_type.value, "amount": amount},
        ))
        await self.db.commit()
        return rule

    async def update(
        self, *, rule_id: str, name: str, amount: int, config: dict[str, Any],
        description: str | None, admin_id: str,
    ) -> CreditGrantRule:
        rule = await self.get(rule_id)
        if rule is None:
            raise ValueError("not found")
        if amount <= 0:
            raise ValueError("amount must be > 0")
        config = _validated_config(rule.rule_type, config or {})
        rule.name = name
        rule.amount = amount
        rule.description = description
        rule.config = config
        self.db.add(AdminLog(
            action="credit_rule_update", admin_id=admin_id, target_user_id=None,
            details={"rule_id": rule_id, "amount_after": amount},
        ))
        await self.db.commit()
        return rule

    async def toggle(self, rule_id: str, admin_id: str) -> CreditGrantRule:
        rule = await self.get(rule_id)
        if rule is None:
            raise ValueError("not found")
        previous = rule.enabled
        rule.enabled = not previous
        self.db.add(AdminLog(
            action="credit_rule_toggle", admin_id=admin_id, target_user_id=None,
            details={"rule_id": rule_id, "enabled_before": previous, "enabled_after": rule.enabled},
        ))
        await self.db.commit()
        return rule

    async def delete(self, rule_id: str, admin_id: str) -> None:
        rule = await self.get(rule_id)
        if rule is None:
            raise ValueError("not found")
        await self.db.delete(rule)
        self.db.add(AdminLog(
            action="credit_rule_delete", admin_id=admin_id, target_user_id=None,
            details={"rule_id": rule_id, "rule_type": rule.rule_type.value},
        ))
        await self.db.commit()

    async def get_active_rule(self, rule_type: CreditGrantRuleType) -> CreditGrantRule | None:
        """Returns the first enabled rule of the given type, or None."""
        result = await self.db.execute(
            select(CreditGrantRule)
            .where(CreditGrantRule.rule_type == rule_type)
            .where(CreditGrantRule.enabled == True)  # noqa: E712
            .order_by(CreditGrantRule.created_at)
        )
        return result.scalars().first()
```

- [ ] **Step 3: Install croniter**

Run: `cd backend && .venv/bin/pip install croniter` (then add `croniter` to `pyproject.toml` dependencies)

- [ ] **Step 4: Run tests**

Run: `cd backend && .venv/bin/python -m pytest tests/services/test_credit_grant_rule_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/services/credit_grant_rule_service.py backend/tests/services/test_credit_grant_rule_service.py backend/pyproject.toml
git commit -m "feat(credits): rule service with discriminated-union config validation"
```

### Task 4.5: CreditRedeemService — batch generate + atomic redeem

**Files:**
- Create: `backend/src/services/credit_redeem_service.py`
- Create: `backend/tests/services/test_credit_redeem_service.py`

- [ ] **Step 1: Write failing tests including concurrency safety**

```python
"""Tests for CreditRedeemService — focus on atomic redemption under concurrency."""
import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.services.credit_redeem_service import CreditRedeemService, RedeemError


@pytest.mark.asyncio
async def test_batch_generate_creates_n_unique_codes(real_async_db):
    service = CreditRedeemService(db=real_async_db)
    codes = await service.batch_generate(
        amount=200, count=10, max_uses=1, per_user_limit=1,
        expires_at=None, description="test", admin_id="admin-uuid",
    )
    assert len(codes) == 10
    assert len({c.code for c in codes}) == 10  # all unique


@pytest.mark.asyncio
async def test_redeem_increments_use_count(real_async_db, seed_user):
    service = CreditRedeemService(db=real_async_db)
    [code] = await service.batch_generate(
        amount=100, count=1, max_uses=1, per_user_limit=1,
        expires_at=None, description="t", admin_id="admin-uuid",
    )
    txn = await service.redeem(code=code.code, user_id=seed_user.id)
    assert txn.amount == 100
    await real_async_db.refresh(code)
    assert code.use_count == 1


@pytest.mark.asyncio
async def test_redeem_blocks_exceeding_max_uses(real_async_db, seed_two_users):
    service = CreditRedeemService(db=real_async_db)
    [code] = await service.batch_generate(
        amount=100, count=1, max_uses=1, per_user_limit=1,
        expires_at=None, description="t", admin_id="admin-uuid",
    )
    user1, user2 = seed_two_users
    await service.redeem(code=code.code, user_id=user1.id)
    with pytest.raises(RedeemError, match="exhausted"):
        await service.redeem(code=code.code, user_id=user2.id)


@pytest.mark.asyncio
async def test_redeem_blocks_per_user_limit(real_async_db, seed_user):
    service = CreditRedeemService(db=real_async_db)
    [code] = await service.batch_generate(
        amount=100, count=1, max_uses=5, per_user_limit=1,
        expires_at=None, description="t", admin_id="admin-uuid",
    )
    await service.redeem(code=code.code, user_id=seed_user.id)
    with pytest.raises(RedeemError, match="per-user limit"):
        await service.redeem(code=code.code, user_id=seed_user.id)


@pytest.mark.asyncio
async def test_redeem_expired_rejected(real_async_db, seed_user):
    service = CreditRedeemService(db=real_async_db)
    [code] = await service.batch_generate(
        amount=100, count=1, max_uses=1, per_user_limit=1,
        expires_at=datetime.now(UTC) - timedelta(days=1),
        description="t", admin_id="admin-uuid",
    )
    with pytest.raises(RedeemError, match="expired"):
        await service.redeem(code=code.code, user_id=seed_user.id)


@pytest.mark.asyncio
async def test_redeem_disabled_rejected(real_async_db, seed_user):
    service = CreditRedeemService(db=real_async_db)
    [code] = await service.batch_generate(
        amount=100, count=1, max_uses=1, per_user_limit=1,
        expires_at=None, description="t", admin_id="admin-uuid",
    )
    code.enabled = False
    await real_async_db.commit()
    with pytest.raises(RedeemError, match="disabled"):
        await service.redeem(code=code.code, user_id=seed_user.id)
```

- [ ] **Step 2: Implement service**

```python
"""CreditRedeemService — admin batch generate + user-side atomic redemption.

Atomic redeem uses SELECT ... FOR UPDATE to lock the redeem-code row inside a
transaction, preventing over-redemption under concurrent requests.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import (
    AdminLog, CreditRedeemCode, CreditRedemption, CreditTransaction,
    CreditTransactionType, User,
)
from src.services.redeem_code_generator import generate_code


class RedeemError(Exception):
    """User-facing redeem failure."""


class CreditRedeemService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def batch_generate(
        self,
        *,
        amount: int,
        count: int,
        max_uses: int,
        per_user_limit: int,
        expires_at: datetime | None,
        description: str | None,
        admin_id: str,
    ) -> list[CreditRedeemCode]:
        if amount <= 0:
            raise ValueError("amount must be > 0")
        if count <= 0 or count > 10000:
            raise ValueError("count must be 1..10000")
        if max_uses <= 0 or per_user_limit <= 0:
            raise ValueError("max_uses and per_user_limit must be > 0")

        batch_id = str(uuid.uuid4())
        created: list[CreditRedeemCode] = []

        for _ in range(count):
            for attempt in range(5):
                code = generate_code()
                obj = CreditRedeemCode(
                    code=code, amount=amount, max_uses=max_uses,
                    use_count=0, per_user_limit=per_user_limit,
                    expires_at=expires_at, valid_from=None, enabled=True,
                    batch_id=batch_id, description=description,
                    created_by_admin_id=admin_id,
                )
                self.db.add(obj)
                try:
                    await self.db.flush()
                except IntegrityError:
                    await self.db.rollback()  # unique collision; retry
                    continue
                created.append(obj)
                break
            else:
                raise RuntimeError("failed to generate non-conflicting code after 5 attempts")

        self.db.add(AdminLog(
            action="redeem_code_batch_generate",
            admin_id=admin_id, target_user_id=None,
            details={"batch_id": batch_id, "count": count, "amount": amount},
        ))
        await self.db.commit()
        return created

    async def list_by_filter(
        self,
        *,
        batch_id: str | None = None,
        enabled: bool | None = None,
        keyword: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[CreditRedeemCode]:
        stmt = select(CreditRedeemCode).order_by(CreditRedeemCode.created_at.desc())
        if batch_id:
            stmt = stmt.where(CreditRedeemCode.batch_id == batch_id)
        if enabled is not None:
            stmt = stmt.where(CreditRedeemCode.enabled == enabled)
        if keyword:
            stmt = stmt.where(CreditRedeemCode.code.ilike(f"%{keyword}%"))
        stmt = stmt.limit(limit).offset(offset)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def disable(self, code_id: str, admin_id: str) -> CreditRedeemCode:
        result = await self.db.execute(select(CreditRedeemCode).where(CreditRedeemCode.id == code_id))
        code = result.scalars().first()
        if code is None:
            raise ValueError("not found")
        code.enabled = False
        self.db.add(AdminLog(
            action="redeem_code_disable", admin_id=admin_id, target_user_id=None,
            details={"code_id": code_id, "code": code.code},
        ))
        await self.db.commit()
        return code

    async def redeem(self, *, code: str, user_id: str) -> CreditTransaction:
        """Atomic redemption.

        Acquires a row-level lock on the redeem code (`SELECT ... FOR UPDATE`),
        validates all constraints, writes redemption + transaction, increments use_count.
        Any failure raises RedeemError and the transaction is rolled back.
        """
        async with self.db.begin():
            stmt = (
                select(CreditRedeemCode)
                .where(CreditRedeemCode.code == code)
                .with_for_update()
            )
            result = await self.db.execute(stmt)
            row = result.scalars().first()

            if row is None:
                raise RedeemError("code not found")
            if not row.enabled:
                raise RedeemError("code disabled")
            now = datetime.now(UTC)
            if row.expires_at and row.expires_at < now:
                raise RedeemError("code expired")
            if row.valid_from and row.valid_from > now:
                raise RedeemError("code not yet valid")
            if row.use_count >= row.max_uses:
                raise RedeemError("code exhausted")

            user_uses_result = await self.db.execute(
                select(func.count())
                .select_from(CreditRedemption)
                .where(CreditRedemption.code_id == row.id)
                .where(CreditRedemption.user_id == user_id)
            )
            user_uses = int(user_uses_result.scalar_one())
            if user_uses >= row.per_user_limit:
                raise RedeemError("per-user limit reached")

            user_result = await self.db.execute(select(User).where(User.id == user_id))
            user = user_result.scalars().first()
            if user is None:
                raise RedeemError("user not found")

            new_balance = (user.credits or 0) + row.amount
            user.credits = new_balance
            user.total_credits_earned = (user.total_credits_earned or 0) + row.amount

            txn = CreditTransaction(
                user_id=user_id,
                transaction_type=CreditTransactionType.REDEEM_CODE,
                amount=row.amount,
                balance_after=new_balance,
                description=f"兑换码 {row.code[:9]}***",
            )
            self.db.add(txn)
            await self.db.flush()

            redemption = CreditRedemption(
                code_id=row.id, user_id=user_id, transaction_id=txn.id,
            )
            self.db.add(redemption)
            row.use_count += 1

        return txn
```

- [ ] **Step 3: Run tests**

Run: `cd backend && .venv/bin/python -m pytest tests/services/test_credit_redeem_service.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/src/services/credit_redeem_service.py backend/tests/services/test_credit_redeem_service.py
git commit -m "feat(credits): redeem service — batch generate + atomic FOR UPDATE redeem"
```

### Task 4.6: ReferralService

**Files:**
- Create: `backend/src/services/referral_service.py`
- Create: `backend/tests/services/test_referral_service.py`

- [ ] **Step 1: Write failing test**

```python
"""Tests for ReferralService."""
import pytest

from src.database import CreditGrantRuleType
from src.services.referral_service import ReferralService


@pytest.mark.asyncio
async def test_record_referral_creates_row(real_async_db, seed_two_users):
    referrer, referee = seed_two_users
    service = ReferralService(db=real_async_db)
    ref = await service.record(referrer_user_id=referrer.id, referee_user_id=referee.id)
    assert ref.referrer_user_id == referrer.id
    assert ref.referee_user_id == referee.id


@pytest.mark.asyncio
async def test_record_referral_idempotent_per_referee(real_async_db, seed_three_users):
    a, b, c = seed_three_users
    service = ReferralService(db=real_async_db)
    await service.record(referrer_user_id=a.id, referee_user_id=b.id)
    # Try to add b as referee again from c — must fail (unique constraint)
    with pytest.raises(ValueError, match="already"):
        await service.record(referrer_user_id=c.id, referee_user_id=b.id)


@pytest.mark.asyncio
async def test_credit_referee_on_signup_when_rule_enabled(real_async_db, seed_two_users, seed_referred_rule):
    referrer, referee = seed_two_users
    service = ReferralService(db=real_async_db)
    await service.record(referrer_user_id=referrer.id, referee_user_id=referee.id)
    txn = await service.fire_referee_on_signup(referee.id)
    assert txn is not None
    assert txn.amount == seed_referred_rule.amount
```

- [ ] **Step 2: Implement**

```python
"""ReferralService — owns invitation relationship + downstream credit firing."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import (
    CreditGrantRule, CreditGrantRuleType, CreditTransaction, CreditTransactionType,
    Referral, User,
)


class ReferralService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def record(self, *, referrer_user_id: str, referee_user_id: str) -> Referral:
        if referrer_user_id == referee_user_id:
            raise ValueError("cannot refer self")
        ref = Referral(referrer_user_id=referrer_user_id, referee_user_id=referee_user_id)
        self.db.add(ref)
        try:
            await self.db.commit()
        except IntegrityError as e:
            await self.db.rollback()
            raise ValueError("referee already has a referrer") from e
        return ref

    async def get_by_referee(self, referee_user_id: str) -> Referral | None:
        result = await self.db.execute(
            select(Referral).where(Referral.referee_user_id == referee_user_id)
        )
        return result.scalars().first()

    async def fire_referee_on_signup(self, referee_user_id: str) -> CreditTransaction | None:
        ref = await self.get_by_referee(referee_user_id)
        if ref is None:
            return None
        from src.services.credit_grant_rule_service import CreditGrantRuleService
        rule_svc = CreditGrantRuleService(self.db)
        rule = await rule_svc.get_active_rule(CreditGrantRuleType.REFERRAL_REFERRED)
        if rule is None:
            return None
        if rule.config.get("trigger") != "on_signup":
            return None
        return await self._grant(
            user_id=referee_user_id, amount=rule.amount,
            description="邀请奖励：作为被邀请者",
            mark_field="referee_credited_at", referral=ref,
        )

    async def fire_first_task_for_referrer(self, referee_user_id: str) -> CreditTransaction | None:
        ref = await self.get_by_referee(referee_user_id)
        if ref is None:
            return None
        if ref.referee_first_task_at is not None:
            return None  # already fired
        ref.referee_first_task_at = datetime.now(UTC)

        from src.services.credit_grant_rule_service import CreditGrantRuleService
        rule_svc = CreditGrantRuleService(self.db)
        rule = await rule_svc.get_active_rule(CreditGrantRuleType.REFERRAL_REFERRER)
        if rule is None:
            await self.db.commit()
            return None
        if rule.config.get("trigger") != "on_first_task":
            await self.db.commit()
            return None
        txn = await self._grant(
            user_id=ref.referrer_user_id, amount=rule.amount,
            description=f"邀请奖励：被邀请者 {referee_user_id[:8]}*** 首次完成任务",
            mark_field="referrer_credited_at", referral=ref,
        )
        await self.db.commit()
        return txn

    async def _grant(
        self, *, user_id: str, amount: int, description: str,
        mark_field: str, referral: Referral,
    ) -> CreditTransaction:
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalars().first()
        if user is None:
            raise ValueError(f"user {user_id} not found")
        user.credits = (user.credits or 0) + amount
        user.total_credits_earned = (user.total_credits_earned or 0) + amount
        txn = CreditTransaction(
            user_id=user_id,
            transaction_type=CreditTransactionType.REFERRAL_BONUS,
            amount=amount,
            balance_after=user.credits,
            description=description,
        )
        self.db.add(txn)
        setattr(referral, mark_field, datetime.now(UTC))
        return txn
```

- [ ] **Step 3: Run tests + commit**

Run: `cd backend && .venv/bin/python -m pytest tests/services/test_referral_service.py -v`
Expected: PASS

```bash
git add backend/src/services/referral_service.py backend/tests/services/test_referral_service.py
git commit -m "feat(credits): referral service + on-signup / on-first-task triggers"
```

### Task 4.7: Hook into existing register flow

**Files:**
- Modify: `backend/src/gateway/routers/auth.py` (the register endpoint)
- Modify: `backend/src/services/credit_service.py` (or wherever REGISTRATION_BONUS is granted)

- [ ] **Step 1: Find current registration bonus code**

Run: `grep -rn "REGISTRATION_BONUS\|registration_bonus" backend/src --include="*.py" | grep -v __pycache__`
Locate where the hardcoded grant happens (likely in auth router register endpoint or a user-create service).

- [ ] **Step 2: Replace hardcoded amount with rule lookup**

Add this helper to `backend/src/services/credit_grant_rule_service.py`:

```python
    async def apply_registration_bonus(self, user_id: str) -> CreditTransaction | None:
        """Apply the active registration_bonus rule's amount to a freshly-registered user."""
        rule = await self.get_active_rule(CreditGrantRuleType.REGISTRATION_BONUS)
        if rule is None:
            return None
        from src.database import CreditTransaction, CreditTransactionType, User
        from sqlalchemy import select
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalars().first()
        if user is None:
            raise ValueError("user not found")
        user.credits = (user.credits or 0) + rule.amount
        user.total_credits_earned = (user.total_credits_earned or 0) + rule.amount
        txn = CreditTransaction(
            user_id=user_id, transaction_type=CreditTransactionType.REGISTRATION_BONUS,
            amount=rule.amount, balance_after=user.credits,
            description=f"注册奖励 (rule {rule.id[:8]}***)",
        )
        self.db.add(txn)
        return txn
```

In the register endpoint, replace the hardcoded `CreditTransaction(..., amount=200, ...)` block with:

```python
from src.services.credit_grant_rule_service import CreditGrantRuleService
from src.services.referral_service import ReferralService

# ... after user created ...
rule_svc = CreditGrantRuleService(db)
await rule_svc.apply_registration_bonus(user.id)

if invite_code := payload.invite_code:  # NEW: optional invite_code field
    referrer = await resolve_invite_code(db, invite_code)  # implement helper or stub
    if referrer:
        referral_svc = ReferralService(db)
        try:
            await referral_svc.record(referrer_user_id=referrer.id, referee_user_id=user.id)
            await referral_svc.fire_referee_on_signup(user.id)
        except ValueError:
            pass  # referee already has referrer — ignore

await db.commit()
```

(`resolve_invite_code` and the `invite_code` field on the payload model are stubs — they let the backend accept the parameter so it can be wired later when user-side UI ships.)

- [ ] **Step 3: Update register payload model**

In the auth router payload model (Pydantic), add:

```python
invite_code: str | None = None
```

- [ ] **Step 4: Add stub resolver**

```python
async def resolve_invite_code(db: AsyncSession, code: str) -> User | None:
    """Stub for user-side invite code system.

    Out of scope for this Phase (see spec §7). Returns None for now;
    user-side UI / invite-code system will be wired in a follow-up.
    """
    return None
```

- [ ] **Step 5: Run auth tests**

Run: `cd backend && .venv/bin/python -m pytest tests/gateway/test_auth.py -v`
Expected: PASS (registration still grants amount-from-rule; if no rule enabled, grants 0; existing tests may need adjustment if they assert a specific hardcoded amount — update them to seed a rule before asserting).

- [ ] **Step 6: Commit**

```bash
git add backend/src/services/credit_grant_rule_service.py backend/src/gateway/routers/auth.py
git commit -m "feat(credits): register flow reads registration_bonus rule + accepts invite_code (stub)"
```

### Task 4.8: Hook first-task event to referrer trigger

**Files:**
- Modify: wherever task completion is observed (likely `backend/src/services/execution_commit_service.py` or a task lifecycle observer)

- [ ] **Step 1: Locate task-completion event emission**

Run: `grep -rn "task_completed\|first_task\|status.*completed" backend/src/services/execution_commit_service.py | head -10`

If `execution_commit_service.py` handles "execution finished" path, add hook there. Otherwise, search for the place that updates `task_records.status = 'completed'`.

- [ ] **Step 2: Add hook**

At the point of task completion, add:

```python
from src.services.referral_service import ReferralService

# After task marked completed for user_id:
referral_svc = ReferralService(db)
await referral_svc.fire_first_task_for_referrer(user_id)
```

The service is idempotent — if the user has no referral row, or already fired once, it's a no-op.

- [ ] **Step 3: Run integration tests**

Run: `cd backend && .venv/bin/python -m pytest tests/services/ -v -k "execution_commit"`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/src/services/execution_commit_service.py
git commit -m "feat(credits): fire referral_referrer rule on user's first task completion"
```

### Task 4.9: Celery beat task for periodic rules

**Files:**
- Create: `backend/src/task/tasks/credit_periodic.py`
- Modify: `backend/src/task/worker.py` (add beat schedule)

- [ ] **Step 1: Write the periodic task**

```python
"""Celery beat task — scans enabled periodic credit grant rules.

Runs every 5 minutes. For each enabled `periodic` rule, checks its cron schedule
against last_triggered_at to decide whether it's due. If due, applies target_filter
to find users, batch-grants the rule.amount to each, updates last_triggered_at.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from croniter import croniter
from sqlalchemy import select

from src.database import (
    CreditGrantRule, CreditGrantRuleType, CreditTransaction, CreditTransactionType,
    User, get_db_session,
)
from src.task.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _process_periodic_rules() -> dict[str, int]:
    now = datetime.now(UTC)
    summary = {"rules_evaluated": 0, "rules_fired": 0, "users_granted": 0}
    async with get_db_session() as db:
        result = await db.execute(
            select(CreditGrantRule)
            .where(CreditGrantRule.rule_type == CreditGrantRuleType.PERIODIC)
            .where(CreditGrantRule.enabled == True)  # noqa: E712
        )
        rules = list(result.scalars().all())

        for rule in rules:
            summary["rules_evaluated"] += 1
            cron_expr = rule.config.get("cron")
            if not cron_expr:
                logger.warning("rule %s missing cron in config; skipping", rule.id)
                continue

            base = rule.last_triggered_at or (now - timedelta(days=30))
            try:
                itr = croniter(cron_expr, base)
                next_fire = itr.get_next(datetime).replace(tzinfo=UTC)
            except Exception:
                logger.exception("rule %s invalid cron %r; skipping", rule.id, cron_expr)
                continue

            if next_fire > now:
                continue  # not yet due

            tf = rule.config.get("target_filter", {})
            user_stmt = select(User)
            active_within_days = tf.get("active_within_days")
            if active_within_days is not None:
                threshold = now - timedelta(days=int(active_within_days))
                user_stmt = user_stmt.where(User.last_login >= threshold)
            role = tf.get("role")
            if role == "user":
                user_stmt = user_stmt.where(User.is_superuser == False)  # noqa: E712
            elif role == "admin":
                user_stmt = user_stmt.where(User.is_superuser == True)  # noqa: E712

            user_result = await db.execute(user_stmt)
            users = list(user_result.scalars().all())

            for user in users:
                user.credits = (user.credits or 0) + rule.amount
                user.total_credits_earned = (user.total_credits_earned or 0) + rule.amount
                db.add(CreditTransaction(
                    user_id=user.id,
                    transaction_type=CreditTransactionType.ADMIN_GRANT,
                    amount=rule.amount,
                    balance_after=user.credits,
                    description=f"周期发放（rule {rule.id[:8]}***）",
                ))
                summary["users_granted"] += 1

            rule.last_triggered_at = now
            summary["rules_fired"] += 1

        await db.commit()
    return summary


@celery_app.task(name="credit_periodic.process_credit_grant_rules")
def process_credit_grant_rules() -> dict[str, int]:
    return asyncio.run(_process_periodic_rules())
```

(`celery_app` must exist — see [backend/src/task/](../../backend/src/task/) for actual import path. Adjust if it lives at `src.task.celery_app` or similar.)

- [ ] **Step 2: Add beat schedule**

In the celery configuration (likely `backend/src/task/celery_app.py` or `worker.py`), add:

```python
celery_app.conf.beat_schedule = {
    **getattr(celery_app.conf, "beat_schedule", {}),
    "process-credit-grant-rules": {
        "task": "credit_periodic.process_credit_grant_rules",
        "schedule": 300.0,  # every 5 minutes
    },
}
```

- [ ] **Step 3: Verify celery beat is in deployment**

Run: `grep -A 3 "beat\|celery" docker-compose.yml`
Expected: find a beat service. If absent, the spec's risk #2 has materialized — add a beat service block:

```yaml
celery_beat:
  build: ./backend
  command: celery -A src.task.celery_app beat --loglevel=info
  depends_on:
    - redis
    - postgres
  env_file: .env
```

(Coordinate with the user before changing docker-compose.yml since it affects deployment.)

- [ ] **Step 4: Manual test**

Seed a periodic rule with cron `* * * * *` (every minute) and amount 1, then in worker shell:

```python
from src.task.tasks.credit_periodic import process_credit_grant_rules
print(process_credit_grant_rules())
```

Expected: `{"rules_evaluated": 1, "rules_fired": 1, "users_granted": N}` and a CreditTransaction row appears.

- [ ] **Step 5: Commit**

```bash
git add backend/src/task/tasks/credit_periodic.py backend/src/task/celery_app.py docker-compose.yml
git commit -m "feat(credits): celery beat task for periodic grant rules"
```

### Task 4.10: Admin routers — credit rules + redeem codes + user-side redeem

**Files:**
- Create: `backend/src/gateway/routers/admin_credit_rules.py`
- Create: `backend/src/gateway/routers/admin_redeem_codes.py`
- Create: `backend/src/gateway/routers/credits_redeem.py`
- Modify: `backend/src/gateway/main.py`

- [ ] **Step 1: Write admin_credit_rules.py**

```python
"""Admin endpoints for credit grant rules."""

from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Response

from src.database import CreditGrantRuleType, User, get_db_session
from src.gateway.auth_dependencies import get_current_admin
from src.services.credit_grant_rule_service import CreditGrantRuleService

router = APIRouter(prefix="/admin/credit-rules", tags=["admin", "credits"])


async def _service():
    async with get_db_session() as db:
        yield CreditGrantRuleService(db)


def _to_dict(rule) -> dict[str, Any]:
    return {
        "id": rule.id, "name": rule.name, "rule_type": rule.rule_type.value,
        "enabled": rule.enabled, "amount": rule.amount, "description": rule.description,
        "config": rule.config, "last_triggered_at": rule.last_triggered_at,
        "created_at": rule.created_at, "updated_at": rule.updated_at,
    }


@router.get("")
async def list_rules(
    service: CreditGrantRuleService = Depends(_service),
    _admin: User = Depends(get_current_admin),
) -> dict[str, Any]:
    rules = await service.list_all()
    return {"items": [_to_dict(r) for r in rules], "total": len(rules)}


@router.post("")
async def create_rule(
    payload: dict = Body(...),
    service: CreditGrantRuleService = Depends(_service),
    admin: User = Depends(get_current_admin),
) -> dict[str, Any]:
    try:
        rule = await service.create(
            name=payload["name"],
            rule_type=CreditGrantRuleType(payload["rule_type"]),
            amount=int(payload["amount"]),
            config=payload.get("config", {}),
            description=payload.get("description"),
            admin_id=admin.id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return _to_dict(rule)


@router.put("/{rule_id}")
async def update_rule(
    rule_id: str,
    payload: dict = Body(...),
    service: CreditGrantRuleService = Depends(_service),
    admin: User = Depends(get_current_admin),
) -> dict[str, Any]:
    try:
        rule = await service.update(
            rule_id=rule_id,
            name=payload["name"],
            amount=int(payload["amount"]),
            config=payload.get("config", {}),
            description=payload.get("description"),
            admin_id=admin.id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return _to_dict(rule)


@router.post("/{rule_id}/toggle")
async def toggle_rule(
    rule_id: str,
    service: CreditGrantRuleService = Depends(_service),
    admin: User = Depends(get_current_admin),
) -> dict[str, Any]:
    try:
        rule = await service.toggle(rule_id, admin_id=admin.id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return _to_dict(rule)


@router.delete("/{rule_id}")
async def delete_rule(
    rule_id: str,
    service: CreditGrantRuleService = Depends(_service),
    admin: User = Depends(get_current_admin),
) -> Response:
    try:
        await service.delete(rule_id, admin_id=admin.id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return Response(status_code=204)
```

- [ ] **Step 2: Write admin_redeem_codes.py**

```python
"""Admin endpoints for redeem codes."""

from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response

from src.database import User, get_db_session
from src.gateway.auth_dependencies import get_current_admin
from src.services.credit_redeem_service import CreditRedeemService

router = APIRouter(prefix="/admin/redeem-codes", tags=["admin", "credits"])


async def _service():
    async with get_db_session() as db:
        yield CreditRedeemService(db)


def _to_dict(code) -> dict[str, Any]:
    return {
        "id": code.id, "code": code.code, "amount": code.amount,
        "max_uses": code.max_uses, "use_count": code.use_count,
        "per_user_limit": code.per_user_limit, "expires_at": code.expires_at,
        "valid_from": code.valid_from, "enabled": code.enabled,
        "batch_id": code.batch_id, "description": code.description,
        "created_at": code.created_at,
    }


@router.get("")
async def list_codes(
    batch_id: str | None = Query(None),
    enabled: bool | None = Query(None),
    keyword: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    service: CreditRedeemService = Depends(_service),
    _admin: User = Depends(get_current_admin),
) -> dict[str, Any]:
    codes = await service.list_by_filter(
        batch_id=batch_id, enabled=enabled, keyword=keyword,
        limit=page_size, offset=(page - 1) * page_size,
    )
    return {"items": [_to_dict(c) for c in codes], "page": page}


@router.post("/batch")
async def batch_generate(
    payload: dict = Body(...),
    service: CreditRedeemService = Depends(_service),
    admin: User = Depends(get_current_admin),
) -> dict[str, Any]:
    try:
        expires_at_raw = payload.get("expires_at")
        expires_at = datetime.fromisoformat(expires_at_raw) if expires_at_raw else None
        codes = await service.batch_generate(
            amount=int(payload["amount"]),
            count=int(payload["count"]),
            max_uses=int(payload.get("max_uses", 1)),
            per_user_limit=int(payload.get("per_user_limit", 1)),
            expires_at=expires_at,
            description=payload.get("description"),
            admin_id=admin.id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {
        "batch_id": codes[0].batch_id if codes else None,
        "items": [_to_dict(c) for c in codes],
    }


@router.post("/{code_id}/disable")
async def disable_code(
    code_id: str,
    service: CreditRedeemService = Depends(_service),
    admin: User = Depends(get_current_admin),
) -> dict[str, Any]:
    try:
        code = await service.disable(code_id, admin_id=admin.id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    return _to_dict(code)


@router.get("/export.csv")
async def export_csv(
    batch_id: str,
    service: CreditRedeemService = Depends(_service),
    _admin: User = Depends(get_current_admin),
) -> Response:
    codes = await service.list_by_filter(batch_id=batch_id, limit=10000)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["code", "amount", "expires_at", "max_uses", "per_user_limit", "batch_id"])
    for c in codes:
        writer.writerow([
            c.code, c.amount,
            c.expires_at.isoformat() if c.expires_at else "",
            c.max_uses, c.per_user_limit, c.batch_id or "",
        ])
    return Response(
        content=buf.getvalue().encode("utf-8-sig"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="redeem-codes-{batch_id}.csv"'},
    )
```

- [ ] **Step 3: Write credits_redeem.py (user-side)**

```python
"""User-facing redeem endpoint."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

from src.database import User, get_db_session
from src.gateway.auth_dependencies import get_current_user
from src.services.credit_redeem_service import CreditRedeemService, RedeemError

router = APIRouter(prefix="/credits", tags=["credits"])


async def _service():
    async with get_db_session() as db:
        yield CreditRedeemService(db)


@router.post("/redeem")
async def redeem(
    payload: dict = Body(...),
    service: CreditRedeemService = Depends(_service),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    code = (payload.get("code") or "").strip().upper()
    if not code:
        raise HTTPException(400, "code required")
    try:
        txn = await service.redeem(code=code, user_id=user.id)
    except RedeemError as e:
        raise HTTPException(400, str(e)) from e
    return {
        "amount": txn.amount,
        "balance_after": txn.balance_after,
        "transaction_id": txn.id,
    }
```

- [ ] **Step 4: Register routers**

In the FastAPI app init, add:

```python
from src.gateway.routers.admin_credit_rules import router as admin_credit_rules_router
from src.gateway.routers.admin_redeem_codes import router as admin_redeem_codes_router
from src.gateway.routers.credits_redeem import router as credits_redeem_router

app.include_router(admin_credit_rules_router)
app.include_router(admin_redeem_codes_router)
app.include_router(credits_redeem_router)
```

- [ ] **Step 5: Commit**

```bash
git add backend/src/gateway/routers/
git commit -m "feat(admin): credit rules + redeem codes routers + user redeem endpoint"
```

### Task 4.11: Frontend API client for credits

**Files:**
- Create: `frontend/lib/api/admin-credit-rules.ts`
- Create: `frontend/lib/api/admin-redeem-codes.ts`

- [ ] **Step 1: Write admin-credit-rules.ts**

```typescript
import { authorizedFetch } from "@/lib/api/client";

export type RuleType = "registration_bonus" | "referral_referrer" | "referral_referred" | "periodic";

export interface CreditGrantRule {
  id: string;
  name: string;
  rule_type: RuleType;
  enabled: boolean;
  amount: number;
  description: string | null;
  config: Record<string, unknown>;
  last_triggered_at: string | null;
  created_at: string;
  updated_at: string;
}

export async function listCreditRules(): Promise<{ items: CreditGrantRule[]; total: number }> {
  return authorizedFetch("/admin/credit-rules");
}

export async function createCreditRule(payload: {
  name: string;
  rule_type: RuleType;
  amount: number;
  config: Record<string, unknown>;
  description?: string;
}): Promise<CreditGrantRule> {
  return authorizedFetch("/admin/credit-rules", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function updateCreditRule(
  id: string,
  payload: { name: string; amount: number; config: Record<string, unknown>; description?: string }
): Promise<CreditGrantRule> {
  return authorizedFetch(`/admin/credit-rules/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function toggleCreditRule(id: string): Promise<CreditGrantRule> {
  return authorizedFetch(`/admin/credit-rules/${id}/toggle`, { method: "POST" });
}

export async function deleteCreditRule(id: string): Promise<void> {
  await authorizedFetch(`/admin/credit-rules/${id}`, { method: "DELETE" });
}
```

- [ ] **Step 2: Write admin-redeem-codes.ts**

```typescript
import { authorizedFetch } from "@/lib/api/client";

export interface RedeemCode {
  id: string;
  code: string;
  amount: number;
  max_uses: number;
  use_count: number;
  per_user_limit: number;
  expires_at: string | null;
  enabled: boolean;
  batch_id: string | null;
  description: string | null;
  created_at: string;
}

export async function listRedeemCodes(params: {
  batch_id?: string; enabled?: boolean; keyword?: string; page?: number; page_size?: number;
}): Promise<{ items: RedeemCode[]; page: number }> {
  const query = new URLSearchParams();
  if (params.batch_id) query.set("batch_id", params.batch_id);
  if (params.enabled !== undefined) query.set("enabled", String(params.enabled));
  if (params.keyword) query.set("keyword", params.keyword);
  if (params.page) query.set("page", String(params.page));
  if (params.page_size) query.set("page_size", String(params.page_size));
  return authorizedFetch(`/admin/redeem-codes?${query}`);
}

export async function batchGenerateRedeemCodes(payload: {
  amount: number; count: number; max_uses: number; per_user_limit: number;
  expires_at: string | null; description: string | null;
}): Promise<{ batch_id: string; items: RedeemCode[] }> {
  return authorizedFetch("/admin/redeem-codes/batch", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function disableRedeemCode(id: string): Promise<RedeemCode> {
  return authorizedFetch(`/admin/redeem-codes/${id}/disable`, { method: "POST" });
}
```

- [ ] **Step 3: Typecheck + commit**

Run: `cd frontend && npm run typecheck`
Expected: PASS

```bash
git add frontend/lib/api/admin-credit-rules.ts frontend/lib/api/admin-redeem-codes.ts
git commit -m "feat(frontend): admin credit rules + redeem codes API client"
```

### Task 4.12: Frontend rules page

**Files:**
- Create: `frontend/app/dashboard/admin/credits/rules/page.tsx`
- Create: `frontend/app/dashboard/admin/credits/rules/CreditRuleDialog.tsx`

- [ ] **Step 1: Write CreditRuleDialog**

```typescript
"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  createCreditRule, updateCreditRule, type CreditGrantRule, type RuleType,
} from "@/lib/api/admin-credit-rules";

interface Props {
  open: boolean;
  rule: CreditGrantRule | null;
  onClose: (refresh: boolean) => void;
}

export function CreditRuleDialog({ open, rule, onClose }: Props) {
  const isEdit = rule !== null;
  const [name, setName] = useState(rule?.name ?? "");
  const [ruleType, setRuleType] = useState<RuleType>(rule?.rule_type ?? "registration_bonus");
  const [amount, setAmount] = useState(String(rule?.amount ?? 100));
  const [description, setDescription] = useState(rule?.description ?? "");
  const [trigger, setTrigger] = useState<string>(
    (rule?.config?.trigger as string) ?? (ruleType === "referral_referrer" ? "on_first_task" : "on_signup")
  );
  const [cron, setCron] = useState((rule?.config?.cron as string) ?? "0 0 * * 1");
  const [activeWithinDays, setActiveWithinDays] = useState(
    String((rule?.config?.target_filter as any)?.active_within_days ?? 30)
  );
  const [role, setRole] = useState((rule?.config?.target_filter as any)?.role ?? "user");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const buildConfig = (): Record<string, unknown> => {
    switch (ruleType) {
      case "registration_bonus":
        return {};
      case "referral_referrer":
        return { trigger };
      case "referral_referred":
        return { trigger: "on_signup" };
      case "periodic":
        return {
          cron,
          target_filter: {
            active_within_days: parseInt(activeWithinDays, 10) || null,
            role: role || null,
          },
        };
    }
  };

  const handleSubmit = async () => {
    setError(null);
    setLoading(true);
    try {
      const payload = { name, amount: parseInt(amount, 10), config: buildConfig(), description };
      if (isEdit) {
        await updateCreditRule(rule!.id, payload);
      } else {
        await createCreditRule({ ...payload, rule_type: ruleType });
      }
      onClose(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(false); }}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{isEdit ? "编辑规则" : "新建规则"}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1">
            <Label>规则名</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label>类型</Label>
            <Select value={ruleType} onValueChange={(v) => setRuleType(v as RuleType)} disabled={isEdit}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="registration_bonus">注册奖励</SelectItem>
                <SelectItem value="referral_referrer">邀请者奖励</SelectItem>
                <SelectItem value="referral_referred">被邀请者奖励</SelectItem>
                <SelectItem value="periodic">周期发放</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label>积分数量</Label>
            <Input type="number" min={1} value={amount} onChange={(e) => setAmount(e.target.value)} />
          </div>

          {ruleType === "referral_referrer" && (
            <div className="space-y-1">
              <Label>触发时机</Label>
              <Select value={trigger} onValueChange={setTrigger}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="on_signup">被邀请者注册时</SelectItem>
                  <SelectItem value="on_first_task">被邀请者首次完成任务时（推荐）</SelectItem>
                </SelectContent>
              </Select>
            </div>
          )}

          {ruleType === "periodic" && (
            <>
              <div className="space-y-1">
                <Label>Cron 表达式</Label>
                <Input value={cron} onChange={(e) => setCron(e.target.value)} placeholder="0 0 * * 1" />
                <p className="text-xs text-[var(--text-muted)]">每周一 00:00：<code>0 0 * * 1</code></p>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1">
                  <Label>活跃天数内</Label>
                  <Input type="number" min={1} value={activeWithinDays} onChange={(e) => setActiveWithinDays(e.target.value)} />
                </div>
                <div className="space-y-1">
                  <Label>角色</Label>
                  <Select value={role} onValueChange={setRole}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="user">普通用户</SelectItem>
                      <SelectItem value="admin">管理员</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </>
          )}

          <div className="space-y-1">
            <Label>说明（可选）</Label>
            <Input value={description} onChange={(e) => setDescription(e.target.value)} />
          </div>

          {error && <div className="text-sm text-rose-600">{error}</div>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onClose(false)} disabled={loading}>取消</Button>
          <Button onClick={handleSubmit} disabled={loading}>
            {loading && <Loader2 className="w-4 h-4 mr-1 animate-spin" />}
            {isEdit ? "保存" : "创建"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 2: Write rules/page.tsx**

```typescript
"use client";

import { useEffect, useState } from "react";
import { Plus } from "lucide-react";

import { AdminPageHeader } from "../../components/AdminPageHeader";
import { CreditRuleDialog } from "./CreditRuleDialog";
import { Button } from "@/components/ui/button";
import {
  deleteCreditRule, listCreditRules, toggleCreditRule, type CreditGrantRule,
} from "@/lib/api/admin-credit-rules";

const RULE_TYPE_LABEL = {
  registration_bonus: "注册奖励",
  referral_referrer: "邀请者奖励",
  referral_referred: "被邀请者奖励",
  periodic: "周期发放",
} as const;

export default function CreditRulesPage() {
  const [rules, setRules] = useState<CreditGrantRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<CreditGrantRule | null>(null);
  const [reloadNonce, setReloadNonce] = useState(0);

  useEffect(() => {
    setLoading(true);
    listCreditRules()
      .then((res) => setRules(res.items))
      .finally(() => setLoading(false));
  }, [reloadNonce]);

  const handleToggle = async (rule: CreditGrantRule) => {
    await toggleCreditRule(rule.id);
    setReloadNonce((v) => v + 1);
  };

  const handleDelete = async (rule: CreditGrantRule) => {
    if (!confirm(`确认删除规则 "${rule.name}"？`)) return;
    await deleteCreditRule(rule.id);
    setReloadNonce((v) => v + 1);
  };

  return (
    <>
      <AdminPageHeader
        title="发放规则"
        description={`共 ${rules.length} 条`}
        actions={
          <Button size="sm" onClick={() => { setEditing(null); setDialogOpen(true); }}>
            <Plus className="w-4 h-4 mr-1" /> 新建规则
          </Button>
        }
      />

      <div className="route-card rounded-2xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left border-b border-[var(--border-default)]">
              <th className="px-4 py-3 w-12"></th>
              <th className="px-4 py-3">规则名</th>
              <th className="px-4 py-3">类型</th>
              <th className="px-4 py-3">配置</th>
              <th className="px-4 py-3 text-right">积分</th>
              <th className="px-4 py-3 w-24 text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            {rules.map((rule) => (
              <tr key={rule.id} className="border-t border-[var(--border-default)]/50">
                <td className="px-4 py-3">
                  <button
                    onClick={() => handleToggle(rule)}
                    className={`inline-flex w-2.5 h-2.5 rounded-full ${rule.enabled ? "bg-emerald-500" : "bg-slate-400"}`}
                  />
                </td>
                <td className="px-4 py-3 text-[var(--text-primary)]">{rule.name}</td>
                <td className="px-4 py-3 text-[var(--text-secondary)]">{RULE_TYPE_LABEL[rule.rule_type]}</td>
                <td className="px-4 py-3 text-xs text-[var(--text-muted)] font-mono">
                  {summarizeConfig(rule)}
                </td>
                <td className="px-4 py-3 text-right font-medium">+{rule.amount}</td>
                <td className="px-4 py-3 text-right space-x-2">
                  <button onClick={() => { setEditing(rule); setDialogOpen(true); }} className="text-[var(--accent-primary)] hover:underline">编辑</button>
                  <button onClick={() => handleDelete(rule)} className="text-rose-600 hover:underline">删除</button>
                </td>
              </tr>
            ))}
            {!loading && rules.length === 0 && (
              <tr><td colSpan={6} className="px-4 py-6 text-center text-[var(--text-muted)]">暂无规则</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <CreditRuleDialog
        open={dialogOpen}
        rule={editing}
        onClose={(refresh) => {
          setDialogOpen(false);
          setEditing(null);
          if (refresh) setReloadNonce((v) => v + 1);
        }}
      />
    </>
  );
}

function summarizeConfig(rule: CreditGrantRule): string {
  if (rule.rule_type === "periodic") {
    const tf = (rule.config?.target_filter as any) ?? {};
    return `${rule.config?.cron ?? "-"} · 活跃 ${tf.active_within_days ?? "-"} 天 · ${tf.role ?? "-"}`;
  }
  if (rule.rule_type === "referral_referrer") {
    return `trigger: ${rule.config?.trigger}`;
  }
  return "";
}
```

- [ ] **Step 3: Smoke test + commit**

Manual: navigate to `/dashboard/admin/credits/rules`, create one rule of each type, edit, toggle, delete.

```bash
git add frontend/app/dashboard/admin/credits/rules
git commit -m "feat(admin): credit grant rules page"
```

### Task 4.13: Frontend redeem-codes page

**Files:**
- Create: `frontend/app/dashboard/admin/credits/redeem-codes/page.tsx`
- Create: `frontend/app/dashboard/admin/credits/redeem-codes/BatchGenerateDialog.tsx`

- [ ] **Step 1: Write BatchGenerateDialog**

```typescript
"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { batchGenerateRedeemCodes } from "@/lib/api/admin-redeem-codes";

interface Props {
  open: boolean;
  onClose: (batchId: string | null) => void;
}

export function BatchGenerateDialog({ open, onClose }: Props) {
  const [amount, setAmount] = useState("200");
  const [count, setCount] = useState("10");
  const [maxUses, setMaxUses] = useState("1");
  const [perUserLimit, setPerUserLimit] = useState("1");
  const [expiresAt, setExpiresAt] = useState("");
  const [description, setDescription] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleGenerate = async () => {
    setError(null);
    setLoading(true);
    try {
      const res = await batchGenerateRedeemCodes({
        amount: parseInt(amount, 10),
        count: parseInt(count, 10),
        max_uses: parseInt(maxUses, 10),
        per_user_limit: parseInt(perUserLimit, 10),
        expires_at: expiresAt ? new Date(expiresAt).toISOString() : null,
        description: description.trim() || null,
      });

      const link = document.createElement("a");
      link.href = `/admin/redeem-codes/export.csv?batch_id=${encodeURIComponent(res.batch_id)}`;
      link.download = `redeem-codes-${res.batch_id}.csv`;
      link.click();

      onClose(res.batch_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "生成失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(null); }}>
      <DialogContent>
        <DialogHeader><DialogTitle>批量生成兑换码</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1"><Label>每码积分</Label><Input type="number" min={1} value={amount} onChange={(e) => setAmount(e.target.value)} /></div>
            <div className="space-y-1"><Label>数量</Label><Input type="number" min={1} max={10000} value={count} onChange={(e) => setCount(e.target.value)} /></div>
            <div className="space-y-1"><Label>单码可用次数</Label><Input type="number" min={1} value={maxUses} onChange={(e) => setMaxUses(e.target.value)} /></div>
            <div className="space-y-1"><Label>单用户上限</Label><Input type="number" min={1} value={perUserLimit} onChange={(e) => setPerUserLimit(e.target.value)} /></div>
          </div>
          <div className="space-y-1"><Label>有效期（可选）</Label><Input type="date" value={expiresAt} onChange={(e) => setExpiresAt(e.target.value)} /></div>
          <div className="space-y-1"><Label>批次说明</Label><Input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="例如：双 11 营销" /></div>
          {error && <div className="text-sm text-rose-600">{error}</div>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onClose(null)} disabled={loading}>取消</Button>
          <Button onClick={handleGenerate} disabled={loading}>
            {loading && <Loader2 className="w-4 h-4 mr-1 animate-spin" />}
            生成 {count} 个码并下载 CSV
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 2: Write redeem-codes/page.tsx**

```typescript
"use client";

import { useEffect, useState } from "react";
import { Plus } from "lucide-react";

import { AdminPageHeader } from "../../components/AdminPageHeader";
import { BatchGenerateDialog } from "./BatchGenerateDialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  disableRedeemCode, listRedeemCodes, type RedeemCode,
} from "@/lib/api/admin-redeem-codes";

function formatDate(s: string | null) {
  if (!s) return "-";
  return new Date(s).toLocaleString();
}

export default function RedeemCodesPage() {
  const [codes, setCodes] = useState<RedeemCode[]>([]);
  const [loading, setLoading] = useState(true);
  const [batchId, setBatchId] = useState("");
  const [keyword, setKeyword] = useState("");
  const [page, setPage] = useState(1);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [reloadNonce, setReloadNonce] = useState(0);

  useEffect(() => {
    setLoading(true);
    listRedeemCodes({
      batch_id: batchId || undefined, keyword: keyword || undefined,
      page, page_size: 50,
    })
      .then((res) => setCodes(res.items))
      .finally(() => setLoading(false));
  }, [batchId, keyword, page, reloadNonce]);

  const handleDisable = async (code: RedeemCode) => {
    if (!confirm(`下线兑换码 ${code.code}？`)) return;
    await disableRedeemCode(code.id);
    setReloadNonce((v) => v + 1);
  };

  return (
    <>
      <AdminPageHeader
        title="兑换码"
        actions={
          <Button size="sm" onClick={() => setDialogOpen(true)}>
            <Plus className="w-4 h-4 mr-1" /> 批量生成
          </Button>
        }
      />

      <div className="route-card rounded-2xl p-4 mb-4 flex flex-wrap gap-2">
        <Input placeholder="批次 ID" value={batchId} onChange={(e) => { setBatchId(e.target.value); setPage(1); }} className="max-w-xs" />
        <Input placeholder="关键词" value={keyword} onChange={(e) => { setKeyword(e.target.value); setPage(1); }} className="max-w-xs" />
      </div>

      <div className="route-card rounded-2xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left border-b border-[var(--border-default)]">
              <th className="px-4 py-3 w-12"></th>
              <th className="px-4 py-3">兑换码</th>
              <th className="px-4 py-3 text-right">积分</th>
              <th className="px-4 py-3">使用情况</th>
              <th className="px-4 py-3">到期时间</th>
              <th className="px-4 py-3">批次</th>
              <th className="px-4 py-3 w-20 text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            {codes.map((c) => (
              <tr key={c.id} className="border-t border-[var(--border-default)]/50">
                <td className="px-4 py-3">
                  <span className={`inline-flex w-2.5 h-2.5 rounded-full ${c.enabled ? "bg-emerald-500" : "bg-slate-400"}`} />
                </td>
                <td className="px-4 py-3 font-mono text-xs">{c.code}</td>
                <td className="px-4 py-3 text-right font-medium">+{c.amount}</td>
                <td className="px-4 py-3 text-[var(--text-secondary)]">{c.use_count}/{c.max_uses}</td>
                <td className="px-4 py-3 text-[var(--text-secondary)]">{formatDate(c.expires_at)}</td>
                <td className="px-4 py-3 font-mono text-xs text-[var(--text-muted)]">{c.batch_id?.slice(0, 8) ?? "-"}</td>
                <td className="px-4 py-3 text-right">
                  {c.enabled && <button onClick={() => handleDisable(c)} className="text-rose-600 hover:underline text-sm">下线</button>}
                </td>
              </tr>
            ))}
            {!loading && codes.length === 0 && (
              <tr><td colSpan={7} className="px-4 py-6 text-center text-[var(--text-muted)]">暂无兑换码</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="mt-4 flex justify-between items-center">
        <span className="text-xs text-[var(--text-muted)]">第 {page} 页</span>
        <div className="space-x-2">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>上一页</Button>
          <Button variant="outline" size="sm" disabled={codes.length < 50} onClick={() => setPage(page + 1)}>下一页</Button>
        </div>
      </div>

      <BatchGenerateDialog
        open={dialogOpen}
        onClose={(batch) => {
          setDialogOpen(false);
          if (batch) setReloadNonce((v) => v + 1);
        }}
      />
    </>
  );
}
```

- [ ] **Step 3: Smoke test + commit**

Manual: generate 5 codes, verify CSV downloads, verify list shows them, disable one.

```bash
git add frontend/app/dashboard/admin/credits/redeem-codes
git commit -m "feat(admin): redeem codes page + batch generate dialog"
```

---

## Phase 5 — Analytics

**Goal:** 4 chart panels (user growth, capability hotness, credits/token trends, workspace/task distribution), backed by real-time SQL aggregation with Redis caching (TTL 5min).

**Pre-conditions:** Phase 2 merged (admin IA exists). Independent of P3 / P4.

### Task 5.1: Migration 052 — analytics indexes

**Files:**
- Create: `backend/alembic/versions/052_analytics_indexes.py`

- [ ] **Step 1: Write migration**

```python
"""Indexes for analytics aggregation queries.

Revision ID: 052_analytics_indexes
Revises: 051_credit_grant_rules_and_redeem_codes
Create Date: 2026-05-14
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "052_analytics_indexes"
down_revision: str | None = "051_credit_grant_rules_and_redeem_codes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_executions_created_at_status "
        "ON executions (created_at, status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_messages_user_created "
        "ON messages (user_id, created_at) WHERE user_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_messages_user_created")
    op.execute("DROP INDEX IF EXISTS idx_executions_created_at_status")
```

(If `messages` table doesn't have a `user_id` column directly — it might join via `thread.user_id` — adjust the index accordingly. Inspect schema first: `cd backend && .venv/bin/python -c "from src.database.models.thread import Message; print(Message.__table__.columns.keys())"`)

- [ ] **Step 2: Run + commit**

Run: `cd backend && .venv/bin/alembic upgrade head`
Expected: indexes created.

```bash
git add backend/alembic/versions/052_analytics_indexes.py
git commit -m "feat(db): analytics query indexes"
```

### Task 5.2: AdminAnalyticsService — 4 aggregation methods

**Files:**
- Create: `backend/src/services/admin_analytics_service.py`
- Create: `backend/tests/services/test_admin_analytics_service.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for AdminAnalyticsService."""
from datetime import UTC, datetime, timedelta

import pytest

from src.services.admin_analytics_service import AdminAnalyticsService


@pytest.mark.asyncio
async def test_user_growth_returns_kpis_and_series(real_async_db, seed_users_messages):
    service = AdminAnalyticsService(real_async_db)
    res = await service.user_growth(range_days=7, granularity="day")
    assert "kpis" in res
    assert {"dau", "wau", "retention_7d", "retention_30d"} <= set(res["kpis"].keys())
    assert isinstance(res["time_series"], list)
    assert isinstance(res["retention_matrix"], list)


@pytest.mark.asyncio
async def test_capabilities_usage_returns_items(real_async_db, seed_executions):
    service = AdminAnalyticsService(real_async_db)
    res = await service.capabilities_usage(range_days=30)
    assert "items" in res
    for item in res["items"]:
        assert {"capability_id", "workspace_type", "calls", "success_rate", "avg_duration_seconds"} <= set(item.keys())


@pytest.mark.asyncio
async def test_credits_tokens_trends_kpis(real_async_db, seed_credit_transactions):
    service = AdminAnalyticsService(real_async_db)
    res = await service.credits_tokens_trends(range_days=30, granularity="day")
    assert {"total_issued", "total_spent", "current_pool"} <= set(res["kpis"].keys())
    assert isinstance(res["credit_series"], list)


@pytest.mark.asyncio
async def test_workspaces_tasks_distribution(real_async_db, seed_workspaces_tasks):
    service = AdminAnalyticsService(real_async_db)
    res = await service.workspaces_tasks(range_days=30)
    assert "workspace_by_type" in res
    assert "task_by_status" in res
    assert "failed_top_errors" in res
```

- [ ] **Step 2: Implement service**

```python
"""AdminAnalyticsService — 4 aggregation methods for admin analytics panels.

All queries operate on real-time SQL against PG. Callers wrap with Redis cache decorator.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from sqlalchemy import and_, case, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import (
    CreditTransaction, CreditTransactionType, TaskRecord, User, Workspace,
)


Granularity = Literal["day", "week"]


def _date_trunc(granularity: Granularity, col: Any) -> Any:
    return func.date_trunc(granularity, col)


class AdminAnalyticsService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def user_growth(self, *, range_days: int, granularity: Granularity = "day") -> dict[str, Any]:
        now = datetime.now(UTC)
        since = now - timedelta(days=range_days)

        signups_stmt = (
            select(
                _date_trunc(granularity, User.created_at).label("bucket"),
                func.count().label("signups"),
            )
            .where(User.created_at >= since)
            .group_by("bucket")
            .order_by("bucket")
        )
        signups_rows = (await self.db.execute(signups_stmt)).all()

        from src.database import Message  # adjust import path if Message lives elsewhere
        dau_stmt = (
            select(
                _date_trunc(granularity, Message.created_at).label("bucket"),
                func.count(distinct(Message.user_id)).label("dau"),
            )
            .where(Message.created_at >= since)
            .where(Message.user_id.is_not(None))
            .group_by("bucket")
            .order_by("bucket")
        )
        dau_rows = (await self.db.execute(dau_stmt)).all()

        signups_map = {r.bucket.isoformat(): int(r.signups) for r in signups_rows}
        dau_map = {r.bucket.isoformat(): int(r.dau) for r in dau_rows}
        all_buckets = sorted(set(signups_map) | set(dau_map))
        time_series = [
            {"date": b, "signups": signups_map.get(b, 0), "dau": dau_map.get(b, 0)}
            for b in all_buckets
        ]

        dau_today = await self._dau_in_window(now - timedelta(days=1), now)
        wau = await self._dau_in_window(now - timedelta(days=7), now)
        retention_7d = await self._retention(window_days=7)
        retention_30d = await self._retention(window_days=30)

        retention_matrix = await self._retention_matrix(weeks=6)

        return {
            "kpis": {"dau": dau_today, "wau": wau, "retention_7d": retention_7d, "retention_30d": retention_30d},
            "time_series": time_series,
            "retention_matrix": retention_matrix,
        }

    async def _dau_in_window(self, start: datetime, end: datetime) -> int:
        from src.database import Message
        result = await self.db.execute(
            select(func.count(distinct(Message.user_id)))
            .where(Message.created_at >= start)
            .where(Message.created_at < end)
            .where(Message.user_id.is_not(None))
        )
        return int(result.scalar() or 0)

    async def _retention(self, *, window_days: int) -> float:
        """Returns the fraction of users signed up window_days ago who are active today."""
        from src.database import Message
        now = datetime.now(UTC)
        cohort_start = now - timedelta(days=window_days + 1)
        cohort_end = now - timedelta(days=window_days)
        recent_active_since = now - timedelta(days=1)

        cohort_result = await self.db.execute(
            select(func.count())
            .select_from(User)
            .where(User.created_at >= cohort_start)
            .where(User.created_at < cohort_end)
        )
        cohort = int(cohort_result.scalar() or 0)
        if cohort == 0:
            return 0.0

        retained_result = await self.db.execute(
            select(func.count(distinct(Message.user_id)))
            .where(Message.user_id.in_(
                select(User.id).where(User.created_at >= cohort_start).where(User.created_at < cohort_end)
            ))
            .where(Message.created_at >= recent_active_since)
        )
        retained = int(retained_result.scalar() or 0)
        return retained / cohort

    async def _retention_matrix(self, *, weeks: int) -> list[dict[str, Any]]:
        """6x6 cohort retention. Row = signup week; columns = week offset 0..5 (% active in that week)."""
        from src.database import Message
        now = datetime.now(UTC)
        matrix: list[dict[str, Any]] = []
        for cohort_offset in range(weeks):
            cohort_end = now - timedelta(weeks=cohort_offset)
            cohort_start = cohort_end - timedelta(weeks=1)
            cohort_size_result = await self.db.execute(
                select(func.count()).select_from(User)
                .where(User.created_at >= cohort_start)
                .where(User.created_at < cohort_end)
            )
            cohort_size = int(cohort_size_result.scalar() or 0)
            offsets: dict[str, float] = {}
            for week_offset in range(weeks):
                if week_offset > cohort_offset:
                    offsets[f"w{week_offset}"] = 0.0
                    continue
                window_end = cohort_end + timedelta(weeks=week_offset + 1)
                window_start = cohort_end + timedelta(weeks=week_offset)
                if cohort_size == 0:
                    offsets[f"w{week_offset}"] = 0.0
                    continue
                active_result = await self.db.execute(
                    select(func.count(distinct(Message.user_id)))
                    .where(Message.user_id.in_(
                        select(User.id).where(User.created_at >= cohort_start).where(User.created_at < cohort_end)
                    ))
                    .where(Message.created_at >= window_start)
                    .where(Message.created_at < window_end)
                )
                active = int(active_result.scalar() or 0)
                offsets[f"w{week_offset}"] = active / cohort_size
            matrix.append({"cohort_week": cohort_start.date().isoformat(), "cohort_size": cohort_size, **offsets})
        matrix.reverse()
        return matrix

    async def capabilities_usage(self, *, range_days: int) -> dict[str, Any]:
        from src.database import Execution
        since = datetime.now(UTC) - timedelta(days=range_days)
        duration_seconds = func.extract("epoch", Execution.completed_at - Execution.created_at)
        stmt = (
            select(
                Execution.capability_id.label("capability_id"),
                Workspace.type.label("workspace_type"),
                func.count().label("calls"),
                func.sum(case((Execution.status.in_(["completed", "failed_partial"]), 1), else_=0)).label("success_count"),
                func.avg(duration_seconds).label("avg_duration"),
                func.percentile_cont(0.95).within_group(duration_seconds).label("p95_duration"),
            )
            .join(Workspace, Workspace.id == Execution.workspace_id)
            .where(Execution.created_at >= since)
            .group_by(Execution.capability_id, Workspace.type)
            .order_by(func.count().desc())
            .limit(15)
        )
        rows = (await self.db.execute(stmt)).all()
        items = []
        for r in rows:
            calls = int(r.calls)
            success = int(r.success_count or 0)
            items.append({
                "capability_id": r.capability_id,
                "workspace_type": r.workspace_type if isinstance(r.workspace_type, str) else r.workspace_type.value,
                "calls": calls,
                "success_rate": (success / calls) if calls > 0 else 0,
                "avg_duration_seconds": float(r.avg_duration or 0),
                "p95_duration_seconds": float(r.p95_duration or 0),
            })
        return {"items": items}

    async def credits_tokens_trends(self, *, range_days: int, granularity: Granularity = "day") -> dict[str, Any]:
        since = datetime.now(UTC) - timedelta(days=range_days)
        stmt = (
            select(
                _date_trunc(granularity, CreditTransaction.created_at).label("bucket"),
                CreditTransaction.transaction_type.label("ttype"),
                func.sum(CreditTransaction.amount).label("total"),
            )
            .where(CreditTransaction.created_at >= since)
            .group_by("bucket", "ttype")
            .order_by("bucket")
        )
        rows = (await self.db.execute(stmt)).all()

        inflow_types = {
            CreditTransactionType.ADMIN_GRANT, CreditTransactionType.REGISTRATION_BONUS,
            CreditTransactionType.REFERRAL_BONUS, CreditTransactionType.REDEEM_CODE, CreditTransactionType.REFUND,
        }
        series_by_bucket: dict[str, dict[str, Any]] = {}
        for r in rows:
            bucket = r.bucket.isoformat()
            ttype = r.ttype if isinstance(r.ttype, str) else r.ttype.value
            amount = int(r.total)
            series_by_bucket.setdefault(bucket, {"date": bucket, "in_by_type": {}, "out_by_type": {}})
            try:
                ttype_enum = CreditTransactionType(ttype)
            except ValueError:
                continue
            if ttype_enum in inflow_types:
                series_by_bucket[bucket]["in_by_type"][ttype] = amount
            else:
                series_by_bucket[bucket]["out_by_type"][ttype] = abs(amount)

        credit_series = [series_by_bucket[k] for k in sorted(series_by_bucket)]

        kpis_result = await self.db.execute(
            select(
                func.coalesce(func.sum(User.total_credits_earned), 0).label("issued"),
                func.coalesce(func.sum(User.total_credits_spent), 0).label("spent"),
                func.coalesce(func.sum(User.credits), 0).label("pool"),
            )
        )
        kpi_row = kpis_result.one()

        # Token usage: reuse existing admin_dashboard_service logic if it exposes a helper.
        # Fallback: stub aggregation across thread / feature_task / subagent token columns.
        from src.services.admin_dashboard_service import AdminDashboardService
        td = await AdminDashboardService(self.db).get_dashboard()
        tokens_total = td.get("summary", {}).get("token_usage", {}).get("thread", {}).get("total_tokens", 0)

        return {
            "kpis": {
                "total_issued": int(kpi_row.issued),
                "total_spent": int(kpi_row.spent),
                "current_pool": int(kpi_row.pool),
                "total_tokens_30d": tokens_total,
            },
            "credit_series": credit_series,
            "token_series": [],
        }

    async def workspaces_tasks(self, *, range_days: int) -> dict[str, Any]:
        since = datetime.now(UTC) - timedelta(days=range_days)

        ws_result = await self.db.execute(
            select(Workspace.type, func.count()).group_by(Workspace.type)
        )
        workspace_by_type = [
            {"type": (t if isinstance(t, str) else t.value), "count": int(c)}
            for t, c in ws_result.all()
        ]

        task_result = await self.db.execute(
            select(TaskRecord.status, func.count())
            .where(TaskRecord.created_at >= since)
            .group_by(TaskRecord.status)
        )
        task_by_status = [
            {"status": s, "count": int(c)} for s, c in task_result.all()
        ]

        err_result = await self.db.execute(
            select(func.substr(TaskRecord.last_error, 1, 80).label("pattern"), func.count().label("count"))
            .where(TaskRecord.status == "failed")
            .where(TaskRecord.created_at >= since)
            .where(TaskRecord.last_error.is_not(None))
            .group_by("pattern")
            .order_by(func.count().desc())
            .limit(10)
        )
        failed_top_errors = [{"pattern": r.pattern, "count": int(r.count)} for r in err_result.all()]

        total_ws_result = await self.db.execute(select(func.count()).select_from(Workspace))
        running_result = await self.db.execute(
            select(func.count()).where(TaskRecord.status == "running")
        )
        last_24h_failed_result = await self.db.execute(
            select(func.count()).where(TaskRecord.status == "failed")
            .where(TaskRecord.created_at >= datetime.now(UTC) - timedelta(hours=24))
        )
        last_24h_total_result = await self.db.execute(
            select(func.count()).where(TaskRecord.created_at >= datetime.now(UTC) - timedelta(hours=24))
        )
        total_24h = int(last_24h_total_result.scalar() or 0)
        fail_24h = int(last_24h_failed_result.scalar() or 0)

        return {
            "kpis": {
                "workspace_total": int(total_ws_result.scalar() or 0),
                "tasks_running": int(running_result.scalar() or 0),
                "tasks_failed_24h": fail_24h,
                "fail_rate": (fail_24h / total_24h) if total_24h > 0 else 0.0,
            },
            "workspace_by_type": workspace_by_type,
            "task_by_status": task_by_status,
            "failed_top_errors": failed_top_errors,
        }
```

- [ ] **Step 3: Run tests**

Run: `cd backend && .venv/bin/python -m pytest tests/services/test_admin_analytics_service.py -v`
Expected: PASS (some tests may need fixture adjustments for Message model import path; fix in line as needed)

- [ ] **Step 4: Commit**

```bash
git add backend/src/services/admin_analytics_service.py backend/tests/services/test_admin_analytics_service.py
git commit -m "feat(analytics): 4 aggregation methods (user growth, capability, credits/tokens, workspace/tasks)"
```

### Task 5.3: Redis cache decorator

**Files:**
- Create: `backend/src/services/admin_analytics_cache.py`

- [ ] **Step 1: Write the cache helper**

```python
"""Redis cache for analytics queries.

5-minute TTL; key = analytics:{endpoint}:{range}:{granularity}.
Pass cache_bust=True to skip the cache for one read.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 300


async def cached(
    *,
    cache_key: str,
    fetcher: Callable[[], Awaitable[dict[str, Any]]],
    cache_bust: bool = False,
) -> dict[str, Any]:
    from src.academic.cache.redis_client import redis_client

    if redis_client._client is None:
        await redis_client.connect()

    if not cache_bust:
        try:
            cached_value = await redis_client.client.get(cache_key)
            if cached_value:
                return json.loads(cached_value)
        except Exception:
            logger.warning("analytics cache read failed for %s", cache_key, exc_info=True)

    fresh = await fetcher()
    try:
        await redis_client.client.set(cache_key, json.dumps(fresh, default=str), ex=CACHE_TTL_SECONDS)
    except Exception:
        logger.warning("analytics cache write failed for %s", cache_key, exc_info=True)
    return fresh
```

- [ ] **Step 2: Commit**

```bash
git add backend/src/services/admin_analytics_cache.py
git commit -m "feat(analytics): Redis cache helper (5min TTL, bust param)"
```

### Task 5.4: Analytics router

**Files:**
- Create: `backend/src/gateway/routers/admin_analytics.py`
- Modify: `backend/src/gateway/main.py`

- [ ] **Step 1: Write router**

```python
"""Admin analytics endpoints."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Query

from src.database import User, get_db_session
from src.gateway.auth_dependencies import get_current_admin
from src.services.admin_analytics_cache import cached
from src.services.admin_analytics_service import AdminAnalyticsService

router = APIRouter(prefix="/admin/analytics", tags=["admin", "analytics"])

Granularity = Literal["day", "week"]


async def _service():
    async with get_db_session() as db:
        yield AdminAnalyticsService(db)


def _parse_range(range_str: str) -> int:
    if range_str.endswith("d"):
        return int(range_str[:-1])
    return int(range_str)


@router.get("/users-growth")
async def users_growth(
    range: str = Query("30d"),
    granularity: Granularity = Query("day"),
    cache_bust: bool = Query(False),
    service: AdminAnalyticsService = Depends(_service),
    _admin: User = Depends(get_current_admin),
) -> dict[str, Any]:
    days = _parse_range(range)
    return await cached(
        cache_key=f"analytics:users-growth:{days}:{granularity}",
        fetcher=lambda: service.user_growth(range_days=days, granularity=granularity),
        cache_bust=cache_bust,
    )


@router.get("/capabilities-usage")
async def capabilities_usage(
    range: str = Query("30d"),
    cache_bust: bool = Query(False),
    service: AdminAnalyticsService = Depends(_service),
    _admin: User = Depends(get_current_admin),
) -> dict[str, Any]:
    days = _parse_range(range)
    return await cached(
        cache_key=f"analytics:capabilities-usage:{days}",
        fetcher=lambda: service.capabilities_usage(range_days=days),
        cache_bust=cache_bust,
    )


@router.get("/credits-tokens-trends")
async def credits_tokens_trends(
    range: str = Query("30d"),
    granularity: Granularity = Query("day"),
    cache_bust: bool = Query(False),
    service: AdminAnalyticsService = Depends(_service),
    _admin: User = Depends(get_current_admin),
) -> dict[str, Any]:
    days = _parse_range(range)
    return await cached(
        cache_key=f"analytics:credits-tokens:{days}:{granularity}",
        fetcher=lambda: service.credits_tokens_trends(range_days=days, granularity=granularity),
        cache_bust=cache_bust,
    )


@router.get("/workspaces-tasks")
async def workspaces_tasks(
    range: str = Query("30d"),
    cache_bust: bool = Query(False),
    service: AdminAnalyticsService = Depends(_service),
    _admin: User = Depends(get_current_admin),
) -> dict[str, Any]:
    days = _parse_range(range)
    return await cached(
        cache_key=f"analytics:workspaces-tasks:{days}",
        fetcher=lambda: service.workspaces_tasks(range_days=days),
        cache_bust=cache_bust,
    )
```

- [ ] **Step 2: Register router + commit**

In FastAPI app init: `app.include_router(admin_analytics_router)`.

```bash
git add backend/src/gateway/routers/admin_analytics.py backend/src/gateway/main.py
git commit -m "feat(analytics): admin router for 4 panel endpoints"
```

### Task 5.5: Install Recharts + frontend API client

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/lib/api/admin-analytics.ts`

- [ ] **Step 1: Install**

Run: `cd frontend && npm i recharts`

- [ ] **Step 2: Write API client**

```typescript
import { authorizedFetch } from "@/lib/api/client";

export interface UserGrowthResponse {
  kpis: { dau: number; wau: number; retention_7d: number; retention_30d: number };
  time_series: Array<{ date: string; signups: number; dau: number }>;
  retention_matrix: Array<{ cohort_week: string; cohort_size: number } & Record<string, number>>;
}

export interface CapabilityUsageItem {
  capability_id: string;
  workspace_type: string;
  calls: number;
  success_rate: number;
  avg_duration_seconds: number;
  p95_duration_seconds: number;
}

export interface CreditsTokensResponse {
  kpis: { total_issued: number; total_spent: number; current_pool: number; total_tokens_30d: number };
  credit_series: Array<{ date: string; in_by_type: Record<string, number>; out_by_type: Record<string, number> }>;
  token_series: Array<{ date: string; total: number }>;
}

export interface WorkspacesTasksResponse {
  kpis: { workspace_total: number; tasks_running: number; tasks_failed_24h: number; fail_rate: number };
  workspace_by_type: Array<{ type: string; count: number }>;
  task_by_status: Array<{ status: string; count: number }>;
  failed_top_errors: Array<{ pattern: string; count: number }>;
}

const q = (range: string, granularity?: string, cacheBust?: boolean) => {
  const params = new URLSearchParams({ range });
  if (granularity) params.set("granularity", granularity);
  if (cacheBust) params.set("cache_bust", "true");
  return params.toString();
};

export async function getUsersGrowth(range = "30d", granularity = "day", cacheBust = false): Promise<UserGrowthResponse> {
  return authorizedFetch(`/admin/analytics/users-growth?${q(range, granularity, cacheBust)}`);
}

export async function getCapabilitiesUsage(range = "30d", cacheBust = false): Promise<{ items: CapabilityUsageItem[] }> {
  return authorizedFetch(`/admin/analytics/capabilities-usage?${q(range, undefined, cacheBust)}`);
}

export async function getCreditsTokensTrends(range = "30d", granularity = "day", cacheBust = false): Promise<CreditsTokensResponse> {
  return authorizedFetch(`/admin/analytics/credits-tokens-trends?${q(range, granularity, cacheBust)}`);
}

export async function getWorkspacesTasks(range = "30d", cacheBust = false): Promise<WorkspacesTasksResponse> {
  return authorizedFetch(`/admin/analytics/workspaces-tasks?${q(range, undefined, cacheBust)}`);
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/lib/api/admin-analytics.ts
git commit -m "feat(frontend): install recharts + analytics API client"
```

### Task 5.6: Shared components (KpiCard, DateRangePicker)

**Files:**
- Create: `frontend/app/dashboard/admin/analytics/components/KpiCard.tsx`
- Create: `frontend/app/dashboard/admin/analytics/components/DateRangePicker.tsx`

- [ ] **Step 1: Write KpiCard**

```typescript
export function KpiCard({
  label, value, hint, format = "number",
}: { label: string; value: number; hint?: string; format?: "number" | "percent" | "duration" }) {
  let display: string;
  if (format === "percent") display = `${(value * 100).toFixed(1)}%`;
  else if (format === "duration") display = `${value.toFixed(1)} s`;
  else display = value.toLocaleString();

  return (
    <div className="rounded-xl border border-[var(--border-default)] bg-[var(--bg-surface)] p-4">
      <div className="text-xs text-[var(--text-muted)]">{label}</div>
      <div className="mt-1 text-2xl font-bold text-[var(--text-primary)]">{display}</div>
      {hint && <div className="mt-1 text-[11px] text-[var(--text-muted)]">{hint}</div>}
    </div>
  );
}
```

- [ ] **Step 2: Write DateRangePicker**

```typescript
"use client";

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

interface Props {
  range: string;
  onRangeChange: (v: string) => void;
  granularity: "day" | "week";
  onGranularityChange: (v: "day" | "week") => void;
}

export function DateRangePicker({ range, onRangeChange, granularity, onGranularityChange }: Props) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <div className="flex items-center gap-2">
        <span className="text-xs text-[var(--text-muted)]">时间范围</span>
        <Select value={range} onValueChange={onRangeChange}>
          <SelectTrigger className="w-32 h-8 text-xs"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="7d">最近 7 天</SelectItem>
            <SelectItem value="30d">最近 30 天</SelectItem>
            <SelectItem value="90d">最近 90 天</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div className="flex items-center gap-2">
        <span className="text-xs text-[var(--text-muted)]">粒度</span>
        <Select value={granularity} onValueChange={(v) => onGranularityChange(v as "day" | "week")}>
          <SelectTrigger className="w-24 h-8 text-xs"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="day">日</SelectItem>
            <SelectItem value="week">周</SelectItem>
          </SelectContent>
        </Select>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/app/dashboard/admin/analytics/components/
git commit -m "feat(analytics): shared KpiCard + DateRangePicker components"
```

### Task 5.7: UserGrowthPanel

**Files:**
- Create: `frontend/app/dashboard/admin/analytics/components/UserGrowthPanel.tsx`

- [ ] **Step 1: Write the panel**

```typescript
"use client";

import { useEffect, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { KpiCard } from "./KpiCard";
import { getUsersGrowth, type UserGrowthResponse } from "@/lib/api/admin-analytics";

export function UserGrowthPanel({ range, granularity }: { range: string; granularity: "day" | "week" }) {
  const [data, setData] = useState<UserGrowthResponse | null>(null);

  useEffect(() => {
    getUsersGrowth(range, granularity).then(setData);
  }, [range, granularity]);

  if (!data) {
    return <div className="text-sm text-[var(--text-muted)]">加载中...</div>;
  }

  return (
    <div id="user-growth" className="route-card rounded-2xl p-5 space-y-4">
      <h3 className="text-base font-semibold">用户增长 / 活跃</h3>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-2">
        <KpiCard label="DAU" value={data.kpis.dau} />
        <KpiCard label="WAU" value={data.kpis.wau} />
        <KpiCard label="7 日留存" value={data.kpis.retention_7d} format="percent" />
        <KpiCard label="30 日留存" value={data.kpis.retention_30d} format="percent" />
      </div>

      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data.time_series}>
            <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
            <XAxis dataKey="date" tickFormatter={(d) => d.slice(5, 10)} fontSize={11} />
            <YAxis fontSize={11} />
            <Tooltip />
            <Legend />
            <Line type="monotone" dataKey="signups" stroke="#a78bfa" name="新注册" strokeWidth={2} />
            <Line type="monotone" dataKey="dau" stroke="#60a5fa" name="DAU" strokeWidth={2} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div>
        <h4 className="text-sm font-medium mb-2">留存矩阵（6 周）</h4>
        <div className="overflow-x-auto">
          <table className="text-xs">
            <thead>
              <tr>
                <th className="text-left px-2 py-1">注册周</th>
                <th className="text-right px-2 py-1">人数</th>
                {[0, 1, 2, 3, 4, 5].map((w) => <th key={w} className="text-right px-2 py-1">W{w}</th>)}
              </tr>
            </thead>
            <tbody>
              {data.retention_matrix.map((row) => (
                <tr key={row.cohort_week}>
                  <td className="px-2 py-1 font-mono">{row.cohort_week}</td>
                  <td className="px-2 py-1 text-right text-[var(--text-muted)]">{row.cohort_size}</td>
                  {[0, 1, 2, 3, 4, 5].map((w) => {
                    const v = (row as any)[`w${w}`] as number | undefined;
                    return (
                      <td key={w} className="px-2 py-1 text-right" style={{
                        background: v ? `rgba(167, 139, 250, ${Math.min(1, v)})` : "transparent",
                      }}>
                        {v !== undefined ? `${(v * 100).toFixed(0)}%` : "-"}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/app/dashboard/admin/analytics/components/UserGrowthPanel.tsx
git commit -m "feat(analytics): user growth panel"
```

### Task 5.8: Other 3 panels

**Files:**
- Create: `frontend/app/dashboard/admin/analytics/components/CapabilityUsagePanel.tsx`
- Create: `frontend/app/dashboard/admin/analytics/components/CreditsTokensPanel.tsx`
- Create: `frontend/app/dashboard/admin/analytics/components/WorkspaceTasksPanel.tsx`

- [ ] **Step 1: CapabilityUsagePanel**

```typescript
"use client";

import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { getCapabilitiesUsage, type CapabilityUsageItem } from "@/lib/api/admin-analytics";

export function CapabilityUsagePanel({ range }: { range: string }) {
  const [items, setItems] = useState<CapabilityUsageItem[]>([]);

  useEffect(() => {
    getCapabilitiesUsage(range).then((res) => setItems(res.items));
  }, [range]);

  return (
    <div id="capability-usage" className="route-card rounded-2xl p-5 space-y-4">
      <h3 className="text-base font-semibold">Capability 使用热点</h3>
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={items} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
            <XAxis type="number" fontSize={11} />
            <YAxis type="category" dataKey="capability_id" fontSize={11} width={140} />
            <Tooltip />
            <Bar dataKey="calls" fill="#a78bfa" />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <table className="w-full text-xs">
        <thead>
          <tr className="text-left border-b border-[var(--border-default)]">
            <th className="px-2 py-1">capability</th>
            <th className="px-2 py-1">workspace</th>
            <th className="px-2 py-1 text-right">调用</th>
            <th className="px-2 py-1 text-right">成功率</th>
            <th className="px-2 py-1 text-right">avg(s)</th>
            <th className="px-2 py-1 text-right">p95(s)</th>
          </tr>
        </thead>
        <tbody>
          {items.map((it) => (
            <tr key={`${it.capability_id}-${it.workspace_type}`} className="border-t border-[var(--border-default)]/50">
              <td className="px-2 py-1 font-mono">{it.capability_id}</td>
              <td className="px-2 py-1">{it.workspace_type}</td>
              <td className="px-2 py-1 text-right">{it.calls}</td>
              <td className="px-2 py-1 text-right">{(it.success_rate * 100).toFixed(1)}%</td>
              <td className="px-2 py-1 text-right">{it.avg_duration_seconds.toFixed(1)}</td>
              <td className="px-2 py-1 text-right">{it.p95_duration_seconds.toFixed(1)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 2: CreditsTokensPanel**

```typescript
"use client";

import { useEffect, useState } from "react";
import { Area, AreaChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { KpiCard } from "./KpiCard";
import { getCreditsTokensTrends, type CreditsTokensResponse } from "@/lib/api/admin-analytics";

const INFLOW_COLORS = ["#a78bfa", "#60a5fa", "#34d399", "#fbbf24"];

export function CreditsTokensPanel({ range, granularity }: { range: string; granularity: "day" | "week" }) {
  const [data, setData] = useState<CreditsTokensResponse | null>(null);

  useEffect(() => {
    getCreditsTokensTrends(range, granularity).then(setData);
  }, [range, granularity]);

  if (!data) return <div className="text-sm text-[var(--text-muted)]">加载中...</div>;

  const flat = data.credit_series.map((d) => {
    const flat: Record<string, any> = { date: d.date };
    Object.entries(d.in_by_type).forEach(([k, v]) => { flat[`in_${k}`] = v; });
    Object.entries(d.out_by_type).forEach(([k, v]) => { flat[`out_${k}`] = -v; });
    return flat;
  });
  const inflowKeys = Array.from(new Set(flat.flatMap((d) => Object.keys(d).filter((k) => k.startsWith("in_")))));

  return (
    <div id="credits-tokens" className="route-card rounded-2xl p-5 space-y-4">
      <h3 className="text-base font-semibold">积分 / Token 趋势</h3>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-2">
        <KpiCard label="累计发放" value={data.kpis.total_issued} />
        <KpiCard label="累计消耗" value={data.kpis.total_spent} />
        <KpiCard label="余额池" value={data.kpis.current_pool} />
        <KpiCard label="30d Token" value={data.kpis.total_tokens_30d} />
      </div>
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={flat}>
            <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
            <XAxis dataKey="date" tickFormatter={(d) => d.slice(5, 10)} fontSize={11} />
            <YAxis fontSize={11} />
            <Tooltip />
            <Legend />
            {inflowKeys.map((k, i) => (
              <Area key={k} type="monotone" dataKey={k} stackId="1" stroke={INFLOW_COLORS[i % INFLOW_COLORS.length]} fill={INFLOW_COLORS[i % INFLOW_COLORS.length]} fillOpacity={0.6} />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: WorkspaceTasksPanel**

```typescript
"use client";

import { useEffect, useState } from "react";
import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import { KpiCard } from "./KpiCard";
import { getWorkspacesTasks, type WorkspacesTasksResponse } from "@/lib/api/admin-analytics";

const WS_COLORS = ["#a78bfa", "#60a5fa", "#34d399", "#fbbf24", "#fb7185"];
const STATUS_COLORS = ["#34d399", "#fbbf24", "#a78bfa", "#fb7185", "#6b7280"];

export function WorkspaceTasksPanel({ range }: { range: string }) {
  const [data, setData] = useState<WorkspacesTasksResponse | null>(null);

  useEffect(() => {
    getWorkspacesTasks(range).then(setData);
  }, [range]);

  if (!data) return <div className="text-sm text-[var(--text-muted)]">加载中...</div>;

  return (
    <div id="workspaces-tasks" className="route-card rounded-2xl p-5 space-y-4">
      <h3 className="text-base font-semibold">Workspace / 任务状态</h3>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-2">
        <KpiCard label="工作空间" value={data.kpis.workspace_total} />
        <KpiCard label="运行中" value={data.kpis.tasks_running} />
        <KpiCard label="24h 失败" value={data.kpis.tasks_failed_24h} />
        <KpiCard label="失败率" value={data.kpis.fail_rate} format="percent" />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div className="h-48">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={data.workspace_by_type} dataKey="count" nameKey="type" innerRadius={36} outerRadius={64} fontSize={11}>
                {data.workspace_by_type.map((_, i) => <Cell key={i} fill={WS_COLORS[i % WS_COLORS.length]} />)}
              </Pie>
              <Tooltip />
              <Legend wrapperStyle={{ fontSize: 11 }} />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div className="h-48">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={data.task_by_status} dataKey="count" nameKey="status" innerRadius={36} outerRadius={64} fontSize={11}>
                {data.task_by_status.map((_, i) => <Cell key={i} fill={STATUS_COLORS[i % STATUS_COLORS.length]} />)}
              </Pie>
              <Tooltip />
              <Legend wrapperStyle={{ fontSize: 11 }} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>
      <div>
        <h4 className="text-sm font-medium mb-2">失败原因 top 10</h4>
        <table className="w-full text-xs">
          <tbody>
            {data.failed_top_errors.map((e) => (
              <tr key={e.pattern} className="border-t border-[var(--border-default)]/50">
                <td className="px-2 py-1 text-[var(--text-secondary)] truncate max-w-md">{e.pattern}</td>
                <td className="px-2 py-1 text-right">{e.count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/app/dashboard/admin/analytics/components/
git commit -m "feat(analytics): capability usage + credits/tokens + workspace/tasks panels"
```

### Task 5.9: Analytics page container

**Files:**
- Create: `frontend/app/dashboard/admin/analytics/page.tsx`

- [ ] **Step 1: Write the container**

```typescript
"use client";

import { useState } from "react";

import { AdminPageHeader } from "../components/AdminPageHeader";
import { CapabilityUsagePanel } from "./components/CapabilityUsagePanel";
import { CreditsTokensPanel } from "./components/CreditsTokensPanel";
import { DateRangePicker } from "./components/DateRangePicker";
import { UserGrowthPanel } from "./components/UserGrowthPanel";
import { WorkspaceTasksPanel } from "./components/WorkspaceTasksPanel";

export default function AnalyticsPage() {
  const [range, setRange] = useState("30d");
  const [granularity, setGranularity] = useState<"day" | "week">("day");

  return (
    <>
      <AdminPageHeader
        title="数据分析"
        description="4 个图表面板，5 分钟缓存。点击刷新强制重算。"
        actions={
          <DateRangePicker
            range={range} onRangeChange={setRange}
            granularity={granularity} onGranularityChange={setGranularity}
          />
        }
      />

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <UserGrowthPanel range={range} granularity={granularity} />
        <CapabilityUsagePanel range={range} />
        <CreditsTokensPanel range={range} granularity={granularity} />
        <WorkspaceTasksPanel range={range} />
      </div>
    </>
  );
}
```

- [ ] **Step 2: Smoke test**

Manual: navigate to `/dashboard/admin/analytics` — all 4 panels load, time-range switcher refetches all 4.

- [ ] **Step 3: Performance check**

In Chrome devtools network tab, time the 4 endpoint responses. Expected: each < 1.5s cold (no cache), < 50ms warm (cache hit). Retention matrix is the heaviest — confirm < 200ms warm.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/dashboard/admin/analytics/page.tsx
git commit -m "feat(analytics): 4-panel page with time range + granularity controls"
```

---

## Self-Review

After writing the plan, I scanned for:

1. **Spec coverage** — Every spec section has tasks:
   - §4.1 Cleanup → Tasks 1.6-1.10, 1.13-1.17
   - §4.2 Schema → Tasks 1.2-1.5, 1.11
   - §4.3 Admin IA → Phase 2
   - §4.4 Capability/Skill mgmt → Phase 3
   - §4.5 Credit rules + redeem codes → Phase 4
   - §4.6 Analytics → Phase 5
2. **Placeholders** — Each step has concrete code or commands. Where exact line numbers may drift (e.g., `page.tsx:1211`), the plan instructs to grep first.
3. **Type consistency** — `WorkspaceFeature` → `WorkspaceCapability` rename is applied consistently from Task 1.14 through 1.16. `CapabilityYamlModel` is defined in Task 3.1 and used by name in 3.2, 3.3.
4. **External dependencies called out**: croniter (P4.4), @monaco-editor/react + js-yaml (P3.7), recharts (P5.5), celery beat in docker-compose (P4.9).

---

## Execution Handoff

Plan complete and saved to [`docs/superpowers/plans/2026-05-14-admin-dashboard-rebuild.md`](2026-05-14-admin-dashboard-rebuild.md). Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?


