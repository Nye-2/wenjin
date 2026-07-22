"""Provider-neutral contracts for bounded sandbox operations."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SANDBOX_OPERATION_SCHEMA_VERSION = "wenjin.sandbox.operation.v2"
SANDBOX_COMMAND_SCHEMA_VERSION = "wenjin.sandbox.command.v2"
SANDBOX_POLICY_VERSION = "wenjin.sandbox.policy.v2"

_CONTENT_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_IMAGE_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_OPERATION_KEY_RE = re.compile(r"^sbxop_[0-9a-f]{64}$")
_OUTPUT_REF_RE = re.compile(r"^sbxout_[A-Za-z0-9_-]{20,}$")
_ARTIFACT_OBJECT_RE = re.compile(r"^sbxobj_[0-9a-f]{64}$")
_PACKAGE_SPEC_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_.-]*"
    r"(?:\[[A-Za-z0-9_,.-]+\])?"
    r"(?:\s*(?:==|!=|~=|>=|<=|>|<)\s*[A-Za-z0-9_.!*+-]+)?$"
)
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$")


class FrozenContract(BaseModel):
    """Strict immutable base for cross-runtime sandbox contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class SandboxOperationKind(StrEnum):
    RUN_PYTHON = "run_python"
    RUN_NOTEBOOK = "run_notebook"
    SMOKE_CHECK = "smoke_check"
    INSTALL_DEPENDENCIES = "install_dependencies"
    REGISTER_DATASET = "register_dataset"
    REGISTER_ARTIFACT = "register_artifact"
    READ_OUTPUT_REF = "read_output_ref"


class SandboxNetworkProfile(StrEnum):
    NONE = "none"
    PACKAGE_INDEX_ONLY = "package_index_only"
    EXPLICIT_EGRESS_ADMIN_ONLY = "explicit_egress_admin_only"


class SandboxOperationStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    POLICY_DENIED = "policy_denied"
    PERMISSION_REQUIRED = "permission_required"
    RECONCILIATION_REQUIRED = "reconciliation_required"


class SandboxRetryDisposition(StrEnum):
    REUSE_RECEIPT = "reuse_receipt"
    SAFE_TO_RETRY = "safe_to_retry"
    REQUIRES_RECONCILIATION = "requires_reconciliation"
    DO_NOT_RETRY = "do_not_retry"


class SandboxMissionProvenance(FrozenContract):
    """Mission linkage required for every sandbox effect."""

    workspace_id: str = Field(pattern=_IDENTIFIER_RE.pattern)
    mission_id: str = Field(pattern=_IDENTIFIER_RE.pattern)
    mission_item_seq: int | None = Field(default=None, ge=1)
    subagent_id: str | None = Field(default=None, pattern=_IDENTIFIER_RE.pattern)
    lease_epoch: int = Field(ge=1)


class SandboxResourceLimits(FrozenContract):
    """Hard operation limits enforced by the provider boundary."""

    cpu_cores: float = Field(default=1.0, gt=0, le=8)
    memory_bytes: int = Field(default=1_073_741_824, ge=134_217_728, le=17_179_869_184)
    memory_swap_bytes: int = Field(default=1_073_741_824, ge=134_217_728, le=17_179_869_184)
    pids: int = Field(default=128, ge=16, le=1024)
    # Mission sandbox tools have a 150 second orchestrator boundary.  Keep the
    # process deadline below it so Docker shutdown and durable receipt closure
    # always have a bounded margin.
    wall_time_seconds: int = Field(default=120, ge=1, le=3600)
    tmpfs_bytes: int = Field(default=268_435_456, ge=16_777_216, le=2_147_483_648)
    workspace_bytes: int = Field(default=2_147_483_648, ge=67_108_864, le=53_687_091_200)
    stream_capture_bytes: int = Field(default=4_194_304, ge=65_536, le=33_554_432)
    stream_preview_chars: int = Field(default=6_000, ge=500, le=50_000)

    @model_validator(mode="after")
    def validate_memory_swap(self) -> SandboxResourceLimits:
        if self.memory_swap_bytes < self.memory_bytes:
            raise ValueError("memory_swap_bytes must be greater than or equal to memory_bytes")
        return self


