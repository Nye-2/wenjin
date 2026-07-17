from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, call, patch

import pytest

from src.application.errors import BadRequestError, PaymentRequiredError
from src.application.handlers.thread_turn_handler import ThreadTurnHandler
from src.application.results import (
    GeneratedThreadReply,
    PreparedThreadTurn,
    ThreadTurnRequest,
)
from src.contracts.billing import ThreadTurnBillingStatus
from src.contracts.model_usage import ModelUsage
from src.dataservice_client import DataServiceClientError


def _thread() -> SimpleNamespace:
    return SimpleNamespace(
        id="thread-1",
        workspace_id="workspace-1",
        user_id="user-1",
        model="gpt-5.6-terra",
        message_count=0,
    )


def _message(
    *,
    message_id: str,
    role: str,
    content: str,
    sequence_index: int,
    metadata: dict[str, object] | None = None,
    blocks: list[dict[str, object]] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=message_id,
        role=role,
        content=content,
        sequence_index=sequence_index,
        timestamp=datetime(2026, 7, 17, tzinfo=UTC),
        metadata_json=dict(metadata or {}),
        blocks=[
            SimpleNamespace(payload_json=dict(item))
            for item in (blocks or [])
        ],
    )


def _authorization(
    *,
    status: ThreadTurnBillingStatus = ThreadTurnBillingStatus.AUTHORIZED,
    assistant_message: SimpleNamespace | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        billing=SimpleNamespace(
            id="billing-1",
            status=status,
            user_message_id="user-message-1",
        ),
        user_message=(
            SimpleNamespace(id="user-message-1")
            if status == ThreadTurnBillingStatus.AUTHORIZED
            else None
        ),
        assistant_message=assistant_message,
        created=status == ThreadTurnBillingStatus.AUTHORIZED,
    )


def _completion(*, content: str = "模型回答") -> SimpleNamespace:
    return SimpleNamespace(
        assistant_message=_message(
            message_id="assistant-message-1",
            role="assistant",
            content=content,
            sequence_index=1,
            metadata={"source": "workspace_agent"},
            blocks=[{"kind": "text", "content": content}],
        ),
        billing_metadata={"credits_charged": 2},
    )


def _handler() -> tuple[ThreadTurnHandler, SimpleNamespace, SimpleNamespace, SimpleNamespace]:
    thread = _thread()
    thread_service = SimpleNamespace(
        get_or_create_thread=AsyncMock(return_value=thread),
        list_thread_messages=AsyncMock(return_value=[]),
        set_title_if_empty=AsyncMock(),
    )
    billing_gateway = SimpleNamespace(
        authorize=AsyncMock(return_value=_authorization()),
        complete=AsyncMock(return_value=_completion()),
        release=AsyncMock(),
        release_by_idempotency_key=AsyncMock(),
        rollback=AsyncMock(return_value=True),
    )
    handler = ThreadTurnHandler(
        thread_service=thread_service,
        billing_gateway=billing_gateway,
    )
    return handler, thread, thread_service, billing_gateway


@pytest.mark.asyncio
async def test_run_turn_authorizes_before_invoking_model() -> None:
    handler, thread, _, billing_gateway = _handler()
    events: list[str] = []

    async def authorize(**_kwargs: object) -> SimpleNamespace:
        events.append("authorize")
        return _authorization()

    async def generate(*_args: object, **_kwargs: object) -> GeneratedThreadReply:
        events.append("model")
        return GeneratedThreadReply(
            content="模型回答",
            blocks=[{"kind": "text", "content": "模型回答"}],
            metadata={"usage": {"input_tokens": 3, "output_tokens": 2}},
        )

    async def complete(**_kwargs: object) -> SimpleNamespace:
        events.append("complete")
        return _completion()

    billing_gateway.authorize.side_effect = authorize
    billing_gateway.complete.side_effect = complete
    request = ThreadTurnRequest(
        message="请回答",
        workspace_id="workspace-1",
        turn_idempotency_key="turn-1",
    )

    with (
        patch(
            "src.application.handlers.thread_turn_handler.generate_thread_response",
            side_effect=generate,
        ),
        patch(
            "src.application.handlers.thread_turn_handler.set_thread_status",
            new_callable=AsyncMock,
        ),
        patch(
            "src.application.handlers.thread_turn_handler.publish_thread_updated",
            new_callable=AsyncMock,
        ),
    ):
        completed = await handler.run_turn(request, actor_id="user-1")

    assert events == ["authorize", "model", "complete"]
    assert completed.reply.content == "模型回答"
    billing_gateway.authorize.assert_awaited_once_with(
        thread=thread,
        content="请回答",
        metadata=None,
        idempotency_key="turn-1",
    )


