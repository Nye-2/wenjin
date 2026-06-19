"""Harness tool boundary for research figure generation."""

from __future__ import annotations

import re
import tempfile
from contextlib import suppress
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from src.agents.lead_agent.v2.sandbox_artifact_discovery import DISCOVERY_SCHEMA
from src.agents.lead_agent.v2.sandbox_runtime_session import (
    SandboxRuntimeContext,
    SandboxRuntimeSession,
    ensure_runtime_workspace_layout,
)
from src.agents.lead_agent.v2.sandbox_script_executor import sanitize_script_name
from src.contracts.figure_generation import FigureArtifactManifest, FigureSpec
from src.execution.providers.ai_image import AIImageProvider
from src.sandbox.workspace_layout import (
    WORKSPACE_ROOT,
    is_user_reviewable_workspace_artifact_path,
    is_workspace_internal_path,
    is_workspace_protected_path,
    workspace_artifact_root_for_path,
)

from .contracts import HarnessPolicy, HarnessRunContext, HarnessToolResult
from .sandbox_execution_tools import SandboxExecutionTools

CODE_STRATEGIES = frozenset({"matplotlib", "seaborn", "plotly_static", "mermaid", "graphviz", "tikz"})
STRATEGY_DEPENDENCY_HINTS: dict[str, tuple[str, ...]] = {
    "mermaid": ("mermaid-cli",),
    "graphviz": ("graphviz",),
    "tikz": ("tectonic",),
}
SENSITIVE_METADATA_KEYS = frozenset(
    {
        "access_token",
        "api_key",
        "authorization",
        "credential",
        "credentials",
        "password",
        "private_key",
        "raw_secret",
        "refresh_token",
        "secret",
        "token",
    }
)
SENSITIVE_TEXT_PATTERNS = (
    re.compile(r"(?i)\bauthorization\s+(?:bearer\s+)?[^\s,;.]+"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)\bapi[-_\s]?key\s*[:=]?\s*[^\s,;.]+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]+"),
)


@dataclass(slots=True)
class FigureGenerationTools:
    """Generate reviewable figure artifacts through approved sandbox boundaries."""

    context: HarnessRunContext
    policy: HarnessPolicy
    image_adapter: Any | None = None

    async def generate_figure(
        self,
        *,
        spec: dict[str, Any],
        source_code: str | None = None,
        source_prompt: str | None = None,
        dependency_hints: list[str] | str | None = None,
    ) -> HarnessToolResult:
        self._require_generate_figure_permission()
        figure_spec = FigureSpec.model_validate(spec)

        if figure_spec.strategy in CODE_STRATEGIES:
            if not source_code:
                raise ValueError(f"{figure_spec.strategy} figure generation requires source_code")
            return await self._generate_code_figure(
                figure_spec=figure_spec,
                source_code=source_code,
                dependency_hints=dependency_hints,
            )

        generated_artifacts = await self._generate_llm_image(
            figure_spec=figure_spec,
            source_prompt=source_prompt,
            dependency_hints=dependency_hints,
        )
        artifacts = _figure_artifacts(generated_artifacts, figure_spec)
        _require_reviewable_figure_artifact(artifacts, figure_spec)
        return self._figure_result(
            figure_spec=figure_spec,
            figure_manifest=_figure_manifest(
                figure_spec=figure_spec,
                generated_artifacts=artifacts,
                source_prompt=source_prompt,
            ),
            generated_artifacts=artifacts,
            run_python_payload=None,
        )

    async def _generate_code_figure(
        self,
        *,
        figure_spec: FigureSpec,
        source_code: str,
        dependency_hints: list[str] | str | None,
    ) -> HarnessToolResult:
        script_name = _figure_script_name(figure_spec.figure_id)
        run_result = await SandboxExecutionTools(
            context=self.context,
            policy=self.policy,
        ).run_python(
            script=source_code,
            script_name=script_name,
            dependency_hints=_figure_dependency_hints(figure_spec.strategy, dependency_hints),
        )
        run_payload = _sanitize_metadata_value(dict(run_result.structured_payload))
        artifacts = _figure_artifacts(
            run_payload.get("generated_artifacts"),
            figure_spec,
            sandbox_job_id=_clean_optional_text(run_payload.get("sandbox_job_id")),
            sandbox_environment_id=_clean_optional_text(run_payload.get("sandbox_environment_id")),
        )
        _require_reviewable_figure_artifact(artifacts, figure_spec)
        run_payload["generated_artifacts"] = artifacts
        return self._figure_result(
            figure_spec=figure_spec,
            figure_manifest=_figure_manifest(
                figure_spec=figure_spec,
                generated_artifacts=artifacts,
                source_script=_source_script_path(run_payload, script_name),
            ),
            generated_artifacts=artifacts,
            run_python_payload=run_payload,
            output_refs=run_result.output_refs,
            truncated=run_result.truncated,
            externalized=run_result.externalized,
            error=run_result.error,
        )

    async def _generate_llm_image(
        self,
        *,
        figure_spec: FigureSpec,
        source_prompt: str | None,
        dependency_hints: list[str] | str | None,
    ) -> list[dict[str, Any]]:
        adapter = self.image_adapter or ServerSideAIImageFigureAdapter(context=self.context)
        result = await adapter.generate_figure(
            figure_spec=figure_spec,
            source_prompt=source_prompt,
            dependency_hints=dependency_hints,
        )
        if not isinstance(result, list):
            raise ValueError("LLM image adapter must return a list of artifact metadata")
        return [dict(item) for item in result if isinstance(item, dict)]

    def _figure_result(
        self,
        *,
        figure_spec: FigureSpec,
        figure_manifest: dict[str, Any],
        generated_artifacts: list[dict[str, Any]],
        run_python_payload: dict[str, Any] | None,
        output_refs: tuple[str, ...] = (),
        truncated: bool = False,
        externalized: bool = False,
        error: str | None = None,
    ) -> HarnessToolResult:
        payload = {
            "schema": "wenjin.harness.figure_generation.v1",
            "figure_spec": _sanitize_metadata_value(figure_spec.model_dump(mode="json", by_alias=True)),
            "figure_manifest": figure_manifest,
            "generated_artifacts": generated_artifacts,
        }
        if run_python_payload is not None:
            payload["run_python"] = run_python_payload
            for key in (
                "sandbox_job_id",
                "sandbox_environment_id",
                "execution_manifest",
                "reproducibility_manifest",
                "experiment_narrative",
                "command_audit",
                "install_command_audits",
            ):
                if key in run_python_payload:
                    payload[key] = run_python_payload[key]
        return HarnessToolResult(
            preview_text=f"Generated figure via {figure_spec.strategy}: {figure_spec.title}",
            structured_payload=payload,
            output_refs=output_refs,
            truncated=truncated,
            externalized=externalized,
            error=error,
        )

    def _require_generate_figure_permission(self) -> None:
        if "sandbox.generate_figure" not in self.policy.permissions:
            raise PermissionError("harness policy does not allow sandbox.generate_figure")


