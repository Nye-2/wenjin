"""Sandbox vNext exceptions safe for runtime normalization."""


class SandboxError(Exception):
    """Base exception for provider-neutral sandbox operations."""


class SandboxPolicyError(SandboxError):
    """The typed operation was denied before provider execution."""


class SandboxPermissionRequired(SandboxPolicyError):
    """MissionRuntime must resume the operation with a current permission."""


class SandboxProviderError(SandboxError):
    """The operation provider failed before or during execution."""

    def __init__(self, message: str, *, effect_uncertain: bool = False) -> None:
        super().__init__(message)
        self.effect_uncertain = effect_uncertain


class SandboxReceiptConflictError(SandboxError):
    """A receipt transition conflicts with the claimed operation key."""


class SandboxOutputRefError(SandboxError):
    """An opaque output reference is missing, expired, or invalid."""


class SandboxEnvironmentError(SandboxError):
    """A content-addressed environment is missing or not sealed."""


class SandboxMaterializationError(SandboxError):
    """Staged output materialization may have partially changed public files."""
