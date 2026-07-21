from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk

from src.agents.workspace_agent.agent import (
    WorkspaceAgent,
    WorkspaceAgentProtocolError,
    _tool_descriptors,
    parse_provider_action,
)
from src.agents.workspace_agent.contracts import (
    ActiveMissionContext,
    ContinuationMissionContext,
    MissionPolicyHint,
    WorkspaceAgentContext,
)
from src.contracts.mission_input import MissionInputContext, MissionInputManifest
from src.mission_runtime.contracts import MissionStartReceipt


class FakeModel:
    def __init__(self, message: AIMessage) -> None:
        self.message = message
        self.bind_kwargs = None

    def bind_tools(self, tools, **kwargs):
        self.bind_kwargs = (tools, kwargs)
        return self

    async def astream(self, messages):
        self.messages = messages
        yield AIMessageChunk(
            content=self.message.content,
            tool_calls=self.message.tool_calls,
            usage_metadata=self.message.usage_metadata,
        )


class SequenceModel:
    def __init__(self, messages: list[AIMessage]) -> None:
        self.messages = list(messages)
        self.invocations = []

    def bind_tools(self, tools, **kwargs):
        self.bind_kwargs = (tools, kwargs)
        return self

    async def astream(self, messages):
        self.invocations.append(messages)
        message = self.messages.pop(0)
        yield AIMessageChunk(
            content=message.content,
            tool_calls=message.tool_calls,
            usage_metadata=message.usage_metadata,
        )


class ControlledStreamModel:
    def __init__(self, chunks: list[AIMessageChunk]) -> None:
        self.chunks = chunks
        self.first_chunk_sent = asyncio.Event()
        self.release = asyncio.Event()
        self.closed = asyncio.Event()

    def bind_tools(self, tools, **kwargs):
        self.bind_kwargs = (tools, kwargs)
        return self

    async def astream(self, messages):
        self.messages = messages
        try:
            yield self.chunks[0]
            self.first_chunk_sent.set()
            await self.release.wait()
            for chunk in self.chunks[1:]:
                yield chunk
        finally:
            self.closed.set()


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


def context(
    *,
    active: ActiveMissionContext | None = None,
    continuation: ContinuationMissionContext | None = None,
    mission_inputs: tuple[MissionInputManifest, ...] = (),
    attachment_contexts: tuple[MissionInputContext, ...] = (),
) -> WorkspaceAgentContext:
    return WorkspaceAgentContext(
        workspace_id="workspace-1",
        workspace_type="sci",
        thread_id="thread-1",
        user_id="user-1",
        user_message_id="message-1",
        user_message="梳理联邦学习研究空白",
        model_id="gpt-5.6-sol",
        reasoning_effort="xhigh",
        model_capability_profile_hash="a" * 64,
        review_mode="auto_draft",
        conversation=({"role": "user", "content": "梳理联邦学习研究空白"},),
        mission_inputs=mission_inputs,
        attachment_contexts=attachment_contexts,
        policy_hints=(
            MissionPolicyHint(
                policy_id="sci.research",
                content_hash="b" * 64,
                display_name="研究定位",
                summary="形成可验证的研究空白与创新点",
                positive_examples=("梳理研究空白",),
                required_context=("topic",),
                completion_targets={"literature_positioning": ("scope", "literature")},
                default_completion_target="literature_positioning",
            ),
        ),
        active_mission=active,
        continuation_target=continuation,
    )


def tool_message(
    name: str,
    args: dict,
    *,
    usage_metadata: dict | None = None,
) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": "call-1"}],
        usage_metadata=usage_metadata,
    )


def start_args() -> dict:
    return {
        "mission": {
            "title": "联邦学习研究空白",
            "objective": "梳理联邦学习研究空白",
            "mission_policy_id": "sci.research",
            "initial_params": [
                {"key": "topic", "value": "联邦学习"},
                {"key": "target_outcome", "value": "literature_positioning"},
            ],
        }
    }


