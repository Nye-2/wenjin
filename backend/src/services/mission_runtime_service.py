"""Gateway/worker composition seam for the canonical MissionRuntime."""

from __future__ import annotations

import hashlib
from typing import Any

from src.contracts.mission_policy import ReviewPolicy
from src.contracts.review_policy import ReviewMode
from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.mission import (
    MissionRunPayload,
    MissionStatus,
    MissionUserCommandPayload,
)
from src.mission_runtime import (
    MissionContinuationDirective,
    MissionRuntime,
    MissionStartReceipt,
    MissionStartRejectedError,
    MissionStartRequest,
)
from src.mission_runtime.composition import build_production_mission_runtime
from src.mission_runtime.production import (
    CeleryMissionWakeupPublisher,
    MissionProductionConfigurationError,
)
from src.review_commit_runtime.contracts import (
    CommitBatchOutcome,
    ReviewAction,
    ReviewDecision,
    ReviewDecisionBatchOutcome,
)
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
        result = await self.dataservice.missions.append_command(
            mission_id,
            MissionUserCommandPayload(
                command_id=request_id,
                command_type="pause",
                summary=reason,
                producer="mission_gateway",
                payload_json={"reason": reason},
            ),
        )
        await self.runtime.wakeups.publish(
            mission_id,
            command_hint=request_id,
        )
        return result.mission

    async def set_review_mode(
        self,
        mission_id: str,
        *,
        command_id: str,
        actor_user_id: str,
        review_mode: ReviewMode,
    ) -> MissionRunPayload:
        current = await self.dataservice.missions.get(mission_id)
        if current is None or current.user_id != actor_user_id:
            raise PermissionError("MissionRun does not belong to the actor")
        raw_policy = current.runtime_context_json.get("mission_policy_snapshot")
        if not isinstance(raw_policy, dict) or not isinstance(
            raw_policy.get("review_policy"),
            dict,
        ):
            raise ValueError("Pinned MissionPolicy review policy is unavailable")
        pinned_review_policy = ReviewPolicy.model_validate(raw_policy["review_policy"])
        review_mode = pinned_review_policy.require_allowed_mode(review_mode)
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
        if result.mission.status not in {
            MissionStatus.COMPLETED,
            MissionStatus.FAILED,
            MissionStatus.CANCELLED,
        }:
            await self.runtime.wakeups.publish(
                mission_id,
                command_hint=command_id,
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
        mission_inputs: tuple[dict[str, Any], ...] = (),
        prism_context_ref: dict[str, Any] | None = None,
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
                input_json={
                    "kind": input_kind,
                    "instruction": instruction,
                    "mission_inputs": list(mission_inputs),
                    **({"prism_context_ref": prism_context_ref} if prism_context_ref is not None else {}),
                },
            )
        if input_kind == "advisory":
            raise ValueError("Advisory input must remain in chat")
        result = await self.dataservice.missions.append_command(
            mission_id,
            MissionUserCommandPayload(
                command_id=command_id,
                command_type=input_kind,
                summary=instruction,
                payload_json={
                    "instruction": instruction,
                    "mission_inputs": list(mission_inputs),
                    **({"prism_context_ref": prism_context_ref} if prism_context_ref is not None else {}),
                },
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
        result = await self.decide_reviews(
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
        )
        target_mission_id = result.continuation_mission_id or mission_id
        refreshed = await self.dataservice.missions.get(target_mission_id)
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
        result = await self.commit_reviews(
            mission_id,
            actor_user_id=actor_user_id,
            review_item_ids=review_item_ids,
            request_id=request_id,
        )
        target_mission_id = result.continuation_mission_id or mission_id
        refreshed = await self.dataservice.missions.get(target_mission_id)
        if refreshed is None:
            raise RuntimeError("MissionRun disappeared after commit request")
        return refreshed

    async def decide_reviews(
        self,
        mission_id: str,
        *,
        actor_user_id: str,
        decision_id: str,
        decisions: list[ReviewDecision],
    ) -> ReviewDecisionBatchOutcome:
        result = await self.review_commit.decide(
            mission_id,
            actor_user_id=actor_user_id,
            decision_id=decision_id,
            decisions=decisions,
        )
        rework = [outcome for outcome in result.outcomes if outcome.applied and outcome.action in {ReviewAction.NEEDS_MORE_EVIDENCE, ReviewAction.REGENERATE}]
        if not rework:
            return result
        reason = "needs_more_evidence" if any(outcome.action == ReviewAction.NEEDS_MORE_EVIDENCE for outcome in rework) else "regenerate"
        rationale = next(
            (decision.rationale for decision in decisions if decision.review_item_id in {outcome.review_item_id for outcome in rework} and decision.rationale),
            None,
        )
        continuation_id, error_code = await self._continue_review_work(
            mission_id,
            actor_user_id=actor_user_id,
            review_item_ids=tuple(outcome.review_item_id for outcome in rework),
            reason=reason,
            rationale=rationale,
            request_key=decision_id,
        )
        return result.model_copy(
            update={
                "continuation_mission_id": continuation_id,
                "continuation_error_code": error_code,
            }
        )

    async def commit_reviews(
        self,
        mission_id: str,
        *,
        actor_user_id: str,
        review_item_ids: tuple[str, ...] | list[str],
        request_id: str,
    ) -> CommitBatchOutcome:
        result = await self.review_commit.commit_many(
            mission_id,
            actor_user_id=actor_user_id,
            review_item_ids=list(review_item_ids),
        )
        failed_ids = {outcome.review_item_id for outcome in result.outcomes if not outcome.committed and outcome.reason_code}
        if not failed_ids:
            return result
        review_items = await self.dataservice.missions.list_review_items(mission_id)
        regenerate_ids = tuple(item.review_item_id for item in review_items if item.review_item_id in failed_ids and item.status.value == "superseded")
        if not regenerate_ids:
            return result
        continuation_id, error_code = await self._continue_review_work(
            mission_id,
            actor_user_id=actor_user_id,
            review_item_ids=regenerate_ids,
            reason="regenerate",
            rationale="The reviewed target or preview changed before it could be saved.",
            request_key=request_id,
        )
        return result.model_copy(
            update={
                "continuation_mission_id": continuation_id,
                "continuation_error_code": error_code,
            }
        )

    async def _continue_review_work(
        self,
        mission_id: str,
        *,
        actor_user_id: str,
        review_item_ids: tuple[str, ...],
        reason: str,
        rationale: str | None,
        request_key: str,
    ) -> tuple[str | None, str | None]:
        parent = await self.dataservice.missions.get(mission_id)
        if parent is None or parent.user_id != actor_user_id:
            return None, "mission_not_found"
        reset_stage_ids = await self._review_source_stage_ids(
            parent,
            review_item_ids=review_item_ids,
        )
        if not reset_stage_ids:
            return None, "review_source_stage_unavailable"
        if parent.status not in {
            MissionStatus.COMPLETED,
            MissionStatus.FAILED,
            MissionStatus.CANCELLED,
        }:
            command_id = _review_continuation_key(
                "review-command",
                mission_id,
                request_key,
            )
            await self.dataservice.missions.append_command(
                mission_id,
                MissionUserCommandPayload(
                    command_id=command_id,
                    command_type="review_feedback",
                    producer="review_commit_runtime",
                    summary=(rationale or "Continue from user review feedback")[:4000],
                    payload_json={
                        "reason": reason,
                        "review_item_ids": list(review_item_ids),
                        "reset_stage_ids": list(reset_stage_ids),
                        "rationale": rationale,
                    },
                ),
            )
            await self.runtime.wakeups.publish(
                mission_id,
                command_hint=command_id,
            )
            return None, None

        idempotency_key = _review_continuation_key(
            "review-continuation",
            mission_id,
            request_key,
        )
        title_prefix = "补充材料" if reason == "needs_more_evidence" else "重新生成"
        try:
            receipt = await self.runtime.start(
                MissionStartRequest(
                    workspace_id=parent.workspace_id,
                    thread_id=parent.thread_id,
                    user_id=parent.user_id,
                    workspace_type=parent.workspace_type,
                    title=f"{title_prefix}：{parent.title}"[:60],
                    objective=(f"Continue the parent objective after user review. Reason: {reason}. Feedback: {rationale or 'No additional rationale.'} Parent objective: {parent.objective}")[:20_000],
                    mission_idempotency_key=idempotency_key,
                    mission_policy_id=parent.mission_policy_id,
                    parent_mission_id=parent.mission_id,
                    continuation=MissionContinuationDirective(
                        reason=reason,
                        review_item_ids=review_item_ids,
                        reset_stage_ids=reset_stage_ids,
                        rationale=rationale,
                    ),
                    review_mode=parent.review_mode,
                    model_id=parent.model_id,
                    reasoning_effort=parent.reasoning_effort,
                    snapshot_json={
                        "intake": {
                            "review_feedback": rationale or reason,
                        }
                    },
                    runtime_context_json={
                        "policy_content_hash": parent.runtime_context_json.get("policy_content_hash"),
                        "model_capability_profile_hash": parent.runtime_context_json.get("model_capability_profile_hash"),
                    },
                )
            )
        except MissionStartRejectedError as exc:
            return None, exc.code.value
        except MissionProductionConfigurationError as exc:
            return None, exc.code.value
        return receipt.mission_id, None

    async def _review_source_stage_ids(
        self,
        parent: MissionRunPayload,
        *,
        review_item_ids: tuple[str, ...],
    ) -> tuple[str, ...]:
        accepted = parent.snapshot_json.get("stage_acceptance")
        passed_stage_ids = {str(stage_id) for stage_id, result in (accepted.items() if isinstance(accepted, dict) else ()) if isinstance(result, dict) and result.get("result") == "pass"}
        review_items = await self.dataservice.missions.list_review_items(parent.mission_id)
        by_id = {item.review_item_id: item for item in review_items}
        selected_items = [by_id.get(review_item_id) for review_item_id in review_item_ids]
        if any(item is None or item.source_item_seq is None for item in selected_items):
            return ()
        source_seqs = tuple(sorted({item.source_item_seq for item in selected_items if item is not None}))
        source_items = await self.dataservice.missions.list_items_by_seqs(
            parent.mission_id,
            seqs=source_seqs,
        )
        if {item.seq for item in source_items} != set(source_seqs):
            return ()
        if any(item.stage_id not in passed_stage_ids for item in source_items):
            return ()
        source_stage_ids = {str(item.stage_id) for item in source_items if item.stage_id in passed_stage_ids}
        return tuple(sorted(source_stage_ids))


def _review_continuation_key(prefix: str, mission_id: str, request_key: str) -> str:
    digest = hashlib.sha256(f"{prefix}:{mission_id}:{request_key}".encode()).hexdigest()
    return f"{prefix}:{digest}"


__all__ = [
    "CeleryMissionWakeupPublisher",
    "MissionRuntimeService",
    "build_mission_runtime",
]
