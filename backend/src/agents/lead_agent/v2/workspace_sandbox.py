"""Workspace-scoped sandbox DataService manager."""

from __future__ import annotations

import re
import shlex
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.sandbox import (
    SandboxEnvironmentCreatePayload,
    SandboxEnvironmentPayload,
    SandboxJobCreatePayload,
    SandboxJobPayload,
    SandboxJobUpdatePayload,
    SandboxLeaseAcquirePayload,
    SandboxLeaseReleasePayload,
)
from src.dataservice_client.provider import dataservice_client

WORKSPACE_VENV_DIR = "/workspace/.wenjin/env/python"
WORKSPACE_VENV_PYTHON = f"{WORKSPACE_VENV_DIR}/bin/python"
WORKSPACE_PIP_CACHE_DIR = "/workspace/.wenjin/cache/pip"
ENSURE_WORKSPACE_VENV_COMMAND = f"test -x {WORKSPACE_VENV_PYTHON} || python -m venv {WORKSPACE_VENV_DIR}"

_MAX_DEPENDENCY_HINTS = 20
_SAFE_PACKAGE_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_.-]*"
    r"(?:\[[A-Za-z0-9_,.-]+\])?"
    r"(?:\s*(?:==|!=|~=|>=|<=|>|<)\s*[A-Za-z0-9_.!*+-]+)?$"
)
_SAFE_MODULE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
_MISSING_MODULE_PATTERNS = (
    re.compile(r"ModuleNotFoundError:\s+No module named ['\"]([^'\"]+)['\"]"),
    re.compile(r"ImportError:\s+No module named ['\"]?([A-Za-z0-9_.]+)['\"]?"),
)
_MODULE_PACKAGE_OVERRIDES = {
    "bs4": "beautifulsoup4",
    "cv2": "opencv-python",
    "pil": "Pillow",
    "sklearn": "scikit-learn",
    "yaml": "PyYAML",
}


def workspace_provider_key(workspace_id: str) -> str:
    """Return the deterministic provider key for one workspace sandbox."""

    return re.sub(r"[^A-Za-z0-9_.-]", "-", f"workspace-{workspace_id}")[:100]


def normalize_dependency_hints(raw: Any) -> list[str]:
    """Normalize user/model supplied Python package hints into safe pip specs."""

    if raw is None:
        return []
    if isinstance(raw, str):
        items: list[Any] = [item for item in re.split(r"[,\n]", raw)]
    elif isinstance(raw, (list, tuple, set)):
        items = list(raw)
    else:
        raise ValueError("dependency_hints must be a string or list of package specs")

    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = " ".join(str(item or "").strip().split())
        if not value:
            continue
        if len(normalized) >= _MAX_DEPENDENCY_HINTS:
            raise ValueError("dependency_hints exceeds 20 package specs")
        if (
            "://" in value
            or value.startswith(("-", ".", "/"))
            or "@" in value
            or ";" in value
            or any(ch in value for ch in ("|", "&", "`", "$", "\\"))
            or not _SAFE_PACKAGE_RE.fullmatch(value)
        ):
            raise ValueError(f"unsafe sandbox dependency hint: {item}")
        key = _package_key(value)
        if key not in seen:
            seen.add(key)
            normalized.append(value)
    return normalized


def policy_allows_package_install(policy: dict[str, Any]) -> bool:
    """Return whether a capability policy permits controlled package installs."""

    allowed = {str(item) for item in policy.get("allowed_operations") or []}
    return bool(policy.get("allow_package_install")) or bool(
        {"install_python_packages", "install_dependencies", "pip_install"}.intersection(allowed)
    )


def build_pip_install_command(package_specs: list[str]) -> str:
    """Build the controlled pip install command run inside the workspace venv."""

    packages = _normalized_install_packages(package_specs)
    quoted = " ".join(shlex.quote(package) for package in packages)
    return (
        f"{WORKSPACE_VENV_PYTHON} -m pip install --disable-pip-version-check "
        f"--no-input --cache-dir {WORKSPACE_PIP_CACHE_DIR} {quoted}"
    )


def build_pip_install_argv(package_specs: list[str]) -> tuple[str, ...]:
    """Build the argv form used for command audit and future exec contracts."""

    packages = _normalized_install_packages(package_specs)
    return (
        WORKSPACE_VENV_PYTHON,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-input",
        "--cache-dir",
        WORKSPACE_PIP_CACHE_DIR,
        *packages,
    )


def detect_missing_python_module(output_text: str) -> str | None:
    """Extract a missing Python module name from stderr/stdout."""

    for pattern in _MISSING_MODULE_PATTERNS:
        match = pattern.search(output_text or "")
        if match:
            module = match.group(1).strip()
            if _SAFE_MODULE_RE.fullmatch(module):
                return module.split(".", 1)[0]
    return None


