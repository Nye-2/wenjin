# DataService Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use engineering-context:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Centralize Wenjin database models, table ownership, repositories, data-domain services, review state transitions, and read projections under `backend/src/dataservice`.

**Architecture:** Keep `backend/src/database` as infrastructure only: SQLAlchemy `Base`, engine, session, and Alembic bootstrap. Move new domain models into `backend/src/dataservice/models`, route database reads/writes through repositories, and expose workspace use cases through DataService domain services and projection builders. Migration is done by bounded domain slices with no runtime fallback or dual-write layer.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy async, Alembic, Pydantic v2, pytest, PostgreSQL JSONB, SQLite-compatible test models where needed.

---

## Source Documents

- `/Users/ze/wenjin/docs/superpowers/specs/2026-05-20-super-agent-capability-system-design.md`
- `/Users/ze/wenjin/docs/superpowers/specs/2026-05-20-wenjin-native-prism-integration-overview.md`
- `/Users/ze/wenjin/AGENTS.md`

## Design Rules

1. `backend/src/database` becomes infrastructure only. After convergence, no new business model belongs under `backend/src/database/models`.
2. `backend/src/dataservice/models` owns business table definitions.
3. `backend/src/dataservice/repositories` is the only layer that imports ORM models and executes SQLAlchemy statements for business data.
4. `backend/src/dataservice/services` owns business state transitions and must use repositories.
5. Routers, agents, Compute, execution runtime, Prism services, and sandbox runner must call DataService services or projections, not database models directly.
6. Workspace-scoped data access must require `workspace_id`; user-owned entry points must also validate `user_id`.
7. Review/apply actions are transactional: review state change and target write commit together.
8. Agent-produced artifacts never write primary workspace documents directly; they enter `ReviewItem v2` first.
9. No compatibility layer, alias table, fallback read, or dual-write path after each domain slice is migrated.

## Target File Structure

### Create

- `/Users/ze/wenjin/backend/src/dataservice/__init__.py`
- `/Users/ze/wenjin/backend/src/dataservice/contracts/__init__.py`
- `/Users/ze/wenjin/backend/src/dataservice/contracts/common.py`
- `/Users/ze/wenjin/backend/src/dataservice/contracts/review.py`
- `/Users/ze/wenjin/backend/src/dataservice/contracts/prism_document.py`
- `/Users/ze/wenjin/backend/src/dataservice/contracts/sandbox_artifact.py`
- `/Users/ze/wenjin/backend/src/dataservice/contracts/provenance.py`
- `/Users/ze/wenjin/backend/src/dataservice/models/__init__.py`
- `/Users/ze/wenjin/backend/src/dataservice/models/review.py`
- `/Users/ze/wenjin/backend/src/dataservice/models/prism_document.py`
- `/Users/ze/wenjin/backend/src/dataservice/models/sandbox_artifact.py`
- `/Users/ze/wenjin/backend/src/dataservice/models/provenance.py`
- `/Users/ze/wenjin/backend/src/dataservice/repositories/__init__.py`
- `/Users/ze/wenjin/backend/src/dataservice/repositories/rooms.py`
- `/Users/ze/wenjin/backend/src/dataservice/repositories/review_items.py`
- `/Users/ze/wenjin/backend/src/dataservice/repositories/prism_documents.py`
- `/Users/ze/wenjin/backend/src/dataservice/repositories/sandbox_artifacts.py`
- `/Users/ze/wenjin/backend/src/dataservice/repositories/provenance.py`
- `/Users/ze/wenjin/backend/src/dataservice/services/__init__.py`
- `/Users/ze/wenjin/backend/src/dataservice/services/workspace_data.py`
- `/Users/ze/wenjin/backend/src/dataservice/services/workspace_rooms.py`
- `/Users/ze/wenjin/backend/src/dataservice/services/review_workflow.py`
- `/Users/ze/wenjin/backend/src/dataservice/services/prism_documents.py`
- `/Users/ze/wenjin/backend/src/dataservice/services/sandbox_artifacts.py`
- `/Users/ze/wenjin/backend/src/dataservice/services/provenance.py`
- `/Users/ze/wenjin/backend/src/dataservice/projections/__init__.py`
- `/Users/ze/wenjin/backend/src/dataservice/projections/workspace_context.py`
- `/Users/ze/wenjin/backend/src/dataservice/projections/prism_surface.py`
- `/Users/ze/wenjin/backend/src/dataservice/projections/compute_launch.py`
- `/Users/ze/wenjin/backend/src/dataservice/guards/__init__.py`
- `/Users/ze/wenjin/backend/alembic/versions/059_dataservice_review_prism_sandbox.py`
- `/Users/ze/wenjin/backend/tests/architecture/test_dataservice_boundaries.py`
- `/Users/ze/wenjin/backend/tests/dataservice/test_review_workflow_service.py`
- `/Users/ze/wenjin/backend/tests/dataservice/test_prism_document_repository.py`
- `/Users/ze/wenjin/backend/tests/dataservice/test_sandbox_artifact_repository.py`
- `/Users/ze/wenjin/backend/tests/dataservice/test_workspace_context_projection.py`

