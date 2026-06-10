# Citation Source Audit Review Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Normalize high-risk citation/source quality-gate findings into bounded evidence attached to existing TeamKernel quality gate results.

**Architecture:** Add a pure `citation_source_audit.py` helper next to TeamKernel quality gates. `quality_gates.py` remains the decision engine and embeds normalized findings into existing `QualityGateResult.findings`; no DataService table, execution stream, frontend store, external verifier, or runtime path is added.

**Tech Stack:** Python 3.13, Pydantic v2 contracts, pytest, ruff.

---

## File Structure

- Create `backend/src/agents/lead_agent/v2/team/citation_source_audit.py`
  - Pure normalizer for bounded citation/source audit evidence.
  - No side effects and no DataService/runtime dependency.
- Create `backend/tests/agents/lead_agent/v2/test_citation_source_audit.py`
  - Unit tests for normalizer behavior.
- Modify `backend/src/agents/lead_agent/v2/team/quality_gates.py`
  - Import normalizer and attach normalized evidence under `findings[*].citation_source_audit`.
- Modify `backend/tests/agents/lead_agent/v2/test_team_quality_gates.py`
  - Integration assertion that quality gates expose audit evidence.
- Modify `docs/current/native-harness-convergence-audit.md`
  - Record the closure and verification evidence.
- Modify `docs/current/architecture.md`
  - Mention citation/source audit evidence stays inside existing TeamKernel quality gate projection.

## Task 1: Pure Citation/Source Audit Normalizer

**Files:**
- Create: `backend/src/agents/lead_agent/v2/team/citation_source_audit.py`
- Create: `backend/tests/agents/lead_agent/v2/test_citation_source_audit.py`

- [ ] **Step 1: Write failing normalizer tests**

Create `backend/tests/agents/lead_agent/v2/test_citation_source_audit.py` with:

```python
from src.agents.lead_agent.v2.team.citation_source_audit import (
    collect_citation_source_audit_findings,
)


def test_collects_fabrication_and_missing_source_findings() -> None:
    findings = collect_citation_source_audit_findings(
        invocation_id="citation_auditor.v1__1",
        template_id="citation_auditor.v1",
        display_name="引文审计员",
        output={
            "fabrication_risks": [
                {
                    "citation_key": "fake2026",
                    "claim": "A fabricated claim",
                    "status": "fabricated",
                    "severity": "high",
                    "message": "not found in library",
                }
            ],
            "missing_sources": [
                {
                    "claim": "Needs a source",
                    "status": "missing",
                    "suggested_action": "find_source",
                }
            ],
        },
        quality_contract={
            "allowed_citation_keys": ["smith2026"],
            "allowed_source_ids": ["source-1"],
        },
        active_gate_ids={"no_fabricated_citations", "weak_support_flagged"},
    )

    assert findings == [
        {
            "schema": "wenjin.quality.citation_source_audit_finding.v1",
            "invocation_id": "citation_auditor.v1__1",
            "template_id": "citation_auditor.v1",
            "display_name": "引文审计员",
            "field": "fabrication_risks",
            "index": 0,
            "risk": "fabricated",
            "severity": "high",
            "citation_key": None,
            "source_id": None,
            "unknown_refs": ["fake2026"],
            "claim": "A fabricated claim",
            "message": "not found in library",
            "suggested_action": "replace_or_remove_citation",
        },
        {
            "schema": "wenjin.quality.citation_source_audit_finding.v1",
            "invocation_id": "citation_auditor.v1__1",
            "template_id": "citation_auditor.v1",
            "display_name": "引文审计员",
            "field": "missing_sources",
            "index": 0,
            "risk": "missing",
            "severity": None,
            "citation_key": None,
            "source_id": None,
            "unknown_refs": [],
            "claim": "Needs a source",
            "message": "Source is missing for this claim.",
            "suggested_action": "find_source",
        },
    ]


def test_records_unknown_refs_without_trusting_them() -> None:
    findings = collect_citation_source_audit_findings(
        invocation_id="source_quality_auditor.v1__1",
        template_id="source_quality_auditor.v1",
        display_name=None,
        output={
            "citation_key_audit": [
                {
                    "citation_key": "missing2026",
                    "source_id": "source-2",
                    "status": "not_ready",
                    "claim": "Unsupported claim",
                }
            ]
        },
        quality_contract={
            "allowed_citation_keys": ["smith2026"],
            "allowed_source_ids": ["source-1"],
        },
        active_gate_ids={"claim_source_binding_checked"},
    )

    assert findings[0]["citation_key"] is None
    assert findings[0]["source_id"] is None
    assert findings[0]["unknown_refs"] == ["source-2", "missing2026"]


def test_ignores_safe_entries() -> None:
    findings = collect_citation_source_audit_findings(
        invocation_id="citation_auditor.v1__1",
        template_id="citation_auditor.v1",
        display_name=None,
        output={
            "citation_key_audit": [
                {
                    "citation_key": "smith2026",
                    "source_id": "source-1",
                    "status": "ready",
                    "severity": "low",
                }
            ],
            "fabrication_risks": [],
            "missing_sources": [],
        },
        quality_contract={
            "allowed_citation_keys": ["smith2026"],
            "allowed_source_ids": ["source-1"],
        },
        active_gate_ids={"no_fabricated_citations", "claim_source_binding_checked"},
    )

    assert findings == []
```

