"""Hardened rootless Docker operation-container provider."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Literal, Protocol, cast
from urllib.parse import urlsplit

from docker.errors import DockerException, ImageNotFound

import docker
from src.sandbox.base import (
    PreparedSandboxJob,
    ProviderEffectState,
    ProviderExecutionResult,
    SandboxOperationProvider,
)
from src.sandbox.config import DockerSandboxConfig
from src.sandbox.contracts import (
    RunPythonInput,
    SandboxNetworkProfile,
    SandboxOperationKind,
    SandboxPreflightCheck,
    SandboxPreflightReport,
    compiled_command_fingerprint,
    sandbox_job_id,
    utc_now,
)
from src.sandbox.exceptions import SandboxPolicyError, SandboxProviderError
from src.sandbox.security import is_artifact_path, validate_secret_free_environment

logger = logging.getLogger(__name__)

_MANAGED_LABEL = "wenjin.sandbox.operation"
_ALLOWED_MOUNT_TARGETS = frozenset(
    {
        "/workspace/main",
        "/workspace/datasets",
        "/workspace/scripts",
        "/workspace/outputs",
        "/workspace/reports",
        "/opt/wenjin/env",
    }
)

_DEADLINE_WRAPPER = """import json, os, signal, subprocess, sys
command = json.loads(sys.argv[1])
timeout = int(sys.argv[2])
process = subprocess.Popen(command, start_new_session=True)
try:
    code = process.wait(timeout=timeout)
except subprocess.TimeoutExpired:
    os.killpg(process.pid, signal.SIGKILL)
    process.wait()
    raise SystemExit(124)
