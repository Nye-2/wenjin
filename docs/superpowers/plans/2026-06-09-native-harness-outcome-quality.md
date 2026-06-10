# Native Harness Outcome Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first deterministic outcome-quality gate to Wenjin native harness so research outputs are evaluated for strong citation/source support, not only structural closure.

**Architecture:** Keep the existing `ChatAgent -> LeadAgent -> TeamKernel/static graph -> ReactSubagent -> Wenjin Harness -> DataService/Sandbox/Review` chain. Add an optional `citation_strength` research-eval surface that consumes existing `citation_source_audit` / team quality-gate metadata; do not add a new runtime, second event store, Codex SDK bridge, or compatibility layer.

**Tech Stack:** Python 3.13, Pydantic v2 task contracts, existing Wenjin harness metadata, pytest, Ruff, docs/current architecture records.

**Execution Status:** Implemented in this branch on 2026-06-09. RED covered missing `citation_strength`, `not_ready` rejection, and weak-status priority over low-risk, then GREEN verified `tests/agents/harness/test_research_task_eval.py` with 12 passed, Ruff on changed Python files, `git diff --check`, and the native harness regression gate with 300 passed.

---

## Scope Boundary

This slice is intentionally narrow. It improves output-quality verification without changing agent orchestration.

Implement:
- Add `citation_strength` as an optional `ResearchSurface`.
- Treat `literature` as structural evidence coverage, preserving current weak-reference acceptance where tests already rely on it.
- Treat `citation_strength` as stricter quality evidence: weak-only audit refs fail, supported/verified/low-risk refs pass, fabricated/missing/high-risk refs are rejected.
- Expose bounded evidence payloads so release gates can show why a task passed or failed.
- Update current docs so future workers understand this is a quality gate, not a new runtime.

Do not implement in this slice:
- No Codex SDK, cc-switch, ACP, deer-flow runtime, or protocol bridge.
- No generic `sandbox.run_command`.
- No new DB table or frontend stream/store.
- No refactor of the team quality-gate engine unless tests prove a bug in the existing contract.
- No browser testing for this backend-only gate unless a frontend route is changed later.

## File Structure

Modify:
- `backend/src/agents/harness/research_task_eval.py`
  - Add `citation_strength` surface.
  - Add helper functions for strict citation audit evidence.
  - Reuse existing audit extraction helpers where possible.
- `backend/tests/agents/harness/test_research_task_eval.py`
  - Add red/green tests for strict citation strength.
  - Preserve existing weak-reference literature test.
- `docs/current/architecture.md`
  - Record optional outcome-quality eval surface.
- `docs/current/native-harness-external-gap-matrix.md`
  - Mark citation strength as the first implemented content-quality gate and list remaining gaps.
- `docs/current/native-harness-convergence-audit.md`
  - Add this slice to convergence history.
- `docs/current/release-gate-checklist.md`
  - Add the focused and native-harness verification commands.

No new files are needed besides this plan.

---

### Task 1: Write Failing Citation Strength Tests

**Files:**
- Modify: `backend/tests/agents/harness/test_research_task_eval.py`

- [ ] **Step 1: Add a passing test for supported citation audit refs**

Append this test after `test_research_task_eval_accepts_team_quality_gate_citation_refs`:

```python
def test_research_task_eval_passes_citation_strength_with_supported_audit_refs() -> None:
    evaluation = evaluate_research_task_evidence(
        _report(),
        node_events=[
            {
                "node_type": "agent_invocation",
                "status": "completed",
                "node_metadata": {
                    "template_id": "citation_auditor.v1",
                    "harness": {
                        "citation_source_audit": [
                            {
                                "schema": "wenjin.quality.citation_source_audit_finding.v1",
                                "source_id": "source-1",
                                "citation_key": "smith2026",
                                "status": "supported",
                                "risk": "low",
                                "severity": "medium",
                                "claim": "The method comparison is supported by the cited paper.",
                            }
                        ]
                    },
                },
            }
        ],
        required_surfaces=("citation_strength",),
    )

    assert evaluation.status == "pass"
    assert evaluation.coverage == {"citation_strength": "pass"}
    assert evaluation.findings == []
    assert evaluation.evidence["citation_strength"] == {
        "strong_refs": [
            {
                "source_id": "source-1",
                "citation_key": "smith2026",
                "status": "supported",
                "risk": "low",
                "severity": "medium",
            }
        ],
        "weak_refs": [],
        "rejected_refs": [],
        "strong_count": 1,
        "weak_count": 0,
        "rejected_count": 0,
    }
```

- [ ] **Step 2: Add a failing test for weak-only refs**

Append this test after the passing citation-strength test:

