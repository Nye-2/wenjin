# Academic Harness v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Wenjin Academic Harness v1 as the shared contract and runtime substrate for academic ACI tools, expert reports, review packets, quality surfaces, and long-task context compaction.

**Architecture:** Keep the existing Chat Agent -> `launch_feature` -> `ExecutionRecord` -> Lead Agent / TeamKernel -> harness -> ResultCard / Prism chain. Add contracts and projections inside existing harness, TeamKernel, task-report, DataService review-item, and RunView boundaries. Do not add a second runner, public sandbox endpoint, frontend local router, or parallel execution store.

**Tech Stack:** Python 3.13, Pydantic v2, dataclasses, FastAPI/DataService contracts, LangGraph TeamKernel runtime, TypeScript, Next.js 16, React 19, Vitest, Playwright.

---

## Scope Check

The design spec covers six tightly coupled harness workstreams. They are not independent products: Review Packet depends on ExpertReport; quality surfaces consume expert evidence and review items; context compaction protects the same evidence identifiers; frontend projection reads the same execution/result contracts. This plan keeps one implementation sequence, with frequent commits and tests, rather than six divergent plans.

First release scope:

- Implement core contracts.
- Migrate SCI first-wave capabilities.
- Project review packet and quality highlights in the existing workbench UI.
- Add deterministic tests and one browser path.

Deferred release scope:

- Full migration of thesis, proposal, patent, and software-copyright capabilities.
- User-visible approval prompts for `ask` permission.
- LLM-judged diagnostic rubrics beyond deterministic surfaces.

## File Structure

### Backend Contracts

- Modify `backend/src/contracts/research_evidence.py`
  - Owns canonical research surface names and enforcement parsing.
- Modify `backend/src/agents/harness/research_eval_surfaces.py`
  - Re-exports research surface helpers for harness runtime.
- Modify `backend/src/agents/harness/contracts.py`
  - Owns Academic ACI observation and permission contracts.
- Modify `backend/src/agents/contracts/task_report.py`
  - Owns Review Packet contract and TaskReport projection.
- Modify `backend/src/contracts/team_expert.py`
  - Owns ExpertReport v1 plus existing snapshot/preview sanitizers.
- Create `backend/src/agents/harness/research_state.py`
  - Owns compact long-task research state.

### Backend Runtime

- Modify `backend/src/agents/lead_agent/v2/output_mapping.py`
  - Maps ExpertReport envelopes and graph outputs into Review Packet items.
- Modify `backend/src/agents/lead_agent/v2/team/expert_runtime.py`
  - Normalizes member raw outputs into ExpertReport where possible.
- Modify `backend/src/agents/lead_agent/v2/team/kernel.py`
  - Stores expert reports in runtime state and adds review packet to TaskReport.
- Modify `backend/src/agents/lead_agent/v2/team/member_context.py`
  - Injects compact research state and protected quality summaries into later members.
- Modify `backend/src/agents/lead_agent/v2/team/quality_gates.py`
  - Reads the expanded surface registry and enforcement levels.
- Modify `backend/src/agents/harness/research_task_eval.py`
  - Evaluates review-packet completeness and claim/evidence alignment.

### Catalog Seeds

- Modify `backend/seed/capabilities/sci/sci_literature_positioning.yaml`
- Modify `backend/seed/capabilities/sci/research_question_to_paper.yaml`
- Modify `backend/seed/capabilities/sci/sci_empirical_package.yaml`
- Modify `backend/seed/capabilities/sci/reproducibility_audit.yaml`
- Modify selected skills:
  - `backend/seed/skills/query-planner.yaml`
  - `backend/seed/skills/research-scout.yaml`
  - `backend/seed/skills/source-screener.yaml`
  - `backend/seed/skills/literature-synthesizer.yaml`
  - `backend/seed/skills/citation-auditor.yaml`
  - `backend/seed/skills/method-design.yaml`
  - `backend/seed/skills/evidence-analyst.yaml`
  - `backend/seed/skills/reproducibility-auditor.yaml`
  - `backend/seed/skills/manuscript-architect.yaml`
  - `backend/seed/skills/manuscript-writer.yaml`
  - `backend/seed/skills/review-critic.yaml`

### Frontend

- Modify `frontend/lib/execution-run-view.ts`
  - Projects review packet and quality surfaces from execution result/runtime state.
- Modify `frontend/lib/workspace-result-preview.ts`
  - Builds typed previews from Review Packet items.
- Modify `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/useLiveWorkflowViewModel.ts`
  - Uses Review Packet as the primary right-panel review source when present.
- Modify `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/ReviewView.tsx`
  - Renames default review language to “待确认成果” and shows compact trust signals.
- Modify `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/EvidenceView.tsx`
  - Shows source/script/dataset/artifact provenance chips without raw internals.

### Tests

- Modify `backend/tests/agents/harness/test_research_eval_surfaces.py`
- Create `backend/tests/agents/harness/test_academic_aci_contracts.py`
- Create `backend/tests/agents/contracts/test_review_packet.py`
- Modify `backend/tests/contracts/test_team_expert.py`
- Modify `backend/tests/agents/lead_agent/v2/test_output_mapping.py`
- Create `backend/tests/agents/harness/test_research_state.py`
- Modify `backend/tests/agents/lead_agent/v2/test_team_kernel.py`
- Modify `backend/tests/agents/lead_agent/v2/test_team_member_context.py`
- Create `backend/tests/architecture/test_academic_harness_catalog.py`
- Modify `frontend/tests/unit/v2/execution-run-view.test.ts`
- Modify `frontend/tests/unit/v2/live-workflow-view-model.test.ts`
- Modify `frontend/tests/unit/lib/workspace-result-preview.test.ts`
- Modify `frontend/tests/unit/v2/LiveWorkflowPanel.test.tsx`
- Add or extend `frontend/tests/e2e/golden-path.spec.ts`

---

## Task 1: Expand Research Surface Registry

**Files:**

- Modify: `backend/src/contracts/research_evidence.py`
- Modify: `backend/src/agents/harness/research_eval_surfaces.py`
- Modify: `backend/tests/agents/harness/test_research_eval_surfaces.py`

- [ ] **Step 1: Write failing tests for new surfaces and enforcement levels**

Add these tests to `backend/tests/agents/harness/test_research_eval_surfaces.py`:

```python
from src.agents.harness.research_eval_surfaces import (
    required_surface_requirements_from_capability_policy,
    required_surfaces_from_capability_policy,
    validate_research_surface_enforcement,
)


def test_research_surface_registry_accepts_academic_harness_v1_surfaces() -> None:
    surfaces = required_surfaces_from_capability_policy(
        {
            "research_evidence": {
                "required_surfaces": [
                    "claim_evidence_alignment",
                    "experiment_reproducibility",
                    "figure_data_consistency",
                    "review_packet_completeness",
                ]
            }
        }
    )

    assert surfaces == (
        "claim_evidence_alignment",
        "experiment_reproducibility",
        "figure_data_consistency",
        "review_packet_completeness",
    )


def test_surface_enforcement_levels_are_parsed_per_surface() -> None:
    requirements = required_surface_requirements_from_capability_policy(
        {
            "research_evidence": {
                "required_surfaces": ["workflow_trace", "review_packet_completeness"],
                "surface_enforcement": {
                    "workflow_trace": "required_runtime",
                    "review_packet_completeness": "required_final",
                },
            }
        }
    )

    assert [(item.surface, item.enforcement) for item in requirements] == [
        ("workflow_trace", "required_runtime"),
        ("review_packet_completeness", "required_final"),
    ]


def test_surface_enforcement_rejects_unknown_level() -> None:
    try:
        validate_research_surface_enforcement({"workflow_trace": "hard_block"})
    except ValueError as exc:
        assert "unknown research surface enforcement" in str(exc)
        assert "hard_block" in str(exc)
    else:
        raise AssertionError("unknown enforcement level should fail")
```

- [ ] **Step 2: Run the failing tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/harness/test_research_eval_surfaces.py -v
```

Expected before implementation: import failure for `required_surface_requirements_from_capability_policy` or `validate_research_surface_enforcement`.

- [ ] **Step 3: Implement surface registry and enforcement parsing**

In `backend/src/contracts/research_evidence.py`, extend the literal and add the enforcement contract:

```python
from dataclasses import dataclass

ResearchSurface = Literal[
    "literature",
    "experiment",
    "writing",
    "workflow_trace",
    "citation_strength",
    "experiment_interpretation",
    "paper_relevance",
    "statistical_robustness",
    "writing_semantic_preservation",
    "writing_academic_style",
    "output_ref_reuse",
    "claim_evidence_alignment",
    "experiment_reproducibility",
    "figure_data_consistency",
    "review_packet_completeness",
]

ResearchSurfaceEnforcement = Literal["required_runtime", "required_final", "diagnostic"]
KNOWN_RESEARCH_SURFACE_ENFORCEMENT = frozenset(get_args(ResearchSurfaceEnforcement))


@dataclass(frozen=True, slots=True)
class ResearchSurfaceRequirement:
    surface: ResearchSurface
    enforcement: ResearchSurfaceEnforcement = "required_final"


def required_surface_requirements_from_capability_policy(
    capability_policy: dict[str, Any] | None,
    *,
    default: tuple[ResearchSurface, ...] = DEFAULT_RESEARCH_SURFACES,
) -> tuple[ResearchSurfaceRequirement, ...]:
    policy = capability_policy if isinstance(capability_policy, dict) else {}
    research_evidence = policy.get("research_evidence")
    research_evidence = research_evidence if isinstance(research_evidence, dict) else {}
    surfaces = required_surfaces_from_capability_policy(policy, default=default)
    enforcement = validate_research_surface_enforcement(research_evidence.get("surface_enforcement"))
    return tuple(
        ResearchSurfaceRequirement(
            surface=cast(ResearchSurface, surface),
            enforcement=enforcement.get(surface, "required_final"),
        )
        for surface in surfaces
    )


