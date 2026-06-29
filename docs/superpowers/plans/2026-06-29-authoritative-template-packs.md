# Authoritative Template Packs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the authoritative software copyright and CUMCM template packs, visual routing rules, `math_modeling` workspace support, and one-shot capability seeds described in `docs/superpowers/specs/2026-06-29-authoritative-template-packs-design.md`.

**Architecture:** Keep the implementation data-driven. Built-in template packs live under `backend/seed/latex_templates`, DataService bootstraps them into `latex_templates.metadata_json`, workspace defaults resolve them by workspace type, and Lead/capability runtime reads bounded metadata rather than prompt-embedding template text. Visual generation remains FigureSpec-first: evidence figures use code or structured diagram routes, optional decorative images route through configured image models only.

**Tech Stack:** Python 3.13, SQLAlchemy async, Alembic, Pydantic v2, FastAPI/DataService, YAML seed files, existing sandbox artifact review path, Next.js/TypeScript only for light preview metadata if needed.

---

## File Structure

- Modify `backend/src/database/models/latex_template.py`: add `metadata_json`.
- Create `backend/alembic/versions/081_latex_template_metadata.py`: database migration for `latex_templates.metadata_json`.
- Modify `backend/src/dataservice_client/contracts/latex.py`: expose `metadata_json` in `LatexTemplatePayload`.
- Modify `backend/src/dataservice_app/routers/latex.py`: include `metadata_json` in template API responses.
- Modify `backend/src/dataservice/domains/latex/repository.py`: add template upsert helper.
- Modify `backend/src/dataservice/domains/latex/service.py`: load `backend/seed/latex_templates/registry.yaml`, validate assets, upsert by id.
- Modify `backend/src/services/latex/paths.py`: default template root to in-repo seed assets.
- Create `backend/seed/latex_templates/registry.yaml`: authoritative template catalog.
- Create `backend/seed/latex_templates/assets/software_copyright_cn_application_pack/*`: software copyright template assets and visual profile.
- Create `backend/seed/latex_templates/assets/math_modeling_cumcm2026_paper_pack/*`: CUMCM template assets and visual profile.
- Modify `backend/src/contracts/figure_generation.py`: add evidence level, visual profile fields, screenshot/schematic types, and route validation.
- Modify `backend/tests/contracts/test_figure_generation.py`: failing tests for evidence-level and screenshot route validation.
- Modify workspace type files: `backend/src/gateway/validators/workspace.py`, `backend/src/database/models/workspace.py`, `backend/src/dataservice_client/contracts/workspace.py`, `backend/src/sandbox/workspace_layout.py`, and label maps.
- Modify `backend/src/services/workspace_latex_projects.py`: map `software_copyright` and `math_modeling` to new template ids.
- Add `backend/seed/capabilities/math_modeling/math_modeling_paper_pack.yaml`: one-shot CUMCM capability.
- Modify `backend/seed/capabilities/software_copyright/software_copyright_application_pack.yaml`: add template/visual profile extensions, visual phases, and quality gates.
- Modify capability seed tests in `backend/tests/integration/test_capability_skill_seeds.py` and `backend/tests/seed/test_capability_seeds_load.py` as needed.

## Task 1: LaTeX Template Metadata Migration And Contracts

**Files:**
- Modify: `backend/src/database/models/latex_template.py`
- Create: `backend/alembic/versions/081_latex_template_metadata.py`
- Modify: `backend/src/dataservice_client/contracts/latex.py`
- Modify: `backend/src/dataservice_app/routers/latex.py`
- Test: `backend/tests/database/test_latex_project_model_contract.py`
- Test: `backend/tests/dataservice/test_foundation.py`

- [ ] **Step 1: Write failing model/contract tests**

Add a test asserting `LatexTemplate` has a `metadata_json` column and a test asserting `LatexTemplatePayload` accepts and exposes metadata:

