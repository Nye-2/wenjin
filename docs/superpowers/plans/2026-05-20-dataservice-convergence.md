# DataService SSOT Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use engineering-context:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign Wenjin's data layer into a stable DataService SSOT so database models, table ownership, repositories, transactions, review state, Prism documents, sandbox artifacts, provenance, and projections have one canonical home.

**Architecture:** This is not a wrapper over the existing services. It is a one-time model convergence plus a service-boundary split: DataService is a standalone internal service in this monorepo, deployed as its own Docker container in Compose. `backend/src/dataservice` owns business data models, repositories, unit-of-work, domain services, and projections; `backend/src/dataservice_app` exposes the internal FastAPI API; gateway/worker/agents call it through `backend/src/dataservice_client`. Redundant legacy tables are migrated into canonical tables, consumers cut over in domain slices, and old tables are deleted or archived without runtime fallback, dual-write, or alias readers.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy async, Alembic, Pydantic v2, pytest, PostgreSQL JSONB, SQLite-compatible tests only where production models cannot be used directly.

---

## Source Documents

- `/Users/ze/wenjin/docs/superpowers/specs/2026-05-20-super-agent-capability-system-design.md`
- `/Users/ze/wenjin/docs/superpowers/specs/2026-05-20-wenjin-native-prism-integration-overview.md`
- `/Users/ze/wenjin/docs/superpowers/specs/2026-05-21-dataservice-full-migration-overview.md`
- `/Users/ze/wenjin/docs/superpowers/specs/2026-05-20-dataservice-internal-architecture.md`
- `/Users/ze/wenjin/AGENTS.md`

## Planning Premise

The current database has accumulated migration-era overlap. DataService should use this window to redraw the canonical model instead of preserving old table boundaries. After this convergence, DataService should be treated as a stable platform layer; future feature work should extend typed models and contracts, not create parallel tables for the same concept.

## Current Redundancy Audit

| Area | Existing Overlap | SSOT Decision |
| --- | --- | --- |
| Workspace/thread binding | `workspaces.thread_id` and `threads.workspace_id` both express workspace/thread relationship. | Keep `threads.workspace_id` for membership. Use `workspaces.active_thread_id` only for selected active thread. Do not infer membership from active thread. |
| Execution lifecycle | `executions`, `execution_nodes`, `task_records`, `subagent_task_records`, `workspace_run`, `run_history`, `compute_sessions` all express run/task state. | `executions` + `execution_nodes` are execution SSOT. Queue/task rows are infrastructure only. Run history and compute state become projections from execution/review data. |
| User-facing tasks | `task_records` and `workspace_tasks` both use "task" naming. | `workspace_tasks` are user-visible work items. `task_records` are worker queue/infrastructure and must not be product state. |
| Library/reference | `library_items` and `workspace_references` both represent research materials. | `sources` is source/library SSOT. Generic uploaded/generated files go to `workspace_assets`; legacy `library_items` and `workspace_references` migrate into source rows where possible. |
| Documents/artifacts/assets | `documents_v2`, `artifacts`, `generation_records`, reference assets, and inline document metadata all store output/file concepts. | `workspace_assets` is generic file/material SSOT. Prism primary documents and references have specialized tables that link to assets. Sandbox artifacts are execution-produced assets plus reproducibility metadata. |
| Sandbox runtime | `sandboxes`, execution payload artifact ids, and ad hoc sandbox outputs mix environment state with produced files. | `sandbox_environments` owns workspace sandbox state; `sandbox_job_records` owns execution reproducibility; `sandbox_artifacts` links job outputs to workspace assets and review. |
| Prism document | `latex_projects` contains user project, workspace binding, file ordering, LLM config, adapter config, and surface role. | `prism_projects` / `prism_documents` / `prism_files` own workspace primary documents. LaTeX becomes an adapter, not the root model. |
| Review state | `prism_review_items`, `TaskReport.outputs`, frontend ResultCard state, and commit payloads all express reviewable outputs. | `review_batches` + `review_items` are the only review/apply state source. Prism changes, room writes, and sandbox artifacts are target kinds. |
| Provenance | `prism_source_links`, `reference_usage_events`, review payload source fields, and artifact metadata all link claims to sources. | `provenance_links` is the canonical source-target graph. Domain-specific projections read from it. |
| Capability schema | `capabilities.runtime`, `brief_schema`, `graph_template`, `dashboard_meta`, and skill `config` carry mixed v1/v2 semantics. | `capability_definitions` and `capability_skills` are versioned catalog models with strict v2 schema payloads and typed searchable columns. |
| Workspace settings | `workspaces.config` and `workspace_settings.metadata_json` both store workspace config. | `workspace_settings` owns user-editable settings. `workspaces` keeps identity fields and immutable/top-level metadata only. |

## Canonical Model Principles

