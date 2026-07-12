import pytest
from pydantic import ValidationError

from src.gateway.routers.chat_turn_contracts import ChatTurnCreateRequest


def test_run_create_request_accepts_xhigh_reasoning_effort() -> None:
    request = ChatTurnCreateRequest(
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
            message="deep work",
            reasoning_effort=reasoning_effort,
        )