```python
from src.database.models.latex_template import LatexTemplate
from src.dataservice_client.contracts.latex import LatexTemplatePayload


def test_latex_template_model_has_metadata_json_column() -> None:
    assert "metadata_json" in LatexTemplate.__table__.columns
    assert LatexTemplate.__table__.columns["metadata_json"].nullable is False


def test_latex_template_payload_exposes_metadata_json() -> None:
    payload = LatexTemplatePayload(
        id="math_modeling_cumcm2026_paper_pack",
        label="数模国赛论文包",
        main_file="main.tex",
        category="math_modeling",
        featured=True,
        template_path="math_modeling_cumcm2026_paper_pack",
        metadata_json={"visual_profile": {"id": "math_modeling_cumcm_default"}},
    )
    assert payload.metadata_json["visual_profile"]["id"] == "math_modeling_cumcm_default"
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/database/test_latex_project_model_contract.py tests/dataservice/test_foundation.py -k "latex_template" -v
```

Expected: failures show missing `metadata_json`.

- [ ] **Step 3: Implement minimal metadata support**

Add `metadata_json` to the SQLAlchemy model with `JSONB`, default `{}`, and server default `"{}"`. Add the field to `LatexTemplatePayload`. Add `metadata_json` to `_template_payload()`.

- [ ] **Step 4: Add Alembic migration**

Create migration `081_latex_template_metadata.py` with revision id `081_latex_template_metadata`, down revision `080_skill_execution_strategy_defaults`, and add/drop `latex_templates.metadata_json`.

- [ ] **Step 5: Run GREEN tests**

Run the same pytest command. Expected: selected tests pass.

## Task 2: Registry-backed Template Bootstrap

**Files:**
- Create: `backend/seed/latex_templates/registry.yaml`
- Create: template asset directories under `backend/seed/latex_templates/assets/`
- Modify: `backend/src/dataservice/domains/latex/repository.py`
- Modify: `backend/src/dataservice/domains/latex/service.py`
- Modify: `backend/src/services/latex/paths.py`
- Test: `backend/tests/dataservice/test_latex_template_registry.py`

- [ ] **Step 1: Write failing bootstrap tests**

Create tests covering:

```python
async def test_registry_bootstrap_upserts_authoritative_templates_even_when_old_templates_exist(...)
async def test_registry_bootstrap_fails_when_asset_directory_missing(...)
async def test_registry_bootstrap_validates_visual_profile(...)
```

The first test should create an existing `acl` template, call `ensure_default_templates()`, and assert both `software_copyright_cn_application_pack` and `math_modeling_cumcm2026_paper_pack` exist with `metadata_json.visual_profile.id`.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/dataservice/test_latex_template_registry.py -v
```

Expected: import or assertion failures because registry bootstrap does not exist.

- [ ] **Step 3: Add registry and assets**

Create the registry and minimal but real template files from the spec. Include:

- `TEMPLATE.md`
- `manual.tex` or `main.tex`
- profile/style files
- `quality-gates.json`
- CUMCM `code/solve.py`

- [ ] **Step 4: Implement registry loader**

Implement a small loader inside `DataServiceLatexService` or a focused helper in the same domain. Use `yaml.safe_load`, validate `template_path` under configured template root, validate `visual-profile.yaml` exists and id matches metadata, and upsert by template id.

- [ ] **Step 5: Run GREEN tests**

Run the registry tests. Expected: all pass.

## Task 3: Workspace Type And Sandbox Profile

**Files:**
- Modify: `backend/src/gateway/validators/workspace.py`
- Modify: `backend/src/database/models/workspace.py`
- Modify: `backend/src/dataservice_client/contracts/workspace.py`
- Modify: `backend/src/sandbox/workspace_layout.py`
- Modify: `backend/src/services/workspace_summary_service.py`
- Test: `backend/tests/database/test_workspace_type.py`
- Test: `backend/tests/sandbox/test_workspace_layout.py`

- [ ] **Step 1: Write failing workspace tests**

Add tests asserting `math_modeling` is accepted by workspace validators/contracts and `workspace_type_profile("math_modeling")` contains `/workspace/main/main.tex`, `/workspace/scripts/solve.py`, `/workspace/outputs/figures`, and `/workspace/reports/visual-manifest.md`.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/database/test_workspace_type.py tests/sandbox/test_workspace_layout.py -k "math_modeling" -v
```