class SandboxNetworkGrant(FrozenContract):
    """Durable MissionRuntime permission reference for non-default network."""

    permission_request_id: str = Field(pattern=_IDENTIFIER_RE.pattern)
    approved_scope: Literal["mission", "operation", "admin"]
    allowed_hosts: tuple[str, ...] = Field(default=(), max_length=100)
    expires_at: datetime

    @model_validator(mode="after")
    def validate_expiry(self) -> SandboxNetworkGrant:
        if self.expires_at.tzinfo is None:
            raise ValueError("expires_at must be timezone-aware")
        return self


class RunPythonInput(FrozenContract):
    kind: Literal[SandboxOperationKind.RUN_PYTHON] = SandboxOperationKind.RUN_PYTHON
    script: str = Field(min_length=1, max_length=2_000_000)
    script_path: str = Field(default="/workspace/scripts/analysis.py", min_length=1, max_length=500)
    base_content_hash: str | None = Field(default=None, pattern=_CONTENT_HASH_RE.pattern)
    environment_id: str | None = Field(default=None, min_length=1, max_length=100)
    dataset_paths: tuple[str, ...] = Field(default=(), max_length=100)
    artifact_input_paths: tuple[str, ...] = Field(default=(), max_length=100)
    output_base_hashes: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_output_hashes(self) -> RunPythonInput:
        if any(not _CONTENT_HASH_RE.fullmatch(value) for value in self.output_base_hashes.values()):
            raise ValueError("output_base_hashes must contain sha256 digests")
        if len(set(self.artifact_input_paths)) != len(self.artifact_input_paths):
            raise ValueError("artifact_input_paths must not contain duplicates")
        return self


class RunNotebookInput(FrozenContract):
    kind: Literal[SandboxOperationKind.RUN_NOTEBOOK] = SandboxOperationKind.RUN_NOTEBOOK
    notebook_path: str = Field(min_length=1, max_length=500)
    output_path: str = Field(min_length=1, max_length=500)
    base_content_hash: str | None = Field(default=None, pattern=_CONTENT_HASH_RE.pattern)
    environment_id: str = Field(min_length=1, max_length=100)
    dataset_paths: tuple[str, ...] = Field(default=(), max_length=100)


class SmokeCheckInput(FrozenContract):
    kind: Literal[SandboxOperationKind.SMOKE_CHECK] = SandboxOperationKind.SMOKE_CHECK


class InstallDependenciesInput(FrozenContract):
    kind: Literal[SandboxOperationKind.INSTALL_DEPENDENCIES] = SandboxOperationKind.INSTALL_DEPENDENCIES
    packages: tuple[str, ...] = Field(min_length=1, max_length=100)
    runtime: str = Field(default="python3.13", pattern=r"^python3\.(?:1[2-9]|[2-9][0-9])$")

    @model_validator(mode="after")
    def validate_packages(self) -> InstallDependenciesInput:
        for package in self.packages:
            normalized = " ".join(package.split())
            if package != normalized or not _PACKAGE_SPEC_RE.fullmatch(normalized) or "://" in normalized or "@" in normalized or ";" in normalized or any(token in normalized for token in ("|", "&", "`", "$", "\\")):
                raise ValueError(f"unsafe package spec: {package}")
        return self


class RegisterDatasetInput(FrozenContract):
    kind: Literal[SandboxOperationKind.REGISTER_DATASET] = SandboxOperationKind.REGISTER_DATASET
    path: str = Field(min_length=1, max_length=500)
    source: str = Field(min_length=1, max_length=1000)
    license: str | None = Field(default=None, max_length=200)
    pii_risk: Literal["none", "possible", "confirmed", "unknown"] = "unknown"
    uploaded_by: str = Field(min_length=1, max_length=100)
    observed_at: datetime


class RegisterArtifactInput(FrozenContract):
    kind: Literal[SandboxOperationKind.REGISTER_ARTIFACT] = SandboxOperationKind.REGISTER_ARTIFACT
    path: str = Field(min_length=1, max_length=500)
    producing_operation_key: str = Field(pattern=_OPERATION_KEY_RE.pattern)


class ReadOutputRefInput(FrozenContract):
    kind: Literal[SandboxOperationKind.READ_OUTPUT_REF] = SandboxOperationKind.READ_OUTPUT_REF
    output_ref: str = Field(pattern=_OUTPUT_REF_RE.pattern)
    offset: int = Field(default=0, ge=0)
    max_bytes: int = Field(default=32_768, ge=1, le=131_072)