@dataclass(slots=True)
class ServerSideAIImageFigureAdapter:
    """Generate image figures server-side and materialize them into the workspace sandbox."""

    context: HarnessRunContext
    provider: AIImageProvider | None = None

    async def generate_figure(
        self,
        *,
        figure_spec: FigureSpec,
        source_prompt: str | None,
        dependency_hints: list[str] | str | None,
    ) -> list[dict[str, Any]]:
        prompt = str(source_prompt or figure_spec.purpose or "").strip()
        if not prompt:
            raise ValueError("LLM image figure generation requires source_prompt or purpose")
        target_path = _default_figure_output_target(figure_spec)
        job_context = await self._prepare_image_job(
            figure_spec=figure_spec,
            target_path=target_path,
            dependency_hints=dependency_hints,
        )
        try:
            with tempfile.TemporaryDirectory(prefix="wenjin-figure-") as tmpdir:
                result = await (self.provider or AIImageProvider()).execute(
                    content=prompt,
                    work_dir=tmpdir,
                    options={
                        "figure_id": figure_spec.figure_id,
                        "output_filename": figure_spec.figure_id,
                        "dependency_hints": _dependency_hint_list(dependency_hints),
                    },
                )
                if not result.success:
                    detail = _redact_sensitive_text(result.error_message) or "provider_error"
                    raise RuntimeError(f"AI image generation failed: {detail}")
                image_path = _provider_output_path(tmpdir, result.output_files)
                image_bytes = image_path.read_bytes()
            await self._write_workspace_bytes(
                target_path,
                image_bytes,
                runtime_context=job_context.runtime_context,
            )
            await job_context.mark_completed(metadata={"target_path": target_path})
        except Exception as exc:
            await job_context.mark_failed(str(exc) or type(exc).__name__)
            raise
        artifact = {
            "schema": DISCOVERY_SCHEMA,
            "path": target_path,
            "root": _artifact_root_name(target_path),
            "title": figure_spec.title,
            "artifact_kind": "figure",
            "mime_type": "image/png",
            "size": len(image_bytes),
            "size_bytes": len(image_bytes),
            "content_hash": f"sha256:{sha256(image_bytes).hexdigest()}",
            "sandbox_job_id": job_context.sandbox_job_id,
            "sandbox_environment_id": job_context.sandbox_environment_id,
            "review_surface": "sandbox_artifact",
            "materialization_status": "candidate",
        }
        artifact.update(_safe_provider_metadata(result.metadata))
        return [artifact]

    async def _prepare_image_job(
        self,
        *,
        figure_spec: FigureSpec,
        target_path: str,
        dependency_hints: list[str] | str | None,
    ) -> _ImageGenerationJob:
        bundled = self.context.context_bundle.get("_harness_sandbox_job")
        if isinstance(bundled, dict):
            job_id = _clean_optional_text(bundled.get("sandbox_job_id"))
            environment_id = _clean_optional_text(bundled.get("sandbox_environment_id"))
            if job_id and environment_id:
                return _ImageGenerationJob(
                    sandbox_job_id=job_id,
                    sandbox_environment_id=environment_id,
                )
        sandbox_policy = dict(self.context.capability_policy.get("sandbox_policy") or {})
        runtime_ctx = await SandboxRuntimeSession().build_context(
            workspace_id=self.context.workspace_id,
            workspace_type=self.context.workspace_type,
            sandbox_policy=sandbox_policy,
        )
        job = await runtime_ctx.manager.create_job(
            workspace_id=self.context.workspace_id,
            environment_id=str(runtime_ctx.environment.id),
            execution_id=self.context.execution_id,
            node_id=self.context.node_id,
            operation="generate_figure",
            billable=False,
            command="server_side_ai_image",
            runtime_image=runtime_ctx.runtime_image,
            sandbox_policy=sandbox_policy,
            resource_limits=dict(runtime_ctx.limits or {}),
            metadata={
                "tool": "sandbox.generate_figure",
                "strategy": figure_spec.strategy,
                "figure_id": figure_spec.figure_id,
                "target_path": target_path,
                "dependency_hints": _dependency_hint_list(dependency_hints),
            },
            network_policy="none",
        )
        await runtime_ctx.manager.update_job(str(job.id), status="running")
        return _ImageGenerationJob(
            sandbox_job_id=str(job.id),
            sandbox_environment_id=str(runtime_ctx.environment.id),
            runtime_context=runtime_ctx,
            manager=runtime_ctx.manager,
        )

    async def _write_workspace_bytes(
        self,
        target_path: str,
        content: bytes,
        *,
        runtime_context: SandboxRuntimeContext | None = None,
    ) -> None:
        sandbox = self.context.context_bundle.get("_harness_sandbox")
        release = None
        if sandbox is None:
            runtime_ctx = runtime_context
            if runtime_ctx is None:
                session = SandboxRuntimeSession()
                runtime_ctx = await session.build_context(
                    workspace_id=self.context.workspace_id,
                    workspace_type=self.context.workspace_type,
                    sandbox_policy=dict(self.context.capability_policy.get("sandbox_policy") or {}),
                )
            sandbox = await runtime_ctx.provider.acquire(runtime_ctx.sandbox_key)
            release = runtime_ctx.provider.release
            ensure_runtime_workspace_layout(
                sandbox=sandbox,
                workspace_id=self.context.workspace_id,
                sandbox_id=runtime_ctx.sandbox_key,
                workspace_type=runtime_ctx.workspace_type,
            )
        try:
            _write_bytes_via_sandbox_resolver(sandbox, target_path, content)
        finally:
            if release is not None:
                with suppress(Exception):
                    await release(sandbox)


