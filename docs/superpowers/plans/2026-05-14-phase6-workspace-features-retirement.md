# Phase 6 — Workspace Features Module Retirement

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retire `backend/src/workspace_features/` entirely. Migrate its 7 live consumers (dashboard, summary, compute, chat-agent tools) to read from the `capabilities` DB table. Delete 18 module-bound tests. Designed as a follow-up to the original Phase 1 — needed because P1's audit under-counted live consumers of `workspace_features.registry`.

**Architecture:** The `Capability` table already carries id, workspace_type, display_name, description, ui_meta, etc. P6 adds two more JSONB blocks: `runtime` (mode, requirements, paths) and `dashboard` (status template hints). Existing consumer code is then rewritten to query `Capability` instead of iterating registry tuples. The mixin-keyed-by-feature-id pattern in `DashboardService` is preserved — only the iteration source swaps.

**Tech Stack:** Python 3.13, SQLAlchemy async, Alembic, Pydantic v2.

**Spec:** see decisions inline below.

---

## Decisions

| Topic | Decision |
|-------|----------|
| Where do runtime profile fields live? | New `runtime` JSONB column on `capabilities` table |
| Where do dashboard module status hints live? | New `dashboard_meta` JSONB column on `capabilities` table |
| Backfill strategy | One-off script reads `workspace_features.registry` + `workspace_features.runtime_profiles` (both still alive during P6 execution), writes to new columns |
| Tests under `backend/tests/workspace_features/` | Delete (they test a module that's going away) |
| Consumer migration order | dashboard_service → workspace_summary_service → compute/projection_service → tools/builtins/workspace.py → dead-chain delete → directory delete |
| Order of deletion at end | Only after ALL consumers migrated AND backfill verified |

---

## Phase 6 Task List (10 tasks)

### Task 6.1: Migration 053 — add `runtime` + `dashboard_meta` columns

**Files:**
- Create: `backend/alembic/versions/053_capability_add_runtime_and_dashboard_meta.py`

- [ ] **Step 1: Write the migration**

```python
"""Add runtime + dashboard_meta JSONB columns to capabilities.

Revision ID: 053_capability_add_runtime_and_dashboard_meta
Revises: 052_analytics_indexes
Create Date: 2026-05-21
"""

from __future__ import annotations
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "053_capability_add_runtime_and_dashboard_meta"
down_revision: str | None = "052_analytics_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("capabilities", sa.Column(
        "runtime", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
    ))
    op.add_column("capabilities", sa.Column(
        "dashboard_meta", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
    ))


def downgrade() -> None:
    op.drop_column("capabilities", "dashboard_meta")
    op.drop_column("capabilities", "runtime")
```

- [ ] **Step 2: Run migration**

```bash
cd backend && .venv/bin/alembic upgrade head
```

- [ ] **Step 3: Update Capability ORM**

In `backend/src/database/models/capability.py`, add two columns after `ui_meta`:

```python
runtime: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
dashboard_meta: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
```

- [ ] **Step 4: Verify column exists**

```bash
cd backend && .venv/bin/python -c "from src.database.models.capability import Capability; assert 'runtime' in Capability.__table__.columns.keys() and 'dashboard_meta' in Capability.__table__.columns.keys(); print('OK')"
```

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/053_capability_add_runtime_and_dashboard_meta.py backend/src/database/models/capability.py
git commit -m "feat(db): add runtime + dashboard_meta columns to capabilities"
```

### Task 6.2: Define the runtime + dashboard_meta YAML schema

**Files:**
- Modify: `backend/src/services/capability_schema.py`

- [ ] **Step 1: Add Pydantic models**

Append to `backend/src/services/capability_schema.py`:

```python
from enum import StrEnum

class FeatureRuntimeMode(StrEnum):
    """Execution mode for a capability. Mirrors the v1 enum from workspace_features.runtime_profiles."""
    CHAT_ONLY = "chat_only"
    DETERMINISTIC = "deterministic"
    COMPUTE_WORKFLOW = "compute_workflow"
    COMPUTE_AGENTIC = "compute_agentic"


class RuntimeProfileModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: FeatureRuntimeMode = FeatureRuntimeMode.CHAT_ONLY
    requires_sandbox: bool = False
    review_gate: dict[str, Any] = Field(default_factory=dict)
    allowed_paths: list[str] = Field(default_factory=list)


class DashboardMetaModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status_kind: str = "default"      # which DashboardService mixin to call (e.g., "lit_management", "writing")
    panel: str | None = None          # legacy panel name carried over for compatibility
```

- [ ] **Step 2: Extend `CapabilityYamlModel`**

Add to the existing `CapabilityYamlModel`:

```python
runtime: RuntimeProfileModel = Field(default_factory=RuntimeProfileModel)
dashboard_meta: DashboardMetaModel = Field(default_factory=DashboardMetaModel)
```

- [ ] **Step 3: Update `_yaml_to_orm_kwargs` in `admin_capability_service.py`**

Add `runtime` and `dashboard_meta` fields to the dict construction.

- [ ] **Step 4: Run schema tests**

```bash
cd backend && .venv/bin/python -m pytest tests/services/test_capability_schema.py -v
```

Expected: PASS. Existing tests use minimal capability data — defaults take over.

- [ ] **Step 5: Commit**

```bash
git add backend/src/services/capability_schema.py backend/src/services/admin_capability_service.py
git commit -m "feat(schema): runtime + dashboard_meta Pydantic models"
```

### Task 6.3: Backfill script — registry → capabilities.runtime/dashboard_meta

**Files:**
- Create: `backend/scripts/backfill_capability_runtime_from_registry.py`

- [ ] **Step 1: Write the backfill script**

```python
"""One-off backfill: read workspace_features.registry + runtime_profiles
to populate capabilities.runtime and capabilities.dashboard_meta.

Runs once during P6 Task 6.3. Idempotent (overwrites on each run).
After P6 Task 6.10 deletes workspace_features/, this script can no longer
run — keeps as historical record.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from database import Capability, get_db_session  # noqa: E402
from workspace_features.registry import iter_workspace_features  # noqa: E402
from workspace_features.runtime_profiles import get_feature_runtime_profile  # noqa: E402


async def main() -> int:
    updated = 0
    missing = 0
    async with get_db_session() as db:
        for feature in iter_workspace_features():
            stmt = select(Capability).where(
                Capability.id == feature.id,
                Capability.workspace_type == feature.workspace_type,
            )
            result = await db.execute(stmt)
            cap = result.scalars().first()
            if cap is None:
                print(f"MISS: {feature.workspace_type}/{feature.id} (no matching capability row)")
                missing += 1
                continue
            profile = get_feature_runtime_profile(feature.workspace_type, feature.id)
            cap.runtime = {
                "mode": profile.mode.value if profile else "chat_only",
                "requires_sandbox": getattr(profile, "requires_sandbox", False),
                "review_gate": getattr(profile, "review_gate", {}) or {},
                "allowed_paths": list(getattr(profile, "allowed_paths", []) or []),
            }
            cap.dashboard_meta = {
                "status_kind": feature.id,
                "panel": feature.panel,
            }
            updated += 1
            print(f"OK: {feature.workspace_type}/{feature.id}")
        await db.commit()
    print(f"\nUpdated: {updated}  Missing: {missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
```

- [ ] **Step 2: Run backfill**

```bash
cd backend && .venv/bin/python scripts/backfill_capability_runtime_from_registry.py
```

Expected: ~21 rows updated (the rows from registry). The 4 orphan capabilities from P1.1 (outline_generate, section_write, section_revise, section_writing) will not have registry entries — those need hand-fixed `runtime` blocks. After the script, manually set their runtime mode:

```bash
cd backend && .venv/bin/python -c "
import asyncio
from sqlalchemy import select
from src.database import Capability, get_db_session

ORPHANS = [
    ('thesis', 'outline_generate'),
    ('thesis', 'section_write'),
    ('thesis', 'section_revise'),
    ('sci', 'section_writing'),
]

async def main():
    async with get_db_session() as db:
        for ws, cid in ORPHANS:
            cap = (await db.execute(select(Capability).where(Capability.id==cid, Capability.workspace_type==ws))).scalars().first()
            if cap is None:
                print(f'MISSING {ws}/{cid}')
                continue
            cap.runtime = {'mode':'compute_agentic', 'requires_sandbox':False, 'review_gate':{}, 'allowed_paths':[]}
            cap.dashboard_meta = {'status_kind':cid, 'panel':None}
            print(f'fixed {ws}/{cid}')
        await db.commit()

asyncio.run(main())
"
```

- [ ] **Step 3: Verify all 25 capabilities have non-empty runtime + dashboard_meta**

```bash
cd backend && .venv/bin/python -c "
import asyncio
from sqlalchemy import select, func
from src.database import Capability, get_db_session
async def main():
    async with get_db_session() as db:
        result = await db.execute(select(Capability))
        bad = [c for c in result.scalars().all() if not c.runtime or not c.dashboard_meta]
        print(f'capabilities with empty runtime/dashboard_meta: {len(bad)}')
        for c in bad: print(f'  {c.workspace_type}/{c.id}')
asyncio.run(main())
"
```

Expected: 0 bad rows.

- [ ] **Step 4: Also update the 25 seed YAMLs**

Write a second script (`backend/scripts/sync_capability_runtime_back_to_yaml.py`) that reads DB and writes the runtime + dashboard_meta blocks back into the seed YAMLs (so the next fresh-DB import preserves them). Same shape as P1.1's ETL but reading DB instead of registry.

After running, commit:

```bash
git add backend/scripts/backfill_capability_runtime_from_registry.py backend/scripts/sync_capability_runtime_back_to_yaml.py backend/seed/capabilities/
git commit -m "feat(seeds): backfill runtime + dashboard_meta from registry and sync to YAML"
```

### Task 6.4: Migrate DashboardService

**Files:**
- Modify: `backend/src/services/dashboard_service.py`
- Modify: `backend/tests/services/test_dashboard_service.py`

- [ ] **Step 1: Write failing test**

In `tests/services/test_dashboard_service.py`, add a test that verifies dashboard modules are built from Capability rows (not registry):

```python
@pytest.mark.asyncio
async def test_modules_built_from_capability_table(real_async_db, seed_capabilities_for_dashboard):
    """Dashboard reads modules from capabilities table, not registry."""
    service = DashboardService(real_async_db)
    modules = await service._get_modules_for_workspace("ws-uuid", "thesis")
    assert len(modules) > 0
    assert {m["id"] for m in modules} <= {c.id for c in seed_capabilities_for_dashboard}
```

- [ ] **Step 2: Update `_get_modules_for_workspace`**

Replace the body:

```python
async def _get_modules_for_workspace(
    self, workspace_id: str, workspace_type: str,
) -> list[dict[str, Any]]:
    from sqlalchemy import select
    from src.database import Capability

    result = await self.db.execute(
        select(Capability)
        .where(Capability.workspace_type == workspace_type)
        .where(Capability.enabled == True)  # noqa: E712
    )
    capabilities = sorted(result.scalars().all(), key=lambda c: (c.ui_meta.get("order", 0), c.id))

    modules: list[dict[str, Any]] = []
    for cap in capabilities:
        status_kind = cap.dashboard_meta.get("status_kind", cap.id)
        method_name = f"_get_{status_kind}_status"
        if not hasattr(self, method_name):
            raise RuntimeError(f"No dashboard status builder for status_kind '{status_kind}'")
        modules.append(await getattr(self, method_name)(workspace_id))
    return modules
```

- [ ] **Step 3: Remove `from src.workspace_features import list_workspace_features` import**

Delete the import line at top of the file.

- [ ] **Step 4: Run tests**

```bash
cd backend && .venv/bin/python -m pytest tests/services/test_dashboard_service.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/services/dashboard_service.py backend/tests/services/test_dashboard_service.py
git commit -m "feat(dashboard): read modules from capabilities table, not workspace_features registry"
```

### Task 6.5: Migrate WorkspaceSummaryService

**Files:**
- Modify: `backend/src/services/workspace_summary_service.py`
- Modify: tests if applicable

- [ ] **Step 1: Locate `list_workspace_features` callsite**

`grep -n "list_workspace_features" backend/src/services/workspace_summary_service.py` (~line 127).

- [ ] **Step 2: Swap to Capability query**

Replace the iteration to fetch from `Capability` table filtered by `workspace_type` and `enabled=True`, sorted by `ui_meta.order`. Use same field access pattern as DashboardService.

- [ ] **Step 3: Remove the import**

`from src.workspace_features import list_workspace_features` — delete.

- [ ] **Step 4: Run tests**

`cd backend && .venv/bin/python -m pytest tests/services/test_workspace_summary_service.py -v` (if such file exists) or run broader summary tests.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(summary): read capabilities from DB for workspace summary"
```

### Task 6.6: Migrate ComputeProjectionService

**Files:**
- Modify: `backend/src/compute/projection_service.py`

- [ ] **Step 1: Read current usage**

`grep -n "runtime_profile\|get_feature_runtime_profile\|workspace_features" backend/src/compute/projection_service.py`

The function `_build_runtime_profile_projection(execution)` calls `get_feature_runtime_profile(execution.workspace_type, execution.feature_id)`.

- [ ] **Step 2: Replace with Capability column read**

```python
async def _build_runtime_profile_projection_from_db(
    db: AsyncSession, execution: ExecutionRecord,
) -> dict[str, Any]:
    from sqlalchemy import select
    from src.database import Capability

    result = await db.execute(
        select(Capability.runtime).where(
            Capability.id == execution.feature_id,
            Capability.workspace_type == execution.workspace_type,
        )
    )
    runtime = result.scalar() or {}
    return runtime
```

(Adjust signature if surrounding code is sync vs async.)

- [ ] **Step 3: Update callers**

Find every caller of the old function and pass `db` if newly required.

- [ ] **Step 4: Remove import + run compute tests**

`grep -n "from src.workspace_features" backend/src/compute/projection_service.py` — should be 0 after fix.

`cd backend && .venv/bin/python -m pytest tests/compute/ -v`

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(compute): runtime profile from capability table, not registry"
```

### Task 6.7: Migrate `tools/builtins/workspace.py`

**Files:**
- Modify: `backend/src/tools/builtins/workspace.py`
- Modify: `backend/src/agents/chat_agent/agent.py` (if needed)

- [ ] **Step 1: Rewrite `list_workspace_features_tool`**

Replace `build_workspace_feature_overview` call with a direct Capability table query. The "overview" structure expected by the tool: array of features with id, display_name, description.

```python
@tool("list_workspace_features", args_schema=ListWorkspaceFeaturesInput)
async def list_workspace_features_tool(
    config: RunnableConfig | None = None,
) -> str:
    runtime = _runtime_context(config)
    if runtime.workspace_id is None or runtime.user_id is None:
        return json.dumps({"error": "runtime_context_missing"}, ensure_ascii=False)
    from sqlalchemy import select
    from src.database import Capability, Workspace, get_db_session
    async with get_db_session() as db:
        ws_result = await db.execute(select(Workspace.type).where(Workspace.id == runtime.workspace_id))
        ws_type = ws_result.scalar()
        if not ws_type:
            return json.dumps({"error": "workspace_not_found"}, ensure_ascii=False)
        cap_result = await db.execute(
            select(Capability).where(Capability.workspace_type == ws_type).where(Capability.enabled == True)  # noqa: E712
        )
        capabilities = sorted(cap_result.scalars().all(), key=lambda c: (c.ui_meta.get("order", 0), c.id))
    items = [
        {"id": c.id, "display_name": c.display_name, "description": c.description}
        for c in capabilities
    ]
    return json.dumps({"items": items}, ensure_ascii=False)
```

(The tool name stays `list_workspace_features` since chat_agent prompts reference it; we just change the internals.)

- [ ] **Step 2: Rewrite `list_workspace_artifacts_tool`**

Replace `build_workspace_artifact_overview` call with a direct Artifact table query. Read `backend/src/workspace_features/thread_catalog.py` for what shape was being returned, then replicate with direct SQL.

- [ ] **Step 3: Remove imports**

```python
# old
from src.workspace_features.thread_catalog import (
    build_workspace_artifact_overview,
    build_workspace_feature_overview,
)
# delete
```

- [ ] **Step 4: Run chat_agent integration tests**

```bash
cd backend && .venv/bin/python -m pytest tests/agents/chat_agent/ -v
```

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(tools): read capabilities + artifacts directly from DB, drop workspace_features dep"
```

### Task 6.8: Delete dead chain `application/services/feature_*_service.py`

**Files:**
- Delete: `backend/src/application/services/feature_submission_service.py`
- Delete: `backend/src/application/services/feature_launch_service.py`
- Delete: `backend/src/application/services/feature_ingress_factory.py` (if exists)

- [ ] **Step 1: Confirm dead**

```bash
grep -rn "FeatureLaunchService\|FeatureSubmissionService\|FeatureIngressService" backend/src --include="*.py" | grep -v __pycache__ | grep -v "application/services/feature_"
```

Expected: at most `gateway/deps/application.py` registers them but no router uses them. If any router uses them, the chain isn't dead — investigate.

- [ ] **Step 2: Remove DI registrations**

In `backend/src/gateway/deps/application.py` (or wherever they're registered), remove the factory functions.

- [ ] **Step 3: Delete files + run tests**

```bash
git rm backend/src/application/services/feature_submission_service.py
git rm backend/src/application/services/feature_launch_service.py
git rm backend/src/application/services/feature_ingress_factory.py 2>/dev/null || true
cd backend && .venv/bin/python -m pytest tests/ -x --tb=short 2>&1 | tail -20
```

- [ ] **Step 4: Commit**

```bash
git commit -m "refactor: remove dead application/services/feature_*_service chain"
```

### Task 6.9: Delete tests under `backend/tests/workspace_features/`

**Files:**
- Delete: `backend/tests/workspace_features/` (whole directory)

- [ ] **Step 1: List**

`ls backend/tests/workspace_features/` — confirm 18 files all test the module being deleted.

- [ ] **Step 2: Delete**

```bash
git rm -rf backend/tests/workspace_features/
```

- [ ] **Step 3: Run test discovery**

```bash
cd backend && .venv/bin/python -m pytest tests/ --collect-only 2>&1 | tail -10
```

Expected: collection succeeds (no missing-import errors from deleted module).

- [ ] **Step 4: Commit**

```bash
git commit -m "test: drop module-bound tests for retired workspace_features"
```

### Task 6.10: Final delete — `workspace_features/`

**Files:**
- Delete: `backend/src/workspace_features/` (whole directory)

- [ ] **Step 1: Final safety check**

```bash
grep -rn "from src.workspace_features\|import workspace_features" backend/src backend/tests --include="*.py" | grep -v __pycache__
```

Expected: empty (or only the do-not-re-run scripts under `backend/scripts/` which are historical record).

- [ ] **Step 2: Delete**

```bash
git rm -rf backend/src/workspace_features/
find backend -name "*.pyc" -path "*workspace_features*" -delete
```

- [ ] **Step 3: Full test run**

```bash
cd backend && .venv/bin/python -m pytest tests/ -x --tb=short 2>&1 | tail -30
```

Expected: PASS (any remaining failure is unrelated and pre-existing).

- [ ] **Step 4: Verify import smoke tests**

```bash
cd backend && .venv/bin/python -c "from src.agents.chat_agent.agent import make_chat_agent; print('OK')"
cd backend && .venv/bin/python -c "from src.gateway.routers.workspaces import router; print('OK')"
cd backend && .venv/bin/python -c "from src.services.dashboard_service import DashboardService; print('OK')"
cd backend && .venv/bin/python -c "from src.compute.projection_service import build_projection; print('OK')"
```

Expected: all OK.

- [ ] **Step 5: Commit**

```bash
git commit -m "refactor: retire workspace_features module entirely

All consumers migrated to read from capabilities table (P6 tasks 6.1-6.7).
Dead chain removed (6.8). Module-bound tests dropped (6.9). Registry,
runtime_profiles, thread_catalog all gone.
"
```

---

## Risks

1. **Backfill data quality** — the 4 orphan capabilities (outline_generate, section_write, section_revise, section_writing) need hand-set runtime modes. Task 6.3 step 2 covers this with `compute_agentic` default; if that's wrong for any of them, surface in 6.4 testing.

2. **DashboardService mixin breakage** — if any `_get_<feature_id>_status` method is missing for a capability that has a `dashboard_meta.status_kind`, the dashboard breaks at runtime. Verify by enumerating all capabilities and matching against existing mixin methods before 6.4 ships.

3. **Compute runtime profile semantics** — if v2 needs new fields not in the v1 `FeatureRuntimeProfile` dataclass, add them to `RuntimeProfileModel` in 6.2 before backfill in 6.3.

4. **Test deletions are not safe to revert** — once 6.9 deletes 18 test files, restoring them requires `git revert`. Make sure 6.4-6.7 cover the original test intent first.

## Out of scope

- Frontend dashboard catalog page (this Phase is backend-only)
- Renaming `list_workspace_features` tool to `list_capabilities` — the tool name is in chat_agent prompts; renaming is a separate concern handled when we revisit prompts holistically.
- Replacement of v1 `panel` semantics — `dashboard_meta.panel` keeps the legacy value for compatibility; deprecating panel-based UI is a separate cleanup.
