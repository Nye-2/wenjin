# DataService Internal Architecture Design

**Date:** 2026-05-20
**Status:** Accepted design gate before code
**Scope:** Internal domain model, aggregate boundaries, business services, repository rules, API shape, and model optimization rules for the standalone DataService.

---

## 1. Design Position

DataService is a standalone internal service, not a backend package facade. Its internal structure must optimize Wenjin's data model instead of mirroring the current table layout.

The main correction is:

```text
old shape: routers/services import old ORM tables directly
bad migration: wrap every old table with one repository
target shape: DataService owns domain aggregates and exposes command/query APIs
```

The service owns business semantics. Tables are persistence details behind aggregate repositories.

---

## 2. Core Decisions

| Decision | Requirement |
| --- | --- |
| Domain-sliced package | Organize DataService by business domain, not by global `models/`, `repositories/`, `services/` buckets. |
| Aggregate root first | Every write operation targets an aggregate root and enforces invariants before persistence. |
| Command/query split | Mutating APIs are command endpoints with idempotency and actor context. Read APIs are projection endpoints. |
| No remote CRUD | Other services cannot call `create_row`, `update_table`, or `select_model`. They call business operations. |
| Review-centered materialization | Agent-produced mutations are staged into review batches/items, then applied by target handlers. |
| Workspace access as first-class model | Workspace access is not inferred forever from `workspaces.user_id`; membership is a canonical table. |
| Outbox-ready | Domain commands can append outbox events in the same transaction. Publishing can be added later without changing command semantics. |
| Legacy tables are input material | Existing tables are migration sources, not the shape of the new model. |

---

## 3. Target Package Layout

```text
backend/src/dataservice/
  common/
    actor.py
    errors.py
    idempotency.py
    pagination.py
    time.py
    unit_of_work.py
  domains/
    workspace/
      models.py
      contracts.py
      repository.py
      service.py
      projection.py
      policies.py
    conversation/
      models.py
      contracts.py
      repository.py
      service.py
      projection.py
      block_protocol.py
    catalog/
      models.py
      contracts.py
      repository.py
      service.py
      seed_loader.py
    execution/
      models.py
      contracts.py
      repository.py
      service.py
      projection.py
    review/
      models.py
      contracts.py
      repository.py
      service.py
      registry.py
    asset/
      models.py
      contracts.py
      repository.py
      service.py
      review_handler.py
    prism/
      models.py
      contracts.py
      repository.py
      service.py
      projection.py
      review_handler.py
      adapters/
        latex.py
        markdown.py
    source/
      models.py
      contracts.py
      repository.py
      service.py
      projection.py
      importers.py
      preprocess.py
      review_handler.py
    sandbox/
      models.py
      contracts.py
      repository.py
      service.py
      projection.py
      policy.py
      review_handler.py
    provenance/
      models.py
      contracts.py
      repository.py
      service.py
    rooms/
      models.py
      contracts.py
      repository.py
      service.py
      projection.py
      review_handler.py
    operations/
      models.py
      repository.py
      outbox.py
  app_boundary.py
  conversation_api.py
  workspace_api.py
backend/src/dataservice_app/
  app.py
  deps.py
  auth.py
  routers/
    health.py
    workspace.py
    conversation.py
    catalog.py
    execution.py
    review.py
    asset.py
    prism.py
    source.py
    sandbox.py
    rooms.py
backend/src/dataservice_client/
  client.py
  errors.py
  contracts/
```

Rationale:

- Domain files stay small enough to reason about.
- Aggregates, repository methods, and domain services live together.
- Tests can target one domain without importing the whole DataService surface.
- A future repo split can move `dataservice/`, `dataservice_app/`, and `dataservice_client/` cleanly.
- `workspace_api.py` is the current monorepo public boundary for workspace operations while runtime consumers are being cut over. Runtime code may depend on this public module, but must not import `src.dataservice.domains.*`. The end-state consumer path remains `dataservice_client -> dataservice_app -> domains`.
- `conversation_api.py` plays the same temporary public-boundary role for thread message/block writes while `threads.messages` is still maintained as a response bridge.

---

## 4. Actor And Workspace Scope

Every command/query receives an actor context:

| Field | Meaning |
| --- | --- |
| `actor_user_id` | Authenticated user id from gateway. |
| `actor_kind` | `user`, `system`, `worker`, `migration`, `admin`. |
| `workspace_id` | Required for workspace-scoped operations. |
| `request_id` | Request/correlation id. |
| `idempotency_key` | Required for mutating external calls. |
| `source_service` | `gateway`, `worker`, `langgraph`, `admin`, `migration`. |

