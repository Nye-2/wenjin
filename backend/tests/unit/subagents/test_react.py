"""Unit tests for ReactSubagent — helper functions + mock-LLM integration."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, ToolMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES

from src.agents.harness.contracts import HarnessToolResult
from src.subagents.v2.base import SubagentContext
from src.subagents.v2.registry import REGISTRY
from src.subagents.v2.types.react import (
    ReactSubagent,
    _build_default_user_payload,
    _build_degraded_react_text,
    _parse_output,
    _patch_dangling_tool_messages,
    _react_pre_model_hook,
    _render_user_message,
    _resolve_tools,
    _run_react_loop,
    _runtime_output_config,
    _with_harness_context_bundle,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ctx(
    *,
    inputs: dict | None = None,
    skill=None,
    tools=None,
    prompt: str = "",
    capability_policy: dict | None = None,
    workspace_data: dict | None = None,
    publish_event=None,
) -> SubagentContext:
    return SubagentContext(
        workspace_id="ws-test",
        execution_id="exec-test",
        prompt=prompt,
        inputs=inputs or {},
        tools=tools or [],
        workspace_data=workspace_data or {},
        capability_policy=capability_policy or {},
        skill=skill,
        publish_event=publish_event,
    )


def _make_skill(
    prompt: str = "",
    config: dict | None = None,
    resources: list | None = None,
    allowed_tools: list | None = None,
) -> MagicMock:
    skill = MagicMock()
    skill.prompt = prompt
    skill.config = config or {}
    skill.resources = resources or []
    skill.allowed_tools = allowed_tools or []
    return skill


# ---------------------------------------------------------------------------
# _render_user_message
# ---------------------------------------------------------------------------


class TestRenderUserMessage:
    def test_no_template_dumps_inputs(self):
        result = _render_user_message(None, {"topic": "AI", "n": 5})
        parsed = json.loads(result)
        assert parsed == {"topic": "AI", "n": 5}

    def test_custom_template_substitution(self):
        template = "主题: {{topic}}, 数量: {{n}}"
        result = _render_user_message(template, {"topic": "量子计算", "n": 10})
        assert result == "主题: 量子计算, 数量: 10"

    def test_missing_key_replaced_with_empty(self):
        template = "Hello {{name}}, {{missing}}"
        result = _render_user_message(template, {"name": "World"})
        assert result == "Hello World, "

    def test_empty_inputs_with_template(self):
        template = "Query: {{query}}"
        result = _render_user_message(template, {})
        assert result == "Query: "

    def test_empty_inputs_no_template(self):
        result = _render_user_message(None, {})
        assert json.loads(result) == {}


class TestDefaultUserPayload:
    def test_includes_capability_policy_for_default_payload(self):
        ctx = _make_ctx(
            inputs={"topic": "AI"},
            prompt="Draft {{topic}}",
            capability_policy={"quality_gates": ["claim_source_binding_checked"]},
        )
        payload = _build_default_user_payload(ctx, {"quality_gates": ["no_fabrication"]})

        assert payload["topic"] == "AI"
        assert payload["_task_prompt"] == "Draft {{topic}}"
        assert payload["_capability_policy"] == {
            "quality_gates": ["claim_source_binding_checked"]
        }
        assert payload["_skill_quality_gates"] == ["no_fabrication"]

    def test_includes_harness_context_for_sandbox_tools(self):
        ctx = _make_ctx(
            inputs={"topic": "federated LLM experiments"},
            tools=["sandbox.run_python"],
            capability_policy={
                "sandbox_policy": {"allowed_operations": ["run_python"]},
            },
        )

        payload = _build_default_user_payload(ctx, {})

        context = payload["_harness_context"]
        assert "_sandbox_workspace" not in payload
        assert context["schema"] == "wenjin.harness.context_bundle.v1"
        assert context["sandbox"]["root"] == "/workspace"
        assert "/workspace/scripts" in context["sandbox"]["standard_dirs"]
        assert "/workspace/outputs" in context["sandbox"]["artifact_roots"]
        assert "/workspace/tmp/tasks/.harness/**" in context["sandbox"]["internal_paths"]
        assert ".wenjin/**" in context["sandbox"]["protected_paths"]
        assert "**/.env" in context["sandbox"]["protected_paths"]


class TestSandboxWorkspaceContractPrompt:
    def test_appends_contract_to_system_prompt_for_sandbox_tool_agents(self):
        ctx = _make_ctx(
            tools=["sandbox.run_python"],
            inputs={"workspace_type": "sci"},
        )

        prompt = _with_harness_context_bundle("你是实验专家", ctx)

        assert "你是实验专家" in prompt
        assert "Harness context bundle" in prompt
        assert "wenjin.harness.context_bundle.v1" in prompt
        assert "/workspace/scripts" in prompt
        assert "/workspace/reports" in prompt

    def test_leaves_system_prompt_unchanged_without_sandbox_tools(self):
        ctx = _make_ctx(tools=[])

        assert _with_harness_context_bundle("你是综述专家", ctx) == "你是综述专家"


class TestDanglingToolCallRepair:
    def test_patch_dangling_tool_messages_inserts_synthetic_error_result(self):
        messages = [
            HumanMessage(content="read file"),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "call-1",
                        "name": "sandbox.read_file",
                        "args": {"path": "/workspace/main/a.tex"},
                    }
                ],
            ),
        ]

        patched = _patch_dangling_tool_messages({"messages": messages})

        assert "messages" in patched
        assert len(patched["messages"]) == 4
        assert isinstance(patched["messages"][0], RemoveMessage)
        assert patched["messages"][0].id == REMOVE_ALL_MESSAGES
        tool_message = patched["messages"][3]
        assert isinstance(tool_message, ToolMessage)
        assert tool_message.tool_call_id == "call-1"
        assert tool_message.name == "sandbox.read_file"
        assert tool_message.status == "error"
        assert "recoverable" in str(tool_message.content).lower()
        assert "/workspace/main/a.tex" not in str(tool_message.content)

    def test_patch_dangling_tool_messages_noops_when_result_exists(self):
        messages = [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "call-1",
                        "name": "sandbox.read_file",
                        "args": {},
                    }
                ],
            ),
            ToolMessage(content="ok", tool_call_id="call-1", name="sandbox.read_file"),
        ]

        assert _patch_dangling_tool_messages({"messages": messages}) == {}

    def test_patch_dangling_tool_messages_repairs_raw_provider_tool_call(self):
        messages = [
            AIMessage(
                content="",
                additional_kwargs={
                    "tool_calls": [
                        {
                            "id": "raw-call-1",
                            "type": "function",
                            "function": {
                                "name": "sandbox.grep",
                                "arguments": "{\"pattern\":\"secret\",\"glob\":\"/workspace/main/*.tex\"}",
                            },
                        }
                    ]
                },
            )
        ]

        patched = _patch_dangling_tool_messages({"messages": messages})

        assert isinstance(patched["messages"][0], RemoveMessage)
        assert patched["messages"][0].id == REMOVE_ALL_MESSAGES
        tool_message = patched["messages"][2]
        assert isinstance(tool_message, ToolMessage)
        assert tool_message.tool_call_id == "raw-call-1"
        assert tool_message.name == "sandbox.grep"
        assert tool_message.status == "error"
        assert "secret" not in str(tool_message.content)
        assert "/workspace/main/*.tex" not in str(tool_message.content)

    def test_patch_dangling_tool_messages_repairs_invalid_tool_call_without_raw_args(self):
        message = AIMessage(content="")
        message.invalid_tool_calls = [
            {
                "id": "invalid-call-1",
                "name": "sandbox.write_file",
                "args": "{\"path\":\"/workspace/main/a.tex\",\"content\":\"raw draft\"",
                "error": "Invalid JSON: missing closing brace",
            }
        ]

        patched = _patch_dangling_tool_messages({"messages": [message]})

        assert isinstance(patched["messages"][0], RemoveMessage)
        assert patched["messages"][0].id == REMOVE_ALL_MESSAGES
        tool_message = patched["messages"][2]
        assert isinstance(tool_message, ToolMessage)
        assert tool_message.tool_call_id == "invalid-call-1"
        assert tool_message.name == "sandbox.write_file"
        assert tool_message.status == "error"
        assert "Invalid JSON" in str(tool_message.content)
        assert "raw draft" not in str(tool_message.content)
        assert "/workspace/main/a.tex" not in str(tool_message.content)

    def test_react_pre_model_hook_returns_llm_input_messages_when_no_patch_needed(self):
        messages = [HumanMessage(content="continue")]

        patched = _react_pre_model_hook({"messages": messages})

        assert patched == {"llm_input_messages": messages}

    def test_react_pre_model_hook_returns_overwrite_messages_when_patch_needed(self):
        messages = [
            AIMessage(
                content="",
                tool_calls=[{"id": "call-1", "name": "sandbox.read_file", "args": {}}],
            )
        ]

        patched = _react_pre_model_hook({"messages": messages})

        assert "messages" in patched
        assert "llm_input_messages" not in patched
        assert isinstance(patched["messages"][0], RemoveMessage)


# ---------------------------------------------------------------------------
# _parse_output
# ---------------------------------------------------------------------------


class TestParseOutput:
    def test_document_kind(self):
        result = _parse_output("# Title\nBody", {"output_kind": "document"})
        assert result == {"markdown": "# Title\nBody"}

    def test_json_kind_valid(self):
        payload = {"sections": ["intro", "methods"]}
        text = json.dumps(payload, ensure_ascii=False)
        result = _parse_output(text, {"output_kind": "json"})
        assert result == payload

    def test_json_kind_invalid_fallback(self):
        result = _parse_output("not valid json", {"output_kind": "json"})
        assert result == {"text": "not valid json"}

    def test_json_kind_non_dict_fallback(self):
        result = _parse_output("[1, 2, 3]", {"output_kind": "json"})
        assert result == {"text": "[1, 2, 3]"}

    def test_text_default(self):
        result = _parse_output("just some text", {"output_kind": "text"})
        assert result == {"text": "just some text"}

    def test_unknown_kind_falls_back_to_text(self):
        result = _parse_output("mystery output", {"output_kind": "unknown"})
        assert result == {"text": "mystery output"}

    def test_no_output_kind_key(self):
        result = _parse_output("plain output", {})
        assert result == {"text": "plain output"}

    def test_v2_output_schema_parses_fenced_json_without_output_kind(self):
        payload = {
            "text": "planned queries",
            "quality_gates_checked": ["query_strategy_recorded"],
            "query_log": [{"query": "federated LoRA"}],
        }
        result = _parse_output(
            "```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```",
            {
                "quality_gates": ["query_strategy_recorded"],
                "io_contract": {
                    "output_schema": {
                        "type": "object",
                        "required": ["text", "quality_gates_checked", "query_log"],
                        "properties": {
                            "text": {"type": "string"},
                            "quality_gates_checked": {"type": "array"},
                            "query_log": {"type": "array"},
                        },
                    }
                },
            },
        )

        assert result == payload

    def test_v2_output_schema_fallback_fills_contract_fields(self):
        result = _parse_output(
            "plain model text",
            {
                "quality_gates": ["task_scope_bounded"],
                "io_contract": {
                    "output_schema": {
                        "type": "object",
                        "required": ["text", "quality_gates_checked", "decision_candidates"],
                        "properties": {
                            "text": {"type": "string"},
                            "quality_gates_checked": {"type": "array"},
                            "decision_candidates": {"type": "array"},
                        },
                    }
                },
            },
        )

        assert result == {
            "text": "plain model text",
            "quality_gates_checked": [],
            "decision_candidates": [],
        }

    def test_runtime_output_config_prefers_resolved_quality_contract(self):
        base_config = {
            "quality_gates": ["skill_gate"],
            "io_contract": {
                "output_schema": {
                    "type": "object",
                    "required": ["text"],
                    "properties": {"text": {"type": "string"}},
                }
            },
        }
        contract_schema = {
            "type": "object",
            "required": ["text", "quality_gates_checked", "checked_requirements"],
            "properties": {
                "text": {"type": "string"},
                "quality_gates_checked": {"type": "array"},
                "checked_requirements": {"type": "array"},
            },
        }

        result = _runtime_output_config(
            base_config,
            {
                "quality_contract": {
                    "output_schema": contract_schema,
                    "acknowledgement_required_gates": ["format_requirements_checked"],
                }
            },
        )

        assert result["io_contract"]["output_schema"] == contract_schema
        assert result["quality_gates"] == ["format_requirements_checked"]
        assert base_config["io_contract"]["output_schema"]["required"] == ["text"]


class TestDegradedOutput:
    def test_manuscript_writer_degraded_output_uses_library_citations(self):
        ctx = _make_ctx(
            inputs={
                "task_focus": "写作 SCI manuscript",
                "topic": "federated fine-tuning of large language models",
                "library_context": {
                    "citation_keys": ["fedllm2026", "flora2024"],
                    "citable_sources": [
                        {"citation_key": "fedllm2026", "title": "FedLLM"},
                        {"citation_key": "flora2024", "title": "FLoRA"},
                    ],
                },
            },
            skill=_make_skill(prompt="manuscript writer"),
        )

        text = _build_degraded_react_text(ctx, RuntimeError("502 Bad Gateway"))

        assert "\\documentclass" in text
        assert "\\cite{fedllm2026}" in text
        assert "\\cite{flora2024}" in text
        assert "\\bibliography{refs}" in text
        assert "Bad Gateway" not in text
        assert "configured model provider" not in text


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_registered_in_global_registry(self):
        assert "react" in REGISTRY.all_names()
        assert REGISTRY.get("react") is ReactSubagent


# ---------------------------------------------------------------------------
# No skill => empty output
# ---------------------------------------------------------------------------


class TestNoSkill:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_skill(self):
        sub = ReactSubagent()
        ctx = _make_ctx(skill=None)
        result = await sub.run(ctx)
        assert result.output == {"text": ""}


# ---------------------------------------------------------------------------
# Task 13: Mock LLM integration test
# ---------------------------------------------------------------------------


class TestMockLLM:
    @pytest.mark.asyncio
    async def test_skill_with_mock_model(self):
        """Verify ReactSubagent calls the model via astream and parses document output."""
        # Build fake stream chunks (LangChain AIMessageChunk-like)
        fake_chunk = MagicMock()
        fake_chunk.content = "# 综述报告\n\n这是一篇关于量子计算的综述。"
        fake_chunk.additional_kwargs = {}

        async def _fake_astream(messages):
            yield fake_chunk

        fake_model = MagicMock()
        fake_model.astream = MagicMock(return_value=_fake_astream([]))

        with patch(
            "src.subagents.v2.types.react.create_chat_model",
            return_value=fake_model,
        ):
            sub = ReactSubagent()
            skill = _make_skill(
                prompt="你是综述写手",
                config={
                    "output_kind": "document",
                    "user_template": "主题: {{topic}}",
                },
            )
            ctx = _make_ctx(inputs={"topic": "量子计算"}, skill=skill)
            result = await sub.run(ctx)

        # Verify model.astream was called with system + user messages
        fake_model.astream.assert_called_once()
        call_args = fake_model.astream.call_args[0][0]  # positional arg: messages list
        assert len(call_args) == 2
        assert call_args[0].content == "你是综述写手"
        assert call_args[1].content == "主题: 量子计算"

        # Verify output parsed as document
        assert result.output == {
            "markdown": "# 综述报告\n\n这是一篇关于量子计算的综述。"
        }

    @pytest.mark.asyncio
    async def test_requested_tools_without_registered_callables_fail_explicitly(self):
        fake_model = MagicMock()

        with patch(
            "src.subagents.v2.types.react.create_chat_model",
            return_value=fake_model,
        ):
            with pytest.raises(RuntimeError, match="React tools were requested"):
                await _run_react_loop(
                    system_prompt="system",
                    user_message="user",
                    tools=["unknown.tool"],
                )

        fake_model.astream.assert_not_called()

    @pytest.mark.asyncio
    async def test_resolve_tools_returns_harness_backed_read_file_tool(self):
        class FakeSandbox:
            async def read_file(self, path: str) -> str:
                assert path == "/workspace/main.tex"
                return "hello harness"

        tool_records = []
        ctx = _make_ctx(
            tools=["sandbox.read_file"],
            workspace_data={
                "_harness_sandbox": FakeSandbox(),
                "_harness_tool_records": tool_records,
            },
            capability_policy={
                "allowed_tools": ["sandbox.read_file"],
                "permissions": ["filesystem.read"],
            },
            skill=_make_skill(allowed_tools=["sandbox.read_file"]),
        )

        tools = _resolve_tools(["sandbox.read_file"], ctx)

        assert [tool.name for tool in tools] == ["sandbox_read_file", "sandbox_read_output_ref"]
        result = await tools[0].ainvoke({"path": "/workspace/main.tex"})
        assert "hello harness" in result
        assert tool_records == [
            {
                "name": "sandbox.read_file",
                "status": "completed",
                "args": {"path": "/workspace/main.tex"},
                "result_preview": result[:500],
            }
        ]

    @pytest.mark.asyncio
    async def test_harness_grep_invalid_regex_returns_recoverable_json_error(self):
        events: list[tuple[str, str, dict]] = []

        async def publish_event(execution_id: str, event_type: str, payload: dict) -> None:
            events.append((execution_id, event_type, payload))

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            main_dir = workspace / "main"
            main_dir.mkdir(parents=True)
            (main_dir / "file.txt").write_text("alpha\n", encoding="utf-8")

            class FakeSandbox:
                path_mappings = {"/workspace": str(workspace)}

            tool_records = []
            ctx = _make_ctx(
                tools=["sandbox.grep"],
                workspace_data={
                    "_harness_sandbox": FakeSandbox(),
                    "_harness_tool_records": tool_records,
                },
                capability_policy={
                    "allowed_tools": ["sandbox.grep"],
                    "permissions": ["filesystem.read"],
                },
                skill=_make_skill(allowed_tools=["sandbox.grep"]),
                publish_event=publish_event,
            )

            tool = _resolve_tools(["sandbox.grep"], ctx)[0]
            result = await tool.ainvoke({"pattern": "[", "glob": "main/*.txt"})

        payload = json.loads(result)

        assert payload["error"].startswith("invalid_regex:")
        assert payload["payload"]["error_code"] == "invalid_regex"
        assert payload["payload"]["matches"] == []
        assert payload["payload"]["scanned_files"] == 0
        assert tool_records[-1]["status"] == "completed"
        assert tool_records[-1]["recoverable_error"].startswith("invalid_regex:")
        assert tool_records[-1]["error_code"] == "invalid_regex"
        completed_events = [event for event in events if event[1] == "execution.harness.tool_call.completed"]
        assert completed_events
        completed_payload = completed_events[-1][2]["payload"]
        assert completed_payload["recoverable_error"].startswith("invalid_regex:")
        assert completed_payload["error_code"] == "invalid_regex"

    @pytest.mark.asyncio
    async def test_harness_tool_record_and_events_include_externalized_output_refs(self):
        class FakeSandbox:
            def __init__(self) -> None:
                self.files: dict[str, str] = {}

            async def read_file(self, path: str) -> str:
                assert path == "/workspace/main/large.txt"
                return "large line\n" * 80

            async def write_file(self, path: str, content: str, append: bool = False) -> None:
                self.files[path] = self.files.get(path, "") + content if append else content

        tool_records = []
        events: list[tuple[str, str, dict]] = []

        async def publish_event(execution_id: str, event_type: str, payload: dict) -> None:
            events.append((execution_id, event_type, payload))

        ctx = _make_ctx(
            tools=["sandbox.read_file"],
            workspace_data={
                "_harness_sandbox": FakeSandbox(),
                "_harness_tool_records": tool_records,
            },
            capability_policy={
                "allowed_tools": ["sandbox.read_file"],
                "permissions": ["filesystem.read"],
                "sandbox_policy": {
                    "output_budget": {
                        "externalize_above_chars": 100,
                        "preview_head_chars": 40,
                        "preview_tail_chars": 40,
                    }
                },
            },
            skill=_make_skill(allowed_tools=["sandbox.read_file"]),
            publish_event=publish_event,
        )

        tool = _resolve_tools(["sandbox.read_file"], ctx)[0]
        result = await tool.ainvoke({"path": "/workspace/main/large.txt"})
        payload = json.loads(result)

        assert payload["externalized"] is True
        assert payload["output_refs"]
        assert tool_records == [
            {
                "name": "sandbox.read_file",
                "status": "completed",
                "args": {"path": "/workspace/main/large.txt"},
                "result_preview": result[:500],
                "output_refs": payload["output_refs"],
                "truncated": True,
                "externalized": True,
            }
        ]
        completed_events = [event for event in events if event[1] == "execution.harness.tool_call.completed"]
        externalized_events = [event for event in events if event[1] == "execution.harness.output_externalized"]
        assert completed_events
        assert completed_events[-1][2]["payload"]["output_refs"] == payload["output_refs"]
        assert externalized_events
        assert externalized_events[-1][2]["payload"]["output_refs"] == payload["output_refs"]

    @pytest.mark.asyncio
    async def test_harness_tool_record_and_events_include_generated_artifacts(self, monkeypatch):
        artifact = {
            "schema": "wenjin.sandbox.generated_artifact_candidate.v1",
            "path": "/workspace/reports/summary.md",
            "root": "reports",
            "artifact_kind": "sandbox_report",
            "mime_type": "text/markdown",
            "size": 18,
            "content_hash": "sha256:abc",
            "review_surface": "sandbox_artifact",
            "materialization_status": "candidate",
        }

        async def fake_run_python(self, **kwargs):
            return HarnessToolResult(
                preview_text="Python execution completed",
                structured_payload={
                    "sandbox_job_id": "job-1",
                    "sandbox_environment_id": "env-1",
                    "generated_artifacts": [artifact],
                },
            )

        monkeypatch.setattr(
            "src.agents.harness.sandbox_execution_tools.SandboxExecutionTools.run_python",
            fake_run_python,
        )

        tool_records = []
        events: list[tuple[str, str, dict]] = []

        async def publish_event(execution_id: str, event_type: str, payload: dict) -> None:
            events.append((execution_id, event_type, payload))

        skill = _make_skill()
        skill.skill_json = {"sandbox_access": {"mode": "required", "profiles": ["analysis"]}}
        ctx = _make_ctx(
            tools=["sandbox.run_python"],
            workspace_data={"_harness_tool_records": tool_records},
            capability_policy={
                "sandbox_policy": {
                    "mode": "required",
                    "allowed_operations": ["run_python"],
                }
            },
            skill=skill,
            publish_event=publish_event,
        )

        tool = _resolve_tools(["sandbox.run_python"], ctx)[0]
        result = await tool.ainvoke({"script": "print('ok')", "script_name": "analysis.py"})
        payload = json.loads(result)

        expected_artifact = {
            **artifact,
            "sandbox_job_id": "job-1",
            "sandbox_environment_id": "env-1",
        }
        assert payload["payload"]["generated_artifacts"] == [artifact]
        assert tool_records[-1]["generated_artifacts"] == [expected_artifact]
        completed_events = [event for event in events if event[1] == "execution.harness.tool_call.completed"]
        assert completed_events
        assert completed_events[-1][2]["payload"]["generated_artifacts"] == [expected_artifact]

    @pytest.mark.asyncio
    async def test_harness_run_python_record_and_events_include_command_audit(self, monkeypatch):
        command_audit = {
            "verdict": "pass",
            "risk_level": "low",
            "reasons": [],
            "command": {
                "argv": [
                    "/workspace/.wenjin/env/python/bin/python",
                    "/workspace/scripts/analysis.py",
                ],
                "shell_command": None,
                "cwd": "/workspace",
                "env": {},
                "network_profile": "none",
                "timeout_seconds": None,
                "output_bytes_cap": None,
            },
        }

        async def fake_run_python(self, **kwargs):
            return HarnessToolResult(
                preview_text="Python execution completed",
                structured_payload={
                    "sandbox_job_id": "job-1",
                    "command_audit": command_audit,
                },
            )

        monkeypatch.setattr(
            "src.agents.harness.sandbox_execution_tools.SandboxExecutionTools.run_python",
            fake_run_python,
        )

        tool_records = []
        events: list[tuple[str, str, dict]] = []

        async def publish_event(execution_id: str, event_type: str, payload: dict) -> None:
            events.append((execution_id, event_type, payload))

        skill = _make_skill()
        skill.skill_json = {"sandbox_access": {"mode": "required", "profiles": ["analysis"]}}
        ctx = _make_ctx(
            tools=["sandbox.run_python"],
            workspace_data={"_harness_tool_records": tool_records},
            capability_policy={
                "sandbox_policy": {
                    "mode": "required",
                    "allowed_operations": ["run_python"],
                }
            },
            skill=skill,
            publish_event=publish_event,
        )

        tool = _resolve_tools(["sandbox.run_python"], ctx)[0]
        await tool.ainvoke({"script": "print('ok')", "script_name": "analysis.py"})

        assert tool_records[-1]["command_audit"] == command_audit
        completed_events = [event for event in events if event[1] == "execution.harness.tool_call.completed"]
        assert completed_events
        assert completed_events[-1][2]["payload"]["command_audit"] == command_audit

    @pytest.mark.asyncio
    async def test_harness_tool_record_and_events_include_file_changes(self):
        class FakeSandbox:
            def __init__(self) -> None:
                self.files = {"/workspace/main.tex": "old\n"}

            async def read_file(self, path: str) -> str:
                if path not in self.files:
                    raise FileNotFoundError(path)
                return self.files[path]

            async def write_file(self, path: str, content: str, append: bool = False) -> None:
                self.files[path] = self.files.get(path, "") + content if append else content

        tool_records = []
        events: list[tuple[str, str, dict]] = []

        async def publish_event(execution_id: str, event_type: str, payload: dict) -> None:
            events.append((execution_id, event_type, payload))

        ctx = _make_ctx(
            tools=["sandbox.write_file"],
            workspace_data={
                "_harness_sandbox": FakeSandbox(),
                "_harness_tool_records": tool_records,
            },
            capability_policy={
                "allowed_tools": ["sandbox.write_file"],
                "permissions": ["filesystem.write", "filesystem.diff"],
            },
            skill=_make_skill(allowed_tools=["sandbox.write_file"]),
            publish_event=publish_event,
        )

        tool = _resolve_tools(["sandbox.write_file"], ctx)[0]
        result = await tool.ainvoke({"path": "/workspace/main.tex", "content": "new\n"})
        payload = json.loads(result)

        file_change = payload["file_change"]
        assert file_change["path"] == "/workspace/main.tex"
        assert file_change["operation"] == "update"
        assert tool_records[-1]["file_changes"] == [file_change]
        file_change_events = [event for event in events if event[1] == "execution.harness.file_change"]
        assert file_change_events
        assert file_change_events[-1][2]["payload"]["file_changes"] == [file_change]
        completed_events = [event for event in events if event[1] == "execution.harness.tool_call.completed"]
        assert completed_events
        assert completed_events[-1][2]["payload"]["file_changes"] == [file_change]

    @pytest.mark.asyncio
    async def test_harness_tool_loop_guard_blocks_repeated_calls(self):
        class FakeSandbox:
            async def read_file(self, path: str) -> str:
                return f"content from {path}"

        tool_records = []
        ctx = _make_ctx(
            tools=["sandbox.read_file"],
            workspace_data={
                "_harness_sandbox": FakeSandbox(),
                "_harness_tool_records": tool_records,
            },
            capability_policy={
                "allowed_tools": ["sandbox.read_file"],
                "permissions": ["filesystem.read"],
                "sandbox_policy": {"max_tool_calls": 3},
            },
            skill=_make_skill(allowed_tools=["sandbox.read_file"]),
        )
        tool = _resolve_tools(["sandbox.read_file"], ctx)[0]

        await tool.ainvoke({"path": "/workspace/main.tex"})
        await tool.ainvoke({"path": "/workspace/main.tex"})
        with pytest.raises(RuntimeError, match="repeated tool call"):
            await tool.ainvoke({"path": "/workspace/main.tex"})

        assert tool_records[-1]["status"] == "failed"
        assert tool_records[-1]["error"] == "tool_loop_hard_stop"

    @pytest.mark.asyncio
    async def test_harness_tool_loop_guard_publishes_warning_event_without_blocking(self):
        class FakeSandbox:
            async def read_file(self, path: str) -> str:
                return f"content from {path}"

        tool_records = []
        events: list[tuple[str, str, dict]] = []

        async def publish_event(execution_id: str, event_type: str, payload: dict) -> None:
            events.append((execution_id, event_type, payload))

        ctx = _make_ctx(
            tools=["sandbox.read_file"],
            workspace_data={
                "_harness_sandbox": FakeSandbox(),
                "_harness_tool_records": tool_records,
            },
            capability_policy={
                "allowed_tools": ["sandbox.read_file"],
                "permissions": ["filesystem.read"],
                "sandbox_policy": {"max_tool_calls": 5},
            },
            skill=_make_skill(allowed_tools=["sandbox.read_file"]),
            publish_event=publish_event,
        )
        tool = _resolve_tools(["sandbox.read_file"], ctx)[0]

        await tool.ainvoke({"path": "/workspace/main.tex"})
        await tool.ainvoke({"path": "/workspace/main.tex"})
        await tool.ainvoke({"path": "/workspace/main.tex"})

        warning_events = [event for event in events if event[1] == "execution.harness.loop_warning"]
        assert warning_events
        payload = warning_events[-1][2]
        assert payload["visibility"] == "team_visible"
        assert payload["sequence_kind"] == "loop"
        assert payload["payload"] == {
            "name": "sandbox.read_file",
            "args": {"path": "/workspace/main.tex"},
            "repeat_count": 3,
            "warn_threshold": 3,
        }
        assert tool_records[-1]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_react_subagent_returns_harness_tool_records(self):
        async def fake_loop(**kwargs):
            harness_context = kwargs["harness_context"]
            harness_context.workspace_data["_harness_tool_records"].append(
                {"name": "sandbox.read_file", "status": "completed"}
            )
            return "final text"

        skill = _make_skill(
            prompt="Use tools",
            config={"output_kind": "text"},
            allowed_tools=["sandbox.read_file"],
        )
        ctx = _make_ctx(
            skill=skill,
            tools=["sandbox.read_file"],
            capability_policy={
                "allowed_tools": ["sandbox.read_file"],
                "permissions": ["filesystem.read"],
            },
        )

        with patch("src.subagents.v2.types.react._run_react_loop", side_effect=fake_loop):
            result = await ReactSubagent().run(ctx)

        assert result.output == {"text": "final text"}
        assert result.tool_calls == [{"name": "sandbox.read_file", "status": "completed"}]

    def test_resolve_tools_accepts_existing_sandbox_python_alias(self):
        ctx = _make_ctx(
            tools=["sandbox_python"],
            capability_policy={"allowed_tools": ["sandbox_python"]},
            skill=MagicMock(
                allowed_tools=[],
                config={},
                skill_json={"sandbox_access": {"mode": "required", "profiles": ["analysis"]}},
            ),
        )

        tools = _resolve_tools(["sandbox_python"], ctx)

        assert [tool.name for tool in tools] == ["sandbox_run_python"]
