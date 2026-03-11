"""Docker client wrapper for container execution.

Provides a clean async interface for Docker operations with lazy initialization,
proper error handling, and volume management.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import docker
from docker.errors import DockerException, ImageNotFound, APIError

logger = logging.getLogger(__name__)

# Shared thread pool for Docker operations
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="docker-")


class DockerExecutionError(Exception):
    """Exception raised for Docker execution failures."""

    def __init__(self, message: str, original_error: Exception | None = None):
        super().__init__(message)
        self.original_error = original_error


class DockerClient:
    """Async wrapper around Docker SDK.

    Features:
    - Lazy client initialization (no immediate connection)
    - Async methods using run_in_executor
    - Image management (pull if missing)
    - Volume mapping helpers
    - Health checking
    """

    def __init__(self) -> None:
        """Initialize DockerClient without immediate connection."""
        self._client: docker.DockerClient | None = None

    @property
    def client(self) -> docker.DockerClient:
        """Get Docker client, creating it lazily.

        Returns:
            Docker client instance.

        Raises:
            DockerExecutionError: If connection fails.
        """
        if self._client is None:
            try:
                self._client = docker.from_env()
                logger.debug("Docker client initialized")
            except DockerException as e:
                raise DockerExecutionError(
                    f"Failed to connect to Docker: {e}",
                    original_error=e
                ) from e
        return self._client

    async def ensure_image(self, image: str) -> bool:
        """Ensure Docker image exists, pulling if necessary.

        Args:
            image: Image name with optional tag (e.g., "python:3.12").

        Returns:
            True if image is available.

        Raises:
            DockerExecutionError: If image pull fails.
        """
        def _ensure() -> bool:
            try:
                # Check if image exists
                self.client.images.get(image)
                logger.debug(f"Image already exists: {image}")
                return True
            except ImageNotFound:
                # Pull the image
                logger.info(f"Pulling image: {image}")
                try:
                    self.client.images.pull(image)
                    logger.info(f"Successfully pulled image: {image}")
                    return True
                except (APIError, DockerException) as e:
                    raise DockerExecutionError(
                        f"Failed to pull image {image}: {e}",
                        original_error=e
                    ) from e

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_executor, _ensure)

    def build_volume_mapping(
        self,
        host_path: str,
        container_path: str,
        mode: str = "rw"
    ) -> dict[str, dict[str, str]]:
        """Build Docker volume mapping.

        Args:
            host_path: Path on host machine.
            container_path: Path inside container.
            mode: Access mode ("rw" for read-write, "ro" for read-only).

        Returns:
            Volume mapping dictionary for Docker API.
        """
        return {
            host_path: {
                "bind": container_path,
                "mode": mode
            }
        }

    async def run_container(
        self,
        image: str,
        command: list[str] | None = None,
        volumes: dict[str, dict[str, str]] | None = None,
        working_dir: str | None = None,
        environment: dict[str, str] | None = None,
        timeout: int = 120,
        remove: bool = True,
        **kwargs: Any
    ) -> tuple[int, str, str]:
        """Run a Docker container and return results.

        Args:
            image: Docker image name.
            command: Command to run in container.
            volumes: Volume mappings from build_volume_mapping().
            working_dir: Working directory inside container.
            environment: Environment variables.
            timeout: Execution timeout in seconds.
            remove: Whether to remove container after execution.
            **kwargs: Additional container creation options.

        Returns:
            Tuple of (exit_code, stdout, stderr).

        Raises:
            DockerExecutionError: If container execution fails.
            TimeoutError: If execution exceeds timeout.
        """
        # Ensure image exists
        await self.ensure_image(image)

        def _run() -> tuple[int, str, str]:
            try:
                # Create and run container
                container = self.client.containers.run(
                    image=image,
                    command=command,
                    volumes=volumes,
                    working_dir=working_dir,
                    environment=environment or {},
                    detach=True,
                    **kwargs
                )

                logger.debug(f"Started container: {container.id[:12]}")

                # Wait for completion with timeout
                try:
                    result = container.wait(timeout=timeout)
                    exit_code = result.get("StatusCode", -1)
                except Exception as e:
                    # Kill container on timeout
                    try:
                        container.kill()
                    except Exception:
                        pass
                    logger.warning(f"Container killed due to error: {container.id[:12]}")
                    raise TimeoutError(
                        f"Container execution exceeded {timeout}s or failed: {e}"
                    ) from e

                # Get logs
                stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
                stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")

                # Remove container if requested
                if remove:
                    try:
                        container.remove(force=True)
                        logger.debug(f"Removed container: {container.id[:12]}")
                    except Exception as e:
                        logger.warning(f"Failed to remove container: {e}")

                return exit_code, stdout, stderr

            except DockerException as e:
                raise DockerExecutionError(
                    f"Container execution failed: {e}",
                    original_error=e
                ) from e

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_executor, _run)

    async def health_check(self) -> dict[str, Any]:
        """Check Docker daemon health.

        Returns:
            Health status dictionary with:
            - healthy: bool
            - version: str (if healthy)
            - error: str (if unhealthy)
        """
        def _check() -> dict[str, Any]:
            try:
                version_info = self.client.version()
                return {
                    "healthy": True,
                    "version": version_info.get("Version", "unknown"),
                    "api_version": version_info.get("ApiVersion", "unknown"),
                }
            except DockerException as e:
                return {
                    "healthy": False,
                    "error": str(e)
                }

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_executor, _check)

    def close(self) -> None:
        """Close Docker client connection."""
        if self._client is not None:
            self._client.close()
            self._client = None
            logger.debug("Docker client closed")
