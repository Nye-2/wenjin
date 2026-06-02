from src.application.services.feature_launch_context import (
    build_execution_launch_params,
    resolve_missing_context_fields,
)


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


def test_missing_context_rejects_generic_workbench_launch_prompt():
    prompt = "\n".join(
        [
            "请启动「文献定位与创新点」能力。",
            "能力目标：建立相关工作、gap 和 contribution positioning",
            "如果当前对话缺少具体研究主题、材料或目标，请先向用户确认，不要用空泛主题启动检索、写作或实验。",
            "请先判断是否需要实验或检索；若需要，请由右侧 Lead Agent/subagent 自主推进，并在右侧工作台展示关键证据、运行状态和可审阅结果。",
        ]
    )

    assert resolve_missing_context_fields(
        feature_id="sci_literature_positioning",
        params={"goal": prompt, "user_request": prompt},
        launch_source="tool",
    ) == ["goal"]


def test_missing_context_accepts_specific_topic_goal():
    assert resolve_missing_context_fields(
        feature_id="sci_literature_positioning",
        params={"goal": "federated LoRA fine-tuning for large language models"},
        launch_source="tool",
    ) == []