SandboxOperationInput = Annotated[
    RunPythonInput | RunNotebookInput | SmokeCheckInput | InstallDependenciesInput | RegisterDatasetInput | RegisterArtifactInput | ReadOutputRefInput,
    Field(discriminator="kind"),
]


class SandboxOperationRequest(FrozenContract):
    """One idempotent, bounded sandbox operation requested by MissionRuntime."""

    schema_version: Literal["wenjin.sandbox.operation.v2"] = "wenjin.sandbox.operation.v2"
    operation_key: str = Field(pattern=_OPERATION_KEY_RE.pattern)
    provenance: SandboxMissionProvenance
    operation_input: SandboxOperationInput
    image_digest: str = Field(pattern=_IMAGE_DIGEST_RE.pattern)
    policy_version: str = Field(default=SANDBOX_POLICY_VERSION, min_length=1, max_length=100)
    command_schema_version: str = Field(default=SANDBOX_COMMAND_SCHEMA_VERSION, min_length=1, max_length=100)
    network_profile: SandboxNetworkProfile = SandboxNetworkProfile.NONE
    network_grant: SandboxNetworkGrant | None = None
    limits: SandboxResourceLimits = Field(default_factory=SandboxResourceLimits)
    input_hashes: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_operation(self) -> SandboxOperationRequest:
        if self.operation_input.kind == SandboxOperationKind.INSTALL_DEPENDENCIES:
            if self.network_profile != SandboxNetworkProfile.PACKAGE_INDEX_ONLY:
                raise ValueError("install_dependencies requires package_index_only network")
        elif self.network_profile == SandboxNetworkProfile.PACKAGE_INDEX_ONLY:
            raise ValueError("package_index_only is reserved for install_dependencies")
        if self.network_profile == SandboxNetworkProfile.NONE and self.network_grant is not None:
            raise ValueError("network_grant is invalid when network_profile is none")
        if self.network_profile != SandboxNetworkProfile.NONE and self.network_grant is None:
            raise ValueError("non-default network requires a MissionRuntime permission reference")
        if self.network_profile == SandboxNetworkProfile.EXPLICIT_EGRESS_ADMIN_ONLY and self.network_grant is not None and self.network_grant.approved_scope != "admin":
            raise ValueError("explicit egress requires admin approval")
        if self.operation_key != sandbox_operation_key(self):
            raise ValueError("operation_key does not match the canonical request payload")
        for name, value in self.input_hashes.items():
            if not name or not _CONTENT_HASH_RE.fullmatch(value):
                raise ValueError("input_hashes must contain named sha256 digests")
        return self

    @classmethod
    def build(
        cls,
        *,
        provenance: SandboxMissionProvenance,
        operation_input: SandboxOperationInput,
        image_digest: str,
        policy_version: str = SANDBOX_POLICY_VERSION,
        command_schema_version: str = SANDBOX_COMMAND_SCHEMA_VERSION,
        network_profile: SandboxNetworkProfile = SandboxNetworkProfile.NONE,
        network_grant: SandboxNetworkGrant | None = None,
        limits: SandboxResourceLimits | None = None,
        input_hashes: dict[str, str] | None = None,
    ) -> SandboxOperationRequest:
        effective_limits = limits or SandboxResourceLimits()
        effective_hashes = input_hashes or {}
        provisional = cls.model_construct(
            schema_version="wenjin.sandbox.operation.v2",
            operation_key="",
            provenance=provenance,
            operation_input=operation_input,
            image_digest=image_digest,
            policy_version=policy_version,
            command_schema_version=command_schema_version,
            network_profile=network_profile,
            network_grant=network_grant,
            limits=effective_limits,
            input_hashes=effective_hashes,
        )
        return cls(
            operation_key=sandbox_operation_key(provisional),
            provenance=provenance,
            operation_input=operation_input,
            image_digest=image_digest,
            policy_version=policy_version,
            command_schema_version=command_schema_version,
            network_profile=network_profile,
            network_grant=network_grant,
            limits=effective_limits,
            input_hashes=effective_hashes,
        )

    @property
    def operation(self) -> SandboxOperationKind:
        return self.operation_input.kind