1. **One concept, one table family.** A model may have projections, but it must have exactly one write source.
2. **DataService is a service boundary.** Canonical business writes live in the DataService service process. Gateway, worker, agents, and Compute call it through `dataservice_client`.
3. **Repositories never commit.** All transaction ownership lives in `DataServiceUnitOfWork` or a domain service that owns a complete use case.
4. **No product state in queue tables.** Worker queue/task infrastructure may reference product entities but cannot become the user-visible state source.
5. **No untyped payload as primary schema.** JSONB is allowed for extension payloads, but core identity, state, ownership, timestamps, and target links must be typed columns.
6. **Workspace-scoped by default.** Workspace data tables require `workspace_id`; user-owned entry points validate both `user_id` and `workspace_id`.
7. **Review before materialization.** Agent-produced document changes, room writes, and sandbox artifacts enter `review_batches` / `review_items` before applying to user-facing rooms or Prism primary documents.
8. **Append-only where history matters.** Review actions, provenance links, file versions, and execution nodes should preserve history instead of overwriting meaning.
9. **Cutover, not compatibility.** During a domain migration, old data is copied into canonical tables and consumers are switched to the canonical repository in the same release slice.

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
5. **No new direct DB imports**: new code outside the DataService service process must not import `src.database.models`, `src.dataservice.domains.*.models`, or `src.dataservice.domains.*.repository`.
6. **No direct business queries outside DataService**: routers, agents, Compute, Prism, and execution runtime must not call `session.execute(select(...))` for business data after their domain cutover; they must call `dataservice_client`.
7. **Repository discipline**: repositories execute queries and writes but never commit, publish events, or call LLM/tools.
8. **Unit-of-work discipline**: domain services own use-case transactions through `DataServiceUnitOfWork`.
9. **Review state discipline**: all agent-produced materialization targets go through `review_batches` / `review_items`; direct writes are allowed only for user edits and infrastructure bookkeeping.
10. **Projection discipline**: UI/agent/Compute read models come from DataService domain projections; projections return Pydantic contracts or plain dictionaries, never ORM rows.
11. **Migration proof**: each data-copy migration must include row-count checks and fail loudly on unmapped legacy rows.
12. **Service boundary proof**: gateway/worker/agents use `dataservice_client`; only the DataService app imports domain repositories/models.
13. **Legacy deletion proof**: a legacy table or runtime path can be archived/deleted only after its consumer imports are removed and architecture tests pass.
14. **Doc sync**: every domain cutover updates this plan and the SSOT model spec in the same commit.
15. **Test floor**: each domain commit runs architecture tests, domain unit tests, migration upgrade, and affected service/projection tests.

## Target Package Structure

```text
backend/src/dataservice/
  common/
    actor.py
    errors.py
    idempotency.py
    unit_of_work.py
  domains/
    workspace/{models.py,contracts.py,repository.py,service.py,projection.py,policies.py}
    conversation/{models.py,contracts.py,repository.py,service.py,projection.py,block_protocol.py}
    catalog/{models.py,contracts.py,repository.py,service.py,seed_loader.py}
    execution/{models.py,contracts.py,repository.py,service.py,projection.py}
    review/{models.py,contracts.py,repository.py,service.py,registry.py}
    asset/{models.py,contracts.py,repository.py,service.py,review_handler.py}
    prism/{models.py,contracts.py,repository.py,service.py,projection.py,review_handler.py}
    source/{models.py,contracts.py,repository.py,service.py,projection.py,review_handler.py}
    sandbox/{models.py,contracts.py,repository.py,service.py,projection.py,review_handler.py}
    provenance/{models.py,contracts.py,repository.py,service.py}
    rooms/{models.py,contracts.py,repository.py,service.py,projection.py,review_handler.py}
    operations/{models.py,repository.py,outbox.py}
backend/src/dataservice_app/
  __init__.py
  app.py
  health.py
  deps.py
  auth.py
  routers/
    __init__.py
backend/src/dataservice_client/
  __init__.py
  client.py
  errors.py
  contracts/
```

## Canonical Table Families

### 1. Workspace Core

Canonical tables:

- `workspaces`
- `workspace_memberships`
- `workspace_settings`
- `threads`

SSOT rules:

- `workspaces` stores identity/lifecycle: creator, name, type, discipline, description, active thread pointer.
- `workspace_memberships` stores access and collaboration membership.
- `workspace_settings` stores mutable user/workspace settings.
- `threads.workspace_id` stores conversation membership.
- `workspaces.active_thread_id` points to the currently selected thread but does not define membership.

Legacy cleanup:

- Rename `workspaces.thread_id` to `active_thread_id`.
- Seed owner memberships from existing `workspaces.user_id`.
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

- `review_batches`
- `review_items`
- `review_action_logs`

Required typed columns:

- `review_batches.workspace_id`
- `review_batches.execution_id`
- `review_batches.status`
- `review_batches.title`
- `review_batches.summary`
- `review_batches.source_type`
- `review_batches.source_id`
- `review_batches.review_kind`
- `review_batches.schema_version`
- `review_batches.item_count`
- `review_batches.accepted_count`
- `review_batches.rejected_count`
- `review_batches.applied_count`
- `review_batches.failed_count`
- `review_items.batch_id`
- `review_items.workspace_id`
- `review_items.source_item_id`
- `review_items.item_kind`
- `review_items.target_domain`
- `review_items.target_kind`
- `review_items.target_ref_json`
- `review_items.status`
- `review_items.title`
- `review_items.summary`
- `review_items.sort_order`
- `review_items.applied_at`

JSONB extension columns:

- `review_batches.payload_json`
- `review_items.payload_json`
- `review_items.preview_json`
- `review_items.result_json`
- `review_items.provenance_json`

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

- `review_batches` is the aggregate root for a user-reviewable result set.
- `review_items.status` stores item-level acceptance/apply state inside a batch.
- Applying a batch writes selected targets, item transitions, batch transition, action logs, and provenance links in one transaction.
- Prism-specific review rows and transient ResultCard outputs migrate into generic `review_batches` / `review_items`.

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

### 7. Workspace Assets And Sandbox Runtime

Canonical tables:

- `workspace_assets`
- `sandbox_environments`
- `sandbox_job_records`
- `sandbox_artifacts`

SSOT rules:

- `workspace_assets` stores metadata for files/materials created or uploaded in a workspace.
- Asset binary/content storage stays outside DB unless content is small inline text.
- `sandbox_environments` stores workspace sandbox provider, external environment id, state, workspace path, and effective policy.
- `sandbox_job_records` stores runtime image, language, command/script hash, input hashes, network policy, resource limits, and result status.
- `sandbox_artifacts` stores reproducibility metadata and links to a `workspace_asset`.

Legacy cleanup:

- Migrate `documents_v2`, generic `artifacts`, and `generation_records` into `workspace_assets` where they represent files/materialized outputs.
- Migrate `sandboxes` into `sandbox_environments`; do not merge environment state into artifact rows.
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

