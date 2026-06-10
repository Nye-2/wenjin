"""Mermaid diagram execution provider."""

import logging
from pathlib import Path
from typing import Any

from src.sandbox.workspace_layout import workspace_virtual_path

from ..base import ExecutionProvider
from ..types import ProviderResult

logger = logging.getLogger(__name__)


class MermaidProvider(ExecutionProvider):
    """Mermaid diagram provider using mermaid-cli Docker image."""

    _execution_type = "mermaid_diagram"
    _docker_image = "minlag/mermaid-cli:latest"

    @property
    def execution_type(self) -> str:
        return self._execution_type

    @property
    def docker_image(self) -> str | None:
        return self._docker_image

    def build_command(self, content: str, options: dict[str, Any]) -> list[str]:
        """Build mmdc command for Mermaid rendering.

        The content (Mermaid source) is written to /workspace/input.mmd
        by the DockerExecutionService work dir preparation.  We instruct
        mmdc to read from stdin via a shell wrapper so we don't need to
        pre-write the file in the host.
        """
        output_format = options.get("format", "svg")
        outputs_path = workspace_virtual_path("outputs")
        output_path = f"{outputs_path}/diagram.{output_format}"

        # Use shell to write content to file then run mmdc
        escaped_content = content.replace("'", "'\\''")
        return [
            "sh",
            "-c",
            (
                f"mkdir -p {outputs_path} && "
                f"echo '{escaped_content}' > /workspace/input.mmd && "
                f"mmdc -i /workspace/input.mmd -o {output_path} -b transparent"
            ),
        ]

    async def execute(
        self,
        content: str,
        work_dir: str,
        options: dict[str, Any],
        docker_client: Any = None,
    ) -> ProviderResult:
        """Execute Mermaid rendering (handled by Docker)."""
        raise NotImplementedError("Use DockerExecutionService.execute instead")

    async def process_result(
        self,
        exit_code: int,
        stdout: str,
        stderr: str,
        work_dir: str,
        options: dict[str, Any],
    ) -> ProviderResult:
        """Process Docker execution result for Mermaid."""
        work_path = Path(work_dir)
        output_dir = work_path / "outputs"

        if exit_code == 0 and output_dir.exists():
            outputs = (
                list(output_dir.glob("*.svg"))
                + list(output_dir.glob("*.png"))
                + list(output_dir.glob("*.pdf"))
            )
            if outputs:
                return ProviderResult(
                    success=True,
                    output_files=[f"outputs/{f.name}" for f in outputs],
                    metadata={"format": options.get("format", "svg")},
                    logs=stdout,
                )

        return ProviderResult(
            success=False,
            error_message=stderr or "Mermaid rendering failed: no output produced",
            logs=(stdout + "\n" + stderr).strip(),
        )
