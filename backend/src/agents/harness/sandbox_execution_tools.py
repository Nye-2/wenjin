"""Execution tools backed by the existing Lead Agent sandbox runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.agents.lead_agent.v2.sandbox_errors import SandboxCommandExecutionError
from src.agents.lead_agent.v2.sandbox_job_runner import SandboxJobRunner
from src.agents.lead_agent.v2.sandbox_script_executor import sanitize_script_name
from src.sandbox.workspace_layout import (
    build_dataset_provenance_manifest,
    is_workspace_internal_path,
    is_workspace_protected_path,
    merge_dataset_provenance_manifest,
)

from .contracts import HarnessPolicy, HarnessRunContext, HarnessToolResult
from .events import publish_harness_event
from .scheduler import WorkspaceToolScheduler, default_workspace_tool_scheduler


@dataclass(slots=True)
class SandboxExecutionTools:
    """Python execution wrapper for harness tools."""

    context: HarnessRunContext
    policy: HarnessPolicy
    runner: Any | None = None
    scheduler: WorkspaceToolScheduler = default_workspace_tool_scheduler

    async def run_python(
        self,
        *,
        script: str,
        script_name: str = "analysis.py",
        dependency_hints: list[str] | str | None = None,
        billing_reservation_id: str | None = None,
    ) -> HarnessToolResult:
        if "sandbox.run_python" not in self.policy.permissions:
            raise PermissionError("harness policy does not allow sandbox.run_python")

        safe_script_name = sanitize_script_name(script_name)
        runner = self.runner or SandboxJobRunner()

        async def _run() -> dict[str, Any]:
            return await runner.run_python_script(
                workspace_id=self.context.workspace_id,
                execution_id=self.context.execution_id,
                node_id=self.context.node_id,
                sandbox_policy=self._sandbox_policy(),
                script=script,
                script_name=safe_script_name,
                dependency_hints=dependency_hints,
                dataset_provenance=_dataset_provenance_from_context(self.context),
                billing_reservation_id=billing_reservation_id,
            )

        timeout_seconds = min(self.policy.max_sandbox_seconds, 30)
        try:
            payload = await self.scheduler.run(
                self.context.workspace_id,
                _run,
                timeout_seconds=timeout_seconds,
            )
        except SandboxCommandExecutionError as exc:
            payload = dict(exc.output)
            payload.setdefault("status", "failed")
            payload["failure_classification"] = _classify_run_python_failure(payload)
            payload["error_code"] = payload["failure_classification"]["failure_code"]
            _ensure_failure_recovery_guidance(payload)
        payload["execution_manifest"] = _execution_manifest(
            context=self.context,
            sandbox_policy=self._sandbox_policy(),
            script_name=safe_script_name,
            dependency_hints=dependency_hints,
            payload=payload,
            timeout_seconds=timeout_seconds,
        )
        payload["reproducibility_manifest"] = _reproducibility_manifest(
            context=self.context,
            execution_manifest=payload["execution_manifest"],
            payload=payload,
        )
        await self._publish_command_audit_events(payload)
        status = str(payload.get("status") or "completed")
        failure_classification = payload.get("failure_classification")
        error = _failure_error(failure_classification)
        preview = f"Python execution {status}"
        if error:
            preview = f"{preview}: {error}"
        parsed = payload.get("parsed_stdout")
        if parsed:
            preview = f"{preview}: {str(parsed)[:500]}"
        elif payload.get("stdout") and not error:
            preview = f"{preview}: {str(payload['stdout'])[:500]}"
        output_refs = tuple(str(ref) for ref in payload.get("output_refs") or () if str(ref).strip())
        externalized = bool(output_refs or payload.get("stdout_externalized") or payload.get("stderr_externalized"))
        return HarnessToolResult(
            preview_text=preview,
            structured_payload=dict(payload),
            output_refs=output_refs,
            truncated=externalized,
            externalized=externalized,
            error=error,
        )

    async def _publish_command_audit_events(self, payload: dict[str, Any]) -> None:
        sandbox_job_id = str(payload.get("sandbox_job_id") or "").strip()
        command_audit = payload.get("command_audit")
        if isinstance(command_audit, dict):
            await publish_harness_event(
                self.context,
                "command_audit",
                visibility="team_visible",
                sequence_kind="audit",
                payload={
                    "name": "sandbox.run_python",
                    "sandbox_job_id": sandbox_job_id,
                    "command_audit": dict(command_audit),
                },
            )
        install_job_ids = [str(item) for item in payload.get("install_job_ids") or [] if str(item).strip()]
        install_audits = payload.get("install_command_audits")
        if not isinstance(install_audits, list):
            return
        for index, raw_audit in enumerate(install_audits):
            if not isinstance(raw_audit, dict):
                continue
            await publish_harness_event(
                self.context,
                "command_audit",
                visibility="team_visible",
                sequence_kind="audit",
                payload={
                    "name": "sandbox.install_dependencies",
                    "sandbox_job_id": install_job_ids[index] if index < len(install_job_ids) else "",
                    "run_sandbox_job_id": sandbox_job_id,
                    "command_audit": dict(raw_audit),
                },
            )

    def _sandbox_policy(self) -> dict[str, Any]:
        raw = self.context.capability_policy.get("sandbox_policy")
        policy = dict(raw) if isinstance(raw, dict) else {}
        if self.policy.allow_package_install:
            policy["allow_package_install"] = True
        policy.setdefault("allowed_operations", ["run_python"])
        return policy


def _execution_manifest(
    *,
    context: HarnessRunContext,
    sandbox_policy: dict[str, Any],
    script_name: str,
    dependency_hints: list[str] | str | None,
    payload: dict[str, Any],
    timeout_seconds: int,
) -> dict[str, Any]:
    return {
        "schema": "wenjin.harness.run_python.execution_manifest.v1",
        "tool": "sandbox.run_python",
        "workspace_id": context.workspace_id,
        "execution_id": context.execution_id,
        "node_id": context.node_id,
        "invocation_id": context.invocation_id,
        "script_name": str(payload.get("script_name") or script_name),
        "script_path": str(payload.get("script_path") or f"/workspace/scripts/{script_name}"),
        "dependency_hints": _dependency_hints(payload.get("dependency_hints", dependency_hints)),
        "sandbox_job_id": str(payload.get("sandbox_job_id") or ""),
        "sandbox_environment_id": str(payload.get("sandbox_environment_id") or ""),
        "network_profile": str(sandbox_policy.get("network_profile") or "none"),
        "timeout_seconds": timeout_seconds,
    }


def _dataset_provenance_from_context(context: HarnessRunContext) -> list[dict[str, Any]] | None:
    workspace_summary = context.context_bundle.get("workspace_file_summary")
    if not isinstance(workspace_summary, dict):
        return None
    dataset_provenance = workspace_summary.get("dataset_provenance")
    if not isinstance(dataset_provenance, list):
        return None
    return [dict(item) for item in dataset_provenance if isinstance(item, dict)]


def _reproducibility_manifest(
    *,
    context: HarnessRunContext,
    execution_manifest: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    manifest = {
        "schema": "wenjin.harness.run_python.reproducibility_manifest.v1",
        "tool": "sandbox.run_python",
        "workspace_id": context.workspace_id,
        "execution_id": context.execution_id,
        "node_id": context.node_id,
        "invocation_id": context.invocation_id,
        "script": {
            "name": str(execution_manifest.get("script_name") or ""),
            "path": _workspace_path(execution_manifest.get("script_path")),
        },
        "sandbox": {
            "environment_id": str(execution_manifest.get("sandbox_environment_id") or ""),
            "run_job_id": str(execution_manifest.get("sandbox_job_id") or ""),
            "install_job_ids": _string_list(payload.get("install_job_ids"), limit=20),
            "network_profile": str(execution_manifest.get("network_profile") or "none"),
            "timeout_seconds": _positive_int(execution_manifest.get("timeout_seconds")),
            "retry_count": _nonnegative_int(payload.get("retry_count")),
        },
        "dependencies": {
            "requested": _dependency_hints(execution_manifest.get("dependency_hints")),
            "installed": _dependency_hints(payload.get("installed_packages")),
        },
        "artifacts": _artifact_manifest(payload.get("generated_artifacts")),
        "command_audit": _command_audit_manifest(
            payload.get("command_audit"),
            payload.get("install_command_audits"),
        ),
    }
    datasets = _dataset_provenance_manifest(payload.get("dataset_provenance"))
    if datasets:
        manifest["datasets"] = datasets
    return manifest


def _classify_run_python_failure(payload: dict[str, Any]) -> dict[str, Any]:
    exit_code = _int_or_none(payload.get("exit_code"))
    stderr = str(payload.get("stderr") or "").strip()
    if exit_code is not None and exit_code != 0:
        return {
            "schema": "wenjin.harness.run_python.failure_classification.v1",
            "category": "user_code",
            "reason": "nonzero_exit",
            "failure_code": "python_exit_nonzero",
            "exit_code": exit_code,
            "stderr_preview": _compact_text(stderr),
            "recoverable": True,
        }
    return {
        "schema": "wenjin.harness.run_python.failure_classification.v1",
        "category": "sandbox_runtime",
        "reason": "runner_exception",
        "failure_code": "sandbox_job_failed",
        "exit_code": exit_code,
        "stderr_preview": _compact_text(stderr),
        "recoverable": False,
    }


def _failure_error(raw: Any) -> str | None:
    if not isinstance(raw, dict):
        return None
    failure_code = str(raw.get("failure_code") or "sandbox_job_failed").strip()
    exit_code = raw.get("exit_code")
    if isinstance(exit_code, int):
        return f"{failure_code}: exit_code={exit_code}"
    return failure_code


def _ensure_failure_recovery_guidance(payload: dict[str, Any]) -> None:
    classification = payload.get("failure_classification")
    if not isinstance(classification, dict) or not classification.get("recoverable"):
        return
    guidance = _failure_recovery_guidance(classification)
    report = str(payload.get("report_markdown") or "").strip()
    if "Recovery guidance" in report:
        return
    payload["report_markdown"] = f"{report}\n\n{guidance}" if report else guidance


def _failure_recovery_guidance(classification: dict[str, Any]) -> str:
    failure_code = str(classification.get("failure_code") or "sandbox_job_failed")
    exit_code = classification.get("exit_code")
    exit_text = f" exit code `{exit_code}`" if isinstance(exit_code, int) else ""
    return (
        "## Recovery guidance\n\n"
        f"- Failure code: `{failure_code}`{exit_text}.\n"
        "- Revise the Python script in the same workspace sandbox and retry once before escalating.\n"
        "- Reuse existing `/workspace/datasets`, `/workspace/scripts`, `/workspace/outputs`, and `/workspace/reports` context instead of recreating the experiment from scratch.\n"
        "- If the error is caused by a missing dependency, add a precise `dependency_hints` package spec and rerun through `sandbox.run_python`.\n"
    )


def _dataset_provenance_manifest(raw_entries: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_entries, list):
        return []
    manifest = merge_dataset_provenance_manifest(
        build_dataset_provenance_manifest(),
        [dict(item) for item in raw_entries if isinstance(item, dict)],
    )
    return [
        dict(item)
        for item in manifest.get("datasets") or []
        if isinstance(item, dict)
    ][:20]


def _dependency_hints(raw: Any) -> list[str]:
    if isinstance(raw, str):
        values = [raw]
    elif isinstance(raw, list | tuple | set):
        values = list(raw)
    else:
        values = []
    return [str(item).strip() for item in values if str(item).strip()][:50]


def _string_list(raw: Any, *, limit: int) -> list[str]:
    if isinstance(raw, str):
        values = [raw]
    elif isinstance(raw, list | tuple | set):
        values = list(raw)
    else:
        values = []
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def _artifact_manifest(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    artifacts: list[dict[str, Any]] = []
    for item in raw:
        if len(artifacts) >= 20:
            break
        if not isinstance(item, dict):
            continue
        path = _workspace_path(item.get("path"))
        if not path:
            continue
        artifact: dict[str, Any] = {"path": path}
        for key in (
            "name",
            "kind",
            "artifact_kind",
            "root",
            "title",
            "mime_type",
            "content_hash",
            "review_surface",
            "materialization_status",
        ):
            value = _safe_text(item.get(key), limit=120)
            if value:
                artifact[key] = value
        size = _positive_int(item.get("size"))
        if size:
            artifact["size"] = size
        size_bytes = _positive_int(item.get("size_bytes"))
        if size_bytes:
            artifact["size_bytes"] = size_bytes
        artifacts.append(artifact)
    return artifacts


def _command_audit_manifest(raw_run_audit: Any, raw_install_audits: Any) -> dict[str, Any]:
    run_audit = raw_run_audit if isinstance(raw_run_audit, dict) else {}
    install_audits = raw_install_audits if isinstance(raw_install_audits, list) else []
    install_dicts = [audit for audit in install_audits if isinstance(audit, dict)]
    return {
        "run_verdict": _safe_text(run_audit.get("verdict"), limit=80),
        "run_risk_level": _safe_text(run_audit.get("risk_level"), limit=80),
        "install_verdicts": [_safe_text(audit.get("verdict"), limit=80) for audit in install_dicts[:20]],
        "install_risk_levels": [_safe_text(audit.get("risk_level"), limit=80) for audit in install_dicts[:20]],
    }


def _workspace_path(raw: Any) -> str:
    path = str(raw or "").strip()
    if not path.startswith("/workspace/"):
        return ""
    if is_workspace_internal_path(path) or is_workspace_protected_path(path):
        return ""
    return path


def _safe_text(raw: Any, *, limit: int) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    return text if len(text) <= limit else f"{text[: limit - 3]}..."


def _positive_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value if value > 0 else 0
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return parsed if parsed > 0 else 0


def _nonnegative_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value if value >= 0 else 0
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return parsed if parsed >= 0 else 0


def _compact_text(text: str) -> str:
    value = str(text or "").strip()
    return value if len(value) <= 500 else f"{value[:497]}..."


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
