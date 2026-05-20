# Workspace Prism Surface Release Notes

Date: 2026-05-20

## Summary

Workspace-owned Prism is now the canonical manuscript surface for Wenjin workspaces. Writing results, pending file changes, review actions, and legacy LaTeX project links converge on `/workspaces/:workspaceId/prism`.

## User-Facing Changes

- Workbench now exposes a persistent Workbench / Prism surface switch.
- Workspace manuscript editing opens at `/workspaces/:id/prism`.
- Result cards with Prism file changes route to `/workspaces/:id/prism?focus=file_changes`.
- Pending file changes must be reviewed and applied in Prism before they change the manuscript.
- Legacy workspace-owned `/latex/:projectId` links redirect to the workspace Prism surface.
- Prism loading, empty, error, and legacy redirect states now use the v2 surface-state pattern and localized copy.

## Backend Contract Changes

- `LatexProject` has explicit `workspace_id` and `surface_role` binding fields.
- `GET /api/workspaces/{workspace_id}/prism` returns the workspace-owned Prism surface projection with `latex_project_id`, `target_files`, `file_changes`, and `applied_file_changes`.
- `POST /api/workspaces/{workspace_id}/prism/ensure` creates or repairs the primary manuscript binding.
- Legacy `llm_config.workspace_id` projects are still discoverable and normalized into explicit bindings.
- Workspace Prism integrity reporting is available through `python -m scripts.workspace_prism_integrity_report`.

## Verification

- Backend: `cd backend && .venv/bin/python -m pytest tests/ -q` -> 1844 passed.
- Frontend unit: `cd frontend && npm test` -> 193 passed.
- Frontend typecheck: `cd frontend && npm run typecheck` -> passed.
- Playwright: `cd frontend && npx playwright test tests/e2e/iteration.spec.ts tests/e2e/prism-surface.spec.ts --project=chromium` -> 5 passed.
- Docker compose config: `docker compose config --quiet` -> passed.

## Rollout Watchpoints

- Watch 404s with `Workspace Prism surface not found` or `Workspace-owned Prism project not found`.
- Watch unexpected traffic to legacy `/latex/:projectId` after the redirect rollout.
- Run the integrity report before enabling a partial unique index on `(workspace_id, surface_role)`.
- Monitor Prism file-change apply/revert errors for stale hashes or unexpected manual overwrite conflicts.
