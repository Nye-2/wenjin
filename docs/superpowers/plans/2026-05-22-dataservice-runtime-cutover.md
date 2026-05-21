# DataService Runtime Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use engineering-context:subagent-driven-development (recommended) or engineering-context:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make standalone DataService the only runtime database boundary for gateway, worker, tools, agents, and business services, replacing in-process `src.dataservice.*_api` usage and remaining direct business SQL reads.

**Architecture:** `src.dataservice` and `src.dataservice_app` remain the only packages allowed to own SQLAlchemy models, repositories, unit-of-work, and DataService domain orchestration. Runtime code must use `src.dataservice_client.AsyncDataServiceClient` plus typed client contracts. No compatibility fallback: after each slice is cut over, architecture guards block the old in-process import/query path.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy async inside DataService only, httpx-based `AsyncDataServiceClient`, Pydantic v2 contracts, pytest architecture guards.

---

## Current State Audit

The DataService extraction has three completed layers:

1. `dataservice_app` runs as a standalone HTTP service in Docker Compose.
2. Every `backend/src/dataservice/*_api.py` surface now has a matching `backend/src/dataservice_app/routers/*.py` route module.
3. Every DataService surface has a matching typed client contract file under `backend/src/dataservice_client/contracts/`.

The runtime cutover is not complete:

1. `AsyncDataServiceClient` is not used by gateway/worker/business runtime yet. Current search only finds it in the client package and tests.
2. About 60 runtime files still import in-process DataService facades such as `CatalogDataService`, `SourceDataService`, `WorkspaceDataService`, `ExecutionDataService`, etc.
3. About 10 non-DataService runtime files still contain direct `select(...)` / `session.execute(...)` query paths. Some are test-model injection branches, but production code still carries direct DB logic.
4. Docker already provides `DATASERVICE_URL=http://dataservice:8080` to gateway/worker services, so deployment wiring exists; application code simply does not consume it yet.

## Target Rules

After this plan is complete:

1. Runtime packages (`gateway`, `services`, `task`, `agents`, `tools`, `compute`, `academic`) must not import `src.dataservice.*_api`.
2. Runtime packages must not import DataService domain modules or repositories.
3. Runtime packages must not run business SQL via `select(...)`, `session.execute(...)`, `session.get(...)`, or `db.execute(...)`.
4. The only runtime database exceptions are app lifecycle/bootstrap plumbing and explicitly test/dev-only hooks.
5. Gateway auth may keep the authenticated subject model only until the dedicated auth subject projection is introduced; business reads behind that subject still go through DataService client.
6. No fallback paths from HTTP client back to in-process DataService facades.

## Files To Modify

Core infrastructure:

- Modify: `backend/src/dataservice_client/client.py`
- Create: `backend/src/dataservice_client/provider.py`
- Modify: `backend/src/gateway/deps/core.py`
- Modify: `backend/tests/architecture/test_dataservice_boundaries.py`
- Modify: `backend/tests/dataservice/test_foundation.py`

Catalog/capability/skill runtime:

- Modify: `backend/src/services/capability_loader.py`
- Modify: `backend/src/services/skill_loader.py`
- Modify: `backend/src/services/capability_resolver.py`
- Modify: `backend/src/services/skill_resolver.py`
- Modify: `backend/src/services/admin_capability_service.py`
- Modify: `backend/src/services/admin_skill_service.py`
- Modify: `backend/src/services/capability_schema.py`
- Modify: `backend/src/services/dashboard_service.py`
- Modify: `backend/src/services/workspace_summary_service.py`
- Modify: `backend/src/agents/lead_agent/v2/runtime.py`
- Modify: `backend/src/agents/middlewares/capability_skill_preload.py`
- Modify: `backend/src/tools/builtins/launch_feature.py`

Workspace, rooms, source, assets:

- Modify: `backend/src/gateway/routers/workspace_rooms.py`
- Modify: `backend/src/gateway/routers/references.py`
- Modify: `backend/src/gateway/routers/workspaces.py`
- Modify: `backend/src/tools/builtins/workspace.py`
- Modify: `backend/src/tools/builtins/references.py`
- Modify: `backend/src/services/references/service.py`
- Modify: `backend/src/gateway/deps/academic.py`

Execution, task, commit:

- Modify: `backend/src/services/execution_service.py`
- Modify: `backend/src/services/execution_commit_service.py`
- Modify: `backend/src/gateway/routers/execution_commit.py`
- Modify: `backend/src/task/store.py`
- Modify: `backend/src/task/tasks/credit_periodic.py`
- Modify: `backend/src/task/tasks/run.py`
- Modify: `backend/src/compute/session_service.py`
- Modify: `backend/src/compute/projection_service.py`

