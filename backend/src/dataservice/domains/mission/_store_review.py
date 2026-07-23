"""Mission review decisions and commit saga persistence."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta

from src.database.models.mission import (
    MissionReviewItemRecord,
    MissionRunRecord,
)
from src.dataservice.common.errors import (
    DataServiceConflictError,
    DataServiceNotFoundError,
    DataServiceValidationError,
)
from src.dataservice.domains.mission._store_core import (
    _REVIEW_TRANSITIONS,
    TERMINAL_MISSION_STATUSES,
    _aware,
    _canonical_preview,
    _commit_holds_review_preview,
    _decode_record_cursor,
    _encode_record_cursor,
    _review_materialization_destination,
)
from src.dataservice.domains.mission.chat_cards import MissionChatCardContext
from src.dataservice.domains.mission.projection import (
    mission_commit_to_payload,
    mission_review_item_to_payload,
    mission_run_to_payload,
)
from src.dataservice_client.contracts.mission import (
    MissionCommitCreatePayload,
    MissionCommitCreateResultPayload,
    MissionCommitFinishPayload,
    MissionCommitPagePayload,
    MissionCommitResultPayload,
    MissionCommitStartPayload,
    MissionCommitStatus,
    MissionCursorPagePayload,
    MissionDerivedReviewItemCreatePayload,
    MissionItemDraftPayload,
    MissionPreviewCleanupPayload,
    MissionPreviewCleanupResultPayload,
    MissionReviewDecisionsPayload,
    MissionReviewItemDraftPayload,
    MissionReviewItemPayload,
    MissionReviewItemsCreatePayload,
    MissionReviewItemsResultPayload,
    MissionReviewPagePayload,
    MissionRunPatchPayload,
)


class MissionReviewOperations:
    """Mission review decisions and commit saga persistence."""

    async def load_review_item(
        self,
        mission_id: str,
        review_item_id: str,
    ) -> MissionReviewItemPayload | None:
        run = await self.repository.get_run(mission_id)
        if run is None:
            return None
        record = await self.repository.get_review_item(review_item_id)
        if record is None or record.mission_id != mission_id:
            return None
        return mission_review_item_to_payload(record, review_mode=run.review_mode)

    async def load_commit_for_review_item(
        self,
        mission_id: str,
        review_item_id: str,
    ) -> MissionCommitResultPayload | None:
        run = await self.repository.get_run(mission_id)
        if run is None:
            return None
        commit = await self.repository.find_commit_by_review_item(
            mission_id=mission_id,
            review_item_id=review_item_id,
        )
        if commit is None:
            return None
        return MissionCommitResultPayload(
            mission=mission_run_to_payload(run),
            commit=mission_commit_to_payload(commit),
        )

    async def list_commits_page(
        self,
        mission_id: str,
        *,
        limit: int = 100,
        cursor: str | None = None,
    ) -> MissionCommitPagePayload:
        if await self.repository.get_run(mission_id) is None:
            raise DataServiceNotFoundError("MissionRun not found")
        after_created_at: datetime | None = None
        after_commit_id: str | None = None
        if cursor is not None:
            after_created_at, after_commit_id = _decode_record_cursor(
                cursor,
                kind="commit",
            )
        records = await self.repository.list_commits(
            mission_id=mission_id,
            after_created_at=after_created_at,
            after_commit_id=after_commit_id,
            limit=limit + 1,
        )
        page_records = records[:limit]
        next_cursor = None
        if len(records) > limit and page_records:
            last = page_records[-1]
            next_cursor = _encode_record_cursor(
                kind="commit",
                created_at=last.created_at,
                record_id=str(last.commit_id),
            )
        return MissionCommitPagePayload(
            items=[mission_commit_to_payload(record) for record in page_records],
            page=MissionCursorPagePayload(
                total=await self.repository.count_commits(mission_id=mission_id),
                returned=len(page_records),
                next_cursor=next_cursor,
            ),
        )

    async def create_review_items(
        self,
        mission_id: str,
        command: MissionReviewItemsCreatePayload,
    ) -> MissionReviewItemsResultPayload:
        run = await self._locked_run(mission_id)
        replay = await self._review_item_replay(
            run,
            mission_id=mission_id,
            drafts=command.review_items,
        )
        if replay is not None:
            return replay
        now = await self.repository.database_now()
        self._require_driver_fence(
            run,
            expected_state_version=command.expected_state_version,
            lease_owner=command.lease_owner,
            lease_epoch=command.lease_epoch,
            now=now,
        )
        return await self._create_new_review_items_locked(
            run,
            mission_id=mission_id,
            drafts=command.review_items,
            now=now,
            producer="mission_runtime",
            ledger_items=command.items,
            snapshot_json=command.snapshot_json,
            patch=command.patch,
        )

    async def create_derived_review_item(
        self,
        mission_id: str,
        command: MissionDerivedReviewItemCreatePayload,
    ) -> MissionReviewItemsResultPayload:
        """Stage one review item derived from a committed Mission output."""

        run = await self._locked_run(mission_id)
        source = await self.repository.get_review_item(
            command.source_review_item_id,
            for_update=True,
        )
        if (
            source is None
            or source.mission_id != mission_id
            or source.status != "committed"
            or source.target_kind != "workspace_asset"
        ):
            raise DataServiceConflictError(
                "Derived review items require a committed source review item"
            )
        source_commit = await self.repository.find_commit_by_review_item(
            mission_id=mission_id,
            review_item_id=source.review_item_id,
        )
        if source_commit is None or source_commit.status != "committed":
            raise DataServiceConflictError(
                "Derived review source has no committed materialization receipt"
            )
        commit_items = await self.repository.list_items_by_operation(
            mission_id=mission_id,
            operation_id=source_commit.commit_key,
            item_type="commit_completed",
        )
        if not commit_items:
            raise DataServiceConflictError(
                "Derived review source has no immutable commit receipt"
            )
        draft = command.item.model_copy(
            update={"source_item_seq": commit_items[-1].seq}
        )
        materialization = draft.preview_json.get("materialization")
        materialization_payload = (
            materialization.get("payload")
            if isinstance(materialization, dict)
            else None
        )
        committed_target_ref = str(
            dict(source_commit.targets_json or {}).get("target_ref") or ""
        )
        if (
            draft.target_kind != "prism_visual_insertion"
            or draft.target_room != "documents"
            or not draft.target_ref
            or not isinstance(materialization, dict)
            or materialization.get("operation") != "documents.insert_visual_asset"
            or not isinstance(materialization_payload, dict)
            or materialization_payload.get("asset_id") != committed_target_ref
            or materialization_payload.get("source_mission_commit_id")
            != source_commit.commit_id
        ):
            raise DataServiceValidationError(
                "Derived visual review items require one canonical Prism insertion target"
            )
        replay = await self._review_item_replay(
            run,
            mission_id=mission_id,
            drafts=(draft,),
        )
        if replay is not None:
            return replay
        self._require_state_version(run, command.expected_state_version)
        now = await self.repository.database_now()
        return await self._create_new_review_items_locked(
            run,
            mission_id=mission_id,
            drafts=(draft,),
            now=now,
            producer=command.actor_user_id,
        )

    async def _review_item_replay(
        self,
        run: MissionRunRecord,
        *,
        mission_id: str,
        drafts: Sequence[MissionReviewItemDraftPayload],
    ) -> MissionReviewItemsResultPayload | None:
        requested_ids = [item.review_item_id for item in drafts]
        if len(requested_ids) != len(set(requested_ids)):
            raise DataServiceValidationError("review_item_id values must be unique")
        output_keys = [item.output_key for item in drafts]
        if len(output_keys) != len(set(output_keys)):
            raise DataServiceValidationError("output_key values must be unique within one review batch")
        existing = await self.repository.list_review_items_by_ids(
            mission_id=mission_id,
            review_item_ids=requested_ids,
        )
        if existing:
            if len(existing) != len(requested_ids):
                raise DataServiceConflictError("Review-item retry mixed existing and new identifiers")
            existing_by_id = {item.review_item_id: item for item in existing}
            for draft in drafts:
                record = existing_by_id[draft.review_item_id]
                preview_json, preview_hash = _canonical_preview(draft)
                if (
                    record.source_item_seq != draft.source_item_seq
                    or record.output_key != draft.output_key
                    or record.target_kind != draft.target_kind
                    or record.target_room != draft.target_room
                    or record.target_ref != draft.target_ref
                    or record.base_revision_ref != draft.base_revision_ref
                    or record.base_hash != draft.base_hash
                    or record.title != draft.title
                    or record.summary != draft.summary
                    or record.risk_level != draft.risk_level.value
                    or record.review_required_reason != draft.review_required_reason
                    or dict(record.preview_json or {}) != preview_json
                    or record.preview_ref != draft.preview_ref
                    or record.preview_hash != preview_hash
                    or _aware(record.preview_expires_at) != _aware(draft.preview_expires_at)
                ):
                    raise DataServiceConflictError(
                        "review_item_id was reused with different candidate content",
                        detail={"review_item_id": draft.review_item_id},
                    )
            return MissionReviewItemsResultPayload(
                mission=mission_run_to_payload(run),
                items=[
                    mission_review_item_to_payload(
                        existing_by_id[item_id],
                        review_mode=run.review_mode,
                    )
                    for item_id in requested_ids
                ],
            )
        return None

    async def _create_new_review_items_locked(
        self,
        run: MissionRunRecord,
        *,
        mission_id: str,
        drafts: Sequence[MissionReviewItemDraftPayload],
        now: datetime,
        producer: str,
        ledger_items: Sequence[MissionItemDraftPayload] = (),
        snapshot_json: dict[str, object] | None = None,
        patch: MissionRunPatchPayload | None = None,
    ) -> MissionReviewItemsResultPayload:
        prepared_snapshot = (
            self._prepare_snapshot_replacement(run, snapshot_json)
            if snapshot_json is not None
            else None
        )
        output_keys = [item.output_key for item in drafts]
        candidate_destinations = {
            destination
            for draft in drafts
            if (
                destination := _review_materialization_destination(
                    target_kind=draft.target_kind,
                    target_room=draft.target_room,
                    target_ref=draft.target_ref,
                    preview_json=draft.preview_json,
                )
            )
            is not None
        }
        prior_candidates = await self.repository.list_review_items_for_replacement(
            mission_id=mission_id,
            output_keys=output_keys,
            destinations=list(candidate_destinations),
            for_update=True,
        )
        accepted_candidate_ids = [
            str(record.review_item_id)
            for record in prior_candidates
            if record.status == "accepted"
        ]
        active_commits = {
            str(commit.review_item_id): commit
            for commit in await self.repository.list_commits_by_review_item_ids(
                mission_id=mission_id,
                review_item_ids=accepted_candidate_ids,
            )
        }
        superseded_ids: list[str] = []
        superseded_pending = 0
        for record in prior_candidates:
            same_output = record.output_key in output_keys
            same_destination = (
                _review_materialization_destination(
                    target_kind=record.target_kind,
                    target_room=record.target_room,
                    target_ref=record.target_ref,
                    preview_json=dict(record.preview_json or {}),
                )
                in candidate_destinations
            )
            if not same_output and not same_destination:
                continue
            if record.status in {"committed", "superseded"}:
                continue
            if record.status == "accepted":
                active_commit = active_commits.get(str(record.review_item_id))
                if _commit_holds_review_preview(active_commit):
                    raise DataServiceConflictError(
                        "Cannot replace an output while its accepted candidate has a retryable save",
                        detail={
                            "review_item_id": record.review_item_id,
                            "commit_status": active_commit.status,
                        },
                    )
            if record.status == "pending":
                superseded_pending += 1
            record.status = "superseded"
            record.decision_json = {
                "decision": "superseded",
                "reason": "A newer candidate now represents this output.",
            }
            record.decided_by = None
            record.decided_at = now
            record.updated_at = now
            superseded_ids.append(str(record.review_item_id))
        records: list[MissionReviewItemRecord] = []
        audit_drafts: list[MissionItemDraftPayload] = []
        for review_item_id in superseded_ids:
            audit_drafts.append(
                MissionItemDraftPayload(
                    item_type="review_candidate_superseded",
                    operation_id=review_item_id,
                    phase="completed",
                    producer=producer,
                    summary="A newer candidate replaced this output.",
                    payload_json={"review_item_id": review_item_id},
                )
            )
        source_seqs = tuple(
            sorted(
                {
                    draft.source_item_seq
                    for draft in drafts
                    if draft.source_item_seq is not None
                }
            )
        )
        source_items = await self.repository.list_items_by_seqs(
            mission_id=mission_id,
            seqs=source_seqs,
        )
        if {record.seq for record in source_items} != set(source_seqs):
            raise DataServiceValidationError(
                "source_item_seq must reference the same mission ledger"
            )
        for draft in drafts:
            preview_json, preview_hash = _canonical_preview(draft)
            values = draft.model_dump(mode="python")
            values.update(
                {
                    "mission_id": mission_id,
                    "status": "pending",
                    "decision_json": None,
                    "decided_by": None,
                    "decided_at": None,
                    "created_at": now,
                    "updated_at": now,
                    "preview_json": preview_json,
                    "preview_hash": preview_hash,
                }
            )
            records.append(self.repository.create_review_item(values))
            audit_drafts.append(
                MissionItemDraftPayload(
                    item_type="review_candidate_created",
                    operation_id=draft.review_item_id,
                    phase="completed",
                    producer=producer,
                    summary=draft.title,
                    risk_level=draft.risk_level,
                    payload_json={
                        "review_item_id": draft.review_item_id,
                        "target_kind": draft.target_kind,
                        "target_room": draft.target_room,
                    },
                )
            )
        self._append_drafts(run, [*audit_drafts, *ledger_items], now=now)
        run.pending_review_count = max(
            run.pending_review_count - superseded_pending + len(records),
            0,
        )
        if prepared_snapshot is not None:
            self._install_prepared_snapshot(run, prepared_snapshot)
        if records:
            self._enqueue_chat_card(
                "review_request_created",
                MissionChatCardContext.from_run(run),
                {
                    "review_items": [
                        {
                            "review_item_id": str(record.review_item_id),
                            "title": str(record.title or ""),
                        }
                        for record in records
                    ],
                },
            )
        if patch is not None:
            self._apply_patch(run, patch, now=now)
        self._touch(run, now)
        await self._finish()
        return MissionReviewItemsResultPayload(
            mission=mission_run_to_payload(run),
            items=[
                mission_review_item_to_payload(item, review_mode=run.review_mode)
                for item in records
            ],
            superseded_review_item_ids=superseded_ids,
        )

    async def list_review_items(
        self,
        mission_id: str,
        *,
        status: list[str] | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> list[MissionReviewItemPayload]:
        page = await self.list_review_items_page(
            mission_id,
            status=status,
            limit=limit,
            cursor=cursor,
        )
        return page.items

    async def list_review_items_page(
        self,
        mission_id: str,
        *,
        status: list[str] | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> MissionReviewPagePayload:
        run = await self.repository.get_run(mission_id)
        if run is None:
            raise DataServiceNotFoundError("MissionRun not found")
        after_created_at: datetime | None = None
        after_review_item_id: str | None = None
        if cursor is not None:
            after_created_at, after_review_item_id = _decode_record_cursor(
                cursor,
                kind="review",
            )
        records = await self.repository.list_review_items(
            mission_id=mission_id,
            status=status,
            after_created_at=after_created_at,
            after_review_item_id=after_review_item_id,
            limit=limit + 1,
        )
        page_records = records[:limit]
        next_cursor = None
        if len(records) > limit and page_records:
            last = page_records[-1]
            next_cursor = _encode_record_cursor(
                kind="review",
                created_at=last.created_at,
                record_id=str(last.review_item_id),
            )
        return MissionReviewPagePayload(
            items=[
                mission_review_item_to_payload(record, review_mode=run.review_mode)
                for record in page_records
            ],
            page=MissionCursorPagePayload(
                total=await self.repository.count_review_items(
                    mission_id=mission_id,
                    status=status,
                ),
                returned=len(page_records),
                next_cursor=next_cursor,
            ),
        )

    async def apply_review_decisions(
        self,
        mission_id: str,
        command: MissionReviewDecisionsPayload,
    ) -> MissionReviewItemsResultPayload:
        run = await self._locked_run(mission_id)
        prior_audits = await self.repository.list_items_by_operation(
            mission_id=mission_id,
            operation_id=command.decision_id,
            item_type="review_decision_audit",
        )
        requested_ids = [decision.review_item_id for decision in command.decisions]
        if prior_audits:
            if any(audit.producer != command.actor_user_id for audit in prior_audits):
                raise DataServiceConflictError(
                    "decision_id was reused by a different actor",
                    detail={"decision_id": command.decision_id},
                )
            recorded_ids: set[str] = set()
            recorded_targets: dict[str, str] = {}
            recorded_decisions: dict[str, dict[str, object]] = {}
            for audit in prior_audits:
                payload = dict(audit.payload_json or {})
                review_item_id = payload.get("review_item_id")
                if review_item_id is not None:
                    item_id = str(review_item_id)
                    recorded_ids.add(item_id)
                    if payload.get("status_to") is not None:
                        recorded_targets[item_id] = str(payload["status_to"])
                    recorded_decisions[item_id] = dict(payload.get("decision_json") or {})
                for replayed in payload.get("decisions") or []:
                    item_id = str(replayed["review_item_id"])
                    recorded_ids.add(item_id)
                    recorded_targets[item_id] = str(replayed["status"])
                    recorded_decisions[item_id] = dict(replayed.get("decision_json") or {})
            requested_targets = {decision.review_item_id: decision.status.value for decision in command.decisions}
            requested_decisions = {decision.review_item_id: dict(decision.decision_json) for decision in command.decisions}
            if recorded_ids != set(requested_ids) or recorded_targets != requested_targets or recorded_decisions != requested_decisions:
                raise DataServiceConflictError(
                    "decision_id was reused with different review content",
                    detail={"decision_id": command.decision_id},
                )
            records = await self.repository.list_review_items_by_ids(mission_id=mission_id, review_item_ids=requested_ids)
            by_id = {record.review_item_id: record for record in records}
            return MissionReviewItemsResultPayload(
                mission=mission_run_to_payload(run),
                items=[
                    mission_review_item_to_payload(
                        by_id[item_id],
                        review_mode=run.review_mode,
                    )
                    for item_id in requested_ids
                ],
            )
        self._require_state_version(run, command.expected_state_version)
        records = await self.repository.list_review_items_by_ids(
            mission_id=mission_id,
            review_item_ids=requested_ids,
            for_update=True,
        )
        if len(records) != len(requested_ids):
            raise DataServiceNotFoundError("One or more MissionReviewItems do not belong to the mission")
        by_id = {record.review_item_id: record for record in records}
        accepted_review_ids = [
            str(record.review_item_id)
            for record in records
            if record.status == "accepted"
        ]
        active_commits = {
            str(commit.review_item_id): commit
            for commit in await self.repository.list_commits_by_review_item_ids(
                mission_id=mission_id,
                review_item_ids=accepted_review_ids,
            )
        }
        now = await self.repository.database_now()
        audit_drafts: list[MissionItemDraftPayload] = []
        for decision in command.decisions:
            record = by_id[decision.review_item_id]
            target = decision.status.value
            if target == record.status:
                continue
            if target not in _REVIEW_TRANSITIONS[record.status]:
                raise DataServiceConflictError(
                    "Invalid MissionReviewItem transition",
                    detail={
                        "review_item_id": record.review_item_id,
                        "from": record.status,
                        "to": target,
                    },
                )
            if record.status == "accepted":
                active_commit = active_commits.get(str(record.review_item_id))
                if active_commit is not None and active_commit.status == "applying":
                    raise DataServiceConflictError(
                        "Review item has an applying commit",
                        detail={"review_item_id": record.review_item_id},
                    )
            if record.status == "pending":
                run.pending_review_count -= 1
            previous = record.status
            record.status = target
            record.decision_json = {
                **dict(decision.decision_json),
                "decision_id": command.decision_id,
            }
            record.decided_by = command.actor_user_id
            record.decided_at = now
            record.updated_at = now
            audit_drafts.append(
                MissionItemDraftPayload(
                    item_type="review_decision_audit",
                    operation_id=command.decision_id,
                    phase="completed",
                    producer=command.actor_user_id,
                    summary=f"{previous} -> {target}",
                    risk_level=record.risk_level,
                    payload_json={
                        "review_item_id": record.review_item_id,
                        "status_from": previous,
                        "status_to": target,
                        "decision_json": decision.decision_json,
                    },
                )
            )
        if not audit_drafts:
            audit_drafts.append(
                MissionItemDraftPayload(
                    item_type="review_decision_audit",
                    operation_id=command.decision_id,
                    phase="completed",
                    producer=command.actor_user_id,
                    summary="Review decision was already reflected",
                    payload_json={
                        "decisions": [
                            {
                                "review_item_id": decision.review_item_id,
                                "status": decision.status.value,
                                "decision_json": decision.decision_json,
                            }
                            for decision in command.decisions
                        ]
                    },
                )
            )
        self._append_drafts(run, audit_drafts, now=now)
        revision_ids = [decision.review_item_id for decision in command.decisions if decision.status.value != "accepted"]
        for review_item_id in revision_ids:
            if self._resolve_review_wait(
                run,
                review_item_id=review_item_id,
                next_action="revise_current_stage",
                now=now,
            ):
                break
        if run.status not in TERMINAL_MISSION_STATUSES and revision_ids:
            run.next_wakeup_at = now
        self._touch(run, now)
        await self._finish()
        return MissionReviewItemsResultPayload(
            mission=mission_run_to_payload(run),
            items=[
                mission_review_item_to_payload(
                    by_id[item_id],
                    review_mode=run.review_mode,
                )
                for item_id in requested_ids
            ],
        )

    async def record_commit(
        self,
        mission_id: str,
        command: MissionCommitCreatePayload,
    ) -> MissionCommitCreateResultPayload:
        run = await self._locked_run(mission_id)
        existing_by_key = await self.repository.find_commit_by_key(mission_id=mission_id, commit_key=command.commit_key)
        existing_by_item = await self.repository.find_commit_by_review_item(
            mission_id=mission_id,
            review_item_id=command.review_item_id,
        )
        existing = existing_by_key or existing_by_item
        if existing is not None:
            if existing.mission_id != mission_id or existing.review_item_id != command.review_item_id or existing.commit_key != command.commit_key:
                raise DataServiceConflictError("Commit key or review item is already bound to another commit")
            return MissionCommitCreateResultPayload(
                mission=mission_run_to_payload(run),
                commit=mission_commit_to_payload(existing),
                created=False,
            )
        self._require_state_version(run, command.expected_state_version)
        review_item = await self.repository.get_review_item(command.review_item_id, for_update=True)
        if review_item is None or review_item.mission_id != mission_id:
            raise DataServiceNotFoundError("MissionReviewItem not found for mission")
        if review_item.status != "accepted":
            raise DataServiceConflictError(
                "Only an accepted MissionReviewItem can be committed",
                detail={
                    "review_item_id": command.review_item_id,
                    "status": review_item.status,
                },
            )
        now = await self.repository.database_now()
        commit = self.repository.create_commit(
            {
                "mission_id": mission_id,
                "review_item_id": command.review_item_id,
                "commit_key": command.commit_key,
                "status": "pending",
                "actor_user_id": command.actor_user_id,
                "targets_json": {},
                "error_json": None,
                "attempt_count": 0,
                "attempt_token": None,
                "attempt_started_at": None,
                "attempt_expires_at": None,
                "created_at": now,
                "completed_at": None,
            }
        )
        self._append_drafts(
            run,
            [
                MissionItemDraftPayload(
                    item_type="commit_started",
                    operation_id=command.commit_key,
                    phase="started",
                    producer=command.actor_user_id,
                    payload_json={
                        "commit_id": commit.commit_id,
                        "review_item_id": command.review_item_id,
                    },
                )
            ],
            now=now,
        )
        self._touch(run, now)
        await self._finish()
        return MissionCommitCreateResultPayload(
            mission=mission_run_to_payload(run),
            commit=mission_commit_to_payload(commit),
            created=True,
        )

    async def start_commit(
        self,
        mission_id: str,
        commit_id: str,
        command: MissionCommitStartPayload,
    ) -> MissionCommitResultPayload:
        run = await self._locked_run(mission_id)
        commit = await self.repository.get_commit(commit_id, for_update=True)
        if commit is None or commit.mission_id != mission_id:
            raise DataServiceNotFoundError("MissionCommit not found for mission")
        now = await self.repository.database_now()
        if commit.status == "applying":
            if commit.attempt_token == command.attempt_token:
                return MissionCommitResultPayload(
                    mission=mission_run_to_payload(run),
                    commit=mission_commit_to_payload(commit),
                )
            if commit.attempt_expires_at is not None and _aware(commit.attempt_expires_at) > _aware(now):
                raise DataServiceConflictError("MissionCommit is already applying")
        if commit.status in {"committed", "cancelled"}:
            raise DataServiceConflictError("Terminal MissionCommit cannot restart")
        if commit.status not in {"pending", "failed", "applying"}:
            raise DataServiceConflictError("MissionCommit is not startable")
        review_item = await self.repository.get_review_item(
            commit.review_item_id,
            for_update=True,
        )
        if review_item is None or review_item.mission_id != mission_id:
            raise DataServiceConflictError("MissionCommit lost its review item")
        if review_item.status != "accepted":
            raise DataServiceConflictError(
                "Only an accepted MissionReviewItem can start materialization",
                detail={
                    "review_item_id": review_item.review_item_id,
                    "status": review_item.status,
                },
            )
        commit.status = "applying"
        commit.attempt_count += 1
        commit.attempt_token = command.attempt_token
        commit.attempt_started_at = now
        commit.attempt_expires_at = now + timedelta(seconds=command.lease_seconds)
        commit.completed_at = None
        commit.error_json = None
        self._append_drafts(
            run,
            [
                MissionItemDraftPayload(
                    item_type="commit_started",
                    operation_id=commit.commit_key,
                    phase="progress",
                    producer=commit.actor_user_id,
                    payload_json={
                        "commit_id": commit.commit_id,
                        "attempt_count": commit.attempt_count,
                        "attempt_token": command.attempt_token,
                    },
                )
            ],
            now=now,
        )
        self._touch(run, now)
        await self._finish()
        return MissionCommitResultPayload(mission=mission_run_to_payload(run), commit=mission_commit_to_payload(commit))

    async def finish_commit(
        self,
        mission_id: str,
        commit_id: str,
        command: MissionCommitFinishPayload,
    ) -> MissionCommitResultPayload:
        run = await self._locked_run(mission_id)
        commit = await self.repository.get_commit(commit_id, for_update=True)
        if commit is None or commit.mission_id != mission_id:
            raise DataServiceNotFoundError("MissionCommit not found for mission")
        target_status = command.status.value
        if commit.status == target_status:
            expected_error = dict(command.error_json) if command.error_json is not None else None
            if commit.attempt_token != command.attempt_token or dict(commit.targets_json or {}) != dict(command.targets_json) or commit.error_json != expected_error:
                raise DataServiceConflictError("MissionCommit terminal replay does not match the stored receipt")
            return MissionCommitResultPayload(mission=mission_run_to_payload(run), commit=mission_commit_to_payload(commit))
        if commit.status != "applying":
            raise DataServiceConflictError("Only an applying MissionCommit can finish")
        if commit.attempt_token != command.attempt_token:
            raise DataServiceConflictError("MissionCommit attempt fence was lost")
        now = await self.repository.database_now()
        commit.status = target_status
        commit.targets_json = dict(command.targets_json)
        commit.error_json = dict(command.error_json) if command.error_json is not None else None
        commit.completed_at = now
        commit.attempt_expires_at = None
        if target_status == MissionCommitStatus.COMMITTED.value:
            review_item = await self.repository.get_review_item(commit.review_item_id, for_update=True)
            if review_item is None or review_item.mission_id != mission_id:
                raise DataServiceConflictError("MissionCommit lost its review item")
            if review_item.status != "accepted":
                raise DataServiceConflictError(
                    "Review item changed before commit completion",
                    detail={"review_item_id": review_item.review_item_id},
                )
            review_item.status = "committed"
            review_item.updated_at = now
            if run.status not in TERMINAL_MISSION_STATUSES:
                self._resolve_review_wait(
                    run,
                    review_item_id=review_item.review_item_id,
                    next_action="plan_or_replan",
                    now=now,
                )
                run.next_wakeup_at = now
        phase = {
            "committed": "completed",
            "failed": "failed",
            "cancelled": "cancelled",
        }[target_status]
        self._append_drafts(
            run,
            [
                MissionItemDraftPayload(
                    item_type="commit_completed",
                    operation_id=commit.commit_key,
                    phase=phase,
                    producer=commit.actor_user_id,
                    payload_json={
                        "commit_id": commit.commit_id,
                        "status": target_status,
                        "targets": command.targets_json,
                    },
                )
            ],
            now=now,
        )
        self._touch(run, now)
        await self._finish()
        return MissionCommitResultPayload(mission=mission_run_to_payload(run), commit=mission_commit_to_payload(commit))

    async def cleanup_expired_previews(
        self,
        command: MissionPreviewCleanupPayload,
    ) -> MissionPreviewCleanupResultPayload:
        mission_ids = await self.repository.list_mission_ids_with_expired_previews(
            now=command.now,
            limit=command.limit,
        )
        refs: list[str] = []
        review_item_ids: list[str] = []
        remaining = command.limit
        for mission_id in mission_ids:
            if remaining <= 0:
                break
            run = await self._locked_run(mission_id)
            records = await self.repository.list_expired_review_previews(
                mission_id=mission_id,
                now=command.now,
                limit=remaining,
                for_update=True,
            )
            commits = await self.repository.list_commits_by_review_item_ids(
                mission_id=mission_id,
                review_item_ids=[str(record.review_item_id) for record in records],
            )
            commits_by_review_item = {
                str(commit.review_item_id): commit for commit in commits
            }
            audit: list[MissionItemDraftPayload] = []
            changed = False
            for record in records:
                if remaining <= 0:
                    break
                expires_at = _aware(record.preview_expires_at)
                if (
                    expires_at is None
                    or expires_at > _aware(command.now)
                    or (record.preview_ref is None and not record.preview_json)
                ):
                    continue
                commit = commits_by_review_item.get(str(record.review_item_id))
                if _commit_holds_review_preview(commit):
                    continue
                remaining -= 1
                changed = True
                review_item_ids.append(str(record.review_item_id))
                if record.preview_ref:
                    refs.append(record.preview_ref)
                if record.status in {"pending", "accepted"}:
                    if record.status == "pending":
                        run.pending_review_count = max(
                            run.pending_review_count - 1,
                            0,
                        )
                    record.status = "superseded"
                    record.decision_json = {
                        "decision": "superseded",
                        "reason_code": "review_preview_expired",
                    }
                    record.decided_by = None
                    record.decided_at = command.now
                    audit.append(
                        MissionItemDraftPayload(
                            item_type="review_candidate_superseded",
                            operation_id=record.review_item_id,
                            phase="completed",
                            producer="preview_cleanup",
                            summary="Expired review preview was retired.",
                            payload_json={
                                "review_item_id": record.review_item_id,
                                "reason_code": "review_preview_expired",
                            },
                        )
                    )
                record.preview_json = {}
                record.preview_ref = None
                record.updated_at = command.now
            if changed:
                if audit:
                    self._append_drafts(run, audit, now=command.now)
                self._touch(run, command.now)
        await self._finish()
        return MissionPreviewCleanupResultPayload(
            review_item_ids=review_item_ids,
            preview_refs=refs,
        )

__all__ = ['MissionReviewOperations']
