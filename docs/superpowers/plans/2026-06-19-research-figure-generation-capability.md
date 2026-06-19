# Research Figure Generation Capability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a capability-driven, sandbox-centered figure generation loop for data plots, experiment charts, diagrams, and LLM-generated conceptual images.

**Architecture:** Figure generation is routed through Chat Agent -> capability -> Lead Agent / TeamKernel -> figure specialist. Runtime generation happens through a new harness tool `sandbox.generate_figure`, which uses sandbox Python for reproducible code/diagram figures and a server-side image provider for LLM images while materializing outputs back into sandbox artifacts. Existing result-card review and DataService asset/sandbox artifact materialization remain the only commit path.

**Tech Stack:** Python 3.13, Pydantic v2, FastAPI backend, Wenjin native harness, LangGraph/TeamKernel, Docker sandbox, SQLAlchemy/DataService, Next.js 16, React 19, TypeScript.

---

## Reference Spec

Read `docs/superpowers/specs/2026-06-19-research-figure-generation-capability-design.md` before executing this plan.

## File Structure

- Create `backend/src/contracts/figure_generation.py`: typed `FigureSpec`, strategy policy validation, and artifact manifest models.
- Create `backend/tests/contracts/test_figure_generation.py`: contract and validation tests.
- Create `backend/src/agents/harness/figure_generation_tools.py`: harness-facing figure generation orchestration.
- Modify `backend/src/agents/harness/builtins.py`: register `sandbox.generate_figure`.
- Modify `backend/src/agents/harness/langchain_adapter.py`: expose the tool to React subagents.
- Modify `backend/src/agents/harness/policy.py`: derive `sandbox.generate_figure` permission from capability policy.
- Modify `backend/seed/skills/figure-engineer.yaml`: upgrade from planning-only to strategy + generation.
- Modify or add workspace capability seeds under `backend/seed/capabilities/*/`: route figure requests and enable `render_figures`.
- Modify `backend/seed/agent_templates/*.yaml`: let the figure expert use the new sandbox tool where needed.
- Remove or migrate `backend/src/thesis/execution/figure_tool.py`: eliminate the thesis-only product path.
- Modify `frontend/lib/workspace-result-preview.ts`: project figure artifact previews cleanly.
- Modify `frontend/app/(workbench)/workspaces/[id]/components/ResultCard.tsx`: show figure thumbnails, caption, strategy, and provenance summary.
- Add backend and frontend tests listed in each task.

---

### Task 1: Figure Generation Contracts

**Files:**
- Create: `backend/src/contracts/figure_generation.py`
- Test: `backend/tests/contracts/test_figure_generation.py`

- [ ] **Step 1: Write failing contract tests**

```python
import pytest
from pydantic import ValidationError

from src.contracts.figure_generation import FigureArtifactManifest, FigureSpec


def test_data_plot_rejects_llm_image_strategy() -> None:
    with pytest.raises(ValidationError, match="data figures must use code"):
        FigureSpec(
            figure_id="fed_llm_curve",
            title="Federated LLM Accuracy",
            figure_type="data_plot",
            strategy="llm_image",
            purpose="Show benchmark trend",
            output_targets=["/workspace/outputs/figures/fed_llm_curve/figure.png"],
        )


def test_matplotlib_figure_spec_accepts_workspace_output() -> None:
    spec = FigureSpec(
        figure_id="fed_llm_curve",
        title="Federated LLM Accuracy",
        figure_type="experiment_plot",
        strategy="matplotlib",
        purpose="Show benchmark trend",
        output_targets=["/workspace/outputs/figures/fed_llm_curve/figure.png"],
        dataset_paths=["/workspace/datasets/results.csv"],
    )

    assert spec.strategy == "matplotlib"
    assert spec.output_targets[0].startswith("/workspace/outputs/")


def test_manifest_requires_reviewable_workspace_path() -> None:
    with pytest.raises(ValidationError, match="reviewable workspace artifact"):
        FigureArtifactManifest(
            figure_id="bad",
            figure_type="graphical_abstract",
            strategy="llm_image",
            primary_path="/workspace/.wenjin/cache/secret.png",
        )
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run:

```bash
cd backend
PYTHONPATH=. .venv/bin/python -m pytest tests/contracts/test_figure_generation.py -q
```

Expected: import failure for `src.contracts.figure_generation`.

- [ ] **Step 3: Implement the contract**

Implement:

```python
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

