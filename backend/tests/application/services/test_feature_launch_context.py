from src.application.services.feature_launch_context import build_execution_launch_params


def test_build_execution_launch_params_unwraps_task_brief_shaped_params():
    payload = build_execution_launch_params(
        feature_id="sci_literature_positioning",
        workspace_id="workspace-1",
        params={
            "brief": {
                "topic": "federated LoRA",
                "save_to_library": True,
            },
            "raw_message": "find papers about federated LoRA",
        },
    )

    brief = payload["brief"]
    assert brief["raw_message"] == "find papers about federated LoRA"
    assert brief["brief"] == {
        "topic": "federated LoRA",
        "save_to_library": True,
    }