@dataclass(slots=True)
class _ImageGenerationJob:
    sandbox_job_id: str
    sandbox_environment_id: str
    runtime_context: SandboxRuntimeContext | None = None
    manager: Any | None = None

    async def mark_completed(self, *, metadata: dict[str, Any]) -> None:
        if self.manager is not None:
            await self.manager.update_job(
                self.sandbox_job_id,
                status="completed",
                exit_code=0,
                metadata=metadata,
            )

    async def mark_failed(self, error_text: str) -> None:
        if self.manager is not None:
            await self.manager.update_job(
                self.sandbox_job_id,
                status="failed",
                exit_code=1,
                error_text=_redact_sensitive_text(error_text),
            )


def _figure_script_name(figure_id: str) -> str:
    return sanitize_script_name(f"{figure_id}_figure.py")


def _default_figure_output_target(figure_spec: FigureSpec) -> str:
    target = (
        figure_spec.output_targets[0]
        if figure_spec.output_targets
        else f"/workspace/outputs/figures/{_safe_figure_id_path_segment(figure_spec.figure_id)}/figure.png"
    )
    return _validated_figure_primary_path(figure_spec, target)


def _safe_figure_id_path_segment(figure_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", figure_id).strip(".-") or "figure"


def _validated_figure_primary_path(figure_spec: FigureSpec, target_path: str) -> str:
    manifest = FigureArtifactManifest(
        figure_id=figure_spec.figure_id,
        figure_type=figure_spec.figure_type,
        strategy=figure_spec.strategy,
        primary_path=target_path,
    )
    return str(manifest.model_dump(mode="json", by_alias=True)["primary_path"])


def _figure_dependency_hints(strategy: str, dependency_hints: list[str] | str | None) -> list[str] | None:
    values = _dependency_hint_list(dependency_hints)
    seen = set(values)
    for hint in STRATEGY_DEPENDENCY_HINTS.get(strategy, ()):
        if hint not in seen:
            values.append(hint)
            seen.add(hint)
    return values or None


def _dependency_hint_list(dependency_hints: list[str] | str | None) -> list[str]:
    if isinstance(dependency_hints, str):
        raw_values = [dependency_hints]
    elif isinstance(dependency_hints, list | tuple | set | frozenset):
        raw_values = list(dependency_hints)
    else:
        raw_values = []
    values: list[str] = []
    seen: set[str] = set()
    for value in raw_values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        values.append(text)
        seen.add(text)
    return values


def _source_script_path(run_payload: dict[str, Any], script_name: str) -> str:
    execution_manifest = run_payload.get("execution_manifest")
    if isinstance(execution_manifest, dict):
        script_path = str(execution_manifest.get("script_path") or "").strip()
        if script_path:
            return script_path
    return f"/workspace/scripts/{script_name}"


def _figure_manifest(
    *,
    figure_spec: FigureSpec,
    generated_artifacts: list[dict[str, Any]],
    source_script: str | None = None,
    source_prompt: str | None = None,
) -> dict[str, Any]:
    primary_path = _primary_path(figure_spec, generated_artifacts)
    manifest = FigureArtifactManifest(
        figure_id=figure_spec.figure_id,
        figure_type=figure_spec.figure_type,
        strategy=figure_spec.strategy,
        primary_path=primary_path,
        source_script=source_script,
        source_prompt=_source_prompt_reference(source_prompt),
        dataset_paths=figure_spec.dataset_paths,
    )
    return manifest.model_dump(mode="json", by_alias=True)


def _source_prompt_reference(source_prompt: str | None) -> str | None:
    if source_prompt is None:
        return None
    return f"redacted:sha256:{sha256(source_prompt.encode('utf-8')).hexdigest()}"


def _primary_path(figure_spec: FigureSpec, generated_artifacts: list[dict[str, Any]]) -> str:
    for artifact in generated_artifacts:
        path = str(artifact.get("path") or "").strip()
        if path:
            return path
    if figure_spec.output_targets:
        return figure_spec.output_targets[0]
    raise ValueError("figure generation requires at least one output target or generated artifact")


def _figure_artifacts(
    raw_artifacts: Any,
    figure_spec: FigureSpec,
    *,
    sandbox_job_id: str | None = None,
    sandbox_environment_id: str | None = None,
) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    raw_list = raw_artifacts if isinstance(raw_artifacts, list) else []
    target_paths = set(figure_spec.output_targets)
    for raw_artifact in raw_list:
        if not isinstance(raw_artifact, dict):
            continue
        artifact = _without_sensitive_metadata(raw_artifact)
        path = str(artifact.get("path") or "").strip()
        if not path:
            continue
        if _is_figure_artifact_path(path, target_paths):
            artifact["artifact_kind"] = "figure"
            artifact.setdefault("schema", DISCOVERY_SCHEMA)
            artifact.setdefault("review_surface", "sandbox_artifact")
            artifact.setdefault("materialization_status", "candidate")
        if sandbox_job_id and not artifact.get("sandbox_job_id"):
            artifact["sandbox_job_id"] = sandbox_job_id
        if sandbox_environment_id and not artifact.get("sandbox_environment_id"):
            artifact["sandbox_environment_id"] = sandbox_environment_id
        artifacts.append(artifact)
    return artifacts


def _require_reviewable_figure_artifact(artifacts: list[dict[str, Any]], figure_spec: FigureSpec) -> None:
    target_paths = set(figure_spec.output_targets)
    for artifact in artifacts:
        path = str(artifact.get("path") or "").strip()
        if (
            path
            and artifact.get("artifact_kind") == "figure"
            and _is_figure_artifact_path(path, target_paths)
            and is_user_reviewable_workspace_artifact_path(path)
            and str(artifact.get("sandbox_job_id") or "").strip()
            and artifact.get("schema") == DISCOVERY_SCHEMA
            and artifact.get("review_surface") == "sandbox_artifact"
            and artifact.get("materialization_status") == "candidate"
        ):
            return
    raise RuntimeError("figure generation did not produce a reviewable figure artifact")


def _is_figure_artifact_path(path: str, target_paths: set[str]) -> bool:
    return path in target_paths or path.startswith("/workspace/outputs/figures/")


def _artifact_root_name(path: str) -> str:
    root = workspace_artifact_root_for_path(path)
    return str(root.get("name") or "outputs") if root else "outputs"


def _clean_optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _provider_output_path(work_dir: str, output_files: list[str]) -> Path:
    if not output_files:
        raise RuntimeError("AI image provider did not return an output file")
    root = Path(work_dir).resolve()
    path = (root / str(output_files[0])).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise RuntimeError("AI image provider output escaped work directory") from exc
    if not path.is_file():
        raise RuntimeError("AI image provider output file is missing")
    return path


def _write_bytes_via_sandbox_resolver(sandbox: Any, target_path: str, content: bytes) -> None:
    target_path = _validate_reviewable_figure_artifact_path(target_path)
    resolver = getattr(sandbox, "_resolve_path", None)
    if not callable(resolver):
        raise RuntimeError("workspace sandbox does not expose a safe path resolver")
    workspace_root = Path(resolver(WORKSPACE_ROOT)).resolve()
    raw_physical_target = Path(resolver(target_path))
    if raw_physical_target.exists() and raw_physical_target.is_symlink():
        raise RuntimeError("figure output target resolves through a symlink")
    physical_target = raw_physical_target.resolve()
    try:
        physical_target.relative_to(workspace_root)
    except ValueError as exc:
        raise RuntimeError("figure output target resolves outside workspace") from exc
    reversed_target = _reverse_sandbox_path(sandbox, physical_target)
    if reversed_target and (
        is_workspace_protected_path(reversed_target) or is_workspace_internal_path(reversed_target)
    ):
        raise RuntimeError("figure output target resolves to protected or internal workspace path")
    if not is_user_reviewable_workspace_artifact_path(reversed_target):
        raise RuntimeError("figure output target does not resolve to a reviewable artifact path")
    physical_target.parent.mkdir(parents=True, exist_ok=True)
    physical_target.write_bytes(content)


def _validate_reviewable_figure_artifact_path(target_path: str) -> str:
    manifest = FigureArtifactManifest(
        figure_id="materialized_figure",
        figure_type="other",
        strategy="llm_image",
        primary_path=target_path,
    )
    return str(manifest.model_dump(mode="json", by_alias=True)["primary_path"])


def _reverse_sandbox_path(sandbox: Any, physical_target: Path) -> str:
    reverser = getattr(sandbox, "_reverse_resolve_path", None)
    if not callable(reverser):
        raise RuntimeError("workspace sandbox does not expose a safe reverse path resolver")
    try:
        return str(reverser(str(physical_target))).strip()
    except Exception as exc:
        raise RuntimeError("workspace sandbox reverse path resolution failed") from exc


def _safe_provider_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    allowed_keys = {"provider", "model_id", "model", "size", "format", "quality"}
    if not isinstance(metadata, dict):
        return {}
    return {
        key: _sanitize_metadata_value(value)
        for key, value in metadata.items()
        if isinstance(key, str) and key in allowed_keys
    }


def _without_sensitive_metadata(raw: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in raw.items():
        key_text = str(key)
        if _is_sensitive_key(key_text):
            continue
        clean[key_text] = _sanitize_metadata_value(value)
    return clean


def _sanitize_metadata_value(value: Any) -> Any:
    if isinstance(value, dict):
        return _without_sensitive_metadata(value)
    if isinstance(value, list):
        return [_sanitize_metadata_value(item) for item in value]
    if isinstance(value, str):
        return _redact_sensitive_text(value)
    return value


def _redact_sensitive_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = value
    for pattern in SENSITIVE_TEXT_PATTERNS:
        text = pattern.sub("[redacted]", text)
    return text


def _is_sensitive_key(key: str) -> bool:
    normalized = _normalize_metadata_key(key)
    return normalized in SENSITIVE_METADATA_KEYS or any(part in normalized for part in SENSITIVE_METADATA_KEYS)


def _normalize_metadata_key(key: str) -> str:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(key or ""))
    text = re.sub(r"[^A-Za-z0-9]+", "_", text)
    return text.strip("_").lower()
