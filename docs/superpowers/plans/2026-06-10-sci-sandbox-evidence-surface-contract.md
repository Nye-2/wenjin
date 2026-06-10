# SCI Sandbox Evidence Surface Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make SCI sandbox-heavy capabilities declare the deterministic research evidence surfaces they require, so `workflow_trace` and `output_ref_reuse` are part of the data-driven capability contract instead of only living in tests or docs.

**Architecture:** Keep the existing `ChatAgent -> LeadAgent -> TeamKernel/static graph -> ReactSubagent -> Wenjin Harness -> DataService/Sandbox/Review` chain. Add a small capability-definition contract under `definition_json.research_evidence.required_surfaces`, project it through `LeadAgentRuntime._capability_policy()`, and enforce seed invariants for SCI sandbox capabilities. Do not add a new evaluator runner, new quality-gate framework, compatibility layer, or frontend surface in this slice.

**Tech Stack:** Python 3.13, pytest, PyYAML seed tests, existing capability v2 YAML seeds, existing deterministic `research_task_eval` surfaces.

---

## Scope

Do:

- Add a data-driven `research_evidence.required_surfaces` contract to SCI sandbox capabilities that should be evaluated by deterministic research evidence checks.
- Enforce that sandbox-required SCI capabilities with `run_python` declare `workflow_trace`, `experiment_interpretation`, and `output_ref_reuse` when they generate/consume sandbox evidence.
- Project `research_evidence` through `LeadAgentRuntime._capability_policy()` so downstream runtime/tests can inspect it.
- Update docs to say this is a capability contract, not a new runtime.

Do not:

- Do not make `evaluate_research_task_evidence()` run automatically inside TeamKernel in this slice.
- Do not add a generic shell, new run table, external SDK, deer-flow runtime, or second quality gate system.
- Do not require non-sandbox literature/writing capabilities to declare `output_ref_reuse`.

## Files

- Modify: `backend/tests/integration/test_capability_skill_seeds.py`
  - Add seed invariant tests for `research_evidence.required_surfaces`.
- Modify: `backend/seed/capabilities/sci/sci_empirical_package.yaml`
  - Declare required deterministic evidence surfaces for the empirical package.
- Modify: `backend/seed/capabilities/sci/reproducibility_audit.yaml`
  - Declare required deterministic evidence surfaces for reproducibility review.
- Modify if needed: `backend/seed/capabilities/sci/internal_sandbox_smoke.yaml`
  - Keep hidden infrastructure smoke excluded from user-facing research-evidence requirements unless the invariant says otherwise.
- Modify: `backend/src/agents/lead_agent/v2/runtime.py`
  - Project `research_evidence` into capability policy.
- Modify or add test: `backend/tests/agents/lead_agent/v2/test_runtime.py`
  - Assert `_capability_policy()` preserves `research_evidence`.
- Modify: `docs/current/native-harness-external-gap-matrix.md`
- Modify: `docs/current/native-harness-convergence-audit.md`
- Modify: `docs/current/release-gate-checklist.md`

---

### Task 1: Add Seed Invariant for Research Evidence Surfaces

- [x] **Step 1: Write failing seed invariant**

Add a test to `backend/tests/integration/test_capability_skill_seeds.py`:

```python
def test_sci_sandbox_research_capabilities_declare_evidence_surfaces():
    required = {
        "sci_empirical_package": {
            "literature",
            "experiment",
            "writing",
            "workflow_trace",
            "experiment_interpretation",
            "output_ref_reuse",
        },
        "reproducibility_audit": {
            "experiment",
            "workflow_trace",
            "experiment_interpretation",
            "output_ref_reuse",
        },
    }
    by_id = {
        yaml.safe_load(path.read_text())["id"]: path
        for path in _collect_capability_files()
    }
    for capability_id, required_surfaces in required.items():
        data = yaml.safe_load(by_id[capability_id].read_text())
        research_evidence = data.get("research_evidence") or {}
        surfaces = set(research_evidence.get("required_surfaces") or [])
        assert required_surfaces <= surfaces, (
            f"{capability_id}: missing research evidence surfaces "
            f"{sorted(required_surfaces - surfaces)}"
        )
```

- [x] **Step 2: Run RED test**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/integration/test_capability_skill_seeds.py::test_sci_sandbox_research_capabilities_declare_evidence_surfaces -q
```

Expected: fail because the field does not exist in these seed files yet.

- [x] **Step 3: Add seed fields**

Add to `backend/seed/capabilities/sci/sci_empirical_package.yaml`:

```yaml
research_evidence:
  required_surfaces:
    - literature
    - experiment
    - writing
    - workflow_trace
    - experiment_interpretation
    - output_ref_reuse
  notes:
    - The workflow must produce reviewable literature, sandbox artifact, writing output, member execution trace, interpreted experiment evidence, and reused output refs when recoverable refs exist.
