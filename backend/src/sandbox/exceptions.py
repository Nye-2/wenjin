"""Sandbox-specific exceptions."""


class SandboxError(Exception):
    """Base exception for sandbox operations."""

    pass


class SandboxNotFoundError(SandboxError):
    """Raised when a sandbox cannot be found."""

    def __init__(self, message: str, sandbox_id: str | None = None):
        self.sandbox_id = sandbox_id
        if sandbox_id:
            message = f"{message} (sandbox_id={sandbox_id})"
        super().__init__(message)


class SandboxRuntimeError(SandboxError):
    """Raised when sandbox execution fails."""

    def __init__(
        self,
        message: str,
        command: str | None = None,
        exit_code: int | None = None,
    ):
        self.command = command
        self.exit_code = exit_code
        details = message
        if command:
            details = f"{message} (command: {command})"
        if exit_code is not None:
            details = f"{details}, exit_code: {exit_code}"
        super().__init__(details)


class SandboxTimeoutError(SandboxRuntimeError):
    """Raised when sandbox operation times out."""

    def __init__(
        self,
        message: str,
        timeout: int | None = None,
        command: str | None = None,
    ):
        self.timeout = timeout
        if timeout:
            message = f"{message} (timeout: {timeout}s)"
        super().__init__(message, command=command)
