"""Task persistence endpoints for DataService internal API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from src.dataservice.common.api import envelope_ok
from src.dataservice.common.unit_of_work import DataServiceUnitOfWork
from src.dataservice.task_api import TaskDataService
from src.dataservice_app.auth import require_internal_token
from src.dataservice_app.deps import get_uow
from src.dataservice_client.contracts.task import (
    TaskRecordCompletedPayload,
    TaskRecordCreateGuardedPayload,
    TaskRecordCreatePayload,
    TaskRecordPatchPayload,
    TaskRecordRuntimeStatePayload,
    TaskRecordStartedPayload,
)

router = APIRouter(
    prefix="/internal/v1/tasks",
    tags=["tasks"],
    dependencies=[Depends(require_internal_token)],
)


@router.get("/users/{user_id}")
async def list_user_tasks(
    user_id: str,
    status: list[str] | None = Query(default=None),
    task_type: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=200),
    workspace_id: str | None = Query(default=None),
    feature_id: str | None = Query(default=None),
    action: str | None = Query(default=None),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    records = await TaskDataService(
        uow.required_session,
        autocommit=False,
    ).list_user_tasks(
        user_id=user_id,
        status=status,
        task_type=task_type,
        limit=limit,
        workspace_id=workspace_id,
        feature_id=feature_id,
        action=action,
    )
    return envelope_ok([record.model_dump(mode="json") for record in records])


@router.get("/users/{user_id}/active-count")
async def count_active_tasks(
    user_id: str,
    active_statuses: list[str] = Query(default_factory=list),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    count = await TaskDataService(
        uow.required_session,
        autocommit=False,
    ).count_active_tasks(user_id=user_id, active_statuses=active_statuses)
    return envelope_ok({"count": count})


@router.post("")
async def create_task_record(
    payload: TaskRecordCreatePayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    record = await TaskDataService(
        uow.required_session,
        autocommit=False,
    ).create_task_record(**payload.model_dump())
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json"))


@router.post("/guarded")
async def create_task_record_guarded(
    payload: TaskRecordCreateGuardedPayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    values = payload.model_dump()
    record, active_count = await TaskDataService(
        uow.required_session,
        autocommit=False,
    ).create_task_record_guarded(**values)
    await uow.commit()
    return envelope_ok(
        {
            "record": record.model_dump(mode="json") if record is not None else None,
            "active_count": active_count,
        }
    )


@router.get("/{task_id}")
async def get_task_record(
    task_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    record = await TaskDataService(
        uow.required_session,
        autocommit=False,
    ).get_task_record(task_id)
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.patch("/{task_id}")
async def update_task_record(
    task_id: str,
    payload: TaskRecordPatchPayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    record = await TaskDataService(
        uow.required_session,
        autocommit=False,
    ).update_task_record(task_id, **payload.model_dump(exclude_unset=True))
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.post("/{task_id}/started")
async def mark_task_started(
    task_id: str,
    payload: TaskRecordStartedPayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    record = await TaskDataService(
        uow.required_session,
        autocommit=False,
    ).mark_task_started(task_id=task_id, started_at=payload.started_at)
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.post("/{task_id}/runtime-state")
async def persist_runtime_state(
    task_id: str,
    payload: TaskRecordRuntimeStatePayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    record = await TaskDataService(
        uow.required_session,
        autocommit=False,
    ).persist_runtime_state(task_id=task_id, runtime_state=payload.runtime_state)
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.post("/{task_id}/completed")
async def mark_task_completed(
    task_id: str,
    payload: TaskRecordCompletedPayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    record = await TaskDataService(
        uow.required_session,
        autocommit=False,
    ).mark_task_completed(task_id=task_id, **payload.model_dump())
    await uow.commit()
    return envelope_ok(record.model_dump(mode="json") if record else None)
