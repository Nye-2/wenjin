"""Shared context for Source domain subservices."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.domains.provenance.repository import ProvenanceRepository
from src.dataservice.domains.source.repository import SourceRepository


@dataclass(slots=True)
class SourceDomainContext:
    session: AsyncSession
    repository: SourceRepository
    provenance_repository: ProvenanceRepository
    autocommit: bool = True

    async def finish(self) -> None:
        if self.autocommit:
            await self.session.commit()
        else:
            await self.session.flush()
