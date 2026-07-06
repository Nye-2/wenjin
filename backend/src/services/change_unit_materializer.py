"""Materialize accepted ChangeUnits into workspace rooms."""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from src.agents.contracts.task_report import (
    DecisionOutput,
    DocumentOutput,
    LibraryItemOutput,
    MemoryFactOutput,
    ResultOutput,
    TaskOutput,
    TaskReport,
)
from src.contracts.change_set import ChangeSet, ChangeUnit
from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.prism import PrismWorkspaceFileUpsertPayload
from src.dataservice_client.contracts.rooms import (
    DecisionSetPayload,
    WorkspaceTaskCreatePayload,
)
from src.dataservice_client.contracts.source import (
    SourceExternalIdCreatePayload,
    SourceImportPayload,
)
from src.dataservice_client.contracts.workspace import WorkspaceSettingsUpdatePayload
from src.dataservice_client.contracts.workspace_memory import (
    WorkspaceMemoryItemPayload,
    WorkspaceMemoryMergePayload,
)

logger = logging.getLogger(__name__)

COUNT_ROOM_KEYS = ("library", "prism", "memory", "decisions", "tasks", "sandbox", "settings")
ROOM_TARGET_KEYS = ("prism", "library", "memory", "decisions", "tasks", "sandbox", "settings")

_CITATION_KEY_RE = re.compile(r"[^a-z0-9]+")
_PRISM_SUPPORTED_EXTENSIONS = {
    ".md",
    ".markdown",
    ".tex",
    ".bib",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".svg",
}
_WORKSPACE_SETTINGS_UPDATE_KEYS = frozenset(
    {
        "default_model",
        "thinking_enabled",
        "sandbox_provider",
        "auto_compact_threshold",
        "capability_overrides",
        "settings_json",
        "write_mode",
        "metadata_json",
    }
)


@dataclass(frozen=True)
class ChangeUnitMaterializationResult:
    """Summary of room writes created from accepted ChangeUnits."""

    counts: dict[str, int]
    room_targets: dict[str, list[dict[str, Any]]]


UnitMaterializedCallback = Callable[[str, ChangeUnitMaterializationResult], Awaitable[None]]


