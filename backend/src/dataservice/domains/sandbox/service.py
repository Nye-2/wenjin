"""Sandbox aggregate domain service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.common.errors import DataServiceNotFoundError, DataServiceValidationError
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
from src.sandbox.workspace_layout import (
    is_workspace_internal_path,
    is_workspace_protected_path,
    normalize_workspace_virtual_path,
)


class SandboxDataDomainService:
    """DataService-owned sandbox metadata operations."""

    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self.session = session
        self.autocommit = autocommit
        self.repository = SandboxRepository(session)

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
            existing_metadata = dict(getattr(existing, "metadata_json", None) or {})
            merged_metadata = _merge_environment_metadata(
                existing_metadata,
                command.metadata_json,
                sandbox_id=existing.sandbox_id,
            )
            if merged_metadata != existing_metadata:
                existing.metadata_json = merged_metadata
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
                "mission_id": command.mission_id,
                "mission_item_seq": command.mission_item_seq,
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
            existing.holder_mission_id = command.holder_mission_id
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
                "holder_mission_id": command.holder_mission_id,
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
        mission_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[SandboxJobProjection]:
        return [
            job_to_projection(record)
            for record in await self.repository.list_jobs(
                workspace_id=workspace_id,
                sandbox_environment_id=sandbox_environment_id,
                mission_id=mission_id,
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
        metadata_json = dict(command.metadata_json or {})
        reproducibility_json = {
            **dict(command.reproducibility_json or {}),
            "sandbox_job_id": command.sandbox_job_id,
            "runtime_image": job.runtime_image,
            "script_hash": job.script_hash,
            "input_hashes": dict(job.input_hashes_json or {}),
        }
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
                "reproducibility_json": reproducibility_json,
                "materialization_status": "pending_review",
                "metadata_json": metadata_json,
            }
        )
        await self._finish()
        return artifact_to_projection(artifact)

    async def mark_artifact_materialized(
        self,
        artifact_id: str,
        *,
        mission_commit_id: str,
    ) -> SandboxArtifactProjection | None:
        record = await self.repository.get_artifact(artifact_id)
        if record is None:
            return None
        if record.mission_commit_id not in (None, mission_commit_id):
            raise DataServiceValidationError(
                "Mission commit does not match sandbox artifact",
                detail={"artifact_id": artifact_id, "mission_commit_id": mission_commit_id},
            )
        record.mission_commit_id = mission_commit_id
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


def _sandbox_artifact_review_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key in ("title", "description", "notes") for value in (_nonempty_metadata_value(metadata.get(key)),) if value is not None}


def _sandbox_artifact_review_reproducibility(
    reproducibility: dict[str, Any],
    *,
    content_hash: str | None,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in ("source_task_id", "sandbox_environment_id"):
        value = _nonempty_metadata_value(reproducibility.get(key))
        if value is not None:
            result[key] = value
    source_script = _workspace_script_path(reproducibility.get("source_script"))
    if source_script:
        result["source_script"] = source_script
    dataset_paths = _workspace_dataset_paths(reproducibility.get("dataset_paths"))
    if dataset_paths:
        result["dataset_paths"] = dataset_paths
    hash_value = _nonempty_metadata_value(reproducibility.get("content_hash") or content_hash)
    if hash_value is not None:
        result["content_hash"] = hash_value
    return result


def _sandbox_artifact_review_provenance(reproducibility: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in ("source_task_id", "sandbox_environment_id", "source_script"):
        value = _nonempty_metadata_value(reproducibility.get(key))
        if value is not None:
            result[key] = value
    dataset_paths = _string_list(reproducibility.get("dataset_paths"))
    if dataset_paths:
        result["dataset_paths"] = dataset_paths
    return result


def _nonempty_metadata_value(value: Any) -> Any | None:
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return value if value is not None else None


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        raw = [value]
    elif isinstance(value, list | tuple | set | frozenset):
        raw = list(value)
    else:
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in raw:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        result.append(text)
        seen.add(text)
        if len(result) >= 50:
            break
    return result


def _workspace_path(value: Any) -> str:
    try:
        path = normalize_workspace_virtual_path(str(value or "").strip())
    except ValueError:
        return ""
    if is_workspace_protected_path(path) or is_workspace_internal_path(path):
        return ""
    return path


def _workspace_script_path(value: Any) -> str:
    path = _workspace_path(value)
    if not path.startswith("/workspace/scripts/") or not path.endswith(".py"):
        return ""
    return path


def _workspace_dataset_paths(value: Any) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for item in _string_list(value):
        path = _workspace_path(item)
        if not path.startswith("/workspace/datasets/") or path in seen:
            continue
        paths.append(path)
        seen.add(path)
        if len(paths) >= 50:
            break
    return paths


def _merge_environment_metadata(
    existing: dict | None,
    incoming: dict | None,
    *,
    sandbox_id: str,
) -> dict:
    merged = dict(existing or {})
    candidate = dict(incoming or {})
    candidate.setdefault("provider_key", sandbox_id)
    if _known_workspace_type(merged) and not _known_workspace_type(candidate):
        candidate.pop("workspace_layout", None)
        candidate.pop("workspace_profile", None)
    return {**merged, **candidate}


def _known_workspace_type(metadata: dict) -> str | None:
    layout = metadata.get("workspace_layout")
    if isinstance(layout, dict):
        value = str(layout.get("workspace_type") or "").strip()
        if value and value != "generic":
            return value
    profile = metadata.get("workspace_profile")
    if isinstance(profile, dict):
        value = str(profile.get("workspace_type") or "").strip()
        if value and value != "generic":
            return value
    return None


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
