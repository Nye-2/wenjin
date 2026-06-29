# Prism File Workspace and Workspace Memory Refactor

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
| Documents room | Index/provenance over Prism files | Yes, lightweight | It should not be a second independent document store. |
| Workspace memory | `workspace_memory` backend domain | No, initially hidden | One Markdown blob per workspace with bounded revisions. |
| Cross-workspace user memory | Retired | No | Do not read or write global `user_knowledge` at runtime. |
| Per-fact workspace memory list | Retired | No | Do not keep a long visible list of facts. |

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

`ExecutionCommitService` currently commits document outputs as DataService assets for the Documents room. That makes sense for a room drawer, but after removing the product/artifact tab, documents also need to live in Prism as real files. If both stores hold independent content, users will not know which copy is canonical.

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

### Documents Room Pointer

Documents room should become an index over Prism files for generated documents.

For newly committed generated documents, use a pointer shape instead of duplicating full content:

```json
{
  "storage_path": "prism://<prism_file_id>",
  "metadata_json": {
    "kind": "draft",
    "prism_file_id": "<file-id>",
    "prism_path": "docs/software-copyright/application.md",
    "prism_version_id": "<version-id>",
    "source_execution_id": "<execution-id>",
    "source_output_id": "<output-id>"
  }
}
```

The Documents drawer can list these records, but opening them should deep-link to Prism instead of rendering an independent document copy.

Older asset-backed documents can remain historical data, but new execution commits should write Prism first and then create a lightweight Documents pointer.

### Workspace Memory

Introduce a dedicated DataService domain, for example:

```text
workspace_memory_documents
workspace_memory_revisions
```

Recommended `workspace_memory_documents` fields:

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

Recommended `workspace_memory_revisions` fields:

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
  -> create Documents room pointer
  -> persist commit_state with prism targets
  -> publish workspace.refresh including prism/documents
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
- Documents room pointer created by the commit should still be deleted during undo.

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

The agent prompt should receive this memory as a bounded block, for example:

```xml
<workspace_memory>
...
</workspace_memory>
```

Do not inject old `user_knowledge` or individual `memory_facts` after the refactor.

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

Empty state:

- Do not say "还没有绑定写作项目".
- Say the workspace file area is ready and generated files will appear after a workflow writes results.

### Documents Room

Documents room should not pretend Prism-backed documents are independent copies.

For `storage_path = prism://...`:

- Show document title and path.
- Primary action opens `/workspaces/{workspace_id}/prism?file=<file_id>`.
- Preview may call Prism file content API, but it must label the file as Prism-backed.

### Memory UI

Do not add a visible Memory tab/drawer in the first implementation.

Settings should not show a user-editable memory list. If debugging is needed later, add an admin/developer-only diagnostics surface, not a default user room.

## Backend Refactor Requirements

### Retire Cross-Workspace Runtime Memory

Stop using these as runtime prompt memory:

- `user_knowledge`
- `KnowledgeService` as a cross-workspace memory facade
- global active memory queries

The user can still have account settings later, but they are not agent memory.

### Retire Memory Fact Commit Path

Do not materialize `memory_fact` outputs as many individual room records.

Options for outputs that currently declare `kind = "memory_fact"`:

1. Preferred: change output mapping so durable context updates become a workspace memory rewrite candidate.
2. Acceptable transition inside the same release: collect selected memory-like outputs and merge them into the single workspace memory document during commit, without creating `memory_facts`.

The final runtime should not create new `memory_facts` for normal workspace operation.

### Keep Decisions Separate

Decisions remain separate from memory. A decision is a structured fact with a key/value and may affect workflow routing. Workspace memory may summarize important decisions, but it is not the decision database.

## Migration Strategy

### Prism

No destructive migration is required for existing Prism tables. Add service/API operations around existing records.

For existing Documents assets:

- Leave historical assets readable.
- New commits should use Prism files plus Documents pointers.
- Optional future migration can create Prism files for historical inline documents.

### Memory

Create the new workspace memory tables.

One-time migration:

1. For each workspace, collect active `memory_facts`.
2. Collect `user_knowledge` rows where `workspace_context = workspace_id`.
3. Render a single concise Markdown memory document.
4. Insert `workspace_memory_documents` row and revision 1.
5. Stop runtime reads/writes from `user_knowledge` and `memory_facts`.

Cross-workspace `user_knowledge` rows should not be injected into any workspace. They can be archived or left unused until a cleanup migration drops the old table, but runtime must not read them.

After runtime and tests are updated, remove user-facing memory room routes/components and clean old memory tests around fact-list behavior.

## Testing Requirements

### Backend

Add or update tests for:

- Prism file path sanitizer rejects unsafe paths.
- Prism file upsert appends versions instead of duplicating files.
- Gateway surface returns `prism_files` even without `latex_project_id`.
- Prism file content API returns Markdown inline content.
- Prism file content API returns image asset pointer for image files.
- Execution commit writes accepted document output to Prism and creates a Documents pointer.
- Execution undo restores previous Prism version or soft-deletes a new file.
- Execution undo skips Prism rollback if file changed after commit.
- Memory update creates or rewrites exactly one workspace memory document.
- Runtime memory context reads workspace memory only.
- Cross-workspace `user_knowledge` is not read.
- `memory_fact` outputs no longer create fact-list records.

### Frontend

Add or update tests for:

- Prism route renders file workspace shell without a LaTeX project.
- File tree displays nested Markdown, TeX, BibTeX, and image paths.
- Selecting a Markdown file loads and renders preview.
- Selecting an image file renders real preview from asset URL.
- Selecting a TeX file still supports the existing LaTeX editor when adapter data exists.
- Empty Prism state no longer says "还没有绑定写作项目".
- Documents drawer opens Prism-backed documents in Prism.
- Memory drawer/settings entry is not shown in default workspace UX.

### Browser Smoke

Run through:

1. Software copyright workspace: generate/accept document output, confirm files appear under `docs/software-copyright`.
2. Math modeling workspace: generate/accept paper output, confirm `paper/main.tex`, `paper/figures`, and Markdown notes preview correctly.
3. Undo accepted run, confirm Prism versions roll back or file disappears when it was new.
4. Refresh browser, confirm Prism file tree persists.
5. Confirm no Memory room is visible.

## Release Criteria

The change is complete when:

- Prism can open as a file workspace without a LaTeX adapter.
- Accepted generated documents are saved as Prism files with stable paths.
- Documents room no longer owns duplicate generated document content for new commits.
- Images can be represented as Prism files and previewed.
- One workspace has at most one current workspace memory document.
- Runtime memory injection uses only the workspace memory document.
- Cross-workspace user memory is not used by Chat Agent, Lead Agent, or subagents.
- Memory facts are not exposed as a default user-facing room.
- Tests cover Prism file read/write, commit, undo, and workspace memory rewrite behavior.

## Spec Self-Review

- Placeholder scan: no placeholder sections remain.
- Internal consistency: Prism owns user files; workspace memory is backend-only and excluded from Prism.
- Scope check: this is one coherent refactor because commit, Prism, Documents, and memory all meet at workspace persistence and user-facing file semantics.
- Ambiguity check: memory is explicitly workspace-scoped only; cross-workspace memory is retired from runtime.