### Modify

- `/Users/ze/wenjin/backend/src/database/models/__init__.py`
- `/Users/ze/wenjin/backend/alembic/env.py`
- `/Users/ze/wenjin/backend/src/services/execution_commit_service.py`
- `/Users/ze/wenjin/backend/src/services/prism_review_service.py`
- `/Users/ze/wenjin/backend/src/services/workspace_prism_service.py`
- `/Users/ze/wenjin/backend/src/compute/projection_service.py`
- `/Users/ze/wenjin/backend/src/gateway/routers/workspaces.py`
- `/Users/ze/wenjin/backend/src/gateway/routers/latex.py`
- `/Users/ze/wenjin/backend/src/agents/lead_agent/v2/runtime.py`

## Domain Ownership Map

| Domain | Current Home | Target Home | Migration Commit |
| --- | --- | --- | --- |
| Workspace core | `academic/services/workspace_service.py`, `database/models/workspace.py` | `dataservice/repositories/workspaces.py`, `dataservice/services/workspace_data.py` | after architecture guard |
| Rooms | `services/rooms/*`, `database/models/{library_item,document_v2,decision,memory_fact,workspace_task,run_history,sandbox}.py` | `dataservice/repositories/rooms.py`, `dataservice/services/workspace_rooms.py` | first behavioral slice |
| Prism review | `database/models/prism.py`, `services/prism_review_service.py` | `dataservice/models/review.py`, `dataservice/repositories/review_items.py`, `dataservice/services/review_workflow.py` | second behavioral slice |
| Prism document | `LatexProject`, `workspace_prism_service.py`, `services/latex/*` | `dataservice/models/prism_document.py`, `dataservice/repositories/prism_documents.py`, `dataservice/services/prism_documents.py` | third behavioral slice |
| Sandbox artifacts | `services/rooms/sandbox_service.py`, execution payloads | `dataservice/models/sandbox_artifact.py`, `dataservice/repositories/sandbox_artifacts.py` | fourth behavioral slice |
| Provenance | `PrismSourceLink`, references services, review payloads | `dataservice/models/provenance.py`, `dataservice/services/provenance.py` | fourth behavioral slice |
| Capability catalog | `database/models/capability*.py`, `services/capability_*`, `services/admin_*` | `dataservice/repositories/capabilities.py`, `dataservice/services/capability_catalog.py` | after schema v2 |

## Task 1: Add DataService Boundary Test

**Files:**
- Create: `/Users/ze/wenjin/backend/tests/architecture/test_dataservice_boundaries.py`

- [ ] **Step 1: Write the architecture guard**

