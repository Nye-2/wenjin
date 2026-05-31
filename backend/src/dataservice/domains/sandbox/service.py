"""Sandbox aggregate domain service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.common.errors import DataServiceNotFoundError, DataServiceValidationError
from src.dataservice.domains.review.contracts import ReviewBatchCreateCommand, ReviewItemCreateCommand
from src.dataservice.domains.review.service import DataServiceReviewService
from src.dataservice.domains.sandbox.contracts import (
    SandboxArtifactCreateCommand,
    SandboxArtifactProjection,
    SandboxEnvironmentCreateCommand,
    SandboxEnvironmentProjection,
    SandboxEnvironmentUpdateCommand,
    SandboxJobCreateCommand,
    SandboxJobProjection,
    SandboxJobUpdateCommand,
    SandboxLeaseAcquireCommand,
    SandboxLeaseProjection,
    SandboxLeaseReleaseCommand,
    SandboxLeaseRenewCommand,
    default_resource_limits,
    default_sandbox_policy,
)
from src.dataservice.domains.sandbox.policy import (
    validate_python_job_contract,
    validate_sandbox_policy,
)
from src.dataservice.domains.sandbox.projection import (
    artifact_to_projection,
    environment_to_projection,
    job_to_projection,
    lease_to_projection,
)
from src.dataservice.domains.sandbox.repository import SandboxRepository


class SandboxDataDomainService:
    """DataService-owned sandbox metadata operations."""

    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self.session = session
        self.autocommit = autocommit
        self.repository = SandboxRepository(session)
        self.review_service = DataServiceReviewService(session, autocommit=False)

    async def create_environment(
        self,
        command: SandboxEnvironmentCreateCommand,
    ) -> SandboxEnvironmentProjection:
        policy_json = dict(command.policy_json or default_sandbox_policy())
        resource_limits_json = dict(command.resource_limits_json or default_resource_limits())
        validate_sandbox_policy(policy_json)
        sandbox_id = command.sandbox_id or _workspace_sandbox_id(command.workspace_id)
        if command.state == "active":
            existing = await self.repository.get_active_environment(command.workspace_id)
            if existing is not None:
                raise DataServiceValidationError(
                    "active sandbox environment already exists",
                    detail={"workspace_id": command.workspace_id},
                )
        metadata_json = dict(command.metadata_json or {})
        metadata_json.setdefault("provider_key", sandbox_id)
        record = self.repository.create_environment(
            {
                "workspace_id": command.workspace_id,
                "sandbox_id": sandbox_id,
                "provider": command.provider,
                "state": command.state,
                "workspace_path": command.workspace_path,
                "network_policy": command.network_policy,
                "policy_json": policy_json,
                "resource_limits_json": resource_limits_json,
                "created_by": command.created_by,
                "last_active_at": datetime.now(UTC) if command.state == "active" else None,
                "released_at": None if command.state == "active" else datetime.now(UTC),
                "metadata_json": metadata_json,
            }
        )
        await self._finish()
        return environment_to_projection(record)

    async def get_or_create_environment(
        self,
        command: SandboxEnvironmentCreateCommand,
    ) -> SandboxEnvironmentProjection:
        existing = await self.repository.get_active_environment(command.workspace_id)
        if existing is not None:
            existing.last_active_at = datetime.now(UTC)
            await self._finish()
            return environment_to_projection(existing)
        return await self.create_environment(command)

    async def get_environment(self, environment_id: str) -> SandboxEnvironmentProjection | None:
        record = await self.repository.get_environment(environment_id)
        return environment_to_projection(record) if record is not None else None

    async def list_environments(
        self,
        *,
        workspace_id: str,
        state: str | None = None,
        limit: int = 50,
    ) -> list[SandboxEnvironmentProjection]:
        return [
            environment_to_projection(record)
            for record in await self.repository.list_environments(
                workspace_id=workspace_id,
                state=state,
                limit=limit,
            )
        ]

    async def update_environment(
        self,
        environment_id: str,
        command: SandboxEnvironmentUpdateCommand,
    ) -> SandboxEnvironmentProjection | None:
        record = await self.repository.get_environment(environment_id)
        if record is None:
            return None
        now = datetime.now(UTC)
        if command.state is not None:
            record.state = command.state
            record.last_active_at = now if command.state == "active" else record.last_active_at
            record.released_at = now if command.state == "stopped" else record.released_at
        for field in ("workspace_path", "network_policy", "metadata_json"):
            value = getattr(command, field)
            if value is not None:
                setattr(record, field, dict(value) if field == "metadata_json" else value)
        if command.policy_json is not None:
            validate_sandbox_policy(command.policy_json)
            record.policy_json = dict(command.policy_json)
        if command.resource_limits_json is not None:
            record.resource_limits_json = dict(command.resource_limits_json)
        record.updated_at = now
        await self._finish()
        return environment_to_projection(record)

    async def create_job(self, command: SandboxJobCreateCommand) -> SandboxJobProjection:
        policy_json = dict(command.policy_json or default_sandbox_policy())
        resource_limits_json = dict(command.resource_limits_json or default_resource_limits())
        metadata_json = dict(command.metadata_json or {})
        package_specs = metadata_json.get("packages")
        if not isinstance(package_specs, list):
            package_specs = None
        validate_python_job_contract(
            operation=command.operation,
            language=command.language,
            command=command.command,
            policy_json=policy_json,
            package_specs=package_specs,
        )
        environment = await self.repository.get_environment(command.sandbox_environment_id)
        if environment is None:
            raise DataServiceNotFoundError(
                "Sandbox environment not found",
                detail={"sandbox_environment_id": command.sandbox_environment_id},
            )
        if environment.workspace_id != command.workspace_id:
            raise DataServiceValidationError(
                "Sandbox job workspace does not match environment workspace",
                detail={
                    "workspace_id": command.workspace_id,
                    "environment_workspace_id": environment.workspace_id,
                },
            )
        now = datetime.now(UTC)
        record = self.repository.create_job(
            {
                "workspace_id": command.workspace_id,
                "sandbox_environment_id": command.sandbox_environment_id,
                "execution_id": command.execution_id,
                "execution_node_id": command.execution_node_id,
                "operation": command.operation,
                "billable": command.billable,
                "language": command.language,
                "runtime_image": command.runtime_image,
                "command": command.command,
                "script_hash": command.script_hash,
                "input_hashes_json": dict(command.input_hashes_json or {}),
                "network_policy": command.network_policy,
                "resource_limits_json": resource_limits_json,
                "policy_json": policy_json,
                "status": "queued",
                "metadata_json": metadata_json,
            }
        )
        environment.last_active_at = now
        await self._finish()
        return job_to_projection(record)

    async def acquire_lease(self, command: SandboxLeaseAcquireCommand) -> SandboxLeaseProjection:
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=command.ttl_seconds)
        existing = await self.repository.get_lease_for_update(command.workspace_id)
        metadata_json = dict(command.metadata_json or {})
        if existing is not None:
            existing_expires_at = _ensure_aware(existing.expires_at)
            if existing_expires_at > now and existing.lease_token != command.lease_token:
                raise DataServiceValidationError(
                    "workspace sandbox is busy",
                    detail={
                        "workspace_id": command.workspace_id,
                        "holder_job_id": existing.holder_job_id,
                        "expires_at": existing.expires_at.isoformat(),
                    },
                )
            existing.sandbox_environment_id = command.sandbox_environment_id
            existing.holder_job_id = command.holder_job_id
            existing.holder_execution_id = command.holder_execution_id
            existing.lease_token = command.lease_token
            existing.expires_at = expires_at
            existing.metadata_json = metadata_json
            existing.updated_at = now
            await self._finish()
            return lease_to_projection(existing)

        record = self.repository.create_lease(
            {
                "workspace_id": command.workspace_id,
                "sandbox_environment_id": command.sandbox_environment_id,
                "holder_job_id": command.holder_job_id,
                "holder_execution_id": command.holder_execution_id,
                "lease_token": command.lease_token,
                "expires_at": expires_at,
                "metadata_json": metadata_json,
            }
        )
        await self._finish()
        return lease_to_projection(record)

    async def renew_lease(self, command: SandboxLeaseRenewCommand) -> SandboxLeaseProjection | None:
        record = await self.repository.get_lease_for_update(command.workspace_id)
        if record is None or record.lease_token != command.lease_token:
            return None
        now = datetime.now(UTC)
        record.expires_at = now + timedelta(seconds=command.ttl_seconds)
        if command.metadata_json is not None:
            record.metadata_json = dict(command.metadata_json)
        record.updated_at = now
        await self._finish()
        return lease_to_projection(record)

    async def release_lease(self, command: SandboxLeaseReleaseCommand) -> bool:
        record = await self.repository.get_lease_for_update(command.workspace_id)
        if record is None or record.lease_token != command.lease_token:
            return False
        await self.repository.delete_lease(record)
        await self._finish()
        return True

    async def update_job(self, job_id: str, command: SandboxJobUpdateCommand) -> SandboxJobProjection | None:
        record = await self.repository.get_job(job_id)
        if record is None:
            return None
        now = datetime.now(UTC)
        before = record.status
        record.status = command.status
        record.exit_code = command.exit_code
        record.error_text = command.error_text
        if command.stdout_asset_id is not None:
            record.stdout_asset_id = command.stdout_asset_id
        if command.stderr_asset_id is not None:
            record.stderr_asset_id = command.stderr_asset_id
        if command.metadata_json is not None:
            record.metadata_json = dict(command.metadata_json)
        if command.status == "running" and before != "running":
            record.started_at = now
        if command.status in {"succeeded", "failed", "cancelled"}:
            record.finished_at = now
        record.updated_at = now
        await self._finish()
        return job_to_projection(record)

    async def list_jobs(
        self,
        *,
        workspace_id: str,
        sandbox_environment_id: str | None = None,
        execution_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[SandboxJobProjection]:
        return [
            job_to_projection(record)
            for record in await self.repository.list_jobs(
                workspace_id=workspace_id,
                sandbox_environment_id=sandbox_environment_id,
                execution_id=execution_id,
                status=status,
                limit=limit,
            )
        ]

    async def register_artifact(
        self,
        command: SandboxArtifactCreateCommand,
    ) -> SandboxArtifactProjection:
        job = await self.repository.get_job(command.sandbox_job_id)
        if job is None:
            raise DataServiceNotFoundError(
                "Sandbox job not found",
                detail={"sandbox_job_id": command.sandbox_job_id},
            )
        if job.workspace_id != command.workspace_id:
            raise DataServiceValidationError(
                "Sandbox artifact workspace does not match job workspace",
                detail={"workspace_id": command.workspace_id, "job_workspace_id": job.workspace_id},
            )
        artifact = self.repository.create_artifact(
            {
                "workspace_id": command.workspace_id,
                "sandbox_environment_id": job.sandbox_environment_id,
                "sandbox_job_id": command.sandbox_job_id,
                "workspace_asset_id": command.workspace_asset_id,
                "artifact_kind": command.artifact_kind,
                "path": command.path,
                "mime_type": command.mime_type,
                "content_hash": command.content_hash,
                "reproducibility_json": {
                    **dict(command.reproducibility_json or {}),
                    "sandbox_job_id": command.sandbox_job_id,
                    "runtime_image": job.runtime_image,
                    "script_hash": job.script_hash,
                    "input_hashes": dict(job.input_hashes_json or {}),
                },
                "materialization_status": "pending_review",
                "metadata_json": dict(command.metadata_json or {}),
            }
        )
        review = await self.review_service.create_batch(
            ReviewBatchCreateCommand(
                workspace_id=command.workspace_id,
                execution_id=job.execution_id,
                source_type="sandbox_job",
                source_id=job.id,
                review_kind="sandbox_artifact",
                title=f"Review sandbox artifact: {command.artifact_kind}",
                summary=command.path,
                payload_json={"sandbox_job_id": job.id, "sandbox_environment_id": job.sandbox_environment_id},
                items=[
                    ReviewItemCreateCommand(
                        source_item_id=artifact.id,
                        item_kind="sandbox_artifact",
                        target_domain="sandbox",
                        target_kind="sandbox_artifact",
                        target_ref_json={
                            "sandbox_artifact_id": artifact.id,
                            "workspace_asset_id": command.workspace_asset_id,
                        },
                        title=f"Accept sandbox artifact: {command.artifact_kind}",
                        summary=command.path,
                        payload_json={
                            "sandbox_artifact_id": artifact.id,
                            "workspace_asset_id": command.workspace_asset_id,
                            "artifact_kind": command.artifact_kind,
                            "path": command.path,
                        },
                        preview_json={
                            "path": command.path,
                            "mime_type": command.mime_type,
                            "content_hash": command.content_hash,
                        },
                        provenance_json={
                            "source_kind": "sandbox_job",
                            "source_id": job.id,
                            "execution_id": job.execution_id,
                        },
                    )
                ],
            )
        )
        artifact.review_batch_id = review.batch.id
        artifact.review_item_id = review.items[0].id if review.items else None
        await self._finish()
        return artifact_to_projection(artifact)

    async def mark_artifact_materialized(
        self,
        artifact_id: str,
        *,
        review_item_id: str | None = None,
    ) -> SandboxArtifactProjection | None:
        record = await self.repository.get_artifact(artifact_id)
        if record is None:
            return None
        if review_item_id is not None and record.review_item_id not in (None, review_item_id):
            raise DataServiceValidationError(
                "Review item does not match sandbox artifact",
                detail={"artifact_id": artifact_id, "review_item_id": review_item_id},
            )
        record.review_item_id = review_item_id or record.review_item_id
        record.materialization_status = "applied"
        record.updated_at = datetime.now(UTC)
        await self._finish()
        return artifact_to_projection(record)

    async def list_artifacts(
        self,
        *,
        workspace_id: str,
        sandbox_job_id: str | None = None,
        materialization_status: str | None = None,
        limit: int = 50,
    ) -> list[SandboxArtifactProjection]:
        return [
            artifact_to_projection(record)
            for record in await self.repository.list_artifacts(
                workspace_id=workspace_id,
                sandbox_job_id=sandbox_job_id,
                materialization_status=materialization_status,
                limit=limit,
            )
        ]

    async def _finish(self) -> None:
        if self.autocommit:
            await self.session.commit()
        else:
            await self.session.flush()


def _workspace_sandbox_id(workspace_id: str) -> str:
    return f"workspace-{workspace_id}"[:100]


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
