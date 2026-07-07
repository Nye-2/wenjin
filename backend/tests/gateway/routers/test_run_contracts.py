from src.gateway.routers.run_contracts import RunCreateRequest


def test_run_create_request_accepts_xhigh_reasoning_effort() -> None:
    request = RunCreateRequest(
        message="deep work",
        reasoning_effort="xhigh",
    )

    assert request.reasoning_effort == "xhigh"