async def materialize_accepted_change_units(
    *,
    dataservice: AsyncDataServiceClient,
    execution: Any,
    report: TaskReport,
    change_set: ChangeSet,
    accepted_unit_ids: list[str],
    completed_unit_ids: set[str] | None = None,
    on_unit_materialized: UnitMaterializedCallback | None = None,
) -> ChangeUnitMaterializationResult:
    """Write accepted ChangeUnits to their target workspace rooms."""

    counts = empty_counts()
    room_targets = empty_room_targets()
    completed = set(completed_unit_ids or set())
    outputs_by_id = {output.id: output for output in report.outputs}
    units_by_id = {unit.id: unit for unit in change_set.units}
    selected_units = [units_by_id[unit_id] for unit_id in accepted_unit_ids]
    execution_id = str(getattr(execution, "id", "") or report.execution_id)
    workspace_id = str(getattr(execution, "workspace_id", "") or change_set.workspace_id)

    needs_existing_prism_files = any(unit.target.room == "documents" for unit in selected_units)
    existing_prism_files_by_path = (
        await _existing_prism_files_by_path(
            dataservice=dataservice,
            workspace_id=workspace_id,
        )
        if needs_existing_prism_files
        else {}
    )

    for unit in selected_units:
        if unit.id in completed:
            continue

        output_id = _unit_output_id(unit)
        if output_id is None and unit.materialization is None:
            raise ValueError(
                f"accepted ChangeUnit {unit.id} has no output provenance and cannot be materialized"
            )
        output = outputs_by_id.get(output_id) if output_id is not None else None
        if output_id is not None and output is None:
            raise ValueError(
                f"accepted ChangeUnit {unit.id} references missing output id {output_id}"
            )
        operation = _unit_operation(unit, output)
        data = _unit_payload(unit, output)
        target_output_id = output_id or unit.id
        provenance_key = _unit_provenance_key(execution_id=execution_id, unit_id=unit.id)
        unit_counts = empty_counts()
        unit_room_targets = empty_room_targets()

        if operation == "library.import_source":
            import_result = await dataservice.import_source(
                _source_import_payload(
                    workspace_id=workspace_id,
                    execution_id=execution_id,
                    data=data,
                )
            )
            counts["library"] += 1
            unit_counts["library"] += 1
            target = {
                "output_id": target_output_id,
                "item_id": import_result.source.id,
                "unit_id": unit.id,
                "provenance_key": provenance_key,
            }
            room_targets["library"].append(target)
            unit_room_targets["library"].append(target)
            await _notify_unit_materialized(
                unit_id=unit.id,
                counts=unit_counts,
                room_targets=unit_room_targets,
                callback=on_unit_materialized,
            )
            continue

        if operation == "documents.upsert_prism_file":
            prism_payload = _document_prism_payload(
                execution=execution,
                output_id=target_output_id,
                data=data,
            )
            if prism_payload is None:
                logger.warning(
                    "Skipping document ChangeUnit '%s' for execution %s: no Prism-compatible content",
                    unit.id,
                    execution_id,
                )
                await _notify_unit_materialized(
                    unit_id=unit.id,
                    counts=unit_counts,
                    room_targets=unit_room_targets,
                    callback=on_unit_materialized,
                )
                continue
            previous_file = existing_prism_files_by_path.get(prism_payload.path)
            write = await dataservice.upsert_prism_workspace_file(
                workspace_id,
                prism_payload,
            )
            existing_prism_files_by_path[write.file.path] = write.file
            if write.changed and write.version is not None:
                counts["prism"] += 1
                unit_counts["prism"] += 1
                target = _prism_room_target(
                    output_id=target_output_id,
                    file_id=write.file.id,
                    path=write.file.path,
                    version_id=write.version.id,
                    content_hash=write.version.content_hash,
                    previous_version_id=(
                        previous_file.current_version_id if previous_file is not None else None
                    ),
                    previous_hash=previous_file.content_hash if previous_file is not None else None,
                    created_file=previous_file is None,
                )
                target["unit_id"] = unit.id
                target["provenance_key"] = provenance_key
                room_targets["prism"].append(target)
                unit_room_targets["prism"].append(target)
            await _notify_unit_materialized(
                unit_id=unit.id,
                counts=unit_counts,
                room_targets=unit_room_targets,
                callback=on_unit_materialized,
            )
            continue

        if operation == "memory.merge_items":
            memory_review_result = await dataservice.merge_workspace_memory(
                workspace_id,
                WorkspaceMemoryMergePayload(
                    workspace_id=workspace_id,
                    items=_memory_items_from_payload(data),
                    update_reason="execution_commit",
                    updated_by=provenance_key,
                    source_execution_id=execution_id,
                ),
            )
            if memory_review_result.changed:
                counts["memory"] += 1
                unit_counts["memory"] += 1
                target = {
                    "output_id": target_output_id,
                    "item_id": memory_review_result.document.id,
                    "unit_id": unit.id,
                    "document_id": memory_review_result.document.id,
                    "revision": str(memory_review_result.document.revision),
                    "content_hash": memory_review_result.document.content_hash,
                    "provenance_key": provenance_key,
                }
                room_targets["memory"].append(target)
                unit_room_targets["memory"].append(target)
            await _notify_unit_materialized(
                unit_id=unit.id,
                counts=unit_counts,
                room_targets=unit_room_targets,
                callback=on_unit_materialized,
            )
            continue

        if operation == "decisions.set":
            decision = await dataservice.set_room_decision(
                DecisionSetPayload(
                    workspace_id=workspace_id,
                    key=str(data["key"]),
                    value=str(data["value"]),
                    confidence=float(data.get("confidence", 1.0) or 1.0),
                    extracted_by=provenance_key,
                )
            )
            counts["decisions"] += 1
            unit_counts["decisions"] += 1
            target = {
                "output_id": target_output_id,
                "item_id": decision.id,
                "unit_id": unit.id,
                "provenance_key": provenance_key,
            }
            room_targets["decisions"].append(target)
            unit_room_targets["decisions"].append(target)
            await _notify_unit_materialized(
                unit_id=unit.id,
                counts=unit_counts,
                room_targets=unit_room_targets,
                callback=on_unit_materialized,
            )
            continue

        if operation == "tasks.create":
            priority = data["priority"] if isinstance(data.get("priority"), int) else 0
            task = await dataservice.create_room_task(
                WorkspaceTaskCreatePayload(
                    workspace_id=workspace_id,
                    title=str(data["title"]),
                    description=data.get("description"),
                    priority=priority,
                    related_execution_ids=[execution_id],
                    created_by=provenance_key,
                )
            )
            counts["tasks"] += 1
            unit_counts["tasks"] += 1
            target = {
                "output_id": target_output_id,
                "item_id": task.id,
                "unit_id": unit.id,
                "provenance_key": provenance_key,
            }
            room_targets["tasks"].append(target)
            unit_room_targets["tasks"].append(target)
            await _notify_unit_materialized(
                unit_id=unit.id,
                counts=unit_counts,
                room_targets=unit_room_targets,
                callback=on_unit_materialized,
            )
            continue

        if operation == "sandbox.materialize_artifact":
            artifact_id = str(data["artifact_id"])
            artifact = await dataservice.mark_sandbox_artifact_materialized(
                artifact_id,
                review_item_id=_first_text(data.get("review_item_id")),
            )
            if artifact is None:
                raise ValueError(f"Sandbox artifact {artifact_id} was not found")
            counts["sandbox"] += 1
            unit_counts["sandbox"] += 1
            target = {
                "output_id": target_output_id,
                "item_id": artifact.id,
                "unit_id": unit.id,
                "artifact_id": artifact.id,
                "provenance_key": provenance_key,
                **({"path": data["path"]} if data.get("path") else {}),
            }
            room_targets["sandbox"].append(target)
            unit_room_targets["sandbox"].append(target)
            await _notify_unit_materialized(
                unit_id=unit.id,
                counts=unit_counts,
                room_targets=unit_room_targets,
                callback=on_unit_materialized,
            )
            continue

        if operation == "settings.update":
            command = _workspace_settings_update_payload(data)
            settings = await dataservice.update_workspace_settings(workspace_id, command)
            if settings is None:
                raise ValueError(f"Workspace settings for {workspace_id} were not found")
            counts["settings"] += 1
            unit_counts["settings"] += 1
            target = {
                "output_id": target_output_id,
                "item_id": settings.workspace_id,
                "unit_id": unit.id,
                "settings_keys": ",".join(sorted(command.model_fields_set)),
                "provenance_key": provenance_key,
            }
            room_targets["settings"].append(target)
            unit_room_targets["settings"].append(target)
            await _notify_unit_materialized(
                unit_id=unit.id,
                counts=unit_counts,
                room_targets=unit_room_targets,
                callback=on_unit_materialized,
            )
            continue

        raise ValueError(f"ChangeUnit {unit.id} uses unsupported operation: {operation}")

    return ChangeUnitMaterializationResult(
        counts=counts,
        room_targets=room_targets,
    )