@pytest.mark.asyncio
async def test_dataservice_402_maps_to_payment_required_before_model_call() -> None:
    handler, _, _, billing_gateway = _handler()
    billing_gateway.authorize.side_effect = DataServiceClientError(
        "insufficient credits",
        status_code=402,
    )

    with (
        patch(
            "src.application.handlers.thread_turn_handler.generate_thread_response",
            new_callable=AsyncMock,
        ) as generate,
        patch(
            "src.application.handlers.thread_turn_handler.set_thread_status",
            new_callable=AsyncMock,
        ) as set_status,
    ):
        with pytest.raises(PaymentRequiredError, match="积分额度不足"):
            await handler.run_turn(
                ThreadTurnRequest(
                    message="请回答",
                    workspace_id="workspace-1",
                    turn_idempotency_key="turn-insufficient-credit",
                ),
                actor_id="user-1",
            )

    generate.assert_not_awaited()
    billing_gateway.complete.assert_not_awaited()
    billing_gateway.release.assert_not_awaited()
    billing_gateway.release_by_idempotency_key.assert_not_awaited()
    set_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_prepare_turn_rejects_missing_stable_request_identity() -> None:
    handler, _, _, billing_gateway = _handler()

    with pytest.raises(BadRequestError, match="stable request identity"):
        await handler.prepare_turn(
            ThreadTurnRequest(message="请回答", workspace_id="workspace-1"),
            actor_id="user-1",
        )

    billing_gateway.authorize.assert_not_awaited()


@pytest.mark.asyncio
async def test_settled_idempotent_replay_returns_assistant_without_model_call() -> None:
    handler, _, thread_service, billing_gateway = _handler()
    replayed = _message(
        message_id="assistant-replay-1",
        role="assistant",
        content="已结算回答",
        sequence_index=1,
        metadata={"billing": {"credits_charged": 2}},
        blocks=[{"kind": "text", "content": "已结算回答"}],
    )
    billing_gateway.authorize.return_value = _authorization(
        status=ThreadTurnBillingStatus.SETTLED,
        assistant_message=replayed,
    )

    with (
        patch(
            "src.application.handlers.thread_turn_handler.generate_thread_response",
            new_callable=AsyncMock,
        ) as generate,
        patch(
            "src.application.handlers.thread_turn_handler.set_thread_status",
            new_callable=AsyncMock,
        ) as set_status,
    ):
        completed = await handler.run_turn(
            ThreadTurnRequest(
                message="请回答",
                workspace_id="workspace-1",
                turn_idempotency_key="turn-replay",
            ),
            actor_id="user-1",
        )

    assert completed.assistant_message["id"] == "assistant-replay-1"
    assert completed.reply.content == "已结算回答"
    assert completed.reply.blocks == [{"kind": "text", "content": "已结算回答"}]
    generate.assert_not_awaited()
    thread_service.list_thread_messages.assert_not_awaited()
    billing_gateway.complete.assert_not_awaited()
    billing_gateway.release.assert_not_awaited()
    set_status.assert_has_awaits(
        [
            call("workspace-1", "thread-1", status="running"),
            call("workspace-1", "thread-1", status="completed"),
        ]
    )