def validate_research_surface_enforcement(value: Any) -> dict[str, ResearchSurfaceEnforcement]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("research_evidence.surface_enforcement must be an object")
    result: dict[str, ResearchSurfaceEnforcement] = {}
    for raw_surface, raw_level in value.items():
        surface = _clean_text(raw_surface)
        level = _clean_text(raw_level)
        if surface not in KNOWN_RESEARCH_SURFACES:
            raise ValueError(f"unknown research evidence surface in surface_enforcement: {surface}")
        if level not in KNOWN_RESEARCH_SURFACE_ENFORCEMENT:
            raise ValueError(f"unknown research surface enforcement: {level}")
        result[surface] = cast(ResearchSurfaceEnforcement, level)
    return result
```

In `backend/src/agents/harness/research_eval_surfaces.py`, re-export the new names:

```python
from src.contracts.research_evidence import (
    DEFAULT_RESEARCH_SURFACES,
    KNOWN_RESEARCH_SURFACE_ENFORCEMENT,
    KNOWN_RESEARCH_SURFACES,
    ResearchSurface,
    ResearchSurfaceEnforcement,
    ResearchSurfaceRequirement,
    normalize_research_surfaces,
    required_surface_requirements_from_capability_policy,
    required_surfaces_from_capability_policy,
    validate_research_surface_enforcement,
    validate_research_surfaces,
)

__all__ = [
    "DEFAULT_RESEARCH_SURFACES",
    "KNOWN_RESEARCH_SURFACE_ENFORCEMENT",
    "KNOWN_RESEARCH_SURFACES",
    "ResearchSurface",
    "ResearchSurfaceEnforcement",
    "ResearchSurfaceRequirement",
    "normalize_research_surfaces",
    "required_surface_requirements_from_capability_policy",
    "required_surfaces_from_capability_policy",
    "validate_research_surface_enforcement",
    "validate_research_surfaces",
]
```

- [ ] **Step 4: Run tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/harness/test_research_eval_surfaces.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/src/contracts/research_evidence.py backend/src/agents/harness/research_eval_surfaces.py backend/tests/agents/harness/test_research_eval_surfaces.py
git commit -m "feat: expand academic research surfaces"
```

---

## Task 2: Add Academic ACI Observation And Permission Contracts

**Files:**

- Modify: `backend/src/agents/harness/contracts.py`
- Create: `backend/tests/agents/harness/test_academic_aci_contracts.py`

- [ ] **Step 1: Write failing contract tests**

Create `backend/tests/agents/harness/test_academic_aci_contracts.py`:

```python
from src.agents.harness.contracts import AcademicACIObservation, AcademicACIPermissionCheck


def test_academic_aci_observation_is_bounded_and_structured() -> None:
    observation = AcademicACIObservation(
        tool="sandbox.run_python",
        status="ok",
        summary="Generated metrics from panel.csv.",
        evidence_refs=("dataset:/workspace/datasets/panel.csv",),
        artifact_refs=("artifact:/workspace/outputs/metrics/result.json",),
        output_refs=("harness-output-ref:exec/node/stdout",),
        warnings=("stdout externalized",),
        provenance={
            "execution_id": "exec-1",
            "node_id": "node-1",
            "workspace_id": "ws-1",
        },
    )

    payload = observation.to_payload()

    assert payload["schema"] == "wenjin.academic_aci.observation.v1"
    assert payload["tool"] == "sandbox.run_python"
    assert payload["status"] == "ok"
    assert payload["artifact_refs"] == ["artifact:/workspace/outputs/metrics/result.json"]
    assert payload["output_refs"] == ["harness-output-ref:exec/node/stdout"]


def test_academic_aci_permission_check_uses_allow_ask_deny() -> None:
    check = AcademicACIPermissionCheck(
        tool="sandbox.generate_figure",
        decision="ask",
        reason="image provider call requires explicit policy permission",
        required_permissions=("sandbox.generate_figure",),
    )

    assert check.to_payload() == {
        "schema": "wenjin.academic_aci.permission_check.v1",
        "tool": "sandbox.generate_figure",
        "decision": "ask",
        "reason": "image provider call requires explicit policy permission",
        "required_permissions": ["sandbox.generate_figure"],
    }
```

- [ ] **Step 2: Run failing tests**

```bash
cd backend && .venv/bin/python -m pytest tests/agents/harness/test_academic_aci_contracts.py -v
```

Expected before implementation: import failure for `AcademicACIObservation`.

- [ ] **Step 3: Implement contracts**

Add to `backend/src/agents/harness/contracts.py`:

```python
HarnessToolStatus = Literal["ok", "warning", "error"]
HarnessPermissionDecision = Literal["allow", "ask", "deny"]


@dataclass(frozen=True, slots=True)
class AcademicACIObservation:
    """Bounded structured observation returned from an Academic ACI tool."""

    tool: str
    status: HarnessToolStatus
    summary: str
    evidence_refs: tuple[str, ...] = ()
    artifact_refs: tuple[str, ...] = ()
    output_refs: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    provenance: dict[str, Any] = field(default_factory=dict)
    structured_payload: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema": "wenjin.academic_aci.observation.v1",
            "tool": self.tool,
            "status": self.status,
            "summary": self.summary,
            "evidence_refs": list(self.evidence_refs),
            "artifact_refs": list(self.artifact_refs),
            "output_refs": list(self.output_refs),
            "warnings": list(self.warnings),
            "provenance": dict(self.provenance),
            "structured_payload": dict(self.structured_payload),
        }


@dataclass(frozen=True, slots=True)
class AcademicACIPermissionCheck:
    """Permission decision for an Academic ACI tool call."""

    tool: str
    decision: HarnessPermissionDecision
    reason: str
    required_permissions: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema": "wenjin.academic_aci.permission_check.v1",
            "tool": self.tool,
            "decision": self.decision,
            "reason": self.reason,
            "required_permissions": list(self.required_permissions),
        }
```

- [ ] **Step 4: Run tests**

```bash
cd backend && .venv/bin/python -m pytest tests/agents/harness/test_academic_aci_contracts.py tests/agents/harness/test_policy_and_registry.py -v
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/src/agents/harness/contracts.py backend/tests/agents/harness/test_academic_aci_contracts.py
git commit -m "feat: add academic aci contracts"
```

---

## Task 3: Add Review Packet Contract To TaskReport

**Files:**

- Modify: `backend/src/agents/contracts/task_report.py`
- Create: `backend/tests/agents/contracts/test_review_packet.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/agents/contracts/test_review_packet.py`:

```python
from src.agents.contracts.task_report import ReviewPacket, ReviewPacketItem, TaskReport


def test_review_packet_item_carries_provenance_and_default_checked() -> None:
    item = ReviewPacketItem(
        item_id="item-1",
        kind="document",
        title="文献定位与创新点.md",
        summary="主题矩阵、gap 和可引用论断。",
        preview={"format": "markdown", "excerpt": "# 文献定位"},
        source={"expert_id": "literature_synthesizer.v1", "node_id": "node-1"},
        claim_refs=["claim-1"],
        evidence_refs=["library:paper-1"],
        quality_surfaces=["citation_strength"],
        risk={"level": "medium", "reasons": ["1 条引用需要人工确认"]},
        default_checked=True,
        can_commit=True,
        provenance={"execution_id": "exec-1"},
    )

    payload = item.model_dump()

    assert payload["schema_version"] == "wenjin.review_packet.item.v1"
    assert payload["kind"] == "document"
    assert payload["default_checked"] is True
    assert payload["can_commit"] is True
    assert payload["risk"]["level"] == "medium"


def test_task_report_can_embed_review_packet() -> None:
    packet = ReviewPacket(
        packet_id="packet-1",
        execution_id="exec-1",
        capability_id="sci_literature_positioning",
        title="文献定位与创新点",
        summary="生成 1 个文档候选。",
        completion_status="complete",
        items=[],
    )
    report = TaskReport(
        execution_id="exec-1",
        capability_id="sci_literature_positioning",
        status="completed",
        duration_seconds=2,
        narrative="完成。",
        review_packet=packet,
    )

    assert report.review_packet is not None
    assert report.review_packet.packet_id == "packet-1"
```

- [ ] **Step 2: Run failing tests**

```bash
cd backend && .venv/bin/python -m pytest tests/agents/contracts/test_review_packet.py -v
```

Expected before implementation: import failure for `ReviewPacket`.

- [ ] **Step 3: Implement Review Packet models**

Add to `backend/src/agents/contracts/task_report.py` before `TaskReport`:

```python
ReviewPacketItemKind = Literal[
    "document",
    "memory",
    "decision",
    "reference",
    "dataset",
    "artifact",
    "prism_change",
    "task",
    "warning",
]

ReviewPacketCompletionStatus = Literal["complete", "partial", "failed", "cancelled"]


class ReviewPacketItem(BaseModel):
    """A user-reviewable candidate produced by an academic harness run."""

    schema_version: Literal["wenjin.review_packet.item.v1"] = "wenjin.review_packet.item.v1"
    item_id: str
    kind: ReviewPacketItemKind
    title: str
    summary: str
    preview: dict[str, Any] = Field(default_factory=dict)
    source: dict[str, Any] = Field(default_factory=dict)
    claim_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    prism_change_refs: list[str] = Field(default_factory=list)
    quality_surfaces: list[str] = Field(default_factory=list)
    risk: dict[str, Any] = Field(default_factory=lambda: {"level": "low", "reasons": []})
    default_checked: bool = True
    can_commit: bool = True
    provenance: dict[str, Any] = Field(default_factory=dict)


class ReviewPacket(BaseModel):
    """Semantic review packet projected into ResultCard and right-panel review UX."""

    schema_version: Literal["wenjin.review_packet.v1"] = "wenjin.review_packet.v1"
    packet_id: str
    execution_id: str
    capability_id: str
    title: str
    summary: str
    completion_status: ReviewPacketCompletionStatus
    items: list[ReviewPacketItem] = Field(default_factory=list)
```

