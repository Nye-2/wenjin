"""Execution endpoints for DataService internal API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from src.dataservice.common.api import envelope_ok
from src.dataservice.common.unit_of_work import DataServiceUnitOfWork
from src.dataservice.domains.execution.contracts import (
    ComputeSessionEnsureCommand,
    ComputeSessionUpdateCommand,
    ExecutionCreateCommand,
    ExecutionEventCreateCommand,
    ExecutionNodePatchCommand,
    ExecutionNodeUpsertCommand,
    ExecutionUpdateCommand,
)
from src.dataservice.domains.execution.service import DataServiceExecutionService
from src.dataservice_app.auth import require_internal_token
from src.dataservice_app.deps import get_uow

router = APIRouter(
    prefix="/internal/v1/executions",
    tags=["execution"],
    dependencies=[Depends(require_internal_token)],
)


@router.post("")
async def create_execution(
    command: ExecutionCreateCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceExecutionService(uow.required_session, autocommit=False)
    record = await service.create_execution(command)
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json"))


@router.get("")
async def list_executions(
    user_id: str | None = Query(default=None),
    workspace_id: str | None = Query(default=None),
    thread_id: str | None = Query(default=None),
    execution_type: str | None = Query(default=None),
    status: list[str] | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceExecutionService(uow.required_session, autocommit=False)
    records = await service.list_executions(
        user_id=user_id,
        workspace_id=workspace_id,
        thread_id=thread_id,
        execution_type=execution_type,
        status=status,
        limit=limit,
    )
    return envelope_ok([record.model_dump(mode="json") for record in records])


@router.post("/reconcile-interrupted")
async def reconcile_interrupted_executions(
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceExecutionService(uow.required_session, autocommit=False)
    reconciled = await service.reconcile_interrupted_executions()
    await uow.commit()
    return envelope_ok({"reconciled": reconciled})


@router.get("/{execution_id}")
async def get_execution(
    execution_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceExecutionService(uow.required_session, autocommit=False)
    record = await service.get_execution(execution_id)
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.patch("/{execution_id}")
async def update_execution(
    execution_id: str,
    command: ExecutionUpdateCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceExecutionService(uow.required_session, autocommit=False)
    record = await service.update_execution(execution_id, command)
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.post("/compute-sessions/ensure")
async def ensure_compute_session(
    command: ComputeSessionEnsureCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceExecutionService(uow.required_session, autocommit=False)
    record, changed = await service.ensure_compute_session(command)
    await uow.commit()
    return envelope_ok({"session": record.model_dump(mode="json"), "changed": changed})


@router.get("/compute-sessions/list")
async def list_compute_sessions(
    workspace_id: str = Query(...),
    user_id: str = Query(...),
    limit: int = Query(default=20, ge=1, le=100),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceExecutionService(uow.required_session, autocommit=False)
    records = await service.list_compute_sessions(
        workspace_id=workspace_id,
        user_id=user_id,
        limit=limit,
    )
    return envelope_ok([record.model_dump(mode="json") for record in records])


@router.get("/compute-sessions/by-execution/{execution_id}")
async def get_compute_session_by_execution(
    execution_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceExecutionService(uow.required_session, autocommit=False)
    record = await service.get_compute_session_by_execution(execution_id)
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.get("/compute-sessions/{compute_session_id}")
async def get_compute_session(
    compute_session_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceExecutionService(uow.required_session, autocommit=False)
    record = await service.get_compute_session(compute_session_id)
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.patch("/compute-sessions/{compute_session_id}")
async def update_compute_session(
    compute_session_id: str,
    command: ComputeSessionUpdateCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceExecutionService(uow.required_session, autocommit=False)
    record = await service.update_compute_session(compute_session_id, command)
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.get("/nodes/{node_record_id}")
async def get_node_by_record_id(
    node_record_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceExecutionService(uow.required_session, autocommit=False)
    record = await service.get_node_by_record_id(node_record_id)
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.patch("/nodes/{node_record_id}")
async def update_node(
    node_record_id: str,
    command: ExecutionNodePatchCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceExecutionService(uow.required_session, autocommit=False)
    record = await service.update_node(node_record_id, command)
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.get("/{execution_id}/nodes")
async def list_nodes(
    execution_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceExecutionService(uow.required_session, autocommit=False)
    records = await service.list_nodes(execution_id)
    return envelope_ok([record.model_dump(mode="json") for record in records])


@router.post("/{execution_id}/nodes")
async def upsert_node(
    execution_id: str,
    command: ExecutionNodeUpsertCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceExecutionService(uow.required_session, autocommit=False)
    record = await service.upsert_node(execution_id, command)
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json"))


@router.get("/{execution_id}/nodes/{node_id}")
async def find_node_by_node_id(
    execution_id: str,
    node_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceExecutionService(uow.required_session, autocommit=False)
    record = await service.find_node_by_node_id(
        execution_id=execution_id,
        node_id=node_id,
    )
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.post("/{execution_id}/events")
async def append_event(
    execution_id: str,
    command: ExecutionEventCreateCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceExecutionService(uow.required_session, autocommit=False)
    record = await service.append_event(execution_id, command)
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json"))


@router.get("/{execution_id}/events")
async def list_events(
    execution_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceExecutionService(uow.required_session, autocommit=False)
    records = await service.list_events(execution_id)
    return envelope_ok([record.model_dump(mode="json") for record in records])