@pytest.mark.asyncio
async def test_complete_commit_ack_loss_replay_does_not_repeat_provider_or_charge() -> None:
    handler, _, thread_service, billing_gateway = _handler()
    completion = _completion(content="已提交回答")
    settled = _authorization(
        status=ThreadTurnBillingStatus.SETTLED,
        assistant_message=completion.assistant_message,
    )
    billing_gateway.authorize.side_effect = [_authorization(), settled]
    billing_gateway.complete.return_value = completion
    generated = GeneratedThreadReply(
        content="已提交回答",
        blocks=[{"kind": "text", "content": "已提交回答"}],
        metadata={"usage": {"input_tokens": 3, "output_tokens": 2}},
    )
    request = ThreadTurnRequest(
        message="请回答",
        workspace_id="workspace-1",
        turn_idempotency_key="turn-ack-loss",
    )

    with (
        patch(
            "src.application.handlers.thread_turn_handler.generate_thread_response",
            new=AsyncMock(return_value=generated),
        ) as generate,
        patch(
            "src.application.handlers.thread_turn_handler.publish_thread_updated",
            new=AsyncMock(side_effect=RuntimeError("metadata ACK lost")),
        ),
        patch(
            "src.application.handlers.thread_turn_handler.set_thread_status",
            new_callable=AsyncMock,
        ),
    ):
        with pytest.raises(RuntimeError, match="metadata ACK lost"):
            await handler.run_turn(request, actor_id="user-1")

        replayed = await handler.run_turn(request, actor_id="user-1")

    assert replayed.reply.content == "已提交回答"
    assert replayed.assistant_message["id"] == "assistant-message-1"
    assert billing_gateway.authorize.await_count == 2
    assert all(
        item.kwargs["idempotency_key"] == "turn-ack-loss"
        for item in billing_gateway.authorize.await_args_list
    )
    generate.assert_awaited_once()
    thread_service.list_thread_messages.assert_awaited_once()
    billing_gateway.complete.assert_awaited_once()


@pytest.mark.asyncio
async def test_successful_finalize_completes_billing_with_model_usage() -> None:
    handler, thread, thread_service, billing_gateway = _handler()
    prepared = PreparedThreadTurn(
        request=ThreadTurnRequest(message="请回答", workspace_id="workspace-1"),
        thread=thread,
        user_message_id="user-message-1",
        billing_authorization_id="billing-1",
    )
    reply = GeneratedThreadReply(
        content="模型回答",
        blocks=[{"kind": "text", "content": "模型回答"}],
        metadata={
            "usage": {
                "input_tokens": 11,
                "output_tokens": 4,
                "reasoning_tokens": 2,
                "total_tokens": 15,
            }
        },
    )

    with (
        patch(
            "src.application.handlers.thread_turn_handler.generate_thread_response",
            new=AsyncMock(return_value=reply),
        ),
        patch(
            "src.application.handlers.thread_turn_handler.publish_thread_updated",
            new_callable=AsyncMock,
        ) as publish_updated,
        patch(
            "src.application.handlers.thread_turn_handler.set_thread_status",
            new_callable=AsyncMock,
        ) as set_status,
    ):
        completed = await handler.complete_turn(prepared, actor_id="user-1")

    complete_kwargs = billing_gateway.complete.await_args.kwargs
    assert complete_kwargs["thread"] is thread
    assert complete_kwargs["billing_id"] == "billing-1"
    assert complete_kwargs["content"] == "模型回答"
    assert complete_kwargs["blocks"] == [{"kind": "text", "content": "模型回答"}]
    assert complete_kwargs["usage"] == ModelUsage(
        input_tokens=11,
        output_tokens=4,
        reasoning_tokens=2,
        total_tokens=15,
    )
    assert completed.assistant_message["id"] == "assistant-message-1"
    assert completed.reply.metadata["billing"] == {"credits_charged": 2}
    thread_service.list_thread_messages.assert_awaited_once_with(thread)
    thread_service.set_title_if_empty.assert_awaited_once_with(thread, "请回答")
    publish_updated.assert_awaited_once_with(thread)
    set_status.assert_awaited_once_with(
        "workspace-1",
        "thread-1",
        status="completed",
    )