- `dataservice/domains/<domain>/models.py` imports SQLAlchemy and defines tables for one aggregate boundary.
- `dataservice/domains/<domain>/repository.py` imports domain models and executes SQLAlchemy statements for that aggregate.
- `dataservice/domains/<domain>/service.py` opens transactions through `DataServiceUnitOfWork` and calls repositories.
- `dataservice/domains/<domain>/projection.py` calls repositories and returns Pydantic/read-model dictionaries.
- `dataservice/domains/operations` owns idempotency, outbox, and migration report records.

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
- `backend/src/dataservice_app`
- `backend/src/dataservice_client`
- `DataServiceUnitOfWork`
- common actor, error, pagination, idempotency, and contract primitives
- architecture guard with shrinking legacy allowlist
- DataService Docker target and Compose service
- Alembic metadata import path for `src.dataservice.domains.*.models`

No user-facing behavior changes.

### Phase 2: Canonical Tables

Create migrations:

- `059_dataservice_operations.py`
- `060_dataservice_workspace_core.py`
- `061_dataservice_conversation_blocks.py`
- `062_dataservice_capability_catalog.py`
- `063_dataservice_execution_graph.py`
- `064_dataservice_review_queue.py`
- `065_dataservice_workspace_assets.py`
- `066_dataservice_prism_documents.py`
- `067_dataservice_sources_provenance.py`
- `068_dataservice_sandbox_runtime.py`
- `069_dataservice_rooms_hooks.py`
- `070_dataservice_projection_cleanup.py`

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
- live workflow
- Prism surface
- Compute launch
- run history
- library
- sandbox
- activity feed
- capability catalog

Projection builders return Pydantic contracts or plain dictionaries, never ORM rows.

### Phase 5: Legacy Deletion

Delete or archive old table families once consumers are cut over:

- `workspace_references*` after source rename/copy is verified
- `library_items`
- `prism_review_items`
- `prism_source_links`
- `reference_usage_events`
- `workspace_run`
- `subagent_task_records`
- `run_history` if replaced by projection
- `compute_sessions` if replaced by projection/cache rebuild
- `generation_records` if migrated to assets/executions
- `documents_v2` if migrated to workspace assets
- generic `artifacts` if migrated to workspace assets
- `sandboxes` if migrated to `sandbox_environments`
- `latex_projects` workspace binding if Prism universal document owns the surface

## Implementation Tasks

### Task 1: Write Data Model ERD And Migration Map

**Files:**

- Modify: `/Users/ze/wenjin/docs/superpowers/plans/2026-05-20-dataservice-convergence.md`
- Create: `/Users/ze/wenjin/docs/superpowers/specs/2026-05-20-dataservice-ssot-model.md`

Steps:

- [x] List every current business table and mark it as `keep`, `rename`, `merge`, `projection`, `infrastructure`, or `delete`.
- [x] Draw the canonical ERD using Mermaid.
- [x] Define every canonical table with primary key, required foreign keys, typed state fields, and JSON extension fields.
- [x] Define legacy-to-canonical copy rules.
- [x] Review the open decisions in this plan before code begins.

### Task 2: Add Standalone DataService Foundation

**Files:**

- Create: `/Users/ze/wenjin/backend/src/dataservice/__init__.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/app_boundary.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/common/actor.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/common/errors.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/common/idempotency.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/common/pagination.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/common/unit_of_work.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/operations/models.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/operations/repository.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/operations/outbox.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice_app/__init__.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice_app/app.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice_app/auth.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice_app/deps.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice_app/routers/__init__.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice_app/routers/health.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice_client/__init__.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice_client/client.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice_client/errors.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice_client/contracts/__init__.py`
- Create: `/Users/ze/wenjin/backend/alembic/versions/059_dataservice_operations.py`
- Modify: `/Users/ze/wenjin/backend/Dockerfile`
- Modify: `/Users/ze/wenjin/docker-compose.yml`
- Modify: `/Users/ze/wenjin/docker-compose.local-build.yml`
- Create: `/Users/ze/wenjin/backend/tests/architecture/test_dataservice_boundaries.py`

Steps:

- [x] Add package skeleton with `common`, `domains`, `dataservice_app`, and `dataservice_client`.
- [x] Add `ActorContext`, `DataServiceUnitOfWork`, idempotency record helpers, and typed errors.
- [x] Add operations tables for `dataservice_idempotency_keys`, `dataservice_outbox_events`, and `dataservice_migration_reports`.
- [x] Add DataService FastAPI app with `/livez` and `/readyz`.
- [x] Add typed `dataservice_client` health/readiness methods.
- [x] Add Docker target and Compose `dataservice` service with internal `DATASERVICE_URL`.
- [x] Add architecture guard that blocks non-DataService runtime imports of DataService models/repositories.
- [x] Generate explicit `LEGACY_ALLOWED_FILES` when the first legacy database model is migrated into a DataService domain.
- [x] Run `cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py -q`.
- [x] Commit `feat: add dataservice service foundation`.

### Task 3: Move Workspace Aggregate To DataService

**Files:**

- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/workspace/models.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/workspace/contracts.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/workspace/repository.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/workspace/service.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/workspace/projection.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/workspace/policies.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice_app/routers/workspace.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice_client/contracts/workspace.py`
- Create: `/Users/ze/wenjin/backend/alembic/versions/060_dataservice_workspace_core.py`
- Modify: `/Users/ze/wenjin/backend/src/services/thread_service.py`
- Modify: `/Users/ze/wenjin/backend/src/services/workspace_summary_service.py`

Steps:

- [x] Add DataService workspace domain with contracts, repository, service, projection, and policy layer.
- [x] Add internal workspace API routes and client workspace contracts.
- [x] Rename DataService contract field `type` to `workspace_type`.
- [x] Expose `workspaces.thread_id` as `active_thread_id` in the DataService contract and validate same-workspace binding.
- [x] Expose `workspaces.user_id` as `created_by_user_id` and seed `workspace_memberships` owner rows.
- [x] Move settings payload into `workspace_settings.settings_json` while preserving `workspaces.config` as the source column until physical cleanup.
- [x] Cut workspace CRUD and access checks through the DataService public workspace boundary.
- [x] Add architecture guard coverage so runtime code cannot import `src.dataservice.domains.*`.
- [ ] Cut runtime consumers from the in-process public boundary to `dataservice_client` once the DataService service is required in all dev/test paths.
- [ ] Physically rename or replace legacy ORM columns (`user_id`, `type`, `thread_id`, `config`) after all consumers use DataService projections.
- [x] Enforce at least one active owner membership per workspace.
- [x] Run workspace/thread/settings tests plus architecture guard.
- [x] Commit `feat: add dataservice workspace core`.

### Task 4: Move Conversation And Block Protocol To DataService

**Files:**

- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/conversation/models.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/conversation/contracts.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/conversation/repository.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/conversation/service.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/conversation/projection.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/conversation/block_protocol.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice_app/routers/conversation.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice_client/contracts/conversation.py`
- Create: `/Users/ze/wenjin/backend/alembic/versions/061_dataservice_conversation_blocks.py`
- Modify: `/Users/ze/wenjin/backend/src/services/thread_service.py`

