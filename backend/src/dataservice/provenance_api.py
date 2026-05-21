"""Public in-process provenance API for DataService."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.domains.provenance.contracts import (
    ProvenanceLinkCreateCommand,
    ProvenanceLinkProjection,
)
from src.dataservice.domains.provenance.service import ProvenanceDataDomainService


class ProvenanceDataService:
    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self._domain = ProvenanceDataDomainService(session, autocommit=autocommit)

    async def create_link(self, command: ProvenanceLinkCreateCommand) -> ProvenanceLinkProjection:
        return await self._domain.create_link(command)

    async def list_links(
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
    ) -> list[ProvenanceLinkProjection]:
        return await self._domain.list_links(
            workspace_id=workspace_id,
            source_id=source_id,
            target_domain=target_domain,
            target_kind=target_kind,
            target_id=target_id,
            review_item_id=review_item_id,
            relation_kind=relation_kind,
            limit=limit,
        )

    async def delete_links(
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
        return await self._domain.delete_links(
            workspace_id=workspace_id,
            source_id=source_id,
            target_domain=target_domain,
            target_kind=target_kind,
            target_id=target_id,
            review_item_id=review_item_id,
            relation_kind=relation_kind,
        )