```

Add to `backend/seed/capabilities/sci/reproducibility_audit.yaml`:

```yaml
research_evidence:
  required_surfaces:
    - experiment
    - workflow_trace
    - experiment_interpretation
    - output_ref_reuse
  notes:
    - The audit focuses on reproducible sandbox evidence, member execution trace, interpreted results, and output-ref reuse before rerunning expensive work.
```

- [x] **Step 4: Run GREEN seed test**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/integration/test_capability_skill_seeds.py::test_sci_sandbox_research_capabilities_declare_evidence_surfaces -q
```

Expected: pass.

### Task 2: Project Research Evidence Into Runtime Capability Policy

- [x] **Step 1: Add runtime policy test**

Add a test to `backend/tests/agents/lead_agent/v2/test_runtime.py` or extend an existing `_capability_policy` test:

```python
def test_capability_policy_preserves_research_evidence_contract() -> None:
    capability = SimpleNamespace(
        definition_json={
            "research_evidence": {
                "required_surfaces": ["workflow_trace", "output_ref_reuse"],
                "notes": ["reuse output refs before rerunning"],
            }
        }
    )

    policy = LeadAgentRuntime._capability_policy(capability)

    assert policy["research_evidence"] == {
        "required_surfaces": ["workflow_trace", "output_ref_reuse"],
        "notes": ["reuse output refs before rerunning"],
    }
```

- [x] **Step 2: Run RED runtime test**

Run the focused test. Expected: fail because `_capability_policy()` currently omits `research_evidence`.

- [x] **Step 3: Implement runtime projection**

In `backend/src/agents/lead_agent/v2/runtime.py`, add:

```python
"research_evidence": dict(definition.get("research_evidence") or {}),
```

to `_capability_policy()` return value.

- [x] **Step 4: Run GREEN runtime test**

Run the focused test again. Expected: pass.

### Task 3: Verify and Document

- [x] **Step 1: Run focused tests**

```bash
cd backend && .venv/bin/python -m pytest \
  tests/integration/test_capability_skill_seeds.py::test_sci_sandbox_research_capabilities_declare_evidence_surfaces \
  tests/agents/lead_agent/v2/test_runtime.py::test_capability_policy_preserves_research_evidence_contract -q
```

- [x] **Step 2: Run broader seed/runtime checks**

```bash
cd backend && .venv/bin/python -m pytest tests/integration/test_capability_skill_seeds.py tests/agents/lead_agent/v2/test_runtime.py::test_run_session_prism_review_items_satisfy_writing_evidence_eval -q
```

- [x] **Step 3: Run Ruff on changed Python**

```bash
cd backend && .venv/bin/ruff check src/agents/lead_agent/v2/runtime.py tests/integration/test_capability_skill_seeds.py tests/agents/lead_agent/v2/test_runtime.py
```

- [x] **Step 4: Update docs**

Document that `research_evidence.required_surfaces` is the data-driven capability contract for deterministic research evidence checks. State that automatic enforcement inside TeamKernel is intentionally deferred; release gates and targeted workflow smoke tests can read the contract today.

- [x] **Step 5: Run drift and diff checks**

```bash
rg -n "from .*codex|import .*codex|cc-switch|ccswitch|deerflow|deer-flow|sandbox\.run_command|/mnt/user-data" \
  backend/src/agents/harness \
  backend/src/agents/lead_agent/v2 \
  backend/src/subagents/v2 \
  backend/src/sandbox/providers \
  backend/src/services/release_gate_service.py \
  backend/src/quality/release_gate.py -g '*.py'
git diff --check
```

Expected: drift scan no output; diff check no output.

- [ ] **Step 6: Commit**

```bash
git add \
  backend/seed/capabilities/sci/sci_empirical_package.yaml \
  backend/seed/capabilities/sci/reproducibility_audit.yaml \
  backend/src/agents/lead_agent/v2/runtime.py \
  backend/tests/integration/test_capability_skill_seeds.py \
  backend/tests/agents/lead_agent/v2/test_runtime.py \
  docs/current/native-harness-external-gap-matrix.md \
  docs/current/native-harness-convergence-audit.md \
  docs/current/release-gate-checklist.md \
  docs/superpowers/plans/2026-06-10-sci-sandbox-evidence-surface-contract.md
git commit -m "feat: declare sci sandbox evidence surfaces"
```

## Completion Criteria

- SCI sandbox user-facing capabilities declare deterministic research evidence surfaces in seed data.
- Runtime capability policy exposes the same contract.
- Tests prove seed and runtime projection behavior.
- No new runtime, fallback layer, external SDK, generic shell, or hidden-path exposure is introduced.
