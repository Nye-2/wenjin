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
        invocation_id="citation_auditor.v1__1",
        template_id="citation_auditor.v1",
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


def test_preserves_trusted_refs_when_other_refs_are_unknown() -> None:
    findings = collect_citation_source_audit_findings(
        invocation_id="citation_auditor.v1__1",
        template_id="citation_auditor.v1",
        display_name=None,
        output={
            "citation_key_audit": [
                {
                    "citation_key": "missing2026",
                    "source_id": "source-1",
                    "status": "not_ready",
                }
            ]
        },
        quality_contract={
            "allowed_citation_keys": ["smith2026"],
            "allowed_source_ids": ["source-1"],
        },
        active_gate_ids={"claim_source_binding_checked"},
    )

    assert findings[0]["source_id"] == "source-1"
    assert findings[0]["citation_key"] is None
    assert findings[0]["unknown_refs"] == ["missing2026"]


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
