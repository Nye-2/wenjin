"""Execution aggregate command/query service."""

from __future__ import annotations

from contextlib import suppress
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.billing.reservation_metadata import reservation_id_from_params
from src.dataservice.domains.credit.service import DataServiceCreditService
from src.dataservice.domains.execution.contracts import (
    EXECUTION_COMMIT_FINALIZE_DELETABLE_RESULT_KEYS,
    ComputeSessionEnsureCommand,
    ComputeSessionProjection,
    ComputeSessionUpdateCommand,
    ExecutionCommitClaimCommand,
    ExecutionCommitFailCommand,
    ExecutionCommitFinalizeCommand,
    ExecutionCommitResetCommand,
    ExecutionCreateCommand,
    ExecutionEventCreateCommand,
    ExecutionEventProjection,
    ExecutionLeaseClaimCommand,
    ExecutionLeaseHeartbeatCommand,
    ExecutionNodePatchCommand,
    ExecutionNodeProjection,
    ExecutionNodeUpsertCommand,
    ExecutionRecordProjection,
    ExecutionResultPatchCommand,
    ExecutionRunHistoryProjection,
    ExecutionUpdateCommand,
    GenerationRecordCreateCommand,
    GenerationRecordProjection,
)
from src.dataservice.domains.execution.projection import (
    compute_session_to_projection,
    event_to_projection,
    execution_to_projection,
    execution_to_run_history_projection,
    generation_record_to_projection,
    node_to_projection,
)
from src.dataservice.domains.execution.repository import ExecutionRepository

_COMMIT_CLAIM_LEASE = timedelta(minutes=30)
_COMMIT_COUNT_ROOM_KEYS = ("library", "prism", "memory", "decisions", "tasks", "sandbox", "settings")
_COMMIT_ROOM_TARGET_KEYS = ("library", "prism", "memory", "decisions", "tasks", "sandbox", "settings")
_EXECUTION_IN_FLIGHT_STATUSES = ("pending", "running", "cancelling")
_EXECUTION_LEASE_ACTIVE_STATUSES = {"pending", "running"}
_EXECUTION_LEASE_KEY = "execution_lease"


