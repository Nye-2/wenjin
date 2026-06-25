"""Execution commit service — writes accepted ResultOutputs to rooms in one pass.

Spec §4.7.5: All outputs go in one pass; Run History always recorded (regardless
of user selection). Idempotent via idempotency_key (Redis-backed cache, 24h TTL).
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, cast

from src.agents.contracts.task_report import TaskReport
from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.asset import WorkspaceAssetCreatePayload
from src.dataservice_client.contracts.execution import ExecutionEventCreatePayload
from src.dataservice_client.contracts.rooms import RoomCandidatePayload
from src.dataservice_client.contracts.source import (
    SourceExternalIdCreatePayload,
    SourceImportPayload,
)
from src.dataservice_client.provider import dataservice_client
from src.services.execution_service import ExecutionService
from src.services.references import SourceBibliographyService
from src.workspace_events import publish_workspace_event

logger = logging.getLogger(__name__)

# Synthetic storage path used for inline DataService asset documents. The real
# content lives in asset metadata so gateway and worker do not need a shared
# filesystem for generated markdown.
_INLINE_DOC_PATH_PREFIX = "inline://"
_DOCUMENTS_ROOM_SOURCE_KIND = "documents_room"
_CITATION_KEY_RE = re.compile(r"[^a-z0-9]+")
_COUNT_ROOM_KEYS = ("library", "documents", "memory", "decisions", "tasks")
_ROOM_TARGET_KEYS = ("documents", "library", "memory", "decisions", "tasks")
_COMMIT_LOCK_TTL_SECONDS = 60
_ALLOWED_OVERRIDE_FIELDS: dict[str, set[str]] = {
    "document": {"content", "name", "doc_kind"},
    "library_item": {"title", "authors", "year", "doi", "url", "abstract"},
    "memory_fact": {"category", "content", "confidence"},
    "decision": {"key", "value"},
    "task": {"title", "description", "priority"},
}


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
        output_overrides: dict[str, dict[str, Any]] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Commit accepted outputs to rooms and record run history.

        Args:
            execution_id: The execution to commit outputs for.
            actor_user_id: Authenticated user attempting the writeback.
            accept_all: If True, all outputs in the TaskReport are written.
            accepted_ids: Specific output IDs to write (ignored when accept_all=True).
            output_overrides: Per-output staged edits applied before materializing rooms.
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
        if accept_all:
            selection_provided = True
            if report.status != "completed":
                raise ValueError(
                    "accept_all is only allowed for completed executions; "
                    "use accepted_ids for partial results"
                )
            selected = list(report.outputs)
        elif accepted_ids is not None:
            selection_provided = True
            id_set = set(accepted_ids)
            missing_ids = sorted(id_set - set(output_by_id))
            if missing_ids:
                raise ValueError(
                    "accepted_ids contains unknown output id(s): "
                    + ", ".join(missing_ids)
                )
            selected = [o for o in report.outputs if o.id in id_set]
        else:
            selection_provided = False
            selected = []

        overrides = output_overrides or {}
        selected_ids = {output.id for output in selected}
        unknown_override_ids = sorted(set(overrides) - set(output_by_id))
        if unknown_override_ids:
            raise ValueError(
                "output_overrides contains unknown output id(s): "
                + ", ".join(unknown_override_ids)
            )
        unaccepted_override_ids = sorted(set(overrides) - selected_ids)
        if unaccepted_override_ids:
            raise ValueError(
                "output_overrides contains unaccepted output id(s): "
                + ", ".join(unaccepted_override_ids)
            )
        if overrides:
            selected = [
                _apply_output_override(output, overrides.get(output.id))
                for output in selected
            ]

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
            if not claim_execution.result or "task_report" not in claim_execution.result:
                raise ValueError(f"execution {execution_id} has no task_report")
            execution = claim_execution
            claimed_for_materialization = True

            room_candidates: list[RoomCandidatePayload] = []

            # 5. Write to rooms
            async with self._client() as dataservice:
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
                        # Agent-generated documents carry their content inline; the
                        # document service stores that content as DataService asset
                        # metadata. File-backed documents keep their storage_path.
                        inline_content = data.get("content")
                        existing_path = data.get("storage_path")
                        if not existing_path and not inline_content:
                            logger.warning(
                                "Skipping document commit '%s' for execution %s: no "
                                "storage_path and no inline content provided",
                                data.get("name"),
                                execution_id,
                            )
                            continue

                        if existing_path:
                            storage_path = existing_path
                            size_bytes = int(data.get("size_bytes", 0))
                            metadata_extra: dict[str, Any] = {}
                        else:
                            inline_content_text = str(inline_content)
                            storage_path = f"{_INLINE_DOC_PATH_PREFIX}{output.id}"
                            size_bytes = len(inline_content_text.encode("utf-8"))
                            metadata_extra = {"content": inline_content_text}

                        payload = {
                            "workspace_id": execution.workspace_id,
                            "name": data["name"],
                            "asset_kind": data.get("doc_kind", "draft"),
                            "mime_type": data.get("mime_type") or "text/markdown",
                            "storage_path": storage_path,
                            "size_bytes": size_bytes,
                            "parent_asset_id": data.get("parent_id"),
                            "created_by": f"execution:{execution_id}",
                            "source_kind": _DOCUMENTS_ROOM_SOURCE_KIND,
                            "source_id": output.id,
                        }
                        metadata_extra.setdefault("kind", payload["asset_kind"])
                        if metadata_extra:
                            payload["metadata_json"] = metadata_extra
                        doc = await dataservice.register_asset(
                            WorkspaceAssetCreatePayload(**payload)
                        )
                        counts["documents"] += 1
                        room_targets["documents"].append(
                            {"output_id": output.id, "item_id": doc.id}
                        )

                    elif kind == "memory_fact":
                        room_candidates.append(
                            RoomCandidatePayload(
                                source_item_id=output.id,
                                target_kind="memory_fact",
                                title=f"Memory fact: {data['category']}",
                                summary=data["content"],
                                payload_json={
                                    "category": data["category"],
                                    "content": data["content"],
                                    "confidence": data.get("confidence", 1.0),
                                },
                                preview_json={"content": data["content"]},
                                provenance_json={
                                    "execution_id": execution_id,
                                    "output_id": output.id,
                                },
                            )
                        )

                    elif kind == "decision":
                        room_candidates.append(
                            RoomCandidatePayload(
                                source_item_id=output.id,
                                target_kind="decision",
                                title=f"Decision: {data['key']}",
                                summary=data["value"],
                                payload_json={
                                    "key": data["key"],
                                    "value": data["value"],
                                    "confidence": data.get("confidence", 1.0),
                                    "extracted_by": f"execution:{execution_id}",
                                },
                                preview_json={"key": data["key"], "value": data["value"]},
                                provenance_json={
                                    "execution_id": execution_id,
                                    "output_id": output.id,
                                },
                            )
                        )

                    elif kind == "task":
                        priority = data["priority"] if isinstance(data.get("priority"), int) else 0
                        room_candidates.append(
                            RoomCandidatePayload(
                                source_item_id=output.id,
                                target_kind="workspace_task",
                                title=f"Task: {data['title']}",
                                summary=data.get("description"),
                                payload_json={
                                    "title": data["title"],
                                    "description": data.get("description"),
                                    "priority": priority,
                                    "related_execution_ids": [execution_id],
                                    "created_by": f"execution:{execution_id}",
                                },
                                preview_json={"title": data["title"]},
                                provenance_json={
                                    "execution_id": execution_id,
                                    "output_id": output.id,
                                },
                            )
                        )

                room_review_result = None
                if room_candidates:
                    room_review_result = await dataservice.stage_and_apply_room_candidates(
                        workspace_id=execution.workspace_id,
                        execution_id=execution_id,
                        candidates=room_candidates,
                    )
                    for key, value in room_review_result.counts.items():
                        if key in counts:
                            counts[key] += value
                    for item in room_review_result.item_results:
                        room = item.get("room")
                        source_item_id = item.get("source_item_id")
                        record_id = item.get("record_id")
                        if room in room_targets and source_item_id and record_id:
                            room_targets[room].append(
                                {
                                    "output_id": str(source_item_id),
                                    "item_id": str(record_id),
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
                            "artifact_count": len(selected),
                        },
                    ),
                )

            committed_at = datetime.now(UTC).isoformat()
            accepted_output_ids = [output.id for output in selected]
            accepted_output_id_set = set(accepted_output_ids)
            commit_state = _build_commit_state(
                status="committed" if selected else "discarded",
                accepted_ids=accepted_output_ids,
                rejected_ids=[
                    output.id
                    for output in report.outputs
                    if output.id not in accepted_output_id_set
                ],
                counts=counts,
                room_targets=room_targets,
                committed_at=committed_at,
                review_batch_id=(
                    room_review_result.review_batch_id
                    if room_review_result is not None
                    else None
                ),
            )
            result = _response_from_commit_state(commit_state)
            if room_review_result is not None:
                result["review_batch_id"] = room_review_result.review_batch_id
                result["room_review_results"] = room_review_result.item_results

            result_payload = dict(execution.result)
            result_payload["commit_state"] = commit_state
            persisted_execution = await self.execution.finalize_execution_commit(
                execution_id,
                result=result_payload,
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
                        "documents",
                        "library",
                        "memory",
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

    async def _fire_referral_first_task(self, user_id: str) -> None:
        if self._referral_first_task_callback is not None:
            await self._referral_first_task_callback(user_id)
            return

        from src.services.referral_service import ReferralService

        referral_svc = ReferralService()
        await referral_svc.fire_first_task_for_referrer(user_id)

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
        room_targets: dict[str, list[dict[str, str]]],
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


def _empty_room_targets() -> dict[str, list[dict[str, str]]]:
    return {key: [] for key in _ROOM_TARGET_KEYS}


def _noop_commit_response() -> dict[str, Any]:
    return {
        "committed": _empty_counts(),
        "room_targets": _empty_room_targets(),
    }


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
    room_targets: dict[str, list[dict[str, str]]],
    committed_at: str,
    review_batch_id: str | None,
) -> dict[str, Any]:
    commit_state: dict[str, Any] = {
        "status": status,
        "accepted_ids": list(accepted_ids),
        "rejected_ids": list(rejected_ids),
        "counts": {key: int(counts.get(key, 0)) for key in _COUNT_ROOM_KEYS},
        "room_targets": _copy_room_targets(room_targets),
        "committed_at": committed_at,
    }
    if review_batch_id is not None:
        commit_state["review_batch_id"] = review_batch_id
    return commit_state


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
    return value


def _response_from_commit_state(commit_state: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "committed": {
            key: int(commit_state["counts"].get(key, 0))
            for key in _COUNT_ROOM_KEYS
        },
        "room_targets": _copy_room_targets(commit_state["room_targets"]),
        "commit_state": commit_state,
    }
    if "review_batch_id" in commit_state:
        result["review_batch_id"] = commit_state["review_batch_id"]
    return result


def _copy_room_targets(
    room_targets: dict[str, list[dict[str, str]]],
) -> dict[str, list[dict[str, str]]]:
    copied: dict[str, list[dict[str, str]]] = {}
    for key in _ROOM_TARGET_KEYS:
        copied[key] = [
            {
                "output_id": str(target["output_id"]),
                "item_id": str(target["item_id"]),
            }
            for target in room_targets.get(key, [])
        ]
    return copied


def _is_str_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


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


def _apply_output_override(output: Any, override: dict[str, Any] | None) -> Any:
    """Overlay allowed staged edits onto a TaskReport output model."""
    if not override:
        return output

    unknown_keys = sorted(set(override) - {"data", "preview"})
    if unknown_keys:
        raise ValueError(
            f"output_overrides.{output.id} contains unsupported key(s): "
            + ", ".join(unknown_keys)
        )

    payload = output.model_dump(mode="json")
    data_override = override.get("data")
    if data_override is not None:
        if not isinstance(data_override, dict):
            raise ValueError(f"output_overrides.{output.id}.data must be an object")
        allowed = _ALLOWED_OVERRIDE_FIELDS.get(output.kind, set())
        unknown_fields = sorted(set(data_override) - allowed)
        if unknown_fields:
            raise ValueError(
                f"output_overrides.{output.id}.data contains unsupported field(s): "
                + ", ".join(unknown_fields)
            )
        payload["data"] = {
            **dict(payload.get("data") or {}),
            **data_override,
        }

    if "preview" in override:
        preview = override["preview"]
        if not isinstance(preview, str) or not preview.strip():
            raise ValueError(f"output_overrides.{output.id}.preview must be a non-empty string")
        payload["preview"] = preview.strip()

    return output.__class__.model_validate(payload)
