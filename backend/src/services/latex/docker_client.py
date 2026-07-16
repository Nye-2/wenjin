"""Docker client wrapper for container execution.

Provides a clean async interface for Docker operations with lazy initialization,
proper error handling, and volume management.
"""

import asyncio
import logging
import os
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, BinaryIO, Protocol, cast

from docker.errors import APIError, DockerException, ImageNotFound

import docker

logger = logging.getLogger(__name__)

# Shared thread pool for Docker operations
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="docker-")
_LATEX_IMAGE = "wenjin/texlive:2024"
_LATEX_IMAGE_ARCHIVE = "wenjin-texlive-2024.tar"
SANDBOX_MANAGED_LABEL = "wenjin.sandbox.managed"
SANDBOX_KIND_LABEL = "wenjin.sandbox.kind"
SANDBOX_THREAD_LABEL = "wenjin.sandbox.thread_id"


class DockerImagesProtocol(Protocol):
    """Subset of Docker image operations used by the wrapper."""

    def get(self, image: str) -> object: ...

    def pull(self, image: str) -> object: ...


class DockerArchiveAPIProtocol(Protocol):
    """Subset of low-level Docker API used for image loading."""

    def load_image(self, data: BinaryIO, quiet: bool = True) -> Iterable[object] | None: ...


class DockerContainerHandleProtocol(Protocol):
    """Subset of container methods used by the wrapper."""

    id: str

    def wait(self, timeout: int | None = None) -> dict[str, object]: ...

    def logs(self, *, stdout: bool, stderr: bool) -> bytes: ...

    def kill(self) -> object: ...

    def remove(self, force: bool = False) -> object: ...


class DockerContainersProtocol(Protocol):
    """Subset of container management methods used by the wrapper."""

    def run(
        self,
        *,
        image: str,
        command: list[str] | None = None,
        volumes: dict[str, dict[str, str]] | None = None,
        working_dir: str | None = None,
        environment: dict[str, str] | None = None,
        detach: bool = True,
        **kwargs: Any,
    ) -> DockerContainerHandleProtocol: ...

    def list(
        self,
        *,
        all: bool = False,
        filters: dict[str, Any] | None = None,
    ) -> list[DockerContainerHandleProtocol]: ...


class DockerSDKProtocol(Protocol):
    """Subset of Docker SDK client surface used by the wrapper."""

    images: DockerImagesProtocol
    api: DockerArchiveAPIProtocol
    containers: DockerContainersProtocol

    def version(self) -> dict[str, object]: ...

    def close(self) -> object: ...


def _create_docker_client() -> DockerSDKProtocol:
    """Create a Docker SDK client through the dynamically imported module."""
    from_env = cast(Callable[[], DockerSDKProtocol], docker.from_env)  # type: ignore[attr-defined]
    return from_env()


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
        self._client: DockerSDKProtocol | None = None

    @property
    def client(self) -> DockerSDKProtocol:
        """Get Docker client, creating it lazily.

        Returns:
            Docker client instance.

        Raises:
            DockerExecutionError: If connection fails.
        """
        if self._client is None:
            try:
                self._client = _create_docker_client()
                logger.debug("Docker client initialized")
            except DockerException as e:
                raise DockerExecutionError(
                    f"Failed to connect to Docker: {e}",
                    original_error=e
                ) from e
        return self._client

    async def ensure_image(self, image: str) -> bool:
        """Ensure Docker image exists, loading/pulling if necessary.

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
                if self._try_load_local_archive(image):
                    return True

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

    def _get_local_archive_candidates(self, image: str) -> list[Path]:
        """Get candidate tar archives for local image auto-loading."""
        if image != _LATEX_IMAGE:
            return []

        candidates: list[Path] = []

        env_specific = os.getenv("WENJIN_TEXLIVE_IMAGE_TAR")
        if env_specific:
            candidates.append(Path(env_specific))

        env_generic = os.getenv("DOCKER_IMAGE_TAR_PATH")
        if env_generic:
            candidates.append(Path(env_generic))

        backend_root = Path(__file__).resolve().parents[3]
        candidates.append(
            backend_root / "docker" / "images" / "texlive" / _LATEX_IMAGE_ARCHIVE
        )
        candidates.append(
            Path("/opt/wenjin/images/texlive") / _LATEX_IMAGE_ARCHIVE
        )

        deduped: list[Path] = []
        seen: set[str] = set()
        for path in candidates:
            resolved = str(path.expanduser())
            if resolved in seen:
                continue
            seen.add(resolved)
            deduped.append(Path(resolved))
        return deduped

    def _try_load_local_archive(self, image: str) -> bool:
        """Try loading an image from local tar archive if available."""
        for archive_path in self._get_local_archive_candidates(image):
            if not archive_path.is_file():
                continue

            logger.info(
                "Image '%s' not found locally. Trying archive: %s",
                image,
                archive_path,
            )
            try:
                with archive_path.open("rb") as archive_fp:
                    load_stream = self.client.api.load_image(
                        archive_fp,
                        quiet=True,
                    )
                    if load_stream is not None:
                        for _ in load_stream:
                            pass

                self.client.images.get(image)
                logger.info("Loaded image from archive: %s", archive_path)
                return True
            except Exception as exc:
                logger.warning(
                    "Failed loading image '%s' from archive '%s': %s",
                    image,
                    archive_path,
                    exc,
                )

        return False

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
            container: DockerContainerHandleProtocol | None = None
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
                    exit_code_raw = result.get("StatusCode", -1)
                    exit_code = (
                        int(exit_code_raw)
                        if isinstance(exit_code_raw, (int, float))
                        else -1
                    )
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

                return exit_code, stdout, stderr

            except DockerException as e:
                raise DockerExecutionError(
                    f"Container execution failed: {e}",
                    original_error=e
                ) from e
            finally:
                if remove and container is not None:
                    try:
                        container.remove(force=True)
                        logger.debug(f"Removed container: {container.id[:12]}")
                    except Exception as exc:
                        logger.warning(f"Failed to remove container: {exc}")

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_executor, _run)

    async def cleanup_containers_by_label(self, labels: dict[str, str]) -> int:
        """Best-effort cleanup for containers matching all given labels."""
        label_filters = [f"{key}={value}" for key, value in labels.items() if key and value]

        def _cleanup() -> int:
            try:
                containers = self.client.containers.list(
                    all=True,
                    filters={"label": label_filters} if label_filters else None,
                )
            except DockerException as exc:
                raise DockerExecutionError(
                    f"Failed to list containers for cleanup: {exc}",
                    original_error=exc,
                ) from exc

            removed = 0
            for container in containers:
                try:
                    container.remove(force=True)
                    removed += 1
                except Exception as exc:  # noqa: BLE001
                    cid = getattr(container, "id", "unknown")
                    logger.warning(
                        "Failed to remove container %s during cleanup: %s",
                        str(cid)[:12],
                        exc,
                    )
            return removed

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_executor, _cleanup)

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
                version = version_info.get("Version")
                api_version = version_info.get("ApiVersion")
                return {
                    "healthy": True,
                    "version": str(version or "unknown"),
                    "api_version": str(api_version or "unknown"),
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
