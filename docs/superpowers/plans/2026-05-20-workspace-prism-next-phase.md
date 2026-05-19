# Workspace Prism Surface Next Phase Plan

## Goal

Turn the newly canonical workspace Prism surface into a production-ready manuscript workflow: database rollout is verified, old links converge cleanly, review/commit actions are workspace-aware end to end, and QA covers the main academic writing golden paths.

## Phase 1: Migration And Data Integrity

- [x] Run `alembic upgrade head` against the local development database.
- [x] Verify legacy `llm_config.workspace_id` Prism projects are backfilled to `workspace_id` and `surface_role = primary_manuscript` in the local database.
- [x] Add an integrity query/report for workspaces with zero or multiple primary manuscript projects.
- [x] Decide whether `(workspace_id, surface_role)` should become a partial unique index for `primary_manuscript` after duplicates are cleaned.

Decision: keep the current non-unique `(workspace_id, surface_role)` index for this phase. Add a partial unique index only after production/staging integrity reports show no duplicate primary manuscripts. Local report on 2026-05-20 found no duplicates and multiple E2E/debug workspaces with zero primary manuscripts.

Verification:

```bash
cd backend && .venv/bin/python -m alembic upgrade head
cd backend && .venv/bin/python -m alembic current
cd backend && .venv/bin/python -m scripts.workspace_prism_integrity_report --json --no-fail
```

## Phase 2: API Contract Hardening

- [x] Add OpenAPI/examples for `WorkspacePrismSurfaceResponse`.
- [x] Add route coverage for missing Prism project, non-owner access, and legacy `/latex/:projectId` non-workspace behavior.
- [x] Confirm `LatexProjectResponse.workspace_id/surface_role` does not expose cross-user information.
- [ ] Normalize frontend and backend field names around `latex_project_id` versus `project_id`.

Note: `LatexProjectResponse` is still returned through `LatexProjectService.get_owned`, so workspace binding fields remain owner-scoped.

## Phase 3: Review And Commit Flow

- [x] Audit all result_card producers for `prism_url` and Prism action payloads.
- [x] Ensure all Prism review/apply/revert actions can operate from `/workspaces/:id/prism` without relying on raw `/latex/:projectId` navigation.
- [x] Add an end-to-end test for staged file changes: generated result_card -> Prism surface -> apply selected changes -> commit to rooms.
- [x] Validate that pending/applied file changes remain authoritative after page reload and execution refresh.

Progress on 2026-05-20: result card producers now derive Prism actions from `latex_project_id` and pending `file_changes`; workspace-scoped Prism actions override legacy `/latex/:projectId` URLs. Frontend `preview_prism_changes` routes to `/workspaces/:id/prism?focus=file_changes`, reusing the editor's pending-write focus behavior. Backend projection tests continue to cover pending/applied metadata refresh after apply/revert.

E2E closure on 2026-05-20: `frontend/tests/e2e/iteration.spec.ts` now covers result_card Prism preview navigation, workspace Prism pending-write apply, and the final commit of selected room outputs.

## Phase 4: Frontend Surface Polish

- [x] Replace temporary Prism loading/error state with the shared v2 empty/error pattern.
- [x] Add mobile checks for the Workbench / Prism switch and LaTeX editor shell.
- [x] Confirm the shared workspace shell does not double-subscribe to streams or reload unrelated rooms during Prism editing.
- [x] Add copy/i18n pass for `Workbench`, `Prism`, and legacy redirect status text.

Progress on 2026-05-20: Prism loading, error, and empty states now use the shared v2 surface-state component. Surface switch and legacy `/latex/:projectId` redirect copy use workspace-surface i18n keys with test fallbacks. A mobile Playwright check covers `/workspaces/:id/prism`, verifies the Workbench / Prism switch and LaTeX editor remain visible, confirms the workspace event stream is present, and ensures Prism editing does not request room drawer endpoints. Existing `useWorkspaceEventStream` unit coverage remains the single-owner guard for workspace SSE.

## Phase 5: Operational Rollout

- [ ] Run full backend tests, frontend typecheck, frontend unit tests, and Playwright golden paths.
- [ ] Smoke test Docker startup after the environment/docker script changes.
- [ ] Prepare release notes for workspace-owned manuscript routing and legacy link compatibility.
- [ ] Monitor production logs for `/latex/:projectId` redirect misses and Prism projection fallback usage.
