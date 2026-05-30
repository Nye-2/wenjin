# Workspace Prism Surface Release Notes

Date: 2026-05-30

## Summary

Workspace-owned Prism is now the canonical manuscript surface for Wenjin workspaces. Writing results, pending file changes, and review actions converge on `/workspaces/:workspaceId/prism`.

## User-Facing Changes

- Workbench now exposes a persistent Workbench / Prism surface switch.
- Workspace manuscript editing opens at `/workspaces/:id/prism`.
- Opening a workspace Prism route now repairs a missing primary binding once via the ensure endpoint before surfacing an error.
- Result cards with Prism file changes route to `/workspaces/:id/prism?focus=file_changes&review_item_id=...&logical_key=...`.
- Workbench result cards, CompletedView, chat result blocks, and Prism Changes use the shared Prism review list.
- Prism context rail now surfaces sources, recent activity, decisions, memory context, and protected sections tied to the manuscript.
- Source links can deep-link back to Library / Documents detail views.
- Pending file changes must be reviewed and applied in Prism before they change the manuscript.
- Prism review actions support apply, reject, revert, and manual section protection from the same contract.
- SCI `research_question_to_paper` and thesis `idea_to_thesis_manuscript` now stage writer output as Prism review items instead of silent runtime text.
- The legacy standalone `/latex/:projectId` page route is removed instead of redirected.
- Prism loading, empty, and error states now use the v2 surface-state pattern and localized copy.

## Backend Contract Changes

- `LatexProject` has explicit `workspace_id` and `surface_role` binding fields.
- `GET /api/workspaces/{workspace_id}/prism` returns the workspace-owned Prism surface projection with `latex_project_id`, `target_files`, `file_changes`, and `applied_file_changes`.
- Workspace Prism projection also includes canonical `review_items`, `source_links`, `protected_sections`, `activity`, and `review_summary`.
- `POST /api/workspaces/{workspace_id}/prism/ensure` creates or repairs the primary manuscript binding.
- Prism editor/file-change/compile/protect APIs are exposed only through `/api/prism/latex-adapter/*`.
- `POST /api/prism/latex-adapter/projects/{project_id}/protected-sections` persists protected manuscript sections for workspace-owned Prism projects.
- Legacy `/api/latex/*` routes are removed rather than redirected or proxied.
- Legacy `llm_config.metadata.file_changes` and `applied_file_changes` are migrated into canonical review/provenance/protection tables and stripped from project metadata.
- `review_items`, `provenance_links`, and `prism_protected_scopes` are the canonical persistence layer for review state, provenance, and manual protection.
- Prism adapter routers and LaTeX/WorkspacePrism runtime services access persistence through DataService client injection, not runtime DB sessions.
- `TaskBrief.manuscript_context` carries lightweight manuscript state into execution without embedding full manuscript content.
- Lead runtime stages `kind: prism_file_change` output declarations into DataService-backed `review_items`; `OutputMappingResolver` excludes those declarations from ordinary room outputs.
- DataService review batch creation flushes batch/items before action logs so Postgres FK constraints remain valid in the standalone DataService deployment.
- The database now enforces one `primary_manuscript` Prism project per workspace through a partial unique index.
- Workspace Prism integrity reporting is available through `python -m scripts.workspace_prism_integrity_report`.

## Verification

- Backend targeted Prism writing review: `cd backend && .venv/bin/python -m pytest tests/dataservice/test_review_batch_service.py tests/dataservice/test_foundation.py::test_dataservice_client_prism_review_contract_methods tests/agents/lead_agent/v2/test_output_mapping.py tests/agents/lead_agent/v2/test_runtime.py tests/services/test_prism_review_workflow_gate.py tests/services/test_workspace_prism_service.py tests/gateway/routers/test_workspace_rooms_router.py::TestRunsRoom::test_list_runs_happy -v` -> 53 passed.
- Frontend Playwright targeted Prism review: `cd frontend && npm run test:e2e -- iteration.spec.ts prism-surface.spec.ts --project=chromium` -> 5 passed.
- Docker + Browser smoke: local-build gateway / worker / dataservice / bootstrap-admin healthy; runtime-staged Prism review item opened in `/workspaces/{workspace_id}/prism`, previewed, applied, and API returned `pending_count=0`, `applied_count=1`.
- Runtime boundary target: `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/gateway/routers/test_latex_upload_limits.py tests/gateway/routers/test_latex_workspace_route_convergence.py tests/services/test_latex_hardening.py tests/services/test_workspace_prism_service.py tests/services/test_prism_review_workflow_gate.py tests/services/test_reference_writing_workflow_gate.py tests/gateway/routers/test_workspace_prism.py tests/compute/test_projection_service.py tests/architecture/test_dataservice_boundaries.py -q` -> 88 passed.
- Frontend Prism adapter API: `cd frontend && npm run test -- tests/unit/lib/prism-review-api.test.ts` -> 5 passed.
- Backend full suite: `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/ -q` -> 2005 passed.
- Frontend typecheck/build: `cd frontend && npm run typecheck` -> passed; `cd frontend && npm run build` -> passed.
- Backend full rollout baseline: `cd backend && .venv/bin/python -m pytest tests/ -q` -> 1938 passed.
- Frontend unit: last full rollout baseline `cd frontend && npx vitest run` -> 200 passed.
- Frontend typecheck: `cd frontend && npm run typecheck` -> passed.
- Frontend lint: `cd frontend && npm run lint` -> passed.
- Frontend build: `cd frontend && npm run build` -> passed.
- Playwright: `cd frontend && npm run test:e2e` -> 19 passed, 1 skipped.
- Docker compose config: `docker compose config --quiet` -> passed.

## Rollout Watchpoints

- Watch 404s with `Workspace Prism surface not found` or `Workspace-owned Prism project not found`.
- Watch unexpected traffic to legacy `/latex/:projectId` or `/api/latex/*`; it should 404 rather than redirect.
- Run the integrity report before deploying the unique-index migration in environments with pre-existing Prism data.
- Monitor Prism file-change apply/revert errors for stale hashes or unexpected manual overwrite conflicts.
- Monitor review action activity volume to confirm apply/reject/revert events are reaching workspace activity as expected.
