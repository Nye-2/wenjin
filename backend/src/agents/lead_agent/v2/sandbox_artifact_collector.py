"""Output shaping for lead-agent sandbox runtime jobs."""

from __future__ import annotations

import json
from typing import Any

from src.agents.lead_agent.v2.sandbox_artifact_discovery import summarize_generated_artifacts
from src.sandbox.base import CommandResult
from src.sandbox.workspace_layout import WORKSPACE_DATASETS_MANIFEST_VIRTUAL_PATH


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
        command_audit: dict[str, Any],
        install_command_audits: list[dict[str, Any]],
        retry_count: int,
        script_path: str,
        stdout_preview: str | None = None,
        stderr_preview: str | None = None,
        stdout_ref: str | None = None,
        stderr_ref: str | None = None,
        generated_artifacts: list[dict[str, Any]] | None = None,
        dataset_provenance: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        raw_stdout = result.stdout.strip()
        raw_stderr = result.stderr.strip()
        parsed_stdout = self._parse_stdout_json(raw_stdout)
        stdout = stdout_preview if stdout_preview is not None else raw_stdout
        stderr = stderr_preview if stderr_preview is not None else raw_stderr
        output_refs = [ref for ref in (stdout_ref, stderr_ref) if ref]
        artifact_candidates = list(generated_artifacts or [])
        dataset_entries = _dataset_provenance_entries(dataset_provenance)
        reproducibility_section = build_reproducibility_report_section(
            script_path=script_path,
            dependency_hints=dependency_hints,
            installed_packages=installed_packages,
            install_job_ids=install_job_ids,
            retry_count=retry_count,
            command_audit=command_audit,
            install_command_audits=install_command_audits,
            generated_artifacts=artifact_candidates,
        )
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
            f"{reproducibility_section}"
            f"{summarize_dataset_provenance(dataset_entries)}"
            f"{summarize_generated_artifacts(artifact_candidates)}"
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
            "command_audit": command_audit,
            "install_command_audits": install_command_audits,
            "retry_count": retry_count,
            "script_path": script_path,
            "script_name": safe_name,
            "script_hash": script_hash,
            "generated_artifacts": artifact_candidates,
            "dataset_provenance": dataset_entries,
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


def build_reproducibility_report_section(
    *,
    script_path: str,
    dependency_hints: list[str],
    installed_packages: list[str],
    install_job_ids: list[str],
    retry_count: int,
    command_audit: dict[str, Any],
    install_command_audits: list[dict[str, Any]],
    generated_artifacts: list[dict[str, Any]],
) -> str:
    """Render bounded human-readable experiment reproducibility evidence."""

    run_verdict = _audit_pair(command_audit)
    install_risks = [_audit_pair(audit) for audit in install_command_audits if isinstance(audit, dict)]
    lines = [
        "\n\n## Reproducibility\n",
        f"- Script path: `{script_path}`",
        f"- Requested dependencies: {_inline_code_list(dependency_hints)}",
        f"- Installed dependencies: {_inline_code_list(installed_packages)}",
        f"- Install job ids: {_inline_code_list(install_job_ids)}",
        f"- Retry count: {max(0, int(retry_count or 0))}",
        f"- Run command audit: {run_verdict}",
    ]
    if install_risks:
        lines.append(f"- Install command audits: {', '.join(install_risks)}")
    if generated_artifacts:
        lines.append(
            "- Reviewable artifact paths: "
            f"{_inline_code_list([str(item.get('path') or '') for item in generated_artifacts])}"
        )
    return "\n".join(lines) + "\n"


def summarize_dataset_provenance(datasets: list[dict[str, Any]]) -> str:
    """Render bounded dataset provenance evidence for long-running experiments."""

    if not datasets:
        return ""
    lines = [
        "\n\n## Dataset provenance\n",
        f"- Manifest: `{WORKSPACE_DATASETS_MANIFEST_VIRTUAL_PATH}`",
    ]
    for item in datasets[:20]:
        path = str(item.get("path") or "").strip()
        if not path:
            continue
        title = str(item.get("title") or item.get("name") or "dataset").strip()
        source_id = str(item.get("source_id") or "").strip()
        hash_text = str(item.get("content_hash") or "").strip()
        suffix_parts = []
        if source_id:
            suffix_parts.append(f"source `{source_id}`")
        if hash_text:
            suffix_parts.append(f"hash `{hash_text}`")
        suffix = f" ({', '.join(suffix_parts)})" if suffix_parts else ""
        lines.append(f"- `{path}` - {title}{suffix}")
    return "\n".join(lines) + "\n"


def build_dependency_install_failure_report(
    *,
    packages: list[str],
    run_job_id: str,
    install_job_id: str,
    stdout: str,
    stderr: str,
    exit_code: int,
) -> str:
    """Render recovery guidance for dependency installation failures."""

    return (
        "# Sandbox dependency installation failed\n\n"
        "Dependency installation failed before the Python script could be retried.\n\n"
        "## Reproducibility\n\n"
        f"- Requested dependencies: {_inline_code_list(packages)}\n"
        f"- Run job id: `{run_job_id}`\n"
        f"- Install job ids: {_inline_code_list([install_job_id])}\n"
        f"- Exit code: {exit_code}\n\n"
        "## Recovery guidance\n\n"
        "- Check dependency_hints for a valid pinned package spec.\n"
        "- Prefer stable package versions already compatible with the workspace Python environment.\n"
        "- If the package requires system libraries, produce a pure-Python fallback or ask Lead Agent to revise the experiment plan.\n\n"
        "## stdout\n\n"
        "```text\n"
        f"{stdout}\n"
        "```\n\n"
        "## stderr\n\n"
        "```text\n"
        f"{stderr}\n"
        "```\n"
    )


def _inline_code_list(values: list[str]) -> str:
    clean = [str(value).strip() for value in values if str(value).strip()]
    if not clean:
        return "`none`"
    return ", ".join(f"`{value}`" for value in clean[:20])


def _dataset_provenance_entries(raw_entries: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not raw_entries:
        return []
    return [dict(item) for item in raw_entries if isinstance(item, dict)]


def _audit_pair(audit: dict[str, Any]) -> str:
    verdict = str(audit.get("verdict") or "unknown").strip() or "unknown"
    risk = str(audit.get("risk_level") or "unknown").strip() or "unknown"
    return f"{verdict} / {risk}"
