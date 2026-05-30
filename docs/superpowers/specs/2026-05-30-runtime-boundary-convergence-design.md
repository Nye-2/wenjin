# Runtime Boundary Convergence Design

Date: 2026-05-30
Status: Implemented on master

Implementation commits:

- `86f10cef` — auth/account runtime now uses Account DataService subject/client boundary.
- `c57e5efd` — artifact runtime naming and client contracts are WorkspaceArtifact / Asset DataService.
- `4f93cba3` — LaTeX public API moved behind Prism adapter routes; adapter runtime services no longer carry DB sessions.

## Goal

Converge the remaining historical runtime boundaries into the current Wenjin architecture:

1. Account/auth runtime uses Account DataService projections, not database sessions or ORM user models.
2. Workspace artifact payloads use canonical Asset terminology and DataService contracts, not `legacy_artifact` names.
3. LaTeX is no longer a standalone public product API. It becomes the Prism manuscript adapter and all old `/latex/*` routes are removed without compatibility redirects or fallback.

The migration is intentionally clean. Old public entry points, alias classes, dual-read code, and compatibility facades should be deleted when each replacement is in place.

## Non-Negotiable Constraints

- No compatibility layer for removed `/latex/*` routes.
- No runtime service in these domains may accept `AsyncSession` only to pass through to DataService.
- No runtime service outside `database`, `dataservice`, or `dataservice_app` may import migrated ORM model classes or enum classes for these domains.
- Router code may adapt HTTP protocol and auth only; it must not own domain orchestration.
- DataService remains the persistence SSOT.
- Prism remains the only user-facing manuscript surface.

## Target Architecture

### Account/Auth

Current issue: authentication dependencies still depend on `get_db`, annotate `src.database.User`, and token helpers accept `db` even though reads/writes already go through Account DataService.

Target:

- Add an application-facing auth projection, `AccountAuthSubject`.
- `get_current_user`, `get_current_user_optional`, and `get_current_admin` return `AccountAuthSubject`.
- `services/auth.py` token helpers accept only DataService client injection and token/user data.
- `UserService` has no `db` constructor parameter and returns Account DataService projections.
- Runtime imports of `AsyncSession`, `get_db`, and migrated `User` ORM in auth boundaries are guarded.

`AccountAuthSubject` must expose the fields already used by routers:

- `id`
- `email`
- `name`
- `role`
- `is_active`
- `is_superuser`
- `credits`
- `created_at`
- `last_login`
- refresh-token fields where token validation needs them

### Workspace Asset / Artifact

Current issue: artifact persistence is behind AssetDataService, but the runtime and internal DataService client still expose `LegacyArtifact*` contracts and `/internal/v1/assets/legacy-artifacts`.

Target:

- Rename DataService contracts to `WorkspaceArtifactCreatePayload`, `WorkspaceArtifactUpdatePayload`, and `WorkspaceArtifactPayload`.
- Rename client methods to `create_workspace_artifact`, `list_workspace_artifacts`, `get_workspace_artifact`, `update_workspace_artifact`, `delete_workspace_artifact`, `count_workspace_artifacts`, `find_latest_workspace_artifact`, `list_workspace_artifact_versions`, and `get_workspace_artifact_lineage`.
- Rename internal routes from `/internal/v1/assets/legacy-artifacts...` to `/internal/v1/assets/artifacts...`.
- Rename the runtime facade to `WorkspaceArtifactService` or keep `ArtifactService` only if it is a product noun, not a compatibility facade. It must not accept `db`.
- The physical database table can remain `artifacts` during this stage if it is fully owned behind AssetDataService. The runtime surface must not contain `legacy_artifact` naming.

### Prism LaTeX Adapter

Current issue: old `/latex/*` API routes still exist and many routers construct LaTeX services with `AsyncSession = Depends(get_db)`. The service implementations mostly call `LatexDataService`, but the public surface still reads like a standalone LaTeX product.

Target:

- Delete or retire old `/latex/*` routers.
- Introduce Prism adapter routes under `/prism/latex-adapter/*`.
- Update frontend API client calls from `/latex/*` to `/prism/latex-adapter/*`.
- Keep `/workspaces/{workspace_id}/prism` as the user-facing manuscript entry.
- `LatexProjectService`, `LatexTemplateService`, `LatexCompileService`, `WorkspaceLatexProjectService`, and `WorkspacePrismService` must not accept or store `db`.
- LaTeX compile/history/project/template persistence uses `LatexDataService` client only.
- File-system operations remain in the LaTeX adapter service because they are not database persistence.

The new adapter API should cover existing editor needs:

- project list/create/get/update/delete
- project file tree/file read/write/folder/rename/delete/order
- upload/upload archive
- compile/history PDF/SyncTeX/blob
- feedback list/update/rewrite/map
- templates
- file-change preview/apply/discard/revert/protected sections

Routes should be mechanically equivalent except for the prefix and any naming that exposes standalone LaTeX as a product.

## Data Flow

### Auth request flow

```text
HTTP Authorization header
  -> get_current_user
  -> verify_access_token
  -> UserService(dataservice).get_by_id
  -> AccountAuthSubject
  -> router/service authorization checks
```

No DB session is opened by auth dependencies.

### Artifact flow

```text
runtime artifact call
  -> WorkspaceArtifactService
  -> AsyncDataServiceClient.workspace_artifact method
  -> DataService /internal/v1/assets/artifacts
  -> WorkspaceAssetService artifact-owned persistence
```

No runtime call uses `legacy_artifact` names.

### Prism manuscript flow

```text
frontend Prism editor
  -> /api/prism/latex-adapter/*
  -> backend Prism LaTeX adapter router
  -> LaTeX adapter services
  -> DataService Latex/Prism/Review/Source APIs
  -> filesystem or compile worker where needed
```

No frontend or backend runtime calls `/latex/*`.

## Error Handling

- Removed `/latex/*` routes should return 404 through normal router absence. Do not add explicit redirect or tombstone handlers.
- Auth failures keep existing HTTP semantics: 401 for missing/invalid/disabled users, 403 for non-admin.
- Artifact/asset not found remains `None` at service level and existing HTTP 404 at router level.
- Prism adapter compile errors keep existing compile-history semantics.

## Testing Strategy

### Architecture Guards

Add or extend guards to fail if:

- auth runtime imports `AsyncSession`, `get_db`, or `src.database.User`
- account/credit/artifact/latex/prism adapter runtime services accept `db` constructor arguments
- runtime code references `legacy_artifact` outside DataService database migration notes
- frontend API calls `/latex/`
- backend routers register `/latex`

### Targeted Backend Tests

- auth dependency tests with fake DataService user projection
- auth router registration/login/refresh/logout tests after removing `db` token helper parameters
- artifact service and router tests after canonical rename
- LaTeX adapter route tests for old prefix removal and new prefix behavior
- Prism workspace tests to ensure editor/project/compile flows still use the adapter

### Frontend Tests

- API client tests assert Prism adapter prefix
- Prism editor tests assert no `/latex/*` calls
- Workspace Prism route tests remain unchanged for user-facing route

### Full Verification

- `cd backend && env -u ALL_PROXY -u all_proxy -u HTTP_PROXY -u http_proxy -u HTTPS_PROXY -u https_proxy .venv/bin/python -m pytest tests/ -q`
- `cd frontend && npm run typecheck`
- `cd frontend && npm run build`

## Rollout

This is a direct migration on `master`:

1. Auth/account boundary first.
2. Artifact/asset naming next.
3. Prism LaTeX adapter route migration last.
4. Update current architecture docs after each domain is closed.
5. Push only after full backend/frontend verification is green.

## Out Of Scope

- Changing the physical `artifacts` table name if runtime/DataService contracts are already canonical.
- Rewriting the LaTeX file editor UI design.
- Replacing the LaTeX compile engine.
- Keeping old `/latex/*` clients alive.
