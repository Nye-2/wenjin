from __future__ import annotations

from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage

from src.agents.workspace_agent.agent import (
    WorkspaceAgent,
    WorkspaceAgentProtocolError,
    _tool_descriptors,
    parse_provider_action,
)
from src.agents.workspace_agent.contracts import (
    ActiveMissionContext,
    MissionPolicyHint,
    WorkspaceAgentContext,
)
from src.mission_runtime.contracts import MissionStartReceipt


class FakeModel:
    def __init__(self, message: AIMessage) -> None:
        self.message = message
        self.bind_kwargs = None

    def bind_tools(self, tools, **kwargs):
        self.bind_kwargs = (tools, kwargs)
        return self

    async def ainvoke(self, messages):
        self.messages = messages
        return self.message


class FakeMissions:
    def __init__(self) -> None:
        self.starts = []
        self.steers = []
        self.reviews = []
        self.commits = []
        self.by_key = {}
        self.start_error = None

    async def start(self, request):
        if self.start_error is not None:
            raise self.start_error
        self.starts.append(request)
        receipt = self.by_key.get(request.mission_idempotency_key)
        if receipt is None:
            receipt = MissionStartReceipt(
                mission_id="mission-1",
                status="created",
                title=request.title,
                created=True,
                wakeup_published=True,
            )
            self.by_key[request.mission_idempotency_key] = receipt
        return receipt

    async def steer(self, mission_id, **kwargs):
        self.steers.append((mission_id, kwargs))
        return SimpleNamespace(mission_id=mission_id)

    async def review(self, mission_id, **kwargs):
        self.reviews.append((mission_id, kwargs))
        return SimpleNamespace(mission_id=mission_id)

    async def request_commit(self, mission_id, **kwargs):
        self.commits.append((mission_id, kwargs))
        return SimpleNamespace(mission_id=mission_id)


def context(*, active: ActiveMissionContext | None = None) -> WorkspaceAgentContext:
    return WorkspaceAgentContext(
        workspace_id="workspace-1",
        workspace_type="sci",
        thread_id="thread-1",
        user_id="user-1",
        user_message_id="message-1",
        user_message="梳理联邦学习研究空白",
        model_id="gpt-5.5",
        reasoning_effort="xhigh",
        model_capability_profile_hash="a" * 64,
        conversation=({"role": "user", "content": "梳理联邦学习研究空白"},),
        policy_hints=(
            MissionPolicyHint(
                policy_id="sci.research",
                content_hash="b" * 64,
                display_name="研究定位",
                summary="形成可验证的研究空白与创新点",
                positive_examples=("梳理研究空白",),
                required_context=("topic",),
            ),
        ),
        active_mission=active,
    )


def tool_message(name: str, args: dict) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": "call-1"}])


def start_args() -> dict:
    return {
        "mission": {
            "workspace_id": "workspace-1",
            "thread_id": "thread-1",
            "user_id": "user-1",
            "workspace_type": "sci",
            "raw_user_message_id": "message-1",
            "mission_idempotency_key": "mission:thread-1:message-1",
            "objective": "梳理联邦学习研究空白",
            "mission_policy_id": "sci.research",
            "initial_params": [{"key": "topic", "value": "联邦学习"}],
            "review_mode": "balanced_default",
            "model_id": "gpt-5.5",
            "reasoning_effort": "xhigh",
            "model_capability_profile_hash": "a" * 64,
            "runtime_context_refs": [],
        }
    }


@pytest.mark.asyncio
async def test_advisory_answer_never_mutates_mission() -> None:
    missions = FakeMissions()
    agent = WorkspaceAgent(
        model=FakeModel(tool_message("answer", {"text": "这是一个轻量解释。"})),
        missions=missions,
    )
    reply = await agent.run(context(active=ActiveMissionContext(
        mission_id="mission-1",
        title="研究定位",
        objective="梳理空白",
        status="running",
    )))
    assert reply.action.action == "answer"
    assert not missions.starts and not missions.steers


