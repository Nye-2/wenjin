"""Data types for execution service."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ExecutionType(Enum):
    """Execution type."""
    LATEX_COMPILE = "latex_compile"
    PYTHON_PLOT = "python_plot"
    MERMAID_DIAGRAM = "mermaid_diagram"
    AI_IMAGE = "ai_image"


class ExecutionStatus(Enum):
    """Execution status."""
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    SECURITY_VIOLATION = "security_violation"


class CompilerType(Enum):
    """LaTeX compiler type."""
    PDFLATEX = "pdflatex"
    XELATEX = "xelatex"


class ImageProvider(Enum):
    """AI image generation provider."""
    KLING = "kling"
    DALLE = "dalle"


@dataclass
class ExecutionRequest:
    """Execution request."""
    execution_type: ExecutionType
    content: str  # Source code or prompt
    options: dict[str, Any] = field(default_factory=dict)
    timeout: int = 120
    workspace_id: str | None = None
    thread_id: str | None = None
    output_filename: str | None = None


@dataclass
class ProviderResult:
    """Provider execution result (internal)."""
    success: bool
    output_files: list[str] = field(default_factory=list)  # Relative to work_dir
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    logs: str | None = None


@dataclass
class ExecutionResult:
    """Execution result (returned to Tool)."""
    status: ExecutionStatus
    sandbox_path: str | None = None  # Virtual path like /mnt/user-data/...
    artifact_id: str | None = None
    error_message: str | None = None
    execution_time_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    logs: str | None = None
    source_code: str | None = None

    def to_tool_output(self) -> str:
        """Convert to tool return string."""
        if self.status == ExecutionStatus.SUCCESS:
            msg = f"Success. Output saved to: {self.sandbox_path}"
            if self.metadata.get("page_count"):
                msg += f" ({self.metadata['page_count']} pages)"
            return msg
        elif self.status == ExecutionStatus.TIMEOUT:
            return f"Execution timed out: {self.error_message}"
        elif self.status == ExecutionStatus.SECURITY_VIOLATION:
            return f"Security violation: {self.error_message}"
        else:  # FAILED
            return f"Failed: {self.error_message}"
