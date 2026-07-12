"""Background run worker that executes one thread turn and publishes stream events."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Mapping
from typing import Any

from src.application.errors import ApplicationError
from src.application.handlers.thread_turn_handler import ThreadTurnHandler
from src.application.results import ThreadTurnRequest
from src.services.thread_events import set_thread_status

from ..stream_bridge import StreamBridge
from .manager import ChatTurnRunManager, ChatTurnRunRecord
from .schemas import ChatTurnRunStatus

logger = logging.getLogger(__name__)


async def _emit_assistant_blocks(
    bridge: StreamBridge, *, run_id: str, message: Mapping[str, Any]
) -> None:
    """Spec §5.2 — publish one 'block' event per AgentBlock.

    Frontend groups blocks by message_id; we generate one fresh id per turn so
    all blocks of the same agent message render together.

    Plain assistant content is normalized to a TextBlock at this transport
    boundary; Mission actions still require provider-structured tool frames.
    """
    raw_blocks = message.get("blocks") if isinstance(message, Mapping) else None
    blocks: list[dict[str, Any]]
    if isinstance(raw_blocks, list) and raw_blocks:
        blocks = [b for b in raw_blocks if isinstance(b, Mapping)]
    else:
        content = message.get("content") if isinstance(message, Mapping) else None
        if isinstance(content, str) and content:
            blocks = [{"kind": "text", "content": content}]
        else:
            return  # nothing to emit

    message_id = str(uuid.uuid4())
    for block in blocks:
        await bridge.publish(
            run_id,
            "block",
            {"type": "block", "message_id": message_id, "block": dict(block)},
        )


def _is_timeout_exception(exc: BaseException) -> bool:
    """Detect timeout-shaped exceptions across provider/http stacks."""
    cursor: BaseException | None = exc
    seen: set[int] = set()
    timeout_names = {
        "TimeoutError",
        "ReadTimeout",
        "WriteTimeout",
        "ConnectTimeout",
        "PoolTimeout",
        "TimeoutException",
        "APITimeoutError",
    }
    while cursor is not None and id(cursor) not in seen:
        seen.add(id(cursor))
        if isinstance(cursor, (TimeoutError, asyncio.TimeoutError)):
            return True
        if cursor.__class__.__name__ in timeout_names:
            return True
        cursor = cursor.__cause__ or cursor.__context__
    return False


async def _maybe_close_stream_run(stream_run: Any) -> None:
    """Best-effort close for stream wrappers exposing aclose()."""
    closer = getattr(stream_run, "aclose", None)
    if closer is None or not callable(closer):
        return
    maybe_awaitable = closer()
    if isinstance(maybe_awaitable, Awaitable):
        await maybe_awaitable


async def _set_idle_status_if_no_other_active_chat_turns(
    *,
    run_manager: ChatTurnRunManager,
    run_id: str,
    prepared: Any,
) -> None:
    """Avoid stale idle overwrite when another run is already active."""
    try:
        thread_id = str(prepared.thread.id)
        records = await run_manager.list_by_thread(thread_id)
        has_other_active_run = any(
            item.run_id != run_id
            and item.status in (ChatTurnRunStatus.pending, ChatTurnRunStatus.running)
            for item in records
        )
        if has_other_active_run:
            return
        await set_thread_status(
            prepared.thread.workspace_id,
            prepared.thread.id,
            status="idle",
            skill=prepared.thread.skill,
            skill_name=None,
        )
    except Exception:
        logger.debug(
            "Skipped interrupted run status sync for run %s",
            run_id,
            exc_info=True,
        )


async def run_chat_turn(
    bridge: StreamBridge,
    run_manager: ChatTurnRunManager,
    record: ChatTurnRunRecord,
    *,
    handler: ThreadTurnHandler,
    request: ThreadTurnRequest,
    actor_id: str,
) -> None:
    """Execute one thread turn and publish canonical stream events."""

    run_id = record.run_id
    stream_run = None
    wait_completed_raised = False
    prepared = None

    try:
        await run_manager.set_status(run_id, ChatTurnRunStatus.running)

        prepared = await handler.prepare_turn(request, actor_id=actor_id)
        resolved_thread_id = str(prepared.thread.id)
        await run_manager.bind_thread(run_id, resolved_thread_id)

        await bridge.publish(
            run_id,
            "metadata",
            {
                "run_id": run_id,
                "thread_id": resolved_thread_id,
                "workspace_id": prepared.thread.workspace_id,
            },
        )
        await bridge.publish(
            run_id,
            "thread_id",
            {
                "type": "thread_id",
                "thread_id": resolved_thread_id,
                "skill": prepared.thread.skill,
                "skill_name": None,
            },
        )

        stream_run = handler.stream_turn(prepared, actor_id=actor_id)
        async for delta in stream_run:
            if await run_manager.is_abort_requested(run_id):
                break
            if delta.kind == "reasoning":
                await bridge.publish(
                    run_id,
                    "reasoning",
                    {"type": "reasoning", "content": delta.text},
                )
            elif delta.kind == "content":
                await bridge.publish(
                    run_id,
                    "content",
                    {"type": "content", "content": delta.text},
                )
            elif delta.kind == "tool_invocation":
                await bridge.publish(
                    run_id,
                    "tool_invocation",
                    {
                        "type": "tool_invocation",
                        "data": delta.data or {},
                    },
                )
            elif delta.kind == "tool_result":
                await bridge.publish(
                    run_id,
                    "tool_result",
                    {
                        "type": "tool_result",
                        "data": delta.data or {},
                    },
                )

        if await run_manager.is_abort_requested(run_id):
            await _maybe_close_stream_run(stream_run)
            abort_action = await run_manager.get_abort_action(run_id)
            if prepared is not None:
                await handler.handle_run_interruption(
                    prepared,
                    rollback=abort_action == "rollback",
                )
            await run_manager.set_status(run_id, ChatTurnRunStatus.interrupted)
            if prepared is not None:
                await _set_idle_status_if_no_other_active_chat_turns(
                    run_manager=run_manager,
                    run_id=run_id,
                    prepared=prepared,
                )
            return

        completed = await stream_run.wait_completed()
        await _emit_assistant_blocks(bridge, run_id=run_id, message=completed.assistant_message)
        await bridge.publish(run_id, "done", {"type": "done"})
        await run_manager.set_status(run_id, ChatTurnRunStatus.success)
    except asyncio.CancelledError:
        logger.warning("Run %s cancelled; marking interrupted", run_id)
        wait_completed_raised = True
        await _maybe_close_stream_run(stream_run)
        abort_action = await run_manager.get_abort_action(run_id)
        if prepared is not None:
            await handler.handle_run_interruption(
                prepared,
                rollback=abort_action == "rollback",
            )
        await run_manager.set_status(run_id, ChatTurnRunStatus.interrupted)
        if prepared is not None:
            await _set_idle_status_if_no_other_active_chat_turns(
                run_manager=run_manager,
                run_id=run_id,
                prepared=prepared,
            )
        await bridge.publish(
            run_id,
            "error",
            {"type": "error", "error": "Run interrupted"},
        )
    except ApplicationError as exc:
        await run_manager.set_status(run_id, ChatTurnRunStatus.error, error=exc.message)
        await bridge.publish(
            run_id,
            "error",
            {"type": "error", "error": exc.message},
        )
    except Exception as exc:
        logger.exception("Run %s failed", run_id)
        message = (
            "AI 响应超时，请稍后重试。"
            if _is_timeout_exception(exc)
            else "AI 服务内部错误，请稍后重试。"
        )
        await run_manager.set_status(run_id, ChatTurnRunStatus.error, error=str(exc))
        await bridge.publish(
            run_id,
            "error",
            {"type": "error", "error": message},
        )
    finally:
        if stream_run is not None:
            try:
                if not wait_completed_raised:
                    await stream_run.wait_completed()
            except BaseException:
                pass
        await bridge.publish_end(run_id)
        asyncio.create_task(bridge.cleanup(run_id, delay=120))
        asyncio.create_task(run_manager.cleanup(run_id, delay=300))
