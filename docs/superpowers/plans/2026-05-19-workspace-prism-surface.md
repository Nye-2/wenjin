# Workspace Prism Surface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make WenjinPrism the canonical manuscript surface of a workspace via explicit data binding, workspace-owned routing, authoritative compute projection, and workspace-aware frontend navigation.

**Architecture:** Add explicit `workspace_id` / `surface_role` binding to `LatexProject`, introduce a product-level `WorkspacePrismService`, route manuscript entry through `/workspaces/:id/prism`, and make Compute consume Prism state from the authoritative linked project instead of scanning task payloads as the primary source.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy async, Alembic, Pydantic v2, Next.js 16, React 19, TypeScript, Zustand, Vitest, Playwright.

---

## File Structure

### Backend

- Create: `/Users/ze/wenjin/backend/alembic/versions/056_workspace_prism_surface_binding.py`
  - Add `workspace_id` and `surface_role` to `latex_projects`, backfill from `llm_config`, and index `(workspace_id, surface_role)`.
- Create: `/Users/ze/wenjin/backend/src/services/workspace_prism_service.py`
  - Canonical lookup / ensure / projection / route-resolve service for workspace-owned Prism.
- Create: `/Users/ze/wenjin/backend/tests/services/test_workspace_prism_service.py`
  - TDD coverage for explicit binding lookup, ensure behavior, and legacy fallback.
- Modify: `/Users/ze/wenjin/backend/src/database/models/latex_project.py`
  - Add explicit ORM columns for workspace binding.
- Modify: `/Users/ze/wenjin/backend/src/services/workspace_latex_projects.py`
  - Write explicit binding fields when creating/updating workspace-owned projects.
- Modify: `/Users/ze/wenjin/backend/src/gateway/routers/workspaces_contracts.py`
  - Add Prism surface response model.
- Modify: `/Users/ze/wenjin/backend/src/gateway/routers/workspaces.py`
  - Route `ensure` and new workspace Prism surface endpoint through `WorkspacePrismService`.
- Modify: `/Users/ze/wenjin/backend/src/gateway/routers/latex.py`
  - Redirect workspace-owned `/latex/:projectId` requests to `/workspaces/:id/prism`.
- Modify: `/Users/ze/wenjin/backend/src/compute/projection_service.py`
  - Prefer authoritative Prism projection from the linked project; keep payload scan as fallback.
- Modify: `/Users/ze/wenjin/backend/src/services/latex/prism_status_resolver.py`
  - Refresh authoritative Prism state using explicit binding-aware project reads.
- Test: `/Users/ze/wenjin/backend/tests/gateway/routers/test_workspace_prism.py`
- Test: `/Users/ze/wenjin/backend/tests/compute/test_projection_service.py`

### Frontend

- Create: `/Users/ze/wenjin/frontend/app/(workbench)/workspaces/[id]/prism/page.tsx`
  - Workspace-owned Prism route container.
- Create: `/Users/ze/wenjin/frontend/app/(workbench)/workspaces/[id]/components/SurfaceSwitch.tsx`
  - Workbench / Prism surface switch UI.
- Create: `/Users/ze/wenjin/frontend/tests/unit/v2/prism-surface.test.tsx`
  - Route-level tests for Prism surface rendering and switch state.
- Modify: `/Users/ze/wenjin/frontend/app/(workbench)/workspaces/[id]/layout.tsx`
  - Share shell between workbench and Prism routes.
- Modify: `/Users/ze/wenjin/frontend/app/(workbench)/workspaces/[id]/page.tsx`
  - Render switch and preserve workbench semantics.
- Modify: `/Users/ze/wenjin/frontend/app/latex/[projectId]/page.tsx`
  - Treat legacy project route as compatibility-only entry.
- Modify: `/Users/ze/wenjin/frontend/lib/api/types.ts`
  - Add workspace Prism surface response types.
- Modify: `/Users/ze/wenjin/frontend/lib/api/workspace.ts`
  - Add `getWorkspacePrismSurface`.
- Modify: `/Users/ze/wenjin/frontend/lib/block-actions.ts`
  - Route Prism actions to `/workspaces/:id/prism` when workspace context exists.
