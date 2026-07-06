"""Sandbox endpoints for DataService internal API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from src.dataservice.common.api import envelope_ok
from src.dataservice.common.unit_of_work import DataServiceUnitOfWork
from src.dataservice.domains.sandbox.contracts import (
    SandboxArtifactCreateCommand,
    SandboxEnvironmentCreateCommand,
    SandboxEnvironmentUpdateCommand,
    SandboxJobCreateCommand,
    SandboxJobUpdateCommand,
    SandboxLeaseAcquireCommand,
    SandboxLeaseReleaseCommand,
    SandboxLeaseRenewCommand,
)
from src.dataservice.domains.sandbox.service import SandboxDataDomainService
from src.dataservice_app.auth import require_internal_token
from src.dataservice_app.deps import get_uow

router = APIRouter(
    prefix="/internal/v1/sandbox",
    tags=["sandbox"],
    dependencies=[Depends(require_internal_token)],
)


class SandboxArtifactMaterializeRequest(BaseModel):
    review_item_id: str | None = None


@router.post("/environments")
async def create_environment(
    command: SandboxEnvironmentCreateCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SandboxDataDomainService(uow.required_session, autocommit=False)
    record = await service.create_environment(command)
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json"))


@router.put("/workspaces/{workspace_id}/environment")
async def get_or_create_environment(
    workspace_id: str,
    command: SandboxEnvironmentCreateCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SandboxDataDomainService(uow.required_session, autocommit=False)
    record = await service.get_or_create_environment(command.model_copy(update={"workspace_id": workspace_id}))
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json"))


@router.get("/environments")
async def list_environments(
    workspace_id: str = Query(),
    state: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SandboxDataDomainService(uow.required_session, autocommit=False)
    records = await service.list_environments(workspace_id=workspace_id, state=state, limit=limit)
    return envelope_ok([record.model_dump(mode="json") for record in records])


@router.get("/environments/{environment_id}")
async def get_environment(
    environment_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SandboxDataDomainService(uow.required_session, autocommit=False)
    record = await service.get_environment(environment_id)
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.patch("/environments/{environment_id}")
async def update_environment(
    environment_id: str,
    command: SandboxEnvironmentUpdateCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SandboxDataDomainService(uow.required_session, autocommit=False)
    record = await service.update_environment(environment_id, command)
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.post("/jobs")
async def create_job(
    command: SandboxJobCreateCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SandboxDataDomainService(uow.required_session, autocommit=False)
    record = await service.create_job(command)
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json"))


@router.get("/jobs")
async def list_jobs(
    workspace_id: str = Query(),
    sandbox_environment_id: str | None = Query(default=None),
    execution_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SandboxDataDomainService(uow.required_session, autocommit=False)
    records = await service.list_jobs(
        workspace_id=workspace_id,
        sandbox_environment_id=sandbox_environment_id,
        execution_id=execution_id,
        status=status,
        limit=limit,
    )
    return envelope_ok([record.model_dump(mode="json") for record in records])


@router.patch("/jobs/{job_id}")
async def update_job(
    job_id: str,
    command: SandboxJobUpdateCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SandboxDataDomainService(uow.required_session, autocommit=False)
    record = await service.update_job(job_id, command)
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.post("/leases/acquire")
async def acquire_lease(
    command: SandboxLeaseAcquireCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SandboxDataDomainService(uow.required_session, autocommit=False)
    record = await service.acquire_lease(command)
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json"))


@router.post("/leases/renew")
async def renew_lease(
    command: SandboxLeaseRenewCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SandboxDataDomainService(uow.required_session, autocommit=False)
    record = await service.renew_lease(command)
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.post("/leases/release")
async def release_lease(
    command: SandboxLeaseReleaseCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SandboxDataDomainService(uow.required_session, autocommit=False)
    released = await service.release_lease(command)
    await uow.commit()
    return envelope_ok({"released": released})


@router.post("/artifacts")
async def register_artifact(
    command: SandboxArtifactCreateCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SandboxDataDomainService(uow.required_session, autocommit=False)
    record = await service.register_artifact(command)
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json"))


@router.post("/artifacts/{artifact_id}/materialized")
async def mark_artifact_materialized(
    artifact_id: str,
    command: SandboxArtifactMaterializeRequest,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SandboxDataDomainService(uow.required_session, autocommit=False)
    record = await service.mark_artifact_materialized(
        artifact_id,
        review_item_id=command.review_item_id,
    )
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.get("/artifacts")
async def list_artifacts(
    workspace_id: str = Query(),
    sandbox_job_id: str | None = Query(default=None),
    materialization_status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = SandboxDataDomainService(uow.required_session, autocommit=False)
    records = await service.list_artifacts(
        workspace_id=workspace_id,
        sandbox_job_id=sandbox_job_id,
        materialization_status=materialization_status,
        limit=limit,
    )
    return envelope_ok([record.model_dump(mode="json") for record in records])
