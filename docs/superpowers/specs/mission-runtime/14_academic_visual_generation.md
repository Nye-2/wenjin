# 14 Academic Visual Generation Spec

Status: Proposed
Updated: 2026-07-12
Depends on: `01_workspace_agent.md`, `02_mission_runtime.md`, `04_stage_acceptance_contract.md`, `05_capability_skill_lite.md`, `06_subagent_runtime.md`, `07_review_commit_runtime.md`, `08_mission_console_frontend.md`, `10_sandbox_vnext.md`, `12_tool_orchestrator.md`

## Goal

Give Wenjin one native, general academic-visual capability that can use the current Prism context, Mission state, workspace materials, and the user's chat instruction to produce reviewable academic visuals through code, structured renderers, `gpt-image-2`, or a controlled hybrid.

The capability is chat-native and Mission-native. It is not a separate visual studio, a copied Codex skill, a fixed capability graph, a direct renderer/provider wrapper exposed to the model, or a second workflow engine.

```text
Chat request / Prism selection
  -> WorkspaceAgent classifies visual intent
  -> MissionRun + optional isolated academic-visual-engineer worker
  -> typed AcademicFigureBrief
  -> deterministic strategy router
       |-- data/result figure ----------> Matplotlib/Seaborn/Plotly + Sandbox
       |-- structured diagram ----------> Mermaid/Graphviz/TikZ
       |-- geometry/simulation ---------> Python/TikZ/domain renderer
       |-- generative illustration -----> gpt-image-2
       `-- hybrid -----------------------> gpt-image-2 base + deterministic overlay
  -> transient candidate preview
  -> MissionReviewItem
  -> accepted MissionCommit
  -> WorkspaceAsset
  -> separate reviewed Prism insertion