```python
def test_research_task_eval_fails_citation_strength_when_refs_are_only_weak() -> None:
    evaluation = evaluate_research_task_evidence(
        _report(),
        node_events=[
            {
                "node_type": "agent_invocation",
                "status": "completed",
                "node_metadata": {
                    "template_id": "citation_auditor.v1",
                    "harness": {
                        "citation_source_audit": [
                            {
                                "schema": "wenjin.quality.citation_source_audit_finding.v1",
                                "source_id": "source-1",
                                "citation_key": "smith2026",
                                "status": "weak",
                                "risk": "weak",
                                "severity": "medium",
                                "claim": "The central claim has only partial support.",
                            }
                        ]
                    },
                },
            }
        ],
        required_surfaces=("citation_strength",),
    )

    assert evaluation.status == "fail"
    assert evaluation.coverage == {"citation_strength": "fail"}
    assert evaluation.findings == [
        {
            "surface": "citation_strength",
            "severity": "high",
            "message": "No strong citation/source audit evidence was produced.",
        }
    ]
    assert evaluation.evidence["citation_strength"] == {
        "strong_refs": [],
        "weak_refs": [
            {
                "source_id": "source-1",
                "citation_key": "smith2026",
                "status": "weak",
                "risk": "weak",
                "severity": "medium",
            }
        ],
        "rejected_refs": [],
        "strong_count": 0,
        "weak_count": 1,
        "rejected_count": 0,
    }
```

- [ ] **Step 3: Add a failing test for fabricated/high-risk refs**

Append this test after the weak-only test:

```python
def test_research_task_eval_rejects_citation_strength_with_fabricated_refs() -> None:
    evaluation = evaluate_research_task_evidence(
        _report(),
        node_events=[
            {
                "node_type": "agent_invocation",
                "status": "completed",
                "node_metadata": {
                    "template_id": "citation_auditor.v1",
                    "harness": {
                        "citation_source_audit": [
                            {
                                "schema": "wenjin.quality.citation_source_audit_finding.v1",
                                "source_id": "source-1",
                                "citation_key": "smith2026",
                                "status": "fabricated",
                                "risk": "fabricated",
                                "severity": "critical",
                                "claim": "This should never satisfy citation strength.",
                            }
                        ]
                    },
                },
            }
        ],
        required_surfaces=("citation_strength",),
    )

    assert evaluation.status == "fail"
    assert evaluation.coverage == {"citation_strength": "fail"}
    assert evaluation.evidence["citation_strength"]["strong_refs"] == []
    assert evaluation.evidence["citation_strength"]["rejected_refs"] == [
        {
            "source_id": "source-1",
            "citation_key": "smith2026",
            "status": "fabricated",
            "risk": "fabricated",
            "severity": "critical",
        }
    ]
```

- [ ] **Step 4: Run tests and verify failure is from missing surface**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/harness/test_research_task_eval.py -q
```

Expected:

```text
KeyError: 'citation_strength'
```

or an equivalent failure showing `citation_strength` is not implemented yet.

---

### Task 2: Implement `citation_strength` Surface

**Files:**
- Modify: `backend/src/agents/harness/research_task_eval.py`

- [ ] **Step 1: Extend surface literal and checks map**

Change:

```python
ResearchSurface = Literal["literature", "experiment", "writing", "workflow_trace"]
```

to:

```python
ResearchSurface = Literal[
    "literature",
    "experiment",
    "writing",
    "workflow_trace",
    "citation_strength",
]
```

Add to `checks`:

```python
"citation_strength": _evaluate_citation_strength,
```

- [ ] **Step 2: Add strict citation-strength evaluator**

Insert this function after `_evaluate_literature`:

```python
def _evaluate_citation_strength(
    report: TaskReport,
    node_events: list[dict[str, Any]],
) -> tuple[bool, dict[str, Any], str]:
    del report
    evidence = _citation_strength_evidence(node_events)
    if evidence["strong_count"] > 0:
        return True, evidence, ""
    return (
        False,
        evidence,
        "No strong citation/source audit evidence was produced.",
    )