class CompiledSandboxCommand(FrozenContract):
    """Internal argv-only command emitted by the typed operation compiler."""

    schema_version: Literal["wenjin.sandbox.command.v2"] = "wenjin.sandbox.command.v2"
    operation: SandboxOperationKind
    argv: tuple[str, ...] = Field(min_length=1, max_length=256)
    cwd: str = Field(min_length=1, max_length=500)
    env: dict[str, str] = Field(default_factory=dict)
    compiler_fingerprint: str = Field(pattern=_CONTENT_HASH_RE.pattern)


class CommandAuditEvidence(FrozenContract):
    """Auditable policy decision produced before provider execution."""

    schema_version: Literal["wenjin.sandbox.command_audit.v2"] = "wenjin.sandbox.command_audit.v2"
    decision: Literal["allow", "deny"]
    risk_level: Literal["low", "medium", "high"]
    reasons: tuple[str, ...] = ()
    operation: SandboxOperationKind
    command_schema_version: str = Field(min_length=1, max_length=100)
    compiler_fingerprint: str = Field(pattern=_CONTENT_HASH_RE.pattern)
    command_fingerprint: str = Field(pattern=_CONTENT_HASH_RE.pattern)
    argv_preview: tuple[str, ...] = Field(default=(), max_length=32)
    cwd: str
    env_keys: tuple[str, ...] = Field(default=(), max_length=100)
    network_profile: SandboxNetworkProfile


class SandboxOutputRef(FrozenContract):
    """Opaque TTL reference for a redacted full stdout/stderr payload."""

    output_ref: str = Field(pattern=_OUTPUT_REF_RE.pattern)
    stream: Literal["stdout", "stderr"]
    content_hash: str = Field(pattern=_CONTENT_HASH_RE.pattern)
    size_bytes: int = Field(ge=0)
    expires_at: datetime


class SandboxOutputSlice(FrozenContract):
    """Bounded page returned only by sandbox.read_output_ref."""

    output_ref: str = Field(pattern=_OUTPUT_REF_RE.pattern)
    offset: int = Field(ge=0)
    returned_bytes: int = Field(ge=0)
    next_offset: int | None = Field(default=None, ge=0)


class SandboxArtifactManifest(FrozenContract):
    """Trusted artifact manifest computed after provider execution."""

    path: str = Field(min_length=1, max_length=500)
    object_ref: str = Field(pattern=_ARTIFACT_OBJECT_RE.pattern)
    kind: str = Field(min_length=1, max_length=100)
    content_hash: str = Field(pattern=_CONTENT_HASH_RE.pattern)
    source_script: str | None = Field(default=None, max_length=500)
    dataset_paths: tuple[str, ...] = Field(default=(), max_length=100)
    sandbox_environment_id: str = Field(min_length=1, max_length=100)
    sandbox_job_id: str = Field(min_length=1, max_length=100)
    mission_id: str = Field(min_length=1, max_length=100)
    mission_item_seq: int | None = Field(default=None, ge=1)
    network_profile: SandboxNetworkProfile
    stdout_truncated: bool
    stderr_truncated: bool
    size_bytes: int = Field(ge=0)
    created_at: datetime


class SandboxDatasetManifest(FrozenContract):
    """Trusted dataset provenance computed from a public workspace file."""

    dataset_id: str = Field(min_length=1, max_length=100)
    path: str = Field(min_length=1, max_length=500)
    source: str = Field(min_length=1, max_length=1000)
    source_hash: str = Field(pattern=_CONTENT_HASH_RE.pattern)
    license: str | None = Field(default=None, max_length=200)
    pii_risk: Literal["none", "possible", "confirmed", "unknown"]
    uploaded_by: str = Field(min_length=1, max_length=100)
    observed_at: datetime
    used_by_artifacts: tuple[str, ...] = Field(default=(), max_length=100)


class SandboxEnvironmentManifest(FrozenContract):
    """Immutable content-addressed dependency environment."""

    environment_id: str = Field(pattern=r"^sbxenv_[0-9a-f]{64}$")
    image_digest: str = Field(pattern=_IMAGE_DIGEST_RE.pattern)
    runtime: str = Field(min_length=1, max_length=100)
    lock_hash: str = Field(pattern=_CONTENT_HASH_RE.pattern)
    requested_packages: tuple[str, ...] = Field(default=(), max_length=100)
    created_at: datetime
    sealed: Literal[True] = True