- Modify: `/Users/ze/wenjin/frontend/app/(workbench)/workspaces/[id]/components/CompletedView.tsx`
  - Consume workspace Prism route instead of raw `/latex/:projectId`.
- Test: `/Users/ze/wenjin/frontend/tests/unit/v2/layout.test.tsx`
- Test: `/Users/ze/wenjin/frontend/tests/unit/v2/ExecutionCard.test.tsx`
- Test: `/Users/ze/wenjin/frontend/tests/e2e/iteration.spec.ts`
- Test: `/Users/ze/wenjin/frontend/tests/e2e/golden-path.spec.ts`

## Task 1: Add Explicit Workspace Prism Binding

**Files:**
- Create: `/Users/ze/wenjin/backend/alembic/versions/056_workspace_prism_surface_binding.py`
- Create: `/Users/ze/wenjin/backend/src/services/workspace_prism_service.py`
- Create: `/Users/ze/wenjin/backend/tests/services/test_workspace_prism_service.py`
- Modify: `/Users/ze/wenjin/backend/src/database/models/latex_project.py`
- Modify: `/Users/ze/wenjin/backend/src/services/workspace_latex_projects.py`

- [ ] **Step 1: Write the failing service test**

```python
# /Users/ze/wenjin/backend/tests/services/test_workspace_prism_service.py
from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.latex_project import LatexProject
from src.services.workspace_prism_service import WorkspacePrismService


@pytest.mark.asyncio
async def test_get_primary_project_prefers_explicit_workspace_binding(
    db: AsyncSession,
    user: SimpleNamespace,
) -> None:
    explicit = LatexProject(
        id="latex-explicit",
        user_id=user.id,
        name="Explicit Manuscript",
        workspace_id="ws-1",
        surface_role="primary_manuscript",
        llm_config={"workspace_id": "legacy-ws", "bridge": "workspace_latex_project"},
    )
    legacy = LatexProject(
        id="latex-legacy",
        user_id=user.id,
        name="Legacy Manuscript",
        llm_config={"workspace_id": "ws-1", "bridge": "workspace_latex_project"},
    )
    db.add_all([explicit, legacy])
    await db.commit()

    project = await WorkspacePrismService(db).get_primary_project(
        "ws-1",
        user_id=user.id,
    )

    assert project is not None
    assert str(project.id) == "latex-explicit"


@pytest.mark.asyncio
async def test_get_primary_project_falls_back_to_legacy_llm_config_binding(
    db: AsyncSession,
    user: SimpleNamespace,
) -> None:
    legacy = LatexProject(
        id="latex-legacy",
        user_id=user.id,
        name="Legacy Manuscript",
        llm_config={"workspace_id": "ws-2", "bridge": "workspace_latex_project"},
    )
    db.add(legacy)
    await db.commit()

    project = await WorkspacePrismService(db).get_primary_project(
        "ws-2",
        user_id=user.id,
    )

    assert project is not None
    assert str(project.id) == "latex-legacy"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/services/test_workspace_prism_service.py -q
```

Expected:

```text
FAIL ... ModuleNotFoundError: No module named 'src.services.workspace_prism_service'
```

- [ ] **Step 3: Write the minimal model, migration, and service implementation**

```python
# /Users/ze/wenjin/backend/src/database/models/latex_project.py
workspace_id: Mapped[str | None] = mapped_column(
    String(36),
    ForeignKey("workspaces.id", ondelete="SET NULL"),
    nullable=True,
    index=True,
)
surface_role: Mapped[str | None] = mapped_column(
    String(64),
    nullable=True,
    index=True,
)
```

