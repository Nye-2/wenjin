from __future__ import annotations

import base64
import hashlib
import struct
import zlib
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest

from src.academic_visual_runtime import (
    AcademicFigureBrief,
    AcademicVisualExecutionContext,
    AcademicVisualRenderInput,
    AcademicVisualRuntime,
    AcademicVisualRuntimeError,
    CodeVisualPayload,
    GenerativeVisualPayload,
    StructuredVisualPayload,
)
from src.academic_visual_runtime.image_provider import (
    ImageGenerationRequest,
    ImageGenerationResult,
    OpenAIImagesProvider,
)
from src.academic_visual_runtime.quality import RasterQualityError, inspect_raster
from src.contracts.figure_generation import ExactVisualLabel, FigureSpec
from src.contracts.prism_context import PrismContextRef
from src.review_commit_runtime.preview_store import MissionPreviewStore
from src.sandbox import SandboxOperationStatus, SandboxRetryDisposition


def _brief(spec: FigureSpec) -> AcademicFigureBrief:
    return AcademicFigureBrief(
        figure_spec=spec,
        intended_use="manuscript",
        audience="computer science researchers",
        target_language="English",
        aspect_ratio="16:9",
        composition="A restrained left-to-right academic composition.",
        scientific_invariants=("Client data remains local.",),
        source_refs=("source:paper-1",),
    )


def _context() -> AcademicVisualExecutionContext:
    return AcademicVisualExecutionContext(
        workspace_id="workspace-1",
        mission_id="mission-1",
        caller_id="workspace-agent",
        caller_kind="workspace_agent",
        lease_epoch=2,
        policy_version="policy@hash",
    )


class _Sandbox:
    def __init__(self, target: str) -> None:
        self.target = target
        self.request = None
        self.precondition_hashes: dict[str, str] = {}

    def build_request(self, **kwargs):
        self.request = SimpleNamespace(**kwargs, operation_key="sbxop_" + "1" * 64)
        return self.request

    async def execute(self, request):
        now = datetime.now(UTC)
        artifact = SimpleNamespace(
            path=self.target,
            object_ref="sbxobj_" + "b" * 64,
            content_hash="sha256:" + "b" * 64,
            sandbox_environment_id="sandbox-env-1",
            size_bytes=2048,
        )
        return SimpleNamespace(
            status=SandboxOperationStatus.SUCCEEDED,
            retry_disposition=SandboxRetryDisposition.REUSE_RECEIPT,
            stderr_preview="",
            artifacts=(artifact,),
            operation_key=request.operation_key,
            sandbox_job_id="job-1",
            reused_receipt=False,
            started_at=now,
            finished_at=now,
        )

    async def read_artifact_bytes(
        self,
        *,
        workspace_id: str,
        object_ref: str,
        expected_content_hash: str,
        max_bytes: int,
    ) -> bytes:
        assert workspace_id == "workspace-1"
        assert object_ref == "sbxobj_" + "b" * 64
        assert expected_content_hash == "sha256:" + "b" * 64
        assert max_bytes > 0
        if self.target.endswith(".png"):
            return _png(64, 64, include_text=False, varied=True)
        return b"sandbox-visual"

    async def read_public_file_precondition_hash(
        self,
        *,
        workspace_id: str,
        path: str,
        max_bytes: int,
    ) -> str | None:
        assert workspace_id == "workspace-1"
        assert max_bytes > 0
        if path in self.precondition_hashes:
            return self.precondition_hashes[path]
        if path.startswith("/workspace/datasets/"):
            return "sha256:" + hashlib.sha256(path.encode()).hexdigest()
        return None


class _UnusedProvider:
    async def generate(self, _request):
        raise AssertionError("image provider must not be called")


class _PreviewStore:
    def __init__(self) -> None:
        self.content = b""

    async def put(self, *, workspace_id, content, mime_type, filename, metadata=None):
        self.content = content
        assert workspace_id == "workspace-1"
        assert mime_type in {"image/png", "image/svg+xml", "application/pdf"}
        assert filename
        content_hash = hashlib.sha256(content).hexdigest()
        return SimpleNamespace(
            ref=f"mpv1_{'x' * 32}",
            content_hash=content_hash,
            size_bytes=len(content),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )


@pytest.mark.asyncio
async def test_code_visual_reuses_sandbox_runtime_and_emits_candidate_first_manifest() -> None:
    target = "/workspace/outputs/result.png"
    sandbox = _Sandbox(target)
    runtime = AcademicVisualRuntime(
        sandbox=sandbox,
        image_provider=_UnusedProvider(),
        preview_store=_PreviewStore(),
    )
    spec = FigureSpec(
        figure_id="result-figure",
        title="Ablation result",
        figure_type="experiment_plot",
        strategy="matplotlib",
        evidence_level="evidence",
        purpose="Plot verified ablation values.",
        output_targets=[target],
        dataset_paths=["/workspace/datasets/ablation.csv"],
    )
    request = AcademicVisualRenderInput(
        brief=_brief(spec),
        render=CodeVisualPayload(
            source_code="from pathlib import Path\nPath('/workspace/outputs/result.png').write_bytes(b'png')",
            script_path="/workspace/scripts/academic_visual.py",
            dataset_paths=("/workspace/datasets/ablation.csv",),
        ),
    )

    receipt = await runtime.render_candidate(request, context=_context())
    candidate = receipt.candidate

    assert sandbox.request.operation_input.kind.value == "run_python"
    assert sandbox.request.provenance.mission_id == "mission-1"
    assert candidate.sandbox_artifact_ref
    assert receipt.manifest.candidate.ref == candidate.sandbox_artifact_ref
    assert receipt.manifest.schema_ == "wenjin.figure_generation.artifact.v2"
    assert candidate.reproducibility_ref == "sandbox-operation:sbxop_" + "1" * 64
    assert candidate.source_code_hash
    assert candidate.ai_generated is False
    assert candidate.dataset_content_hashes == {
        "/workspace/datasets/ablation.csv": "sha256:"
        + hashlib.sha256(b"/workspace/datasets/ablation.csv").hexdigest()
    }
    assert receipt.manifest.dataset_content_hashes == candidate.dataset_content_hashes


@pytest.mark.asyncio
async def test_code_visual_hash_binds_verified_derived_artifact_inputs() -> None:
    target = "/workspace/outputs/figures/q3_policy_summary.png"
    derived_data = "/workspace/outputs/q3_plot_data.csv"
    sandbox = _Sandbox(target)
    runtime = AcademicVisualRuntime(
        sandbox=sandbox,
        image_provider=_UnusedProvider(),
        preview_store=_PreviewStore(),
    )
    spec = FigureSpec(
        figure_id="q3-policy-summary",
        title="Policy comparison",
        figure_type="statistical_chart",
        strategy="matplotlib",
        evidence_level="evidence",
        purpose="Plot verified policy results.",
        output_targets=[target],
        dataset_paths=[derived_data],
    )
    request = AcademicVisualRenderInput(
        brief=_brief(spec),
        render=CodeVisualPayload(
            source_code="print('render')",
            script_path="/workspace/scripts/q3_policy_summary.py",
            dataset_paths=(derived_data,),
        ),
    )
    sandbox.precondition_hashes[derived_data] = "sha256:" + "4" * 64

    receipt = await runtime.render_candidate(request, context=_context())

    assert sandbox.request.operation_input.dataset_paths == ()
    assert sandbox.request.operation_input.artifact_input_paths == (derived_data,)
    assert receipt.candidate.dataset_refs == (derived_data,)
    assert receipt.candidate.dataset_content_hashes[derived_data] == (
        "sha256:" + "4" * 64
    )


