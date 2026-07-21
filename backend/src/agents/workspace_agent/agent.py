"""Single chat-and-mission WorkspaceAgent with a strict provider action boundary."""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_core.messages.utils import message_chunk_to_message
from pydantic import ValidationError

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
from src.mission_runtime import MissionStartRejectedError, MissionStartRejectionCode
from src.mission_runtime.contracts import MissionStartRequest
from src.mission_runtime.production import (
    MissionProductionConfigurationError,
    MissionProductionConfigurationErrorCode,
)
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
        mission_inputs: tuple[dict[str, Any], ...] = (),
        prism_context_ref: dict[str, Any] | None = None,
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

_STREAMABLE_ACTION_FIELDS = {
    "answer": "text",
    "ask_user": "question",
}


@dataclass(slots=True)
class _StructuredTextProjector:
    action_name: str = ""
    arguments: str = ""
    emitted_chars: int = 0
    disabled: bool = False

    def feed(self, chunk: AIMessageChunk) -> str:
        for call in chunk.tool_call_chunks:
            index = call.get("index")
            if index not in (None, 0):
                self.disabled = True
                return ""
            name = str(call.get("name") or "")
            if name:
                if self.action_name and self.action_name != name:
                    self.disabled = True
                    return ""
                self.action_name = name
            arguments = call.get("args")
            if isinstance(arguments, str):
                self.arguments += arguments

        field = _STREAMABLE_ACTION_FIELDS.get(self.action_name)
        if self.disabled or field is None:
            return ""
        projected = _partial_json_string_field(self.arguments, field)
        if len(projected) <= self.emitted_chars:
            return ""
        delta = projected[self.emitted_chars :]
        self.emitted_chars = len(projected)
        return delta


def _partial_json_string_field(arguments: str, field: str) -> str:
    """Decode a complete prefix of one streamed JSON string field."""
    match = re.search(rf'"{re.escape(field)}"\s*:\s*"', arguments)
    if match is None:
        return ""

    cursor = match.end()
    raw: list[str] = []
    while cursor < len(arguments):
        char = arguments[cursor]
        if char == '"':
            break
        if char != "\\":
            if ord(char) < 0x20:
                break
            raw.append(char)
            cursor += 1
            continue

        if cursor + 1 >= len(arguments):
            break
        escaped = arguments[cursor + 1]
        if escaped == "u":
            codepoint = arguments[cursor + 2 : cursor + 6]
            if len(codepoint) < 4 or any(part not in "0123456789abcdefABCDEF" for part in codepoint):
                break
            raw.extend(("\\", "u", codepoint))
            cursor += 6
            continue
        if escaped not in '"\\/bfnrt':
            break
        raw.extend(("\\", escaped))
        cursor += 2

    try:
        decoded = json.loads(f'"{"".join(raw)}"')
    except json.JSONDecodeError:
        return ""
    if isinstance(decoded, str) and decoded and 0xD800 <= ord(decoded[-1]) <= 0xDBFF:
        decoded = decoded[:-1]
    return decoded if isinstance(decoded, str) else ""