```python
from __future__ import annotations

import ast
from pathlib import Path

BACKEND_SRC = Path(__file__).resolve().parents[2] / "src"

ALLOWED_MODEL_IMPORT_PREFIXES = (
    "database",
    "dataservice",
    "alembic",
)

ALLOWED_SQL_EXECUTE_PREFIXES = (
    "dataservice",
    "database",
    "alembic",
)


def _module_path(path: Path) -> str:
    rel = path.relative_to(BACKEND_SRC).with_suffix("")
    return ".".join(rel.parts)


def _iter_python_files() -> list[Path]:
    return [
        path
        for path in BACKEND_SRC.rglob("*.py")
        if "__pycache__" not in path.parts
    ]


def test_new_business_code_does_not_import_database_models_outside_dataservice() -> None:
    violations: list[str] = []
    for path in _iter_python_files():
        module = _module_path(path)
        if module.startswith(ALLOWED_MODEL_IMPORT_PREFIXES):
            continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("src.database.models") or node.module == "src.database":
                    violations.append(f"{path}:{node.lineno} imports {node.module}")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("src.database.models"):
                        violations.append(f"{path}:{node.lineno} imports {alias.name}")

    assert violations == []
```

- [ ] **Step 2: Run the guard and capture current violations**

Run:

```bash
cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py -q
```

Expected:

```text
FAIL ... existing direct imports are reported
```

- [ ] **Step 3: Add a temporary allowlist for existing violations**

The first commit should not rewrite the whole backend. Add an explicit `LEGACY_ALLOWED_FILES` set containing the currently reported files. The test must still fail for any new non-DataService direct import.

- [ ] **Step 4: Run the guard again**

Run:

```bash
cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py -q
```

Expected:

```text
1 passed
```

- [ ] **Step 5: Commit**

```bash
git add backend/tests/architecture/test_dataservice_boundaries.py
git commit -m "test: guard dataservice database boundaries"
```

## Task 2: Create DataService Package Skeleton

**Files:**
- Create all `backend/src/dataservice/**/__init__.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/contracts/common.py`

- [ ] **Step 1: Create package skeleton**

Create empty package files for `contracts`, `models`, `repositories`, `services`, `projections`, and `guards`.

- [ ] **Step 2: Add common contracts**

```python
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class WorkspaceScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str = Field(min_length=1)
    user_id: str | None = None


class PageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=50, ge=1, le=200)
    cursor: str | None = None


class PageResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[dict]
    next_cursor: str | None = None


ReviewState = Literal["pending", "applied", "rejected", "deferred", "reverted"]


class StateTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_state: str
    to_state: str
    actor_id: str
    reason: str | None = None
    occurred_at: datetime
```

- [ ] **Step 3: Run import smoke test**

Run:

```bash
cd /Users/ze/wenjin/backend && .venv/bin/python - <<'PY'
from src.dataservice.contracts.common import WorkspaceScope
print(WorkspaceScope(workspace_id="ws-1").model_dump())
PY
```

Expected:

```text
{'workspace_id': 'ws-1', 'user_id': None}
```

- [ ] **Step 4: Commit**

```bash
git add backend/src/dataservice
git commit -m "feat: add dataservice package skeleton"
```

## Task 3: Move Room Writes Behind WorkspaceRoomService

**Files:**
- Create: `/Users/ze/wenjin/backend/src/dataservice/repositories/rooms.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/services/workspace_rooms.py`
- Modify: `/Users/ze/wenjin/backend/src/services/execution_commit_service.py`
- Test: `/Users/ze/wenjin/backend/tests/services/test_execution_commit_service.py`

- [ ] **Step 1: Write tests for one-pass room commit through DataService**

Test that accepted `library_item`, `document`, `decision`, `memory_fact`, and `task` outputs are committed by `WorkspaceRoomService.commit_reviewed_outputs()` and return room targets.

- [ ] **Step 2: Implement `RoomRepository`**

`RoomRepository` owns inserts for Library, Documents, Decisions, Memory, Tasks, Sandbox, and Run History. It receives an `AsyncSession` and never commits internally.

- [ ] **Step 3: Implement `WorkspaceRoomService`**

`WorkspaceRoomService` converts accepted output payloads to repository writes. It returns counts and target ids. It does not publish events and does not call Redis.

