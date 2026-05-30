"""Lead-agent owned sandbox execution helpers.

Only the right-side LeadAgentRuntime/subagent path should import this module.
The left chat agent may launch capabilities, but must not acquire or execute a
sandbox directly.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from src.sandbox.providers.docker import DockerSandboxProvider

_SMOKE_COMMAND = (
    "python -c \"import json, platform, statistics; "
    "data=[2,4,6,8]; "
    "print(json.dumps({'ok': True, 'mean': statistics.mean(data), "
    "'python': platform.python_version(), 'engine': 'lead_agent_docker_sandbox'}, "
    "ensure_ascii=False, sort_keys=True))\""
)
_SCRIPT_NAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")
_MAX_SCRIPT_BYTES = 128 * 1024


class SandboxCommandExecutionError(RuntimeError):
    """Raised when user code ran in sandbox but exited unsuccessfully."""

    def __init__(self, message: str, *, output: dict[str, Any]) -> None:
        super().__init__(message)
        self.output = output


def _default_base_dir() -> str:
    configured = os.getenv("WENJIN_AGENT_SANDBOX_BASE_DIR")
    if configured:
        return configured

    latex_dir = os.getenv("WENJIN_LATEX_DATA_DIR")
    if latex_dir:
        return str(Path(latex_dir).expanduser().resolve().parent / "agent_sandboxes")

    return str((Path.cwd() / ".wenjin" / "agent_sandboxes").resolve())


def _default_image() -> str:
    return os.getenv(
        "WENJIN_AGENT_SANDBOX_IMAGE",
        "docker.m.daocloud.io/library/python:3.13-slim",
    )


def _resource_limits(policy: Mapping[str, Any]) -> Mapping[str, Any]:
    limits = policy.get("resource_limits")
    return limits if isinstance(limits, Mapping) else {}


def _sandbox_key(*, execution_id: str, node_id: str) -> str:
    raw = f"{execution_id}-{node_id}".strip("-") or "lead-sandbox"
    return re.sub(r"[^A-Za-z0-9_.-]", "-", raw)[:120]


def require_run_python_allowed(policy: Mapping[str, Any]) -> None:
    """Raise when the capability policy does not allow Python sandbox execution."""
    mode = str(policy.get("mode") or "none")
    allowed = {str(item) for item in policy.get("allowed_operations") or []}
    if mode not in {"required", "optional", "conditional"} or "run_python" not in allowed:
        raise PermissionError("capability sandbox_policy does not allow run_python")


def _provider_from_policy(policy: Mapping[str, Any]) -> DockerSandboxProvider:
    limits = _resource_limits(policy)
    memory_mb = int(limits.get("memory_mb") or os.getenv("WENJIN_AGENT_SANDBOX_MEMORY_MB") or 512)
    cpu_limit = int(limits.get("cpu") or os.getenv("WENJIN_AGENT_SANDBOX_CPU") or 1)
    timeout_seconds = int(limits.get("timeout_seconds") or 120)
    return DockerSandboxProvider(
        base_dir=_default_base_dir(),
        image=_default_image(),
        timeout=timeout_seconds,
        memory=f"{memory_mb}m",
        cpu_limit=cpu_limit,
    )


async def run_python_smoke_check(
    *,
    workspace_id: str,
    execution_id: str,
    node_id: str,
    sandbox_policy: Mapping[str, Any],
    provider: DockerSandboxProvider | None = None,
) -> dict[str, Any]:
    """Run the controlled Python smoke calculation in a Docker sandbox."""

    require_run_python_allowed(sandbox_policy)
    limits = _resource_limits(sandbox_policy)
    timeout_seconds = int(limits.get("timeout_seconds") or 120)
    sandbox_timeout = max(1, min(timeout_seconds, 120))
    resolved_provider = provider or _provider_from_policy(sandbox_policy)
    sandbox = await resolved_provider.acquire(
        _sandbox_key(execution_id=execution_id, node_id=node_id)
    )

    try:
        result = await sandbox.execute_command(_SMOKE_COMMAND, timeout=sandbox_timeout)
    finally:
        await resolved_provider.release(sandbox)

    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    parsed: dict[str, Any] = {}
    if stdout:
        try:
            loaded = json.loads(stdout)
            parsed = loaded if isinstance(loaded, dict) else {}
        except json.JSONDecodeError:
            parsed = {}

    mean = parsed.get("mean")
    python_version = parsed.get("python")
    report_markdown = (
        "# 内部实验环境自检\n\n"
        "- 执行位置：LeadAgentRuntime / subagent node\n"
        "- 隔离方式：Docker sandbox\n"
        f"- Workspace：{workspace_id}\n"
        f"- Execution：{execution_id}\n"
        f"- Node：{node_id}\n"
        f"- Python：{python_version}\n"
        f"- 固定计算 mean([2,4,6,8])：{mean}\n"
        f"- Docker image：{getattr(resolved_provider, 'image', None)}\n"
    )
    output = {
        "status": "completed",
        "operation": "smoke_check",
        "mean": mean,
        "python": python_version,
        "engine": parsed.get("engine"),
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": result.exit_code,
        "docker_image": getattr(resolved_provider, "image", None),
        "report_markdown": report_markdown,
    }
    if not result.success:
        output["status"] = "failed"
        raise SandboxCommandExecutionError(
            "Docker sandbox Python smoke check failed "
            f"(exit_code={result.exit_code}, stderr={stderr or 'none'})",
            output=output,
        )

    return output


async def run_python_script(
    *,
    workspace_id: str,
    execution_id: str,
    node_id: str,
    sandbox_policy: Mapping[str, Any],
    script: str,
    script_name: str = "analysis.py",
    provider: DockerSandboxProvider | None = None,
) -> dict[str, Any]:
    """Run a capability-declared Python script in the Docker sandbox."""

    require_run_python_allowed(sandbox_policy)
    if not isinstance(script, str) or not script.strip():
        raise ValueError("sandbox_python python_script requires a non-empty script")
    script_bytes = script.encode("utf-8")
    if len(script_bytes) > _MAX_SCRIPT_BYTES:
        raise ValueError("sandbox_python script exceeds 128 KiB limit")

    safe_name = _safe_script_name(script_name)
    script_path = f"/mnt/user-data/workspace/{safe_name}"
    script_hash = hashlib.sha256(script_bytes).hexdigest()
    limits = _resource_limits(sandbox_policy)
    timeout_seconds = int(limits.get("timeout_seconds") or 120)
    sandbox_timeout = max(1, min(timeout_seconds, 120))
    resolved_provider = provider or _provider_from_policy(sandbox_policy)
    sandbox = await resolved_provider.acquire(
        _sandbox_key(execution_id=execution_id, node_id=node_id)
    )

    try:
        await sandbox.write_file(script_path, script)
        command = f"python {script_path}"
        result = await sandbox.execute_command(command, timeout=sandbox_timeout)
    finally:
        await resolved_provider.release(sandbox)

    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    parsed_stdout: dict[str, Any] = {}
    if stdout:
        try:
            loaded = json.loads(stdout)
            parsed_stdout = loaded if isinstance(loaded, dict) else {}
        except json.JSONDecodeError:
            parsed_stdout = {}

    report_markdown = (
        "# Sandbox Python 执行报告\n\n"
        "- 执行位置：LeadAgentRuntime / subagent node\n"
        "- 隔离方式：Docker sandbox\n"
        f"- Workspace：{workspace_id}\n"
        f"- Execution：{execution_id}\n"
        f"- Node：{node_id}\n"
        f"- Script：{safe_name}\n"
        f"- Script SHA256：`{script_hash}`\n"
        f"- Docker image：{getattr(resolved_provider, 'image', None)}\n"
        f"- Exit code：{result.exit_code}\n\n"
        "## stdout\n\n"
        "```text\n"
        f"{stdout}\n"
        "```\n\n"
        "## stderr\n\n"
        "```text\n"
        f"{stderr}\n"
        "```\n"
    )
    output = {
        "status": "completed",
        "operation": "python_script",
        "stdout": stdout,
        "stderr": stderr,
        "parsed_stdout": parsed_stdout,
        "exit_code": result.exit_code,
        "docker_image": getattr(resolved_provider, "image", None),
        "script_path": script_path,
        "script_name": safe_name,
        "script_hash": script_hash,
        "report_markdown": report_markdown,
    }
    if not result.success:
        output["status"] = "failed"
        raise SandboxCommandExecutionError(
            "Docker sandbox Python script failed "
            f"(exit_code={result.exit_code}, stderr={stderr or 'none'})",
            output=output,
        )

    return output


def _safe_script_name(value: str) -> str:
    name = _SCRIPT_NAME_RE.sub("_", str(value or "").strip())
    if not name or name in {".", ".."}:
        name = "analysis.py"
    if not name.endswith(".py"):
        name = f"{name}.py"
    return name[:80]
