"""Projection helpers for canonical Mission Runtime records."""

from __future__ import annotations

from src.database.models.mission import (
    MissionCommitRecord,
    MissionItemRecord,
    MissionReviewItemRecord,
    MissionRunRecord,
)
from src.dataservice_client.contracts.mission import (
    MissionCommitPayload,
    MissionItemPayload,
    MissionReviewItemPayload,
    MissionRunPayload,
    MissionViewRunPayload,
)


def mission_run_to_payload(record: MissionRunRecord) -> MissionRunPayload:
    return MissionRunPayload(
        mission_id=str(record.mission_id),
        parent_mission_id=record.parent_mission_id,
        workspace_id=str(record.workspace_id),
        thread_id=record.thread_id,
        user_id=str(record.user_id),
        workspace_type=record.workspace_type,
        mission_policy_id=record.mission_policy_id,
        title=record.title,
        objective=record.objective,
        status=record.status,
        review_mode=record.review_mode,
        active_stage_id=record.active_stage_id,
        model_id=record.model_id,
        reasoning_effort=record.reasoning_effort,
        snapshot_json=dict(record.snapshot_json or {}),
        runtime_context_json=dict(record.runtime_context_json or {}),
        context_checkpoint_ref=record.context_checkpoint_ref,
        pending_review_count=record.pending_review_count,
        evidence_count=record.evidence_count,
        artifact_count=record.artifact_count,
        active_subagent_count=record.active_subagent_count,
        mission_idempotency_key=record.mission_idempotency_key,
        last_command_seq=record.last_command_seq,
        last_applied_command_seq=record.last_applied_command_seq,
        next_wakeup_at=record.next_wakeup_at,
        lease_owner=record.lease_owner,
        lease_epoch=record.lease_epoch,
        lease_expires_at=record.lease_expires_at,
        dispatch_owner=record.dispatch_owner,
        dispatch_epoch=record.dispatch_epoch,
        dispatch_expires_at=record.dispatch_expires_at,
        state_version=record.state_version,
        last_item_seq=record.last_item_seq,
        created_at=record.created_at,
        updated_at=record.updated_at,
        started_at=record.started_at,
        completed_at=record.completed_at,
    )


def mission_run_to_view_payload(record: MissionRunRecord) -> MissionViewRunPayload:
    return MissionViewRunPayload(
        mission_id=str(record.mission_id),
        parent_mission_id=record.parent_mission_id,
        workspace_id=str(record.workspace_id),
        thread_id=record.thread_id,
        workspace_type=record.workspace_type,
        title=record.title,
        objective=record.objective,
        status=record.status,
        review_mode=record.review_mode,
        active_stage_id=record.active_stage_id,
        model_id=record.model_id,
        reasoning_effort=record.reasoning_effort,
        pending_review_count=record.pending_review_count,
        evidence_count=record.evidence_count,
        artifact_count=record.artifact_count,
        active_subagent_count=record.active_subagent_count,
        state_version=record.state_version,
        last_item_seq=record.last_item_seq,
        created_at=record.created_at,
        updated_at=record.updated_at,
        started_at=record.started_at,
        completed_at=record.completed_at,
    )


def mission_item_to_payload(record: MissionItemRecord) -> MissionItemPayload:
    return MissionItemPayload(
        id=str(record.id),
        mission_id=str(record.mission_id),
        seq=record.seq,
        item_type=record.item_type,
        operation_id=record.operation_id,
        phase=record.phase,
        stage_id=record.stage_id,
        producer=record.producer,
        summary=record.summary,
        risk_level=record.risk_level,
        payload_json=dict(record.payload_json or {}),
        payload_ref=record.payload_ref,
        created_at=record.created_at,
    )


def mission_review_item_to_payload(
    record: MissionReviewItemRecord,
) -> MissionReviewItemPayload:
    return MissionReviewItemPayload(
        review_item_id=str(record.review_item_id),
        mission_id=str(record.mission_id),
        source_item_seq=record.source_item_seq,
        output_key=record.output_key,
        target_kind=record.target_kind,
        target_room=record.target_room,
        target_ref=record.target_ref,
        base_revision_ref=record.base_revision_ref,
        base_hash=record.base_hash,
        title=record.title,
        summary=record.summary,
        risk_level=record.risk_level,
        status=record.status,
        review_required_reason=record.review_required_reason,
        preview_json=dict(record.preview_json or {}),
        preview_ref=record.preview_ref,
        preview_hash=record.preview_hash,
        preview_expires_at=record.preview_expires_at,
        requires_explicit_review=record.requires_explicit_review,
        batch_acceptable=record.batch_acceptable,
        suggested_selected=record.suggested_selected,
        decision_json=dict(record.decision_json) if record.decision_json is not None else None,
        decided_by=record.decided_by,
        decided_at=record.decided_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def mission_commit_to_payload(record: MissionCommitRecord) -> MissionCommitPayload:
    return MissionCommitPayload(
        commit_id=str(record.commit_id),
        mission_id=str(record.mission_id),
        review_item_id=str(record.review_item_id),
        commit_key=record.commit_key,
        status=record.status,
        actor_user_id=str(record.actor_user_id),
        targets_json=dict(record.targets_json or {}),
        error_json=dict(record.error_json) if record.error_json is not None else None,
        attempt_count=record.attempt_count,
        attempt_token=record.attempt_token,
        attempt_started_at=record.attempt_started_at,
        attempt_expires_at=record.attempt_expires_at,
        created_at=record.created_at,
        completed_at=record.completed_at,
    )


__all__ = [
    "mission_commit_to_payload",
    "mission_item_to_payload",
    "mission_review_item_to_payload",
    "mission_run_to_payload",
    "mission_run_to_view_payload",
]