```python
# /Users/ze/wenjin/backend/src/services/workspace_prism_service.py
from __future__ import annotations

from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.latex_project import LatexProject
from src.services.workspace_latex_projects import WorkspaceLatexProjectService


class WorkspacePrismService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.bridge = WorkspaceLatexProjectService(db)

    async def get_primary_project(
        self,
        workspace_id: str,
        *,
        user_id: str,
    ) -> LatexProject | None:
        explicit = await self.db.scalar(
            select(LatexProject)
            .where(
                LatexProject.user_id == user_id,
                LatexProject.workspace_id == workspace_id,
                LatexProject.surface_role == "primary_manuscript",
            )
            .order_by(LatexProject.updated_at.desc())
            .limit(1)
        )
        if explicit is not None:
            return explicit

        return await self.db.scalar(
            select(LatexProject)
            .where(
                LatexProject.user_id == user_id,
                LatexProject.workspace_id.is_(None),
                LatexProject.llm_config.is_not(None),
            )
            .where(
                and_(
                    LatexProject.llm_config["workspace_id"].as_string() == workspace_id,
                    LatexProject.llm_config["bridge"].as_string() == "workspace_latex_project",
                )
            )
            .order_by(LatexProject.updated_at.desc())
            .limit(1)
        )

    async def ensure_primary_project(
        self,
        workspace_id: str,
        *,
        user_id: str,
        project_name: str,
    ) -> LatexProject:
        project = await self.get_primary_project(workspace_id, user_id=user_id)
        if project is not None:
            return project
        project = await self.bridge.ensure_workspace_project(
            workspace_id=workspace_id,
            project_name=project_name,
        )
        project.workspace_id = workspace_id
        project.surface_role = "primary_manuscript"
        await self.db.commit()
        await self.db.refresh(project)
        return project
```

```python
# /Users/ze/wenjin/backend/alembic/versions/056_workspace_prism_surface_binding.py
"""add explicit workspace Prism binding

Revision ID: 056_workspace_prism_surface_binding
Revises: 055_credit_grant_rules_and_redeem_codes
Create Date: 2026-05-19 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "056_workspace_prism_surface_binding"
down_revision = "055_credit_grant_rules_and_redeem_codes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("latex_projects", sa.Column("workspace_id", sa.String(length=36), nullable=True))
    op.add_column("latex_projects", sa.Column("surface_role", sa.String(length=64), nullable=True))
    op.create_index("ix_latex_projects_workspace_id", "latex_projects", ["workspace_id"], unique=False)
    op.create_index("ix_latex_projects_surface_role", "latex_projects", ["surface_role"], unique=False)
    op.create_index(
        "ix_latex_projects_workspace_surface_role",
        "latex_projects",
        ["workspace_id", "surface_role"],
        unique=False,
    )
    op.execute(
        '''
        update latex_projects
        set workspace_id = llm_config->>'workspace_id',
            surface_role = 'primary_manuscript'
        where llm_config is not null
          and llm_config->>'bridge' = 'workspace_latex_project'
          and coalesce(llm_config->>'workspace_id', '') <> ''
        '''
    )


def downgrade() -> None:
    op.drop_index("ix_latex_projects_workspace_surface_role", table_name="latex_projects")
    op.drop_index("ix_latex_projects_surface_role", table_name="latex_projects")
    op.drop_index("ix_latex_projects_workspace_id", table_name="latex_projects")
    op.drop_column("latex_projects", "surface_role")
    op.drop_column("latex_projects", "workspace_id")
```

```python
# /Users/ze/wenjin/backend/src/services/workspace_latex_projects.py
update_payload["llm_config"] = {
    "workspace_id": workspace_id,
    "bridge": "workspace_latex_project",
    "template": template,
    "role": "primary",
    "metadata": project_metadata,
}
linked_project.workspace_id = workspace_id
linked_project.surface_role = "primary_manuscript"
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/services/test_workspace_prism_service.py -q
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Commit**

```bash
git -C /Users/ze/wenjin add \
  backend/alembic/versions/056_workspace_prism_surface_binding.py \
  backend/src/database/models/latex_project.py \
  backend/src/services/workspace_latex_projects.py \
  backend/src/services/workspace_prism_service.py \
  backend/tests/services/test_workspace_prism_service.py
