# Workspace LaTeX Projectization Plan

## Background

`/latex` is now a standalone LaTeX editor with project CRUD, file tree, file operations, upload, local compile, and PDF preview.

Current workspace writing features still mostly stop at one of these layers:

- semantic artifacts such as `framework_outline`, `paper_draft`, `thesis_chapter`, `proposal`, `patent_outline`
- compile-time payloads containing `latex_content` and `bib_content`
- a `LATEX_PROJECT` artifact that still behaves more like a serialized document blob than a real project directory

This is not enough for the final product direction. The last-mile output of long-form writing should not be a single `.tex` string. It should be a complete LaTeX project folder that the user can open, inspect, edit, compile, and continue iterating on.

## Product Positioning

The correct product role split is:

- Workspace features are the upstream generators and editors of research content.
- `/latex` is the canonical document IDE for final assembly, layout, compilation, and submission-facing iteration.
- `LATEX_PROJECT` should become the bridge between the two.

This means:

- Features should not try to become mini-editors.
- `/latex` should not try to replace semantic feature outputs.
- The stable handoff object is a reusable LaTeX project, not just raw generated prose.

## Core Decision

For long-form outputs, Wenjin should standardize on:

- semantic artifacts for reasoning and traceability
- one linked persisted LaTeX project for document assembly and final delivery

The linked LaTeX project should be a real directory tree under the new `/latex` storage system, not a transient compile sandbox and not a single JSON field.

## Current State By Workspace Type

### Thesis

Current chain:

- `thesis_writing` creates chapter-level artifacts such as `THESIS_CHAPTER`
- `figure_generation` creates figure artifacts
- `compile_export` assembles chapters into `latex_content` and compiles
- `LATEX_PROJECT` is already referenced in `thesis_feature_service`, but still treated as a blob payload with keys like `main_tex` / `bib_tex`

Gap:

- compile/export can reuse prior LaTeX text, but not a persisted project directory with sections, assets, bib files, and editable structure

### SCI

Current chain:

- `framework_outline` produces outline-level structure
- `writing` produces section drafts as `PAPER_DRAFT`
- `literature_review`, `paper_analysis`, `peer_review` produce supporting artifacts

Gap:

- no canonical promoted target project
- no persistent section file mapping
- no direct path from section drafts to an editable LaTeX project directory

### Proposal

Current chain:

- `proposal_outline`
- `background_research`
- `experiment_design`

Gap:

- outputs are structured sections and planning payloads, but not a real proposal manuscript project

### Patent

Current chain:

- `patent_outline`
- `prior_art_search`

Gap:

- good structure and claims drafts exist, but no final editable patent document project

### Software Copyright

Current chain:

- `copyright_materials`
- `technical_description`

Gap:

- may not always need LaTeX first, but if product wants unified final-document editing, it should still be able to materialize a document project

## Target Architecture

### 1. Linked Project Bridge

Introduce a stable bridge from workspace to LaTeX project:

- a workspace can have zero or one primary linked LaTeX project per output line
- artifact content for `LATEX_PROJECT` should include `latex_project_id`
- workspace features should read and update that linked project instead of emitting only `latex_content`

Recommended persisted shape in artifact content:

```json
{
  "schema_version": "v2",
  "latex_project_id": "uuid",
  "workspace_id": "uuid",
  "workspace_type": "thesis",
  "template": "thesis_default",
  "main_file": "main.tex",
  "section_map": {
    "introduction": "sections/introduction.tex",
    "methodology": "sections/methodology.tex"
  },
  "asset_map": {
    "figure:123": "assets/figures/figure-123.png"
  },
  "source_artifact_ids": ["..."],
  "sync_status": "synced"
}
```

### 2. New Service Layer

Add a reusable service, for example:

- `src/services/workspace_latex_projects.py`

Responsibilities:

- create or load the linked LaTeX project for a workspace
- choose template by workspace type
- map semantic artifacts into section files
- map generated figures/tables into `assets/`
- write `references.bib`
- keep `LATEX_PROJECT` artifact metadata in sync
- trigger compile using the existing `/latex` project service

This service should be the only place that knows how workspace artifacts become real LaTeX files.

### 3. Template Strategy By Workspace Type

Recommended default templates:

- `thesis`: thesis-style template, multi-section structure
- `sci`: conference/journal style project template
- `proposal`: proposal report template
- `patent`: patent report/specification template
- `software_copyright`: technical document template

