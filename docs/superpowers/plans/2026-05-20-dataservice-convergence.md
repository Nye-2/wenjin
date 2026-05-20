# DataService SSOT Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use engineering-context:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign Wenjin's data layer into a stable DataService SSOT so database models, table ownership, repositories, transactions, review state, Prism documents, sandbox artifacts, provenance, and projections have one canonical home.

**Architecture:** This is not a wrapper over the existing services. It is a one-time model convergence: define canonical DataService models first, migrate redundant legacy tables into them, cut consumers over in domain slices, then delete or archive old tables without runtime fallback, dual-write, or alias readers. `backend/src/database` becomes infrastructure only; `backend/src/dataservice` owns business data models, repositories, unit-of-work, domain services, and projections.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy async, Alembic, Pydantic v2, pytest, PostgreSQL JSONB, SQLite-compatible tests only where production models cannot be used directly.

---

## Source Documents

- `/Users/ze/wenjin/docs/superpowers/specs/2026-05-20-super-agent-capability-system-design.md`
- `/Users/ze/wenjin/docs/superpowers/specs/2026-05-20-wenjin-native-prism-integration-overview.md`
- `/Users/ze/wenjin/AGENTS.md`

## Planning Premise

The current database has accumulated migration-era overlap. DataService should use this window to redraw the canonical model instead of preserving old table boundaries. After this convergence, DataService should be treated as a stable platform layer; future feature work should extend typed models and contracts, not create parallel tables for the same concept.

## Current Redundancy Audit

| Area | Existing Overlap | SSOT Decision |
| --- | --- | --- |
| Workspace/thread binding | `workspaces.thread_id` and `threads.workspace_id` both express workspace/thread relationship. | Keep `threads.workspace_id` for membership. Use `workspaces.active_thread_id` only for selected active thread. Do not infer membership from active thread. |
| Execution lifecycle | `executions`, `execution_nodes`, `task_records`, `subagent_task_records`, `workspace_run`, `run_history`, `compute_sessions` all express run/task state. | `executions` + `execution_nodes` are execution SSOT. Queue/task rows are infrastructure only. Run history and compute state become projections from execution/review data. |
| User-facing tasks | `task_records` and `workspace_tasks` both use "task" naming. | `workspace_tasks` are user-visible work items. `task_records` are worker queue/infrastructure and must not be product state. |
| Library/reference | `library_items` and `workspace_references` both represent research materials. | `workspace_references` is source/library SSOT. Generic uploaded/generated files go to `workspace_assets`; legacy `library_items` migrates into source/reference rows where possible. |
| Documents/artifacts/assets | `documents_v2`, `artifacts`, `generation_records`, `sandboxes`, reference assets, and inline document metadata all store output/file concepts. | `workspace_assets` is generic file/material SSOT. Prism primary documents and references have specialized tables that link to assets. Sandbox artifacts are execution-produced assets plus reproducibility metadata. |
| Prism document | `latex_projects` contains user project, workspace binding, file ordering, LLM config, adapter config, and surface role. | `prism_projects` / `prism_documents` / `prism_files` own workspace primary documents. LaTeX becomes an adapter, not the root model. |
| Review state | `prism_review_items`, `TaskReport.outputs`, frontend ResultCard state, and commit payloads all express reviewable outputs. | `review_items` is the only review/apply state source. Prism changes, room writes, and sandbox artifacts are target kinds. |
| Provenance | `prism_source_links`, `reference_usage_events`, review payload source fields, and artifact metadata all link claims to sources. | `provenance_links` is the canonical source-target graph. Domain-specific projections read from it. |
| Capability schema | `capabilities.runtime`, `brief_schema`, `graph_template`, `dashboard_meta`, and skill `config` carry mixed v1/v2 semantics. | `capability_definitions` and `capability_skills` are versioned catalog models with strict v2 schema payloads and typed searchable columns. |
| Workspace settings | `workspaces.config` and `workspace_settings.metadata_json` both store workspace config. | `workspace_settings` owns user-editable settings. `workspaces` keeps identity fields and immutable/top-level metadata only. |

