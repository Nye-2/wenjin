"""Mission-backed workspace activity projection."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.provider import dataservice_client


class WorkspaceActivityService:
    """Project recent MissionRuns into the compact workspace activity feed."""

    def __init__(self, *, dataservice: AsyncDataServiceClient | None = None) -> None:
        self._dataservice = dataservice

    async def get_activity(
        self,
        workspace_id: str,
        *,
        user_id: str | None = None,
        limit: int = 40,
    ) -> dict[str, Any]:
        if self._dataservice is not None:
            missions = await self._dataservice.missions.list_workspace(
                workspace_id=workspace_id,
                user_id=user_id,
                limit=limit,
            )
        else:
            async with dataservice_client() as client:
                missions = await client.missions.list_workspace(
                    workspace_id=workspace_id,
                    user_id=user_id,
                    limit=limit,
                )
        items = [self._mission_item(mission) for mission in missions]
        return {"items": items, "count": len(items)}

    @staticmethod
    def _mission_item(mission: Any) -> dict[str, Any]:
        occurred_at: datetime | str = mission.completed_at or mission.updated_at or mission.created_at
        return {
            "id": f"mission:{mission.mission_id}",
            "kind": "mission",
            "workspace_id": mission.workspace_id,
            "occurred_at": occurred_at,
            "title": mission.title,
            "summary": mission.objective,
            "status": mission.status.value,
            "thread_id": mission.thread_id,
            "mission_id": mission.mission_id,
            "mission_policy_id": None,
            "metadata": {
                "active_stage_id": mission.active_stage_id,
                "pending_review_count": mission.pending_review_count,
                "evidence_count": mission.evidence_count,
                "artifact_count": mission.artifact_count,
            },
        }


__all__ = ["WorkspaceActivityService"]
