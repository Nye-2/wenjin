from src.agents.harness.claim_evidence import (
    ClaimInventoryV1,
    EvidencePacketV1,
    validate_claim_evidence_alignment,
)


def test_claim_evidence_alignment_passes_supported_claims() -> None:
    claims = ClaimInventoryV1(
        claims=[
            {
                "claim_id": "claim-1",
                "claim_type": "literature_position",
                "text": "FedLoRA reduces communication while heterogeneity remains open.",
                "support_status": "supported",
                "evidence_refs": ["ev-1"],
            }
        ]
    )
    evidence = EvidencePacketV1(
        packet_id="evidence-1",
        items=[
            {
                "evidence_id": "ev-1",
                "evidence_type": "library_source",
                "title": "FedLoRA",
                "source_key": "library:paper-1",
                "support_strength": "high",
                "relevance": "direct",
            }
        ],
        links=[
            {
                "claim_id": "claim-1",
                "evidence_id": "ev-1",
                "support_relation": "supports",
                "confidence": "high",
            }
        ],
    )

    decision = validate_claim_evidence_alignment(claims, evidence)

    assert decision.status == "pass"
    assert decision.blocking_reasons == []


def test_claim_evidence_alignment_blocks_missing_evidence_refs() -> None:
    claims = ClaimInventoryV1(
        claims=[
            {
                "claim_id": "claim-1",
                "claim_type": "novelty",
                "text": "This is a new AAAI-ready contribution.",
                "support_status": "supported",
                "evidence_refs": ["missing-ev"],
            }
        ]
    )
    evidence = EvidencePacketV1(packet_id="evidence-1", items=[], links=[])

    decision = validate_claim_evidence_alignment(claims, evidence)

    assert decision.status == "block"
    assert any("missing-ev" in reason for reason in decision.blocking_reasons)


def test_claim_evidence_alignment_blocks_supported_claim_without_refs() -> None:
    claims = ClaimInventoryV1(
        claims=[
            {
                "claim_id": "claim-supported",
                "claim_type": "literature_position",
                "text": "Recent work converges on retrieval-augmented supervision.",
                "support_status": "supported",
            }
        ]
    )

    decision = validate_claim_evidence_alignment(claims, EvidencePacketV1(packet_id="evidence-1"))

    assert decision.status == "block"
    assert any("marked supported" in reason and "evidence_refs" in reason for reason in decision.blocking_reasons)


def test_claim_evidence_alignment_blocks_core_claim_without_refs() -> None:
    claims = ClaimInventoryV1(
        claims=[
            {
                "claim_id": "claim-comparison",
                "claim_type": "comparison",
                "text": "Our method is more robust than the baseline.",
                "support_status": "partially_supported",
            }
        ]
    )

    decision = validate_claim_evidence_alignment(claims, EvidencePacketV1(packet_id="evidence-1"))

    assert decision.status == "block"
    assert any("requires evidence refs" in reason for reason in decision.blocking_reasons)


def test_claim_evidence_alignment_blocks_supported_claim_with_only_unreviewable_evidence() -> None:
    claims = ClaimInventoryV1(
        claims=[
            {
                "claim_id": "claim-judgment",
                "claim_type": "literature_position",
                "text": "The field is ready for a benchmark pivot.",
                "support_status": "supported",
                "evidence_refs": ["ev-judgment"],
            }
        ]
    )
    evidence = EvidencePacketV1(
        packet_id="evidence-1",
        items=[
            {
                "evidence_id": "ev-judgment",
                "evidence_type": "expert_judgment",
                "title": "internal judgement",
                "support_strength": "medium",
                "relevance": "direct",
            }
        ],
        links=[
            {
                "claim_id": "claim-judgment",
                "evidence_id": "ev-judgment",
                "support_relation": "supports",
            }
        ],
    )

    decision = validate_claim_evidence_alignment(claims, evidence)

    assert decision.status == "block"
    assert any("verified or reviewable evidence" in reason for reason in decision.blocking_reasons)
    assert any("expert_judgment" in warning for warning in decision.warnings)


def test_claim_evidence_alignment_warns_when_supported_claim_lacks_supportive_link() -> None:
    claims = ClaimInventoryV1(
        claims=[
            {
                "claim_id": "claim-link",
                "claim_type": "literature_position",
                "text": "Retrieval quality is the main bottleneck.",
                "support_status": "supported",
                "evidence_refs": ["ev-source"],
            }
        ]
    )
    evidence = EvidencePacketV1(
        packet_id="evidence-1",
        items=[
            {
                "evidence_id": "ev-source",
                "evidence_type": "library_source",
                "source_key": "library:paper-1",
                "support_strength": "high",
                "relevance": "direct",
            }
        ],
        links=[],
    )

    decision = validate_claim_evidence_alignment(claims, evidence)

    assert decision.status == "warn"
    assert any("supportive evidence link" in warning for warning in decision.warnings)


def test_claim_evidence_alignment_blocks_numeric_claim_without_artifact() -> None:
    claims = ClaimInventoryV1(
        claims=[
            {
                "claim_id": "claim-f1",
                "claim_type": "numeric_result",
                "text": "The method improves F1 by 3.2 points.",
                "support_status": "supported",
                "evidence_refs": ["ev-run"],
            }
        ]
    )
    evidence = EvidencePacketV1(
        packet_id="evidence-1",
        items=[
            {
                "evidence_id": "ev-run",
                "evidence_type": "expert_judgment",
                "title": "expert summary",
                "support_strength": "weak",
                "relevance": "direct",
            }
        ],
        links=[],
    )

    decision = validate_claim_evidence_alignment(claims, evidence)

    assert decision.status == "block"
    assert any("artifact" in reason for reason in decision.blocking_reasons)
    assert any("expert_judgment" in warning for warning in decision.warnings)


def test_claim_evidence_alignment_warns_for_insufficient_non_core_claims() -> None:
    claims = ClaimInventoryV1(
        claims=[
            {
                "claim_id": "claim-background",
                "claim_type": "background_fact",
                "text": "FedLLM is an active research area.",
                "support_status": "insufficient_evidence",
            }
        ]
    )

    decision = validate_claim_evidence_alignment(claims, EvidencePacketV1(packet_id="evidence-1"))

    assert decision.status == "warn"
    assert decision.blocking_reasons == []
    assert decision.warnings
