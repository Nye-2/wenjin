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
    prepared = None
    execution_task: asyncio.Task[Any] | None = None
    abort_task: asyncio.Task[str] | None = None

    async def execute() -> Any:
        nonlocal prepared, stream_run
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
            },
        )

        stream_run = handler.stream_turn(prepared, actor_id=actor_id)
        async for delta in stream_run:
            await bridge.publish(
                run_id,
                "content",
                {"type": "content", "content": delta.text},
            )
        return await stream_run.wait_completed()

    async def interrupt(abort_action: str) -> None:
        if execution_task is not None and not execution_task.done():
            execution_task.cancel()
            try:
                await execution_task
            except BaseException:
                pass
        await _maybe_close_stream_run(stream_run)
        if prepared is not None:
            await handler.handle_run_interruption(
                prepared,
                rollback=abort_action == "rollback",
            )
        await run_manager.transition_status(
            run_id,
            ChatTurnRunStatus.interrupted,
            expected=(ChatTurnRunStatus.pending, ChatTurnRunStatus.running),
        )
        if prepared is not None:
            await _set_idle_status_if_no_other_active_chat_turns(
                run_manager=run_manager,
                run_id=run_id,
                prepared=prepared,
            )

    try:
        started = await run_manager.transition_status(
            run_id,
            ChatTurnRunStatus.running,
            expected=(ChatTurnRunStatus.pending,),
        )
        if not started:
            return

        execution_task = asyncio.create_task(execute())
        abort_task = asyncio.create_task(run_manager.wait_for_abort(run_id))
        done, _ = await asyncio.wait(
            (execution_task, abort_task),
            return_when=asyncio.FIRST_COMPLETED,
        )
        if abort_task in done:
            await interrupt(abort_task.result())
            return

        abort_task.cancel()
        try:
            await abort_task
        except asyncio.CancelledError:
            pass
        completed = execution_task.result()
        completed_transition = await run_manager.transition_status(
            run_id,
            ChatTurnRunStatus.success,
            expected=(ChatTurnRunStatus.running,),
        )
        if not completed_transition:
            return
        await _emit_assistant_blocks(bridge, run_id=run_id, message=completed.assistant_message)
        await bridge.publish(run_id, "done", {"type": "done"})
    except asyncio.CancelledError:
        logger.warning("Run %s cancelled; marking interrupted", run_id)
        abort_action = await run_manager.get_abort_action(run_id)
        await interrupt(abort_action)
    except ApplicationError as exc:
        changed = await run_manager.transition_status(
            run_id,
            ChatTurnRunStatus.error,
            expected=(ChatTurnRunStatus.running,),
            error=exc.message,
        )
        if changed:
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
        changed = await run_manager.transition_status(
            run_id,
            ChatTurnRunStatus.error,
            expected=(ChatTurnRunStatus.running,),
            error=str(exc),
        )
        if changed:
            await bridge.publish(
                run_id,
                "error",
                {"type": "error", "error": message},
            )
    finally:
        if abort_task is not None and not abort_task.done():
            abort_task.cancel()
            try:
                await abort_task
            except asyncio.CancelledError:
                pass
        await bridge.publish_end(run_id)
        asyncio.create_task(bridge.cleanup(run_id, delay=120))
        asyncio.create_task(run_manager.cleanup(run_id, delay=300))