Prism and LaTeX:

- Modify: `backend/src/services/workspace_prism_service.py`
- Modify: `backend/src/services/workspace_latex_projects.py`
- Modify: `backend/src/services/latex/project_service.py`
- Modify: `backend/src/services/latex/template_service.py`
- Modify: `backend/src/services/latex/compile_service.py`
- Modify: `backend/src/gateway/routers/latex_files.py`
- Modify: `backend/src/gateway/routers/latex_helpers.py`

Account, credit, audit:

- Modify: `backend/src/services/auth.py`
- Modify: `backend/src/services/user_service.py`
- Modify: `backend/src/services/user_dashboard_service.py`
- Modify: `backend/src/services/admin_dashboard_service.py`
- Modify: `backend/src/services/admin_analytics_service.py`
- Modify: `backend/src/services/credit_service.py`
- Modify: `backend/src/services/credit_redeem_service.py`
- Modify: `backend/src/services/credit_grant_rule_service.py`
- Modify: `backend/src/services/referral_service.py`
- Modify: `backend/src/services/audit_service.py`
- Modify: `backend/src/gateway/routers/admin_credit_rules.py`
- Modify: `backend/src/gateway/routers/admin_redeem_codes.py`
- Modify: `backend/src/gateway/routers/credits_redeem.py`

Docs:

- Modify: `docs/superpowers/specs/2026-05-21-dataservice-full-migration-overview.md`
- Modify: `docs/superpowers/plans/2026-05-20-dataservice-convergence.md`
- Modify: `docs/current/release-gate-checklist.md`

## Task 1: Add Runtime Client Provider And Guard Rails

- [ ] **Step 1: Add a shared DataService client provider**

Create `backend/src/dataservice_client/provider.py`:

```python
"""Runtime provider for standalone DataService HTTP clients."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from src.dataservice_client import AsyncDataServiceClient


@asynccontextmanager
async def dataservice_client() -> AsyncIterator[AsyncDataServiceClient]:
    async with AsyncDataServiceClient() as client:
        yield client
```

- [ ] **Step 2: Add FastAPI dependency wrapper**

Modify `backend/src/gateway/deps/core.py` to expose:

```python
from collections.abc import AsyncIterator

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.provider import dataservice_client


async def get_dataservice_client() -> AsyncIterator[AsyncDataServiceClient]:
    async with dataservice_client() as client:
        yield client
```

- [ ] **Step 3: Add architecture guard for in-process DataService API imports**

Modify `backend/tests/architecture/test_dataservice_boundaries.py` with a new test:

```python
RUNTIME_DATASERVICE_API_ALLOWED_ROOTS = {
    "dataservice",
    "dataservice_app",
    "dataservice_client",
}


def test_runtime_code_uses_dataservice_client_not_in_process_apis() -> None:
    violations: list[str] = []
    for path in _python_files(SRC_ROOT):
        relative = path.relative_to(SRC_ROOT)
        if relative.parts and relative.parts[0] in RUNTIME_DATASERVICE_API_ALLOWED_ROOTS:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        visitor = _RuntimeImportVisitor()
        visitor.visit(tree)
        for node in visitor.import_from_nodes:
            module = node.module or ""
            if module.startswith("src.dataservice.") and module.endswith("_api"):
                violations.append(f"{relative} imports {module}")
        for node in visitor.import_nodes:
            for alias in node.names:
                if alias.name.startswith("src.dataservice.") and alias.name.endswith("_api"):
                    violations.append(f"{relative} imports {alias.name}")
    assert not violations, "Runtime code must use dataservice_client, not in-process DataService APIs:\n" + "\n".join(violations)
```

Initially mark this test with a local allowlist containing the current violating files. Each later task removes entries until the allowlist is empty, then delete the allowlist.

- [ ] **Step 4: Add guard for direct runtime business SQL**

Add a second test that blocks `select`, `session.execute`, `db.execute`, and `session.get` outside owner packages. Start with a temporary allowlist matching the current 10 files. Remove allowlist entries slice by slice.

