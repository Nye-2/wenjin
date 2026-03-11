"""Tests for Docker client wrapper."""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from src.execution.docker.client import DockerClient, DockerExecutionError


class TestDockerClient:
    """Tests for DockerClient."""

    @pytest.fixture
    def mock_docker(self):
        """Mock docker module."""
        with patch("src.execution.docker.client.docker") as mock:
            yield mock

    @pytest.fixture
    def client(self, mock_docker):
        """Create DockerClient instance."""
        return DockerClient()

    def test_client_initialization(self, client):
        """Should initialize without immediate connection."""
        assert client._client is None

    def test_lazy_client_creation(self, client, mock_docker):
        """Should create client lazily."""
        _ = client.client
        mock_docker.from_env.assert_called_once()

    @pytest.mark.asyncio
    async def test_ensure_image_exists(self, client, mock_docker):
        """Should not pull if image exists."""
        mock_docker.from_env.return_value.images.get.return_value = True

        result = await client.ensure_image("test:latest")

        assert result is True
        mock_docker.from_env.return_value.images.pull.assert_not_called()

    @pytest.mark.asyncio
    async def test_ensure_image_pulls_if_missing(self, client, mock_docker):
        """Should pull if image doesn't exist."""
        from docker.errors import ImageNotFound
        mock_docker.from_env.return_value.images.get.side_effect = ImageNotFound("test")
        mock_docker.from_env.return_value.images.pull.return_value = None

        result = await client.ensure_image("test:latest")

        assert result is True
        mock_docker.from_env.return_value.images.pull.assert_called_with("test:latest")

    def test_build_volume_mapping(self, client):
        """Should create proper volume mapping."""
        mapping = client.build_volume_mapping("/host/path", "/container/path", "rw")

        assert mapping == {
            "/host/path": {"bind": "/container/path", "mode": "rw"}
        }