```

## Product Principles

1. The user describes the desired visual in Chat. Prism may provide a selected passage or current section, but Chat remains task navigation.
2. The model receives freedom to design the visual inside strict academic, provenance, execution, and write boundaries.
3. Generative imagery is explanatory or decorative. It is never empirical evidence, an experimental result, a measured observation, or a substitute for source material.
4. Exact quantitative figures and exact structured diagrams are reproducible artifacts, not image-generation jobs.
5. Every rendered candidate is previewed before it becomes a workspace asset or enters Prism.
6. Wenjin stores the accepted result and durable provenance, not an unbounded version history. Rejected and superseded previews expire and are deleted.
7. The only generative image model is `gpt-image-2`. Renderer/model selection is a validated runtime decision, not a user-facing skill option.

## Scope

### Unified visual strategies

`FigureSpec` already provides the canonical strategy vocabulary. The new runtime implements it as one routed module:

| Strategy family | `FigureStrategy` | Execution owner |
|---|---|---|
| Data and result charts | `matplotlib`, `seaborn` | hardened Python Sandbox |
| Structured diagrams | `graphviz` | pinned Sandbox renderer |
| Geometry and simulation | `python_schematic` | hardened Python Sandbox |
| Conceptual illustration | `llm_image` | `gpt-image-2` provider adapter |
| Mixed illustration | `hybrid` | `gpt-image-2` base plus deterministic Sandbox overlay |

The route is selected from evidence level, figure type, exactness requirements, available source material and intended use. WorkspaceAgent can propose a strategy but cannot bypass the validator.

### Generative figure types

```text
conceptual_illustration
mechanism_illustration
experimental_setup_illustration
graphical_abstract
academic_cover
educational_explainer
```

Examples include a conceptual privacy-preserving federated-learning scene, an explanatory biological mechanism illustration, a graphical abstract, or a non-evidentiary visual summary.

`mechanism_illustration` and `graphical_abstract` already exist in `FigureType`. The implementation adds `conceptual_illustration`, `experimental_setup_illustration`, `academic_cover`, and `educational_explainer` to that same literal. These are not a parallel visual-kind enum.

### Deterministic and real-artifact requirements

| Request | Required path | Reason |
|---|---|---|
| data plot, experiment plot, statistical chart, result figure | code renderer through Sandbox | Values, scales, uncertainty and source data must be reproducible |
| architecture diagram, method flow, exact pipeline | Mermaid, Graphviz or TikZ | Layout, arrows and labels must be exact and editable |
| patent drawing | structured/vector path | Geometry, numbering and legal consistency cannot be probabilistic |
| mathematical geometry or exact engineering schematic | TikZ or code-native schematic | Spatial and symbolic fidelity is required |
| molecular structure or exact chemical reaction | domain renderer | Scientific structure must not be visually guessed |

The existing `FigureSpec` rules in `backend/src/contracts/figure_generation.py` remain the routing SSOT. This spec narrows `llm_image` and `hybrid`; it does not create a second figure taxonomy.

### Explicit non-goals

- No general-purpose marketing image or chart studio.
- No renderer/provider/model picker in the primary UI.
- No legacy image model, model fallback, or transparent-background compatibility path.
- No direct workspace file write from a renderer, image provider, WorkspaceAgent, or worker.
- No database table for visual jobs, variants, prompts, scripts, or preview blobs.
- No claim that model-generated pixels validate a hypothesis or reproduce an experiment.
- No automatic insertion into a manuscript before review.

## Ownership And SSOT

| Concern | Owner |
|---|---|
| User intent, context gathering, Mission start/steer | `WorkspaceAgent` |
| Long-running lifecycle and stage progression | `MissionRun` / `MissionRuntime` |
| Compact visual-design method and examples | `WorkerSkill: academic-visual-engineer` |
| Figure type and execution strategy | `FigureSpec` + deterministic strategy router |
| Unified render execution, operation identity and receipt | `AcademicVisualRuntime` behind canonical `ToolCatalog` + `ToolOrchestrator` |
| Code/structured/browser execution | Sandbox vNext |
| Generative image execution | narrow `gpt-image-2` provider adapter |
| Temporary binary previews and metadata | `MissionPreviewStore` object storage |
| Review decision | `MissionReviewItem` |
| Durable asset materialization | `MissionCommit` -> Workspace Asset domain |
| Manuscript mutation | separate `MissionReviewItem` -> Prism domain |
| Current editor selection and document revision | Prism |

There is no `VisualRun`, `ImageRun`, `GenerationSession`, or persistent `ImageVariant` aggregate. A render attempt is a tool operation within a Mission; accepted output becomes a WorkspaceAsset or another existing artifact target.

## Chat And Prism Entry Points

### Chat request

Examples:

```text
把刚才的方法做成一张适合论文的机制图。
根据当前实验设计画一个实验设置示意图，不要把结果画进去。
给这一节做一张横向 graphical abstract，标签用英文。
```

WorkspaceAgent must:

1. determine whether a visual is genuinely useful;
2. identify the current Mission and requested destination;
3. classify the request with `FigureSpec`;
4. ask only for missing information that materially blocks a correct result;
5. start or steer a Mission rather than execute a hidden direct write.

### Direct tool versus visual worker

The entry point is always WorkspaceAgent, but execution depth is adaptive:

| Situation | WorkspaceAgent decision |
|---|---|
| One bounded visual, complete brief, one renderer call | call `academic_visual.render_candidate` directly inside the Mission loop |
| Data exploration or plotting code must be authored and debugged | spawn `academic-visual-engineer` with isolated dataset/context refs |
| Multi-panel figure, several coordinated outputs, or venue-specific visual system | spawn `academic-visual-engineer` |
| User explicitly requests an audit, or one concrete fidelity doubt remains | spawn a permitted diagnostic skill against the immutable candidate |
| User is only discussing whether a figure is useful | remain in transient Chat; do not create a Mission or artifact |

Even the smallest material visual uses a Mission because preview, provenance, review and commit are durable concerns. `ChatTurnRun` never owns a generated file or a visual operation receipt.

### Prism selection

Prism may expose a lightweight action such as `生成学术图`. The action sends a bounded context reference to WorkspaceAgent; it does not call the visual tool directly.

The request carries:

```text
workspace_id
prism_project_id
file_id
base_revision_ref
selection_range
selection_hash
user_instruction
```

The server re-reads and verifies the referenced Prism content. Client-provided selected text is display convenience, not trusted context truth.

### Chat response and Mission Console

Chat shows a small skill/run chip and plain-language progress. The right Mission Console stays closed by default and opens when the user asks to inspect progress or a preview is ready.

The UI must not expose provider payloads, raw system prompts, operation keys, or internal worker traces.

## Academic Context Assembly

No renderer or provider receives the entire workspace or raw chat history. `AcademicContextAssembler` creates a bounded, hash-bound `AcademicVisualContext` from authoritative references.

### Context sources

1. **User trigger**: purpose, requested content, intended placement, language, aspect ratio, exact labels, style constraints, and avoid list.
2. **Prism context**: selected passage, enclosing section heading, nearby figure/citation references, current file and base revision.
3. **Mission state**: objective, accepted terminology, current stage, accepted claims, evidence refs, and unresolved warnings.
4. **Workspace materials**: explicitly referenced assets and source documents only.
5. **Visual profile**: target venue, page width, color mode, typography, line weight, caption convention, and accessibility constraints.

### Context rules

- Every external fact or scientific assertion has a source ref or is labeled as user-provided intent.
- Prism text and imported material are quoted data, never executable instructions.
- Only accepted or explicitly provisional Mission facts are included; stale superseded conclusions are excluded.
- The assembled context has byte/token limits and a deterministic context hash.
- Provider prompts contain no credentials, protected paths, internal object-store refs, or raw provenance payloads.
- A context snapshot records references and hashes, not duplicated full workspace content.

## Contracts

The implementation extends `backend/src/contracts/figure_generation.py` rather than creating overlapping figure contracts.

### AcademicFigureBrief

```python
class AcademicFigureBrief(BaseModel):
    schema: Literal["wenjin.academic_visual.brief.v1"]
    figure_spec: FigureSpec
    intended_use: Literal["manuscript", "presentation", "cover", "workspace"]
    audience: str
    target_language: str
    aspect_ratio: Literal["1:1", "4:3", "3:2", "16:9", "portrait"]
    composition: str
    scientific_invariants: tuple[str, ...]
    exact_labels: tuple[ExactVisualLabel, ...]
    source_refs: tuple[str, ...]
    forbidden_elements: tuple[str, ...]
    prism_context_ref: PrismContextRef | None