Steps:

- [x] Add `thread_messages`, `message_blocks`, `tool_invocation_records`, and `tool_result_records`.
- [x] Preserve the canonical 7 block types and arrival-order append semantics.
- [x] Keep `threads.messages` JSON only as bridge data until consumers cut over.
- [x] Migrate existing thread JSON blocks into message/block rows.
- [x] Add DataService conversation internal routes and typed client contracts.
- [x] Route `ThreadService.add_message` / bridge rebuild paths through the DataService conversation boundary.
- [x] Cut thread detail/state/history readers from `threads.messages` to DataService message projections.
- [x] Cut Chat Agent runtime context, run wait views, workspace activity, compaction, rollback, and attachment status updates to DataService message projections.
- [x] Remove `threads.messages` bridge writes after message append, attachment metadata, compaction, and rollback consumers no longer require JSON response compatibility.
- [x] Run thread/block protocol tests plus architecture guard.
- [x] Commit `feat: add dataservice conversation blocks`.
- [x] Commit `feat: read threads from dataservice conversation projection`.
- [x] Commit `feat: use dataservice conversation projections at runtime`.

### Task 5: Move Capability Catalog Aggregate To DataService

**Files:**

- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/catalog/models.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/catalog/contracts.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/catalog/repository.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/catalog/service.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/catalog/seed_loader.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice_app/routers/catalog.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice_client/contracts/catalog.py`
- Create: `/Users/ze/wenjin/backend/alembic/versions/062_dataservice_capability_catalog.py`
- Modify capability seed loader and admin capability/skill services.

Steps:

- [x] Create `capability_seed_revisions`.
- [x] Reshape `capabilities` as `capability_definitions` with `schema_version = capability.v2`.
- [x] Reshape `capability_skills` with `schema_version = capability_skill.v2`, `worker_type`, and `skill_json`.
- [x] Move catalog YAML seed loading into the DataService catalog domain and make it idempotent by checksum.
- [x] Cut runtime catalog consumers, admin capability/skill services, and cross-reference validation to `CatalogDataService`.
- [x] Run seed load tests, admin capability/skill service tests, catalog runtime tests, and architecture guard.
- [x] Commit `feat: move capability catalog aggregate into dataservice`.

### Task 6: Move Execution Aggregate To DataService

**Files:**

- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/execution/models.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/execution/contracts.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/execution/repository.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/execution/service.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/execution/projection.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/execution_api.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice_app/routers/execution.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice_client/contracts/execution.py`
- Create: `/Users/ze/wenjin/backend/alembic/versions/063_dataservice_execution_graph.py`
- Modify: `/Users/ze/wenjin/backend/src/agents/lead_agent/v2/runtime.py`
- Modify: `/Users/ze/wenjin/backend/src/execution/engine.py`

Steps:

- [x] Keep `executions` as product run SSOT and expose DataService contract fields `feature_id` -> `capability_id`, `params` -> `task_brief_json`, and `graph_structure` -> `graph_json`.
- [x] Create `execution_events` with ordered per-execution `sequence_index`.
- [x] Add DataService execution routes/client contracts and event append/list projection.
- [x] Record status events from `ExecutionEngineV2` and node lifecycle events from the Celery execution callback.
- [x] Cut `ExecutionService` create/read/list/update/cancel/node-state writes through `ExecutionDataService` while preserving caller-facing compatibility attributes.
- [x] Move `subagent_task_records` semantics into `execution_nodes` and `execution_events`.
- [x] Remove product-state reads from `task_records`.
- [x] Replace `workspace_run`, `run_history`, and `compute_sessions` product reads with DataService projections or rebuildable cache reads.
- [x] Run lead runtime, execution service, compute projection, dashboard/activity, run-history, and architecture guard tests.
- [x] Commit `feat: converge execution aggregate ssot`.

### Task 7: Add Review Batch Aggregate

**Files:**

- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/review/models.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/review/contracts.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/review/repository.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/review/service.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/review/registry.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice_app/routers/review.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice_client/contracts/review.py`
- Create: `/Users/ze/wenjin/backend/alembic/versions/064_dataservice_review_queue.py`
- Create: `/Users/ze/wenjin/backend/tests/dataservice/test_review_batch_service.py`

Steps:

- [x] Create `review_batches`, `review_items`, and `review_action_logs`.
- [x] Migrate `prism_review_items` and transient result-card outputs into batch/item rows.
- [x] Add state transition tests for batch statuses `pending`, `partially_applied`, `applied`, `rejected`, and `failed`.
- [x] Add state transition tests for item statuses `pending`, `accepted`, `rejected`, `applied`, `reverted`, and `failed`.
- [x] Ensure apply action uses target-domain review handlers and one transaction for target write, item transition, batch transition, action log, and provenance links.
- [x] Remove legacy Prism review status reads from new code paths.
- [x] Commit `feat: add review batch aggregate`.

Implementation status:

- 2026-05-21: Review aggregate foundation is implemented in DataService with domain models, migration `064_dataservice_review_queue.py`, public in-process API, internal HTTP routes, typed client contracts, handler registry, action logs, and state-machine tests.
- Verification: `cd backend && .venv/bin/python -m pytest tests/ -q` passes with 1895 tests.
- Prism/result-card runtime cutover remains in the later Prism/rooms materialization slices because target-domain review handlers and provenance links depend on those domains.

### Task 8: Add Workspace Asset Aggregate

**Files:**

- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/asset/models.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/asset/contracts.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/asset/repository.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/asset/service.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/asset/review_handler.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice_app/routers/asset.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice_client/contracts/asset.py`
- Create: `/Users/ze/wenjin/backend/alembic/versions/065_dataservice_workspace_assets.py`