- [ ] **Step 2: Run RED**

Run:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/agents/lead_agent/v2/test_citation_source_audit.py -q
```

Expected: fail with `ModuleNotFoundError` or missing function.

- [ ] **Step 3: Implement normalizer**

Create `citation_source_audit.py` with:

```python
"""Normalize citation/source quality audit evidence for TeamKernel."""

from __future__ import annotations

from typing import Any

AUDIT_FINDING_SCHEMA = "wenjin.quality.citation_source_audit_finding.v1"
MAX_FINDINGS_PER_INVOCATION = 20
TEXT_LIMIT = 240

CITATION_SOURCE_AUDIT_FIELDS_BY_GATE = {
    "source_authority_checked": ("citation_key_audit",),
    "metadata_completeness_checked": ("citation_key_audit", "missing_sources"),
    "weak_support_flagged": ("missing_sources", "fabrication_risks"),
    "no_fabricated_citations": ("fabrication_risks",),
    "claim_source_binding_checked": ("citation_key_audit", "missing_sources"),
    "style_consistency_checked": ("bibtex_projection_notes",),
}

BLOCKING_STATUSES = {
    "blocked",
    "contradicted",
    "fabricated",
    "incomplete",
    "missing",
    "missing_metadata",
    "needs_replacement",
    "not_ready",
    "replace",
    "unsupported",
    "weak",
    "weakly_supported",
}
BLOCKING_SEVERITIES = {"blocking", "critical", "high"}


def collect_citation_source_audit_findings(
    *,
    invocation_id: str,
    template_id: str,
    display_name: str | None,
    output: dict[str, Any],
    quality_contract: dict[str, Any],
    active_gate_ids: set[str],
) -> list[dict[str, Any]]:
    fields = _fields_for_active_gates(active_gate_ids)
    if not fields:
        return []
    allowed_sources = set(_string_list(quality_contract.get("allowed_source_ids")))
    allowed_citations = set(_string_list(quality_contract.get("allowed_citation_keys")))
    findings: list[dict[str, Any]] = []
    for field in fields:
        raw_entries = output.get(field)
        if not isinstance(raw_entries, list):
            continue
        for index, item in enumerate(raw_entries):
            if not isinstance(item, dict):
                continue
            finding = _finding_from_entry(
                invocation_id=invocation_id,
                template_id=template_id,
                display_name=display_name,
                field=field,
                index=index,
                item=item,
                allowed_sources=allowed_sources,
                allowed_citations=allowed_citations,
            )
            if finding:
                findings.append(finding)
            if len(findings) >= MAX_FINDINGS_PER_INVOCATION:
                return findings
    return findings


def _fields_for_active_gates(active_gate_ids: set[str]) -> list[str]:
    fields: list[str] = []
    for gate_id in active_gate_ids:
        fields.extend(CITATION_SOURCE_AUDIT_FIELDS_BY_GATE.get(gate_id, ()))
    return _dedupe(fields)


