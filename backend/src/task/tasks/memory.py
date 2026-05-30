"""Celery task for durable long-term memory capture."""

from __future__ import annotations

from typing import Any

from celery import Task, shared_task


async def _capture_memory_async(payload: dict[str, Any]) -> dict[str, Any]:
    from src.services.memory_capture_service import MemoryCaptureService

    count = await MemoryCaptureService().persist_conversation(
        user_id=str(payload.get("user_id") or "") or None,
        conversation_text=str(payload.get("conversation_text") or ""),
        workspace_context=(
            str(payload.get("workspace_id"))
            if payload.get("workspace_id")
            else None
        ),
        source=str(payload.get("source") or "thread"),
    )
    return {"persisted_count": count}


def _capture_memory_entry(self: Task, payload: dict[str, Any]) -> dict[str, Any]:
    from src.task.worker import run_worker_coroutine

    return run_worker_coroutine(_capture_memory_async(payload))


capture_memory = shared_task(
    bind=True,
    name="src.task.tasks.capture_memory",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 2},
)(_capture_memory_entry)