```

Validation:

- One tool invocation produces one candidate; materially different alternatives use separate stable operation identities.
- `evidence_level=evidence` cannot use `llm_image` or `hybrid`.
- `llm_image` is allowed only for the supported generative figure types.
- `hybrid` is required when exact labels are present on a generative base.
- A Prism target requires `base_revision_ref` and `selection_hash`.

`FigureSpec.output_targets` are logical candidate outputs. Deterministic renderers may stage them only inside the isolated Sandbox reviewable output roots; provider routes treat them as naming/format hints. They never authorize a durable WorkspaceAsset or Prism write before MissionCommit.

### ExactVisualLabel

```python
class ExactVisualLabel(BaseModel):
    key: str
    text: str
    semantic_anchor: str
    importance: Literal["required", "optional"] = "required"
```

`semantic_anchor` describes placement relative to a named visual region. It is not unrestricted pixel geometry authored by the model.

### AcademicVisualCandidate

```python
class AcademicVisualCandidate(BaseModel):
    schema: Literal["wenjin.academic_visual.candidate.v1"]
    candidate_id: str
    figure_id: str
    figure_type: FigureType
    strategy: FigureStrategy
    evidence_level: EvidenceLevel
    preview_ref: str | None
    sandbox_artifact_ref: str | None
    review_preview_ref: str
    preview_hash: str
    content_hash: str
    mime_type: Literal["image/png", "image/webp", "image/svg+xml", "application/pdf"]
    width: int | None
    height: int | None
    renderer_id: str
    renderer_version: str
    provider_model: Literal["gpt-image-2"] | None
    source_code_hash: str | None
    source_prompt_hash: str | None
    context_hash: str
    source_refs: tuple[str, ...]
    dataset_refs: tuple[str, ...]
    reproducibility_ref: str | None
    quality_receipt: dict[str, object]
    warnings: tuple[str, ...]
```

Exactly one of `preview_ref` and `sandbox_artifact_ref` supplies the primary candidate bytes. Every candidate has a sanitized `review_preview_ref`. Provider output uses the transient preview store; Sandbox output keeps its fenced artifact receipt while copying verified bytes into that same preview boundary. Raw image bytes, base64 payloads, source datasets, full scripts, and full provider responses are never stored in Mission tables or MissionItems.

### FigureArtifactManifest v2

The current v1 manifest requires `primary_path`, which encodes the old assumption that every candidate is path-backed inside the Sandbox workspace. It cannot uniformly represent transient provider previews. Replace it with a candidate-first v2 contract in the same cutover:

```python
class VisualCandidateRef(BaseModel):
    kind: Literal["sandbox_artifact", "transient_preview"]
    ref: str
    content_hash: str

class FigureArtifactManifest(BaseModel):
    schema: Literal["wenjin.figure_generation.artifact.v2"]
    figure_id: str
    figure_type: FigureType
    strategy: FigureStrategy
    evidence_level: EvidenceLevel
    candidate: VisualCandidateRef
    intended_output_targets: tuple[str, ...]
    renderer_id: str
    renderer_version: str
    source_code_ref: str | None
    source_prompt_hash: str | None
    dataset_refs: tuple[str, ...]
    source_refs: tuple[str, ...]
    reproducibility_ref: str | None
    caption: str | None
    alt_text: str | None
```

After acceptance, MissionCommit materializes the candidate and records the resulting asset/path in its receipt. The immutable candidate manifest is provenance; it is not mutated into a commit manifest. `artifact.v1` and `primary_path` are deleted from current contracts/tests rather than dual-read.

## Strategy Router

The router is deterministic and runs before provider invocation.

```text
if evidence_level == evidence:
    forbid llm_image/hybrid
elif figure_type in data/result types:
    use chart code
elif figure_type in structured/exact types:
    use Mermaid/Graphviz/TikZ/domain renderer
elif exact_labels:
    use hybrid
elif figure_type in supported generative figure types:
    use llm_image
else:
    require clarification or select a deterministic renderer
