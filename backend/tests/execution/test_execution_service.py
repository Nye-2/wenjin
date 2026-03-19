"""Tests for DockerExecutionService."""

from unittest.mock import AsyncMock, patch

import pytest

from src.execution.service import DockerExecutionService
from src.execution.types import ExecutionRequest, ExecutionType


class TestDockerExecutionService:
    """Tests for DockerExecutionService."""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        """Create temporary directory."""
        return str(tmp_path)

    @pytest.fixture
    def service(self, temp_dir):
        """Create DockerExecutionService instance."""
        return DockerExecutionService(sandbox_base_dir=temp_dir)

    def test_provider_map_has_all_types(self, service):
        """Should have providers for all execution types."""
        assert ExecutionType.LATEX_COMPILE in service.PROVIDER_MAP
        # Others will be added in later phases

    @pytest.mark.asyncio
    async def test_health_check(self, service):
        """Should return health status."""
        with patch.object(service.docker_client, 'health_check', new_callable=AsyncMock) as mock:
            mock.return_value = {"status": "healthy"}
            result = await service.health_check()
            assert result["status"] == "healthy"

    def test_prepare_work_dir(self, service, temp_dir):
        """Should create working directory."""
        request = ExecutionRequest(
            execution_type=ExecutionType.LATEX_COMPILE,
            content="test",
            thread_id="test-thread",
        )
        work_dir = service._prepare_work_dir(request)

        assert work_dir.exists()
        assert "test-thread" in str(work_dir)
        assert "latex_compile" in str(work_dir)