def empty_counts() -> dict[str, int]:
    return {key: 0 for key in COUNT_ROOM_KEYS}


def empty_room_targets() -> dict[str, list[dict[str, Any]]]:
    return {key: [] for key in ROOM_TARGET_KEYS}


async def _notify_unit_materialized(
    *,
    unit_id: str,
    counts: dict[str, int],
    room_targets: dict[str, list[dict[str, Any]]],
    callback: UnitMaterializedCallback | None,
) -> None:
    if callback is None:
        return
    await callback(
        unit_id,
        ChangeUnitMaterializationResult(
            counts={key: int(counts.get(key, 0)) for key in COUNT_ROOM_KEYS},
            room_targets={
                key: [dict(target) for target in room_targets.get(key, [])]
                for key in ROOM_TARGET_KEYS
            },
        ),
    )


def _unit_provenance_key(*, execution_id: str, unit_id: str, max_length: int = 60) -> str:
    raw = f"execution:{execution_id}:unit:{unit_id}"
    if len(raw) <= max_length:
        return raw
    unit_digest = hashlib.sha256(f"{execution_id}:{unit_id}".encode()).hexdigest()[:8]
    execution_prefix = f"execution:{execution_id}"
    compact = f"{execution_prefix}:unit:{unit_digest}"
    if len(compact) <= max_length:
        return compact
    execution_digest = hashlib.sha256(execution_id.encode()).hexdigest()[:16]
    return f"execution:{execution_digest}:unit:{unit_digest}"


