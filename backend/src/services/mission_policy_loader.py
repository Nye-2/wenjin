"""Load content-addressed MissionPolicy bundles from YAML into the catalog."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from src.contracts.mission_policy import MissionPolicy
from src.contracts.stage_acceptance import StageAcceptanceContract
from src.dataservice.domains.catalog.service import MissionCatalogService
from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.catalog import CatalogSeedItemPayload, CatalogSeedLoadPayload
from src.dataservice_client.provider import dataservice_client
from src.services.mission_policy_schema import resolve_mission_policy_bundle

logger = logging.getLogger(__name__)

DEFAULT_POLICY_SEED_DIR = Path(__file__).resolve().parent.parent.parent / "seed" / "mission_policies"


class MissionPolicyLoader:
    """Resolve MissionPolicy seeds and their pinned StageAcceptanceContracts."""

    def __init__(
        self,
        seed_dir: Path | str | None = None,
        dataservice: AsyncDataServiceClient | None = None,
    ) -> None:
        self.seed_dir = Path(seed_dir) if seed_dir is not None else DEFAULT_POLICY_SEED_DIR
        self._dataservice = dataservice

    async def load_policies_if_empty(self) -> int:
        if self._dataservice is not None:
            has_policies = await self._dataservice.has_mission_policies()
        else:
            async with dataservice_client() as client:
                has_policies = await client.has_mission_policies()
        if has_policies:
            return 0
        return await self._load_all_dataservice(overwrite=False)

    async def load_all(self, overwrite: bool = False) -> list[object]:
        await self._load_all_dataservice(overwrite=overwrite)
        if self._dataservice is not None:
            return await self._dataservice.list_mission_policies()
        async with dataservice_client() as client:
            return await client.list_mission_policies()

    async def sync_policy_updates(self) -> int:
        if self._dataservice is not None:
            return await self._sync_policy_updates(self._dataservice)
        async with dataservice_client() as client:
            return await self._sync_policy_updates(client)

    async def sync_with_service(self, service: MissionCatalogService) -> int:
        """Synchronize seed-owned policies through the caller's database transaction."""
        items = self.select_seed_updates(await service.list_policies())
        if not items:
            return 0
        return await service.load_policies(items, overwrite=False)

    async def _sync_policy_updates(self, client: AsyncDataServiceClient) -> int:
        seed_items = self.select_seed_updates(await client.list_mission_policies())
        if not seed_items:
            return 0
        result = await client.load_mission_policy_seed_items(self._seed_command(seed_items, overwrite=False))
        return result.loaded

    async def _load_all_dataservice(self, *, overwrite: bool) -> int:
        items = self.read_seed_items()
        command = self._seed_command(items, overwrite=overwrite)
        if self._dataservice is not None:
            result = await self._dataservice.load_mission_policy_seed_items(command)
        else:
            async with dataservice_client() as client:
                result = await client.load_mission_policy_seed_items(command)
        if result.loaded:
            logger.info("Loaded %d MissionPolicy seed(s) from %s", result.loaded, self.seed_dir)
        return result.loaded

    def _seed_command(
        self,
        items: list[dict[str, Any]],
        *,
        overwrite: bool,
    ) -> CatalogSeedLoadPayload:
        return CatalogSeedLoadPayload(
            overwrite=overwrite,
            items=[
                CatalogSeedItemPayload(
                    data=item["data"],
                    source_path=item["source_path"],
                )
                for item in items
            ],
        )

    def select_seed_updates(self, existing_records: list[object]) -> list[dict[str, Any]]:
        existing = {(str(getattr(record, "workspace_type", "")), str(getattr(record, "id", ""))): record for record in existing_records}
        updates: list[dict[str, Any]] = []
        for item in self.read_seed_items():
            data = item["data"]
            record = existing.get((str(data["workspace_type"]), str(data["id"])))
            if record is None:
                updates.append(item)
                continue
            source_path = str(getattr(record, "source_path", "") or "")
            content_hash = str(getattr(record, "content_hash", "") or "")
            if source_path != item["source_path"] or content_hash != item["data"]["content_hash"]:
                updates.append(item)
        return updates

    def read_seed_items(self) -> list[dict[str, Any]]:
        policies: list[tuple[Path, MissionPolicy]] = []
        contracts: list[StageAcceptanceContract] = []
        for yaml_path in sorted(self.seed_dir.rglob("*.yaml")):
            for index, raw in enumerate(yaml.safe_load_all(yaml_path.read_text(encoding="utf-8")), start=1):
                if raw is None:
                    continue
                if not isinstance(raw, dict):
                    raise ValueError(f"Expected dict in {yaml_path} document {index}")
                schema_version = raw.get("schema_version")
                try:
                    if schema_version == "mission_policy.v1":
                        policies.append((yaml_path, MissionPolicy.model_validate(raw)))
                    elif schema_version == "stage_acceptance_contract.v1":
                        contracts.append(StageAcceptanceContract.model_validate(raw))
                    else:
                        raise ValueError(f"unsupported schema_version {schema_version!r}")
                except Exception as exc:
                    raise ValueError(f"Invalid mission policy seed in {yaml_path} document {index}: {exc}") from exc

        contract_ids = [contract.contract_id for contract in contracts]
        if len(contract_ids) != len(set(contract_ids)):
            raise ValueError("duplicate stage acceptance contract ids across seed files")

        items: list[dict[str, Any]] = []
        for path, policy in policies:
            bundle = resolve_mission_policy_bundle(policy, contracts)
            items.append(
                {
                    "data": bundle.to_catalog_data(),
                    "source_path": path.relative_to(self.seed_dir).as_posix(),
                }
            )
        if not items:
            raise ValueError(f"No mission_policy.v1 seeds found in {self.seed_dir}")
        return items
