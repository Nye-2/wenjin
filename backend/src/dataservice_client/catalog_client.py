"""Typed client methods for the Mission policy catalog."""

from src.dataservice_client.contracts.catalog import CatalogSeedLoadPayload, CatalogSeedLoadResultPayload, MissionPolicyPayload, WorkerSkillPayload


class CatalogDataServiceClientMixin:
    async def list_mission_policies(self, *, workspace_type: str | None = None, enabled_only: bool = False) -> list[MissionPolicyPayload]:
        payload = await self._request("GET", "/internal/v1/catalog/mission-policies", params={"workspace_type": workspace_type, "enabled_only": enabled_only})
        return [MissionPolicyPayload.model_validate(item) for item in payload["data"]]

    async def has_mission_policies(self) -> bool:
        payload = await self._request("GET", "/internal/v1/catalog/mission-policies/exists")
        return bool(payload["data"]["exists"])

    async def get_mission_policy(self, *, policy_id: str, workspace_type: str) -> MissionPolicyPayload:
        payload = await self._request("GET", f"/internal/v1/catalog/mission-policies/{workspace_type}/{policy_id}")
        return MissionPolicyPayload.model_validate(payload["data"])

    async def load_mission_policy_seed_items(self, command: CatalogSeedLoadPayload) -> CatalogSeedLoadResultPayload:
        payload = await self._request("POST", "/internal/v1/catalog/mission-policies/seed-load", json=command.model_dump(mode="json"))
        return CatalogSeedLoadResultPayload.model_validate(payload["data"])

    async def list_worker_skills(self, *, enabled_only: bool = False) -> list[WorkerSkillPayload]:
        payload = await self._request("GET", "/internal/v1/catalog/worker-skills", params={"enabled_only": enabled_only})
        return [WorkerSkillPayload.model_validate(item) for item in payload["data"]]

    async def has_worker_skills(self) -> bool:
        payload = await self._request("GET", "/internal/v1/catalog/worker-skills/exists")
        return bool(payload["data"]["exists"])

    async def get_worker_skill(self, skill_id: str) -> WorkerSkillPayload:
        payload = await self._request("GET", f"/internal/v1/catalog/worker-skills/{skill_id}")
        return WorkerSkillPayload.model_validate(payload["data"])

    async def load_worker_skill_seed_items(self, command: CatalogSeedLoadPayload) -> CatalogSeedLoadResultPayload:
        payload = await self._request("POST", "/internal/v1/catalog/worker-skills/seed-load", json=command.model_dump(mode="json"))
        return CatalogSeedLoadResultPayload.model_validate(payload["data"])
