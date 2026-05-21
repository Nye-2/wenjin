"""Execution commit service — writes accepted ResultOutputs to rooms in one pass.

Spec §4.7.5: All outputs go in one pass; Run History always recorded (regardless
of user selection). Idempotent via idempotency_key (Redis-backed cache, 24h TTL).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

from src.agents.contracts.task_report import TaskReport
from src.dataservice.asset_api import AssetDataService
from src.dataservice.execution_api import ExecutionDataService
from src.dataservice.rooms_api import RoomCandidateCommand, RoomsDataService
from src.dataservice.source_api import SourceCreateCommand, SourceDataService
from src.services.execution_service import ExecutionService
from src.workspace_events import publish_workspace_event

logger = logging.getLogger(__name__)

# Synthetic storage path used for inline DataService asset documents. The real
# content lives in asset metadata so gateway and worker do not need a shared
# filesystem for generated markdown.
_INLINE_DOC_PATH_PREFIX = "inline://"
_CITATION_KEY_RE = re.compile(r"[^a-z0-9]+")


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
        source_data_service: SourceDataService | None = None,
        asset_data_service: AssetDataService | None = None,
        execution_data_service: ExecutionDataService | None = None,
        rooms_data_service: RoomsDataService | None = None,
        audit_service: Any | None = None,
        redis: Any = None,  # for idempotency cache; if None, no idempotency
        referral_first_task_callback: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        self.execution = execution_service
        self.sources = source_data_service
        self.assets = asset_data_service
        self.execution_data = execution_data_service
        self.rooms_data = rooms_data_service
        self.audit = audit_service
        self.redis = redis
        self._referral_first_task_callback = referral_first_task_callback

    async def commit_outputs(
        self,
        execution_id: str,
        *,
        accept_all: bool = False,
        accepted_ids: list[str] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Commit accepted outputs to rooms and record run history.

        Args:
            execution_id: The execution to commit outputs for.
            accept_all: If True, all outputs in the TaskReport are written.
            accepted_ids: Specific output IDs to write (ignored when accept_all=True).
            idempotency_key: Optional key for idempotent repeat calls (24h cache).

        Returns:
            dict with key "committed" containing per-room write counts.

        Raises:
            ValueError: If execution not found or has no task_report.
        """
        # 1. Idempotency cache check
        if idempotency_key and self.redis:
            cache_key = f"commit:cache:{execution_id}:{idempotency_key}"
            cached = await self.redis.get(cache_key)
            if cached:
                return json.loads(cached)

        # 2. Fetch execution + report
        execution = await self.execution.get_by_id(execution_id)
        if execution is None:
            raise ValueError(f"execution {execution_id} not found")
        if not execution.result or "task_report" not in execution.result:
            raise ValueError(f"execution {execution_id} has no task_report")

        report = TaskReport.model_validate(execution.result["task_report"])

        # 3. Select outputs
        if accept_all:
            selected = list(report.outputs)
        elif accepted_ids is not None:
            id_set = set(accepted_ids)
            selected = [o for o in report.outputs if o.id in id_set]
        else:
            selected = []

        counts: dict[str, int] = {
            "library": 0,
            "documents": 0,
            "memory": 0,
            "decisions": 0,
            "tasks": 0,
        }
        room_targets: dict[str, list[dict[str, str]]] = {
            "documents": [],
            "library": [],
        }
        room_candidates: list[RoomCandidateCommand] = []

        # 4. Write to rooms
        for output in selected:
            kind = output.kind
            data = output.data.model_dump() if hasattr(output.data, "model_dump") else dict(output.data)

            if kind == "library_item":
                item = await self._resolve_source_data_service().create_source(
                    SourceCreateCommand(
                        workspace_id=execution.workspace_id,
                        source_kind="paper",
                        title=data["title"],
                        authors_json=list(data.get("authors") or []),
                        year=data.get("year"),
                        doi=data.get("doi"),
                        url=data.get("url"),
                        abstract=data.get("abstract"),
                        ingest_kind="execution",
                        ingest_label=f"execution:{execution_id}",
                        ingest_execution_id=execution_id,
                        library_status="included",
                        citation_key=_citation_key(data),
                        bibtex_fields_json=dict(data.get("metadata") or {}),
                    )
                )
                counts["library"] += 1
                room_targets["library"].append(
                    {"output_id": output.id, "item_id": item.id}
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
                    storage_path = f"{_INLINE_DOC_PATH_PREFIX}{output.id}"
                    size_bytes = len(inline_content.encode("utf-8"))
                    metadata_extra = {"content": inline_content}

                payload = {
                    "name": data["name"],
                    "asset_kind": data.get("doc_kind", "draft"),
                    "mime_type": data.get("mime_type") or "text/markdown",
                    "storage_path": storage_path,
                    "size_bytes": size_bytes,
                    "parent_asset_id": data.get("parent_id"),
                    "created_by": f"execution:{execution_id}",
                }
                metadata_extra.setdefault("kind", payload["asset_kind"])
                if metadata_extra:
                    payload["metadata_json"] = metadata_extra
                doc = await self._resolve_asset_data_service().register_asset_record(
                    workspace_id=execution.workspace_id,
                    source_kind="execution_output",
                    source_id=output.id,
                    **payload,
                )
                counts["documents"] += 1
                room_targets["documents"].append(
                    {"output_id": output.id, "item_id": doc.id}
                )

            elif kind == "memory_fact":
                room_candidates.append(
                    RoomCandidateCommand(
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
                        provenance_json={"execution_id": execution_id, "output_id": output.id},
                    )
                )

            elif kind == "decision":
                room_candidates.append(
                    RoomCandidateCommand(
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
                        provenance_json={"execution_id": execution_id, "output_id": output.id},
                    )
                )

            elif kind == "task":
                room_candidates.append(
                    RoomCandidateCommand(
                        source_item_id=output.id,
                        target_kind="workspace_task",
                        title=f"Task: {data['title']}",
                        summary=data.get("description"),
                        payload_json={
                            "title": data["title"],
                            "description": data.get("description"),
                            "priority": data["priority"] if isinstance(data.get("priority"), int) else 0,
                            "related_execution_ids": [execution_id],
                            "created_by": f"execution:{execution_id}",
                        },
                        preview_json={"title": data["title"]},
                        provenance_json={"execution_id": execution_id, "output_id": output.id},
                    )
                )

        room_review_result = None
        if room_candidates:
            rooms_data = self._resolve_rooms_data_service()
            room_review_result = await rooms_data.stage_and_apply_candidates(
                workspace_id=execution.workspace_id,
                execution_id=execution_id,
                candidates=room_candidates,
                actor_id=f"execution:{execution_id}",
            )
            for key, value in room_review_result.counts.items():
                if key in counts:
                    counts[key] += value

        # 5. Always write run_history
        capability_id = execution.feature_id or report.capability_id
        await self._resolve_execution_data_service().record_event(
            execution_id=execution_id,
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
        )

        result: dict[str, Any] = {
            "committed": counts,
            "room_targets": room_targets,
        }
        if room_review_result is not None:
            result["review_batch_id"] = room_review_result.review_batch_id
            result["room_review_results"] = room_review_result.item_results

        # 6. Cache idempotent result
        if idempotency_key and self.redis:
            cache_key = f"commit:cache:{execution_id}:{idempotency_key}"
            await self.redis.set(cache_key, json.dumps(result), ex=86400)  # 24h

        # 7. Publish canonical workspace refresh event
        try:
            await publish_workspace_event(
                execution.workspace_id,
                "workspace.refresh",
                {
                    "refresh_targets": [
                        "activity",
                        "artifacts",
                        "dashboard",
                        "references",
                    ]
                },
            )
        except Exception:
            logger.exception("workspace.refresh publish failed")

        # 8. Audit
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

    def _resolve_rooms_data_service(self) -> RoomsDataService:
        if self.rooms_data is not None:
            return self.rooms_data
        db = getattr(self.execution, "db", None)
        if db is None:
            raise RuntimeError("ExecutionCommitService requires RoomsDataService for room candidate apply")
        self.rooms_data = RoomsDataService(db)
        return self.rooms_data

    def _resolve_source_data_service(self) -> SourceDataService:
        if self.sources is not None:
            return self.sources
        db = getattr(self.execution, "db", None)
        if db is None:
            raise RuntimeError("ExecutionCommitService requires SourceDataService for library commits")
        self.sources = SourceDataService(db)
        return self.sources

    def _resolve_asset_data_service(self) -> AssetDataService:
        if self.assets is not None:
            return self.assets
        db = getattr(self.execution, "db", None)
        if db is None:
            raise RuntimeError("ExecutionCommitService requires AssetDataService for document commits")
        self.assets = AssetDataService(db)
        return self.assets

    def _resolve_execution_data_service(self) -> ExecutionDataService:
        if self.execution_data is not None:
            return self.execution_data
        db = getattr(self.execution, "db", None)
        if db is None:
            raise RuntimeError("ExecutionCommitService requires ExecutionDataService for run history")
        self.execution_data = ExecutionDataService(db)
        return self.execution_data

    async def _fire_referral_first_task(self, user_id: str) -> None:
        if self._referral_first_task_callback is not None:
            await self._referral_first_task_callback(user_id)
            return

        from src.database import get_db_session
        from src.services.referral_service import ReferralService

        async with get_db_session() as db:
            referral_svc = ReferralService(db)
            await referral_svc.fire_first_task_for_referrer(user_id)


def _citation_key(data: dict[str, Any]) -> str:
    raw = str(data.get("citation_key") or data.get("title") or "source").lower()
    key = _CITATION_KEY_RE.sub("_", raw).strip("_")
    year = data.get("year")
    if year and str(year) not in key:
        key = f"{key}_{year}"
    return key or "source"
