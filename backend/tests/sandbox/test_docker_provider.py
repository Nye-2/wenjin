from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from docker.errors import DockerException

from src.sandbox.base import (
    PreparedSandboxJob,
    ProviderEffectState,
    ProviderNetworkConfig,
    SandboxMount,
)
from src.sandbox.config import DockerEgressConfig, DockerSandboxConfig
from src.sandbox.contracts import (
    CommandAuditEvidence,
    CompiledSandboxCommand,
    InstallDependenciesInput,
    RunPythonInput,
    SandboxMissionProvenance,
    SandboxNetworkGrant,
    SandboxNetworkProfile,
    SandboxOperationRequest,
    compiled_command_fingerprint,
    content_hash_bytes,
    sandbox_job_id,
)
from src.sandbox.exceptions import SandboxPolicyError, SandboxProviderError
from src.sandbox.providers.docker import (
    DockerRawExecution,
    DockerSandboxProvider,
    DockerSdkGateway,
)

IMAGE_DIGEST = f"sha256:{'a' * 64}"
IMAGE = "registry.example/wenjin-sandbox:2"


class _FakeGateway:
    def __init__(
        self,
        *,
        security_options=None,
        image_environment=(),
        network_internal: bool = True,
        network_container_names: tuple[str, ...] = ("egress-proxy",),
    ) -> None:
        self.security_options = security_options or [
            "name=seccomp,profile=builtin",
            "name=rootless",
        ]
        self.image_environment = image_environment
        self.network_internal = network_internal
        self.network_container_names = network_container_names
        self.run_calls: list[dict] = []

    async def daemon_info(self):
        return {"SecurityOptions": self.security_options}

    async def ensure_image(self, image_reference: str, *, allow_pull: bool):
        return {
            "Id": IMAGE_DIGEST,
            "RepoDigests": [f"{IMAGE}@{IMAGE_DIGEST}"],
            "Config": {"Env": list(self.image_environment)},
        }

    async def network_attributes(self, _network_name: str):
        return {
            "Internal": self.network_internal,
            "Containers": {str(index): {"Name": name} for index, name in enumerate(self.network_container_names)},
        }

    async def run_container(self, **kwargs):
        self.run_calls.append(kwargs)
        return DockerRawExecution(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            timed_out=False,
            stdout_truncated=False,
            stderr_truncated=False,
            effect_state=ProviderEffectState.CONFIRMED,
        )


class _DispatchFailureClient:
    class _Containers:
        @staticmethod
        def run(**_kwargs):
            raise DockerException("connection lost during dispatch")

    containers = _Containers()


def _provenance() -> SandboxMissionProvenance:
    return SandboxMissionProvenance(
        workspace_id="workspace-1",
        mission_id="mission-1",
        mission_item_seq=2,
        lease_epoch=3,
    )


def _run_request() -> SandboxOperationRequest:
    operation_input = RunPythonInput(script="print('ok')\n")
    return SandboxOperationRequest.build(
        provenance=_provenance(),
        operation_input=operation_input,
        image_digest=IMAGE_DIGEST,
        input_hashes={"script": content_hash_bytes(operation_input.script.encode())},
    )


def _prepared_job(tmp_path, request: SandboxOperationRequest) -> PreparedSandboxJob:
    roots = {}
    for name in ("main", "datasets", "scripts"):
        path = tmp_path / name
        path.mkdir()
        roots[name] = path
    for name in ("outputs", "reports"):
        path = tmp_path / "operation_staging" / request.operation_key / name
        path.mkdir(parents=True)
        roots[name] = path
    command = CompiledSandboxCommand(
        operation=request.operation,
        argv=("python3", "/workspace/scripts/analysis.py"),
        cwd="/workspace",
        env={"PYTHONUNBUFFERED": "1"},
        compiler_fingerprint=content_hash_bytes(b"compiler"),
    )
    audit = CommandAuditEvidence(
        decision="allow",
        risk_level="low",
        operation=request.operation,
        command_schema_version=command.schema_version,
        compiler_fingerprint=command.compiler_fingerprint,
        command_fingerprint=compiled_command_fingerprint(command),
        argv_preview=command.argv,
        cwd=command.cwd,
        env_keys=("PYTHONUNBUFFERED",),
        network_profile=request.network_profile,
    )
    return PreparedSandboxJob(
        request=request,
        sandbox_job_id=sandbox_job_id(request.operation_key),
        command=command,
        command_audit=audit,
        mounts=tuple(
            SandboxMount(
                source=roots[name],
                target=f"/workspace/{name}",
                read_only=name not in {"outputs", "reports"},
            )
            for name in roots
        ),
        network=ProviderNetworkConfig(profile=request.network_profile),
        image_reference=f"{IMAGE}@{IMAGE_DIGEST}",
    )