- [ ] **Step 5: Verify current baseline**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py -q
```

Expected: pass with allowlisted current debt.

- [ ] **Step 6: Commit**

```bash
git add backend/src/dataservice_client/provider.py backend/src/gateway/deps/core.py backend/tests/architecture/test_dataservice_boundaries.py
git commit -m "test: guard dataservice runtime cutover"
```

## Task 2: Cut Over Catalog, Capability, And Skill Runtime

- [ ] **Step 1: Extend client where missing**

Check `backend/src/dataservice_client/client.py` for methods needed by catalog runtime:

- `has_capabilities`
- `has_skills`
- `load_capability_seed_dir` is not suitable over HTTP because it depends on local filesystem validation callbacks; replace runtime seed loading with DataService-owned seed endpoints or run seed loading only inside the DataService app.
- `upsert_capability`
- `upsert_skill`
- `record_admin_log`

If a needed method is missing, add it with a typed contract under `backend/src/dataservice_client/contracts/catalog.py`.

- [ ] **Step 2: Replace production catalog reads**

Replace `CatalogDataService(self.db, ...)` production branches with `AsyncDataServiceClient` calls in:

- `backend/src/services/capability_resolver.py`
- `backend/src/services/skill_resolver.py`
- `backend/src/services/dashboard_service.py`
- `backend/src/services/workspace_summary_service.py`
- `backend/src/agents/lead_agent/v2/runtime.py`
- `backend/src/agents/middlewares/capability_skill_preload.py`
- `backend/src/tools/builtins/launch_feature.py`

Preserve unit test injection only by injecting a fake DataService client, not an ORM model.

- [ ] **Step 3: Move seed loading into DataService ownership**

Refactor:

- `backend/src/services/capability_loader.py`
- `backend/src/services/skill_loader.py`

Production seed loading should run from DataService app/startup/admin endpoint or an explicit `dataservice` CLI command. Runtime gateway/worker must not seed catalog rows directly.

- [ ] **Step 4: Replace admin catalog writes**

Refactor:

- `backend/src/services/admin_capability_service.py`
- `backend/src/services/admin_skill_service.py`
- `backend/src/services/capability_schema.py`

The YAML parsing/validation can stay in service code if it has no DB dependency. Cross-reference validation must call DataService client list/get methods instead of direct DB queries.

- [ ] **Step 5: Remove catalog files from architecture allowlists**

Remove all catalog/capability/skill files from the new guard allowlists.

- [ ] **Step 6: Run tests**

```bash
cd backend && .venv/bin/python -m pytest \
  tests/services/test_admin_capability_service.py \
  tests/services/test_admin_skill_service.py \
  tests/services/test_capability_resolver.py \
  tests/services/test_skill_resolver.py \
  tests/services/test_dashboard_service.py \
  tests/architecture/test_dataservice_boundaries.py \
  -q
```

Use actual existing test file names if they differ; if no direct test exists, add focused unit tests next to the affected service.

- [ ] **Step 7: Commit**

```bash
git add backend/src backend/tests
git commit -m "refactor: route catalog runtime through dataservice client"
```

## Task 3: Cut Over Workspace, Rooms, Source, And Asset Runtime

- [ ] **Step 1: Replace gateway room dependencies**

In `backend/src/gateway/routers/workspace_rooms.py`, replace dependency providers returning in-process `AssetDataService`, `RoomsDataService`, `SourceDataService`, `WorkspaceDataService`, `SandboxDataService`, and `ExecutionDataService` with `AsyncDataServiceClient`.

- [ ] **Step 2: Replace room route calls**

Map route operations to existing client methods:

- rooms candidates/tasks/memory/decision operations -> `AsyncDataServiceClient` rooms methods
- workspace access and metadata -> workspace client methods
- assets -> asset client methods
- source creates/imports -> source client methods
- sandbox environment creation -> sandbox client methods

If a method is missing, add it to `client.py` and the relevant contract file before changing the route.

- [ ] **Step 3: Replace Reference Library gateway/tool calls**

Refactor:

- `backend/src/gateway/routers/references.py`
- `backend/src/tools/builtins/references.py`
- `backend/src/services/references/service.py`
- `backend/src/gateway/deps/academic.py`

All source/provenance/asset/workspace operations must go through `AsyncDataServiceClient`.

- [ ] **Step 4: Replace workspace tools**

Refactor `backend/src/tools/builtins/workspace.py` so workspace access checks, capability list, and artifact list use the client.

- [ ] **Step 5: Remove files from guard allowlists**

Remove the workspace/source/rooms/assets files from both the in-process DataService API allowlist and direct SQL allowlist.

- [ ] **Step 6: Run tests**

```bash
cd backend && .venv/bin/python -m pytest \
  tests/gateway/routers/test_workspace_rooms.py \
  tests/gateway/routers/test_references.py \
  tests/services/test_references_service.py \
  tests/tools \
  tests/architecture/test_dataservice_boundaries.py \
  -q
