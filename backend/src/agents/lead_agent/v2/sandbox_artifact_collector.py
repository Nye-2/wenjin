"""Output shaping for lead-agent sandbox runtime jobs."""

from __future__ import annotations

import json
from typing import Any

from src.sandbox.base import CommandResult


class SandboxArtifactCollector:
    """Build stable sandbox result payloads consumed by subagents."""

    def smoke_output(
        self,
        *,
        result: CommandResult,
        workspace_id: str,
        execution_id: str,
        node_id: str,
        runtime_image: str,
        provider_image: str | None,
        environment_id: str,
        job_id: str,
    ) -> dict[str, Any]:
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        parsed = self._parse_stdout_json(stdout)
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
            f"- Docker image：{provider_image}\n"
        )
        return {
            "status": "completed",
            "operation": "smoke_check",
            "mean": mean,
            "python": python_version,
            "engine": parsed.get("engine"),
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": result.exit_code,
            "docker_image": runtime_image,
            "sandbox_environment_id": environment_id,
            "sandbox_job_id": job_id,
            "report_markdown": report_markdown,
        }

    def script_output(
        self,
        *,
        result: CommandResult,
        workspace_id: str,
        execution_id: str,
        node_id: str,
        safe_name: str,
        script_hash: str,
        runtime_image: str,
        provider_image: str | None,
        environment_id: str,
        job_id: str,
        dependency_hints: list[str],
        installed_packages: list[str],
        install_job_ids: list[str],
        retry_count: int,
        script_path: str,
        stdout_preview: str | None = None,
        stderr_preview: str | None = None,
        stdout_ref: str | None = None,
        stderr_ref: str | None = None,
    ) -> dict[str, Any]:
        raw_stdout = result.stdout.strip()
        raw_stderr = result.stderr.strip()
        parsed_stdout = self._parse_stdout_json(raw_stdout)
        stdout = stdout_preview if stdout_preview is not None else raw_stdout
        stderr = stderr_preview if stderr_preview is not None else raw_stderr
        output_refs = [ref for ref in (stdout_ref, stderr_ref) if ref]
        report_markdown = (
            "# Sandbox Python 执行报告\n\n"
            "- 执行位置：LeadAgentRuntime / subagent node\n"
            "- 隔离方式：Docker sandbox\n"
            f"- Workspace：{workspace_id}\n"
            f"- Execution：{execution_id}\n"
            f"- Node：{node_id}\n"
            f"- Script：{safe_name}\n"
            f"- Script SHA256：`{script_hash}`\n"
            f"- Docker image：{provider_image}\n"
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
        return {
            "status": "completed",
            "operation": "python_script",
            "stdout": stdout,
            "stderr": stderr,
            "parsed_stdout": parsed_stdout,
            "exit_code": result.exit_code,
            "docker_image": runtime_image,
            "sandbox_environment_id": environment_id,
            "sandbox_job_id": job_id,
            "stdout_externalized": stdout_ref is not None,
            "stderr_externalized": stderr_ref is not None,
            "stdout_ref": stdout_ref,
            "stderr_ref": stderr_ref,
            "output_refs": output_refs,
            "dependency_hints": dependency_hints,
            "installed_packages": installed_packages,
            "install_job_ids": install_job_ids,
            "retry_count": retry_count,
            "script_path": script_path,
            "script_name": safe_name,
            "script_hash": script_hash,
            "report_markdown": report_markdown,
        }

    @staticmethod
    def _parse_stdout_json(stdout: str) -> dict[str, Any]:
        if not stdout:
            return {}
        try:
            loaded = json.loads(stdout)
        except json.JSONDecodeError:
            return {}
        return loaded if isinstance(loaded, dict) else {}
