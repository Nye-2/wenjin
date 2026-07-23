"""Coherent Mission history and user-facing read projections."""

from __future__ import annotations

from datetime import UTC, datetime

from src.dataservice.common.errors import (
    DataServiceNotFoundError,
)
from src.dataservice.domains.mission._store_core import (
    _MISSION_VIEW_READ_ATTEMPTS,
    _REVIEW_TRANSITIONS,
    NONTERMINAL_MISSION_STATUSES,
    MissionProjectionStaleError,
    _artifact_projection_revision,
    _decode_history_cursor,
    _decode_record_cursor,
    _encode_history_cursor,
    _encode_record_cursor,
    _project_activity,
    _project_artifact,
    _project_attention_request,
    _project_current_operation,
    _project_evidence,
    _project_failure,
    _project_input_summary,
    _project_quality_highlights,
    _project_review_view_item,
    _project_stages,
    _project_subagents,
    _review_projection_revision,
    _review_selection_revision,
)
from src.dataservice.domains.mission.projection import (
    mission_item_to_payload,
    mission_run_to_payload,
    mission_run_to_view_payload,
)
from src.dataservice_client.contracts.mission import (
    MissionArtifactPagePayload,
    MissionArtifactProjectionPagePayload,
    MissionChangeHintPayload,
    MissionCommitSummaryPayload,
    MissionEvidencePagePayload,
    MissionHistoryPagePayload,
    MissionItemPagePayload,
    MissionItemPayload,
    MissionProjectionPagePayload,
    MissionReviewPolicyPayload,
    MissionReviewProjectionPagePayload,
    MissionReviewSummaryPayload,
    MissionReviewViewPagePayload,
    MissionRunPayload,
    MissionStatus,
    MissionUserSummaryPayload,
    MissionViewPayload,
    MissionWorkspaceSummaryPayload,
)