@pytest.mark.asyncio
async def test_advisory_answer_never_mutates_mission() -> None:
    missions = FakeMissions()
    agent = WorkspaceAgent(
        model=FakeModel(tool_message("answer", {"text": "这是一个轻量解释。"})),
        missions=missions,
    )
    reply = await agent.run(
        context(
            active=ActiveMissionContext(
                mission_id="mission-1",
                title="研究定位",
                objective="梳理空白",
                status="running",
            )
        )
    )
    assert reply.action.action == "answer"
    assert not missions.starts and not missions.steers


@pytest.mark.asyncio
async def test_clarification_returns_one_structured_question() -> None:
    missions = FakeMissions()
    agent = WorkspaceAgent(
        model=FakeModel(
            tool_message(
                "ask_user",
                {
                    "request_id": "question-1",
                    "question": "你希望聚焦哪个应用领域？",
                    "choices": [],
                },
            )
        ),
        missions=missions,
    )
    reply = await agent.run(context())
    assert reply.text == "你希望聚焦哪个应用领域？"
    assert not missions.starts


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("action_name", "first_args", "second_args", "expected_first", "expected_text"),
    [
        ("answer", '{"text":"前半', '后半"}', "前半", "前半后半"),
        (
            "ask_user",
            '{"request_id":"question-1","question":"选择',
            '方向？","choices":[]}',
            "选择",
            "选择方向？",
        ),
    ],
)
async def test_streams_public_structured_text_before_provider_completion(
    action_name: str,
    first_args: str,
    second_args: str,
    expected_first: str,
    expected_text: str,
) -> None:
    model = ControlledStreamModel(
        [
            AIMessageChunk(
                content="",
                additional_kwargs={"reasoning": "hidden chain of thought"},
                tool_call_chunks=[
                    {
                        "name": action_name,
                        "args": first_args,
                        "id": "call-1",
                        "index": 0,
                    }
                ],
            ),
            AIMessageChunk(
                content="",
                tool_call_chunks=[
                    {
                        "name": None,
                        "args": second_args,
                        "id": None,
                        "index": 0,
                    }
                ],
                usage_metadata={
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "total_tokens": 15,
                },
            ),
        ]
    )
    deltas: list[str] = []

    async def on_text_delta(delta: str) -> None:
        deltas.append(delta)

    task = asyncio.create_task(
        WorkspaceAgent(model=model, missions=FakeMissions()).run(
            context(),
            on_text_delta=on_text_delta,
        )
    )
    await model.first_chunk_sent.wait()

    assert deltas == [expected_first]
    assert "hidden chain of thought" not in "".join(deltas)
    assert task.done() is False

    model.release.set()
    reply = await task

    assert reply.text == expected_text
    assert "".join(deltas) == expected_text
    assert model.closed.is_set()


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
    assert missions.starts[0].workspace_id == "workspace-1"
    assert missions.starts[0].thread_id == "thread-1"
    assert missions.starts[0].user_id == "user-1"
    assert missions.starts[0].model_id == "gpt-5.6-sol"
    assert missions.starts[0].reasoning_effort == "xhigh"
    assert missions.starts[0].review_mode == "auto_draft"
    assert missions.starts[0].title == "联邦学习研究空白"
    assert missions.starts[0].snapshot_json["intake"] == {
        "target_outcome": "literature_positioning",
        "topic": "联邦学习",
    }
    assert "已开始处理" in first.text


@pytest.mark.asyncio
async def test_continuation_start_uses_only_the_server_projected_parent() -> None:
    parent = ContinuationMissionContext(
        mission_id="11111111-1111-1111-1111-111111111111",
        title="联邦学习研究空白",
        objective="梳理联邦学习研究空白",
        status="failed",
        mission_policy_id="sci.research",
        passed_stage_ids=("scope", "literature"),
    )
    args = start_args()
    args["mission"]["parent_mission_id"] = parent.mission_id
    missions = FakeMissions()

    await WorkspaceAgent(
        model=FakeModel(tool_message("start_mission", args)),
        missions=missions,
    ).run(context(continuation=parent))

    assert missions.starts[0].parent_mission_id == parent.mission_id


