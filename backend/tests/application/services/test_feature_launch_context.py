from src.application.services.feature_launch_context import (
    build_execution_launch_params,
    hydrate_missing_context_params_from_resume_message,
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


def test_missing_context_without_minimum_context_has_no_static_requirement():
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
    ) == []


def test_missing_context_rejects_generic_workbench_picker_prompt_from_dynamic_contract():
    prompt = "\n".join(
        [
            "我想使用「问题到 SCI 初稿」能力。",
            "请先确认启动所需的具体研究主题、材料或目标；信息足够时再组织研究团队。",
        ]
    )

    assert resolve_missing_context_fields(
        feature_id="research_question_to_paper",
        params={"topic": prompt, "raw_message": prompt},
        launch_source="tool",
        minimum_context={"topic": "required"},
    ) == ["topic"]


def test_missing_context_accepts_dynamic_capability_minimum_context():
    assert resolve_missing_context_fields(
        feature_id="research_question_to_paper",
        params={"topic": "federated LoRA fine-tuning for large language models"},
        launch_source="tool",
        minimum_context={"topic": "required"},
    ) == []


def test_dynamic_minimum_context_does_not_fall_back_to_static_requirements():
    assert resolve_missing_context_fields(
        feature_id="sci_literature_positioning",
        params={},
        launch_source="tool",
        minimum_context={"target_journal": "optional"},
    ) == []


def test_missing_context_accepts_specific_topic_goal():
    assert resolve_missing_context_fields(
        feature_id="sci_literature_positioning",
        params={"goal": "federated LoRA fine-tuning for large language models"},
        launch_source="tool",
    ) == []


def test_resume_hydrates_legacy_missing_context_from_launch_message():
    hydrated = hydrate_missing_context_params_from_resume_message(
        feature_id="sci_literature_positioning",
        params={},
        launch_source="tool",
        launch_message="federated LoRA fine-tuning for large language models",
    )

    assert hydrated["goal"] == "federated LoRA fine-tuning for large language models"