@pytest.mark.asyncio
async def test_successful_provider_reply_without_usage_fails_closed() -> None:
    handler, thread, _thread_service, billing_gateway = _handler()
    prepared = PreparedThreadTurn(
        request=ThreadTurnRequest(message="请回答", workspace_id="workspace-1"),
        thread=thread,
        user_message_id="user-message-1",
        billing_authorization_id="billing-1",
    )

    with (
        patch(
            "src.application.handlers.thread_turn_handler.generate_thread_response",
            new=AsyncMock(
                return_value=GeneratedThreadReply(
                    content="缺失用量的回答",
                    metadata={},
                )
            ),
        ),
        patch(
            "src.application.handlers.thread_turn_handler.set_thread_status",
            new_callable=AsyncMock,
        ),
    ):
        with pytest.raises(RuntimeError, match="model-usage receipt"):
            await handler.complete_turn(prepared, actor_id="user-1")

    billing_gateway.complete.assert_not_awaited()
    billing_gateway.release.assert_awaited_once_with(
        billing_id="billing-1",
        user_id="user-1",
        reason="chat turn failed",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "model_error",
    [RuntimeError("provider failed"), asyncio.CancelledError()],
    ids=["failure", "cancellation"],
)
async def test_model_failure_or_cancellation_releases_authorization(
    model_error: BaseException,
) -> None:
    handler, _, _, billing_gateway = _handler()

    with (
        patch(
            "src.application.handlers.thread_turn_handler.generate_thread_response",
            new=AsyncMock(side_effect=model_error),
        ),
        patch(
            "src.application.handlers.thread_turn_handler.set_thread_status",
            new_callable=AsyncMock,
        ) as set_status,
    ):
        with pytest.raises(type(model_error)):
            await handler.run_turn(
                ThreadTurnRequest(
                    message="请回答",
                    workspace_id="workspace-1",
                    turn_idempotency_key="turn-provider-failure",
                ),
                actor_id="user-1",
            )

    billing_gateway.release.assert_awaited_once_with(
        billing_id="billing-1",
        user_id="user-1",
        reason="chat turn failed",
    )
    billing_gateway.complete.assert_not_awaited()
    billing_gateway.rollback.assert_not_awaited()
    set_status.assert_has_awaits(
        [
            call("workspace-1", "thread-1", status="running"),
            call("workspace-1", "thread-1", status="failed"),
        ]
    )


@pytest.mark.asyncio
async def test_interruption_rolls_back_authorized_turn_without_started_mission() -> None:
    handler, thread, _, billing_gateway = _handler()
    prepared = PreparedThreadTurn(
        request=ThreadTurnRequest(message="请回答", workspace_id="workspace-1"),
        thread=thread,
        user_message_id="user-message-1",
        billing_authorization_id="billing-1",
    )

    with (
        patch.object(
            ThreadTurnHandler,
            "_started_mission_exists",
            new=AsyncMock(return_value=False),
        ) as started_mission_exists,
        patch(
            "src.application.handlers.thread_turn_handler.set_thread_status",
            new_callable=AsyncMock,
        ) as set_status,
    ):
        await handler.handle_run_interruption(prepared, rollback=True)

    started_mission_exists.assert_awaited_once_with(prepared)
    billing_gateway.rollback.assert_awaited_once_with(
        thread=thread,
        billing_id="billing-1",
        user_id="user-1",
        reason="chat turn interrupted with rollback",
    )
    billing_gateway.release.assert_not_awaited()
    set_status.assert_awaited_once_with(
        "workspace-1",
        "thread-1",
        status="failed",
    )


@pytest.mark.asyncio
async def test_post_authorization_prepare_failure_releases_hold() -> None:
    handler, _, _, billing_gateway = _handler()

    with patch(
        "src.application.handlers.thread_turn_handler.set_thread_status",
        new=AsyncMock(side_effect=RuntimeError("status publish failed")),
    ):
        with pytest.raises(RuntimeError, match="status publish failed"):
            await handler.prepare_turn(
                ThreadTurnRequest(
                    message="请回答",
                    workspace_id="workspace-1",
                    turn_idempotency_key="turn-prepare-failure",
                ),
                actor_id="user-1",
            )

    billing_gateway.release.assert_awaited_once_with(
        billing_id="billing-1",
        user_id="user-1",
        reason="chat turn preparation failed",
    )


