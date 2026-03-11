"""Test configuration and fixtures."""

import asyncio
import subprocess
from collections.abc import Generator

import pytest
import pytest_asyncio


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create an event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def docker_available():
    """Check if Docker is available and running."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


@pytest_asyncio.fixture
async def mock_db_session():
    """Mock database session for tests."""
    # TODO: Add actual mock implementation
    pass
