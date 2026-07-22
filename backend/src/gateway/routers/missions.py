"""Public MissionView, review, commit, history, and permission endpoints."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.config import get_settings
from src.contracts.archive_filename import recover_legacy_zip_filename
from src.contracts.prism_context import PrismContextRef
from src.contracts.review_policy import ReviewMode
from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.errors import DataServiceClientError
from src.gateway.auth_dependencies import AccountAuthSubject, get_current_user
from src.gateway.deps.core import get_dataservice_client
from src.permission_runtime import PermissionResolutionService
from src.permission_runtime.contracts import PermissionDecision
from src.review_commit_runtime.composition import (
    build_review_commit_runtime,
    get_mission_preview_store,
)
from src.review_commit_runtime.contracts import ReviewDecision
from src.review_commit_runtime.membership import (
    DataServiceMembershipAuthorizer,
    require_owned_mission,
)
from src.review_commit_runtime.preview_store import MissionPreviewStore
from src.review_commit_runtime.visual_insertion import PrismVisualInsertionService
from src.services.mission_runtime_service import MissionRuntimeService, build_mission_runtime
from src.services.workspace_uploads import resolve_workspace_upload_relative_path

router = APIRouter(tags=["missions"])


def _add_artifact_download_urls(payload: dict[str, Any], mission_id: str) -> None:
    raw_items = payload.get("artifact_items")
    if not isinstance(raw_items, list):
        raw_items = payload.get("items")
    for item in raw_items if isinstance(raw_items, list) else []:
        if not isinstance(item, dict):
            continue
        item["download_url"] = (
            f"/api/missions/{quote(mission_id, safe='')}/artifacts/"
            f"{quote(str(item.get('item_id') or ''), safe='')}/download"
            if item.get("download_available") is True
            else None
        )


def _repair_legacy_evidence_names(payload: dict[str, Any]) -> None:
    raw_items = payload.get("evidence_items")
    if not isinstance(raw_items, list):
        raw_items = payload.get("items")
    for item in raw_items if isinstance(raw_items, list) else []:
        if not isinstance(item, dict):
            continue
        for field in ("title", "summary"):
            value = item.get(field)
            if isinstance(value, str):
                item[field] = recover_legacy_zip_filename(value)

_TRACE_SUMMARY_LABELS = {
    "Mission budget reserved": "已准备任务资源",
    "Mission planning started": "正在组织研究计划",
    "Mission drive loop started": "研究任务开始推进",
    "Mission checkpoint saved at a safe boundary": "已保存当前任务进度",
    "Mission action needs schema repair; Mission will retry": "正在校正下一步",
    "tool operation claimed": "已开始执行研究工具",
    "tool operation succeeded": "研究工具执行完成",
    "tool operation failed": "研究工具本轮未完成，正在调整",
    "sandbox operation claimed": "正在运行计算与验证",
    "sandbox operation succeeded": "计算与验证已完成",
    "Read a verified, unmaterialized artifact candidate.": "已读取通过验证的候选成果",
    "The Sandbox file is unavailable or exceeds the read boundary.": "未读取到目标文件，正在检查材料路径",
    "Stage acceptance contract passed": "当前阶段已通过质量验收",
    "Previously completed operation reused": "已复用此前完成的研究步骤",
    "Subagent model call started": "研究成员开始分析材料",
    "Workspace Agent model call started": "问津开始分析并规划下一步",
    "Subagent model step failed": "研究成员本轮未完成，正在重试",
    "Model service was temporarily unavailable; Mission will retry": "连接暂时波动，问津正在重试",
    "Model service remained unavailable; Mission stopped with its partial work preserved": "连接多次未恢复，已保留当前成果",
    "Model service is busy; preserving worker context and retrying": "连接暂时波动，研究成员正在重试",
    "Selected context could not be loaded": "未读取到所需材料，研究成员正在调整",
    "Tool invocation failed before producing a typed result": "研究工具本轮未完成，研究成员正在调整",
    "The current Mission slice cannot cover this tool's pinned attempt boundary.": "本轮处理范围已到边界，正在续接后续工作",
    "The Mission slice cannot cover another pinned tool attempt.": "本轮处理范围已到边界，正在续接后续工作",
    "Subagent exhausted its model-turn budget": "研究成员已保留本轮分析进度",
    "Subagent exhausted its tool-step budget": "研究成员已保留本轮工具进度",
    "Subagent exhausted its retries for structured model output": "结构化结果未通过校验，已保留当前进度",
}

_TRACE_FALLBACK_LABELS = {
    "tool_call": "正在执行下一项研究步骤",
    "tool_result": "研究工具已返回结果",
    "operation_claim": "已开始执行研究工具",
    "operation_terminal": "研究工具状态已更新",
    "subagent_progress": "研究成员完成了一项工作",
    "subagent_completed": "研究成员已完成本轮工作",
    "error": "本轮未完成，问津正在调整",
    "context_checkpoint": "已保存当前任务进度",
    "status_update": "任务状态已更新",
}

_HIDDEN_PUBLIC_TRACE_ITEM_TYPES = {
    "billing_reconciliation_required",
    "model_call_terminal",
    "subagent_action_checkpoint",
    "usage_receipt",
}

_READ_MATERIAL_RE = re.compile(r"^Read \d+ (?:character|byte)\(s\) from (.+)\.$")
_SUBAGENT_RESULT_RE = re.compile(r"^(\d+) of \d+ subagent jobs produced usable results$")
_HAS_CJK_RE = re.compile(r"[\u3400-\u9fff]")


def _bounded_trace_text(value: str, *, limit: int = 180) -> str:
    if len(value) <= limit:
        return value
    return f"{value[:limit].rstrip()}…"


def _public_trace_summary(
    *,
    item_type: str,
    summary: str | None,
    allow_freeform: bool = True,
) -> str:
    """Project an internal ledger receipt into calm, user-facing trace text."""
    normalized = (summary or "").strip()
    if not normalized:
        return {
            "evidence": "发现新材料",
            "artifact": "生成候选成果",
            "quality_check": "完成阶段质量检查",
            "review_candidate": "内容已进入确认",
            "commit": "内容保存状态已更新",
        }.get(item_type, "任务进展已更新")
    exact = _TRACE_SUMMARY_LABELS.get(normalized)
    if exact is not None:
        return exact
    material_match = _READ_MATERIAL_RE.fullmatch(normalized)
    if material_match is not None:
        material = material_match.group(1).strip()
        if material == "Sandbox file":
            return "已读取计算文件"
        return f"已读取研究材料：{material}"
    if normalized.startswith("Loaded review candidate: "):
        title = normalized.removeprefix("Loaded review candidate: ").strip()
        return f"已读取待确认成果：{title}" if title else "已读取待确认成果"
    if normalized.endswith(" started"):
        name = normalized.removesuffix(" started").strip()
        return f"{name}开始工作" if name else "研究成员开始工作"
    subagent_match = _SUBAGENT_RESULT_RE.fullmatch(normalized)
    if subagent_match is not None:
        usable = subagent_match.group(1)
        if usable == "0":
            return "本轮研究成员结果未达到可用要求，正在调整"
        return f"{usable} 位研究成员已完成本轮工作"
    if item_type in {"evidence", "artifact"}:
        return _bounded_trace_text(normalized)
    if not allow_freeform:
        return _TRACE_FALLBACK_LABELS.get(item_type, "任务进展已更新")
    if normalized.startswith(("{", "[")) or not _HAS_CJK_RE.search(normalized):
        return _TRACE_FALLBACK_LABELS.get(item_type, "任务进展已更新")
    return _bounded_trace_text(normalized)


def _public_trace_item_summary(item: Any) -> str:
    public_summary = ""
    if item.item_type == "subagent_progress":
        public_summary = str((item.payload_json or {}).get("public_summary") or "").strip()
    return _public_trace_summary(
        item_type=item.item_type,
        summary=public_summary or item.summary,
        allow_freeform=item.item_type != "subagent_progress" or bool(public_summary),
    )


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReviewDecisionsRequest(_StrictModel):
    decision_id: str = Field(min_length=1, max_length=160)
    decisions: list[ReviewDecision] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def require_unique_review_items(self) -> ReviewDecisionsRequest:
        review_item_ids = [decision.review_item_id for decision in self.decisions]
        if len(review_item_ids) != len(set(review_item_ids)):
            raise ValueError("review_item_id values must be unique")
        return self


class MissionCommitRequest(_StrictModel):
    request_id: str = Field(min_length=1, max_length=160)
    review_item_ids: list[str] = Field(min_length=1, max_length=100)


class PrismVisualInsertionRequest(_StrictModel):
    source_review_item_id: str = Field(min_length=1, max_length=36)
    prism_context_ref: PrismContextRef


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


class SetReviewModeMissionAction(_StrictModel):
    action: Literal["set_review_mode"]
    command_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1, max_length=160)
    review_mode: ReviewMode


MissionAction = Annotated[
    CancelMissionAction | PauseMissionAction | ResumeMissionAction | SteerMissionAction | SetReviewModeMissionAction,
    Field(discriminator="action"),
]


async def _mission_runtime_service(
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> MissionRuntimeService:
    review_commit = build_review_commit_runtime(dataservice)
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
    while not await request.is_disconnected():
        runs = await dataservice.missions.list_workspace_changes(
            workspace_id=workspace_id,
            updated_at=cursor.watermark,
            after_mission_id=cursor.after_mission_id,
            limit=100,
        )
        emitted = False
        for run in runs:
            cursor.watermark = run.updated_at
            cursor.after_mission_id = run.mission_id
            if run.user_id != user_id:
                continue
            emitted = True
            token = _encode_cursor(cursor)
            yield _event_frame(
                event_id=token,
                payload={
                    "type": "mission.updated",
                    "missionId": run.mission_id,
                    "stateVersion": run.state_version,
                    "lastItemSeq": run.last_item_seq,
                    "cursor": token,
                },
            )
        if emitted:
            heartbeat_elapsed = 0.0
        else:
            heartbeat_elapsed += poll_seconds
            if heartbeat_elapsed >= heartbeat_seconds:
                heartbeat_elapsed = 0.0
                yield ": keep-alive\n\n"
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
    payload = view.model_dump(mode="json")
    for item in payload.get("review_items", []):
        has_binary_preview = bool(item.pop("preview_ref", None))
        item["preview_url"] = f"/api/missions/{mission_id}/review-items/{item['review_item_id']}/preview" if has_binary_preview else None
    _add_artifact_download_urls(payload, mission_id)
    _repair_legacy_evidence_names(payload)
    return payload


@router.get("/missions/{mission_id}/evidence")
async def list_mission_evidence(
    mission_id: str,
    cursor: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: AccountAuthSubject = Depends(get_current_user),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> dict[str, Any]:
    await _owned_run(
        mission_id,
        user_id=str(current_user.id),
        dataservice=dataservice,
    )
    page = await dataservice.missions.list_evidence_projection(
        mission_id,
        after_seq=cursor,
        limit=limit,
    )
    if page is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    payload = page.model_dump(mode="json")
    _repair_legacy_evidence_names(payload)
    return payload


@router.get("/missions/{mission_id}/review-items")
async def list_mission_review_projection(
    mission_id: str,
    cursor: str | None = Query(default=None, min_length=1, max_length=1024),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: AccountAuthSubject = Depends(get_current_user),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> dict[str, Any]:
    await _owned_run(
        mission_id,
        user_id=str(current_user.id),
        dataservice=dataservice,
    )
    page = await dataservice.missions.list_review_projection(
        mission_id,
        cursor=cursor,
        limit=limit,
    )
    if page is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    payload = page.model_dump(mode="json")
    for item in payload.get("items", []):
        has_binary_preview = bool(item.pop("preview_ref", None))
        item["preview_url"] = (
            f"/api/missions/{mission_id}/review-items/"
            f"{item['review_item_id']}/preview"
            if has_binary_preview
            else None
        )
    return payload


@router.get("/missions/{mission_id}/artifacts/{review_item_id}/download")
async def download_mission_artifact(
    mission_id: str,
    review_item_id: str,
    current_user: AccountAuthSubject = Depends(get_current_user),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> FileResponse:
    run = await _owned_run(
        mission_id,
        user_id=str(current_user.id),
        dataservice=dataservice,
    )
    result = await dataservice.missions.get_commit_for_review_item(
        mission_id,
        review_item_id,
    )
    if result is None or result.commit.status.value != "committed":
        raise HTTPException(status_code=404, detail="Committed Mission artifact not found")
    target_ref = str(result.commit.targets_json.get("target_ref") or "")
    if not target_ref:
        raise HTTPException(status_code=404, detail="Committed Mission artifact not found")
    download = await dataservice.resolve_asset_download(target_ref)
    if (
        download is None
        or download.asset.workspace_id != run.workspace_id
        or download.storage_backend != "local"
    ):
        raise HTTPException(status_code=404, detail="Committed Mission artifact not found")
    try:
        actual_path = resolve_workspace_upload_relative_path(
            run.workspace_id,
            download.storage_path,
            root=get_settings().workspace_asset_root,
        )
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Artifact path is outside the workspace") from exc
    if actual_path.is_symlink() or not actual_path.is_file():
        raise HTTPException(status_code=404, detail="Committed Mission artifact not found")
    return FileResponse(
        path=actual_path,
        filename=Path(download.filename).name,
        media_type=download.mime_type or "application/octet-stream",
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.get("/missions/{mission_id}/artifacts")
async def list_mission_artifacts(
    mission_id: str,
    cursor: int = Query(default=0, ge=0),
    tiebreaker: str = Query(default="", max_length=36),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: AccountAuthSubject = Depends(get_current_user),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> dict[str, Any]:
    await _owned_run(
        mission_id,
        user_id=str(current_user.id),
        dataservice=dataservice,
    )
    page = await dataservice.missions.list_artifact_projection(
        mission_id,
        after_seq=cursor,
        after_review_item_id=tiebreaker,
        limit=limit,
    )
    if page is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    payload = page.model_dump(mode="json")
    _add_artifact_download_urls(payload, mission_id)
    return payload


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


@router.get("/workspaces/{workspace_id}/missions/summary")
async def get_workspace_mission_summary(
    workspace_id: str,
    current_user: AccountAuthSubject = Depends(get_current_user),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> dict[str, Any]:
    user_id = str(current_user.id)
    try:
        await DataServiceMembershipAuthorizer(dataservice).require_active_member(
            workspace_id=workspace_id,
            user_id=user_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=404, detail="Workspace not found") from exc
    summary = await dataservice.missions.get_workspace_summary(
        workspace_id=workspace_id,
        user_id=user_id,
    )
    return summary.model_dump(mode="json")


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
    before_seq: int | None = Query(default=None, ge=1),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: AccountAuthSubject = Depends(get_current_user),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> dict[str, Any]:
    run = await _owned_run(
        mission_id,
        user_id=str(current_user.id),
        dataservice=dataservice,
    )
    upper_bound = min(before_seq or (run.last_item_seq + 1), run.last_item_seq + 1)
    requested_limit = min(limit, max(upper_bound - 1, 0))
    items = (
        await dataservice.missions.list_items(
            mission_id,
            after_seq=max(0, upper_bound - requested_limit - 1),
            limit=requested_limit,
        )
        if requested_limit
        else []
    )
    return {
        "items": [
            {
                "id": item.id,
                "mission_id": item.mission_id,
                "seq": item.seq,
                "item_type": item.item_type,
                "phase": item.phase.value,
                "stage_id": item.stage_id,
                "producer": item.producer,
                "summary": _public_trace_item_summary(item),
                "created_at": item.created_at.isoformat(),
                "detail_available": bool(item.payload_json or item.payload_ref),
            }
            for item in items
            if item.item_type not in _HIDDEN_PUBLIC_TRACE_ITEM_TYPES
        ],
        "next_cursor": items[0].seq if items and items[0].seq > 1 else None,
    }


@router.get("/missions/{mission_id}/review-items/{review_item_id}/preview")
async def get_mission_review_preview(
    mission_id: str,
    review_item_id: str,
    current_user: AccountAuthSubject = Depends(get_current_user),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
    preview_store: MissionPreviewStore = Depends(get_mission_preview_store),
) -> Response:
    run = await _owned_run(
        mission_id,
        user_id=str(current_user.id),
        dataservice=dataservice,
    )
    item = await dataservice.missions.get_review_item(mission_id, review_item_id)
    if (
        item is None
        or item.review_item_id != review_item_id
        or item.mission_id != mission_id
        or item.preview_ref is None
    ):
        raise HTTPException(status_code=404, detail="Mission preview not found")
    if item.preview_expires_at is not None and item.preview_expires_at <= datetime.now(UTC):
        raise HTTPException(status_code=410, detail="Mission preview expired")
    metadata_hash = hashlib.sha256(
        json.dumps(
            item.preview_json,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    if not item.preview_hash or not hmac.compare_digest(metadata_hash, item.preview_hash):
        raise HTTPException(status_code=409, detail="Mission preview integrity check failed")
    try:
        preview = await preview_store.read(item.preview_ref, workspace_id=run.workspace_id)
    except (LookupError, PermissionError):
        raise HTTPException(status_code=404, detail="Mission preview not found") from None
    except ValueError as exc:
        code = str(exc)
        if code == "review_preview_expired":
            raise HTTPException(status_code=410, detail="Mission preview expired") from exc
        raise HTTPException(status_code=409, detail="Mission preview integrity check failed") from exc

    descriptor = preview.descriptor
    materialization = dict(item.preview_json.get("materialization") or {})
    payload = dict(materialization.get("payload") or {})
    expected_hash = str(payload.get("content_hash") or item.preview_json.get("content_hash") or "")
    expected_mime = str(payload.get("mime_type") or item.preview_json.get("mime_type") or "")
    if expected_hash and not hmac.compare_digest(expected_hash, descriptor.content_hash):
        raise HTTPException(status_code=409, detail="Mission preview integrity check failed")
    if expected_mime and expected_mime != descriptor.mime_type:
        raise HTTPException(status_code=409, detail="Mission preview integrity check failed")
    encoded_filename = quote(descriptor.filename)
    inline_mimes = {"application/pdf", "image/png", "image/svg+xml", "image/webp"}
    disposition = "inline" if descriptor.mime_type in inline_mimes else "attachment"
    return Response(
        content=preview.content,
        media_type=descriptor.mime_type,
        headers={
            "Cache-Control": "private, no-store, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
            "ETag": f'"{descriptor.content_hash}"',
            "Content-Disposition": f"{disposition}; filename*=UTF-8''{encoded_filename}",
            "Content-Security-Policy": "sandbox; default-src 'none'; style-src 'unsafe-inline'",
            "X-Content-Type-Options": "nosniff",
        },
    )


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
    runtime: MissionRuntimeService = Depends(_mission_runtime_service),
) -> dict[str, Any]:
    try:
        result = await runtime.decide_reviews(
            mission_id,
            actor_user_id=str(current_user.id),
            decision_id=command.decision_id,
            decisions=command.decisions,
        )
    except (LookupError, PermissionError) as exc:
        raise HTTPException(status_code=404, detail="Mission not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except DataServiceClientError as exc:
        from src.gateway.error_mapping import dataservice_client_to_http_exception

        raise dataservice_client_to_http_exception(exc) from exc
    return result.model_dump(mode="json")


@router.post("/missions/{mission_id}/commits")
async def commit_mission_review_items(
    mission_id: str,
    command: MissionCommitRequest,
    current_user: AccountAuthSubject = Depends(get_current_user),
    runtime: MissionRuntimeService = Depends(_mission_runtime_service),
) -> dict[str, Any]:
    try:
        result = await runtime.commit_reviews(
            mission_id,
            actor_user_id=str(current_user.id),
            review_item_ids=tuple(command.review_item_ids),
            request_id=command.request_id,
        )
    except (LookupError, PermissionError) as exc:
        raise HTTPException(status_code=404, detail="Mission not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except DataServiceClientError as exc:
        from src.gateway.error_mapping import dataservice_client_to_http_exception

        raise dataservice_client_to_http_exception(exc) from exc
    return result.model_dump(mode="json")


@router.post("/missions/{mission_id}/visual-insertions")
async def stage_mission_visual_insertion(
    mission_id: str,
    command: PrismVisualInsertionRequest,
    current_user: AccountAuthSubject = Depends(get_current_user),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> dict[str, str]:
    try:
        item = await PrismVisualInsertionService(
            dataservice=dataservice,
            membership=DataServiceMembershipAuthorizer(dataservice),
        ).stage(
            mission_id,
            actor_user_id=str(current_user.id),
            source_review_item_id=command.source_review_item_id,
            prism_context_ref=command.prism_context_ref,
        )
    except (LookupError, PermissionError) as exc:
        raise HTTPException(status_code=404, detail="Mission not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except DataServiceClientError as exc:
        from src.gateway.error_mapping import dataservice_client_to_http_exception

        raise dataservice_client_to_http_exception(exc) from exc
    return {"review_item_id": item.review_item_id}


@router.post("/missions/{mission_id}/permissions/{request_id}/resolve")
async def resolve_mission_permission(
    mission_id: str,
    request_id: str,
    command: PermissionResolutionRequest,
    current_user: AccountAuthSubject = Depends(get_current_user),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
    runtime: MissionRuntimeService = Depends(_mission_runtime_service),
) -> dict[str, Any]:
    try:
        result = await PermissionResolutionService(
            missions=dataservice.missions,
            membership=DataServiceMembershipAuthorizer(dataservice),
            resumer=runtime,
        ).resolve(
            mission_id,
            request_id=request_id,
            decision=command.decision,
            actor_user_id=str(current_user.id),
            input_json=command.input_json,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Mission not found") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Active workspace membership required") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except DataServiceClientError as exc:
        from src.gateway.error_mapping import dataservice_client_to_http_exception

        raise dataservice_client_to_http_exception(exc) from exc
    return result.model_dump(mode="json")


__all__ = ["MissionAction", "_mission_event_stream", "router"]
