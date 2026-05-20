"""Provenance graph domain service."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.domains.provenance.contracts import (
    ProvenanceLinkCreateCommand,
    ProvenanceLinkProjection,
)
from src.dataservice.domains.provenance.projection import provenance_link_to_projection
from src.dataservice.domains.provenance.repository import ProvenanceRepository


class ProvenanceDataDomainService:
    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self.session = session
        self.autocommit = autocommit
        self.repository = ProvenanceRepository(session)

    async def create_link(self, command: ProvenanceLinkCreateCommand) -> ProvenanceLinkProjection:
        record = self.repository.create_link(command.model_dump())
        await self._finish()
        return provenance_link_to_projection(record)

    async def list_links(
        self,
        *,
        workspace_id: str,
        source_id: str | None = None,
        target_domain: str | None = None,
        target_id: str | None = None,
        limit: int = 50,
    ) -> list[ProvenanceLinkProjection]:
        return [
            provenance_link_to_projection(record)
            for record in await self.repository.list_links(
                workspace_id=workspace_id,
                source_id=source_id,
                target_domain=target_domain,
                target_id=target_id,
                limit=limit,
            )
        ]

    async def _finish(self) -> None:
        if self.autocommit:
            await self.session.commit()
        else:
            await self.session.flush()
