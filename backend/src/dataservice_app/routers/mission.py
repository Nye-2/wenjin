"""Internal typed API for canonical Mission Runtime persistence."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query

from src.dataservice.common.api import envelope_ok
from src.dataservice.common.unit_of_work import DataServiceUnitOfWork
from src.dataservice.domains.mission.admission import MissionAdmissionService
from src.dataservice.domains.mission.service import MissionStore
from src.dataservice_app.auth import require_internal_token
from src.dataservice_app.deps import get_uow
from src.dataservice_client.contracts.mission import (
    MissionAppendPayload,
    MissionApplyCommandsPayload,
    MissionCheckpointPayload,
    MissionCommitCreatePayload,
    MissionCommitFinishPayload,
    MissionCommitStartPayload,
    MissionCreatePayload,
    MissionDerivedReviewItemCreatePayload,
    MissionDispatchReleasePayload,
    MissionItemSeqsPayload,
    MissionLeaseClaimPayload,
    MissionLeaseHeartbeatPayload,
    MissionLeaseReleasePayload,
    MissionOperationClaimPayload,
    MissionOperationFinishPayload,
    MissionPausePayload,
    MissionPreviewCleanupPayload,
    MissionReservationReconcilePayload,
    MissionResumePayload,
    MissionReviewDecisionsPayload,
    MissionReviewItemsCreatePayload,
    MissionRunnableBatchClaimPayload,
    MissionStatus,
    MissionUserCommandPayload,
)

router = APIRouter(
    prefix="/internal/v1",
    tags=["missions"],
    dependencies=[Depends(require_internal_token)],
)


def _store(uow: DataServiceUnitOfWork) -> MissionStore:
    return MissionStore(uow.required_session, autocommit=False)


@router.post("/mission-admissions")
async def admit_mission(
    command: MissionCreatePayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    result = await MissionAdmissionService(uow.required_session).admit(command)
    await uow.commit()
    return envelope_ok(result.model_dump(mode="json"))


@router.post("/mission-reservation-reconciliation")
async def reconcile_mission_reservations(
    command: MissionReservationReconcilePayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    result = await MissionAdmissionService(
        uow.required_session
    ).reconcile_expired_reservations(command)
    await uow.commit()
    return envelope_ok(result.model_dump(mode="json"))


@router.get("/missions/{mission_id}")
async def get_mission(
    mission_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    result = await _store(uow).load_run_snapshot(mission_id)
    return envelope_ok(result.model_dump(mode="json") if result else None)


@router.get("/missions/{mission_id}/view")
async def get_mission_view(
    mission_id: str,
    projection_item_limit: int = Query(default=50, ge=1, le=200),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    result = await _store(uow).get_view(
        mission_id,
        projection_item_limit=projection_item_limit,
    )
    return envelope_ok(result.model_dump(mode="json") if result else None)


@router.get("/missions/{mission_id}/review-items/{review_item_id}/commit")
async def get_mission_commit_for_review_item(
    mission_id: str,
    review_item_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    result = await _store(uow).load_commit_for_review_item(
        mission_id,
        review_item_id,
    )
    return envelope_ok(result.model_dump(mode="json") if result else None)


@router.get("/missions/{mission_id}/evidence")
async def list_mission_evidence_projection(
    mission_id: str,
    after_seq: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    result = await _store(uow).list_evidence_projection_page(
        mission_id,
        after_seq=after_seq,
        limit=limit,
    )
    return envelope_ok(result.model_dump(mode="json") if result else None)


@router.get("/missions/{mission_id}/artifacts")
async def list_mission_artifact_projection(
    mission_id: str,
    after_seq: int = Query(default=0, ge=0),
    after_review_item_id: str = Query(default="", max_length=36),
    limit: int = Query(default=50, ge=1, le=200),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    result = await _store(uow).list_artifact_projection_page(
        mission_id,
        after_seq=after_seq,
        after_review_item_id=after_review_item_id,
        limit=limit,
    )
    return envelope_ok(result.model_dump(mode="json") if result else None)


@router.post("/missions/review-previews/cleanup")
async def cleanup_mission_review_previews(
    command: MissionPreviewCleanupPayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    result = await _store(uow).cleanup_expired_previews(command)
    await uow.commit()
    return envelope_ok(result.model_dump(mode="json"))


@router.get("/workspaces/{workspace_id}/missions")
async def list_workspace_missions(
    workspace_id: str,
    user_id: str | None = Query(default=None, min_length=1, max_length=36),
    status: list[MissionStatus] | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None, min_length=1, max_length=1024),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    result = await _store(uow).list_runs_summary(
        workspace_id=workspace_id,
        user_id=user_id,
        status=status,
        limit=limit,
        cursor=cursor,
    )
    return envelope_ok(result.model_dump(mode="json"))


@router.get("/workspaces/{workspace_id}/missions/summary")
async def get_workspace_mission_summary(
    workspace_id: str,
    user_id: str | None = Query(default=None, min_length=1, max_length=36),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    result = await _store(uow).get_workspace_summary(
        workspace_id=workspace_id,
        user_id=user_id,
    )
    return envelope_ok(result.model_dump(mode="json"))


@router.get("/users/{user_id}/missions/summary")
async def get_user_mission_summary(
    user_id: str,
    recent_limit: int = Query(default=10, ge=1, le=20),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    result = await _store(uow).get_user_summary(
        user_id=user_id,
        recent_limit=recent_limit,
    )
    return envelope_ok(result.model_dump(mode="json"))


@router.get("/workspaces/{workspace_id}/missions/by-idempotency-key")
async def get_mission_by_idempotency_key(
    workspace_id: str,
    key: str = Query(min_length=1, max_length=160),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    result = await _store(uow).find_by_mission_idempotency_key(
        workspace_id=workspace_id,
        mission_idempotency_key=key,
    )
    return envelope_ok(result.model_dump(mode="json") if result else None)


@router.get("/workspaces/{workspace_id}/threads/{thread_id}/foreground-mission")
async def get_thread_foreground_mission(
    workspace_id: str,
    thread_id: str,
    user_id: str = Query(min_length=1, max_length=36),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    result = await _store(uow).foreground_for_thread(
        workspace_id=workspace_id,
        thread_id=thread_id,
        user_id=user_id,
    )
    return envelope_ok(result.model_dump(mode="json") if result else None)


@router.get("/workspaces/{workspace_id}/threads/{thread_id}/latest-mission")
async def get_thread_latest_mission(
    workspace_id: str,
    thread_id: str,
    user_id: str = Query(min_length=1, max_length=36),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    result = await _store(uow).latest_for_thread(
        workspace_id=workspace_id,
        thread_id=thread_id,
        user_id=user_id,
    )
    return envelope_ok(result.model_dump(mode="json") if result else None)


@router.get("/workspaces/{workspace_id}/missions/changes")
async def list_workspace_mission_changes(
    workspace_id: str,
    updated_at: datetime,
    after_mission_id: str = "",
    limit: int = Query(default=100, ge=1, le=200),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    results = await _store(uow).list_runs_updated_after(
        workspace_id=workspace_id,
        updated_at=updated_at,
        mission_id=after_mission_id,
        limit=limit,
    )
    return envelope_ok([result.model_dump(mode="json") for result in results])


@router.get("/admin/missions/stats")
async def get_admin_mission_stats(
    created_since: datetime,
    granularity: Literal["day", "week"] = "day",
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    result = await _store(uow).aggregate_stats(
        created_since=created_since,
        granularity=granularity,
    )
    return envelope_ok(result.model_dump(mode="json"))


@router.post("/missions/runnable/claim")
async def claim_runnable_missions(
    command: MissionRunnableBatchClaimPayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    results = await _store(uow).claim_runnable_batch_skip_locked(command)
    await uow.commit()
    return envelope_ok([result.model_dump(mode="json") for result in results])


@router.post("/missions/{mission_id}/dispatch/release")
async def release_mission_dispatch(
    mission_id: str,
    command: MissionDispatchReleasePayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    result = await _store(uow).release_dispatch_claim(mission_id, command)
    await uow.commit()
    return envelope_ok(result.model_dump(mode="json"))


@router.post("/missions/{mission_id}/operations/claim")
async def claim_mission_operation(
    mission_id: str,
    command: MissionOperationClaimPayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    result = await _store(uow).claim_operation(mission_id, command)
    await uow.commit()
    return envelope_ok(result.model_dump(mode="json"))


@router.get("/missions/{mission_id}/operations/{operation_key}")
async def get_mission_operation(
    mission_id: str,
    operation_key: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    result = await _store(uow).get_operation(mission_id, operation_key)
    return envelope_ok(result.model_dump(mode="json") if result else None)


@router.post("/missions/{mission_id}/operations/finish")
async def finish_mission_operation(
    mission_id: str,
    command: MissionOperationFinishPayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    result = await _store(uow).finish_operation(mission_id, command)
    await uow.commit()
    return envelope_ok(result.model_dump(mode="json"))


@router.post("/missions/{mission_id}/lease/claim")
async def claim_mission_lease(
    mission_id: str,
    command: MissionLeaseClaimPayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    result = await _store(uow).claim_run_lease(mission_id, command)
    await uow.commit()
    return envelope_ok(result.model_dump(mode="json"))


@router.post("/missions/{mission_id}/lease/heartbeat")
async def heartbeat_mission_lease(
    mission_id: str,
    command: MissionLeaseHeartbeatPayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    result = await _store(uow).heartbeat_run_lease(mission_id, command)
    await uow.commit()
    return envelope_ok(result.model_dump(mode="json"))


@router.post("/missions/{mission_id}/lease/release")
async def release_mission_lease(
    mission_id: str,
    command: MissionLeaseReleasePayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    result = await _store(uow).release_run_lease(mission_id, command)
    await uow.commit()
    return envelope_ok(result.model_dump(mode="json"))


@router.post("/missions/{mission_id}/items/append")
async def append_mission_items(
    mission_id: str,
    command: MissionAppendPayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    result = await _store(uow).append_items_and_update_snapshot(mission_id, command)
    await uow.commit()
    return envelope_ok(result.model_dump(mode="json"))


@router.post("/missions/{mission_id}/checkpoint")
async def checkpoint_mission(
    mission_id: str,
    command: MissionCheckpointPayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    result = await _store(uow).checkpoint_run(mission_id, command)
    await uow.commit()
    return envelope_ok(result.model_dump(mode="json"))


@router.get("/missions/{mission_id}/items")
async def list_mission_items(
    mission_id: str,
    after_seq: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    item_type: str | None = Query(default=None, max_length=80),
    operation_id: str | None = Query(default=None, max_length=200),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    result = await _store(uow).get_items_page(
        mission_id,
        after_seq=after_seq,
        limit=limit,
        item_type=item_type,
        operation_id=operation_id,
    )
    return envelope_ok(result.model_dump(mode="json"))


@router.get("/missions/{mission_id}/model-calls")
async def list_mission_model_calls(
    mission_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    results = await _store(uow).list_model_call_states(mission_id)
    return envelope_ok([result.model_dump(mode="json") for result in results])


@router.post("/missions/{mission_id}/items/by-seqs")
async def list_mission_items_by_seqs(
    mission_id: str,
    command: MissionItemSeqsPayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    results = await _store(uow).list_items_by_seqs(
        mission_id,
        seqs=command.seqs,
    )
    return envelope_ok([result.model_dump(mode="json") for result in results])


@router.post("/missions/{mission_id}/commands")
async def append_mission_command(
    mission_id: str,
    command: MissionUserCommandPayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    result = await _store(uow).append_command_once(mission_id, command)
    await uow.commit()
    return envelope_ok(result.model_dump(mode="json"))


@router.get("/missions/{mission_id}/commands/unapplied")
async def list_unapplied_mission_commands(
    mission_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    results = await _store(uow).list_unapplied_commands(mission_id, limit=limit)
    return envelope_ok([result.model_dump(mode="json") for result in results])


@router.post("/missions/{mission_id}/commands/apply")
async def apply_mission_commands(
    mission_id: str,
    command: MissionApplyCommandsPayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    result = await _store(uow).apply_commands_and_advance_cursor(mission_id, command)
    await uow.commit()
    return envelope_ok(result.model_dump(mode="json"))


@router.post("/missions/{mission_id}/pause")
async def pause_mission(
    mission_id: str,
    command: MissionPausePayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    result = await _store(uow).pause_run(mission_id, command)
    await uow.commit()
    return envelope_ok(result.model_dump(mode="json"))


@router.post("/missions/{mission_id}/resume")
async def resume_mission(
    mission_id: str,
    command: MissionResumePayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    result = await MissionAdmissionService(uow.required_session).resume(
        mission_id,
        command,
    )
    await uow.commit()
    return envelope_ok(result.model_dump(mode="json"))


@router.post("/missions/{mission_id}/review-items")
async def create_mission_review_items(
    mission_id: str,
    command: MissionReviewItemsCreatePayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    result = await _store(uow).create_review_items(mission_id, command)
    await uow.commit()
    return envelope_ok(result.model_dump(mode="json"))


@router.post("/missions/{mission_id}/derived-review-item")
async def create_derived_mission_review_item(
    mission_id: str,
    command: MissionDerivedReviewItemCreatePayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    result = await _store(uow).create_derived_review_item(mission_id, command)
    await uow.commit()
    return envelope_ok(result.model_dump(mode="json"))


@router.get("/missions/{mission_id}/review-items")
async def list_mission_review_items(
    mission_id: str,
    status: list[str] | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    cursor: str | None = Query(default=None, min_length=1, max_length=1024),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    result = await _store(uow).list_review_items_page(
        mission_id,
        status=status,
        limit=limit,
        cursor=cursor,
    )
    return envelope_ok(result.model_dump(mode="json"))


@router.get("/missions/{mission_id}/commits")
async def list_mission_commits(
    mission_id: str,
    limit: int = Query(default=100, ge=1, le=200),
    cursor: str | None = Query(default=None, min_length=1, max_length=1024),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    result = await _store(uow).list_commits_page(
        mission_id,
        limit=limit,
        cursor=cursor,
    )
    return envelope_ok(result.model_dump(mode="json"))


@router.post("/missions/{mission_id}/review-decisions")
async def apply_mission_review_decisions(
    mission_id: str,
    command: MissionReviewDecisionsPayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    result = await _store(uow).apply_review_decisions(mission_id, command)
    await uow.commit()
    return envelope_ok(result.model_dump(mode="json"))


@router.post("/missions/{mission_id}/commits")
async def create_mission_commit(
    mission_id: str,
    command: MissionCommitCreatePayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    result = await _store(uow).record_commit(mission_id, command)
    await uow.commit()
    return envelope_ok(result.model_dump(mode="json"))


@router.post("/missions/{mission_id}/commits/{commit_id}/start")
async def start_mission_commit(
    mission_id: str,
    commit_id: str,
    command: MissionCommitStartPayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    result = await _store(uow).start_commit(mission_id, commit_id, command)
    await uow.commit()
    return envelope_ok(result.model_dump(mode="json"))


@router.post("/missions/{mission_id}/commits/{commit_id}/finish")
async def finish_mission_commit(
    mission_id: str,
    commit_id: str,
    command: MissionCommitFinishPayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    result = await _store(uow).finish_commit(mission_id, commit_id, command)
    await uow.commit()
    return envelope_ok(result.model_dump(mode="json"))