FigureType = Literal[
    "data_plot",
    "experiment_plot",
    "statistical_chart",
    "architecture_diagram",
    "method_flow",
    "mechanism_illustration",
    "graphical_abstract",
    "patent_drawing",
    "table_visual",
    "other",
]

FigureStrategy = Literal[
    "matplotlib",
    "seaborn",
    "plotly_static",
    "mermaid",
    "graphviz",
    "tikz",
    "llm_image",
    "hybrid",
]

CODE_REQUIRED_TYPES = {"data_plot", "experiment_plot", "statistical_chart", "table_visual"}
REVIEWABLE_ROOTS = ("/workspace/outputs/", "/workspace/reports/")


class FigureSpec(BaseModel):
    schema: str = "wenjin.figure_generation.spec.v1"
    figure_id: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=240)
    figure_type: FigureType
    strategy: FigureStrategy
    purpose: str = Field(min_length=1, max_length=1000)
    inputs: dict[str, object] = Field(default_factory=dict)
    output_targets: list[str] = Field(default_factory=list)
    caption: str | None = None
    alt_text: str | None = None
    dataset_paths: list[str] = Field(default_factory=list)
    provenance: dict[str, object] = Field(default_factory=dict)
    quality_checks: list[str] = Field(default_factory=list)

    @field_validator("output_targets", "dataset_paths")
    @classmethod
    def _validate_paths(cls, paths: list[str]) -> list[str]:
        for path in paths:
            if path.startswith("/workspace/.wenjin") or "/.." in path:
                raise ValueError("unsafe workspace path")
        return paths

    @model_validator(mode="after")
    def _validate_strategy(self) -> "FigureSpec":
        if self.figure_type in CODE_REQUIRED_TYPES and self.strategy in {"llm_image", "hybrid"}:
            raise ValueError("data figures must use code generation strategies")
        for path in self.output_targets:
            if not path.startswith(REVIEWABLE_ROOTS):
                raise ValueError("output target must be a reviewable workspace artifact")
        return self


class FigureArtifactManifest(BaseModel):
    schema: str = "wenjin.figure_generation.artifact.v1"
    figure_id: str = Field(min_length=1, max_length=120)
    figure_type: FigureType
    strategy: FigureStrategy
    primary_path: str
    source_script: str | None = None
    source_prompt: str | None = None
    dataset_paths: list[str] = Field(default_factory=list)
    caption_path: str | None = None
    alt_text_path: str | None = None
    created_by: str | None = None
    content_hash: str | None = None
    review_notes: str | None = None

    @field_validator("primary_path")
    @classmethod
    def _primary_path_reviewable(cls, path: str) -> str:
        if not path.startswith(REVIEWABLE_ROOTS):
            raise ValueError("primary_path must be a reviewable workspace artifact")
        return path
```

- [ ] **Step 4: Run tests and verify pass**

Run:

```bash
cd backend
PYTHONPATH=. .venv/bin/python -m pytest tests/contracts/test_figure_generation.py -q
```

Expected: all tests pass.

---

### Task 2: Harness Figure Tool

**Files:**
- Create: `backend/src/agents/harness/figure_generation_tools.py`
- Modify: `backend/src/agents/harness/builtins.py`
- Modify: `backend/src/agents/harness/langchain_adapter.py`
- Modify: `backend/src/agents/harness/policy.py`
- Test: `backend/tests/agents/harness/test_figure_generation_tool.py`

- [ ] **Step 1: Write tool permission and code-strategy tests**

Test cases:

```python
import pytest

from src.agents.harness.contracts import HarnessPolicy
from src.agents.harness.figure_generation_tools import FigureGenerationTools


@pytest.mark.asyncio
async def test_generate_figure_requires_permission(harness_context) -> None:
    tool = FigureGenerationTools(context=harness_context, policy=HarnessPolicy(permissions=frozenset()))

    with pytest.raises(PermissionError, match="sandbox.generate_figure"):
        await tool.generate_figure(
            spec={
                "figure_id": "curve",
                "title": "Curve",
                "figure_type": "experiment_plot",
                "strategy": "matplotlib",
                "purpose": "show results",
                "output_targets": ["/workspace/outputs/figures/curve/figure.png"],
            },
            source_code="print('x')",
        )