git -C /Users/ze/wenjin commit -m "feat: add explicit workspace prism binding"
```

### Task 2: Route Workspace-Owned Prism Through Workspace APIs

**Files:**
- Modify: `/Users/ze/wenjin/backend/src/gateway/routers/workspaces_contracts.py`
- Modify: `/Users/ze/wenjin/backend/src/gateway/routers/workspaces.py`
- Modify: `/Users/ze/wenjin/backend/src/gateway/routers/latex.py`
- Modify: `/Users/ze/wenjin/backend/tests/gateway/routers/test_workspace_prism.py`
- Create: `/Users/ze/wenjin/backend/tests/gateway/routers/test_latex_workspace_redirect.py`

- [ ] **Step 1: Write the failing route tests**

```python
# /Users/ze/wenjin/backend/tests/gateway/routers/test_workspace_prism.py
def test_prism_ensure_returns_workspace_prism_route():
    client = _create_client(user_id="user-1", workspace_owner_id="user-1")

    with patch(
        "src.gateway.routers.workspaces.WorkspacePrismService.ensure_primary_project",
        new=AsyncMock(return_value=SimpleNamespace(id="latex-1")),
    ):
        response = client.post("/workspaces/ws-1/prism/ensure")

    assert response.status_code == 200
    assert response.json() == {
        "latex_project_id": "latex-1",
        "url": "/workspaces/ws-1/prism",
        "sync_status": "ready",
    }


def test_workspace_prism_surface_returns_linked_project_metadata():
    client = _create_client(user_id="user-1", workspace_owner_id="user-1")

    with patch(
        "src.gateway.routers.workspaces.WorkspacePrismService.get_surface_projection",
        new=AsyncMock(
            return_value={
                "workspace_id": "ws-1",
                "latex_project_id": "latex-1",
                "surface_role": "primary_manuscript",
                "url": "/workspaces/ws-1/prism",
            }
        ),
    ):
        response = client.get("/workspaces/ws-1/prism")

    assert response.status_code == 200
    assert response.json()["latex_project_id"] == "latex-1"
```

```python
# /Users/ze/wenjin/backend/tests/gateway/routers/test_latex_workspace_redirect.py
def test_workspace_owned_project_redirects_to_workspace_prism(client: TestClient):
    with patch(
        "src.gateway.routers.latex.WorkspacePrismService.resolve_workspace_from_project",
        new=AsyncMock(return_value=("ws-1", SimpleNamespace(id="latex-1"))),
    ):
        response = client.get("/latex/latex-1", follow_redirects=False)

    assert response.status_code in {302, 307}
    assert response.headers["location"] == "/workspaces/ws-1/prism"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest \
  tests/gateway/routers/test_workspace_prism.py \
  tests/gateway/routers/test_latex_workspace_redirect.py -q
```

Expected:

```text
FAIL ... GET /workspaces/ws-1/prism not found
FAIL ... expected /workspaces/ws-1/prism but got /latex/latex-1
```

- [ ] **Step 3: Implement the workspace Prism API and redirect logic**

```python
# /Users/ze/wenjin/backend/src/gateway/routers/workspaces_contracts.py
class WorkspacePrismSurfaceResponse(BaseModel):
    workspace_id: str
    latex_project_id: str
    surface_role: str
    url: str
    main_file: str | None = None
    compile_status: str | None = None
    has_pending_changes: bool = False
```

```python
# /Users/ze/wenjin/backend/src/gateway/routers/workspaces.py
@router.get(
    "/{workspace_id}/prism",
    response_model=WorkspacePrismSurfaceResponse,
)
async def get_workspace_prism_surface(
    workspace_id: str,
    current_user: User = Depends(get_current_user),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
    db: Any = Depends(get_db),
) -> WorkspacePrismSurfaceResponse:
    workspace = await get_owned_workspace(
        workspace_id=workspace_id,
        current_user=current_user,
        workspace_service=workspace_service,
    )
    projection = await WorkspacePrismService(db).get_surface_projection(
        workspace_id,
        user_id=str(current_user.id),
    )
    return WorkspacePrismSurfaceResponse(**projection)


@router.post(
    "/{workspace_id}/prism/ensure",
    response_model=WorkspacePrismEnsureResponse,
)
async def ensure_workspace_prism_project(...):
    workspace = await get_owned_workspace(...)
    linked_project = await WorkspacePrismService(db).ensure_primary_project(
        workspace_id=workspace_id,
        user_id=str(current_user.id),
        project_name=str(workspace.name or ""),
    )
    return WorkspacePrismEnsureResponse(
        latex_project_id=str(linked_project.id),
        url=f"/workspaces/{workspace_id}/prism",
        sync_status="ready",
    )
