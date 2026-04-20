"""Tests for Docker client wrapper."""

from unittest.mock import AsyncMock, patch

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
            result = await client.ensure_image("wenjin/texlive:2024")

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
            result = await client.ensure_image("wenjin/texlive:2024")

        assert result is True
        mock_docker.from_env.return_value.images.pull.assert_called_with(
            "wenjin/texlive:2024"
        )

    def test_build_volume_mapping(self, client):
        """Should create proper volume mapping."""
        mapping = client.build_volume_mapping("/host/path", "/container/path", "rw")

        assert mapping == {
            "/host/path": {"bind": "/container/path", "mode": "rw"}
        }

    @pytest.mark.asyncio
    async def test_run_container_timeout_still_removes_container(self, client, mock_docker):
        """Timeout path must still remove the created container to avoid leaks."""
        container = mock_docker.from_env.return_value.containers.run.return_value
        container.id = "abcdef123456"
        container.wait.side_effect = RuntimeError("wait timeout")
        container.kill.return_value = None
        container.remove.return_value = None

        with patch.object(client, "ensure_image", AsyncMock(return_value=True)):
            with pytest.raises(TimeoutError):
                await client.run_container(
                    image="wenjin/sandbox:test",
                    command=["/bin/sh", "-lc", "sleep 999"],
                    timeout=1,
                    remove=True,
                )

        container.remove.assert_called_once_with(force=True)

    @pytest.mark.asyncio
    async def test_cleanup_containers_by_label_removes_matches(self, client, mock_docker):
        """cleanup_containers_by_label should remove every listed container."""
        c1 = mock_docker.from_env.return_value.containers.run.return_value
        c2 = type("ContainerStub", (), {"id": "deadbeef1234", "remove": lambda self, force=True: None})()
        mock_docker.from_env.return_value.containers.list.return_value = [c1, c2]
        c1.id = "abcabcabcabc"
        c1.remove.return_value = None

        removed = await client.cleanup_containers_by_label(
            {"wenjin.sandbox.managed": "true", "wenjin.sandbox.kind": "sandbox_exec"}
        )

        assert removed == 2
        mock_docker.from_env.return_value.containers.list.assert_called_once_with(
            all=True,
            filters={"label": ["wenjin.sandbox.managed=true", "wenjin.sandbox.kind=sandbox_exec"]},
        )