@pytest.mark.asyncio
async def test_matplotlib_strategy_uses_run_python_and_registers_figure(monkeypatch, harness_context) -> None:
    calls = []

    async def fake_run_python(self, **kwargs):
        calls.append(kwargs)
        return {
            "ok": True,
            "generated_artifacts": [
                {
                    "schema": "wenjin.sandbox.generated_artifact_candidate.v1",
                    "path": "/workspace/outputs/figures/curve/figure.png",
                    "artifact_kind": "figure",
                    "review_surface": "sandbox_artifact",
                    "materialization_status": "candidate",
                    "sandbox_job_id": "job-1",
                }
            ],
        }

    monkeypatch.setattr("src.agents.harness.figure_generation_tools.SandboxExecutionTools.run_python", fake_run_python)

    tool = FigureGenerationTools(
        context=harness_context,
        policy=HarnessPolicy(permissions=frozenset({"sandbox.generate_figure", "sandbox.run_python"})),
    )
    result = await tool.generate_figure(
        spec={
            "figure_id": "curve",
            "title": "Curve",
            "figure_type": "experiment_plot",
            "strategy": "matplotlib",
            "purpose": "show results",
            "output_targets": ["/workspace/outputs/figures/curve/figure.png"],
        },
        source_code="import matplotlib.pyplot as plt\nplt.plot([1,2],[3,4])\nplt.savefig('/workspace/outputs/figures/curve/figure.png')",
    )

    assert calls
    assert result["generated_artifacts"][0]["artifact_kind"] == "figure"
```

- [ ] **Step 2: Implement `FigureGenerationTools.generate_figure`**

Implementation requirements:

- Validate `spec` with `FigureSpec`.
- Require `sandbox.generate_figure` permission.
- For code strategies, require `source_code` and delegate to `SandboxExecutionTools.run_python`.
- For structured diagram strategies, render through sandbox Python using explicit package hints.
- For `llm_image`, call a server-side adapter and write image bytes to sandbox using controlled file APIs.
- Return bounded metadata with `generated_artifacts`, `figure_spec`, and `figure_manifest`.

- [ ] **Step 3: Register the tool**

Add `sandbox.generate_figure` in:

- `backend/src/agents/harness/builtins.py`
- `backend/src/agents/harness/langchain_adapter.py`
- `backend/src/agents/harness/policy.py`

Permission derivation rule:

```python
if "render_figures" in sandbox_policy.get("allowed_operations", []):
    tools.append("sandbox.generate_figure")
