"""Provider-neutral sandbox runtime ports.

The public sandbox boundary is operation-based.  It deliberately has no
acquire/release session API and exposes no container identity.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from src.sandbox.contracts import (
    CommandAuditEvidence,
    CompiledSandboxCommand,
    SandboxMissionProvenance,
    SandboxNetworkProfile,
    SandboxOperationRequest,
    SandboxOperationResult,
    SandboxPreflightReport,
)


class ProviderEffectState(StrEnum):
    NOT_STARTED = "not_started"
    CONFIRMED = "confirmed"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True, slots=True)
class SandboxMount:
    """One explicit host-to-operation-container mount."""

    source: Path
    target: str
    read_only: bool


@dataclass(frozen=True, slots=True)
class ProviderNetworkConfig:
    """Enforced provider network attachment, never model-authored config."""

    profile: SandboxNetworkProfile = SandboxNetworkProfile.NONE
    network_name: str | None = None
    proxy_url: str | None = None
    package_index_url: str | None = None
    allowed_hosts: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PreparedSandboxJob:
    """Fully validated and audited provider input."""

    request: SandboxOperationRequest
    sandbox_job_id: str
    command: CompiledSandboxCommand
    command_audit: CommandAuditEvidence
    mounts: tuple[SandboxMount, ...]
    network: ProviderNetworkConfig
    image_reference: str


@dataclass(frozen=True, slots=True)
class ProviderExecutionResult:
    """Bounded provider receipt without Docker-specific public identity."""

    exit_code: int | None
    stdout: bytes = b""
    stderr: bytes = b""
    timed_out: bool = False
    stdout_capture_truncated: bool = False
    stderr_capture_truncated: bool = False
    effect_state: ProviderEffectState = ProviderEffectState.CONFIRMED
    started_at: datetime | None = None
    finished_at: datetime | None = None
    diagnostics: tuple[str, ...] = ()


class SandboxOperationProvider(ABC):
    """Provider SPI for one short-lived operation container."""

    @abstractmethod
    async def execute(self, job: PreparedSandboxJob) -> ProviderExecutionResult:
        """Execute exactly one prepared operation and remove its container."""

    @abstractmethod
    async def preflight(self, *, release_gate: bool) -> SandboxPreflightReport:
        """Verify daemon, image and security controls for the requested gate."""


class CommandAuditPort(Protocol):
    """Mandatory policy port implemented by the harness command auditor."""

    def audit(
        self,
        command: CompiledSandboxCommand,
        request: SandboxOperationRequest,
    ) -> CommandAuditEvidence: ...


class MissionLeaseGuard(Protocol):
    """MissionRuntime fencing port; stale drivers cannot start effects."""

    async def assert_current(self, provenance: SandboxMissionProvenance) -> None: ...


class SandboxReceiptState(StrEnum):
    CLAIMED = "claimed"
    TERMINAL = "terminal"


@dataclass(frozen=True, slots=True)
class SandboxReceiptClaim:
    """Atomic operation-key claim outcome."""

    state: SandboxReceiptState
    acquired: bool
    existing_result: SandboxOperationResult | None = None
    claimed_at: datetime | None = None


class SandboxReceiptStore(Protocol):
    """Durable operation-key receipt port owned by the sandbox domain."""

    async def claim(
        self,
        request: SandboxOperationRequest,
        *,
        sandbox_job_id: str,
    ) -> SandboxReceiptClaim: ...

    async def finalize(self, result: SandboxOperationResult) -> None: ...

    async def get(
        self,
        mission_id: str,
        operation_key: str,
    ) -> SandboxOperationResult | None: ...

    async def inspect(
        self,
        mission_id: str,
        operation_key: str,
    ) -> SandboxReceiptClaim | None: ...
