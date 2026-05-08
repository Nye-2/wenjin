"""Task failure recovery workflow release gate tests."""

from src.application.presenters.thread_feature_cards import build_feature_task_failure_card


def test_failure_card_preserves_resume_and_retry_seed() -> None:
    reply = build_feature_task_failure_card(
        feature_id="framework_outline",
        task_id="task-failed-artifact",
        execution_session_id="exec-failed-artifact",
        payload={
            "params": {
                "topic": "LLM planning",
                "source_artifact_id": "artifact-current",
                "context_artifact_ids": ["artifact-current"],
                "__internal_trace": "hidden",
            }
        },
        error="tool timeout",
        completed=["outline drafted"],
    )

    failure_block = reply.blocks[0]
    assert failure_block["type"] == "task_failure"
    assert failure_block["data"]["execution_session_id"] == "exec-failed-artifact"
    assert [item["action"] for item in failure_block["data"]["recovery_actions"]] == [
        "resume_execution",
        "continue_thread",
    ]

    rerun = reply.blocks[-1]["data"]["items"][1]
    assert rerun["action"] == "rerun_from_artifact"
    assert rerun["params"]["topic"] == "LLM planning"
    assert rerun["params"]["source_artifact_id"] == "artifact-current"
    assert rerun["params"]["context_artifact_ids"] == ["artifact-current"]
    assert "__internal_trace" not in rerun["params"]


def test_failure_card_does_not_offer_resume_without_execution_session() -> None:
    reply = build_feature_task_failure_card(
        feature_id="framework_outline",
        task_id="task-failed-artifact",
        execution_session_id=None,
        payload={"params": {"topic": "LLM planning"}},
        error="tool timeout",
    )

    actions = [
        item["action"]
        for item in reply.blocks[0]["data"]["recovery_actions"]
    ]
    assert actions == ["continue_thread"]