def _config(**changes) -> DockerSandboxConfig:
    values = {
        "image": IMAGE,
        "image_digest": IMAGE_DIGEST,
        "workspace_quota_attested": True,
        "bind_mount_identity_attested": True,
        "egress": DockerEgressConfig(
            network_name="wenjin-package-egress",
            proxy_url="http://egress-proxy:3128",
            package_index_url="https://pypi.org/simple",
            enforcement_attested=True,
        ),
    }
    values.update(changes)
    return DockerSandboxConfig(**values)


@pytest.mark.asyncio
async def test_docker_dispatch_error_is_treated_as_an_uncertain_effect() -> None:
    gateway = DockerSdkGateway(client=_DispatchFailureClient())

    with pytest.raises(SandboxProviderError) as captured:
        await gateway.run_container(
            image_reference=f"{IMAGE}@{IMAGE_DIGEST}",
            command=("python3", "-c", "print('ok')"),
            create_options={},
            timeout_seconds=10,
            capture_bytes=1024,
        )

    assert captured.value.effect_uncertain


@pytest.mark.asyncio
async def test_operation_container_enforces_hardening_and_resource_limits(tmp_path) -> None:
    gateway = _FakeGateway()
    provider = DockerSandboxProvider(
        _config(),
        sandbox_root=tmp_path,
        preflight_mode="release",
        gateway=gateway,
    )
    job = _prepared_job(tmp_path, _run_request())

    result = await provider.execute(job)

    assert result.exit_code == 0
    [call] = gateway.run_calls
    options = call["create_options"]
    assert call["image_reference"] == f"{IMAGE}@{IMAGE_DIGEST}"
    assert call["command"][:2] == ("python3", "-c")
    assert tuple(json.loads(call["command"][3])) == job.command.argv
    assert call["command"][4] == str(job.request.limits.wall_time_seconds)
    assert call["timeout_seconds"] == job.request.limits.wall_time_seconds + 15
    assert options["user"] == "65532:65532"
    assert options["privileged"] is False
    assert options["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in options["security_opt"]
    assert options["read_only"] is True
    assert options["network_mode"] == "none"
    assert options["pids_limit"] == job.request.limits.pids
    assert options["mem_limit"] == job.request.limits.memory_bytes
    assert options["memswap_limit"] == job.request.limits.memory_swap_bytes
    assert options["nano_cpus"] == int(job.request.limits.cpu_cores * 1_000_000_000)
    assert options["tmpfs"]["/workspace/tmp"].startswith("rw,noexec,nosuid,nodev")
    assert options["restart_policy"] == {"Name": "no"}
    assert options["labels"]["wenjin.sandbox.deadline_epoch"]
    assert all(volume["bind"] != "/workspace" for volume in options["volumes"].values())
    assert all("control" not in source for source in options["volumes"])
    assert "devices" not in options
    assert "ports" not in options


@pytest.mark.asyncio
async def test_package_install_uses_only_attested_proxy_network(tmp_path) -> None:
    gateway = _FakeGateway()
    provider = DockerSandboxProvider(
        _config(),
        sandbox_root=tmp_path,
        preflight_mode="release",
        gateway=gateway,
    )
    grant = SandboxNetworkGrant(
        permission_request_id="permission-1",
        approved_scope="operation",
        allowed_hosts=("pypi.org",),
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    request = SandboxOperationRequest.build(
        provenance=_provenance(),
        operation_input=InstallDependenciesInput(packages=("pandas==2.3.0",)),
        image_digest=IMAGE_DIGEST,
        network_profile=SandboxNetworkProfile.PACKAGE_INDEX_ONLY,
        network_grant=grant,
    )
    job = _prepared_job(tmp_path, request)
    env_source = tmp_path / "environments" / ".staging" / request.operation_key
    env_source.mkdir(parents=True)
    install_command = CompiledSandboxCommand(
        operation=request.operation,
        argv=("python3", "-c", "pass", '["pandas==2.3.0"]'),
        cwd="/opt/wenjin/env",
        env={"PYTHONUNBUFFERED": "1"},
        compiler_fingerprint=content_hash_bytes(b"compiler"),
    )
    job = PreparedSandboxJob(
        request=job.request,
        sandbox_job_id=job.sandbox_job_id,
        command=install_command,
        command_audit=job.command_audit.model_copy(
            update={
                "operation": request.operation,
                "network_profile": request.network_profile,
                "command_fingerprint": compiled_command_fingerprint(install_command),
            }
        ),
        mounts=(SandboxMount(source=env_source, target="/opt/wenjin/env", read_only=False),),
        network=ProviderNetworkConfig(
            profile=SandboxNetworkProfile.PACKAGE_INDEX_ONLY,
            network_name="wenjin-package-egress",
        ),
        image_reference=job.image_reference,
    )

    await provider.execute(job)

    options = gateway.run_calls[0]["create_options"]
    assert options["network_mode"] == "wenjin-package-egress"
    assert options["environment"]["HTTPS_PROXY"] == "http://egress-proxy:3128"
    assert options["environment"]["PIP_INDEX_URL"] == "https://pypi.org/simple"
    assert options["environment"]["NO_PROXY"] == ""


@pytest.mark.asyncio
async def test_provider_rejects_command_changed_after_audit(tmp_path) -> None:
    gateway = _FakeGateway()
    provider = DockerSandboxProvider(
        _config(),
        sandbox_root=tmp_path,
        preflight_mode="release",
        gateway=gateway,
    )
    job = _prepared_job(tmp_path, _run_request())
    tampered = PreparedSandboxJob(
        request=job.request,
        sandbox_job_id=job.sandbox_job_id,
        command=job.command.model_copy(update={"argv": ("python3", "/workspace/scripts/other.py")}),
        command_audit=job.command_audit,
        mounts=job.mounts,
        network=job.network,
        image_reference=job.image_reference,
    )

    with pytest.raises(SandboxPolicyError, match="argv binding"):
        await provider.execute(tampered)

    assert gateway.run_calls == []


@pytest.mark.asyncio
async def test_release_preflight_accepts_rootless_pinned_and_attested_profile(tmp_path) -> None:
    provider = DockerSandboxProvider(
        _config(),
        sandbox_root=tmp_path,
        preflight_mode="release",
        gateway=_FakeGateway(),
    )

    report = await provider.preflight(release_gate=True)

    assert report.operational_ready
    assert report.release_ready
    assert not report.development_override
    assert all(check.passed for check in report.checks)


@pytest.mark.asyncio
async def test_release_preflight_rejects_direct_route_or_missing_proxy(tmp_path) -> None:
    direct_route = DockerSandboxProvider(
        _config(),
        sandbox_root=tmp_path / "direct",
        preflight_mode="release",
        gateway=_FakeGateway(network_internal=False),
    )
    missing_proxy = DockerSandboxProvider(
        _config(),
        sandbox_root=tmp_path / "missing-proxy",
        preflight_mode="release",
        gateway=_FakeGateway(network_container_names=("other-service",)),
    )

    direct_report = await direct_route.preflight(release_gate=True)
    missing_report = await missing_proxy.preflight(release_gate=True)

    assert not direct_report.release_ready
    assert not missing_report.release_ready
    direct_check = next(check for check in direct_report.checks if check.name == "package_index_egress")
    assert direct_check.detail == "package-index network is not internal"


@pytest.mark.asyncio
async def test_release_mode_blocks_execution_before_container_when_preflight_fails(
    tmp_path,
) -> None:
    gateway = _FakeGateway(security_options=["name=seccomp,profile=builtin"])
    provider = DockerSandboxProvider(
        _config(),
        sandbox_root=tmp_path,
        preflight_mode="release",
        gateway=gateway,
    )

    with pytest.raises(SandboxPolicyError, match="preflight"):
        await provider.execute(_prepared_job(tmp_path, _run_request()))

    assert gateway.run_calls == []


@pytest.mark.asyncio
async def test_rootful_development_override_never_passes_release_gate(tmp_path) -> None:
    gateway = _FakeGateway(security_options=["name=seccomp,profile=builtin"])
    provider = DockerSandboxProvider(
        _config(allow_rootful_development=True),
        sandbox_root=tmp_path,
        preflight_mode="development",
        gateway=gateway,
    )

    development = await provider.preflight(release_gate=False)
    release = await provider.preflight(release_gate=True)

    assert development.development_override
    assert development.operational_ready
    assert not development.release_ready
    assert not release.development_override
    assert not release.release_ready


@pytest.mark.asyncio
async def test_image_with_baked_secret_like_environment_fails_preflight(tmp_path) -> None:
    gateway = _FakeGateway(image_environment=("OPENAI_API_KEY=should-not-be-here",))
    provider = DockerSandboxProvider(
        _config(),
        sandbox_root=tmp_path,
        preflight_mode="release",
        gateway=gateway,
    )

    report = await provider.preflight(release_gate=True)

    assert not report.operational_ready
    assert not report.release_ready
    image_check = next(check for check in report.checks if check.name == "image_environment")
    assert not image_check.passed


@pytest.mark.asyncio
async def test_unattested_package_egress_is_denied_before_container(tmp_path) -> None:
    gateway = _FakeGateway()
    provider = DockerSandboxProvider(
        _config(egress=DockerEgressConfig()),
        sandbox_root=tmp_path,
        preflight_mode="development",
        gateway=gateway,
    )
    grant = SandboxNetworkGrant(
        permission_request_id="permission-1",
        approved_scope="operation",
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    request = SandboxOperationRequest.build(
        provenance=_provenance(),
        operation_input=InstallDependenciesInput(packages=("pandas==2.3.0",)),
        image_digest=IMAGE_DIGEST,
        network_profile=SandboxNetworkProfile.PACKAGE_INDEX_ONLY,
        network_grant=grant,
    )
    job = _prepared_job(tmp_path, request)
    env_source = tmp_path / "environments" / ".staging" / request.operation_key
    env_source.mkdir(parents=True)
    job = PreparedSandboxJob(
        request=job.request,
        sandbox_job_id=job.sandbox_job_id,
        command=job.command,
        command_audit=job.command_audit,
        mounts=(SandboxMount(source=env_source, target="/opt/wenjin/env", read_only=False),),
        network=ProviderNetworkConfig(
            profile=SandboxNetworkProfile.PACKAGE_INDEX_ONLY,
            network_name="missing",
        ),
        image_reference=job.image_reference,
    )

    with pytest.raises(SandboxPolicyError, match="egress preflight"):
        await provider.execute(job)

    assert gateway.run_calls == []


@pytest.mark.asyncio
async def test_provider_rejects_control_or_host_mount_even_with_allowed_target(tmp_path) -> None:
    gateway = _FakeGateway()
    provider = DockerSandboxProvider(
        _config(),
        sandbox_root=tmp_path,
        preflight_mode="release",
        gateway=gateway,
    )
    request = _run_request()
    job = _prepared_job(tmp_path, request)
    control = tmp_path / "workspaces" / "x" / "control"
    control.mkdir(parents=True)
    unsafe = PreparedSandboxJob(
        request=job.request,
        sandbox_job_id=job.sandbox_job_id,
        command=job.command,
        command_audit=job.command_audit,
        mounts=(SandboxMount(source=control, target="/workspace/main", read_only=False),),
        network=job.network,
        image_reference=job.image_reference,
    )

    with pytest.raises(SandboxPolicyError, match="control"):
        await provider.execute(unsafe)

    assert gateway.run_calls == []


@pytest.mark.asyncio
async def test_provider_rejects_direct_writable_public_artifact_mount(tmp_path) -> None:
    gateway = _FakeGateway()
    provider = DockerSandboxProvider(
        _config(),
        sandbox_root=tmp_path,
        preflight_mode="release",
        gateway=gateway,
    )
    request = _run_request()
    job = _prepared_job(tmp_path, request)
    public_outputs = tmp_path / "workspaces" / "x" / "public" / "outputs"
    public_outputs.mkdir(parents=True)
    unsafe = PreparedSandboxJob(
        request=job.request,
        sandbox_job_id=job.sandbox_job_id,
        command=job.command,
        command_audit=job.command_audit,
        mounts=(
            SandboxMount(
                source=public_outputs,
                target="/workspace/outputs",
                read_only=False,
            ),
        ),
        network=job.network,
        image_reference=job.image_reference,
    )

    with pytest.raises(SandboxPolicyError, match="operation-scoped staging"):
        await provider.execute(unsafe)

    assert gateway.run_calls == []
