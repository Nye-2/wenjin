# Prism File Workspace and Workspace Memory Refactor

Status: Partially superseded for runtime topology by `docs/superpowers/specs/mission-runtime-overview.md` and `docs/superpowers/specs/mission-runtime/`.

Note: Prism and workspace memory product boundaries remain useful. ExecutionCommitService, ReviewBatch, execution provenance, and Lead Agent references must be migrated to MissionReviewItem, MissionCommit, mission provenance, and WorkspaceAgent / MissionRuntime boundaries.

## Goal

Refactor Wenjin's workspace persistence model around two clear surfaces:

1. **WenjinPrism** is the user-facing file workspace for generated Markdown, LaTeX, BibTeX, and image files.
2. **Workspace Memory** is one backend-maintained Markdown memory document per workspace, not a Prism file, not a user-facing room, and not cross-workspace global memory.

The product outcome should feel simple:

- Users open Prism and see a file tree like a lightweight VSCode workspace.
- Generated documents have stable file paths and previews.
- The system remembers workspace context through one concise memory document in the background.
- There is no visible "Memory" room, no artifact tab duplication, and no cross-workspace memory leak.

## Product Decision

Use a split model:

| Concern | Canonical home | User visible? | Notes |
| --- | --- | --- | --- |
| Markdown deliverables | Prism file tree | Yes | Open, preview, edit later. |
| LaTeX deliverables | Prism file tree + LaTeX adapter where available | Yes | Existing LaTeX shell remains available for `.tex`. |
| Images / screenshots / figures | Prism file tree, binary content via asset pointer | Yes | Preview in Prism. |
| Documents room | Retired from default UX | No | Prism file tree replaces Documents as the user-facing document surface. |
| Workspace memory | `workspace_memory` backend domain | No, initially hidden | One Markdown blob per workspace with bounded revisions. |
| Cross-workspace user memory | Runtime retired | No | Do not read or write global `user_knowledge` in agent runtime. |
| Per-fact workspace memory list | Runtime retired | No | Normal execution must not create new `memory_facts`. |

## Review Decisions

This spec intentionally makes the following defaults explicit so implementation does not branch:

1. **Prism is the canonical active file workspace.** New generated Markdown, LaTeX, BibTeX, and image outputs must be written to Prism files first.
2. **Documents room is retired.** New generated documents are opened from Prism, not from a separate Documents room, index, asset, or pointer. Commit provenance is recorded in execution commit state and Prism file versions.
3. **Workspace memory is one backend Markdown document.** Revisions are audit history only; the current memory document is the only runtime memory source.
4. **No cross-workspace memory injection.** Runtime prompt context must not read global `user_knowledge`.
5. **No normal memory fact fan-out.** If existing outputs still produce `memory_fact`, commit merges the selected facts into the one workspace memory document and does not create `memory_facts` rows.
6. **No memory in Prism.** Prism's tree has no `/memory` directory, no `workspace_memory.md`, and no hidden system memory file.
7. **Workspace memory updates are low-frequency.** The MVP only rewrites memory after finalized intake specs, accepted execution commits, or explicit user corrections.
8. **Development migration deletes old memory data.** In the current development environment, old `user_knowledge` and `memory_facts` data should be migrated into workspace memory where relevant and then removed, not left as unused runtime-adjacent state.
9. **Prism text files support full editing and autosave in the first implementation.** Markdown, TeX, and BibTeX files must support direct editing, debounced autosave, versioning, and undo-safe commit semantics.

## Current Problems

### Prism Is Too LaTeX-Centric

Current `frontend/app/(workbench)/workspaces/[id]/prism/page.tsx` only renders `LatexEditorShell` when `surface.latex_project_id` exists. If a workflow creates Markdown documents or images, Prism can still show "还没有绑定写作项目", even though the workspace may have real generated files.

DataService already has a Prism project/document/file/version model:

- `prism_projects`
- `prism_documents`
- `prism_files`
- `prism_file_versions`

