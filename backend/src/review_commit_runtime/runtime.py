"""Application runtime for atomic Mission review decisions and commits."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx

from src.contracts.review_policy import ReviewMode, project_review_policy
from src.dataservice_client.contracts.mission import (
    MissionCommitCreatePayload,
    MissionCommitFinishPayload,
    MissionCommitStartPayload,
    MissionCommitStatus,
    MissionReviewDecisionPayload,
    MissionReviewDecisionsPayload,
    MissionReviewDecisionStatus,
    MissionReviewItemPayload,
    MissionRunPayload,
)
from src.dataservice_client.errors import DataServiceClientError
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

    async def reconcile_auto_drafts(
        self,
        mission_id: str,
    ) -> CommitBatchOutcome:
        """Accept and materialize eligible draft-only candidates idempotently."""

        run = await self._missions.get(mission_id)
        if run is None or run.review_mode != ReviewMode.AUTO_DRAFT:
            return CommitBatchOutcome(outcomes=[])
        await self._membership.require_active_member(
            workspace_id=run.workspace_id,
            user_id=run.user_id,
        )
        items = await self._missions.list_review_items(mission_id)
        eligible = [
            item
            for item in items
            if item.status.value in {"pending", "accepted"}
            and project_review_policy(
                review_mode=run.review_mode,
                target_kind=item.target_kind,
                target_room=item.target_room,
                target_ref=item.target_ref,
                risk_level=item.risk_level.value,
            ).auto_draft_eligible
        ]
        accepted_review_item_ids: list[str] = []
        for item in eligible:
            if item.status.value == "pending":
                decision = await self._missions.apply_review_decisions(
                    mission_id,
                    MissionReviewDecisionsPayload(
                        decision_id=f"auto-draft:{item.review_item_id}",
                        expected_state_version=run.state_version,
                        actor_user_id=_AUTO_DRAFT_POLICY_ACTOR,
                        decisions=[
                            MissionReviewDecisionPayload(
                                review_item_id=item.review_item_id,
                                status=MissionReviewDecisionStatus.ACCEPTED,
                                decision_json={
                                    "action": ReviewAction.SAVE_DRAFT_ONLY.value,
                                    "policy": ReviewMode.AUTO_DRAFT.value,
                                    "reason": "eligible_low_risk_new_document",
                                },
                            )
                        ],
                    ),
                )
                run = decision.mission
            accepted_review_item_ids.append(item.review_item_id)
        if not accepted_review_item_ids:
            return CommitBatchOutcome(outcomes=[])
        return await self.commit_many(
            mission_id,
            actor_user_id=run.user_id,
            review_item_ids=accepted_review_item_ids,
        )

    async def decide(
        self,
        mission_id: str,
        *,
        actor_user_id: str,
        decision_id: str,
        decisions: list[ReviewDecision],
    ) -> ReviewDecisionBatchOutcome:
        review_item_ids = [decision.review_item_id for decision in decisions]
        if len(review_item_ids) != len(set(review_item_ids)):
            raise ValueError("duplicate_review_item_id")
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
            policy = project_review_policy(
                review_mode=run.review_mode,
                target_kind=item.target_kind,
                target_room=item.target_room,
                target_ref=item.target_ref,
                risk_level=item.risk_level.value,
            )
            if (
                len(decisions) > 1
                and decision.action == ReviewAction.ACCEPT
                and not policy.batch_acceptable
            ):
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
            if (
                decision.action == ReviewAction.SAVE_DRAFT_ONLY
                and not policy.auto_draft_eligible
            ):
                outcomes.append(
                    ReviewDecisionOutcome(
                        review_item_id=item.review_item_id,
                        action=decision.action,
                        applied=False,
                        status=item.status.value,
                        reason_code="draft_target_required",
                    )
                )
                continue
            allowed.append(decision)

        if allowed:
            result = await self._missions.apply_review_decisions(
                mission_id,
                MissionReviewDecisionsPayload(
                    decision_id=decision_id,
                    expected_state_version=run.state_version,
                    actor_user_id=actor_user_id,
                    decisions=[
                        MissionReviewDecisionPayload(
                            review_item_id=decision.review_item_id,
                            status=_durable_decision_status(decision.action),
                            decision_json={
                                "action": decision.action.value,
                                "rationale": decision.rationale,
                            },
                        )
                        for decision in allowed
                    ],
                ),
            )
            updated_by_id = {item.review_item_id: item for item in result.items}
            for decision in allowed:
                updated = updated_by_id[decision.review_item_id]
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
    ) -> CommitBatchOutcome:
        outcomes: list[CommitOutcome] = []
        for review_item_id in review_item_ids:
            try:
                outcome = await self.commit_one(
                    mission_id,
                    actor_user_id=actor_user_id,
                    review_item_id=review_item_id,
                    commit_key=_commit_key(review_item_id),
                )
            except Exception as exc:
                outcomes.append(
                    CommitOutcome(
                        review_item_id=review_item_id,
                        committed=False,
                        reason_code=_commit_error_code(exc),
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
        existing_result = await self._missions.get_commit_for_review_item(
            mission_id,
            review_item_id,
        )
        existing_commit = existing_result.commit if existing_result is not None else None
        if existing_commit is not None and existing_commit.status == MissionCommitStatus.COMMITTED:
            return CommitOutcome(
                review_item_id=review_item_id,
                commit=existing_commit,
                committed=True,
                reason_code="already_committed",
            )
        recovering_apply = bool(
            existing_commit is not None
            and existing_commit.status == MissionCommitStatus.APPLYING
        )
        try:
            item = await self._verified_preview(
                item,
                workspace_id=run.workspace_id,
                require_live_object=not recovering_apply,
            )
            if not recovering_apply:
                current = await self._target_writer.read_target(
                    item,
                    workspace_id=run.workspace_id,
                )
                _validate_base_precondition(
                    item,
                    current.revision_ref,
                    current.content_hash,
                )
        except Exception as exc:
            if _commit_error_code(exc) in _SUPERSEDE_ON_COMMIT_ERROR:
                await self._supersede_uncommittable(
                    run,
                    item,
                    actor_user_id=actor_user_id,
                    reason_code=_commit_error_code(exc),
                )
            raise

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
                mission_commit_attempt_token=attempt_token,
                actor_user_id=actor_user_id,
            )
            if not receipt.content_hash:
                raise _MaterializationOutcomeUnknown(
                    "materialization receipt requires content_hash"
                )
        except Exception as exc:
            if _materialization_outcome_is_unknown(exc):
                # Keep the fenced attempt in APPLYING. Its lease expiry makes a
                # later retry replay the same mission_commit_id idempotently,
                # allowing the target domain to return the durable receipt.
                raise
            failed = await self._missions.finish_commit(
                mission_id,
                commit.commit_id,
                MissionCommitFinishPayload(
                    attempt_token=attempt_token,
                    status=MissionCommitStatus.FAILED,
                    error_json={"code": type(exc).__name__},
                ),
            )
            if _commit_error_code(exc) in _SUPERSEDE_ON_COMMIT_ERROR:
                await self._supersede_uncommittable(
                    failed.mission,
                    item,
                    actor_user_id=actor_user_id,
                    reason_code=_commit_error_code(exc),
                )
            raise
        # Authorization is captured before the fenced domain write. Revocation
        # after that write must not prevent its durable MissionCommit receipt.
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

    async def _supersede_uncommittable(
        self,
        run: MissionRunPayload,
        item: MissionReviewItemPayload,
        *,
        actor_user_id: str,
        reason_code: str,
    ) -> None:
        current = await self._require_review_item(
            run.mission_id,
            item.review_item_id,
        )
        if current.status.value == "superseded":
            return
        if current.status.value != "accepted":
            return
        latest = await self._missions.get(run.mission_id)
        if latest is None:
            return
        await self._missions.apply_review_decisions(
            run.mission_id,
            MissionReviewDecisionsPayload(
                decision_id=(
                    f"commit-invalidated:{item.review_item_id}:{reason_code}"
                )[:160],
                expected_state_version=latest.state_version,
                actor_user_id=actor_user_id,
                decisions=[
                    MissionReviewDecisionPayload(
                        review_item_id=item.review_item_id,
                        status=MissionReviewDecisionStatus.SUPERSEDED,
                        decision_json={
                            "action": "regenerate",
                            "reason_code": reason_code,
                        },
                    )
                ],
            ),
        )

    async def _require_run(
        self,
        mission_id: str,
        *,
        actor_user_id: str,
    ) -> MissionRunPayload:
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
        require_live_object: bool = True,
    ) -> MissionReviewItemPayload:
        if (
            require_live_object
            and item.preview_expires_at is not None
            and item.preview_expires_at <= datetime.now(UTC)
        ):
            raise ValueError("review_preview_expired")
        preview = dict(item.preview_json)
        if item.preview_ref is not None and require_live_object:
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
    if action == ReviewAction.REGENERATE:
        return MissionReviewDecisionStatus.SUPERSEDED
    if action == ReviewAction.NEEDS_MORE_EVIDENCE:
        return MissionReviewDecisionStatus.NEEDS_MORE_EVIDENCE
    if action == ReviewAction.SAVE_DRAFT_ONLY:
        return MissionReviewDecisionStatus.ACCEPTED
    return MissionReviewDecisionStatus(action.value + "ed")


def _preview_hash(preview: dict[str, Any]) -> str:
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


def _commit_key(review_item_id: str) -> str:
    return f"mission-review-item:{review_item_id}"


_AUTO_DRAFT_POLICY_ACTOR = "policy:auto_draft"


_SUPERSEDE_ON_COMMIT_ERROR = frozenset(
    {
        "review_preview_expired",
        "review_preview_integrity_failed",
        "stale_target_precondition",
        "target_path_conflict",
    }
)


class _MaterializationOutcomeUnknown(RuntimeError):
    """The target may have committed even though no valid receipt arrived."""


def _materialization_outcome_is_unknown(exc: BaseException) -> bool:
    return (
        isinstance(exc, (httpx.TransportError, _MaterializationOutcomeUnknown))
        or isinstance(exc, DataServiceClientError)
        and exc.status_code is None
    )


def _commit_error_code(exc: BaseException) -> str:
    if _materialization_outcome_is_unknown(exc):
        return "materialization_outcome_unknown"
    detail = str(exc).strip()
    if detail and re.fullmatch(r"[a-z][a-z0-9_]{2,120}", detail):
        return detail
    return type(exc).__name__


__all__ = ["ReviewCommitRuntime"]