Add the field to `TaskReport`:

```python
    review_packet: ReviewPacket | None = None
```

- [ ] **Step 4: Run tests**

```bash
cd backend && .venv/bin/python -m pytest tests/agents/contracts/test_review_packet.py tests/agents/contracts/test_contracts.py -v
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/src/agents/contracts/task_report.py backend/tests/agents/contracts/test_review_packet.py
git commit -m "feat: add academic review packet contract"
```

---

## Task 4: Add ExpertReport v1 Contract

**Files:**

- Modify: `backend/src/contracts/team_expert.py`
- Modify: `backend/tests/contracts/test_team_expert.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/contracts/test_team_expert.py`:

```python
from src.contracts.team_expert import sanitize_expert_report


def test_sanitize_expert_report_bounds_claims_and_evidence() -> None:
    report = sanitize_expert_report(
        {
            "schema_version": "wenjin.expert_report.v1",
            "expert_id": "literature_synthesizer.v1",
            "skill_id": "literature-synthesizer",
            "task_focus": "Synthesize papers into themes and gaps.",
            "summary": "token=secret-value " + ("summary " * 200),
            "claims": [
                {
                    "claim_id": "claim-1",
                    "text": "FedLoRA reduces communication but heterogeneity remains open.",
                    "support_level": "supported",
                    "evidence_ids": ["ev-1"],
                    "citation_keys": ["smith2025fedlora"],
                    "limitations": ["mostly SFT evidence"],
                }
            ],
            "evidence": [
                {
                    "evidence_id": "ev-1",
                    "source_type": "library_reference",
                    "source_id": "source-1",
                    "citation_key": "smith2025fedlora",
                    "relevance": "high",
                    "risk": "low",
                    "bounded_excerpt": "reports communication reduction",
                    "used_for": ["claim-1"],
                }
            ],
            "artifacts": [],
            "review_items": [],
            "quality_gates_checked": ["citation_strength"],
            "uncertainties": ["privacy-utility evidence is weaker"],
            "next_actions": ["audit two candidate papers"],
        }
    )

    assert report.schema_version == "wenjin.expert_report.v1"
    assert "secret-value" not in report.summary
    assert len(report.summary) <= 700
    assert report.claims[0].support_level == "supported"
    assert report.evidence[0].source_id == "source-1"
```

- [ ] **Step 2: Run failing test**

```bash
cd backend && .venv/bin/python -m pytest tests/contracts/test_team_expert.py::test_sanitize_expert_report_bounds_claims_and_evidence -v
```

Expected before implementation: import failure for `sanitize_expert_report`.

- [ ] **Step 3: Implement ExpertReport models and sanitizer**

Add these types to `backend/src/contracts/team_expert.py`:

```python
ExpertClaimSupportLevel = Literal["verified", "supported", "plausible", "weak", "unsupported"]
ExpertEvidenceSourceType = Literal[
    "library_reference",
    "document",
    "memory",
    "sandbox_artifact",
    "dataset",
    "prism",
    "expert_output",
]


class ExpertClaimV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str
    text: str
    support_level: ExpertClaimSupportLevel
    evidence_ids: list[str] = Field(default_factory=list)
    citation_keys: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ExpertEvidenceV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    source_type: ExpertEvidenceSourceType
    source_id: str | None = None
    citation_key: str | None = None
    relevance: Literal["low", "medium", "high"] | None = None
    risk: Literal["low", "medium", "high", "critical"] | None = None
    bounded_excerpt: str | None = None
    used_for: list[str] = Field(default_factory=list)


class ExpertArtifactV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str
    kind: str
    path: str
    source_script: str | None = None
    dataset_paths: list[str] = Field(default_factory=list)
    content_hash: str | None = None
    caption: str | None = None
    reviewable: bool = True


class ExpertReportV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["wenjin.expert_report.v1"] = "wenjin.expert_report.v1"
    expert_id: str
    skill_id: str
    task_focus: str
    summary: str
    claims: list[ExpertClaimV1] = Field(default_factory=list)
    evidence: list[ExpertEvidenceV1] = Field(default_factory=list)
    artifacts: list[ExpertArtifactV1] = Field(default_factory=list)
    review_items: list[dict[str, Any]] = Field(default_factory=list)
    quality_gates_checked: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    domain_payload: dict[str, Any] = Field(default_factory=dict)
```

Add the sanitizer:

```python
_MAX_REPORT_SUMMARY_CHARS = 700
_MAX_CLAIM_TEXT_CHARS = 500
_MAX_EVIDENCE_EXCERPT_CHARS = 500


def sanitize_expert_report(payload: dict[str, Any]) -> ExpertReportV1:
    data = {
        "schema_version": "wenjin.expert_report.v1",
        "expert_id": _clean_text(payload.get("expert_id")),
        "skill_id": _clean_text(payload.get("skill_id")),
        "task_focus": _truncate(_scrub_text(payload.get("task_focus")), 300),
        "summary": _truncate(_scrub_text(payload.get("summary")), _MAX_REPORT_SUMMARY_CHARS),
        "claims": _sanitize_expert_claims(payload.get("claims"), limit=30),
        "evidence": _sanitize_expert_evidence(payload.get("evidence"), limit=60),
        "artifacts": _sanitize_expert_artifacts(payload.get("artifacts"), limit=20),
        "review_items": _sanitize_small_dicts(payload.get("review_items"), limit=20),
        "quality_gates_checked": _sanitize_string_list(payload.get("quality_gates_checked"), limit=20),
        "uncertainties": _sanitize_string_list(payload.get("uncertainties"), limit=20, max_chars=240),
        "next_actions": _sanitize_string_list(payload.get("next_actions"), limit=20, max_chars=240),
        "domain_payload": payload.get("domain_payload") if isinstance(payload.get("domain_payload"), dict) else {},
    }
    return ExpertReportV1.model_validate(data)
```

Add helper functions in the same file:

```python
def _sanitize_expert_claims(value: Any, *, limit: int) -> list[dict[str, Any]]:
    if not isinstance(value, list | tuple):
        return []
    claims: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        claim = {
            "claim_id": _clean_text(item.get("claim_id")),
            "text": _truncate(_scrub_text(item.get("text")), _MAX_CLAIM_TEXT_CHARS),
            "support_level": item.get("support_level"),
            "evidence_ids": _sanitize_string_list(item.get("evidence_ids"), limit=20),
            "citation_keys": _sanitize_string_list(item.get("citation_keys"), limit=20),
            "limitations": _sanitize_string_list(item.get("limitations"), limit=10, max_chars=180),
        }
        if claim["claim_id"] and claim["text"]:
            claims.append(claim)
        if len(claims) >= limit:
            break
    return claims


def _sanitize_expert_evidence(value: Any, *, limit: int) -> list[dict[str, Any]]:
    if not isinstance(value, list | tuple):
        return []
    evidence: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        evidence_item = {
            "evidence_id": _clean_text(item.get("evidence_id")),
            "source_type": item.get("source_type"),
            "source_id": _optional_clean_text(item.get("source_id")),
            "citation_key": _optional_clean_text(item.get("citation_key")),
            "relevance": item.get("relevance"),
            "risk": item.get("risk"),
            "bounded_excerpt": _optional_truncated_scrubbed(item.get("bounded_excerpt"), _MAX_EVIDENCE_EXCERPT_CHARS),
            "used_for": _sanitize_string_list(item.get("used_for"), limit=20),
        }
        if evidence_item["evidence_id"]:
            evidence.append({key: val for key, val in evidence_item.items() if val is not None})
        if len(evidence) >= limit:
            break
    return evidence


def _sanitize_expert_artifacts(value: Any, *, limit: int) -> list[dict[str, Any]]:
    if not isinstance(value, list | tuple):
        return []
    artifacts: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        path = _optional_clean_text(item.get("path"))
        if not path or not _is_safe_ref_path(path):
            continue
        artifact = {
            "artifact_id": _clean_text(item.get("artifact_id")),
            "kind": _clean_text(item.get("kind")),
            "path": path,
            "source_script": _optional_clean_text(item.get("source_script")),
            "dataset_paths": [
                path_value
                for path_value in _sanitize_string_list(item.get("dataset_paths"), limit=10)
                if _is_safe_ref_path(path_value)
            ],
            "content_hash": _optional_clean_text(item.get("content_hash")),
            "caption": _optional_truncated_scrubbed(item.get("caption"), 240),
            "reviewable": item.get("reviewable", True) is not False,
        }
        if artifact["artifact_id"] and artifact["kind"]:
            artifacts.append({key: val for key, val in artifact.items() if val is not None})
        if len(artifacts) >= limit:
            break
    return artifacts
```

Add `_sanitize_string_list` and `_sanitize_small_dicts` if they do not already exist:

```python
def _sanitize_string_list(value: Any, *, limit: int, max_chars: int = 120) -> list[str]:
    if not isinstance(value, list | tuple | set | frozenset):
        return []
    result: list[str] = []
    for item in value:
        text = _truncate(_scrub_text(item), max_chars)
        if text:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def _sanitize_small_dicts(value: Any, *, limit: int) -> list[dict[str, Any]]:
    if not isinstance(value, list | tuple):
        return []
    result: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            result.append({str(key): val for key, val in item.items() if isinstance(key, str)})
        if len(result) >= limit:
            break
    return result
```

- [ ] **Step 4: Run tests**

```bash
cd backend && .venv/bin/python -m pytest tests/contracts/test_team_expert.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/src/contracts/team_expert.py backend/tests/contracts/test_team_expert.py
git commit -m "feat: add expert report contract"
```

---

## Task 5: Map ExpertReport To Review Packet

**Files:**

- Modify: `backend/src/agents/lead_agent/v2/output_mapping.py`
- Modify: `backend/tests/agents/lead_agent/v2/test_output_mapping.py`

- [ ] **Step 1: Write failing mapper test**

Append to `backend/tests/agents/lead_agent/v2/test_output_mapping.py`:

```python
from src.agents.lead_agent.v2.output_mapping import review_packet_from_expert_reports  # noqa: E402
from src.contracts.team_expert import sanitize_expert_report  # noqa: E402


def test_review_packet_from_expert_reports_maps_claims_artifacts_and_warnings():
    report = sanitize_expert_report(
        {
            "schema_version": "wenjin.expert_report.v1",
            "expert_id": "literature_synthesizer.v1",
            "skill_id": "literature-synthesizer",
            "task_focus": "Summarize literature.",
            "summary": "Three directions found.",
            "claims": [
                {
                    "claim_id": "claim-1",
                    "text": "Communication-efficient FL fine-tuning remains unresolved.",
                    "support_level": "supported",
                    "evidence_ids": ["ev-1"],
                    "citation_keys": ["smith2025"],
                    "limitations": [],
                },
                {
                    "claim_id": "claim-2",
                    "text": "All FedLLM methods solve privacy leakage.",
                    "support_level": "unsupported",
                    "evidence_ids": [],
                    "citation_keys": [],
                    "limitations": ["unsupported overclaim"],
                },
            ],
            "evidence": [
                {
                    "evidence_id": "ev-1",
                    "source_type": "library_reference",
                    "source_id": "source-1",
                    "citation_key": "smith2025",
                    "relevance": "high",
                    "risk": "low",
                    "bounded_excerpt": "communication cost reduced",
                    "used_for": ["claim-1"],
                }
            ],
            "artifacts": [
                {
                    "artifact_id": "artifact-1",
                    "kind": "report",
                    "path": "/workspace/reports/lit.md",
                    "content_hash": "sha256:abc",
                    "reviewable": True,
                }
            ],
            "quality_gates_checked": ["citation_strength"],
            "uncertainties": ["claim-2 is unsupported"],
            "next_actions": [],
        }
    )

    packet = review_packet_from_expert_reports(
        execution_id="exec-1",
        capability_id="sci_literature_positioning",
        title="文献定位与创新点",
        reports=[report],
        completion_status="partial",
    )

    assert packet.schema_version == "wenjin.review_packet.v1"
    assert packet.completion_status == "partial"
    assert [item.kind for item in packet.items] == ["document", "warning"]
    assert packet.items[0].artifact_refs == ["artifact:/workspace/reports/lit.md"]
    assert packet.items[0].evidence_refs == ["library_reference:source-1"]
    assert packet.items[0].default_checked is False
    assert packet.items[1].can_commit is False
```

- [ ] **Step 2: Run failing test**

```bash
cd backend && .venv/bin/python -m pytest tests/agents/lead_agent/v2/test_output_mapping.py::test_review_packet_from_expert_reports_maps_claims_artifacts_and_warnings -v
```

Expected before implementation: import failure for `review_packet_from_expert_reports`.

- [ ] **Step 3: Implement mapper**

Add imports in `backend/src/agents/lead_agent/v2/output_mapping.py`:

```python
from src.agents.contracts.task_report import ReviewPacket, ReviewPacketItem
from src.contracts.team_expert import ExpertReportV1
```

Add the function:

```python
def review_packet_from_expert_reports(
    *,
    execution_id: str,
    capability_id: str,
    title: str,
    reports: list[ExpertReportV1],
    completion_status: str,
) -> ReviewPacket:
    items: list[ReviewPacketItem] = []
    for report_index, report in enumerate(reports):
        artifact_refs = [f"artifact:{artifact.path}" for artifact in report.artifacts if artifact.reviewable]
        evidence_refs = [
            f"{evidence.source_type}:{evidence.source_id}"
            for evidence in report.evidence
            if evidence.source_id
        ]
        claim_refs = [claim.claim_id for claim in report.claims if claim.support_level in {"verified", "supported", "plausible"}]
        if report.summary or artifact_refs or claim_refs:
            items.append(
                ReviewPacketItem(
                    item_id=f"{report.expert_id}-{report_index}-summary",
                    kind="document" if artifact_refs else "memory",
                    title=_review_packet_title_for_report(report),
                    summary=report.summary,
                    preview={"format": "markdown", "excerpt": report.summary[:500]},
                    source={"expert_id": report.expert_id, "skill_id": report.skill_id},
                    claim_refs=claim_refs,
                    evidence_refs=evidence_refs,
                    artifact_refs=artifact_refs,
                    quality_surfaces=list(report.quality_gates_checked),
                    risk=_risk_from_report(report),
                    default_checked=completion_status == "complete" and not _report_has_unsupported_claims(report),
                    can_commit=True,
                    provenance={"execution_id": execution_id, "expert_id": report.expert_id},
                )
            )
        unsupported_claims = [claim for claim in report.claims if claim.support_level in {"weak", "unsupported"}]
        for claim in unsupported_claims:
            items.append(
                ReviewPacketItem(
                    item_id=f"{report.expert_id}-{claim.claim_id}-warning",
                    kind="warning",
                    title="弱证据或未支持论断",
                    summary=claim.text,
                    preview={"format": "text", "excerpt": claim.text},
                    source={"expert_id": report.expert_id, "skill_id": report.skill_id},
                    claim_refs=[claim.claim_id],
                    evidence_refs=list(claim.evidence_ids),
                    quality_surfaces=list(report.quality_gates_checked),
                    risk={"level": "high", "reasons": claim.limitations or ["claim is not sufficiently supported"]},
                    default_checked=False,
                    can_commit=False,
                    provenance={"execution_id": execution_id, "expert_id": report.expert_id},
                )
            )
    return ReviewPacket(
        packet_id=f"{execution_id}-review-packet",
        execution_id=execution_id,
        capability_id=capability_id,
        title=title,
        summary=_review_packet_summary(items),
        completion_status=completion_status,
        items=items,
    )
```

Add helpers:

```python
def _review_packet_title_for_report(report: ExpertReportV1) -> str:
    if report.artifacts:
        return f"{report.skill_id} 产物"
    return f"{report.skill_id} 摘要"


def _report_has_unsupported_claims(report: ExpertReportV1) -> bool:
    return any(claim.support_level in {"weak", "unsupported"} for claim in report.claims)


def _risk_from_report(report: ExpertReportV1) -> dict[str, Any]:
    if _report_has_unsupported_claims(report):
        return {"level": "high", "reasons": ["contains weak or unsupported claims"]}
    if report.uncertainties:
        return {"level": "medium", "reasons": list(report.uncertainties[:5])}
    return {"level": "low", "reasons": []}


def _review_packet_summary(items: list[ReviewPacketItem]) -> str:
    committable = sum(1 for item in items if item.can_commit)
    blocked = len(items) - committable
    if blocked:
        return f"{committable} 项可保存，{blocked} 项需要确认。"
    return f"{committable} 项待确认成果。"
```

- [ ] **Step 4: Run tests**

```bash
cd backend && .venv/bin/python -m pytest tests/agents/lead_agent/v2/test_output_mapping.py tests/agents/contracts/test_review_packet.py -v
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/src/agents/lead_agent/v2/output_mapping.py backend/tests/agents/lead_agent/v2/test_output_mapping.py
git commit -m "feat: map expert reports to review packets"
```

---

## Task 6: Add Research State Compaction Contract

**Files:**

- Create: `backend/src/agents/harness/research_state.py`
- Create: `backend/tests/agents/harness/test_research_state.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/agents/harness/test_research_state.py`:

```python
from src.agents.harness.research_state import ResearchStateV1, compact_research_state


def test_compact_research_state_preserves_claim_evidence_and_artifact_ids() -> None:
    state = compact_research_state(
        execution_id="exec-1",
        goal="AAAI paper on federated LLM fine-tuning",
        expert_reports=[
            {
                "claims": [{"claim_id": "claim-1", "text": "FedLoRA reduces communication", "support_level": "supported"}],
                "evidence": [{"evidence_id": "ev-1", "source_type": "library_reference", "source_id": "source-1"}],
                "artifacts": [{"artifact_id": "artifact-1", "kind": "report", "path": "/workspace/reports/lit.md"}],
                "uncertainties": ["privacy evidence remains weak"],
            }
        ],
        quality_state=[{"surface": "citation_strength", "status": "warning"}],
    )

    assert isinstance(state, ResearchStateV1)
    assert state.execution_id == "exec-1"
    assert state.claims[0]["claim_id"] == "claim-1"
    assert state.evidence_index[0]["evidence_id"] == "ev-1"
    assert state.artifact_index[0]["artifact_id"] == "artifact-1"
    assert state.open_questions == ["privacy evidence remains weak"]
    assert state.quality_state[0]["surface"] == "citation_strength"
```

- [ ] **Step 2: Run failing tests**