But gateway and frontend do not expose these records as the primary workspace file surface.

### Documents And Prism Are Becoming Duplicates

`ExecutionCommitService` currently commits document outputs as DataService assets for the Documents room. That old room behavior conflicts with the new Prism file workspace. If both stores hold independent content or both appear as user-facing document surfaces, users will not know which copy is canonical.

### Memory Has Too Many Forms

The codebase currently has several memory concepts:

- `user_knowledge`: cross-workspace user memory.
- `memory_facts`: workspace room facts.
- Memory room UI and settings surfaces.
- Memory injection into agent prompts.

The desired direction is simpler: no cross-workspace system memory, no long fact list, and no user-facing memory room. Each workspace should have one concise, dynamically maintained memory document.

## Non-Goals

- Do not put memory files under Prism.
- Do not expose memory in the Prism file tree.
- Do not keep a user-facing Memory drawer in the default workspace UX.
- Do not keep a user-facing Documents drawer in the default workspace UX after Prism file tree is ready.
- Do not build a full generic IDE.
- Do not add arbitrary binary file management in the first implementation.
- Do not restore the removed artifact/product tab.
- Do not introduce a second execution stream, second workspace router, or bypass the Chat Agent -> Lead Agent pipeline.
- Do not use cross-workspace user memory as a runtime fallback.

## Target Information Architecture

### Prism File Tree

Prism owns user-facing deliverable files. The first supported file families are:

```text
.md
.markdown
.tex
.bib
.png
.jpg
.jpeg
.webp
.svg
```

Canonical directory layout:

```text
/
  README.md
  docs/
    software-copyright/
      application.md
      user-manual.md
      material-checklist.md
    math-modeling/
      paper-draft.md
      modeling-notes.md
  paper/
    main.tex
    sections/
    figures/
    refs.bib
  assets/
    images/
      software-copyright/
      math-modeling/
```

There must be no `/memory` directory in Prism.

Prism should scaffold `README.md` only as a user-facing workspace guide. It must not contain system memory or hidden prompt context.

### Workspace Memory Document

Workspace memory is a backend document bound to `workspace_id`.

It is conceptually a Markdown file, but it is not stored in Prism and not shown in the user file tree.

Recommended content shape:

```markdown
# Workspace Memory

## Project Context
- Stable description of what this workspace is trying to accomplish.

## User Preferences
- Stable preferences that matter for future work in this workspace.

## Working Constraints
- Constraints the agents should respect.

## Decisions To Preserve
- Durable choices that should not be repeatedly re-asked.

## Open Questions
- Still unresolved questions that affect execution.
```

The memory document should be short. Target length is 1,500 to 3,000 Chinese characters, with a hard backend limit around 8,000 characters to prevent prompt bloat.

## Data Model

### Prism Files

Keep using the existing Prism aggregate:

- Project: workspace-owned primary file workspace.
- Document: logical grouping.
- File: path, role, mime type, current version pointer.
- File version: immutable inline text or asset pointer.

Add missing operations around the existing model:

- Upsert file by workspace + normalized path.
- Append file version.
- Read current file version.
- Restore previous file version for undo when safe.
- Soft-delete file when undoing a commit-created file with no previous version.

The primary Prism project should support a non-LaTeX file workspace mode. A workspace may have:

- `adapter_kind = "workspace_files"` and no LaTeX adapter.
- `adapter_kind = "latex"` with a LaTeX adapter ref.

Frontend must render the file workspace in both cases.

If a workspace already has a LaTeX adapter, file-workspace APIs must reuse that Prism project and must not replace or detach the LaTeX adapter metadata. The file tree is a capability of the Prism surface, not a competing adapter.

### Documents Room Retirement

Documents room should not remain a default user-facing room. Prism replaces it as the document browsing and editing surface.

New execution commits must not create `WorkspaceAsset` document records, `storage_path=prism://...` pointers, or any other Documents-room surrogate for generated documents. The workspace hub should not show a Documents room entry after this refactor.