@pytest.mark.asyncio
async def test_code_visual_reads_script_and_target_preconditions_before_replacement() -> None:
    target = "/workspace/outputs/result.png"
    script_path = "/workspace/scripts/academic_visual.py"
    script_hash = "sha256:" + "1" * 64
    target_hash = "sha256:" + "2" * 64
    sandbox = _Sandbox(target)
    sandbox.precondition_hashes = {
        script_path: script_hash,
        target: target_hash,
    }
    runtime = AcademicVisualRuntime(
        sandbox=sandbox,
        image_provider=_UnusedProvider(),
        preview_store=_PreviewStore(),
    )
    spec = FigureSpec(
        figure_id="result-figure",
        title="Result",
        figure_type="data_plot",
        strategy="matplotlib",
        evidence_level="evidence",
        purpose="Plot source data.",
        output_targets=[target],
    )

    await runtime.render_candidate(
        AcademicVisualRenderInput(
            brief=_brief(spec),
            render=CodeVisualPayload(
                source_code="print('render')",
                script_path=script_path,
            ),
        ),
        context=_context(),
    )

    operation_input = sandbox.request.operation_input
    assert operation_input.base_content_hash == script_hash
    assert operation_input.output_base_hashes == {target: target_hash}


@pytest.mark.asyncio
async def test_code_visual_exposes_bounded_script_failure_for_model_repair() -> None:
    target = "/workspace/outputs/result.png"

    class _FailingSandbox(_Sandbox):
        async def execute(self, request):
            return SimpleNamespace(
                status=SandboxOperationStatus.FAILED,
                retry_disposition=SandboxRetryDisposition.DO_NOT_RETRY,
                stderr_preview="AssertionError: Unexpected columns",
                artifacts=(),
                operation_key=request.operation_key,
            )

    runtime = AcademicVisualRuntime(
        sandbox=_FailingSandbox(target),
        image_provider=_UnusedProvider(),
        preview_store=_PreviewStore(),
    )
    spec = FigureSpec(
        figure_id="result-figure",
        title="Result",
        figure_type="data_plot",
        strategy="matplotlib",
        evidence_level="evidence",
        purpose="Plot source data.",
        output_targets=[target],
    )
    request = AcademicVisualRenderInput(
        brief=_brief(spec),
        render=CodeVisualPayload(
            source_code="raise AssertionError('Unexpected columns')",
            script_path="/workspace/scripts/academic_visual.py",
        ),
    )

    with pytest.raises(AcademicVisualRuntimeError, match="Unexpected columns") as error:
        await runtime.render_candidate(request, context=_context())

    assert error.value.code == "sandbox_execution_failed"
    assert error.value.recoverable is True


@pytest.mark.asyncio
async def test_code_visual_rejects_dataset_provenance_drift_before_sandbox() -> None:
    target = "/workspace/outputs/result.png"
    sandbox = _Sandbox(target)
    runtime = AcademicVisualRuntime(
        sandbox=sandbox,
        image_provider=_UnusedProvider(),
        preview_store=_PreviewStore(),
    )
    spec = FigureSpec(
        figure_id="result-figure",
        title="Result",
        figure_type="data_plot",
        strategy="matplotlib",
        evidence_level="evidence",
        purpose="Plot source data.",
        output_targets=[target],
        dataset_paths=["/workspace/datasets/source.csv"],
    )
    request = AcademicVisualRenderInput(
        brief=_brief(spec),
        render=CodeVisualPayload(
            source_code="print('render')",
            script_path="/workspace/scripts/academic_visual.py",
            dataset_paths=("/workspace/datasets/different.csv",),
        ),
    )

    with pytest.raises(AcademicVisualRuntimeError, match="exactly match") as error:
        await runtime.render_candidate(request, context=_context())

    assert error.value.code == "reproducibility_manifest_invalid"
    assert sandbox.request is None


@pytest.mark.asyncio
async def test_code_visual_rejects_non_script_path_before_sandbox() -> None:
    target = "/workspace/outputs/result.png"
    sandbox = _Sandbox(target)
    runtime = AcademicVisualRuntime(
        sandbox=sandbox,
        image_provider=_UnusedProvider(),
        preview_store=_PreviewStore(),
    )
    spec = FigureSpec(
        figure_id="result-figure",
        title="Result",
        figure_type="data_plot",
        strategy="matplotlib",
        evidence_level="evidence",
        purpose="Plot source data.",
        output_targets=[target],
    )
    request = AcademicVisualRenderInput(
        brief=_brief(spec),
        render=CodeVisualPayload(
            source_code="print('render')",
            script_path="/workspace/outputs/not-a-script.py",
        ),
    )

    with pytest.raises(AcademicVisualRuntimeError, match="under /workspace/scripts"):
        await runtime.render_candidate(request, context=_context())

    assert sandbox.request is None


