# Workspace Prism Surface Next Phase Plan

## Goal

Turn the newly canonical workspace Prism surface into a production-ready manuscript workflow: database rollout is verified, old links converge cleanly, review/commit actions are workspace-aware end to end, and QA covers the main academic writing golden paths.

## Phase 1: Migration And Data Integrity

- [ ] Run `alembic upgrade head` against a staging-like database snapshot.
- [ ] Verify legacy `llm_config.workspace_id` Prism projects are backfilled to `workspace_id` and `surface_role = primary_manuscript`.
- [ ] Add an integrity query/report for workspaces with zero or multiple primary manuscript projects.
- [ ] Decide whether `(workspace_id, surface_role)` should become a partial unique index for `primary_manuscript` after duplicates are cleaned.

## Phase 2: API Contract Hardening

- [ ] Add OpenAPI/examples for `WorkspacePrismSurfaceResponse`.
- [ ] Add route coverage for missing Prism project, non-owner access, and legacy `/latex/:projectId` non-workspace behavior.
- [ ] Confirm `LatexProjectResponse.workspace_id/surface_role` does not expose cross-user information.
- [ ] Normalize frontend and backend field names around `latex_project_id` versus `project_id`.

## Phase 3: Review And Commit Flow

- [ ] Audit all result_card producers for `prism_url` and Prism action payloads.
- [ ] Ensure all Prism review/apply/revert actions can operate from `/workspaces/:id/prism` without relying on raw `/latex/:projectId` navigation.
- [ ] Add an end-to-end test for staged file changes: generated result_card -> Prism surface -> apply selected changes -> commit to rooms.
- [ ] Validate that pending/applied file changes remain authoritative after page reload and execution refresh.

## Phase 4: Frontend Surface Polish

- [ ] Replace temporary Prism loading/error state with the shared v2 empty/error pattern.
- [ ] Add mobile checks for the Workbench / Prism switch and LaTeX editor shell.
- [ ] Confirm the shared workspace shell does not double-subscribe to streams or reload unrelated rooms during Prism editing.
- [ ] Add copy/i18n pass for `Workbench`, `Prism`, and legacy redirect status text.

## Phase 5: Operational Rollout

- [ ] Run full backend tests, frontend typecheck, frontend unit tests, and Playwright golden paths.
- [ ] Smoke test Docker startup after the environment/docker script changes.
- [ ] Prepare release notes for workspace-owned manuscript routing and legacy link compatibility.
- [ ] Monitor production logs for `/latex/:projectId` redirect misses and Prism projection fallback usage.
