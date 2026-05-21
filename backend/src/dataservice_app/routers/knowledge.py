"""Knowledge memory endpoints for DataService internal API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from src.dataservice.common.api import envelope_ok
from src.dataservice.common.unit_of_work import DataServiceUnitOfWork
from src.dataservice.knowledge_api import KnowledgeDataService
from src.dataservice_app.auth import require_internal_token
from src.dataservice_app.deps import get_uow
from src.dataservice_client.contracts.knowledge import (
    KnowledgeArchiveLowConfidencePayload,
    KnowledgeMemoryCreatePayload,
    KnowledgeMemoryUpdatePayload,
)

router = APIRouter(
    prefix="/internal/v1/knowledge",
    tags=["knowledge"],
    dependencies=[Depends(require_internal_token)],
)


def _knowledge_payload(record: Any) -> dict[str, Any] | None:
    if record is None:
        return None
    category = record.category.value if hasattr(record.category, "value") else str(record.category)
    return {
        "id": str(record.id),
        "user_id": str(record.user_id),
        "category": category,
        "content": record.content,
        "confidence": float(record.confidence),
        "source": record.source,
        "workspace_context": record.workspace_context,
        "is_active": bool(record.is_active),
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


@router.get("/users/{user_id}")
async def list_user_knowledge(
    user_id: str,
    category: str | None = Query(default=None),
    min_confidence: float | None = Query(default=None, ge=0.0, le=1.0),
    active_only: bool = Query(default=True),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    records = await KnowledgeDataService(
        uow.required_session,
        autocommit=False,
    ).list_by_user(
        user_id=user_id,
        category=category,
        min_confidence=min_confidence,
        active_only=active_only,
    )
    return envelope_ok([_knowledge_payload(record) for record in records])


@router.get("/users/{user_id}/active")
async def list_active_knowledge(
    user_id: str,
    workspace_context: str | None = Query(default=None),
    include_global: bool = Query(default=True),
    min_confidence: float = Query(default=0.5, ge=0.0, le=1.0),
    limit: int = Query(default=20, ge=1, le=200),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    records = await KnowledgeDataService(
        uow.required_session,
        autocommit=False,
    ).list_active(
        user_id=user_id,
        workspace_context=workspace_context,
        include_global=include_global,
        min_confidence=min_confidence,
        limit=limit,
    )
    return envelope_ok([_knowledge_payload(record) for record in records])


@router.get("/users/{user_id}/active-count")
async def count_active_knowledge(
    user_id: str,
    workspace_context: str | None = Query(default=None),
    include_global: bool | None = Query(default=None),
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    count = await KnowledgeDataService(
        uow.required_session,
        autocommit=False,
    ).count_active(
        user_id=user_id,
        workspace_context=workspace_context,
        include_global=include_global,
    )
    return envelope_ok({"count": count})


@router.post("/users/{user_id}/archive-low-confidence")
async def archive_low_confidence_knowledge(
    user_id: str,
    payload: KnowledgeArchiveLowConfidencePayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    count = await KnowledgeDataService(
        uow.required_session,
        autocommit=False,
    ).archive_low_confidence(user_id=user_id, threshold=payload.threshold)
    await uow.commit()
    return envelope_ok({"archived": count})


@router.post("")
async def create_knowledge(
    payload: KnowledgeMemoryCreatePayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    record = await KnowledgeDataService(
        uow.required_session,
        autocommit=False,
    ).create(**payload.model_dump())
    await uow.commit()
    return envelope_ok(_knowledge_payload(record))


@router.post("/upsert")
async def upsert_knowledge(
    payload: KnowledgeMemoryCreatePayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    record = await KnowledgeDataService(
        uow.required_session,
        autocommit=False,
    ).upsert(**payload.model_dump())
    await uow.commit()
    return envelope_ok(_knowledge_payload(record))


@router.get("/{knowledge_id}")
async def get_knowledge(
    knowledge_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    record = await KnowledgeDataService(
        uow.required_session,
        autocommit=False,
    ).get(knowledge_id)
    return envelope_ok(_knowledge_payload(record))


@router.patch("/{knowledge_id}")
async def update_knowledge(
    knowledge_id: str,
    payload: KnowledgeMemoryUpdatePayload,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    record = await KnowledgeDataService(
        uow.required_session,
        autocommit=False,
    ).update(knowledge_id=knowledge_id, **payload.model_dump(exclude_unset=True))
    await uow.commit()
    return envelope_ok(_knowledge_payload(record))


@router.post("/{knowledge_id}/deactivate")
async def deactivate_knowledge(
    knowledge_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    deactivated = await KnowledgeDataService(
        uow.required_session,
        autocommit=False,
    ).deactivate(knowledge_id)
    await uow.commit()
    return envelope_ok({"deactivated": deactivated})


@router.delete("/{knowledge_id}")
async def delete_knowledge(
    knowledge_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    deleted = await KnowledgeDataService(
        uow.required_session,
        autocommit=False,
    ).delete(knowledge_id)
    await uow.commit()
    return envelope_ok({"deleted": deleted})
