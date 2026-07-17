"""Unified orchestration for reviewable academic visual candidates."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from src.academic_visual_runtime.contracts import (
    AcademicVisualCandidate,
    AcademicVisualExecutionContext,
    AcademicVisualOperationIdentity,
    AcademicVisualReceipt,
    AcademicVisualRenderInput,
    CodeVisualPayload,
    FigureArtifactManifest,
    GenerativeVisualPayload,
    StructuredVisualPayload,
    VisualCandidateRef,
)
from src.academic_visual_runtime.image_provider import (
    AcademicImageProvider,
    ImageGenerationRequest,
    ImageProviderError,
)
from src.academic_visual_runtime.overlay import overlay_exact_labels, overlay_manifest_hash
from src.academic_visual_runtime.prompt_compiler import PROMPT_CONTRACT_VERSION, compile_image_prompt
from src.academic_visual_runtime.quality import RasterQualityError, inspect_raster
from src.academic_visual_runtime.router import InvalidFigureStrategyError, VisualRoute, route_visual
from src.sandbox import (
    SandboxMissionProvenance,
    SandboxNetworkProfile,
    SandboxOperationResult,
    SandboxOperationStatus,
)
from src.sandbox.contracts import RunPythonInput
from src.sandbox.security import (
    SandboxPathError,
    is_artifact_path,
    is_dataset_path,
    is_script_path,
)

RUNTIME_VERSION = "wenjin.academic_visual.runtime.v1"
RENDER_CONTRACT_VERSION = "wenjin.academic_visual.render.v1"
_CONTENT_HASH_PATTERN = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
_EMBEDDED_CONTENT_HASH_PATTERN = re.compile(r"sha256:([0-9a-f]{64})")
_MIME_BY_SUFFIX = {
    ".png": "image/png",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".pdf": "application/pdf",
}


class SandboxExecutionPort(Protocol):
    def build_request(self, **kwargs: Any) -> Any: ...

    async def execute(self, request: Any) -> SandboxOperationResult: ...

    async def read_artifact_bytes(
        self,
        *,
        workspace_id: str,
        object_ref: str,
        expected_content_hash: str,
        max_bytes: int,
    ) -> bytes: ...

    async def read_public_file_precondition_hash(
        self,
        *,
        workspace_id: str,
        path: str,
        max_bytes: int,
    ) -> str | None: ...


class PreviewWriteDescriptor(Protocol):
    ref: str
    content_hash: str
    size_bytes: int
    expires_at: datetime


class PreviewWriter(Protocol):
    async def put(
        self,
        *,
        workspace_id: str,
        content: bytes,
        mime_type: str,
        filename: str,
        metadata: dict[str, Any] | None = None,
    ) -> PreviewWriteDescriptor: ...


class AcademicVisualRuntimeError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        recoverable: bool = False,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.recoverable = recoverable
        self.retry_after_seconds = retry_after_seconds


class AcademicVisualRuntime:
    """Routes a FigureSpec to an existing execution boundary and emits one receipt."""

    def __init__(
        self,
        *,
        sandbox: SandboxExecutionPort,
        image_provider: AcademicImageProvider,
        preview_store: PreviewWriter,
    ) -> None:
        self.sandbox = sandbox
        self.image_provider = image_provider
        self.preview_store = preview_store

    async def render_candidate(
        self,
        request: AcademicVisualRenderInput,
        *,
        context: AcademicVisualExecutionContext,
    ) -> AcademicVisualReceipt:
        prism_ref = request.brief.prism_context_ref
        if prism_ref is None and context.prism_context_hash is not None:
            raise AcademicVisualRuntimeError(
                "reproducibility_manifest_invalid",
                "resolved Prism context requires a hash-bound Prism context ref",
            )
        if prism_ref is not None and (
            context.prism_context_text is None
            or context.prism_context_hash != prism_ref.selection_hash
        ):
            raise AcademicVisualRuntimeError(
                "reproducibility_manifest_invalid",
                "the resolved Prism context does not match the FigureSpec context ref",
            )
        try:
            route = route_visual(request)
        except InvalidFigureStrategyError as exc:
            raise AcademicVisualRuntimeError("invalid_figure_strategy", str(exc)) from exc
        if route.family in {"code", "structured"}:
            return await self._render_in_sandbox(request, context=context, route=route)
        if route.family in {"generative", "hybrid"}:
            return await self._render_generative(request, context=context, route=route)
        raise AcademicVisualRuntimeError("invalid_figure_strategy", "unsupported academic visual route")

    async def semantic_identity(
        self,
        request: AcademicVisualRenderInput,
        *,
        context: AcademicVisualExecutionContext,
        source_item_seq: int,
        contract_hashes: tuple[str, ...] = (),
        content_hash_refs: dict[str, str] | None = None,
        variant_ordinal: int = 0,
    ) -> AcademicVisualOperationIdentity:
        """Resolve the stable, server-owned identity used by ToolOrchestrator."""

        try:
            route = route_visual(request)
        except InvalidFigureStrategyError as exc:
            raise AcademicVisualRuntimeError("invalid_figure_strategy", str(exc)) from exc
        data_hashes = await self._dataset_content_hashes(
            context=context,
            paths=tuple(request.brief.figure_spec.dataset_paths),
        )
        known_hashes = {
            ref: _normalize_content_hash(content_hash)
            for ref, content_hash in (content_hash_refs or {}).items()
        }
        for path, content_hash in data_hashes.items():
            expected = known_hashes.get(path)
            if expected is not None and expected != content_hash:
                raise AcademicVisualRuntimeError(
                    "dataset_unavailable",
                    "visual data changed after its verified source receipt",
                )
        source_hashes = _source_content_hashes(request.brief.source_refs)
        source_hashes.update(
            {
                ref: known_hashes[ref]
                for ref in request.brief.source_refs
                if ref in known_hashes
            }
        )
        payload = request.render
        prompt_hash: str | None = None
        prompt_contract_version: str | None = None
        provider_model: str | None = None
        quality: str | None = None
        size: str | None = None
        overlay_hash: str | None = None
        if isinstance(payload, CodeVisualPayload):
            source_semantic_hash = _sha256_text(payload.source_code)
            renderer_version = payload.environment_id or RUNTIME_VERSION
        elif isinstance(payload, StructuredVisualPayload):
            source_semantic_hash = _sha256_text(payload.source)
            renderer_version = RUNTIME_VERSION
        elif isinstance(payload, GenerativeVisualPayload):
            _prompt, prompt_hash = compile_image_prompt(
                request.brief,
                prism_context=context.prism_context_text,
            )
            source_semantic_hash = prompt_hash
            renderer_version = PROMPT_CONTRACT_VERSION
            prompt_contract_version = PROMPT_CONTRACT_VERSION
            provider_model = "gpt-image-2"
            quality = payload.quality
            size = payload.size
            if route.family == "hybrid":
                overlay_hash = overlay_manifest_hash(request.brief.exact_labels)
        else:  # pragma: no cover - discriminated union exhaustiveness
            raise AcademicVisualRuntimeError(
                "invalid_figure_strategy",
                "academic visual render payload is unsupported",
            )
        context_hash = _context_hash(request, context.prism_context_hash)
        return AcademicVisualOperationIdentity(
            source_item_seq=source_item_seq,
            variant_ordinal=variant_ordinal,
            figure_id=request.brief.figure_spec.figure_id,
            brief_hash=_canonical_hash(
                request.brief.model_dump(mode="json", by_alias=True)
            ),
            context_hash=context_hash,
            render_contract_hash=_canonical_hash(
                {
                    "render_contract_version": RENDER_CONTRACT_VERSION,
                    "runtime_version": RUNTIME_VERSION,
                }
            ),
            contract_hashes=tuple(sorted(set(contract_hashes))),
            renderer_id=route.renderer_id,
            renderer_version=renderer_version,
            source_semantic_hash=source_semantic_hash,
            prompt_contract_version=prompt_contract_version,
            prompt_hash=prompt_hash,
            dataset_content_hashes=data_hashes,
            source_content_hashes=source_hashes,
            provider_model=provider_model,
            quality=quality,
            size=size,
            overlay_manifest_hash=overlay_hash,
        )

    async def _dataset_content_hashes(
        self,
        *,
        context: AcademicVisualExecutionContext,
        paths: tuple[str, ...],
    ) -> dict[str, str]:
        content_hashes: dict[str, str] = {}
        for path in paths:
            try:
                content_hash = await self.sandbox.read_public_file_precondition_hash(
                    workspace_id=context.workspace_id,
                    path=path,
                    max_bytes=50 * 1024 * 1024,
                )
            except SandboxPathError as exc:
                raise AcademicVisualRuntimeError(
                    "dataset_unavailable",
                    "academic visual data is unavailable or outside the workspace",
                ) from exc
            if content_hash is None:
                raise AcademicVisualRuntimeError(
                    "dataset_unavailable",
                    f"academic visual data has no verified content hash: {path}",
                )
            content_hashes[path] = _normalize_content_hash(content_hash)
        return content_hashes

    async def _render_in_sandbox(
        self,
        request: AcademicVisualRenderInput,
        *,
        context: AcademicVisualExecutionContext,
        route: VisualRoute,
    ) -> AcademicVisualReceipt:
        targets = tuple(request.brief.figure_spec.output_targets)
        if len(targets) != 1:
            raise AcademicVisualRuntimeError(
                "invalid_figure_strategy",
                "a visual candidate requires exactly one reviewable output target",
            )
        target = targets[0]
        payload = request.render
        if payload.kind == "code":
            script = payload.source_code
            script_path = payload.script_path
            if not is_script_path(script_path) or not script_path.endswith(".py"):
                raise AcademicVisualRuntimeError(
                    "invalid_figure_strategy",
                    "code visual script_path must be a .py file under /workspace/scripts",
                )
            data_input_paths = payload.dataset_paths
            if tuple(request.brief.figure_spec.dataset_paths) != data_input_paths:
                raise AcademicVisualRuntimeError(
                    "reproducibility_manifest_invalid",
                    "code payload dataset paths must exactly match FigureSpec dataset paths",
                )
            dataset_paths = tuple(
                path for path in data_input_paths if is_dataset_path(path)
            )
            artifact_input_paths = tuple(
                path for path in data_input_paths if is_artifact_path(path)
            )
            if len(dataset_paths) + len(artifact_input_paths) != len(data_input_paths):
                raise AcademicVisualRuntimeError(
                    "invalid_dataset_path",
                    "visual data inputs must live under datasets, outputs, or reports",
                )
            environment_id = payload.environment_id
            output_base_hashes: dict[str, str] = {}
        elif isinstance(payload, StructuredVisualPayload):
            script, script_path = _structured_renderer_script(
                strategy=request.brief.figure_spec.strategy,
                source=payload.source,
                output_format=payload.output_format,
                target=target,
            )
            dataset_paths = ()
            artifact_input_paths = ()
            environment_id = None
            output_base_hashes = {}
        else:
            raise AcademicVisualRuntimeError("invalid_figure_strategy", "sandbox route received the wrong payload")
        dataset_content_hashes = await self._dataset_content_hashes(
            context=context,
            paths=tuple(request.brief.figure_spec.dataset_paths),
        )
        source_content_hashes = _source_content_hashes(request.brief.source_refs)
        try:
            base_content_hash = await self.sandbox.read_public_file_precondition_hash(
                workspace_id=context.workspace_id,
                path=script_path,
                max_bytes=2_000_000,
            )
            target_base_hash = await self.sandbox.read_public_file_precondition_hash(
                workspace_id=context.workspace_id,
                path=target,
                max_bytes=50 * 1024 * 1024,
            )
        except SandboxPathError as exc:
            raise AcademicVisualRuntimeError(
                "sandbox_precondition_unavailable",
                "academic visual inputs could not satisfy read-before-write",
            ) from exc
        output_base_hashes = (
            {target: target_base_hash} if target_base_hash is not None else {}
        )
        operation_input = RunPythonInput(
            script=script,
            script_path=script_path,
            base_content_hash=base_content_hash,
            environment_id=environment_id,
            dataset_paths=dataset_paths,
            artifact_input_paths=artifact_input_paths,
            output_base_hashes=output_base_hashes,
        )
        try:
            sandbox_request = self.sandbox.build_request(
                provenance=SandboxMissionProvenance(
                    workspace_id=context.workspace_id,
                    mission_id=context.mission_id,
                    subagent_id=(
                        context.caller_id
                        if context.caller_kind == "subagent"
                        else None
                    ),
                    lease_epoch=context.lease_epoch,
                ),
                operation_input=operation_input,
                policy_version=context.policy_version,
                network_profile=SandboxNetworkProfile.NONE,
                network_grant=None,
            )
        except SandboxPathError as exc:
            raise AcademicVisualRuntimeError(
                "invalid_dataset_path",
                "visual data inputs are unavailable or outside the allowed workspace roots",
            ) from exc
        result = await self.sandbox.execute(sandbox_request)
        if result.status is not SandboxOperationStatus.SUCCEEDED:
            code, recoverable = _sandbox_failure(result.status)
            raise AcademicVisualRuntimeError(
                code,
                result.stderr_preview or "academic visual sandbox execution failed",
                recoverable=recoverable,
            )
        artifact = next((item for item in result.artifacts if item.path == target), None)
        if artifact is None:
            raise AcademicVisualRuntimeError("expected_output_missing", f"renderer did not produce {target}")
        if len(result.artifacts) != 1:
            raise AcademicVisualRuntimeError(
                "reproducibility_manifest_invalid",
                "one academic visual candidate must produce exactly one declared artifact",
            )
        mime_type = _mime_for_path(target)
        source_hash = _sha256_text(script)
        try:
            artifact_bytes = await self.sandbox.read_artifact_bytes(
                workspace_id=context.workspace_id,
                object_ref=artifact.object_ref,
                expected_content_hash=artifact.content_hash,
                max_bytes=50 * 1024 * 1024,
            )
        except (OSError, ValueError) as exc:
            raise AcademicVisualRuntimeError(
                "sandbox_artifact_unavailable",
                "sandbox visual bytes could not be verified",
            ) from exc
        try:
            raster_quality = (
                inspect_raster(
                    artifact_bytes,
                    expected_mime_type=mime_type,
                    minimum_dimension=32,
                )
                if mime_type in {"image/png", "image/webp"}
                else {}
            )
        except RasterQualityError as exc:
            raise AcademicVisualRuntimeError(
                "quality_gate_failed",
                "sandbox academic visual is invalid or visually empty",
            ) from exc
        try:
            stored = await self.preview_store.put(
                workspace_id=context.workspace_id,
                content=artifact_bytes,
                mime_type=mime_type,
                filename=Path(target).name,
                metadata={
                    "figure_id": request.brief.figure_spec.figure_id,
                    "strategy": request.brief.figure_spec.strategy,
                    "sandbox_operation_key": result.operation_key,
                    "sandbox_content_hash": artifact.content_hash,
                },
            )
        except (OSError, ValueError) as exc:
            raise AcademicVisualRuntimeError(
                "preview_store_unavailable",
                "sandbox visual could not be staged for review",
            ) from exc
        candidate_ref = VisualCandidateRef(
            kind="sandbox_artifact",
            ref=f"sandbox-artifact:{artifact.content_hash.removeprefix('sha256:')}",
            content_hash=artifact.content_hash,
        )
        manifest = _manifest(
            request,
            candidate_ref=candidate_ref,
            renderer_id=route.renderer_id,
            renderer_version=artifact.sandbox_environment_id,
            source_code_hash=source_hash,
            reproducibility_ref=f"sandbox-operation:{result.operation_key}",
            prism_context_hash=context.prism_context_hash,
            dataset_content_hashes=dataset_content_hashes,
            source_content_hashes=source_content_hashes,
        )
        candidate = _candidate(
            request,
            candidate_ref=candidate_ref,
            mime_type=mime_type,
            renderer_id=route.renderer_id,
            renderer_version=artifact.sandbox_environment_id,
            review_preview_ref=stored.ref,
            preview_hash=stored.content_hash,
            source_code_hash=source_hash,
            reproducibility_ref=f"sandbox-operation:{result.operation_key}",
            prism_context_hash=context.prism_context_hash,
            dataset_content_hashes=dataset_content_hashes,
            source_content_hashes=source_content_hashes,
            width=_optional_int(raster_quality.get("width")),
            height=_optional_int(raster_quality.get("height")),
            quality_receipt={
                "sandbox_operation_key": result.operation_key,
                "sandbox_job_id": result.sandbox_job_id,
                "size_bytes": artifact.size_bytes,
                "preview_size_bytes": stored.size_bytes,
                "preview_expires_at": stored.expires_at.isoformat(),
                "reused_receipt": result.reused_receipt,
                **raster_quality,
            },
        )
        return AcademicVisualReceipt(candidate=candidate, manifest=manifest)

    async def _render_generative(
        self,
        request: AcademicVisualRenderInput,
        *,
        context: AcademicVisualExecutionContext,
        route: VisualRoute,
    ) -> AcademicVisualReceipt:
        payload = request.render
        if not isinstance(payload, GenerativeVisualPayload):
            raise AcademicVisualRuntimeError("invalid_figure_strategy", "generative route received the wrong payload")
        prompt, prompt_hash = compile_image_prompt(
            request.brief,
            prism_context=context.prism_context_text,
        )
        dataset_content_hashes = await self._dataset_content_hashes(
            context=context,
            paths=tuple(request.brief.figure_spec.dataset_paths),
        )
        source_content_hashes = _source_content_hashes(request.brief.source_refs)
        overlay_hash = (
            overlay_manifest_hash(request.brief.exact_labels)
            if route.family == "hybrid"
            else None
        )
        try:
            generated = await self.image_provider.generate(
                ImageGenerationRequest(prompt=prompt, size=payload.size, quality=payload.quality)
            )
        except ImageProviderError as exc:
            raise AcademicVisualRuntimeError(
                exc.code,
                str(exc),
                recoverable=exc.code in {"provider_rate_limited", "provider_timeout", "provider_unavailable"},
                retry_after_seconds=exc.retry_after_seconds,
            ) from exc
        if generated.provider_model != "gpt-image-2":
            raise AcademicVisualRuntimeError("provider_invalid_payload", "image provider returned an unpinned model receipt")
        content = generated.content
        if route.family == "hybrid":
            try:
                content = overlay_exact_labels(content, request.brief.exact_labels)
            except (OSError, ValueError) as exc:
                raise AcademicVisualRuntimeError(
                    "quality_gate_failed",
                    "exact academic labels could not be rendered deterministically",
                ) from exc
        content_hash = hashlib.sha256(content).hexdigest()
        try:
            raster_quality = inspect_raster(
                content,
                expected_mime_type=generated.mime_type,
                minimum_dimension=256,
            )
        except RasterQualityError as exc:
            raise AcademicVisualRuntimeError(
                "quality_gate_failed",
                "generated academic visual is invalid or visually empty",
            ) from exc
        try:
            stored = await self.preview_store.put(
                workspace_id=context.workspace_id,
                content=content,
                mime_type=generated.mime_type,
                filename=f"{request.brief.figure_spec.figure_id}.png",
                metadata={
                    "figure_id": request.brief.figure_spec.figure_id,
                    "strategy": request.brief.figure_spec.strategy,
                    "provider_model": "gpt-image-2",
                    "content_hash_before_store": content_hash,
                },
            )
        except (OSError, ValueError) as exc:
            raise AcademicVisualRuntimeError("preview_store_unavailable", "generated visual could not be staged for review") from exc
        candidate_ref = VisualCandidateRef(
            kind="transient_preview",
            ref=stored.ref,
            content_hash=stored.content_hash,
        )
        manifest = _manifest(
            request,
            candidate_ref=candidate_ref,
            renderer_id=route.renderer_id,
            renderer_version=PROMPT_CONTRACT_VERSION,
            source_prompt_hash=prompt_hash,
            prompt_contract_version=PROMPT_CONTRACT_VERSION,
            prism_context_hash=context.prism_context_hash,
            dataset_content_hashes=dataset_content_hashes,
            source_content_hashes=source_content_hashes,
            overlay_manifest_hash=overlay_hash,
        )
        candidate = _candidate(
            request,
            candidate_ref=candidate_ref,
            mime_type=generated.mime_type,
            renderer_id=route.renderer_id,
            renderer_version=PROMPT_CONTRACT_VERSION,
            review_preview_ref=stored.ref,
            preview_hash=stored.content_hash,
            provider_model="gpt-image-2",
            source_prompt_hash=prompt_hash,
            prompt_contract_version=PROMPT_CONTRACT_VERSION,
            prism_context_hash=context.prism_context_hash,
            dataset_content_hashes=dataset_content_hashes,
            source_content_hashes=source_content_hashes,
            overlay_manifest_hash=overlay_hash,
            width=generated.width,
            height=generated.height,
            quality_receipt={
                "size_bytes": stored.size_bytes,
                "width": generated.width,
                "height": generated.height,
                "provider_request_id": generated.provider_request_id,
                "requested_quality": payload.quality,
                "requested_size": payload.size,
                "preview_expires_at": stored.expires_at.isoformat(),
                **raster_quality,
            },
            warnings=("AI-generated explanatory illustration; not empirical evidence.",),
        )
        return AcademicVisualReceipt(candidate=candidate, manifest=manifest)


def _manifest(
    request: AcademicVisualRenderInput,
    *,
    candidate_ref: VisualCandidateRef,
    renderer_id: str,
    renderer_version: str,
    source_code_hash: str | None = None,
    source_prompt_hash: str | None = None,
    prompt_contract_version: str | None = None,
    reproducibility_ref: str | None = None,
    prism_context_hash: str | None = None,
    dataset_content_hashes: dict[str, str] | None = None,
    source_content_hashes: dict[str, str] | None = None,
    overlay_manifest_hash: str | None = None,
) -> FigureArtifactManifest:
    spec = request.brief.figure_spec
    return FigureArtifactManifest(
        figure_id=spec.figure_id,
        figure_type=spec.figure_type,
        strategy=spec.strategy,
        evidence_level=spec.evidence_level,
        candidate=candidate_ref,
        intended_output_targets=tuple(spec.output_targets),
        renderer_id=renderer_id,
        renderer_version=renderer_version,
        source_code_ref=(f"sandbox-script:sha256:{source_code_hash}" if source_code_hash else None),
        source_code_hash=source_code_hash,
        prompt_contract_version=prompt_contract_version,
        source_prompt_hash=source_prompt_hash,
        context_hash=_context_hash(request, prism_context_hash),
        dataset_refs=tuple(spec.dataset_paths),
        source_refs=request.brief.source_refs,
        dataset_content_hashes=dataset_content_hashes or {},
        source_content_hashes=source_content_hashes or {},
        reproducibility_ref=reproducibility_ref,
        ai_generated=spec.strategy in {"llm_image", "hybrid"},
        overlay_manifest_hash=overlay_manifest_hash,
        caption=spec.caption,
        alt_text=spec.alt_text,
    )


def _candidate(
    request: AcademicVisualRenderInput,
    *,
    candidate_ref: VisualCandidateRef,
    mime_type: str,
    renderer_id: str,
    renderer_version: str,
    review_preview_ref: str,
    preview_hash: str,
    provider_model: str | None = None,
    source_code_hash: str | None = None,
    source_prompt_hash: str | None = None,
    prompt_contract_version: str | None = None,
    reproducibility_ref: str | None = None,
    prism_context_hash: str | None = None,
    dataset_content_hashes: dict[str, str] | None = None,
    source_content_hashes: dict[str, str] | None = None,
    overlay_manifest_hash: str | None = None,
    width: int | None = None,
    height: int | None = None,
    quality_receipt: dict[str, str | int | float | bool | None] | None = None,
    warnings: tuple[str, ...] = (),
) -> AcademicVisualCandidate:
    spec = request.brief.figure_spec
    context_hash = _context_hash(request, prism_context_hash)
    identity = _canonical_hash(
        {
            "runtime": RUNTIME_VERSION,
            "brief_hash": _canonical_hash(
                request.brief.model_dump(mode="json", by_alias=True)
            ),
            "context_hash": context_hash,
            "candidate_content_hash": candidate_ref.content_hash,
            "renderer_id": renderer_id,
            "renderer_version": renderer_version,
            "source_code_hash": source_code_hash,
            "source_prompt_hash": source_prompt_hash,
            "prompt_contract_version": prompt_contract_version,
            "dataset_content_hashes": dataset_content_hashes or {},
            "source_content_hashes": source_content_hashes or {},
            "provider_model": provider_model,
            "overlay_manifest_hash": overlay_manifest_hash,
        }
    )
    return AcademicVisualCandidate(
        candidate_id=f"avc_{identity}",
        figure_id=spec.figure_id,
        figure_type=spec.figure_type,
        strategy=spec.strategy,
        evidence_level=spec.evidence_level,
        preview_ref=(candidate_ref.ref if candidate_ref.kind == "transient_preview" else None),
        sandbox_artifact_ref=(candidate_ref.ref if candidate_ref.kind == "sandbox_artifact" else None),
        review_preview_ref=review_preview_ref,
        preview_hash=preview_hash,
        content_hash=candidate_ref.content_hash,
        mime_type=mime_type,
        width=width,
        height=height,
        renderer_id=renderer_id,
        renderer_version=renderer_version,
        provider_model=provider_model,
        prompt_contract_version=prompt_contract_version,
        source_code_hash=source_code_hash,
        source_prompt_hash=source_prompt_hash,
        context_hash=context_hash,
        source_refs=request.brief.source_refs,
        dataset_refs=tuple(spec.dataset_paths),
        source_content_hashes=source_content_hashes or {},
        dataset_content_hashes=dataset_content_hashes or {},
        reproducibility_ref=reproducibility_ref,
        ai_generated=spec.strategy in {"llm_image", "hybrid"},
        overlay_manifest_hash=overlay_manifest_hash,
        quality_receipt=quality_receipt or {},
        warnings=warnings,
    )


def _structured_renderer_script(*, strategy: str, source: str, output_format: str, target: str) -> tuple[str, str]:
    if Path(target).suffix.lower() != f".{output_format}":
        raise AcademicVisualRuntimeError("invalid_figure_strategy", "structured output format must match its target suffix")
    encoded = base64.b64encode(source.encode()).decode()
    if strategy == "graphviz":
        command = f"['dot', '-T{output_format}', str(source_path), '-o', str(output_path)]"
        source_suffix = ".dot"
    else:
        raise AcademicVisualRuntimeError("invalid_figure_strategy", "unsupported structured renderer")
    source_name = f"figure{source_suffix}"
    script = f"""import base64