Execution provenance and undo data should live in `commit_state.prism[]` and Prism file-version metadata. If old asset-backed documents exist in the development database, migration may import them into Prism and then delete the old document asset rows. No compatibility read path should remain in the default runtime.

The write path must be idempotent by execution id and output id so retrying the commit appends no duplicate content version unless the content hash changed.

### Workspace Memory

Introduce a dedicated DataService domain:

```text
workspace_memory_documents
workspace_memory_revisions
```

`workspace_memory_documents` fields:

```text
id
workspace_id unique
content_markdown
content_hash
revision
updated_by
source_execution_id nullable
source_thread_id nullable
metadata_json
created_at
updated_at
```

`workspace_memory_revisions` fields:

```text
id
workspace_id
document_id
revision
content_markdown
content_hash
update_reason
source_execution_id nullable
source_thread_id nullable
created_by
created_at
```

The product still has "one memory file" because only the current Markdown content is the runtime source of truth. Revisions are backend audit/history, not user-facing memory items.

Do not use `user_knowledge` for runtime memory after this refactor. Do not create new `memory_facts` for normal execution outputs after this refactor.

Revision retention should be bounded. Keep the latest 20 revisions per workspace by default, plus any revision referenced by an active execution commit state. Older revisions can be hard-deleted by a maintenance job because the current Markdown document remains the runtime source of truth.

Because this is a development environment migration, old cross-workspace `user_knowledge` rows and old per-fact `memory_facts` rows should be deleted after successful workspace-memory migration. No compatibility read path should remain.

## Path Rules

Prism paths are workspace-relative and must pass a strict sanitizer:

- No absolute paths.
- No `..`.
- No empty segments.
- No backslash normalization surprises.
- No hidden system directories such as `.wenjin`.
- Only supported extensions in the first release.
- File names should be slugged but readable.

Default path resolver:

| Workspace type | Output hint | Prism path |
| --- | --- | --- |
| `software_copyright` | application form material | `docs/software-copyright/application.md` |
| `software_copyright` | user manual | `docs/software-copyright/user-manual.md` |
| `software_copyright` | checklist | `docs/software-copyright/material-checklist.md` |
| `software_copyright` | screenshot/image | `assets/images/software-copyright/<slug>.<ext>` |
| `math_modeling` | Markdown paper draft | `docs/math-modeling/paper-draft.md` |
| `math_modeling` | LaTeX main paper | `paper/main.tex` |
| `math_modeling` | BibTeX | `paper/refs.bib` |
| `math_modeling` | figure | `paper/figures/<slug>.<ext>` |
| other workspace types | Markdown document | `docs/<doc-kind-or-slug>.md` |
| other workspace types | LaTeX file | `paper/<slug>.tex` |

If an output provides a safe explicit `prism_path`, use it. Otherwise use the resolver above.

## Runtime Data Flow

### Commit Generated Documents

When the user accepts document outputs from a completed execution:

```text
TaskReport.outputs[]
  -> ExecutionCommitService selection
  -> resolve Prism path
  -> create/upsert Prism file
  -> append Prism file version
  -> persist commit_state with prism targets
  -> publish workspace.refresh including prism
```

Commit should not report success if the Prism file write fails. Otherwise the user may think a document was saved while the canonical file is missing.

### Undo Generated Documents

Commit state must record Prism targets:

```json
{
  "prism": [
    {
      "output_id": "output-1",
      "file_id": "file-1",
      "path": "docs/math-modeling/paper-draft.md",
      "version_id": "version-3",
      "previous_version_id": "version-2"
    }
  ]
}
```

Undo rules:

- If the current file version is still `version_id`, restore `previous_version_id`.
- If no previous version exists, soft-delete the file.
- If the file has changed since commit, do not overwrite it. Mark undo as skipped for that Prism target.
- Undo should not touch a Documents room because new commits no longer create Documents records.

Undo response should expose skipped Prism targets in `commit_state.revert_skipped.prism[]` so the UI can explain that a newer file edit was preserved.