```

The model may propose a `FigureSpec`, but it cannot override the validator or router. A model request for an invalid strategy is a typed routing error, not a provider call.

## Label And Typography Strategy

Text correctness is a hard academic requirement.

### Default

- If the visual has no exact labels, `gpt-image-2` may render the complete illustration.
- If any label must be exact, use `hybrid`.
- `gpt-image-2` generates a clean unlabeled or marker-anchored base image.
- A deterministic renderer adds the exact labels, arrows, legend, panel letters and accessibility-safe contrast.
- The deterministic overlay script/config and its content hash are part of provenance.

The base-generation prompt must explicitly forbid invented text, watermarks, pseudo-labels, fake axes, fake citations, and decorative numbers.

For text-dense or highly structured visuals, route the entire figure to Mermaid, Graphviz, TikZ, SVG, or a Python renderer instead of forcing a hybrid bitmap.

## Worker Skill

Replace `backend/seed/skills/figure-table-engineer.yaml` with `backend/seed/skills/academic-visual-engineer.yaml` in one clean seed/policy cutover:

```yaml
schema_version: worker_skill.v1
id: academic-visual-engineer
version: 1
enabled: true
role_hint: Academic visual engineer for reproducible figures, structured diagrams and reviewed illustrations
instructions:
  - Convert the user goal and verified Prism/Mission context into one bounded AcademicFigureBrief.
  - Preserve data, units, uncertainty, scientific invariants and accepted terminology; never invent evidence, results or citations.
  - Route evidence figures to reproducible code or structured renderers.
  - Use gpt-image-2 only for explanatory or decorative visuals and use hybrid rendering when exact labels are required.
  - Capture scripts, renderer versions, source refs, manifests, commands and hashes for every reproducible visual.
  - Prefer one strong candidate; request variants only when comparison materially helps.
  - Return source refs, warnings, caption and alt-text candidates with every visual.
allowed_tool_groups: [workspace_read, academic_visual_render]
input_contract: {type: object}
output_contract:
  type: object
  required: [summary, evidence_refs, artifact_refs, warnings]
quality_focus: [data_consistency, scientific_fidelity, reproducibility, visual_hierarchy, label_accuracy, accessibility, provenance]
```

This skill is compact guidance, not a lifecycle or routing owner. WorkspaceAgent can call the same visual tool directly for a bounded request. It spawns this worker when visual planning, code authoring, multi-panel composition, iterative critique, or several coordinated outputs justify isolated context.

`figure-table-engineer` is deleted after every relevant MissionPolicy points to `academic-visual-engineer`. There is no alias or fallback skill id.

All six academic workspace policies may pin `academic_visual_render` and `academic-visual-engineer`. Their stage contracts still decide whether a visual is relevant and what quality/evidence criteria apply. Merely making the tool available must not cause the agent to generate decorative figures unprompted.

## Canonical Tool

Register one strategy-neutral candidate tool in `backend/src/tools/mission/catalog.py`:

```text
tool id: academic_visual.render_candidate
tool group: academic_visual_render
kind: WRITE_CANDIDATE
side effect: IDEMPOTENT
allowed callers: WorkspaceAgent, Subagent
network profile: academic_visual_scoped
model: none for deterministic routes; gpt-image-2 for llm_image/hybrid only
timeout: strategy-bounded
payload limit: bounded typed request
```

The model-facing input is a discriminated union. The renderer payload must agree with `brief.figure_spec.strategy`:

```python
class CodeVisualPayload(BaseModel):
    kind: Literal["code"]
    source_code: str
    script_path: str
    dataset_paths: tuple[str, ...]

class StructuredVisualPayload(BaseModel):
    kind: Literal["structured"]
    source: str
    output_format: Literal["svg", "pdf", "png"]

class GenerativeVisualPayload(BaseModel):
    kind: Literal["generative"]
    quality: Literal["low", "medium", "high", "auto"] = "high"
    size: Literal["1024x1024", "1536x1024", "1024x1536"]

class AcademicVisualRenderInput(BaseModel):
    brief: AcademicFigureBrief
    render: Annotated[
        CodeVisualPayload | StructuredVisualPayload | GenerativeVisualPayload,
        Field(discriminator="kind"),
    ]
