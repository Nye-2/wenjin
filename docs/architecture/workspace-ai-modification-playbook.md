# Workspace AI Modification Playbook

Last updated: 2026-03-17  
Audience: AI coding agents modifying `AcademiaGPT-V2` workspace pipelines (backend-first)

## 1. Scope And Goals

This document defines the safe way to modify workspace features without breaking:

- task dispatch and execution contracts
- thesis LangGraph + handler fallback chain
- artifact persistence and version lineage
- memory extraction and personalization flow
- frontend-visible response schemas

If a change conflicts with this playbook, update tests first, then update this playbook in the same PR.

## 2. End-To-End Chain (Backend)

High-level path (workspace feature execution):

1. API receives feature execution request.
2. Unified task dispatch routes by `task_type` and feature metadata.
3. `execute_workspace_feature()` executes the feature.
4. For thesis `workspace_feature` tasks, LangGraph is attempted first; fallback handler is used on failure.
5. Artifacts are persisted and returned as references.
6. Async memory extraction is scheduled.

Key files:

- `backend/src/workspace_features/registry.py`
- `backend/src/workspace_features/runtime.py`
- `backend/src/task/handlers/workspace_feature_handler.py`
- `backend/src/agents/thesis_lead_agent.py`
- `backend/src/agents/graphs/thesis/*.py`
- `backend/src/academic/services/artifact_service.py`
- `backend/src/services/knowledge_service.py`
- `backend/src/agents/middleware/memory.py`

## 3. Non-Negotiable Contracts

### 3.1 Feature Result Payload Contract

Every feature execution result returned to task layer must include:

- `success` (bool)
- `feature_id`
- `feature_name`
- `workspace_type`
- `handler_key`
- `message`
- `artifacts` (list)
- `refresh_targets` (list)
- `data` (dict)

Notes:

- Non-thesis handler results are normalized by `WorkspaceFeatureExecutionResult.to_payload()`.
- Thesis LangGraph wrapper in `workspace_feature_handler._try_langgraph_execution()` must keep schema parity, including `success: True`.

### 3.2 Artifact Persistence Contract

Versioned artifacts are protected at two levels:

1. Application-level lock + retry in `ArtifactService.create()`
2. DB unique constraint: `(workspace_id, type, title, version)`

Current implementation:

- Model constraint: `backend/src/database/models/artifact.py`
- Retry logic: `backend/src/academic/services/artifact_service.py`
- Migration: `backend/alembic/versions/006_add_artifact_version_unique_constraint.py`

Do not remove either level. App lock alone is insufficient.

### 3.3 Knowledge Service Single Source Of Truth

Only one `KnowledgeService` implementation is allowed:

- Canonical path: `backend/src/services/knowledge_service.py`

Do not recreate `backend/src/academic/services/knowledge_service.py` or any duplicate implementation.

## 4. How To Add Or Modify A Workspace Feature

### Step 1: Registry Definition

Add/update `WorkspaceFeatureDefinition` in `backend/src/workspace_features/registry.py`.

Required fields to verify:

- `workspace_type`
- `id` (stable)
- `handler_key` (stable)
- `task_type` (correct route target)

Rule:

- `task_type="thesis_generation"` is reserved for thesis writing flow.
- Other thesis features commonly use `task_type="workspace_feature"` with LangGraph-first behavior.

### Step 2: Handler Implementation (Fallback Path)

Implement handler under `backend/src/workspace_features/handlers/`.

Use runtime context APIs:

- `context.update(...)`
- `context.persist_artifacts(...)`

Return `WorkspaceFeatureExecutionResult` only.

Do not return ad-hoc dict schemas from handlers.

### Step 3: Thesis LangGraph Sub-Graph (If Applicable)

If feature is thesis and should use LangGraph:

1. Add graph module in `backend/src/agents/graphs/thesis/`.
2. Register with `@register_feature_graph("<feature_id>")`.
3. Ensure it is imported by `_ensure_graphs_loaded()` in `workspace_feature_handler.py`.
4. Add artifact mapping in `_build_langgraph_artifact_drafts()` if artifacts are expected.

Rule:

- LangGraph result schema should be deterministic and JSON-serializable.
- Fallback to handler must remain functional on any graph exception.

### Step 4: Artifact Type And Title Strategy

When persisting artifacts:

- Use stable `ArtifactType` values.
- Use deterministic, user-readable titles.
- For version-tracked artifacts (with title), avoid title randomness that breaks lineage.

### Step 5: Memory Integration

Memory writeback is async and scheduled from `workspace_feature_handler._schedule_memory_extraction()`.

Do:

- keep `feature_id` and `message` meaningful for extraction prompts

Do not:

- block feature completion on memory extraction
- raise errors if memory extraction fails

## 5. Testing Requirements (Minimum)

For any workspace-chain change, run at least:

```bash
pytest -q tests/agents/graphs/thesis
pytest -q tests/task/test_workspace_feature_handler.py
pytest -q tests/task/test_langgraph_dispatch.py
pytest -q tests/task/test_thesis_handlers.py
pytest -q tests/task/test_workspace_feature_runtime.py
pytest -q tests/task/test_workspace_feature_registry.py
pytest -q tests/academic/services/test_artifact_versioning.py
pytest -q tests/services/test_knowledge_service.py tests/services/test_memory_compaction.py
pytest -q tests/agents/middleware/test_memory.py
pytest -q tests/workspace_features/test_five_workspace_smoke.py tests/workspace_features/test_workspace_e2e_matrix.py
```