```bash
cd backend && .venv/bin/python -m pytest tests/agents/harness/test_research_state.py -v
```

Expected before implementation: import failure for `research_state`.

- [ ] **Step 3: Implement research state**

Create `backend/src/agents/harness/research_state.py`:

```python
"""Compact long-task research state for academic harness runs."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ResearchStateV1(BaseModel):
    schema_version: Literal["wenjin.research_state.v1"] = "wenjin.research_state.v1"
    execution_id: str
    goal: str
    decisions: list[dict[str, Any]] = Field(default_factory=list)
    claims: list[dict[str, Any]] = Field(default_factory=list)
    evidence_index: list[dict[str, Any]] = Field(default_factory=list)
    artifact_index: list[dict[str, Any]] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    quality_state: list[dict[str, Any]] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


def compact_research_state(
    *,
    execution_id: str,
    goal: str,
    expert_reports: list[dict[str, Any]],
    quality_state: list[dict[str, Any]],
    decisions: list[dict[str, Any]] | None = None,
    next_actions: list[str] | None = None,
) -> ResearchStateV1:
    claims: list[dict[str, Any]] = []
    evidence_index: list[dict[str, Any]] = []
    artifact_index: list[dict[str, Any]] = []
    open_questions: list[str] = []
    for report in expert_reports:
        if not isinstance(report, dict):
            continue
        claims.extend(_dict_items(report.get("claims"), id_key="claim_id"))
        evidence_index.extend(_dict_items(report.get("evidence"), id_key="evidence_id"))
        artifact_index.extend(_dict_items(report.get("artifacts"), id_key="artifact_id"))
        open_questions.extend(_string_items(report.get("uncertainties")))
    return ResearchStateV1(
        execution_id=execution_id,
        goal=goal,
        decisions=decisions or [],
        claims=_dedupe_by_key(claims, "claim_id"),
        evidence_index=_dedupe_by_key(evidence_index, "evidence_id"),
        artifact_index=_dedupe_by_key(artifact_index, "artifact_id"),
        open_questions=_dedupe_strings(open_questions),
        quality_state=quality_state,
        next_actions=next_actions or [],
    )
```

Add helpers:

```python
def _dict_items(value: Any, *, id_key: str) -> list[dict[str, Any]]:
    if not isinstance(value, list | tuple):
        return []
    return [item for item in value if isinstance(item, dict) and item.get(id_key)]


def _string_items(value: Any) -> list[str]:
    if not isinstance(value, list | tuple | set | frozenset):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _dedupe_by_key(items: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        item_key = str(item.get(key) or "").strip()
        if not item_key or item_key in seen:
            continue
        result.append(item)
        seen.add(item_key)
    return result


def _dedupe_strings(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item in seen:
            continue
        result.append(item)
        seen.add(item)
    return result
```

- [ ] **Step 4: Run tests**

```bash
cd backend && .venv/bin/python -m pytest tests/agents/harness/test_research_state.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/src/agents/harness/research_state.py backend/tests/agents/harness/test_research_state.py
git commit -m "feat: add compact research state contract"
```

---

## Task 7: Integrate ExpertReport, Review Packet, And Research State Into TeamKernel

**Files:**

- Modify: `backend/src/agents/lead_agent/v2/team/expert_runtime.py`
- Modify: `backend/src/agents/lead_agent/v2/team/kernel.py`
- Modify: `backend/src/agents/lead_agent/v2/team/member_context.py`
- Modify: `backend/tests/agents/lead_agent/v2/test_team_kernel.py`
- Modify: `backend/tests/agents/lead_agent/v2/test_team_member_context.py`

- [ ] **Step 1: Write failing TeamKernel test**

Add a focused test to `backend/tests/agents/lead_agent/v2/test_team_kernel.py`:

```python
from src.agents.lead_agent.v2.team.kernel import build_academic_harness_outputs
from src.contracts.team_expert import sanitize_expert_report


def test_build_academic_harness_outputs_attaches_review_packet_and_research_state():
    report = sanitize_expert_report(
        {
            "schema_version": "wenjin.expert_report.v1",
            "expert_id": "literature_synthesizer.v1",
            "skill_id": "literature-synthesizer",
            "task_focus": "Synthesize literature.",
            "summary": "Found one supported direction.",
            "claims": [
                {
                    "claim_id": "claim-1",
                    "text": "FedLoRA reduces communication.",
                    "support_level": "supported",
                    "evidence_ids": ["ev-1"],
                    "citation_keys": ["smith2025"],
                    "limitations": [],
                }
            ],
            "evidence": [
                {
                    "evidence_id": "ev-1",
                    "source_type": "library_reference",
                    "source_id": "source-1",
                    "citation_key": "smith2025",
                    "relevance": "high",
                    "risk": "low",
                    "bounded_excerpt": "communication reduction",
                    "used_for": ["claim-1"],
                }
            ],
            "artifacts": [],
            "quality_gates_checked": ["citation_strength"],
            "uncertainties": [],
            "next_actions": [],
        }
    )

    packet, research_state = build_academic_harness_outputs(
        execution_id="exec-1",
        capability_id="sci_literature_positioning",
        capability_name="文献定位与创新点",
        expert_reports=[report],
        completion_status="complete",
        quality_state=[{"surface": "citation_strength", "status": "pass"}],
    )

    assert packet.items[0].claim_refs == ["claim-1"]
    assert research_state.claims[0]["claim_id"] == "claim-1"
```

- [ ] **Step 2: Write failing context handoff test**

Add to `backend/tests/agents/lead_agent/v2/test_team_member_context.py`:

```python
from src.agents.lead_agent.v2.team.member_context import project_research_state_for_member_context


def test_member_context_includes_compact_research_state_for_later_batches():
    context = project_research_state_for_member_context(
        {
            "schema_version": "wenjin.research_state.v1",
            "execution_id": "exec-1",
            "goal": "AAAI paper on federated LLM fine-tuning",
            "claims": [{"claim_id": "claim-1", "text": "FedLoRA reduces communication"}],
            "evidence_index": [{"evidence_id": "ev-1", "source_id": "source-1"}],
            "artifact_index": [],
            "open_questions": ["privacy evidence remains weak"],
            "quality_state": [{"surface": "citation_strength", "status": "warning"}],
        }
    )

    assert context is not None
    assert context["claims"][0]["claim_id"] == "claim-1"
    assert context["quality_state"][0]["surface"] == "citation_strength"
```

- [ ] **Step 3: Run failing tests**

```bash
cd backend && .venv/bin/python -m pytest tests/agents/lead_agent/v2/test_team_kernel.py tests/agents/lead_agent/v2/test_team_member_context.py -v
```

Expected before implementation: missing normalization helper or missing `research_state` in context.

- [ ] **Step 4: Implement runtime normalization**

In `backend/src/agents/lead_agent/v2/team/expert_runtime.py`, add a helper that returns sanitized expert reports:

```python
from src.contracts.team_expert import ExpertReportV1, sanitize_expert_report


def expert_report_from_member_output(member_output: dict[str, Any]) -> ExpertReportV1 | None:
    if not isinstance(member_output, dict):
        return None
    raw_report = member_output.get("expert_report")
    if isinstance(raw_report, dict):
        return sanitize_expert_report(raw_report)
    if member_output.get("schema_version") == "wenjin.expert_report.v1":
        return sanitize_expert_report(member_output)
    return None
```

In `backend/src/agents/lead_agent/v2/team/kernel.py`, after each member output is collected, append the sanitized report to `runtime_state["expert_reports"]`. Before building the final `TaskReport`, build a Review Packet:

```python
from src.agents.harness.research_state import compact_research_state
from src.agents.lead_agent.v2.output_mapping import review_packet_from_expert_reports
from src.contracts.team_expert import ExpertReportV1


def build_academic_harness_outputs(
    *,
    execution_id: str,
    capability_id: str,
    capability_name: str,
    expert_reports: list[ExpertReportV1],
    completion_status: str,
    quality_state: list[dict[str, Any]],
) -> tuple[ReviewPacket, ResearchStateV1]:
    packet = review_packet_from_expert_reports(
        execution_id=execution_id,
        capability_id=capability_id,
        title=capability_name,
        reports=expert_reports,
        completion_status=completion_status,
    )
    research_state = compact_research_state(
        execution_id=execution_id,
        goal=capability_name,
        expert_reports=[report.model_dump() for report in expert_reports],
        quality_state=quality_state,
    )
    return packet, research_state
```

Set `TaskReport.review_packet = packet` and set `runtime_state["research_state"] = research_state.model_dump()` before returning the final report.

In `backend/src/agents/lead_agent/v2/team/member_context.py`, add `project_research_state_for_member_context()` and call it when building member context:

```python
def project_research_state_for_member_context(research_state: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(research_state, dict):
        return None
    return {
        "schema_version": research_state.get("schema_version"),
        "execution_id": research_state.get("execution_id"),
        "goal": research_state.get("goal"),
        "claims": list(research_state.get("claims") or [])[:30],
        "evidence_index": list(research_state.get("evidence_index") or [])[:60],
        "artifact_index": list(research_state.get("artifact_index") or [])[:30],
        "open_questions": list(research_state.get("open_questions") or [])[:20],
        "quality_state": list(research_state.get("quality_state") or [])[:20],
    }


research_state_projection = project_research_state_for_member_context(workspace_data.get("research_state"))
if research_state_projection is not None:
    context["research_state"] = research_state_projection
```

- [ ] **Step 5: Run tests**