Steps:

- [x] Create `workspace_assets`.
- [x] Migrate file-like `documents_v2` rows into `workspace_assets`.
- [x] Migrate binary/large `artifacts` and file-like `generation_records` into `workspace_assets`.
- [x] Enforce large content storage through managed storage, not business JSON blobs.
- [x] Run asset repository and migration validation tests.
- [x] Commit `feat: add workspace asset aggregate`.

Implementation status:

- 2026-05-21: Workspace asset aggregate foundation is implemented in DataService with domain model, migration `065_dataservice_workspace_assets.py`, public in-process API, internal HTTP routes, typed client contracts, and review handler factory.
- Forward writes require `storage_path`; DataService records metadata, storage pointer, hash, size, source linkage, soft-delete state, and derivative parent pointer.
- Migration seeds assets from file-like `documents_v2`, file-backed `artifacts`, and file-like `generation_records` while preserving legacy source ids in metadata instead of copying large payloads into business JSON.
- Verification: targeted asset/review/boundary tests pass with 11 tests, and `cd backend && .venv/bin/python -m pytest tests/ -q` passes with 1899 tests.

### Task 9: Add Prism Project Aggregate

**Files:**

- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/prism/models.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/prism/contracts.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/prism/repository.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/prism/service.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/prism/projection.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/prism/review_handler.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/prism/adapters/latex.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice_app/routers/prism.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice_client/contracts/prism.py`
- Create: `/Users/ze/wenjin/backend/alembic/versions/066_dataservice_prism_documents.py`
- Modify: `/Users/ze/wenjin/backend/src/services/workspace_prism_service.py`
- Test: `/Users/ze/wenjin/backend/tests/dataservice/test_prism_project_service.py`

Steps:

- [x] Create `prism_projects`, `prism_documents`, `prism_files`, `prism_file_versions`, `prism_renders`, `prism_protected_scopes`.
- [x] Copy workspace-owned `latex_projects` into `prism_projects`.
- [x] Store LaTeX-specific metadata under adapter metadata.
- [x] Route workspace Prism projection through DataService.
- [x] Stop using `LatexProject.workspace_id` as the canonical workspace binding.
- [x] Commit `feat: add prism project aggregate`.

Implementation status:

- 2026-05-21: Prism project aggregate foundation is implemented in DataService with canonical project/document/file/version/render/protected-scope models, migration `066_dataservice_prism_documents.py`, public in-process API, internal HTTP routes, typed client contracts, LaTeX adapter metadata helper, and Prism review handler factory.
- Workspace-owned `latex_projects` with `surface_role = 'primary_manuscript'` migrate into `prism_projects`; adapter-specific fields are stored in `adapter_metadata_json` with `adapter_ref_id` pointing at the LaTeX adapter project.
- `WorkspacePrismService` now resolves the canonical Prism surface via `PrismDataService` and only then loads the LaTeX adapter project; `LatexProject.workspace_id` is no longer the lookup SSOT.
- Verification: Prism domain/service tests, workspace Prism service tests, DataService domain tests, and architecture boundary tests pass with 45 targeted tests; `cd backend && .venv/bin/python -m pytest tests/ -q` passes with 1903 tests.

### Task 10: Add Source And Provenance Aggregates

**Files:**

- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/source/models.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/source/contracts.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/source/repository.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/source/service.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/source/projection.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/source/importers.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/source/preprocess.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/source/review_handler.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/provenance/models.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/provenance/contracts.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/provenance/repository.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/provenance/service.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice_app/routers/source.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice_client/contracts/source.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice_client/contracts/provenance.py`
- Create: `/Users/ze/wenjin/backend/alembic/versions/067_dataservice_sources_provenance.py`

Steps:

- [x] Create `sources`, `source_external_ids`, `source_assets`, `source_outline_nodes`, `source_text_units`, `source_bibtex_snapshots`.
- [x] Create `source_anchors` and `provenance_links`.
- [x] Migrate `workspace_references*` into source tables.
- [x] Migrate `library_items` into sources/assets.
- [x] Migrate `reference_usage_events` and `prism_source_links` into provenance.
- [x] Ensure source-backed Prism edits have provenance links.
- [x] Commit `feat: add source and provenance aggregates`.

Implementation status:

- 2026-05-21: Source and Provenance aggregate foundation is implemented in DataService with canonical source/source-asset/source-text/BibTeX snapshot tables, source anchors, provenance links, domain services, internal routes, typed client contracts, review handler factory, and migration `067_dataservice_sources_provenance.py`.
- Migration copies `workspace_references*`, `library_items`, `reference_assets`, `reference_usage_events`, `reference_bibtex_snapshots`, and `prism_source_links` into canonical source/provenance structures where source ids can be resolved.
- Forward runtime creation of source-backed Prism provenance during review apply remains for the cross-domain review/provenance materialization phase.
- Verification: Source/Provenance domain tests, DataService domain tests, and architecture boundary tests pass with 40 targeted tests; `cd backend && .venv/bin/python -m pytest tests/ -q` passes with 1906 tests.

### Task 11: Add Sandbox Environment Aggregate

**Files:**

- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/sandbox/models.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/sandbox/contracts.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/sandbox/repository.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/sandbox/service.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/sandbox/projection.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/sandbox/policy.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/sandbox/review_handler.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice_app/routers/sandbox.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice_client/contracts/sandbox.py`
- Create: `/Users/ze/wenjin/backend/alembic/versions/068_dataservice_sandbox_runtime.py`

Steps:

- [x] Create `sandbox_environments`, `sandbox_job_records`, and `sandbox_artifacts`.
- [x] Migrate `sandboxes` into `sandbox_environments`.
- [x] Enforce Python-only sandbox job contract.
- [x] Ensure sandbox artifact creation also creates a pending review batch/item.
- [x] Ensure sandbox policy blocks host/container/server control while allowing approved data/API/web workflows.
- [x] Commit `feat: add sandbox environment aggregate`.

Implementation status:

- 2026-05-21: Sandbox aggregate foundation is implemented in DataService with canonical environment/job/artifact tables, domain contracts, repository, projection, service, policy validator, review handler factory, internal routes, typed client contracts, public in-process API, and migration `068_dataservice_sandbox_runtime.py`.
- Migration copies legacy `sandboxes` rows into `sandbox_environments` with a policy snapshot that allows Python/data/API/web workflows while blocking Docker socket, privileged mode, host network, host-path mounts, sibling-container access, and server-level control.
- Sandbox job records are Python-only at both Pydantic contract and database check-constraint layers. DataService records reproducibility metadata and artifacts; container execution remains outside DataService.
- `register_artifact` creates a `sandbox_artifacts` row and a pending `review_batches` / `review_items` entry in the same transaction boundary so sandbox outputs do not materialize directly into Prism or rooms.
- Verification: Sandbox domain tests, DataService domain tests, and architecture boundary tests pass with 44 targeted tests; `cd backend && .venv/bin/python -m pytest tests/ -q` passes with 1910 tests.

### Task 12: Move Workspace Rooms Aggregate Into DataService

**Files:**

- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/rooms/models.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/rooms/contracts.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/rooms/repository.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/rooms/service.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/rooms/projection.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice/domains/rooms/review_handler.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice_app/routers/rooms.py`
- Create: `/Users/ze/wenjin/backend/src/dataservice_client/contracts/rooms.py`
- Create: `/Users/ze/wenjin/backend/alembic/versions/069_dataservice_rooms_hooks.py`
- Modify: `/Users/ze/wenjin/backend/src/services/execution_commit_service.py`

Steps:

- [x] Keep `decisions`, `memory_facts`, and `workspace_tasks` as canonical room tables if field audit passes.
- [x] Add `source_review_batch_id` and `source_review_item_id` hooks where materialized room records need traceability.
- [x] Move all room query/write code into DataService room repository/service.
- [x] Make candidate room writes go through `review_batches` / `review_items`.
- [x] Replace `ExecutionCommitService` room writes with `ReviewBatchService.apply_many()`.
- [x] Commit `refactor: move workspace rooms aggregate into dataservice`.

Implementation status:

- 2026-05-21: Rooms aggregate foundation is implemented in DataService while keeping `decisions`, `memory_facts`, and `workspace_tasks` as canonical physical tables.
- Migration `069_dataservice_rooms_hooks.py` adds `source_review_batch_id` and `source_review_item_id` trace hooks to all three room tables and widens `decisions.extracted_by` for execution/review actors.
- `backend/src/dataservice/domains/rooms/` owns room contracts, repository, projections, service, and review handler factory. `dataservice_app` exposes internal rooms routes and `dataservice_client` has typed room methods.
- Workspace room routes for decisions, memory, and workspace tasks now call `RoomsDataService` directly; the former `decisions_service.py`, `memory_service.py`, and `workspace_tasks_service.py` facades have been deleted.
- `ExecutionCommitService` no longer writes memory/decision/task outputs directly. It creates room review candidates, stages them in `review_batches` / `review_items`, and applies accepted items through review handlers via `apply_many()`.
- Verification: Rooms domain tests, DataService domain tests, architecture boundary tests, execution commit tests, and workspace room router tests pass with 83 targeted tests; `cd backend && .venv/bin/python -m pytest tests/ -q` passes with 1914 tests.

### Task 13: Rebuild Cross-Domain Projections And Delete Legacy Runtime Paths

**Files:**

- Modify: `/Users/ze/wenjin/backend/src/dataservice/domains/workspace/projection.py`
- Modify: `/Users/ze/wenjin/backend/src/dataservice/domains/execution/projection.py`
- Modify: `/Users/ze/wenjin/backend/src/dataservice/domains/prism/projection.py`
- Modify: `/Users/ze/wenjin/backend/src/dataservice/domains/source/projection.py`
- Modify: `/Users/ze/wenjin/backend/src/dataservice/domains/sandbox/projection.py`
- Modify: `/Users/ze/wenjin/backend/src/dataservice/domains/rooms/projection.py`
- Create: `/Users/ze/wenjin/backend/alembic/versions/070_dataservice_projection_cleanup.py`
- Modify routers, agents, Compute, Prism, commit services, and capability catalog consumers.
- Modify `/Users/ze/wenjin/backend/tests/architecture/test_dataservice_boundaries.py`.

Steps:

- [x] Replace direct model imports for migrated room, sandbox, source/library, document-room, and settings-room slices with DataService APIs.
- [x] Add architecture guard coverage for migrated room, sandbox, source/library, document-room, settings-room, legacy workspace-run, compute-session, execution-record, and execution-node models.
- [ ] Replace remaining direct model imports for domains not yet migrated.
- [x] Delete old service facade files once gateway routes and smoke tests no longer instantiate them.
- [x] Run `cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/dataservice tests/architecture tests/compute tests/services tests/gateway/routers -q`.
- [x] Commit projection cleanup slices.

Implementation status:

- 2026-05-21: Projection cleanup slices are implemented for migrated room, sandbox, source/library, document-room, settings-room, legacy workspace-run, compute-session state, execution-record read projections, and execution-node lifecycle snapshots. Runtime code no longer imports `Decision`, `MemoryFact`, `WorkspaceTask`, `Sandbox`, `LibraryItem`, `DocumentV2`, `WorkspaceSettings`, `WorkspaceRunRow`, `ComputeSessionRecord`, `ExecutionRecord`, or `ExecutionNodeRecord` legacy models directly outside DataService/database ownership packages.
- Architecture guard now has an explicit empty `LEGACY_ALLOWED_FILES` set for migrated legacy database model imports; no runtime exception is currently permitted.
- `ThreadService` no longer writes `threads.messages` JSON for message append, attachment metadata updates, compaction, or rollback. It updates thread summary fields and writes/rebuilds canonical `thread_messages` / `message_blocks` through `ConversationDataService`; architecture guard coverage blocks runtime `thread.messages` access from returning. Legacy `Thread.messages` ORM mapping has been removed, and migration `074_drop_legacy_thread_messages_column.py` drops the old JSON column.
- Workspace membership now has a database-level invariant. Migration `075_enforce_workspace_owner_membership.py` verifies existing data, replaces the membership lookup index with `(workspace_id, role, status)`, and installs deferred PostgreSQL constraint triggers that prevent any workspace from committing without at least one active owner membership.
- `WorkspacePrismService` now reads decision and memory context through `RoomsDataService`; workspace sandbox exec now calls `SandboxDataService` directly, and the former `services/rooms/sandbox_service.py` facade has been deleted.
- Workspace library room endpoints now call `SourceDataService` directly for list/create/get/delete, and the former `services/rooms/library_service.py` facade has been deleted. `SourceDataService` exposes source soft-delete for room delete flows.
- Workspace documents room endpoints now call `AssetDataService` directly for create/read/update/delete/version operations, and the former `services/rooms/documents_service.py` facade has been deleted. Document room writes create canonical `workspace_assets` rows instead of `documents_v2` rows.
- Workspace settings room endpoints now call `WorkspaceDataService` directly, and the former `services/rooms/settings_service.py` facade has been deleted.
- `ExecutionCommitService` no longer depends on room service facades for library, document, or run-history writes. It writes library outputs through `SourceDataService`, document outputs through `AssetDataService`, run-history through `ExecutionDataService.record_event`, and memory/decision/task outputs through `RoomsDataService.stage_and_apply_candidates`.
- `ExecutionEngineV2` also records run history as canonical `execution.run_history` events instead of depending on `RunHistoryService`; Celery execution entrypoint no longer instantiates the run-history room facade.
- Workspace runs room endpoints now read run-history projections from `ExecutionDataService` directly, and the former `services/rooms/run_history_service.py` facade has been deleted.
- Workspace decisions, memory, tasks, settings, sandbox environment-touch, library, and documents endpoints now call DataService APIs directly. The old `services/rooms/*_service.py` facade files and empty package have been deleted.
- `services/workspace_run_service.py` has been deleted; product run state stays on DataService execution projections. Legacy `WorkspaceRunRow` ORM has been removed, `subagent_task_records.run_id` is now an unconstrained historical id field, and migration `073_drop_legacy_workspace_run_table.py` drops the old `workspace_run` table.
- `compute/session_service.py`, compute routes, and compute projection reads now use Execution DataService compute-session commands/projections; DataService app routes and typed client contracts expose the same compute shell boundary for future split deployment.
- `services/workspace_activity_service.py` now builds artifact activity from `AssetDataService` / `workspace_assets` instead of querying the legacy `artifacts` table.
- `services/execution_service.py` now delegates execution-node create/update/find operations and interrupted-execution reconciliation to `ExecutionDataService`; internal DataService routes and typed client contracts expose node get/find/upsert/patch and reconciliation commands for future split deployment.
- Admin analytics execution DAU/WAU and execution stats now read from `ExecutionDataService`; dashboard feature running-count/latest-status helpers also read through `ExecutionDataService`.
- `ReviewDataService` now exposes filtered review-item listing across in-process, internal HTTP, and typed client boundaries. Workspace activity Prism review cards, workspace execution review summaries, and Lead runtime completion reports now read Prism review items from canonical `review_items` instead of direct `prism_review_items` queries.
- `WorkspacePrismService` now uses canonical `review_items` for Prism file-change review cards, file-change counts, launch-context pending review items, and recent review activity.
- `ReviewDataService` now exposes canonical item get/patch/delete operations across in-process, internal HTTP, and typed client boundaries; `PrismReviewDataService` owns Prism file-change review identity on top of canonical `review_items`.
- `ReviewDataService.apply_many()` now runs all target-domain handlers before a single DataService finish step, so accepted item materialization, item transitions, batch status recomputation, action logs, and handler-owned provenance writes share the same transaction boundary.
- `WorkspaceLatexProjectService` now creates/clears pending Prism file-change review items through `PrismReviewDataService`, and LaTeX preview/apply/discard/revert actions transition canonical `review_items`. `defer` has been removed from the Prism action contract, backend routes, frontend API/store, and review UI.
- Prism source links now use canonical `provenance_links`, and Prism protected sections now use `prism_protected_scopes`; `WorkspacePrismService` no longer reads legacy `prism_source_links` or `prism_protected_sections`.
- Source citation usage now writes through DataService. LaTeX/Prism file-change apply records citation usage against canonical `sources`, materializes `provenance_links`, marks eligible sources `used_in_draft`, and exposes the same command through the internal DataService route and typed client. `PrismReviewDataService` now resolves citation links by citation-key Source lookup instead of workspace-wide scans.
- Legacy `ReferenceUsageService` and `WorkspaceReferenceService.record_reference_usage` have been removed; runtime citation usage writes only through `SourceDataService.record_citation_usage`.
- Agent-side LaTeX compilation bibliography generation now resolves `citation_ids` through Source DataService within the runtime workspace and formats BibTeX from canonical Source metadata. `ExecutionMiddleware` no longer imports legacy reference ORM models or the bibliography sync service.
- Workspace built-in tools now resolve workspace access through `WorkspaceDataService` and list recent artifacts through `AssetDataService` / `workspace_assets`; they no longer import `Workspace` or `Artifact` ORM models directly.
- Thesis literature-management dashboard counts now use Source DataService count projections for total/core source state instead of reading `workspace_references`.
- Reference Library built-in tools now read outlines, search text units, and fetch source sections through Source DataService. Section access auditing now writes `provenance_links` instead of `reference_usage_events`.
- Source outline/text-unit/section read projections are exposed through internal DataService routes and typed client methods, keeping the Reference Library tool path ready for split DataService deployment.
- Gateway Reference Library list/count/detail/update/delete/status endpoints now use Source DataService projections and mutation commands. Outline/search/outline-node/page read endpoints already use Source read projections instead of `ReferenceIndexService`.
- Legacy `ReferenceIndexService` has been removed; Source outline/text-unit/page reads are owned by Source DataService.
- Historical reference rows were migrated into canonical `sources`; new manual, Semantic Scholar, Deep Search, BibTeX, and PDF-upload imports now write canonical Source rows directly.
- Source DataService now owns `source_external_ids` read/upsert APIs, internal routes, and typed client methods; reference adapter synchronization carries Semantic Scholar/upload hashes into Source detail instead of leaving external ids as an empty projection.
- Manual, Semantic Scholar, Deep Search artifact, BibTeX metadata imports, and PDF upload now use Source/Asset DataService as the canonical write path, so metadata dedupe, citation-key uniqueness, external-id upsert, asset registration, and Source projection serialization are owned by DataService.
- Reference BibTeX build, citation validation, and Prism sync now read canonical Source metadata through Source DataService; Source curation state is reflected in exported `refs.bib`.
- Prism BibTeX sync now writes projection snapshots through Source DataService into canonical `source_bibtex_snapshots`; runtime no longer writes `reference_bibtex_snapshots`.
- Chat/LangGraph citation and literature-context middleware now receives Source DataService projections from FastAPI and Celery run entrypoints, parses LaTeX `\cite{...}` keys, and records usage through Source citation usage/provenance commands. Legacy `search_in_workspace` / `record_reference_usage` fallback has been removed.
- Reference evidence-pack assembly is now a canonical `SourceDataService.build_evidence_pack` contract over Source library outlines and Source text-unit search results; the gateway no longer exports or calls `ReferenceEvidenceService`.
- PDF preprocessing now mirrors rebuilt reference outline/text-unit indexes into Source DataService, including Source status/evidence promotion to indexed full text.
- Reference PDF and derived markdown/manifest assets now register canonical `workspace_assets` rows and `source_assets` links; Source detail/list projections can return asset metadata from DataService.
- Source DataService now exposes source asset read/update APIs for preprocess status and metadata, enabling PDF preprocess to move off `reference_assets`.
- Reference PDF upload now creates canonical `sources`, `workspace_assets`, and `source_assets` directly; queued preprocess payloads use `source_id`, `source_asset_id`, and `workspace_asset_id`, and `SourcePreprocessService` writes canonical Source indexes.
- Legacy `WorkspaceReferenceService` and `ReferencePreprocessService` have been removed from the runtime service surface; reference detail and PDF preprocess no longer use legacy reference ORM tables.
- Legacy reference ORM table models have been removed. Migration `072_drop_legacy_reference_tables.py` drops `workspace_references`, `reference_external_ids`, `reference_assets`, `reference_outline_nodes`, `reference_text_units`, `reference_usage_events`, and `reference_bibtex_snapshots` after the Source DataService cutover.
- Gateway import/BibTeX service classes have been renamed to `SourceLibraryImportService` and `SourceBibliographyService`; no legacy `ReferenceImportService` / `ReferenceBibTeXService` aliases remain.
- Remaining Source convergence debt is limited to broad product route naming decisions, not data ownership or compatibility fallback.
- Alembic env no longer imports legacy reference/workspace-run/thread-message JSON ORM models; `cd backend && .venv/bin/python -m alembic heads` resolves `075_enforce_workspace_owner_membership` as the single head.
- Legacy `PrismReviewService` has been deleted. Runtime code outside DataService/database ownership packages is guarded from importing `PrismReviewItem`, `PrismSourceLink`, or `PrismProtectedSection`.
- Legacy Prism review ORM models have been deleted. Migration `071_drop_legacy_prism_review_tables.py` drops `prism_review_items`, `prism_source_links`, and `prism_protected_sections` after the DataService cutover.
- Verification after the Source curation/evidence/indexer/asset/upload-preprocess/BibTeX snapshot cleanup, Prism action-contract cleanup, conversation JSON-write removal, owner invariant, review transaction cleanup, run-history route cutover, and rooms direct-DataService route cutover slices is green through `cd /Users/ze/wenjin/backend && .venv/bin/python -m pytest tests/ -q` with 1935 backend tests.
- Architecture guard now blocks runtime imports of migrated room/sandbox/source/document/settings/workspace-run/compute-session legacy model modules and model names; `WorkspaceRunRow` no longer exists in ORM metadata. The guard also blocks runtime access to legacy `threads.messages` JSON.
- Architecture guard also blocks the retired `src.services.rooms` service facade package from returning.
- Migration `070_dataservice_projection_cleanup.py` records the projection cleanup stage in `dataservice_migration_reports`.
- Source-named gateway services (`SourceLibraryImportService`, `SourceBibliographyService`) delegate canonical business logic to DataService; no legacy reference service class aliases remain.
- Verification: `cd backend && .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py tests/services/test_thread_service.py tests/dataservice/test_conversation_domain.py tests/services/test_workspace_activity_service.py -q` passes with 44 tests; owner invariant target tests pass with 11 tests; review transaction target tests pass with 14 tests; execution commit DataService target tests pass with 34 tests; execution engine run-history event tests pass with 16 tests; workspace run-history route cutover target tests pass with 28 tests; room direct-DataService route target tests pass with 34 tests; sandbox route cutover target tests pass with 32 tests; library route cutover target tests pass with 44 tests; documents route cutover target tests pass with 34 tests; `cd backend && .venv/bin/python -m pytest tests/ -q` passes with 1935 tests; `cd frontend && npm run typecheck` and `cd frontend && npm run lint` pass.

### Task 14: Final Drop/Archive Gate

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
