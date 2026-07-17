import pytest
from pydantic import ValidationError

from src.gateway.routers.chat_turn_contracts import (
    ChatTurnCreateRequest,
    to_turn_request,
)
from src.runtime.chat_turns.schemas import chat_turn_idempotency_key


def test_run_create_request_accepts_xhigh_reasoning_effort() -> None:
    request = ChatTurnCreateRequest(
        request_id="request-1",
        message="deep work",
        reasoning_effort="xhigh",
    )

    assert request.reasoning_effort == "xhigh"


@pytest.mark.parametrize("reasoning_effort", ["minimal", "none"])
def test_run_create_request_rejects_unsupported_reasoning_effort(
    reasoning_effort: str,
) -> None:
    with pytest.raises(ValidationError):
        ChatTurnCreateRequest(
            request_id="request-1",
            message="deep work",
            reasoning_effort=reasoning_effort,
        )


def test_run_create_request_requires_stable_request_id() -> None:
    with pytest.raises(ValidationError):
        ChatTurnCreateRequest(message="deep work")


def test_run_create_request_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ChatTurnCreateRequest.model_validate(
            {
                "request_id": "request-1",
                "message": "deep work",
                "legacy_run_id": "run-1",
            }
        )


def test_run_create_request_rejects_server_owned_metadata() -> None:
    with pytest.raises(ValidationError, match="server-owned"):
        ChatTurnCreateRequest(
            request_id="request-1",
            message="deep work",
            metadata={"_owner_id": "forged-user"},
        )


def test_to_turn_request_carries_request_id_across_dispatch() -> None:
    body = ChatTurnCreateRequest(
        request_id="  client-request-1  ",
        message="deep work",
        metadata={"source": "test"},
    )

    request = to_turn_request(
        body,
        actor_id="user-1",
        forced_thread_id="thread-1",
    )

    assert body.request_id == "client-request-1"
    assert request.turn_idempotency_key == chat_turn_idempotency_key(
        "client-request-1",
        actor_id="user-1",
    )
    assert request.metadata == {"source": "test"}


def test_billing_key_is_stable_and_actor_scoped() -> None:
    first = chat_turn_idempotency_key(
        "request-1",
        actor_id="user-1",
    )

    assert first == chat_turn_idempotency_key(
        "request-1",
        actor_id="user-1",
    )
    assert first != chat_turn_idempotency_key(
        "request-1",
        actor_id="user-2",
    )
    assert len(first) < 200
