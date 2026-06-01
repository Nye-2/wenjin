"""Lead-agent sandbox runtime errors."""

from __future__ import annotations

from typing import Any


class SandboxCommandExecutionError(RuntimeError):
    """Raised when user code ran in sandbox but exited unsuccessfully."""

    def __init__(self, message: str, *, output: dict[str, Any]) -> None:
        super().__init__(message)
        self.output = output