### Apply Prism Review Items

Existing `prism_file_change` review/apply flow remains for manuscript changes. It should operate on Prism files and LaTeX adapter files where applicable.

This spec does not remove the review-first flow. It adds direct committed files for accepted document outputs and keeps review items for generated manuscript edits that need user apply/reject decisions.

### Update Workspace Memory

Memory update should be a rewrite of the single workspace memory document, not an append-only fact insertion.

Recommended flow:

```text
chat turn / execution completion
  -> gather bounded workspace context
  -> load current workspace memory markdown
  -> generate candidate rewritten memory markdown
  -> validate size, sections, sensitive data filters
  -> save new revision only if content hash changed
```

Important rules:

- The memory update is workspace-scoped only.
- Never write cross-workspace global memory.
- Do not store secrets, API keys, credentials, personal contact details, or payment identifiers.
- Do not store transient run logs or raw model output.
- Prefer stable preferences, project context, constraints, and durable decisions.
- Keep one concise current Markdown document.

MVP update triggers:

1. **Intake spec launched:** merge the finalized super-workflow spec facts into workspace memory when execution starts from that spec.
2. **Execution commit:** merge accepted durable outputs, decisions, and user-approved constraints into workspace memory.
3. **Explicit user correction:** if the user says a stable preference or context should be remembered for this workspace, rewrite workspace memory.

Do not rewrite memory after every assistant turn or every draft spec edit. That would create churn, cost, and noisy revisions.

The agent prompt should receive this memory as a bounded block, for example:

```xml
<workspace_memory>
...
</workspace_memory>
```

Do not inject old `user_knowledge` or individual `memory_facts` after the refactor.

The memory rewrite service should treat the current memory as the base document and produce a full replacement document, not a patch. It must validate required headings, character budget, and sensitive-data filters before saving. If the generated candidate removes all useful prior context or violates the schema, keep the previous memory and log a skipped update.

## Gateway/API Requirements

### Prism

Extend workspace Prism API:

```text
POST /api/workspaces/{workspace_id}/prism/ensure
GET  /api/workspaces/{workspace_id}/prism
GET  /api/workspaces/{workspace_id}/prism/files/{file_id}
```

`GET /prism` should include:

```json
{
  "workspace_id": "ws-1",
  "prism_project_id": "project-1",
  "prism_documents": [],
  "prism_files": [],
  "latex_project_id": "latex-1 or null",
  "surface_role": "primary_manuscript",
  "url": "/workspaces/ws-1/prism"
}
```

`GET /prism/files/{file_id}` should return:

```json
{
  "file": {},
  "current_version": {},
  "content_inline": "# Markdown...",
  "content_asset_id": null,
  "asset_url": null
}
```

For binary image files, return `content_asset_id` and a signed/servable asset URL, not inline bytes.

### Workspace Memory

Workspace memory should be internal/backend-facing first.

Recommended internal DataService endpoints:

```text
GET /internal/v1/workspace-memory/workspaces/{workspace_id}
PUT /internal/v1/workspace-memory/workspaces/{workspace_id}
GET /internal/v1/workspace-memory/workspaces/{workspace_id}/revisions
```

Gateway should not expose user-facing memory routes in the first implementation. Runtime services can read/write through DataService client methods.

Gateway may add an admin/developer diagnostics endpoint later, but that endpoint must not be part of the default workspace UI and must not be used by agent runtime.

## Frontend Requirements

### Prism Workspace Shell

Replace the current LaTeX-only Prism route shell with a file workspace shell:

```text
WorkspaceChrome
  -> PrismWorkspaceShell
       left: file tree
       center: preview/editor surface
       right/top: context rail and review status
```

Rendering rules:

- `.md` and `.markdown`: Markdown source/preview toggle, default preview.
- `.tex` and `.bib`: source preview; if a LaTeX adapter exists and the selected file is part of the manuscript, expose the existing LaTeX editor shell path.
- Images: real image preview, filename, dimensions when available, path for copy/reference.
- Unsupported file: metadata-only empty state.

