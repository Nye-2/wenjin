"""Gateway/worker composition seam for the canonical MissionRuntime."""

from __future__ import annotations

from typing import Any

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.mission import (
    MissionPausePayload,
    MissionReviewMode,
    MissionRunPayload,
    MissionStatus,
    MissionUserCommandPayload,
)
from src.mission_runtime import (
    MissionRuntime,
    MissionStartReceipt,
    MissionStartRequest,
)
from src.mission_runtime.composition import build_production_mission_runtime
from src.mission_runtime.production import CeleryMissionWakeupPublisher
from src.review_commit_runtime.contracts import ReviewAction, ReviewDecision
from src.review_commit_runtime.runtime import ReviewCommitRuntime


async def build_mission_runtime(dataservice: AsyncDataServiceClient) -> MissionRuntime:
    return await build_production_mission_runtime(dataservice)


class MissionRuntimeService:
    """Narrow start/resume/cancel API used by the future WorkspaceAgent."""

    def __init__(
        self,
        runtime: MissionRuntime,
        *,
        dataservice: AsyncDataServiceClient,
        review_commit: ReviewCommitRuntime,
    ) -> None:
        self.runtime = runtime
        self.dataservice = dataservice
        self.review_commit = review_commit

    async def start(self, request: MissionStartRequest) -> MissionStartReceipt:
        return await self.runtime.start(request)

    async def resume(
        self,
        mission_id: str,
        *,
        request_id: str,
        input_json: dict[str, Any],
        producer: str = "workspace_agent",
    ) -> MissionRunPayload:
        return await self.runtime.resume(
            mission_id,
            request_id=request_id,
            input_json=input_json,
            producer=producer,
        )

    async def cancel(
        self,
        mission_id: str,
        *,
        request_id: str,
        reason: str | None = None,
        producer: str = "workspace_agent",
    ) -> MissionRunPayload:
        return await self.runtime.cancel(
            mission_id,
            request_id=request_id,
            reason=reason,
            producer=producer,
        )

    async def pause(
        self,
        mission_id: str,
        *,
        request_id: str,
        actor_user_id: str,
        reason: str,
    ) -> MissionRunPayload:
        current = await self.dataservice.missions.get(mission_id)
        if current is None or current.user_id != actor_user_id:
            raise PermissionError("MissionRun does not belong to the actor")
        result = await self.dataservice.missions.pause(
            mission_id,
            MissionPausePayload(
                request_id=request_id,
                reason="user_input",
                pending_request={
                    "request_id": request_id,
                    "request_type": "user_pause",
                    "summary": reason,
                },
                producer="mission_gateway",
            ),
        )
        return result.mission

    async def set_review_mode(
        self,
        mission_id: str,
        *,
        command_id: str,
        actor_user_id: str,
        review_mode: MissionReviewMode,
    ) -> MissionRunPayload:
        current = await self.dataservice.missions.get(mission_id)
        if current is None or current.user_id != actor_user_id:
            raise PermissionError("MissionRun does not belong to the actor")
        result = await self.dataservice.missions.append_command(
            mission_id,
            MissionUserCommandPayload(
                command_id=command_id,
                command_type="set_review_mode",
                summary=f"Review mode changed to {review_mode.value}",
                producer="mission_gateway",
                payload_json={"review_mode": review_mode.value},
            ),
        )
        return result.mission

    async def get(self, mission_id: str) -> MissionRunPayload | None:
        return await self.dataservice.missions.get(mission_id)

    async def foreground_for_thread(
        self,
        *,
        workspace_id: str,
        thread_id: str,
        user_id: str,
    ) -> MissionRunPayload | None:
        return await self.dataservice.missions.get_foreground_for_thread(
            workspace_id=workspace_id,
            thread_id=thread_id,
            user_id=user_id,
        )

    async def steer(
        self,
        mission_id: str,
        *,
        command_id: str,
        actor_user_id: str,
        input_kind: str,
        instruction: str,
        request_id: str | None = None,
    ) -> MissionRunPayload:
        current = await self.dataservice.missions.get(mission_id)
        if current is None:
            raise ValueError("MissionRun was not found")
        if current.user_id != actor_user_id:
            raise PermissionError("MissionRun does not belong to the actor")
        if input_kind == "cancel":
            return await self.cancel(
                mission_id,
                request_id=request_id or command_id,
                reason=instruction,
            )
        if current.status == MissionStatus.WAITING:
            if not request_id:
                raise ValueError("Waiting mission input requires request_id")
            return await self.resume(
                mission_id,
                request_id=request_id,
                input_json={"kind": input_kind, "instruction": instruction},
            )
        if input_kind == "advisory":
            raise ValueError("Advisory input must remain in chat")
        result = await self.dataservice.missions.append_command(
            mission_id,
            MissionUserCommandPayload(
                command_id=command_id,
                command_type=input_kind,
                summary=instruction,
                payload_json={"instruction": instruction},
            ),
        )
        await self.runtime.wakeups.publish(mission_id, command_hint=command_id)
        return result.mission

    async def review(
        self,
        mission_id: str,
        *,
        decision_id: str,
        actor_user_id: str,
        review_item_ids: tuple[str, ...],
        decision: str,
        rationale: str | None,
    ) -> MissionRunPayload:
        current = await self.dataservice.missions.get(mission_id)
        if current is None:
            raise ValueError("MissionRun was not found")
        if current.user_id != actor_user_id:
            raise PermissionError("MissionRun does not belong to the actor")
        await self.review_commit.decide(
            mission_id,
            actor_user_id=actor_user_id,
            decision_id=decision_id,
            decisions=[
                ReviewDecision(
                    review_item_id=item_id,
                    action=ReviewAction(decision),
                    rationale=rationale,
                )
                for item_id in review_item_ids
            ],
            bulk=False,
        )
        refreshed = await self.dataservice.missions.get(mission_id)
        if refreshed is None:
            raise RuntimeError("MissionRun disappeared after review decision")
        return refreshed

    async def request_commit(
        self,
        mission_id: str,
        *,
        actor_user_id: str,
        review_item_ids: tuple[str, ...],
        request_id: str,
    ) -> MissionRunPayload:
        current = await self.dataservice.missions.get(mission_id)
        if current is None:
            raise ValueError("MissionRun was not found")
        if current.user_id != actor_user_id:
            raise PermissionError("MissionRun does not belong to the actor")
        await self.review_commit.commit_many(
            mission_id,
            actor_user_id=actor_user_id,
            review_item_ids=list(review_item_ids),
            request_id=request_id,
        )
        refreshed = await self.dataservice.missions.get(mission_id)
        if refreshed is None:
            raise RuntimeError("MissionRun disappeared after commit request")
        return refreshed


__all__ = [
    "CeleryMissionWakeupPublisher",
    "MissionRuntimeService",
    "build_mission_runtime",
]
