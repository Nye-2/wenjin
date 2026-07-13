"""Workspace-scoped handlers behind canonical Mission tool descriptors."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from src.academic_visual_runtime import (
    AcademicVisualExecutionContext,
    AcademicVisualRenderInput,
    AcademicVisualRuntime,
    AcademicVisualRuntimeError,
)
from src.config import get_settings
from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.source import SourceImportPayload
from src.sandbox import (
    SandboxMissionProvenance,
    SandboxNetworkGrant,
    SandboxNetworkProfile,
    SandboxOperationStatus,
    SandboxRuntime,
)
from src.sandbox.contracts import (
    InstallDependenciesInput,
    ReadOutputRefInput,
    RegisterArtifactInput,
    RegisterDatasetInput,
    RunNotebookInput,
    RunPythonInput,
    SmokeCheckInput,
)
from src.sandbox.security import SandboxPathError, is_artifact_path
from src.services.search import MODEL_NATIVE_SEARCH_TOOL_ID
from src.services.workspace_uploads import workspace_upload_root
from src.tools.mission.contracts import (
    CreateArtifactCandidateInput,
    ImportSourceCandidateInput,
    InstallDependenciesToolInput,
    ListSourceCodeFilesInput,
    ListWorkspaceAssetsInput,
    ListWorkspaceDocumentsInput,
    ReadMissionReviewCandidateInput,
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
from src.tools.orchestrator import (
    ResearchToolOutcome,
    ToolDispatchError,
    ToolErrorType,
    ToolHandlerResult,
    ToolOperation,
    ToolOutcomeStatus,
    ToolReference,
    VerificationStatus,
)

_TEXT_MIME_PREFIXES = ("text/", "application/json", "application/xml", "application/x-yaml")
_SOURCE_SUFFIXES = frozenset(
    {
        ".bib",
        ".c",
        ".cc",
        ".cpp",
        ".cs",
        ".csv",
        ".css",
        ".go",
        ".h",
        ".hpp",
        ".html",
        ".java",
        ".js",
        ".json",
        ".jsx",
        ".kt",
        ".md",
        ".php",
        ".py",
        ".rb",
        ".rs",
        ".scala",
        ".sh",
        ".sql",
        ".swift",
        ".toml",
        ".ts",
        ".tsx",
        ".txt",
        ".vue",
        ".xml",
        ".yaml",
        ".yml",
    }
)


class MissionToolHandlers:
    def __init__(
        self,
        *,
        dataservice: AsyncDataServiceClient,
        sandbox: SandboxRuntime,
        academic_visual: AcademicVisualRuntime | None = None,
        asset_root: Path | None = None,
    ) -> None:
        self.dataservice = dataservice
        self.sandbox = sandbox
        self.academic_visual = academic_visual
        self.asset_root = Path(asset_root or get_settings().workspace_asset_root)

    async def list_workspace_assets(self, operation: ToolOperation, args: ListWorkspaceAssetsInput) -> ToolHandlerResult:
        assets = await self.dataservice.list_assets(
            workspace_id=await self._workspace_id(operation),
            asset_kind=args.asset_kind,
            limit=args.limit,
        )
        refs = tuple(
            ToolReference(
                ref_id=f"asset:{item.id}",
                kind="workspace_asset",
                title=item.title or item.name,
                metadata={
                    "asset_kind": item.asset_kind,
                    "mime_type": item.mime_type,
                    "size_bytes": item.size_bytes,
                    "content_hash": item.content_hash,
                    "source_id": item.source_id,
                },
            )
            for item in assets
        )
        return _success(f"Found {len(refs)} workspace asset(s).", refs=refs)

    async def read_review_candidate(
        self,
        operation: ToolOperation,
        args: ReadMissionReviewCandidateInput,
    ) -> ToolHandlerResult:
        view = await self.dataservice.missions.get_view(operation.mission_id)
        if view is None:
            raise ToolDispatchError(ToolErrorType.INVALID_INPUT, "Mission is unavailable.")
        item = next(
            (
                candidate
                for candidate in view.review_items
                if candidate.review_item_id == args.review_item_id
            ),
            None,
        )
        if item is None:
            raise ToolDispatchError(
                ToolErrorType.INVALID_INPUT,
                "Review candidate is unavailable in this Mission.",
            )
        return ToolHandlerResult(
            status=ToolOutcomeStatus.SUCCESS,
            summary=f"Loaded review candidate: {item.title}",
            evidence_refs=(
                ToolReference(
                    ref_id=f"mission-review:{item.review_item_id}",
                    kind="mission_review_candidate",
                    title=item.title,
                    metadata={
                        "review_item_id": item.review_item_id,
                        "preview_hash": item.preview_hash,
                        "preview": item.preview_json,
                    },
                ),
            ),
            verification_status=VerificationStatus.VERIFIED,
        )

    async def read_workspace_asset(self, operation: ToolOperation, args: ReadWorkspaceAssetInput) -> ToolHandlerResult:
        workspace_id = await self._workspace_id(operation)
        asset = await self.dataservice.get_asset(args.asset_id)
        if asset is None or asset.workspace_id != workspace_id or asset.deleted_at is not None:
            raise ToolDispatchError(ToolErrorType.NO_RESULTS, "The requested workspace asset was not found.")
        if (asset.mime_type and not asset.mime_type.startswith(_TEXT_MIME_PREFIXES)) or (not asset.mime_type and Path(asset.name).suffix.lower() not in _SOURCE_SUFFIXES):
            raise ToolDispatchError(ToolErrorType.INVALID_INPUT, "This asset is not directly readable text.")
        download = await self.dataservice.resolve_asset_download(asset.id)
        if download is None or download.asset.workspace_id != workspace_id or download.storage_backend != "local":
            raise ToolDispatchError(ToolErrorType.PERMISSION_DENIED, "The asset storage is not readable by this worker.")
        path = _controlled_asset_path(workspace_id, download.storage_path, root=self.asset_root)
        content, truncated = _read_bounded_file(path, offset=args.offset, max_bytes=args.max_bytes)
        ref = ToolReference(
            ref_id=f"asset:{asset.id}",
            kind="workspace_asset_text",
            title=asset.title or asset.name,
            metadata={"content": content, "offset": args.offset, "truncated": truncated, "content_hash": asset.content_hash},
        )
        return _success(f"Read {len(content.encode())} byte(s) from {asset.name}.", refs=(ref,), payload_ref=f"asset:{asset.id}")

    async def list_workspace_documents(self, operation: ToolOperation, args: ListWorkspaceDocumentsInput) -> ToolHandlerResult:
        surface = await self.dataservice.get_prism_surface(await self._workspace_id(operation))
        files = list(surface.files[: args.limit]) if surface is not None else []
        refs = tuple(
            ToolReference(
                ref_id=f"prism-file:{item.id}",
                kind="workspace_document",
                title=item.path,
                metadata={"mime_type": item.mime_type, "content_hash": item.content_hash, "file_role": item.file_role},
            )
            for item in files
            if item.deleted_at is None
        )
        return _success(f"Found {len(refs)} current document file(s).", refs=refs)

    async def read_workspace_document(self, operation: ToolOperation, args: ReadWorkspaceDocumentInput) -> ToolHandlerResult:
        workspace_id = await self._workspace_id(operation)
        result = await self.dataservice.get_prism_workspace_file(workspace_id, args.file_id)
        if result is None or result.file.workspace_id != workspace_id or result.file.deleted_at is not None:
            raise ToolDispatchError(ToolErrorType.NO_RESULTS, "The requested document file was not found.")
        version = result.current_version
        if version is None or version.content_inline is None:
            raise ToolDispatchError(ToolErrorType.NO_RESULTS, "The current document content is not available inline.")
        content = version.content_inline[args.offset : args.offset + args.max_chars]
        truncated = args.offset + len(content) < len(version.content_inline)
        ref = ToolReference(
            ref_id=f"prism-file:{result.file.id}",
            kind="workspace_document_text",
            title=result.file.path,
            metadata={"content": content, "offset": args.offset, "truncated": truncated, "content_hash": version.content_hash},
        )
        return _success(f"Read {len(content)} character(s) from {result.file.path}.", refs=(ref,), payload_ref=ref.ref_id)

    async def search_workspace_source_text(self, operation: ToolOperation, args: SearchWorkspaceSourceTextInput) -> ToolHandlerResult:
        workspace_id = await self._workspace_id(operation)
        records = await self.dataservice.search_source_text_units(
            workspace_id=workspace_id,
            query=args.query,
            source_ids=list(args.source_ids) or None,
            limit=args.limit,
        )
        bounded = [_bounded_mapping(item, maximum=4_000) for item in records[: args.limit]]
        refs = tuple(
            ToolReference(
                ref_id=f"source-text:{item.get('id') or index}",
                kind="processed_source_text",
                title=str(item.get("title") or item.get("section_title") or "Processed source text"),
                metadata=item,
            )
            for index, item in enumerate(bounded)
        )
        return _success(f"Found {len(refs)} processed source text unit(s).", refs=refs)

    async def import_source_candidate(self, operation: ToolOperation, args: ImportSourceCandidateInput) -> ToolHandlerResult:
        workspace_id = await self._workspace_id(operation)
        await self._verify_source_origin(operation, workspace_id, args)
        result = await self.dataservice.import_source(
            SourceImportPayload(
                workspace_id=workspace_id,
                source_kind=args.source_kind,
                title=args.title,
                authors_json=list(args.authors),
                year=args.year,
                venue=args.venue,
                doi=args.doi,
                url=args.url,
                abstract=args.abstract,
                ingest_kind="mission_verified",
                ingest_label=args.verification_ref,
                ingest_mission_id=operation.mission_id,
                verified_at=_utc_now(),
                library_status="candidate",
                evidence_level=("uploaded_fulltext" if args.verification_ref.startswith("asset:") else "external_verified"),
                citation_key=args.citation_key,
            )
        )
        ref = ToolReference(
            ref_id=f"source:{result.source.id}",
            kind="source_candidate",
            title=result.source.title,
            uri=result.source.url,
            metadata={"created": result.created, "verification_ref": args.verification_ref, "citation_key": result.source.citation_key},
        )
        return _success("Registered a verified source candidate for review.", refs=(ref,), payload_ref=ref.ref_id, risk="medium")

    async def list_source_code_files(self, operation: ToolOperation, args: ListSourceCodeFilesInput) -> ToolHandlerResult:
        root, asset, single_file = await self._source_root(operation, args.asset_id)
        base = _safe_descendant(root, args.relative_dir)
        paths = _list_source_files(
            base=base,
            root=root,
            single_file=single_file,
            limit=args.limit,
        )
        relative = [str(path.relative_to(root)) for path in paths[: args.limit]]
        ref = ToolReference(
            ref_id=f"source-root:{asset.id}",
            kind="source_code_listing",
            title=asset.title or asset.name,
            metadata={"files": relative, "truncated": len(paths) > len(relative)},
        )
        return _success(f"Found {len(relative)} source file(s).", refs=(ref,))

    async def read_source_code_file(self, operation: ToolOperation, args: ReadSourceCodeFileInput) -> ToolHandlerResult:
        root, asset, single_file = await self._source_root(operation, args.asset_id)
        path = _safe_descendant(root, args.relative_path)
        if not path.is_file() or path.is_symlink() or path.suffix.lower() not in _SOURCE_SUFFIXES or (single_file is not None and path != single_file):
            raise ToolDispatchError(ToolErrorType.NO_RESULTS, "The requested source file is unavailable.")
        content, truncated = _read_bounded_file(path, offset=args.offset, max_bytes=args.max_bytes)
        ref = ToolReference(
            ref_id=f"source-code:{asset.id}:{args.relative_path}",
            kind="source_code",
            title=args.relative_path,
            metadata={
                "content": content,
                "offset": args.offset,
                "truncated": truncated,
                "sha256": _sha256_file(path),
            },
        )
        return _success(f"Read {len(content.encode())} byte(s) from {args.relative_path}.", refs=(ref,))

    async def sandbox_run_python(self, operation: ToolOperation, args: RunPythonToolInput) -> ToolHandlerResult:
        return await self._sandbox(operation, RunPythonInput(**args.model_dump()))

    async def sandbox_run_notebook(self, operation: ToolOperation, args: RunNotebookToolInput) -> ToolHandlerResult:
        return await self._sandbox(operation, RunNotebookInput(**args.model_dump()))

    async def sandbox_smoke_check(self, operation: ToolOperation, _args: SmokeCheckToolInput) -> ToolHandlerResult:
        return await self._sandbox(operation, SmokeCheckInput())

    async def sandbox_install_dependencies(self, operation: ToolOperation, args: InstallDependenciesToolInput) -> ToolHandlerResult:
        grant = SandboxNetworkGrant(
            permission_request_id=args.permission_request_id,
            approved_scope="mission",
            allowed_hosts=("pypi.org", "files.pythonhosted.org"),
            expires_at=args.permission_expires_at,
        )
        return await self._sandbox(
            operation,
            InstallDependenciesInput(packages=args.packages),
            network_profile=SandboxNetworkProfile.PACKAGE_INDEX_ONLY,
            network_grant=grant,
        )

    async def sandbox_register_dataset(self, operation: ToolOperation, args: RegisterDatasetToolInput) -> ToolHandlerResult:
        return await self._sandbox(
            operation,
            RegisterDatasetInput(**args.model_dump(), uploaded_by=operation.caller_id),
        )

    async def sandbox_register_artifact(self, operation: ToolOperation, args: RegisterArtifactToolInput) -> ToolHandlerResult:
        return await self._sandbox(operation, RegisterArtifactInput(**args.model_dump()))

    async def sandbox_read_output(self, operation: ToolOperation, args: ReadSandboxOutputInput) -> ToolHandlerResult:
        return await self._sandbox(operation, ReadOutputRefInput(**args.model_dump()))

    async def create_artifact_candidate(self, operation: ToolOperation, args: CreateArtifactCandidateInput) -> ToolHandlerResult:
        candidate_id = hashlib.sha256(json.dumps({"mission_id": operation.mission_id, **args.model_dump(mode="json")}, sort_keys=True).encode()).hexdigest()
        ref = ToolReference(
            ref_id=f"artifact-candidate:{candidate_id}",
            kind="artifact_candidate",
            title=args.title,
            metadata={**args.model_dump(mode="json"), "mission_id": operation.mission_id, "operation_key": operation.operation_key, "materialized": False},
        )
        return ToolHandlerResult(
            status=ToolOutcomeStatus.SUCCESS,
            summary="Prepared a previewable artifact candidate; it has not been written to the workspace.",
            artifact_refs=(ref,),
            verification_status=VerificationStatus.VERIFIED,
            risk_level="medium",
            payload_ref=ref.ref_id,
        )

    async def render_academic_visual_candidate(
        self,
        operation: ToolOperation,
        args: AcademicVisualRenderInput,
    ) -> ToolHandlerResult:
        if self.academic_visual is None:
            raise ToolDispatchError(ToolErrorType.TOOL_UNAVAILABLE, "Academic visual runtime is not configured.")
        workspace_id = await self._workspace_id(operation)
        prism_context_text, prism_context_hash = await self._resolve_visual_prism_context(
            workspace_id,
            args,
        )
        try:
            receipt = await self.academic_visual.render_candidate(
                args,
                context=AcademicVisualExecutionContext(
                    workspace_id=workspace_id,
                    mission_id=operation.mission_id,
                    caller_id=operation.caller_id,
                    caller_kind=operation.caller_kind.value,
                    lease_epoch=operation.lease_epoch,
                    policy_version=operation.policy_snapshot_ref,
                    prism_context_text=prism_context_text,
                    prism_context_hash=prism_context_hash,
                ),
            )
        except AcademicVisualRuntimeError as exc:
            raise ToolDispatchError(
                _academic_visual_error(exc.code),
                str(exc),
                recoverable_by_model=exc.recoverable,
                retry_after_seconds=exc.retry_after_seconds,
            ) from exc
        candidate = receipt.candidate
        metadata = receipt.model_dump(mode="json", by_alias=True)
        ref = ToolReference(
            ref_id=f"academic-visual:{candidate.candidate_id}",
            kind="academic_visual_candidate",
            title=args.brief.figure_spec.title,
            metadata=metadata,
        )
        evidence_refs: tuple[ToolReference, ...] = ()
        if candidate.sandbox_artifact_ref is not None:
            evidence_refs = (
                ToolReference(
                    ref_id=candidate.sandbox_artifact_ref,
                    kind="sandbox_artifact_manifest",
                    title=f"Reproducibility receipt: {args.brief.figure_spec.title}",
                    metadata={
                        "content_hash": candidate.content_hash,
                        "preview_hash": candidate.preview_hash,
                        "reproducibility_ref": candidate.reproducibility_ref,
                        "dataset_refs": list(candidate.dataset_refs),
                        "surfaces": [
                            "figure_data_consistency",
                            "experiment_reproducibility",
                        ],
                    },
                ),
            )
        return ToolHandlerResult(
            status=ToolOutcomeStatus.SUCCESS,
            summary="Prepared an academic visual candidate for review; no workspace asset or document was changed.",
            evidence_refs=evidence_refs,
            artifact_refs=(ref,),
            verification_status=VerificationStatus.VERIFIED,
            risk_level="medium",
            payload_ref=candidate.review_preview_ref,
        )

    async def _resolve_visual_prism_context(
        self,
        workspace_id: str,
        args: AcademicVisualRenderInput,
    ) -> tuple[str | None, str | None]:
        context_ref = args.brief.prism_context_ref
        if context_ref is None:
            return None, None
        if context_ref.workspace_id != workspace_id:
            raise ToolDispatchError(
                ToolErrorType.PERMISSION_DENIED,
                "The Prism selection belongs to a different workspace.",
            )
        surface = await self.dataservice.get_prism_surface(workspace_id)
        if surface is None or surface.project.id != context_ref.prism_project_id:
            raise ToolDispatchError(ToolErrorType.NO_RESULTS, "The Prism project is unavailable.")
        result = await self.dataservice.get_prism_workspace_file(workspace_id, context_ref.file_id)
        if result is None or result.file.deleted_at is not None:
            raise ToolDispatchError(ToolErrorType.NO_RESULTS, "The Prism file is unavailable.")
        version = result.current_version
        if version is None or version.id != context_ref.base_revision_ref:
            raise ToolDispatchError(
                ToolErrorType.PROVENANCE_MISSING,
                "The Prism selection is stale; read the current document revision before rendering.",
            )
        if version.content_inline is None:
            raise ToolDispatchError(
                ToolErrorType.NO_RESULTS,
                "The selected Prism content is not available inline.",
            )
        start, end = context_ref.selection_range
        if end > len(version.content_inline) or end - start > 16_000:
            raise ToolDispatchError(
                ToolErrorType.INVALID_INPUT,
                "The Prism selection is outside the current file or exceeds the visual context limit.",
            )
        selection = version.content_inline[start:end]
        selection_hash = f"sha256:{hashlib.sha256(selection.encode()).hexdigest()}"
        if selection_hash != context_ref.selection_hash:
            raise ToolDispatchError(
                ToolErrorType.PROVENANCE_MISSING,
                "The Prism selection changed; read the current selection before rendering.",
            )
        return selection, selection_hash

    async def _workspace_id(self, operation: ToolOperation) -> str:
        mission = await self.dataservice.missions.get(operation.mission_id)
        if mission is None or not mission.workspace_id:
            raise ToolDispatchError(ToolErrorType.PERMISSION_DENIED, "Mission workspace scope is unavailable.")
        return mission.workspace_id

    async def _verify_source_origin(
        self,
        operation: ToolOperation,
        workspace_id: str,
        args: ImportSourceCandidateInput,
    ) -> None:
        kind, value = args.verification_ref.split(":", 1)
        if kind == "asset":
            asset = await self.dataservice.get_asset(value)
            if asset is None or asset.workspace_id != workspace_id or asset.deleted_at is not None:
                raise ToolDispatchError(ToolErrorType.PERMISSION_DENIED, "The source asset is outside this workspace.")
            metadata_url = str(getattr(asset, "metadata_json", {}).get("canonical_url") or "")
            if args.url and (not metadata_url or _canonical_url(args.url) != _canonical_url(metadata_url)):
                raise ToolDispatchError(
                    ToolErrorType.PROVENANCE_MISSING,
                    "The uploaded asset does not verify the supplied source URL.",
                )
        elif kind == "source":
            source = await self.dataservice.get_source_for_workspace(source_id=value, workspace_id=workspace_id)
            if source is None:
                raise ToolDispatchError(ToolErrorType.PERMISSION_DENIED, "The source record is outside this workspace.")
            if args.url and (not source.url or _canonical_url(args.url) != _canonical_url(source.url)):
                raise ToolDispatchError(
                    ToolErrorType.PROVENANCE_MISSING,
                    "The existing workspace source does not verify the supplied URL.",
                )
        elif kind == "search-receipt":
            operation_key, separator, source_id = value.partition("#")
            if not separator or not operation_key or not source_id:
                raise ToolDispatchError(ToolErrorType.PROVENANCE_MISSING, "Search receipt ref must identify an operation and source.")
            expected_url = _canonical_url(str(args.url))
            matched = False
            after_seq = 0
            while True:
                items = await self.dataservice.missions.list_items(
                    operation.mission_id,
                    after_seq=after_seq,
                    limit=100,
                    item_type="tool_operation_terminal",
                )
                for item in items:
                    if item.payload_json.get("operation_key") != operation_key:
                        continue
                    try:
                        outcome = ResearchToolOutcome.model_validate(item.payload_json.get("outcome"))
                    except ValueError:
                        continue
                    if (
                        outcome.tool_id != MODEL_NATIVE_SEARCH_TOOL_ID
                        or outcome.status is not ToolOutcomeStatus.SUCCESS
                        or outcome.verification_status
                        not in {
                            VerificationStatus.PROVIDER_RECEIPT,
                            VerificationStatus.VERIFIED,
                        }
                    ):
                        continue
                    matched = any(
                        source.source_id == source_id
                        and _canonical_url(source.canonical_url) == expected_url
                        and source.verification_status
                        in {
                            VerificationStatus.PROVIDER_RECEIPT,
                            VerificationStatus.VERIFIED,
                        }
                        for source in outcome.source_refs
                    )
                    if matched:
                        break
                if matched or len(items) < 100:
                    break
                after_seq = items[-1].seq
            if not matched:
                raise ToolDispatchError(ToolErrorType.PROVENANCE_MISSING, "No current Mission search receipt verifies this source URL.")

    async def _source_root(self, operation: ToolOperation, asset_id: str) -> tuple[Path, Any, Path | None]:
        workspace_id = await self._workspace_id(operation)
        asset = await self.dataservice.get_asset(asset_id)
        if asset is None or asset.workspace_id != workspace_id or asset.deleted_at is not None:
            raise ToolDispatchError(ToolErrorType.PERMISSION_DENIED, "The source root is outside this workspace.")
        download = await self.dataservice.resolve_asset_download(asset_id)
        if download is None or download.asset.workspace_id != workspace_id or download.storage_backend != "local":
            raise ToolDispatchError(ToolErrorType.PERMISSION_DENIED, "The source root is not locally readable.")
        path = _controlled_asset_path(workspace_id, download.storage_path, root=self.asset_root)
        root = path if path.is_dir() else path.parent
        return root, asset, (None if path.is_dir() else path)

    async def _sandbox(
        self,
        operation: ToolOperation,
        operation_input: Any,
        *,
        network_profile: SandboxNetworkProfile = SandboxNetworkProfile.NONE,
        network_grant: SandboxNetworkGrant | None = None,
    ) -> ToolHandlerResult:
        mission = await self.dataservice.missions.get(operation.mission_id)
        if mission is None or mission.workspace_id == "":
            raise ToolDispatchError(ToolErrorType.PERMISSION_DENIED, "Mission workspace scope is unavailable.")
        if isinstance(operation_input, RegisterArtifactInput) and not is_artifact_path(
            operation_input.path
        ):
            raise ToolDispatchError(
                ToolErrorType.INVALID_INPUT,
                "Only files under /workspace/outputs or /workspace/reports can be registered as reviewable artifacts; task scratch is temporary.",
                recoverable_by_model=True,
            )
        try:
            request = self.sandbox.build_request(
                provenance=SandboxMissionProvenance(
                    workspace_id=mission.workspace_id,
                    mission_id=operation.mission_id,
                    subagent_id=(operation.caller_id if operation.caller_kind.value == "subagent" else None),
                    lease_epoch=operation.lease_epoch,
                ),
                operation_input=operation_input,
                policy_version=operation.policy_snapshot_ref,
                network_profile=network_profile,
                network_grant=network_grant,
            )
        except SandboxPathError as exc:
            raise ToolDispatchError(
                ToolErrorType.INVALID_INPUT,
                f"Sandbox input is unavailable or outside its allowed workspace root: {exc}",
                recoverable_by_model=True,
            ) from exc
        result = await self.sandbox.execute(request)
        refs = tuple(
            ToolReference(
                ref_id=f"sandbox-artifact:{item.content_hash.removeprefix('sha256:')}",
                kind="sandbox_artifact_manifest",
                title=Path(item.path).name,
                metadata=item.model_dump(mode="json"),
            )
            for item in result.artifacts
        )
        evidence = tuple(
            ToolReference(
                ref_id=f"sandbox-dataset:{item.dataset_id}",
                kind="sandbox_dataset_manifest",
                title=Path(item.path).name,
                metadata=item.model_dump(mode="json"),
            )
            for item in result.datasets
        )
        if result.status is not SandboxOperationStatus.SUCCEEDED:
            raise ToolDispatchError(
                _sandbox_error(result.status),
                result.stderr_preview or "The typed sandbox operation did not complete.",
                recoverable_by_model=result.retry_disposition.value == "safe_to_retry",
            )
        output_ref = result.stdout_ref.output_ref if result.stdout_ref is not None else None
        summary = result.stdout_preview or f"Sandbox operation {result.operation.value} completed."
        return ToolHandlerResult(
            status=ToolOutcomeStatus.SUCCESS,
            summary=summary[:4000],
            evidence_refs=evidence,
            artifact_refs=refs,
            verification_status=VerificationStatus.VERIFIED,
            payload_ref=output_ref,
        )


def _success(
    summary: str,
    *,
    refs: tuple[ToolReference, ...] = (),
    payload_ref: str | None = None,
    risk: str = "low",
) -> ToolHandlerResult:
    return ToolHandlerResult(
        status=ToolOutcomeStatus.SUCCESS,
        summary=summary,
        evidence_refs=refs,
        verification_status=VerificationStatus.VERIFIED,
        payload_ref=payload_ref,
        risk_level=risk,
    )


def _academic_visual_error(code: str) -> ToolErrorType:
    if code in {"invalid_figure_strategy", "insufficient_visual_context", "provider_invalid_payload"}:
        return ToolErrorType.INVALID_INPUT
    if code in {
        "reference_asset_unavailable",
        "dataset_unavailable",
        "expected_output_missing",
        "sandbox_artifact_unavailable",
    }:
        return ToolErrorType.NO_RESULTS
    if code in {"provider_rate_limited"}:
        return ToolErrorType.RATE_LIMITED
    if code in {"provider_auth_or_config"}:
        return ToolErrorType.AUTH_REQUIRED
    if code in {"provider_timeout"}:
        return ToolErrorType.TIMEOUT
    if code in {"image_decode_failed", "image_policy_rejected", "quality_gate_failed"}:
        return ToolErrorType.UNSAFE_OUTPUT
    if code in {"reproducibility_manifest_invalid"}:
        return ToolErrorType.PROVENANCE_MISSING
    return ToolErrorType.TOOL_UNAVAILABLE


def _read_bounded_file(path: Path, *, offset: int, max_bytes: int) -> tuple[str, bool]:
    if path.is_symlink():
        raise ToolDispatchError(ToolErrorType.PERMISSION_DENIED, "Symlink files are not readable.")
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise ToolDispatchError(ToolErrorType.NO_RESULTS, "The requested file is unavailable.")
    size = resolved.stat().st_size
    with resolved.open("rb") as handle:
        handle.seek(offset)
        raw = handle.read(max_bytes + 1)
    truncated = len(raw) > max_bytes or offset + min(len(raw), max_bytes) < size
    return raw[:max_bytes].decode("utf-8", errors="replace"), truncated


def _safe_descendant(root: Path, relative: str) -> Path:
    if Path(relative).is_absolute():
        raise ToolDispatchError(ToolErrorType.INVALID_INPUT, "Source paths must be relative to the uploaded root.")
    unresolved = root / relative
    cursor = unresolved
    while cursor != root:
        if cursor.is_symlink():
            raise ToolDispatchError(ToolErrorType.PERMISSION_DENIED, "Symlink source paths are not readable.")
        if cursor.parent == cursor:
            break
        cursor = cursor.parent
    candidate = unresolved.resolve(strict=True)
    if candidate != root and root not in candidate.parents:
        raise ToolDispatchError(ToolErrorType.PERMISSION_DENIED, "Source path escapes the uploaded root.")
    return candidate


def _list_source_files(
    *,
    base: Path,
    root: Path,
    single_file: Path | None,
    limit: int,
) -> list[Path]:
    if single_file is not None:
        return [single_file] if base == root else []
    paths: list[Path] = []
    for directory, directory_names, file_names in os.walk(base, followlinks=False):
        directory_names[:] = sorted(name for name in directory_names if not (Path(directory) / name).is_symlink())
        for name in sorted(file_names):
            path = Path(directory) / name
            if path.is_symlink() or path.suffix.lower() not in _SOURCE_SUFFIXES:
                continue
            resolved = path.resolve(strict=True)
            if resolved != root and root not in resolved.parents:
                continue
            paths.append(resolved)
            if len(paths) > limit:
                return paths
    return paths


def _controlled_asset_path(workspace_id: str, stored_path: str, *, root: Path) -> Path:
    """Resolve an untrusted DB path only inside the configured workspace upload root."""
    controlled_root = root.resolve()
    scoped_root = workspace_upload_root(workspace_id, root=root).resolve()
    raw = Path(str(stored_path or "").strip())
    if not str(raw) or any(part == ".." for part in raw.parts):
        raise ToolDispatchError(ToolErrorType.PERMISSION_DENIED, "The asset path is outside the controlled upload root.")
    if raw.is_absolute():
        unresolved = raw
    elif tuple(raw.parts[: len(root.parts)]) == root.parts:
        unresolved = raw.absolute()
    else:
        unresolved = scoped_root / raw
    try:
        unresolved.relative_to(controlled_root)
    except ValueError as exc:
        raise ToolDispatchError(ToolErrorType.PERMISSION_DENIED, "The asset path is outside the controlled upload root.") from exc
    cursor = unresolved
    while cursor != controlled_root:
        if cursor.is_symlink():
            raise ToolDispatchError(ToolErrorType.PERMISSION_DENIED, "Symlink asset paths are not readable.")
        if cursor.parent == cursor:
            break
        cursor = cursor.parent
    try:
        resolved = unresolved.resolve(strict=True)
        resolved.relative_to(scoped_root)
    except (OSError, ValueError) as exc:
        raise ToolDispatchError(ToolErrorType.PERMISSION_DENIED, "The asset path is outside this workspace upload root.") from exc
    return resolved


def _bounded_mapping(value: dict[str, Any], *, maximum: int) -> dict[str, Any]:
    encoded = json.dumps(value, ensure_ascii=False, default=str)
    if len(encoded.encode()) <= maximum:
        return value
    return {"preview": encoded[:maximum], "truncated": True}


def _sandbox_error(status: SandboxOperationStatus) -> ToolErrorType:
    if status is SandboxOperationStatus.PERMISSION_REQUIRED:
        return ToolErrorType.PERMISSION_DENIED
    if status is SandboxOperationStatus.POLICY_DENIED:
        return ToolErrorType.POLICY_FORBIDDEN
    if status is SandboxOperationStatus.TIMED_OUT:
        return ToolErrorType.TIMEOUT
    if status is SandboxOperationStatus.RECONCILIATION_REQUIRED:
        return ToolErrorType.RECEIPT_UNKNOWN
    return ToolErrorType.INTERNAL_ERROR


def _canonical_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ToolDispatchError(ToolErrorType.PROVENANCE_MISSING, "Source URL is not canonical HTTP(S).")
    host = parsed.hostname.lower()
    port = parsed.port
    netloc = host if port is None else f"{host}:{port}"
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), netloc, path, parsed.query, ""))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now():
    from datetime import UTC, datetime

    return datetime.now(UTC)


__all__ = ["MissionToolHandlers"]
