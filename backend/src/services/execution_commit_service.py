"""Execution commit service — writes accepted ResultOutputs to rooms in one pass.

Spec §4.7.5: All outputs go in one pass; Run History always recorded (regardless
of user selection). Idempotent via idempotency_key (Redis-backed cache, 24h TTL).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from src.agents.contracts.task_report import TaskReport
from src.services.execution_service import ExecutionService
from src.services.rooms.decisions_service import DecisionsService
from src.services.rooms.documents_service import DocumentsService
from src.services.rooms.library_service import LibraryService
from src.services.rooms.memory_service import FactCreate, MemoryService
from src.services.rooms.run_history_service import RunHistoryService
from src.services.rooms.workspace_tasks_service import WorkspaceTasksService
from src.workspace_events import publish_workspace_event

logger = logging.getLogger(__name__)

# Synthetic storage path used for inline (DB-backed) documents.  The real
# content lives in ``DocumentV2.metadata_json['content']`` so both gateway
# and worker can serve the document without sharing a filesystem.
_INLINE_DOC_PATH_PREFIX = "inline://"


class ExecutionCommitService:
    """Commits accepted ResultOutputs to corresponding rooms.

    Spec §4.7.5: All outputs go in one pass; Run History always recorded
    (regardless of user selection). Idempotent via idempotency_key (Redis-backed
    cache). For V1 atomicity is best-effort — each room service commits
    individually. Hard atomicity is a Phase 4 follow-up.
    """

    def __init__(
        self,
        *,
        execution_service: ExecutionService,
        library_service: LibraryService,
        documents_service: DocumentsService,
        decisions_service: DecisionsService,
        memory_service: MemoryService,
        workspace_tasks_service: WorkspaceTasksService,
        run_history_service: RunHistoryService,
        audit_service: Any | None = None,
        redis: Any = None,  # for idempotency cache; if None, no idempotency
        referral_first_task_callback: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        self.execution = execution_service
        self.library = library_service
        self.documents = documents_service
        self.decisions = decisions_service
        self.memory = memory_service
        self.tasks = workspace_tasks_service
        self.run_history = run_history_service
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

        # 4. Write to rooms
        for output in selected:
            kind = output.kind
            data = output.data.model_dump() if hasattr(output.data, "model_dump") else dict(output.data)

            if kind == "library_item":
                item = await self.library.add(
                    execution.workspace_id,
                    {
                        "item_type": "paper",
                        "title": data["title"],
                        "authors": data.get("authors", []),
                        "year": data.get("year"),
                        "doi": data.get("doi"),
                        "url": data.get("url"),
                        "abstract": data.get("abstract"),
                        "metadata_json": data.get("metadata") or {},
                        "added_by": f"execution:{execution_id}",
                    },
                )
                counts["library"] += 1
                room_targets["library"].append(
                    {"output_id": output.id, "item_id": item.id}
                )

            elif kind == "document":
                # Agent-generated documents carry their content inline; we
                # persist that content into DocumentV2.metadata_json so it
                # round-trips through the DB without needing a shared
                # filesystem between gateway and worker.  File-backed
                # documents (uploads etc.) keep their existing storage_path.
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
                    "kind": data.get("doc_kind", "draft"),
                    "mime_type": data.get("mime_type") or "text/markdown",
                    "storage_path": storage_path,
                    "size_bytes": size_bytes,
                    "parent_id": data.get("parent_id"),
                    "added_by": f"execution:{execution_id}",
                }
                if metadata_extra:
                    payload["metadata_json"] = metadata_extra
                doc = await self.documents.add(execution.workspace_id, payload)
                counts["documents"] += 1
                room_targets["documents"].append(
                    {"output_id": output.id, "item_id": doc.id}
                )

            elif kind == "memory_fact":
                await self.memory.add_facts(
                    execution.workspace_id,
                    [
                        FactCreate(
                            category=data["category"],
                            content=data["content"],
                            confidence=data.get("confidence", 1.0),
                        )
                    ],
                )
                counts["memory"] += 1

            elif kind == "decision":
                await self.decisions.set(
                    execution.workspace_id,
                    key=data["key"],
                    value=data["value"],
                    extracted_by=f"execution:{execution_id}",
                    confidence=data.get("confidence", 1.0),
                )
                counts["decisions"] += 1

            elif kind == "task":
                await self.tasks.add(
                    execution.workspace_id,
                    {
                        "title": data["title"],
                        "description": data.get("description"),
                        "priority": data["priority"] if isinstance(data.get("priority"), int) else 0,
                        "related_execution_ids": [execution_id],
                        "created_by": f"execution:{execution_id}",
                    },
                )
                counts["tasks"] += 1

        # 5. Always write run_history
        capability_id = execution.feature_id or report.capability_id
        await self.run_history.record(
            execution.workspace_id,
            execution_id,
            capability_id,
            report.narrative[:200],
            report.narrative,
            report.status,
            report.duration_seconds,
            token_usage=report.token_usage,
            artifact_count=len(selected),
        )

        result: dict[str, Any] = {
            "committed": counts,
            "room_targets": room_targets,
        }

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

    async def _fire_referral_first_task(self, user_id: str) -> None:
        if self._referral_first_task_callback is not None:
            await self._referral_first_task_callback(user_id)
            return

        from src.database import get_db_session
        from src.services.referral_service import ReferralService

        async with get_db_session() as db:
            referral_svc = ReferralService(db)
            await referral_svc.fire_first_task_for_referrer(user_id)
