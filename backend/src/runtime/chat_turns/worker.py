"""Background run worker that executes one thread turn and publishes stream events."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Mapping
from dataclasses import replace
from typing import Any

from src.application.errors import ApplicationError
from src.application.handlers.thread_turn_handler import ThreadTurnHandler
from src.application.results import ThreadTurnRequest
from src.services.thread_events import set_thread_status

from ..stream_bridge import StreamBridge
from .manager import ChatTurnRunManager, ChatTurnRunRecord
from .schemas import ChatTurnExecutionRenewal, ChatTurnRunStatus

logger = logging.getLogger(__name__)


class _ExecutionLeaseLost(RuntimeError):
    """The worker can no longer produce side effects for this transport."""


class _ExecutionLeaseUnavailable(RuntimeError):
    """The execution lease could not be renewed before its deadline."""


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


async def _close_stream_run_best_effort(stream_run: Any, *, run_id: str) -> None:
    try:
        await _maybe_close_stream_run(stream_run)
    except (Exception, asyncio.CancelledError):
        logger.warning("Failed to close stream for run %s", run_id, exc_info=True)


async def _publish_best_effort(
    bridge: StreamBridge,
    run_id: str,
    event: str,
    data: Mapping[str, Any],
) -> None:
    try:
        await bridge.publish(run_id, event, data)
    except (Exception, asyncio.CancelledError):
        logger.warning(
            "Failed to publish %s event for run %s",
            event,
            run_id,
            exc_info=True,
        )


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
    turn_idempotency_key = str(request.turn_idempotency_key or "").strip()
    stream_run = None
    prepared = None
    execution_task: asyncio.Task[Any] | None = None
    abort_task: asyncio.Task[str] | None = None
    heartbeat_task: asyncio.Task[None] | None = None
    authorization_cleanup_attempted = False
    lost_execution_ownership = False

    execution_owner = await run_manager.claim_execution(run_id)
    if execution_owner is None:
        return

    async def renew_execution_claim() -> None:
        interval = max(0.02, run_manager.execution_lease_seconds / 3)
        last_confirmed = time.monotonic()
        while True:
            await asyncio.sleep(interval)
            renewal = await run_manager.renew_execution_claim(
                run_id,
                execution_owner,
            )
            if renewal is ChatTurnExecutionRenewal.renewed:
                last_confirmed = time.monotonic()
                continue
            if renewal is ChatTurnExecutionRenewal.lost:
                raise _ExecutionLeaseLost(
                    f"Execution lease lost for chat turn {run_id}"
                )
            if (
                time.monotonic() - last_confirmed
                >= run_manager.execution_lease_seconds
            ):
                raise _ExecutionLeaseUnavailable(
                    f"Execution lease unavailable for chat turn {run_id}"
                )

    async def fail_authorized_turn(reason: str) -> None:
        nonlocal authorization_cleanup_attempted
        if prepared is None or authorization_cleanup_attempted:
            return
        failure_handler = getattr(handler, "handle_run_failure", None)
        if failure_handler is None or not callable(failure_handler):
            return
        authorization_cleanup_attempted = True
        try:
            await failure_handler(
                prepared,
                actor_id=actor_id,
                reason=reason,
            )
        except (Exception, asyncio.CancelledError):
            logger.exception(
                "Failed to close authorization after run %s failure",
                run_id,
            )

    async def execute() -> Any:
        nonlocal prepared, stream_run
        try:
            prepared = await handler.prepare_turn(request, actor_id=actor_id)
            resolved_thread_id = str(prepared.thread.id)
            bound = await run_manager.bind_thread(
                run_id,
                resolved_thread_id,
                expected_execution_owner=execution_owner,
            )
            if not bound:
                renewal = await run_manager.renew_execution_claim(
                    run_id,
                    execution_owner,
                )
                if renewal is ChatTurnExecutionRenewal.renewed:
                    bound = await run_manager.bind_thread(
                        run_id,
                        resolved_thread_id,
                        expected_execution_owner=execution_owner,
                    )
                if not bound and renewal is not ChatTurnExecutionRenewal.lost:
                    raise _ExecutionLeaseUnavailable(
                        f"Transport unavailable before binding chat turn {run_id}"
                    )
            if not bound:
                raise _ExecutionLeaseLost(
                    f"Execution lease lost before binding chat turn {run_id}"
                )

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
        except asyncio.CancelledError:
            raise
        except BaseException:
            await _close_stream_run_best_effort(stream_run, run_id=run_id)
            renewal = await run_manager.renew_execution_claim(
                run_id,
                execution_owner,
            )
            if renewal is ChatTurnExecutionRenewal.renewed:
                await fail_authorized_turn("chat turn transport failed")
            raise

    async def interrupt(abort_action: str) -> None:
        nonlocal authorization_cleanup_attempted
        if execution_task is not None and not execution_task.done():
            execution_task.cancel()
            try:
                await execution_task
            except BaseException:
                pass
        await _close_stream_run_best_effort(stream_run, run_id=run_id)
        if prepared is not None:
            try:
                await handler.handle_run_interruption(
                    prepared,
                    rollback=abort_action == "rollback",
                )
                authorization_cleanup_attempted = True
            except (Exception, asyncio.CancelledError):
                logger.exception("Failed to interrupt authorization for run %s", run_id)
                await fail_authorized_turn("chat turn interruption failed")
        await run_manager.transition_status(
            run_id,
            ChatTurnRunStatus.interrupted,
            expected=(
                ChatTurnRunStatus.pending,
                ChatTurnRunStatus.running,
                ChatTurnRunStatus.interrupted,
            ),
            expected_execution_owner=execution_owner,
        )
        if prepared is not None:
            await _set_idle_status_if_no_other_active_chat_turns(
                run_manager=run_manager,
                run_id=run_id,
                prepared=prepared,
            )

    try:
        if not turn_idempotency_key:
            raise RuntimeError("Chat turn is missing its stable request identity")
        request = replace(
            request,
            turn_idempotency_key=turn_idempotency_key,
        )
        heartbeat_task = asyncio.create_task(renew_execution_claim())
        execution_task = asyncio.create_task(execute())
        abort_task = asyncio.create_task(run_manager.wait_for_abort(run_id))
        done, _ = await asyncio.wait(
            (execution_task, abort_task, heartbeat_task),
            return_when=asyncio.FIRST_COMPLETED,
        )
        if abort_task in done:
            await interrupt(abort_task.result())
            return
        if heartbeat_task in done:
            heartbeat_task.result()

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
            expected_execution_owner=execution_owner,
        )
        if not completed_transition:
            latest = await run_manager.get_or_load(run_id, refresh=True)
            lost_execution_ownership = (
                latest is None or latest.execution_owner != execution_owner
            )
            return
        await _emit_assistant_blocks(bridge, run_id=run_id, message=completed.assistant_message)
        await bridge.publish(run_id, "done", {"type": "done"})
    except asyncio.CancelledError:
        logger.warning("Run %s cancelled; marking interrupted", run_id)
        abort_action = await run_manager.get_abort_action(run_id)
        await interrupt(abort_action)
    except _ExecutionLeaseLost:
        lost_execution_ownership = True
        logger.warning("Run %s lost its execution lease; fencing old worker", run_id)
        if execution_task is not None and not execution_task.done():
            execution_task.cancel()
            try:
                await execution_task
            except BaseException:
                pass
        await _close_stream_run_best_effort(stream_run, run_id=run_id)
    except _ExecutionLeaseUnavailable:
        lost_execution_ownership = True
        logger.warning(
            "Run %s could not renew its execution lease; retrying delivery",
            run_id,
        )
        if execution_task is not None and not execution_task.done():
            execution_task.cancel()
            try:
                await execution_task
            except BaseException:
                pass
        await _close_stream_run_best_effort(stream_run, run_id=run_id)
        raise
    except ApplicationError as exc:
        changed = await run_manager.transition_status(
            run_id,
            ChatTurnRunStatus.error,
            expected=(ChatTurnRunStatus.running,),
            error=exc.message,
            expected_execution_owner=execution_owner,
        )
        if changed:
            await _publish_best_effort(
                bridge,
                run_id,
                "error",
                {"type": "error", "error": exc.message},
            )
        else:
            latest = await run_manager.get_or_load(run_id, refresh=True)
            lost_execution_ownership = (
                latest is None or latest.execution_owner != execution_owner
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
            expected_execution_owner=execution_owner,
        )
        if changed:
            await _publish_best_effort(
                bridge,
                run_id,
                "error",
                {"type": "error", "error": message},
            )
        else:
            latest = await run_manager.get_or_load(run_id, refresh=True)
            lost_execution_ownership = (
                latest is None or latest.execution_owner != execution_owner
            )
    finally:
        if abort_task is not None and not abort_task.done():
            abort_task.cancel()
            try:
                await abort_task
            except asyncio.CancelledError:
                pass
        if heartbeat_task is not None:
            if not heartbeat_task.done():
                heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
            except (_ExecutionLeaseLost, _ExecutionLeaseUnavailable):
                pass
            except Exception:
                logger.warning(
                    "Execution-claim heartbeat failed for run %s",
                    run_id,
                    exc_info=True,
                )
        await run_manager.release_execution_claim(run_id, execution_owner)
        if not lost_execution_ownership:
            try:
                await bridge.publish_end(run_id)
            except (Exception, asyncio.CancelledError):
                logger.warning("Failed to publish end for run %s", run_id, exc_info=True)