def _finding_from_entry(
    *,
    invocation_id: str,
    template_id: str,
    display_name: str | None,
    field: str,
    index: int,
    item: dict[str, Any],
    allowed_sources: set[str],
    allowed_citations: set[str],
) -> dict[str, Any] | None:
    risk = _risk_status(item, field=field)
    severity = _severity(item)
    refs = _refs(item)
    unknown_refs = [
        *[ref for ref in refs["source_ids"] if allowed_sources and ref not in allowed_sources],
        *[ref for ref in refs["citation_keys"] if allowed_citations and ref not in allowed_citations],
    ]
    if not risk and not severity and not unknown_refs:
        return None
    citation_key = refs["citation_keys"][0] if refs["citation_keys"] and not unknown_refs else None
    source_id = refs["source_ids"][0] if refs["source_ids"] and not unknown_refs else None
    return {
        "schema": AUDIT_FINDING_SCHEMA,
        "invocation_id": invocation_id,
        "template_id": template_id,
        "display_name": display_name,
        "field": field,
        "index": index,
        "risk": risk or None,
        "severity": severity or None,
        "citation_key": citation_key,
        "source_id": source_id,
        "unknown_refs": _dedupe(unknown_refs),
        "claim": _clean_text(item.get("claim") or item.get("statement") or item.get("finding")),
        "message": _message(item, field=field, risk=risk, unknown_refs=unknown_refs),
        "suggested_action": _suggested_action(item, field=field, risk=risk, unknown_refs=unknown_refs),
    }


def _risk_status(item: dict[str, Any], *, field: str) -> str:
    for key in ("status", "decision", "readiness", "result"):
        value = _normalized_token(item.get(key))
        if value in BLOCKING_STATUSES:
            return value
    if field == "fabrication_risks":
        return _normalized_token(item.get("status")) or "present"
    if field == "missing_sources":
        return _normalized_token(item.get("status")) or "missing_source"
    return ""


def _severity(item: dict[str, Any]) -> str:
    for key in ("severity", "risk_level"):
        value = _normalized_token(item.get(key))
        if value in BLOCKING_SEVERITIES:
            return value
    return ""


def _refs(item: dict[str, Any]) -> dict[str, list[str]]:
    source_ids: list[str] = []
    citation_keys: list[str] = []
    for key in ("source_id", "source_ids", "source_ref", "source_refs"):
        source_ids.extend(_string_list(item.get(key)))
    for key in ("citation_key", "citation_keys", "bibtex_key", "bibtex_keys"):
        citation_keys.extend(_string_list(item.get(key)))
    return {"source_ids": _dedupe(source_ids), "citation_keys": _dedupe(citation_keys)}


def _message(
    item: dict[str, Any],
    *,
    field: str,
    risk: str,
    unknown_refs: list[str],
) -> str:
    explicit = _clean_text(item.get("message") or item.get("reason") or item.get("issue"))
    if explicit:
        return explicit
    if unknown_refs:
        return "Citation/source refs are outside the current workspace Library context."
    if field == "missing_sources":
        return "Source is missing for this claim."
    if field == "fabrication_risks" or risk in {"fabricated", "present"}:
        return "Citation appears fabricated or unsupported by the current workspace Library."
    return "Citation/source audit finding requires review."


def _suggested_action(
    item: dict[str, Any],
    *,
    field: str,
    risk: str,
    unknown_refs: list[str],
) -> str:
    explicit = _clean_text(item.get("suggested_action") or item.get("recommendation"))
    if explicit:
        return explicit
    if unknown_refs:
        return "replace_with_workspace_source"
    if field == "missing_sources":
        return "find_source"
    if field == "fabrication_risks" or risk in {"fabricated", "present"}:
        return "replace_or_remove_citation"
    return "review_citation_source_binding"


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list | tuple | set):
        return [
            str(item).strip()
            for item in value
            if str(item or "").strip()
        ]
    return [str(value).strip()] if str(value or "").strip() else []


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _clean_text(value: Any) -> str:
    text = str(value or "").strip()
    text = " ".join(text.split())
    return text[:TEXT_LIMIT]