- [ ] **Step 4: Refactor `ExecutionCommitService`**

Replace direct room service dependencies with one `WorkspaceRoomService`. Keep idempotency, event publish, audit, and referral callback in `ExecutionCommitService`.

- [ ] **Step 5: Run tests**

Run:

```bash
cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/services/test_execution_commit_service.py tests/architecture/test_dataservice_boundaries.py -q
```

Expected:

```text
all selected tests pass
```

- [ ] **Step 6: Commit**

```bash
git add backend/src/dataservice backend/src/services/execution_commit_service.py backend/tests/services/test_execution_commit_service.py backend/tests/architecture/test_dataservice_boundaries.py
git commit -m "feat: route room commits through dataservice"
```

## Task 4: Add ReviewItem v2 Model And Workflow Service

**Files:**
- Create: `/Users/ze/wenjin/backend/src/dataservice/contracts/review.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/models/review.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/repositories/review_items.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/services/review_workflow.py`
- Create: `/Users/ze/wenjin/backend/tests/dataservice/test_review_workflow_service.py`
- Create migration: `/Users/ze/wenjin/backend/alembic/versions/059_dataservice_review_prism_sandbox.py`

- [ ] **Step 1: Define review target contract**

`ReviewTarget.kind` supports:

```text
room_document
room_library_item
room_decision_candidate
room_memory_candidate
room_task
prism_file_change
sandbox_artifact
```

- [ ] **Step 2: Create DB model**

Create `review_items` and `review_action_logs`. Required columns: `workspace_id`, `producer_kind`, `producer_id`, `target_kind`, `target_payload`, `preview_payload`, `status`, `validation`, `applied_at`, `reverted_at`.

- [ ] **Step 3: Implement repository**

Repository methods:

```text
create_pending()
get_for_update()
list_for_workspace()
transition()
record_action()
```

- [ ] **Step 4: Implement state machine**

Allowed transitions:

```text
pending -> applied
pending -> rejected
pending -> deferred
deferred -> applied
deferred -> rejected
applied -> reverted
```

- [ ] **Step 5: Run tests**

Run:

```bash
cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/dataservice/test_review_workflow_service.py -q
```

Expected:

```text
all review workflow tests pass
```

- [ ] **Step 6: Commit**

```bash
git add backend/src/dataservice backend/alembic/versions/059_dataservice_review_prism_sandbox.py backend/tests/dataservice/test_review_workflow_service.py
git commit -m "feat: add dataservice review workflow"
```

## Task 5: Add Universal Prism Document Data Model

**Files:**
- Create: `/Users/ze/wenjin/backend/src/dataservice/contracts/prism_document.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/models/prism_document.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/repositories/prism_documents.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/services/prism_documents.py`
- Modify migration: `/Users/ze/wenjin/backend/alembic/versions/059_dataservice_review_prism_sandbox.py`
- Test: `/Users/ze/wenjin/backend/tests/dataservice/test_prism_document_repository.py`

- [ ] **Step 1: Define Prism document tables**

Tables:

```text
prism_projects
prism_documents
prism_files
prism_renders
```

Required relations:

```text
workspace_id -> workspaces.id
project_id -> prism_projects.id
document_id -> prism_documents.id
```

- [ ] **Step 2: Define adapters**

Supported initial adapters:

```text
latex
structured_markdown
docx_form
```

- [ ] **Step 3: Implement repository**

Repository methods:

```text
ensure_workspace_project()
get_workspace_project()
list_documents()
upsert_file()
list_files()
record_render()
```

- [ ] **Step 4: Implement service**

`PrismDocumentService` owns document creation, file update, render metadata, and target file selection. It must not apply agent changes directly; agent changes enter ReviewItem v2.

- [ ] **Step 5: Run tests**

Run:

```bash
cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/dataservice/test_prism_document_repository.py -q
```

Expected:

```text
all Prism document repository tests pass
```

- [ ] **Step 6: Commit**

