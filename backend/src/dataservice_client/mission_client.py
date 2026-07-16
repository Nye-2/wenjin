"""Composed typed client for the Mission DataService domain."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, TypeVar

from pydantic import BaseModel

from src.dataservice_client.contracts.mission import (
    MissionAppendPayload,
    MissionAppendResultPayload,
    MissionApplyCommandsPayload,
    MissionArtifactPagePayload,
    MissionCancelPayload,
    MissionCheckpointPayload,
    MissionCommitCreatePayload,
    MissionCommitCreateResultPayload,
    MissionCommitFinishPayload,
    MissionCommitResultPayload,
    MissionCommitStartPayload,
    MissionCreatePayload,
    MissionCreateResultPayload,
    MissionDispatchReleasePayload,
    MissionEvidencePagePayload,
    MissionHistoryPagePayload,
    MissionItemPayload,
    MissionLeaseClaimPayload,
    MissionLeaseHeartbeatPayload,
    MissionLeaseReleasePayload,
    MissionOperationClaimPayload,
    MissionOperationClaimResultPayload,
    MissionOperationFinishPayload,
    MissionOperationFinishResultPayload,
    MissionOperationReceiptPayload,
    MissionPausePayload,
    MissionPreviewCleanupPayload,
    MissionPreviewCleanupResultPayload,
    MissionResumePayload,
    MissionReviewDecisionsPayload,
    MissionReviewItemPayload,
    MissionReviewItemsCreatePayload,
    MissionReviewItemsResultPayload,
    MissionRunnableBatchClaimPayload,
    MissionRunPayload,
    MissionStatsPayload,
    MissionStatus,
    MissionUserCommandPayload,
    MissionUserSummaryPayload,
    MissionViewPayload,
    MissionViewRunPayload,
    MissionWorkspaceSummaryPayload,
)

RequestCallable = Callable[..., Awaitable[dict[str, Any]]]
PayloadT = TypeVar("PayloadT", bound=BaseModel)


class MissionDataServiceClient:
    """Mission-only client composed into the root DataService transport."""

    def __init__(self, request: RequestCallable) -> None:
        self._request = request

    async def _post(
        self,
        path: str,
        command: BaseModel,
        response_type: type[PayloadT],
    ) -> PayloadT:
        response = await self._request("POST", path, json=command.model_dump(mode="json"))
        return response_type.model_validate(response["data"])

    async def create(self, command: MissionCreatePayload) -> MissionCreateResultPayload:
        return await self._post("/internal/v1/missions", command, MissionCreateResultPayload)

    async def get(self, mission_id: str) -> MissionRunPayload | None:
        response = await self._request("GET", f"/internal/v1/missions/{mission_id}")
        return MissionRunPayload.model_validate(response["data"]) if response.get("data") else None

    async def get_view(self, mission_id: str) -> MissionViewPayload | None:
        response = await self._request("GET", f"/internal/v1/missions/{mission_id}/view")
        return MissionViewPayload.model_validate(response["data"]) if response.get("data") else None

    async def list_evidence_projection(
        self,
        mission_id: str,
        *,
        after_seq: int = 0,
        limit: int = 50,
    ) -> MissionEvidencePagePayload | None:
        response = await self._request(
            "GET",
            f"/internal/v1/missions/{mission_id}/evidence",
            params={"after_seq": after_seq, "limit": limit},
        )
        return (
            MissionEvidencePagePayload.model_validate(response["data"])
            if response.get("data")
            else None
        )

    async def list_artifact_projection(
        self,
        mission_id: str,
        *,
        after_seq: int = 0,
        limit: int = 50,
    ) -> MissionArtifactPagePayload | None:
        response = await self._request(
            "GET",
            f"/internal/v1/missions/{mission_id}/artifacts",
            params={"after_seq": after_seq, "limit": limit},
        )
        return (
            MissionArtifactPagePayload.model_validate(response["data"])
            if response.get("data")
            else None
        )

    async def get_by_idempotency_key(
        self,
        *,
        workspace_id: str,
        key: str,
    ) -> MissionRunPayload | None:
        response = await self._request(
            "GET",
            f"/internal/v1/workspaces/{workspace_id}/missions/by-idempotency-key",
            params={"key": key},
        )
        return (
            MissionRunPayload.model_validate(response["data"])
            if response.get("data")
            else None
        )

    async def get_foreground_for_thread(
        self,
        *,
        workspace_id: str,
        thread_id: str,
        user_id: str,
    ) -> MissionRunPayload | None:
        response = await self._request(
            "GET",
            f"/internal/v1/workspaces/{workspace_id}/threads/{thread_id}/foreground-mission",
            params={"user_id": user_id},
        )
        return (
            MissionRunPayload.model_validate(response["data"])
            if response.get("data")
            else None
        )

    async def get_latest_for_thread(
        self,
        *,
        workspace_id: str,
        thread_id: str,
        user_id: str,
    ) -> MissionRunPayload | None:
        response = await self._request(
            "GET",
            f"/internal/v1/workspaces/{workspace_id}/threads/{thread_id}/latest-mission",
            params={"user_id": user_id},
        )
        return (
            MissionRunPayload.model_validate(response["data"])
            if response.get("data")
            else None
        )

    async def cleanup_expired_previews(self, command: MissionPreviewCleanupPayload) -> MissionPreviewCleanupResultPayload:
        return await self._post(
            "/internal/v1/missions/review-previews/cleanup",
            command,
            MissionPreviewCleanupResultPayload,
        )

    async def list_workspace(
        self,
        *,
        workspace_id: str,
        user_id: str | None = None,
        status: list[MissionStatus] | None = None,
        limit: int = 50,
    ) -> list[MissionViewRunPayload]:
        page = await self.list_workspace_page(
            workspace_id=workspace_id,
            user_id=user_id,
            status=status,
            limit=limit,
        )
        return page.items

    async def list_workspace_page(
        self,
        *,
        workspace_id: str,
        user_id: str | None = None,
        status: list[MissionStatus] | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> MissionHistoryPagePayload:
        response = await self._request(
            "GET",
            f"/internal/v1/workspaces/{workspace_id}/missions",
            params={
                "user_id": user_id,
                "status": [item.value for item in status] if status else None,
                "limit": limit,
                "cursor": cursor,
            },
        )
        return MissionHistoryPagePayload.model_validate(response["data"])

    async def get_workspace_summary(
        self,
        *,
        workspace_id: str,
        user_id: str | None = None,
    ) -> MissionWorkspaceSummaryPayload:
        response = await self._request(
            "GET",
            f"/internal/v1/workspaces/{workspace_id}/missions/summary",
            params={"user_id": user_id},
        )
        return MissionWorkspaceSummaryPayload.model_validate(response["data"])

    async def get_user_summary(
        self,
        *,
        user_id: str,
        recent_limit: int = 10,
    ) -> MissionUserSummaryPayload:
        response = await self._request(
            "GET",
            f"/internal/v1/users/{user_id}/missions/summary",
            params={"recent_limit": recent_limit},
        )
        return MissionUserSummaryPayload.model_validate(response["data"])

    async def list_workspace_changes(
        self,
        *,
        workspace_id: str,
        updated_at: datetime,
        after_mission_id: str = "",
        limit: int = 100,
    ) -> list[MissionRunPayload]:
        response = await self._request(
            "GET",
            f"/internal/v1/workspaces/{workspace_id}/missions/changes",
            params={
                "updated_at": updated_at.isoformat(),
                "after_mission_id": after_mission_id,
                "limit": limit,
            },
        )
        return [MissionRunPayload.model_validate(item) for item in response["data"]]

    async def aggregate_stats(
        self,
        *,
        created_since: datetime,
        granularity: str,
    ) -> MissionStatsPayload:
        response = await self._request(
            "GET",
            "/internal/v1/admin/missions/stats",
            params={
                "created_since": created_since.isoformat(),
                "granularity": granularity,
            },
        )
        return MissionStatsPayload.model_validate(response["data"])

    async def claim_lease(self, mission_id: str, command: MissionLeaseClaimPayload) -> MissionRunPayload:
        return await self._post(
            f"/internal/v1/missions/{mission_id}/lease/claim",
            command,
            MissionRunPayload,
        )

    async def heartbeat_lease(self, mission_id: str, command: MissionLeaseHeartbeatPayload) -> MissionRunPayload:
        return await self._post(
            f"/internal/v1/missions/{mission_id}/lease/heartbeat",
            command,
            MissionRunPayload,
        )

    async def release_lease(self, mission_id: str, command: MissionLeaseReleasePayload) -> MissionRunPayload:
        return await self._post(
            f"/internal/v1/missions/{mission_id}/lease/release",
            command,
            MissionRunPayload,
        )

    async def claim_runnable(self, command: MissionRunnableBatchClaimPayload) -> list[MissionRunPayload]:
        response = await self._request(
            "POST",
            "/internal/v1/missions/runnable/claim",
            json=command.model_dump(mode="json"),
        )
        return [MissionRunPayload.model_validate(item) for item in response["data"]]

    async def release_dispatch(
        self,
        mission_id: str,
        command: MissionDispatchReleasePayload,
    ) -> MissionRunPayload:
        return await self._post(
            f"/internal/v1/missions/{mission_id}/dispatch/release",
            command,
            MissionRunPayload,
        )

    async def claim_operation(
        self,
        mission_id: str,
        command: MissionOperationClaimPayload,
    ) -> MissionOperationClaimResultPayload:
        return await self._post(
            f"/internal/v1/missions/{mission_id}/operations/claim",
            command,
            MissionOperationClaimResultPayload,
        )

    async def get_operation(
        self,
        mission_id: str,
        operation_key: str,
    ) -> MissionOperationReceiptPayload | None:
        response = await self._request(
            "GET",
            f"/internal/v1/missions/{mission_id}/operations/{operation_key}",
        )
        return (
            MissionOperationReceiptPayload.model_validate(response["data"])
            if response.get("data")
            else None
        )

    async def finish_operation(
        self,
        mission_id: str,
        command: MissionOperationFinishPayload,
    ) -> MissionOperationFinishResultPayload:
        return await self._post(
            f"/internal/v1/missions/{mission_id}/operations/finish",
            command,
            MissionOperationFinishResultPayload,
        )

    async def append_items(self, mission_id: str, command: MissionAppendPayload) -> MissionAppendResultPayload:
        return await self._post(
            f"/internal/v1/missions/{mission_id}/items/append",
            command,
            MissionAppendResultPayload,
        )

    async def checkpoint(self, mission_id: str, command: MissionCheckpointPayload) -> MissionAppendResultPayload:
        return await self._post(
            f"/internal/v1/missions/{mission_id}/checkpoint",
            command,
            MissionAppendResultPayload,
        )

    async def list_items(
        self,
        mission_id: str,
        *,
        after_seq: int = 0,
        limit: int = 100,
        item_type: str | None = None,
        operation_id: str | None = None,
    ) -> list[MissionItemPayload]:
        response = await self._request(
            "GET",
            f"/internal/v1/missions/{mission_id}/items",
            params={
                "after_seq": after_seq,
                "limit": limit,
                "item_type": item_type,
                "operation_id": operation_id,
            },
        )
        return [MissionItemPayload.model_validate(item) for item in response["data"]]

    async def append_command(self, mission_id: str, command: MissionUserCommandPayload) -> MissionAppendResultPayload:
        return await self._post(
            f"/internal/v1/missions/{mission_id}/commands",
            command,
            MissionAppendResultPayload,
        )

    async def list_unapplied_commands(self, mission_id: str, *, limit: int = 100) -> list[MissionItemPayload]:
        response = await self._request(
            "GET",
            f"/internal/v1/missions/{mission_id}/commands/unapplied",
            params={"limit": limit},
        )
        return [MissionItemPayload.model_validate(item) for item in response["data"]]

    async def apply_commands(self, mission_id: str, command: MissionApplyCommandsPayload) -> MissionAppendResultPayload:
        return await self._post(
            f"/internal/v1/missions/{mission_id}/commands/apply",
            command,
            MissionAppendResultPayload,
        )

    async def pause(self, mission_id: str, command: MissionPausePayload) -> MissionAppendResultPayload:
        return await self._post(
            f"/internal/v1/missions/{mission_id}/pause",
            command,
            MissionAppendResultPayload,
        )

    async def resume(self, mission_id: str, command: MissionResumePayload) -> MissionAppendResultPayload:
        return await self._post(
            f"/internal/v1/missions/{mission_id}/resume",
            command,
            MissionAppendResultPayload,
        )

    async def cancel(self, mission_id: str, command: MissionCancelPayload) -> MissionAppendResultPayload:
        return await self._post(
            f"/internal/v1/missions/{mission_id}/cancel",
            command,
            MissionAppendResultPayload,
        )

    async def create_review_items(self, mission_id: str, command: MissionReviewItemsCreatePayload) -> MissionReviewItemsResultPayload:
        return await self._post(
            f"/internal/v1/missions/{mission_id}/review-items",
            command,
            MissionReviewItemsResultPayload,
        )

    async def list_review_items(self, mission_id: str, *, status: list[str] | None = None) -> list[MissionReviewItemPayload]:
        response = await self._request(
            "GET",
            f"/internal/v1/missions/{mission_id}/review-items",
            params={"status": status},
        )
        return [MissionReviewItemPayload.model_validate(item) for item in response["data"]]

    async def apply_review_decisions(self, mission_id: str, command: MissionReviewDecisionsPayload) -> MissionReviewItemsResultPayload:
        return await self._post(
            f"/internal/v1/missions/{mission_id}/review-decisions",
            command,
            MissionReviewItemsResultPayload,
        )

    async def commit(self, mission_id: str, command: MissionCommitCreatePayload) -> MissionCommitCreateResultPayload:
        return await self._post(
            f"/internal/v1/missions/{mission_id}/commits",
            command,
            MissionCommitCreateResultPayload,
        )

    async def start_commit(
        self,
        mission_id: str,
        commit_id: str,
        command: MissionCommitStartPayload,
    ) -> MissionCommitResultPayload:
        return await self._post(
            f"/internal/v1/missions/{mission_id}/commits/{commit_id}/start",
            command,
            MissionCommitResultPayload,
        )

    async def finish_commit(
        self,
        mission_id: str,
        commit_id: str,
        command: MissionCommitFinishPayload,
    ) -> MissionCommitResultPayload:
        return await self._post(
            f"/internal/v1/missions/{mission_id}/commits/{commit_id}/finish",
            command,
            MissionCommitResultPayload,
        )


__all__ = ["MissionDataServiceClient"]