class DataServiceExecutionService:
    """DataService-owned execution operations."""

    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self.session = session
        self.autocommit = autocommit
        self.repository = ExecutionRepository(session)

    async def create_execution(self, command: ExecutionCreateCommand) -> ExecutionRecordProjection:
        now = datetime.now(UTC)
        record = self.repository.create_execution(
            {
                "user_id": command.user_id,
                "workspace_id": command.workspace_id,
                "thread_id": command.thread_id,
                "execution_type": command.execution_type,
                "feature_id": command.capability_id,
                "entry_skill_id": command.entry_skill_id,
                "workspace_type": command.workspace_type,
                "display_name": command.display_name,
                "status": "pending",
                "params": dict(command.task_brief_json or {}),
                "node_states": {},
                "progress": 0,
                "artifact_ids": [],
                "next_actions": [],
                "child_execution_ids": [],
                "parent_execution_id": command.parent_execution_id,
                "created_at": now,
                "updated_at": now,
            }
        )
        await self._finish()
        return execution_to_projection(record)

    async def get_execution(self, execution_id: str) -> ExecutionRecordProjection | None:
        record = await self.repository.get_execution(execution_id)
        return execution_to_projection(record) if record else None

    async def list_executions(
        self,
        *,
        user_id: str | None = None,
        workspace_id: str | None = None,
        thread_id: str | None = None,
        execution_type: str | None = None,
        status: list[str] | None = None,
        limit: int = 50,
    ) -> list[ExecutionRecordProjection]:
        return [
            execution_to_projection(record)
            for record in await self.repository.list_executions(
                user_id=user_id,
                workspace_id=workspace_id,
                thread_id=thread_id,
                execution_type=execution_type,
                status=status,
                limit=limit,
            )
        ]

    async def count_executions(
        self,
        *,
        user_id: str | None = None,
        status: list[str] | None = None,
        created_since: datetime | None = None,
    ) -> int:
        return await self.repository.count_executions(
            user_id=user_id,
            status=status,
            created_since=created_since,
        )

    async def count_executions_by_status(
        self,
        *,
        user_id: str | None = None,
    ) -> dict[str, int]:
        return await self.repository.count_executions_by_status(user_id=user_id)

    async def count_executions_by_user_ids(
        self,
        user_ids: list[str],
    ) -> dict[str, int]:
        return await self.repository.count_executions_by_user_ids(user_ids)

    async def count_active_execution_users(self, *, created_since: datetime) -> int:
        return await self.repository.count_distinct_execution_users(
            created_since=created_since,
        )

    async def aggregate_execution_stats(
        self,
        *,
        created_since: datetime,
        granularity: str,
    ) -> dict[str, Any]:
        rows = await self.repository.list_execution_stat_buckets(
            created_since=created_since,
            granularity=granularity,
        )
        series_map: dict[str, dict[str, Any]] = {}
        for row in rows:
            bucket = row.bucket.isoformat()
            workspace_type = row.workspace_type or "unknown"
            status = row.status or "unknown"
            series_map.setdefault(bucket, {"date": bucket, "by_type": {}, "by_status": {}})
            series_map[bucket]["by_type"].setdefault(workspace_type, 0)
            series_map[bucket]["by_type"][workspace_type] += int(row.count)
            series_map[bucket]["by_status"].setdefault(status, 0)
            series_map[bucket]["by_status"][status] += int(row.count)

        total = await self.repository.count_executions(created_since=created_since)
        success = await self.repository.count_executions(
            status=["completed", "completed_partial"],
            created_since=created_since,
        )
        failed = await self.repository.count_executions(
            status=["failed"],
            created_since=created_since,
        )
        by_workspace_type = [
            {"type": workspace_type, "count": count}
            for workspace_type, count in (
                await self.repository.count_executions_by_workspace_type(
                    created_since=created_since
                )
            ).items()
        ]

        return {
            "kpis": {
                "total": total,
                "success": success,
                "failed": failed,
                "success_rate": (success / total) if total > 0 else 0.0,
            },
            "time_series": [series_map[key] for key in sorted(series_map)],
            "by_workspace_type": by_workspace_type,
        }

    async def count_running_feature_executions(
        self,
        *,
        workspace_id: str,
        capability_id: str,
    ) -> int:
        return await self.repository.count_running_feature_executions(
            workspace_id=workspace_id,
            capability_id=capability_id,
        )

    async def get_latest_feature_execution_status(
        self,
        *,
        workspace_id: str,
        capability_id: str,
    ) -> str | None:
        return await self.repository.get_latest_feature_execution_status(
            workspace_id=workspace_id,
            capability_id=capability_id,
        )

    async def find_execution_by_launch_idempotency_key(
        self,
        *,
        workspace_id: str,
        thread_id: str,
        user_id: str,
        capability_id: str,
        launch_idempotency_key: str,
    ) -> ExecutionRecordProjection | None:
        record = await self.repository.find_execution_by_launch_idempotency_key(
            workspace_id=workspace_id,
            thread_id=thread_id,
            user_id=user_id,
            capability_id=capability_id,
            launch_idempotency_key=launch_idempotency_key,
        )
        return execution_to_projection(record) if record else None

    async def reconcile_interrupted_executions(self) -> int:
        """Mark stale in-flight executions terminal after process restart."""
        records = await self.repository.list_executions_by_status(
            list(_EXECUTION_IN_FLIGHT_STATUSES)
        )
        if not records:
            return 0

        now = datetime.now(UTC)
        restart_summary = "Execution interrupted by process restart"
        stale_lease_summary = "Execution interrupted by stale worker lease"
        credit_service = DataServiceCreditService(self.session, autocommit=False)
        reconciled = 0
        for record in records:
            runtime_state = _copy_runtime_state(record.runtime_state)
            lease_state = _execution_lease_state(runtime_state)
            if lease_state is not None and _execution_lease_is_active(lease_state, now):
                continue

            interrupted_summary = stale_lease_summary if lease_state is not None else restart_summary
            reservation_id = reservation_id_from_params(record.params)
            if reservation_id:
                with suppress(ValueError):
                    await credit_service.release_reservation(
                        reservation_id,
                        reason=interrupted_summary,
                    )
            if record.status == "cancelling":
                record.status = "cancelled"
                if not record.result_summary:
                    record.result_summary = interrupted_summary
                if not record.error:
                    record.error = interrupted_summary
                if not record.last_error:
                    record.last_error = interrupted_summary
            else:
                record.status = "failed"
                record.error = interrupted_summary
                record.last_error = interrupted_summary
                record.result_summary = interrupted_summary
            runtime_state.pop(_EXECUTION_LEASE_KEY, None)
            record.runtime_state = runtime_state or None
            record.worker_task_id = None
            record.completed_at = record.completed_at or now
            record.updated_at = now
            reconciled += 1

        if reconciled == 0:
            return 0
        await self._finish()
        return reconciled

    async def create_generation_record(
        self,
        command: GenerationRecordCreateCommand,
    ) -> GenerationRecordProjection:
        record = self.repository.create_generation_record(
            {
                "workspace_id": command.workspace_id,
                "thread_id": command.thread_id,
                "skill_name": command.skill_name,
                "model_name": command.model_name,
                "input_summary": command.input_summary,
                "output_summary": command.output_summary,
                "duration_ms": command.duration_ms,
                "token_usage": command.token_usage,
                "status": command.status,
                "error_message": command.error_message,
                "extra_data": dict(command.metadata or {}),
            }
        )
        await self._finish()
        return generation_record_to_projection(record)

    async def get_generation_record(
        self,
        record_id: str,
    ) -> GenerationRecordProjection | None:
        record = await self.repository.get_generation_record(record_id)
        return generation_record_to_projection(record) if record else None

    async def list_generation_records(
        self,
        *,
        workspace_id: str,
        skill_name: str | None = None,
        status: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[GenerationRecordProjection]:
        return [
            generation_record_to_projection(record)
            for record in await self.repository.list_generation_records(
                workspace_id=workspace_id,
                skill_name=skill_name,
                status=status,
                since=since,
                limit=limit,
            )
        ]

    async def list_generation_records_by_thread(
        self,
        thread_id: str,
    ) -> list[GenerationRecordProjection]:
        return [
            generation_record_to_projection(record)
            for record in await self.repository.list_generation_records_by_thread(thread_id)
        ]

    async def get_generation_usage_stats(
        self,
        *,
        workspace_id: str,
        since: datetime | None = None,
    ) -> dict[str, Any]:
        records = await self.list_generation_records(
            workspace_id=workspace_id,
            since=since,
            limit=100_000,
        )
        skill_counts: dict[str, int] = {}
        status_counts: dict[str, int] = {}
        for record in records:
            skill_counts[record.skill_name] = skill_counts.get(record.skill_name, 0) + 1
            status_counts[record.status] = status_counts.get(record.status, 0) + 1

        return {
            "total_executions": len(records),
            "successful_executions": status_counts.get("success", 0),
            "failed_executions": status_counts.get("failed", 0),
            "total_tokens": sum(record.total_tokens for record in records),
            "total_input_tokens": sum(record.input_tokens for record in records),
            "total_output_tokens": sum(record.output_tokens for record in records),
            "total_duration_ms": sum(record.duration_ms or 0 for record in records),
            "skill_breakdown": skill_counts,
            "status_breakdown": status_counts,
        }

    async def cleanup_old_generation_records(
        self,
        *,
        days_old: int = 90,
        workspace_id: str | None = None,
    ) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=days_old)
        deleted = await self.repository.delete_generation_records_before(
            cutoff=cutoff,
            workspace_id=workspace_id,
        )
        await self._finish()
        return deleted

    async def ensure_compute_session(
        self,
        command: ComputeSessionEnsureCommand,
    ) -> tuple[ComputeSessionProjection, bool]:
        existing = await self.repository.get_compute_session_by_execution(command.execution_id)
        if existing is not None:
            changed = False
            if command.sandbox_session_id and existing.sandbox_session_id != command.sandbox_session_id:
                existing.sandbox_session_id = command.sandbox_session_id
                existing.updated_at = datetime.now(UTC)
                changed = True
            if changed:
                await self._finish()
            return compute_session_to_projection(existing), changed

        now = datetime.now(UTC)
        record = self.repository.create_compute_session(
            {
                "execution_id": command.execution_id,
                "workspace_id": command.workspace_id,
                "user_id": command.user_id,
                "sandbox_session_id": command.sandbox_session_id,
                "active_view": "overview",
                "ui_state": {},
                "created_at": now,
                "updated_at": now,
            }
        )
        await self._finish()
        return compute_session_to_projection(record), True

    async def get_compute_session(
        self,
        compute_session_id: str,
    ) -> ComputeSessionProjection | None:
        record = await self.repository.get_compute_session(compute_session_id)
        return compute_session_to_projection(record) if record is not None else None

    async def get_compute_session_by_execution(
        self,
        execution_id: str,
    ) -> ComputeSessionProjection | None:
        record = await self.repository.get_compute_session_by_execution(execution_id)
        return compute_session_to_projection(record) if record is not None else None

    async def list_compute_sessions(
        self,
        *,
        workspace_id: str,
        user_id: str,
        limit: int = 20,
    ) -> list[ComputeSessionProjection]:
        return [
            compute_session_to_projection(record)
            for record in await self.repository.list_compute_sessions(
                workspace_id=workspace_id,
                user_id=user_id,
                limit=limit,
            )
        ]

    async def update_compute_session(
        self,
        compute_session_id: str,
        command: ComputeSessionUpdateCommand,
    ) -> ComputeSessionProjection | None:
        record = await self.repository.get_compute_session(compute_session_id)
        if record is None:
            return None
        changed = False
        if "sandbox_session_id" in command.model_fields_set and command.sandbox_session_id != record.sandbox_session_id:
            record.sandbox_session_id = command.sandbox_session_id
            changed = True
        if command.active_view is not None and command.active_view != record.active_view:
            record.active_view = command.active_view
            changed = True
        if command.ui_state is not None and command.ui_state != dict(record.ui_state or {}):
            record.ui_state = dict(command.ui_state)
            changed = True
        if "ui_state_delta" in command.model_fields_set:
            current_ui = dict(record.ui_state or {})
            current_ui.update(command.ui_state_delta or {})
            record.ui_state = current_ui
            changed = True
        if changed:
            record.updated_at = datetime.now(UTC)
            await self._finish()
        return compute_session_to_projection(record)

    async def list_run_history(
        self,
        *,
        workspace_id: str,
        limit: int = 50,
    ) -> list[ExecutionRunHistoryProjection]:
        return [
            execution_to_run_history_projection(record)
            for record in await self.repository.list_executions(
                workspace_id=workspace_id,
                limit=limit,
            )
        ]

    async def get_run_history_item(
        self,
        *,
        workspace_id: str,
        run_id: str,
    ) -> ExecutionRunHistoryProjection | None:
        record = await self.repository.get_execution(run_id)
        if record is None or record.workspace_id != workspace_id:
            return None
        return execution_to_run_history_projection(record)

    async def update_execution(
        self,
        execution_id: str,
        command: ExecutionUpdateCommand,
    ) -> ExecutionRecordProjection | None:
        if command.expected_status is not None:
            await self.repository.lock_execution(execution_id)
        record = await self.repository.get_execution(execution_id)
        if record is None:
            return None
        if (
            command.expected_status is not None
            and str(record.status or "") != command.expected_status
        ):
            return None
        changed = self._apply_update(record, command)
        if changed:
            record.updated_at = datetime.now(UTC)
        await self._finish()
        return execution_to_projection(record)

    async def patch_execution_result(
        self,
        execution_id: str,
        command: ExecutionResultPatchCommand,
    ) -> ExecutionRecordProjection | None:
        await self.repository.lock_execution(execution_id)
        record = await self.repository.get_execution(execution_id)
        if record is None:
            return None

        current_result = dict(record.result or {})
        changed = False
        for key, value in dict(command.result_patch or {}).items():
            if current_result.get(key) != value:
                current_result[key] = value
                changed = True
        if changed:
            record.result = current_result
            record.updated_at = datetime.now(UTC)
        await self._finish()
        return execution_to_projection(record)

    async def claim_execution_lease(
        self,
        execution_id: str,
        command: ExecutionLeaseClaimCommand,
    ) -> dict[str, Any]:
        await self.repository.lock_execution(execution_id)
        record = await self.repository.get_execution(execution_id)
        if record is None:
            return {"status": "not_found", "execution": None}
        if str(record.status or "") not in _EXECUTION_LEASE_ACTIVE_STATUSES:
            return {
                "status": "not_claimable",
                "execution": execution_to_projection(record),
            }

        now = command.claimed_at or datetime.now(UTC)
        runtime_state = _copy_runtime_state(record.runtime_state)
        lease_state = _execution_lease_state(runtime_state)
        current_worker = str(lease_state.get("worker_id") or "") if lease_state else ""
        if (
            lease_state is not None
            and current_worker != command.worker_id
            and _execution_lease_is_active(lease_state, now)
        ):
            return {
                "status": "in_progress",
                "execution": execution_to_projection(record),
            }

        runtime_state[_EXECUTION_LEASE_KEY] = _execution_lease_payload(
            worker_id=command.worker_id,
            claimed_at=now,
            heartbeat_at=now,
            ttl_seconds=command.ttl_seconds,
        )
        record.runtime_state = runtime_state
        record.worker_task_id = command.worker_id
        record.updated_at = now
        await self._finish()
        return {
            "status": "claimed",
            "execution": execution_to_projection(record),
        }

    async def heartbeat_execution_lease(
        self,
        execution_id: str,
        command: ExecutionLeaseHeartbeatCommand,
    ) -> dict[str, Any]:
        await self.repository.lock_execution(execution_id)
        record = await self.repository.get_execution(execution_id)
        if record is None:
            return {"status": "not_found", "execution": None}
        if str(record.status or "") not in _EXECUTION_IN_FLIGHT_STATUSES:
            return {
                "status": "not_claimable",
                "execution": execution_to_projection(record),
            }

        now = command.heartbeat_at or datetime.now(UTC)
        runtime_state = _copy_runtime_state(record.runtime_state)
        lease_state = _execution_lease_state(runtime_state)
        if lease_state is None:
            return {
                "status": "missing",
                "execution": execution_to_projection(record),
            }
        if str(lease_state.get("worker_id") or "") != command.worker_id:
            return {
                "status": "owner_mismatch",
                "execution": execution_to_projection(record),
            }
        if not _execution_lease_is_active(lease_state, now):
            return {
                "status": "stale",
                "execution": execution_to_projection(record),
            }

        claimed_at = _parse_datetime(lease_state.get("claimed_at")) or now
        runtime_state[_EXECUTION_LEASE_KEY] = _execution_lease_payload(
            worker_id=command.worker_id,
            claimed_at=claimed_at,
            heartbeat_at=now,
            ttl_seconds=command.ttl_seconds,
        )
        record.runtime_state = runtime_state
        record.worker_task_id = command.worker_id
        record.updated_at = now
        await self._finish()
        return {
            "status": "heartbeat",
            "execution": execution_to_projection(record),
        }

    async def claim_execution_commit(
        self,
        execution_id: str,
        command: ExecutionCommitClaimCommand,
    ) -> dict[str, Any]:
        await self.repository.lock_execution(execution_id)
        record = await self.repository.get_execution(execution_id)
        if record is None:
            return {"status": "not_found", "execution": None}

        result_payload = dict(record.result or {})
        commit_state = result_payload.get("commit_state")
        if isinstance(commit_state, dict):
            status = str(commit_state.get("status") or "")
            if status in {"committed", "discarded"}:
                return {
                    "status": status,
                    "execution": execution_to_projection(record),
                }
            if status == "committing":
                if _commit_claim_is_expired(commit_state, datetime.now(UTC)):
                    return {
                        "status": "stale",
                        "execution": execution_to_projection(record),
                    }
                return {
                    "status": "in_progress",
                    "execution": execution_to_projection(record),
                }
            if status == "failed":
                return {
                    "status": "failed",
                    "execution": execution_to_projection(record),
                }

        now = datetime.now(UTC)
        claimed_at = command.claimed_at or now
        result_payload["commit_state"] = {
            "status": "committing",
            "commit_token": command.commit_token,
            "started_at": claimed_at.isoformat(),
            "lease_expires_at": (claimed_at + _COMMIT_CLAIM_LEASE).isoformat(),
        }
        record.result = result_payload
        record.updated_at = now
        await self._finish()
        return {
            "status": "claimed",
            "execution": execution_to_projection(record),
        }

    async def finalize_execution_commit(
        self,
        execution_id: str,
        command: ExecutionCommitFinalizeCommand,
    ) -> ExecutionRecordProjection | None:
        await self.repository.lock_execution(execution_id)
        record = await self.repository.get_execution(execution_id)
        if record is None:
            return None

        current_result = dict(record.result or {})
        current_commit_state = current_result.get("commit_state")
        if isinstance(current_commit_state, dict):
            current_status = str(current_commit_state.get("status") or "")
            if current_status in {"committed", "discarded"}:
                return execution_to_projection(record)
            if current_status != "committing":
                return None
            if current_commit_state.get("commit_token") != command.commit_token:
                return None
        else:
            return None

        submitted_result = dict(command.result_json)
        next_commit_state = submitted_result.get("commit_state")
        if _valid_terminal_commit_state(next_commit_state) is None:
            return None

        next_result = dict(current_result)
        for key in command.delete_result_keys:
            next_result.pop(key, None)
        for key, value in submitted_result.items():
            if key == "commit_state" or key in next_result:
                continue
            next_result[key] = value
        next_result["commit_state"] = next_commit_state
        record.result = next_result
        record.updated_at = datetime.now(UTC)
        await self._finish()
        return execution_to_projection(record)

    async def fail_execution_commit(
        self,
        execution_id: str,
        command: ExecutionCommitFailCommand,
    ) -> ExecutionRecordProjection | None:
        await self.repository.lock_execution(execution_id)
        record = await self.repository.get_execution(execution_id)
        if record is None:
            return None

        current_result = dict(record.result or {})
        current_commit_state = current_result.get("commit_state")
        if isinstance(current_commit_state, dict):
            current_status = str(current_commit_state.get("status") or "")
            if current_status in {"committed", "discarded"}:
                return execution_to_projection(record)
            if current_status == "failed":
                return execution_to_projection(record)
            if current_status != "committing":
                return None
            if current_commit_state.get("commit_token") != command.commit_token:
                return None
        else:
            return None

        failed_at = command.failed_at or datetime.now(UTC)
        current_result["commit_state"] = {
            "status": "failed",
            "commit_token": command.commit_token,
            "started_at": current_commit_state.get("started_at"),
            "failed_at": failed_at.isoformat(),
            "error_text": command.error_text,
            "accepted_ids": list(command.accepted_ids or []),
            "rejected_ids": list(command.rejected_ids or []),
            "partial_counts": dict(command.partial_counts or {}),
            "partial_room_targets": dict(command.partial_room_targets or {}),
            "manual_recovery_required": True,
        }
        record.result = current_result
        record.updated_at = failed_at
        await self._finish()
        return execution_to_projection(record)

    async def reset_execution_commit(
        self,
        execution_id: str,
        command: ExecutionCommitResetCommand,
    ) -> ExecutionRecordProjection | None:
        await self.repository.lock_execution(execution_id)
        record = await self.repository.get_execution(execution_id)
        if record is None:
            return None

        result_payload = dict(record.result or {})
        current_commit_state = result_payload.get("commit_state")
        if not isinstance(current_commit_state, dict):
            return None
        if current_commit_state.get("status") in {"committed", "discarded"}:
            return None
        if (
            command.current_commit_token is not None
            and current_commit_state.get("commit_token") != command.current_commit_token
        ):
            return None

        reset_at = command.reset_at or datetime.now(UTC)
        recovery_log = list(result_payload.get("commit_recovery_log") or [])
        recovery_log.insert(
            0,
            {
                "reason": command.reason,
                "reset_at": reset_at.isoformat(),
                "previous_commit_state": dict(current_commit_state),
            },
        )
        result_payload["commit_recovery_log"] = recovery_log[:20]
        result_payload.pop("commit_state", None)
        record.result = result_payload
        record.updated_at = reset_at
        await self._finish()
        return execution_to_projection(record)

    async def list_nodes(self, execution_id: str) -> list[ExecutionNodeProjection]:
        return [
            node_to_projection(record)
            for record in await self.repository.list_nodes(execution_id)
        ]

    async def list_nodes_by_execution_ids(
        self,
        execution_ids: list[str],
    ) -> list[ExecutionNodeProjection]:
        return [
            node_to_projection(record)
            for record in await self.repository.list_nodes_by_execution_ids(execution_ids)
        ]

    async def get_node_by_record_id(
        self,
        node_record_id: str,
    ) -> ExecutionNodeProjection | None:
        record = await self.repository.get_node_by_record_id(node_record_id)
        return node_to_projection(record) if record else None

    async def find_node_by_node_id(
        self,
        *,
        execution_id: str,
        node_id: str,
    ) -> ExecutionNodeProjection | None:
        record = await self.repository.get_node_by_node_id(
            execution_id=execution_id,
            node_id=node_id,
        )
        return node_to_projection(record) if record else None

    async def upsert_node(
        self,
        execution_id: str,
        command: ExecutionNodeUpsertCommand,
    ) -> ExecutionNodeProjection:
        now = datetime.now(UTC)
        record = await self.repository.upsert_node(
            {
                "execution_id": execution_id,
                "parent_node_id": command.parent_node_id,
                "node_id": command.node_id,
                "node_type": command.node_type,
                "label": command.label,
                "status": command.status,
                "input_data": command.input_data,
                "output_data": command.output_data,
                "thinking": command.thinking,
                "tool_calls": command.tool_calls,
                "token_usage": command.token_usage,
                "node_metadata": command.node_metadata,
                "started_at": command.started_at,
                "completed_at": command.completed_at,
                "created_at": now,
                "updated_at": now,
            }
        )
        await self._finish()
        return node_to_projection(record)

    async def update_node(
        self,
        node_record_id: str,
        command: ExecutionNodePatchCommand,
    ) -> ExecutionNodeProjection | None:
        record = await self.repository.get_node_by_record_id(node_record_id)
        if record is None:
            return None
        changed = self._apply_node_patch(record, command)
        if changed:
            record.updated_at = datetime.now(UTC)
        await self._finish()
        return node_to_projection(record)

    async def append_event(
        self,
        execution_id: str,
        command: ExecutionEventCreateCommand,
    ) -> ExecutionEventProjection:
        await self.repository.lock_execution(execution_id)
        record = await self.repository.append_event(
            execution_id=execution_id,
            workspace_id=command.workspace_id,
            node_id=command.node_id,
            event_type=command.event_type,
            payload_json=dict(command.payload_json or {}),
            occurred_at=command.occurred_at,
        )
        await self._finish()
        return event_to_projection(record)

    async def list_events(self, execution_id: str) -> list[ExecutionEventProjection]:
        return [
            event_to_projection(record)
            for record in await self.repository.list_events(execution_id)
        ]

    @staticmethod
    def _apply_update(record: Any, command: ExecutionUpdateCommand) -> bool:
        changed = False
        mapping = {
            "status": "status",
            "thread_id": "thread_id",
            "entry_skill_id": "entry_skill_id",
            "workspace_type": "workspace_type",
            "display_name": "display_name",
            "task_brief_json": "params",
            "result_json": "result",
            "error_text": "error",
            "result_summary": "result_summary",
            "graph_json": "graph_structure",
            "node_states_json": "node_states",
            "runtime_state_json": "runtime_state",
            "progress": "progress",
            "message": "message",
            "artifact_ids": "artifact_ids",
            "next_actions": "next_actions",
            "advisory_code": "advisory_code",
            "last_error": "last_error",
            "dispatch_mode": "dispatch_mode",
            "worker_task_id": "worker_task_id",
            "started_at": "started_at",
            "completed_at": "completed_at",
        }
        data = command.model_dump(exclude_unset=True)
        for command_key, record_key in mapping.items():
            if command_key not in data:
                continue
            value = data[command_key]
            if command_key == "result_json":
                value = _protect_commit_result_fields(
                    current_result=getattr(record, record_key),
                    incoming_result=value,
                )
            if getattr(record, record_key) != value:
                setattr(record, record_key, value)
                changed = True
        return changed

    @staticmethod
    def _apply_node_patch(record: Any, command: ExecutionNodePatchCommand) -> bool:
        changed = False
        data = command.model_dump(exclude_unset=True)
        for key, value in data.items():
            if getattr(record, key) != value:
                setattr(record, key, value)
                changed = True
        return changed

    async def _finish(self) -> None:
        if self.autocommit:
            await self.session.commit()
        else:
            await self.session.flush()


