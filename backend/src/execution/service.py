"""Docker-based execution service."""

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .base import ExecutionService
from .types import (
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    ExecutionType,
    ProviderResult,
)
from .docker.client import DockerClient, DockerExecutionError
from .providers.latex import LaTeXProvider

logger = logging.getLogger(__name__)


class DockerExecutionService(ExecutionService):
    """Execution service using Docker containers.

    This service orchestrates execution by delegating to specialized providers
    for each execution type (LaTeX, Python plotting, diagrams, AI images).
    """

    # Provider registry
    PROVIDER_MAP: dict[ExecutionType, type] = {
        ExecutionType.LATEX_COMPILE: LaTeXProvider,
        # More providers added in later phases:
        # ExecutionType.PYTHON_PLOT: PythonVizProvider,
        # ExecutionType.MERMAID_DIAGRAM: DiagramProvider,
        # ExecutionType.AI_IMAGE: AIImageProvider,
    }

    def __init__(
        self,
        sandbox_base_dir: str,
    ):
        """Initialize execution service.

        Args:
            sandbox_base_dir: Base directory for sandbox files.
        """
        self.sandbox_base_dir = Path(sandbox_base_dir)
        self.docker_client = DockerClient()
        self._providers: dict[ExecutionType, Any] = {}

    def _get_provider(self, exec_type: ExecutionType):
        """Get or create provider instance.

        Args:
            exec_type: Execution type.

        Returns:
            Provider instance.

        Raises:
            ValueError: If execution type is not supported.
        """
        if exec_type not in self._providers:
            provider_cls = self.PROVIDER_MAP.get(exec_type)
            if not provider_cls:
                raise ValueError(f"Unsupported execution type: {exec_type}")
            self._providers[exec_type] = provider_cls()
        return self._providers[exec_type]

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute a task.

        Args:
            request: Execution request.

        Returns:
            Execution result.
        """
        start_time = time.time()
        exec_type = request.execution_type.value

        logger.info(f"Starting execution: {exec_type} for thread {request.thread_id}")

        try:
            provider = self._get_provider(request.execution_type)

            # Prepare work directory
            work_dir = self._prepare_work_dir(request)
            logger.debug(f"Work directory: {work_dir}")

            # Execute based on provider type
            if provider.docker_image:
                # Docker-based execution
                result = await self._execute_in_docker(
                    provider, request, str(work_dir)
                )
            else:
                # Non-Docker execution (e.g., API calls)
                result = await provider.execute(
                    content=request.content,
                    work_dir=str(work_dir),
                    options=request.options,
                )

            # Calculate execution time
            execution_time_ms = int((time.time() - start_time) * 1000)

            # Build result
            if result.success and result.output_files:
                # Convert to sandbox virtual path
                sandbox_path = self._to_sandbox_path(
                    work_dir / result.output_files[0],
                    request.thread_id,
                )

                logger.info(
                    f"Execution succeeded: {exec_type} "
                    f"-> {sandbox_path} ({execution_time_ms}ms)"
                )

                return ExecutionResult(
                    status=ExecutionStatus.SUCCESS,
                    sandbox_path=sandbox_path,
                    execution_time_ms=execution_time_ms,
                    metadata=result.metadata,
                    logs=result.logs,
                )
            else:
                logger.warning(
                    f"Execution failed: {exec_type} - {result.error_message}"
                )
                return ExecutionResult(
                    status=ExecutionStatus.FAILED,
                    error_message=result.error_message or "Execution failed",
                    execution_time_ms=execution_time_ms,
                    logs=result.logs,
                )

        except DockerExecutionError as e:
            execution_time_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Docker execution error: {e}")
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                error_message=str(e),
                execution_time_ms=execution_time_ms,
            )

        except ValueError as e:
            execution_time_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Validation error: {e}")
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                error_message=str(e),
                execution_time_ms=execution_time_ms,
            )

        except Exception as e:
            execution_time_ms = int((time.time() - start_time) * 1000)
            logger.exception(f"Unexpected error during execution: {e}")
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                error_message=f"Internal error: {e}",
                execution_time_ms=execution_time_ms,
            )

    async def _execute_in_docker(
        self,
        provider: Any,
        request: ExecutionRequest,
        work_dir: str,
    ) -> ProviderResult:
        """Execute task in Docker container.

        Args:
            provider: Execution provider.
            request: Execution request.
            work_dir: Working directory path.

        Returns:
            Provider result.
        """
        # Ensure Docker image is available
        await self.docker_client.ensure_image(provider.docker_image)

        # Build volume mapping
        volumes = self.docker_client.build_volume_mapping(
            host_dir=work_dir,
            container_dir="/workspace",
        )

        # Build command
        command = provider.build_command(request.content, request.options)

        # Run container
        exit_code, stdout, stderr = await self.docker_client.run_container(
            image=provider.docker_image,
            command=command,
            volumes=volumes,
            timeout=request.timeout,
        )

        # Process result
        return await provider.process_result(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            work_dir=work_dir,
            options=request.options,
        )

    def _prepare_work_dir(self, request: ExecutionRequest) -> Path:
        """Prepare working directory for execution.

        Args:
            request: Execution request.

        Returns:
            Working directory path.
        """
        thread_id = request.thread_id or "default"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        work_dir = (
            self.sandbox_base_dir
            / thread_id
            / "execution"
            / request.execution_type.value
            / timestamp
        )
        work_dir.mkdir(parents=True, exist_ok=True)

        return work_dir

    def _to_sandbox_path(self, physical_path: Path, thread_id: str | None) -> str:
        """Convert physical path to sandbox virtual path.

        Args:
            physical_path: Physical file path.
            thread_id: Thread ID.

        Returns:
            Sandbox virtual path (e.g., /mnt/user-data/...).
        """
        thread_id = thread_id or "default"
        relative = physical_path.relative_to(self.sandbox_base_dir / thread_id)
        return f"/mnt/user-data/{relative}"

    async def health_check(self) -> dict:
        """Check service health.

        Returns:
            Health status dictionary.
        """
        docker_health = await self.docker_client.health_check()

        return {
            "status": docker_health.get("status", "unknown"),
            "docker": docker_health,
            "providers": list(self.PROVIDER_MAP.keys()),
        }