@pytest.mark.asyncio
async def test_clarification_returns_one_structured_question() -> None:
    missions = FakeMissions()
    agent = WorkspaceAgent(
        model=FakeModel(tool_message("ask_user", {
            "request_id": "question-1",
            "question": "你希望聚焦哪个应用领域？",
            "choices": [],
        })),
        missions=missions,
    )
    reply = await agent.run(context())
    assert reply.text == "你希望聚焦哪个应用领域？"
    assert not missions.starts


@pytest.mark.asyncio
async def test_start_is_idempotent_and_receipt_contains_real_mission_id() -> None:
    missions = FakeMissions()
    first = await WorkspaceAgent(
        model=FakeModel(tool_message("start_mission", start_args())),
        missions=missions,
    ).run(context())
    second = await WorkspaceAgent(
        model=FakeModel(tool_message("start_mission", start_args())),
        missions=missions,
    ).run(context())
    assert first.mission_id == second.mission_id == "mission-1"
    assert len(missions.by_key) == 1
    assert missions.starts[0].runtime_context_json["policy_content_hash"] == "b" * 64
    assert missions.starts[0].runtime_context_json["policy_ref"] == f"sci.research@{'b' * 64}"
    assert missions.starts[0].snapshot_json["intake"] == {"topic": "联邦学习"}
    assert "已开始处理" in first.text


def test_provider_tool_schemas_are_recursively_strict() -> None:
    def assert_strict(node) -> None:
        if isinstance(node, dict):
            assert "default" not in node
            properties = node.get("properties")
            if isinstance(properties, dict):
                assert node.get("additionalProperties") is False
                assert node.get("required") == list(properties)
            for value in node.values():
                assert_strict(value)
        elif isinstance(node, list):
            for value in node:
                assert_strict(value)

    for descriptor in _tool_descriptors():
        assert descriptor["function"]["strict"] is True
        assert_strict(descriptor["function"]["parameters"])


@pytest.mark.asyncio
async def test_unverified_runtime_capability_is_a_user_facing_non_start() -> None:
    from src.mission_runtime.production import MissionProductionConfigurationError

    missions = FakeMissions()
    missions.start_error = MissionProductionConfigurationError(
        "completed_event_boundary_not_verified"
    )
    reply = await WorkspaceAgent(
        model=FakeModel(tool_message("start_mission", start_args())),
        missions=missions,
    ).run(context())

    assert reply.mission_id is None
    assert "研究任务没有启动" in reply.text
    assert reply.metadata["mission_start"]["status"] == "not_started"


@pytest.mark.asyncio
async def test_active_mission_steer_appends_typed_command() -> None:
    missions = FakeMissions()
    active = ActiveMissionContext(
        mission_id="mission-1",
        title="研究定位",
        objective="梳理空白",
        status="running",
    )
    agent = WorkspaceAgent(
        model=FakeModel(tool_message("steer_mission", {
            "mission_id": "mission-1",
            "command_id": "command-1",
            "input_kind": "correction",
            "instruction": "聚焦医疗场景",
        })),
        missions=missions,
    )
    await agent.run(context(active=active))
    assert missions.steers == [("mission-1", {
        "command_id": "command-1",
        "actor_user_id": "user-1",
        "input_kind": "correction",
        "instruction": "聚焦医疗场景",
        "request_id": None,
    })]


@pytest.mark.asyncio
async def test_unrelated_new_mission_requires_user_choice() -> None:
    missions = FakeMissions()
    active = ActiveMissionContext(
        mission_id="mission-1",
        title="联邦学习研究定位",
        objective="梳理空白",
        status="running",
    )
    reply = await WorkspaceAgent(
        model=FakeModel(tool_message("start_mission", start_args())),
        missions=missions,
    ).run(context(active=active))
    assert reply.action.action == "ask_user"
    assert "继续" in reply.text
    assert not missions.starts


def test_plain_assistant_text_is_never_parsed_as_action() -> None:
    with pytest.raises(WorkspaceAgentProtocolError, match="exactly one"):
        parse_provider_action(AIMessage(content='{"action":"start_mission"}'))
