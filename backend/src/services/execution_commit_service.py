"""Execution commit service — writes accepted ResultOutputs to rooms in one pass.

Spec §4.7.5: All outputs go in one pass; Run History always recorded (regardless
of user selection). Idempotent via idempotency_key (Redis-backed cache, 24h TTL).
"""

from __future__ import annotations

import hashlib
import inspect
import json
import logging
import re
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, cast

from src.agents.contracts.task_report import TaskReport
from src.contracts.change_set import ChangeSet
from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.execution import ExecutionEventCreatePayload
from src.dataservice_client.contracts.prism import (
    PrismFileRestorePayload,
    PrismWorkspaceFileUpsertPayload,
)
from src.dataservice_client.contracts.rooms import (
    DecisionSetPayload,
    WorkspaceTaskCreatePayload,
)
from src.dataservice_client.contracts.source import (
    SourceExternalIdCreatePayload,
    SourceImportPayload,
)
from src.dataservice_client.contracts.workspace_memory import (
    WorkspaceMemoryItemPayload,
    WorkspaceMemoryMergePayload,
)
from src.dataservice_client.provider import dataservice_client
from src.services.change_unit_materializer import (
    ChangeUnitMaterializationResult,
    materialize_accepted_change_units,
)
from src.services.execution_service import ExecutionService
from src.services.references import SourceBibliographyService
from src.workspace_events import publish_workspace_event

logger = logging.getLogger(__name__)

_CITATION_KEY_RE = re.compile(r"[^a-z0-9]+")
_PRISM_SUPPORTED_EXTENSIONS = {".md", ".markdown", ".tex", ".bib", ".png", ".jpg", ".jpeg", ".webp", ".svg"}
_COUNT_ROOM_KEYS = ("library", "prism", "memory", "decisions", "tasks", "sandbox", "settings")
_ROOM_TARGET_KEYS = ("prism", "library", "memory", "decisions", "tasks", "sandbox", "settings")
_CHANGE_UNIT_MATERIALIZATION_RESULT_KEY = "change_unit_materialization"
_CHANGE_SET_TEMP_RESULT_KEYS = [
    "change_set",
    "change_set_review_state",
    "unit_states",
    _CHANGE_UNIT_MATERIALIZATION_RESULT_KEY,
]
_RECEIPT_ROOM_TARGET_KEYS = (
    "output_id",
    "item_id",
    "file_id",
    "path",
    "content_hash",
    "document_id",
    "revision",
)
_COMMIT_LOCK_TTL_SECONDS = 60
_MAX_COMMIT_ID_COUNT = 200
_MAX_COMMIT_ID_LENGTH = 160
_BULK_UNSAFE_KINDS = {"decision", "library_item"}
_BULK_UNSAFE_REVIEW_KINDS = {"reference", "warning"}
_BULK_UNSAFE_REVIEW_RISK_LEVELS = {"medium", "high", "critical"}
_BULK_UNSAFE_FLAG_KEYS = {
    "citation_audit",
    "citation_gap",
    "evidence_gap",
    "manual_review_required",
    "needs_review",
    "requires_manual_review",
    "review_required",
    "unsupported_claim",
}
_BULK_UNSAFE_REF_KEYS = {
    "claim_refs",
    "evidence_refs",
}
_BULK_UNSAFE_STATUS_KEYS = {
    "risk",
    "risk_level",
    "support_level",
    "support_state",
    "support_status",
}
_BULK_UNSAFE_STATUS_VALUES = {
    "blocked",
    "blocker",
    "critical",
    "evidence_gap",
    "high",
    "manual_review",
    "medium",
    "needs_review",
    "requires_manual_review",
    "unsupported",
    "unsupported_claim",
    "weak",
}
_BULK_UNSAFE_STRUCTURED_VALUES = {
    "citation_audit",
    "citation_gap",
    "evidence_gap",
    "manual_review_required",
    "requires_manual_review",
    "review_required",
    "unsupported_claim",
}
_MEMORY_STRONG_UNSAFE_PHRASES = (
    "citation gap",
    "evidence gap",
    "manual review required",
    "requires manual review",
    "unsupported claim",
)


class ExecutionCommitNotFoundError(LookupError):
    """Raised when a commit target is missing or hidden from this actor."""


class ExecutionCommitConcurrencyError(RuntimeError):
    """Raised when a commit is already being materialized elsewhere."""


class ExecutionCommitPersistenceError(RuntimeError):
    """Raised when durable commit_state persistence cannot be confirmed."""