class MissionQueryOperations:
    """Coherent Mission history and user-facing read projections."""

    async def load_run_snapshot(self, mission_id: str) -> MissionRunPayload | None:
        record = await self.repository.get_run(mission_id)
        return mission_run_to_payload(record) if record is not None else None

    async def foreground_for_thread(
        self,
        *,
        workspace_id: str,
        thread_id: str,
        user_id: str,
    ) -> MissionRunPayload | None:
        record = await self.repository.find_foreground_for_thread(thread_id)
        if record is None:
            return None
        if record.workspace_id != workspace_id or record.user_id != user_id:
            return None
        return mission_run_to_payload(record)

    async def latest_for_thread(
        self,
        *,
        workspace_id: str,
        thread_id: str,
        user_id: str,
    ) -> MissionRunPayload | None:
        record = await self.repository.find_latest_for_thread(thread_id)
        if record is None:
            return None
        if record.workspace_id != workspace_id or record.user_id != user_id:
            return None
        return mission_run_to_payload(record)

    async def find_by_mission_idempotency_key(
        self,
        *,
        workspace_id: str,
        mission_idempotency_key: str,
    ) -> MissionRunPayload | None:
        record = await self.repository.find_by_idempotency_key(
            workspace_id=workspace_id,
            mission_idempotency_key=mission_idempotency_key,
        )
        return mission_run_to_payload(record) if record is not None else None

    async def list_runs_summary(
        self,
        *,
        workspace_id: str,
        user_id: str | None = None,
        status: list[MissionStatus] | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> MissionHistoryPagePayload:
        before_updated_at, before_mission_id = _decode_history_cursor(cursor) if cursor else (None, None)
        records = await self.repository.list_runs(
            workspace_id=workspace_id,
            user_id=user_id,
            status=[item.value for item in status] if status else None,
            limit=limit + 1,
            before_updated_at=before_updated_at,
            before_mission_id=before_mission_id,
        )
        page_records = records[:limit]
        next_cursor = None
        if len(records) > limit and page_records:
            last = page_records[-1]
            next_cursor = _encode_history_cursor(
                updated_at=last.updated_at,
                mission_id=last.mission_id,
            )
        return MissionHistoryPagePayload(
            items=[mission_run_to_view_payload(record) for record in page_records],
            next_cursor=next_cursor,
        )

    async def list_runs_updated_after(
        self,
        *,
        workspace_id: str,
        user_id: str,
        updated_at: datetime,
        mission_id: str,
        limit: int = 100,
    ) -> list[MissionChangeHintPayload]:
        records = await self.repository.list_runs_updated_after(
            workspace_id=workspace_id,
            user_id=user_id,
            updated_at=updated_at,
            mission_id=mission_id,
            limit=limit,
        )
        return [
            MissionChangeHintPayload(
                mission_id=record.mission_id,
                workspace_id=record.workspace_id,
                user_id=record.user_id,
                state_version=record.state_version,
                last_item_seq=record.last_item_seq,
                updated_at=record.updated_at,
            )
            for record in records
        ]

    async def get_workspace_summary(
        self,
        *,
        workspace_id: str,
        user_id: str | None = None,
    ) -> MissionWorkspaceSummaryPayload:
        def version_token(records) -> tuple[datetime, str, int] | None:
            if not records:
                return None
            record = records[0]
            return (
                record.updated_at,
                str(record.mission_id),
                int(record.state_version),
            )

        for _attempt in range(_MISSION_VIEW_READ_ATTEMPTS):
            latest_before = await self.repository.list_runs(
                workspace_id=workspace_id,
                user_id=user_id,
                limit=1,
            )
            before_token = version_token(latest_before)
            rows = await self.repository.aggregate_workspace_runs(
                workspace_id=workspace_id,
                user_id=user_id,
            )
            active_records = await self.repository.list_runs(
                workspace_id=workspace_id,
                user_id=user_id,
                status=list(NONTERMINAL_MISSION_STATUSES),
                limit=1,
            )
            active_payload = (
                mission_run_to_view_payload(active_records[0])
                if active_records
                else None
            )
            # ORM identity caching must not hide a committed update between the
            # two fence reads.
            self.session.expire_all()
            latest_after = await self.repository.list_runs(
                workspace_id=workspace_id,
                user_id=user_id,
                limit=1,
            )
            if before_token == version_token(latest_after):
                status_counts = {
                    status: count for status, count, _, _, _ in rows
                }
                return MissionWorkspaceSummaryPayload(
                    total=sum(status_counts.values()),
                    status_counts=status_counts,
                    pending_review_count=sum(row[2] for row in rows),
                    evidence_count=sum(row[3] for row in rows),
                    artifact_count=sum(row[4] for row in rows),
                    latest=(
                        mission_run_to_view_payload(latest_after[0])
                        if latest_after
                        else None
                    ),
                    active=active_payload,
                )
            self.session.expire_all()
        raise MissionProjectionStaleError(
            "Mission workspace summary changed repeatedly while it was being read",
            detail={
                "workspace_id": workspace_id,
                "attempts": _MISSION_VIEW_READ_ATTEMPTS,
            },
        )

    async def get_user_summary(
        self,
        *,
        user_id: str,
        recent_limit: int = 10,
    ) -> MissionUserSummaryPayload:
        rows = await self.repository.aggregate_user_runs(user_id=user_id)
        recent_records = await self.repository.list_user_runs(
            user_id=user_id,
            limit=recent_limit,
        )
        status_counts = {status: count for status, count in rows}
        return MissionUserSummaryPayload(
            total=sum(status_counts.values()),
            status_counts=status_counts,
            recent=[mission_run_to_view_payload(record) for record in recent_records],
        )

    async def aggregate_stats(
        self,
        *,
        created_since: datetime,
        granularity: str,
    ):
        from src.dataservice_client.contracts.mission import (
            MissionStatsKpisPayload,
            MissionStatsPayload,
            MissionStatsTimePointPayload,
            MissionWorkspaceTypeCountPayload,
        )

        if granularity not in {"day", "week"}:
            raise ValueError("granularity must be day or week")
        rows = await self.repository.aggregate_stats(
            created_since=created_since,
            granularity=granularity,
        )
        by_date: dict[str, dict[str, dict[str, int]]] = {}
        by_workspace_type: dict[str, int] = {}
        by_status: dict[str, int] = {}
        for bucket, status, workspace_type, count in rows:
            date_key = bucket.date().isoformat()
            point = by_date.setdefault(date_key, {"by_type": {}, "by_status": {}})
            point["by_type"][workspace_type] = point["by_type"].get(workspace_type, 0) + count
            point["by_status"][status] = point["by_status"].get(status, 0) + count
            by_workspace_type[workspace_type] = by_workspace_type.get(workspace_type, 0) + count
            by_status[status] = by_status.get(status, 0) + count
        total = sum(by_status.values())
        success = by_status.get("completed", 0)
        failed = by_status.get("failed", 0) + by_status.get("cancelled", 0)
        return MissionStatsPayload(
            kpis=MissionStatsKpisPayload(
                total=total,
                success=success,
                failed=failed,
                success_rate=(success / total) if total else 0.0,
            ),
            time_series=[MissionStatsTimePointPayload(date=date, **counts) for date, counts in sorted(by_date.items())],
            by_workspace_type=[MissionWorkspaceTypeCountPayload(type=workspace_type, count=count) for workspace_type, count in sorted(by_workspace_type.items())],
        )

    async def list_items_page(
        self,
        mission_id: str,
        *,
        after_seq: int = 0,
        limit: int = 100,
        item_type: str | None = None,
        operation_id: str | None = None,
    ) -> list[MissionItemPayload]:
        page = await self.get_items_page(
            mission_id,
            after_seq=after_seq,
            limit=limit,
            item_type=item_type,
            operation_id=operation_id,
        )
        return page.items

    async def get_items_page(
        self,
        mission_id: str,
        *,
        after_seq: int = 0,
        limit: int = 100,
        item_type: str | None = None,
        operation_id: str | None = None,
    ) -> MissionItemPagePayload:
        if await self.repository.get_run(mission_id) is None:
            raise DataServiceNotFoundError("MissionRun not found")
        if operation_id is not None:
            records = await self.repository.list_items_by_operation(
                mission_id=mission_id,
                operation_id=operation_id,
                item_type=item_type,
                after_seq=after_seq,
                limit=limit + 1,
            )
        else:
            records = await self.repository.list_items(
                mission_id=mission_id,
                after_seq=after_seq,
                limit=limit + 1,
                item_type=item_type,
            )
        page_records = records[:limit]
        return MissionItemPagePayload(
            items=[mission_item_to_payload(record) for record in page_records],
            page=MissionProjectionPagePayload(
                total=await self.repository.count_items(
                    mission_id=mission_id,
                    item_type=item_type,
                    operation_id=operation_id,
                ),
                returned=len(page_records),
                next_cursor=(
                    page_records[-1].seq
                    if len(records) > limit and page_records
                    else None
                ),
            ),
        )

    async def list_items_by_seqs(
        self,
        mission_id: str,
        *,
        seqs: tuple[int, ...],
    ) -> list[MissionItemPayload]:
        if await self.repository.get_run(mission_id) is None:
            raise DataServiceNotFoundError("MissionRun not found")
        records = await self.repository.list_items_by_seqs(
            mission_id=mission_id,
            seqs=seqs,
        )
        return [mission_item_to_payload(record) for record in records]

    async def get_view(
        self,
        mission_id: str,
        *,
        projection_item_limit: int = 50,
    ) -> MissionViewPayload | None:
        last_start_version: int | None = None
        last_end_version: int | None = None
        for _attempt in range(_MISSION_VIEW_READ_ATTEMPTS):
            start_version = await self.repository.get_run_state_version(mission_id)
            if start_version is None:
                return None
            view = await self._project_view_once(
                mission_id,
                projection_item_limit=projection_item_limit,
            )
            if view is None:
                return None
            end_version = await self.repository.get_run_state_version(mission_id)
            if (
                start_version == end_version
                and view.mission.state_version == start_version
            ):
                return view
            last_start_version = start_version
            last_end_version = end_version
            self.session.expire_all()
        raise MissionProjectionStaleError(
            "Mission projection changed repeatedly while it was being read",
            detail={
                "mission_id": mission_id,
                "attempts": _MISSION_VIEW_READ_ATTEMPTS,
                "start_state_version": last_start_version,
                "end_state_version": last_end_version,
            },
        )

    async def _project_view_once(
        self,
        mission_id: str,
        *,
        projection_item_limit: int,
    ) -> MissionViewPayload | None:
        run = await self.repository.get_run(mission_id)
        if run is None:
            return None
        visible_review_page_records = await self.repository.list_current_review_items(
            mission_id=mission_id,
            limit=projection_item_limit + 1,
        )
        visible_review_records = visible_review_page_records[:projection_item_limit]
        artifact_records = await self.repository.list_current_artifact_review_items(
            mission_id=mission_id,
            limit=projection_item_limit + 1,
        )
        artifact_review_records = artifact_records[:projection_item_limit]
        review_status_counts = await self.repository.aggregate_current_review_statuses(
            mission_id=mission_id
        )
        commit_status_counts = await self.repository.aggregate_commit_statuses(
            mission_id=mission_id
        )
        projected_review_ids = {
            str(record.review_item_id)
            for record in [*visible_review_records, *artifact_review_records]
        }
        commit_records = await self.repository.list_commits_by_review_item_ids(
            mission_id=mission_id,
            review_item_ids=sorted(projected_review_ids),
        )
        evidence_records = await self.repository.list_unique_evidence_items(
            mission_id=mission_id,
            limit=projection_item_limit + 1,
        )
        pending_review_sources = await self.repository.list_items_by_seqs(
            mission_id=mission_id,
            seqs=tuple(record.source_item_seq for record in visible_review_records if record.status == "pending" and record.source_item_seq is not None),
        )
        inflight = (run.snapshot_json or {}).get("inflight_operation")
        active_subagent_operation_id: str | None = None
        if isinstance(inflight, dict) and inflight.get("kind") == "subagent":
            active_subagent_operation_id = (
                str(inflight.get("operation_id") or "") or None
            )
        activity_records, subagent_progress_records = (
            await self.repository.list_activity_with_subagent_projection(
                mission_id=mission_id,
                after_seq=max(0, run.last_item_seq - 100),
                activity_limit=100,
                operation_id=active_subagent_operation_id,
            )
        )
        inflight_seq = int(inflight.get("call_item_seq") or 0) if isinstance(inflight, dict) else 0
        if inflight_seq and all(record.seq != inflight_seq for record in activity_records):
            activity_records = [
                *(
                    await self.repository.list_items_by_seqs(
                        mission_id=mission_id,
                        seqs=(inflight_seq,),
                    )
                ),
                *activity_records,
            ]
        review_counts = {status: 0 for status in _REVIEW_TRANSITIONS}
        review_counts.update(dict(review_status_counts))
        commit_counts = {status: 0 for status in ("pending", "applying", "committed", "failed", "cancelled")}
        commit_counts.update(dict(commit_status_counts))
        evidence_page_records = evidence_records[:projection_item_limit]
        required_stage_ids, stage_summaries = _project_stages(
            run,
            observed_stage_ids=[record.stage_id for record in pending_review_sources if record.stage_id is not None],
        )
        passed_stage_count = sum(1 for stage in stage_summaries if stage.status == "passed")
        team_summary, subagents = _project_subagents(
            run,
            subagent_progress_records,
        )
        committed_review_ids = {record.review_item_id for record in commit_records if record.status == "committed"}
        commits_by_review_item = {
            str(record.review_item_id): record for record in commit_records
        }
        projection_now = datetime.now(UTC)
        review_revision_rows = (
            await self.repository.list_review_projection_revision_rows(
                mission_id=mission_id,
            )
        )
        review_revision = _review_projection_revision(
            review_revision_rows,
            review_mode=run.review_mode,
            now=projection_now,
        )
        artifact_revision_rows = (
            await self.repository.list_artifact_projection_revision_rows(
                mission_id=mission_id,
            )
        )
        visible_artifact_count = len(artifact_revision_rows)
        artifact_revision = _artifact_projection_revision(artifact_revision_rows)
        return MissionViewPayload(
            mission=mission_run_to_view_payload(run),
            activity=_project_activity(
                run,
                last_progress_at=(activity_records[-1].created_at if activity_records else run.started_at),
            ),
            current_operation=_project_current_operation(run, activity_records),
            input_summary=_project_input_summary(run),
            failure=_project_failure(
                run,
                passed_stages=passed_stage_count,
                visible_artifact_count=visible_artifact_count,
            ),
            attention_request=_project_attention_request(run),
            review_summary=MissionReviewSummaryPayload(**review_counts),
            commit_summary=MissionCommitSummaryPayload(**commit_counts),
            review_items=[
                _project_review_view_item(
                    record,
                    review_mode=run.review_mode,
                    commit=commits_by_review_item.get(str(record.review_item_id)),
                    now=projection_now,
                )
                for record in visible_review_records
            ],
            review_page=MissionReviewProjectionPagePayload(
                total=len(review_revision_rows),
                returned=len(visible_review_records),
                next_cursor=(
                    _encode_record_cursor(
                        kind="review-view",
                        created_at=visible_review_records[-1].created_at,
                        record_id=str(visible_review_records[-1].review_item_id),
                    )
                    if len(visible_review_page_records) > projection_item_limit
                    and visible_review_records
                    else None
                ),
                revision=review_revision,
            ),
            required_stage_ids=required_stage_ids,
            stage_summaries=stage_summaries,
            team_summary=team_summary,
            subagents=subagents,
            evidence_items=[_project_evidence(record) for record in evidence_page_records],
            evidence_page=MissionProjectionPagePayload(
                total=run.evidence_count,
                returned=len(evidence_page_records),
                next_cursor=(evidence_page_records[-1].seq if len(evidence_records) > projection_item_limit else None),
            ),
            artifact_items=[
                _project_artifact(
                    record,
                    committed_review_ids,
                    now=projection_now,
                )
                for record in artifact_review_records
            ],
            artifact_page=MissionArtifactProjectionPagePayload(
                total=visible_artifact_count,
                returned=len(artifact_review_records),
                next_cursor=(
                    artifact_review_records[-1].source_item_seq
                    if len(artifact_records) > projection_item_limit
                    else None
                ),
                next_tiebreaker=(
                    str(artifact_review_records[-1].review_item_id)
                    if len(artifact_records) > projection_item_limit
                    else None
                ),
                revision=artifact_revision,
            ),
            review_policy=MissionReviewPolicyPayload(
                mode=run.review_mode,
                protected_outputs_require_confirmation=True,
                draft_outputs_may_be_automatic=run.review_mode != "review_all",
            ),
            review_selection_revision=_review_selection_revision(
                review_revision_rows,
                review_mode=run.review_mode,
            ),
            quality_highlights=_project_quality_highlights(run),
            refresh_token=f"{run.updated_at.isoformat()}:{run.mission_id}:{run.state_version}",
        )

    async def list_evidence_projection_page(
        self,
        mission_id: str,
        *,
        after_seq: int = 0,
        limit: int = 50,
    ) -> MissionEvidencePagePayload | None:
        run = await self.repository.get_run(mission_id)
        if run is None:
            return None
        records = await self.repository.list_unique_evidence_items(
            mission_id=mission_id,
            after_seq=after_seq,
            limit=limit + 1,
        )
        page_records = records[:limit]
        return MissionEvidencePagePayload(
            items=[_project_evidence(record) for record in page_records],
            page=MissionProjectionPagePayload(
                total=run.evidence_count,
                returned=len(page_records),
                next_cursor=(page_records[-1].seq if len(records) > limit else None),
            ),
        )

    async def list_artifact_projection_page(
        self,
        mission_id: str,
        *,
        after_seq: int = 0,
        after_review_item_id: str = "",
        limit: int = 50,
    ) -> MissionArtifactPagePayload | None:
        last_start_version: int | None = None
        last_end_version: int | None = None
        for _attempt in range(_MISSION_VIEW_READ_ATTEMPTS):
            start_version = await self.repository.get_run_state_version(mission_id)
            if start_version is None:
                return None
            page = await self._list_artifact_projection_page_once(
                mission_id,
                after_seq=after_seq,
                after_review_item_id=after_review_item_id,
                limit=limit,
            )
            end_version = await self.repository.get_run_state_version(mission_id)
            if start_version == end_version:
                return page
            last_start_version = start_version
            last_end_version = end_version
            self.session.expire_all()
        raise MissionProjectionStaleError(
            "Mission artifact projection changed repeatedly while it was being read",
            detail={
                "mission_id": mission_id,
                "attempts": _MISSION_VIEW_READ_ATTEMPTS,
                "start_state_version": last_start_version,
                "end_state_version": last_end_version,
            },
        )

    async def _list_artifact_projection_page_once(
        self,
        mission_id: str,
        *,
        after_seq: int,
        after_review_item_id: str,
        limit: int,
    ) -> MissionArtifactPagePayload:
        artifact_records = await self.repository.list_current_artifact_review_items(
            mission_id=mission_id,
            after_seq=after_seq,
            after_review_item_id=after_review_item_id,
            limit=limit + 1,
        )
        page_records = artifact_records[:limit]
        commit_records = await self.repository.list_commits_by_review_item_ids(
            mission_id=mission_id,
            review_item_ids=[
                str(record.review_item_id) for record in page_records
            ],
        )
        committed_review_ids = {
            str(record.review_item_id)
            for record in commit_records
            if record.status == "committed"
        }
        projection_now = datetime.now(UTC)
        artifact_revision_rows = (
            await self.repository.list_artifact_projection_revision_rows(
                mission_id=mission_id,
            )
        )
        return MissionArtifactPagePayload(
            items=[
                _project_artifact(
                    record,
                    committed_review_ids,
                    now=projection_now,
                )
                for record in page_records
            ],
            page=MissionArtifactProjectionPagePayload(
                total=len(artifact_revision_rows),
                returned=len(page_records),
                next_cursor=(
                    page_records[-1].source_item_seq
                    if len(artifact_records) > limit and page_records
                    else None
                ),
                next_tiebreaker=(
                    str(page_records[-1].review_item_id)
                    if len(artifact_records) > limit and page_records
                    else None
                ),
                revision=_artifact_projection_revision(artifact_revision_rows),
            ),
        )

    async def list_review_projection_page(
        self,
        mission_id: str,
        *,
        cursor: str | None = None,
        limit: int = 50,
    ) -> MissionReviewViewPagePayload | None:
        last_start_version: int | None = None
        last_end_version: int | None = None
        for _attempt in range(_MISSION_VIEW_READ_ATTEMPTS):
            start_version = await self.repository.get_run_state_version(mission_id)
            if start_version is None:
                return None
            page = await self._list_review_projection_page_once(
                mission_id,
                cursor=cursor,
                limit=limit,
            )
            if page is None:
                return None
            end_version = await self.repository.get_run_state_version(mission_id)
            if start_version == end_version:
                return page
            last_start_version = start_version
            last_end_version = end_version
            self.session.expire_all()
        raise MissionProjectionStaleError(
            "Mission review projection changed repeatedly while it was being read",
            detail={
                "mission_id": mission_id,
                "attempts": _MISSION_VIEW_READ_ATTEMPTS,
                "start_state_version": last_start_version,
                "end_state_version": last_end_version,
            },
        )

    async def _list_review_projection_page_once(
        self,
        mission_id: str,
        *,
        cursor: str | None,
        limit: int,
    ) -> MissionReviewViewPagePayload | None:
        run = await self.repository.get_run(mission_id)
        if run is None:
            return None
        after_created_at: datetime | None = None
        after_review_item_id: str | None = None
        if cursor is not None:
            after_created_at, after_review_item_id = _decode_record_cursor(
                cursor,
                kind="review-view",
            )
        records = await self.repository.list_current_review_items(
            mission_id=mission_id,
            after_created_at=after_created_at,
            after_review_item_id=after_review_item_id,
            limit=limit + 1,
        )
        page_records = records[:limit]
        commits = await self.repository.list_commits_by_review_item_ids(
            mission_id=mission_id,
            review_item_ids=[str(record.review_item_id) for record in page_records],
        )
        commits_by_review_item = {
            str(record.review_item_id): record for record in commits
        }
        revision_rows = await self.repository.list_review_projection_revision_rows(
            mission_id=mission_id,
        )
        now = datetime.now(UTC)
        return MissionReviewViewPagePayload(
            items=[
                _project_review_view_item(
                    record,
                    review_mode=run.review_mode,
                    commit=commits_by_review_item.get(str(record.review_item_id)),
                    now=now,
                )
                for record in page_records
            ],
            page=MissionReviewProjectionPagePayload(
                total=len(revision_rows),
                returned=len(page_records),
                next_cursor=(
                    _encode_record_cursor(
                        kind="review-view",
                        created_at=page_records[-1].created_at,
                        record_id=str(page_records[-1].review_item_id),
                    )
                    if len(records) > limit and page_records
                    else None
                ),
                revision=_review_projection_revision(
                    revision_rows,
                    review_mode=run.review_mode,
                    now=now,
                ),
            ),
        )

__all__ = ['MissionQueryOperations']
