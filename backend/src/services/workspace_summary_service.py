"""Mission-backed workspace summary projection."""

from __future__ import annotations

from typing import Any

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.mission import MissionStatus
from src.dataservice_client.provider import dataservice_client
from src.services.workspace_activity_service import WorkspaceActivityService

_ACTIVE = {MissionStatus.CREATED, MissionStatus.PLANNING, MissionStatus.RUNNING, MissionStatus.WAITING}


class WorkspaceSummaryService:
    """Build the lightweight dashboard summary from canonical MissionRuns."""

    def __init__(
        self,
        *,
        dataservice: AsyncDataServiceClient | None = None,
        activity_service: WorkspaceActivityService | None = None,
        **_: Any,
    ) -> None:
        self._dataservice = dataservice
        self._activity_service = activity_service or WorkspaceActivityService(dataservice=dataservice)

    async def get_summary(
        self,
        workspace_id: str,
        *,
        workspace_type: str,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        if self._dataservice is not None:
            summary = await self._dataservice.missions.get_workspace_summary(
                workspace_id=workspace_id,
                user_id=user_id,
            )
        else:
            async with dataservice_client() as client:
                summary = await client.missions.get_workspace_summary(
                    workspace_id=workspace_id,
                    user_id=user_id,
                )

        completed = summary.status_counts.get(MissionStatus.COMPLETED.value, 0)
        active = sum(summary.status_counts.get(status.value, 0) for status in _ACTIVE)
        failed = sum(
            summary.status_counts.get(status.value, 0)
            for status in (MissionStatus.FAILED, MissionStatus.CANCELLED)
        )
        total = summary.total
        percent = int(completed * 100 / total) if total else 0
        current = summary.active
        latest = summary.latest

        recent = await self._activity_service.get_activity(workspace_id, limit=1)
        recent_items = recent.get("items", [])
        recent_item = recent_items[0] if recent_items else None
        phase_source = current or latest
        current_phase = {
            "mission_id": phase_source.mission_id if phase_source else None,
            "mission_policy_id": None,
            "title": phase_source.title if phase_source else "描述你的研究目标",
            "status": phase_source.status.value if phase_source else "not_started",
            "description": (phase_source.objective if phase_source else "问津会在对话中理解目标并组织研究任务。"),
        }
        next_step = None
        if current is not None:
            next_step = {
                "mission_id": current.mission_id,
                "mission_policy_id": None,
                "title": "继续当前研究任务",
                "description": current.objective,
                "reason": "任务已有可恢复进展。",
                "status": current.status.value,
                "status_label": "进行中",
            }

        return {
            "workspace_id": workspace_id,
            "workspace_type": workspace_type,
            "headline": (f"{active} 项研究任务正在推进" if active else "从一个具体研究目标开始"),
            "progress": {
                "completed": completed,
                "in_progress": active,
                "failed": failed,
                "total": total,
                "percent": percent,
            },
            "current_phase": current_phase,
            "next_step": next_step,
            "recommended_actions": [next_step] if next_step else [],
            "risk_items": [],
            "recent_activity": (
                {
                    "title": recent_item["title"],
                    "summary": recent_item.get("summary"),
                    "kind": recent_item.get("kind"),
                    "occurred_at": str(recent_item["occurred_at"]),
                }
                if recent_item
                else None
            ),
        }


__all__ = ["WorkspaceSummaryService"]
