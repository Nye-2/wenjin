from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.mission_runtime.production import StrictToolExecutionGuard
from src.sandbox.contracts import (
    SandboxOperationRequest,
    SandboxOperationResult,
    SandboxOperationStatus,
    SandboxRetryDisposition,
)
from src.services.search import MODEL_NATIVE_SEARCH_TOOL_ID
from src.tools.mission import MISSION_TOOL_GROUPS, MissionToolHandlers, build_mission_tool_registrations
from src.tools.mission.contracts import (
    MISSION_TOOL_INPUT_MODELS,
    AcademicVisualRenderInput,
    CreateArtifactCandidateInput,
    ImportSourceCandidateInput,
    ListSourceCodeFilesInput,
    ReadMissionReviewCandidateInput,
    ReadSourceCodeFileInput,
    ReadWorkspaceAssetInput,
    RegisterArtifactToolInput,
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
    ToolReference,
    VerificationStatus,
)

IMAGE_DIGEST = f"sha256:{'a' * 64}"


def test_every_mission_tool_group_id_has_one_canonical_input_model() -> None:
    grouped_ids = {
        tool_id
        for tool_ids in MISSION_TOOL_GROUPS.values()
        for tool_id in tool_ids
    }

    assert set(MISSION_TOOL_INPUT_MODELS) == grouped_ids


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


class _Missions:
    def __init__(self, items=(), view=None) -> None:
        self.items = list(items)
        self.view = view

    async def get(self, mission_id: str):
        assert mission_id == "mission-1"
        return SimpleNamespace(workspace_id="workspace-1")

    async def list_items(self, mission_id: str, **_kwargs):
        assert mission_id == "mission-1"
        after_seq = int(_kwargs.get("after_seq") or 0)
        limit = int(_kwargs.get("limit") or 100)
        return [item for index, item in enumerate(self.items, start=1) if int(getattr(item, "seq", index)) > after_seq][:limit]

    async def get_view(self, mission_id: str):
        assert mission_id == "mission-1"
        return self.view


class _DataService:
    def __init__(self, *, asset=None, mission_items=(), mission_view=None, prism_surface=None, prism_file=None) -> None:
        self.missions = _Missions(mission_items, mission_view)
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
        path: str,
        expected_content_hash: str,
        max_bytes: int,
    ) -> bytes:
        assert workspace_id == "workspace-1"
        content = self.artifact_contents[path]
        assert len(content) <= max_bytes
        assert f"sha256:{hashlib.sha256(content).hexdigest()}" == expected_content_hash
        return content


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
    assert all(
        descriptor.network_profile == "none"
        for tool_id, descriptor in by_id.items()
        if tool_id not in {"sandbox.install_dependencies", "academic_visual.render_candidate"}
    )


