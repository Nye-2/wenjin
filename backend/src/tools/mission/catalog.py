"""Canonical Mission tool registrations and policy-group mapping."""

from __future__ import annotations

from collections.abc import Callable

from src.academic_visual_runtime import (
    AcademicVisualExecutionContext,
    AcademicVisualRuntime,
    AcademicVisualRuntimeError,
    ConfiguredGptImage2Provider,
)
from src.agents.harness.command_audit import CommandAuditPolicy, SandboxCommandAuditor
from src.dataservice_client import AsyncDataServiceClient
from src.review_commit_runtime.composition import get_mission_preview_store
from src.sandbox import SandboxOperationKind, SandboxRuntime, compiler_fingerprints, get_sandbox_settings
from src.sandbox.providers import DockerSandboxProvider
from src.tools.mission.contracts import (
    AcademicVisualRenderInput,
    CreateArtifactCandidateInput,
    ImportSourceCandidateInput,
    InstallDependenciesToolInput,
    ListSourceCodeFilesInput,
    ListWorkspaceAssetsInput,
    ListWorkspaceDocumentsInput,
    ReadArtifactCandidateInput,
    ReadMissionInputInput,
    ReadSandboxArtifactInput,
    ReadSandboxFileInput,
    ReadSandboxOutputInput,
    ReadSourceCodeFileInput,
    ReadWorkspaceAssetInput,
    ReadWorkspaceDocumentInput,
    RegisterArtifactToolInput,
    RegisterDatasetToolInput,
    RunNotebookToolInput,
    RunPythonToolInput,
    SearchWorkspaceSourceTextInput,
    SmokeCheckToolInput,
)
from src.tools.mission.runtime import MissionToolHandlers
from src.tools.orchestrator import (
    MalformedToolArgumentsError,
    SideEffectClass,
    ToolCallerKind,
    ToolInvocationContext,
    ToolKind,
    ToolRegistration,
    ToolSemanticIdentityBuilder,
    build_tool_registration,
)

WORKSPACE_READ_TOOL_IDS = (
    "workspace.list_assets",
    "workspace.read_asset",
    "workspace.read_input",
    "workspace.list_documents",
    "workspace.read_document",
    "workspace.search_source_text",
)
SOURCE_IMPORT_TOOL_IDS = ("source.import_candidate",)
SOURCE_CODE_READ_TOOL_IDS = ("source_code.list_files", "source_code.read_file")
SANDBOX_COMPUTE_TOOL_IDS = (
    "sandbox.run_python",
    "sandbox.run_notebook",
    "sandbox.smoke_check",
    "sandbox.install_dependencies",
    "sandbox.register_dataset",
    "sandbox.register_artifact",
)
SANDBOX_READ_TOOL_IDS = (
    "sandbox.read_artifact",
    "sandbox.read_file",
    "sandbox.read_output_ref",
)
ARTIFACT_CANDIDATE_READ_TOOL_IDS = ("artifact.read_candidate",)
ARTIFACT_RENDER_TOOL_IDS = ("artifact.create_candidate",)
ACADEMIC_VISUAL_RENDER_TOOL_IDS = ("academic_visual.render_candidate",)

MISSION_TOOL_GROUPS: dict[str, tuple[str, ...]] = {
    "workspace_read": WORKSPACE_READ_TOOL_IDS,
    "artifact_candidate_read": ARTIFACT_CANDIDATE_READ_TOOL_IDS,
    "source_import": SOURCE_IMPORT_TOOL_IDS,
    "source_code_read": SOURCE_CODE_READ_TOOL_IDS,
    "sandbox_compute": SANDBOX_COMPUTE_TOOL_IDS,
    "sandbox_read": SANDBOX_READ_TOOL_IDS,
    "artifact_render": ARTIFACT_RENDER_TOOL_IDS,
    "academic_visual_render": ACADEMIC_VISUAL_RENDER_TOOL_IDS,
}

_CALLERS = (ToolCallerKind.WORKSPACE_AGENT, ToolCallerKind.SUBAGENT)


