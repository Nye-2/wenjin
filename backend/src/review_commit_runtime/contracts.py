"""Canonical contracts for atomic Mission review and commit operations."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from src.dataservice_client.contracts.mission import (
    MissionCommitPayload,
    MissionReviewItemPayload,
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReviewAction(StrEnum):
    ACCEPT = "accept"
    REJECT = "reject"
    NEEDS_MORE_EVIDENCE = "needs_more_evidence"
    REGENERATE = "regenerate"
    SAVE_DRAFT_ONLY = "save_draft_only"


class ReviewDecision(_StrictModel):
    review_item_id: str = Field(min_length=1, max_length=36)
    action: ReviewAction
    rationale: str | None = Field(default=None, max_length=4000)


class ReviewDecisionOutcome(_StrictModel):
    review_item_id: str
    action: ReviewAction
    applied: bool
    status: str
    reason_code: str | None = None


class ReviewDecisionBatchOutcome(_StrictModel):
    outcomes: list[ReviewDecisionOutcome]

    @property
    def partial(self) -> bool:
        return any(item.applied for item in self.outcomes) and any(not item.applied for item in self.outcomes)


class TargetSnapshot(_StrictModel):
    target_ref: str | None = None
    revision_ref: str | None = None
    content_hash: str | None = None


class MaterializationReceipt(_StrictModel):
    target_ref: str
    revision_ref: str | None = None
    content_hash: str
    manifest_ref: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)


class CommitOutcome(_StrictModel):
    review_item_id: str
    commit: MissionCommitPayload | None = None
    committed: bool
    reason_code: str | None = None


class CommitBatchOutcome(_StrictModel):
    outcomes: list[CommitOutcome]

    @property
    def partial(self) -> bool:
        return any(item.committed for item in self.outcomes) and any(not item.committed for item in self.outcomes)


class MissionTargetWriter(Protocol):
    """Domain writer with mandatory read-before-write semantics."""

    async def read_target(
        self,
        item: MissionReviewItemPayload,
        *,
        workspace_id: str,
    ) -> TargetSnapshot: ...

    async def apply(
        self,
        item: MissionReviewItemPayload,
        *,
        workspace_id: str,
        mission_commit_id: str,
        actor_user_id: str,
    ) -> MaterializationReceipt: ...


class PreviewObjectStore(Protocol):
    async def read(self, ref: str) -> dict[str, Any]: ...

    async def delete(self, ref: str) -> None: ...


__all__ = [
    "CommitBatchOutcome",
    "CommitOutcome",
    "MaterializationReceipt",
    "MissionTargetWriter",
    "PreviewObjectStore",
    "ReviewAction",
    "ReviewDecisionBatchOutcome",
    "ReviewDecision",
    "ReviewDecisionOutcome",
    "TargetSnapshot",
]