```

- [ ] **Step 7: Commit**

```bash
git add backend/src backend/tests
git commit -m "refactor: route workspace rooms and source runtime through dataservice client"
```

## Task 4: Cut Over Execution, Task, And Commit Runtime

- [ ] **Step 1: Replace execution service facade**

Refactor `backend/src/services/execution_service.py` to use `AsyncDataServiceClient` for execution records, events, graph nodes, analytics, and reconciliation.

- [ ] **Step 2: Replace task store persistence**

Refactor `backend/src/task/store.py` so DB task-record persistence uses DataService client task methods. Redis runtime cache and event publishing remain in `TaskStore`.

- [ ] **Step 3: Replace execution commit service dependencies**

Refactor:

- `backend/src/services/execution_commit_service.py`
- `backend/src/gateway/routers/execution_commit.py`

Use client methods for room/source/asset/execution writes. If multiple DB mutations need to stay atomic, move that composition into one DataService app route instead of issuing several client calls from runtime.

- [ ] **Step 4: Replace compute services**

Refactor:

- `backend/src/compute/session_service.py`
- `backend/src/compute/projection_service.py`

Compute-session and execution projection reads must use the client.

- [ ] **Step 5: Replace worker tasks**

Refactor:

- `backend/src/task/tasks/run.py`
- `backend/src/task/tasks/credit_periodic.py`

Keep DB session only for DataService app ownership. Worker task runtime uses DataService client.

- [ ] **Step 6: Run tests**

```bash
cd backend && .venv/bin/python -m pytest \
  tests/task \
  tests/services/test_execution_service.py \
  tests/services/test_execution_commit_service.py \
  tests/compute \
  tests/architecture/test_dataservice_boundaries.py \
  -q
```

- [ ] **Step 7: Commit**

```bash
git add backend/src backend/tests
git commit -m "refactor: route execution and task runtime through dataservice client"
```

## Task 5: Cut Over Prism And LaTeX Runtime

- [ ] **Step 1: Replace workspace Prism service DataService facades**

Refactor `backend/src/services/workspace_prism_service.py` to use client methods for:

- Prism primary project/surface/file versions/protected scopes
- LaTeX workspace primary project
- review items
- provenance links
- rooms memory facts
- run history

The file-system and LaTeX content orchestration remains in this service.

- [ ] **Step 2: Move binding integrity query into DataService**

The current `get_binding_integrity_report()` uses raw SQL in `workspace_prism_service.py`. Add a DataService app/client method for this projection, then replace the raw SQL call.

- [ ] **Step 3: Replace workspace LaTeX project service**

Refactor `backend/src/services/workspace_latex_projects.py` to use:

- LaTeX client methods
- Prism-review client methods
- Workspace client methods

- [ ] **Step 4: Replace LaTeX service facades**

Refactor:

- `backend/src/services/latex/project_service.py`
- `backend/src/services/latex/template_service.py`
- `backend/src/services/latex/compile_service.py`

These services should retain file-system/compile orchestration only.

- [ ] **Step 5: Replace LaTeX gateway routes**

Refactor:

- `backend/src/gateway/routers/latex_files.py`
- `backend/src/gateway/routers/latex_helpers.py`

All Prism/PrismReview/Source operations use client methods.

- [ ] **Step 6: Run tests**

```bash
cd backend && .venv/bin/python -m pytest \
  tests/services/test_workspace_prism_service.py \
  tests/services/test_prism_review_workflow_gate.py \
  tests/services/test_latex_hardening.py \
  tests/gateway/routers/test_workspace_prism.py \
  tests/gateway/routers/test_latex_workspace_route_convergence.py \
  tests/architecture/test_dataservice_boundaries.py \
  -q
