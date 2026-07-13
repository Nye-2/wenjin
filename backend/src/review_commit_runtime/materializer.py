"""Mission-native workspace domain writer with provenance and preconditions."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.asset import WorkspaceAssetCreatePayload
from src.dataservice_client.contracts.mission import MissionReviewItemPayload
from src.dataservice_client.contracts.prism import (
    PrismFileContentUpdatePayload,
    PrismWorkspaceFileUpsertPayload,
)
from src.dataservice_client.contracts.rooms import DecisionSetPayload, WorkspaceTaskCreatePayload
from src.dataservice_client.contracts.source import SourceImportPayload
from src.dataservice_client.contracts.workspace_memory import WorkspaceMemoryMergePayload
from src.services.path_safety import normalize_path_component

from .contracts import MaterializationReceipt, PreviewObjectStore, TargetSnapshot
from .preview_store import copy_preview_to_asset

_ASSET_SUFFIX_BY_MIME = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/svg+xml": ".svg",
    "image/webp": ".webp",
}


class MissionDomainWriter:
    """Apply one normalized materialization descriptor to its owning domain."""

    def __init__(
        self,
        dataservice: AsyncDataServiceClient,
        *,
        preview_store: PreviewObjectStore | None = None,
        workspace_asset_root: Path | None = None,
    ) -> None:
        self._dataservice = dataservice
        self._preview_store = preview_store
        self._workspace_asset_root = Path(workspace_asset_root or ".wenjin/workspace_uploads")

    async def read_target(
        self,
        item: MissionReviewItemPayload,
        *,
        workspace_id: str,
    ) -> TargetSnapshot:
        if item.target_ref is None:
            return TargetSnapshot()
        if item.target_kind in {"document", "prism_file", "prism_file_change", "prism_structure"}:
            current = await self._dataservice.get_prism_workspace_file(workspace_id, item.target_ref)
            if current is None:
                raise LookupError("materialization_target_not_found")
            return TargetSnapshot(
                target_ref=current.file.id,
                revision_ref=current.file.current_version_id,
                content_hash=current.file.content_hash,
            )
        if item.target_kind in {"long_term_memory", "memory_fact"}:
            current = await self._dataservice.get_workspace_memory_document(workspace_id)
            if current is None:
                raise LookupError("materialization_target_not_found")
            return TargetSnapshot(
                target_ref=current.id,
                revision_ref=str(current.revision),
                content_hash=current.content_hash,
            )
        raise ValueError("existing_target_kind_has_no_precondition_reader")

    async def apply(
        self,
        item: MissionReviewItemPayload,
        *,
        workspace_id: str,
        mission_commit_id: str,
        actor_user_id: str,
    ) -> MaterializationReceipt:
        descriptor = dict(item.preview_json.get("materialization") or {})
        operation = str(descriptor.get("operation") or "")
        payload = dict(descriptor.get("payload") or {})
        provenance = {
            "mission_id": item.mission_id,
            "mission_item_seq": item.source_item_seq,
            "mission_commit_id": mission_commit_id,
            "mission_review_item_id": item.review_item_id,
        }
        if operation == "documents.upsert_prism_file":
            return await self._write_prism(
                item,
                workspace_id=workspace_id,
                actor_user_id=actor_user_id,
                payload=payload,
                provenance=provenance,
            )
        if operation == "library.import_source":
            command = SourceImportPayload.model_validate(
                {
                    **payload,
                    "workspace_id": workspace_id,
                    "ingest_mission_id": item.mission_id,
                    "ingest_mission_commit_id": mission_commit_id,
                }
            )
            result = await self._dataservice.import_source(command)
            return _receipt(
                target_ref=result.source.id,
                content_hash=_hash_json(result.source.model_dump(mode="json")),
                provenance=provenance,
            )
        if operation == "memory.merge_items":
            command = WorkspaceMemoryMergePayload.model_validate(
                {
                    **payload,
                    "workspace_id": workspace_id,
                    "updated_by": f"mission:{item.mission_id}:commit:{mission_commit_id}",
                    "source_mission_id": item.mission_id,
                    "source_mission_commit_id": mission_commit_id,
                    "metadata_json": {
                        **dict(payload.get("metadata_json") or {}),
                        **provenance,
                    },
                }
            )
            result = await self._dataservice.merge_workspace_memory(workspace_id, command)
            return _receipt(
                target_ref=result.document.id,
                revision_ref=str(result.revision.revision if result.revision else result.document.revision),
                content_hash=(result.revision.content_hash if result.revision else result.document.content_hash),
                provenance=provenance,
            )
        if operation == "decisions.set":
            result = await self._dataservice.set_room_decision(
                DecisionSetPayload.model_validate(
                    {
                        **payload,
                        "workspace_id": workspace_id,
                        "extracted_by": f"mission:{item.mission_id}:commit:{mission_commit_id}",
                        "source_mission_id": item.mission_id,
                        "source_mission_item_seq": item.source_item_seq,
                        "source_mission_commit_id": mission_commit_id,
                    }
                )
            )
            return _receipt(
                target_ref=result.id,
                content_hash=_hash_json(result.model_dump(mode="json")),
                provenance=provenance,
            )
        if operation == "tasks.create":
            result = await self._dataservice.create_room_task(
                WorkspaceTaskCreatePayload.model_validate(
                    {
                        **payload,
                        "workspace_id": workspace_id,
                        "created_by": f"mission:{item.mission_id}:commit:{mission_commit_id}",
                        "source_mission_id": item.mission_id,
                        "source_mission_item_seq": item.source_item_seq,
                        "source_mission_commit_id": mission_commit_id,
                    }
                )
            )
            return _receipt(
                target_ref=result.id,
                content_hash=_hash_json(result.model_dump(mode="json")),
                provenance=provenance,
            )
        if operation == "sandbox.materialize_artifact":
            artifact_id = str(payload["sandbox_artifact_id"])
            result = await self._dataservice.mark_sandbox_artifact_materialized(
                artifact_id,
                mission_commit_id=mission_commit_id,
            )
            if result is None or not result.content_hash:
                raise ValueError("sandbox_materialization_receipt_missing")
            return _receipt(
                target_ref=result.workspace_asset_id,
                content_hash=result.content_hash,
                manifest_ref=str(payload.get("manifest_ref") or "") or None,
                provenance=provenance,
            )
        if operation == "assets.create_from_preview":
            return await self._create_asset_from_preview(
                item,
                workspace_id=workspace_id,
                mission_commit_id=mission_commit_id,
                actor_user_id=actor_user_id,
                payload=payload,
                provenance=provenance,
            )
        raise ValueError("unknown_materialization_operation")

    async def _create_asset_from_preview(
        self,
        item: MissionReviewItemPayload,
        *,
        workspace_id: str,
        mission_commit_id: str,
        actor_user_id: str,
        payload: dict[str, Any],
        provenance: dict[str, Any],
    ) -> MaterializationReceipt:
        if item.target_kind != "workspace_asset" or item.target_ref is not None:
            raise ValueError("workspace_asset_materialization_requires_new_target")
        if self._preview_store is None or item.preview_ref is None:
            raise ValueError("workspace_asset_preview_unavailable")

        existing = await self._dataservice.list_assets(
            workspace_id=workspace_id,
            source_kind="mission_review_item",
            source_id=item.review_item_id,
            limit=2,
        )
        if existing:
            asset = existing[0]
            if not asset.content_hash:
                raise ValueError("workspace_asset_receipt_missing_hash")
            return _receipt(
                target_ref=asset.id,
                content_hash=asset.content_hash,
                manifest_ref=str(payload.get("manifest_ref") or "") or None,
                provenance=provenance,
            )

        preview = await self._preview_store.read(item.preview_ref, workspace_id=workspace_id)
        descriptor = preview.descriptor
        expected_hash = str(payload.get("content_hash") or "")
        if not expected_hash or expected_hash != descriptor.content_hash:
            raise ValueError("workspace_asset_content_hash_mismatch")
        requested_mime = str(payload.get("mime_type") or descriptor.mime_type)
        if requested_mime != descriptor.mime_type or requested_mime not in _ASSET_SUFFIX_BY_MIME:
            raise ValueError("workspace_asset_mime_type_mismatch")

        suffix = _ASSET_SUFFIX_BY_MIME[requested_mime]
        relative_path = Path("generated_visuals") / expected_hash[:2] / f"{expected_hash}{suffix}"
        destination = self._workspace_asset_root / normalize_path_component(workspace_id) / relative_path
        copy_preview_to_asset(preview.content, destination, expected_hash=expected_hash)
        name = Path(str(payload.get("name") or descriptor.filename)).name
        if not name or name in {".", ".."}:
            name = descriptor.filename
        metadata = {
            **dict(payload.get("metadata_json") or {}),
            **provenance,
            "generated_by": "wenjin_academic_visual",
            "preview_content_hash": descriptor.content_hash,
        }
        asset = await self._dataservice.register_asset(
            WorkspaceAssetCreatePayload(
                workspace_id=workspace_id,
                asset_kind=str(payload.get("asset_kind") or "academic_visual"),
                name=name,
                title=str(payload.get("title") or "") or None,
                mime_type=requested_mime,
                storage_backend="local",
                storage_path=relative_path.as_posix(),
                size_bytes=descriptor.size_bytes,
                content_hash=descriptor.content_hash,
                created_by=actor_user_id,
                source_kind="mission_review_item",
                source_id=item.review_item_id,
                metadata_json=metadata,
            )
        )
        return _receipt(
            target_ref=asset.id,
            content_hash=descriptor.content_hash,
            manifest_ref=str(payload.get("manifest_ref") or "") or None,
            provenance=provenance,
        )

    async def _write_prism(
        self,
        item: MissionReviewItemPayload,
        *,
        workspace_id: str,
        actor_user_id: str,
        payload: dict[str, Any],
        provenance: dict[str, Any],
    ) -> MaterializationReceipt:
        metadata = {**dict(payload.get("metadata_json") or {}), **provenance}
        if item.target_ref:
            command = PrismFileContentUpdatePayload.model_validate(
                {
                    "content_inline": payload.get("content_inline"),
                    "content_asset_id": payload.get("content_asset_id"),
                    "content_hash": payload["content_hash"],
                    "created_by": actor_user_id,
                    "mission_review_item_id": item.review_item_id,
                    "mission_commit_id": provenance["mission_commit_id"],
                    "expected_current_hash": item.base_hash,
                    "metadata_json": metadata,
                }
            )
            result = await self._dataservice.update_prism_workspace_file(
                workspace_id,
                item.target_ref,
                command,
            )
        else:
            command = PrismWorkspaceFileUpsertPayload.model_validate(
                {
                    **payload,
                    "created_by": actor_user_id,
                    "mission_review_item_id": item.review_item_id,
                    "mission_commit_id": provenance["mission_commit_id"],
                    "metadata_json": metadata,
                }
            )
            result = await self._dataservice.upsert_prism_workspace_file(workspace_id, command)
        if result.skipped_reason == "hash_mismatch":
            raise ValueError("stale_target_precondition")
        return _receipt(
            target_ref=result.file.id,
            revision_ref=result.version.id if result.version else result.file.current_version_id,
            content_hash=result.file.content_hash or str(payload["content_hash"]),
            provenance=provenance,
        )


def _receipt(
    *,
    target_ref: str,
    content_hash: str,
    provenance: dict[str, Any],
    revision_ref: str | None = None,
    manifest_ref: str | None = None,
) -> MaterializationReceipt:
    return MaterializationReceipt(
        target_ref=target_ref,
        revision_ref=revision_ref,
        content_hash=content_hash,
        manifest_ref=manifest_ref,
        provenance=provenance,
    )


def _hash_json(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


__all__ = ["MissionDomainWriter"]
