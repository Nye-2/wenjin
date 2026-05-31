"""Source asset service."""

from __future__ import annotations

from datetime import UTC, datetime

from src.dataservice.domains.source.context import SourceDomainContext
from src.dataservice.domains.source.contracts import SourceAssetUpdateCommand
from src.dataservice.domains.source.helpers import serialize_source_asset


class SourceAssetService:
    def __init__(self, context: SourceDomainContext) -> None:
        self.context = context

    async def link_source_asset(
        self,
        *,
        workspace_id: str,
        source_id: str,
        workspace_asset_id: str,
        asset_type: str,
        source_asset_id: str | None = None,
        preprocess_status: str = "skipped",
        manifest_asset_id: str | None = None,
        metadata_json: dict[str, object] | None = None,
    ) -> dict[str, object]:
        values = {
            "workspace_id": workspace_id,
            "source_id": source_id,
            "workspace_asset_id": workspace_asset_id,
            "asset_type": asset_type,
            "preprocess_status": preprocess_status,
            "manifest_asset_id": manifest_asset_id,
            "metadata_json": dict(metadata_json or {}),
        }
        record = await self.context.repository.get_source_asset(source_asset_id) if source_asset_id else None
        if record is None:
            record = self.context.repository.create_source_asset(
                {
                    **values,
                    **({"id": source_asset_id} if source_asset_id else {}),
                }
            )
        else:
            for field, value in values.items():
                setattr(record, field, value)
            record.updated_at = datetime.now(UTC)
        await self.context.finish()
        return serialize_source_asset(record, None)

    async def get_source_asset(
        self,
        *,
        workspace_id: str,
        source_asset_id: str,
    ) -> dict[str, object] | None:
        record = await self.context.repository.get_source_asset(source_asset_id)
        if record is None or str(record.workspace_id) != workspace_id:
            return None
        return serialize_source_asset(record, None)

    async def update_source_asset(
        self,
        *,
        workspace_id: str,
        source_asset_id: str,
        command: SourceAssetUpdateCommand,
    ) -> dict[str, object] | None:
        record = await self.context.repository.get_source_asset(source_asset_id)
        if record is None or str(record.workspace_id) != workspace_id:
            return None
        if command.preprocess_status is not None:
            record.preprocess_status = command.preprocess_status
        if command.manifest_asset_id is not None:
            record.manifest_asset_id = command.manifest_asset_id
        if command.metadata_json is not None:
            record.metadata_json = {
                **dict(record.metadata_json or {}),
                **dict(command.metadata_json or {}),
            }
        record.updated_at = datetime.now(UTC)
        await self.context.finish()
        return serialize_source_asset(record, None)

    async def list_source_assets(self, *, workspace_id: str, source_id: str) -> list[dict[str, object]]:
        return [
            serialize_source_asset(source_asset, workspace_asset)
            for source_asset, workspace_asset in await self.context.repository.list_source_assets(
                workspace_id=workspace_id,
                source_id=source_id,
            )
        ]
