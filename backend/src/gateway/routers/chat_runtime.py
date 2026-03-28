"""Shared runtime helpers for chat router flows."""

from __future__ import annotations

from fastapi import HTTPException
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from src.database import ChatThread, User
from src.models.router import InvalidRequestedModelError
from src.services import ChatThreadAccessError, ChatThreadService

from .chat_contracts import ChatRequest


def resolve_workspace_id(request: ChatRequest, thread: ChatThread) -> str | None:
    """Resolve workspace context from request or existing thread."""
    return request.workspace_id or thread.workspace_id


def build_langchain_messages(thread: ChatThread) -> list[BaseMessage]:
    """Convert stored thread messages into LangChain message objects."""
    messages: list[BaseMessage] = []
    for msg in thread.messages or []:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            messages.append(AIMessage(content=msg["content"]))
        elif msg["role"] == "system":
            messages.append(SystemMessage(content=msg["content"]))
    return messages


async def get_or_create_owned_thread(
    request: ChatRequest,
    current_user: User,
    chat_thread_service: ChatThreadService,
) -> ChatThread:
    """Fetch or create a thread while enforcing owner isolation."""
    try:
        return await chat_thread_service.get_or_create_thread(
            thread_id=request.thread_id,
            user_id=str(current_user.id),
            workspace_id=request.workspace_id,
            model=request.model,
            skill=request.skill,
            skill_explicit="skill" in request.model_fields_set,
        )
    except ChatThreadAccessError as exc:
        raise HTTPException(status_code=404, detail="Thread not found") from exc
    except InvalidRequestedModelError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
