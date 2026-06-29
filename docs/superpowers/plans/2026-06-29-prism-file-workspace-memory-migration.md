# Prism File Workspace Memory Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the Prism file workspace and workspace-memory refactor so generated files live in Prism, memory is one hidden backend Markdown document per workspace, and Documents/Memory legacy surfaces are removed from the default architecture.

**Architecture:** Reuse the existing DataService-owned Prism file/version tables as the canonical user-facing file workspace. Add a focused workspace-memory domain for the hidden Markdown memory document. Switch execution commit and frontend navigation to Prism without Documents-room compatibility layers, then delete/stop old `user_knowledge` and `memory_facts` runtime paths.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, Pydantic v2, DataService internal routers/client, Next.js 16, React 19, TypeScript, Zustand, Tailwind, Vitest, Pytest.

---

## File Map

- Modify `backend/src/dataservice/domains/prism/contracts.py`: add file create/upsert/read/update/restore command and projection contracts.
- Modify `backend/src/dataservice/domains/prism/repository.py`: add current-version lookup, version lookup, file lookup by workspace/path, soft-delete, and current-version restore helpers.
- Modify `backend/src/dataservice/domains/prism/service.py`: add safe path normalization, workspace primary file project ensure, upsert file, read current file, append-if-changed autosave, restore/soft-delete operations.
- Modify `backend/src/dataservice_app/routers/prism.py`: expose internal Prism file APIs.
- Modify `backend/src/dataservice_client/contracts/prism.py` and `backend/src/dataservice_client/client.py`: expose DataService client payloads and methods for the new Prism APIs.
- Create `backend/src/dataservice/domains/workspace_memory/models.py`, `contracts.py`, `repository.py`, `projection.py`, `service.py`: one hidden Markdown memory document per workspace with bounded revisions.
- Create `backend/src/dataservice/workspace_memory_api.py` and `backend/src/dataservice_app/routers/workspace_memory.py`: internal DataService memory API.
- Modify `backend/src/dataservice_app/app.py`: include the new workspace-memory router and remove old knowledge/memory routers if unused by runtime.
- Modify `backend/alembic/versions/082_workspace_memory_prism_migration.py`: create workspace-memory tables, migrate useful workspace-scoped memory into one document, delete old `user_knowledge` and `memory_facts` development data, and drop old tables when safe.
- Modify `backend/src/services/workspace_prism_service.py`: return a file-workspace surface without requiring a LaTeX adapter; add file read/update helpers; hide memory payloads from Prism surface.
- Modify `backend/src/gateway/routers/workspaces_contracts.py`, `backend/src/gateway/routers/workspaces.py`: add Prism file contracts and user-facing file content/update routes; make `latex_project_id` nullable.
- Modify `backend/src/services/user_memory_service.py`, `backend/src/services/memory_capture_service.py`, `backend/src/agents/middlewares/memory.py`, `backend/src/application/handlers/thread_turn_handler.py`: stop cross-workspace memory capture and load only the hidden workspace memory document at low frequency.
- Modify `backend/src/services/execution_commit_service.py`: commit document/figure outputs into Prism file versions, merge selected `memory_fact` outputs into workspace memory, update commit_state/undo semantics, and remove Documents-room writes.
- Modify `backend/src/dataservice/domains/rooms/*`, `backend/src/dataservice_app/routers/rooms.py`, `backend/src/gateway/routers/workspace_rooms.py`: remove default memory-fact and Documents-room operations from runtime routes.
- Modify `frontend/lib/api/types.ts`, `frontend/lib/api/workspace.ts`: add Prism file types and APIs.
- Create `frontend/app/(workbench)/workspaces/[id]/prism/PrismWorkspaceShell.tsx`: file tree, editor, preview, autosave state, and file open behavior.
- Modify `frontend/app/(workbench)/workspaces/[id]/prism/page.tsx`: render Prism workspace shell for all Prism projects, including non-LaTeX projects.
- Modify `frontend/app/(workbench)/workspaces/[id]/components/shell/WorkspaceHubDrawer.tsx` and `frontend/app/(workbench)/workspaces/[id]/page.tsx`: remove Documents from hub/type/routing and keep Memory hidden.
- Modify `frontend/lib/workspace-result-preview.ts`, `frontend/lib/execution-commit.ts`: point saved document/figure links to Prism and remove memory/document room assumptions.
- Update backend tests under `backend/tests/dataservice/`, `backend/tests/services/`, `backend/tests/gateway/routers/`, `backend/tests/agents/`.
- Update frontend tests under `frontend/tests/unit/` and `frontend/tests/e2e/`.