```bash
cd backend && .venv/bin/python -m pytest tests/agents/lead_agent/v2/test_team_kernel.py tests/agents/lead_agent/v2/test_team_member_context.py tests/agents/lead_agent/v2/test_team_quality_gates.py -v
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/src/agents/lead_agent/v2/team/expert_runtime.py backend/src/agents/lead_agent/v2/team/kernel.py backend/src/agents/lead_agent/v2/team/member_context.py backend/tests/agents/lead_agent/v2/test_team_kernel.py backend/tests/agents/lead_agent/v2/test_team_member_context.py
git commit -m "feat: integrate expert reports into team kernel"
```

---

## Task 8: Add Deterministic Evaluators For New Quality Surfaces

**Files:**

- Modify: `backend/src/agents/harness/research_task_eval.py`
- Modify: `backend/tests/agents/harness/test_research_task_eval.py`

- [ ] **Step 1: Write failing evaluator tests**

Add to `backend/tests/agents/harness/test_research_task_eval.py`:

```python
def test_research_task_eval_fails_review_packet_completeness_when_packet_empty() -> None:
    result = evaluate_research_task_report(
        {
            "execution_id": "exec-1",
            "capability_id": "sci_literature_positioning",
            "status": "completed",
            "review_packet": {
                "schema_version": "wenjin.review_packet.v1",
                "packet_id": "packet-1",
                "execution_id": "exec-1",
                "capability_id": "sci_literature_positioning",
                "title": "文献定位与创新点",
                "summary": "empty",
                "completion_status": "complete",
                "items": [],
            },
        },
        required_surfaces=("review_packet_completeness",),
    )

    assert result.passed is False
    assert "review_packet_completeness" in result.failed_surfaces


def test_research_task_eval_passes_claim_evidence_alignment_for_supported_claim() -> None:
    result = evaluate_research_task_report(
        {
            "execution_id": "exec-1",
            "capability_id": "sci_literature_positioning",
            "status": "completed",
            "review_packet": {
                "schema_version": "wenjin.review_packet.v1",
                "packet_id": "packet-1",
                "execution_id": "exec-1",
                "capability_id": "sci_literature_positioning",
                "title": "文献定位与创新点",
                "summary": "1 item",
                "completion_status": "complete",
                "items": [
                    {
                        "schema_version": "wenjin.review_packet.item.v1",
                        "item_id": "item-1",
                        "kind": "document",
                        "title": "report",
                        "summary": "supported",
                        "claim_refs": ["claim-1"],
                        "evidence_refs": ["library_reference:source-1"],
                        "default_checked": True,
                        "can_commit": True,
                    }
                ],
            },
        },
        required_surfaces=("claim_evidence_alignment", "review_packet_completeness"),
    )

    assert result.passed is True
```

Use the current evaluator function/class names in `test_research_task_eval.py`. Keep the input payload and surface expectations unchanged.

- [ ] **Step 2: Run failing tests**

```bash
cd backend && .venv/bin/python -m pytest tests/agents/harness/test_research_task_eval.py -v
```

Expected before implementation: unknown surface or missing evaluator behavior.

- [ ] **Step 3: Implement deterministic checks**

In `backend/src/agents/harness/research_task_eval.py`, add surface checks that read `review_packet` from TaskReport dicts:

```python
def _check_review_packet_completeness(report: dict[str, Any]) -> SurfaceCheckResult:
    packet = report.get("review_packet") if isinstance(report, dict) else None
    items = packet.get("items") if isinstance(packet, dict) else None
    if not isinstance(items, list) or not items:
        return SurfaceCheckResult(
            surface="review_packet_completeness",
            passed=False,
            detail="review packet has no previewable items",
        )
    previewable = [item for item in items if isinstance(item, dict) and item.get("title") and item.get("summary")]
    return SurfaceCheckResult(
        surface="review_packet_completeness",
        passed=bool(previewable),
        detail=f"{len(previewable)} previewable items",
    )


def _check_claim_evidence_alignment(report: dict[str, Any]) -> SurfaceCheckResult:
    packet = report.get("review_packet") if isinstance(report, dict) else None
    items = packet.get("items") if isinstance(packet, dict) else []
    unsupported = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        claim_refs = item.get("claim_refs") or []
        evidence_refs = item.get("evidence_refs") or []
        if claim_refs and not evidence_refs:
            unsupported.append(item.get("item_id") or item.get("title") or "unknown")
    return SurfaceCheckResult(
        surface="claim_evidence_alignment",
        passed=not unsupported,
        detail="all claim-bearing review items have evidence refs" if not unsupported else f"missing evidence for {unsupported}",
    )
```

Wire these functions into the existing surface dispatch table or conditional chain. Use current result class names from the file.

- [ ] **Step 4: Run tests**

```bash
cd backend && .venv/bin/python -m pytest tests/agents/harness/test_research_task_eval.py tests/agents/harness/test_research_eval_surfaces.py -v
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/src/agents/harness/research_task_eval.py backend/tests/agents/harness/test_research_task_eval.py
git commit -m "feat: evaluate review packet quality surfaces"
```

---

## Task 9: Migrate First-Wave SCI Capability And Skill Seeds

**Files:**

- Modify: `backend/seed/capabilities/sci/sci_literature_positioning.yaml`
- Modify: `backend/seed/capabilities/sci/research_question_to_paper.yaml`
- Modify: `backend/seed/capabilities/sci/sci_empirical_package.yaml`
- Modify: `backend/seed/capabilities/sci/reproducibility_audit.yaml`
- Modify selected skill YAML files listed in the file structure section.
- Create: `backend/tests/architecture/test_academic_harness_catalog.py`

- [ ] **Step 1: Write catalog architecture test**

Create `backend/tests/architecture/test_academic_harness_catalog.py`:

```python
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]


FIRST_WAVE = [
    "backend/seed/capabilities/sci/sci_literature_positioning.yaml",
    "backend/seed/capabilities/sci/research_question_to_paper.yaml",
    "backend/seed/capabilities/sci/sci_empirical_package.yaml",
    "backend/seed/capabilities/sci/reproducibility_audit.yaml",
]


def _read_yaml(path: str) -> dict:
    return yaml.safe_load((ROOT / path).read_text()) or {}


def test_first_wave_capabilities_declare_academic_harness_policy() -> None:
    for path in FIRST_WAVE:
        capability = _read_yaml(path)
        policy = capability.get("research_evidence") or capability.get("policy", {}).get("academic_harness")
        assert isinstance(policy, dict), path
        assert policy.get("review_packet") == "required", path
        assert isinstance(policy.get("required_surfaces"), list) and policy["required_surfaces"], path
        assert isinstance(policy.get("surface_enforcement"), dict), path


def test_first_wave_team_kernel_capabilities_have_ordered_phases_or_team_policy() -> None:
    for path in FIRST_WAVE:
        capability = _read_yaml(path)
        assert capability.get("runtime", {}).get("mode") in {"team_kernel", "graph"}, path
        has_team = bool(capability.get("team_policy", {}).get("core_templates"))
        has_graph = bool(capability.get("graph_template", {}).get("phases"))
        assert has_team or has_graph, path
```

- [ ] **Step 2: Run failing test**

```bash
cd backend && .venv/bin/python -m pytest tests/architecture/test_academic_harness_catalog.py -v
```

Expected before seed edits: failure because first-wave capabilities do not consistently declare `research_evidence.review_packet`.

- [ ] **Step 3: Add academic harness policy to first-wave capabilities**

For each first-wave capability, add this top-level block with surfaces adjusted per capability:

```yaml
research_evidence:
  review_packet: required
  required_surfaces:
    - workflow_trace
    - review_packet_completeness
    - claim_evidence_alignment
  surface_enforcement:
    workflow_trace: required_runtime
    review_packet_completeness: required_final
    claim_evidence_alignment: required_final
```

Use these surface additions:

- `sci_literature_positioning.yaml`: add `paper_relevance` and `citation_strength`.
- `research_question_to_paper.yaml`: add `citation_strength`, `writing_semantic_preservation`, and `writing_academic_style`.
- `sci_empirical_package.yaml`: add `experiment_reproducibility`, `experiment_interpretation`, `statistical_robustness`, and `figure_data_consistency`.
- `reproducibility_audit.yaml`: add `experiment_reproducibility`, `statistical_robustness`, and `output_ref_reuse`.

- [ ] **Step 4: Update selected skill prompts to mention ExpertReport**

In each selected skill YAML, add one sentence under `Output Contract:`:

```text
- When producing structured runtime output, include `expert_report(schema=wenjin.expert_report.v1)` with summary, claims, evidence, artifacts, review_items, quality_gates_checked, uncertainties, and next_actions.
```

For writing skills that stage Prism changes, add:

```text
- Manuscript edits must be staged as reviewable Prism changes; do not claim that changes were applied until the user applies them.
```

For experiment and figure skills, add:

```text
- Sandbox artifacts must include source_script, dataset_paths, content_hash, and a short limitation note.
```

- [ ] **Step 5: Run catalog and seed tests**

```bash
cd backend && .venv/bin/python -m pytest tests/architecture/test_academic_harness_catalog.py tests/dataservice/test_catalog_domain.py tests/architecture/test_super_agent_capability_cutover.py -v
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/seed/capabilities/sci/sci_literature_positioning.yaml backend/seed/capabilities/sci/research_question_to_paper.yaml backend/seed/capabilities/sci/sci_empirical_package.yaml backend/seed/capabilities/sci/reproducibility_audit.yaml backend/seed/skills backend/tests/architecture/test_academic_harness_catalog.py
git commit -m "feat: declare academic harness policy for sci capabilities"
```

---

## Task 10: Project Review Packet And Quality Highlights In Frontend

**Files:**

