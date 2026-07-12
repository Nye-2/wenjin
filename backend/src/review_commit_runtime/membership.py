"""Single authorization boundary for user-driven Mission operations."""

from __future__ import annotations

from typing import Protocol

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.mission import MissionRunPayload
from src.dataservice_client.mission_client import MissionDataServiceClient


class MembershipAuthorizer(Protocol):
    async def require_active_member(
        self,
        *,
        workspace_id: str,
        user_id: str,
    ) -> None: ...


class DataServiceMembershipAuthorizer:
    """Fail closed against the current workspace membership state."""

    def __init__(self, dataservice: AsyncDataServiceClient) -> None:
        self._dataservice = dataservice

    async def require_active_member(self, *, workspace_id: str, user_id: str) -> None:
        if not await self._dataservice.workspace_has_active_membership(
            workspace_id=workspace_id,
            user_id=user_id,
        ):
            raise PermissionError("active_workspace_membership_required")


async def require_owned_mission(
    missions: MissionDataServiceClient,
    authorizer: MembershipAuthorizer,
    *,
    mission_id: str,
    actor_user_id: str,
) -> MissionRunPayload:
    run = await missions.get(mission_id)
    if run is None or run.user_id != actor_user_id:
        raise LookupError("MissionRun not found")
    await authorizer.require_active_member(
        workspace_id=run.workspace_id,
        user_id=actor_user_id,
    )
    return run


__all__ = [
    "DataServiceMembershipAuthorizer",
    "MembershipAuthorizer",
    "require_owned_mission",
]
