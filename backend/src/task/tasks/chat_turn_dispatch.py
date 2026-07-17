"""At-least-once broker publication for transient ChatTurnRun intents."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from celery import shared_task

from src.runtime.chat_turns import (
    ChatTurnRunManager,
    ChatTurnRunStatus,
)

logger = logging.getLogger(__name__)


def enqueue_chat_turn(
    run_id: str,
    request_payload: dict[str, Any],
    actor_id: str,
) -> str:
    """Publish one deterministic Celery delivery and return its task id."""
    from src.task.tasks.run import process_chat_turn

    task = process_chat_turn.apply_async(
        args=[run_id, request_payload, actor_id],
        queue="default",
        task_id=run_id,
    )
    return str(task.id)


async def reconcile_chat_turn_dispatches(
    manager: ChatTurnRunManager,
    *,
    publish: Callable[[str, dict[str, Any], str], str] = enqueue_chat_turn,
    limit: int = 100,
) -> dict[str, int]:
    """Claim and publish durable Redis dispatch intents."""
    published = 0
    skipped = 0
    invalid = 0
    failed = 0
    for record in await manager.list_pending_dispatches(limit=limit):
        owner = await manager.claim_dispatch(record.run_id, wait_seconds=0)
        if owner is None:
            skipped += 1
            continue
        actor_id = str(record.metadata.get("_owner_id") or "").strip()
        request_payload = dict(record.dispatch_payload)
        if not actor_id or not request_payload:
            invalid += 1
            logger.error("Invalid dispatch intent for chat turn %s", record.run_id)
            await manager.release_dispatch_claim(record.run_id, owner=owner)
            await manager.transition_status(
                record.run_id,
                ChatTurnRunStatus.error,
                expected=(ChatTurnRunStatus.pending,),
                error="Invalid durable chat-turn dispatch intent",
            )
            continue
        try:
            worker_task_id = publish(record.run_id, request_payload, actor_id)
        except Exception:
            failed += 1
            logger.warning(
                "Failed to publish chat turn %s",
                record.run_id,
                exc_info=True,
            )
            await manager.release_dispatch_claim(record.run_id, owner=owner)
            continue
        if await manager.mark_dispatched(
            record.run_id,
            owner=owner,
            worker_task_id=worker_task_id,
        ):
            published += 1
        else:
            failed += 1
            logger.warning(
                "Published chat turn %s without a durable dispatch receipt",
                record.run_id,
            )
    return {
        "published": published,
        "skipped": skipped,
        "invalid": invalid,
        "failed": failed,
    }


async def _reconcile_chat_turn_dispatches_async() -> dict[str, int]:
    from src.academic.cache.redis_client import redis_client
    from src.config import settings

    await redis_client.reset_client(close_current=False)
    await redis_client.connect()
    manager = ChatTurnRunManager(
        redis_backend=redis_client.client,
        chat_turn_ttl_seconds=settings.runtime_run_ttl_seconds,
    )
    return await reconcile_chat_turn_dispatches(manager)


def _reconcile_chat_turn_dispatches_entry() -> dict[str, int]:
    from src.task.worker import run_worker_coroutine

    return run_worker_coroutine(_reconcile_chat_turn_dispatches_async())


reconcile_chat_turn_dispatches_task = shared_task(
    name="src.task.tasks.reconcile_chat_turn_dispatches",
)(_reconcile_chat_turn_dispatches_entry)
