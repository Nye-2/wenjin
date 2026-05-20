"""Source library domain service."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.domains.source.contracts import SourceCreateCommand, SourceProjection
from src.dataservice.domains.source.projection import source_to_projection
from src.dataservice.domains.source.repository import SourceRepository


class SourceDataDomainService:
    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self.session = session
        self.autocommit = autocommit
        self.repository = SourceRepository(session)

    async def create_source(self, command: SourceCreateCommand) -> SourceProjection:
        normalized_title = command.normalized_title or command.title.strip().lower()
        record = self.repository.create_source(
            {
                **command.model_dump(exclude={"normalized_title"}),
                "normalized_title": normalized_title,
            }
        )
        await self._finish()
        return source_to_projection(record)

    async def get_source(self, source_id: str) -> SourceProjection | None:
        record = await self.repository.get_source(source_id)
        return source_to_projection(record) if record else None

    async def list_sources(
        self,
        *,
        workspace_id: str,
        library_status: str | None = None,
        include_deleted: bool = False,
        limit: int = 50,
    ) -> list[SourceProjection]:
        return [
            source_to_projection(record)
            for record in await self.repository.list_sources(
                workspace_id=workspace_id,
                library_status=library_status,
                include_deleted=include_deleted,
                limit=limit,
            )
        ]

    async def _finish(self) -> None:
        if self.autocommit:
            await self.session.commit()
        else:
            await self.session.flush()
