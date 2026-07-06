"""Sandbox DataService client methods."""

from __future__ import annotations

from typing import Any

from src.dataservice_client.contracts.sandbox import (
    SandboxArtifactCreatePayload,
    SandboxArtifactPayload,
    SandboxEnvironmentCreatePayload,
    SandboxEnvironmentPayload,
    SandboxEnvironmentUpdatePayload,
    SandboxJobCreatePayload,
    SandboxJobPayload,
    SandboxJobUpdatePayload,
    SandboxLeaseAcquirePayload,
    SandboxLeasePayload,
    SandboxLeaseReleasePayload,
    SandboxLeaseRenewPayload,
)


class SandboxDataServiceClientMixin:
    """Typed DataService methods for this domain."""

    async def _request(
        self,
        method: str,
        path: str,
        *,
        authenticated: bool = True,
        **kwargs: Any,
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def create_sandbox_environment(
        self,
        command: SandboxEnvironmentCreatePayload,
    ) -> SandboxEnvironmentPayload:
        payload = await self._request(
            "POST",
            "/internal/v1/sandbox/environments",
            json=command.model_dump(mode="json"),
        )
        return SandboxEnvironmentPayload.model_validate(payload["data"])

    async def get_or_create_sandbox_environment(
        self,
        workspace_id: str,
        command: SandboxEnvironmentCreatePayload,
    ) -> SandboxEnvironmentPayload:
        payload = await self._request(
            "PUT",
            f"/internal/v1/sandbox/workspaces/{workspace_id}/environment",
            json=command.model_dump(mode="json"),
        )
        return SandboxEnvironmentPayload.model_validate(payload["data"])

    async def list_sandbox_environments(
        self,
        *,
        workspace_id: str,
        state: str | None = None,
        limit: int = 50,
    ) -> list[SandboxEnvironmentPayload]:
        payload = await self._request(
            "GET",
            "/internal/v1/sandbox/environments",
            params={"workspace_id": workspace_id, "state": state, "limit": limit},
        )
        return [SandboxEnvironmentPayload.model_validate(item) for item in payload["data"]]

    async def get_sandbox_environment(self, environment_id: str) -> SandboxEnvironmentPayload | None:
        payload = await self._request("GET", f"/internal/v1/sandbox/environments/{environment_id}")
        data = payload.get("data")
        return SandboxEnvironmentPayload.model_validate(data) if data is not None else None

    async def update_sandbox_environment(
        self,
        environment_id: str,
        command: SandboxEnvironmentUpdatePayload,
    ) -> SandboxEnvironmentPayload | None:
        payload = await self._request(
            "PATCH",
            f"/internal/v1/sandbox/environments/{environment_id}",
            json=command.model_dump(mode="json", exclude_unset=True),
        )
        data = payload.get("data")
        return SandboxEnvironmentPayload.model_validate(data) if data is not None else None

    async def create_sandbox_job(self, command: SandboxJobCreatePayload) -> SandboxJobPayload:
        payload = await self._request(
            "POST",
            "/internal/v1/sandbox/jobs",
            json=command.model_dump(mode="json"),
        )
        return SandboxJobPayload.model_validate(payload["data"])

    async def update_sandbox_job(
        self,
        job_id: str,
        command: SandboxJobUpdatePayload,
    ) -> SandboxJobPayload | None:
        payload = await self._request(
            "PATCH",
            f"/internal/v1/sandbox/jobs/{job_id}",
            json=command.model_dump(mode="json", exclude_unset=True),
        )
        data = payload.get("data")
        return SandboxJobPayload.model_validate(data) if data is not None else None

    async def list_sandbox_jobs(
        self,
        *,
        workspace_id: str,
        sandbox_environment_id: str | None = None,
        execution_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[SandboxJobPayload]:
        payload = await self._request(
            "GET",
            "/internal/v1/sandbox/jobs",
            params={
                "workspace_id": workspace_id,
                "sandbox_environment_id": sandbox_environment_id,
                "execution_id": execution_id,
                "status": status,
                "limit": limit,
            },
        )
        return [SandboxJobPayload.model_validate(item) for item in payload["data"]]

    async def acquire_sandbox_lease(self, command: SandboxLeaseAcquirePayload) -> SandboxLeasePayload:
        payload = await self._request(
            "POST",
            "/internal/v1/sandbox/leases/acquire",
            json=command.model_dump(mode="json"),
        )
        return SandboxLeasePayload.model_validate(payload["data"])

    async def renew_sandbox_lease(self, command: SandboxLeaseRenewPayload) -> SandboxLeasePayload | None:
        payload = await self._request(
            "POST",
            "/internal/v1/sandbox/leases/renew",
            json=command.model_dump(mode="json", exclude_unset=True),
        )
        data = payload.get("data")
        return SandboxLeasePayload.model_validate(data) if data is not None else None

    async def release_sandbox_lease(self, command: SandboxLeaseReleasePayload) -> bool:
        payload = await self._request(
            "POST",
            "/internal/v1/sandbox/leases/release",
            json=command.model_dump(mode="json"),
        )
        data = payload.get("data") or {}
        return bool(data.get("released"))

    async def register_sandbox_artifact(
        self,
        command: SandboxArtifactCreatePayload,
    ) -> SandboxArtifactPayload:
        payload = await self._request(
            "POST",
            "/internal/v1/sandbox/artifacts",
            json=command.model_dump(mode="json"),
        )
        return SandboxArtifactPayload.model_validate(payload["data"])

    async def mark_sandbox_artifact_materialized(
        self,
        artifact_id: str,
        *,
        review_item_id: str | None = None,
    ) -> SandboxArtifactPayload | None:
        payload = await self._request(
            "POST",
            f"/internal/v1/sandbox/artifacts/{artifact_id}/materialized",
            json={"review_item_id": review_item_id},
        )
        data = payload.get("data")
        return SandboxArtifactPayload.model_validate(data) if data is not None else None

    async def list_sandbox_artifacts(
        self,
        *,
        workspace_id: str,
        sandbox_job_id: str | None = None,
        materialization_status: str | None = None,
        limit: int = 50,
    ) -> list[SandboxArtifactPayload]:
        payload = await self._request(
            "GET",
            "/internal/v1/sandbox/artifacts",
            params={
                "workspace_id": workspace_id,
                "sandbox_job_id": sandbox_job_id,
                "materialization_status": materialization_status,
                "limit": limit,
            },
        )
        return [SandboxArtifactPayload.model_validate(item) for item in payload["data"]]