Workspace access is checked through `workspace_memberships`.

Canonical workspace model amendment:

| Table | Purpose |
| --- | --- |
| `workspaces` | Workspace identity and lifecycle. |
| `workspace_memberships` | Access/membership SSOT. Seeded from existing `workspaces.user_id`. |
| `workspace_settings` | Mutable settings. |
| `threads` | Conversation membership. |

`workspaces.user_id` should not stay as the long-term access SSOT. It can be migrated to `created_by_user_id` or retained only as a denormalized owner shortcut during the first cut.

---

## 5. Aggregate Map

| Domain | Aggregate root | Owns | Does not own |
| --- | --- | --- | --- |
| Workspace | `WorkspaceAggregate` | workspace identity, membership, settings, active thread pointer | message blocks, executions, assets |
| Conversation | `ConversationAggregate` | threads, messages, block protocol arrival order, tool invocation/result linkage | execution graph, review apply |
| Catalog | `CapabilityCatalogAggregate` | capability definitions, skills, seed revisions | execution state |
| Execution | `ExecutionAggregate` | execution, nodes, events, run status | worker queue internals, review apply |
| Review | `ReviewBatchAggregate` | review batches, review items, action logs, state transitions, apply orchestration | target table internals |
| Asset | `WorkspaceAssetAggregate` | file/blob metadata, derivative links, deletion state | source semantics, Prism editable file semantics |
| Prism | `PrismProjectAggregate` | Prism project/doc/file/version/render/protected scope | source library, binary storage, execution running |
| Source | `SourceAggregate` | source metadata, external ids, source assets, outline, text units, BibTeX snapshots | workspace assets binary storage, Prism files |
| Sandbox | `SandboxEnvironmentAggregate` | environment state, sandbox jobs, sandbox artifacts | Docker execution implementation, host/container control |
| Provenance | `ProvenanceGraphAggregate` | anchors and links from sources/assets/executions to targets | target mutation state |
| Rooms | `WorkspaceRoomsAggregate` | decisions, memory facts, workspace tasks | review staging, execution lifecycle |
| Operations | `DataOperationAggregate` | idempotency keys, outbox events, migration reports | user-facing business facts |

---

## 6. Domain Responsibilities

### 6.1 Workspace Domain

Current scattered logic:

- `thread_service.py`
- `workspace_summary_service.py`
- workspace access checks in gateway routers
- settings room service

Target commands:

| Command | Behavior |
| --- | --- |
| `create_workspace` | Create workspace, owner membership, settings row, and optional initial thread in one transaction. |
| `set_active_thread` | Validate thread belongs to workspace, then update active pointer. |
| `patch_workspace_settings` | Update typed settings and extension JSON with schema validation. |
| `archive_workspace` | Soft archive workspace and emit outbox event. |
| `ensure_workspace_access` | Shared policy used by every workspace-scoped command/query. |

Invariants:

- Every workspace has at least one `owner` membership.
- Active thread must belong to the same workspace.
- Settings row is 1:1 with workspace.
- Workspace type is immutable after creation unless an admin migration command changes it.

### 6.1.1 Conversation Domain

Current scattered logic:

- `thread_service.py`
- JSON `threads.messages` bridge storage
- block protocol payloads in agent/runtime/frontend flow
- tool invocation/result metadata embedded in message blocks

Target commands:

| Command | Behavior |
| --- | --- |
| `create_thread` | Create workspace-scoped or standalone thread with actor context. |
| `append_message` | Append user/assistant/system message metadata. |
| `append_block` | Append one of the canonical 7 block types in arrival order. |
| `append_tool_invocation` | Persist tool call metadata and link to message/execution node when available. |
| `append_tool_result` | Persist tool result metadata and link to invocation. |
| `compact_thread_context` | Write compaction metadata without rewriting historical block order. |
| `get_conversation_projection` | Return thread/message/block read model for workbench chat. |

Invariants:

- The 7 block types are canonical: `text`, `thinking`, `status_line`, `question_card`, `result_card`, `tool_invocation`, `tool_result`.
- Block arrival order is append-only.
- Thinking blocks are stored in arrival order, never prepended.
- `threads.messages` can be a migration bridge, not the final block protocol SSOT; API readers, run wait views, workspace activity, Chat Agent context, compaction, rollback, and attachment-status mutation sources already read DataService conversation projections.
- Tool invocation and result records can link to execution nodes when produced by Lead Agent runs.