## Canonical Model Principles

1. **One concept, one table family.** A model may have projections, but it must have exactly one write source.
2. **Repositories never commit.** All transaction ownership lives in `DataServiceUnitOfWork` or a domain service that owns a complete use case.
3. **No product state in queue tables.** Worker queue/task infrastructure may reference product entities but cannot become the user-visible state source.
4. **No untyped payload as primary schema.** JSONB is allowed for extension payloads, but core identity, state, ownership, timestamps, and target links must be typed columns.
5. **Workspace-scoped by default.** Workspace data tables require `workspace_id`; user-owned entry points validate both `user_id` and `workspace_id`.
6. **Review before materialization.** Agent-produced document changes, room writes, and sandbox artifacts enter `review_items` before applying to user-facing rooms or Prism primary documents.
7. **Append-only where history matters.** Review actions, provenance links, file versions, and execution nodes should preserve history instead of overwriting meaning.
8. **Cutover, not compatibility.** During a domain migration, old data is copied into canonical tables and consumers are switched to the canonical repository in the same release slice.

## Accepted Architecture Decisions

1. **Cutover deployment style**: use a maintenance-window cutover. Run data migrations, deploy app code reading canonical tables, and do not build dual-write.
2. **Legacy table retention**: rename migrated legacy tables to `_legacy_20260520` for one release, exclude them from runtime, and drop them after backup validation.
3. **Scope of database ownership**: DataService ultimately owns all business models, including auth, admin, billing, and referral. The first milestone focuses on workspace / Super Agent Harness data.
4. **File/content storage policy**: DB stores metadata and small inline text only. Large binaries, PDFs, DOCX, images, compile outputs, and sandbox outputs stay in managed file/object storage with `workspace_assets` metadata.
5. **Execution vs task queue semantics**: `executions` is product run SSOT. `task_records` is worker queue infrastructure only and must not feed user-facing Compute or Run History after convergence.
6. **Source library naming**: product and code concepts converge on `Source`. `workspace_references` can be physically migrated to `sources`; do not retain LibraryItem/Reference as two product concepts.

## Development Norms And Architecture Gates

These rules are mandatory for DataService work:

1. **SSOT doc first**: no model or migration work starts until `/Users/ze/wenjin/docs/superpowers/specs/2026-05-20-dataservice-ssot-model.md` defines the canonical ERD and legacy-to-canonical migration map.
2. **One domain per commit**: do not mix review, Prism document, source/assets, sandbox/provenance, execution, and rooms in one implementation commit.
3. **One migration per domain group**: never edit a committed migration. Add the next numbered migration for follow-up changes.
4. **Architecture guard first**: the first code task must add the DataService boundary guard with a shrinking legacy allowlist.
5. **No new direct DB imports**: new code outside DataService must not import `src.database.models` or business models from `src.database`.
6. **No direct business queries outside DataService**: routers, agents, Compute, Prism, and execution runtime must not call `session.execute(select(...))` for business data.
7. **Repository discipline**: repositories execute queries and writes but never commit, publish events, or call LLM/tools.
8. **Unit-of-work discipline**: domain services own use-case transactions through `DataServiceUnitOfWork`.
9. **Review state discipline**: all agent-produced materialization targets go through `review_items`; direct writes are allowed only for user edits and infrastructure bookkeeping.
10. **Projection discipline**: UI/agent/Compute read models come from `dataservice/projections`; projections return Pydantic contracts or plain dictionaries, never ORM rows.
11. **Migration proof**: each data-copy migration must include row-count checks and fail loudly on unmapped legacy rows.
12. **Legacy deletion proof**: a legacy table or runtime path can be archived/deleted only after its consumer imports are removed and architecture tests pass.
13. **Doc sync**: every domain cutover updates this plan and the SSOT model spec in the same commit.
14. **Test floor**: each domain commit runs architecture tests, domain unit tests, migration upgrade, and affected service/projection tests.

