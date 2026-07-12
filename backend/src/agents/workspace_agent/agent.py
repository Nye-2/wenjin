"""Single chat-and-mission WorkspaceAgent with a strict provider action boundary."""

from __future__ import annotations

from typing import Any, Protocol

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from src.agents.workspace_agent.contracts import (
    AgentAction,
    AgentActionAdapter,
    AnswerAction,
    AskUserAction,
    MissionPolicyHint,
    ProposeReviewAction,
    RequestCommitAction,
    StartMissionAction,
    SteerMissionAction,
    WorkspaceAgentContext,
    WorkspaceAgentReply,
)
from src.agents.workspace_agent.prompts import render_workspace_agent_prompt
from src.mission_runtime.contracts import MissionStartRequest
from src.mission_runtime.production import MissionProductionConfigurationError
from src.models.provider_schema import strict_provider_schema


class WorkspaceAgentProtocolError(RuntimeError):
    """Provider did not return exactly one valid structured action frame."""


class WorkspaceMissionPort(Protocol):
    async def start(self, request: MissionStartRequest): ...

    async def steer(
        self,
        mission_id: str,
        *,
        command_id: str,
        actor_user_id: str,
        input_kind: str,
        instruction: str,
        request_id: str | None = None,
    ): ...

    async def review(
        self,
        mission_id: str,
        *,
        decision_id: str,
        actor_user_id: str,
        review_item_ids: tuple[str, ...],
        decision: str,
        rationale: str | None,
    ): ...

    async def request_commit(
        self,
        mission_id: str,
        *,
        actor_user_id: str,
        review_item_ids: tuple[str, ...],
        request_id: str,
    ): ...


_ACTION_MODELS = {
    "answer": AnswerAction,
    "ask_user": AskUserAction,
    "start_mission": StartMissionAction,
    "steer_mission": SteerMissionAction,
    "propose_review": ProposeReviewAction,
    "request_commit": RequestCommitAction,
}


def _tool_descriptors() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": f"Return the WorkspaceAgent {name} action.",
                "parameters": strict_provider_schema(model.model_json_schema()),
                "strict": True,
            },
        }
        for name, model in _ACTION_MODELS.items()
    ]


def parse_provider_action(message: AIMessage) -> AgentAction:
    """Accept provider tool-call frames only; never parse assistant prose."""
    calls = message.tool_calls
    if len(calls) != 1:
        raise WorkspaceAgentProtocolError("WorkspaceAgent requires exactly one structured action")
    call = calls[0]
    name = str(call.get("name") or "")
    if name not in _ACTION_MODELS:
        raise WorkspaceAgentProtocolError(f"Unknown WorkspaceAgent action: {name}")
    arguments = call.get("args")
    if not isinstance(arguments, dict):
        raise WorkspaceAgentProtocolError("WorkspaceAgent action arguments must be an object")
    payload = {**arguments, "action": name}
    try:
        return AgentActionAdapter.validate_python(payload)
    except Exception as exc:
        raise WorkspaceAgentProtocolError("WorkspaceAgent returned invalid structured arguments") from exc


def _conversation_messages(context: WorkspaceAgentContext) -> list[BaseMessage]:
    messages: list[BaseMessage] = [SystemMessage(render_workspace_agent_prompt(context))]
    for item in context.conversation[-40:]:
        role = str(item.get("role") or "").strip()
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        if role == "user":
            messages.append(HumanMessage(content))
        elif role == "assistant":
            messages.append(AIMessage(content))
    if not messages or not isinstance(messages[-1], HumanMessage):
        messages.append(HumanMessage(context.user_message))
    return messages