### 6.2 Catalog Domain

Current scattered logic:

- capability seed loaders
- admin capability/skill services
- capability resolver / skill resolver / middleware preload

Target commands:

| Command | Behavior |
| --- | --- |
| `load_seed_revision` | Validate v2 YAML, write seed revision, upsert definitions/skills. |
| `patch_capability` | Admin edit with schema validation and audit metadata. |
| `patch_skill` | Admin edit with worker/tool/resource validation. |
| `resolve_launch_catalog` | Query available capabilities for workspace type and actor. |

Invariants:

- Every catalog row has `schema_version`.
- Seed load is idempotent by checksum.
- Runtime consumes DB catalog only; YAML is seed input.

Implementation checkpoint, 2026-05-21:

- Catalog domain package exists with models, contracts, repository, projection, service, and seed loader.
- Internal DataService catalog routes and typed client contracts exist.
- `CatalogDataService` is the public in-process boundary for the current monorepo cutover; runtime/admin code imports it instead of domain repositories or old catalog ORM models.
- YAML seed loading is centralized in `DataServiceCatalogSeedLoader`; `CapabilityLoader` and `SkillLoader` now only validate legacy YAML shapes and delegate persistence to DataService.
- Admin capability/skill services, capability/skill resolvers, middleware preload, launch/list tools, dashboard/summary projections, Lead runtime skill loading, and Compute projection now consume catalog projections.
- `capability_skills` remains the physical skill table during this slice, but ownership moved to the DataService catalog aggregate and its external contract is `capability_skill.v2`.

### 6.3 Execution Domain

Current scattered logic:

- `execution_service.py`
- `execution/engine.py`
- `compute/projection_service.py`
- `workspace_run_service.py`
- `run_history_service.py`
- `task_records` product reads

Target commands:

| Command | Behavior |
| --- | --- |
| `create_execution` | Create execution root, initial graph, initial event. |
| `mark_execution_running` | Enforce one active execution per workspace. |
| `record_node_event` | Upsert node state and append ordered event. |
| `complete_execution` | Set terminal status and summary, append event. |
| `fail_execution` | Set terminal failure and append error event. |
| `get_live_workflow_projection` | Build workflow read model from execution/nodes/events/review. |

Invariants:

- Execution is product run SSOT.
- `task_records` is infrastructure only.
- Ordered events are append-only.
- Node state can be updated, but event history is not rewritten.

### 6.4 Review Domain

Current scattered logic:

- `ExecutionCommitService`
- `PrismReviewService`
- frontend transient ResultCard state
- room services accepting direct candidate writes

Target model amendment:

| Table | Purpose |
| --- | --- |
| `review_batches` | One review surface/package, usually produced by one execution. |
| `review_items` | Individual proposed mutations inside a batch. |
| `review_action_logs` | Append-only state transition audit. |

Target commands:

| Command | Behavior |
| --- | --- |
| `stage_review_batch` | Create batch and items from execution output with default selections. |
| `set_item_decision` | Accept/reject/edit a single item. |
| `apply_batch` | Apply accepted items through target handlers in one transaction boundary. |
| `apply_item` | Apply one accepted item through the matching handler. |
| `revert_item` | Revert supported targets and log action. |

Target handler registry:

| Target kind | Handler location | Target owner |
| --- | --- | --- |
| `prism_file_change` | `domains/prism/review_handler.py` | Prism |
| `source_candidate` | `domains/source/review_handler.py` | Source |
| `workspace_asset` | `domains/asset/review_handler.py` | Asset |
| `room_decision`, `room_memory`, `room_task`, `room_document` | `domains/rooms/review_handler.py` | Rooms |
| `sandbox_artifact` | `domains/sandbox/review_handler.py` | Sandbox |

Invariants:

- Agent output cannot mutate Prism/rooms/assets directly.
- Apply action and target write are one transaction.
- Review owns state transitions and orchestration; target domains own target business writes.
- Review item status transitions are controlled by domain service.

### 6.5 Asset Domain

Current scattered logic:

- `documents_v2`
- `artifacts`
- file-like generation outputs
- latex compile output paths
- reference asset file metadata

Target commands:

| Command | Behavior |
| --- | --- |
| `register_asset` | Store metadata for an uploaded/generated file. |
| `register_derivative` | Link derivative asset to parent asset. |
| `mark_deleted` | Soft delete asset and optionally descendants. |
| `resolve_asset_download` | Return storage pointer only after workspace access check. |

Invariants:

- Large content is outside DB.
- `workspace_assets` owns file/blob metadata, not business meaning.
- Business domains link to assets instead of duplicating storage fields.

### 6.6 Prism Domain

Current scattered logic:

- `LatexProjectService`
- `WorkspacePrismService`
- `LatexCompileService`
- `PrismReviewService`
- direct LaTeX filesystem writes

Target commands:

| Command | Behavior |
| --- | --- |
| `ensure_primary_project` | Create/retrieve workspace primary Prism project. |
| `create_document_file` | Create a Prism file node and initial version. |
| `apply_file_change` | Create immutable file version from accepted review item. |
| `record_render` | Record render/compile result and asset links. |
| `protect_scope` | Add protected scope for user/system/review reason. |
| `get_prism_surface_projection` | Return editor/preview/readiness projection. |

Invariants:

- Prism is adapter-neutral; LaTeX is an adapter.
- Editable text history is in file versions.
- Compile/render outputs are assets linked by `prism_renders`.
- Primary manuscript is unique per workspace.

### 6.7 Source Domain

Current scattered logic:

- `WorkspaceReferenceService`
- `ReferenceImportService`
- `ReferencePreprocessService`
- `ReferenceIndexService`
- `ReferenceBibTeXService`
- legacy `LibraryService`

Target commands:

| Command | Behavior |
| --- | --- |
| `upsert_source` | Deduplicate by DOI/external id/normalized title and merge evidence. |
| `import_sources` | Import manual/semantic scholar/deep search/BibTeX/uploaded PDF candidates. |
| `attach_source_asset` | Link source to workspace asset. |
| `apply_preprocess_result` | Replace outline/text units for an asset with migration-safe deletion/rebuild. |
| `record_source_usage` | Create provenance link, not source-local usage event. |
| `build_bibtex_snapshot` | Project sources into a deterministic BibTeX snapshot. |

Invariants:

- Product name is `Source`; no `LibraryItem` vs `Reference` split.
- Full-text extraction output is replaceable/rebuildable.
- Citation key uniqueness is workspace-scoped.

### 6.8 Sandbox Domain

Current scattered logic:

- `rooms/sandbox_service.py`
- execution Docker service
- compute projection sandbox output parsing

Target commands:

| Command | Behavior |
| --- | --- |
| `ensure_environment` | Create/update workspace sandbox environment state and policy snapshot. |
| `record_job_started` | Persist runtime image, language, input assets, policy, hashes. |
| `record_job_finished` | Persist terminal status, stdout/stderr assets, error. |
| `register_artifact` | Link job output asset to review item and artifact role. |

Invariants:

- Sandbox jobs are Python-only in the first version.
- Sandbox policy blocks Docker socket, host network, privileged mode, host paths, sibling container access, and server-level operations.
- Sandbox execution implementation remains outside DataService; DataService records state and artifacts.

### 6.9 Provenance Domain

Current scattered logic:

- `prism_source_links`
- `reference_usage_events`
- source fields embedded in review payloads

Target commands:

| Command | Behavior |
| --- | --- |
| `create_anchor` | Create reusable anchor into source/asset/sandbox/external URL/execution. |
| `link_target` | Link anchor to Prism version, source, room entity, asset, or review item. |
| `replace_target_links` | Replace target provenance after accepted edit. |

Invariants:

- Provenance is a graph, not a per-domain side table.
- Links are append-friendly and queryable by source or target.
- Target writes do not invent source semantics outside provenance.

### 6.10 Rooms Domain

Current scattered logic:

- `rooms/decisions_service.py`
- `rooms/memory_service.py`
- `rooms/workspace_tasks_service.py`
- direct room writes from commit flow

Target commands:

| Command | Behavior |
| --- | --- |
| `apply_decision_candidate` | Supersede old decision if needed and create provenance. |
| `apply_memory_candidate` | Add memory fact with confidence and provenance. |
| `apply_workspace_task_candidate` | Create/update task with execution/review linkage. |
| `get_room_projection` | Return room read models. |

Invariants:

- Candidate room writes come through review.
- User direct edits can write rooms directly through DataService commands.
- Memory and decisions are workspace-scoped, not global user knowledge.

### 6.11 Operations Domain

This domain supports service correctness, not product features.

Tables:

| Table | Purpose |
| --- | --- |
| `dataservice_idempotency_keys` | Deduplicate mutating API calls. |
| `dataservice_outbox_events` | Transactional event publishing buffer. |
| `dataservice_migration_reports` | Row counts, hashes, orphan reports, and cutover proof. |