```bash
git add backend/src/dataservice backend/alembic/versions/059_dataservice_review_prism_sandbox.py backend/tests/dataservice/test_prism_document_repository.py
git commit -m "feat: add universal prism document data model"
```

## Task 6: Add Sandbox Artifact And Provenance Domains

**Files:**
- Create: `/Users/ze/wenjin/backend/src/dataservice/contracts/sandbox_artifact.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/contracts/provenance.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/models/sandbox_artifact.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/models/provenance.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/repositories/sandbox_artifacts.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/repositories/provenance.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/services/sandbox_artifacts.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/services/provenance.py`
- Modify migration: `/Users/ze/wenjin/backend/alembic/versions/059_dataservice_review_prism_sandbox.py`
- Test: `/Users/ze/wenjin/backend/tests/dataservice/test_sandbox_artifact_repository.py`

- [ ] **Step 1: Define sandbox artifact tables**

Tables:

```text
sandbox_job_records
sandbox_artifacts
```

Required fields: `workspace_id`, `execution_id`, `job_id`, `input_hashes`, `script_hash`, `output_path`, `mime_type`, `preview_metadata`, `review_item_id`.

- [ ] **Step 2: Define provenance tables**

Tables:

```text
provenance_links
source_anchors
```

Required fields: `workspace_id`, `source_kind`, `source_id`, `target_kind`, `target_id`, `quote`, `section_key`, `confidence`, `metadata_json`.

- [ ] **Step 3: Implement services**

`SandboxArtifactService.record_artifact()` creates artifact metadata and a pending review item. `ProvenanceService.link()` records links between source materials, sandbox outputs, and Prism document sections.

- [ ] **Step 4: Run tests**

Run:

```bash
cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/dataservice/test_sandbox_artifact_repository.py -q
```

Expected:

```text
all sandbox artifact tests pass
```

- [ ] **Step 5: Commit**

```bash
git add backend/src/dataservice backend/alembic/versions/059_dataservice_review_prism_sandbox.py backend/tests/dataservice/test_sandbox_artifact_repository.py
git commit -m "feat: add sandbox artifact and provenance data domains"
```

## Task 7: Build Workspace Context And Compute Projections

**Files:**
- Create: `/Users/ze/wenjin/backend/src/dataservice/projections/workspace_context.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/projections/prism_surface.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/projections/compute_launch.py`
- Modify: `/Users/ze/wenjin/backend/src/services/workspace_prism_service.py`
- Modify: `/Users/ze/wenjin/backend/src/compute/projection_service.py`
- Test: `/Users/ze/wenjin/backend/tests/dataservice/test_workspace_context_projection.py`
- Test: `/Users/ze/wenjin/backend/tests/compute/test_projection_service.py`

- [ ] **Step 1: Define projection contracts**

Projection builders return plain dictionaries or Pydantic response models. They do not expose ORM rows.

- [ ] **Step 2: Route WorkspacePrismService through projection**

`WorkspacePrismService.get_surface_projection()` should delegate to `PrismSurfaceProjectionBuilder`.

- [ ] **Step 3: Route Compute projection through projection**

`compute/projection_service.py` should read authoritative Prism/review state via `ComputeLaunchProjectionBuilder`.

- [ ] **Step 4: Run tests**

Run:

```bash
cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/dataservice/test_workspace_context_projection.py tests/compute/test_projection_service.py -q
```

Expected:

```text
all projection tests pass
```

- [ ] **Step 5: Commit**

```bash
git add backend/src/dataservice backend/src/services/workspace_prism_service.py backend/src/compute/projection_service.py backend/tests/dataservice/test_workspace_context_projection.py backend/tests/compute/test_projection_service.py
git commit -m "feat: serve workspace projections from dataservice"
```

## Task 8: Migrate Consumers And Delete Old Data Services

**Files:**
- Modify: `/Users/ze/wenjin/backend/src/gateway/routers/workspaces.py`
- Modify: `/Users/ze/wenjin/backend/src/gateway/routers/latex.py`
- Modify: `/Users/ze/wenjin/backend/src/agents/lead_agent/v2/runtime.py`
- Modify: `/Users/ze/wenjin/backend/src/services/prism_review_service.py`
- Modify: `/Users/ze/wenjin/backend/src/services/rooms/*.py`
- Modify: `/Users/ze/wenjin/backend/tests/architecture/test_dataservice_boundaries.py`