## Tasks

- [ ] **Task 1: Add Prism file operations in DataService.**
  - Add tests in `backend/tests/dataservice/test_prism_project_service.py` for safe path rejection, upsert by path, current-content read, append-if-hash-changed, restore previous version, and soft-delete of a commit-created file.
  - Implement Prism file commands/projections in `backend/src/dataservice/domains/prism/contracts.py`.
  - Implement repository helpers in `backend/src/dataservice/domains/prism/repository.py`.
  - Implement service methods in `backend/src/dataservice/domains/prism/service.py`.
  - Expose internal routes in `backend/src/dataservice_app/routers/prism.py`.
  - Expose client methods in `backend/src/dataservice_client/contracts/prism.py` and `backend/src/dataservice_client/client.py`.
  - Verify with `cd backend && .venv/bin/python -m pytest tests/dataservice/test_prism_project_service.py -v`.

- [ ] **Task 2: Add hidden workspace-memory domain.**
  - Add SQLAlchemy models and Pydantic contracts for `workspace_memory_documents` and `workspace_memory_revisions`.
  - Add repository/service behavior: ensure default document, get current document, rewrite document with bounded content, append revision only on hash change, merge memory facts into the canonical Markdown sections.
  - Add internal DataService router/client methods.
  - Add Alembic migration `082_workspace_memory_prism_migration.py` that creates new tables, imports workspace-scoped legacy rows where possible, deletes old `user_knowledge` and `memory_facts` data in dev, and drops old tables only when constraints allow.
  - Add tests in `backend/tests/dataservice/test_workspace_memory_domain.py`.
  - Verify with `cd backend && .venv/bin/python -m pytest tests/dataservice/test_workspace_memory_domain.py -v`.

- [ ] **Task 3: Replace runtime memory with workspace-memory only.**
  - Add `backend/src/services/workspace_memory_service.py` as the only prompt memory service; format current workspace memory as `<workspace_memory>...</workspace_memory>`.
  - Change `MemoryMiddleware.before_model` to require `workspace_id` and load workspace memory only.
  - Disable default per-turn capture in `MemoryMiddleware.after_model` and `_persist_thread_reply`; only explicit low-frequency update calls should write memory.
  - Remove old `user_knowledge` reads/writes from runtime services; delete or orphan old Knowledge routes from active app wiring.
  - Update memory tests so they assert no cross-workspace memory is loaded and no capture job is enqueued on ordinary turns.
  - Verify with `cd backend && .venv/bin/python -m pytest tests/unit/middlewares/test_memory.py tests/agents/middleware/test_memory.py tests/agents/middlewares/test_memory_middleware_cache.py -v`.

- [ ] **Task 4: Switch execution commit from Documents to Prism and workspace memory.**
  - Add tests in `backend/tests/services/test_execution_commit_service.py` for document output -> Prism file version, figure output -> Prism asset-pointer file, no `register_asset` for documents, memory_fact -> workspace memory merge, undo restore/soft-delete/skip-on-newer-edit.
  - Update commit counts/targets to include `prism`, `library`, `memory`, `decisions`, `tasks`; remove `documents`.
  - Resolve Prism paths from output metadata/name/workspace type using the spec mapping, with strict sanitizer.
  - Append Prism file versions with provenance metadata containing execution id/output id/previous version/current version.
  - Merge selected memory-like outputs through workspace-memory service and do not create `memory_facts`.
  - Update undo to restore previous Prism version or soft-delete new files, skipping when the current hash differs from the committed hash.
  - Update workspace refresh targets to remove `documents` and hidden `memory`, keeping `prism`, `library`, `decisions`, `tasks`, `runs`, `references`.
  - Verify with `cd backend && .venv/bin/python -m pytest tests/services/test_execution_commit_service.py tests/gateway/routers/test_execution_commit_router.py -v`.