import pathlib
import subprocess

scratch = pathlib.Path('/tmp/wenjin-academic-visual')
scratch.mkdir(parents=True, exist_ok=True)
source_path = scratch / {source_name!r}
output_path = pathlib.Path({target!r})
output_path.parent.mkdir(parents=True, exist_ok=True)
source_path.write_bytes(base64.b64decode({encoded!r}))
subprocess.run({command}, check=True, timeout=110)
if not output_path.is_file() or output_path.stat().st_size == 0:
    raise RuntimeError('structured renderer produced no output')
"""
    return script, "/workspace/scripts/academic_visual_structured.py"


def _mime_for_path(path: str) -> str:
    mime = _MIME_BY_SUFFIX.get(Path(path).suffix.lower())
    if mime is None:
        raise AcademicVisualRuntimeError("reproducibility_manifest_invalid", "visual output MIME is unsupported")
    return mime


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def _context_hash(
    request: AcademicVisualRenderInput,
    prism_context_hash: str | None,
) -> str:
    return _canonical_hash(
        {
            "brief": request.brief.model_dump(mode="json", by_alias=True),
            "prism_context_hash": prism_context_hash,
        }
    )


def _normalize_content_hash(value: str) -> str:
    normalized = value.strip().lower()
    if not _CONTENT_HASH_PATTERN.fullmatch(normalized):
        raise AcademicVisualRuntimeError(
            "reproducibility_manifest_invalid",
            "academic visual content hash is malformed",
        )
    return f"sha256:{normalized.removeprefix('sha256:')}"


def _source_content_hashes(source_refs: tuple[str, ...]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for source_ref in source_refs:
        match = _EMBEDDED_CONTENT_HASH_PATTERN.search(source_ref.lower())
        if match is not None:
            hashes[source_ref] = f"sha256:{match.group(1)}"
    return hashes


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _sandbox_failure(status: SandboxOperationStatus) -> tuple[str, bool]:
    if status is SandboxOperationStatus.FAILED:
        return "sandbox_execution_failed", True
    if status is SandboxOperationStatus.TIMED_OUT:
        return "sandbox_execution_timeout", True
    if status is SandboxOperationStatus.POLICY_DENIED:
        return "sandbox_policy_denied", False
    if status is SandboxOperationStatus.PERMISSION_REQUIRED:
        return "sandbox_permission_required", False
    if status is SandboxOperationStatus.RECONCILIATION_REQUIRED:
        return "sandbox_reconciliation_required", False
    return "sandbox_unavailable", False


__all__ = [
    "AcademicVisualRuntime",
    "AcademicVisualRuntimeError",
    "PreviewWriter",
    "RENDER_CONTRACT_VERSION",
    "RUNTIME_VERSION",
    "SandboxExecutionPort",
]