Testing rules:

- Handler unit tests must isolate handler behavior.
  - If needed, patch `_try_langgraph_execution` to `None` in handler-specific tests.
- LangGraph dispatch tests should validate wrapper contracts and fallback behavior.
- Artifact tests must include conflict/retry scenarios.

## 6. Migration Rules

When adding constraints/indexes on hot tables:

1. pre-clean invalid/duplicate data in migration
2. add constraint/index
3. ensure downgrade path exists
4. add/adjust service-level retries if write conflicts are possible

Never ship a constraint migration that can fail on existing production-like data.

## 7. Common Anti-Patterns To Avoid

- Duplicating service implementations across namespaces
- Returning inconsistent payload schemas between LangGraph and fallback handlers
- Coupling tests to external DB/LLM/model-provider availability
- Swallowing exceptions without logging context
- Using artifact titles that prevent version lineage
- Adding thesis logic branches outside centralized dispatch/registry flow

## 8. Definition Of Done For Workspace Changes

A workspace change is done only if:

1. Registry, runtime, and handler/graph routing are aligned.
2. Response schema is contract-compatible (`success` and standard fields present).
3. Artifact persistence is deterministic and version-safe.
4. Memory side effects are non-blocking.
5. Required test matrix passes.
6. This playbook is updated if architectural behavior changed.

## 9. Quick Decision Guide

- "Need deterministic business fallback?" -> implement/maintain handler in `workspace_features/handlers`.
- "Need multi-step reasoning or richer generation?" -> add/extend thesis LangGraph sub-graph.
- "Need persistent user memory?" -> use `src/services/knowledge_service.py`, do not fork.
- "Need new artifact chain semantics?" -> update model + migration + `ArtifactService` retry logic together.

## 10. Frontend Alignment (TaskFeedbackBanner / ResultPanel / refresh_targets)

This section defines how frontend must consume workspace task results so UI and backend contracts stay aligned.

### 10.1 Frontend Integration Surface

Primary files:

- `frontend/components/workspace/TaskFeedbackBanner.tsx`
- `frontend/components/workspace/WorkspaceResultPanel.tsx`
- `frontend/hooks/useFeatureTaskRunner.ts`
- `frontend/app/(workbench)/workspaces/[id]/components/ChatPanel.tsx`
- `frontend/stores/workspace.ts`

Rule:

- Do not bypass these building blocks with feature-specific ad-hoc polling logic.
- If a feature needs special rendering, keep polling and refresh logic in shared hook/component layers.

### 10.2 TaskFeedbackBanner Contract

`TaskFeedbackBanner` is for execution feedback, not final business output.

Expected usage:

- `isRunning=true` -> show pending/spinning status.
- `status` -> show progress/status message from task polling.
- `error` -> show terminal failure message (highest priority).
- `onRetry` -> retry the exact same action function with current form state.

Do:

- pass backend progress text (`task.message`) as `status`.
- clear stale error/status before re-running task.

Do not:

- put final generated content in banner.
- hide backend error details unless they contain sensitive data.

### 10.3 WorkspaceResultPanel Contract

`WorkspaceResultPanel` is a normalized view layer, not raw task JSON.

Use `WorkspaceResultViewModel` shape only:

- `summary`: one concise business summary
- `sections`: structured key blocks (`title`, `content`)
- `nextActions`: concrete next steps for users
- `outputLanguage`: optional language tag (`zh`/`en`)

Mapping rule:

- parse `task.result` defensively (unknown -> typed view model).
- tolerate partial/missing fields and provide safe defaults.
- never assume backend fields always exist; guard each field before rendering.

### 10.4 refresh_targets Linkage Contract

Backend emits refresh directives in terminal task result:

- path: `task.result.refresh_targets`
- current supported values: `artifacts`, `papers`, `workspace`

Consumer behavior:

- If `artifacts` present -> call `fetchArtifacts(workspaceId)`
- If `papers` present -> call `fetchPapers(workspaceId)`
- If `workspace` present -> call `loadWorkspace(workspaceId)`

Current implementation status:

- `ChatPanel` already follows this contract.
- `useFeatureTaskRunner` now supports automatic target-based refresh on success.

Reference implementation pattern:

```ts
const targets = Array.isArray(task.result?.refresh_targets)
  ? task.result.refresh_targets.filter((t): t is string => typeof t === "string")
  : [];

const jobs: Promise<unknown>[] = [];
if (targets.includes("artifacts")) jobs.push(fetchArtifacts(workspaceId));
if (targets.includes("papers")) jobs.push(fetchPapers(workspaceId));
if (targets.includes("workspace")) jobs.push(loadWorkspace(workspaceId));
await Promise.all(jobs);
```

Extension rule:

- If backend introduces a new refresh target, frontend must update:
  - consumer mapping logic (`ChatPanel` and/or shared runner hook)
  - corresponding store action support
  - tests or page-level verification

### 10.5 Frontend Done Criteria For Workspace Changes

A workspace frontend change is done only if:

1. Task submission and polling use shared APIs (`executeWorkspaceFeature`, `getTaskStatus`).
2. Banner state and result panel state are clearly separated.
3. `refresh_targets` are consumed for all relevant resources.
4. No page relies on backend-specific raw JSON layout without defensive parsing.
5. Failure, warning, and retry flows are explicitly testable in UI.