```

- [ ] **Step 4: Run harness tests**

Run:

```bash
cd backend
PYTHONPATH=. .venv/bin/python -m pytest tests/agents/harness/test_figure_generation_tool.py tests/agents/harness/test_scheduler_and_python_tool.py -q
```

Expected: all tests pass.

---

### Task 3: Capability, Skill, and Expert Seeds

**Files:**
- Modify: `backend/seed/skills/figure-engineer.yaml`
- Modify: `backend/seed/agent_templates/*.yaml`
- Add or modify: `backend/seed/capabilities/sci/*figure*.yaml`
- Add or modify: `backend/seed/capabilities/thesis/*figure*.yaml`
- Modify existing proposal, software copyright, and patent diagram/drawing capabilities that already declare `render_figures` so they use the shared FigureSpec and sandbox artifact flow.
- Test: `backend/tests/services/test_capability_schema.py`

- [ ] **Step 1: Upgrade `figure-engineer` role prompt**

Add rules covering:

- Build a `FigureSpec` before generation.
- Pick code strategies for data plots.
- Pick Mermaid/Graphviz/TikZ for structured diagrams.
- Use LLM image only for conceptual or graphical abstract figures.
- Register all outputs as reviewable sandbox artifacts.
- Never write canonical workspace rooms directly.

- [ ] **Step 2: Grant the figure expert the right tools**

For the figure expert template, include:

```yaml
allowed_tools:
  - sandbox.list_dir
  - sandbox.read_file
  - sandbox.register_artifact
  - sandbox.run_python
  - sandbox.generate_figure
risk_profile:
  filesystem: sandbox_only
```

- [ ] **Step 3: Add thin workspace capabilities**

Each visible capability should include:

```yaml
sandbox_policy:
  mode: required
  profiles:
    - visualization
  allowed_operations:
    - run_python
    - install_python_packages
    - render_figures
review_policy:
  default_targets:
    - sandbox_artifact
  require_user_acceptance: true
quality_gates:
  - result_card_review_before_commit
  - figure_purpose_explicit
  - data_dependencies_marked
  - caption_and_callout_required
```

- [ ] **Step 4: Run seed schema tests**

Run:

```bash
cd backend
PYTHONPATH=. .venv/bin/python -m pytest tests/services/test_capability_schema.py tests/services/test_capability_loader.py -q
```

Expected: all tests pass.

---

### Task 4: Remove Old Thesis Figure Product Path

**Files:**
- Delete or empty product exports from: `backend/src/thesis/execution/figure_tool.py`
- Modify: `backend/src/thesis/execution/__init__.py`
- Test: affected imports found by search.

- [ ] **Step 1: Find callers**

Run:

```bash
rg -n "generate_figure|FigureStrategy|figure_tool" backend tests
```

Expected: callers are either old exports or tests that should be migrated.

- [ ] **Step 2: Remove the old path**

Remove thesis-only generation export from `backend/src/thesis/execution/__init__.py`. Delete `backend/src/thesis/execution/figure_tool.py` if it has no valid callers.

- [ ] **Step 3: Verify no stale imports remain**

Run:

```bash
rg -n "from .*figure_tool|generate_figure\\(|FigureStrategy" backend tests
```

Expected: no thesis product path remains.

---

### Task 5: Figure Preview UX

**Files:**
- Modify: `frontend/lib/workspace-result-preview.ts`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/ResultCard.tsx`
- Test: frontend unit tests around result preview and result cards.

- [ ] **Step 1: Add a preview test for figure artifacts**

Expected projection:

```ts
expect(preview.kind).toBe("figure");
expect(preview.title).toContain("Federated LLM Accuracy");
expect(preview.previewPath).toBe("/workspace/outputs/figures/fed_llm_curve/figure.png");
expect(preview.metadata.strategy).toBe("matplotlib");
```

- [ ] **Step 2: Render figure candidate cards**

Default card content:

- thumbnail when `mime_type` starts with `image/`;
- title;
- caption summary;
- strategy label;
- provenance summary;
- accept/regenerate/ignore actions.

- [ ] **Step 3: Run frontend checks**

Run:

```bash
cd frontend
npm run typecheck
npx vitest run
```

Expected: typecheck and unit tests pass.

---

### Task 6: End-to-End Verification

**Files:**
- Add or update backend integration tests for mock figure capability execution.
- Add browser test under `frontend/tests/e2e/v2/`.

- [ ] **Step 1: Backend mock capability run**

Test behavior:

- user request routes to a figure capability;
- figure specialist creates `FigureSpec`;
- `sandbox.generate_figure` produces a `figure` artifact candidate;
- result-card review item includes the artifact.

- [ ] **Step 2: Browser flow**

Browser scenario:

1. Open a SCI workspace.
2. Ask: `根据这些实验结果画一张对比曲线图，并给出论文图注。`
3. Verify the workbench shows a figure candidate.
4. Open preview.
5. Accept the artifact.
6. Verify the accepted asset appears in document/library preview surfaces.

- [ ] **Step 3: Full verification**

Run:

```bash
cd backend
PYTHONPATH=. .venv/bin/python -m pytest tests/contracts/test_figure_generation.py tests/agents/harness/test_figure_generation_tool.py tests/services/test_capability_schema.py -q

cd ../frontend
npm run typecheck
npx vitest run
```

Expected: all selected checks pass.

---

## Self-Review Checklist

- [ ] Figure requests route through capability execution, not raw chat middleware.
- [ ] `sandbox.generate_figure` is permission-gated by `render_figures`.
- [ ] Data and experiment figures cannot use `llm_image`.
- [ ] Image provider secrets stay server-side.
- [ ] All generated user-facing files land under `/workspace/outputs` or `/workspace/reports`.
- [ ] Result-card review is required before DataService commit.
- [ ] Old thesis-only figure helper is removed as a product path.
- [ ] UI shows figures as previewable artifacts, not raw logs.