Interaction rules:

- File selection must be represented in the URL, for example `/workspaces/{workspace_id}/prism?file=<file_id>`.
- Browser refresh must restore the selected file.
- Mobile should collapse the file tree into a drawer; desktop should keep the tree visible.
- Use Lucide icons or the existing icon set for file actions; do not use emoji icons.
- Do not add duplicate "保存" buttons on both sides. Markdown, TeX, and BibTeX files must support direct editing with debounced autosave.
- Autosave should append a Prism file version only after the content hash changes and the debounce window settles.
- The editor must show compact save state such as "正在保存", "已保存", or "保存失败，可重试"; it must not require the user to understand internal version ids.
- Autosave failures must keep local editor content intact and offer retry.

Empty state:

- Do not say "还没有绑定写作项目".
- Say the workspace file area is ready and generated files will appear after a workflow writes results.

### Documents Room

Documents room should be removed from the default workspace hub/navigation after Prism file tree is ready.

Historical document rows should be migrated into Prism or deleted in the development cleanup. The default user workspace should not show a separate Documents drawer once this migration is complete.

### Memory UI

Do not add a visible Memory tab/drawer in the first implementation.

Settings should not show a user-editable memory list. If debugging is needed later, add an admin/developer-only diagnostics surface, not a default user room.

## Backend Refactor Requirements

### Retire Cross-Workspace Runtime Memory

Stop using these as runtime prompt memory:

- `user_knowledge`
- `KnowledgeService` as a cross-workspace memory facade
- global active memory queries

Account-level product settings may exist outside this refactor, but they are not agent memory and must not be injected as workspace memory.

### Retire Memory Fact Commit Path

Do not materialize `memory_fact` outputs as many individual room records.

Outputs that currently declare `kind = "memory_fact"` should be handled in two phases:

1. First implementation: `ExecutionCommitService` collects selected memory-like outputs and merges them into the single workspace memory document without creating `memory_facts`.
2. Follow-up cleanup: output mapping should stop emitting normal `memory_fact` outputs and should instead emit workspace memory update candidates or rely on the memory rewrite trigger after commit.

The final runtime should not create new `memory_facts` for normal workspace operation.

### Keep Decisions Separate

Decisions remain separate from memory. A decision is a structured fact with a key/value and may affect workflow routing. Workspace memory may summarize important decisions, but it is not the decision database.

## Migration Strategy

### Prism

No destructive migration is required for existing Prism tables. Add service/API operations around existing records.

For existing Documents assets:

- Migrate useful historical inline documents into Prism files when practical.
- Delete old document asset rows in the development cleanup after migration.
- New commits must not create Documents assets or Prism pointer assets.

### Memory

Create the new workspace memory tables.

One-time development migration:

1. For each workspace, collect active `memory_facts`.
2. Collect `user_knowledge` rows where `workspace_context = workspace_id`.
3. Render a single concise Markdown memory document.
4. Insert `workspace_memory_documents` row and revision 1.
5. Delete migrated `memory_facts`.
6. Delete `user_knowledge` rows, including cross-workspace global rows, because this development environment does not need to preserve old global memory.
7. Stop runtime reads/writes from `user_knowledge` and `memory_facts`.

Cross-workspace `user_knowledge` rows should not be injected into any workspace and should be removed in this migration. No compatibility layer should keep reading them.

After runtime and tests are updated, remove user-facing memory room routes/components and clean old memory tests around fact-list behavior.

Migration must be idempotent. If a workspace already has a `workspace_memory_documents` row, migration should skip it unless a force flag is explicitly supplied for an admin maintenance command.

## Implementation Slices

### Slice 1: Prism File Surface

- Expose `prism_documents`, `prism_files`, and file content through gateway.
- Render Prism as a file workspace even without a LaTeX adapter.
- Keep existing LaTeX editor behavior for `.tex` projects.

### Slice 2: Commit To Prism