- [ ] **Task 5: Remove Documents/Memory room runtime routes from default UX.**
  - Remove Documents from `WorkspaceHubDrawer` type and room list.
  - Remove `DocumentsDrawer` imports/mounting and `room=documents` parsing in workspace page.
  - Remove Memory tab/view from settings/default workspace UX; memory stays backend-only.
  - Remove frontend saved links to Documents/Memory and point Prism targets to `/workspaces/{id}/prism?file_id=...`.
  - Remove or update unit tests that assert Documents drawer visibility; replace with Prism file link assertions.
  - Verify with `cd frontend && npm run typecheck` and targeted Vitest for workspace hub/result-preview/commit.

- [ ] **Task 6: Build editable Prism workspace shell.**
  - Add `PrismWorkspaceShell.tsx` with a compact file tree, editor, Markdown preview, LaTeX/plain preview, image preview, and autosave state.
  - Add file APIs in `frontend/lib/api/workspace.ts` for `getWorkspacePrismFile` and `saveWorkspacePrismFile`.
  - Update `prism/page.tsx` to render the file workspace shell even when `latex_project_id` is null; keep LaTeX adapter affordance only for supported `.tex` workflows.
  - Autosave behavior: debounce around 1200-1800 ms, save only when local hash/content changed, preserve unsaved local content on error, retry on next edit/save tick, and show compact `已保存/保存中/保存失败` state.
  - Add frontend tests for non-LaTeX Prism render, Markdown preview, autosave no-op on unchanged content, and image preview.
  - Verify with `cd frontend && npx vitest run frontend/tests/unit/v2/prism-surface.test.tsx frontend/tests/unit/lib/execution-commit.test.ts frontend/tests/unit/lib/workspace-result-preview.test.ts`.

- [ ] **Task 7: Clean old Documents/Memory code paths and review for debt.**
  - Run `rg -n "documents|DocumentsDrawer|MemoryViewer|memory_facts|memory_fact|user_knowledge|UserKnowledge|KnowledgeService|create_knowledge_memory|list_room_memory_facts" backend/src frontend/app frontend/lib frontend/stores`.
  - Keep only historical migration/test/doc references that are intentionally non-runtime; remove active runtime imports/routes/fallbacks.
  - Run `rg -n "compat|fallback|legacy" backend/src frontend/app frontend/lib` and remove new compatibility branches introduced by this migration.
  - Update `docs/current/workspace-current-state.md` and related docs if runtime behavior changed materially.

- [ ] **Task 8: Global verification and browser smoke.**
  - Run `cd backend && .venv/bin/python -m pytest tests/ -v` unless runtime is too slow; if too slow, run all touched suites and record skipped risk.
  - Run `cd frontend && npm run typecheck`.
  - Run `cd frontend && npx vitest run`.
  - Run dev server, open current workspace in browser, verify hub has no Documents/Memory, Prism opens file tree, edit Markdown, autosave persists after refresh, execution committed document opens in Prism.
  - Fix any regressions found in the smoke.

## Self-Review

- Spec coverage: every finalized decision maps to a task: hidden single memory document (Tasks 2-3), low-frequency memory writes (Tasks 3-4), immediate deletion of old dev memory data (Task 2), hidden memory UI (Task 5), Prism full editing/autosave (Task 6), no Documents room (Tasks 4-5), and no compatibility layer cleanup (Task 7).
- Placeholder scan: no task relies on a future unspecified fallback; each task names concrete files, behaviors, and verification commands.
- Type consistency: commit targets move from `documents` to `prism`; `latex_project_id` becomes nullable; workspace memory uses `content_markdown`, `content_hash`, and monotonically increasing `revision`.