Rule:

- workspace type picks the initial project structure
- feature outputs fill or patch files inside that structure

### 4. File Mapping Strategy

Do not append every feature result into one giant `main.tex`.

Instead:

- `main.tex` is a stable shell
- sections live in `sections/*.tex`
- bibliography lives in `references.bib`
- assets live in `assets/figures`, `assets/tables`, `assets/generated`
- feature metadata stays in artifact content and optional project metadata files

## Feature Cooperation Model

### Thesis

- `thesis_writing`: writes chapter files into `sections/`
- `figure_generation`: writes outputs into `assets/figures/`
- `opening_research`: can seed abstract/introduction/background sections
- `compile_export`: becomes a sync + compile entry, not the only assembler

### SCI

- `framework_outline`: creates skeleton `main.tex` + section placeholders
- `writing`: writes targeted section files, one section at a time
- `literature_review`: updates `sections/related_work.tex`
- `peer_review`: should not overwrite files directly; it should emit review artifacts plus optional patch suggestions
- final compile should happen on the linked project

### Proposal

- `proposal_outline`: creates proposal project structure
- `background_research`: writes background and significance sections
- `experiment_design`: writes methodology / schedule / feasibility sections

### Patent

- `patent_outline`: creates `spec.tex`, `claims.tex`, optional appendix files
- `prior_art_search`: updates comparison appendix and references

### Software Copyright

- `technical_description`: writes technical description sections
- `copyright_materials`: fills forms/checklists or generated appendix files

## Implementation Phases

### Phase A: Complete `/latex` Editor Usability

Status:

- file tree, create file/folder, rename, delete, upload to current directory, drag reorder, compile, preview

Remaining:

- inline folder/file creation in tree
- richer context menu
- directory drag-and-drop upload
- breadcrumb + active folder indicator

### Phase B: Workspace-to-LaTeX Bridge

Tasks:

- add `workspace_latex_projects` service
- define v2 `LATEX_PROJECT` artifact schema
- add helper to create or get linked LaTeX project for workspace
- define workspace-type template mapping

### Phase C: Thesis Migration

Tasks:

- make `compile_export` reuse linked project
- make `thesis_writing` write into project section files
- make `figure_generation` sync files into project assets

### Phase D: SCI Migration

Tasks:

- convert `framework_outline` into project bootstrapper
- convert `writing` to file-targeted section generation
- route final full-paper assembly to linked project instead of standalone text blob

### Phase E: Proposal / Patent / Copyright

Tasks:

- define per-workspace templates
- wire section outputs into project directories
- add compile/export entry wherever document output is the final artifact

## Todo

### Editor Todo

- add inline create-in-tree flows
- add breadcrumb and selected-folder status
- add richer preview for PDF/image/code assets
- add cross-folder move support after same-folder reorder stabilizes

### Projectization Todo

- expand `workspace_latex_projects` service to all long-form workspace types
- keep one primary linked latex project per workspace in v1 via `llm_config.role=primary`
- define v2 `LATEX_PROJECT` artifact content with `latex_project_id`
- thesis migration to linked project
- sci migration to linked project
- proposal migration to linked project
- patent migration to linked project
- software copyright migration to linked project
- compile/export should always target a real project directory

### Current Status

- `/latex` editor has CRUD, file tree, rename, delete, reorder, upload to selected folder, directory upload, compile, and preview.
- `workspace_latex_projects` exists and is already wired into thesis.
- SCI `framework_outline` and `writing` already sync to a linked project skeleton and section files.
- Proposal outline/background/experiment outputs already sync to a linked project skeleton.
- Patent outline skeleton already syncs to a linked project.
- Bridge writes now have first-pass conflict protection: if the user edits a managed file in `/latex`, workspace sync skips overwrite and records `sync_conflicts`.
- Software copyright is still pending.

## Guardrails

- Do not let each feature invent its own file layout.
- Do not let compile/export remain the only place that knows how to assemble a paper.
- Do not overwrite user-edited LaTeX files blindly from workspace features.
- Prefer section-level sync and explicit conflict handling.
- Keep semantic artifacts as the source of reasoning truth, and LaTeX project as the source of delivery truth.

## Recommendation

The next correct move is:

1. finish `/latex` into a reliable document IDE
2. introduce the workspace-to-project bridge service
3. migrate `thesis` first
4. migrate `sci` second
5. then generalize to proposal/patent

This order matches real user value and minimizes architectural drift.
