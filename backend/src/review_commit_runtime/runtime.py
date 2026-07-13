"""Application runtime for atomic Mission review decisions and commits."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from uuid import uuid4

from src.dataservice_client.contracts.mission import (
    MissionCommitCreatePayload,
    MissionCommitFinishPayload,
    MissionCommitStartPayload,
    MissionCommitStatus,
    MissionReviewDecisionPayload,
    MissionReviewDecisionsPayload,
    MissionReviewDecisionStatus,
    MissionReviewItemPayload,
)
from src.dataservice_client.mission_client import MissionDataServiceClient

from .contracts import (
    CommitBatchOutcome,
    CommitOutcome,
    MissionTargetWriter,
    PreviewObjectStore,
    ReviewAction,
    ReviewDecision,
    ReviewDecisionBatchOutcome,
    ReviewDecisionOutcome,
)
from .membership import MembershipAuthorizer, require_owned_mission
from .policy import may_bulk_accept


class ReviewCommitRuntime:
    """Coordinates policy, durable decisions, domain writes, and commit audit."""

    def __init__(
        self,
        *,
        missions: MissionDataServiceClient,
        target_writer: MissionTargetWriter,
        membership: MembershipAuthorizer,
        preview_store: PreviewObjectStore | None = None,
    ) -> None:
        self._missions = missions
        self._target_writer = target_writer
        self._membership = membership
        self._preview_store = preview_store

    async def decide(
        self,
        mission_id: str,
        *,
        actor_user_id: str,
        decision_id: str,
        decisions: list[ReviewDecision],
        bulk: bool = False,
    ) -> ReviewDecisionBatchOutcome:
        run = await self._require_run(mission_id, actor_user_id=actor_user_id)
        items = await self._missions.list_review_items(mission_id)
        by_id = {item.review_item_id: item for item in items}
        outcomes: list[ReviewDecisionOutcome] = []
        allowed: list[ReviewDecision] = []
        for decision in decisions:
            item = by_id.get(decision.review_item_id)
            if item is None:
                outcomes.append(
                    ReviewDecisionOutcome(
                        review_item_id=decision.review_item_id,
                        action=decision.action,
                        applied=False,
                        status="missing",
                        reason_code="review_item_not_found",
                    )
                )
                continue
            if bulk and decision.action == ReviewAction.ACCEPT and not may_bulk_accept(item):
                outcomes.append(
                    ReviewDecisionOutcome(
                        review_item_id=item.review_item_id,
                        action=decision.action,
                        applied=False,
                        status=item.status.value,
                        reason_code="explicit_review_required",
                    )
                )
                continue
            allowed.append(decision)

        for index, decision in enumerate(allowed):
            durable_status = _durable_decision_status(decision.action)
            result = await self._missions.apply_review_decisions(
                mission_id,
                MissionReviewDecisionsPayload(
                    decision_id=f"{decision_id}:{index}",
                    expected_state_version=run.state_version,
                    actor_user_id=actor_user_id,
                    decisions=[
                        MissionReviewDecisionPayload(
                            review_item_id=decision.review_item_id,
                            status=durable_status,
                            decision_json={
                                "action": decision.action.value,
                                "rationale": decision.rationale,
                            },
                        )
                    ],
                ),
            )
            run = result.mission
            updated = result.items[0]
            outcomes.append(
                ReviewDecisionOutcome(
                    review_item_id=updated.review_item_id,
                    action=decision.action,
                    applied=True,
                    status=updated.status.value,
                )
            )
        order = {item.review_item_id: index for index, item in enumerate(decisions)}
        outcomes.sort(key=lambda item: order.get(item.review_item_id, len(order)))
        return ReviewDecisionBatchOutcome(outcomes=outcomes)

    async def commit_many(
        self,
        mission_id: str,
        *,
        actor_user_id: str,
        review_item_ids: list[str],
        request_id: str,
    ) -> CommitBatchOutcome:
        outcomes: list[CommitOutcome] = []
        for review_item_id in review_item_ids:
            try:
                outcome = await self.commit_one(
                    mission_id,
                    actor_user_id=actor_user_id,
                    review_item_id=review_item_id,
                    commit_key=_commit_key(request_id, review_item_id),
                )
            except Exception as exc:
                outcomes.append(
                    CommitOutcome(
                        review_item_id=review_item_id,
                        committed=False,
                        reason_code=type(exc).__name__,
                    )
                )
            else:
                outcomes.append(outcome)
        return CommitBatchOutcome(outcomes=outcomes)

    async def commit_one(
        self,
        mission_id: str,
        *,
        actor_user_id: str,
        review_item_id: str,
        commit_key: str,
    ) -> CommitOutcome:
        run = await self._require_run(mission_id, actor_user_id=actor_user_id)
        item = await self._require_review_item(mission_id, review_item_id)
        if item.status.value == "committed":
            return CommitOutcome(
                review_item_id=review_item_id,
                committed=True,
                reason_code="already_committed",
            )
        if item.status.value != "accepted":
            return CommitOutcome(
                review_item_id=review_item_id,
                committed=False,
                reason_code="review_item_not_accepted",
            )
        item = await self._verified_preview(item, workspace_id=run.workspace_id)
        current = await self._target_writer.read_target(item, workspace_id=run.workspace_id)
        _validate_base_precondition(item, current.revision_ref, current.content_hash)

        created = await self._missions.commit(
            mission_id,
            MissionCommitCreatePayload(
                expected_state_version=run.state_version,
                review_item_id=review_item_id,
                commit_key=commit_key,
                actor_user_id=actor_user_id,
            ),
        )
        commit = created.commit
        if commit.status == MissionCommitStatus.COMMITTED:
            return CommitOutcome(review_item_id=review_item_id, commit=commit, committed=True)

        run = created.mission
        attempt_token = str(uuid4())
        await self._missions.start_commit(
            mission_id,
            commit.commit_id,
            MissionCommitStartPayload(attempt_token=attempt_token),
        )
        try:
            await self._membership.require_active_member(
                workspace_id=run.workspace_id,
                user_id=actor_user_id,
            )
            receipt = await self._target_writer.apply(
                item,
                workspace_id=run.workspace_id,
                mission_commit_id=commit.commit_id,
                actor_user_id=actor_user_id,
            )
            if not receipt.content_hash:
                raise ValueError("materialization receipt requires content_hash")
        except Exception as exc:
            await self._missions.finish_commit(
                mission_id,
                commit.commit_id,
                MissionCommitFinishPayload(
                    attempt_token=attempt_token,
                    status=MissionCommitStatus.FAILED,
                    error_json={"code": type(exc).__name__},
                ),
            )
            raise
        # A successful external write stays "applying" if authorization or the
        # final database write becomes unavailable. A later fenced retry reads
        # the target by mission_commit_id and completes without duplicating it.
        await self._membership.require_active_member(
            workspace_id=run.workspace_id,
            user_id=actor_user_id,
        )
        finished = await self._missions.finish_commit(
            mission_id,
            commit.commit_id,
            MissionCommitFinishPayload(
                attempt_token=attempt_token,
                status=MissionCommitStatus.COMMITTED,
                targets_json=receipt.model_dump(mode="json"),
            ),
        )
        if item.preview_ref and self._preview_store is not None:
            await self._preview_store.delete(item.preview_ref, workspace_id=run.workspace_id)
        return CommitOutcome(
            review_item_id=review_item_id,
            commit=finished.commit,
            committed=True,
        )

    async def _require_run(self, mission_id: str, *, actor_user_id: str):
        return await require_owned_mission(
            self._missions,
            self._membership,
            mission_id=mission_id,
            actor_user_id=actor_user_id,
        )

    async def _require_review_item(self, mission_id: str, review_item_id: str) -> MissionReviewItemPayload:
        items = await self._missions.list_review_items(mission_id)
        item = next((value for value in items if value.review_item_id == review_item_id), None)
        if item is None:
            raise LookupError("MissionReviewItem not found")
        return item

    async def _verified_preview(
        self,
        item: MissionReviewItemPayload,
        *,
        workspace_id: str,
    ) -> MissionReviewItemPayload:
        if item.preview_expires_at is not None and item.preview_expires_at <= datetime.now(UTC):
            raise ValueError("review_preview_expired")
        preview = dict(item.preview_json)
        if item.preview_ref is not None:
            if self._preview_store is None:
                raise ValueError("review_preview_store_unavailable")
            stored = await self._preview_store.read(item.preview_ref, workspace_id=workspace_id)
            descriptor = dict(preview.get("materialization") or {})
            payload = dict(descriptor.get("payload") or {})
            expected_hash = str(payload.get("content_hash") or "")
            if expected_hash and not hmac.compare_digest(expected_hash, stored.descriptor.content_hash):
                raise ValueError("review_preview_integrity_failed")
            expected_mime = str(payload.get("mime_type") or "")
            if expected_mime and expected_mime != stored.descriptor.mime_type:
                raise ValueError("review_preview_content_type_mismatch")
        if not preview or not item.preview_hash:
            raise ValueError("review_preview_hash_required")
        actual_hash = _preview_hash(preview)
        if not hmac.compare_digest(actual_hash, item.preview_hash):
            raise ValueError("review_preview_integrity_failed")
        return item


def _durable_decision_status(action: ReviewAction) -> MissionReviewDecisionStatus:
    if action in {ReviewAction.REGENERATE, ReviewAction.NEEDS_MORE_EVIDENCE}:
        return MissionReviewDecisionStatus.NEEDS_MORE_EVIDENCE
    if action == ReviewAction.SAVE_DRAFT_ONLY:
        return MissionReviewDecisionStatus.ACCEPTED
    return MissionReviewDecisionStatus(action.value + "ed")


def _preview_hash(preview: dict) -> str:
    encoded = json.dumps(
        preview,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_base_precondition(
    item: MissionReviewItemPayload,
    current_revision_ref: str | None,
    current_hash: str | None,
) -> None:
    if item.target_ref is None:
        return
    if not item.base_revision_ref or not item.base_hash:
        raise ValueError("existing_target_requires_base_precondition")
    if item.base_revision_ref != current_revision_ref or item.base_hash != current_hash:
        raise ValueError("stale_target_precondition")


def _commit_key(request_id: str, review_item_id: str) -> str:
    digest = hashlib.sha256(f"{request_id}:{review_item_id}".encode()).hexdigest()[:32]
    return f"mission-commit:{digest}"


__all__ = ["ReviewCommitRuntime"]