- Modify: `frontend/lib/execution-run-view.ts`
- Modify: `frontend/lib/workspace-result-preview.ts`
- Modify: `frontend/tests/unit/v2/execution-run-view.test.ts`
- Modify: `frontend/tests/unit/lib/workspace-result-preview.test.ts`

- [ ] **Step 1: Write failing RunView test**

Append to `frontend/tests/unit/v2/execution-run-view.test.ts`:

```ts
it("projects review packet items and quality highlights", () => {
  const record = baseRecord({
    status: "completed",
    result: {
      execution_id: "exec-1",
      capability_id: "sci_literature_positioning",
      status: "completed",
      duration_seconds: 2,
      narrative: "完成。",
      review_packet: {
        schema_version: "wenjin.review_packet.v1",
        packet_id: "packet-1",
        execution_id: "exec-1",
        capability_id: "sci_literature_positioning",
        title: "文献定位与创新点",
        summary: "1 项待确认成果。",
        completion_status: "complete",
        items: [
          {
            schema_version: "wenjin.review_packet.item.v1",
            item_id: "item-1",
            kind: "document",
            title: "文献定位与创新点.md",
            summary: "主题矩阵和 gap。",
            quality_surfaces: ["citation_strength"],
            risk: { level: "low", reasons: [] },
            default_checked: true,
            can_commit: true,
          },
        ],
      },
    },
  });

  const view = runViewFromExecution(record);

  expect(view.reviewPacket?.items).toHaveLength(1);
  expect(view.reviewPacket?.items[0].title).toBe("文献定位与创新点.md");
  expect(view.qualityHighlights.some((item) => item.label.includes("引用"))).toBe(true);
});
```

- [ ] **Step 2: Write failing preview test**

Add to `frontend/tests/unit/lib/workspace-result-preview.test.ts`:

```ts
it("builds workspace previews from review packet items", () => {
  const previews = buildWorkspaceResultPreviewsFromReviewPacket({
    schema_version: "wenjin.review_packet.v1",
    packet_id: "packet-1",
    execution_id: "exec-1",
    capability_id: "sci_literature_positioning",
    title: "文献定位与创新点",
    summary: "1 item",
    completion_status: "complete",
    items: [
      {
        schema_version: "wenjin.review_packet.item.v1",
        item_id: "item-1",
        kind: "document",
        title: "文献定位与创新点.md",
        summary: "主题矩阵。",
        default_checked: true,
        can_commit: true,
      },
    ],
  });

  expect(previews[0]).toMatchObject({
    id: "item-1",
    title: "文献定位与创新点.md",
    kind: "document",
    defaultChecked: true,
  });
});
```

- [ ] **Step 3: Run failing frontend tests**

```bash
cd frontend && npx vitest run tests/unit/v2/execution-run-view.test.ts tests/unit/lib/workspace-result-preview.test.ts
```

Expected before implementation: missing `reviewPacket` projection and missing `buildWorkspaceResultPreviewsFromReviewPacket`.

- [ ] **Step 4: Implement frontend projection**

In `frontend/lib/execution-run-view.ts`, add interfaces:

```ts
export interface RunViewReviewPacketItem {
  id: string;
  kind: string;
  title: string;
  summary: string;
  defaultChecked: boolean;
  canCommit: boolean;
  riskLevel?: string;
  qualitySurfaces: string[];
}

export interface RunViewReviewPacket {
  id: string;
  title: string;
  summary: string;
  completionStatus: string;
  items: RunViewReviewPacketItem[];
}
```

Add `reviewPacket?: RunViewReviewPacket | null;` to `RunView`.

Add parser:

```ts
function reviewPacketFromTaskReport(taskReport: TaskReportProjection | null): RunViewReviewPacket | null {
  const packet = objectValue(taskReport?.review_packet);
  if (!packet) return null;
  const items = arrayValue(packet.items).map((item) => {
    const itemObject = objectValue(item) ?? {};
    return {
      id: stringValue(itemObject.item_id) || stringValue(itemObject.id) || "review-item",
      kind: stringValue(itemObject.kind) || "document",
      title: stringValue(itemObject.title) || "待确认成果",
      summary: stringValue(itemObject.summary) || "",
      defaultChecked: itemObject.default_checked !== false,
      canCommit: itemObject.can_commit !== false,
      riskLevel: stringValue(objectValue(itemObject.risk)?.level),
      qualitySurfaces: arrayValue(itemObject.quality_surfaces).map((value) => stringValue(value)).filter(Boolean),
    };
  });
  return {
    id: stringValue(packet.packet_id) || "review-packet",
    title: stringValue(packet.title) || "待确认成果",
    summary: stringValue(packet.summary) || "",
    completionStatus: stringValue(packet.completion_status) || "complete",
    items,
  };
}
```

In `runViewFromExecution`, compute `const reviewPacket = reviewPacketFromTaskReport(taskReport);` and include it in returned `RunView`.

Extend `qualityHighlightsFromRuntimeState` or add packet-derived highlights:

```ts
function qualityHighlightsFromReviewPacket(packet: RunViewReviewPacket | null): RunViewQualityHighlight[] {
  if (!packet) return [];
  const surfaceSet = new Set(packet.items.flatMap((item) => item.qualitySurfaces));
  const highlights: RunViewQualityHighlight[] = [];
  if (surfaceSet.has("citation_strength")) {
    highlights.push({ label: "引用核验", status: "pass", detail: "已生成引用相关质量检查摘要" });
  }
  if (surfaceSet.has("claim_evidence_alignment")) {
    highlights.push({ label: "证据对齐", status: "pass", detail: "论断已关联证据引用" });
  }
  return highlights;
}
```

In `frontend/lib/workspace-result-preview.ts`, add:

```ts
export function buildWorkspaceResultPreviewsFromReviewPacket(packet: unknown): WorkspaceResultPreview[] {
  const packetObject = isRecord(packet) ? packet : null;
  const items = Array.isArray(packetObject?.items) ? packetObject.items : [];
  return items.filter(isRecord).map((item) => ({
    id: stringFromUnknown(item.item_id) || stringFromUnknown(item.id) || "review-item",
    kind: stringFromUnknown(item.kind) || "document",
    title: stringFromUnknown(item.title) || "待确认成果",
    subtitle: stringFromUnknown(item.summary),
    summary: stringFromUnknown(item.summary),
    defaultChecked: item.default_checked !== false,
    canCommit: item.can_commit !== false,
    source: "review_packet",
    raw: item,
  }));
}
```

Use helper names already present in `workspace-result-preview.ts`. If helper names differ, add local helpers with the same behavior and keep exported function signature unchanged.

- [ ] **Step 5: Run tests**

```bash
cd frontend && npx vitest run tests/unit/v2/execution-run-view.test.ts tests/unit/lib/workspace-result-preview.test.ts
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/execution-run-view.ts frontend/lib/workspace-result-preview.ts frontend/tests/unit/v2/execution-run-view.test.ts frontend/tests/unit/lib/workspace-result-preview.test.ts
git commit -m "feat: project academic review packets in workbench"
```

---

## Task 11: Wire Right-Panel UX To Review Packet And Run Browser QA

**Files:**

- Modify: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/useLiveWorkflowViewModel.ts`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/ReviewView.tsx`
- Modify: `frontend/app/(workbench)/workspaces/[id]/components/live-workflow/EvidenceView.tsx`
- Modify: `frontend/tests/unit/v2/live-workflow-view-model.test.ts`
- Modify: `frontend/tests/unit/v2/LiveWorkflowPanel.test.tsx`
- Modify: `frontend/tests/e2e/golden-path.spec.ts`

- [ ] **Step 1: Write failing view-model test**

Add to `frontend/tests/unit/v2/live-workflow-view-model.test.ts`:

```ts
it("prefers review packet previews over raw outputs", () => {
  const model = buildLiveWorkflowViewModel({
    records: [
      {
        id: "exec-1",
        workspace_id: "ws-1",
        execution_type: "capability",
        feature_id: "sci_literature_positioning",
        status: "completed",
        params: {},
        node_states: {},
        artifact_ids: [],
        next_actions: [],
        child_execution_ids: [],
        created_at: "2026-06-19T00:00:00Z",
        updated_at: "2026-06-19T00:00:01Z",
        result: {
          review_packet: {
            packet_id: "packet-1",
            title: "文献定位与创新点",
            summary: "1 item",
            completion_status: "complete",
            items: [
              {
                item_id: "item-1",
                kind: "document",
                title: "文献定位与创新点.md",
                summary: "主题矩阵。",
                default_checked: true,
                can_commit: true,
              },
            ],
          },
          outputs: [],
        },
        graph_structure: { mode: "team_kernel", nodes: [], edges: [] },
      },
    ],
    workspaceId: "ws-1",
    selectedRunId: null,
    focusedRunId: null,
    activeRunId: null,
    selectedPreviewId: null,
    draftEdits: {},
  });

  expect(model.previews[0].title).toBe("文献定位与创新点.md");
  expect(model.pendingReviewCount).toBe(1);
});
```

- [ ] **Step 2: Write failing UI copy test**

In `frontend/tests/unit/v2/LiveWorkflowPanel.test.tsx`, assert the right panel uses lighter review language:

```ts
expect(screen.getByText("待确认成果")).toBeInTheDocument();
expect(screen.queryByText("候选结果")).not.toBeInTheDocument();
```

Place this assertion inside the existing test that renders completed run review content.

- [ ] **Step 3: Run failing frontend tests**

```bash
cd frontend && npx vitest run tests/unit/v2/live-workflow-view-model.test.ts tests/unit/v2/LiveWorkflowPanel.test.tsx
```

Expected before implementation: view model ignores `review_packet` and UI still shows “候选结果”.