def resolve_package_for_missing_module(module_name: str, dependency_hints: list[str]) -> str | None:
    """Map a missing import name to a package spec, preferring explicit hints."""

    if not _SAFE_MODULE_RE.fullmatch(module_name or ""):
        return None
    module_key = module_name.split(".", 1)[0].lower().replace("_", "-")
    for hint in dependency_hints:
        if _package_key(hint) == module_key:
            return hint
    return _MODULE_PACKAGE_OVERRIDES.get(module_key, module_key)


def install_policy_snapshot(policy: dict[str, Any]) -> dict[str, Any]:
    """Translate capability-level install permission into the DataService contract."""

    snapshot = dict(policy or {})
    snapshot["allow_package_install"] = policy_allows_package_install(snapshot)
    return snapshot


def _package_key(package_spec: str) -> str:
    base = re.split(r"\s*(?:==|!=|~=|>=|<=|>|<)\s*", package_spec, maxsplit=1)[0]
    base = base.split("[", 1)[0]
    return base.lower().replace("_", "-")


def _normalized_install_packages(package_specs: list[str]) -> list[str]:
    packages = normalize_dependency_hints(package_specs)
    if not packages:
        raise ValueError("package install requires at least one package")
    return packages


class WorkspaceSandboxManager:
    """DataService-backed manager for one workspace sandbox environment."""

    def __init__(self, dataservice: AsyncDataServiceClient | None = None) -> None:
        self._dataservice = dataservice

    @asynccontextmanager
    async def _client(self) -> AsyncIterator[AsyncDataServiceClient]:
        if self._dataservice is not None:
            yield self._dataservice
            return
        async with dataservice_client() as client:
            yield client

    async def get_or_create_environment(
        self,
        *,
        workspace_id: str,
        sandbox_policy: dict[str, Any],
        resource_limits: dict[str, Any],
        runtime_image: str,
    ) -> SandboxEnvironmentPayload:
        provider_key = workspace_provider_key(workspace_id)
        async with self._client() as client:
            return await client.get_or_create_sandbox_environment(
                workspace_id,
                SandboxEnvironmentCreatePayload(
                    workspace_id=workspace_id,
                    sandbox_id=provider_key,
                    provider="docker",
                    state="active",
                    workspace_path=None,
                    network_policy="restricted_egress",
                    policy_json=dict(sandbox_policy or {}),
                    resource_limits_json=dict(resource_limits or {}),
                    created_by="lead_agent",
                    metadata_json={
                        "provider_key": provider_key,
                        "runtime_image": runtime_image,
                    },
                ),
            )

    async def create_job(
        self,
        *,
        workspace_id: str,
        environment_id: str,
        execution_id: str,
        node_id: str,
        operation: str,
        billable: bool,
        command: str,
        runtime_image: str,
        sandbox_policy: dict[str, Any],
        resource_limits: dict[str, Any],
        metadata: dict[str, Any],
        script_hash: str | None = None,
        network_policy: str = "none",
    ) -> SandboxJobPayload:
        async with self._client() as client:
            return await client.create_sandbox_job(
                SandboxJobCreatePayload(
                    workspace_id=workspace_id,
                    sandbox_environment_id=environment_id,
                    execution_id=execution_id,
                    execution_node_id=node_id,
                    operation=operation,
                    billable=billable,
                    language="python",
                    runtime_image=runtime_image,
                    command=command,
                    script_hash=script_hash,
                    network_policy=network_policy,
                    resource_limits_json=dict(resource_limits or {}),
                    policy_json=dict(sandbox_policy or {}),
                    metadata_json=dict(metadata or {}),
                )
            )

    async def update_job(
        self,
        job_id: str,
        *,
        status: str,
        exit_code: int | None = None,
        error_text: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        async with self._client() as client:
            await client.update_sandbox_job(
                job_id,
                SandboxJobUpdatePayload(
                    status=status,
                    exit_code=exit_code,
                    error_text=error_text,
                    metadata_json=dict(metadata) if metadata is not None else None,
                ),
            )

    async def acquire_lease(
        self,
        *,
        workspace_id: str,
        environment_id: str,
        job_id: str,
        execution_id: str,
        ttl_seconds: int = 900,
    ) -> str:
        lease_token = str(uuid4())
        async with self._client() as client:
            await client.acquire_sandbox_lease(
                SandboxLeaseAcquirePayload(
                    workspace_id=workspace_id,
                    sandbox_environment_id=environment_id,
                    holder_job_id=job_id,
                    holder_execution_id=execution_id,
                    lease_token=lease_token,
                    ttl_seconds=ttl_seconds,
                )
            )
        return lease_token

    async def release_lease(self, *, workspace_id: str, lease_token: str) -> None:
        async with self._client() as client:
            await client.release_sandbox_lease(
                SandboxLeaseReleasePayload(
                    workspace_id=workspace_id,
                    lease_token=lease_token,
                )
            )
