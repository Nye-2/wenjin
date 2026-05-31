# DataService Client Workspace/Catalog Convergence Plan

> **For agentic workers:** Use superpowers:executing-plans and TDD. Track each step with this checklist.

**Goal:** Finish the remaining DataService client line-count target by moving workspace/template/rooms APIs and catalog/agent-template/admin-log APIs out of `backend/src/dataservice_client/client.py`, reducing the client shell below 1500 lines while preserving `AsyncDataServiceClient` as the public import.

**Architecture:** `AsyncDataServiceClient` remains the HTTP transport shell plus common lifecycle methods. Domain methods live on focused mixins loaded through multiple inheritance. `catalog_client.py` owns capability/skill/agent-template/catalog admin log methods. `workspace_client.py` owns workspace templates, workspace room helpers, workspaces, and workspace settings.

## Tasks

- [x] Add architecture guard requiring `catalog_client.py`, `workspace_client.py`, mixin inheritance, no catalog/workspace methods in `client.py`, and `client.py <1500` lines.
- [x] Verify the guard fails before implementation.
- [x] Create `CatalogDataServiceClientMixin`.
- [x] Create `WorkspaceDataServiceClientMixin`.
- [x] Remove moved imports and methods from `client.py`; add mixins to `AsyncDataServiceClient`.
- [x] Run focused backend tests and ruff.
- [x] Run code-review-graph incremental update and change detection.
- [x] Commit and push.

## Verification

```bash
cd backend && .venv/bin/python -m pytest tests/architecture/test_dataservice_boundaries.py::test_dataservice_client_workspace_catalog_apis_live_in_dedicated_mixins -q
cd backend && .venv/bin/python -m pytest tests/dataservice/test_foundation.py tests/architecture/test_dataservice_boundaries.py::test_dataservice_client_domain_apis_live_in_dedicated_mixins tests/architecture/test_dataservice_boundaries.py::test_dataservice_client_workspace_catalog_apis_live_in_dedicated_mixins -q
cd backend && .venv/bin/ruff check src/dataservice_client/client.py src/dataservice_client/catalog_client.py src/dataservice_client/workspace_client.py tests/architecture/test_dataservice_boundaries.py
wc -l backend/src/dataservice_client/client.py
```

## Self-Review

- Contract check: no method signature changes; callers still import and instantiate `AsyncDataServiceClient`.
- Risk check: pure method relocation can break imports; mitigated by ruff, architecture guard, and DataService client foundation tests.