def _normalized_token(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text.replace(" ", "_").replace("-", "_")
```

- [ ] **Step 4: Run GREEN**

Run:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/agents/lead_agent/v2/test_citation_source_audit.py -q
```

Expected: 3 tests pass.

## Task 2: Quality Gate Integration

**Files:**
- Modify: `backend/src/agents/lead_agent/v2/team/quality_gates.py`
- Modify: `backend/tests/agents/lead_agent/v2/test_team_quality_gates.py`

- [ ] **Step 1: Write failing integration test**

Add a test to `backend/tests/agents/lead_agent/v2/test_team_quality_gates.py`:

```python
def test_quality_gates_embed_citation_source_audit_evidence_for_high_risk_findings() -> None:
    contract = {
        "template_id": "citation_auditor.v1",
        "quality_gates": ["no_fabricated_citations"],
        "allowed_citation_keys": ["smith2026"],
        "allowed_source_ids": ["source-1"],
    }
    gates = evaluate_quality_gates(
        ["no_fabricated_citations"],
        [
            AgentInvocation(
                id="citation_auditor.v1__1",
                template_id="citation_auditor.v1",
                display_name="引文审计员",
                status="succeeded",
                input_brief={"quality_contract": contract},
                output_report={
                    "quality_gates_checked": ["no_fabricated_citations"],
                    "fabrication_risks": [
                        {
                            "citation_key": "fake2026",
                            "claim": "Unsupported claim",
                            "status": "fabricated",
                            "severity": "high",
                        }
                    ],
                },
            )
        ],
        team_policy=CapabilityTeamPolicy(core_templates=["citation_auditor.v1"]),
        counts=Counter({"citation_auditor.v1": 1}),
    )

    gate = next(item for item in gates if item.gate_id == "no_fabricated_citations")
    finding = gate.findings[0]
    assert finding["citation_source_audit"][0]["schema"] == (
        "wenjin.quality.citation_source_audit_finding.v1"
    )
    assert finding["citation_source_audit"][0]["unknown_refs"] == ["fake2026"]
    assert finding["citation_source_audit"][0]["suggested_action"] == "replace_or_remove_citation"
```

- [ ] **Step 2: Run RED**

Run:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/agents/lead_agent/v2/test_team_quality_gates.py -k citation_source_audit -q
```

Expected: fail because `citation_source_audit` is not embedded.

- [ ] **Step 3: Integrate normalizer**

In `quality_gates.py`, import:

```python
from .citation_source_audit import collect_citation_source_audit_findings
```

Inside `_foundation_field_gates()`, after building `finding`, attach:

```python
audit_findings = collect_citation_source_audit_findings(
    invocation_id=invocation.id,
    template_id=invocation.template_id,
    display_name=invocation.display_name,
    output=output,
    quality_contract=contract,
    active_gate_ids={gate_id},
)
if audit_findings:
    finding["citation_source_audit"] = audit_findings
```

Do not change `QualityGateResult` shape or next-action behavior.

- [ ] **Step 4: Run integration tests**

Run:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/agents/lead_agent/v2/test_team_quality_gates.py -q
.venv/bin/python -m pytest tests/agents/lead_agent/v2/test_citation_source_audit.py -q
```

Expected: all selected tests pass.

## Task 3: Docs, Verification, Commit

**Files:**
- Modify: `docs/current/native-harness-convergence-audit.md`
- Modify: `docs/current/architecture.md`

- [ ] **Step 1: Update docs**

Add a short note that high-risk citation/source findings are normalized into bounded `citation_source_audit` evidence inside existing `QualityGateResult.findings`, without a new runtime path.

- [ ] **Step 2: Verify**

Run:

```bash
cd /Users/ze/wenjin/backend
.venv/bin/python -m pytest tests/agents/lead_agent/v2/test_citation_source_audit.py tests/agents/lead_agent/v2/test_team_quality_gates.py tests/agents/lead_agent/v2/test_team_kernel.py -q
.venv/bin/ruff check src/agents/lead_agent/v2/team tests/agents/lead_agent/v2/test_citation_source_audit.py tests/agents/lead_agent/v2/test_team_quality_gates.py
cd /Users/ze/wenjin
git diff --check
```

Expected: pytest, ruff, diff check all pass.

- [ ] **Step 3: Commit**

Run:

```bash
cd /Users/ze/wenjin
git status --short
git add backend/src/agents/lead_agent/v2/team/citation_source_audit.py backend/src/agents/lead_agent/v2/team/quality_gates.py backend/tests/agents/lead_agent/v2/test_citation_source_audit.py backend/tests/agents/lead_agent/v2/test_team_quality_gates.py docs/current/native-harness-convergence-audit.md docs/current/architecture.md docs/superpowers/specs/2026-06-09-citation-source-audit-review-loop.md docs/superpowers/plans/2026-06-09-citation-source-audit-review-loop.md
git commit -m "feat: expose citation source audit evidence"
```

## Self-Review

- Spec coverage: covered pure normalizer, quality gate embedding, bounded evidence, tests, docs, and no new runtime/table/stream.
- Placeholder scan: no TBD/TODO placeholders.
- Type consistency: function names and schema names match the spec.
