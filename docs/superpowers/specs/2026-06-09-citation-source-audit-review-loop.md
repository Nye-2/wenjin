# Citation Source Audit Review Loop Spec

更新时间：2026-06-09
状态：Draft for implementation

## Goal

Turn existing TeamKernel citation/source quality-gate findings into a stable, user-reviewable audit evidence object so Wenjin can explain which claims or citations are risky, why they are risky, and what should be fixed before a research/writing output is trusted.

## Why This Matters

The current harness already detects many citation/source problems:

- `claim_evidence_map_required` rejects supported claims without workspace `source_id` or `citation_key`.
- `source_authority_checked`, `metadata_completeness_checked`, `weak_support_flagged`, `no_fabricated_citations`, `claim_source_binding_checked`, and `style_consistency_checked` inspect structured audit fields such as `citation_key_audit`, `missing_sources`, `fabrication_risks`, and `bibtex_projection_notes`.
- Quality gates can request member revision or stop with warning.

The gap is product closure. A user should not need raw gate JSON to understand citation risk. High-risk findings should be normalized into concise evidence that can be shown in ResultCard/Evidence surfaces and reused by later quality iterations.

## External Reference Lessons

Codex reinforces the need for bounded, structured evidence rather than raw process payloads. For Wenjin, that means citation/source findings should be attached to existing execution state as small normalized facts, not emitted as raw model output.

DeerFlow reinforces phase checklists and source traceability. For Wenjin, that means every evidence-dependent claim should be either tied to current workspace sources or explicitly marked as missing/weak/fabricated.

## Scope

In scope:

- Add a pure normalizer for citation/source audit risk evidence.
- Attach normalized audit evidence to quality gate findings.
- Keep evidence bounded and safe for UI projection.
- Add tests covering high-risk, unknown-ref, and safe cases.
- Update current docs and convergence audit.

Out of scope:

- No new DataService table.
- No new execution stream.
- No external citation verification API.
- No generic web DOI lookup in this slice.
- No change to model prompts beyond existing quality contract semantics.
- No automatic user-side “fix citation” action yet.

## Architecture

The new unit should live beside quality gates:

```text
backend/src/agents/lead_agent/v2/team/citation_source_audit.py
```

It exposes one pure function:

```python
def collect_citation_source_audit_findings(
    *,
    invocation_id: str,
    template_id: str,
    display_name: str | None,
    output: dict[str, Any],
    quality_contract: dict[str, Any],
    active_gate_ids: set[str],
) -> list[dict[str, Any]]:
    ...
```

`quality_gates.py` remains the quality decision engine. It calls this normalizer when evaluating citation/source gates and embeds bounded findings into `QualityGateResult.findings[*].citation_source_audit`.

The normalized finding schema:

```json
{
  "schema": "wenjin.quality.citation_source_audit_finding.v1",
  "invocation_id": "citation_auditor.v1__1",
  "template_id": "citation_auditor.v1",
  "display_name": "引文审计员",
  "field": "fabrication_risks",
  "index": 0,
  "risk": "fabricated",
  "severity": "high",
  "citation_key": "missing2026",
  "source_id": null,
  "claim": "Federated LLM fine-tuning is proven stable in all non-IID settings.",
  "message": "Citation appears fabricated or unsupported by the current workspace Library.",
  "suggested_action": "replace_or_remove_citation"
}
```

Rules:

- Keep at most 20 findings per invocation.
- Keep text fields bounded: `claim`, `message`, and `suggested_action` are short strings.
- Only preserve refs that are in current workspace allowlists, or explicitly list unknown refs as `unknown_refs`.
- Never include raw model JSON, raw BibTeX, raw source text, stdout/stderr, host paths, `.wenjin/**`, `/workspace/outputs/harness/**`, API keys, or secrets.
- Empty audit arrays are not findings.
- Low-risk/pass entries are not findings.

## Data Flow

1. Team member returns structured output.
2. `evaluate_quality_gates()` evaluates required fields and risk status as it does today.
3. For active citation/source gates, `collect_citation_source_audit_findings()` extracts normalized finding objects.
4. The existing `QualityGateResult` includes these objects in `findings[*].citation_source_audit`.
5. TeamKernel persists quality gates to `ExecutionRecord.runtime_state.quality_gates` as it already does.
6. Frontend can later render concise audit evidence from existing run state without parsing raw member output.

## Testing

Backend tests:

- `test_citation_source_audit_collects_fabrication_and_missing_source_findings`
- `test_citation_source_audit_records_unknown_workspace_refs_without_trusting_them`
- `test_citation_source_audit_ignores_safe_entries`
- `test_quality_gates_embed_citation_source_audit_evidence_for_high_risk_findings`

Verification commands:

```bash
cd backend
.venv/bin/python -m pytest tests/agents/lead_agent/v2/test_citation_source_audit.py tests/agents/lead_agent/v2/test_team_quality_gates.py -q
.venv/bin/ruff check src/agents/lead_agent/v2/team tests/agents/lead_agent/v2
```

## Success Criteria

- High-risk citation/source findings are visible as normalized evidence in quality gate results.
- Unknown citation/source refs are flagged without being treated as trusted workspace refs.
- Existing quality gate revision behavior remains unchanged.
- No new runtime path, store, table, stream, or compatibility layer is introduced.
- Tests prove the normalizer and integration behavior.