def _unit_output_id(unit: ChangeUnit) -> str | None:
    return _first_text(
        unit.provenance.get("output_id"),
        unit.provenance.get("source_output_id"),
    )


def _unit_operation(unit: ChangeUnit, output: ResultOutput | None) -> str:
    if unit.materialization is not None:
        return unit.materialization.operation
    if output is None:
        raise ValueError(f"ChangeUnit {unit.id} has no output for materialization")
    if unit.target.room == "library":
        _require_output_type(unit, output, LibraryItemOutput)
        return "library.import_source"
    if unit.target.room == "documents":
        _require_output_type(unit, output, DocumentOutput)
        return "documents.upsert_prism_file"
    if unit.target.room == "memory":
        _require_output_type(unit, output, MemoryFactOutput)
        return "memory.merge_items"
    if unit.target.room == "decisions":
        _require_output_type(unit, output, DecisionOutput)
        return "decisions.set"
    if unit.target.room == "tasks":
        _require_output_type(unit, output, TaskOutput)
        return "tasks.create"
    raise ValueError(f"ChangeUnit {unit.id} targets unsupported room: {unit.target.room}")


def _unit_payload(unit: ChangeUnit, output: ResultOutput | None) -> dict[str, Any]:
    if unit.materialization is not None:
        return dict(unit.materialization.payload)
    if output is None:
        raise ValueError(f"ChangeUnit {unit.id} has no output payload")
    return _output_data(output)


def _require_output_type(
    unit: ChangeUnit,
    output: ResultOutput,
    expected_type: type[Any],
) -> None:
    if not isinstance(output, expected_type):
        raise ValueError(
            f"ChangeUnit {unit.id} targets {unit.target.room} but output {output.id} "
            f"is {output.kind}"
        )


def _output_data(output: ResultOutput) -> dict[str, Any]:
    if hasattr(output.data, "model_dump"):
        return output.data.model_dump()
    return dict(output.data)


def _workspace_settings_update_payload(data: dict[str, Any]) -> WorkspaceSettingsUpdatePayload:
    raw_payload = data.get("updates") or data.get("settings") or data
    if not isinstance(raw_payload, dict):
        raise ValueError("settings.update payload must be a mapping")
    payload = {
        key: raw_payload[key]
        for key in _WORKSPACE_SETTINGS_UPDATE_KEYS
        if key in raw_payload and raw_payload[key] is not None
    }
    if not payload:
        raise ValueError("settings.update payload must include at least one supported setting")
    return WorkspaceSettingsUpdatePayload(**payload)


def _memory_items_from_payload(data: dict[str, Any]) -> list[WorkspaceMemoryItemPayload]:
    raw_items = data.get("items")
    items = raw_items if isinstance(raw_items, list) and raw_items else [data]
    payloads: list[WorkspaceMemoryItemPayload] = []
    for item in items:
        item_data = item if isinstance(item, dict) else {}
        payloads.append(
            WorkspaceMemoryItemPayload(
                category=str(item_data.get("category") or "context"),
                content=str(item_data.get("content") or ""),
                confidence=float(item_data.get("confidence", 1.0) or 1.0),
            )
        )
    return payloads


async def _existing_prism_files_by_path(
    *,
    dataservice: AsyncDataServiceClient,
    workspace_id: str,
) -> dict[str, Any]:
    try:
        surface = await dataservice.get_prism_surface(workspace_id)
    except Exception:
        logger.warning(
            "Failed to load existing Prism surface before ChangeUnit materialization",
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
    inline_content = data.get("content_inline", data.get("content"))
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
            "source": "change_unit_materializer",
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


def _citation_key(data: dict[str, Any]) -> str:
    raw = str(data.get("citation_key") or data.get("title") or "source").lower()
    key = _CITATION_KEY_RE.sub("_", raw).strip("_")
    year = data.get("year")
    if year and str(year) not in key:
        key = f"{key}_{year}"
    return key or "source"


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


def _first_text(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None