## Target Package Structure

```text
backend/src/dataservice/
  __init__.py
  unit_of_work.py
  contracts/
    common.py
    workspace.py
    catalog.py
    execution.py
    review.py
    prism_document.py
    source.py
    asset.py
    sandbox_artifact.py
    provenance.py
    rooms.py
  models/
    __init__.py
    workspace.py
    catalog.py
    execution.py
    review.py
    prism_document.py
    source.py
    asset.py
    sandbox_artifact.py
    provenance.py
    rooms.py
    audit.py
  repositories/
    __init__.py
    workspaces.py
    catalog.py
    executions.py
    review_items.py
    prism_documents.py
    sources.py
    assets.py
    sandbox_artifacts.py
    provenance.py
    rooms.py
  services/
    __init__.py
    workspace_data.py
    capability_catalog.py
    execution_log.py
    review_workflow.py
    prism_documents.py
    source_library.py
    asset_store.py
    sandbox_artifacts.py
    provenance.py
    workspace_rooms.py
  projections/
    __init__.py
    workspace_context.py
    prism_surface.py
    compute_launch.py
    run_history.py
    activity.py
  guards/
    __init__.py
```

## Canonical Table Families

### 1. Workspace Core

Canonical tables:

- `workspaces`
- `workspace_settings`
- `threads`

SSOT rules:

- `workspaces` stores identity: owner, name, type, discipline, description, active thread pointer.
- `workspace_settings` stores mutable user/workspace settings.
- `threads.workspace_id` stores conversation membership.
- `workspaces.active_thread_id` points to the currently selected thread but does not define membership.

Legacy cleanup:

- Rename `workspaces.thread_id` to `active_thread_id`.
- Move rollout/config JSON from `workspaces.config` into `workspace_settings.settings_json`.

### 2. Capability Catalog

Canonical tables:

- `capability_definitions`
- `capability_skills`
- `capability_seed_revisions`

SSOT rules:

- Capability definitions are versioned by `schema_version`.
- Searchable columns: `id`, `workspace_type`, `enabled`, `tier`, `entry_surface`, `display_name`, `schema_version`.
- Full v2 schema lives in `definition_json`, validated by Pydantic.
- Skill v2 schema lives in `skill_json`, not a generic `config`.

Legacy cleanup:

- Migrate existing `capabilities` rows to `capability_definitions`.
- Remove v1 runtime fields after v2 seeds are active.

### 3. Execution And Compute

Canonical tables:

- `executions`
- `execution_nodes`
- `execution_events`

Projection-only or infrastructure:

- `compute_sessions` becomes projection/cache and can be rebuilt.
- `task_records` becomes worker queue infrastructure or is removed if Celery/worker state is enough.
- `subagent_task_records` migrates into `execution_nodes` / `execution_events`.
- `workspace_run` migrates into `executions`.
- `run_history` becomes `run_history` projection from executions + review items, or a materialized projection table owned by DataService.

SSOT rules:

- Product execution state is `executions.status`.
- Node-level status is `execution_nodes.status`.
- Live timeline/logging is `execution_events`.
- Run history UI reads projection, not a separately authored product table.

### 4. Review Workflow

Canonical tables:

- `review_items`
- `review_action_logs`

Required typed columns:

- `workspace_id`
- `producer_kind`
- `producer_id`
- `target_kind`
- `target_id`
- `status`
- `title`
- `summary`
- `created_by`
- `applied_at`
- `reverted_at`

JSONB extension columns:

- `target_payload`
- `preview_payload`
- `validation_json`
- `metadata_json`

Target kinds:

- `prism_file_change`
- `room_document`
- `room_reference`
- `room_decision`
- `room_memory`
- `room_task`
- `sandbox_artifact`
- `workspace_asset`