raise SystemExit(code)
"""


@dataclass(frozen=True, slots=True)
class DockerRawExecution:
    exit_code: int | None
    stdout: bytes
    stderr: bytes
    timed_out: bool
    stdout_truncated: bool
    stderr_truncated: bool
    effect_state: ProviderEffectState


class DockerGateway(Protocol):
    async def daemon_info(self) -> dict[str, Any]: ...

    async def network_attributes(self, network_name: str) -> dict[str, Any]: ...

    async def ensure_image(
        self,
        image_reference: str,
        *,
        allow_pull: bool,
    ) -> dict[str, Any]: ...

    async def run_container(
        self,
        *,
        image_reference: str,
        command: tuple[str, ...],
        create_options: dict[str, Any],
        timeout_seconds: int,
        capture_bytes: int,
    ) -> DockerRawExecution: ...


class DockerSdkGateway:
    """Small async adapter around Docker SDK; no session/container identity leaks out."""

    def __init__(self, client: Any | None = None) -> None:
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            try:
                self._client = docker.from_env()  # type: ignore[attr-defined]
            except DockerException as exc:
                raise SandboxProviderError("Docker daemon is unavailable") from exc
        return self._client

    async def daemon_info(self) -> dict[str, Any]:
        try:
            return cast(dict[str, Any], await asyncio.to_thread(self.client.info))
        except DockerException as exc:
            raise SandboxProviderError("Docker daemon preflight failed") from exc

    async def network_attributes(self, network_name: str) -> dict[str, Any]:
        def _inspect() -> dict[str, Any]:
            try:
                network = self.client.networks.get(network_name)
            except DockerException as exc:
                raise SandboxProviderError("sandbox package-index network is unavailable") from exc
            return cast(dict[str, Any], network.attrs)

        return await asyncio.to_thread(_inspect)

    async def ensure_image(
        self,
        image_reference: str,
        *,
        allow_pull: bool,
    ) -> dict[str, Any]:
        def _ensure() -> dict[str, Any]:
            try:
                image = self.client.images.get(image_reference)
            except ImageNotFound:
                if not allow_pull:
                    raise SandboxProviderError("pinned sandbox image is not present") from None
                try:
                    image = self.client.images.pull(image_reference)
                except DockerException as exc:
                    raise SandboxProviderError("pinned sandbox image pull failed") from exc
            return cast(dict[str, Any], image.attrs)

        return await asyncio.to_thread(_ensure)

    async def run_container(
        self,
        *,
        image_reference: str,
        command: tuple[str, ...],
        create_options: dict[str, Any],
        timeout_seconds: int,
        capture_bytes: int,
    ) -> DockerRawExecution:
        cancellation = threading.Event()
        operation_key = str(
            (create_options.get("labels") or {}).get(
                "wenjin.sandbox.operation_key", ""
            )
        )
        worker = asyncio.create_task(
            asyncio.to_thread(
                self._run_container_sync,
                image_reference,
                command,
                create_options,
                timeout_seconds,
                capture_bytes,
                cancellation,
            )
        )
        try:
            return await worker
        except asyncio.CancelledError:
            cancellation.set()
            if operation_key:
                try:
                    await asyncio.wait_for(
                        asyncio.shield(
                            asyncio.to_thread(
                                self._stop_operation_containers_sync,
                                operation_key,
                            )
                        ),
                        timeout=10,
                    )
                except Exception:  # noqa: BLE001 - cancellation remains authoritative.
                    logger.warning(
                        "Failed to stop cancelled sandbox operation %s",
                        operation_key,
                        exc_info=True,
                    )
            raise

    def _run_container_sync(
        self,
        image_reference: str,
        command: tuple[str, ...],
        create_options: dict[str, Any],
        timeout_seconds: int,
        capture_bytes: int,
        cancellation: threading.Event,
    ) -> DockerRawExecution:
        container = None
        dispatch_attempted = False
        try:
            container = self.client.containers.create(
                image=image_reference,
                command=list(command),
                **create_options,
            )
            if cancellation.is_set():
                raise SandboxProviderError(
                    "Docker operation was cancelled before start",
                    effect_uncertain=False,
                )
            dispatch_attempted = True
            try:
                container.start()
            except DockerException as exc:
                raise SandboxProviderError(
                    "Docker operation failed",
                    effect_uncertain=_container_start_effect_uncertain(container),
                ) from exc
            if cancellation.is_set():
                try:
                    container.kill()
                except Exception:  # noqa: BLE001
                    logger.warning("Failed to stop sandbox container after cancellation")
                raise SandboxProviderError(
                    "Docker operation was cancelled",
                    effect_uncertain=True,
                )
            exit_code: int | None
            try:
                wait_result = container.wait(timeout=timeout_seconds)
                exit_code = int(wait_result.get("StatusCode", -1))
                timed_out = exit_code == 124
                if timed_out:
                    exit_code = None
            except Exception as exc:  # Docker SDK wraps HTTP timeout by transport.
                try:
                    container.kill()
                    container.wait(timeout=10)
                except Exception:  # noqa: BLE001
                    logger.warning("Failed to confirm timed-out sandbox container stop")
                if _looks_like_timeout(exc):
                    exit_code = None
                    timed_out = True
                else:
                    raise SandboxProviderError(
                        "Docker operation result is uncertain",
                        effect_uncertain=True,
                    ) from exc
            stdout, stdout_truncated = _bounded_container_logs(
                container,
                stdout=True,
                stderr=False,
                limit=capture_bytes,
            )
            stderr, stderr_truncated = _bounded_container_logs(
                container,
                stdout=False,
                stderr=True,
                limit=capture_bytes,
            )
            return DockerRawExecution(
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                timed_out=timed_out,
                stdout_truncated=stdout_truncated,
                stderr_truncated=stderr_truncated,
                effect_state=ProviderEffectState.CONFIRMED,
            )
        except SandboxProviderError:
            raise
        except DockerException as exc:
            raise SandboxProviderError(
                "Docker operation failed",
                effect_uncertain=dispatch_attempted,
            ) from exc
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except Exception:  # noqa: BLE001
                    logger.warning("Failed to remove sandbox operation container")

    def _stop_operation_containers_sync(self, operation_key: str) -> None:
        """Best-effort interruption for a cancelled ``to_thread`` dispatch."""

        filters = {
            "label": [
                f"{_MANAGED_LABEL}=true",
                f"wenjin.sandbox.operation_key={operation_key}",
            ]
        }
        for container in self.client.containers.list(all=True, filters=filters):
            try:
                container.kill()
            except Exception:  # noqa: BLE001
                logger.warning(
                    "Failed to kill cancelled sandbox container %s",
                    getattr(container, "id", "unknown"),
                )


def _container_start_effect_uncertain(container: Any) -> bool:
    """Return false only when Docker confirms the process never started."""

    try:
        container.reload()
        state = container.attrs.get("State") or {}
    except Exception:  # noqa: BLE001 - daemon uncertainty must fail closed.
        return True
    started_at = str(state.get("StartedAt") or "")
    never_started = not started_at or started_at.startswith("0001-01-01T00:00:00")
    return bool(state.get("Running")) or not never_started


class DockerSandboxProvider(SandboxOperationProvider):
    """Runs every audited job in a new hardened, short-lived container."""

    def __init__(
        self,
        config: DockerSandboxConfig,
        *,
        sandbox_root: Path,
        preflight_mode: Literal["development", "release"],
        gateway: DockerGateway | None = None,
    ) -> None:
        self.config = config
        self.sandbox_root = sandbox_root.resolve()
        self.preflight_mode = preflight_mode
        self.gateway = gateway or DockerSdkGateway()
        self._preflight_report: SandboxPreflightReport | None = None
        self._preflight_lock = asyncio.Lock()

    @property
    def image_digest(self) -> str:
        digest = self.config.image_digest
        if digest:
            return digest
        if "@sha256:" in self.config.image:
            return f"sha256:{self.config.image.rsplit('@sha256:', 1)[1]}"
        raise SandboxPolicyError("sandbox image digest must be resolved before dispatch")

    @property
    def image_reference(self) -> str:
        reference = self.config.image_reference
        if "@sha256:" not in reference:
            raise SandboxPolicyError("sandbox operation image must be digest-pinned")
        return reference

    async def execute(self, job: PreparedSandboxJob) -> ProviderExecutionResult:
        await self._ensure_ready(require_egress=job.request.network_profile != SandboxNetworkProfile.NONE)
        _validate_command_audit_binding(job)
        if job.request.image_digest != self.image_digest:
            raise SandboxPolicyError("mission sandbox image digest does not match provider")
        if job.image_reference != self.image_reference:
            raise SandboxPolicyError("prepared image reference does not match provider")
        _validate_mounts(job, sandbox_root=self.sandbox_root)
        environment = dict(job.command.env)
        validate_secret_free_environment(environment)
        network_options = self._network_options(job, environment)
        limits = job.request.limits
        started_at = utc_now()
        volumes = {
            str(mount.source.resolve()): {
                "bind": mount.target,
                "mode": "ro" if mount.read_only else "rw",
            }
            for mount in job.mounts
        }
        security_opt = ["no-new-privileges:true"]
        if self.config.seccomp_profile != "default":
            security_opt.append(f"seccomp={self.config.seccomp_profile}")
        create_options: dict[str, Any] = {
            "volumes": volumes,
            "working_dir": job.command.cwd,
            "environment": environment,
            "user": f"{self.config.user_uid}:{self.config.user_gid}",
            "privileged": False,
            "cap_drop": ["ALL"],
            "security_opt": security_opt,
            "read_only": True,
            "tmpfs": {
                "/tmp": f"rw,noexec,nosuid,nodev,size={limits.tmpfs_bytes}",
                "/workspace/tmp": f"rw,noexec,nosuid,nodev,size={limits.tmpfs_bytes}",
            },
            "pids_limit": limits.pids,
            "mem_limit": limits.memory_bytes,
            "memswap_limit": limits.memory_swap_bytes,
            "nano_cpus": int(limits.cpu_cores * 1_000_000_000),
            "oom_kill_disable": False,
            "stdin_open": False,
            "tty": False,
            "init": True,
            "auto_remove": False,
            "restart_policy": {"Name": "no"},
            "labels": {
                _MANAGED_LABEL: "true",
                "wenjin.sandbox.job": job.sandbox_job_id,
                "wenjin.sandbox.operation_key": job.request.operation_key,
                "wenjin.sandbox.network_profile": job.request.network_profile.value,
                "wenjin.sandbox.deadline_epoch": str(int(started_at.timestamp()) + limits.wall_time_seconds),
            },
            **network_options,
        }
        raw = await self.gateway.run_container(
            image_reference=self.image_reference,
            command=_deadline_wrapped_command(
                job.command.argv,
                timeout_seconds=limits.wall_time_seconds,
            ),
            create_options=create_options,
            timeout_seconds=limits.wall_time_seconds + 15,
            capture_bytes=limits.stream_capture_bytes,
        )
        return ProviderExecutionResult(
            exit_code=raw.exit_code,
            stdout=raw.stdout,
            stderr=raw.stderr,
            timed_out=raw.timed_out,
            stdout_capture_truncated=raw.stdout_truncated,
            stderr_capture_truncated=raw.stderr_truncated,
            effect_state=raw.effect_state,
            started_at=started_at,
            finished_at=utc_now(),
        )

    async def preflight(self, *, release_gate: bool) -> SandboxPreflightReport:
        checks: list[SandboxPreflightCheck] = []
        development_override = False
        try:
            info = await self.gateway.daemon_info()
            checks.append(SandboxPreflightCheck(name="daemon", passed=True, detail="reachable"))
        except SandboxProviderError as exc:
            return SandboxPreflightReport(
                provider="docker",
                operational_ready=False,
                release_ready=False,
                checks=(SandboxPreflightCheck(name="daemon", passed=False, detail=str(exc)),),
            )

        security_options = tuple(str(item).lower() for item in info.get("SecurityOptions") or ())
        rootless = any("rootless" in item for item in security_options)
        userns = any("userns" in item for item in security_options)
        equivalent = userns and self.config.allow_userns_remap_equivalent
        isolation_passed = rootless or equivalent
        if not isolation_passed and not release_gate and self.config.allow_rootful_development:
            development_override = True
        checks.append(
            SandboxPreflightCheck(
                name="rootless_daemon",
                passed=isolation_passed or development_override,
                detail=("rootless" if rootless else "reviewed userns-remap equivalent" if equivalent else "development-only rootful override" if development_override else "rootless or reviewed userns-remap is required"),
            )
        )
        seccomp = any("seccomp" in item and "unconfined" not in item for item in security_options)
        checks.append(
            SandboxPreflightCheck(
                name="seccomp",
                passed=seccomp,
                detail="daemon default/custom seccomp" if seccomp else "seccomp is unavailable",
            )
        )
        pinned = "@sha256:" in self.config.image_reference
        image_ok = False
        image_env_safe = False
        image_detail = "image is not digest-pinned"
        if pinned:
            try:
                attributes = await self.gateway.ensure_image(
                    self.config.image_reference,
                    allow_pull=self.config.pull_missing_pinned_image,
                )
                image_ok = _image_has_digest(attributes, self.image_digest)
                image_detail = "pinned digest verified" if image_ok else "image digest mismatch"
                image_env_safe = _image_environment_is_secret_free(attributes)
            except SandboxProviderError as exc:
                image_detail = str(exc)
        checks.append(SandboxPreflightCheck(name="image_digest", passed=image_ok, detail=image_detail))
        checks.append(
            SandboxPreflightCheck(
                name="image_environment",
                passed=image_env_safe,
                detail=("image environment has no secret-like keys" if image_env_safe else "image environment contains secret-like keys or is unreadable"),
            )
        )
        checks.append(
            SandboxPreflightCheck(
                name="workspace_quota",
                passed=self.config.workspace_quota_attested,
                detail=("host workspace quota attested" if self.config.workspace_quota_attested else "host workspace quota is not attested"),
            )
        )
        checks.append(
            SandboxPreflightCheck(
                name="bind_mount_identity",
                passed=self.config.bind_mount_identity_attested,
                detail=("non-root bind-mount write identity attested" if self.config.bind_mount_identity_attested else "non-root bind-mount write identity is not attested"),
            )
        )
        egress = self.config.egress
        egress_ready = False
        egress_detail = "package-index proxy enforcement is incomplete"
        if egress.enforcement_attested and egress.network_name and egress.proxy_url and egress.package_index_url:
            try:
                network_attributes = await self.gateway.network_attributes(egress.network_name)
                proxy_host = urlsplit(egress.proxy_url).hostname or ""
                attached_names = {str(value.get("Name") or "") for value in (network_attributes.get("Containers") or {}).values() if isinstance(value, dict)}
                network_internal = network_attributes.get("Internal") is True
                proxy_attached = proxy_host in attached_names
                egress_ready = network_internal and proxy_attached
                if not network_internal:
                    egress_detail = "package-index network is not internal"
                elif not proxy_attached:
                    egress_detail = "configured package proxy is not attached to the network"
                else:
                    egress_detail = "internal proxy-only package network verified"
            except SandboxProviderError as exc:
                egress_detail = str(exc)
        checks.append(
            SandboxPreflightCheck(
                name="package_index_egress",
                passed=egress_ready,
                detail=egress_detail,
            )
        )
        essential_names = {
            "daemon",
            "rootless_daemon",
            "seccomp",
            "image_digest",
            "image_environment",
        }
        operational_ready = all(check.passed for check in checks if check.name in essential_names)
        release_ready = all(check.passed for check in checks) and not development_override
        return SandboxPreflightReport(
            provider="docker",
            operational_ready=operational_ready,
            release_ready=release_ready,
            development_override=development_override,
            checks=tuple(checks),
        )

    async def _ensure_ready(self, *, require_egress: bool) -> None:
        if self._preflight_report is not None:
            self._assert_preflight_ready(
                self._preflight_report,
                require_egress=require_egress,
            )
            return
        async with self._preflight_lock:
            if self._preflight_report is not None:
                self._assert_preflight_ready(
                    self._preflight_report,
                    require_egress=require_egress,
                )
                return
            release_gate = self.preflight_mode == "release"
            report = await self.preflight(release_gate=release_gate)
            self._assert_preflight_ready(
                report,
                require_egress=require_egress,
            )
            self._preflight_report = report

    def _assert_preflight_ready(
        self,
        report: SandboxPreflightReport,
        *,
        require_egress: bool,
    ) -> None:
        release_gate = self.preflight_mode == "release"
        ready = report.release_ready if release_gate else report.operational_ready
        if not ready:
            raise SandboxPolicyError("sandbox provider preflight did not satisfy the configured deployment mode")
        egress_ready = next(
            (check.passed for check in report.checks if check.name == "package_index_egress"),
            False,
        )
        if require_egress and not egress_ready:
            raise SandboxPolicyError("sandbox package-index egress preflight is not ready")

    def _network_options(
        self,
        job: PreparedSandboxJob,
        environment: dict[str, str],
    ) -> dict[str, Any]:
        profile = job.request.network_profile
        if profile == SandboxNetworkProfile.NONE:
            if job.network.profile != SandboxNetworkProfile.NONE:
                raise SandboxPolicyError("prepared network profile mismatch")
            return {"network_mode": "none"}
        if profile == SandboxNetworkProfile.EXPLICIT_EGRESS_ADMIN_ONLY:
            raise SandboxPolicyError("explicit sandbox egress has no phase-one provider controller")
        egress = self.config.egress
        if not (egress.enforcement_attested and egress.network_name and egress.proxy_url and egress.package_index_url):
            raise SandboxPolicyError("package-index proxy enforcement is not configured")
        if job.network.network_name != egress.network_name:
            raise SandboxPolicyError("prepared egress network mismatch")
        parsed_proxy = urlsplit(egress.proxy_url)
        if parsed_proxy.username or parsed_proxy.password:
            raise SandboxPolicyError("proxy credentials may not be passed to operation containers")
        environment.update(
            {
                "HTTP_PROXY": egress.proxy_url,
                "HTTPS_PROXY": egress.proxy_url,
                "ALL_PROXY": egress.proxy_url,
                "NO_PROXY": "",
                "PIP_INDEX_URL": egress.package_index_url,
                "PIP_NO_INPUT": "1",
                "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            }
        )
        validate_secret_free_environment(environment)
        return {"network_mode": egress.network_name}


def _validate_mounts(job: PreparedSandboxJob, *, sandbox_root: Path) -> None:
    targets: set[str] = set()
    operation_input = job.request.operation_input
    artifact_input_targets = (
        set(operation_input.artifact_input_paths)
        if isinstance(operation_input, RunPythonInput)
        else set()
    )
    for mount in job.mounts:
        artifact_input_mount = mount.target in artifact_input_targets
        if mount.target not in _ALLOWED_MOUNT_TARGETS and not artifact_input_mount:
            raise SandboxPolicyError(f"sandbox mount target is forbidden: {mount.target}")
        if mount.target in targets:
            raise SandboxPolicyError("duplicate sandbox mount target")
        targets.add(mount.target)
        source = mount.source.resolve(strict=False)
        if sandbox_root != source and sandbox_root not in source.parents:
            raise SandboxPolicyError("sandbox mount source is outside the managed root")
        if "control" in source.relative_to(sandbox_root).parts:
            raise SandboxPolicyError("sandbox control state cannot be mounted")
        if mount.source.is_symlink():
            raise SandboxPolicyError("sandbox mount source is missing or is a symlink")
        if artifact_input_mount:
            if not mount.read_only or not mount.source.is_file():
                raise SandboxPolicyError(
                    "artifact input mounts must be read-only regular files"
                )
            if not is_artifact_path(mount.target):
                raise SandboxPolicyError("artifact input mount target is not reviewable")
            target_parts = PurePosixPath(mount.target).parts[2:]
            if not target_parts or source.parts[-len(target_parts) :] != target_parts:
                raise SandboxPolicyError(
                    "artifact input mount source does not match its workspace path"
                )
            continue
        if not mount.source.is_dir():
            raise SandboxPolicyError("sandbox mount source is missing or is a symlink")
        if mount.target in {"/workspace/main", "/workspace/datasets", "/workspace/scripts"} and not mount.read_only:
            raise SandboxPolicyError("workspace inputs and scripts must be mounted read-only")
        if mount.target in {"/workspace/outputs", "/workspace/reports"} and not mount.read_only:
            relative_parts = source.relative_to(sandbox_root).parts
            if "operation_staging" not in relative_parts or job.request.operation_key not in relative_parts:
                raise SandboxPolicyError("writable outputs must use operation-scoped staging")
        if mount.target == "/opt/wenjin/env" and not mount.read_only:
            relative_parts = source.relative_to(sandbox_root).parts
            if ".staging" not in relative_parts or job.request.operation_key not in relative_parts:
                raise SandboxPolicyError("writable environment must use operation-scoped staging")
    if not artifact_input_targets.issubset(targets):
        raise SandboxPolicyError("declared artifact inputs are not mounted")
    if job.request.operation == SandboxOperationKind.INSTALL_DEPENDENCIES:
        if targets != {"/opt/wenjin/env"} or job.mounts[0].read_only:
            raise SandboxPolicyError("dependency installation may mount only its writable environment staging")


def _validate_command_audit_binding(job: PreparedSandboxJob) -> None:
    audit = job.command_audit
    command = job.command
    request = job.request
    if audit.decision != "allow":
        raise SandboxPolicyError("command audit denied provider execution")
    if audit.operation != request.operation or command.operation != request.operation:
        raise SandboxPolicyError("command audit operation binding is invalid")
    if request.command_schema_version != command.schema_version or audit.command_schema_version != command.schema_version:
        raise SandboxPolicyError("command audit schema binding is invalid")
    if job.sandbox_job_id != sandbox_job_id(request.operation_key):
        raise SandboxPolicyError("sandbox job identity binding is invalid")
    if audit.compiler_fingerprint != command.compiler_fingerprint:
        raise SandboxPolicyError("command audit compiler binding is invalid")
    if audit.command_fingerprint != compiled_command_fingerprint(command):
        raise SandboxPolicyError("command audit argv binding is invalid")
    if audit.network_profile != request.network_profile:
        raise SandboxPolicyError("command audit network binding is invalid")
    if job.network.profile != request.network_profile:
        raise SandboxPolicyError("prepared network binding is invalid")


def _image_has_digest(attributes: dict[str, Any], expected_digest: str) -> bool:
    repo_digests = tuple(str(item) for item in attributes.get("RepoDigests") or ())
    image_id = str(attributes.get("Id") or "")
    return image_id == expected_digest or any(item.endswith(f"@{expected_digest}") for item in repo_digests)


def _image_environment_is_secret_free(attributes: dict[str, Any]) -> bool:
    raw = (attributes.get("Config") or {}).get("Env") or ()
    environment: dict[str, str] = {}
    for item in raw:
        key, separator, value = str(item).partition("=")
        if not separator or not key:
            return False
        environment[key] = value
    try:
        validate_secret_free_environment(environment)
    except ValueError:
        return False
    return True


def _bounded_container_logs(
    container: Any,
    *,
    stdout: bool,
    stderr: bool,
    limit: int,
) -> tuple[bytes, bool]:
    chunks: list[bytes] = []
    size = 0
    truncated = False
    raw: Iterable[bytes] = container.logs(
        stdout=stdout,
        stderr=stderr,
        stream=True,
        follow=False,
    )
    for chunk in raw:
        if not isinstance(chunk, bytes):
            chunk = bytes(chunk)
        remaining = max(0, limit - size)
        if remaining:
            chunks.append(chunk[:remaining])
            size += min(len(chunk), remaining)
        if len(chunk) > remaining:
            truncated = True
            break
    return b"".join(chunks), truncated


def _looks_like_timeout(exc: Exception) -> bool:
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    return "timeout" in name or "timed out" in text or "read timed out" in text


def _deadline_wrapped_command(
    command: tuple[str, ...],
    *,
    timeout_seconds: int,
) -> tuple[str, ...]:
    return (
        "python3",
        "-c",
        _DEADLINE_WRAPPER,
        json.dumps(command, ensure_ascii=True, separators=(",", ":")),
        str(timeout_seconds),
    )