Expected: `math_modeling` is unknown.

- [ ] **Step 3: Add workspace type**

Add `MATH_MODELING = "math_modeling"` and update tuple/list constants and label maps. Add the sandbox profile using the existing common layout roots.

- [ ] **Step 4: Run GREEN tests**

Run the same pytest command. Expected: math modeling tests pass.

## Task 4: FigureSpec Evidence And Screenshot Routing

**Files:**
- Modify: `backend/src/contracts/figure_generation.py`
- Test: `backend/tests/contracts/test_figure_generation.py`
- Test: `backend/tests/agents/harness/test_figure_generation_tool.py`

- [ ] **Step 1: Write failing FigureSpec tests**

Add tests for:

```python
def test_evidence_level_rejects_llm_image() -> None: ...
def test_ui_screenshot_requires_playwright_or_uploaded_source() -> None: ...
def test_ui_screenshot_accepts_playwright_screenshot_outputs() -> None: ...
def test_python_schematic_accepts_geometric_schematic() -> None: ...
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/contracts/test_figure_generation.py -v
```

Expected: new literals/fields are rejected.

- [ ] **Step 3: Implement contract extension**

Add `EvidenceLevel`, new figure types, new strategies, fields, and validation. Keep existing tests green: data plots still require chart code; structured diagrams still require Mermaid/Graphviz/TikZ.

- [ ] **Step 4: Run GREEN tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/contracts/test_figure_generation.py tests/agents/harness/test_figure_generation_tool.py -v
```

Expected: all pass.

## Task 5: Workspace LaTeX Default Templates

**Files:**
- Modify: `backend/src/services/workspace_latex_projects.py`
- Test: `backend/tests/services/test_workspace_prism_service.py` or create `backend/tests/services/test_workspace_latex_projects.py`

- [ ] **Step 1: Write failing default-template tests**

Add tests asserting:

```python
assert WorkspaceLatexProjectService._default_template_for_workspace("software_copyright") == "software_copyright_cn_application_pack"
assert WorkspaceLatexProjectService._default_template_for_workspace("math_modeling") == "math_modeling_cumcm2026_paper_pack"
```

- [ ] **Step 2: Run tests and verify RED**

Run the targeted test. Expected: old software copyright id and missing math modeling mapping.

- [ ] **Step 3: Update mapping**

Change `_default_template_for_workspace()` only.

- [ ] **Step 4: Run GREEN tests**

Run the targeted test. Expected: pass.

## Task 6: Capability Seeds And Quality Gates

**Files:**
- Modify: `backend/seed/capabilities/software_copyright/software_copyright_application_pack.yaml`
- Create: `backend/seed/capabilities/math_modeling/math_modeling_paper_pack.yaml`
- Possibly create: `backend/seed/capabilities/math_modeling/prism_selection_optimize.yaml`
- Possibly create worker skills if existing `method-design`, `figure-engineer`, `manuscript-writer`, `format-compliance-checker`, and `review-critic` are insufficient.
- Test: `backend/tests/seed/test_capability_seeds_load.py`
- Test: `backend/tests/integration/test_capability_skill_seeds.py`

- [ ] **Step 1: Write failing seed tests**

Update expected workspace/capability counts and add assertions that:

- `math_modeling_paper_pack` exists.
- Both super workflows declare `extensions.authoritative_template_id`.
- Both super workflows declare `extensions.visual_profile_id`.
- Software copyright gates include `no_ai_generated_evidence_screenshots`.
- Math modeling gates include `evidence_figures_code_generated` and `ai_use_disclosure_or_no_ai_declaration_present`.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/seed/test_capability_seeds_load.py tests/integration/test_capability_skill_seeds.py -k "capability or workspace_specific_quality_gates or total_user_visible" -v
```