```

The tool has one semantic result contract for every strategy. Internally it delegates to Sandbox vNext or the image-provider adapter. The model cannot choose an arbitrary executable, provider URL, binary output path, browser URL, or model id.

For `llm_image` and `hybrid`, the runtime compiles the final provider prompt and calls the standard Images API generation endpoint with `gpt-image-2`. Provider-specific fields do not leak into WorkerSkill or MissionPolicy.

### Operation identity

The stable operation key includes:

```text
mission_id
source_item_seq
figure_id
brief_hash
context_hash
render_contract_version and prompt_contract_version when generative
renderer_id and renderer_version
source_code/source/asset/prompt semantic hash
dataset and source content hashes
provider_model, quality and size when generative
variant_ordinal
```

A retry with the same key returns the existing valid receipt/candidate. Changing the brief or requesting regeneration creates a new key and supersedes the old review item.

### Typed failures

```text
invalid_figure_strategy
insufficient_visual_context
dataset_unavailable
renderer_unavailable
renderer_dependency_denied
sandbox_execution_failed
expected_output_missing
reproducibility_manifest_invalid
provider_rate_limited
provider_auth_or_config
provider_timeout
provider_invalid_payload
image_decode_failed
image_policy_rejected
preview_store_unavailable
quality_gate_failed
```

The UI translates these into useful recovery actions. It must not show provider exception strings as the primary user message.

## Academic Visual Runtime

Create one narrow `backend/src/academic_visual_runtime/` module:

```text
contracts.py                typed brief/render union/candidate/receipt
context.py                  bounded Prism/Mission context assembler
router.py                   deterministic FigureSpec strategy validation
runtime.py                  candidate orchestration and unified receipt
validation.py               shared artifact/content/quality validation
manifest.py                 FigureArtifactManifest and reproducibility receipt
renderers/chart.py          Matplotlib/Seaborn/Plotly Sandbox adapter
renderers/structured.py     Graphviz Sandbox adapter
renderers/schematic.py      Python simulation and geometry adapter
renderers/image_provider.py gpt-image-2 Images API adapter
renderers/overlay.py        deterministic exact-label composition
prompt_compiler.py          versioned generative-image prompt contract
```

`AcademicVisualRuntime` composes existing `SandboxRuntime`; it does not create another shell/container/session abstraction. Every deterministic route must use pinned compilers, approved output roots, bounded stdout/stderr, read-before-write, file-change receipts and the existing Sandbox artifact registration boundary.

The image-provider adapter must:

- use server-side credentials and the configured OpenAI-compatible base URL;
- allow only `gpt-image-2`;
- enforce endpoint, timeout, response-size and retry limits;
- never expose the API key to the model, browser, Prism or Sandbox;
- accept no arbitrary URL from a model tool call;
- verify MIME, decodeability, dimensions, alpha mode and content hash;
- strip EXIF and nonessential metadata before preview storage;
- redact or externalize oversized provider responses;
- emit a typed ToolOrchestrator receipt with cost/latency metadata where available.

`academic_visual_runtime` is an infrastructure adapter behind the canonical tool. It is not a direct WorkspaceAgent dependency and does not own Mission lifecycle, policy, review, assets, or Prism writes.

## Preview Storage

Implement a concrete `MissionPreviewStore` behind the existing `PreviewObjectStore` protocol. Generalize the protocol payload to support typed binary preview descriptors; do not place image/PDF/SVG bytes in `preview_json`.

Sandbox-generated candidates remain referenced by their fenced `sandbox_artifact_ref`; the runtime may place a bounded rasterized preview in `MissionPreviewStore` for browser display. Provider-generated candidates live only in `MissionPreviewStore` until accepted. Both routes produce the same `AcademicVisualCandidate` and review projection.

Required behavior:

- private, workspace-authorized object storage;
- content-addressed object key;
- short TTL for pending/rejected/superseded variants;
- bounded maximum bytes, pages and dimensions;
- hash verification on every read;
- signed or authenticated gateway streaming route;
- deletion after commit or terminal review grace period;
- reconciler cleanup for orphaned objects;
- no new database table.

`MissionReviewItem.preview_ref`, `preview_hash`, and `preview_expires_at` remain the persistent pointer and integrity boundary. `preview_json` stores bounded display metadata only.

The current `PreviewObjectStore.read() -> dict` contract should become a typed preview-envelope read, or expose separate metadata and byte-stream methods. Do not encode binary visual artifacts into the existing JSON hash helper.

## Review And Commit

### Candidate review item

Every candidate creates one `MissionReviewItem` with:

```text
target_kind: workspace_asset
target_ref: null for a new asset
risk_level: derived from evidence level and strategy
review_required_reason: academic visual output requires visual confirmation
preview_ref or sandbox_artifact_ref: candidate bytes
preview_json:
  figure brief summary
  figure type, strategy, evidence level and intended use
  caption and alt-text candidates
  labels, units, datasets and source refs
  renderer/model and reproducibility status
  AI-generated illustration marker when applicable
  warnings and quality findings
