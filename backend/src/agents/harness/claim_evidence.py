"""Claim and evidence packet contracts for Academic Harness v2."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ClaimType = Literal[
    "background_fact",
    "literature_position",
    "method_description",
    "novelty",
    "comparison",
    "numeric_result",
    "figure_or_table_interpretation",
    "limitation",
    "recommendation",
    "writing_revision",
]
ClaimSupportStatus = Literal[
    "supported",
    "partially_supported",
    "insufficient_evidence",
    "conflicting_evidence",
    "not_checked",
]
EvidenceType = Literal[
    "library_source",
    "external_source",
    "citation_audit",
    "dataset",
    "script",
    "sandbox_artifact",
    "prism_section",
    "user_provided_material",
    "expert_judgment",
]
SupportStrength = Literal["weak", "medium", "high"]
EvidenceRelevance = Literal["direct", "indirect", "background"]
EvidenceVerificationStatus = Literal["verified", "unverified", "failed", "not_checked"]
SupportRelation = Literal["supports", "partially_supports", "contradicts", "qualifies", "background"]
EvidenceConfidence = Literal["low", "medium", "high"]
GateDecisionStatus = Literal["pass", "warn", "block"]
RiskLevel = Literal["low", "medium", "high", "critical"]

_CORE_BLOCKING_CLAIM_TYPES = {
    "novelty",
    "comparison",
    "numeric_result",
    "figure_or_table_interpretation",
    "writing_revision",
}
_ARTIFACT_REQUIRED_CLAIM_TYPES = {"numeric_result", "figure_or_table_interpretation"}
_SUPPORTIVE_RELATIONS = {"supports", "partially_supports", "qualifies"}
_REVIEWABLE_EVIDENCE_TYPES = {
    "library_source",
    "external_source",
    "citation_audit",
    "dataset",
    "script",
    "sandbox_artifact",
    "prism_section",
    "user_provided_material",
}
_MAX_TEXT = 700
_MAX_SHORT_TEXT = 220


class ClaimLocationV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str | None = None
    path: str | None = None
    section: str | None = None


class ClaimRiskV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: RiskLevel = "low"
    reasons: list[str] = Field(default_factory=list)


class ClaimRecommendedActionV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    summary: str


class AtomicClaimV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str
    claim_type: ClaimType
    text: str
    location: ClaimLocationV1 | None = None
    owner_expert_id: str | None = None
    support_status: ClaimSupportStatus
    evidence_refs: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    conflict_refs: list[str] = Field(default_factory=list)
    risk: ClaimRiskV1 = Field(default_factory=ClaimRiskV1)
    recommended_action: ClaimRecommendedActionV1 | None = None


class ClaimInventoryV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["wenjin.claim_inventory.v1"] = "wenjin.claim_inventory.v1"
    claims: list[AtomicClaimV1] = Field(default_factory=list)


class EvidenceLocatorV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    value: str


class EvidenceVerificationV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: EvidenceVerificationStatus = "not_checked"
    method: str | None = None
    checked_at: str | None = None


class EvidenceItemV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    evidence_type: EvidenceType
    title: str | None = None
    source_key: str | None = None
    locator: EvidenceLocatorV1 | None = None
    excerpt: str | None = None
    support_strength: SupportStrength = "weak"
    relevance: EvidenceRelevance = "background"
    verification: EvidenceVerificationV1 = Field(default_factory=EvidenceVerificationV1)
    limitations: list[str] = Field(default_factory=list)


class EvidenceLinkV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str
    evidence_id: str
    support_relation: SupportRelation
    confidence: EvidenceConfidence = "medium"


class EvidenceGateDecisionV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: GateDecisionStatus
    blocking_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class EvidencePacketV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["wenjin.evidence_packet.v1"] = "wenjin.evidence_packet.v1"
    packet_id: str
    items: list[EvidenceItemV1] = Field(default_factory=list)
    links: list[EvidenceLinkV1] = Field(default_factory=list)
    gate_decision: EvidenceGateDecisionV1 | None = None


def validate_claim_evidence_alignment(
    claim_inventory: ClaimInventoryV1 | dict[str, Any] | None,
    evidence_packet: EvidencePacketV1 | dict[str, Any] | None,
) -> EvidenceGateDecisionV1:
    """Run deterministic claim/evidence alignment checks."""

    claims = _coerce_claim_inventory(claim_inventory)
    evidence = _coerce_evidence_packet(evidence_packet)
    if claims is None:
        return EvidenceGateDecisionV1(status="warn", warnings=["claim_inventory is missing"])
    if evidence is None:
        evidence = EvidencePacketV1(packet_id="missing-evidence")

    evidence_by_id = {item.evidence_id: item for item in evidence.items}
    blockers: list[str] = []
    warnings: list[str] = []

    for claim in claims.claims:
        missing_refs = [ref for ref in claim.evidence_refs if ref not in evidence_by_id]
        if missing_refs:
            blockers.append(f"claim {claim.claim_id} references missing evidence: {', '.join(missing_refs)}")

        if claim.claim_type in _CORE_BLOCKING_CLAIM_TYPES and not claim.evidence_refs:
            blockers.append(f"claim {claim.claim_id} requires evidence refs for core claim type {claim.claim_type}")

        if claim.claim_type in _ARTIFACT_REQUIRED_CLAIM_TYPES and not claim.artifact_refs:
            blockers.append(f"claim {claim.claim_id} requires artifact evidence for {claim.claim_type}")

        if claim.support_status in {"insufficient_evidence", "conflicting_evidence"}:
            message = f"claim {claim.claim_id} is {claim.support_status}"
            if claim.claim_type in _CORE_BLOCKING_CLAIM_TYPES:
                blockers.append(message)
            else:
                warnings.append(message)
        elif claim.support_status in {"partially_supported", "not_checked"}:
            warnings.append(f"claim {claim.claim_id} is {claim.support_status}")

        referenced_evidence = [
            evidence_by_id[ref]
            for ref in claim.evidence_refs
            if ref in evidence_by_id
        ]
        supportive_evidence_ids = _supportive_evidence_ids_for_claim(claim, evidence.links)
        supportive_evidence = [
            item for item in referenced_evidence if item.evidence_id in supportive_evidence_ids
        ]
        if claim.support_status == "supported":
            if not claim.evidence_refs:
                blockers.append(f"claim {claim.claim_id} is marked supported but has no evidence_refs")
            if referenced_evidence and not any(_is_verified_or_reviewable_evidence(item) for item in referenced_evidence):
                blockers.append(
                    f"claim {claim.claim_id} is marked supported but has no verified or reviewable evidence"
                )
            if referenced_evidence and not any(item.relevance in {"direct", "indirect"} for item in referenced_evidence):
                blockers.append(f"claim {claim.claim_id} is marked supported but has no direct or indirect evidence")
            if referenced_evidence and not supportive_evidence_ids:
                warnings.append(f"claim {claim.claim_id} has evidence_refs but no supportive evidence link")
            elif supportive_evidence and not any(item.relevance == "direct" for item in supportive_evidence):
                warnings.append(f"claim {claim.claim_id} has no direct supportive evidence")

        if referenced_evidence and all(item.evidence_type == "expert_judgment" for item in referenced_evidence):
            warnings.append(f"claim {claim.claim_id} uses only expert_judgment evidence")
        if referenced_evidence and all(item.support_strength == "weak" for item in referenced_evidence):
            warnings.append(f"claim {claim.claim_id} uses only weak evidence")

    for link in evidence.links:
        if link.claim_id not in {claim.claim_id for claim in claims.claims}:
            warnings.append(f"evidence link references missing claim: {link.claim_id}")
        if link.evidence_id not in evidence_by_id:
            blockers.append(f"evidence link references missing evidence: {link.evidence_id}")
        if link.support_relation == "contradicts":
            warnings.append(f"evidence {link.evidence_id} contradicts claim {link.claim_id}")

    if evidence.gate_decision:
        blockers.extend(evidence.gate_decision.blocking_reasons)
        warnings.extend(evidence.gate_decision.warnings)

    if blockers:
        status: GateDecisionStatus = "block"
    elif warnings:
        status = "warn"
    else:
        status = "pass"
    return EvidenceGateDecisionV1(
        status=status,
        blocking_reasons=_dedupe_strings(blockers),
        warnings=_dedupe_strings(warnings),
    )


def _supportive_evidence_ids_for_claim(claim: AtomicClaimV1, links: list[EvidenceLinkV1]) -> set[str]:
    return {
        link.evidence_id
        for link in links
        if link.claim_id == claim.claim_id and link.support_relation in _SUPPORTIVE_RELATIONS
    }


def _is_verified_or_reviewable_evidence(item: EvidenceItemV1) -> bool:
    if item.verification.status == "verified":
        return True
    if item.verification.status == "failed":
        return False
    if item.evidence_type not in _REVIEWABLE_EVIDENCE_TYPES:
        return False
    return bool(item.source_key or item.locator or item.excerpt)


def sanitize_claim_inventory(value: Any, *, limit: int = 80) -> ClaimInventoryV1 | None:
    if not isinstance(value, dict):
        return None
    claims = []
    raw_claims = value.get("claims")
    if isinstance(raw_claims, list | tuple):
        for item in raw_claims:
            claim = _sanitize_claim(item)
            if claim is not None:
                claims.append(claim)
            if len(claims) >= limit:
                break
    return ClaimInventoryV1.model_validate({"schema_version": "wenjin.claim_inventory.v1", "claims": claims})


def sanitize_evidence_packet(value: Any, *, item_limit: int = 160, link_limit: int = 240) -> EvidencePacketV1 | None:
    if not isinstance(value, dict):
        return None
    packet_id = _clean_text(value.get("packet_id")) or "evidence-packet"
    items = []
    raw_items = value.get("items")
    if isinstance(raw_items, list | tuple):
        for item in raw_items:
            evidence_item = _sanitize_evidence_item(item)
            if evidence_item is not None:
                items.append(evidence_item)
            if len(items) >= item_limit:
                break
    links = []
    raw_links = value.get("links")
    if isinstance(raw_links, list | tuple):
        for item in raw_links:
            link = _sanitize_evidence_link(item)
            if link is not None:
                links.append(link)
            if len(links) >= link_limit:
                break
    gate_decision = _sanitize_gate_decision(value.get("gate_decision"))
    return EvidencePacketV1.model_validate(
        {
            "schema_version": "wenjin.evidence_packet.v1",
            "packet_id": _truncate(packet_id, 120),
            "items": items,
            "links": links,
            "gate_decision": gate_decision,
        }
    )


def _coerce_claim_inventory(value: ClaimInventoryV1 | dict[str, Any] | None) -> ClaimInventoryV1 | None:
    if isinstance(value, ClaimInventoryV1):
        return value
    return sanitize_claim_inventory(value) if isinstance(value, dict) else None


def _coerce_evidence_packet(value: EvidencePacketV1 | dict[str, Any] | None) -> EvidencePacketV1 | None:
    if isinstance(value, EvidencePacketV1):
        return value
    return sanitize_evidence_packet(value) if isinstance(value, dict) else None


def _sanitize_claim(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    claim_id = _clean_text(value.get("claim_id"))
    text = _clean_text(value.get("text"))
    if not claim_id or not text:
        return None
    data = {
        "claim_id": _truncate(claim_id, 120),
        "claim_type": value.get("claim_type"),
        "text": _truncate(text, _MAX_TEXT),
        "location": _sanitize_location(value.get("location")),
        "owner_expert_id": _optional_truncated(value.get("owner_expert_id"), 120),
        "support_status": value.get("support_status"),
        "evidence_refs": _bounded_strings(value.get("evidence_refs"), limit=30, max_chars=120),
        "artifact_refs": _bounded_strings(value.get("artifact_refs"), limit=20, max_chars=180),
        "conflict_refs": _bounded_strings(value.get("conflict_refs"), limit=20, max_chars=120),
        "risk": _sanitize_risk(value.get("risk")),
        "recommended_action": _sanitize_recommended_action(value.get("recommended_action")),
    }
    try:
        return AtomicClaimV1.model_validate(data).model_dump(mode="json")
    except Exception:  # noqa: BLE001 - drop malformed LLM items.
        return None


def _sanitize_evidence_item(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    evidence_id = _clean_text(value.get("evidence_id"))
    if not evidence_id:
        return None
    data = {
        "evidence_id": _truncate(evidence_id, 120),
        "evidence_type": value.get("evidence_type"),
        "title": _optional_truncated(value.get("title"), 180),
        "source_key": _optional_truncated(value.get("source_key"), 180),
        "locator": _sanitize_locator(value.get("locator")),
        "excerpt": _optional_truncated(value.get("excerpt"), 700),
        "support_strength": value.get("support_strength", "weak"),
        "relevance": value.get("relevance", "background"),
        "verification": _sanitize_verification(value.get("verification")),
        "limitations": _bounded_strings(value.get("limitations"), limit=10, max_chars=180),
    }
    try:
        return EvidenceItemV1.model_validate(data).model_dump(mode="json")
    except Exception:  # noqa: BLE001
        return None


def _sanitize_evidence_link(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    data = {
        "claim_id": _truncate(_clean_text(value.get("claim_id")), 120),
        "evidence_id": _truncate(_clean_text(value.get("evidence_id")), 120),
        "support_relation": value.get("support_relation"),
        "confidence": value.get("confidence", "medium"),
    }
    if not data["claim_id"] or not data["evidence_id"]:
        return None
    try:
        return EvidenceLinkV1.model_validate(data).model_dump(mode="json")
    except Exception:  # noqa: BLE001
        return None


def _sanitize_location(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {
        "kind": _optional_truncated(value.get("kind"), 80),
        "path": _optional_truncated(value.get("path"), 180),
        "section": _optional_truncated(value.get("section"), 120),
    }


def _sanitize_risk(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"level": "low", "reasons": []}
    return {
        "level": value.get("level", "low"),
        "reasons": _bounded_strings(value.get("reasons"), limit=8, max_chars=140),
    }


def _sanitize_recommended_action(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    kind = _clean_text(value.get("kind"))
    summary = _clean_text(value.get("summary"))
    if not kind or not summary:
        return None
    return {"kind": _truncate(kind, 80), "summary": _truncate(summary, _MAX_SHORT_TEXT)}


def _sanitize_locator(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    kind = _clean_text(value.get("kind"))
    locator_value = _clean_text(value.get("value"))
    if not kind or not locator_value:
        return None
    return {"kind": _truncate(kind, 80), "value": _truncate(locator_value, 160)}


def _sanitize_verification(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"status": "not_checked"}
    return {
        "status": value.get("status", "not_checked"),
        "method": _optional_truncated(value.get("method"), 120),
        "checked_at": _optional_truncated(value.get("checked_at"), 80),
    }


def _sanitize_gate_decision(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    try:
        return EvidenceGateDecisionV1.model_validate(
            {
                "status": value.get("status"),
                "blocking_reasons": _bounded_strings(value.get("blocking_reasons"), limit=20, max_chars=220),
                "warnings": _bounded_strings(value.get("warnings"), limit=20, max_chars=220),
            }
        ).model_dump(mode="json")
    except Exception:  # noqa: BLE001
        return None


def _bounded_strings(value: Any, *, limit: int, max_chars: int) -> list[str]:
    if not isinstance(value, list | tuple | set | frozenset):
        return []
    result: list[str] = []
    for item in value:
        text = _truncate(_clean_text(item), max_chars)
        if text:
            result.append(text)
        if len(result) >= limit:
            break
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


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _optional_truncated(value: Any, max_chars: int) -> str | None:
    text = _truncate(_clean_text(value), max_chars)
    return text or None


def _truncate(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    if max_chars <= 3:
        return value[:max_chars]
    return value[: max_chars - 3].rstrip() + "..."