class LazyProductionSandbox:
    """Create the hardened Docker runtime only when a sandbox tool is invoked."""

    def __init__(self, *, lease_guard, receipt_store) -> None:
        self._lease_guard = lease_guard
        self._receipt_store = receipt_store
        self._runtime: SandboxRuntime | None = None

    def _get(self) -> SandboxRuntime:
        if self._runtime is not None:
            return self._runtime
        settings = get_sandbox_settings()
        image_digest = settings.docker.image_digest
        if image_digest is None:
            raise RuntimeError("SANDBOX_DOCKER__IMAGE_DIGEST is required for Mission sandbox execution")
        provider = DockerSandboxProvider(
            settings.docker,
            sandbox_root=settings.root_dir,
            preflight_mode=("release" if settings.deployment_mode == "production" else "development"),
        )
        audit_operations = frozenset(
            {
                SandboxOperationKind.RUN_PYTHON,
                SandboxOperationKind.RUN_NOTEBOOK,
                SandboxOperationKind.SMOKE_CHECK,
                SandboxOperationKind.INSTALL_DEPENDENCIES,
            }
        )
        self._runtime = SandboxRuntime(
            provider=provider,
            command_auditor=SandboxCommandAuditor(
                CommandAuditPolicy(
                    allowed_operations=audit_operations,
                    compiler_fingerprints=compiler_fingerprints(),
                    allow_package_install=True,
                )
            ),
            lease_guard=self._lease_guard,
            sandbox_root=settings.root_dir,
            image_reference=settings.docker.image_reference,
            image_digest=image_digest,
            output_ref_ttl_seconds=settings.output_ref_ttl_seconds,
            receipt_store_factory=lambda _workspace: self._receipt_store,
        )
        return self._runtime

    def build_request(self, **kwargs):
        return self._get().build_request(**kwargs)

    async def execute(self, request):
        return await self._get().execute(request)

    async def read_artifact_bytes(self, **kwargs):
        return await self._get().read_artifact_bytes(**kwargs)

    async def read_public_file_bytes(self, **kwargs):
        return await self._get().read_public_file_bytes(**kwargs)

    async def read_public_file_precondition_hash(self, **kwargs):
        return await self._get().read_public_file_precondition_hash(**kwargs)


def build_mission_tool_registrations(
    *,
    dataservice: AsyncDataServiceClient,
    lease_guard,
    receipt_store,
    sandbox_runtime: SandboxRuntime | None = None,
    academic_visual_runtime: AcademicVisualRuntime | None = None,
) -> tuple[ToolRegistration, ...]:
    sandbox = sandbox_runtime or LazyProductionSandbox(
        lease_guard=lease_guard,
        receipt_store=receipt_store,
    )
    academic_visual = academic_visual_runtime or AcademicVisualRuntime(
        sandbox=sandbox,  # type: ignore[arg-type]
        image_provider=ConfiguredGptImage2Provider(),
        preview_store=get_mission_preview_store(),
    )
    handlers = MissionToolHandlers(
        dataservice=dataservice,
        sandbox=sandbox,  # type: ignore[arg-type]
        academic_visual=academic_visual,
    )

    async def build_academic_visual_identity(
        raw_args,
        invocation_context: ToolInvocationContext,
    ):
        if not isinstance(raw_args, AcademicVisualRenderInput):
            raise MalformedToolArgumentsError(
                "Academic visual arguments did not satisfy the canonical input contract."
            )
        if invocation_context.source_item_seq is None:
            raise MalformedToolArgumentsError(
                "Academic visual rendering requires a durable source MissionItem."
            )
        prism_context_text, prism_context_hash = (
            await handlers._resolve_visual_prism_context(  # noqa: SLF001
                invocation_context.workspace_id,
                raw_args,
            )
        )
        try:
            return await academic_visual.semantic_identity(
                raw_args,
                context=AcademicVisualExecutionContext(
                    workspace_id=invocation_context.workspace_id,
                    mission_id=invocation_context.mission_id,
                    caller_id=invocation_context.caller_id,
                    caller_kind=invocation_context.caller_kind.value,
                    lease_epoch=invocation_context.lease_epoch,
                    policy_version="semantic-identity-preflight",
                    prism_context_text=prism_context_text,
                    prism_context_hash=prism_context_hash,
                ),
                source_item_seq=invocation_context.source_item_seq,
                contract_hashes=invocation_context.contract_hashes,
                content_hash_refs={
                    item.ref: item.content_hash
                    for item in invocation_context.content_hash_refs
                },
                variant_ordinal=invocation_context.variant_ordinal,
            )
        except AcademicVisualRuntimeError as exc:
            raise MalformedToolArgumentsError(str(exc)) from exc
    read = _registration_factory(
        ToolKind.READ,
        SideEffectClass.NONE,
        timeout_seconds=45,
        max_attempts=2,
    )
    mutation = _registration_factory(
        ToolKind.SANDBOX_MUTATION,
        SideEffectClass.IDEMPOTENT,
        timeout_seconds=150,
        max_attempts=1,
    )
    return (
        read("workspace.list_assets", ListWorkspaceAssetsInput, handlers.list_workspace_assets, "workspace_read"),
        read("workspace.read_asset", ReadWorkspaceAssetInput, handlers.read_workspace_asset, "workspace_read"),
        read("workspace.read_input", ReadMissionInputInput, handlers.read_mission_input, "workspace_read"),
        read("workspace.list_documents", ListWorkspaceDocumentsInput, handlers.list_workspace_documents, "workspace_read"),
        read("workspace.read_document", ReadWorkspaceDocumentInput, handlers.read_workspace_document, "workspace_read"),
        read("workspace.search_source_text", SearchWorkspaceSourceTextInput, handlers.search_workspace_source_text, "workspace_read"),
        _build(
            "source.import_candidate",
            ToolKind.WRITE_CANDIDATE,
            ImportSourceCandidateInput,
            handlers.import_source_candidate,
            SideEffectClass.IDEMPOTENT,
            "source_import",
            provenance=("workspace_scope", "verification_ref", "mission_receipt"),
            timeout_seconds=60,
            max_attempts=1,
        ),
        read("source_code.list_files", ListSourceCodeFilesInput, handlers.list_source_code_files, "source_code_read"),
        read("source_code.read_file", ReadSourceCodeFileInput, handlers.read_source_code_file, "source_code_read"),
        mutation("sandbox.run_python", RunPythonToolInput, handlers.sandbox_run_python, "sandbox_compute"),
        mutation("sandbox.run_notebook", RunNotebookToolInput, handlers.sandbox_run_notebook, "sandbox_compute"),
        mutation("sandbox.smoke_check", SmokeCheckToolInput, handlers.sandbox_smoke_check, "sandbox_compute"),
        _build(
            "sandbox.install_dependencies",
            ToolKind.SANDBOX_MUTATION,
            InstallDependenciesToolInput,
            handlers.sandbox_install_dependencies,
            SideEffectClass.IDEMPOTENT,
            "sandbox_compute",
            network_profile="package_index_only",
            provenance=("mission_permission", "sandbox_receipt"),
            timeout_seconds=150,
            max_attempts=1,
        ),
        mutation("sandbox.register_dataset", RegisterDatasetToolInput, handlers.sandbox_register_dataset, "sandbox_compute"),
        mutation("sandbox.register_artifact", RegisterArtifactToolInput, handlers.sandbox_register_artifact, "sandbox_compute"),
        read("sandbox.read_artifact", ReadSandboxArtifactInput, handlers.sandbox_read_artifact, "sandbox_read"),
        read("sandbox.read_file", ReadSandboxFileInput, handlers.sandbox_read_file, "sandbox_read"),
        read("sandbox.read_output_ref", ReadSandboxOutputInput, handlers.sandbox_read_output, "sandbox_read"),
        _build(
            "artifact.create_candidate",
            ToolKind.WRITE_CANDIDATE,
            CreateArtifactCandidateInput,
            handlers.create_artifact_candidate,
            SideEffectClass.IDEMPOTENT,
            "artifact_render",
            provenance=("mission_receipt",),
            timeout_seconds=60,
            max_attempts=1,
            payload_limit_bytes=262_144,
        ),
        read(
            "artifact.read_candidate",
            ReadArtifactCandidateInput,
            handlers.read_artifact_candidate,
            "artifact_candidate_read",
        ),
        _build(
            "academic_visual.render_candidate",
            ToolKind.WRITE_CANDIDATE,
            AcademicVisualRenderInput,
            handlers.render_academic_visual_candidate,
            SideEffectClass.NON_IDEMPOTENT,
            "academic_visual_render",
            network_profile="academic_visual_scoped",
            provenance=("workspace_scope", "mission_receipt", "visual_manifest"),
            semantic_identity_builder=build_academic_visual_identity,
            timeout_seconds=150,
            max_attempts=1,
            payload_limit_bytes=524_288,
        ),
    )


