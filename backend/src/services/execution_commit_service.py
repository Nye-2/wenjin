"""Execution commit service — writes accepted ResultOutputs to rooms in one pass.

Spec §4.7.5: All outputs go in one pass; Run History always recorded (regardless
of user selection). Idempotent via idempotency_key (Redis-backed cache, 24h TTL).
"""

from __future__ import annotations

import json
import logging
import re
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
_ALLOWED_OVERRIDE_FIELDS: dict[str, set[str]] = {
    "document": {"content", "name", "doc_kind"},
    "library_item": {"title", "authors", "year", "doi", "url", "abstract"},
    "memory_fact": {"category", "content", "confidence"},
    "decision": {"key", "value"},
    "task": {"title", "description", "priority"},
}


class ExecutionCommitNotFoundError(LookupError):
    """Raised when a commit target is missing or hidden from this actor."""


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

        # 2. Idempotency cache check
        if idempotency_key and self.redis:
            cache_key = f"commit:cache:{execution_id}:{idempotency_key}"
            cached = await self.redis.get(cache_key)
            if cached:
                return cast(dict[str, Any], json.loads(cached))

        # 3. Validate report
        if not execution.result or "task_report" not in execution.result:
            raise ValueError(f"execution {execution_id} has no task_report")

        report = TaskReport.model_validate(execution.result["task_report"])

        # 4. Select outputs
        output_by_id = {output.id: output for output in report.outputs}
        if accept_all:
            selected = list(report.outputs)
        elif accepted_ids is not None:
            id_set = set(accepted_ids)
            missing_ids = sorted(id_set - set(output_by_id))
            if missing_ids:
                raise ValueError(
                    "accepted_ids contains unknown output id(s): "
                    + ", ".join(missing_ids)
                )
            selected = [o for o in report.outputs if o.id in id_set]
        else:
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
            "memory": [],
            "decisions": [],
            "tasks": [],
        }
        room_candidates: list[RoomCandidatePayload] = []

        # 5. Write to rooms
        async with self._client() as dataservice:
            for output in selected:
                kind = output.kind
                data = output.data.model_dump() if hasattr(output.data, "model_dump") else dict(output.data)

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
                            provenance_json={"execution_id": execution_id, "output_id": output.id},
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
                            provenance_json={"execution_id": execution_id, "output_id": output.id},
                        )
                    )

                elif kind == "task":
                    room_candidates.append(
                        RoomCandidatePayload(
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

            # 6. Always write run_history
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

        result: dict[str, Any] = {
            "committed": counts,
            "room_targets": room_targets,
        }
        if room_review_result is not None:
            result["review_batch_id"] = room_review_result.review_batch_id
            result["room_review_results"] = room_review_result.item_results

        # 7. Cache idempotent result
        if idempotency_key and self.redis:
            cache_key = f"commit:cache:{execution_id}:{idempotency_key}"
            await self.redis.set(cache_key, json.dumps(result), ex=86400)  # 24h

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