class ExecutionCommitService:
    """Commits accepted ResultOutputs to corresponding rooms.

    Spec §4.7.5: All outputs go in one pass; Run History always recorded
    (regardless of user selection). Idempotent via idempotency_key (Redis-backed
    cache). Room materialization is staged through DataService review handlers.
    """

    def __init__(
        self,
        *,
        execution_service: ExecutionService,
        dataservice: AsyncDataServiceClient | None = None,
        audit_service: Any | None = None,
        redis: Any = None,  # for idempotency cache; if None, no idempotency
        referral_first_task_callback: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        self.execution = execution_service
        self._dataservice = dataservice
        self.audit = audit_service
        self.redis = redis
        self._referral_first_task_callback = referral_first_task_callback

    @asynccontextmanager
    async def _client(self) -> AsyncIterator[AsyncDataServiceClient]:
        if self._dataservice is not None:
            yield self._dataservice
            return
        async with dataservice_client() as client:
            yield client

    def _supports_commit_lock(self) -> bool:
        return self.redis is not None and callable(getattr(self.redis, "set", None)) and callable(
            getattr(self.redis, "eval", None)
        )

    async def _acquire_commit_lock(self, execution_id: str) -> str | None:
        """Acquire a best-effort Redis lock when Redis exposes lock primitives."""
        if not self._supports_commit_lock():
            return None

        key = f"commit:lock:{execution_id}"
        token = uuid.uuid4().hex
        try:
            acquired = await self.redis.set(
                key,
                token,
                nx=True,
                ex=_COMMIT_LOCK_TTL_SECONDS,
            )
        except Exception:
            logger.warning(
                "Failed to acquire execution commit lock for %s",
                execution_id,
                exc_info=True,
            )
            return None
        if not acquired:
            raise ExecutionCommitConcurrencyError(
                f"execution {execution_id} commit is already in progress"
            )
        return token

    async def _release_commit_lock(self, execution_id: str, token: str | None) -> None:
        if token is None or not self._supports_commit_lock():
            return
        try:
            await self.redis.eval(
                """
                if redis.call('get', KEYS[1]) == ARGV[1] then
                    return redis.call('del', KEYS[1])
                end
                return 0
                """,
                1,
                f"commit:lock:{execution_id}",
                token,
            )
        except Exception:
            logger.warning(
                "Failed to release execution commit lock for %s",
                execution_id,
                exc_info=True,
            )

    async def commit_outputs(
        self,
        execution_id: str,
        *,
        actor_user_id: str,
        accept_all: bool = False,
        accepted_ids: list[str] | None = None,
        accepted_unit_ids: list[str] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Commit accepted outputs to rooms and record run history.

        Args:
            execution_id: The execution to commit outputs for.
            actor_user_id: Authenticated user attempting the writeback.
            accept_all: If True, all outputs in the TaskReport are written.
            accepted_ids: Specific historical output IDs to write (ignored when accept_all=True).
            accepted_unit_ids: Specific accepted ChangeUnit IDs to materialize.
            idempotency_key: Optional key for idempotent repeat calls (24h cache).

        Returns:
            dict with key "committed" containing per-room write counts.

        Raises:
            ExecutionCommitNotFoundError: If execution is missing or hidden.
            ValueError: If execution has no task_report or commit input is invalid.
        """
        # 1. Fetch execution and enforce ownership before any write or cache read.
        execution = await self.execution.get_by_id(execution_id)
        if execution is None:
            raise ExecutionCommitNotFoundError(f"execution {execution_id} not found")
        if str(execution.user_id) != str(actor_user_id):
            raise ExecutionCommitNotFoundError(f"execution {execution_id} not found")
        await self._ensure_active_workspace_membership(execution, actor_user_id=actor_user_id)

        result_payload = _execution_result_payload(execution)
        if result_payload is not None:
            existing_commit_state = _valid_commit_state(result_payload.get("commit_state"))
            if existing_commit_state is not None:
                return _response_from_commit_state(existing_commit_state)

        # 2. Validate report
        if result_payload is None or "task_report" not in result_payload:
            raise ValueError(f"execution {execution_id} has no task_report")

        report = TaskReport.model_validate(result_payload["task_report"])

        # 3. Select outputs. Partial/cancelled runs may expose useful candidates,
        # but they must be intentionally selected by the user.
        output_by_id = {output.id: output for output in report.outputs}
        selected_unit_ids: list[str] | None = None
        selected_change_set: ChangeSet | None = None
        has_change_set = _result_has_change_set(result_payload)
        if accept_all and accepted_unit_ids is not None:
            raise ValueError("accept_all cannot be combined with accepted_unit_ids")
        if accepted_ids is not None and accepted_unit_ids is not None:
            raise ValueError("accepted_ids cannot be combined with accepted_unit_ids")
        if has_change_set and accepted_unit_ids is None and (accept_all or accepted_ids is not None):
            raise ValueError("ChangeSet executions must be saved with accepted_unit_ids")

        if accepted_unit_ids is not None:
            selection_provided = True
            unit_selection = _select_outputs_for_change_units(
                result_payload,
                report=report,
                accepted_unit_ids=accepted_unit_ids,
            )
            selected = unit_selection["outputs"]
            selected_unit_ids = unit_selection["unit_ids"]
            selected_change_set = unit_selection["change_set"]
        elif accept_all:
            selection_provided = True
            if report.status != "completed":
                raise ValueError(
                    "accept_all is only allowed for completed executions; "
                    "use accepted_ids for partial results"
                )
            if _report_has_bulk_unsafe_outputs(report):
                raise ValueError(
                    "Some outputs need explicit review/selection before they can be "
                    "saved. Review and select those outputs individually instead of "
                    "using accept all."
                )
            selected = list(report.outputs)
            _validate_selected_outputs_against_change_set(result_payload, selected)
        elif accepted_ids is not None:
            selection_provided = True
            id_set = set(_normalize_selected_ids(accepted_ids, field_name="accepted_ids"))
            missing_ids = sorted(id_set - set(output_by_id))
            if missing_ids:
                raise ValueError(
                    "accepted_ids contains unknown output id(s): "
                    + _format_limited_id_list(missing_ids)
                )
            selected = [o for o in report.outputs if o.id in id_set]
            _validate_selected_outputs_against_change_set(result_payload, selected)
        else:
            selection_provided = False
            selected = []

        if idempotency_key and self.redis:
            cache_key = f"commit:cache:{execution_id}:{idempotency_key}"
            cached_response = await _read_commit_cache(self.redis, cache_key)
            if cached_response is not None:
                return cached_response

        if not selection_provided:
            return _noop_commit_response()

        lock_token = await self._acquire_commit_lock(execution_id)
        commit_token = uuid.uuid4().hex
        claimed_for_materialization = False
        counts = _empty_counts()
        room_targets = _empty_room_targets()
        try:
            claim = await self.execution.claim_execution_commit(
                execution_id=execution_id,
                commit_token=commit_token,
            )
            claim_status = str(claim.get("status") or "")
            claim_execution = claim.get("execution")
            if claim_status == "not_found":
                raise ExecutionCommitNotFoundError(f"execution {execution_id} not found")
            if claim_status == "in_progress":
                raise ExecutionCommitConcurrencyError(
                    f"execution {execution_id} commit is already in progress"
                )
            if claim_status == "failed":
                raise ExecutionCommitPersistenceError(
                    "previous execution commit failed and requires recovery"
                )
            if claim_status == "stale":
                raise ExecutionCommitPersistenceError(
                    "stale execution commit claim requires recovery"
                )
            if claim_status in {"committed", "discarded"}:
                result_payload = _execution_result_payload(claim_execution)
                commit_state = (
                    _valid_commit_state(result_payload.get("commit_state"))
                    if result_payload is not None
                    else None
                )
                if commit_state is None:
                    raise ExecutionCommitPersistenceError(
                        "commit_state persistence failed for execution commit"
                    )
                return _response_from_commit_state(commit_state)
            if claim_status != "claimed":
                raise ExecutionCommitPersistenceError(
                    f"unexpected execution commit claim status: {claim_status or 'unknown'}"
                )
            if claim_execution is None:
                raise ExecutionCommitPersistenceError(
                    "execution commit claim did not return execution state"
                )
            if str(claim_execution.user_id) != str(actor_user_id):
                raise ExecutionCommitNotFoundError(f"execution {execution_id} not found")
            await self._ensure_active_workspace_membership(
                claim_execution,
                actor_user_id=actor_user_id,
            )
            if not claim_execution.result or "task_report" not in claim_execution.result:
                raise ValueError(f"execution {execution_id} has no task_report")
            execution = claim_execution
            report = TaskReport.model_validate(execution.result["task_report"])
            if selected_unit_ids is not None:
                unit_selection = _select_outputs_for_change_units(
                    execution.result,
                    report=report,
                    accepted_unit_ids=selected_unit_ids,
                )
                selected = unit_selection["outputs"]
                selected_unit_ids = unit_selection["unit_ids"]
                selected_change_set = unit_selection["change_set"]
            else:
                _validate_selected_outputs_against_change_set(execution.result, selected)
            claimed_for_materialization = True

            # 5. Write to rooms
            async with self._client() as dataservice:
                if selected_unit_ids is not None:
                    if selected_change_set is None:
                        raise ExecutionCommitPersistenceError(
                            "accepted_unit_ids requires a valid ChangeSet"
                        )
                    progress_state = _change_unit_materialization_progress(
                        execution.result,
                        execution_id=execution_id,
                        accepted_unit_ids=selected_unit_ids,
                    )
                    counts = _merge_counts(counts, progress_state["counts"])
                    room_targets = _merge_room_targets(
                        room_targets,
                        progress_state["room_targets"],
                    )
                    completed_unit_ids: set[str] = set(progress_state["completed_unit_ids"])

                    async def record_unit_materialized(
                        unit_id: str,
                        unit_result: ChangeUnitMaterializationResult,
                    ) -> None:
                        nonlocal counts, room_targets

                        counts = _merge_counts(counts, unit_result.counts)
                        room_targets = _merge_room_targets(
                            room_targets,
                            unit_result.room_targets,
                        )
                        completed_unit_ids.add(unit_id)
                        await self.execution.patch_execution_result(
                            execution_id,
                            result_patch={
                                _CHANGE_UNIT_MATERIALIZATION_RESULT_KEY: (
                                    _build_change_unit_materialization_progress(
                                        execution_id=execution_id,
                                        accepted_unit_ids=selected_unit_ids or [],
                                        completed_unit_ids=completed_unit_ids,
                                        counts=counts,
                                        room_targets=room_targets,
                                    )
                                )
                            },
                            commit=True,
                        )

                    materialized = await materialize_accepted_change_units(
                        dataservice=dataservice,
                        execution=execution,
                        report=report,
                        change_set=selected_change_set,
                        accepted_unit_ids=selected_unit_ids,
                        completed_unit_ids=completed_unit_ids,
                        on_unit_materialized=record_unit_materialized,
                    )
                    if not completed_unit_ids:
                        counts = _merge_counts(counts, materialized.counts)
                        room_targets = _merge_room_targets(
                            room_targets,
                            materialized.room_targets,
                        )
                else:
                    existing_prism_files_by_path = await _existing_prism_files_by_path(
                        dataservice=dataservice,
                        workspace_id=execution.workspace_id,
                    )
                    memory_items: list[tuple[str, WorkspaceMemoryItemPayload]] = []
                    for output in selected:
                        kind = output.kind
                        data = (
                            output.data.model_dump()
                            if hasattr(output.data, "model_dump")
                            else dict(output.data)
                        )

                        if kind == "library_item":
                            import_result = await dataservice.import_source(
                                _source_import_payload(
                                    workspace_id=execution.workspace_id,
                                    execution_id=execution_id,
                                    data=data,
                                )
                            )
                            counts["library"] += 1
                            room_targets["library"].append(
                                {"output_id": output.id, "item_id": import_result.source.id}
                            )

                        elif kind == "document":
                            prism_payload = _document_prism_payload(
                                execution=execution,
                                output_id=output.id,
                                data=data,
                            )
                            if prism_payload is None:
                                logger.warning(
                                    "Skipping document commit '%s' for execution %s: no Prism-compatible content",
                                    data.get("name"),
                                    execution_id,
                                )
                                continue
                            previous_file = existing_prism_files_by_path.get(prism_payload.path)
                            write = await dataservice.upsert_prism_workspace_file(
                                execution.workspace_id,
                                prism_payload,
                            )
                            existing_prism_files_by_path[write.file.path] = write.file
                            if write.changed and write.version is not None:
                                counts["prism"] += 1
                                room_targets["prism"].append(
                                    _prism_room_target(
                                        output_id=output.id,
                                        file_id=write.file.id,
                                        path=write.file.path,
                                        version_id=write.version.id,
                                        content_hash=write.version.content_hash,
                                        previous_version_id=(
                                            previous_file.current_version_id
                                            if previous_file is not None
                                            else None
                                        ),
                                        previous_hash=(
                                            previous_file.content_hash
                                            if previous_file is not None
                                            else None
                                        ),
                                        created_file=previous_file is None,
                                    )
                                )

                        elif kind == "memory_fact":
                            memory_items.append(
                                (
                                    output.id,
                                    WorkspaceMemoryItemPayload(
                                        category=str(data.get("category") or "context"),
                                        content=str(data.get("content") or ""),
                                        confidence=float(data.get("confidence", 1.0) or 1.0),
                                    ),
                                )
                            )

                        elif kind == "decision":
                            decision = await dataservice.set_room_decision(
                                DecisionSetPayload(
                                    workspace_id=execution.workspace_id,
                                    key=str(data["key"]),
                                    value=str(data["value"]),
                                    confidence=float(data.get("confidence", 1.0) or 1.0),
                                    extracted_by=f"execution:{execution_id}",
                                )
                            )
                            counts["decisions"] += 1
                            room_targets["decisions"].append(
                                {"output_id": output.id, "item_id": decision.id}
                            )

                        elif kind == "task":
                            priority = data["priority"] if isinstance(data.get("priority"), int) else 0
                            task = await dataservice.create_room_task(
                                WorkspaceTaskCreatePayload(
                                    workspace_id=execution.workspace_id,
                                    title=str(data["title"]),
                                    description=data.get("description"),
                                    priority=priority,
                                    related_execution_ids=[execution_id],
                                    created_by=f"execution:{execution_id}",
                                )
                            )
                            counts["tasks"] += 1
                            room_targets["tasks"].append(
                                {"output_id": output.id, "item_id": task.id}
                            )

                    if memory_items:
                        memory_review_result = await dataservice.merge_workspace_memory(
                            execution.workspace_id,
                            WorkspaceMemoryMergePayload(
                                workspace_id=execution.workspace_id,
                                items=[item for _, item in memory_items],
                                update_reason="execution_commit",
                                updated_by=f"execution:{execution_id}",
                                source_execution_id=execution_id,
                            ),
                        )
                        if memory_review_result.changed:
                            counts["memory"] += 1
                            for output_id, _item in memory_items:
                                room_targets["memory"].append(
                                    {
                                        "output_id": output_id,
                                        "item_id": memory_review_result.document.id,
                                        "document_id": memory_review_result.document.id,
                                        "revision": str(memory_review_result.document.revision),
                                        "content_hash": memory_review_result.document.content_hash,
                                    }
                                )

                if counts["library"] > 0:
                    await self._sync_prism_bibliography(
                        workspace_id=execution.workspace_id,
                        dataservice=dataservice,
                    )

                # 6. Always write run_history for explicit commit/discard decisions.
                capability_id = execution.feature_id or report.capability_id
                await dataservice.append_execution_event(
                    execution_id,
                    ExecutionEventCreatePayload(
                        workspace_id=execution.workspace_id,
                        event_type="execution.run_history",
                        payload_json={
                            "capability_id": capability_id,
                            "title": report.narrative[:200],
                            "summary": report.narrative,
                            "status": report.status,
                            "duration_seconds": report.duration_seconds,
                            "token_usage": report.token_usage or {},
                            "artifact_count": _committed_artifact_count(
                                selected_outputs=selected,
                                selected_unit_ids=selected_unit_ids,
                            ),
                        },
                    ),
                )

            committed_at = datetime.now(UTC).isoformat()
            accepted_output_ids = [output.id for output in selected]
            accepted_output_id_set = set(accepted_output_ids)
            commit_state = _build_commit_state(
                status=_commit_status_for_selection(
                    selected_outputs=selected,
                    selected_unit_ids=selected_unit_ids,
                ),
                accepted_ids=accepted_output_ids,
                rejected_ids=[
                    output.id
                    for output in report.outputs
                    if output.id not in accepted_output_id_set
                ],
                counts=counts,
                room_targets=room_targets,
                committed_at=committed_at,
                accepted_unit_ids=selected_unit_ids,
            )
            result = _response_from_commit_state(commit_state)

            result_payload, delete_result_keys = _compact_change_set_after_commit(
                dict(execution.result),
                commit_state=commit_state,
            )
            result_payload["commit_state"] = commit_state
            persisted_execution = await self.execution.finalize_execution_commit(
                execution_id,
                result=result_payload,
                delete_result_keys=delete_result_keys,
                commit_token=commit_token,
                commit=True,
            )
            _ensure_commit_state_persisted(persisted_execution, commit_state)
        except Exception as exc:
            if claimed_for_materialization:
                accepted_ids_for_recovery = [output.id for output in selected]
                accepted_id_set_for_recovery = set(accepted_ids_for_recovery)
                await self._mark_commit_failed(
                    execution_id=execution_id,
                    commit_token=commit_token,
                    error=exc,
                    accepted_ids=accepted_ids_for_recovery,
                    rejected_ids=[
                        output.id
                        for output in report.outputs
                        if output.id not in accepted_id_set_for_recovery
                    ],
                    counts=counts,
                    room_targets=room_targets,
                )
            raise
        finally:
            await self._release_commit_lock(execution_id, lock_token)

        # 7. Cache idempotent result after commit_state is durable.
        if idempotency_key and self.redis:
            cache_key = f"commit:cache:{execution_id}:{idempotency_key}"
            await _write_commit_cache(self.redis, cache_key, result)

        # 8. Publish canonical workspace refresh event
        try:
            await publish_workspace_event(
                execution.workspace_id,
                "workspace.refresh",
                {
                    "refresh_targets": [
                        "activity",
                        "artifacts",
                        "dashboard",
                        "library",
                        "decisions",
                        "tasks",
                        "runs",
                        "references",
                        "prism",
                    ]
                },
            )
        except Exception:
            logger.exception("workspace.refresh publish failed")

        # 9. Audit
        if self.audit:
            try:
                await self.audit.log(
                    action="execution.commit",
                    user_id=execution.user_id,
                    workspace_id=execution.workspace_id,
                    target_type="execution",
                    target_id=execution_id,
                    payload={
                        "counts": counts,
                        "accepted_ids": accepted_ids,
                        "accept_all": accept_all,
                    },
                )
            except Exception:
                logger.exception("audit log failed for execution.commit")

        # Fire referral first-task trigger (idempotent — no-ops if no referral or already fired)
        try:
            await self._fire_referral_first_task(execution.user_id)
        except Exception:
            logger.exception(
                "referral first-task trigger failed for user %s", execution.user_id
            )

        return result

    async def undo_commit(
        self,
        execution_id: str,
        *,
        actor_user_id: str,
    ) -> dict[str, Any]:
        """Undo a previously committed output batch by deleting its room targets."""
        execution = await self.execution.get_by_id(execution_id)
        if execution is None:
            raise ExecutionCommitNotFoundError(f"execution {execution_id} not found")
        if str(execution.user_id) != str(actor_user_id):
            raise ExecutionCommitNotFoundError(f"execution {execution_id} not found")
        await self._ensure_active_workspace_membership(execution, actor_user_id=actor_user_id)

        result_payload = _execution_result_payload(execution)
        if result_payload is None:
            raise ValueError(f"execution {execution_id} has no result payload")

        commit_state = _valid_commit_state(result_payload.get("commit_state"))
        if commit_state is None:
            raise ValueError(f"execution {execution_id} has no committed room batch")
        if commit_state["status"] == "reverted":
            return _response_from_commit_state(commit_state)
        if commit_state["status"] != "committed":
            raise ValueError("only committed execution outputs can be reverted")

        room_targets = _copy_room_targets(commit_state["room_targets"])
        revert_counts = _empty_counts()
        revert_skipped: dict[str, list[dict[str, Any]]] = {"prism": []}
        async with self._client() as dataservice:
            for target in room_targets["prism"]:
                file_id = str(target.get("file_id") or target.get("item_id") or "")
                if not file_id:
                    continue
                if _truthy_target_flag(target.get("created_file")):
                    deleted = await dataservice.delete_prism_workspace_file(
                        execution.workspace_id,
                        file_id,
                        expected_current_hash=target.get("content_hash"),
                    )
                    if deleted.changed:
                        revert_counts["prism"] += 1
                    else:
                        revert_skipped["prism"].append(
                            {
                                "file_id": file_id,
                                "path": target.get("path"),
                                "reason": deleted.skipped_reason or "not_deleted",
                            }
                        )
                    continue
                previous_version_id = target.get("previous_version_id")
                if previous_version_id:
                    restored = await dataservice.restore_prism_workspace_file(
                        execution.workspace_id,
                        file_id,
                        PrismFileRestorePayload(
                            version_id=previous_version_id,
                            expected_current_hash=target.get("content_hash"),
                            created_by=f"undo:{execution_id}",
                        ),
                    )
                    if restored.changed:
                        revert_counts["prism"] += 1
                    else:
                        revert_skipped["prism"].append(
                            {
                                "file_id": file_id,
                                "path": target.get("path"),
                                "reason": restored.skipped_reason or "not_restored",
                            }
                        )
            for target in room_targets["library"]:
                deleted = await dataservice.delete_source(
                    source_id=target["item_id"],
                    workspace_id=execution.workspace_id,
                )
                if deleted:
                    revert_counts["library"] += 1
            for target in room_targets["decisions"]:
                deleted = await dataservice.delete_room_decision(target["item_id"])
                if deleted:
                    revert_counts["decisions"] += 1
            for target in room_targets["tasks"]:
                deleted = await dataservice.delete_room_task(
                    workspace_id=execution.workspace_id,
                    task_id=target["item_id"],
                )
                if deleted:
                    revert_counts["tasks"] += 1

        for room in ("sandbox", "settings"):
            for target in room_targets[room]:
                revert_skipped.setdefault(room, []).append(
                    _manual_revert_skip_target(target)
                )

        reverted_state = _build_reverted_commit_state(
            commit_state,
            reverted_at=datetime.now(UTC).isoformat(),
            reverted_by=actor_user_id,
            revert_counts=revert_counts,
            revert_skipped=_non_empty_revert_skipped(revert_skipped),
        )
        next_result_payload = dict(result_payload)
        next_result_payload["commit_state"] = reverted_state
        persisted_execution = await self.execution.update_execution(
            execution_id,
            result=next_result_payload,
            commit=True,
        )
        persisted_result = _execution_result_payload(persisted_execution)
        persisted_commit_state = (
            _valid_commit_state(persisted_result.get("commit_state"))
            if persisted_result is not None
            else None
        )
        if persisted_commit_state != reverted_state:
            raise ExecutionCommitPersistenceError(
                "commit_state persistence failed for execution undo"
            )

        result = _response_from_commit_state(reverted_state)
        try:
            await publish_workspace_event(
                execution.workspace_id,
                "workspace.refresh",
                {
                    "refresh_targets": [
                        "activity",
                        "artifacts",
                        "dashboard",
                        "library",
                        "decisions",
                        "tasks",
                        "runs",
                        "references",
                        "prism",
                        "settings",
                    ]
                },
            )
        except Exception:
            logger.exception("workspace.refresh publish failed after commit undo")

        if self.audit:
            try:
                await self.audit.log(
                    action="execution.commit.undo",
                    user_id=execution.user_id,
                    workspace_id=execution.workspace_id,
                    target_type="execution",
                    target_id=execution_id,
                    payload={"revert_counts": revert_counts},
                )
            except Exception:
                logger.exception("audit log failed for execution.commit.undo")

        return result

    async def _fire_referral_first_task(self, user_id: str) -> None:
        if self._referral_first_task_callback is not None:
            await self._referral_first_task_callback(user_id)
            return

        from src.services.referral_service import ReferralService

        referral_svc = ReferralService()
        await referral_svc.fire_first_task_for_referrer(user_id)

    async def _ensure_active_workspace_membership(
        self,
        execution: Any,
        *,
        actor_user_id: str,
    ) -> None:
        workspace_id = str(getattr(execution, "workspace_id", "") or "")
        if not workspace_id:
            return
        async with self._client() as dataservice:
            checker = getattr(dataservice, "workspace_has_active_membership", None)
            if not callable(checker):
                return
            result = checker(workspace_id=workspace_id, user_id=str(actor_user_id))
            if inspect.isawaitable(result):
                result = await result
            if result is False:
                raise ExecutionCommitNotFoundError(
                    f"execution {getattr(execution, 'id', '')} not found"
                )

    async def _sync_prism_bibliography(
        self,
        *,
        workspace_id: str,
        dataservice: AsyncDataServiceClient,
    ) -> None:
        """Materialize accepted Library sources into Prism's refs.bib."""
        try:
            await SourceBibliographyService(dataservice).sync_prism(
                workspace_id=workspace_id,
            )
        except Exception:
            logger.warning(
                "Failed to sync Prism bibliography after Library commit",
                extra={"workspace_id": workspace_id},
                exc_info=True,
            )

    async def _mark_commit_failed(
        self,
        *,
        execution_id: str,
        commit_token: str,
        error: BaseException,
        accepted_ids: list[str],
        rejected_ids: list[str],
        counts: dict[str, int],
        room_targets: dict[str, list[dict[str, Any]]],
    ) -> None:
        try:
            await self.execution.fail_execution_commit(
                execution_id=execution_id,
                commit_token=commit_token,
                error_text=str(error) or error.__class__.__name__,
                accepted_ids=accepted_ids,
                rejected_ids=rejected_ids,
                partial_counts=counts,
                partial_room_targets=room_targets,
                commit=True,
            )
        except Exception:
            logger.exception(
                "execution commit failure marker failed",
                extra={"execution_id": execution_id},
            )


def _empty_counts() -> dict[str, int]:
    return {key: 0 for key in _COUNT_ROOM_KEYS}


def _empty_room_targets() -> dict[str, list[dict[str, Any]]]:
    return {key: [] for key in _ROOM_TARGET_KEYS}


def _merge_counts(
    base: dict[str, int],
    incoming: dict[str, Any] | None,
) -> dict[str, int]:
    merged = {key: int(base.get(key, 0)) for key in _COUNT_ROOM_KEYS}
    for key in _COUNT_ROOM_KEYS:
        value = (incoming or {}).get(key, 0)
        merged[key] += int(value) if isinstance(value, int) and not isinstance(value, bool) else 0
    return merged


def _merge_room_targets(
    base: dict[str, list[dict[str, Any]]],
    incoming: dict[str, Any] | None,
) -> dict[str, list[dict[str, Any]]]:
    merged = _copy_room_targets(base)
    if not isinstance(incoming, dict):
        return merged
    seen = {
        _room_target_identity(room, target)
        for room, targets in merged.items()
        for target in targets
    }
    for room in _ROOM_TARGET_KEYS:
        targets = incoming.get(room)
        if not isinstance(targets, list):
            continue
        for target in targets:
            if not isinstance(target, dict):
                continue
            compact = dict(target)
            identity = _room_target_identity(room, compact)
            if identity in seen:
                continue
            merged[room].append(compact)
            seen.add(identity)
    return merged


def _commit_status_for_selection(
    *,
    selected_outputs: list[Any],
    selected_unit_ids: list[str] | None,
) -> str:
    if selected_unit_ids is not None:
        return "committed" if selected_unit_ids else "discarded"
    return "committed" if selected_outputs else "discarded"


def _committed_artifact_count(
    *,
    selected_outputs: list[Any],
    selected_unit_ids: list[str] | None,
) -> int:
    return len(selected_unit_ids) if selected_unit_ids is not None else len(selected_outputs)


def _room_target_identity(room: str, target: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        room,
        str(target.get("unit_id") or ""),
        str(target.get("item_id") or target.get("file_id") or target.get("artifact_id") or ""),
        str(target.get("path") or target.get("output_id") or ""),
    )


def _change_unit_materialization_progress(
    result_payload: dict[str, Any] | None,
    *,
    execution_id: str,
    accepted_unit_ids: list[str],
) -> dict[str, Any]:
    accepted = list(dict.fromkeys(accepted_unit_ids))
    accepted_set = set(accepted)
    empty = {
        "completed_unit_ids": [],
        "counts": _empty_counts(),
        "room_targets": _empty_room_targets(),
    }
    if not isinstance(result_payload, dict):
        return empty
    raw = result_payload.get(_CHANGE_UNIT_MATERIALIZATION_RESULT_KEY)
    if not isinstance(raw, dict):
        return empty
    raw_execution_id = raw.get("execution_id")
    if raw_execution_id and str(raw_execution_id) != str(execution_id):
        return empty
    raw_accepted_value = raw.get("accepted_unit_ids")
    raw_accepted = (
        [str(unit_id) for unit_id in raw_accepted_value]
        if isinstance(raw_accepted_value, list)
        else []
    )
    if raw_accepted and raw_accepted != accepted:
        return empty

    raw_completed_value = raw.get("completed_unit_ids")
    raw_completed = raw_completed_value if isinstance(raw_completed_value, list) else []
    completed = [
        str(unit_id)
        for unit_id in raw_completed
        if str(unit_id) in accepted_set
    ]
    if not completed:
        return empty

    room_targets = _empty_room_targets()
    completed_set = set(completed)
    for room, targets in _copy_room_targets(raw.get("room_targets")).items():
        room_targets[room] = [
            target
            for target in targets
            if str(target.get("unit_id") or "") in completed_set
        ]

    raw_counts = raw.get("counts")
    counts = raw_counts if isinstance(raw_counts, dict) else {}
    return {
        "completed_unit_ids": completed,
        "counts": {
            key: int(counts.get(key, 0))
            if isinstance(counts.get(key, 0), int)
            and not isinstance(counts.get(key, 0), bool)
            else 0
            for key in _COUNT_ROOM_KEYS
        },
        "room_targets": room_targets,
    }


def _build_change_unit_materialization_progress(
    *,
    execution_id: str,
    accepted_unit_ids: list[str],
    completed_unit_ids: set[str],
    counts: dict[str, int],
    room_targets: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    accepted = list(dict.fromkeys(accepted_unit_ids))
    ordered_completed = [unit_id for unit_id in accepted if unit_id in completed_unit_ids]
    return {
        "schema_version": "wenjin.change_unit_materialization.v1",
        "execution_id": execution_id,
        "accepted_unit_ids": accepted,
        "completed_unit_ids": ordered_completed,
        "counts": {key: int(counts.get(key, 0)) for key in _COUNT_ROOM_KEYS},
        "room_targets": _copy_room_targets(room_targets),
        "updated_at": datetime.now(UTC).isoformat(),
    }


def _noop_commit_response() -> dict[str, Any]:
    return {
        "committed": _empty_counts(),
        "room_targets": _empty_room_targets(),
    }


def _normalize_selected_ids(values: list[str], *, field_name: str) -> list[str]:
    if len(values) > _MAX_COMMIT_ID_COUNT:
        raise ValueError(f"{field_name} must contain at most {_MAX_COMMIT_ID_COUNT} ids")
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item_id = str(value or "").strip()
        if not item_id:
            raise ValueError(f"{field_name} must not contain blank ids")
        if len(item_id) > _MAX_COMMIT_ID_LENGTH:
            raise ValueError(f"{field_name} contains an id longer than {_MAX_COMMIT_ID_LENGTH} chars")
        if item_id in seen:
            continue
        result.append(item_id)
        seen.add(item_id)
    return result


def _validate_selected_outputs_against_change_set(
    result_payload: dict[str, Any] | None,
    selected_outputs: list[Any],
) -> None:
    if not selected_outputs or result_payload is None:
        return
    raw_change_set = result_payload.get("change_set")
    if not isinstance(raw_change_set, dict):
        return
    try:
        change_set = ChangeSet.model_validate(raw_change_set)
    except Exception as exc:
        raise ValueError("execution ChangeSet is invalid; refresh and review changes again") from exc

    review_state = _normalized_change_set_review_state(
        result_payload.get("change_set_review_state")
    )
    units_by_output_id: dict[str, list[Any]] = {}
    for unit in change_set.units:
        output_id = _clean_optional_id(unit.provenance.get("output_id"))
        if not output_id:
            continue
        units_by_output_id.setdefault(output_id, []).append(unit)

    rejected_output_ids: list[str] = []
    blocked_output_ids: list[str] = []
    missing_output_ids: list[str] = []
    for output in selected_outputs:
        output_id = _clean_optional_id(getattr(output, "id", None))
        if not output_id:
            continue
        units = units_by_output_id.get(output_id) or []
        if not units:
            missing_output_ids.append(output_id)
            continue
        if any(unit.default_apply_state == "blocked" for unit in units):
            blocked_output_ids.append(output_id)
            continue
        if any(_effective_change_unit_state(unit.id, unit.default_apply_state, review_state) != "accepted" for unit in units):
            rejected_output_ids.append(output_id)

    if missing_output_ids:
        raise ValueError(
            "selected output id(s) are not present in this execution ChangeSet: "
            + _format_limited_id_list(sorted(missing_output_ids))
        )
    if blocked_output_ids:
        raise ValueError(
            "selected output id(s) are blocked and cannot be saved directly: "
            + _format_limited_id_list(sorted(blocked_output_ids))
        )
    if rejected_output_ids:
        raise ValueError(
            "selected output id(s) must be accepted in Review & Changes before saving: "
            + _format_limited_id_list(sorted(rejected_output_ids))
        )


def _result_has_change_set(result_payload: dict[str, Any] | None) -> bool:
    return isinstance(result_payload, dict) and isinstance(result_payload.get("change_set"), dict)


def _select_outputs_for_change_units(
    result_payload: dict[str, Any] | None,
    *,
    report: TaskReport,
    accepted_unit_ids: list[str],
) -> dict[str, Any]:
    if result_payload is None:
        raise ValueError("accepted_unit_ids can only be used when execution has a result payload")
    raw_change_set = result_payload.get("change_set")
    if not isinstance(raw_change_set, dict):
        raise ValueError("accepted_unit_ids can only be used when execution has a ChangeSet")
    try:
        change_set = ChangeSet.model_validate(raw_change_set)
    except Exception as exc:
        raise ValueError("execution ChangeSet is invalid; refresh and review changes again") from exc

    selected_unit_ids = _normalize_selected_ids(
        accepted_unit_ids,
        field_name="accepted_unit_ids",
    )
    units_by_id = {unit.id: unit for unit in change_set.units}
    missing_unit_ids = sorted(set(selected_unit_ids) - set(units_by_id))
    if missing_unit_ids:
        raise ValueError(
            "accepted_unit_ids contains unknown unit id(s): "
            + _format_limited_id_list(missing_unit_ids)
        )

    review_state = _normalized_change_set_review_state(
        result_payload.get("change_set_review_state")
    )
    outputs_by_id = {output.id: output for output in report.outputs}
    selected_output_ids: list[str] = []
    blocked_unit_ids: list[str] = []
    unaccepted_unit_ids: list[str] = []
    unsupported_unit_ids: list[str] = []
    missing_output_ids: list[str] = []
    seen_output_ids: set[str] = set()

    for unit_id in selected_unit_ids:
        unit = units_by_id[unit_id]
        if unit.default_apply_state == "blocked":
            blocked_unit_ids.append(unit_id)
            continue
        if _effective_change_unit_state(unit.id, unit.default_apply_state, review_state) != "accepted":
            unaccepted_unit_ids.append(unit_id)
            continue
        output_id = _clean_optional_id(
            unit.provenance.get("output_id") or unit.provenance.get("source_output_id")
        )
        if not output_id:
            if unit.materialization is None:
                unsupported_unit_ids.append(unit_id)
            continue
        if output_id not in outputs_by_id:
            missing_output_ids.append(output_id)
            continue
        if output_id not in seen_output_ids:
            selected_output_ids.append(output_id)
            seen_output_ids.add(output_id)

    if blocked_unit_ids:
        raise ValueError(
            "accepted_unit_ids contains blocked unit(s): "
            + _format_limited_id_list(blocked_unit_ids)
        )
    if unaccepted_unit_ids:
        raise ValueError(
            "accepted_unit_ids must be accepted in Review & Changes before saving: "
            + _format_limited_id_list(unaccepted_unit_ids)
        )
    if unsupported_unit_ids:
        raise ValueError(
            "accepted_unit_ids contains unit(s) without materializable output provenance: "
            + _format_limited_id_list(unsupported_unit_ids)
        )
    if missing_output_ids:
        raise ValueError(
            "accepted_unit_ids references missing output id(s): "
            + _format_limited_id_list(sorted(set(missing_output_ids)))
        )

    return {
        "change_set": change_set,
        "unit_ids": selected_unit_ids,
        "outputs": [output for output in report.outputs if output.id in seen_output_ids],
    }


def _compact_change_set_after_commit(
    result_payload: dict[str, Any],
    *,
    commit_state: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    delete_keys = [key for key in _CHANGE_SET_TEMP_RESULT_KEYS if key in result_payload]
    if not delete_keys:
        return result_payload, []

    next_result = dict(result_payload)
    receipt = _change_set_receipt(result_payload, commit_state=commit_state)
    for key in delete_keys:
        next_result.pop(key, None)
    next_result["change_set_receipt"] = receipt
    return next_result, delete_keys


def _change_set_receipt(
    result_payload: dict[str, Any],
    *,
    commit_state: dict[str, Any],
) -> dict[str, Any]:
    raw_change_set = result_payload.get("change_set")
    change_set = raw_change_set if isinstance(raw_change_set, dict) else {}
    review_state = _normalized_change_set_review_state(
        result_payload.get("change_set_review_state")
    )
    units = change_set.get("units")
    unit_count = len(units) if isinstance(units, list) else 0
    return {
        "schema_version": "wenjin.change_set.receipt.v1",
        "retention": "compacted_after_commit",
        "execution_id": _clean_optional_id(change_set.get("execution_id")),
        "workspace_id": _clean_optional_id(change_set.get("workspace_id")),
        "write_mode": _clean_optional_id(change_set.get("write_mode")),
        "summary": _clean_optional_id(change_set.get("summary")),
        "unit_count": unit_count,
        "accepted_unit_ids": sorted(review_state["accepted"]),
        "rejected_unit_ids": sorted(review_state["rejected"]),
        "undone_unit_ids": sorted(review_state["undone"]),
        "accepted_output_ids": list(commit_state.get("accepted_ids") or []),
        "rejected_output_ids": list(commit_state.get("rejected_ids") or []),
        "committed_at": commit_state.get("committed_at"),
        "targets": _receipt_room_targets(commit_state.get("room_targets")),
    }


def _receipt_room_targets(value: Any) -> dict[str, list[dict[str, Any]]]:
    room_targets = _copy_room_targets(value if isinstance(value, dict) else {})
    receipt_targets: dict[str, list[dict[str, Any]]] = {}
    for room in _ROOM_TARGET_KEYS:
        items: list[dict[str, Any]] = []
        for target in room_targets.get(room, []):
            compact = {
                key: target[key]
                for key in _RECEIPT_ROOM_TARGET_KEYS
                if key in target and target[key] is not None
            }
            if compact:
                items.append(compact)
        receipt_targets[room] = items
    return receipt_targets


def _normalized_change_set_review_state(value: Any) -> dict[str, set[str]]:
    raw = value if isinstance(value, dict) else {}
    return {
        "accepted": set(_normalize_review_ids(raw.get("accepted_unit_ids"))),
        "rejected": set(_normalize_review_ids(raw.get("rejected_unit_ids"))),
        "undone": set(_normalize_review_ids(raw.get("undone_unit_ids"))),
    }


def _normalize_review_ids(value: Any) -> list[str]:
    if not isinstance(value, list | tuple | set | frozenset):
        return []
    return [item_id for item_id in (_clean_optional_id(item) for item in value) if item_id]


def _effective_change_unit_state(
    unit_id: str,
    default_state: str,
    review_state: dict[str, set[str]],
) -> str:
    if unit_id in review_state["undone"]:
        return "undone"
    if unit_id in review_state["rejected"]:
        return "rejected"
    if unit_id in review_state["accepted"]:
        return "accepted"
    return default_state


def _clean_optional_id(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _format_limited_id_list(values: list[str], *, limit: int = 8) -> str:
    visible = values[:limit]
    suffix = f" (and {len(values) - limit} more)" if len(values) > limit else ""
    return ", ".join(visible) + suffix


def _report_has_bulk_unsafe_outputs(report: TaskReport) -> bool:
    if any(_output_requires_explicit_selection(output) for output in report.outputs):
        return True
    if report.review_packet is not None:
        if any(
            _review_item_requires_explicit_selection(item.model_dump())
            for item in report.review_packet.items
        ):
            return True
    return any(_review_item_requires_explicit_selection(item) for item in report.review_items)


def _output_requires_explicit_selection(output: Any) -> bool:
    if output.default_checked is False:
        return True
    if output.kind in _BULK_UNSAFE_KINDS:
        return True

    data = output.data.model_dump() if hasattr(output.data, "model_dump") else {}
    if output.kind == "document":
        data = {key: value for key, value in data.items() if key != "content"}
    if output.kind == "memory_fact" and _contains_memory_strong_unsafe_phrase(
        data.get("content")
    ):
        return True
    return _contains_structured_bulk_unsafe_signal(data)


def _review_item_requires_explicit_selection(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    if item.get("default_checked") is False:
        return True
    if item.get("can_commit") is False:
        return True
    if str(item.get("kind") or "").lower() in _BULK_UNSAFE_REVIEW_KINDS:
        return True

    risk = item.get("risk")
    if isinstance(risk, dict):
        level = str(risk.get("level") or "").lower()
        if level in _BULK_UNSAFE_REVIEW_RISK_LEVELS:
            return True

    ref_fields = ("claim_refs", "evidence_refs", "quality_surfaces")
    if any(item.get(field) for field in ref_fields):
        return True
    return _contains_structured_bulk_unsafe_signal(
        item,
        item.get("source"),
        item.get("preview"),
        item.get("provenance"),
    )


def _contains_structured_bulk_unsafe_signal(*values: Any) -> bool:
    for value in values:
        if value is None:
            continue
        if isinstance(value, dict):
            for key, nested_value in value.items():
                if _structured_key_value_requires_explicit_selection(key, nested_value):
                    return True
                if isinstance(nested_value, (dict, list)) and _contains_structured_bulk_unsafe_signal(
                    nested_value
                ):
                    return True
            continue
        if isinstance(value, list):
            if _contains_structured_bulk_unsafe_signal(*value):
                return True
            continue
    return False


def _structured_key_value_requires_explicit_selection(key: Any, value: Any) -> bool:
    normalized_key = _normalized_signal_text(key)
    if normalized_key == "default_checked" and value is False:
        return True
    if normalized_key == "can_commit" and value is False:
        return True
    if normalized_key in _BULK_UNSAFE_FLAG_KEYS:
        return _truthy_metadata_flag(value)
    if normalized_key in _BULK_UNSAFE_REF_KEYS:
        return bool(value)
    if normalized_key == "quality_surfaces":
        return bool(value)
    if normalized_key in _BULK_UNSAFE_STATUS_KEYS:
        return _status_value_requires_explicit_selection(value)
    return _short_structured_value_requires_explicit_selection(value)


def _status_value_requires_explicit_selection(value: Any) -> bool:
    if isinstance(value, dict):
        level = value.get("level")
        if level is not None and _status_value_requires_explicit_selection(level):
            return True
        return _contains_structured_bulk_unsafe_signal(value)
    if isinstance(value, list):
        return any(_status_value_requires_explicit_selection(item) for item in value)
    return _normalized_signal_text(value) in _BULK_UNSAFE_STATUS_VALUES


def _short_structured_value_requires_explicit_selection(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    if len(value) > 80:
        return False
    return _normalized_signal_text(value) in _BULK_UNSAFE_STRUCTURED_VALUES


def _contains_memory_strong_unsafe_phrase(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    text = _phrase_text(value)
    return any(phrase in text for phrase in _MEMORY_STRONG_UNSAFE_PHRASES)


def _normalized_signal_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")


def _phrase_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _truthy_metadata_flag(value: Any) -> bool:
    if value is False or value is None:
        return False
    if isinstance(value, str) and _normalized_signal_text(value) in {"", "0", "false", "no"}:
        return False
    return bool(value)


async def _read_commit_cache(redis: Any, cache_key: str) -> dict[str, Any] | None:
    try:
        cached = await redis.get(cache_key)
    except Exception:
        logger.warning(
            "execution commit idempotency cache read failed",
            extra={"cache_key": cache_key},
            exc_info=True,
        )
        return None
    if not cached:
        return None
    try:
        cached_response = json.loads(cached)
    except (TypeError, ValueError):
        logger.warning(
            "execution commit idempotency cache payload was invalid",
            extra={"cache_key": cache_key},
            exc_info=True,
        )
        return None
    if _cached_response_has_valid_commit_state(cached_response):
        return cast(dict[str, Any], cached_response)
    return None


async def _write_commit_cache(
    redis: Any,
    cache_key: str,
    result: dict[str, Any],
) -> None:
    try:
        await redis.set(cache_key, json.dumps(result), ex=86400)  # 24h
    except Exception:
        logger.warning(
            "execution commit idempotency cache write failed",
            extra={"cache_key": cache_key},
            exc_info=True,
        )


def _cached_response_has_valid_commit_state(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and _valid_commit_state(value.get("commit_state")) is not None
    )


def _build_commit_state(
    *,
    status: str,
    accepted_ids: list[str],
    rejected_ids: list[str],
    counts: dict[str, int],
    room_targets: dict[str, list[dict[str, Any]]],
    committed_at: str,
    accepted_unit_ids: list[str] | None = None,
) -> dict[str, Any]:
    commit_state: dict[str, Any] = {
        "status": status,
        "accepted_ids": list(accepted_ids),
        "rejected_ids": list(rejected_ids),
        "counts": {key: int(counts.get(key, 0)) for key in _COUNT_ROOM_KEYS},
        "room_targets": _copy_room_targets(room_targets),
        "committed_at": committed_at,
    }
    if accepted_unit_ids is not None:
        commit_state["accepted_unit_ids"] = list(accepted_unit_ids)
    return commit_state


def _build_reverted_commit_state(
    commit_state: dict[str, Any],
    *,
    reverted_at: str,
    reverted_by: str,
    revert_counts: dict[str, int],
    revert_skipped: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    reverted_state = dict(commit_state)
    reverted_state["status"] = "reverted"
    reverted_state["reverted_at"] = reverted_at
    reverted_state["reverted_by"] = reverted_by
    reverted_state["revert_counts"] = {
        key: int(revert_counts.get(key, 0)) for key in _COUNT_ROOM_KEYS
    }
    if revert_skipped:
        reverted_state["revert_skipped"] = revert_skipped
    return reverted_state


def _non_empty_revert_skipped(
    skipped: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]] | None:
    result = {room: targets for room, targets in skipped.items() if targets}
    return result or None


def _manual_revert_skip_target(target: dict[str, Any]) -> dict[str, Any]:
    skipped = {
        key: value
        for key, value in target.items()
        if key in {"output_id", "item_id", "unit_id", "settings_keys"} and value is not None
    }
    skipped["reason"] = "manual_revert_required"
    return skipped


def _ensure_commit_state_persisted(
    persisted_execution: Any,
    expected_commit_state: dict[str, Any],
) -> None:
    result = _execution_result_payload(persisted_execution)
    persisted_commit_state = (
        _valid_commit_state(result.get("commit_state"))
        if result is not None
        else None
    )
    if persisted_commit_state != expected_commit_state:
        raise ExecutionCommitPersistenceError(
            "commit_state persistence failed for execution commit"
        )


def _execution_result_payload(execution: Any) -> dict[str, Any] | None:
    if execution is None:
        return None
    result = getattr(execution, "result", None)
    if isinstance(result, dict):
        return result
    result_json = getattr(execution, "result_json", None)
    if isinstance(result_json, dict):
        return result_json
    return None


def _valid_commit_state(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    if value.get("status") not in {"committed", "discarded", "reverted"}:
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
    for key in _COUNT_ROOM_KEYS:
        count = counts.get(key)
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            return None

    room_targets = value.get("room_targets")
    if not isinstance(room_targets, dict):
        return None
    for key in _ROOM_TARGET_KEYS:
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
    reverted_at = value.get("reverted_at")
    if reverted_at is not None and not isinstance(reverted_at, str):
        return None
    reverted_by = value.get("reverted_by")
    if reverted_by is not None and not isinstance(reverted_by, str):
        return None
    revert_counts = value.get("revert_counts")
    if revert_counts is not None:
        if not isinstance(revert_counts, dict):
            return None
        for key in _COUNT_ROOM_KEYS:
            count = revert_counts.get(key)
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                return None
    revert_skipped = value.get("revert_skipped")
    if revert_skipped is not None and not isinstance(revert_skipped, dict):
        return None
    return value


def _response_from_commit_state(commit_state: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "committed": {
            key: int(commit_state["counts"][key])
            for key in _COUNT_ROOM_KEYS
        },
        "room_targets": _copy_room_targets(commit_state["room_targets"]),
        "commit_state": commit_state,
    }
    if "review_batch_id" in commit_state:
        result["review_batch_id"] = commit_state["review_batch_id"]
    return result


def _copy_room_targets(
    room_targets: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    copied: dict[str, list[dict[str, Any]]] = {}
    for key in _ROOM_TARGET_KEYS:
        copied[key] = []
        for target in room_targets.get(key, []):
            copied_target: dict[str, Any] = {
                "output_id": str(target["output_id"]),
                "item_id": str(target["item_id"]),
            }
            for extra_key, extra_value in target.items():
                if extra_key in copied_target:
                    continue
                if extra_value is None:
                    continue
                if isinstance(extra_value, bool):
                    copied_target[extra_key] = extra_value
                elif isinstance(extra_value, (str, int, float)):
                    copied_target[extra_key] = str(extra_value)
            copied[key].append(copied_target)
    return copied


def _is_str_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


async def _existing_prism_files_by_path(
    *,
    dataservice: AsyncDataServiceClient,
    workspace_id: str,
) -> dict[str, Any]:
    try:
        surface = await dataservice.get_prism_surface(workspace_id)
    except Exception:
        logger.warning(
            "Failed to load existing Prism surface before execution commit",
            extra={"workspace_id": workspace_id},
            exc_info=True,
        )
        return {}
    if surface is None:
        return {}
    return {str(file.path): file for file in surface.files if str(file.path or "").strip()}


def _document_prism_payload(
    *,
    execution: Any,
    output_id: str,
    data: dict[str, Any],
) -> PrismWorkspaceFileUpsertPayload | None:
    name = _first_text(data.get("name"), output_id) or output_id
    mime_type = _first_text(data.get("mime_type")) or "text/markdown"
    doc_kind = _first_text(data.get("doc_kind")) or "generic"
    inline_content = data.get("content")
    content_inline = str(inline_content) if inline_content is not None else None
    pointer_path = _first_text(data.get("storage_path"))
    if content_inline is None and pointer_path:
        content_inline = f"# {name}\n\nGenerated file path: `{pointer_path}`\n"
        mime_type = "text/markdown"
    if content_inline is None:
        return None
    path = _prism_output_path(
        execution=execution,
        output_id=output_id,
        name=name,
        mime_type=mime_type,
        doc_kind=doc_kind,
    )
    content_hash = hashlib.sha256(content_inline.encode("utf-8")).hexdigest()
    return PrismWorkspaceFileUpsertPayload(
        path=path,
        file_role=doc_kind,
        mime_type=mime_type,
        metadata_json={
            "kind": doc_kind,
            "name": name,
            "source": "execution_commit",
            "output_id": output_id,
        },
        content_inline=content_inline,
        content_hash=content_hash,
        created_by=f"execution:{getattr(execution, 'id', '') or output_id}",
    )


def _prism_output_path(
    *,
    execution: Any,
    output_id: str,
    name: str,
    mime_type: str,
    doc_kind: str,
) -> str:
    extension = _prism_extension_for_document(name=name, mime_type=mime_type, doc_kind=doc_kind)
    filename = _safe_prism_filename(name=name, output_id=output_id, extension=extension)
    feature_id = str(getattr(execution, "feature_id", "") or "").lower()
    if extension in {".tex", ".bib"}:
        directory = "paper"
    elif "software_copyright" in feature_id or "copyright" in feature_id:
        directory = "docs/software-copyright"
    elif "math_modeling" in feature_id or "modeling" in feature_id:
        directory = "docs/math-modeling"
    else:
        directory = "docs/generated"
    return f"{directory}/{filename}"


def _prism_extension_for_document(*, name: str, mime_type: str, doc_kind: str) -> str:
    raw_name = str(name or "")
    suffix = "." + raw_name.rsplit(".", 1)[-1].lower() if "." in raw_name else ""
    if suffix in _PRISM_SUPPORTED_EXTENSIONS:
        return suffix
    normalized_mime = str(mime_type or "").lower()
    if "latex" in normalized_mime or doc_kind == "latex":
        return ".tex"
    if "bibtex" in normalized_mime or doc_kind == "bibtex":
        return ".bib"
    if "svg" in normalized_mime:
        return ".svg"
    if "png" in normalized_mime:
        return ".png"
    if "jpeg" in normalized_mime or "jpg" in normalized_mime:
        return ".jpg"
    if "webp" in normalized_mime:
        return ".webp"
    return ".md"


def _safe_prism_filename(*, name: str, output_id: str, extension: str) -> str:
    raw_name = str(name or output_id).rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if "." in raw_name:
        raw_name = raw_name.rsplit(".", 1)[0]
    slug = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+", "-", raw_name).strip(".-")
    if not slug:
        slug = re.sub(r"[^A-Za-z0-9._-]+", "-", output_id).strip(".-") or "document"
    return f"{slug}{extension}"


def _prism_room_target(
    *,
    output_id: str,
    file_id: str,
    path: str,
    version_id: str,
    content_hash: str,
    previous_version_id: str | None,
    previous_hash: str | None,
    created_file: bool,
) -> dict[str, Any]:
    return {
        "output_id": output_id,
        "item_id": file_id,
        "file_id": file_id,
        "path": path,
        "version_id": version_id,
        "content_hash": content_hash,
        "previous_version_id": previous_version_id,
        "previous_hash": previous_hash,
        "created_file": created_file,
    }


def _truthy_target_flag(value: Any) -> bool:
    return value is True or str(value).lower() == "true"


def _citation_key(data: dict[str, Any]) -> str:
    raw = str(data.get("citation_key") or data.get("title") or "source").lower()
    key = _CITATION_KEY_RE.sub("_", raw).strip("_")
    year = data.get("year")
    if year and str(year) not in key:
        key = f"{key}_{year}"
    return key or "source"


def _source_import_payload(
    *,
    workspace_id: str,
    execution_id: str,
    data: dict[str, Any],
) -> SourceImportPayload:
    metadata = dict(data.get("metadata") or {})
    provider = _first_text(
        data.get("source"),
        metadata.get("source"),
        metadata.get("provider"),
    )
    external_id = _first_text(
        data.get("external_id"),
        metadata.get("external_id"),
        metadata.get("paperId"),
        metadata.get("paper_id"),
        metadata.get("corpusId"),
    )
    evidence_level = _source_evidence_level(data, metadata, provider, external_id)
    verified_at = _verified_at(data, metadata, evidence_level)

    if provider:
        metadata.setdefault("source", provider)
    if external_id:
        metadata.setdefault("external_id", external_id)

    external_ids = []
    if provider and external_id:
        external_ids.append(
            SourceExternalIdCreatePayload(
                provider=provider,
                external_id=external_id,
                url=_first_text(data.get("url"), metadata.get("url")),
                metadata_json=metadata,
            )
        )

    return SourceImportPayload(
        workspace_id=workspace_id,
        source_kind="paper",
        title=data["title"],
        authors_json=list(data.get("authors") or []),
        year=_safe_int(data.get("year")),
        venue=_first_text(data.get("venue"), metadata.get("venue")),
        doi=_first_text(data.get("doi"), metadata.get("doi")),
        url=_first_text(data.get("url"), metadata.get("url")),
        abstract=_first_text(data.get("abstract"), metadata.get("abstract")),
        citation_count=_safe_int(
            data.get("citation_count")
            or metadata.get("citation_count")
            or metadata.get("citations_count")
            or metadata.get("citations")
        ),
        ingest_kind=provider or "execution",
        ingest_label=f"execution:{execution_id}",
        ingest_execution_id=execution_id,
        verified_at=verified_at,
        library_status="included",
        evidence_level=evidence_level,
        citation_key=_citation_key(data),
        bibtex_fields_json=metadata,
        external_ids=external_ids,
    )


def _first_text(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _safe_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _source_evidence_level(
    data: dict[str, Any],
    metadata: dict[str, Any],
    provider: str | None,
    external_id: str | None,
) -> str:
    raw_level = _first_text(data.get("evidence_level"), metadata.get("evidence_level"))
    if raw_level in {"indexed_fulltext", "uploaded_fulltext", "external_verified"}:
        return raw_level
    if provider == "semantic_scholar" and external_id:
        return "external_verified"
    if raw_level == "semantic_scholar_metadata" and provider == "semantic_scholar":
        return "external_verified"
    return raw_level or "metadata_only"


def _verified_at(
    data: dict[str, Any],
    metadata: dict[str, Any],
    evidence_level: str,
) -> datetime | None:
    raw_value = data.get("verified_at") or metadata.get("verified_at")
    if isinstance(raw_value, datetime):
        return raw_value
    if isinstance(raw_value, str) and raw_value.strip():
        try:
            return datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
        except ValueError:
            logger.debug("Ignoring invalid source verified_at value: %s", raw_value)
    if evidence_level != "metadata_only":
        return datetime.now(UTC)
    return None
