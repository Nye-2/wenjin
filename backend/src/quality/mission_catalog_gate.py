"""Live Mission catalog release gate."""

from __future__ import annotations

import asyncio
import json

from src.dataservice_client.provider import dataservice_client
from src.services.mission_catalog_readiness import evaluate_mission_catalog_readiness
from src.services.model_catalog_cache import (
    get_default_runtime_model_id,
    get_runtime_model_config,
    refresh_model_catalog_cache,
)


async def evaluate_live_catalog() -> dict:
    async with dataservice_client() as client:
        await refresh_model_catalog_cache(client)
        policies = await client.list_mission_policies(enabled_only=True)
        skills = await client.list_worker_skills(enabled_only=True)
    model = get_runtime_model_config(get_default_runtime_model_id())
    return evaluate_mission_catalog_readiness(
        policies,
        skills,
        mission_model=model,
    )


def main() -> int:
    try:
        report = asyncio.run(evaluate_live_catalog())
    except Exception as exc:
        report = {"status": "unhealthy", "error": str(exc)}
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report.get("status") == "healthy" else 1


if __name__ == "__main__":
    raise SystemExit(main())