@pytest.mark.asyncio
async def test_code_visual_reports_blank_sandbox_output_as_quality_failure() -> None:
    target = "/workspace/outputs/result.png"

    class _BlankSandbox(_Sandbox):
        async def read_artifact_bytes(self, **_kwargs) -> bytes:
            return _png(64, 64, include_text=False)

    runtime = AcademicVisualRuntime(
        sandbox=_BlankSandbox(target),
        image_provider=_UnusedProvider(),
        preview_store=_PreviewStore(),
    )
    spec = FigureSpec(
        figure_id="blank-result",
        title="Blank result",
        figure_type="data_plot",
        strategy="matplotlib",
        evidence_level="evidence",
        purpose="Reject an empty chart before review.",
        output_targets=[target],
    )
    request = AcademicVisualRenderInput(
        brief=_brief(spec),
        render=CodeVisualPayload(
            source_code="print('render')",
            script_path="/workspace/scripts/academic_visual.py",
        ),
    )

    with pytest.raises(AcademicVisualRuntimeError, match="visually empty") as error:
        await runtime.render_candidate(request, context=_context())

    assert error.value.code == "quality_gate_failed"


@pytest.mark.asyncio
async def test_structured_visual_compiles_fixed_graphviz_adapter_into_same_sandbox() -> None:
    target = "/workspace/outputs/method.svg"
    sandbox = _Sandbox(target)
    runtime = AcademicVisualRuntime(
        sandbox=sandbox,
        image_provider=_UnusedProvider(),
        preview_store=_PreviewStore(),
    )
    spec = FigureSpec(
        figure_id="method-flow",
        title="Method flow",
        figure_type="method_flow",
        strategy="graphviz",
        evidence_level="explanatory",
        purpose="Show the exact method topology.",
        output_targets=[target],
    )

    receipt = await runtime.render_candidate(
        AcademicVisualRenderInput(
            brief=_brief(spec),
            render=StructuredVisualPayload(
                source="digraph G { client -> server; }",
                output_format="svg",
            ),
        ),
        context=_context(),
    )

    script = sandbox.request.operation_input.script
    assert "['dot', '-Tsvg'" in script
    assert "shell=True" not in script
    assert receipt.candidate.renderer_id == "graphviz"
    assert receipt.candidate.mime_type == "image/svg+xml"


@pytest.mark.asyncio
async def test_generative_visual_uses_provider_and_canonical_transient_preview(tmp_path) -> None:
    png = _png(320, 320, include_text=True, varied=True)
    prism_context = "aggregate low-rank updates under client heterogeneity"
    prism_context_hash = f"sha256:{hashlib.sha256(prism_context.encode()).hexdigest()}"

    class _Provider:
        async def generate(self, request):
            assert "never evidence" in request.prompt
            assert "aggregate low-rank updates" in request.prompt
            assert request.size == "1536x1024"
            return ImageGenerationResult(
                content=png,
                mime_type="image/png",
                width=320,
                height=320,
                provider_model="gpt-image-2",
                provider_request_id="request-1",
            )

    preview = MissionPreviewStore(tmp_path / "previews", default_ttl_seconds=3600, max_bytes=1024 * 1024)
    runtime = AcademicVisualRuntime(
        sandbox=_Sandbox("unused"),
        image_provider=_Provider(),
        preview_store=preview,
    )
    spec = FigureSpec(
        figure_id="mechanism",
        title="Federated learning mechanism",
        figure_type="mechanism_illustration",
        strategy="llm_image",
        evidence_level="explanatory",
        purpose="Explain the privacy-preserving training topology.",
    )

    brief = _brief(spec).model_copy(
        update={
            "prism_context_ref": PrismContextRef(
                workspace_id="workspace-1",
                prism_project_id="project-1",
                file_id="file-1",
                base_revision_ref="revision-1",
                selection_hash=prism_context_hash,
                selection_byte_range=(0, len(prism_context.encode("utf-8"))),
            )
        }
    )
    receipt = await runtime.render_candidate(
        AcademicVisualRenderInput(brief=brief, render=GenerativeVisualPayload(size="1536x1024")),
        context=_context().model_copy(
            update={
                "prism_context_text": prism_context,
                "prism_context_hash": prism_context_hash,
            }
        ),
    )
    candidate = receipt.candidate

    assert candidate.provider_model == "gpt-image-2"
    assert candidate.ai_generated is True
    assert candidate.prompt_contract_version
    assert candidate.preview_ref
    assert candidate.source_prompt_hash
    assert candidate.warnings
    stored = await preview.read(candidate.preview_ref, workspace_id="workspace-1")
    assert stored.descriptor.content_hash == candidate.content_hash
    assert b"tEXt" not in stored.content