def _registration_factory(
    kind: ToolKind,
    side_effect: SideEffectClass,
    *,
    timeout_seconds: float,
    max_attempts: int,
):
    def factory(tool_id, input_model, handler, permission):
        return _build(
            tool_id,
            kind,
            input_model,
            handler,
            side_effect,
            permission,
            timeout_seconds=timeout_seconds,
            max_attempts=max_attempts,
        )

    return factory


def _build(
    tool_id: str,
    kind: ToolKind,
    input_model,
    handler: Callable,
    side_effect: SideEffectClass,
    permission: str,
    *,
    network_profile: str = "none",
    provenance: tuple[str, ...] = ("workspace_scope", "mission_receipt"),
    timeout_seconds: float,
    max_attempts: int,
    payload_limit_bytes: int = 131_072,
    semantic_identity_builder: ToolSemanticIdentityBuilder | None = None,
) -> ToolRegistration:
    return build_tool_registration(
        tool_id=tool_id,
        tool_version="1.0.0",
        kind=kind,
        input_model=input_model,
        handler=handler,
        side_effect_class=side_effect,
        allowed_callers=_CALLERS,
        required_permissions=(permission,),
        network_profile=network_profile,
        budget_class="mission_standard",
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
        payload_limit_bytes=payload_limit_bytes,
        provenance_requirements=provenance,
        semantic_identity_builder=semantic_identity_builder,
    )


__all__ = [
    "ACADEMIC_VISUAL_RENDER_TOOL_IDS",
    "ARTIFACT_CANDIDATE_READ_TOOL_IDS",
    "ARTIFACT_RENDER_TOOL_IDS",
    "MISSION_TOOL_GROUPS",
    "SANDBOX_COMPUTE_TOOL_IDS",
    "SOURCE_CODE_READ_TOOL_IDS",
    "SOURCE_IMPORT_TOOL_IDS",
    "WORKSPACE_READ_TOOL_IDS",
    "build_mission_tool_registrations",
]
