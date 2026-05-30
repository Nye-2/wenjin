"""Dev-only endpoints for queueing scripted LLM responses during e2e tests.

Mounted only when settings.environment != "production". The router itself is
disabled at registration time in src.gateway.app.

Endpoints:
- POST /__test__/llm/queue   — enqueue AgentMessage payloads for the next
  parse_with_fallback() call(s). The queue is process-local; if the agent
  workers run in a separate process, this won't reach them.
- POST /__test__/llm/clear   — drain the queue.
- POST /__test__/workspaces  — mint a fresh workspace + first thread for the
  test, returning {"workspace_id": ...}. Uses a synthetic test user.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.academic.services.workspace_service import WorkspaceService
from src.agents.chat_agent.blocks import AgentMessage
from src.dataservice_client import AsyncDataServiceClient
from src.gateway.deps.academic import get_workspace_service
from src.gateway.deps.core import get_dataservice_client
from src.services.user_service import UserService

router = APIRouter(prefix="/__test__", tags=["dev"])

_E2E_USER_EMAIL = "e2e-test@example.com"
_queue: deque[AgentMessage] = deque()


class QueueIn(BaseModel):
    messages: list[AgentMessage]


class WorkspaceIn(BaseModel):
    type: str = "sci"
    name: str = "E2E Workspace"
    discipline: str | None = None


class WorkspaceOut(BaseModel):
    workspace_id: str


@router.post("/llm/queue", status_code=status.HTTP_204_NO_CONTENT)
async def queue_llm_responses(payload: QueueIn) -> None:
    _queue.extend(payload.messages)


@router.post("/llm/clear", status_code=status.HTTP_204_NO_CONTENT)
async def clear_llm() -> None:
    _queue.clear()


def pop_next() -> AgentMessage | None:
    """Pop the next scripted AgentMessage, or return None if empty.

    Called from src.agents.chat_agent.structured_output.parse_with_fallback
    when settings.environment != "production".
    """
    return _queue.popleft() if _queue else None


async def _ensure_e2e_user(dataservice: AsyncDataServiceClient) -> Any:
    user_service = UserService(dataservice=dataservice)
    user = await user_service.get_by_email(_E2E_USER_EMAIL)
    if user is not None:
        return user
    return await user_service.create_user(
        email=_E2E_USER_EMAIL,
        name="E2E Test",
        password="wenjin-e2e-password",
    )


@router.post("/workspaces", response_model=WorkspaceOut)
async def mint_workspace(
    payload: WorkspaceIn = WorkspaceIn(),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceOut:
    user = await _ensure_e2e_user(dataservice)
    try:
        workspace = await workspace_service.create(
            user_id=str(user.id),
            name=payload.name,
            type=payload.type,
            discipline=payload.discipline,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return WorkspaceOut(workspace_id=str(workspace.id))