```

Add `visual_output` to `ReviewRiskCategory` and the non-bypassable review set. Every visual candidate is pending manual visual confirmation, regardless of review mode. Evidence/statistical/reproducibility risks compose with `visual_output`; medical, patent, safety-critical, claim-bearing, or generative explanatory visuals may be escalated to high risk. Review mode never auto-commits a visual into a WorkspaceAsset or Prism.

Available actions:

```text
accept
reject
regenerate
adjust brief
```

`adjust brief` is a steer command that supersedes the current item and produces a new candidate. It need not become a new persisted review status.

### Asset commit

Accepting a candidate creates one `MissionCommit` and materializes one `WorkspaceAssetCreatePayload` through the Asset domain. Metadata includes:

```text
generated_by: wenjin_academic_visual
renderer_id
renderer_version
provider_model if generative
prompt_contract_version and prompt_hash if generative
source_code_hash and reproducibility_ref if deterministic
context_hash
content_hash
dimensions
quality if generative
figure_type
strategy
evidence_level
source_refs
dataset_refs
mission_id
source_item_seq
overlay_manifest_hash if hybrid
ai_generated: true only for llm_image/hybrid
```

The durable asset stores the final validated visual artifact and, where applicable, references its reproducibility bundle. Full scripts, raw prompts and datasets are not duplicated in the asset row; bounded summaries, durable refs and hashes are sufficient for audit. Sensitive context must not be recoverable from metadata.

### Prism insertion is a second atomic item

Visual acceptance and Prism insertion are separate domain writes:

1. commit the accepted visual as a WorkspaceAsset;
2. build a Prism change against the latest file revision using the asset ref, caption, alt text and figure placement;
3. show the exact document diff in a new MissionReviewItem;
4. apply through the existing Prism read-before-write materializer.

This avoids a distributed asset-plus-document transaction. A successful asset commit remains valid if Prism changed concurrently. A stale Prism base revision supersedes only the insertion item and generates a new preview; it never rerenders or duplicates the visual.

## Quality Gates

### 1. Brief completeness

Required before rendering:

- intended use and figure purpose;
- supported figure type and strategy;
- scientific invariants;
- exact labels and language;
- source/context refs;
- forbidden elements;
- target layout/aspect ratio.

### 2. Technical asset validity

Required before review item creation:

- Sandbox or pinned provider operation completed at a verified boundary;
- output decodes/renders and is nonblank;
- expected output path, allowed MIME, dimensions/pages and byte size are valid;
- scripts and declared outputs match the manifest for deterministic routes;
- dataset/source hashes and the Sandbox operation receipt are present when required;
- generated raster metadata is stripped and channel state is valid;
- preview hash matches stored bytes.

### 3. Academic visual fidelity

The WorkspaceAgent and strategy-aware acceptance contract check the rendered candidate against the brief and verified source context:

- required concepts are present;
- prohibited concepts and invented results are absent;
- plotted values, axes, units, legends, uncertainty and sample definitions match their source data;
- structured diagrams preserve declared nodes, edges, direction and grouping;
- topology/directionality matches the accepted method description;
- labels are exact and legible;
- visual hierarchy works at intended print/display size;
- no watermark, fake citation, fake axis, pseudo-text or unexplained iconography;
- color does not carry meaning without a redundant cue;
- caption and alt text match the visible content.

Deterministic receipt, manifest, source, and reproducibility checks own the hard boundary. An optional diagnostic worker may identify a concrete defect and trigger another generation attempt, but it cannot pass or reject the stage, convert pixels into evidence, or replace user approval for a protected write.

### 4. Prism placement

Required before document commit:

- current base revision/hash verified;
- figure number and caption convention valid;
- cross-reference and asset path valid;
- alt text present;
- surrounding prose does not overclaim the illustration;
- layout fits the document target.

Stage progression may require an accepted visual or accepted Prism insertion only when the Mission's stage contract explicitly names that outcome. Visual generation must not silently become a universal completion requirement.

## Frontend

### Chat

- Show `正在整理图表需求`, `正在绘制`, `正在检查`, and `待你确认` as plain progress states. For long computations, use the more specific `正在计算数据` or `正在渲染图表`.
- Show a compact `学术视觉设计` chip that opens the Mission Console.
- Keep the composer usable while a candidate is generated unless Mission policy requires a user answer.
- Return failures with recovery actions such as `调整描述`, `改用结构图`, or `稍后重试`.

### Mission Console

The review surface displays:

- large responsive raster/SVG/PDF preview with zoom;
- one candidate by default;
- optional side-by-side variant comparison when explicitly requested;
- purpose, strategy, labels, caption, alt text, data/source summary, reproducibility state and warnings;
- `采用`, `调整后重做`, and `不保留` actions;
- after asset acceptance, a separate `插入写作台` document-diff action.

Internal terms such as `MissionReviewItem`, provider payload, operation receipt, `blocked`, or raw risk enums are not primary UI copy.

### Prism

- A selection action may launch the chat-native flow with verified context refs.
- Accepted assets appear in the workspace asset picker.
- Prism never embeds a transient preview URL.
- Insertion uses a durable asset ref and reviewed document change.

## Retention And Cost

- Render one candidate by default.
- Render multiple variants only when requested or when the first candidate fails a visual gate and policy permits a bounded retry. Data/result routes normally revise code rather than generate aesthetic variants.
- Pending previews use a short configurable TTL; active review access may refresh within a hard maximum lifetime.
- Rejected and superseded previews are removed after a short grace period.
- Successful commit removes the transient preview after the durable asset hash is verified.
- Keep only accepted asset bytes, referenced reproducibility artifacts, MissionItem/MissionCommit audit, hashes, renderer/model refs, and bounded metadata.
- Sandbox and provider budget is reserved before execution and settled from the tool receipt. Retries under the same operation key are not double charged by Wenjin.

## Security And Trust

1. Treat Prism/source/user text as untrusted quoted context.
2. Execute code/structured/browser routes only through Sandbox vNext with pinned renderers and approved paths.
3. Permit only the configured provider host and Images API route for `llm_image`/`hybrid`.
4. Do not pass workspace filesystem paths or object-store credentials to the provider.
5. Enforce request/output limits before script execution or base64 decoding can exhaust resources.
6. Strip EXIF and hidden metadata from generated images and reject active content in SVG/PDF previews.
7. Mark committed output as AI-generated in provenance when applicable, even if UI disclosure is compact.
8. Reject requests that fabricate experimental observations, clinical imaging, product screenshots, signatures, official seals, or other misleading evidence.
9. Do not let any visual strategy bypass citation, claim, evidence, statistics, reproducibility, patent, or Prism review rules.

## Data And Migration

No schema migration is required for the first implementation.

Reuse:

- `mission_runs`, `mission_items`, `mission_review_items`, `mission_commits`;
- `worker_skills` and `mission_policies`;
- existing model catalog with `gpt-image-2` as the only generative image model;
- existing Sandbox operation, environment, artifact and reproducibility receipts;
- Workspace Asset domain;
- Prism file/version domain;
- existing tool operation/receipt ownership.

Add runtime/storage adapters and contracts, not persistent tables. If the existing Workspace Asset metadata cannot represent the provenance fields, extend its typed metadata contract without adding visual-strategy-specific columns.

Development cutover rules apply: remove `figure-table-engineer` in the same seed/policy cutover; no old `sandbox.generate_figure`, `imagegen`, or skill compatibility alias; no alternate visual tool route; no dual preview storage.

## Implementation Plan

### Phase 1: contracts and routing

1. Extend `FigureType` with the four missing generative types and add strategy/exact-label invariants to `FigureSpec` without creating a second taxonomy.
2. Add typed academic brief, discriminated render input, context-ref, candidate and receipt contracts.
3. Implement and test deterministic strategy routing across every current `FigureStrategy`.
4. Replace `figure-table-engineer` with `academic-visual-engineer` and update all relevant Mission policies atomically.
5. Add `visual_output` to non-bypassable review risks and update every seeded policy in the same cutover.

### Phase 2: deterministic renderers and manifests

1. Implement chart, structured diagram and schematic/simulation adapters over Sandbox vNext.
2. Produce one canonical `FigureArtifactManifest` with scripts, data/source refs, commands, hashes and renderer versions.
3. Register `academic_visual.render_candidate` and `academic_visual_render` in the canonical catalog/policy loader.
4. Prove WorkspaceAgent and Subagent callers receive the same schema, policy and receipt behavior.

### Phase 3: image2, preview and quality

1. Implement the narrow `gpt-image-2` adapter, prompt compiler and deterministic label overlay.
2. Implement shared MIME/decode/dimension/page/metadata validation.
3. Implement `MissionPreviewStore` and authenticated raster/SVG/PDF preview streaming.
4. Add operation identity, lease fencing, receipts, budget and typed failure mapping for every strategy.
5. Add strategy-aware academic quality gates; optional diagnostic findings may guide regeneration but have no acceptance authority and cannot replace explicit user approval for protected writes.

### Phase 4: review, asset and Prism

1. Create MissionReviewItems from unified candidate receipts and materialize accepted WorkspaceAssets with provenance.
2. Build separate Prism insertion items with optimistic revision checks.
3. Add cleanup reconciliation for expired/orphaned previews and superseded Sandbox candidates.

### Phase 5: frontend and acceptance

1. Add Chat progress/chip states without a new frontend lifecycle store.
2. Add responsive raster/SVG/PDF preview, zoom, regenerate/adjust and acceptance UI to Mission Console.
3. Add Prism selection trigger and reviewed insertion diff.
4. Run unit, integration, browser, security, retention, real-Sandbox and real-provider acceptance tests.

## Test Matrix

### Unit

- data/result/evidence requests cannot route to `gpt-image-2`;
- exact structured diagrams route to deterministic renderers;
- render payload discriminator and FigureSpec strategy must agree;
- chart routes require source code, datasets and expected outputs;
- structured routes accept only renderer-specific source and pinned output formats;
- exact labels select hybrid rendering;
- prompt compiler escapes untrusted Prism instructions;
- provider model is fixed to `gpt-image-2`;
- operation key changes only when semantic generation inputs change;
- output byte/decode/dimension limits fail with typed errors;
- rejected metadata cannot leak full source text or credentials.

### Integration

- verified Prism selection -> brief -> each strategy adapter -> unified candidate -> review item;
- Matplotlib fixture -> Sandbox artifact + script/data/reproducibility refs -> review -> asset;
- Graphviz fixture -> SVG/PDF candidate -> sanitized browser preview -> review -> asset;
- fake image response -> transient preview ref -> review item;
- duplicate delivery returns the same candidate receipt;
- accepted candidate -> one WorkspaceAsset and one MissionCommit;
- rejected/superseded candidate never becomes an asset;
- expired preview cannot commit and can be regenerated;
- accepted asset -> separate Prism insertion review -> successful write;
- stale Prism revision supersedes insertion without duplicating the asset;
- hybrid output preserves exact labels and records overlay manifest hash;
- cleanup removes orphaned previews while preserving durable audit metadata.

### Browser

1. Ask in Chat for a data chart from a registered workspace dataset and verify the code/Sandbox route.
2. Ask for a method flow and verify the structured renderer route.
3. Ask for a mechanism illustration using current Mission context and verify the image2/hybrid route.
4. Observe meaningful render progress while the right panel remains optional.
5. Open Mission Console and inspect strategy, preview, source/data summary, labels, caption, alt text and reproducibility state.
6. Adjust one constraint and rerender; verify the old candidate is superseded.
7. Accept the selected candidate and verify it appears as a durable workspace asset.
8. Request insertion into the active Prism section, inspect the document diff, and accept.
9. Reload the workspace and verify the asset and Prism reference persist while discarded previews do not.

### Real-provider acceptance

- `gpt-image-2` completes through the configured Images API endpoint;
- generated bytes pass all validators and render in Chrome;
- timeout/rate-limit/auth errors become typed recoverable states;
- no provider key or raw base64 payload appears in logs, SSE, MissionItem or browser responses;
- cost, latency, model, prompt version and content hash are present in the receipt.

## Release Gates

- Backend tests, Ruff, compileall, Alembic head and mission cutover gate pass.
- Frontend typecheck, Vitest, build and Mission browser chain pass.
- One real-provider generation/preview/accept/asset/Prism flow passes.
- Real-Sandbox Matplotlib and Graphviz fixtures produce valid manifests and previews.
- One evidence-figure request proves deterministic routing and reproducibility enforcement.
- Preview object cleanup and authorization tests pass.
- Static scan finds no legacy image provider/model, direct workspace write, raw base64 persistence, or alternate preview owner.
- Architecture docs are updated only when the production composition is complete.

## Historical Design Disposition

Commit `08f6cfc1` previously introduced:

- `Research Figure Generation Capability Design` and its implementation plan;
- a unified `sandbox.generate_figure` Harness tool;
- code, structured and LLM-image FigureSpec routes;
- `FigureArtifactManifest`, Sandbox artifacts and frontend previews;
- extensive contract, tool and browser tests.

The Mission cutover in `8c238353` correctly removed the old Chat Agent -> capability -> Lead Agent/Harness implementation. This spec deliberately recovers only the durable design strengths:

| Historical element | Disposition |
|---|---|
| One FigureSpec across visual strategies | retain as SSOT |
| Code-first evidence figures | retain and strengthen with Sandbox vNext receipts |
| Unified figure manifest and preview | retain behind Mission candidate/review contracts |
| Server-side image provider | retain as one adapter, fixed to `gpt-image-2` |
| Chat -> capability -> Lead Agent graph | reject; WorkspaceAgent is the single entry/leader |
| Harness-owned lifecycle and result cards | reject; MissionRuntime and MissionView own lifecycle/projection |
| Direct materialization into old Sandbox session paths | reject; candidate preview then MissionCommit |
| Visible figure capability or fixed workflow | reject; chat-native tool plus optional WorkerSkill |

The old files are reference material in Git history, not runtime dependencies. They must not be restored or wrapped.

## Locked Decisions

1. Wenjin owns one `AcademicVisualRuntime`; it does not import Codex's runtime skill implementation or revive the old Harness tool.
2. The public agent surface is one `academic_visual.render_candidate` tool shared by WorkspaceAgent and permitted Subagents.
3. `academic-visual-engineer` is optional bounded guidance; it is not a capability graph or lifecycle owner.
4. `FigureSpec` is the single taxonomy and routing contract across code, structured, capture, upload, image and hybrid strategies.
5. `gpt-image-2` is the only generative image model.
6. Generated imagery cannot be evidence-bearing; data/results always require reproducible deterministic routes.
7. Exact labels use deterministic overlay; exact structured diagrams use deterministic renderers.
8. One candidate is rendered by default.
9. `visual_output` is non-bypassable and requires manual visual confirmation before asset commit.
10. Provider bytes and derived browser previews live in TTL preview storage; Sandbox candidates remain behind fenced artifact refs. Neither is stored in database JSON.
11. A committed visual is a WorkspaceAsset with renderer/model and source/reproducibility provenance.
12. Asset acceptance and Prism insertion are separate atomic MissionReviewItems/MissionCommits.
13. Rejected and superseded variants are deleted; there is no durable visual-version-history table.
14. WorkspaceAgent owns navigation, MissionRuntime owns lifecycle, ToolOrchestrator owns execution, Sandbox/provider adapters own rendering, and ReviewCommitRuntime owns writes.
15. `figure-table-engineer` is removed in the cutover; no compatibility aliases, dual routes, provider fallbacks, or visual-specific persistent aggregate are introduced.