```

- [ ] **Step 3: Add bounded evidence classification helpers**

Insert these helpers near the existing citation-audit helpers:

```python
_STRONG_CITATION_AUDIT_STATUSES = {
    "accepted",
    "grounded",
    "ready",
    "supported",
    "verified",
}
_STRONG_CITATION_AUDIT_RISKS = {
    "grounded",
    "low",
    "verified",
}
_WEAK_CITATION_AUDIT_STATUSES = {
    "partial",
    "uncertain",
    "weak",
}
_WEAK_CITATION_AUDIT_RISKS = {
    "medium",
    "partial",
    "uncertain",
    "weak",
}
_REJECTED_CITATION_AUDIT_STATUSES = {
    "blocked",
    "contradicted",
    "fabricated",
    "missing",
    "missing_source",
    "unsupported",
}
```

```python
def _citation_strength_evidence(node_events: list[dict[str, Any]]) -> dict[str, Any]:
    strong_refs: list[dict[str, str]] = []
    weak_refs: list[dict[str, str]] = []
    rejected_refs: list[dict[str, str]] = []
    for finding in _citation_source_findings(node_events):
        ref = _citation_strength_ref(finding)
        if not ref:
            continue
        if _citation_strength_ref_is_rejected(ref):
            _append_unique_dict(rejected_refs, ref)
            continue
        if _citation_strength_ref_is_strong(ref):
            _append_unique_dict(strong_refs, ref)
            continue
        if _citation_strength_ref_is_weak(ref):
            _append_unique_dict(weak_refs, ref)
    return {
        "strong_refs": strong_refs[:50],
        "weak_refs": weak_refs[:50],
        "rejected_refs": rejected_refs[:50],
        "strong_count": len(strong_refs),
        "weak_count": len(weak_refs),
        "rejected_count": len(rejected_refs),
    }
```

```python
def _citation_strength_ref(finding: dict[str, Any]) -> dict[str, str] | None:
    source_id = _clean_text(finding.get("source_id"))
    citation_key = _clean_text(finding.get("citation_key"))
    if not source_id and not citation_key:
        return None
    ref = {
        "source_id": source_id,
        "citation_key": citation_key,
        "status": _clean_text(finding.get("status")).lower(),
        "risk": _clean_text(finding.get("risk")).lower(),
        "severity": _clean_text(finding.get("severity")).lower(),
    }
    return {key: value for key, value in ref.items() if value}
```

```python
def _citation_strength_ref_is_rejected(ref: dict[str, str]) -> bool:
    return (
        ref.get("status") in _REJECTED_CITATION_AUDIT_STATUSES
        or ref.get("risk") in _UNTRUSTED_CITATION_AUDIT_RISKS
        or ref.get("severity") in _UNTRUSTED_CITATION_AUDIT_SEVERITIES
    )
```

```python
def _citation_strength_ref_is_strong(ref: dict[str, str]) -> bool:
    return (
        ref.get("status") in _STRONG_CITATION_AUDIT_STATUSES
        or ref.get("risk") in _STRONG_CITATION_AUDIT_RISKS
    ) and not _citation_strength_ref_is_rejected(ref)
```

```python
def _citation_strength_ref_is_weak(ref: dict[str, str]) -> bool:
    return (
        ref.get("status") in _WEAK_CITATION_AUDIT_STATUSES
        or ref.get("risk") in _WEAK_CITATION_AUDIT_RISKS
        or bool(ref.get("source_id") or ref.get("citation_key"))
    )
```

```python
def _append_unique_dict(values: list[dict[str, str]], value: dict[str, str]) -> None:
    if value not in values:
        values.append(value)