@pytest.mark.asyncio
async def test_continuation_start_rejects_a_parent_outside_context() -> None:
    args = start_args()
    args["mission"]["parent_mission_id"] = "22222222-2222-2222-2222-222222222222"

    with pytest.raises(WorkspaceAgentProtocolError, match="continuation context"):
        await WorkspaceAgent(
            model=FakeModel(tool_message("start_mission", args)),
            missions=FakeMissions(),
        ).run(context())


@pytest.mark.asyncio
async def test_start_pins_only_model_selected_conversation_inputs() -> None:
    manifest = MissionInputManifest(
        input_ref=f"mission-input:{'c' * 64}",
        workspace_id="workspace-1",
        thread_id="thread-1",
        filename="problem.pdf",
        mime_type="application/pdf",
        extractor="pdf_text",
        content_hash=f"sha256:{'c' * 64}",
        source_content_hash=f"sha256:{'d' * 64}",
        source_size_bytes=100,
        text_size_bytes=50,
        text_chars=50,
    )
    args = start_args()
    args["mission"]["input_refs"] = [manifest.input_ref]
    missions = FakeMissions()

    await WorkspaceAgent(
        model=FakeModel(tool_message("start_mission", args)),
        missions=missions,
    ).run(context(mission_inputs=(manifest,)))

    request = missions.starts[0]
    assert request.snapshot_json["mission_inputs"] == [manifest.model_dump(mode="json")]
    assert request.runtime_context_json["context_refs"] == [manifest.input_ref]


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


def test_provider_tool_schema_binds_context_authorities() -> None:
    manifest = MissionInputManifest(
        input_ref=f"mission-input:{'c' * 64}",
        workspace_id="workspace-1",
        thread_id="thread-1",
        filename="problem.pdf",
        mime_type="application/pdf",
        extractor="pdf_text",
        content_hash=f"sha256:{'c' * 64}",
        source_content_hash=f"sha256:{'d' * 64}",
        source_size_bytes=100,
        text_size_bytes=50,
        text_chars=50,
    )
    descriptors = _tool_descriptors(context(mission_inputs=(manifest,)))
    by_name = {item["function"]["name"]: item["function"]["parameters"] for item in descriptors}
    start_spec = by_name["start_mission"]["$defs"]["MissionStartSpec"]

    assert start_spec["properties"]["input_refs"]["items"]["enum"] == [manifest.input_ref]
    assert by_name["steer_mission"]["properties"]["input_refs"]["items"]["enum"] == [manifest.input_ref]
    assert start_spec["properties"]["mission_policy_id"]["enum"] == ["sci.research"]
    assert start_spec["properties"]["parent_mission_id"]["anyOf"] == [{"type": "null"}]

    no_input_descriptors = _tool_descriptors(context())
    no_input_start = next(item for item in no_input_descriptors if item["function"]["name"] == "start_mission")["function"]["parameters"]
    assert no_input_start["$defs"]["MissionStartSpec"]["properties"]["input_refs"]["maxItems"] == 0


@pytest.mark.asyncio
async def test_invalid_structured_action_repairs_once_and_accounts_usage() -> None:
    invalid = start_args()
    invalid["mission"]["input_refs"] = [
        "academic-visual:avc_q3_summary",
        "artifact-candidate:" + "a" * 64,
    ]
    model = SequenceModel(
        [
            tool_message(
                "start_mission",
                invalid,
                usage_metadata={
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "total_tokens": 15,
                },
            ),
            tool_message(
                "start_mission",
                start_args(),
                usage_metadata={
                    "input_tokens": 20,
                    "output_tokens": 6,
                    "total_tokens": 26,
                },
            ),
        ]
    )
    missions = FakeMissions()

    reply = await WorkspaceAgent(model=model, missions=missions).run(context())

    assert reply.mission_id == "mission-1"
    assert len(model.invocations) == 2
    assert any("input_refs may contain only exact mission-input" in message.content for message in model.invocations[1] if getattr(message, "type", "") == "system")
    assert reply.metadata["usage"] == {
        "input_tokens": 30,
        "output_tokens": 11,
        "total_tokens": 41,
    }