SSOT rules:

- `review_items.status` is the only acceptance state.
- Applying a review item writes the target and state transition in one transaction.
- Prism-specific review rows migrate into generic `review_items`.

### 5. Prism Universal Document

Canonical tables:

- `prism_projects`
- `prism_documents`
- `prism_files`
- `prism_file_versions`
- `prism_renders`
- `prism_protected_scopes`

SSOT rules:

- `prism_projects.workspace_id` owns one or more document surfaces.
- `prism_documents` owns primary workspace-authored documents.
- `prism_files` stores current editable file metadata/content pointer.
- `prism_file_versions` stores applied/history snapshots.
- `prism_renders` stores preview/compile/export metadata.
- LaTeX is an adapter value, not a root model.

Legacy cleanup:

- Migrate workspace-owned `latex_projects` into `prism_projects`.
- Preserve LaTeX files through adapter metadata.
- Remove workspace binding from `latex_projects` after migration, or delete `latex_projects` when adapter no longer needs it.

### 6. Source Library

Canonical tables:

- `sources`
- `source_external_ids`
- `source_assets`
- `source_outline_nodes`
- `source_text_units`
- `source_bibtex_snapshots`

SSOT rules:

- Research/library materials live under `sources`.
- Uploaded papers, PDFs, markdown extracts, images, and fulltext assets link through `source_assets`.
- `source_text_units` owns searchable text chunks.
- Citation key uniqueness is workspace-scoped.

Legacy cleanup:

- Migrate `workspace_references*` into the new `sources*` naming or keep the physical table only if renamed in model/API to Source.
- Migrate `library_items` into `sources` or `workspace_assets` depending on item type.

### 7. Workspace Assets And Sandbox Artifacts

Canonical tables:

- `workspace_assets`
- `sandbox_job_records`
- `sandbox_artifacts`

SSOT rules:

- `workspace_assets` stores metadata for files/materials created or uploaded in a workspace.
- Asset binary/content storage stays outside DB unless content is small inline text.
- `sandbox_artifacts` stores reproducibility metadata and links to a `workspace_asset`.
- Sandbox job records store runtime image, command/script hash, input hashes, network policy, resource limits, and result status.

Legacy cleanup:

- Migrate `documents_v2`, generic `artifacts`, and `generation_records` into `workspace_assets` where they represent files/materialized outputs.
- Keep Prism primary documents out of Documents/Assets except for exports.

### 8. Provenance

Canonical tables:

- `provenance_links`
- `source_anchors`

SSOT rules:

- Provenance is a typed graph: source entity -> target entity.
- Supported source kinds: `source`, `source_text_unit`, `workspace_asset`, `sandbox_artifact`, `execution_node`, `user_decision`.
- Supported target kinds: `prism_file`, `prism_section`, `review_item`, `room_decision`, `room_memory`, `workspace_asset`.
- Domain-specific usage events are projections from provenance links.

Legacy cleanup:

- Migrate `prism_source_links` and `reference_usage_events` into `provenance_links`.
- Remove source linkage from review payloads once provenance links exist.

### 9. Workspace Rooms

Canonical tables:

- `decisions`
- `memory_facts`
- `workspace_tasks`

SSOT rules:

- Decisions are durable user-approved choices.
- Memory facts are durable preferences/context.
- Workspace tasks are user-visible work items.
- Candidate decisions/memory/tasks are review items before materialization.

Legacy cleanup:

- Keep these tables if their fields remain clean.
- Move repository/service ownership to DataService.

## DataService Boundary Rules

Allowed:

- `dataservice/models` imports SQLAlchemy and defines business tables.
- `dataservice/repositories` imports models and executes SQLAlchemy statements.
- `dataservice/services` opens transactions through `DataServiceUnitOfWork` and calls repositories.
- `dataservice/projections` calls repositories and returns Pydantic/read-model dictionaries.

Forbidden outside DataService:

- `from src.database.models...`
- `from src.database import Workspace, Artifact, Capability, ...`
- Direct `session.execute(select(...))` for business data.
- Direct commits from repositories.
- Product state stored only in queue/task infrastructure.

Temporary exceptions:

- Auth/session dependency may import `User` until identity is migrated.
- Database bootstrap may import `Base`, engine, sessions, and all model packages for Alembic metadata registration.
- Legacy files listed in `LEGACY_ALLOWED_FILES` are allowed only until their domain slice is migrated.

## Transaction Model

Create `DataServiceUnitOfWork`:

```python
class DataServiceUnitOfWork:
    def __init__(self, session: AsyncSession) -> None: ...
    async def __aenter__(self) -> "DataServiceUnitOfWork": ...
    async def __aexit__(self, exc_type, exc, tb) -> None: ...
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...
```

Rules:

- Repositories never call `commit()`.
- A domain service owns exactly one user-visible use case transaction.
- Post-commit side effects are event publishing, audit, cache invalidation, and workspace refresh.
- Review apply writes target entity, review transition, action log, and provenance links in one transaction.

## Migration Strategy

### Phase 0: Final SSOT Design Gate

Deliverables:

- Data model ERD in docs.
- Table-by-table migration map.
- Redundancy deletion list.
- Deployment cutover plan.

Exit gate:

- No unresolved SSOT ownership question for workspace, execution, review, Prism, source/library, assets, sandbox, provenance, and rooms.

### Phase 1: DataService Foundation

Create:

- `backend/src/dataservice`
- `DataServiceUnitOfWork`
- common contracts
- architecture guard with shrinking legacy allowlist
- Alembic metadata import path for `src.dataservice.models`

No user-facing behavior changes.

### Phase 2: Canonical Tables

Create migrations:

- `059_dataservice_foundation.py`
- `060_review_items_v2.py`
- `061_prism_documents.py`
- `062_sources_assets_sandbox_provenance.py`
- `063_execution_cleanup_projection.py`

Rules:

- One migration per domain group.
- Do not edit a committed migration.
- Each migration includes upgrade and downgrade where feasible.

### Phase 3: Data Copy And Cutover

For each domain:

1. Add canonical tables.
2. Copy legacy data into canonical tables.
3. Switch repositories/services to canonical tables.
4. Update consumers.
5. Run selected tests.
6. Remove old runtime code path.
7. Archive or drop old tables based on deployment decision.

No long-lived dual-write. No fallback reader after the slice is cut over.

### Phase 4: Projection Rebuild

Move read models into DataService projections:

- workspace context
- Prism surface
- Compute launch
- run history
- activity feed
- capability catalog

Projection builders return Pydantic contracts or plain dictionaries, never ORM rows.

### Phase 5: Legacy Deletion

Delete or archive old table families once consumers are cut over:

- `library_items`
- `prism_review_items`
- `prism_source_links`
- `workspace_run`
- `run_history` if replaced by projection
- `generation_records` if migrated to assets/executions
- generic `artifacts` if migrated to workspace assets
- `latex_projects` workspace binding if Prism universal document owns the surface

## Implementation Tasks

### Task 1: Write Data Model ERD And Migration Map

**Files:**

- Modify: `/Users/ze/wenjin/docs/superpowers/plans/2026-05-20-dataservice-convergence.md`
- Create: `/Users/ze/wenjin/docs/superpowers/specs/2026-05-20-dataservice-ssot-model.md`

Steps:

- [ ] List every current business table and mark it as `keep`, `rename`, `merge`, `projection`, `infrastructure`, or `delete`.
- [ ] Draw the canonical ERD using Mermaid.
- [ ] Define every canonical table with primary key, required foreign keys, typed state fields, and JSON extension fields.
- [ ] Define legacy-to-canonical copy rules.
- [ ] Review the open decisions in this plan before code begins.

### Task 2: Add Foundation Package, UnitOfWork, And Guard

**Files:**