```

- [ ] **Step 4: Reuse existing extraction path**

If `research_task_eval.py` already has `_citation_source_findings_from_value`, `_team_quality_gate_citation_findings`, or equivalent helpers, implement `_citation_source_findings(node_events)` as a thin wrapper over those existing helpers instead of parsing new event shapes from scratch.

The wrapper must collect:

```python
def _citation_source_findings(node_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for event in node_events:
        metadata = _dict_value(_dict_value(event.get("node_metadata")).get("harness"))
        findings.extend(_citation_source_findings_from_value(metadata.get("citation_source_audit")))
        runtime_state = _dict_value(event.get("runtime_state"))
        findings.extend(_team_quality_gate_citation_findings(runtime_state.get("quality_gates")))
    return findings
```

If exact helper names differ, use the local names already present in the file and keep the wrapper focused.

- [ ] **Step 5: Run focused tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/harness/test_research_task_eval.py -q
```

Expected:

```text
... passed
```

---

### Task 3: Documentation Convergence

**Files:**
- Modify: `docs/current/architecture.md`
- Modify: `docs/current/native-harness-external-gap-matrix.md`
- Modify: `docs/current/native-harness-convergence-audit.md`
- Modify: `docs/current/release-gate-checklist.md`

- [ ] **Step 1: Update architecture source of truth**

Add a concise current-state note:

```markdown
- Research-task evaluation now has four structural surfaces (`literature`, `experiment`, `writing`, `workflow_trace`) plus the optional `citation_strength` outcome-quality surface. `citation_strength` is deterministic and reads existing citation/source audit metadata only; it is not a second runtime or a model judge.
```

- [ ] **Step 2: Update external gap matrix**

Add or update the quality-gate row:

```markdown
| Outcome-quality gates | Codex and DeerFlow both make execution inspectable before trust. Wenjin now has deterministic `workflow_trace` plus optional `citation_strength` checks, so citation support can fail even when structural literature coverage passes. | Remaining gaps: experiment interpretation quality, writing semantic preservation, and reviewer-facing scoring are still not fully gated. |
```

- [ ] **Step 3: Update convergence audit**

Add a new latest slice:

```markdown
## 2026-06-09 Citation Strength Eval Slice

- Added optional `citation_strength` research-eval surface.
- Preserved `literature` as structural coverage so weak audit refs can still show evidence exists.
- Required strong citation/source audit evidence for the stricter quality gate and rejected fabricated/missing/high-risk refs.
- No new runtime, no Codex SDK bridge, no extra event store.
```

- [ ] **Step 4: Update release gate checklist**

Add focused commands:

```markdown
- `cd backend && .venv/bin/python -m pytest tests/agents/harness/test_research_task_eval.py -q`
- `cd backend && .venv/bin/ruff check src/agents/harness/research_task_eval.py tests/agents/harness/test_research_task_eval.py`
```

---

### Task 4: Verification and Commit

**Files:**
- Verify all modified code and docs.

- [ ] **Step 1: Run focused eval tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/harness/test_research_task_eval.py -q
```

Expected:

```text
passed
```

- [ ] **Step 2: Run Ruff on changed Python files**

Run:

```bash
cd backend && .venv/bin/ruff check src/agents/harness/research_task_eval.py tests/agents/harness/test_research_task_eval.py
```

Expected:

```text
All checks passed!
```

- [ ] **Step 3: Run native harness regression gate**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/agents/harness/test_scheduler_and_python_tool.py tests/agents/harness/test_sandbox_file_tools.py tests/agents/harness/test_command_audit.py tests/agents/harness/test_policy_and_registry.py tests/agents/harness/test_output_budget_loop_guard_and_diff_tracker.py tests/agents/harness/test_research_task_eval.py tests/agents/harness/test_langchain_adapter.py tests/agents/harness/test_context_assembly.py tests/unit/subagents/test_react.py tests/subagents/v2/test_registry.py tests/agents/lead_agent/v2/test_team_policy.py tests/agents/lead_agent/v2/test_sandbox_runtime.py tests/agents/lead_agent/v2/test_workspace_sandbox_manager.py tests/agents/lead_agent/v2/test_runtime.py::test_run_session_prism_review_items_satisfy_writing_evidence_eval tests/architecture/test_native_harness_boundaries.py tests/dataservice/test_sandbox_domain.py tests/sandbox/test_workspace_layout.py tests/agents/lead_agent/v2/test_sandbox_artifact_discovery.py tests/agents/lead_agent/v2/test_citation_source_audit.py tests/agents/lead_agent/v2/test_team_quality_gates.py tests/services/test_workspace_prism_service.py::test_surface_projection_includes_review_provenance_and_protection tests/services/test_prism_review_projection.py tests/integration/test_harness_mock_sandbox_e2e.py -q
```

Expected:

```text
passed
```

- [ ] **Step 4: Run diff whitespace check**

Run:

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 5: Review final diff**

Run:

```bash
git diff --stat
git diff -- backend/src/agents/harness/research_task_eval.py backend/tests/agents/harness/test_research_task_eval.py
```

Expected:
- Only `citation_strength` eval, tests, and docs changed.
- No runtime, frontend, Docker, or sandbox execution-path drift.

- [ ] **Step 6: Commit**

Run:

```bash
git add backend/src/agents/harness/research_task_eval.py backend/tests/agents/harness/test_research_task_eval.py docs/current/architecture.md docs/current/native-harness-external-gap-matrix.md docs/current/native-harness-convergence-audit.md docs/current/release-gate-checklist.md docs/superpowers/plans/2026-06-09-native-harness-outcome-quality.md
git commit -m "feat: add citation strength research eval"
```

Expected:
- Commit succeeds.
- Goal remains active because broader native harness convergence is not fully complete.

---

## Follow-On Backlog After This Slice

These are next iterations, not part of this commit:

- Experiment interpretation quality: verify produced artifacts include method assumptions, metric definitions, sample size, and limitations.
- Writing semantic preservation: verify Prism edits preserve protected LaTeX structure and cite only approved refs.
- Sandbox file-context scoring: ensure each subagent’s scratch outputs are linked to review items or explicitly discarded.
- User-facing quality projection: expose only concise quality status to the UI, not internal member transcripts.
- Browser test only after a frontend projection changes.

## Self-Review

Spec coverage:
- The plan improves content output quality while staying within native harness.
- It avoids external runtime adoption and keeps existing topology.
- It gives exact files, tests, commands, and acceptance criteria.

Placeholder scan:
- No `TBD`, `TODO`, vague error-handling, or unspecified test steps.

Type consistency:
- `citation_strength` is added as a `ResearchSurface` literal, mapped in `checks`, and validated through `evaluate_research_task_evidence`.
- Evidence keys are stable: `strong_refs`, `weak_refs`, `rejected_refs`, `strong_count`, `weak_count`, `rejected_count`.
