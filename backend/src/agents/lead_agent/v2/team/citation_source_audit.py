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
AUDIT_FIELD_PRIORITY = {
    "fabrication_risks": 0,
    "missing_sources": 1,
    "citation_key_audit": 2,
    "bibtex_projection_notes": 3,
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
    """Return bounded user-facing findings from structured citation/source audit output."""

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
    for gate_id in CITATION_SOURCE_AUDIT_FIELDS_BY_GATE:
        if gate_id not in active_gate_ids:
            continue
        fields.extend(CITATION_SOURCE_AUDIT_FIELDS_BY_GATE.get(gate_id, ()))
    return sorted(
        _dedupe(fields),
        key=lambda field: AUDIT_FIELD_PRIORITY.get(field, len(AUDIT_FIELD_PRIORITY)),
    )


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
    trusted_source_ids = [
        ref for ref in refs["source_ids"] if not allowed_sources or ref in allowed_sources
    ]
    trusted_citation_keys = [
        ref for ref in refs["citation_keys"] if not allowed_citations or ref in allowed_citations
    ]
    return {
        "schema": AUDIT_FINDING_SCHEMA,
        "invocation_id": invocation_id,
        "template_id": template_id,
        "display_name": display_name,
        "field": field,
        "index": index,
        "risk": risk or None,
        "severity": severity or None,
        "citation_key": trusted_citation_keys[0] if trusted_citation_keys else None,
        "source_id": trusted_source_ids[0] if trusted_source_ids else None,
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
    if field == "fabrication_risks" or risk in {"fabricated", "present"}:
        return "replace_or_remove_citation"
    if unknown_refs:
        return "replace_with_workspace_source"
    if field == "missing_sources":
        return "find_source"
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
