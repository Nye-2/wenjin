"""Mermaid diagram execution provider."""

import logging
from pathlib import Path

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

    def build_command(self, content: str, options: dict) -> list[str]:
        """Build mmdc command for Mermaid rendering.

        The content (Mermaid source) is written to /workspace/input.mmd
        by the DockerExecutionService work dir preparation.  We instruct
        mmdc to read from stdin via a shell wrapper so we don't need to
        pre-write the file in the host.
        """
        output_format = options.get("format", "svg")
        output_path = f"/workspace/output/diagram.{output_format}"

        # Use shell to write content to file then run mmdc
        escaped_content = content.replace("'", "'\\''")
        return [
            "sh",
            "-c",
            (
                f"mkdir -p /workspace/output && "
                f"echo '{escaped_content}' > /workspace/input.mmd && "
                f"mmdc -i /workspace/input.mmd -o {output_path} -b transparent"
            ),
        ]

    async def execute(
        self,
        content: str,
        work_dir: str,
        options: dict,
        docker_client=None,
    ) -> ProviderResult:
        """Execute Mermaid rendering (handled by Docker)."""
        raise NotImplementedError("Use DockerExecutionService.execute instead")

    async def process_result(
        self,
        exit_code: int,
        stdout: str,
        stderr: str,
        work_dir: str,
        options: dict,
    ) -> ProviderResult:
        """Process Docker execution result for Mermaid."""
        work_path = Path(work_dir)
        output_dir = work_path / "output"

        if exit_code == 0 and output_dir.exists():
            outputs = (
                list(output_dir.glob("*.svg"))
                + list(output_dir.glob("*.png"))
                + list(output_dir.glob("*.pdf"))
            )
            if outputs:
                return ProviderResult(
                    success=True,
                    output_files=[f"output/{f.name}" for f in outputs],
                    metadata={"format": options.get("format", "svg")},
                    logs=stdout,
                )

        return ProviderResult(
            success=False,
            error_message=stderr or "Mermaid rendering failed: no output produced",
            logs=(stdout + "\n" + stderr).strip(),
        )