def test_start_tool_does_not_expose_server_owned_identity() -> None:
    descriptor = next(item for item in _tool_descriptors() if item["function"]["name"] == "start_mission")
    schema_text = str(descriptor["function"]["parameters"])
    for field in (
        "workspace_id",
        "thread_id",
        "user_id",
        "raw_user_message_id",
        "mission_idempotency_key",
        "model_id",
        "reasoning_effort",
        "model_capability_profile_hash",
    ):
        assert field not in schema_text


@pytest.mark.asyncio
async def test_runtime_configuration_failure_is_a_user_facing_non_start() -> None:
    from src.mission_runtime.production import MissionProductionConfigurationError

    missions = FakeMissions()
    missions.start_error = MissionProductionConfigurationError("completed_event_boundary_not_verified")
    reply = await WorkspaceAgent(
        model=FakeModel(tool_message("start_mission", start_args())),
        missions=missions,
    ).run(context())

    assert reply.mission_id is None
    assert "研究任务没有启动" in reply.text
    assert "联网检索" not in reply.text
    assert reply.metadata["mission_start"]["status"] == "not_started"
    assert reply.metadata["mission_start"]["reason"] == "runtime_configuration_unavailable"


@pytest.mark.asyncio
async def test_native_search_failure_has_a_specific_user_facing_non_start() -> None:
    from src.mission_runtime.production import (
        MissionProductionConfigurationError,
        MissionProductionConfigurationErrorCode,
    )

    missions = FakeMissions()
    missions.start_error = MissionProductionConfigurationError(
        "completed_event_boundary_not_verified",
        code=MissionProductionConfigurationErrorCode.NATIVE_SEARCH_UNAVAILABLE,
    )
    reply = await WorkspaceAgent(
        model=FakeModel(tool_message("start_mission", start_args())),
        missions=missions,
    ).run(context())

    assert reply.mission_id is None
    assert "联网检索" in reply.text
    assert reply.metadata["mission_start"]["reason"] == "native_search_unavailable"


@pytest.mark.asyncio
async def test_invalid_start_state_is_a_user_facing_non_start() -> None:
    from src.mission_runtime import MissionStartRejectedError, MissionStartRejectionCode

    missions = FakeMissions()
    missions.start_error = MissionStartRejectedError(
        "任务启动信息不完整。",
        code=MissionStartRejectionCode.INVALID_START_STATE,
    )
    reply = await WorkspaceAgent(
        model=FakeModel(tool_message("start_mission", start_args())),
        missions=missions,
    ).run(context())

    assert reply.mission_id is None
    assert reply.text == "任务启动信息不完整，因此研究任务没有启动。请重新描述你的目标。"
    assert reply.metadata["mission_start"] == {
        "status": "not_started",
        "reason": "invalid_start_state",
    }


@pytest.mark.asyncio
async def test_continuation_policy_change_has_a_clear_user_facing_non_start() -> None:
    from src.mission_runtime import MissionStartRejectedError, MissionStartRejectionCode

    missions = FakeMissions()
    missions.start_error = MissionStartRejectedError(
        "Parent continuation requires the same pinned MissionPolicy content hash",
        code=MissionStartRejectionCode.CONTINUATION_POLICY_CHANGED,
    )
    reply = await WorkspaceAgent(
        model=FakeModel(tool_message("start_mission", start_args())),
        missions=missions,
    ).run(context())

    assert "研究方法版本已经更新" in reply.text
    assert "Parent continuation" not in reply.text
    assert reply.metadata["mission_start"]["reason"] == "continuation_policy_changed"


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
        model=FakeModel(
            tool_message(
                "steer_mission",
                {
                    "mission_id": "mission-1",
                    "command_id": "command-1",
                    "input_kind": "correction",
                    "instruction": "聚焦医疗场景",
                },
            )
        ),
        missions=missions,
    )
    await agent.run(context(active=active))
    assert missions.steers == [
        (
            "mission-1",
            {
                "command_id": "command-1",
                "actor_user_id": "user-1",
                "input_kind": "correction",
                "instruction": "聚焦医疗场景",
                "request_id": None,
                "mission_inputs": (),
                "prism_context_ref": None,
            },
        )
    ]


