# API Surface Map

Generated: 2026-03-16
Updated: 2026-03-16 (Phase 2 complete — features router slimmed)
Status: Living document, updated with each Phase PR

## Route Inventory

### Auth (`gateway/routers/auth.py`) - Active

| Method | Path | Auth | Owner Isolation | Status |
|--------|------|------|-----------------|--------|
| POST | `/api/auth/send-verification-code` | None | N/A | Active |
| POST | `/api/auth/register` | None | N/A | Active |
| POST | `/api/auth/login` | None | N/A | Active |
| POST | `/api/auth/refresh` | None | N/A | Active |
| GET | `/api/auth/me` | Bearer | N/A | Active |

### Workspaces (`gateway/routers/workspaces.py`) - Active

| Method | Path | Auth | Owner Isolation | Status |
|--------|------|------|-----------------|--------|
| POST | `/api/workspaces/` | Bearer | user_id binding | Active |
| GET | `/api/workspaces/` | Bearer | user_id filter | Active |
| GET | `/api/workspaces/{id}` | Bearer | user_id check | Active |
| PUT | `/api/workspaces/{id}` | Bearer | user_id check | Active |
| DELETE | `/api/workspaces/{id}` | Bearer | user_id check | Active |

### Features (`gateway/routers/features.py`) - Active (Phase 2: thin adapter)

Orchestration extracted to `application/handlers/feature_execution_handler.py`.
Router is now a pure HTTP adapter — no business service imports.

| Method | Path | Auth | Owner Isolation | Status |
|--------|------|------|-----------------|--------|
| GET | `/api/workspaces/{id}/features` | Bearer | workspace owner check | Active |
| POST | `/api/workspaces/{id}/features/{fid}/execute` | Bearer | workspace owner check (via handler) | Active |

### Tasks (`gateway/routers/tasks.py`) - Active

| Method | Path | Auth | Owner Isolation | Status |
|--------|------|------|-----------------|--------|
| GET | `/api/tasks/{id}/status` | Bearer | user_id check | Active |
| POST | `/api/tasks/{id}/cancel` | Bearer | user_id check | Active |
| GET | `/api/tasks/` | Bearer | user_id filter | Active |

### Papers (`gateway/routers/papers.py`) - Active

| Method | Path | Auth | Owner Isolation | Status |
|--------|------|------|-----------------|--------|
| POST | `/api/papers/` | Bearer | Needs Phase 2 | Active |
| GET | `/api/papers/` | Bearer | Needs Phase 2 | Active |
| GET | `/api/papers/{id}` | Bearer | N/A | Active |
| PUT | `/api/papers/{id}` | Bearer | Needs Phase 2 | Active |
| DELETE | `/api/papers/{id}` | Bearer | Needs Phase 2 | Active |
| POST | `/api/papers/{id}/extract` | Bearer | Needs Phase 2 | Active |
| GET | `/api/papers/{id}/sections` | Bearer | N/A | Active |
| POST | `/api/papers/search` | Bearer | N/A | Active |

### Artifacts (`gateway/routers/artifacts.py`) - Active

| Method | Path | Auth | Owner Isolation | Status |
|--------|------|------|-----------------|--------|
| POST | `/api/artifacts/` | Bearer | Needs Phase 2 | Active |
| GET | `/api/artifacts/` | Bearer | Needs Phase 2 | Active |
| GET | `/api/artifacts/{id}` | Bearer | Needs Phase 2 | Active |
| PUT | `/api/artifacts/{id}` | Bearer | Needs Phase 2 | Active |
| DELETE | `/api/artifacts/{id}` | Bearer | Needs Phase 2 | Active |
| GET | `/api/artifacts/{id}/lineage` | Bearer | Needs Phase 2 | Active |

### Academic (`gateway/routers/academic.py`) - Deprecated

| Method | Path | Auth | Owner Isolation | Status |
|--------|------|------|-----------------|--------|
| POST | `/api/papers` | Bearer | N/A | Deprecated (Sunset: 2026-05-01) |
| POST | `/api/papers/upload` | Bearer | Needs Phase 2 | Deprecated (Sunset: 2026-05-01) |
| GET | `/api/papers/search` | Bearer | N/A | Deprecated (Sunset: 2026-05-01) |
| GET | `/api/workspaces/{id}/artifacts` | Bearer | Needs Phase 2 | Deprecated (Sunset: 2026-05-01) |
| POST | `/api/workspaces/{id}/artifacts` | Bearer | Needs Phase 2 | Deprecated (Sunset: 2026-05-01) |
| GET | `/api/workspaces/{id}/artifacts/{aid}` | Bearer | Partial (workspace_id match) | Deprecated (Sunset: 2026-05-01) |
| GET | `/api/workspaces/{id}/artifacts/{aid}/lineage` | Bearer | Needs Phase 2 | Deprecated (Sunset: 2026-05-01) |

### Thesis (`thesis/api.py`) - Deprecated

| Method | Path | Auth | Owner Isolation | Status |
|--------|------|------|-----------------|--------|
| POST | `/api/thesis/generate` | Bearer | user_id in task | Deprecated (Sunset: 2026-05-01) |
| GET | `/api/thesis/status/{id}` | Bearer | user_id check | Deprecated (Sunset: 2026-05-01) |
| DELETE | `/api/thesis/cancel/{id}` | Bearer | user_id check | Deprecated (Sunset: 2026-05-01) |
| GET | `/api/thesis/preview/{id}` | Bearer | user_id check | Deprecated (Sunset: 2026-05-01) |
| GET | `/api/thesis/list` | Bearer | user_id filter | Deprecated (Sunset: 2026-05-01) |

## Summary

- **Total routes**: 35
- **Missing auth**: 0 routes (Phase 1 complete)
- **Missing owner isolation**: 14 routes (Phase 2 target)
- **Deprecated**: 12 routes (academic: 7, thesis: 5) — Sunset: 2026-05-01