- Create: `/Users/ze/wenjin/backend/src/dataservice/__init__.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/unit_of_work.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/contracts/common.py`
- Create: `/Users/ze/wenjin/backend/tests/architecture/test_dataservice_boundaries.py`

Steps:

- [ ] Add package skeleton.
- [ ] Add `DataServiceUnitOfWork`.
- [ ] Add architecture guard for model imports and direct SQLAlchemy business queries.
- [ ] Generate explicit `LEGACY_ALLOWED_FILES` from current violations.
- [ ] Run `cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py -q`.
- [ ] Commit `feat: add dataservice foundation guard`.

### Task 3: Add Canonical Review Workflow

**Files:**

- Create: `/Users/ze/wenjin/backend/src/dataservice/models/review.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/contracts/review.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/repositories/review_items.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/services/review_workflow.py`
- Create: `/Users/ze/wenjin/backend/alembic/versions/060_review_items_v2.py`
- Create: `/Users/ze/wenjin/backend/tests/dataservice/test_review_workflow_service.py`

Steps:

- [ ] Create `review_items` and `review_action_logs`.
- [ ] Migrate `prism_review_items` rows into `review_items`.
- [ ] Add state transition tests for pending/deferred/applied/rejected/reverted.
- [ ] Ensure apply action requires target handler and one transaction.
- [ ] Remove Prism-specific review status reads from new code paths.
- [ ] Commit `feat: add review item ssot`.

### Task 4: Add Universal Prism Document Model

**Files:**

- Create: `/Users/ze/wenjin/backend/src/dataservice/models/prism_document.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/contracts/prism_document.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/repositories/prism_documents.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/services/prism_documents.py`
- Create: `/Users/ze/wenjin/backend/alembic/versions/061_prism_documents.py`
- Modify: `/Users/ze/wenjin/backend/src/services/workspace_prism_service.py`
- Test: `/Users/ze/wenjin/backend/tests/dataservice/test_prism_document_repository.py`

Steps:

- [ ] Create `prism_projects`, `prism_documents`, `prism_files`, `prism_file_versions`, `prism_renders`, `prism_protected_scopes`.
- [ ] Copy workspace-owned `latex_projects` into `prism_projects`.
- [ ] Store LaTeX-specific metadata as adapter metadata.
- [ ] Route workspace Prism projection through DataService.
- [ ] Stop using `LatexProject.workspace_id` as the canonical workspace binding.
- [ ] Commit `feat: add prism document ssot`.

### Task 5: Add Source Library And Workspace Asset SSOT

**Files:**

- Create: `/Users/ze/wenjin/backend/src/dataservice/models/source.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/models/asset.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/repositories/sources.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/repositories/assets.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/services/source_library.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/services/asset_store.py`
- Create: `/Users/ze/wenjin/backend/alembic/versions/062_sources_assets.py`

Steps:

- [ ] Create `sources`, `source_external_ids`, `source_assets`, `source_outline_nodes`, `source_text_units`, `source_bibtex_snapshots`.
- [ ] Create `workspace_assets`.
- [ ] Migrate `workspace_references*` into source tables or rename model/table only if preserving physical table is lower risk.
- [ ] Migrate `library_items` into sources/assets.
- [ ] Migrate file-like `documents_v2`, `artifacts`, and `generation_records` into `workspace_assets`.
- [ ] Commit `feat: add source and asset ssot`.

### Task 6: Add Sandbox Artifact And Provenance SSOT

**Files:**

- Create: `/Users/ze/wenjin/backend/src/dataservice/models/sandbox_artifact.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/models/provenance.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/repositories/sandbox_artifacts.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/repositories/provenance.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/services/sandbox_artifacts.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/services/provenance.py`
- Create: `/Users/ze/wenjin/backend/alembic/versions/063_sandbox_provenance.py`

Steps:

