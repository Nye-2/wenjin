"""Tests for DockerExecutionService."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.execution.path_utils import normalize_thread_id
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
        assert ExecutionType.PYTHON_PLOT in service.PROVIDER_MAP
        assert ExecutionType.MERMAID_DIAGRAM in service.PROVIDER_MAP
        assert ExecutionType.AI_IMAGE in service.PROVIDER_MAP

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

    def test_prepare_work_dir_is_unique_per_call(self, service):
        request = ExecutionRequest(
            execution_type=ExecutionType.LATEX_COMPILE,
            content="test",
            thread_id="test-thread",
        )
        first = service._prepare_work_dir(request)
        second = service._prepare_work_dir(request)
        assert first != second

    def test_prepare_work_dir_sanitizes_thread_id(self, service, temp_dir):
        unsafe_thread_id = "../../unsafe//thread"
        request = ExecutionRequest(
            execution_type=ExecutionType.LATEX_COMPILE,
            content="test",
            thread_id=unsafe_thread_id,
        )
        work_dir = service._prepare_work_dir(request)
        relative_parts = work_dir.relative_to(Path(temp_dir)).parts

        assert relative_parts[0] == normalize_thread_id(unsafe_thread_id)
        assert ".." not in relative_parts