def _tool_descriptors(
    context: WorkspaceAgentContext | None = None,
) -> list[dict[str, Any]]:
    descriptors = [
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
    if context is None:
        return descriptors

    by_name = {str(item["function"]["name"]): item["function"]["parameters"] for item in descriptors}
    available_inputs = tuple(item.input_ref for item in context.mission_inputs)
    start_spec = by_name["start_mission"]["$defs"]["MissionStartSpec"]
    _bind_array_enum(start_spec["properties"]["input_refs"], available_inputs)
    _bind_array_enum(
        by_name["steer_mission"]["properties"]["input_refs"],
        available_inputs,
    )
    policy_ids = [hint.policy_id for hint in context.policy_hints]
    if policy_ids:
        start_spec["properties"]["mission_policy_id"]["enum"] = policy_ids
    parent_schema = start_spec["properties"]["parent_mission_id"]
    if context.continuation_target is None:
        parent_schema["anyOf"] = [{"type": "null"}]
    else:
        string_branch = next(branch for branch in parent_schema["anyOf"] if branch.get("type") == "string")
        string_branch["enum"] = [context.continuation_target.mission_id]
    if context.active_mission is not None:
        active_id = context.active_mission.mission_id
        by_name["steer_mission"]["properties"]["mission_id"]["enum"] = [active_id]
    review_target = context.active_mission or context.continuation_target
    if review_target is not None:
        for action_name in ("propose_review", "request_commit"):
            by_name[action_name]["properties"]["mission_id"]["enum"] = [review_target.mission_id]
    return descriptors


def _bind_array_enum(schema: dict[str, Any], values: tuple[str, ...]) -> None:
    unique = list(dict.fromkeys(values))
    if unique:
        schema["items"]["enum"] = unique
        schema["maxItems"] = min(int(schema.get("maxItems") or len(unique)), len(unique))
        return
    schema["maxItems"] = 0


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
    except ValidationError as exc:
        issues = [f"{'.'.join(str(part) for part in issue['loc'])}: {issue['msg']}" for issue in exc.errors(include_input=False)[:8]]
        detail = "; ".join(issues) or "schema validation failed"
        raise WorkspaceAgentProtocolError(f"WorkspaceAgent returned invalid structured arguments ({detail})") from exc


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


def _with_aggregated_usage(
    response: AIMessage,
    responses: list[AIMessage],
) -> AIMessage:
    """Account for the one bounded protocol-repair call without losing usage."""

    if len(responses) == 1:
        return response
    combined: dict[str, Any] = {}
    for item in responses:
        usage = item.usage_metadata or {}
        for key, value in usage.items():
            if isinstance(value, int):
                combined[key] = int(combined.get(key) or 0) + value
            elif isinstance(value, dict):
                nested = combined.setdefault(key, {})
                if not isinstance(nested, dict):
                    continue
                for nested_key, nested_value in value.items():
                    if isinstance(nested_value, int):
                        nested[nested_key] = int(nested.get(nested_key) or 0) + nested_value
    if not combined:
        return response
    return response.model_copy(update={"usage_metadata": combined})


class WorkspaceAgent:
    def __init__(self, *, model: BaseChatModel, missions: WorkspaceMissionPort) -> None:
        self._model = model
        self._missions = missions

    async def decide(
        self,
        context: WorkspaceAgentContext,
        *,
        on_text_delta: Callable[[str], Awaitable[None]] | None = None,
    ) -> tuple[AgentAction, AIMessage]:
        bound = self._model.bind_tools(
            _tool_descriptors(context),
            tool_choice="required",
            strict=True,
        )
        base_messages = _conversation_messages(context)
        responses: list[AIMessage] = []
        feedback: str | None = None
        for attempt in range(2):
            messages = list(base_messages)
            if feedback is not None:
                messages.insert(
                    1,
                    SystemMessage(
                        content=(
                            "Your previous structured action violated the provider contract. "
                            f"Correct it now: {feedback}. Return exactly one allowed function "
                            "call and no prose. input_refs may contain only exact mission-input "
                            "values offered by the current tool schema; inherited artifact and "
                            "academic-visual refs are carried by the continuation Mission."
                        )
                    ),
                )
            response = await self._stream_provider_action(
                bound,
                messages,
                on_text_delta=on_text_delta,
            )
            responses.append(response)
            try:
                action = parse_provider_action(response)
                self._validate_action_context(action, context)
            except WorkspaceAgentProtocolError as exc:
                if attempt == 1:
                    raise
                feedback = str(exc)
                continue
            return action, _with_aggregated_usage(response, responses)
        raise WorkspaceAgentProtocolError("WorkspaceAgent could not produce a valid action")

    @staticmethod
    async def _stream_provider_action(
        bound: Any,
        messages: list[BaseMessage],
        *,
        on_text_delta: Callable[[str], Awaitable[None]] | None,
    ) -> AIMessage:
        aggregate: AIMessageChunk | None = None
        projector = _StructuredTextProjector()
        async for chunk in bound.astream(messages):
            if not isinstance(chunk, AIMessageChunk):
                raise WorkspaceAgentProtocolError(
                    "WorkspaceAgent provider stream returned a non-message chunk"
                )
            aggregate = chunk if aggregate is None else aggregate + chunk
            if on_text_delta is not None:
                delta = projector.feed(chunk)
                if delta:
                    await on_text_delta(delta)
        if aggregate is None:
            raise WorkspaceAgentProtocolError("WorkspaceAgent provider stream was empty")
        response = message_chunk_to_message(aggregate)
        if not isinstance(response, AIMessage):
            raise WorkspaceAgentProtocolError(
                "WorkspaceAgent provider stream returned a non-message response"
            )
        return response

    def _validate_action_context(
        self,
        action: AgentAction,
        context: WorkspaceAgentContext,
    ) -> None:
        if isinstance(action, StartMissionAction):
            self._validate_start_policy(action, context)
            self._validate_start_parent(action, context)
            try:
                context.select_mission_inputs(
                    action.mission.input_refs,
                    include_current=True,
                )
            except ValueError as exc:
                raise WorkspaceAgentProtocolError(str(exc)) from exc
            return
        if isinstance(action, SteerMissionAction):
            self._validate_active_target(action.mission_id, context)
            if action.input_kind.value == "advisory":
                raise WorkspaceAgentProtocolError("Advisory input cannot mutate a mission")
            try:
                context.select_mission_inputs(
                    action.input_refs,
                    include_current=True,
                )
            except ValueError as exc:
                raise WorkspaceAgentProtocolError(str(exc)) from exc
            return
        if isinstance(action, (ProposeReviewAction, RequestCommitAction)):
            self._validate_review_target(action.mission_id, context)

    async def run(
        self,
        context: WorkspaceAgentContext,
        *,
        on_text_delta: Callable[[str], Awaitable[None]] | None = None,
    ) -> WorkspaceAgentReply:
        action, provider_message = await self.decide(
            context,
            on_text_delta=on_text_delta,
        )
        usage = provider_message.usage_metadata or {}
        if isinstance(action, AnswerAction):
            return WorkspaceAgentReply(text=action.text, action=action, metadata={"usage": usage})
        if isinstance(action, AskUserAction):
            choices = "\n".join(f"- {choice}" for choice in action.choices)
            text = action.question if not choices else f"{action.question}\n{choices}"
            return WorkspaceAgentReply(text=text, action=action, metadata={"usage": usage})
        if isinstance(action, StartMissionAction):
            policy_hint = self._validate_start_policy(action, context)
            parent_mission_id = self._validate_start_parent(action, context)
            if context.active_mission is not None and context.active_mission.status not in {"completed", "failed", "cancelled"}:
                question = AskUserAction(
                    request_id=f"mission-choice:{context.user_message_id}",
                    question=(f"当前还有“{context.active_mission.title}”在进行。你想继续调整这个任务，还是先取消它再开始新的任务？"),
                    choices=("继续当前任务", "取消后开始新任务"),
                )
                return WorkspaceAgentReply(text=question.question, action=question, metadata={"usage": usage})
            spec = action.mission
            try:
                selected_inputs = context.select_mission_inputs(
                    spec.input_refs,
                    include_current=True,
                )
            except ValueError as exc:
                raise WorkspaceAgentProtocolError(str(exc)) from exc
            prism_context = context.prism_context_ref.model_dump(mode="json") if context.prism_context_ref else None
            try:
                receipt = await self._missions.start(
                    MissionStartRequest(
                        workspace_id=context.workspace_id,
                        thread_id=context.thread_id,
                        user_id=context.user_id,
                        workspace_type=context.workspace_type,
                        title=spec.title,
                        objective=spec.objective,
                        mission_idempotency_key=(f"mission:{context.thread_id}:{context.user_message_id}"),
                        mission_policy_id=spec.mission_policy_id,
                        parent_mission_id=parent_mission_id,
                        review_mode=context.review_mode.value,
                        model_id=context.model_id,
                        reasoning_effort=context.reasoning_effort,
                        snapshot_json={
                            "intake": {item.key: item.value for item in spec.initial_params},
                            "mission_inputs": [item.model_dump(mode="json") for item in selected_inputs],
                            **({"prism_context_ref": prism_context} if prism_context is not None else {}),
                        },
                        runtime_context_json={
                            "policy_ref": (f"{spec.mission_policy_id}@{policy_hint.content_hash}"),
                            "policy_content_hash": policy_hint.content_hash,
                            "model_capability_profile_hash": (context.model_capability_profile_hash),
                            "context_refs": [item.input_ref for item in selected_inputs],
                            **({"prism_context_ref": (f"prism-file:{context.prism_context_ref.file_id}@{context.prism_context_ref.base_revision_ref}")} if context.prism_context_ref else {}),
                        },
                    )
                )
            except MissionProductionConfigurationError as exc:
                if exc.code is MissionProductionConfigurationErrorCode.NATIVE_SEARCH_UNAVAILABLE:
                    text = "当前模型的联网检索还没有通过完整性验证，因此研究任务没有启动。你可以继续和我收紧选题或设计方法；待联网验证恢复后再启动系统检索。"
                else:
                    text = "当前任务的运行配置暂未就绪，因此研究任务没有启动。你的对话和材料已经保留，请稍后重试。"
                return WorkspaceAgentReply(
                    text=text,
                    action=action,
                    metadata={
                        "usage": usage,
                        "mission_start": {
                            "status": "not_started",
                            "reason": exc.code.value,
                            "detail": str(exc),
                        },
                    },
                )
            except MissionStartRejectedError as exc:
                if exc.code is MissionStartRejectionCode.CONTINUATION_POLICY_CHANGED:
                    text = "这个任务使用的研究方法版本已经更新，无法直接续接旧运行。旧成果仍然保留；请基于现有材料启动一个新任务。"
                elif exc.code is MissionStartRejectionCode.CONTINUATION_PARENT_NOT_TERMINAL:
                    text = "当前任务仍在进行，请先继续或结束它，再创建续接任务。"
                elif exc.code in {
                    MissionStartRejectionCode.CONTINUATION_PARENT_NOT_FOUND,
                    MissionStartRejectionCode.CONTINUATION_IDENTITY_MISMATCH,
                }:
                    text = "没有找到可可靠续接的同一研究任务，请基于现有材料启动一个新任务。"
                elif exc.code is MissionStartRejectionCode.INVALID_START_STATE:
                    text = "任务启动信息不完整，因此研究任务没有启动。请重新描述你的目标。"
                else:
                    text = str(exc)
                return WorkspaceAgentReply(
                    text=text,
                    action=action,
                    metadata={
                        "usage": usage,
                        "mission_start": {
                            "status": "not_started",
                            "reason": exc.code.value,
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
            try:
                selected_inputs = context.select_mission_inputs(
                    action.input_refs,
                    include_current=True,
                )
            except ValueError as exc:
                raise WorkspaceAgentProtocolError(str(exc)) from exc
            mission = await self._missions.steer(
                action.mission_id,
                command_id=action.command_id,
                actor_user_id=context.user_id,
                input_kind=action.input_kind.value,
                instruction=action.instruction,
                request_id=action.request_id,
                mission_inputs=tuple(item.model_dump(mode="json") for item in selected_inputs),
                prism_context_ref=(context.prism_context_ref.model_dump(mode="json") if context.prism_context_ref else None),
            )
            label = "已取消当前任务。" if action.input_kind.value == "cancel" else "已把你的补充交给当前任务。"
            return WorkspaceAgentReply(text=label, action=action, mission_id=mission.mission_id, metadata={"usage": usage})
        if isinstance(action, ProposeReviewAction):
            self._validate_review_target(action.mission_id, context)
            mission = await self._missions.review(
                action.mission_id,
                decision_id=f"review:{context.user_message_id}",
                actor_user_id=context.user_id,
                review_item_ids=action.review_item_ids,
                decision=action.decision,
                rationale=action.rationale,
            )
            continued = mission.mission_id != action.mission_id
            text = "已根据你的反馈开始补充研究，新的进展会在工作台更新。" if continued else "已记录你的确认决定。"
            return WorkspaceAgentReply(text=text, action=action, mission_id=mission.mission_id, metadata={"usage": usage})
        self._validate_review_target(action.mission_id, context)
        mission = await self._missions.request_commit(
            action.mission_id,
            actor_user_id=context.user_id,
            review_item_ids=action.review_item_ids,
            request_id=f"commit:{context.user_message_id}",
        )
        continued = mission.mission_id != action.mission_id
        text = "保存时发现内容已变化，问津已开始重新生成受影响部分。" if continued else "已提交保存请求，保存进展会在工作台更新。"
        return WorkspaceAgentReply(text=text, action=action, mission_id=mission.mission_id, metadata={"usage": usage})

    @staticmethod
    def _validate_start_policy(
        action: StartMissionAction,
        context: WorkspaceAgentContext,
    ) -> MissionPolicyHint:
        spec = action.mission
        policy_hint = context.policy_hint(spec.mission_policy_id)
        if policy_hint is None:
            raise WorkspaceAgentProtocolError("Provider selected an unknown MissionPolicy")
        return policy_hint

    @staticmethod
    def _validate_start_parent(
        action: StartMissionAction,
        context: WorkspaceAgentContext,
    ) -> str | None:
        parent_mission_id = action.mission.parent_mission_id
        if parent_mission_id is None:
            return None
        target = context.continuation_target
        if target is None or target.mission_id != parent_mission_id:
            raise WorkspaceAgentProtocolError("Provider selected a Mission outside the continuation context")
        if target.mission_policy_id != action.mission.mission_policy_id:
            raise WorkspaceAgentProtocolError("Continuation must keep the parent MissionPolicy")
        return parent_mission_id

    @staticmethod
    def _validate_active_target(
        mission_id: str,
        context: WorkspaceAgentContext,
    ) -> None:
        active = context.active_mission
        if active is None or active.mission_id != mission_id:
            raise WorkspaceAgentProtocolError("Provider targeted a mission outside the active thread context")

    @staticmethod
    def _validate_review_target(
        mission_id: str,
        context: WorkspaceAgentContext,
    ) -> None:
        target = context.active_mission or context.continuation_target
        if target is None or target.mission_id != mission_id:
            raise WorkspaceAgentProtocolError("Provider targeted a mission outside the focused thread context")