@pytest.mark.asyncio
async def test_active_mission_steer_always_pins_ready_current_message_inputs() -> None:
    manifest = MissionInputManifest(
        input_ref=f"mission-input:{'c' * 64}",
        workspace_id="workspace-1",
        thread_id="thread-1",
        filename="supplement.xlsx",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        extractor="plain_text",
        content_hash=f"sha256:{'c' * 64}",
        source_content_hash=f"sha256:{'d' * 64}",
        source_size_bytes=100,
        text_size_bytes=50,
        text_chars=50,
    )
    attachment = MissionInputContext(
        name=manifest.filename,
        content_type=manifest.mime_type,
        size_bytes=manifest.source_size_bytes,
        status="ready",
        input_ref=manifest.input_ref,
        current_message=True,
    )
    missions = FakeMissions()
    active = ActiveMissionContext(
        mission_id="mission-1",
        title="研究定位",
        objective="梳理空白",
        status="waiting",
        pending_request_id="request-1",
    )

    await WorkspaceAgent(
        model=FakeModel(
            tool_message(
                "steer_mission",
                {
                    "mission_id": "mission-1",
                    "command_id": "command-1",
                    "request_id": "request-1",
                    "input_kind": "context",
                    "instruction": "读取补充表格",
                },
            )
        ),
        missions=missions,
    ).run(
        context(
            active=active,
            mission_inputs=(manifest,),
            attachment_contexts=(attachment,),
        )
    )

    assert missions.steers[0][1]["mission_inputs"] == (
        manifest.model_dump(mode="json"),
    )


@pytest.mark.asyncio
async def test_focused_completed_mission_accepts_chat_review_decision() -> None:
    missions = FakeMissions()
    focused = ContinuationMissionContext(
        mission_id="11111111-1111-1111-1111-111111111111",
        title="研究定位",
        objective="梳理空白",
        status="completed",
        mission_policy_id="sci.research",
    )
    reply = await WorkspaceAgent(
        model=FakeModel(
            tool_message(
                "propose_review",
                {
                    "mission_id": focused.mission_id,
                    "review_item_ids": ["review-1"],
                    "decision": "accept",
                },
            )
        ),
        missions=missions,
    ).run(context(continuation=focused))

    assert reply.mission_id == focused.mission_id
    assert missions.reviews == [
        (
            focused.mission_id,
            {
                "decision_id": "review:message-1",
                "actor_user_id": "user-1",
                "review_item_ids": ("review-1",),
                "decision": "accept",
                "rationale": None,
            },
        )
    ]


@pytest.mark.asyncio
async def test_focused_completed_mission_accepts_chat_commit_request() -> None:
    missions = FakeMissions()
    focused = ContinuationMissionContext(
        mission_id="11111111-1111-1111-1111-111111111111",
        title="研究定位",
        objective="梳理空白",
        status="completed",
        mission_policy_id="sci.research",
    )
    reply = await WorkspaceAgent(
        model=FakeModel(
            tool_message(
                "request_commit",
                {
                    "mission_id": focused.mission_id,
                    "review_item_ids": ["review-1"],
                },
            )
        ),
        missions=missions,
    ).run(context(continuation=focused))

    assert reply.mission_id == focused.mission_id
    assert missions.commits == [
        (
            focused.mission_id,
            {
                "actor_user_id": "user-1",
                "review_item_ids": ("review-1",),
                "request_id": "commit:message-1",
            },
        )
    ]


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
