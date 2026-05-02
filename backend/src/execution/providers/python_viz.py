"""Python visualization provider (skeleton)."""

import logging
from pathlib import Path
from typing import Any

from ..base import ExecutionProvider
from ..types import ProviderResult

logger = logging.getLogger(__name__)


class PythonVizProvider(ExecutionProvider):
    """Python data visualization provider using matplotlib."""

    _execution_type = "python_plot"
    _docker_image = "wenjin/python-viz:1.0"

    @property
    def execution_type(self) -> str:
        """Execution type this provider handles."""
        return self._execution_type

    @property
    def docker_image(self) -> str | None:
        """Docker image name."""
        return self._docker_image

    def build_command(self, content: str, options: dict[str, Any]) -> list[str]:
        """Build execution command.

        Args:
            content: Python source code for visualization.
            options: Execution options:
                - format: Output format (default: "png")

        Returns:
            Command list for Docker execution.
        """
        # Wrap code with matplotlib setup and save
        wrapped_code = f'''
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'SimHei', 'WenQuanYi Micro Hei']
plt.rcParams['axes.unicode_minus'] = False

# User code
{content}

# Save figure
import os
os.makedirs('/workspace/output', exist_ok=True)
'''

        return ["python", "-c", wrapped_code]

    async def execute(
        self,
        content: str,
        work_dir: str,
        options: dict[str, Any],
        docker_client: Any = None,
    ) -> ProviderResult:
        """Execute Python visualization (handled by Docker).

        Args:
            content: Python source code.
            work_dir: Working directory path.
            options: Execution options.
            docker_client: Docker client (not used in this method).

        Returns:
            ProviderResult - raises NotImplementedError.

        Raises:
            NotImplementedError: Use DockerExecutionService.execute instead.
        """
        raise NotImplementedError("Use DockerExecutionService.execute instead")

    async def process_result(
        self,
        exit_code: int,
        stdout: str,
        stderr: str,
        work_dir: str,
        options: dict[str, Any],
    ) -> ProviderResult:
        """Process execution result.

        Args:
            exit_code: Container exit code.
            stdout: Container stdout.
            stderr: Container stderr.
            work_dir: Working directory path.
            options: Execution options.

        Returns:
            ProviderResult with output files and metadata.
        """
        work_path = Path(work_dir)
        output_dir = work_path / "output"

        if exit_code == 0 and output_dir.exists():
            images = list(output_dir.glob("*.png")) + list(output_dir.glob("*.svg"))
            if images:
                return ProviderResult(
                    success=True,
                    output_files=[f"output/{img.name}" for img in images],
                    metadata={"format": options.get("format", "png")},
                    logs=stdout,
                )

        return ProviderResult(
            success=False,
            error_message=stderr or "Python execution failed",
            logs=stdout + "\n" + stderr,
        )