class SandboxOperationResult(FrozenContract):
    """Structured terminal or reconciliation result for one operation key."""

    schema_version: Literal["wenjin.sandbox.operation_result.v2"] = "wenjin.sandbox.operation_result.v2"
    operation_key: str = Field(pattern=_OPERATION_KEY_RE.pattern)
    sandbox_job_id: str = Field(min_length=1, max_length=100)
    provenance: SandboxMissionProvenance
    operation: SandboxOperationKind
    image_digest: str = Field(pattern=_IMAGE_DIGEST_RE.pattern)
    policy_version: str = Field(min_length=1, max_length=100)
    command_schema_version: str = Field(min_length=1, max_length=100)
    status: SandboxOperationStatus
    retry_disposition: SandboxRetryDisposition
    exit_code: int | None = None
    stdout_preview: str = ""
    stderr_preview: str = ""
    stdout_ref: SandboxOutputRef | None = None
    stderr_ref: SandboxOutputRef | None = None
    output_slice: SandboxOutputSlice | None = None
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    artifacts: tuple[SandboxArtifactManifest, ...] = Field(default=(), max_length=1000)
    datasets: tuple[SandboxDatasetManifest, ...] = Field(default=(), max_length=1000)
    environment: SandboxEnvironmentManifest | None = None
    command_audit: CommandAuditEvidence | None = None
    recovery_guidance: tuple[str, ...] = Field(default=(), max_length=20)
    reused_receipt: bool = False
    started_at: datetime
    finished_at: datetime


class SandboxReviewCandidate(FrozenContract):
    """Only manifest-backed sandbox output may cross into review runtime."""

    artifact: SandboxArtifactManifest
    suggested_title: str = Field(min_length=1, max_length=200)


class SandboxPreflightCheck(FrozenContract):
    name: str = Field(min_length=1, max_length=100)
    passed: bool
    detail: str = Field(max_length=1000)


class SandboxPreflightReport(FrozenContract):
    provider: str = Field(min_length=1, max_length=100)
    operational_ready: bool
    release_ready: bool
    development_override: bool = False
    checks: tuple[SandboxPreflightCheck, ...]


def sandbox_operation_key(request: SandboxOperationRequest) -> str:
    """Compute a stable key across worker retries and lease takeovers."""

    provenance = request.provenance
    canonical = {
        "schema_version": request.schema_version,
        "workspace_id": provenance.workspace_id,
        "mission_id": provenance.mission_id,
        "mission_item_seq": provenance.mission_item_seq,
        "subagent_id": provenance.subagent_id,
        "operation_input": request.operation_input.model_dump(mode="json"),
        "image_digest": request.image_digest,
        "policy_version": request.policy_version,
        "command_schema_version": request.command_schema_version,
        "network_profile": request.network_profile.value,
        "network_allowed_hosts": sorted(request.network_grant.allowed_hosts if request.network_grant is not None else ()),
        "limits": request.limits.model_dump(mode="json"),
        "input_hashes": dict(sorted(request.input_hashes.items())),
    }
    digest = hashlib.sha256(json.dumps(canonical, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return f"sbxop_{digest}"


def sandbox_job_id(operation_key: str) -> str:
    """Derive the stable provider-neutral job id for an operation key."""

    if not _OPERATION_KEY_RE.fullmatch(operation_key):
        raise ValueError("invalid sandbox operation key")
    return f"sbxjob_{hashlib.sha256(operation_key.encode()).hexdigest()}"


def compiled_command_fingerprint(command: CompiledSandboxCommand) -> str:
    canonical = json.dumps(
        {
            "schema_version": command.schema_version,
            "operation": command.operation.value,
            "argv": command.argv,
            "cwd": command.cwd,
            "env": dict(sorted(command.env.items())),
            "compiler_fingerprint": command.compiler_fingerprint,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return content_hash_bytes(canonical)


def content_hash_bytes(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def environment_id(*, image_digest: str, runtime: str, lock_content: bytes) -> str:
    if not _IMAGE_DIGEST_RE.fullmatch(image_digest):
        raise ValueError("image_digest must be a sha256 digest")
    canonical = b"\0".join((image_digest.encode(), runtime.encode(), lock_content))
    return f"sbxenv_{hashlib.sha256(canonical).hexdigest()}"


def utc_now() -> datetime:
    return datetime.now(UTC)