```

- [ ] **Step 7: Commit**

```bash
git add backend/src backend/tests
git commit -m "refactor: route prism and latex runtime through dataservice client"
```

## Task 6: Cut Over Account, Credit, Audit, And Admin Runtime

- [ ] **Step 1: Replace account services**

Refactor:

- `backend/src/services/user_service.py`
- `backend/src/services/user_dashboard_service.py`
- `backend/src/services/admin_dashboard_service.py`
- `backend/src/services/admin_analytics_service.py`

Use account/credit/workspace/execution/asset client methods.

- [ ] **Step 2: Replace auth helper**

Refactor `backend/src/services/auth.py` so refresh-token/user lookups use account client projection. Keep concrete `User` only where FastAPI auth dependencies still require the existing subject type. Do not perform business reads from that concrete model.

- [ ] **Step 3: Replace credit services and routes**

Refactor:

- `backend/src/services/credit_service.py`
- `backend/src/services/credit_redeem_service.py`
- `backend/src/services/credit_grant_rule_service.py`
- `backend/src/services/referral_service.py`
- `backend/src/gateway/routers/admin_credit_rules.py`
- `backend/src/gateway/routers/admin_redeem_codes.py`
- `backend/src/gateway/routers/credits_redeem.py`

Use credit/catalog client methods.

- [ ] **Step 4: Replace audit service**

Refactor `backend/src/services/audit_service.py` to call audit client methods.

- [ ] **Step 5: Remove files from guard allowlists**

Remove account/credit/audit/admin files from both architecture guard allowlists.

- [ ] **Step 6: Run tests**

```bash
cd backend && .venv/bin/python -m pytest \
  tests/services/test_user_service.py \
  tests/services/test_admin_dashboard_service.py \
  tests/services/test_admin_analytics_service.py \
  tests/services/test_credit_service.py \
  tests/services/test_credit_redeem_service.py \
  tests/services/test_referral_service.py \
  tests/services/test_audit_service.py \
  tests/architecture/test_dataservice_boundaries.py \
  -q
```

- [ ] **Step 7: Commit**

```bash
git add backend/src backend/tests
git commit -m "refactor: route account credit and audit runtime through dataservice client"
```

## Task 7: Delete Test-Model Fallbacks And Direct SQL Runtime Branches

- [ ] **Step 1: Remove production service `model` injection branches**

Delete ORM-model fallback branches from:

- `CapabilityLoader`
- `SkillLoader`
- `CapabilityResolver`
- `SkillResolver`
- `AdminCapabilityService`
- `AdminSkillService`
- `DashboardService`
- `WorkspaceSummaryService`

Tests must inject fake DataService clients or use DataService test fixtures instead of fake ORM models.

- [ ] **Step 2: Remove direct runtime SQL**

Run:

```bash
find backend/src -path 'backend/src/dataservice*' -prune -o -path 'backend/src/database*' -prune -o -name '*.py' -print | xargs rg -n "session\\.execute|db\\.execute|select\\("
```

Expected output after cleanup: only explicitly allowed dev/test/auth bootstrap files, or no output.

- [ ] **Step 3: Make architecture guards strict**

Remove temporary allowlists from `tests/architecture/test_dataservice_boundaries.py`.

- [ ] **Step 4: Run architecture tests**

```bash
cd backend && .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py -q
```

Expected: pass with no allowlisted runtime files.

- [ ] **Step 5: Commit**

```bash
git add backend/src backend/tests
git commit -m "refactor: remove runtime dataservice fallbacks"
```

## Task 8: Full Verification And Documentation

- [ ] **Step 1: Run backend full suite**

```bash
cd backend && .venv/bin/python -m pytest tests/ -q
```

Expected: all tests pass.

- [ ] **Step 2: Run frontend verification**

```bash
cd frontend && npm run typecheck
cd frontend && npm run lint
```

Expected: both pass.

- [ ] **Step 3: Run Docker config validation**

```bash
docker compose config --quiet
```

Expected: no output, exit code 0.

- [ ] **Step 4: Update docs**

Update:

- `docs/superpowers/specs/2026-05-21-dataservice-full-migration-overview.md`
- `docs/superpowers/plans/2026-05-20-dataservice-convergence.md`
- `docs/current/release-gate-checklist.md`

Required wording:

```markdown
Runtime gateway, worker, agents, tools, compute, and business services now use `dataservice_client` for DataService-owned reads/writes. In-process `src.dataservice.*_api` imports are confined to DataService app/domain ownership packages. Direct runtime business SQL is blocked by architecture guard.
```

- [ ] **Step 5: Commit and push**

```bash
git add docs backend
git commit -m "docs: mark dataservice runtime cutover complete"
git push
```

## Acceptance Criteria

1. `rg "from src\\.dataservice\\.[a-z_]+_api" backend/src --glob '*.py'` returns only DataService owner packages or no runtime files.
2. `rg "AsyncDataServiceClient" backend/src --glob '*.py'` shows runtime usage in gateway/services/task/agents/tools/compute.
3. Direct runtime business SQL is blocked by architecture guard.
4. `docker-compose.yml` still runs `dataservice` as its own service and gateway/worker depend on it.
5. Backend full test suite passes.
6. Frontend typecheck/lint passes.
7. Overview, convergence plan, and release gate all state the same final architecture.