- [ ] **Step 4: Implement right-panel projection and copy**

In `useLiveWorkflowViewModel.ts`, import `buildWorkspaceResultPreviewsFromReviewPacket` and prefer packet previews:

```ts
const taskReport = selectedRecord?.result && typeof selectedRecord.result === "object"
  ? selectedRecord.result as Record<string, unknown>
  : null;
const reviewPacketPreviews = buildWorkspaceResultPreviewsFromReviewPacket(taskReport?.review_packet);
const outputPreviews = buildWorkspaceResultPreviewsFromOutputs(editedOutputs);
const reviewPreviews = buildWorkspaceResultPreviewsFromReviewItems(reviewItems);
const previews = reviewPacketPreviews.length > 0
  ? reviewPacketPreviews
  : [...outputPreviews, ...reviewPreviews];
```

Set `pendingReviewCount` to packet previews when present:

```ts
const pendingReviewCount = reviewPacketPreviews.length > 0
  ? reviewPacketPreviews.length
  : outputPreviews.length + reviewItems.length;
```

In `ReviewView.tsx`, replace default headings:

```tsx
<h3>待确认成果</h3>
<p>先预览关键成果，再保存到工作区或应用到 Prism。</p>
```

Use trust chips for quality/risk when preview raw payload has `quality_surfaces` or `risk`:

```tsx
{Array.isArray(preview.raw?.quality_surfaces) && preview.raw.quality_surfaces.length > 0 ? (
  <div className="flex flex-wrap gap-1">
    {preview.raw.quality_surfaces.slice(0, 3).map((surface) => (
      <span key={String(surface)} className="rounded-full border border-[var(--wjn-border)] px-2 py-0.5 text-[11px] text-[var(--wjn-muted)]">
        {qualitySurfaceLabel(String(surface))}
      </span>
    ))}
  </div>
) : null}
```

Add a local label helper in `ReviewView.tsx`:

```tsx
function qualitySurfaceLabel(surface: string): string {
  const labels: Record<string, string> = {
    citation_strength: "引用核验",
    claim_evidence_alignment: "证据对齐",
    review_packet_completeness: "成果可预览",
    experiment_reproducibility: "可复现",
    writing_academic_style: "学术风格",
  };
  return labels[surface] ?? "质量检查";
}
```

In `EvidenceView.tsx`, keep provenance compact:

```tsx
const safeSummary = item.summary
  .replace(/\/workspace\/tmp\/tasks\/\.harness\/outputs\/[^\s]+/g, "内部输出已收起")
  .replace(/stdout|stderr/gi, "运行摘要");
```

- [ ] **Step 5: Run frontend tests**

```bash
cd frontend && npx vitest run tests/unit/v2/live-workflow-view-model.test.ts tests/unit/v2/LiveWorkflowPanel.test.tsx tests/unit/v2/ResultCard.test.tsx
```

Expected: all selected tests pass.

- [ ] **Step 6: Extend browser golden path**

In `frontend/tests/e2e/golden-path.spec.ts`, add a flow after capability completion:

```ts
await expect(page.getByText("待确认成果")).toBeVisible();
await expect(page.getByText("先预览关键成果")).toBeVisible();
await page.getByRole("button", { name: /保存已勾选|全部接受/ }).click();
await expect(page.getByText(/已保存|保存完成/)).toBeVisible();
```

- [ ] **Step 7: Run browser test**

```bash
cd frontend && npx playwright test tests/e2e/golden-path.spec.ts --project=chromium
```

Expected: golden path passes. If backend stack is required, start it with the project's documented Docker or dev commands before this step.

- [ ] **Step 8: Commit**

```bash
git add frontend/app/'(workbench)'/workspaces/'[id]'/components/live-workflow/useLiveWorkflowViewModel.ts frontend/app/'(workbench)'/workspaces/'[id]'/components/live-workflow/ReviewView.tsx frontend/app/'(workbench)'/workspaces/'[id]'/components/live-workflow/EvidenceView.tsx frontend/tests/unit/v2/live-workflow-view-model.test.ts frontend/tests/unit/v2/LiveWorkflowPanel.test.tsx frontend/tests/e2e/golden-path.spec.ts
git commit -m "feat: show academic review packets in workflow panel"
```

---

## Task 12: Release Gate, Docs, And Full Verification

**Files:**

- Modify: `docs/current/architecture.md`
- Modify: `docs/current/workspace-current-state.md`
- Modify: `docs/current/frontend-feature-plugin-contract.md`
- Modify: `docs/current/workspace-feature-catalog.md`
- Modify: `docs/current/release-gate-checklist.md`

- [ ] **Step 1: Update current-state docs**

Apply these doc facts:

```markdown
- Academic Harness v1 is the canonical Lead/TeamKernel action contract for research evidence, sandbox artifacts, expert reports, review packets, and compact research state.
- Review Packet is the semantic completion envelope for academic outputs; ResultCard remains the chat transport and frontend block.
- ExpertReport v1 is the common expert output envelope for claims, evidence, artifacts, review items, quality checks, uncertainties, and next actions.
- First-wave SCI capabilities declare `research_evidence.review_packet: required` and surface enforcement levels.
- The right panel labels reviewable academic outputs as “待确认成果”.
```

- [ ] **Step 2: Run backend targeted suite**

```bash
cd backend && .venv/bin/python -m pytest \
  tests/agents/harness/test_research_eval_surfaces.py \
  tests/agents/harness/test_academic_aci_contracts.py \
  tests/agents/contracts/test_review_packet.py \
  tests/contracts/test_team_expert.py \
  tests/agents/lead_agent/v2/test_output_mapping.py \
  tests/agents/harness/test_research_state.py \
  tests/agents/lead_agent/v2/test_team_kernel.py \
  tests/agents/lead_agent/v2/test_team_member_context.py \
  tests/agents/harness/test_research_task_eval.py \
  tests/architecture/test_academic_harness_catalog.py \
  -v
```

Expected: all selected tests pass.

- [ ] **Step 3: Run frontend targeted suite**

```bash
cd frontend && npx vitest run \
  tests/unit/v2/execution-run-view.test.ts \
  tests/unit/lib/workspace-result-preview.test.ts \
  tests/unit/v2/live-workflow-view-model.test.ts \
  tests/unit/v2/LiveWorkflowPanel.test.tsx
```

Expected: all selected tests pass.

- [ ] **Step 4: Run architecture guards**

```bash
cd backend && .venv/bin/python -m pytest tests/architecture/test_native_harness_boundaries.py tests/architecture/test_layer_boundaries.py tests/architecture/test_docs_current_contract.py -v
```

Expected: all selected tests pass.

- [ ] **Step 5: Run build/type checks**

```bash
cd frontend && npm run typecheck && npm run build
```

Expected: TypeScript check and production build complete successfully.

- [ ] **Step 6: Run browser smoke**

Start the full local stack with the documented command for the current branch:

```bash
docker compose up --build
```

In another shell:

```bash
cd frontend && npx playwright test tests/e2e/golden-path.spec.ts --project=chromium
```

Expected: the test can launch a workspace, trigger a capability with enough context, see “待确认成果”, preview a result, and save selected output.

- [ ] **Step 7: Final status check**

```bash
git status --short
git log --oneline -12
```

Expected: only intended docs/test/code changes are present. No generated screenshots, cache files, logs, or sandbox artifacts are staged.

- [ ] **Step 8: Commit docs and final polish**

```bash
git add docs/current/architecture.md docs/current/workspace-current-state.md docs/current/frontend-feature-plugin-contract.md docs/current/workspace-feature-catalog.md docs/current/release-gate-checklist.md
git commit -m "docs: update academic harness current state"
```

---

## Plan Self-Review

### Spec Coverage

- Wenjin Academic ACI v1: Task 2 defines observation and permission contracts; Task 7 integrates runtime output flow.
- Review Packet / ResultCard v2: Task 3 defines the contract; Task 5 maps expert reports; Task 10 and Task 11 project it in frontend.
- Expert and skill output contracts: Task 4 defines ExpertReport; Task 9 updates first-wave skills.
- Expert pipeline refactor: Task 7 integrates ExpertReport into TeamKernel; Task 9 declares first-wave capability policy and ordered surface expectations.
- Quality gate surfaces: Task 1 expands the registry; Task 8 evaluates new deterministic surfaces; Task 10 projects trust highlights.
- Context compaction: Task 6 defines compact research state; Task 7 injects it into member context.
- Architecture convergence: every task stays inside existing Chat Agent / Lead Agent / TeamKernel / harness / ResultCard / RunView boundaries.

### Placeholder Scan

This plan contains no empty markers, unnamed future work, or vague edge-handling instructions. Each implementation task includes file paths, concrete tests, commands, expected failure/pass states, and commit commands.

### Type Consistency

- Review Packet uses `schema_version`, `packet_id`, `item_id`, `completion_status`, and `quality_surfaces` consistently across Python and TypeScript projections.
- ExpertReport uses `schema_version`, `expert_id`, `skill_id`, `claims`, `evidence`, `artifacts`, `quality_gates_checked`, `uncertainties`, and `next_actions` consistently across sanitizer, mapper, and seed prompt guidance.
- Research surfaces use `required_runtime`, `required_final`, and `diagnostic` consistently in registry, seed policy, and evaluator plan.
- Frontend uses `reviewPacket` in `RunView` and `buildWorkspaceResultPreviewsFromReviewPacket` in preview projection.

### Execution Recommendation

Use Subagent-Driven execution. The tasks are independent enough for fresh implementation agents, but they need review after each contract/runtime boundary because a mistake in early schema names will cascade into seeds and frontend projection.
