# Authoritative Template Packs for Software Copyright and CUMCM

## Goal

Wenjin should ship exactly one built-in authoritative template pack for each of the two priority vertical workspaces:

- `software_copyright`: China software copyright application material pack.
- `math_modeling`: CUMCM / High Education Press Cup mathematical modeling contest paper pack.

The product should not expose a template marketplace, competing template versions, or user choice between multiple system templates for these two verticals. Runtime, capability seeds, and future agents should reference only these built-in template ids unless the user explicitly uploads a workspace-specific override later.

## Product Decision

Use a single authoritative template pack per vertical as the system default:

| Workspace | Template id | User-facing promise |
| --- | --- | --- |
| `software_copyright` | `software_copyright_cn_application_pack` | Input a software name, generate application-form field material, software manual, source/document deposit guide, and submission checklist. |
| `math_modeling` | `math_modeling_cumcm2026_paper_pack` | Upload or paste a contest problem, generate the CUMCM-format paper, reproducible code scaffold, supporting-materials manifest, and AI-use disclosure. |

The template packs are canonical implementation assets, not optional examples. Capability prompts may mention the template id and template contract, but must not duplicate the full template text in role prompts.

Visible primary capabilities:

| Workspace | Capability id | Role |
| --- | --- | --- |
| `software_copyright` | `software_copyright_application_pack` | Upgrade existing capability into the one-shot material package, including diagrams and screenshots. |
| `math_modeling` | `math_modeling_paper_pack` | New one-shot CUMCM paper and supporting-materials package. |

## Research Review And Direction

The two priority workflows should not compete with general AI workbench products by being "another chat that can write documents." They should compete on regulated one-shot depth:

- The user gives the smallest viable input.
- Wenjin expands it into a complete, reviewable material package.
- Evidence-like visuals are generated from code, structured definitions, or real rendered prototypes.
- AI image generation is reserved for optional non-evidentiary visuals.
- The generated package can still be refined through chat and Prism feedback after the one-shot run.

This means each vertical capability should behave like a specialized production line, not like a generic agent choosing tools freely at every turn.

Recommended product shape:

- Keep exactly one visible super workflow per new vertical outcome.
- Keep the existing hidden `prism_selection_optimize` follow-up path for chat/Prism refinement.
- Fold specialized sub-capabilities such as `software_architecture_diagrams` into the one-shot material package as internal stages or artifact follow-up routes.
- Do not expose template choices, image-engine choices, or Canva choices in the primary user path.

## Source Consolidation

### Software Copyright

Authoritative rules come from official and quasi-official registration guidance:

- National Copyright Administration PDF: [Computer Software Copyright Registration Measures](https://www.ncac.gov.cn/xxfb/flfg/bmgz/202410/P020241015604759788122.pdf).
- Beijing government service guide for software copyright preliminary registration review: [北京市政务服务事项](https://banshi.beijing.gov.cn/pubtask/task/1/110000000000/3e283672-76be-4c8c-98e8-0bebe9bd06bf.html?locationCode=110000000000).

Reference-only sources used to shape the practical fields and material order:

- East China / university office templates such as SEU and CUG software copyright application forms and instructions.
- GitHub reference package [AlexanderZhou01/China-software-copyright](https://github.com/AlexanderZhou01/China-software-copyright), structure only because license is unclear.
- MIT-licensed LaTeX manual template [EmpyreanHYR/copyright-of-computer-software_latex_template](https://github.com/EmpyreanHYR/copyright-of-computer-software_latex_template), usable as a structural reference but not copied verbatim unless license text is preserved.

Canonical software copyright rules to encode:

- The official application form itself is not generated. Wenjin generates application-form field material for the user to paste into the official system.
- Registration material includes application form, software identification material, and related proof documents.
- Identification material includes source program and one type of software document.
- Source program and document usually use the first and last consecutive 30 pages; if the whole program or document is under 60 pages, submit the whole material.
- Source pages should satisfy the line-count convention; document pages should satisfy the document line-count convention unless pages contain figures.
- Software name and version must remain exactly consistent across application fields, manual, source deposit material, headers, and checklist.
- Ownership, identity, cooperation, commissioned development, inheritance/transfer, and authorization proof must be explicitly flagged for user confirmation.

### Mathematical Modeling

Authoritative rules come from CUMCM official pages:

- [CUMCM paper format specification, 2026 revision](https://www.cmathc.org.cn/mcm/tz/407.html).
- [CUMCM AI tool use rules, 2025 trial](https://www.cmathc.org.cn/mcm/news/285.html).

Reference-only LaTeX sources:

- [latexstudio/CUMCMThesis](https://github.com/latexstudio/CUMCMThesis), widely used but license is not explicit; do not vendor directly.
- [Sustainable-Enjoyment/CUMCM-LaTeX-Template](https://github.com/Sustainable-Enjoyment/CUMCM-LaTeX-Template), MIT, suitable for implementation pattern reference.
- [EmpyreanHYR/CUMCM-Latex-template](https://github.com/EmpyreanHYR/CUMCM-Latex-template), MIT, secondary implementation reference.

Canonical CUMCM rules to encode:

- Electronic paper must not include commitment page or numbering page; its first page is the abstract page.
- Do not include table of contents in the paper.
- The paper and supporting materials are separate submission files.
- Supporting materials should include runnable source code, self-collected data, and large intermediate figures/tables when used.
- Supporting material content must match paper claims and results.
- No submitted file should expose team identity, school, or contest area information.
- Main body should not include a table of contents and should stay within the official 30-page body limit.
- If no program or supporting material is used, the appendix must explicitly state that.
- If AI tools are used, the paper and support package must disclose tool name/version, use purpose and step, key interactions, adoption and human modification, and impact on final paper.
- If no AI tools are used, the paper must include the official no-AI declaration after references.

### Visual Generation Sources

Visual rules come from current Wenjin architecture plus external rendering guidance:

- Wenjin's existing FigureSpec contract already separates code plots, structured diagrams, and `llm_image`; keep this boundary.
- OpenAI official image generation docs list GPT Image 2 as the latest image model and support image generation/editing through model configuration; Wenjin should use the DataService image model catalog rather than hard-code a provider-specific id.
- Matplotlib documentation recommends choosing colormaps by data type and favors perceptually uniform maps for ordered data.
- ColorBrewer is a suitable reference for print-friendly and colorblind-aware palette choices.
- Canva Autofill is useful for filling existing brand/design templates, but it is not a reproducible evidence engine for CUMCM figures or software copyright screenshots.

Implementation must treat these as source guidance, not as runtime dependencies.

## Visual Generation Strategy

### Core Decision

Use a hybrid strategy, with deterministic generation as the default:

| Visual need | Primary route | AI image route | Canva route |
| --- | --- | --- | --- |
| CUMCM data/statistical/result charts | Python code via `sandbox.generate_figure` using matplotlib/seaborn/plotly static | Forbidden | Forbidden |
| CUMCM algorithm flow, model pipeline, decision process | Mermaid, Graphviz, TikZ, or Python-generated schematic | Forbidden | Forbidden |
| CUMCM maps, geometry, network, simulation snapshots | Python code or TikZ from explicit data/equations | Forbidden unless explicitly decorative | Forbidden |
| CUMCM graphical abstract or cover-like illustration | Optional, off by default | Allowed only as decorative artifact | Optional export polish only |
| Software module, deployment, data-flow, permission diagrams | Mermaid, Graphviz, or TikZ | Forbidden | Forbidden |
| Software operation screenshots | Real rendered prototype + browser screenshot, or uploaded real screenshots | Forbidden for evidence screenshots | Forbidden for evidence screenshots |
| Software icon, cover, brochure-like preview | Optional decorative asset | Allowed if image model configured | Optional polish/export |
| Official forms, code pages, manuals, tables | Text/LaTeX/code generation | Forbidden | Forbidden |

Rationale:

- Mathematical modeling papers are judged by correctness and reproducibility; plots must trace back to data, code, and model assumptions.
- Software copyright screenshots and diagrams are evidence-like materials; they must align with the claimed software name, version, modules, and operation steps.
- AI-generated bitmap images are visually strong but not reliable for exact text, UI consistency, measurements, or reproducible claims.
- Canva can improve presentation assets, but introducing it into the core path would make the workflow harder to reproduce and harder to test.

### Model Policy For AI Images

AI image generation is allowed only for decorative or conceptual assets:

- Route through `route_image_model()` and DataService model catalog category `image`.
- Prefer the configured best image model, such as `gpt-image-2`, when available.
- Never hard-code `gpt-image-2` in capability seeds, templates, or skills.
- If no image model is configured, skip optional decorative images and continue the workflow.
- Store `model_id`, provider metadata, target path, and source prompt hash in the artifact manifest.
- Do not store raw prompts containing user secrets or private materials.

Required failure behavior:

- A missing image model must not fail a CUMCM paper package.
- A missing image model must not fail a software copyright package unless the user explicitly requested a decorative image as the primary deliverable.
- Evidence visuals must never silently fall back to `llm_image`.

### FigureSpec Contract Extensions

Extend the figure contract instead of creating a parallel visual protocol.

Add fields:

```python
evidence_level: Literal["evidence", "explanatory", "decorative"] = "explanatory"
visual_profile_id: str | None = None
palette_id: str | None = None
source_artifact_paths: list[str] = []
reproducibility_command: str | None = None
```

Add figure types:

```python
"ui_screenshot"
"geometric_schematic"
"simulation_snapshot"
```

Add strategies:

```python
"playwright_screenshot"
"python_schematic"
```

Validation rules:

- `evidence_level="evidence"` forbids `llm_image` and `hybrid` when the bitmap is not fully derived from code or a real uploaded artifact.
- `data_plot`, `experiment_plot`, `statistical_chart`, and `table_visual` continue to require code strategies.
- `architecture_diagram`, `method_flow`, and `patent_drawing` continue to require Mermaid, Graphviz, or TikZ.
- `ui_screenshot` requires `playwright_screenshot` or a user-uploaded screenshot source.
- `decorative` visuals may use `llm_image`, but must be excluded from compliance evidence and supporting-material claims.

### Visual Artifact Layout

Generated visuals must stay in reviewable sandbox paths:

```text
/workspace/outputs/figures/
  math_modeling/
    fig01_model_pipeline/
      figure.pdf
      figure.png
      figure.svg
      spec.json
  software_copyright/
    fig01_module_architecture/
      figure.svg
      spec.json
/workspace/outputs/screenshots/
  software_copyright/
    screen01_login.png
    screen02_dashboard.png
    screenshot-spec.json
/workspace/reports/
  visual-manifest.md
```

Every final package must include `visual-manifest.md` with:

- Figure id and title.
- Purpose and evidence level.
- Generation route.
- Source data/script/prototype path.
- Output file paths.
- Caption and target manuscript/manual location.
- Quality gates checked.
- Whether the visual may be used as compliance evidence.

## CUMCM Visual Style Profile

Add `visual-profile.yaml` and `figure-style.mplstyle` to `math_modeling_cumcm2026_paper_pack`.

Default profile:

```yaml
id: math_modeling_cumcm_default
schema: wenjin.visual_profile.v1
workspace_type: math_modeling
default_route: code_first
output_formats: ["pdf", "svg", "png"]
dpi: 300
font:
  latex: xeCJK
  matplotlib_fallbacks: ["Noto Sans CJK SC", "SimHei", "WenQuanYi Micro Hei", "DejaVu Sans"]
palette:
  id: okabe_ito_print_safe
  colors:
    black: "#000000"
    orange: "#E69F00"
    sky_blue: "#56B4E9"
    bluish_green: "#009E73"
    yellow: "#F0E442"
    blue: "#0072B2"
    vermillion: "#D55E00"
    reddish_purple: "#CC79A7"
chart_rules:
  avoid: ["rainbow", "jet", "3d_effects", "decorative_gradients"]
  require_axis_units: true
  require_caption: true
  require_data_source_note: true
  require_marker_or_line_style_for_print: true
```

Math modeling required visuals:

- Model framework or solution pipeline diagram.
- Key result plots for each solved problem.
- Sensitivity analysis chart when the model has tunable parameters.
- Validation or error-analysis chart when data or simulation output exists.
- Tables rendered through LaTeX/booktabs or generated CSV/Markdown plus LaTeX table source.

Generation requirements:

- Use Python scripts under `/workspace/scripts`.
- Read datasets from `/workspace/datasets` when present.
- Write figures/tables to `/workspace/outputs`.
- Produce vector output for paper inclusion where possible.
- Produce PNG preview for review cards.
- Embed only final, manuscript-ready figures in `main.tex`.
- Put large intermediate plots in supporting materials, not the paper body.
- Captions must state what the figure proves, not merely what it shows.

Do not generate:

- Decorative stock-like images inside the competition paper.
- Fake maps, data heatmaps, or simulation visuals without code/data.
- AI-generated charts that cannot be reproduced from submitted code.

## Software Copyright Visual Style Profile

Add `visual-profile.yaml`, `diagram-theme.json`, and `screenshot-style.css` to `software_copyright_cn_application_pack`.

Default profile:

```yaml
id: software_copyright_cn_default
schema: wenjin.visual_profile.v1
workspace_type: software_copyright
default_route: structured_diagram_and_real_screenshot
output_formats: ["svg", "png", "pdf"]
diagram_palette:
  ink: "#1F2937"
  accent: "#2563EB"
  support: "#64748B"
  fill: "#F8FAFC"
  warning: "#B45309"
screenshot_rules:
  require_consistent_software_name: true
  require_consistent_version: true
  require_operation_step_mapping: true
  forbid_ai_generated_evidence_screenshots: true
  allow_generated_prototype_screenshots: true
```

Software copyright required visuals:

- Module architecture diagram.
- Main business or user-operation flowchart.
- Deployment/runtime environment diagram when the software implies a backend, client, or external dependency.
- Permission or role diagram when roles are mentioned.
- Operation screenshots for the main manual steps.

Screenshot strategy:

1. If the user uploads real screenshots, use them as primary evidence after checking name/version/module consistency.
2. If the user only provides a software name and feature idea, generate a clearly marked minimal prototype UI from the claimed modules, render it in sandbox/browser, and capture screenshots.
3. If neither real screenshots nor prototype generation is available, keep screenshot placeholders and flag the package as needing user confirmation.

Prototype screenshots must:

- Render from code, not from image generation.
- Show the exact software name and version used in the manual.
- Use module names from the material planner.
- Avoid claiming production integrations, live data, or unavailable third-party services.
- Be described as "界面示例/原型截图" unless backed by user-provided real software evidence.

AI image generation may produce:

- Optional app icon.
- Optional manual cover illustration.
- Optional conceptual overview image.

AI image generation must not produce:

- Operation screenshots.
- Source code pages.
- Application form images.
- Proof documents.
- Any visual used as evidence of implemented functionality.

Canva may be considered later only for:

- Exporting a polished brochure/cover from already generated assets.
- Filling a user-owned brand template.
- Non-core presentation materials outside the official submission pack.

It must not be a dependency of the one-shot software copyright workflow.

## DataService Design

Keep the implementation simple. Do not add a separate template marketplace or a general `template_pack` table.

Reuse and slightly extend the existing LaTeX template catalog:

- Existing model: `backend/src/database/models/latex_template.py`.
- Add `metadata_json JSONB NOT NULL DEFAULT '{}'` to `latex_templates`.
- Keep `template_path` as the filesystem pointer to the asset directory.
- Store template pack rules, version, source links, license notes, visual profile id, route policy, quality gates, and asset roles in `metadata_json`.

`WorkspaceTemplate` remains workspace-level state:

- Existing model: `backend/src/database/models/workspace_template.py`.
- It should receive an active instance only when a workspace or capability materializes a specific template into the workspace.
- It is not the system source of truth for the built-in template pack.

## Seed And Asset Layout

Create one seed registry and two template asset directories:

```text
backend/seed/latex_templates/
  registry.yaml
  assets/
    software_copyright_cn_application_pack/
      TEMPLATE.md
      application-fields.md
      manual.tex
      source-deposit-guide.md
      proof-checklist.md
      visual-profile.yaml
      diagram-theme.json
      screenshot-style.css
      quality-gates.json
    math_modeling_cumcm2026_paper_pack/
      TEMPLATE.md
      main.tex
      refs.bib
      ai-use-disclosure.tex
      supporting-materials-manifest.md
      visual-profile.yaml
      figure-style.mplstyle
      code/solve.py
      quality-gates.json
```

`registry.yaml` must define both built-ins:

```yaml
schema_version: latex_template_registry.v1
templates:
  - id: software_copyright_cn_application_pack
    label: 软著申报材料包
    main_file: manual.tex
    category: software_copyright
    featured: true
    template_path: software_copyright_cn_application_pack
    metadata_json:
      schema: wenjin.authoritative_template.v1
      workspace_type: software_copyright
      template_kind: software_copyright_application_pack
      version: "2026.1"
      authority_level: official_rules_plus_internal_template
      license: internal_generated
      sources:
        - https://www.ncac.gov.cn/xxfb/flfg/bmgz/202410/P020241015604759788122.pdf
        - https://banshi.beijing.gov.cn/pubtask/task/1/110000000000/3e283672-76be-4c8c-98e8-0bebe9bd06bf.html?locationCode=110000000000
      visual_sources:
        - https://developers.openai.com/api/docs/guides/image-generation
        - https://www.canva.dev/docs/connect/api-reference/autofills/create-design-autofill-job/
      quality_gates:
        - software_name_version_consistent
        - official_form_fields_only_no_fake_form
        - source_document_deposit_rules_checked
        - proof_materials_flagged
        - visual_manifest_present
        - no_ai_generated_evidence_screenshots
      visual_profile:
        id: software_copyright_cn_default
        route_policy: structured_diagram_and_real_screenshot
        ai_image_policy: decorative_only_optional

  - id: math_modeling_cumcm2026_paper_pack
    label: 数模国赛论文包
    main_file: main.tex
    category: math_modeling
    featured: true
    template_path: math_modeling_cumcm2026_paper_pack
    metadata_json:
      schema: wenjin.authoritative_template.v1
      workspace_type: math_modeling
      template_kind: cumcm_paper_pack
      version: "2026.1"
      authority_level: official_rules_plus_internal_template
      license: internal_generated
      sources:
        - https://www.cmathc.org.cn/mcm/tz/407.html
        - https://www.cmathc.org.cn/mcm/news/285.html
      visual_sources:
        - https://matplotlib.org/stable/users/explain/colors/colormaps.html
        - https://colorbrewer2.org/
        - https://developers.openai.com/api/docs/guides/image-generation
      quality_gates:
        - cumcm_abstract_first_page
        - cumcm_no_preface_numbering_or_toc
        - cumcm_main_body_page_limit_checked
        - cumcm_no_identity_leak
        - supporting_materials_consistent
        - ai_use_disclosure_or_no_ai_declaration_present
        - visual_manifest_present
        - evidence_figures_code_generated
      visual_profile:
        id: math_modeling_cumcm_default
        route_policy: code_first
        ai_image_policy: decorative_only_optional
```

The old hard-coded `_DEFAULT_TEMPLATES` in `backend/src/dataservice/domains/latex/service.py` should be replaced with this YAML-backed bootstrap. Bootstrap must upsert by `id`, not skip when any template exists.

The default `WENJIN_LATEX_TEMPLATE_DIR` fallback should point to the in-repo seed assets so local development and Docker deployments do not depend on `/Users/ze/WenjinPrism/templates`.

## Software Copyright Template Contract

`application-fields.md` is the canonical field-material template. It must include:

- Software full name.
- Optional short name.
- Version, defaulting to `V1.0` unless user supplies one.
- Development completion date, explicitly marked as user-confirmed when unknown.
- First publication date/place, optional and marked unknown when absent.
- Development mode: independent, cooperative, commissioned, assigned task, inherited/assigned.
- Rights acquisition mode.
- Rights scope.
- Hardware environment, under the official-field word budget.
- Software environment, under the official-field word budget.
- Programming language and version.
- Source program line count.
- Main functions and technical characteristics, with a concise official-form version and an expanded manual version.
- Applicant, owner, contact, and proof-material placeholders.

`manual.tex` is the canonical software document template. It must include:

- Header commands for `SoftwareName` and `Version`.
- A4 layout, Chinese-friendly `ctexart`, black-print safe styling.
- Page header showing software name and version.
- Page numbering.
- Sections:
  - Software overview.
  - Purpose and application scope.
  - Runtime environment.
  - System architecture.
  - Function modules.
  - Data input/output.
  - User roles and permissions.
  - Operation steps with screenshot placeholders.
  - Exception handling.
  - Deployment and maintenance notes.
  - Version description.
  - Submission checklist.

`source-deposit-guide.md` is the canonical source deposit template. It must include:

- First/last 30-page rule.
- Under-60-pages full submission rule.
- Page header requirements.
- Page numbering requirements.
- Source line-count check.
- No secrets, private keys, unrelated personal data, or implementation claims not backed by code.
- If no source exists, the capability must generate a clearly marked original minimal prototype or flag that source material is missing. It must not pretend a nonexistent system already exists.

`proof-checklist.md` must cover:

- Natural person identity proof.
- Enterprise or institution proof.
- Cooperative development agreement.
- Commissioned development agreement.
- Assigned task proof.
- Transfer/inheritance proof.
- Agent authorization proof when applicable.

`visual-profile.yaml` is the canonical software copyright visual policy. It must include:

- Allowed routes for module diagrams, flowcharts, deployment diagrams, screenshots, and decorative assets.
- The rule that evidence screenshots cannot be AI-generated bitmaps.
- The rule that generated prototype screenshots must be marked as examples unless backed by uploaded real software screenshots.
- Diagram palette and typography values.
- Screenshot consistency checks for software name, version, module names, and operation steps.

`diagram-theme.json` must define:

- Mermaid/Graphviz/TikZ colors and typography.
- Default shapes for modules, external systems, databases, users, and decisions.
- Black-and-white printable fallback styling.

`screenshot-style.css` must define:

- A restrained, generic product UI style suitable for manual screenshots.
- Stable viewport sizes for screenshots.
- Header/footer treatment showing software name and version.
- No brand claims, customer logos, real personal data, or unavailable third-party service names.

If prototype screenshots are generated, the capability must also stage:

- Prototype source under `/workspace/scripts/software_copyright_prototype/`.
- Screenshots under `/workspace/outputs/screenshots/software_copyright/`.
- Screenshot-to-manual mapping in `/workspace/reports/visual-manifest.md`.

## Mathematical Modeling Template Contract

`main.tex` is the canonical CUMCM 2026 electronic paper template. It must:

- Use XeLaTeX-compatible Chinese typesetting.
- Use A4 paper and margins no smaller than 2.5 cm.
- Start directly with title, abstract, and keywords.
- Not include commitment page.
- Not include numbering page.
- Not include table of contents.
- Keep the main body within the official 30-page body limit.
- Avoid school, author, region, team, or personal identity placeholders.
- Include sections:
  - Abstract and keywords.
  - Problem restatement.
  - Assumptions.
  - Notation.
  - Problem analysis.
  - Model establishment.
  - Model solution.
  - Results and interpretation.
  - Model validation.
  - Sensitivity analysis.
  - Strengths and weaknesses.
  - Conclusion.
  - References.
  - Appendix with supporting-materials file list, source program statement, and no-supporting-materials statement when applicable.

`ai-use-disclosure.tex` must include:

- AI tool name and version.
- Developer or company.
- Use date.
- Use purpose and workflow step.
- Key prompts and responses summary.
- Adopted content.
- Human modification and verification.
- Impact on final paper.
- A note that the team must confirm contest compliance before submission.

The package must also support the no-AI path:

- If AI tools were not used, include the official no-AI declaration after references.
- If AI tools were used, generate a separate support-material disclosure file named `AI工具使用详情` for PDF export.
- In both cases, keep team identity, school, and contest-area information out of the paper and support files.

`supporting-materials-manifest.md` must include:

- Runnable source program list.
- Data files used.
- Generated figures and tables.
- Intermediate result files.
- Reproduction commands.
- Expected outputs and hashes when available.
- Statement when no program or no supporting materials are used.
- Identity-leak checklist.

`code/solve.py` is only a scaffold. It should:

- Load data from `/workspace/datasets` when available.
- Write figures/tables/results under `/workspace/outputs`.
- Avoid hard-coded personal paths.
- Emit a short reproducibility summary.

`visual-profile.yaml` is the canonical CUMCM visual policy. It must include:

- Code-first route rules for all evidence figures.
- Palette id and color values.
- Figure size presets for half-width and full-width paper placement.
- Required output formats.
- Caption, axis, unit, and data-source checks.
- Supporting-material inclusion rules for large intermediate figures.

`figure-style.mplstyle` must encode the default matplotlib style:

- 300 DPI save settings.
- Chinese font fallback list.
- Colorblind-aware color cycle.
- Grid, linewidth, marker, and legend defaults that survive grayscale printing.
- No `jet`, rainbow, 3D effects, or decorative gradients.

## Runtime Integration

### Default Template Resolution

Update `WorkspaceLatexProjectService._default_template_for_workspace`:

```python
{
  "software_copyright": "software_copyright_cn_application_pack",
  "math_modeling": "math_modeling_cumcm2026_paper_pack",
}
```

Existing workspace types can keep their current ids unless they are refactored separately.

### Workspace Type Registration

Add `math_modeling` as a first-class workspace type in the same places that currently enumerate `thesis`, `sci`, `proposal`, `software_copyright`, and `patent`:

- Gateway workspace validator.
- Database model enum or type contract.
- DataService client workspace contracts.
- Sandbox workspace type profile.
- Workspace summary labels.
- Capability seed directory.
- Frontend workspace type display surfaces only when required by existing creation/listing UI.

Do not fork sandbox provider layout for `math_modeling`; add a new workspace type profile using the existing `/workspace/main`, `/workspace/scripts`, `/workspace/outputs`, `/workspace/reports`, and `/workspace/datasets` roots.

Recommended `math_modeling` sandbox profile:

```text
primary_files:
  /workspace/main/main.tex
  /workspace/main/refs.bib
  /workspace/main/supporting-materials-manifest.md
script_paths:
  /workspace/scripts/solve.py
  /workspace/scripts/figures.py
output_paths:
  /workspace/outputs/figures
  /workspace/outputs/tables
  /workspace/outputs/results
report_paths:
  /workspace/reports/visual-manifest.md
  /workspace/reports/reproducibility-report.md
  /workspace/reports/format-compliance.md
```

### Capability Integration

Each super workflow capability should declare its template id in `extensions`:

```yaml
extensions:
  authoritative_template_id: software_copyright_cn_application_pack
```

Runtime requirements:

- Lead runtime must fetch template metadata from DataService before drafting.
- Template files are copied when creating or ensuring the workspace primary LaTeX project.
- React subagents receive a bounded template contract summary, not the full unbounded template file dump.
- The writer stage must produce changes against the copied template files.
- Result cards should show template-backed outputs as reviewable file changes and sandbox artifacts.
- Visual profile metadata must be included in the bounded template contract summary.
- Figure and screenshot artifacts must be generated before final manuscript/manual drafting so captions and references are stable.

### One-shot Capability Graphs

`software_copyright_application_pack` should become the only visible primary software copyright super workflow.

Recommended internal phases:

1. `material_intake_planner`: normalize software name, version, development mode, module list, runtime environment, and missing proof decisions.
2. `software_structure_planner`: build module/function/source/manual/screenshot consistency matrix.
3. `software_visual_planner`: produce FigureSpecs for module diagram, operation flow, deployment diagram, role/permission diagram, and screenshot plan.
4. `figure_engineer`: generate structured diagrams and prototype screenshots when real screenshots are absent.
5. `software_doc_drafter`: draft `application-fields.md`, `manual.tex`, source deposit guide content, and proof checklist against generated visual refs.
6. `source_material_packager`: generate or update source/document deposit instructions and optional minimal prototype source metadata.
7. `review_critic`: run compliance review and emit result-card review items.

`software_architecture_diagrams` can remain as a hidden or secondary artifact follow-up capability, but Chat Agent routing should prefer the full material pack when the user asks for "一步到位", "办软著", "生成材料包", or only provides a software name.

Create a new visible `math_modeling_paper_pack` capability for the `math_modeling` workspace.

Recommended internal phases:

1. `problem_intake_parser`: parse the problem statement, identify subquestions, assumptions, data availability, and required outputs.
2. `modeling_strategy_planner`: choose model families and solution plan; mark uncertainty and required assumptions.
3. `sandbox_solver`: generate and run reproducible code scaffold or problem-specific solver scripts.
4. `figure_table_engineer`: generate all evidence figures, tables, visual manifest, captions, and LaTeX include paths.
5. `math_modeling_writer`: draft `main.tex` using the authoritative CUMCM template and generated artifacts.
6. `supporting_materials_packager`: update `supporting-materials-manifest.md`, code list, data list, hashes, and reproduction commands.
7. `format_compliance_checker`: check CUMCM format, identity leak, supporting-material consistency, and AI-use disclosure.

The math modeling workflow may ask a question only when the problem statement itself is missing or unreadable. If data is missing, it should proceed with synthetic placeholders only when clearly marked, or generate a data-request warning while still drafting the paper structure.

### Screenshot Generation Route

Add a sandbox-owned screenshot path rather than using AI image generation:

- Generate a small static prototype from structured module data under `/workspace/scripts/software_copyright_prototype/`.
- Render it with a deterministic local browser route.
- Capture screenshots to `/workspace/outputs/screenshots/software_copyright/`.
- Register screenshots as reviewable sandbox artifacts.
- Map each screenshot to a manual operation step in `visual-manifest.md`.

Implementation can use Playwright through a Node-based sandbox image or a dedicated screenshot runner. The runner must not require host browser state, user login, Chrome extensions, or external network access.

### Canva Decision

Do not integrate Canva in this implementation plan.

Reason:

- The current deliverables are official-style documents, reproducible paper assets, diagrams, screenshots, and compliance manifests.
- Canva's strength is filling and exporting pre-existing design templates, which is useful for later marketing or presentation artifacts.
- Adding it now would introduce OAuth/session/export concerns without improving the core evidence package.

Future Canva integration can be a separate optional export capability after the two one-shot workflows are stable.

### Chat And Follow-up

Initial one-shot runs use the authoritative template.

Follow-up chat refinements must edit the generated template-backed files through Prism review or a rerun with the same template id. Agents must not switch to another implicit template.

Follow-up visual refinements must preserve route class:

- Data chart refinement reruns the script or edits the plotting script.
- Diagram refinement edits Mermaid/Graphviz/TikZ source.
- Screenshot refinement edits the prototype source or asks the user for real screenshots.
- Decorative image refinement may rerun the image model if configured.

## Quality Gates

Add or standardize these gates.

Software copyright:

- `official_form_fields_only_no_fake_form`
- `software_name_version_consistent`
- `source_document_deposit_rules_checked`
- `manual_source_application_alignment`
- `proof_materials_flagged`
- `no_claims_about_unimplemented_features`
- `visual_manifest_present`
- `structured_diagrams_have_source`
- `operation_screenshots_mapped_to_manual_steps`
- `no_ai_generated_evidence_screenshots`
- `prototype_screenshots_marked_when_not_real`

Mathematical modeling:

- `cumcm_abstract_first_page`
- `cumcm_no_preface_numbering_or_toc`
- `cumcm_main_body_page_limit_checked`
- `cumcm_no_identity_leak`
- `cumcm_supporting_materials_manifest_present`
- `supporting_materials_consistent_with_paper`
- `ai_use_disclosure_or_no_ai_declaration_present`
- `runnable_code_or_no_code_statement_present`
- `visual_manifest_present`
- `evidence_figures_code_generated`
- `figure_scripts_reproducible`
- `figure_palette_profile_applied`
- `figure_caption_axis_unit_checked`
- `no_ai_generated_data_figures`

Gate results should appear in the final review report and result card. Failed gates should not block generation, but must be visible before user acceptance.

## DataService API Requirements

Extend `LatexTemplatePayload` with `metadata_json`.

Update internal LaTeX template endpoints:

- `GET /internal/v1/latex/templates`
- `GET /internal/v1/latex/templates/{template_id}`
- `POST /internal/v1/latex/templates/ensure-defaults`

All must include `metadata_json` in responses.

Bootstrap behavior:

- Read `backend/seed/latex_templates/registry.yaml`.
- Upsert templates by `id`.
- Preserve user-created project records.
- Do not delete unknown template rows during bootstrap.
- Fail loudly if a registered template asset directory is missing.
- Validate every `template_path` stays under the configured template root.
- Validate referenced visual profile files exist.
- Validate `metadata_json.visual_profile.id` matches the asset `visual-profile.yaml`.

Template metadata requirements:

- Include source URLs and license notes.
- Include quality gate ids.
- Include visual profile id and route policy.
- Include whether optional decorative AI image generation is enabled by default; for both initial templates it is disabled by default.
- Include the minimum template contract summary that agents may receive at runtime.

## Frontend Requirements

No homepage change.

Workspace / Prism UI may display:

- Template label.
- Template version.
- Source authority summary.
- Visual profile label.
- Reviewable figure/screenshot previews through the existing result-card image preview path.
- Visual manifest link when generated.

Do not show:

- Multiple system template choices for these two verticals.
- Raw template metadata JSON.
- GitHub reference list in the primary user flow.
- Image model selector or Canva selector in the primary one-shot flow.

## Tests

Backend tests:

- DataService template bootstrap upserts both new ids even when old templates exist.
- `LatexTemplatePayload` includes `metadata_json`.
- Missing asset directories make bootstrap fail.
- `LatexProjectService.create(..., template_id=...)` copies `.tex`, `.md`, `.json`, `.css`, `.mplstyle`, YAML profile, and code scaffold files.
- `WorkspaceLatexProjectService` maps `software_copyright` and `math_modeling` to the new authoritative ids.
- Capability seeds reference existing authoritative template ids.
- Quality gate ids are present in both capability definitions.
- `FigureSpec` rejects `llm_image` for evidence-level figures.
- `FigureSpec` rejects `llm_image` for data plots and software evidence screenshots.
- Screenshot route registers `/workspace/outputs/screenshots/software_copyright/*.png` as reviewable artifacts.
- Math modeling figure route writes script path, output paths, and reproducibility command into `visual-manifest.md`.
- Missing image model skips optional decorative images without failing either workflow.

Frontend tests:

- Template metadata display is optional and does not break when absent.
- Workspace creation/listing does not show extra template choices.
- Figure and screenshot review items preview through existing image preview UI.
- Visual manifest appears as a report/document artifact, not as raw metadata JSON.

Regression tests:

- Existing ACL/CVPR/NeurIPS/ICML templates still list when seeded.
- Existing projects with old template ids remain readable.
- Existing `software_architecture_diagrams` runs still produce figure review artifacts if kept enabled.

## Migration And Rollout

1. Add `metadata_json` migration for `latex_templates`.
2. Add seed registry and two asset directories.
3. Replace hard-coded default template bootstrap with registry-backed upsert.
4. Add DataService contract and router payload support.
5. Update workspace default template mapping.
6. Add `math_modeling` workspace type and sandbox profile.
7. Add capability `extensions.authoritative_template_id` and `extensions.visual_profile_id`.
8. Extend FigureSpec for evidence level, screenshot type, and route validation.
9. Add screenshot runner route for software copyright prototype screenshots.
10. Update `software_copyright_application_pack` graph to include visual planning/generation.
11. Add `math_modeling_paper_pack` capability seed and worker skill seeds if existing academic skills are insufficient.
12. Add or update quality gate ids.
13. Run backend seed, DataService, LaTeX, capability, sandbox artifact, and frontend preview tests.

## Acceptance Criteria

- A fresh DataService bootstrap contains `software_copyright_cn_application_pack` and `math_modeling_cumcm2026_paper_pack`.
- Creating a software copyright primary LaTeX project copies the software copyright template files.
- Creating a math modeling primary LaTeX project copies the CUMCM 2026 template files.
- The two super workflow capability seeds reference the matching template id.
- The two super workflow capability seeds reference the matching visual profile id.
- Agents no longer rely on long prompt-embedded template text for these two workflows.
- Result cards expose generated template-backed files for user review.
- Software copyright package generation produces at least one structured diagram and either real screenshots, prototype screenshots, or explicit screenshot-missing warnings.
- Software copyright prototype screenshots are never represented as real production screenshots.
- Math modeling package generation produces code-backed figures and a visual manifest when figures are present.
- AI image generation is optional and never used for evidence figures, operation screenshots, data charts, or compliance proof.
- Canva is not required for a successful run.
- No new public template marketplace, homepage change, or multi-template chooser is introduced.
