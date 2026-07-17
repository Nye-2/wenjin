"""Dependency ports owned by MissionRuntime composition roots."""

from __future__ import annotations

from datetime import UTC, datetime
from time import monotonic
from typing import Protocol

from src.dataservice_client.contracts.mission import (
    MissionAppendPayload,
    MissionAppendResultPayload,
    MissionApplyCommandsPayload,
    MissionCreatePayload,
    MissionCreateResultPayload,
    MissionDispatchReleasePayload,
    MissionItemPayload,
    MissionLeaseClaimPayload,
    MissionLeaseHeartbeatPayload,
    MissionLeaseReleasePayload,
    MissionModelCallStatePayload,
    MissionOperationClaimPayload,
    MissionOperationClaimResultPayload,
    MissionOperationFinishPayload,
    MissionOperationFinishResultPayload,
    MissionOperationReceiptPayload,
    MissionResumePayload,
    MissionReviewItemPayload,
    MissionReviewItemsCreatePayload,
    MissionReviewItemsResultPayload,
    MissionRunnableBatchClaimPayload,
    MissionRunPayload,
    MissionUserCommandPayload,
)
from src.mission_runtime.contracts import (
    MissionAgentDecision,
    MissionEventEnvelope,
    MissionLoopContext,
    MissionPortOutcome,
    MissionStartRequest,
    ReviewCandidateBatch,
    ReviewCandidateRequest,
    StageQualityOutcome,
    StageQualityRequest,
    SubagentExecutionRequest,
    ToolExecutionRequest,
)


class MissionStorePort(Protocol):
    async def admit(self, command: MissionCreatePayload) -> MissionCreateResultPayload: ...

    async def get(self, mission_id: str) -> MissionRunPayload | None: ...

    async def claim_lease(self, mission_id: str, command: MissionLeaseClaimPayload) -> MissionRunPayload: ...

    async def heartbeat_lease(self, mission_id: str, command: MissionLeaseHeartbeatPayload) -> MissionRunPayload: ...

    async def release_lease(self, mission_id: str, command: MissionLeaseReleasePayload) -> MissionRunPayload: ...

    async def claim_runnable(self, command: MissionRunnableBatchClaimPayload) -> list[MissionRunPayload]: ...

    async def release_dispatch(self, mission_id: str, command: MissionDispatchReleasePayload) -> MissionRunPayload: ...

    async def claim_operation(self, mission_id: str, command: MissionOperationClaimPayload) -> MissionOperationClaimResultPayload: ...

    async def get_operation(self, mission_id: str, operation_key: str) -> MissionOperationReceiptPayload | None: ...

    async def finish_operation(self, mission_id: str, command: MissionOperationFinishPayload) -> MissionOperationFinishResultPayload: ...

    async def append_items(self, mission_id: str, command: MissionAppendPayload) -> MissionAppendResultPayload: ...

    async def append_command(self, mission_id: str, command: MissionUserCommandPayload) -> MissionAppendResultPayload: ...

    async def list_items(self, mission_id: str, *, after_seq: int = 0, limit: int = 100, item_type: str | None = None, operation_id: str | None = None) -> list[MissionItemPayload]: ...

    async def list_model_call_states(
        self,
        mission_id: str,
    ) -> list[MissionModelCallStatePayload]: ...

    async def list_unapplied_commands(self, mission_id: str, *, limit: int = 100) -> list[MissionItemPayload]: ...

    async def apply_commands(self, mission_id: str, command: MissionApplyCommandsPayload) -> MissionAppendResultPayload: ...

    async def resume(self, mission_id: str, command: MissionResumePayload) -> MissionAppendResultPayload: ...

    async def create_review_items(self, mission_id: str, command: MissionReviewItemsCreatePayload) -> MissionReviewItemsResultPayload: ...

    async def list_review_items(
        self,
        mission_id: str,
        *,
        status: list[str] | None = None,
    ) -> list[MissionReviewItemPayload]: ...


class MissionAgentPort(Protocol):
    async def decide(self, context: MissionLoopContext) -> MissionAgentDecision: ...


class MissionStartContextPort(Protocol):
    async def pin(self, request: MissionStartRequest) -> MissionStartRequest: ...


class ToolOrchestratorPort(Protocol):
    async def execute(self, request: ToolExecutionRequest) -> MissionPortOutcome: ...


class SubagentRuntimePort(Protocol):
    async def run(self, request: SubagentExecutionRequest) -> MissionPortOutcome: ...

    async def adopt_terminal(
        self,
        request: SubagentExecutionRequest,
    ) -> MissionPortOutcome | None: ...


class StageQualityPort(Protocol):
    async def can_start(
        self,
        mission: MissionRunPayload,
        stage_id: str,
    ) -> tuple[bool, tuple[str, ...]]: ...

    async def evaluate(self, request: StageQualityRequest) -> StageQualityOutcome: ...


class ReviewCandidatePort(Protocol):
    async def build_candidates(self, request: ReviewCandidateRequest) -> ReviewCandidateBatch: ...


class MissionEventPublisherPort(Protocol):
    async def publish(self, event: MissionEventEnvelope) -> None: ...


class MissionWakeupPublisherPort(Protocol):
    async def publish(
        self,
        mission_id: str,
        *,
        command_hint: str | None = None,
        delay_seconds: int = 0,
    ) -> None: ...


class MissionClockPort(Protocol):
    def monotonic(self) -> float: ...

    def now(self) -> datetime: ...


class SystemMissionClock:
    def monotonic(self) -> float:
        return monotonic()

    def now(self) -> datetime:
        return datetime.now(UTC)


__all__ = [
    "MissionAgentPort",
    "MissionClockPort",
    "MissionEventPublisherPort",
    "MissionStorePort",
    "MissionStartContextPort",
    "MissionWakeupPublisherPort",
    "ReviewCandidatePort",
    "StageQualityPort",
    "SubagentRuntimePort",
    "SystemMissionClock",
    "ToolOrchestratorPort",
]