- [ ] Create `sandbox_job_records`, `sandbox_artifacts`, `provenance_links`, `source_anchors`.
- [ ] Migrate `prism_source_links` and `reference_usage_events`.
- [ ] Ensure sandbox artifact creation also creates pending review item.
- [ ] Ensure provenance links can point to Prism sections, source text units, assets, and sandbox artifacts.
- [ ] Commit `feat: add sandbox and provenance ssot`.

### Task 7: Converge Execution, Compute, And Run History

**Files:**

- Create: `/Users/ze/wenjin/backend/src/dataservice/models/execution.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/repositories/executions.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/services/execution_log.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/projections/compute_launch.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/projections/run_history.py`
- Modify: `/Users/ze/wenjin/backend/src/compute/projection_service.py`
- Modify: `/Users/ze/wenjin/backend/src/agents/lead_agent/v2/runtime.py`

Steps:

- [ ] Make `executions` and `execution_nodes` the product execution SSOT.
- [ ] Move `subagent_task_records` semantics into `execution_nodes` / `execution_events`.
- [ ] Treat `task_records` as infrastructure or remove product reads from it.
- [ ] Replace `workspace_run` and `run_history` reads with projections.
- [ ] Commit `refactor: converge execution data ssot`.

### Task 8: Move Room Repositories Into DataService

**Files:**

- Create: `/Users/ze/wenjin/backend/src/dataservice/models/rooms.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/repositories/rooms.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/services/workspace_rooms.py`
- Modify: `/Users/ze/wenjin/backend/src/services/execution_commit_service.py`

Steps:

- [ ] Keep `decisions`, `memory_facts`, and `workspace_tasks` as canonical room tables if field audit passes.
- [ ] Move all room query/write code into DataService repositories.
- [ ] Make candidate room writes go through `review_items`.
- [ ] Replace `ExecutionCommitService` room writes with `ReviewWorkflowService.apply_many()`.
- [ ] Commit `refactor: move workspace rooms into dataservice`.

### Task 9: Migrate Consumers And Delete Legacy Runtime Paths

**Files:**

- Modify routers, agents, Compute, Prism, commit services, and capability catalog consumers.
- Modify `/Users/ze/wenjin/backend/tests/architecture/test_dataservice_boundaries.py`.

Steps:

- [ ] Replace direct model imports with DataService services/projections.
- [ ] Remove migrated files from `LEGACY_ALLOWED_FILES`.
- [ ] Delete old services once no consumer remains.
- [ ] Run `cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/dataservice tests/architecture tests/compute tests/services tests/gateway/routers -q`.
- [ ] Commit `refactor: cut consumers over to dataservice`.

### Task 10: Final Drop/Archive Gate

Steps:

- [ ] Confirm deployment old-table policy.
- [ ] Drop or archive migrated legacy tables.
- [ ] Run `cd /Users/ze/wenjin/backend && alembic upgrade head`.
- [ ] Run backend selected and e2e tests.
- [ ] Update DataService docs as active architecture.
- [ ] Commit `refactor: remove legacy data model paths`.

## Verification Matrix

| Gate | Command |
| --- | --- |
| Architecture | `cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py -q` |
| DataService unit | `cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/dataservice -q` |
| Migrations | `cd /Users/ze/wenjin/backend && alembic upgrade head` |
| Compute projection | `cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/compute/test_projection_service.py -q` |
| Capability catalog | `cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/services/test_cross_ref_validator.py tests/seed/test_capability_seeds_load.py -q` |

## Open Engineering Risks

1. Existing direct DB imports are broad. The first guard must snapshot current violations and force the list to shrink.
2. Renaming/moving all tables in one commit is too risky. Use canonical schema first, then migrate domain slices.
3. Data copy migrations need idempotent checks and row counts; each migration should fail loudly on unmapped legacy rows.
4. Prism/LaTeX migration needs special care because file storage and DB metadata are coupled.
5. Source/library migration needs dedupe by DOI, citation key, normalized title, and uploaded asset identity.