```

```python
# /Users/ze/wenjin/backend/src/gateway/routers/latex.py
@router.get("/{project_id}")
async def open_latex_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    workspace_id, _project = await WorkspacePrismService(db).resolve_workspace_from_project(
        project_id,
        user_id=str(current_user.id),
    )
    if workspace_id is not None:
        return RedirectResponse(url=f"/workspaces/{workspace_id}/prism", status_code=307)
    return HTMLResponse(...)
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest \
  tests/gateway/routers/test_workspace_prism.py \
  tests/gateway/routers/test_latex_workspace_redirect.py -q
```

Expected:

```text
4 passed
```

- [ ] **Step 5: Commit**

```bash
git -C /Users/ze/wenjin add \
  backend/src/gateway/routers/workspaces_contracts.py \
  backend/src/gateway/routers/workspaces.py \
  backend/src/gateway/routers/latex.py \
  backend/tests/gateway/routers/test_workspace_prism.py \
  backend/tests/gateway/routers/test_latex_workspace_redirect.py
git -C /Users/ze/wenjin commit -m "feat: add workspace-owned prism routes"
```

### Task 3: Make Compute Prism Projection Authoritative

**Files:**
- Modify: `/Users/ze/wenjin/backend/src/compute/projection_service.py`
- Modify: `/Users/ze/wenjin/backend/src/services/latex/prism_status_resolver.py`
- Modify: `/Users/ze/wenjin/backend/src/services/workspace_prism_service.py`
- Modify: `/Users/ze/wenjin/backend/tests/compute/test_projection_service.py`

- [ ] **Step 1: Write the failing compute projection test**

```python
# /Users/ze/wenjin/backend/tests/compute/test_projection_service.py
@pytest.mark.asyncio
async def test_projection_prefers_workspace_owned_prism_over_runtime_payload(
    db: AsyncSession,
    seeded_execution: ExecutionRecord,
) -> None:
    seeded_execution.runtime_state = {
        "latex_project_id": "latex-stale",
        "file_changes": [{"path": "sections/stale.tex"}],
    }

    linked_project = LatexProject(
        id="latex-authoritative",
        user_id=seeded_execution.user_id,
        name="Authoritative",
        workspace_id=seeded_execution.workspace_id,
        surface_role="primary_manuscript",
        llm_config={
            "metadata": {
                "file_changes": [{"path": "sections/current.tex"}],
            }
        },
    )
    db.add(linked_project)
    await db.commit()

    projection = await ComputeProjectionService(db).build_for_execution(
        execution_id=seeded_execution.id,
        user_id=seeded_execution.user_id,
    )

    assert projection["prism"]["project_id"] == "latex-authoritative"
    assert projection["prism"]["file_changes"][0]["path"] == "sections/current.tex"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/compute/test_projection_service.py -k authoritative_prism -q
```

Expected:

```text
FAIL ... projection["prism"]["project_id"] == "latex-stale"
```

- [ ] **Step 3: Implement authoritative Prism projection with payload fallback**

```python
# /Users/ze/wenjin/backend/src/services/workspace_prism_service.py
async def get_surface_projection(
    self,
    workspace_id: str,
    *,
    user_id: str,
) -> dict[str, Any]:
    project = await self.get_primary_project(workspace_id, user_id=user_id)
    if project is None:
        raise ValueError(f"Workspace Prism not found: {workspace_id}")

    metadata = (
        project.llm_config.get("metadata")
        if isinstance(project.llm_config, dict) and isinstance(project.llm_config.get("metadata"), dict)
        else {}
    )
    file_changes = list(metadata.get("file_changes") or [])
    applied = list(metadata.get("applied_file_changes") or [])
    return {
        "workspace_id": workspace_id,
        "latex_project_id": str(project.id),
        "surface_role": project.surface_role or "primary_manuscript",
        "url": f"/workspaces/{workspace_id}/prism",
        "main_file": project.main_file,
        "compile_status": None,
        "has_pending_changes": bool(file_changes),
        "file_changes": file_changes,
        "applied_file_changes": applied,
    }
```

```python
# /Users/ze/wenjin/backend/src/compute/projection_service.py
authoritative_prism = None
if execution.workspace_id:
    try:
        authoritative_prism = await WorkspacePrismService(self.db).get_surface_projection(
            execution.workspace_id,
            user_id=execution.user_id,
        )
    except ValueError:
        authoritative_prism = None

