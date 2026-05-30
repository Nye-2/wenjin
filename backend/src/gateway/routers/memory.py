"""Memory router exposing the canonical DB-backed user memory view."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.config.config_loader import MemoryConfig, get_app_config
from src.gateway.auth_dependencies import AccountAuthSubject, get_current_user
from src.services.user_memory_service import build_memory_context, load_user_memory

router = APIRouter()


class MemoryEntry(BaseModel):
    """Single persisted long-term memory item."""

    category: str
    content: str
    confidence: float
    workspace_context: str | None = None


class MemoryResponse(BaseModel):
    """Current user's long-term memory snapshot."""

    workspace_id: str | None = Field(default=None)
    formatted_context: str = Field(default="")
    items: list[MemoryEntry] = Field(default_factory=list)


class MemoryConfigResponse(BaseModel):
    """Runtime memory configuration exposed for debugging."""

    enabled: bool
    debounce_seconds: int
    max_facts: int
    fact_confidence_threshold: float
    injection_enabled: bool
    max_injection_tokens: int
    max_context_turns: int
    similarity_weight: float
    confidence_weight: float


class MemoryStatusResponse(BaseModel):
    """Combined memory data and config response."""

    config: MemoryConfigResponse
    data: MemoryResponse


def _memory_config_response() -> MemoryConfigResponse:
    try:
        memory_config = getattr(get_app_config(), "memory", None)
    except Exception:
        memory_config = None

    config = memory_config or MemoryConfig()
    return MemoryConfigResponse(
        enabled=config.enabled,
        debounce_seconds=config.debounce_seconds,
        max_facts=config.max_facts,
        fact_confidence_threshold=config.fact_confidence_threshold,
        injection_enabled=config.injection_enabled,
        max_injection_tokens=config.max_injection_tokens,
        max_context_turns=config.max_context_turns,
        similarity_weight=config.similarity_weight,
        confidence_weight=config.confidence_weight,
    )


@router.get("/memory", response_model=MemoryResponse)
async def get_memory(
    workspace_id: str | None = None,
    current_user: AccountAuthSubject = Depends(get_current_user),
) -> MemoryResponse:
    """Return the current user's long-term memory snapshot."""
    items = await load_user_memory(str(current_user.id), workspace_id)
    formatted_context = await build_memory_context(str(current_user.id), workspace_id)
    return MemoryResponse(
        workspace_id=workspace_id,
        formatted_context=formatted_context,
        items=[MemoryEntry(**item) for item in items],
    )


@router.get("/memory/config", response_model=MemoryConfigResponse)
async def get_memory_config() -> MemoryConfigResponse:
    """Expose the active memory configuration."""
    return _memory_config_response()


@router.get("/memory/status", response_model=MemoryStatusResponse)
async def get_memory_status(
    workspace_id: str | None = None,
    current_user: AccountAuthSubject = Depends(get_current_user),
) -> MemoryStatusResponse:
    """Return memory config together with the current user's memory snapshot."""
    return MemoryStatusResponse(
        config=_memory_config_response(),
        data=await get_memory(workspace_id=workspace_id, current_user=current_user),
    )
