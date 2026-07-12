"""Sandbox worker-host preflight entry point."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import stat
import tempfile
from collections.abc import Sequence
from pathlib import Path

from src.sandbox.config import SandboxSettings, get_sandbox_settings
from src.sandbox.contracts import (
    SandboxPreflightCheck,
    SandboxPreflightReport,
    content_hash_bytes,
)
from src.sandbox.providers.docker import DockerSandboxProvider
from src.sandbox.security import SandboxPathError, require_read_before_write


async def run_sandbox_preflight(
    settings: SandboxSettings | None = None,
    *,
    release_gate: bool | None = None,
) -> SandboxPreflightReport:
    effective = settings or get_sandbox_settings()
    gate = effective.deployment_mode == "production" if release_gate is None else release_gate
    boundary_checks = (
        docker_socket_access_check(),
        *workspace_policy_checks(effective.root_dir),
    )
    provider = DockerSandboxProvider(
        effective.docker,
        sandbox_root=effective.root_dir,
        preflight_mode="release" if gate else "development",
    )
    provider_report = await provider.preflight(release_gate=gate)
    boundary_ready = all(check.passed for check in boundary_checks)
    return provider_report.model_copy(
        update={
            "operational_ready": provider_report.operational_ready and boundary_ready,
            "release_ready": provider_report.release_ready and boundary_ready,
            "checks": (*boundary_checks, *provider_report.checks),
        }
    )


def docker_socket_access_check(*, docker_host: str | None = None) -> SandboxPreflightCheck:
    """Prove that this process can use the mounted local Docker socket."""

    endpoint = docker_host if docker_host is not None else os.environ.get("DOCKER_HOST", "unix:///var/run/docker.sock")
    if not endpoint.startswith("unix://"):
        return SandboxPreflightCheck(
            name="docker_socket_access",
            passed=False,
            detail="release workers require a local unix Docker socket; remote Docker endpoints are forbidden",
        )
    path = Path(endpoint.removeprefix("unix://"))
    try:
        metadata = path.stat()
    except OSError as exc:
        return SandboxPreflightCheck(
            name="docker_socket_access",
            passed=False,
            detail=f"Docker socket {path} is unavailable: {exc.strerror or type(exc).__name__}",
        )
    mode = stat.S_IMODE(metadata.st_mode)
    identity = f"process uid={os.geteuid()} gids={','.join(str(value) for value in os.getgroups())}; socket uid={metadata.st_uid} gid={metadata.st_gid} mode={mode:04o}"
    if not stat.S_ISSOCK(metadata.st_mode):
        return SandboxPreflightCheck(
            name="docker_socket_access",
            passed=False,
            detail=f"configured Docker endpoint is not a unix socket ({identity})",
        )
    if not os.access(path, os.R_OK | os.W_OK):
        return SandboxPreflightCheck(
            name="docker_socket_access",
            passed=False,
            detail=f"Docker socket is not readable and writable ({identity}); set SANDBOX_DOCKER_GID to the container-visible mounted socket gid and recreate mission-worker",
        )
    return SandboxPreflightCheck(
        name="docker_socket_access",
        passed=True,
        detail=f"local unix Docker socket is readable and writable ({identity})",
    )


def workspace_policy_checks(root_dir: Path) -> tuple[SandboxPreflightCheck, ...]:
    """Exercise workspace writes and the read-before-write guard without retaining data."""

    root = root_dir.expanduser()
    if root.is_symlink():
        detail = f"sandbox root may not be a symlink: {root}"
        failed = SandboxPreflightCheck(name="workspace_access", passed=False, detail=detail)
        return (failed, SandboxPreflightCheck(name="read_before_write", passed=False, detail=detail))
    try:
        root.mkdir(parents=True, exist_ok=True, mode=0o750)
        with tempfile.TemporaryDirectory(prefix=".preflight-", dir=root) as temporary:
            probe = Path(temporary) / "existing.txt"
            content = b"wenjin-sandbox-preflight\n"
            probe.write_bytes(content)
            try:
                require_read_before_write(probe, expected_content_hash=None)
            except SandboxPathError:
                pass
            else:
                raise RuntimeError("existing file mutation was accepted without a base content hash")
            require_read_before_write(
                probe,
                expected_content_hash=content_hash_bytes(content),
            )
    except (OSError, RuntimeError, SandboxPathError) as exc:
        detail = f"sandbox workspace policy probe failed at {root}: {exc}"
        failed = SandboxPreflightCheck(name="workspace_access", passed=False, detail=detail)
        return (failed, SandboxPreflightCheck(name="read_before_write", passed=False, detail=detail))
    return (
        SandboxPreflightCheck(
            name="workspace_access",
            passed=True,
            detail=f"sandbox root is writable and temporary probe cleanup succeeded: {root}",
        ),
        SandboxPreflightCheck(
            name="read_before_write",
            passed=True,
            detail="existing-file writes reject a missing base hash and accept the current content hash",
        ),
    )


def sandbox_free_environment(environment: dict[str, str]) -> dict[str, str]:
    """Remove sandbox authority from processes outside the Mission worker."""

    return {key: value for key, value in environment.items() if not key.upper().startswith("SANDBOX_")}


def exec_process(command: Sequence[str], *, environment: dict[str, str]) -> None:
    if not command:
        raise ValueError("an executable command is required")
    os.execvpe(command[0], list(command), environment)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the Wenjin sandbox worker host")
    parser.add_argument("--release", action="store_true", help="Require production release proof")
    parser.add_argument(
        "--strip-sandbox-env",
        action="store_true",
        help="Remove every SANDBOX_* variable before starting a non-Mission process",
    )
    parser.add_argument("--exec", dest="exec_command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    environment = sandbox_free_environment(dict(os.environ)) if args.strip_sandbox_env else dict(os.environ)
    if args.release or not args.exec_command:
        report = asyncio.run(run_sandbox_preflight(release_gate=args.release))
        print(json.dumps(report.model_dump(mode="json"), ensure_ascii=True, sort_keys=True), flush=True)
        ready = report.release_ready if args.release else report.operational_ready
        if not ready:
            return 1
    if args.exec_command:
        exec_process(args.exec_command, environment=environment)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