@pytest.mark.asyncio
async def test_hybrid_visual_overlays_exact_labels_into_review_preview(tmp_path) -> None:
    png = _png(320, 320, include_text=False, varied=True)

    class _Provider:
        async def generate(self, _request):
            return ImageGenerationResult(
                content=png,
                mime_type="image/png",
                width=320,
                height=320,
                provider_model="gpt-image-2",
                provider_request_id="request-hybrid",
            )

    preview = MissionPreviewStore(tmp_path / "previews", default_ttl_seconds=3600, max_bytes=1024 * 1024)
    runtime = AcademicVisualRuntime(
        sandbox=_Sandbox("unused"),
        image_provider=_Provider(),
        preview_store=preview,
    )
    spec = FigureSpec(
        figure_id="hybrid-mechanism",
        title="Federated learning mechanism",
        figure_type="mechanism_illustration",
        strategy="hybrid",
        evidence_level="explanatory",
        purpose="Explain the aggregation topology.",
    )
    brief = _brief(spec).model_copy(
        update={
            "exact_labels": (
                ExactVisualLabel(key="server", text="Global model", semantic_anchor="top_center"),
            )
        }
    )

    receipt = await runtime.render_candidate(
        AcademicVisualRenderInput(brief=brief, render=GenerativeVisualPayload(size="1024x1024")),
        context=_context(),
    )

    stored = await preview.read(receipt.candidate.review_preview_ref, workspace_id="workspace-1")
    assert stored.content != png
    assert receipt.candidate.renderer_id == "gpt-image-2+deterministic-overlay"
    assert receipt.candidate.preview_hash == stored.descriptor.content_hash
    assert receipt.candidate.ai_generated is True
    assert receipt.candidate.overlay_manifest_hash
    assert (
        receipt.manifest.overlay_manifest_hash
        == receipt.candidate.overlay_manifest_hash
    )


@pytest.mark.asyncio
async def test_visual_candidate_identity_ignores_random_preview_ref() -> None:
    png = _png(320, 320, include_text=True, varied=True)

    class _Provider:
        async def generate(self, _request):
            return ImageGenerationResult(
                content=png,
                mime_type="image/png",
                width=320,
                height=320,
                provider_model="gpt-image-2",
                provider_request_id="request-stable",
            )

    class _RandomPreviewStore:
        def __init__(self) -> None:
            self.count = 0

        async def put(self, *, workspace_id, content, mime_type, filename, metadata=None):
            _ = metadata
            self.count += 1
            assert workspace_id == "workspace-1"
            assert mime_type == "image/png"
            assert filename
            return SimpleNamespace(
                ref=f"mpv1_random_preview_{self.count:02d}",
                content_hash=hashlib.sha256(content).hexdigest(),
                size_bytes=len(content),
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )

    runtime = AcademicVisualRuntime(
        sandbox=_Sandbox("unused"),
        image_provider=_Provider(),
        preview_store=_RandomPreviewStore(),
    )
    request = AcademicVisualRenderInput(
        brief=_brief(
            FigureSpec(
                figure_id="stable-preview",
                title="Stable preview identity",
                figure_type="conceptual_illustration",
                strategy="llm_image",
                purpose="Verify semantic candidate identity.",
            )
        ),
        render=GenerativeVisualPayload(size="1024x1024"),
    )

    first = await runtime.render_candidate(request, context=_context())
    second = await runtime.render_candidate(request, context=_context())

    assert first.candidate.preview_ref != second.candidate.preview_ref
    assert first.candidate.candidate_id == second.candidate.candidate_id