@pytest.mark.asyncio
async def test_authorize_response_loss_recovers_receipt_before_failure_cleanup() -> None:
    handler, _, _, billing_gateway = _handler()
    billing_gateway.authorize.side_effect = [
        TimeoutError("authorization response lost"),
        _authorization(),
    ]

    with patch(
        "src.application.handlers.thread_turn_handler.set_thread_status",
        new=AsyncMock(side_effect=RuntimeError("status publish failed")),
    ):
        with pytest.raises(RuntimeError, match="status publish failed"):
            await handler.prepare_turn(
                ThreadTurnRequest(
                    message="请回答",
                    workspace_id="workspace-1",
                    turn_idempotency_key="turn-authorize-response-loss",
                ),
                actor_id="user-1",
            )

    assert billing_gateway.authorize.await_count == 2
    assert all(
        item.kwargs["idempotency_key"] == "turn-authorize-response-loss"
        for item in billing_gateway.authorize.await_args_list
    )
    billing_gateway.release.assert_awaited_once_with(
        billing_id="billing-1",
        user_id="user-1",
        reason="chat turn preparation failed",
    )
    billing_gateway.release_by_idempotency_key.assert_not_awaited()


@pytest.mark.asyncio
async def test_two_lost_authorization_responses_release_by_stable_key() -> None:
    handler, _, _, billing_gateway = _handler()
    billing_gateway.authorize.side_effect = [
        TimeoutError("first authorization response lost"),
        TimeoutError("second authorization response lost"),
    ]

    with pytest.raises(TimeoutError, match="second authorization response lost"):
        await handler.prepare_turn(
            ThreadTurnRequest(
                message="请回答",
                workspace_id="workspace-1",
                turn_idempotency_key="turn-two-lost-responses",
            ),
            actor_id="user-1",
        )

    assert billing_gateway.authorize.await_count == 2
    billing_gateway.release_by_idempotency_key.assert_awaited_once_with(
        idempotency_key="turn-two-lost-responses",
        user_id="user-1",
        reason="authorization response unavailable after retry",
    )
    billing_gateway.release.assert_not_awaited()


@pytest.mark.asyncio
async def test_abort_during_authorize_waits_for_receipt_then_releases_hold() -> None:
    handler, _, _, billing_gateway = _handler()
    authorize_started = asyncio.Event()
    authorize_finished = asyncio.Event()

    async def authorize(**_kwargs: object) -> SimpleNamespace:
        authorize_started.set()
        await authorize_finished.wait()
        return _authorization()

    billing_gateway.authorize.side_effect = authorize
    with patch(
        "src.application.handlers.thread_turn_handler.set_thread_status",
        new_callable=AsyncMock,
    ) as set_status:
        task = asyncio.create_task(
            handler.prepare_turn(
                ThreadTurnRequest(
                    message="请回答",
                    workspace_id="workspace-1",
                    turn_idempotency_key="turn-cancel-authorize",
                ),
                actor_id="user-1",
            )
        )
        await asyncio.wait_for(authorize_started.wait(), timeout=1)
        task.cancel()
        await asyncio.sleep(0)
        authorize_finished.set()

        with pytest.raises(asyncio.CancelledError):
            await task

    billing_gateway.release.assert_awaited_once_with(
        billing_id="billing-1",
        user_id="user-1",
        reason="chat turn authorization cancelled",
    )
    set_status.assert_awaited_once_with(
        "workspace-1",
        "thread-1",
        status="failed",
    )


@pytest.mark.asyncio
async def test_rollback_probe_failure_falls_back_to_release() -> None:
    handler, thread, _, billing_gateway = _handler()
    prepared = PreparedThreadTurn(
        request=ThreadTurnRequest(message="请回答", workspace_id="workspace-1"),
        thread=thread,
        user_message_id="user-message-1",
        billing_authorization_id="billing-1",
    )

    with (
        patch.object(
            ThreadTurnHandler,
            "_started_mission_exists",
            new=AsyncMock(side_effect=RuntimeError("mission lookup failed")),
        ),
        patch(
            "src.application.handlers.thread_turn_handler.set_thread_status",
            new_callable=AsyncMock,
        ),
    ):
        await handler.handle_run_interruption(prepared, rollback=True)

    billing_gateway.rollback.assert_not_awaited()
    billing_gateway.release.assert_awaited_once_with(
        billing_id="billing-1",
        user_id="user-1",
        reason="chat turn interrupted",
    )