- Write accepted generated document outputs to Prism files.
- Remove default Documents room user surface and route new document opening through Prism.
- Record Prism target versions in commit state.
- Implement conservative undo.

### Slice 3: Workspace Memory Domain

- Add `workspace_memory_documents` and `workspace_memory_revisions`.
- Add runtime service and DataService client methods.
- Migrate workspace-scoped old memory facts into one memory document.
- Delete old `user_knowledge` and `memory_facts` data after migration.
- Stop runtime prompt injection from `user_knowledge` and `memory_facts`.

### Slice 4: UX Cleanup

- Remove Memory from default workspace UI.
- Remove Documents from default workspace UI after Prism file tree is available.
- Browser smoke the software copyright and math modeling flows.

## Testing Requirements

### Backend

Add or update tests for:

- Prism file path sanitizer rejects unsafe paths.
- Prism file upsert appends versions instead of duplicating files.
- Gateway surface returns `prism_files` even without `latex_project_id`.
- Prism file content API returns Markdown inline content.
- Prism file content API returns image asset pointer for image files.
- Execution commit writes accepted document output to Prism and does not create a second user-visible document copy.
- Execution undo restores previous Prism version or soft-deletes a new file.
- Execution undo skips Prism rollback if file changed after commit.
- Memory update creates or rewrites exactly one workspace memory document.
- Runtime memory context reads workspace memory only.
- Cross-workspace `user_knowledge` is not read.
- Old `user_knowledge` and `memory_facts` rows are removed by development migration.
- `memory_fact` outputs no longer create fact-list records.
- Prism text autosave appends versions only when content hash changes.

### Frontend

Add or update tests for:

- Prism route renders file workspace shell without a LaTeX project.
- File tree displays nested Markdown, TeX, BibTeX, and image paths.
- Selecting a Markdown file loads and renders preview.
- Selecting an image file renders real preview from asset URL.
- Selecting a text file supports editing and autosave.
- Selecting a TeX file still supports the existing LaTeX editor when adapter data exists.
- Empty Prism state no longer says "还没有绑定写作项目".
- Documents drawer is not shown in default workspace UX.
- Memory drawer/settings entry is not shown in default workspace UX.

### Browser Smoke

Run through:

1. Software copyright workspace: generate/accept document output, confirm files appear under `docs/software-copyright`.
2. Math modeling workspace: generate/accept paper output, confirm `paper/main.tex`, `paper/figures`, and Markdown notes preview correctly.
3. Undo accepted run, confirm Prism versions roll back or file disappears when it was new.
4. Refresh browser, confirm Prism file tree persists.
5. Edit a Markdown file, wait for autosave, refresh browser, and confirm the edit persists.
6. Confirm no Documents or Memory room is visible.

## Release Criteria

The change is complete when:

- Prism can open as a file workspace without a LaTeX adapter.
- Accepted generated documents are saved as Prism files with stable paths.
- Documents room is not visible in the default workspace UX and no longer owns generated document content.
- Images can be represented as Prism files and previewed.
- One workspace has at most one current workspace memory document.
- Runtime memory injection uses only the workspace memory document.
- Cross-workspace user memory is not used by Chat Agent, Lead Agent, or subagents.
- Old development `user_knowledge` and `memory_facts` data has been deleted or dropped after migration.
- Memory facts are not exposed as a default user-facing room.
- Markdown, TeX, and BibTeX files support direct editing and autosave.
- Tests cover Prism file read/write, commit, undo, and workspace memory rewrite behavior.

## Spec Self-Review

- Placeholder scan: no placeholder sections remain.
- Internal consistency: Prism owns user files; workspace memory is backend-only and excluded from Prism.
- Scope check: this is one coherent refactor because commit, Prism, Documents, and memory all meet at workspace persistence and user-facing file semantics.
- Ambiguity check: memory is explicitly workspace-scoped only; cross-workspace memory is retired and deleted in the development migration. Documents is removed from default UX. Prism text editing and autosave are required in the first implementation.