@pytest.mark.asyncio
async def test_semantic_identity_binds_source_contract_renderer_prompt_and_data_hashes() -> None:
    target = "/workspace/outputs/result.png"
    dataset_path = "/workspace/datasets/results.csv"
    sandbox = _Sandbox(target)
    sandbox.precondition_hashes[dataset_path] = "sha256:" + "7" * 64
    runtime = AcademicVisualRuntime(
        sandbox=sandbox,
        image_provider=_UnusedProvider(),
        preview_store=_PreviewStore(),
    )
    request = AcademicVisualRenderInput(
        brief=_brief(
            FigureSpec(
                figure_id="semantic-result",
                title="Semantic result",
                figure_type="data_plot",
                strategy="matplotlib",
                evidence_level="evidence",
                purpose="Bind verified result data.",
                output_targets=[target],
                dataset_paths=[dataset_path],
            )
        ),
        render=CodeVisualPayload(
            source_code="print('render')",
            script_path="/workspace/scripts/result.py",
            dataset_paths=(dataset_path,),
        ),
    )

    identity = await runtime.semantic_identity(
        request,
        context=_context(),
        source_item_seq=23,
        contract_hashes=("8" * 64,),
        content_hash_refs={dataset_path: "sha256:" + "7" * 64},
    )

    assert identity.source_item_seq == 23
    assert identity.contract_hashes == ("8" * 64,)
    assert identity.renderer_id == "matplotlib"
    assert identity.source_semantic_hash == hashlib.sha256(
        b"print('render')"
    ).hexdigest()
    assert identity.dataset_content_hashes[dataset_path] == "sha256:" + "7" * 64

    changed = await runtime.semantic_identity(
        request,
        context=_context(),
        source_item_seq=23,
        contract_hashes=("9" * 64,),
    )
    assert changed.contract_hashes != identity.contract_hashes


def test_generative_visual_rejects_unbounded_other_figure_type() -> None:
    with pytest.raises(ValueError, match="limited to generative figure types"):
        FigureSpec(
            figure_id="other",
            title="Unclassified visual",
            figure_type="other",
            strategy="llm_image",
            evidence_level="explanatory",
            purpose="Create an unspecified image.",
        )


def test_raster_quality_gate_rejects_blank_images() -> None:
    with pytest.raises(RasterQualityError, match="blank or visually empty"):
        inspect_raster(
            _png(320, 320, include_text=False),
            expected_mime_type="image/png",
            minimum_dimension=256,
        )


@pytest.mark.asyncio
async def test_openai_image_adapter_pins_model_endpoint_and_strips_ancillary_chunks() -> None:
    original = _png(1, 1, include_text=True)

    async def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://images.example/v1/images/generations"
        payload = __import__("json").loads(request.content)
        assert payload["model"] == "gpt-image-2"
        assert payload["response_format"] == "b64_json"
        return httpx.Response(
            200,
            headers={"x-request-id": "image-request-1"},
            json={"data": [{"b64_json": base64.b64encode(original).decode()}]},
        )

    provider = OpenAIImagesProvider(
        api_key="secret",
        base_url="https://images.example/v1",
        transport=httpx.MockTransport(handler),
    )
    result = await provider.generate(ImageGenerationRequest(prompt="academic figure", size="1024x1024", quality="high"))

    assert (result.width, result.height) == (1, 1)
    assert b"tEXt" not in result.content
    assert result.provider_request_id == "image-request-1"


def _png(width: int, height: int, *, include_text: bool, varied: bool = False) -> bytes:
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    rows = []
    for y in range(height):
        pixels = b"".join(
            bytes(((x * 17 + y * 11) % 256, (x * 7) % 256, (y * 13) % 256, 255))
            if varied
            else b"\x00\x00\x00\xff"
            for x in range(width)
        )
        rows.append(b"\x00" + pixels)
    raw = b"".join(rows)
    chunks = [_chunk(b"IHDR", ihdr)]
    if include_text:
        chunks.append(_chunk(b"tEXt", b"private\x00metadata"))
    chunks.extend((_chunk(b"IDAT", zlib.compress(raw)), _chunk(b"IEND", b"")))
    return signature + b"".join(chunks)


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
