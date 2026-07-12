"""Source import and reference lifecycle service."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from src.dataservice.domains.source.context import SourceDomainContext
from src.dataservice.domains.source.contracts import (
    SourceCreateCommand,
    SourceExternalIdCreateCommand,
    SourceImportCommand,
    SourceImportProjection,
    SourceProjection,
    SourceUpdateCommand,
)
from src.dataservice.domains.source.helpers import (
    max_ranked_value,
    normalize_doi,
    serialize_external_id,
)
from src.dataservice.domains.source.projection import source_to_projection


class SourceImportService:
    def __init__(self, context: SourceDomainContext) -> None:
        self.context = context

    async def create_source(self, command: SourceCreateCommand) -> SourceProjection:
        normalized_title = command.normalized_title or command.title.strip().lower()
        record = self.context.repository.create_source(
            {
                **command.model_dump(exclude={"normalized_title"}),
                "normalized_title": normalized_title,
            }
        )
        await self.context.finish()
        return source_to_projection(record)

    async def upsert_source(self, command: SourceCreateCommand) -> SourceProjection:
        record = None
        if command.source_id:
            record = await self.context.repository.get_source_for_workspace(
                workspace_id=command.workspace_id,
                source_id=command.source_id,
                include_deleted=True,
            )
        normalized_title = command.normalized_title or command.title.strip().lower()
        values = {
            **command.model_dump(exclude={"source_id", "normalized_title"}),
            "normalized_title": normalized_title,
        }
        if record is None:
            record = self.context.repository.create_source(
                {
                    **values,
                    **({"source_id": command.source_id} if command.source_id else {}),
                }
            )
        else:
            for field, value in values.items():
                if hasattr(record, field):
                    setattr(record, field, value)
            record.updated_at = datetime.now(UTC)
        await self.context.finish()
        return source_to_projection(record)

    async def import_source(self, command: SourceImportCommand) -> SourceImportProjection:
        if command.ingest_mission_commit_id:
            replay = await self.context.repository.get_source_by_mission_commit(
                command.ingest_mission_commit_id
            )
            if replay is not None:
                if replay.workspace_id != command.workspace_id:
                    raise ValueError("mission_commit_source_workspace_mismatch")
                return SourceImportProjection(
                    source=source_to_projection(replay),
                    created=False,
                    external_ids=await self.list_source_external_ids(
                        workspace_id=command.workspace_id,
                        source_id=str(replay.id),
                    ),
                )
        normalized_title = command.normalized_title or command.title.strip().lower()
        record = await self._find_import_source(command, normalized_title=normalized_title)
        created = record is None
        values = {
            **command.model_dump(
                exclude={
                    "source_id",
                    "normalized_title",
                    "external_ids",
                    "dedupe_by_title",
                }
            ),
            "normalized_title": normalized_title,
            "doi": normalize_doi(command.doi),
        }
        if record is None:
            values["citation_key"] = await self._ensure_unique_citation_key(
                workspace_id=command.workspace_id,
                base_key=command.citation_key,
            )
            record = self.context.repository.create_source(
                {
                    **values,
                    **({"source_id": command.source_id} if command.source_id else {}),
                }
            )
        else:
            self._merge_import_values(record, values)
        await self.context.finish()
        external_ids = await self.upsert_source_external_ids(
            workspace_id=command.workspace_id,
            source_id=str(record.id),
            external_ids=command.external_ids,
        )
        return SourceImportProjection(
            source=source_to_projection(record),
            created=created,
            external_ids=external_ids,
        )

    async def upsert_source_external_ids(
        self,
        *,
        workspace_id: str,
        source_id: str,
        external_ids: list[SourceExternalIdCreateCommand],
    ) -> list[dict[str, object]]:
        source = await self.context.repository.get_source_for_workspace(
            workspace_id=workspace_id,
            source_id=source_id,
            include_deleted=True,
        )
        if source is None:
            return []
        upserted: list[dict[str, object]] = []
        for item in external_ids:
            provider = item.provider.strip()
            external_id = item.external_id.strip()
            if not provider or not external_id:
                continue
            record = await self.context.repository.get_external_id(
                workspace_id=workspace_id,
                provider=provider,
                external_id=external_id,
            )
            if record is None:
                record = self.context.repository.create_external_id(
                    {
                        "workspace_id": workspace_id,
                        "source_id": source_id,
                        "provider": provider,
                        "external_id": external_id,
                        "url": item.url,
                        "metadata_json": dict(item.metadata_json or {}),
                    }
                )
            else:
                record.source_id = source_id
                record.url = record.url or item.url
                record.metadata_json = {
                    **dict(record.metadata_json or {}),
                    **dict(item.metadata_json or {}),
                }
            upserted.append(serialize_external_id(record))
        await self.context.finish()
        return upserted

    async def list_source_external_ids(
        self,
        *,
        workspace_id: str,
        source_id: str,
    ) -> list[dict[str, object]]:
        return [
            serialize_external_id(record)
            for record in await self.context.repository.list_external_ids(
                workspace_id=workspace_id,
                source_id=source_id,
            )
        ]

    async def mark_deleted(self, source_id: str) -> SourceProjection | None:
        record = await self.context.repository.get_source(source_id)
        if record is None:
            return None
        record.is_deleted = True
        record.updated_at = datetime.now(UTC)
        await self.context.finish()
        return source_to_projection(record)

    async def mark_deleted_for_workspace(
        self,
        *,
        workspace_id: str,
        source_id: str,
    ) -> bool:
        record = await self.context.repository.get_source_for_workspace(
            workspace_id=workspace_id,
            source_id=source_id,
        )
        if record is None:
            return False
        record.is_deleted = True
        record.updated_at = datetime.now(UTC)
        await self.context.finish()
        return True

    async def update_source(
        self,
        *,
        workspace_id: str,
        source_id: str,
        command: SourceUpdateCommand,
    ) -> SourceProjection | None:
        record = await self.context.repository.get_source_for_workspace(
            workspace_id=workspace_id,
            source_id=source_id,
        )
        if record is None:
            return None
        updates = command.model_dump(exclude_unset=True)
        if "title" in updates and updates["title"]:
            updates["normalized_title"] = str(updates["title"]).strip().lower()
        if "doi" in updates and updates["doi"] is not None:
            updates["doi"] = normalize_doi(updates["doi"])
        if "citation_key" in updates and updates["citation_key"]:
            updates["citation_key"] = await self._ensure_unique_citation_key(
                workspace_id=workspace_id,
                base_key=str(updates["citation_key"]),
                exclude_source_id=source_id,
            )
        now = datetime.now(UTC)
        for field, value in updates.items():
            if hasattr(record, field):
                setattr(record, field, value)
        record.updated_at = now
        await self.context.finish()
        return source_to_projection(record)

    async def mark_status(
        self,
        *,
        workspace_id: str,
        source_id: str,
        library_status: str | None = None,
        read_status: str | None = None,
    ) -> SourceProjection | None:
        return await self.update_source(
            workspace_id=workspace_id,
            source_id=source_id,
            command=SourceUpdateCommand(
                **{
                    **({"library_status": library_status} if library_status is not None else {}),
                    **({"read_status": read_status} if read_status is not None else {}),
                }
            ),
        )

    async def _ensure_unique_citation_key(
        self,
        *,
        workspace_id: str,
        base_key: str,
        exclude_source_id: str | None = None,
    ) -> str:
        base = re.sub(r"[^A-Za-z0-9_:-]+", "", str(base_key or "").strip()) or "ref"
        candidate = base
        suffix = 2
        while await self.context.repository.citation_key_exists(
            workspace_id=workspace_id,
            citation_key=candidate,
            exclude_source_id=exclude_source_id,
        ):
            candidate = f"{base}{suffix}"
            suffix += 1
        return candidate

    async def _find_import_source(
        self,
        command: SourceImportCommand,
        *,
        normalized_title: str,
    ) -> object | None:
        if command.source_id:
            source = await self.context.repository.get_source_for_workspace(
                workspace_id=command.workspace_id,
                source_id=command.source_id,
                include_deleted=True,
            )
            if source is not None:
                return source
        for external_id in command.external_ids:
            record = await self.context.repository.get_external_id(
                workspace_id=command.workspace_id,
                provider=external_id.provider,
                external_id=external_id.external_id,
            )
            if record is not None:
                source = await self.context.repository.get_source_for_workspace(
                    workspace_id=command.workspace_id,
                    source_id=str(record.source_id),
                    include_deleted=False,
                )
                if source is not None:
                    return source
        doi = normalize_doi(command.doi)
        if doi:
            source = await self.context.repository.find_source_by_doi(
                workspace_id=command.workspace_id,
                doi=doi,
            )
            if source is not None:
                return source
        if command.dedupe_by_title and normalized_title:
            return await self.context.repository.find_source_by_title_year(
                workspace_id=command.workspace_id,
                normalized_title=normalized_title,
                year=command.year,
            )
        return None

    @staticmethod
    def _merge_import_values(record: object, values: dict[str, object]) -> None:
        for field in (
            "title",
            "normalized_title",
            "authors_json",
            "year",
            "venue",
            "publication_type",
            "doi",
            "url",
            "abstract",
            "citation_count",
            "ingest_label",
            "ingest_mission_id",
            "verified_at",
            "bibtex_entry_type",
            "read_status",
            "notes",
        ):
            value = values.get(field)
            if value not in (None, "", [], {}) and not getattr(record, field, None):
                setattr(record, field, value)
        if values.get("bibtex_fields_json"):
            record.bibtex_fields_json = {
                **dict(getattr(record, "bibtex_fields_json", None) or {}),
                **dict(values["bibtex_fields_json"] or {}),
            }
        if values.get("tags_json"):
            record.tags_json = list(dict.fromkeys(list(getattr(record, "tags_json", None) or []) + [str(item) for item in values["tags_json"] or []]))
        incoming_status = str(values.get("library_status") or "")
        if incoming_status and incoming_status != "candidate":
            record.library_status = incoming_status
        record.evidence_level = max_ranked_value(
            getattr(record, "evidence_level", None),
            values.get("evidence_level"),
            {
                "metadata_only": 0,
                "external_verified": 1,
                "uploaded_fulltext": 2,
                "indexed_fulltext": 3,
            },
        )
        record.fulltext_status = max_ranked_value(
            getattr(record, "fulltext_status", None),
            values.get("fulltext_status"),
            {
                "none": 0,
                "failed": 1,
                "uploaded": 2,
                "preprocessing": 3,
                "indexed": 4,
            },
        )
        record.updated_at = datetime.now(UTC)
