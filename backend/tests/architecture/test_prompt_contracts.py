"""Architecture guards for prompt boundaries across chat and Compute."""

from __future__ import annotations

from src.agents.feature_leader.workflow import build_dynamic_feature_workflow_plan
from src.agents.lead_agent.agent import apply_prompt_template
from src.agents.thread_state import ThreadState
from src.subagents.academic.registry import get_all_subagent_types, get_subagent_config
from src.workspace_features.services.llm_json import build_json_prompt, build_json_system_prompt


def test_workspace_type_prompt_preserves_chat_compute_boundary() -> None:
    prompt = apply_prompt_template(
        ThreadState(messages=[], workspace_type="sci"),
        {"configurable": {}},
    )

    assert "学术论文（SCI/EI）" in prompt
    assert "Chat 侧重点" in prompt
    assert "适合提议 Compute 的任务" in prompt
    assert "不编造论文、引用、实验结果" in prompt
    assert "你正在帮助用户撰写一篇面向期刊投稿的学术论文" not in prompt


def test_shared_json_prompt_contract_is_compute_scoped_and_evidence_aware() -> None:
    prompt = build_json_prompt(
        instruction="生成测试产物。",
        context_sections=[("主题", "测试主题")],
        schema='{"summary":"..."}',
    )
    system_prompt = build_json_system_prompt("你是测试角色。")

    assert "严格遵守 schema" in prompt
    assert "优先复用上下文中的工作区产物" in prompt
    assert "不要重启需求发现或向用户提问" in prompt
    assert "待补充/待核验" in prompt
    assert "问津 Compute feature 执行链路" in system_prompt
    assert "不得向用户提问" in system_prompt


def test_feature_leader_subtasks_include_compute_internal_contract() -> None:
    plan = build_dynamic_feature_workflow_plan(
        workspace_type="thesis",
        feature_id="deep_research",
        payload={"params": {"topic": "graph neural networks"}},
    )

    assert plan is not None
    prompts = [
        str(task.get("prompt") or "")
        for phase in plan.phased_plan.phases
        for task in phase.tasks
    ]
    assert prompts
    assert all("Compute feature 内部子任务" in prompt for prompt in prompts)
    assert all("不要向用户提问" in prompt for prompt in prompts)


def test_registered_subagent_prompts_are_compute_scoped() -> None:
    missing: list[str] = []
    for subagent_type in get_all_subagent_types():
        config = get_subagent_config(subagent_type)
        prompt = config.system_prompt
        if "Compute boundary:" not in prompt or "not the chat panel" not in prompt:
            missing.append(subagent_type)

    assert not missing, "Subagent prompts missing Compute boundary: " + ", ".join(missing)
