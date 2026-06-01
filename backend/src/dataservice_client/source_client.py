"""Source DataService client methods."""

from __future__ import annotations

from typing import Any

from src.dataservice_client.contracts.provenance import (
    ProvenanceLinkCreatePayload,
    ProvenanceLinkPayload,
)
from src.dataservice_client.contracts.source import (
    SourceAssetLinkPayload,
    SourceAssetUpdatePayload,
    SourceBibliographyCreatePayload,
    SourceBibliographyPayload,
    SourceBibliographySnapshotCreatePayload,
    SourceBibliographySnapshotPayload,
    SourceCitationUsageCreatePayload,
    SourceCitationUsagePayload,
    SourceCreatePayload,
    SourceEvidencePackCreatePayload,
    SourceEvidencePackPayload,
    SourceExternalIdCreatePayload,
    SourceImportPayload,
    SourceImportResultPayload,
    SourceIndexReplacePayload,
    SourcePayload,
    SourceUpdatePayload,
)


class SourceDataServiceClientMixin:
    """Typed DataService methods for this domain."""

    async def _request(
        self,
        method: str,
        path: str,
        *,
        authenticated: bool = True,
        **kwargs: Any,
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def create_source(self, command: SourceCreatePayload) -> SourcePayload:
        payload = await self._request(
            "POST",
            "/internal/v1/sources",
            json=command.model_dump(mode="json"),
        )
        return SourcePayload.model_validate(payload["data"])

    async def upsert_source(self, command: SourceCreatePayload) -> SourcePayload:
        payload = await self._request(
            "POST",
            "/internal/v1/sources/upsert",
            json=command.model_dump(mode="json"),
        )
        return SourcePayload.model_validate(payload["data"])

    async def import_source(self, command: SourceImportPayload) -> SourceImportResultPayload:
        payload = await self._request(
            "POST",
            "/internal/v1/sources/import",
            json=command.model_dump(mode="json"),
        )
        return SourceImportResultPayload.model_validate(payload["data"])

    async def list_sources(
        self,
        *,
        workspace_id: str,
        library_status: str | None = None,
        source_kind: str | None = None,
        ingest_kind: str | None = None,
        query: str | None = None,
        include_deleted: bool = False,
        include_excluded: bool = True,
        offset: int = 0,
        limit: int = 50,
    ) -> list[SourcePayload]:
        payload = await self._request(
            "GET",
            "/internal/v1/sources",
            params={
                "workspace_id": workspace_id,
                "library_status": library_status,
                "source_kind": source_kind,
                "ingest_kind": ingest_kind,
                "query": query,
                "include_deleted": include_deleted,
                "include_excluded": include_excluded,
                "offset": offset,
                "limit": limit,
            },
        )
        return [SourcePayload.model_validate(item) for item in payload["data"]]

    async def count_sources(
        self,
        *,
        workspace_id: str,
        library_status: str | None = None,
        source_kind: str | None = None,
        ingest_kind: str | None = None,
        query: str | None = None,
        fulltext_status: str | None = None,
        include_deleted: bool = False,
        include_excluded: bool = False,
    ) -> int:
        payload = await self._request(
            "GET",
            "/internal/v1/sources/count",
            params={
                "workspace_id": workspace_id,
                "library_status": library_status,
                "source_kind": source_kind,
                "ingest_kind": ingest_kind,
                "query": query,
                "fulltext_status": fulltext_status,
                "include_deleted": include_deleted,
                "include_excluded": include_excluded,
            },
        )
        return int(payload["data"]["count"])

    async def count_source_reference_summary(self, *, workspace_id: str) -> dict[str, int]:
        payload = await self._request(
            "GET",
            "/internal/v1/sources/count/reference-summary",
            params={"workspace_id": workspace_id},
        )
        return dict(payload["data"])

    async def list_sources_page(
        self,
        *,
        workspace_id: str,
        library_status: str | None = None,
        source_kind: str | None = None,
        ingest_kind: str | None = None,
        query: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        payload = await self._request(
            "GET",
            "/internal/v1/sources/page",
            params={
                "workspace_id": workspace_id,
                "library_status": library_status,
                "source_kind": source_kind,
                "ingest_kind": ingest_kind,
                "query": query,
                "offset": offset,
                "limit": limit,
            },
        )
        return dict(payload["data"])

    async def get_source_library_outline(self, *, workspace_id: str) -> list[dict[str, Any]]:
        payload = await self._request(
            "GET",
            "/internal/v1/sources/library-outline",
            params={"workspace_id": workspace_id},
        )
        return list(payload["data"])

    async def get_source_toc_summary(self, *, workspace_id: str) -> str:
        payload = await self._request(
            "GET",
            "/internal/v1/sources/toc-summary",
            params={"workspace_id": workspace_id},
        )
        return str(payload["data"].get("summary") or "")

    async def get_workspace_toc_summary(self, workspace_id: str) -> str:
        return await self.get_source_toc_summary(workspace_id=workspace_id)

    async def search_source_text_units(
        self,
        *,
        workspace_id: str,
        query: str,
        source_ids: list[str] | None = None,
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        payload = await self._request(
            "GET",
            "/internal/v1/sources/text-units/search",
            params={
                "workspace_id": workspace_id,
                "query": query,
                "source_ids": source_ids,
                "limit": limit,
            },
        )
        return list(payload["data"])

    async def get_source_section_by_path(
        self,
        *,
        source_id: str,
        workspace_id: str,
        section_path: str,
    ) -> dict[str, Any] | None:
        payload = await self._request(
            "GET",
            f"/internal/v1/sources/{source_id}/sections/by-path",
            params={"workspace_id": workspace_id, "section_path": section_path},
        )
        data = payload.get("data")
        return dict(data) if isinstance(data, dict) else None

    async def get_source_section_by_title(
        self,
        *,
        source_id: str,
        workspace_id: str,
        section_title: str,
    ) -> dict[str, Any] | None:
        payload = await self._request(
            "GET",
            f"/internal/v1/sources/{source_id}/sections/by-title",
            params={"workspace_id": workspace_id, "section_title": section_title},
        )
        data = payload.get("data")
        return dict(data) if isinstance(data, dict) else None

    async def get_source(self, source_id: str) -> SourcePayload | None:
        payload = await self._request("GET", f"/internal/v1/sources/{source_id}")
        data = payload.get("data")
        return SourcePayload.model_validate(data) if data is not None else None

    async def get_source_for_workspace(
        self,
        *,
        source_id: str,
        workspace_id: str,
        include_deleted: bool = False,
    ) -> SourcePayload | None:
        payload = await self._request(
            "GET",
            f"/internal/v1/sources/{source_id}/workspace-record",
            params={"workspace_id": workspace_id, "include_deleted": include_deleted},
        )
        data = payload.get("data")
        return SourcePayload.model_validate(data) if data is not None else None

    async def get_source_detail(
        self,
        *,
        source_id: str,
        workspace_id: str,
    ) -> dict[str, Any] | None:
        payload = await self._request(
            "GET",
            f"/internal/v1/sources/{source_id}/detail",
            params={"workspace_id": workspace_id},
        )
        data = payload.get("data")
        return dict(data) if isinstance(data, dict) else None

    async def list_source_assets(
        self,
        *,
        source_id: str,
        workspace_id: str,
    ) -> list[dict[str, Any]]:
        payload = await self._request(
            "GET",
            f"/internal/v1/sources/{source_id}/assets",
            params={"workspace_id": workspace_id},
        )
        return list(payload["data"])

    async def upsert_source_external_ids(
        self,
        *,
        source_id: str,
        workspace_id: str,
        external_ids: list[SourceExternalIdCreatePayload],
    ) -> list[dict[str, Any]]:
        payload = await self._request(
            "POST",
            f"/internal/v1/sources/{source_id}/external-ids",
            params={"workspace_id": workspace_id},
            json=[item.model_dump(mode="json") for item in external_ids],
        )
        return list(payload["data"])

    async def list_source_external_ids(
        self,
        *,
        source_id: str,
        workspace_id: str,
    ) -> list[dict[str, Any]]:
        payload = await self._request(
            "GET",
            f"/internal/v1/sources/{source_id}/external-ids",
            params={"workspace_id": workspace_id},
        )
        return list(payload["data"])

    async def link_source_asset(
        self,
        command: SourceAssetLinkPayload,
    ) -> dict[str, Any]:
        payload = await self._request(
            "POST",
            "/internal/v1/source-assets",
            json=command.model_dump(mode="json"),
        )
        return dict(payload["data"])

    async def get_source_asset(
        self,
        *,
        source_asset_id: str,
        workspace_id: str,
    ) -> dict[str, Any] | None:
        payload = await self._request(
            "GET",
            f"/internal/v1/source-assets/{source_asset_id}",
            params={"workspace_id": workspace_id},
        )
        data = payload.get("data")
        return dict(data) if isinstance(data, dict) else None

    async def update_source_asset(
        self,
        *,
        source_asset_id: str,
        workspace_id: str,
        command: SourceAssetUpdatePayload,
    ) -> dict[str, Any] | None:
        payload = await self._request(
            "PATCH",
            f"/internal/v1/source-assets/{source_asset_id}",
            params={"workspace_id": workspace_id},
            json=command.model_dump(mode="json", exclude_none=True),
        )
        data = payload.get("data")
        return dict(data) if isinstance(data, dict) else None

    async def mark_source_status(
        self,
        *,
        source_id: str,
        workspace_id: str,
        library_status: str | None = None,
        read_status: str | None = None,
    ) -> SourcePayload | None:
        payload = await self._request(
            "PATCH",
            f"/internal/v1/sources/{source_id}/status",
            params={"workspace_id": workspace_id},
            json={
                "library_status": library_status,
                "read_status": read_status,
            },
        )
        data = payload.get("data")
        return SourcePayload.model_validate(data) if data is not None else None

    async def update_source(
        self,
        *,
        source_id: str,
        workspace_id: str,
        command: SourceUpdatePayload,
    ) -> SourcePayload | None:
        payload = await self._request(
            "PATCH",
            f"/internal/v1/sources/{source_id}",
            params={"workspace_id": workspace_id},
            json=command.model_dump(mode="json", exclude_none=True),
        )
        data = payload.get("data")
        return SourcePayload.model_validate(data) if data is not None else None

    async def delete_source(
        self,
        *,
        source_id: str,
        workspace_id: str,
    ) -> bool:
        payload = await self._request(
            "DELETE",
            f"/internal/v1/sources/{source_id}",
            params={"workspace_id": workspace_id},
        )
        return bool(payload["data"].get("deleted"))

    async def build_source_bibliography(
        self,
        command: SourceBibliographyCreatePayload,
    ) -> SourceBibliographyPayload:
        payload = await self._request(
            "POST",
            "/internal/v1/sources/bibliography",
            json=command.model_dump(mode="json"),
        )
        return SourceBibliographyPayload.model_validate(payload["data"])

    async def build_bibliography(
        self,
        command: SourceBibliographyCreatePayload,
    ) -> SourceBibliographyPayload:
        return await self.build_source_bibliography(command)

    async def create_source_bibliography_snapshot(
        self,
        command: SourceBibliographySnapshotCreatePayload,
    ) -> SourceBibliographySnapshotPayload:
        payload = await self._request(
            "POST",
            "/internal/v1/sources/bibliography/snapshots",
            json=command.model_dump(mode="json"),
        )
        return SourceBibliographySnapshotPayload.model_validate(payload["data"])

    async def build_source_evidence_pack(
        self,
        command: SourceEvidencePackCreatePayload,
    ) -> SourceEvidencePackPayload:
        payload = await self._request(
            "POST",
            "/internal/v1/sources/evidence-pack",
            json=command.model_dump(mode="json"),
        )
        return SourceEvidencePackPayload.model_validate(payload["data"])

    async def replace_source_index(
        self,
        command: SourceIndexReplacePayload,
    ) -> dict[str, int]:
        payload = await self._request(
            "PUT",
            f"/internal/v1/sources/{command.source_id}/index",
            json=command.model_dump(mode="json"),
        )
        return {str(key): int(value) for key, value in dict(payload["data"]).items()}

    async def get_source_outline(
        self,
        *,
        source_id: str,
        workspace_id: str,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        payload = await self._request(
            "GET",
            f"/internal/v1/sources/{source_id}/outline",
            params={"workspace_id": workspace_id, "limit": limit},
        )
        return list(payload["data"])

    async def read_source_outline_node(
        self,
        *,
        source_id: str,
        workspace_id: str,
        outline_node_id: str,
    ) -> dict[str, Any] | None:
        payload = await self._request(
            "GET",
            f"/internal/v1/sources/{source_id}/outline/{outline_node_id}/content",
            params={"workspace_id": workspace_id},
        )
        data = payload.get("data")
        return dict(data) if isinstance(data, dict) else None

    async def read_source_pages(
        self,
        *,
        source_id: str,
        workspace_id: str,
        page_start: int,
        page_end: int,
    ) -> list[dict[str, Any]]:
        payload = await self._request(
            "GET",
            f"/internal/v1/sources/{source_id}/pages",
            params={
                "workspace_id": workspace_id,
                "page_start": page_start,
                "page_end": page_end,
            },
        )
        return list(payload["data"])

    async def record_source_citation_usage(
        self,
        command: SourceCitationUsageCreatePayload,
    ) -> SourceCitationUsagePayload:
        payload = await self._request(
            "POST",
            "/internal/v1/sources/citation-usage",
            json=command.model_dump(mode="json"),
        )
        return SourceCitationUsagePayload.model_validate(payload["data"])

    async def record_citation_usage(
        self,
        command: SourceCitationUsageCreatePayload,
    ) -> SourceCitationUsagePayload:
        return await self.record_source_citation_usage(command)

    async def create_provenance_link(
        self,
        command: ProvenanceLinkCreatePayload,
    ) -> ProvenanceLinkPayload:
        payload = await self._request(
            "POST",
            "/internal/v1/provenance/links",
            json=command.model_dump(mode="json"),
        )
        return ProvenanceLinkPayload.model_validate(payload["data"])

    async def list_provenance_links(
        self,
        *,
        workspace_id: str,
        source_id: str | None = None,
        target_domain: str | None = None,
        target_kind: str | None = None,
        target_id: str | None = None,
        review_item_id: str | None = None,
        relation_kind: str | None = None,
        limit: int = 50,
    ) -> list[ProvenanceLinkPayload]:
        payload = await self._request(
            "GET",
            "/internal/v1/provenance/links",
            params={
                "workspace_id": workspace_id,
                "source_id": source_id,
                "target_domain": target_domain,
                "target_kind": target_kind,
                "target_id": target_id,
                "review_item_id": review_item_id,
                "relation_kind": relation_kind,
                "limit": limit,
            },
        )
        return [ProvenanceLinkPayload.model_validate(item) for item in payload["data"]]

    async def delete_provenance_links(
        self,
        *,
        workspace_id: str,
        source_id: str | None = None,
        target_domain: str | None = None,
        target_kind: str | None = None,
        target_id: str | None = None,
        review_item_id: str | None = None,
        relation_kind: str | None = None,
    ) -> int:
        payload = await self._request(
            "DELETE",
            "/internal/v1/provenance/links",
            params={
                "workspace_id": workspace_id,
                "source_id": source_id,
                "target_domain": target_domain,
                "target_kind": target_kind,
                "target_id": target_id,
                "review_item_id": review_item_id,
                "relation_kind": relation_kind,
            },
        )
        data = payload.get("data") or {}
        return int(data.get("deleted") or 0)
