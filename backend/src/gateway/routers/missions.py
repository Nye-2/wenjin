"""Public MissionView, review, commit, history, and permission endpoints."""

from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.mission import MissionReviewMode
from src.dataservice_client.errors import DataServiceClientError
from src.gateway.auth_dependencies import AccountAuthSubject, get_current_user
from src.gateway.deps.core import get_dataservice_client
from src.permission_runtime.contracts import PermissionDecision
from src.permission_runtime.runtime import PermissionRuntime
from src.review_commit_runtime.contracts import ReviewAction, ReviewDecision
from src.review_commit_runtime.materializer import MissionDomainWriter
from src.review_commit_runtime.membership import (
    DataServiceMembershipAuthorizer,
    require_owned_mission,
)
from src.review_commit_runtime.runtime import ReviewCommitRuntime
from src.services.mission_runtime_service import MissionRuntimeService, build_mission_runtime

router = APIRouter(tags=["missions"])


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReviewDecisionsRequest(_StrictModel):
    decision_id: str = Field(min_length=1, max_length=160)
    decisions: list[ReviewDecision] = Field(min_length=1, max_length=100)
    bulk: bool = False


class MissionCommitRequest(_StrictModel):
    request_id: str = Field(min_length=1, max_length=160)
    review_item_ids: list[str] = Field(min_length=1, max_length=100)


class PermissionResolutionRequest(_StrictModel):
    decision: PermissionDecision
    input_json: dict[str, Any] = Field(default_factory=dict)


class CancelMissionAction(_StrictModel):
    action: Literal["cancel"]
    request_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1, max_length=160)
    reason: str | None = Field(default=None, max_length=4000)


class PauseMissionAction(_StrictModel):
    action: Literal["pause"]
    request_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1, max_length=160)
    reason: str = Field(default="user_requested", min_length=1, max_length=4000)


class ResumeMissionAction(_StrictModel):
    action: Literal["resume"]
    request_id: str = Field(min_length=1, max_length=160)
    input_json: dict[str, Any] = Field(default_factory=dict)


class SteerMissionAction(_StrictModel):
    action: Literal["steer"]
    command_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1, max_length=160)
    input_kind: str = Field(default="instruction", min_length=1, max_length=80)
    instruction: str = Field(min_length=1, max_length=4000)
    request_id: str | None = Field(default=None, max_length=160)


class ReviewMissionAction(_StrictModel):
    action: Literal["review"]
    decision_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1, max_length=160)
    review_item_ids: tuple[str, ...] = Field(min_length=1, max_length=100)
    decision: ReviewAction
    rationale: str | None = Field(default=None, max_length=4000)


class CommitMissionAction(_StrictModel):
    action: Literal["commit"]
    request_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1, max_length=160)
    review_item_ids: tuple[str, ...] = Field(min_length=1, max_length=100)


class SetReviewModeMissionAction(_StrictModel):
    action: Literal["set_review_mode"]
    command_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1, max_length=160)
    review_mode: MissionReviewMode


MissionAction = Annotated[
    CancelMissionAction | PauseMissionAction | ResumeMissionAction | SteerMissionAction | ReviewMissionAction | CommitMissionAction | SetReviewModeMissionAction,
    Field(discriminator="action"),
]


