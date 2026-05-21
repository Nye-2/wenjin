# Workspace Prism Surface Release Notes

Date: 2026-05-21

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
- The legacy standalone `/latex/:projectId` page route is removed instead of redirected.
- Prism loading, empty, and error states now use the v2 surface-state pattern and localized copy.

## Backend Contract Changes

- `LatexProject` has explicit `workspace_id` and `surface_role` binding fields.
- `GET /api/workspaces/{workspace_id}/prism` returns the workspace-owned Prism surface projection with `latex_project_id`, `target_files`, `file_changes`, and `applied_file_changes`.
- Workspace Prism projection also includes canonical `review_items`, `source_links`, `protected_sections`, `activity`, and `review_summary`.
- `POST /api/workspaces/{workspace_id}/prism/ensure` creates or repairs the primary manuscript binding.
- `POST /api/latex/projects/{project_id}/protected-sections` persists protected manuscript sections for workspace-owned Prism projects.
- Legacy `llm_config.metadata.file_changes` and `applied_file_changes` are migrated into canonical review/provenance/protection tables and stripped from project metadata.
- `review_items`, `provenance_links`, and `prism_protected_scopes` are the canonical persistence layer for review state, provenance, and manual protection.
- `TaskBrief.manuscript_context` carries lightweight manuscript state into execution without embedding full manuscript content.
- The database now enforces one `primary_manuscript` Prism project per workspace through a partial unique index.
- Workspace Prism integrity reporting is available through `python -m scripts.workspace_prism_integrity_report`.

## Verification

- Backend: `cd backend && .venv/bin/python -m pytest tests/ -q` -> 1934 passed.
- Frontend unit: last full rollout baseline `cd frontend && npx vitest run` -> 200 passed.
- Frontend typecheck: `cd frontend && npm run typecheck` -> passed.
- Frontend lint: `cd frontend && npm run lint` -> passed.
- Frontend build: `cd frontend && npm run build` -> passed.
- Playwright: `cd frontend && npm run test:e2e` -> 19 passed, 1 skipped.
- Docker compose config: `docker compose config --quiet` -> passed.

## Rollout Watchpoints

- Watch 404s with `Workspace Prism surface not found` or `Workspace-owned Prism project not found`.
- Watch unexpected traffic to legacy `/latex/:projectId`; it should now 404 rather than redirect.
- Run the integrity report before deploying the unique-index migration in environments with pre-existing Prism data.
- Monitor Prism file-change apply/revert errors for stale hashes or unexpected manual overwrite conflicts.
- Monitor review action activity volume to confirm apply/reject/revert events are reaching workspace activity as expected.
