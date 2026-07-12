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
        del user_id
        if self._dataservice is not None:
            missions = await self._dataservice.missions.list_workspace(
                workspace_id=workspace_id,
                limit=100,
            )
        else:
            async with dataservice_client() as client:
                missions = await client.missions.list_workspace(
                    workspace_id=workspace_id,
                    limit=100,
                )

        completed = sum(item.status == MissionStatus.COMPLETED for item in missions)
        active = sum(item.status in _ACTIVE for item in missions)
        failed = sum(item.status in {MissionStatus.FAILED, MissionStatus.CANCELLED} for item in missions)
        total = len(missions)
        percent = int(completed * 100 / total) if total else 0
        current = next((item for item in missions if item.status in _ACTIVE), None)
        latest = missions[0] if missions else None

        recent = await self._activity_service.get_activity(workspace_id, limit=1)
        recent_items = recent.get("items", [])
        recent_item = recent_items[0] if recent_items else None
        phase_source = current or latest
        current_phase = {
            "mission_id": phase_source.mission_id if phase_source else None,
            "mission_policy_id": phase_source.mission_policy_id if phase_source else None,
            "title": phase_source.title if phase_source else "描述你的研究目标",
            "status": phase_source.status.value if phase_source else "not_started",
            "description": (phase_source.objective if phase_source else "问津会在对话中理解目标并组织研究任务。"),
        }
        next_step = None
        if current is not None:
            next_step = {
                "mission_id": current.mission_id,
                "mission_policy_id": current.mission_policy_id,
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