def _commit_claim_is_expired(commit_state: dict[str, Any], now: datetime) -> bool:
    expires_at = _parse_datetime(commit_state.get("lease_expires_at"))
    return expires_at is not None and expires_at <= now


def _copy_runtime_state(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return deepcopy(value)
    return {}


def _execution_lease_state(runtime_state: dict[str, Any]) -> dict[str, Any] | None:
    value = runtime_state.get(_EXECUTION_LEASE_KEY)
    return value if isinstance(value, dict) else None


def _execution_lease_payload(
    *,
    worker_id: str,
    claimed_at: datetime,
    heartbeat_at: datetime,
    ttl_seconds: int,
) -> dict[str, str]:
    return {
        "worker_id": worker_id,
        "claimed_at": claimed_at.isoformat(),
        "last_heartbeat_at": heartbeat_at.isoformat(),
        "lease_expires_at": (heartbeat_at + timedelta(seconds=ttl_seconds)).isoformat(),
    }


def _execution_lease_is_active(lease_state: dict[str, Any], now: datetime) -> bool:
    expires_at = _parse_datetime(lease_state.get("lease_expires_at"))
    return expires_at is not None and expires_at > now


def _protect_commit_result_fields(
    *,
    current_result: Any,
    incoming_result: Any,
) -> Any:
    if not isinstance(current_result, dict):
        return incoming_result
    current_commit_state = current_result.get("commit_state")
    if not isinstance(current_commit_state, dict):
        return incoming_result
    if not isinstance(incoming_result, dict):
        return dict(current_result)

    incoming_commit_state = incoming_result.get("commit_state")
    next_result = dict(incoming_result)
    if _valid_reverted_commit_transition(
        current_commit_state=current_commit_state,
        incoming_commit_state=incoming_commit_state,
    ):
        next_result["commit_state"] = deepcopy(incoming_commit_state)
    else:
        next_result["commit_state"] = deepcopy(current_commit_state)
    if "change_set_receipt" in current_result:
        next_result["change_set_receipt"] = deepcopy(current_result["change_set_receipt"])

    if current_commit_state.get("status") in {"committed", "discarded"}:
        for key in EXECUTION_COMMIT_FINALIZE_DELETABLE_RESULT_KEYS:
            if key in current_result:
                next_result[key] = deepcopy(current_result[key])
            else:
                next_result.pop(key, None)
    return next_result


def _valid_reverted_commit_transition(
    *,
    current_commit_state: dict[str, Any],
    incoming_commit_state: Any,
) -> bool:
    if current_commit_state.get("status") != "committed":
        return False
    if not isinstance(incoming_commit_state, dict):
        return False
    if incoming_commit_state.get("status") != "reverted":
        return False
    for key in ("accepted_ids", "rejected_ids", "counts", "room_targets", "committed_at"):
        if incoming_commit_state.get(key) != current_commit_state.get(key):
            return False
    if not isinstance(incoming_commit_state.get("reverted_at"), str):
        return False
    if not isinstance(incoming_commit_state.get("reverted_by"), str):
        return False
    revert_counts = incoming_commit_state.get("revert_counts")
    if not isinstance(revert_counts, dict):
        return False
    for key in _COMMIT_COUNT_ROOM_KEYS:
        count = revert_counts.get(key)
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            return False
    return True


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    with suppress(ValueError):
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed
    return None


def _valid_terminal_commit_state(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    if value.get("status") not in {"committed", "discarded"}:
        return None
    if not _is_str_list(value.get("accepted_ids")):
        return None
    if not _is_str_list(value.get("rejected_ids")):
        return None
    if not isinstance(value.get("committed_at"), str):
        return None

    counts = value.get("counts")
    if not isinstance(counts, dict):
        return None
    for key in _COMMIT_COUNT_ROOM_KEYS:
        count = counts.get(key)
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            return None

    room_targets = value.get("room_targets")
    if not isinstance(room_targets, dict):
        return None
    for key in _COMMIT_ROOM_TARGET_KEYS:
        targets = room_targets.get(key)
        if not isinstance(targets, list):
            return None
        for target in targets:
            if not isinstance(target, dict):
                return None
            if not isinstance(target.get("output_id"), str):
                return None
            if not isinstance(target.get("item_id"), str):
                return None

    review_batch_id = value.get("review_batch_id")
    if review_batch_id is not None and not isinstance(review_batch_id, str):
        return None
    return value


def _is_str_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)
