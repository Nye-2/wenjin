"""Mission-linked typed sandbox operation runtime."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from src.sandbox.base import (
    CommandAuditPort,
    MissionLeaseGuard,
    PreparedSandboxJob,
    ProviderEffectState,
    ProviderNetworkConfig,
    SandboxMount,
    SandboxOperationProvider,
    SandboxReceiptState,
    SandboxReceiptStore,
)
from src.sandbox.compiler import (
    SandboxOperationCompiler,
    artifact_inputs,
    output_base_hashes,
)
from src.sandbox.contracts import (
    CommandAuditEvidence,
    InstallDependenciesInput,
    ReadOutputRefInput,
    RegisterArtifactInput,
    RegisterDatasetInput,
    RunNotebookInput,
    RunPythonInput,
    SandboxArtifactManifest,
    SandboxDatasetManifest,
    SandboxEnvironmentManifest,
    SandboxMissionProvenance,
    SandboxNetworkGrant,
    SandboxNetworkProfile,
    SandboxOperationInput,
    SandboxOperationKind,
    SandboxOperationRequest,
    SandboxOperationResult,
    SandboxOperationStatus,
    SandboxOutputSlice,
    SandboxPreflightReport,
    SandboxResourceLimits,
    SandboxRetryDisposition,
    SandboxReviewCandidate,
    content_hash_bytes,
    environment_id,
    sandbox_job_id,
    utc_now,
)
from src.sandbox.exceptions import (
    SandboxEnvironmentError,
    SandboxMaterializationError,
    SandboxOutputRefError,
    SandboxPermissionRequired,
    SandboxPolicyError,
    SandboxProviderError,
)
from src.sandbox.network import SandboxRuntimeNetworkPolicy
from src.sandbox.security import (
    SandboxPathError,
    is_artifact_path,
    is_dataset_path,
    is_script_path,
    public_relative_path,
    redact_secrets,
    require_read_before_write,
)
from src.sandbox.storage import FilesystemSandboxReceiptStore, SandboxWorkspace

ReceiptStoreFactory = Callable[[SandboxWorkspace], SandboxReceiptStore]


class SandboxRuntime:
    """Coordinates policy, idempotency, storage and one operation provider."""

    def __init__(
        self,
        *,
        provider: SandboxOperationProvider,
        command_auditor: CommandAuditPort,
        lease_guard: MissionLeaseGuard,
        sandbox_root: Path,
        image_reference: str,
        image_digest: str,
        output_ref_ttl_seconds: int = 86_400,
        compiler: SandboxOperationCompiler | None = None,
        network_policy: SandboxRuntimeNetworkPolicy | None = None,
        receipt_store_factory: ReceiptStoreFactory = FilesystemSandboxReceiptStore,
    ) -> None:
        self.provider = provider
        self.command_auditor = command_auditor
        self.lease_guard = lease_guard
        self.sandbox_root = sandbox_root
        self.image_reference = image_reference
        self.image_digest = image_digest
        self.output_ref_ttl_seconds = output_ref_ttl_seconds
        self.compiler = compiler or SandboxOperationCompiler()
        self.network_policy = network_policy or SandboxRuntimeNetworkPolicy()
        self.receipt_store_factory = receipt_store_factory

    def build_request(
        self,
        *,
        provenance: SandboxMissionProvenance,
        operation_input: SandboxOperationInput,
        policy_version: str,
        network_profile: SandboxNetworkProfile = SandboxNetworkProfile.NONE,
        network_grant: SandboxNetworkGrant | None = None,
        limits: SandboxResourceLimits | None = None,
    ) -> SandboxOperationRequest:
        workspace = self._workspace(provenance.workspace_id)
        input_hashes = self._input_hashes(workspace, operation_input)
        return SandboxOperationRequest.build(
            provenance=provenance,
            operation_input=operation_input,
            image_digest=self.image_digest,
            policy_version=policy_version,
            network_profile=network_profile,
            network_grant=network_grant,
            limits=limits,
            input_hashes=input_hashes,
        )

    async def execute(self, request: SandboxOperationRequest) -> SandboxOperationResult:
        if request.image_digest != self.image_digest:
            raise SandboxPolicyError("mission sandbox image digest does not match runtime")
        await self.lease_guard.assert_current(request.provenance)
        now = utc_now()
        workspace = self._workspace(request.provenance.workspace_id)
        job_id = sandbox_job_id(request.operation_key)
        receipt_store = self.receipt_store_factory(workspace)
        existing = await receipt_store.inspect(
            request.provenance.mission_id,
            request.operation_key,
        )
        if existing is not None:
            if existing.state == SandboxReceiptState.TERMINAL and existing.existing_result is not None:
                return existing.existing_result.model_copy(
                    update={
                        "retry_disposition": SandboxRetryDisposition.REUSE_RECEIPT,
                        "reused_receipt": True,
                    }
                )
            return self._unclaimed_result(
                request,
                status=SandboxOperationStatus.RECONCILIATION_REQUIRED,
                retry=SandboxRetryDisposition.REQUIRES_RECONCILIATION,
                stderr="An earlier delivery claimed this operation but has no terminal receipt.",
                guidance=("Reconcile the existing sandbox job before issuing another effect.",),
                now=existing.claimed_at or now,
            )
        try:
            network = self.network_policy.prepare(request, now=now)
        except SandboxPermissionRequired as exc:
            return self._unclaimed_result(
                request,
                status=SandboxOperationStatus.PERMISSION_REQUIRED,
                retry=SandboxRetryDisposition.DO_NOT_RETRY,
                stderr=str(exc),
                guidance=("Resume with a current MissionRuntime network permission.",),
                now=now,
            )
        except SandboxPolicyError as exc:
            return self._unclaimed_result(
                request,
                status=SandboxOperationStatus.POLICY_DENIED,
                retry=SandboxRetryDisposition.DO_NOT_RETRY,
                stderr=str(exc),
                guidance=("Reconfigure the sandbox egress policy before continuing.",),
                now=now,
            )
        claim = await receipt_store.claim(request, sandbox_job_id=job_id)
        if claim.state == SandboxReceiptState.TERMINAL and claim.existing_result is not None:
            return claim.existing_result.model_copy(
                update={
                    "retry_disposition": SandboxRetryDisposition.REUSE_RECEIPT,
                    "reused_receipt": True,
                }
            )
        if not claim.acquired:
            return self._unclaimed_result(
                request,
                status=SandboxOperationStatus.RECONCILIATION_REQUIRED,
                retry=SandboxRetryDisposition.REQUIRES_RECONCILIATION,
                stderr="An earlier delivery claimed this operation but has no terminal receipt.",
                guidance=("Reconcile the existing sandbox job before issuing another effect.",),
                now=claim.claimed_at or now,
            )
        try:
            self._verify_input_hashes(workspace, request)
            workspace_size = workspace.public_size_bytes()
        except SandboxPathError as exc:
            result = self._terminal_failure(
                request,
                job_id=job_id,
                status=SandboxOperationStatus.POLICY_DENIED,
                retry=SandboxRetryDisposition.DO_NOT_RETRY,
                stderr=str(exc),
                guidance=("Rebuild the operation from the current workspace inputs.",),
                started_at=now,
            )
            await receipt_store.finalize(result)
            return result
        if workspace_size > request.limits.workspace_bytes:
            result = self._terminal_failure(
                request,
                job_id=job_id,
                status=SandboxOperationStatus.POLICY_DENIED,
                retry=SandboxRetryDisposition.DO_NOT_RETRY,
                stderr="Workspace quota is already exceeded.",
                guidance=("Remove or archive files before starting another operation.",),
                started_at=now,
            )
            await receipt_store.finalize(result)
            return result
        try:
            if request.operation in {
                SandboxOperationKind.REGISTER_DATASET,
                SandboxOperationKind.REGISTER_ARTIFACT,
                SandboxOperationKind.READ_OUTPUT_REF,
            }:
                await self.lease_guard.assert_current(request.provenance)
                result = await self._execute_metadata_operation(
                    workspace=workspace,
                    request=request,
                    job_id=job_id,
                    now=now,
                    receipt_store=receipt_store,
                )
            else:
                result = await self._execute_provider_operation(
                    workspace=workspace,
                    request=request,
                    job_id=job_id,
                    network=network,
                    now=now,
                )
        except (SandboxPathError, SandboxEnvironmentError, SandboxOutputRefError) as exc:
            result = self._terminal_failure(
                request,
                job_id=job_id,
                status=SandboxOperationStatus.POLICY_DENIED,
                retry=SandboxRetryDisposition.DO_NOT_RETRY,
                stderr=str(exc),
                guidance=("Correct the sandbox path, base hash, environment, or output reference.",),
                started_at=now,
            )
        except SandboxMaterializationError as exc:
            result = self._terminal_failure(
                request,
                job_id=job_id,
                status=SandboxOperationStatus.RECONCILIATION_REQUIRED,
                retry=SandboxRetryDisposition.REQUIRES_RECONCILIATION,
                stderr=str(exc),
                guidance=("Reconcile the retained sandbox staging area before continuing.",),
                started_at=now,
            )
        except PermissionError:
            raise
        except OSError as exc:
            result = self._terminal_failure(
                request,
                job_id=job_id,
                status=SandboxOperationStatus.RECONCILIATION_REQUIRED,
                retry=SandboxRetryDisposition.REQUIRES_RECONCILIATION,
                stderr=f"Sandbox storage transition failed: {exc}",
                guidance=("Reconcile workspace and receipt state before continuing.",),
                started_at=now,
            )
        await receipt_store.finalize(result)
        return result

    async def read_artifact_bytes(
        self,
        *,
        workspace_id: str,
        path: str,
        expected_content_hash: str,
        max_bytes: int,
    ) -> bytes:
        """Read one completed public artifact through the sandbox integrity boundary."""

        if not is_artifact_path(path):
            raise SandboxPathError("sandbox preview source must be a reviewable artifact path")

        def read() -> bytes:
            content = self._workspace(workspace_id).read_bytes(path)
            if not content or len(content) > max_bytes:
                raise SandboxPathError("sandbox preview source exceeds its byte boundary")
            if content_hash_bytes(content) != expected_content_hash:
                raise SandboxPathError("sandbox preview source changed after its operation receipt")
            return content

        return await asyncio.to_thread(read)

    async def preflight(self, *, release_gate: bool) -> SandboxPreflightReport:
        return await self.provider.preflight(release_gate=release_gate)

    @staticmethod
    def review_candidates(
        result: SandboxOperationResult,
    ) -> tuple[SandboxReviewCandidate, ...]:
        return tuple(
            SandboxReviewCandidate(
                artifact=artifact,
                suggested_title=Path(artifact.path).name,
            )
            for artifact in result.artifacts
        )

    async def _execute_provider_operation(
        self,
        *,
        workspace: SandboxWorkspace,
        request: SandboxOperationRequest,
        job_id: str,
        network: ProviderNetworkConfig,
        now: datetime,
    ) -> SandboxOperationResult:
        environment, environment_path = self._resolve_environment(workspace, request, now=now)
        command = self.compiler.compile(request, environment=environment)
        audit = self.command_auditor.audit(command, request)
        if audit.decision != "allow":
            return self._terminal_failure(
                request,
                job_id=job_id,
                status=SandboxOperationStatus.POLICY_DENIED,
                retry=SandboxRetryDisposition.DO_NOT_RETRY,
                stderr="Sandbox command policy denied the compiled operation.",
                guidance=("Replan using an allowed typed sandbox operation.",),
                started_at=now,
                command_audit=audit,
            )
        self._prepare_public_inputs(workspace, request)
        environment_staging = workspace.create_environment_staging(request.operation_key) if request.operation == SandboxOperationKind.INSTALL_DEPENDENCIES else None
        output_staging = (
            workspace.create_output_staging(request.operation_key)
            if request.operation
            in {
                SandboxOperationKind.RUN_PYTHON,
                SandboxOperationKind.RUN_NOTEBOOK,
            }
            else None
        )
        mounts = self._mounts(
            workspace,
            request=request,
            environment_path=environment_path,
            environment_staging=environment_staging,
            output_staging=output_staging,
        )
        prepared = PreparedSandboxJob(
            request=request,
            sandbox_job_id=job_id,
            command=command,
            command_audit=audit,
            mounts=mounts,
            network=network,
            image_reference=self.image_reference,
        )
        await self.lease_guard.assert_current(request.provenance)
        try:
            provider_result = await self.provider.execute(prepared)
        except SandboxPolicyError as exc:
            workspace.discard_output_staging(output_staging)
            workspace.discard_environment_staging(environment_staging)
            return self._terminal_failure(
                request,
                job_id=job_id,
                status=SandboxOperationStatus.POLICY_DENIED,
                retry=SandboxRetryDisposition.DO_NOT_RETRY,
                stderr=str(exc),
                guidance=("Correct the provider policy or prepared operation before retrying.",),
                started_at=now,
                command_audit=audit,
            )
        except SandboxProviderError as exc:
            if not exc.effect_uncertain:
                workspace.discard_output_staging(output_staging)
                workspace.discard_environment_staging(environment_staging)
            retry = SandboxRetryDisposition.REQUIRES_RECONCILIATION if exc.effect_uncertain else SandboxRetryDisposition.SAFE_TO_RETRY
            status = SandboxOperationStatus.RECONCILIATION_REQUIRED if exc.effect_uncertain else SandboxOperationStatus.FAILED
            return self._terminal_failure(
                request,
                job_id=job_id,
                status=status,
                retry=retry,
                stderr=str(exc),
                guidance=("Inspect the existing receipt and workspace before retrying." if exc.effect_uncertain else "A new mission item may retry after provider recovery.",),
                started_at=now,
                command_audit=audit,
            )
        finished_at = provider_result.finished_at or utc_now()
        stdout_text = redact_secrets(provider_result.stdout.decode("utf-8", errors="replace"))
        stderr_text = redact_secrets(provider_result.stderr.decode("utf-8", errors="replace"))
        stdout_bytes = stdout_text.encode()
        stderr_bytes = stderr_text.encode()
        stdout_preview, stdout_preview_truncated = _bounded_preview(
            stdout_text,
            request.limits.stream_preview_chars,
        )
        stderr_preview, stderr_preview_truncated = _bounded_preview(
            stderr_text,
            request.limits.stream_preview_chars,
        )
        stdout_truncated = provider_result.stdout_capture_truncated or stdout_preview_truncated
        stderr_truncated = provider_result.stderr_capture_truncated or stderr_preview_truncated
        try:
            stdout_ref = workspace.write_output_ref(stream="stdout", content=stdout_bytes, now=finished_at) if stdout_truncated else None
            stderr_ref = workspace.write_output_ref(stream="stderr", content=stderr_bytes, now=finished_at) if stderr_truncated else None
        except OSError as exc:
            return self._terminal_failure(
                request,
                job_id=job_id,
                status=SandboxOperationStatus.RECONCILIATION_REQUIRED,
                retry=SandboxRetryDisposition.REQUIRES_RECONCILIATION,
                stderr=f"Provider completed but output receipt persistence failed: {exc}",
                guidance=("Reconcile provider outputs before creating another operation.",),
                started_at=provider_result.started_at or now,
                command_audit=audit,
            )
        if provider_result.effect_state == ProviderEffectState.UNCERTAIN:
            return SandboxOperationResult(
                operation_key=request.operation_key,
                sandbox_job_id=job_id,
                provenance=request.provenance,
                operation=request.operation,
                image_digest=request.image_digest,
                policy_version=request.policy_version,
                command_schema_version=request.command_schema_version,
                status=SandboxOperationStatus.RECONCILIATION_REQUIRED,
                retry_disposition=SandboxRetryDisposition.REQUIRES_RECONCILIATION,
                exit_code=provider_result.exit_code,
                stdout_preview=stdout_preview,
                stderr_preview=stderr_preview,
                stdout_ref=stdout_ref,
                stderr_ref=stderr_ref,
                stdout_truncated=stdout_truncated,
                stderr_truncated=stderr_truncated,
                command_audit=audit,
                recovery_guidance=("Reconcile the provider receipt before retrying.",),
                started_at=provider_result.started_at or now,
                finished_at=finished_at,
            )
        if provider_result.timed_out:
            workspace.discard_output_staging(output_staging)
            workspace.discard_environment_staging(environment_staging)
            return SandboxOperationResult(
                operation_key=request.operation_key,
                sandbox_job_id=job_id,
                provenance=request.provenance,
                operation=request.operation,
                image_digest=request.image_digest,
                policy_version=request.policy_version,
                command_schema_version=request.command_schema_version,
                status=SandboxOperationStatus.TIMED_OUT,
                retry_disposition=SandboxRetryDisposition.REQUIRES_RECONCILIATION,
                exit_code=None,
                stdout_preview=stdout_preview,
                stderr_preview=stderr_preview,
                stdout_ref=stdout_ref,
                stderr_ref=stderr_ref,
                stdout_truncated=stdout_truncated,
                stderr_truncated=stderr_truncated,
                command_audit=audit,
                recovery_guidance=("Inspect partial workspace outputs before creating a revised operation.",),
                started_at=provider_result.started_at or now,
                finished_at=finished_at,
            )
        if provider_result.exit_code != 0:
            workspace.discard_output_staging(output_staging)
            workspace.discard_environment_staging(environment_staging)
            return SandboxOperationResult(
                operation_key=request.operation_key,
                sandbox_job_id=job_id,
                provenance=request.provenance,
                operation=request.operation,
                image_digest=request.image_digest,
                policy_version=request.policy_version,
                command_schema_version=request.command_schema_version,
                status=SandboxOperationStatus.FAILED,
                retry_disposition=SandboxRetryDisposition.DO_NOT_RETRY,
                exit_code=provider_result.exit_code,
                stdout_preview=stdout_preview,
                stderr_preview=stderr_preview,
                stdout_ref=stdout_ref,
                stderr_ref=stderr_ref,
                stdout_truncated=stdout_truncated,
                stderr_truncated=stderr_truncated,
                command_audit=audit,
                recovery_guidance=(
                    "Revise the typed input or script and create a new mission item.",
                    "Reuse existing datasets and inspect bounded logs before rerunning.",
                ),
                started_at=provider_result.started_at or now,
                finished_at=finished_at,
            )
        await self.lease_guard.assert_current(request.provenance)
        if environment_staging is not None:
            operation_input = request.operation_input
            assert isinstance(operation_input, InstallDependenciesInput)
            try:
                environment, _ = workspace.finalize_environment(
                    staging=environment_staging,
                    image_digest=request.image_digest,
                    runtime=operation_input.runtime,
                    requested_packages=operation_input.packages,
                    created_at=finished_at,
                )
            except SandboxEnvironmentError as exc:
                return self._terminal_failure(
                    request,
                    job_id=job_id,
                    status=SandboxOperationStatus.RECONCILIATION_REQUIRED,
                    retry=SandboxRetryDisposition.REQUIRES_RECONCILIATION,
                    stderr=str(exc),
                    guidance=("Inspect and clean the unsealed environment staging area.",),
                    started_at=provider_result.started_at or now,
                    command_audit=audit,
                )
        merged_paths: tuple[str, ...] = ()
        if output_staging is not None:
            try:
                merged_paths = workspace.merge_staged_outputs(
                    staging=output_staging,
                    output_base_hashes=output_base_hashes(request.operation_input),
                    max_workspace_bytes=request.limits.workspace_bytes,
                )
            except SandboxPathError as exc:
                workspace.discard_output_staging(output_staging)
                return self._terminal_failure(
                    request,
                    job_id=job_id,
                    status=SandboxOperationStatus.FAILED,
                    retry=SandboxRetryDisposition.DO_NOT_RETRY,
                    stderr=str(exc),
                    guidance=("Read the current artifact and provide its base content hash before replacing it.",),
                    started_at=provider_result.started_at or now,
                    command_audit=audit,
                )
            except SandboxMaterializationError as exc:
                return self._terminal_failure(
                    request,
                    job_id=job_id,
                    status=SandboxOperationStatus.RECONCILIATION_REQUIRED,
                    retry=SandboxRetryDisposition.REQUIRES_RECONCILIATION,
                    stderr=str(exc),
                    guidance=("Reconcile partially materialized artifacts before continuing.",),
                    started_at=provider_result.started_at or now,
                    command_audit=audit,
                )
        source_script, dataset_paths = artifact_inputs(request.operation_input)
        try:
            artifacts = workspace.artifact_manifests_for_paths(
                paths=merged_paths,
                request=request,
                sandbox_job_id=job_id,
                sandbox_environment_id=environment.environment_id,
                source_script=source_script,
                dataset_paths=dataset_paths,
                stdout_truncated=stdout_truncated,
                stderr_truncated=stderr_truncated,
                created_at=finished_at,
            )
        except SandboxPathError as exc:
            return self._terminal_failure(
                request,
                job_id=job_id,
                status=SandboxOperationStatus.RECONCILIATION_REQUIRED,
                retry=SandboxRetryDisposition.REQUIRES_RECONCILIATION,
                stderr=str(exc),
                guidance=("Remove the unsafe output and rerun from a new mission item.",),
                started_at=provider_result.started_at or now,
                command_audit=audit,
            )
        return SandboxOperationResult(
            operation_key=request.operation_key,
            sandbox_job_id=job_id,
            provenance=request.provenance,
            operation=request.operation,
            image_digest=request.image_digest,
            policy_version=request.policy_version,
            command_schema_version=request.command_schema_version,
            status=SandboxOperationStatus.SUCCEEDED,
            retry_disposition=SandboxRetryDisposition.REUSE_RECEIPT,
            exit_code=provider_result.exit_code,
            stdout_preview=stdout_preview,
            stderr_preview=stderr_preview,
            stdout_ref=stdout_ref,
            stderr_ref=stderr_ref,
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
            artifacts=artifacts,
            environment=environment,
            command_audit=audit,
            started_at=provider_result.started_at or now,
            finished_at=finished_at,
        )

    async def _execute_metadata_operation(
        self,
        *,
        workspace: SandboxWorkspace,
        request: SandboxOperationRequest,
        job_id: str,
        now: datetime,
        receipt_store: SandboxReceiptStore,
    ) -> SandboxOperationResult:
        operation_input = request.operation_input
        artifacts: tuple[SandboxArtifactManifest, ...] = ()
        datasets: tuple[SandboxDatasetManifest, ...] = ()
        stdout_preview = ""
        stdout_truncated = False
        output_slice: SandboxOutputSlice | None = None
        if isinstance(operation_input, RegisterDatasetInput):
            datasets = (
                workspace.register_dataset(
                    path=operation_input.path,
                    source=operation_input.source,
                    license_name=operation_input.license,
                    pii_risk=operation_input.pii_risk,
                    uploaded_by=operation_input.uploaded_by,
                    observed_at=operation_input.observed_at,
                ),
            )
        elif isinstance(operation_input, RegisterArtifactInput):
            producing_result = await receipt_store.get(
                request.provenance.mission_id,
                operation_input.producing_operation_key,
            )
            if producing_result is None or producing_result.status != SandboxOperationStatus.SUCCEEDED or producing_result.provenance.workspace_id != request.provenance.workspace_id:
                raise SandboxPathError("artifact producer has no successful workspace receipt")
            produced_artifact = next(
                (artifact for artifact in producing_result.artifacts if artifact.path == operation_input.path),
                None,
            )
            if produced_artifact is None:
                raise SandboxPathError("artifact is absent from the producer receipt")
            if workspace.content_hash(operation_input.path) != produced_artifact.content_hash:
                raise SandboxPathError("artifact changed after the producer receipt")
            artifacts = (produced_artifact,)
        elif isinstance(operation_input, ReadOutputRefInput):
            content = workspace.read_output_ref(operation_input.output_ref, now=now)
            chunk = content[operation_input.offset : operation_input.offset + operation_input.max_bytes]
            stdout_preview = chunk.decode("utf-8", errors="replace")
            stdout_truncated = operation_input.offset + len(chunk) < len(content)
            output_slice = SandboxOutputSlice(
                output_ref=operation_input.output_ref,
                offset=operation_input.offset,
                returned_bytes=len(chunk),
                next_offset=(operation_input.offset + len(chunk) if stdout_truncated else None),
            )
        return SandboxOperationResult(
            operation_key=request.operation_key,
            sandbox_job_id=job_id,
            provenance=request.provenance,
            operation=request.operation,
            image_digest=request.image_digest,
            policy_version=request.policy_version,
            command_schema_version=request.command_schema_version,
            status=SandboxOperationStatus.SUCCEEDED,
            retry_disposition=SandboxRetryDisposition.REUSE_RECEIPT,
            exit_code=0,
            stdout_preview=stdout_preview,
            stdout_truncated=stdout_truncated,
            output_slice=output_slice,
            artifacts=artifacts,
            datasets=datasets,
            started_at=now,
            finished_at=utc_now(),
        )

    def _prepare_public_inputs(
        self,
        workspace: SandboxWorkspace,
        request: SandboxOperationRequest,
    ) -> None:
        operation_input = request.operation_input
        if isinstance(operation_input, RunPythonInput):
            if not is_script_path(operation_input.script_path) or not operation_input.script_path.endswith(".py"):
                raise SandboxPathError("run_python script must be a .py file under /workspace/scripts")
            workspace.write_text(
                operation_input.script_path,
                operation_input.script,
                expected_content_hash=operation_input.base_content_hash,
            )
        elif isinstance(operation_input, RunNotebookInput):
            notebook_relative = public_relative_path(operation_input.notebook_path)
            if notebook_relative.parts[0] not in {"main", "datasets", "scripts"} or not operation_input.notebook_path.endswith(".ipynb"):
                raise SandboxPathError("notebook input must be a public .ipynb file")
            if not is_artifact_path(operation_input.output_path) or not operation_input.output_path.endswith(".ipynb"):
                raise SandboxPathError("notebook output must be a reviewable .ipynb artifact path")
            output = workspace.resolve_public_path(operation_input.output_path)
            require_read_before_write(
                output,
                expected_content_hash=operation_input.base_content_hash,
            )

    def _resolve_environment(
        self,
        workspace: SandboxWorkspace,
        request: SandboxOperationRequest,
        *,
        now: datetime,
    ) -> tuple[SandboxEnvironmentManifest, Path | None]:
        operation_input = request.operation_input
        selected_id = operation_input.environment_id if isinstance(operation_input, RunPythonInput | RunNotebookInput) else None
        if selected_id:
            manifest = workspace.load_environment(selected_id)
            if manifest.image_digest != request.image_digest:
                raise SandboxEnvironmentError("environment image digest does not match mission")
            return manifest, workspace.environment_path(selected_id)
        runtime = "python3.13"
        lock = b""
        return (
            SandboxEnvironmentManifest(
                environment_id=environment_id(
                    image_digest=request.image_digest,
                    runtime=runtime,
                    lock_content=lock,
                ),
                image_digest=request.image_digest,
                runtime=runtime,
                lock_hash=content_hash_bytes(lock),
                created_at=now,
                sealed=True,
            ),
            None,
        )

    def _mounts(
        self,
        workspace: SandboxWorkspace,
        *,
        request: SandboxOperationRequest,
        environment_path: Path | None,
        environment_staging: Path | None,
        output_staging: Path | None,
    ) -> tuple[SandboxMount, ...]:
        if request.operation == SandboxOperationKind.INSTALL_DEPENDENCIES:
            assert environment_staging is not None
            return (
                SandboxMount(
                    source=environment_staging,
                    target="/opt/wenjin/env",
                    read_only=False,
                ),
            )
        mounts: list[SandboxMount] = []
        for name in ("main", "datasets", "scripts", "outputs", "reports"):
            staged_output = output_staging is not None and name in {"outputs", "reports"}
            source = output_staging / name if output_staging is not None and name in {"outputs", "reports"} else workspace.paths.public_root / name
            mounts.append(
                SandboxMount(
                    source=source,
                    target=f"/workspace/{name}",
                    read_only=not staged_output,
                )
            )
        if environment_path is not None:
            mounts.append(
                SandboxMount(
                    source=environment_path,
                    target="/opt/wenjin/env",
                    read_only=True,
                )
            )
        return tuple(mounts)

    def _input_hashes(
        self,
        workspace: SandboxWorkspace,
        operation_input: SandboxOperationInput,
    ) -> dict[str, str]:
        hashes: dict[str, str] = {}
        if isinstance(operation_input, RunPythonInput):
            hashes["script"] = content_hash_bytes(operation_input.script.encode())
            for path in operation_input.dataset_paths:
                if not is_dataset_path(path):
                    raise SandboxPathError("dataset inputs must live under /workspace/datasets")
                hashes[f"dataset:{path}"] = workspace.content_hash(path)
        elif isinstance(operation_input, RunNotebookInput):
            hashes["notebook"] = workspace.content_hash(operation_input.notebook_path)
            for path in operation_input.dataset_paths:
                if not is_dataset_path(path):
                    raise SandboxPathError("dataset inputs must live under /workspace/datasets")
                hashes[f"dataset:{path}"] = workspace.content_hash(path)
        elif isinstance(operation_input, RegisterDatasetInput):
            hashes["dataset"] = workspace.content_hash(operation_input.path)
        elif isinstance(operation_input, RegisterArtifactInput):
            hashes["artifact"] = workspace.content_hash(operation_input.path)
        return hashes

    def _verify_input_hashes(
        self,
        workspace: SandboxWorkspace,
        request: SandboxOperationRequest,
    ) -> None:
        actual = self._input_hashes(workspace, request.operation_input)
        if actual != request.input_hashes:
            raise SandboxPathError("sandbox operation inputs changed after dispatch")

    def _workspace(self, workspace_id: str) -> SandboxWorkspace:
        workspace = SandboxWorkspace(
            sandbox_root=self.sandbox_root,
            workspace_id=workspace_id,
            output_ref_ttl_seconds=self.output_ref_ttl_seconds,
        )
        workspace.initialize()
        return workspace

    def _unclaimed_result(
        self,
        request: SandboxOperationRequest,
        *,
        status: SandboxOperationStatus,
        retry: SandboxRetryDisposition,
        stderr: str,
        guidance: tuple[str, ...],
        now: datetime,
    ) -> SandboxOperationResult:
        return SandboxOperationResult(
            operation_key=request.operation_key,
            sandbox_job_id=sandbox_job_id(request.operation_key),
            provenance=request.provenance,
            operation=request.operation,
            image_digest=request.image_digest,
            policy_version=request.policy_version,
            command_schema_version=request.command_schema_version,
            status=status,
            retry_disposition=retry,
            stderr_preview=redact_secrets(stderr),
            recovery_guidance=guidance,
            started_at=now,
            finished_at=utc_now(),
        )

    def _terminal_failure(
        self,
        request: SandboxOperationRequest,
        *,
        job_id: str,
        status: SandboxOperationStatus,
        retry: SandboxRetryDisposition,
        stderr: str,
        guidance: tuple[str, ...],
        started_at: datetime,
        command_audit: CommandAuditEvidence | None = None,
    ) -> SandboxOperationResult:
        return SandboxOperationResult(
            operation_key=request.operation_key,
            sandbox_job_id=job_id,
            provenance=request.provenance,
            operation=request.operation,
            image_digest=request.image_digest,
            policy_version=request.policy_version,
            command_schema_version=request.command_schema_version,
            status=status,
            retry_disposition=retry,
            stderr_preview=redact_secrets(stderr),
            command_audit=command_audit,
            recovery_guidance=guidance,
            started_at=started_at,
            finished_at=utc_now(),
        )


def _bounded_preview(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    half = max(1, (limit - 32) // 2)
    return f"{text[:half]}\n...[output truncated]...\n{text[-half:]}", True