if authoritative_prism is not None:
    prism = {
        "status": "pending_changes" if authoritative_prism["has_pending_changes"] else "ready",
        "project_id": authoritative_prism["latex_project_id"],
        "url": authoritative_prism["url"],
        "main_file": authoritative_prism["main_file"],
        "target_files": [change["path"] for change in authoritative_prism["file_changes"]],
        "file_changes": authoritative_prism["file_changes"],
        "applied_file_changes": authoritative_prism["applied_file_changes"],
        "compile": {},
        "items": [],
    }
else:
    prism = _build_prism_projection(execution=execution, tasks=tasks)

prism = await LatexPrismStatusResolver(self.db).refresh(prism, user_id=execution.user_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/compute/test_projection_service.py -k authoritative_prism -q
```

Expected:

```text
1 passed
```

- [ ] **Step 5: Commit**

```bash
git -C /Users/ze/wenjin add \
  backend/src/compute/projection_service.py \
  backend/src/services/latex/prism_status_resolver.py \
  backend/src/services/workspace_prism_service.py \
  backend/tests/compute/test_projection_service.py
git -C /Users/ze/wenjin commit -m "feat: make compute prism projection authoritative"
```

### Task 4: Add Workspace Prism Surface to the Frontend Shell

**Files:**
- Create: `/Users/ze/wenjin/frontend/app/(workbench)/workspaces/[id]/prism/page.tsx`
- Create: `/Users/ze/wenjin/frontend/app/(workbench)/workspaces/[id]/components/SurfaceSwitch.tsx`
- Create: `/Users/ze/wenjin/frontend/tests/unit/v2/prism-surface.test.tsx`
- Modify: `/Users/ze/wenjin/frontend/app/(workbench)/workspaces/[id]/layout.tsx`
- Modify: `/Users/ze/wenjin/frontend/app/(workbench)/workspaces/[id]/page.tsx`
- Modify: `/Users/ze/wenjin/frontend/lib/api/types.ts`
- Modify: `/Users/ze/wenjin/frontend/lib/api/workspace.ts`
- Modify: `/Users/ze/wenjin/frontend/tests/unit/v2/layout.test.tsx`

- [ ] **Step 1: Write the failing frontend tests**

```tsx
// /Users/ze/wenjin/frontend/tests/unit/v2/prism-surface.test.tsx
import { Suspense } from "react";
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import PrismPage from "@/app/(workbench)/workspaces/[id]/prism/page";

describe("workspace prism surface", () => {
  it("renders the manuscript surface switch as active", async () => {
    render(
      <Suspense fallback={<div>Loading</div>}>
        <PrismPage params={Promise.resolve({ id: "ws-1" })} />
      </Suspense>
    );

    expect(screen.getByRole("tab", { name: "Prism" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });
});
```

```tsx
// /Users/ze/wenjin/frontend/tests/unit/v2/layout.test.tsx
it("renders the surface switch for workspace-owned Prism navigation", async () => {
  await act(async () => {
    render(
      <Suspense fallback={<div>Loading</div>}>
        <V2Page params={Promise.resolve({ id: "ws-1" })} />
      </Suspense>
    );
  });

  expect(screen.getByRole("tab", { name: "Workbench" })).toBeInTheDocument();
  expect(screen.getByRole("tab", { name: "Prism" })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd /Users/ze/wenjin/frontend && npx vitest run \
  tests/unit/v2/prism-surface.test.tsx \
  tests/unit/v2/layout.test.tsx
```

Expected:

```text
FAIL ... Cannot find module '@/app/(workbench)/workspaces/[id]/prism/page'
FAIL ... Unable to find role="tab" with name "Prism"
```

- [ ] **Step 3: Implement the Prism surface route and switch**

```tsx
// /Users/ze/wenjin/frontend/app/(workbench)/workspaces/[id]/components/SurfaceSwitch.tsx
"use client";

import Link from "next/link";

type SurfaceSwitchProps = {
  workspaceId: string;
  active: "workbench" | "prism";
};

export function SurfaceSwitch({ workspaceId, active }: SurfaceSwitchProps) {
  return (
    <div role="tablist" aria-label="Workspace surfaces" className="flex gap-2 px-4 pt-3">
      <Link
        role="tab"
        aria-selected={active === "workbench"}
        href={`/workspaces/${workspaceId}`}
        className="rounded-full px-3 py-1.5 text-sm"
      >
        Workbench
      </Link>
      <Link
        role="tab"
        aria-selected={active === "prism"}
        href={`/workspaces/${workspaceId}/prism`}
        className="rounded-full px-3 py-1.5 text-sm"
      >
        Prism
      </Link>
    </div>
  );
}
```

```tsx
// /Users/ze/wenjin/frontend/app/(workbench)/workspaces/[id]/prism/page.tsx
"use client";

import { use } from "react";

import { SurfaceSwitch } from "../components/SurfaceSwitch";
import { LatexEditorShell } from "@/components/latex/LatexEditorShell";
import { useWorkspaceStore } from "@/stores/workspace";

export default function WorkspacePrismPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const latexProjectId = useWorkspaceStore((state) => state.workspace?.prism?.latex_project_id ?? "");

  return (
    <div className="flex h-full flex-col">
      <SurfaceSwitch workspaceId={id} active="prism" />
      <div className="min-h-0 flex-1">
        <LatexEditorShell projectId={latexProjectId} />
      </div>
    </div>
  );
}
```

```ts
// /Users/ze/wenjin/frontend/lib/api/workspace.ts
export async function getWorkspacePrismSurface(
  workspaceId: string,
): Promise<WorkspacePrismSurfaceResponse> {
  const response = await apiClient.get(`/workspaces/${workspaceId}/prism`);
  return response.data;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
cd /Users/ze/wenjin/frontend && npx vitest run \
  tests/unit/v2/prism-surface.test.tsx \
  tests/unit/v2/layout.test.tsx
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Commit**

```bash
git -C /Users/ze/wenjin add \
  frontend/app/'(workbench)'/workspaces/'[id]'/prism/page.tsx \
  frontend/app/'(workbench)'/workspaces/'[id]'/components/SurfaceSwitch.tsx \
  frontend/app/'(workbench)'/workspaces/'[id]'/page.tsx \
  frontend/lib/api/types.ts \
  frontend/lib/api/workspace.ts \
  frontend/tests/unit/v2/prism-surface.test.tsx \
  frontend/tests/unit/v2/layout.test.tsx
git -C /Users/ze/wenjin commit -m "feat: add workspace prism surface"
```

### Task 5: Route Prism Actions Through the Workspace Surface

**Files:**
- Modify: `/Users/ze/wenjin/frontend/lib/block-actions.ts`
- Modify: `/Users/ze/wenjin/frontend/app/(workbench)/workspaces/[id]/components/CompletedView.tsx`
- Modify: `/Users/ze/wenjin/frontend/tests/unit/v2/ExecutionCard.test.tsx`
- Modify: `/Users/ze/wenjin/frontend/tests/e2e/iteration.spec.ts`
- Modify: `/Users/ze/wenjin/frontend/tests/e2e/golden-path.spec.ts`
- Modify: `/Users/ze/wenjin/frontend/tests/e2e/fixtures/workspace-route-mocks.ts`

- [ ] **Step 1: Write the failing action handoff tests**

```tsx
// /Users/ze/wenjin/frontend/tests/unit/v2/ExecutionCard.test.tsx
it("routes Prism review actions through the workspace Prism surface", () => {
  render(
    <ExecutionCard
      execution={{
        id: "ex-1",
        workspace_id: "ws-1",
        feature_id: "writing",
        status: "completed",
        result: {
          result_summary: "写作结果已进入 Prism 待确认区",
          data: { latex_project_id: "latex-1" },
        },
        next_actions: [
          { action: "open_prism", label: "在 WenjinPrism 中继续编辑" },
        ],
      }}
    />,
  );

  expect(
    screen.getByRole("link", { name: "在 WenjinPrism 中继续编辑" }),
  ).toHaveAttribute("href", "/workspaces/ws-1/prism");
});
```

```ts
// /Users/ze/wenjin/frontend/tests/e2e/iteration.spec.ts
test("preview prism changes stays inside the workspace manuscript surface", async ({ page, context }) => {
  await installWorkspaceRouteMocks(page, context, {
    runStreamBody: buildEventStreamBody([
      {
        event: "execution.completed",
        data: {
          execution: {
            id: "ex-1",
            workspace_id: "ws-1",
            status: "completed",
            result: {
              data: { latex_project_id: "latex-1" },
            },
            next_actions: [
              { action: "preview_prism_changes", label: "预览待确认修改" },
            ],
          },
        },
      },
    ]),
  });

  await page.goto("/workspaces/ws-1");
  await page.getByRole("link", { name: "预览待确认修改" }).click();
  await expect(page).toHaveURL(/\\/workspaces\\/ws-1\\/prism$/);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd /Users/ze/wenjin/frontend && npx vitest run tests/unit/v2/ExecutionCard.test.tsx
cd /Users/ze/wenjin/frontend && npx playwright test tests/e2e/iteration.spec.ts --project=chromium
```

Expected:

```text
FAIL ... expected href "/workspaces/ws-1/prism" but received "/latex/latex-1"
FAIL ... URL still matches /latex/latex-1
```

- [ ] **Step 3: Implement workspace Prism action routing**

```ts
// /Users/ze/wenjin/frontend/lib/block-actions.ts
function buildWorkspacePrismHref(
  workspaceId: string | null,
  prismHref: string | null,
): string | null {
  if (workspaceId) {
    return `/workspaces/${workspaceId}/prism`;
  }
  return prismHref;
}

if (actionName === "preview_prism_changes" || actionName === "open_prism") {
  return {
    action: actionName,
    href: buildWorkspacePrismHref(workspaceId ?? null, prismHref ?? null),
    label,
  };
}
```

```tsx
// /Users/ze/wenjin/frontend/app/(workbench)/workspaces/[id]/components/CompletedView.tsx
const prismHref =
  workspaceId
    ? `/workspaces/${workspaceId}/prism`
    : resultPrismUrl || (resultProjectId ? `/latex/${resultProjectId}` : null);
```

```ts
// /Users/ze/wenjin/frontend/tests/e2e/fixtures/workspace-route-mocks.ts
if (pathname === `/api/workspaces/${workspaceId}/prism`) {
  await route.fulfill(
    json({
      workspace_id: workspaceId,
      latex_project_id: "latex-1",
      surface_role: "primary_manuscript",
      url: `/workspaces/${workspaceId}/prism`,
      main_file: "main.tex",
      has_pending_changes: true,
    }),
  );
  return;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
cd /Users/ze/wenjin/frontend && npx vitest run tests/unit/v2/ExecutionCard.test.tsx
cd /Users/ze/wenjin/frontend && npx playwright test tests/e2e/iteration.spec.ts tests/e2e/golden-path.spec.ts --project=chromium
```

Expected:

```text
1 passed
2 passed
```

- [ ] **Step 5: Commit**

```bash
git -C /Users/ze/wenjin add \
  frontend/lib/block-actions.ts \
  frontend/app/'(workbench)'/workspaces/'[id]'/components/CompletedView.tsx \
  frontend/tests/unit/v2/ExecutionCard.test.tsx \
  frontend/tests/e2e/fixtures/workspace-route-mocks.ts \
  frontend/tests/e2e/iteration.spec.ts \
  frontend/tests/e2e/golden-path.spec.ts
git -C /Users/ze/wenjin commit -m "feat: route prism actions through workspace surface"
```

## Self-Review

### Spec coverage

- Explicit binding model: covered by Task 1
- Workspace-owned Prism routes: covered by Task 2
- Authoritative compute projection: covered by Task 3
- Workspace shell / surface switch: covered by Task 4
- Prism action contract and navigation: covered by Task 5

No spec sections are currently unassigned.

### Placeholder scan

- No `TODO` / `TBD` / “implement later” placeholders remain
- All tasks include explicit files, commands, and concrete code snippets

### Type consistency

- Canonical backend field names used consistently:
  - `workspace_id`
  - `surface_role`
  - `primary_manuscript`
- Canonical frontend route used consistently:
  - `/workspaces/:id/prism`
- `WorkspacePrismService` is the only new product-level service introduced in later tasks

## Execution Handoff

Plan complete and saved to `/Users/ze/wenjin/docs/superpowers/plans/2026-05-19-workspace-prism-surface.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