class WorkspaceAgent:
    def __init__(self, *, model: BaseChatModel, missions: WorkspaceMissionPort) -> None:
        self._model = model
        self._missions = missions

    async def decide(self, context: WorkspaceAgentContext) -> tuple[AgentAction, AIMessage]:
        bound = self._model.bind_tools(
            _tool_descriptors(),
            tool_choice="required",
            strict=True,
        )
        response = await bound.ainvoke(_conversation_messages(context))
        if not isinstance(response, AIMessage):
            raise WorkspaceAgentProtocolError("WorkspaceAgent provider returned a non-message response")
        return parse_provider_action(response), response

    async def run(self, context: WorkspaceAgentContext) -> WorkspaceAgentReply:
        action, provider_message = await self.decide(context)
        usage = provider_message.usage_metadata or {}
        if isinstance(action, AnswerAction):
            return WorkspaceAgentReply(text=action.text, action=action, metadata={"usage": usage})
        if isinstance(action, AskUserAction):
            choices = "\n".join(f"- {choice}" for choice in action.choices)
            text = action.question if not choices else f"{action.question}\n{choices}"
            return WorkspaceAgentReply(text=text, action=action, metadata={"usage": usage})
        if isinstance(action, StartMissionAction):
            policy_hint = self._validate_start_identity(action, context)
            if (
                context.active_mission is not None
                and context.active_mission.status not in {"completed", "failed", "cancelled"}
            ):
                question = AskUserAction(
                    request_id=f"mission-choice:{context.user_message_id}",
                    question=(
                        f"当前还有“{context.active_mission.title}”在进行。"
                        "你想继续调整这个任务，还是先取消它再开始新的任务？"
                    ),
                    choices=("继续当前任务", "取消后开始新任务"),
                )
                return WorkspaceAgentReply(text=question.question, action=question, metadata={"usage": usage})
            spec = action.mission
            try:
                receipt = await self._missions.start(
                    MissionStartRequest(
                        workspace_id=spec.workspace_id,
                        thread_id=spec.thread_id,
                        user_id=spec.user_id,
                        workspace_type=spec.workspace_type,
                        title=spec.objective[:300],
                        objective=spec.objective,
                        mission_idempotency_key=spec.mission_idempotency_key,
                        mission_policy_id=spec.mission_policy_id,
                        review_mode=spec.review_mode.value,
                        model_id=spec.model_id,
                        reasoning_effort=spec.reasoning_effort,
                        snapshot_json={
                            "intake": {
                                item.key: item.value for item in spec.initial_params
                            }
                        },
                        runtime_context_json={
                            "policy_ref": (
                                f"{spec.mission_policy_id}@{policy_hint.content_hash}"
                            ),
                            "policy_content_hash": policy_hint.content_hash,
                            "model_capability_profile_hash": (
                                spec.model_capability_profile_hash
                            ),
                            "context_refs": list(spec.runtime_context_refs),
                        },
                    )
                )
            except MissionProductionConfigurationError as exc:
                return WorkspaceAgentReply(
                    text=(
                        "当前模型的联网检索还没有通过完整性验证，因此研究任务没有启动。"
                        "你可以继续和我收紧选题或设计方法；待联网验证恢复后再启动系统检索。"
                    ),
                    action=action,
                    metadata={
                        "usage": usage,
                        "mission_start": {
                            "status": "not_started",
                            "reason": "runtime_capability_unavailable",
                            "detail": str(exc),
                        },
                    },
                )
            text = f"已开始处理“{receipt.title}”。我会在工作台持续更新进展。"
            return WorkspaceAgentReply(
                text=text,
                action=action,
                mission_id=receipt.mission_id,
                metadata={"usage": usage, "mission": receipt.model_dump(mode="json")},
            )
        if isinstance(action, SteerMissionAction):
            self._validate_active_target(action.mission_id, context)
            if action.input_kind.value == "advisory":
                raise WorkspaceAgentProtocolError("Advisory input cannot mutate a mission")
            mission = await self._missions.steer(
                action.mission_id,
                command_id=action.command_id,
                actor_user_id=context.user_id,
                input_kind=action.input_kind.value,
                instruction=action.instruction,
                request_id=action.request_id,
            )
            label = "已取消当前任务。" if action.input_kind.value == "cancel" else "已把你的补充交给当前任务。"
            return WorkspaceAgentReply(text=label, action=action, mission_id=mission.mission_id, metadata={"usage": usage})
        if isinstance(action, ProposeReviewAction):
            self._validate_active_target(action.mission_id, context)
            mission = await self._missions.review(
                action.mission_id,
                decision_id=f"review:{context.user_message_id}",
                actor_user_id=context.user_id,
                review_item_ids=action.review_item_ids,
                decision=action.decision,
                rationale=action.rationale,
            )
            return WorkspaceAgentReply(text="已记录你的复核决定。", action=action, mission_id=mission.mission_id, metadata={"usage": usage})
        self._validate_active_target(action.mission_id, context)
        mission = await self._missions.request_commit(
            action.mission_id,
            actor_user_id=context.user_id,
            review_item_ids=action.review_item_ids,
            request_id=f"commit:{context.user_message_id}",
        )
        return WorkspaceAgentReply(text="已提交保存请求，保存进展会在工作台更新。", action=action, mission_id=mission.mission_id, metadata={"usage": usage})

    @staticmethod
    def _validate_start_identity(
        action: StartMissionAction,
        context: WorkspaceAgentContext,
    ) -> MissionPolicyHint:
        spec = action.mission
        expected = {
            "workspace_id": context.workspace_id,
            "thread_id": context.thread_id,
            "user_id": context.user_id,
            "workspace_type": context.workspace_type,
            "raw_user_message_id": context.user_message_id,
            "mission_idempotency_key": f"mission:{context.thread_id}:{context.user_message_id}",
            "model_id": context.model_id,
            "reasoning_effort": context.reasoning_effort,
            "model_capability_profile_hash": context.model_capability_profile_hash,
        }
        for field, value in expected.items():
            if getattr(spec, field) != value:
                raise WorkspaceAgentProtocolError(f"Provider changed server-owned field: {field}")
        policy_hint = context.policy_hint(spec.mission_policy_id)
        if policy_hint is None:
            raise WorkspaceAgentProtocolError("Provider selected an unknown MissionPolicy")
        return policy_hint

    @staticmethod
    def _validate_active_target(
        mission_id: str,
        context: WorkspaceAgentContext,
    ) -> None:
        active = context.active_mission
        if active is None or active.mission_id != mission_id:
            raise WorkspaceAgentProtocolError("Provider targeted a mission outside the active thread context")
