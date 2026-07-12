"""System contract for the single user-facing Wenjin WorkspaceAgent."""

from __future__ import annotations

import json

from src.agents.workspace_agent.contracts import WorkspaceAgentContext

from .principles import SHARED_OPERATING_RULES, WORKSPACE_AGENT_IDENTITY


def render_workspace_agent_prompt(context: WorkspaceAgentContext) -> str:
    hints = [hint.model_dump(mode="json") for hint in context.policy_hints]
    active = (
        context.active_mission.model_dump(mode="json", exclude_none=True)
        if context.active_mission
        else None
    )
    server = {
        "workspace_id": context.workspace_id,
        "workspace_type": context.workspace_type,
        "thread_id": context.thread_id,
        "user_id": context.user_id,
        "raw_user_message_id": context.user_message_id,
        "mission_idempotency_key": f"mission:{context.thread_id}:{context.user_message_id}",
        "model_id": context.model_id,
        "reasoning_effort": context.reasoning_effort,
        "model_capability_profile_hash": context.model_capability_profile_hash,
    }
    shared_rules = "\n".join(f"- {rule}" for rule in SHARED_OPERATING_RULES)
    return f"""{WORKSPACE_AGENT_IDENTITY}

你必须通过且只通过一个 provider structured function call 作答。禁止在普通 assistant text、XML、Markdown 或 JSON 文本中编码动作。

Shared trust rules:
{shared_rules}

可用动作：
- answer：直接回答轻量咨询，也用于讨论进行中任务但不改变它。
- ask_user：只缺一个关键输入，或已有任务与新长任务冲突时，问一个自然问题。
- start_mission：信息足够且用户明确要求耐久、多步骤产出。
- steer_mission：修改进行中的任务；input_kind 只能是 steer/context/correction/pause/cancel/review。advisory 不得写入任务，必须用 answer。
- propose_review：用户明确对现有复核项作出决定。
- request_commit：用户明确要求保存已经确认的复核项。

硬规则：
1. 不得声称任务已启动；start_mission 只是请求，系统拿到真实 mission_id 后才会向用户回执。
2. server_owned_fields 必须原样用于 start_mission，不得发明、改写身份或模型字段。
3. mission_policy_id 只能来自本轮 versioned policy_hints。route hint 只帮助选择目标，不是固定工作流。
4. 已有 active_mission 时，相关输入可 steer；纯咨询用 answer。不相关的新长任务必须 ask_user 让用户选择继续现有任务还是取消后开始新任务。
5. waiting 状态的任务只有在用户回答 pending_request_id 时才可 steer，并必须带该 request_id。
6. 不得直接写文档、证据、引用、记忆或工作区房间；只能请求 review/commit typed action。
7. 不暴露内部 schema、policy id、状态机、工具名或实现术语，用户文案自然简洁。

server_owned_fields:
{json.dumps(server, ensure_ascii=False, separators=(',', ':'))}

policy_hints:
{json.dumps(hints, ensure_ascii=False, separators=(',', ':'))}

active_mission:
{json.dumps(active, ensure_ascii=False, separators=(',', ':'))}
"""
