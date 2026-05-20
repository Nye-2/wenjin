"""Catalog seed loading owned by DataService."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from src.dataservice.domains.catalog.contracts import SeedLoadResult
from src.dataservice.domains.catalog.service import DataServiceCatalogService

SeedValidator = Callable[[Path, str], dict[str, Any]]
DeleteCommand = Callable[[], Awaitable[None]]
UpsertCommand = Callable[[dict[str, Any], str, str], Awaitable[Any]]


class DataServiceCatalogSeedLoader:
    """Read YAML seed files and apply them as catalog revisions."""

    def __init__(self, service: DataServiceCatalogService, seed_dir: Path) -> None:
        self.service = service
        self.seed_dir = Path(seed_dir)

    async def load_capabilities(
        self,
        *,
        validate_yaml_text: SeedValidator,
        overwrite: bool = False,
    ) -> SeedLoadResult:
        return await self._load(
            catalog_kind="capabilities",
            schema_version="capability.v2",
            glob_pattern="*/*.yaml",
            validate_yaml_text=validate_yaml_text,
            overwrite=overwrite,
            delete_all=self.service.delete_all_capabilities,
            upsert=self._upsert_capability,
        )

    async def load_skills(
        self,
        *,
        validate_yaml_text: SeedValidator,
        overwrite: bool = False,
    ) -> SeedLoadResult:
        return await self._load(
            catalog_kind="skills",
            schema_version="capability_skill.v2",
            glob_pattern="*.yaml",
            validate_yaml_text=validate_yaml_text,
            overwrite=overwrite,
            delete_all=self.service.delete_all_skills,
            upsert=self._upsert_skill,
        )

    async def _load(
        self,
        *,
        catalog_kind: str,
        schema_version: str,
        glob_pattern: str,
        validate_yaml_text: SeedValidator,
        overwrite: bool,
        delete_all: DeleteCommand,
        upsert: UpsertCommand,
    ) -> SeedLoadResult:
        seed_items = self._read_seed_items(
            glob_pattern=glob_pattern,
            validate_yaml_text=validate_yaml_text,
        )
        if not seed_items:
            return SeedLoadResult(loaded=0, skipped=False, checksum=None)

        root_checksum = self._root_checksum(seed_items)
        seed_root = str(self.seed_dir)
        if not overwrite and await self.service.seed_revision_matches(
            catalog_kind=catalog_kind,
            seed_root=seed_root,
            checksum=root_checksum,
        ):
            return SeedLoadResult(loaded=0, skipped=True, checksum=root_checksum)

        original_autocommit = self.service.autocommit
        self.service.autocommit = False
        try:
            if overwrite:
                await delete_all()
            for item in seed_items:
                await upsert(item["data"], item["checksum"], item["source_path"])

            result = await self.service.record_seed_revision(
                catalog_kind=catalog_kind,
                seed_root=seed_root,
                checksum=root_checksum,
                loaded_count=len(seed_items),
                metadata_json={
                    "paths": [item["source_path"] for item in seed_items],
                    "schema_version": schema_version,
                },
            )
            if original_autocommit:
                await self.service.session.commit()
            return result
        finally:
            self.service.autocommit = original_autocommit

    def _read_seed_items(
        self,
        *,
        glob_pattern: str,
        validate_yaml_text: SeedValidator,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for yaml_path in sorted(self.seed_dir.glob(glob_pattern)):
            text = yaml_path.read_text(encoding="utf-8")
            items.append(
                {
                    "data": validate_yaml_text(yaml_path, text),
                    "checksum": DataServiceCatalogService.checksum_text(text),
                    "source_path": str(yaml_path),
                }
            )
        return items

    @staticmethod
    def _root_checksum(items: list[dict[str, Any]]) -> str:
        material = "\n".join(f"{item['source_path']}:{item['checksum']}" for item in items)
        return DataServiceCatalogService.checksum_text(material)

    async def _upsert_capability(self, data: dict[str, Any], checksum: str, source_path: str) -> Any:
        return await self.service.upsert_capability(
            data,
            checksum=checksum,
            source_path=source_path,
        )

    async def _upsert_skill(self, data: dict[str, Any], checksum: str, source_path: str) -> Any:
        return await self.service.upsert_skill(
            data,
            checksum=checksum,
            source_path=source_path,
        )
