"""Conversation endpoints for DataService internal API."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from src.dataservice.common.api import envelope_ok
from src.dataservice.common.unit_of_work import DataServiceUnitOfWork
from src.dataservice.domains.conversation.contracts import (
    ConversationMessageCreateCommand,
    ConversationMessagesRebuildCommand,
    ConversationThreadCreateCommand,
    ConversationThreadUpdateCommand,
)
from src.dataservice.domains.conversation.service import DataServiceConversationService
from src.dataservice_app.auth import require_internal_token
from src.dataservice_app.deps import get_uow

router = APIRouter(
    prefix="/internal/v1/conversations",
    tags=["conversation"],
    dependencies=[Depends(require_internal_token)],
)


@router.post("/threads")
async def create_thread(
    command: ConversationThreadCreateCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceConversationService(uow.required_session, autocommit=False)
    thread = await service.create_thread(command)
    await uow.commit()
    return envelope_ok(thread.model_dump(mode="json"))


@router.get("/threads")
async def list_threads(
    user_id: str,
    workspace_id: str | None = None,
    limit: int = 20,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceConversationService(uow.required_session, autocommit=False)
    threads = await service.list_threads(
        user_id=user_id,
        workspace_id=workspace_id,
        limit=limit,
    )
    return envelope_ok([thread.model_dump(mode="json") for thread in threads])


@router.get("/threads/{thread_id}")
async def get_thread(
    thread_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceConversationService(uow.required_session, autocommit=False)
    thread = await service.get_thread(thread_id)
    return envelope_ok(thread.model_dump(mode="json") if thread else None)


@router.get("/threads/{thread_id}/owned")
async def get_owned_thread(
    thread_id: str,
    user_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceConversationService(uow.required_session, autocommit=False)
    thread = await service.get_owned_thread(thread_id=thread_id, user_id=user_id)
    return envelope_ok(thread.model_dump(mode="json") if thread else None)


@router.get("/workspace-threads/latest")
async def get_latest_workspace_thread(
    user_id: str,
    workspace_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceConversationService(uow.required_session, autocommit=False)
    thread = await service.get_latest_workspace_thread(
        user_id=user_id,
        workspace_id=workspace_id,
    )
    return envelope_ok(thread.model_dump(mode="json") if thread else None)


@router.patch("/threads/{thread_id}")
async def update_thread(
    thread_id: str,
    command: ConversationThreadUpdateCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceConversationService(uow.required_session, autocommit=False)
    thread = await service.update_thread(thread_id, command)
    await uow.commit()
    return envelope_ok(thread.model_dump(mode="json") if thread else None)


@router.delete("/threads/{thread_id}")
async def delete_thread(
    thread_id: str,
    user_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceConversationService(uow.required_session, autocommit=False)
    deleted = await service.delete_thread(thread_id=thread_id, user_id=user_id)
    await uow.commit()
    return envelope_ok({"deleted": deleted})


@router.post("/threads/{thread_id}/lock")
async def lock_thread(
    thread_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceConversationService(uow.required_session, autocommit=False)
    await service.lock_thread(thread_id)
    await uow.commit()
    return envelope_ok({"locked": True})


@router.post("/{thread_id}/messages")
async def append_message(
    thread_id: str,
    command: ConversationMessageCreateCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceConversationService(uow.required_session, autocommit=False)
    message = await service.append_message(command.model_copy(update={"thread_id": thread_id}))
    await uow.commit()
    records = await service.list_message_records(thread_id)
    record = next((item for item in records if item.id == str(message.id)), None)
    return envelope_ok(record.model_dump(mode="json") if record else None)


@router.put("/{thread_id}/messages")
async def rebuild_messages(
    thread_id: str,
    command: ConversationMessagesRebuildCommand,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceConversationService(uow.required_session, autocommit=False)
    await service.rebuild_messages(command.model_copy(update={"thread_id": thread_id}))
    await uow.commit()
    records = await service.list_message_records(thread_id)
    return envelope_ok([record.model_dump(mode="json") for record in records])


@router.get("/{thread_id}/messages")
async def list_messages(
    thread_id: str,
    uow: DataServiceUnitOfWork = Depends(get_uow),
) -> dict:
    service = DataServiceConversationService(uow.required_session, autocommit=False)
    records = await service.list_message_records(thread_id)
    return envelope_ok([record.model_dump(mode="json") for record in records])
