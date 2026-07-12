"""Provenance projection helpers."""

from __future__ import annotations

from src.dataservice.domains.provenance.contracts import ProvenanceLinkProjection
from src.dataservice.domains.provenance.models import ProvenanceLinkRecord


def provenance_link_to_projection(record: ProvenanceLinkRecord) -> ProvenanceLinkProjection:
    return ProvenanceLinkProjection(
        id=str(record.id),
        workspace_id=str(record.workspace_id),
        source_id=record.source_id,
        source_anchor_id=record.source_anchor_id,
        target_domain=record.target_domain,
        target_kind=record.target_kind,
        target_id=record.target_id,
        target_ref_json=dict(record.target_ref_json or {}),
        relation_kind=record.relation_kind,
        citation_key=record.citation_key,
        claim_text=record.claim_text,
        generated_text=record.generated_text,
        mission_review_item_id=record.mission_review_item_id,
        mission_commit_id=record.mission_commit_id,
        mission_id=record.mission_id,
        metadata_json=dict(record.metadata_json or {}),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )
