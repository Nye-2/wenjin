from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.academic_visual_runtime import AcademicVisualRuntimeError
from src.mission_runtime.production import StrictToolExecutionGuard
from src.sandbox.contracts import (
    SandboxOperationRequest,
    SandboxOperationResult,
    SandboxOperationStatus,
    SandboxRetryDisposition,
)
from src.services.mission_inputs import MissionInputStore
from src.services.search import MODEL_NATIVE_SEARCH_TOOL_ID
from src.tools.mission import MISSION_TOOL_GROUPS, MissionToolHandlers, build_mission_tool_registrations
from src.tools.mission.artifact_candidates import (
    artifact_candidate_content_hash,
    artifact_candidate_ref,
)
from src.tools.mission.contracts import (
    MISSION_TOOL_INPUT_MODELS,
    AcademicVisualRenderInput,
    CreateArtifactCandidateInput,
    ImportSourceCandidateInput,
    ListSourceCodeFilesInput,
    ReadArtifactCandidateInput,
    ReadMissionInputInput,
    ReadSandboxArtifactInput,
    ReadSandboxFileInput,
    ReadSourceCodeFileInput,
    ReadWorkspaceAssetInput,
    ReadWorkspaceDocumentInput,
    RegisterArtifactToolInput,
    RunPythonToolInput,
    SmokeCheckToolInput,
)
from src.tools.orchestrator import (
    ResearchToolOutcome,
    SourceReference,
    ToolCallerKind,
    ToolCatalog,
    ToolDispatchError,
    ToolErrorType,
    ToolInvocationContext,
    ToolOperation,
    ToolOrchestrator,
    ToolOutcomeStatus,
    ToolPolicy,
    VerificationStatus,
)

IMAGE_DIGEST = f"sha256:{'a' * 64}"


def test_every_mission_tool_group_id_has_one_canonical_input_model() -> None:
    grouped_ids = {tool_id for tool_ids in MISSION_TOOL_GROUPS.values() for tool_id in tool_ids}

    assert set(MISSION_TOOL_INPUT_MODELS) == grouped_ids


def test_run_python_schema_states_full_replacement_semantics() -> None:
    schema = RunPythonToolInput.model_json_schema(mode="validation")

    assert "complete replacement" in schema["properties"]["script"]["description"].lower()
    assert "before execution" in schema["properties"]["script"]["description"].lower()
    assert "base_content_hash" not in schema["properties"]
    assert "output_base_hashes" not in schema["properties"]


def _operation(*, lease_epoch: int = 4) -> ToolOperation:
    return ToolOperation(
        mission_id="mission-1",
        operation_id="op-1",
        operation_key="operation-key-1",
        command_id="command-1",
        stage_id="stage-1",
        caller_id="workspace-agent",
        caller_kind="workspace_agent",
        tool_id="workspace.list_assets",
        tool_version="1.0.0",
        descriptor_schema_hash="a" * 64,
        args_hash="args-hash",
        policy_snapshot_ref="policy@hash",
        lease_epoch=lease_epoch,
        attempt=1,
    )


def _academic_visual_receipt_metadata(
    *,
    candidate_id: str = "avc_q3_summary",
) -> dict[str, object]:
    content_hash = "sha256:" + "b" * 64
    artifact_ref = "sandbox-artifact:" + "b" * 64
    return {
        "schema": "wenjin.academic_visual.receipt.v1",
        "candidate": {
            "schema": "wenjin.academic_visual.candidate.v1",
            "candidate_id": candidate_id,
            "figure_id": "q3-policy-summary",
            "figure_type": "data_plot",
            "strategy": "matplotlib",
            "evidence_level": "evidence",
            "sandbox_artifact_ref": artifact_ref,
            "review_preview_ref": "sandbox-preview:q3-policy-summary",
            "preview_hash": content_hash,
            "content_hash": content_hash,
            "mime_type": "image/png",
            "width": 1600,
            "height": 900,
            "renderer_id": "wenjin-matplotlib",
            "renderer_version": "1",
            "context_hash": content_hash,
            "source_refs": [],
            "dataset_refs": [],
            "quality_receipt": {},
        },
        "manifest": {
            "schema": "wenjin.figure_generation.artifact.v2",
            "figure_id": "q3-policy-summary",
            "figure_type": "data_plot",
            "strategy": "matplotlib",
            "evidence_level": "evidence",
            "candidate": {
                "kind": "sandbox_artifact",
                "ref": artifact_ref,
                "content_hash": content_hash,
            },
            "intended_output_targets": [
                "/workspace/outputs/figures/q3_policy_summary.png"
            ],
            "renderer_id": "wenjin-matplotlib",
            "renderer_version": "1",
            "dataset_refs": [],
            "source_refs": [],
        },
    }


class _Missions:
    def __init__(self, items=(), view=None, operations=None, mission_inputs=(), thread_id="thread-1") -> None:
        self.items = list(items)
        self.view = view
        self.operations = operations or {}
        self.mission_inputs = list(mission_inputs)
        self.thread_id = thread_id

    async def get(self, mission_id: str):
        assert mission_id == "mission-1"
        return SimpleNamespace(
            mission_id="mission-1",
            parent_mission_id=None,
            workspace_id="workspace-1",
            thread_id=self.thread_id,
            snapshot_json={"mission_inputs": self.mission_inputs},
        )

    async def list_items(self, mission_id: str, **_kwargs):
        assert mission_id == "mission-1"
        after_seq = int(_kwargs.get("after_seq") or 0)
        limit = int(_kwargs.get("limit") or 100)
        item_type = _kwargs.get("item_type")
        return [item for index, item in enumerate(self.items, start=1) if int(getattr(item, "seq", index)) > after_seq and (item_type is None or getattr(item, "item_type", None) == item_type)][:limit]

    async def get_operation(self, mission_id: str, operation_key: str):
        assert mission_id == "mission-1"
        return self.operations.get(operation_key)

    async def get_view(self, mission_id: str):
        assert mission_id == "mission-1"
        return self.view


class _DataService:
    def __init__(self, *, asset=None, mission_items=(), mission_view=None, mission_operations=None, mission_inputs=(), mission_thread_id="thread-1", prism_surface=None, prism_file=None) -> None:
        self.missions = _Missions(mission_items, mission_view, mission_operations, mission_inputs, mission_thread_id)
        self.asset = asset
        self.prism_surface = prism_surface
        self.prism_file = prism_file
        self.import_source = AsyncMock()

    async def get_asset(self, asset_id: str):
        assert asset_id == "asset-1"
        return self.asset

    async def resolve_asset_download(self, asset_id: str):
        assert asset_id == "asset-1"
        return SimpleNamespace(
            asset=self.asset,
            storage_backend="local",
            storage_path=self.asset.storage_path,
        )

    async def get_prism_surface(self, workspace_id: str):
        assert workspace_id == "workspace-1"
        return self.prism_surface

    async def get_prism_workspace_file(self, workspace_id: str, file_id: str):
        assert workspace_id == "workspace-1"
        assert file_id == "file-1"
        return self.prism_file


class _Sandbox:
    def __init__(self) -> None:
        self.requests: list[SandboxOperationRequest] = []
        self.artifact_contents: dict[str, bytes] = {}

    def build_request(self, **kwargs) -> SandboxOperationRequest:
        return SandboxOperationRequest.build(
            provenance=kwargs["provenance"],
            operation_input=kwargs["operation_input"],
            image_digest=IMAGE_DIGEST,
            policy_version=kwargs["policy_version"],
            network_profile=kwargs["network_profile"],
            network_grant=kwargs["network_grant"],
        )

    async def execute(self, request: SandboxOperationRequest) -> SandboxOperationResult:
        self.requests.append(request)
        now = datetime.now(UTC)
        return SandboxOperationResult(
            operation_key=request.operation_key,
            sandbox_job_id="sandbox-job-1",
            provenance=request.provenance,
            operation=request.operation,
            image_digest=request.image_digest,
            policy_version=request.policy_version,
            command_schema_version=request.command_schema_version,
            status=SandboxOperationStatus.SUCCEEDED,
            retry_disposition=SandboxRetryDisposition.REUSE_RECEIPT,
            exit_code=0,
            stdout_preview="ok",
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
        offset: int | None = None,
    ) -> bytes:
        assert workspace_id == "workspace-1"
        content = self.artifact_contents[object_ref]
        assert f"sha256:{hashlib.sha256(content).hexdigest()}" == expected_content_hash
        if offset is None:
            assert len(content) <= max_bytes
            return content
        return content[offset : offset + max_bytes]

    async def read_public_file_bytes(
        self,
        *,
        workspace_id: str,
        path: str,
        max_bytes: int,
    ) -> tuple[bytes, str]:
        assert workspace_id == "workspace-1"
        content = self.artifact_contents[path]
        assert len(content) <= max_bytes
        return content, f"sha256:{hashlib.sha256(content).hexdigest()}"


class _FailedSandbox(_Sandbox):
    async def execute(self, request: SandboxOperationRequest) -> SandboxOperationResult:
        self.requests.append(request)
        now = datetime.now(UTC)
        return SandboxOperationResult(
            operation_key=request.operation_key,
            sandbox_job_id="sandbox-job-failed",
            provenance=request.provenance,
            operation=request.operation,
            image_digest=request.image_digest,
            policy_version=request.policy_version,
            command_schema_version=request.command_schema_version,
            status=SandboxOperationStatus.FAILED,
            retry_disposition=SandboxRetryDisposition.DO_NOT_RETRY,
            exit_code=1,
            stderr_preview="AssertionError: average wait exceeds 10 minutes",
            started_at=now,
            finished_at=now,
        )


def test_every_policy_group_has_canonical_registrations_and_narrow_permissions() -> None:
    registrations = build_mission_tool_registrations(
        dataservice=_DataService(),  # type: ignore[arg-type]
        lease_guard=object(),
        receipt_store=object(),
        sandbox_runtime=_Sandbox(),  # type: ignore[arg-type]
    )
    by_id = {item.descriptor.tool_id: item.descriptor for item in registrations}

    assert all(tool_ids for tool_ids in MISSION_TOOL_GROUPS.values())
    assert {tool_id for ids in MISSION_TOOL_GROUPS.values() for tool_id in ids} == set(by_id)
    for group, tool_ids in MISSION_TOOL_GROUPS.items():
        for tool_id in tool_ids:
            assert by_id[tool_id].required_permissions == (group,)
    assert by_id["sandbox.install_dependencies"].network_profile == "package_index_only"
    assert by_id["academic_visual.render_candidate"].network_profile == "academic_visual_scoped"
    assert by_id["academic_visual.render_candidate"].payload_limit_bytes == 524_288
    assert all(descriptor.network_profile == "none" for tool_id, descriptor in by_id.items() if tool_id not in {"sandbox.install_dependencies", "academic_visual.render_candidate"})


def test_mission_tool_handlers_use_configured_workspace_asset_root(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "src.tools.mission.runtime.get_settings",
        lambda: SimpleNamespace(
            workspace_asset_root=tmp_path / "configured-assets",
            thread_data_root=tmp_path / "threads",
        ),
    )

    handlers = MissionToolHandlers(
        dataservice=_DataService(),  # type: ignore[arg-type]
        sandbox=_Sandbox(),  # type: ignore[arg-type]
    )

    assert handlers.asset_root == tmp_path / "configured-assets"


@pytest.mark.asyncio
async def test_read_mission_input_requires_pinned_manifest_and_verifies_content(tmp_path) -> None:
    store = MissionInputStore(tmp_path / "inputs")
    manifest = store.put_text(
        workspace_id="workspace-1",
        thread_id="thread-1",
        filename="problem.txt",
        mime_type="text/plain",
        extractor="plain_text",
        text="Question 1: formulate the objective and capacity constraints.",
        source_content_hash=f"sha256:{'e' * 64}",
        source_size_bytes=58,
    )
    handlers = MissionToolHandlers(
        dataservice=_DataService(mission_inputs=[manifest.model_dump(mode="json")]),  # type: ignore[arg-type]
        sandbox=_Sandbox(),  # type: ignore[arg-type]
        mission_input_store=store,
    )

    result = await handlers.read_mission_input(
        _operation(),
        ReadMissionInputInput(input_ref=manifest.input_ref),
    )

    assert result.payload_ref == manifest.input_ref
    assert result.evidence_refs[0].metadata["content"].startswith("Question 1")
    with pytest.raises(ToolDispatchError) as exc_info:
        await handlers.read_mission_input(
            _operation(),
            ReadMissionInputInput(input_ref=f"mission-input:{'f' * 64}"),
        )
    assert exc_info.value.error_type is ToolErrorType.NO_RESULTS


@pytest.mark.asyncio
async def test_read_mission_input_rejects_cross_thread_manifest(tmp_path) -> None:
    store = MissionInputStore(tmp_path / "inputs")
    manifest = store.put_text(
        workspace_id="workspace-1",
        thread_id="thread-2",
        filename="problem.txt",
        mime_type="text/plain",
        extractor="plain_text",
        text="Question 1: formulate the objective.",
        source_content_hash=f"sha256:{'d' * 64}",
        source_size_bytes=36,
    )
    handlers = MissionToolHandlers(
        dataservice=_DataService(mission_inputs=[manifest.model_dump(mode="json")]),  # type: ignore[arg-type]
        sandbox=_Sandbox(),  # type: ignore[arg-type]
        mission_input_store=store,
    )

    with pytest.raises(ToolDispatchError) as exc_info:
        await handlers.read_mission_input(
            _operation(),
            ReadMissionInputInput(input_ref=manifest.input_ref),
        )

    assert exc_info.value.error_type is ToolErrorType.PERMISSION_DENIED


@pytest.mark.asyncio
async def test_workspace_document_refs_include_revision_preconditions() -> None:
    file = SimpleNamespace(
        id="file-1",
        workspace_id="workspace-1",
        document_id="document-1",
        path="analysis.md",
        file_role="generated",
        mime_type="text/markdown",
        current_version_id="version-1",
        content_hash="hash-1",
        deleted_at=None,
    )
    version = SimpleNamespace(
        id="version-1",
        content_inline="complete document",
        content_hash="hash-1",
    )
    handlers = MissionToolHandlers(
        dataservice=_DataService(
            prism_surface=SimpleNamespace(files=[file]),
            prism_file=SimpleNamespace(file=file, current_version=version),
        ),  # type: ignore[arg-type]
        sandbox=_Sandbox(),  # type: ignore[arg-type]
    )

    listed = await handlers.list_workspace_documents(
        _operation(),
        MISSION_TOOL_INPUT_MODELS["workspace.list_documents"](),
    )
    read = await handlers.read_workspace_document(
        _operation(),
        ReadWorkspaceDocumentInput(document_ref="prism-file:file-1"),
    )

    assert listed.evidence_refs[0].ref_id == "prism-file:file-1"
    assert listed.evidence_refs[0].metadata["revision_ref"] == "version-1"
    assert read.evidence_refs[0].metadata["revision_ref"] == "version-1"
    assert read.evidence_refs[0].metadata["content_hash"] == "hash-1"


@pytest.mark.asyncio
async def test_academic_visual_prism_context_is_revision_and_hash_bound() -> None:
    content = "Method: aggregate low-rank updates under client heterogeneity."
    selection = content[8:34]
    selection_hash = f"sha256:{hashlib.sha256(selection.encode()).hexdigest()}"
    dataservice = _DataService(
        prism_surface=SimpleNamespace(project=SimpleNamespace(id="project-1")),
        prism_file=SimpleNamespace(
            file=SimpleNamespace(deleted_at=None),
            current_version=SimpleNamespace(id="revision-3", content_inline=content),
        ),
    )
    handlers = MissionToolHandlers(
        dataservice=dataservice,  # type: ignore[arg-type]
        sandbox=_Sandbox(),  # type: ignore[arg-type]
    )
    request = AcademicVisualRenderInput.model_validate(
        {
            "brief": {
                "figure_spec": {
                    "figure_id": "federated-method",
                    "title": "Federated adaptation mechanism",
                    "figure_type": "conceptual_illustration",
                    "strategy": "llm_image",
                    "purpose": "Explain the method",
                    "output_targets": ["/workspace/outputs/figures/federated-method.png"],
                },
                "intended_use": "manuscript",
                "audience": "machine learning researchers",
                "target_language": "English",
                "aspect_ratio": "3:2",
                "composition": "server and client update flow",
                "prism_context_ref": {
                    "workspace_id": "workspace-1",
                    "prism_project_id": "project-1",
                    "file_id": "file-1",
                    "base_revision_ref": "revision-3",
                    "selection_hash": selection_hash,
                    "selection_range": [8, 34],
                },
            },
            "render": {"kind": "generative", "size": "1536x1024"},
        }
    )

    resolved, resolved_hash = await handlers._resolve_visual_prism_context("workspace-1", request)

    assert resolved == selection
    assert resolved_hash == selection_hash

    stale = request.model_copy(update={"brief": request.brief.model_copy(update={"prism_context_ref": request.brief.prism_context_ref.model_copy(update={"selection_hash": f"sha256:{'0' * 64}"})})})
    with pytest.raises(ToolDispatchError, match="selection changed"):
        await handlers._resolve_visual_prism_context("workspace-1", stale)


@pytest.mark.asyncio
async def test_deterministic_academic_visual_exposes_reproducibility_evidence() -> None:
    candidate = SimpleNamespace(
        candidate_id="candidate-1",
        sandbox_artifact_ref=f"sandbox-artifact:{'a' * 64}",
        content_hash=f"sha256:{'a' * 64}",
        preview_hash="b" * 64,
        review_preview_ref="mpv1_abcdefghijklmnopqrstuvwxyzABCDEF",
        reproducibility_ref="sandbox-operation:receipt-1",
        dataset_refs=("/workspace/datasets/results.csv",),
    )

    class _AcademicVisual:
        async def render_candidate(self, _request, *, context):
            assert context.workspace_id == "workspace-1"
            return SimpleNamespace(
                candidate=candidate,
                model_dump=lambda **_kwargs: {"candidate": {"candidate_id": candidate.candidate_id}},
            )

    handlers = MissionToolHandlers(
        dataservice=_DataService(),  # type: ignore[arg-type]
        sandbox=_Sandbox(),  # type: ignore[arg-type]
        academic_visual=_AcademicVisual(),  # type: ignore[arg-type]
    )
    request = AcademicVisualRenderInput.model_validate(
        {
            "brief": {
                "figure_spec": {
                    "figure_id": "result-chart",
                    "title": "Result chart",
                    "figure_type": "experiment_plot",
                    "strategy": "matplotlib",
                    "evidence_level": "evidence",
                    "purpose": "Plot verified results",
                    "dataset_paths": ["/workspace/datasets/results.csv"],
                    "output_targets": ["/workspace/outputs/figures/result-chart.png"],
                },
                "intended_use": "manuscript",
                "audience": "machine learning researchers",
                "target_language": "English",
                "aspect_ratio": "3:2",
                "composition": "comparison chart",
            },
            "render": {
                "kind": "code",
                "source_code": "print('render')",
                "script_path": "/workspace/scripts/result_chart.py",
                "dataset_paths": ["/workspace/datasets/results.csv"],
            },
        }
    )

    outcome = await handlers.render_academic_visual_candidate(_operation(), request)

    assert outcome.evidence_refs[0].ref_id == candidate.sandbox_artifact_ref
    assert outcome.evidence_refs[0].metadata["surfaces"] == [
        "figure_data_consistency",
        "experiment_reproducibility",
    ]


@pytest.mark.asyncio
async def test_academic_visual_script_failure_is_recoverable_execution_error() -> None:
    class _AcademicVisual:
        async def render_candidate(self, _request, *, context):
            assert context.workspace_id == "workspace-1"
            raise AcademicVisualRuntimeError(
                "sandbox_execution_failed",
                "AssertionError: Unexpected columns",
                recoverable=True,
            )

    handlers = MissionToolHandlers(
        dataservice=_DataService(),  # type: ignore[arg-type]
        sandbox=_Sandbox(),  # type: ignore[arg-type]
        academic_visual=_AcademicVisual(),  # type: ignore[arg-type]
    )
    request = AcademicVisualRenderInput.model_validate(
        {
            "brief": {
                "figure_spec": {
                    "figure_id": "result-chart",
                    "title": "Result chart",
                    "figure_type": "experiment_plot",
                    "strategy": "matplotlib",
                    "purpose": "Plot verified results",
                    "output_targets": [
                        "/workspace/outputs/figures/result-chart.png"
                    ],
                },
                "intended_use": "manuscript",
                "audience": "researchers",
                "target_language": "English",
                "aspect_ratio": "3:2",
                "composition": "comparison chart",
            },
            "render": {
                "kind": "code",
                "source_code": "raise AssertionError('Unexpected columns')",
                "script_path": "/workspace/scripts/result_chart.py",
            },
        }
    )

    with pytest.raises(ToolDispatchError, match="Unexpected columns") as error:
        await handlers.render_academic_visual_candidate(_operation(), request)

    assert error.value.error_type is ToolErrorType.EXECUTION_FAILED
    assert error.value.recoverable_by_model is True


@pytest.mark.asyncio
async def test_source_code_read_is_owner_scoped_and_single_file_cannot_escape(tmp_path) -> None:
    upload_root = tmp_path / "uploads"
    workspace_root = upload_root / "workspace-1"
    workspace_root.mkdir(parents=True)
    allowed = workspace_root / "main.py"
    sibling = workspace_root / "secret.py"
    allowed.write_text("print('allowed')", encoding="utf-8")
    sibling.write_text("print('secret')", encoding="utf-8")
    asset = SimpleNamespace(
        id="asset-1",
        workspace_id="workspace-1",
        deleted_at=None,
        storage_path=str(allowed),
        title="main.py",
        name="main.py",
    )
    handlers = MissionToolHandlers(
        dataservice=_DataService(asset=asset),  # type: ignore[arg-type]
        sandbox=_Sandbox(),  # type: ignore[arg-type]
        asset_root=upload_root,
    )

    listing = await handlers.list_source_code_files(_operation(), ListSourceCodeFilesInput(asset_ref="asset:asset-1"))
    assert listing.evidence_refs[0].metadata["files"] == ["main.py"]
    read = await handlers.read_source_code_file(
        _operation(),
        ReadSourceCodeFileInput(asset_ref="asset:asset-1", relative_path="main.py"),
    )
    assert "allowed" in read.evidence_refs[0].metadata["content"]
    with pytest.raises(ToolDispatchError):
        await handlers.read_source_code_file(
            _operation(),
            ReadSourceCodeFileInput(asset_ref="asset:asset-1", relative_path="secret.py"),
        )

    foreign = SimpleNamespace(**{**asset.__dict__, "workspace_id": "workspace-2"})
    foreign_handlers = MissionToolHandlers(
        dataservice=_DataService(asset=foreign),  # type: ignore[arg-type]
        sandbox=_Sandbox(),  # type: ignore[arg-type]
        asset_root=upload_root,
    )
    with pytest.raises(ToolDispatchError):
        await foreign_handlers.list_source_code_files(_operation(), ListSourceCodeFilesInput(asset_ref="asset:asset-1"))


@pytest.mark.asyncio
@pytest.mark.parametrize("tampered_path", ["/etc/passwd", "../workspace-2/secret.py"])
async def test_workspace_asset_rejects_tampered_database_paths(tmp_path, tampered_path: str) -> None:
    upload_root = tmp_path / "uploads"
    (upload_root / "workspace-1").mkdir(parents=True)
    asset = SimpleNamespace(
        id="asset-1",
        workspace_id="workspace-1",
        deleted_at=None,
        storage_path=tampered_path,
        title="tampered",
        name="tampered.txt",
        mime_type="text/plain",
    )
    handlers = MissionToolHandlers(
        dataservice=_DataService(asset=asset),  # type: ignore[arg-type]
        sandbox=_Sandbox(),  # type: ignore[arg-type]
        asset_root=upload_root,
    )

    with pytest.raises(ToolDispatchError):
        await handlers.read_workspace_asset(
            _operation(),
            ReadWorkspaceAssetInput(asset_ref="asset:asset-1"),
        )


@pytest.mark.asyncio
async def test_workspace_asset_rejects_symlink_escape(tmp_path) -> None:
    upload_root = tmp_path / "uploads"
    workspace_root = upload_root / "workspace-1"
    workspace_root.mkdir(parents=True)
    link = workspace_root / "outside.txt"
    link.symlink_to("/etc/passwd")
    asset = SimpleNamespace(
        id="asset-1",
        workspace_id="workspace-1",
        deleted_at=None,
        storage_path=str(link),
        title="outside",
        name="outside.txt",
        mime_type="text/plain",
    )
    handlers = MissionToolHandlers(
        dataservice=_DataService(asset=asset),  # type: ignore[arg-type]
        sandbox=_Sandbox(),  # type: ignore[arg-type]
        asset_root=upload_root,
    )

    with pytest.raises(ToolDispatchError):
        await handlers.read_workspace_asset(_operation(), ReadWorkspaceAssetInput(asset_ref="asset:asset-1"))


@pytest.mark.asyncio
async def test_source_url_import_requires_current_mission_search_receipt() -> None:
    url = "https://example.org/paper"
    outcome = ResearchToolOutcome(
        operation_id="search-op",
        operation_key="search-operation-key",
        producer="research.search_web",
        tool_id=MODEL_NATIVE_SEARCH_TOOL_ID,
        tool_version="1.0.0",
        status=ToolOutcomeStatus.SUCCESS,
        observed_at=datetime.now(UTC),
        summary="search complete",
        source_refs=(
            SourceReference(
                source_id="provider-source-1",
                canonical_url=url,
                title="Paper",
                observed_at=datetime.now(UTC),
                verification_status=VerificationStatus.PROVIDER_RECEIPT,
            ),
        ),
        verification_status=VerificationStatus.PROVIDER_RECEIPT,
    )
    receipt = SimpleNamespace(receipt_json={"outcome": outcome.model_dump(mode="json")})
    dataservice = _DataService(
        mission_operations={outcome.operation_key: receipt},
    )
    dataservice.import_source.return_value = SimpleNamespace(
        source=SimpleNamespace(id="source-1", title="Paper", url=url, citation_key="Paper2026"),
        created=True,
    )
    handlers = MissionToolHandlers(
        dataservice=dataservice,  # type: ignore[arg-type]
        sandbox=_Sandbox(),  # type: ignore[arg-type]
    )
    args = ImportSourceCandidateInput(
        title="Paper",
        citation_key="Paper2026",
        verification_ref="search-receipt:search-operation-key#provider-source-1",
        url=url,
    )

    result = await handlers.import_source_candidate(_operation(), args)

    assert result.payload_ref == "source:source-1"
    dataservice.import_source.assert_awaited_once()

    missing_handlers = MissionToolHandlers(
        dataservice=_DataService(),  # type: ignore[arg-type]
        sandbox=_Sandbox(),  # type: ignore[arg-type]
    )
    with pytest.raises(ToolDispatchError, match="search receipt"):
        await missing_handlers.import_source_candidate(_operation(), args)


@pytest.mark.asyncio
async def test_sandbox_tool_binds_mission_workspace_and_lease_receipt() -> None:
    sandbox = _Sandbox()
    handlers = MissionToolHandlers(
        dataservice=_DataService(),  # type: ignore[arg-type]
        sandbox=sandbox,  # type: ignore[arg-type]
    )

    result = await handlers.sandbox_smoke_check(_operation(lease_epoch=9), SmokeCheckToolInput())

    assert result.summary == "ok"
    [request] = sandbox.requests
    assert request.provenance.workspace_id == "workspace-1"
    assert request.provenance.mission_id == "mission-1"
    assert request.provenance.lease_epoch == 9
    assert request.operation_key.startswith("sbxop_")


@pytest.mark.asyncio
async def test_run_python_derives_read_before_write_hashes_from_verified_receipts() -> None:
    sandbox = _Sandbox()
    script_hash = f"sha256:{'1' * 64}"
    output_hash = f"sha256:{'2' * 64}"
    mission_items = (
        SimpleNamespace(
            seq=1,
            item_type="evidence",
            payload_json={
                "verified": True,
                "kind": "sandbox_public_file",
                "metadata": {
                    "path": "/workspace/scripts/q1_validation.py",
                    "content_hash": script_hash,
                },
            },
        ),
        SimpleNamespace(
            seq=2,
            item_type="evidence",
            payload_json={
                "verified": True,
                "kind": "sandbox_public_file",
                "metadata": {
                    "path": "/workspace/outputs/q1_solution_validation.json",
                    "content_hash": output_hash,
                },
            },
        ),
    )
    handlers = MissionToolHandlers(
        dataservice=_DataService(mission_items=mission_items),  # type: ignore[arg-type]
        sandbox=sandbox,  # type: ignore[arg-type]
    )

    await handlers.sandbox_run_python(
        _operation(),
        RunPythonToolInput(
            script="print('ok')",
            script_path="/workspace/scripts/q1_validation.py",
        ),
    )

    [request] = sandbox.requests
    assert request.operation_input.base_content_hash == script_hash
    assert request.operation_input.output_base_hashes == {
        "/workspace/outputs/q1_solution_validation.json": output_hash,
    }


@pytest.mark.asyncio
async def test_failed_sandbox_computation_is_a_model_recoverable_execution_failure() -> None:
    handlers = MissionToolHandlers(
        dataservice=_DataService(),  # type: ignore[arg-type]
        sandbox=_FailedSandbox(),  # type: ignore[arg-type]
    )

    with pytest.raises(ToolDispatchError) as captured:
        await handlers.sandbox_run_python(
            _operation(),
            RunPythonToolInput(
                script="raise AssertionError('average wait exceeds 10 minutes')",
                script_path="/workspace/scripts/q1_validation.py",
            ),
        )

    assert captured.value.error_type is ToolErrorType.EXECUTION_FAILED
    assert captured.value.recoverable_by_model is True
    assert "average wait exceeds 10 minutes" in captured.value.user_safe_summary


@pytest.mark.asyncio
async def test_sandbox_artifact_registration_rejects_temporary_scratch_as_recoverable_input() -> None:
    sandbox = _Sandbox()
    handlers = MissionToolHandlers(
        dataservice=_DataService(),  # type: ignore[arg-type]
        sandbox=sandbox,  # type: ignore[arg-type]
    )

    with pytest.raises(ToolDispatchError) as captured:
        await handlers.sandbox_register_artifact(
            _operation(),
            RegisterArtifactToolInput(
                path="/workspace/tmp/tasks/mission-1/result.json",
                producing_operation_key=f"sbxop_{'a' * 64}",
            ),
        )

    assert captured.value.error_type is ToolErrorType.INVALID_INPUT
    assert captured.value.recoverable_by_model is True
    assert "task scratch is temporary" in captured.value.user_safe_summary
    assert sandbox.requests == []


@pytest.mark.asyncio
async def test_verified_sandbox_artifact_is_directly_readable_by_canonical_ref() -> None:
    path = "/workspace/outputs/result.json"
    source = b'{"objective": 4, "checks": {"conservation": true}}'
    digest = hashlib.sha256(source).hexdigest()
    artifact_ref = f"sandbox-artifact:{digest}"
    object_ref = f"sbxobj_{digest}"
    mission_item = SimpleNamespace(
        seq=1,
        item_type="artifact",
        payload_json={
            "reference_id": artifact_ref,
            "kind": "sandbox_artifact_manifest",
            "title": "result.json",
            "uri": None,
            "metadata": {
                "path": path,
                "object_ref": object_ref,
                "kind": "application/json",
                "content_hash": f"sha256:{digest}",
                "size_bytes": len(source),
            },
            "verified": True,
        },
    )
    sandbox = _Sandbox()
    sandbox.artifact_contents[object_ref] = source
    handlers = MissionToolHandlers(
        dataservice=_DataService(mission_items=[mission_item]),  # type: ignore[arg-type]
        sandbox=sandbox,  # type: ignore[arg-type]
    )

    result = await handlers.sandbox_read_artifact(
        _operation(),
        ReadSandboxArtifactInput(artifact_ref=artifact_ref),
    )

    assert result.evidence_refs[0].ref_id == artifact_ref
    assert result.evidence_refs[0].metadata["content"] == source.decode()
    assert result.evidence_refs[0].metadata["verified_inline"] is True


@pytest.mark.asyncio
async def test_verified_sandbox_artifact_supports_bounded_pagination() -> None:
    path = "/workspace/outputs/long-result.json"
    source = ("科研结果" * 5_000).encode()
    digest = hashlib.sha256(source).hexdigest()
    artifact_ref = f"sandbox-artifact:{digest}"
    object_ref = f"sbxobj_{digest}"
    mission_item = SimpleNamespace(
        seq=1,
        item_type="artifact",
        payload_json={
            "reference_id": artifact_ref,
            "kind": "sandbox_artifact_manifest",
            "title": "long-result.json",
            "uri": None,
            "metadata": {
                "path": path,
                "object_ref": object_ref,
                "kind": "application/json",
                "content_hash": f"sha256:{digest}",
                "size_bytes": len(source),
            },
            "verified": True,
        },
    )
    sandbox = _Sandbox()
    sandbox.artifact_contents[object_ref] = source
    handlers = MissionToolHandlers(
        dataservice=_DataService(mission_items=[mission_item]),  # type: ignore[arg-type]
        sandbox=sandbox,  # type: ignore[arg-type]
    )

    first = await handlers.sandbox_read_artifact(
        _operation(),
        ReadSandboxArtifactInput(artifact_ref=artifact_ref, max_bytes=24_000),
    )
    first_metadata = first.evidence_refs[0].metadata
    second = await handlers.sandbox_read_artifact(
        _operation(),
        ReadSandboxArtifactInput(
            artifact_ref=artifact_ref,
            offset=first_metadata["next_offset"],
            max_bytes=24_000,
        ),
    )

    assert first_metadata["truncated"] is True
    assert first_metadata["next_offset"] == 24_000
    assert second.evidence_refs[0].metadata["offset"] == 24_000


@pytest.mark.asyncio
async def test_continuation_can_read_verified_artifact_from_parent_mission() -> None:
    path = "/workspace/outputs/result.json"
    source = b'{"objective": 1, "checks": {"conservation": true}}'
    digest = hashlib.sha256(source).hexdigest()
    artifact_ref = f"sandbox-artifact:{digest}"
    object_ref = f"sbxobj_{digest}"
    parent_item = SimpleNamespace(
        seq=1,
        item_type="artifact",
        payload_json={
            "reference_id": artifact_ref,
            "kind": "sandbox_artifact_manifest",
            "title": "result.json",
            "uri": None,
            "metadata": {
                "path": path,
                "object_ref": object_ref,
                "kind": "application/json",
                "content_hash": f"sha256:{digest}",
                "size_bytes": len(source),
            },
            "verified": True,
        },
    )

    class _LineageMissions:
        async def get(self, mission_id: str):
            missions = {
                "mission-1": SimpleNamespace(
                    mission_id="mission-1",
                    parent_mission_id="mission-parent",
                    workspace_id="workspace-1",
                ),
                "mission-parent": SimpleNamespace(
                    mission_id="mission-parent",
                    parent_mission_id=None,
                    workspace_id="workspace-1",
                ),
            }
            return missions.get(mission_id)

        async def list_items(self, mission_id: str, **_kwargs):
            return [parent_item] if mission_id == "mission-parent" else []

    sandbox = _Sandbox()
    sandbox.artifact_contents[object_ref] = source
    dataservice = _DataService()
    dataservice.missions = _LineageMissions()
    handlers = MissionToolHandlers(
        dataservice=dataservice,  # type: ignore[arg-type]
        sandbox=sandbox,  # type: ignore[arg-type]
    )

    result = await handlers.sandbox_read_artifact(
        _operation(),
        ReadSandboxArtifactInput(artifact_ref=artifact_ref),
    )

    assert result.evidence_refs[0].ref_id == artifact_ref
    assert result.evidence_refs[0].metadata["content"] == source.decode()


@pytest.mark.asyncio
async def test_sandbox_file_read_returns_exact_read_before_write_hash() -> None:
    path = "/workspace/scripts/q1_validation.py"
    source = b"print('validated')\n"
    sandbox = _Sandbox()
    sandbox.artifact_contents[path] = source
    handlers = MissionToolHandlers(
        dataservice=_DataService(),  # type: ignore[arg-type]
        sandbox=sandbox,  # type: ignore[arg-type]
    )

    result = await handlers.sandbox_read_file(
        _operation(),
        ReadSandboxFileInput(path=path),
    )

    metadata = result.evidence_refs[0].metadata
    assert metadata["path"] == path
    assert metadata["content"] == source.decode()
    assert metadata["content_hash"] == f"sha256:{hashlib.sha256(source).hexdigest()}"


@pytest.mark.asyncio
async def test_artifact_render_emits_service_hashed_text_candidate() -> None:
    handlers = MissionToolHandlers(
        dataservice=_DataService(),  # type: ignore[arg-type]
        sandbox=_Sandbox(),  # type: ignore[arg-type]
    )
    result = await handlers.create_artifact_candidate(
        _operation(),
        CreateArtifactCandidateInput(
            title="Result brief",
            artifact_kind="modeling_result_brief",
            preview_text="# Result\n\nVerified objective: 4.",
        ),
    )

    [candidate] = result.artifact_refs
    assert candidate.kind == "artifact_candidate"
    assert candidate.metadata["content_hash"] == "sha256:" + hashlib.sha256(b"# Result\n\nVerified objective: 4.").hexdigest()
    assert candidate.metadata["materialized"] is False
    assert candidate.metadata["mission_id"] == "mission-1"


@pytest.mark.asyncio
async def test_artifact_candidate_rejects_unverified_source_refs() -> None:
    handlers = MissionToolHandlers(
        dataservice=_DataService(),  # type: ignore[arg-type]
        sandbox=_Sandbox(),  # type: ignore[arg-type]
    )

    with pytest.raises(ToolDispatchError) as captured:
        await handlers.create_artifact_candidate(
            _operation(),
            CreateArtifactCandidateInput(
                title="Result brief",
                artifact_kind="modeling_result_brief",
                source_refs=("prism-file:missing",),
                preview_text="# Result",
            ),
        )

    assert captured.value.error_type is ToolErrorType.PROVENANCE_MISSING
    assert captured.value.recoverable_by_model is True


@pytest.mark.asyncio
async def test_artifact_candidate_accepts_verified_upstream_candidate_as_provenance() -> None:
    upstream_preview = "# Problem understanding\n\nThree questions were identified."
    upstream_metadata = {
        "title": "Problem understanding",
        "artifact_kind": "problem_brief",
        "source_refs": [],
        "mime_type": "text/markdown",
        "preview_text": upstream_preview,
        "metadata": {},
        "content_hash": artifact_candidate_content_hash(upstream_preview),
        "mission_id": "mission-1",
        "operation_key": "upstream-operation",
        "materialized": False,
    }
    upstream_ref = artifact_candidate_ref(upstream_metadata)
    upstream_item = SimpleNamespace(
        seq=7,
        item_type="artifact",
        payload_json={
            "reference_id": upstream_ref,
            "kind": "artifact_candidate",
            "title": "Problem understanding",
            "verified": True,
            "metadata": upstream_metadata,
        },
    )
    handlers = MissionToolHandlers(
        dataservice=_DataService(mission_items=(upstream_item,)),  # type: ignore[arg-type]
        sandbox=_Sandbox(),  # type: ignore[arg-type]
    )

    result = await handlers.create_artifact_candidate(
        _operation(),
        CreateArtifactCandidateInput(
            title="Question one model",
            artifact_kind="question_model_spec",
            source_refs=(upstream_ref,),
            preview_text="# Model\n\nDerived from the accepted problem understanding.",
        ),
    )

    [candidate] = result.artifact_refs
    assert candidate.metadata["source_refs"] == [upstream_ref]


@pytest.mark.asyncio
async def test_artifact_candidate_can_be_read_from_verified_mission_receipt() -> None:
    preview = "# 第一问\n\n$J=1$"
    metadata = {
        "title": "第一问",
        "artifact_kind": "document",
        "mime_type": "text/markdown",
        "preview_text": preview,
        "content_hash": artifact_candidate_content_hash(preview),
        "source_refs": ["sandbox-artifact:" + "a" * 64],
        "materialized": False,
    }
    candidate_ref = artifact_candidate_ref(metadata)
    item = SimpleNamespace(
        seq=7,
        item_type="artifact",
        payload_json={
            "reference_id": candidate_ref,
            "kind": "artifact_candidate",
            "title": "第一问",
            "verified": True,
            "metadata": metadata,
        },
    )
    handlers = MissionToolHandlers(
        dataservice=_DataService(mission_items=(item,)),  # type: ignore[arg-type]
        sandbox=_Sandbox(),  # type: ignore[arg-type]
    )

    result = await handlers.read_artifact_candidate(
        _operation(),
        ReadArtifactCandidateInput(candidate_ref=candidate_ref),
    )

    assert result.verification_status is VerificationStatus.VERIFIED
    assert result.payload_ref == candidate_ref
    assert result.evidence_refs[0].metadata["preview_text"] == preview


@pytest.mark.asyncio
async def test_academic_visual_can_be_read_as_internal_candidate() -> None:
    candidate_id = "avc_q3_summary"
    candidate_ref = f"academic-visual:{candidate_id}"
    metadata = _academic_visual_receipt_metadata(candidate_id=candidate_id)
    item = SimpleNamespace(
        seq=8,
        item_type="artifact",
        payload_json={
            "reference_id": candidate_ref,
            "kind": "academic_visual_candidate",
            "title": "第三问策略对比",
            "verified": True,
            "metadata": metadata,
        },
    )
    handlers = MissionToolHandlers(
        dataservice=_DataService(mission_items=(item,)),  # type: ignore[arg-type]
        sandbox=_Sandbox(),  # type: ignore[arg-type]
    )

    result = await handlers.read_artifact_candidate(
        _operation(),
        ReadArtifactCandidateInput(candidate_ref=candidate_ref),
    )

    assert result.verification_status is VerificationStatus.VERIFIED
    assert result.payload_ref == candidate_ref
    assert result.evidence_refs[0].kind == "academic_visual_candidate"
    assert result.evidence_refs[0].metadata["candidate"]["candidate_id"] == candidate_id


@pytest.mark.asyncio
async def test_artifact_candidate_accepts_verified_academic_visual_provenance() -> None:
    candidate_id = "avc_q3_summary"
    visual_ref = f"academic-visual:{candidate_id}"
    item = SimpleNamespace(
        seq=8,
        item_type="artifact",
        payload_json={
            "reference_id": visual_ref,
            "kind": "academic_visual_candidate",
            "title": "第三问策略对比",
            "verified": True,
            "metadata": _academic_visual_receipt_metadata(
                candidate_id=candidate_id
            ),
        },
    )
    handlers = MissionToolHandlers(
        dataservice=_DataService(mission_items=(item,)),  # type: ignore[arg-type]
        sandbox=_Sandbox(),  # type: ignore[arg-type]
    )

    result = await handlers.create_artifact_candidate(
        _operation(),
        CreateArtifactCandidateInput(
            title="完整数学建模论文",
            artifact_kind="math_modeling_paper",
            source_refs=(visual_ref,),
            preview_text="# 完整论文\n\n![第三问策略对比](academic-visual:avc_q3_summary)",
        ),
    )

    assert result.artifact_refs[0].metadata["source_refs"] == [visual_ref]


class _Journal:
    def __init__(self) -> None:
        self.terminal = None

    async def load_terminal(self, _operation):
        return self.terminal

    async def claim_started(self, _operation):
        return True

    async def record_terminal(self, _operation, outcome):
        self.terminal = outcome
        return True


class _Fence:
    async def assert_current(self, _operation):
        return None


@pytest.mark.asyncio
async def test_pinned_group_permission_passes_catalog_preflight_end_to_end() -> None:
    registrations = build_mission_tool_registrations(
        dataservice=_DataService(),  # type: ignore[arg-type]
        lease_guard=object(),
        receipt_store=object(),
        sandbox_runtime=_Sandbox(),  # type: ignore[arg-type]
    )
    orchestrator = ToolOrchestrator(
        catalog=ToolCatalog(registrations).freeze(),
        journal=_Journal(),
        lease_fence=_Fence(),
        guard=StrictToolExecutionGuard(),
    )
    context = ToolInvocationContext(
        mission_id="mission-1",
        workspace_id="workspace-1",
        command_id="command-1",
        stage_id="stage-1",
        caller_id="workspace-agent",
        caller_kind=ToolCallerKind.WORKSPACE_AGENT,
        lease_epoch=4,
    )
    policy = ToolPolicy(
        policy_ref="policy@hash",
        allowed_tool_ids=("artifact.create_candidate",),
        granted_permissions=("artifact_render",),
    )

    outcome = await orchestrator.invoke(
        "artifact.create_candidate",
        {
            "title": "Result brief",
            "artifact_kind": "modeling_result_brief",
            "source_refs": [],
            "mime_type": "text/markdown",
            "preview_text": "# Result\n\nVerified objective: 4.",
        },
        context=context,
        policy=policy,
    )

    assert outcome.status is ToolOutcomeStatus.SUCCESS
    assert outcome.artifact_refs
