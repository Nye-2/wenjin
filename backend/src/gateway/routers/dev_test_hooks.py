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

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.academic.services.workspace_service import WorkspaceService
from src.agents.lead_agent.blocks import AgentMessage
from src.database import User
from src.gateway.deps.academic import get_workspace_service
from src.gateway.deps.core import get_db

router = APIRouter(prefix="/__test__", tags=["dev"])

_E2E_USER_EMAIL = "e2e-test@wenjin.local"
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

    Called from src.agents.lead_agent.structured_output.parse_with_fallback
    when settings.environment != "production".
    """
    return _queue.popleft() if _queue else None


async def _ensure_e2e_user(db: AsyncSession) -> User:
    stmt = select(User).where(User.email == _E2E_USER_EMAIL)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if user is not None:
        return user
    user = User(email=_E2E_USER_EMAIL, name="E2E Test", is_active=True)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/workspaces", response_model=WorkspaceOut)
async def mint_workspace(
    payload: WorkspaceIn = WorkspaceIn(),
    db: AsyncSession = Depends(get_db),
    workspace_service: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceOut:
    user = await _ensure_e2e_user(db)
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
