"""Tests for Docker client wrapper."""

from unittest.mock import patch

import pytest

from src.execution.docker.client import DockerClient


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

    @pytest.mark.asyncio
    async def test_ensure_image_loads_from_local_archive_before_pull(
        self,
        client,
        mock_docker,
    ):
        """Should prefer local archive loading when image is missing."""
        from docker.errors import ImageNotFound

        mock_docker.from_env.return_value.images.get.side_effect = ImageNotFound("test")

        with patch.object(client, "_try_load_local_archive", return_value=True):
            result = await client.ensure_image("academiagpt/texlive:2024")

        assert result is True
        mock_docker.from_env.return_value.images.pull.assert_not_called()

    @pytest.mark.asyncio
    async def test_ensure_image_pulls_when_local_archive_load_fails(
        self,
        client,
        mock_docker,
    ):
        """Should pull from registry when local archive loading fails."""
        from docker.errors import ImageNotFound

        mock_docker.from_env.return_value.images.get.side_effect = ImageNotFound("test")
        mock_docker.from_env.return_value.images.pull.return_value = None

        with patch.object(client, "_try_load_local_archive", return_value=False):
            result = await client.ensure_image("academiagpt/texlive:2024")

        assert result is True
        mock_docker.from_env.return_value.images.pull.assert_called_with(
            "academiagpt/texlive:2024"
        )

    def test_build_volume_mapping(self, client):
        """Should create proper volume mapping."""
        mapping = client.build_volume_mapping("/host/path", "/container/path", "rw")

        assert mapping == {
            "/host/path": {"bind": "/container/path", "mode": "rw"}
        }