`dataservice_idempotency_keys` persists the readable scope fields and a derived `scope_hash`. Uniqueness is enforced by `scope_hash` plus `idempotency_key` so nullable `workspace_id` / `actor_user_id` do not weaken deduplication semantics.

First implementation can create these as part of foundation or with the first domain migration. The API and UoW should be designed as if they exist from day one.

---

## 7. API Shape

DataService app endpoints are internal and versioned:

```text
/internal/v1/workspaces/{workspace_id}/context
/internal/v1/workspaces/{workspace_id}/settings
/internal/v1/catalog/resolve
/internal/v1/executions
/internal/v1/executions/{execution_id}/events
/internal/v1/review/batches
/internal/v1/review/batches/{batch_id}/apply
/internal/v1/prism/workspaces/{workspace_id}/surface
/internal/v1/sources
/internal/v1/assets
/internal/v1/sandbox/jobs
/internal/v1/rooms/{workspace_id}
```

Headers:

| Header | Required | Purpose |
| --- | --- | --- |
| `X-Wenjin-Internal-Token` | yes in deployed mode | Service-to-service auth. |
| `X-Wenjin-Actor-User-Id` | for user-scoped requests | Actor identity. |
| `X-Wenjin-Actor-Kind` | yes | `user`, `system`, `worker`, `migration`, `admin`. |
| `X-Request-Id` | yes | Correlation id. |
| `Idempotency-Key` | mutating APIs | Deduplication. |

API rules:

- Commands accept typed request contracts and return typed result contracts.
- Query endpoints return projections and never expose ORM-shaped payloads.
- Internal token authenticates service caller; actor context authorizes business access.
- All endpoints use a standard response envelope: `ok`, `data`, `error`, `request_id`, and optional `revision`.
- Error codes are stable contract values: `UNAUTHENTICATED_INTERNAL_CALL`, `FORBIDDEN_WORKSPACE_ACCESS`, `NOT_FOUND`, `VALIDATION_ERROR`, `IDEMPOTENCY_CONFLICT`, `CONFLICT`, `TARGET_HANDLER_NOT_FOUND`, `TARGET_APPLY_FAILED`, `MIGRATION_VALIDATION_FAILED`, `INTERNAL_ERROR`.
- Idempotency uniqueness is logically scoped by `source_service`, `command_name`, optional `workspace_id`, optional `actor_user_id`, and `idempotency_key`; persisted uniqueness uses a deterministic `scope_hash` plus `idempotency_key`.
- Reusing the same idempotency key with a different normalized request hash returns `IDEMPOTENCY_CONFLICT`.

---

## 8. Repository And Service Rules

Repositories:

- Load and persist aggregate data.
- Use typed query methods, not generic table CRUD.
- May use row locks for aggregate invariants.
- Never commit, never publish events, never call LLM/tools.

Domain services:

- Own command workflows and invariants.
- Coordinate multiple repositories within one UoW.
- Append outbox events for externally relevant changes.
- Call review target handlers for materialization.

Projection builders:

- Read only.
- Return contracts or dictionaries.
- Can compose multiple repositories but cannot mutate state.

Target handlers:

- Are registered by target kind.
- Apply accepted review items to one target domain.
- Must be idempotent by review item id.

---

## 9. Model Optimization Amendments

These amendments should be applied to the SSOT model before implementation:

| Amendment | Reason |
| --- | --- |
| Add `workspace_memberships` | Stops overloading `workspaces.user_id` as permanent access model and prepares collaboration. |
| Add `review_batches` | Matches product result-card flow and avoids loose review item groups. |
| Add operations tables | Enables idempotency, outbox, and migration proof inside service boundary. |
| Domain-slice package layout | Prevents a new `models/` and `services/` directory from becoming another large mixed layer. |
| Treat `compute_sessions` as cache/projection | Avoids a second run lifecycle state. |
| Treat `task_records` as infra | Keeps worker queue separate from product execution. |

---

## 10. Implementation Order

1. Update SSOT docs with this internal architecture.
2. Add only foundation code: package skeleton, app, client, UoW, guard, health.
3. Add workspace domain first, including `workspace_memberships`.
4. Add catalog domain.
5. Add execution domain.
6. Add review domain with `review_batches`.
7. Add asset, Prism, source/provenance, sandbox, rooms domains in that order.
8. Cut consumers to DataService clients one domain at a time.
9. Remove old runtime paths and legacy tables only after architecture guard proves no readers.

No business domain implementation should start until steps 1-2 are complete and reviewed.