- [ ] **Step 1: Replace direct imports in routers**

Routers should depend on DataService domain services via dependency providers.

- [ ] **Step 2: Replace direct imports in agents and Compute**

Agent runtime should load review/projection data through DataService projection builders.

- [ ] **Step 3: Delete migrated old service files**

Delete a service only after all call sites point to DataService and tests pass. The first deletion targets are room services already replaced by `WorkspaceRoomService`.

- [ ] **Step 4: Tighten architecture guard**

Remove migrated files from `LEGACY_ALLOWED_FILES`. The test should prove direct model imports are shrinking per slice.

- [ ] **Step 5: Run backend selected tests**

Run:

```bash
cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/dataservice tests/services tests/compute tests/gateway/routers tests/architecture -q
```

Expected:

```text
all selected backend tests pass
```

- [ ] **Step 6: Commit**

```bash
git add backend/src backend/tests
git commit -m "refactor: migrate data consumers to dataservice"
```

## Task 9: Final Cutover Gates

**Files:**
- Modify: `/Users/ze/wenjin/docs/superpowers/specs/2026-05-20-super-agent-capability-system-design.md`
- Modify: `/Users/ze/wenjin/docs/superpowers/plans/2026-05-20-dataservice-convergence.md`

- [ ] **Step 1: Run schema and migration checks**

Run:

```bash
cd /Users/ze/wenjin/backend && alembic upgrade head
cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/dataservice tests/architecture -q
```

Expected:

```text
alembic upgrade succeeds
all DataService and architecture tests pass
```

- [ ] **Step 2: Run capability path smoke tests**

Run:

```bash
cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/agents/lead_agent/v2 tests/services/test_cross_ref_validator.py tests/seed/test_capability_seeds_load.py -q
```

Expected:

```text
all selected capability tests pass
```

- [ ] **Step 3: Update docs**

Update source docs to say DataService is active and list remaining legacy allowlist files if any.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-05-20-super-agent-capability-system-design.md docs/superpowers/plans/2026-05-20-dataservice-convergence.md backend
git commit -m "docs: close dataservice convergence gates"
```

## Execution Notes

- Start with Task 1 and Task 2 before any business migration. They create the safety rail.
- Migrate by domain slice. Do not mix Prism universal document, review item v2, sandbox artifacts, and capability catalog in the same implementation commit.
- Keep each repository non-committing. Transaction ownership belongs to DataService domain services.
- Keep old model moves direct and bounded. When a domain moves, update imports in the same commit and tighten the architecture guard.
- Do not introduce fallback readers, duplicate writes, or long-lived compatibility wrappers.

## Verification Matrix

| Gate | Command |
| --- | --- |
| Architecture | `cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py -q` |
| DataService unit | `cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/dataservice -q` |
| Compute projection | `cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/compute/test_projection_service.py -q` |
| Capability schema | `cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/services/test_cross_ref_validator.py tests/seed/test_capability_seeds_load.py -q` |
| Migration | `cd /Users/ze/wenjin/backend && alembic upgrade head` |

## Open Engineering Risks

1. Existing direct DB imports are broad. The architecture guard needs a legacy allowlist in the first commit, then the allowlist must shrink with each slice.
2. Moving all models at once would create high import churn. New models should start in DataService immediately; old models move only when their domain is migrated.
3. `ExecutionCommitService` currently owns idempotency, room writes, events, audit, and referral side effects. DataService should first absorb room writes and review state transitions, while side effects stay at the application service boundary.
4. Prism currently still has LaTeX-specific naming. DataService should create universal Prism tables first, then migrate workspace-owned LaTeX data into those tables.
5. SQLite test mirrors need updates when new SQLAlchemy models are added; tests should prefer production models where possible to avoid model drift.