Expected: missing math modeling directory/capability and missing extensions/gates.

- [ ] **Step 3: Update software copyright capability**

Add template/visual extensions, visual planning/generation phase before drafting, and the new quality gates. Keep existing output mapping compatible.

- [ ] **Step 4: Add math modeling capability**

Create the capability with sequential phases: problem parser, modeling planner, sandbox solver, figure/table engineer, writer, supporting materials packager, compliance checker.

- [ ] **Step 5: Run GREEN tests**

Run the seed tests. Expected: all pass.

## Task 7: Screenshot Runner Route

**Files:**
- Extend existing harness or sandbox tool path only if required by Task 6 seed execution tests.
- Preferred minimal first implementation: route `ui_screenshot` FigureSpec validation and artifact registration through existing `sandbox.run_python`/`sandbox.register_artifact` without adding public user APIs.
- Test: `backend/tests/agents/harness/test_figure_generation_tool.py`

- [ ] **Step 1: Write failing screenshot artifact test**

Add a harness-level test that a screenshot artifact path under `/workspace/outputs/screenshots/software_copyright/` is accepted as reviewable and appears in generated artifacts metadata.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/harness/test_figure_generation_tool.py -k "screenshot" -v
```

Expected: screenshot route is unsupported or rejected.

- [ ] **Step 3: Implement minimal screenshot route**

Add `playwright_screenshot` to the code-strategy set only if the tool receives source code for a deterministic runner; otherwise accept uploaded/prototype screenshot artifacts through `sandbox.register_artifact`. Do not call AI image provider.

- [ ] **Step 4: Run GREEN tests**

Run the screenshot test and existing figure generation tests.

## Task 8: Frontend Preview Regression

**Files:**
- Modify only if tests show needed: `frontend/lib/workspace-result-preview.ts`
- Test: `frontend/tests/unit/lib/workspace-result-preview.test.ts`

- [ ] **Step 1: Write failing preview tests only if screenshots do not already preview**

Add a test for `/workspace/outputs/screenshots/software_copyright/screen01.png` with `mime_type: "image/png"` and `artifact_kind: "figure"` or screenshot metadata.

- [ ] **Step 2: Run frontend test**

Run:

```bash
cd frontend && npx vitest run tests/unit/lib/workspace-result-preview.test.ts
```

Expected: existing image preview support should pass without code changes; if it fails, update the preview path recognizer.

## Task 9: Verification Sweep

**Files:** no required edits unless failures reveal issues.

- [ ] **Step 1: Run backend targeted suite**

```bash
cd backend && .venv/bin/python -m pytest \
  tests/contracts/test_figure_generation.py \
  tests/dataservice/test_latex_template_registry.py \
  tests/database/test_latex_project_model_contract.py \
  tests/database/test_workspace_type.py \
  tests/sandbox/test_workspace_layout.py \
  tests/seed/test_capability_seeds_load.py \
  tests/integration/test_capability_skill_seeds.py \
  -v
```

- [ ] **Step 2: Run frontend targeted suite**

```bash
cd frontend && npx vitest run tests/unit/lib/workspace-result-preview.test.ts
```

- [ ] **Step 3: Run formatting/lint-adjacent checks if touched files require them**

Use existing project commands only:

```bash
cd frontend && npm run typecheck
```

Backend full test is expensive; run it if targeted tests reveal shared behavior risk:

```bash
cd backend && .venv/bin/python -m pytest tests/ -v
```

## Self-Review Checklist

- Every authoritative template id in the spec exists in registry and assets.
- Every visual profile id in the spec exists in template assets and registry metadata.
- `math_modeling` is accepted everywhere workspace types are enumerated.
- Evidence-level figures cannot route to `llm_image`.
- Software copyright evidence screenshots cannot route to AI image generation.
- Capability seeds remain `capability.v2` and load through existing seed tests.
- No homepage change and no template marketplace are introduced.