def test_mission_tool_handlers_use_configured_workspace_asset_root(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "src.tools.mission.runtime.get_settings",
        lambda: SimpleNamespace(workspace_asset_root=tmp_path / "configured-assets"),
    )

    handlers = MissionToolHandlers(
        dataservice=_DataService(),  # type: ignore[arg-type]
        sandbox=_Sandbox(),  # type: ignore[arg-type]
    )

    assert handlers.asset_root == tmp_path / "configured-assets"


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

    stale = request.model_copy(
        update={
            "brief": request.brief.model_copy(
                update={
                    "prism_context_ref": request.brief.prism_context_ref.model_copy(
                        update={"selection_hash": f"sha256:{'0' * 64}"}
                    )
                }
            )
        }
    )
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

    listing = await handlers.list_source_code_files(_operation(), ListSourceCodeFilesInput(asset_id="asset-1"))
    assert listing.evidence_refs[0].metadata["files"] == ["main.py"]
    read = await handlers.read_source_code_file(
        _operation(),
        ReadSourceCodeFileInput(asset_id="asset-1", relative_path="main.py"),
    )
    assert "allowed" in read.evidence_refs[0].metadata["content"]
    with pytest.raises(ToolDispatchError):
        await handlers.read_source_code_file(
            _operation(),
            ReadSourceCodeFileInput(asset_id="asset-1", relative_path="secret.py"),
        )

    foreign = SimpleNamespace(**{**asset.__dict__, "workspace_id": "workspace-2"})
    foreign_handlers = MissionToolHandlers(
        dataservice=_DataService(asset=foreign),  # type: ignore[arg-type]
        sandbox=_Sandbox(),  # type: ignore[arg-type]
        asset_root=upload_root,
    )
    with pytest.raises(ToolDispatchError):
        await foreign_handlers.list_source_code_files(_operation(), ListSourceCodeFilesInput(asset_id="asset-1"))


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
            ReadWorkspaceAssetInput(asset_id="asset-1"),
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
        await handlers.read_workspace_asset(_operation(), ReadWorkspaceAssetInput(asset_id="asset-1"))


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
    item = SimpleNamespace(
        seq=101,
        payload_json={
            "operation_key": outcome.operation_key,
            "outcome": outcome.model_dump(mode="json"),
        },
    )
    filler = [
        SimpleNamespace(
            seq=index,
            payload_json={"operation_key": f"other-{index}", "outcome": {}},
        )
        for index in range(1, 101)
    ]
    dataservice = _DataService(mission_items=[*filler, item])
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
async def test_review_candidate_includes_chunked_body_and_verified_sandbox_artifacts() -> None:
    candidate_id = "review-1"
    path = "/workspace/outputs/solution.py"
    source = ("print('verified solution')\n" * 120).encode()
    content_hash = f"sha256:{hashlib.sha256(source).hexdigest()}"
    artifact_ref = ToolReference(
        ref_id=f"sandbox-artifact:{content_hash.removeprefix('sha256:')}",
        kind="sandbox_artifact_manifest",
        metadata={
            "path": path,
            "kind": "text/x-python",
            "content_hash": content_hash,
        },
    )
    outcome = ResearchToolOutcome(
        operation_id="operation-1",
        operation_key="operation-key-1",
        producer="workspace-agent",
        tool_id="sandbox.run_python",
        tool_version="1.0.0",
        status=ToolOutcomeStatus.SUCCESS,
        observed_at=datetime.now(UTC),
        summary="Produced a verified solution artifact.",
        artifact_refs=(artifact_ref,),
        verification_status=VerificationStatus.VERIFIED,
    )
    mission_item = SimpleNamespace(
        seq=1,
        payload_json={"outcome": outcome.model_dump(mode="json")},
    )
    body = "完整候选正文。" * 700
    review_item = SimpleNamespace(
        review_item_id=candidate_id,
        title="问题 1 可复现求解",
        preview_hash="a" * 64,
        preview_json={"body": body, "source_refs": [artifact_ref.ref_id]},
    )
    sandbox = _Sandbox()
    sandbox.artifact_contents[path] = source
    handlers = MissionToolHandlers(
        dataservice=_DataService(
            mission_items=[mission_item],
            mission_view=SimpleNamespace(review_items=[review_item]),
        ),  # type: ignore[arg-type]
        sandbox=sandbox,  # type: ignore[arg-type]
    )

    result = await handlers.read_review_candidate(
        _operation(),
        ReadMissionReviewCandidateInput(review_item_id=candidate_id),
    )

    metadata = result.evidence_refs[0].metadata
    assert "".join(metadata["preview_body_chunks"]) == body
    [artifact] = metadata["sandbox_artifacts"]
    assert artifact["availability"] == "verified_inline"
    assert "".join(artifact["content_chunks"]).encode() == source


@pytest.mark.asyncio
async def test_artifact_render_only_emits_review_candidate_manifest() -> None:
    handlers = MissionToolHandlers(
        dataservice=_DataService(),  # type: ignore[arg-type]
        sandbox=_Sandbox(),  # type: ignore[arg-type]
    )
    result = await handlers.create_artifact_candidate(
        _operation(),
        CreateArtifactCandidateInput(
            title="Result chart",
            artifact_kind="chart",
            source_refs=("sandbox-artifact:abc",),
            mime_type="image/png",
            sandbox_artifact_path="/workspace/outputs/chart.png",
        ),
    )

    [candidate] = result.artifact_refs
    assert candidate.kind == "artifact_candidate"
    assert candidate.metadata["materialized"] is False
    assert candidate.metadata["mission_id"] == "mission-1"


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
            "title": "Chart",
            "artifact_kind": "chart",
            "source_refs": ["sandbox-artifact:abc"],
            "mime_type": "image/png",
            "sandbox_artifact_path": "/workspace/outputs/chart.png",
        },
        context=context,
        policy=policy,
    )

    assert outcome.status is ToolOutcomeStatus.SUCCESS
    assert outcome.artifact_refs