async def _mission_runtime_service(
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> MissionRuntimeService:
    review_commit = ReviewCommitRuntime(
        missions=dataservice.missions,
        target_writer=MissionDomainWriter(dataservice),
        membership=DataServiceMembershipAuthorizer(dataservice),
    )
    return MissionRuntimeService(
        await build_mission_runtime(dataservice),
        dataservice=dataservice,
        review_commit=review_commit,
    )


async def _owned_run(
    mission_id: str,
    *,
    user_id: str,
    dataservice: AsyncDataServiceClient,
):
    try:
        return await require_owned_mission(
            dataservice.missions,
            DataServiceMembershipAuthorizer(dataservice),
            mission_id=mission_id,
            actor_user_id=user_id,
        )
    except (LookupError, PermissionError) as exc:
        raise HTTPException(status_code=404, detail="Mission not found") from exc


class MissionStreamCursor(_StrictModel):
    watermark: datetime
    after_mission_id: str = ""
    positions: dict[str, tuple[int, int]] = Field(default_factory=dict)


def _encode_cursor(cursor: MissionStreamCursor) -> str:
    raw = json.dumps(cursor.model_dump(mode="json"), separators=(",", ":"), sort_keys=True)
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _decode_cursor(value: str | None) -> MissionStreamCursor:
    if not value:
        return MissionStreamCursor(watermark=datetime.fromtimestamp(0, UTC))
    try:
        padded = value + "=" * (-len(value) % 4)
        return MissionStreamCursor.model_validate_json(base64.urlsafe_b64decode(padded))
    except Exception as exc:
        raise ValueError("invalid Mission stream cursor") from exc


def _event_frame(*, event_id: str, payload: dict[str, Any]) -> str:
    return f"id: {event_id}\nevent: mission.updated\ndata: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n"


async def _mission_event_stream(
    *,
    request: Request,
    workspace_id: str,
    user_id: str,
    dataservice: AsyncDataServiceClient,
    cursor: MissionStreamCursor,
    poll_seconds: float = 1.0,
    heartbeat_seconds: float = 15.0,
) -> AsyncIterator[str]:
    """Project reconnectable hints from Mission DB state; hints are never SSOT."""

    heartbeat_elapsed = 0.0
    recovery_elapsed = 0.0
    while not await request.is_disconnected():
        runs = await dataservice.missions.list_workspace_changes(
            workspace_id=workspace_id,
            updated_at=cursor.watermark,
            after_mission_id=cursor.after_mission_id,
            limit=100,
        )
        emitted = False
        for run in runs:
            fingerprint = (run.state_version, run.last_item_seq)
            prior = cursor.positions.get(run.mission_id)
            cursor.watermark = run.updated_at
            cursor.after_mission_id = run.mission_id
            if run.user_id != user_id:
                continue
            if prior == fingerprint:
                continue
            cursor.positions[run.mission_id] = fingerprint
            emitted = True
            replay_required = prior is not None and run.last_item_seq > prior[1] + 1
            token = _encode_cursor(cursor)
            yield _event_frame(
                event_id=token,
                payload={
                    "type": "mission.snapshot.changed" if replay_required else "mission.updated",
                    "missionId": run.mission_id,
                    "stateVersion": run.state_version,
                    "lastItemSeq": run.last_item_seq,
                    "replayRequired": replay_required,
                    "cursor": token,
                },
            )
        if emitted:
            heartbeat_elapsed = 0.0
        else:
            heartbeat_elapsed += poll_seconds
            recovery_elapsed += poll_seconds
            if heartbeat_elapsed >= heartbeat_seconds:
                heartbeat_elapsed = 0.0
                yield ": keep-alive\n\n"
        if recovery_elapsed >= 30:
            recovery_elapsed = 0.0
            # Low-frequency recovery only; the hot path is the indexed
            # updated_at/mission_id delta query above.
            recent = await dataservice.missions.list_workspace(
                workspace_id=workspace_id, limit=100
            )
            for run in reversed(recent):
                if run.user_id != user_id:
                    continue
                fingerprint = (run.state_version, run.last_item_seq)
                if cursor.positions.get(run.mission_id) != fingerprint:
                    cursor.positions[run.mission_id] = fingerprint
                    token = _encode_cursor(cursor)
                    yield _event_frame(
                        event_id=token,
                        payload={
                            "type": "mission.snapshot.changed",
                            "missionId": run.mission_id,
                            "stateVersion": run.state_version,
                            "lastItemSeq": run.last_item_seq,
                            "replayRequired": True,
                            "cursor": token,
                        },
                    )
        await asyncio.sleep(poll_seconds)


@router.get("/missions/{mission_id}")
async def get_mission_view(
    mission_id: str,
    current_user: AccountAuthSubject = Depends(get_current_user),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> dict[str, Any]:
    await _owned_run(
        mission_id,
        user_id=str(current_user.id),
        dataservice=dataservice,
    )
    view = await dataservice.missions.get_view(mission_id)
    if view is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    return view.model_dump(mode="json")


@router.get("/workspaces/{workspace_id}/missions")
async def list_mission_history(
    workspace_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None, min_length=1, max_length=1024),
    current_user: AccountAuthSubject = Depends(get_current_user),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> dict[str, Any]:
    try:
        await DataServiceMembershipAuthorizer(dataservice).require_active_member(
            workspace_id=workspace_id,
            user_id=str(current_user.id),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=404, detail="Workspace not found") from exc
    page = await dataservice.missions.list_workspace_page(
        workspace_id=workspace_id,
        user_id=str(current_user.id),
        limit=limit,
        cursor=cursor,
    )
    return page.model_dump(mode="json")


@router.get("/workspaces/{workspace_id}/missions/events")
async def stream_mission_events(
    workspace_id: str,
    request: Request,
    cursor: str | None = Query(default=None),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    current_user: AccountAuthSubject = Depends(get_current_user),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> StreamingResponse:
    user_id = str(current_user.id)
    has_access = await dataservice.workspace_has_active_membership(
        workspace_id=workspace_id,
        user_id=user_id,
    )
    if not has_access:
        raise HTTPException(status_code=404, detail="Workspace not found")
    try:
        resume_cursor = _decode_cursor(last_event_id or cursor)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Mission stream cursor",
        ) from exc
    return StreamingResponse(
        _mission_event_stream(
            request=request,
            workspace_id=workspace_id,
            user_id=user_id,
            dataservice=dataservice,
            cursor=resume_cursor,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/missions/{mission_id}/items")
async def list_mission_trace_items(
    mission_id: str,
    cursor: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: AccountAuthSubject = Depends(get_current_user),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> dict[str, Any]:
    await _owned_run(
        mission_id,
        user_id=str(current_user.id),
        dataservice=dataservice,
    )
    items = await dataservice.missions.list_items(
        mission_id,
        after_seq=cursor,
        limit=limit,
    )
    return {
        "items": [item.model_dump(mode="json") for item in items],
        "next_cursor": items[-1].seq if items else None,
    }


@router.post("/missions/{mission_id}/actions")
async def act_on_mission(
    mission_id: str,
    command: MissionAction,
    current_user: AccountAuthSubject = Depends(get_current_user),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
    runtime: MissionRuntimeService = Depends(_mission_runtime_service),
) -> dict[str, Any]:
    user_id = str(current_user.id)
    await _owned_run(mission_id, user_id=user_id, dataservice=dataservice)
    try:
        if isinstance(command, CancelMissionAction):
            run = await runtime.cancel(
                mission_id,
                request_id=command.request_id,
                reason=command.reason,
                producer="mission_gateway",
            )
        elif isinstance(command, ResumeMissionAction):
            run = await runtime.resume(
                mission_id,
                request_id=command.request_id,
                input_json=command.input_json,
                producer="mission_gateway",
            )
        elif isinstance(command, ReviewMissionAction):
            run = await runtime.review(
                mission_id,
                decision_id=command.decision_id,
                actor_user_id=user_id,
                review_item_ids=command.review_item_ids,
                decision=command.decision.value,
                rationale=command.rationale,
            )
        elif isinstance(command, CommitMissionAction):
            run = await runtime.request_commit(
                mission_id,
                actor_user_id=user_id,
                review_item_ids=command.review_item_ids,
                request_id=command.request_id,
            )
        elif isinstance(command, SetReviewModeMissionAction):
            run = await runtime.set_review_mode(
                mission_id,
                command_id=command.command_id,
                actor_user_id=user_id,
                review_mode=command.review_mode,
            )
        elif isinstance(command, PauseMissionAction):
            run = await runtime.pause(
                mission_id,
                request_id=command.request_id,
                actor_user_id=user_id,
                reason=command.reason,
            )
        else:
            run = await runtime.steer(
                mission_id,
                command_id=command.command_id,
                actor_user_id=user_id,
                input_kind=command.input_kind,
                instruction=command.instruction,
                request_id=command.request_id,
            )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Mission not found") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=404, detail="Mission not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except DataServiceClientError as exc:
        from src.gateway.error_mapping import dataservice_client_to_http_exception

        raise dataservice_client_to_http_exception(exc) from exc
    return run.model_dump(mode="json")


@router.post("/missions/{mission_id}/review-decisions")
async def decide_mission_review_items(
    mission_id: str,
    command: ReviewDecisionsRequest,
    current_user: AccountAuthSubject = Depends(get_current_user),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> dict[str, Any]:
    runtime = ReviewCommitRuntime(
        missions=dataservice.missions,
        target_writer=MissionDomainWriter(dataservice),
        membership=DataServiceMembershipAuthorizer(dataservice),
    )
    result = await runtime.decide(
        mission_id,
        actor_user_id=str(current_user.id),
        decision_id=command.decision_id,
        decisions=command.decisions,
        bulk=command.bulk,
    )
    return result.model_dump(mode="json")


@router.post("/missions/{mission_id}/commits")
async def commit_mission_review_items(
    mission_id: str,
    command: MissionCommitRequest,
    current_user: AccountAuthSubject = Depends(get_current_user),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> dict[str, Any]:
    runtime = ReviewCommitRuntime(
        missions=dataservice.missions,
        target_writer=MissionDomainWriter(dataservice),
        membership=DataServiceMembershipAuthorizer(dataservice),
    )
    result = await runtime.commit_many(
        mission_id,
        actor_user_id=str(current_user.id),
        review_item_ids=command.review_item_ids,
        request_id=command.request_id,
    )
    return result.model_dump(mode="json")


@router.post("/missions/{mission_id}/permissions/{request_id}/resolve")
async def resolve_mission_permission(
    mission_id: str,
    request_id: str,
    command: PermissionResolutionRequest,
    current_user: AccountAuthSubject = Depends(get_current_user),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> dict[str, Any]:
    result = await PermissionRuntime(
        missions=dataservice.missions,
        membership=DataServiceMembershipAuthorizer(dataservice),
    ).resolve(
        mission_id,
        request_id=request_id,
        decision=command.decision,
        actor_user_id=str(current_user.id),
        input_json=command.input_json,
    )
    return result.model_dump(mode="json")


__all__ = ["MissionAction", "_mission_event_stream", "router"]
