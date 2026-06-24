"""Execution endpoints for DataService internal API."""

from __future__ import annotations

from datetime import datetime

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
    GenerationRecordCreateCommand,
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


@router.get("/analytics/active-users/count")
async def count_active_execution_users(
    created_since: datetime = Query(...),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceExecutionService(uow.required_session, autocommit=False)
    count = await service.count_active_execution_users(created_since=created_since)
    return envelope_ok({"count": count})


@router.get("/analytics/stats")
async def aggregate_execution_stats(
    created_since: datetime = Query(...),
    granularity: str = Query(default="day"),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceExecutionService(uow.required_session, autocommit=False)
    stats = await service.aggregate_execution_stats(
        created_since=created_since,
        granularity=granularity,
    )
    return envelope_ok(stats)


@router.get("/analytics/status-counts")
async def count_executions_by_status(
    user_id: str | None = Query(default=None),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceExecutionService(uow.required_session, autocommit=False)
    counts = await service.count_executions_by_status(user_id=user_id)
    return envelope_ok(counts)


@router.get("/analytics/count")
async def count_executions(
    status: list[str] | None = Query(default=None),
    created_since: datetime | None = Query(default=None),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceExecutionService(uow.required_session, autocommit=False)
    count = await service.count_executions(status=status, created_since=created_since)
    return envelope_ok({"count": count})


@router.get("/analytics/count-by-user")
async def count_executions_by_user_ids(
    user_id: list[str] = Query(default_factory=list),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceExecutionService(uow.required_session, autocommit=False)
    counts = await service.count_executions_by_user_ids(user_id)
    return envelope_ok(counts)


@router.get("/features/running-count")
async def count_running_feature_executions(
    workspace_id: str = Query(...),
    capability_id: str = Query(...),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceExecutionService(uow.required_session, autocommit=False)
    count = await service.count_running_feature_executions(
        workspace_id=workspace_id,
        capability_id=capability_id,
    )
    return envelope_ok({"count": count})


@router.get("/features/latest-status")
async def get_latest_feature_execution_status(
    workspace_id: str = Query(...),
    capability_id: str = Query(...),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceExecutionService(uow.required_session, autocommit=False)
    status = await service.get_latest_feature_execution_status(
        workspace_id=workspace_id,
        capability_id=capability_id,
    )
    return envelope_ok({"status": status})


@router.get("/features/by-launch-idempotency-key")
async def get_execution_by_launch_idempotency_key(
    workspace_id: str = Query(...),
    thread_id: str = Query(...),
    user_id: str = Query(...),
    capability_id: str = Query(...),
    launch_idempotency_key: str = Query(...),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceExecutionService(uow.required_session, autocommit=False)
    record = await service.find_execution_by_launch_idempotency_key(
        workspace_id=workspace_id,
        thread_id=thread_id,
        user_id=user_id,
        capability_id=capability_id,
        launch_idempotency_key=launch_idempotency_key,
    )
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.post("/reconcile-interrupted")
async def reconcile_interrupted_executions(
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceExecutionService(uow.required_session, autocommit=False)
    reconciled = await service.reconcile_interrupted_executions()
    await uow.commit()
    return envelope_ok({"reconciled": reconciled})


@router.post("/generation-records")
async def create_generation_record(
    command: GenerationRecordCreateCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceExecutionService(uow.required_session, autocommit=False)
    record = await service.create_generation_record(command)
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json"))


@router.get("/generation-records")
async def list_generation_records(
    workspace_id: str = Query(...),
    skill_name: str | None = Query(default=None),
    status: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceExecutionService(uow.required_session, autocommit=False)
    records = await service.list_generation_records(
        workspace_id=workspace_id,
        skill_name=skill_name,
        status=status,
        since=since,
        limit=limit,
    )
    return envelope_ok([record.model_dump(mode="json") for record in records])


@router.get("/generation-records/by-thread/{thread_id}")
async def list_generation_records_by_thread(
    thread_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceExecutionService(uow.required_session, autocommit=False)
    records = await service.list_generation_records_by_thread(thread_id)
    return envelope_ok([record.model_dump(mode="json") for record in records])


@router.get("/generation-records/stats")
async def get_generation_usage_stats(
    workspace_id: str = Query(...),
    since: datetime | None = Query(default=None),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceExecutionService(uow.required_session, autocommit=False)
    stats = await service.get_generation_usage_stats(
        workspace_id=workspace_id,
        since=since,
    )
    return envelope_ok(stats)


@router.post("/generation-records/cleanup")
async def cleanup_old_generation_records(
    payload: dict,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceExecutionService(uow.required_session, autocommit=False)
    deleted = await service.cleanup_old_generation_records(
        days_old=int(payload.get("days_old", 90)),
        workspace_id=payload.get("workspace_id"),
    )
    await uow.commit()
    return envelope_ok({"deleted": deleted})


@router.get("/generation-records/{record_id}")
async def get_generation_record(
    record_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceExecutionService(uow.required_session, autocommit=False)
    record = await service.get_generation_record(record_id)
    return envelope_ok(record.model_dump(mode="json") if record else None)


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


@router.get("/nodes/batch")
async def list_nodes_by_execution_ids(
    execution_id: list[str] = Query(default_factory=list),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceExecutionService(uow.required_session, autocommit=False)
    records = await service.list_nodes_by_execution_ids(execution_id)
    return envelope_ok([record.model_dump(mode="json") for record in records])


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
