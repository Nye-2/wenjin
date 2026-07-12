from __future__ import annotations

import os

import pytest

from src.sandbox.config import get_sandbox_settings
from src.sandbox.preflight import run_sandbox_preflight


@pytest.mark.integration
@pytest.mark.asyncio
async def test_configured_production_docker_profile_passes_release_preflight() -> None:
    if os.getenv("WENJIN_SANDBOX_DOCKER_INTEGRATION") != "1":
        pytest.skip("set WENJIN_SANDBOX_DOCKER_INTEGRATION=1 on the sandbox worker host")

    report = await run_sandbox_preflight(get_sandbox_settings(), release_gate=True)

    assert report.release_ready, report.model_dump(mode="json")
    assert not report.development_override
