"""Data types for execution service."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional


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
    workspace_id: Optional[str] = None
    thread_id: Optional[str] = None
    output_filename: Optional[str] = None


@dataclass
class ProviderResult:
    """Provider execution result (internal)."""
    success: bool
    output_files: list[str] = field(default_factory=list)  # Relative to work_dir
    error_message: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    logs: Optional[str] = None


@dataclass
class ExecutionResult:
    """Execution result (returned to Tool)."""
    status: ExecutionStatus
    sandbox_path: Optional[str] = None  # Virtual path like /mnt/user-data/...
    artifact_id: Optional[str] = None
    error_message: Optional[str] = None
    execution_time_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    logs: Optional[str] = None
    source_code: Optional[str] = None

    def to_tool_output(self) -> str:
        """Convert to tool return string."""
        if self.status == ExecutionStatus.SUCCESS:
            msg = f"Success. Output saved to: {self.sandbox_path}"
            if self.metadata.get("page_count"):
                msg += f" ({self.metadata['page_count']} pages)"
            return msg
        return f"Failed: {self.error_message}"
