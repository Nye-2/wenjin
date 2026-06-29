"""ReactSubagent -- MiMo ReAct loop driven by skill prompt and tools."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, RemoveMessage, SystemMessage, ToolMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES

from src.agents.harness.context_assembly import (
    build_harness_context_bundle,
    render_harness_context_for_prompt,
)
from src.config.llm_config import LLMSettings
from src.models import create_chat_model, route_writing_model
from src.services.thread_billing import extract_message_usage
from src.services.token_usage_collector import record_token_usage

from ..base import SubagentBase, SubagentContext, SubagentResult
from ..registry import subagent

logger = logging.getLogger(__name__)

DEFAULT_REACT_AGENT_TIMEOUT_SECONDS = 120.0
DEFAULT_REACT_RECURSION_LIMIT = 10


# ---------------------------------------------------------------------------
# Pure helper functions (testable without LLM)
# ---------------------------------------------------------------------------


def _render_user_message(template: str | None, inputs: dict) -> str:
    """Render the user message from a template + inputs.

    If *template* is provided, ``{{var}}`` placeholders are replaced with
    values from *inputs*.  Missing keys are replaced with an empty string.
    If no template is given, *inputs* is JSON-dumped as the message.
    """
    if template:
        def _replace(match: re.Match) -> str:
            key = match.group(1).strip()
            val = inputs.get(key)
            return str(val) if val is not None else ""
        return re.sub(r"\{\{(.+?)\}\}", _replace, template)
    return json.dumps(inputs, ensure_ascii=False)


def _parse_output(final_text: str, config: dict[str, Any]) -> dict:
    """Parse the LLM final text into a structured output dict.

    Behaviour depends on ``config["output_kind"]``:

    * ``"document"`` -- returns ``{"markdown": text}``.
    * ``"json"`` -- attempts ``json.loads``; on failure wraps as ``{"text": text}``.
    * default / anything else -- returns ``{"text": text}``.
    """
    kind = config.get("output_kind", "text")
    output_schema = _output_schema(config)

    if kind == "document":
        return {"markdown": final_text}

    if kind == "json" or output_schema:
        parsed = _extract_json_object(final_text)
        if isinstance(parsed, dict):
            return _apply_schema_defaults(parsed, output_schema, config, final_text)
        if output_schema:
            return _schema_fallback_output(final_text, output_schema, config)
        return {"text": final_text}

    # Default: plain text
    return {"text": final_text}


def _output_schema(config: dict[str, Any]) -> dict[str, Any]:
    io_contract = config.get("io_contract")
    if not isinstance(io_contract, dict):
        return {}
    output_schema = io_contract.get("output_schema")
    return output_schema if isinstance(output_schema, dict) else {}


def _runtime_output_config(config: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    """Overlay resolved runtime quality contracts onto the skill config.

    Team Kernel injects a merged ``quality_contract`` that may include contract
    overlay skills. Use that resolved contract for prompt and parse shape so
    the worker sees the same output contract that quality gates will enforce.
    """
    runtime_config = dict(config)
    quality_contract = inputs.get("quality_contract")
    if not isinstance(quality_contract, dict):
        return runtime_config

    output_schema = quality_contract.get("output_schema")
    if isinstance(output_schema, dict) and output_schema:
        io_contract = dict(runtime_config.get("io_contract") or {})
        io_contract["output_schema"] = output_schema
        runtime_config["io_contract"] = io_contract

    gates = _string_list(
        quality_contract.get("acknowledgement_required_gates")
        or quality_contract.get("quality_gates")
    )
    if gates:
        runtime_config["quality_gates"] = gates
    return runtime_config


def _react_model_id(harness_context: SubagentContext | None) -> str:
    inputs = harness_context.inputs if harness_context is not None else {}
    candidates = (
        inputs.get("model_id") if isinstance(inputs, dict) else None,
        inputs.get("model_name") if isinstance(inputs, dict) else None,
    )
    for candidate in candidates:
        value = str(candidate or "").strip()
        if value:
            return route_writing_model(requested_model=value)
    return route_writing_model(requested_model=None)


def _extract_json_object(text: str) -> dict[str, Any] | None:
    candidates = [text.strip()]
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if fence_match:
        candidates.insert(0, fence_match.group(1).strip())
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _apply_schema_defaults(
    parsed: dict[str, Any],
    output_schema: dict[str, Any],
    config: dict[str, Any],
    final_text: str,
) -> dict[str, Any]:
    if not output_schema:
        return parsed
    output = dict(parsed)
    properties = output_schema.get("properties")
    if not isinstance(properties, dict):
        properties = {}
    for field in _schema_required_fields(output_schema):
        if field in output:
            continue
        output[field] = _default_schema_field(field, properties.get(field), config, final_text)
    return output


def _schema_fallback_output(
    final_text: str,
    output_schema: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    properties = output_schema.get("properties")
    if not isinstance(properties, dict):
        properties = {}
    output: dict[str, Any] = {}
    for field in _schema_required_fields(output_schema):
        output[field] = _default_schema_field(field, properties.get(field), config, final_text)
    if "text" not in output:
        output["text"] = final_text
    return output


def _schema_required_fields(output_schema: dict[str, Any]) -> list[str]:
    required = output_schema.get("required")
    if not isinstance(required, list):
        return []
    return [str(field) for field in required if str(field).strip()]


def _default_schema_field(
    field: str,
    schema: Any,
    config: dict[str, Any],
    final_text: str,
) -> Any:
    if field == "text":
        return final_text
    if field == "quality_gates_checked":
        return []
    field_type = schema.get("type") if isinstance(schema, dict) else None
    if field_type == "array":
        return []
    if field_type == "object":
        return {}
    if field_type == "boolean":
        return False
    if field_type in {"number", "integer"}:
        return 0
    return ""


def _with_output_contract(system_prompt: str, config: dict[str, Any]) -> str:
    output_schema = _output_schema(config)
    if not output_schema:
        return system_prompt
    schema_text = json.dumps(output_schema, ensure_ascii=False, sort_keys=True)
    gates = config.get("quality_gates")
    gates_text = json.dumps(gates, ensure_ascii=False) if isinstance(gates, list) else "[]"
    contract = (
        "\n\nOutput contract:\n"
        "- Return only one JSON object, without markdown fences or prose outside JSON.\n"
        "- Include every required field from this JSON Schema.\n"
        f"- JSON Schema: {schema_text}\n"
        f"- quality_gates_checked must list the checked gates: {gates_text}"
    )
    return f"{system_prompt}{contract}" if system_prompt else contract.strip()


def _with_harness_context_bundle(system_prompt: str, ctx: SubagentContext) -> str:
    """Append the bounded harness context bundle for sandbox-capable agents."""

    if not _uses_sandbox_tools(ctx):
        return system_prompt
    bundle = _build_harness_context(ctx)
    section = (
        "\n\nHarness context bundle:\n"
        "- Use this bounded context when planning sandbox tool work.\n"
        "- If output_ref_recovery.refs is non-empty and sandbox.read_output_ref is available, use it before rerunning expensive sandbox work.\n"
        "- Reuse scratch_refs, reproducibility_summary, experiment_interpretation_summary, and statistical_robustness_summary before recreating prior experiments.\n"
        "- Use task_scratch_path for temporary task-local files; write user-reviewable artifacts under /workspace/outputs or /workspace/reports.\n"
        "- Do not list, search, write, or register internal /workspace/tmp/tasks/.harness refs as user artifacts.\n"
        f"- Context JSON: {render_harness_context_for_prompt(bundle)}"
    )
    return f"{system_prompt}{section}" if system_prompt else section.strip()


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            text = str(item).strip()
            if text:
                result.append(text)
        return result
    return []


def _build_default_user_payload(ctx: SubagentContext, config: dict[str, Any]) -> dict[str, Any]:
    """Build the default no-template user payload for a React subagent.

    Capability v2 seeds now carry policy and quality gates that are meaningful
    instructions, not just catalog metadata. Custom ``user_template`` configs
    keep their historical behavior; the default JSON payload includes the
    policy so domain skills can actually apply those gates.
    """
    payload = dict(ctx.inputs or {})

    if ctx.prompt:
        payload["_task_prompt"] = ctx.prompt

    if ctx.capability_policy:
        payload["_capability_policy"] = ctx.capability_policy

    if _uses_sandbox_tools(ctx):
        payload["_harness_context"] = _build_harness_context(ctx)

    quality_gates = config.get("quality_gates")
    if quality_gates:
        payload["_skill_quality_gates"] = quality_gates

    return payload


def _uses_sandbox_tools(ctx: SubagentContext) -> bool:
    tools = [str(tool).strip() for tool in ctx.tools or []]
    if any(tool.startswith("sandbox.") or tool in {"sandbox_python", "sandbox_exec"} for tool in tools):
        return True
    sandbox_policy = ctx.capability_policy.get("sandbox_policy")
    return isinstance(sandbox_policy, dict) and bool(sandbox_policy.get("allowed_operations"))


def _build_harness_context(ctx: SubagentContext) -> dict[str, Any]:
    inputs = ctx.inputs or {}
    return build_harness_context_bundle(
        workspace_id=ctx.workspace_id,
        workspace_type=str(inputs.get("workspace_type") or ""),
        task={
            "execution_id": ctx.execution_id,
            "node_id": _context_node_id(ctx),
            "invocation": ctx.invocation or {},
            "prompt": ctx.prompt,
            "inputs": inputs,
        },
        workspace_data=ctx.workspace_data or {},
        allowed_tools=ctx.tools or [],
    )


def _context_node_id(ctx: SubagentContext) -> str:
    invocation = ctx.invocation if isinstance(ctx.invocation, dict) else {}
    return str(
        invocation.get("id")
        or (ctx.inputs or {}).get("node_id")
        or (ctx.inputs or {}).get("template_id")
        or ""
    )


def _patch_dangling_tool_messages(state: dict[str, Any]) -> dict[str, Any]:
    """Patch missing tool results before LangGraph sends messages to the model."""

    messages = list(state.get("messages") or [])
    if not messages:
        return {}

    existing_result_ids = {
        str(getattr(message, "tool_call_id", "") or "").strip()
        for message in messages
        if isinstance(message, ToolMessage)
    }
    patched: list[BaseMessage] = []
    changed = False

    for message in messages:
        patched.append(message)
        if not isinstance(message, AIMessage):
            continue

        for call in _missing_tool_calls_for_message(message, existing_result_ids):
            patched.append(
                ToolMessage(
                    content=_synthetic_tool_recovery_content(call),
                    tool_call_id=call["id"],
                    name=call.get("name") or "unknown_tool",
                    status="error",
                )
            )
            existing_result_ids.add(call["id"])
            changed = True

    if not changed:
        return {}
    return {"messages": [RemoveMessage(id=REMOVE_ALL_MESSAGES), *patched]}


def _react_pre_model_hook(state: dict[str, Any]) -> dict[str, Any]:
    """Return a LangGraph-valid pre-model state update for ReactSubagent."""

    patched = _patch_dangling_tool_messages(state)
    if patched:
        return patched
    return {"llm_input_messages": list(state.get("messages") or [])}


def _missing_tool_calls_for_message(
    message: AIMessage,
    existing_result_ids: set[str],
) -> list[dict[str, str]]:
    missing: list[dict[str, str]] = []
    seen: set[str] = set(existing_result_ids)
    for call in _iter_message_tool_call_refs(message):
        call_id = str(call.get("id") or "").strip()
        if not call_id or call_id in seen:
            continue
        seen.add(call_id)
        missing.append(
            {
                "id": call_id,
                "name": str(call.get("name") or "").strip() or "unknown_tool",
                "kind": str(call.get("kind") or "tool_call"),
                "error": str(call.get("error") or "").strip(),
            }
        )
    return missing


def _iter_message_tool_call_refs(message: AIMessage):
    for call in getattr(message, "tool_calls", None) or []:
        if not isinstance(call, dict):
            continue
        yield {
            "id": call.get("id"),
            "name": call.get("name"),
            "kind": "tool_call",
        }

    additional_kwargs = getattr(message, "additional_kwargs", None)
    raw_calls = additional_kwargs.get("tool_calls") if isinstance(additional_kwargs, dict) else None
    if isinstance(raw_calls, list):
        for raw_call in raw_calls:
            if not isinstance(raw_call, dict):
                continue
            function = raw_call.get("function")
            function_name = function.get("name") if isinstance(function, dict) else None
            yield {
                "id": raw_call.get("id"),
                "name": raw_call.get("name") or function_name,
                "kind": "raw_tool_call",
            }

    for invalid_call in getattr(message, "invalid_tool_calls", None) or []:
        if not isinstance(invalid_call, dict):
            continue
        yield {
            "id": invalid_call.get("id"),
            "name": invalid_call.get("name"),
            "kind": "invalid_tool_call",
            "error": invalid_call.get("error"),
        }


def _synthetic_tool_recovery_content(call: dict[str, str]) -> str:
    base = (
        "Recoverable tool-call repair: this previous tool call did not produce "
        "a matching tool result. Continue with available context, or retry the "
        "tool using valid schema-compliant arguments if the result is still required."
    )
    if call.get("kind") == "invalid_tool_call" and call.get("error"):
        return f"{base} Validation error: {_safe_tool_error_text(call['error'])}"
    return base


def _safe_tool_error_text(value: str, *, max_chars: int = 240) -> str:
    text = re.sub(r"/workspace/[^\s,\"'}]+", "[workspace_path]", str(value))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


# ---------------------------------------------------------------------------
# ReactSubagent
# ---------------------------------------------------------------------------


@subagent("react")
class ReactSubagent(SubagentBase):
    """Runs a MiMo-style ReAct loop driven by a skill prompt.

    Skill fields used:
        prompt (str): System prompt for the LLM.
        config (dict):
            user_template (str | None): Jinja-like ``{{var}}`` template.
            output_kind (str): "document", "json", or "text" (default).
        resources (list[str]): Reference file paths (future use).
        allowed_tools (list[str]): Tools the ReAct agent may invoke.

    Output shape is determined by ``output_kind`` (see :func:`_parse_output`).
    """

    async def run(self, ctx: SubagentContext) -> SubagentResult:
        """Execute the ReAct loop."""
        if ctx.skill is None:
            return SubagentResult(output={"text": ""})

        # Assemble prompts
        config = _runtime_output_config(ctx.skill.config or {}, ctx.inputs or {})
        system_prompt = _with_output_contract(ctx.skill.prompt or "", config)
        system_prompt = _with_harness_context_bundle(system_prompt, ctx)
        user_template = config.get("user_template")
        user_inputs = ctx.inputs if user_template else _build_default_user_payload(ctx, config)
        user_message = _render_user_message(user_template, user_inputs)
        run_tools = [] if _should_run_direct_with_upstream_evidence(ctx, config) else ctx.tools
        tool_records: list[dict[str, Any]] = []
        if run_tools:
            ctx.workspace_data = dict(ctx.workspace_data or {})
            ctx.workspace_data["_harness_tool_records"] = tool_records

        # Run the ReAct loop (or plain invoke if no tools)
        try:
            final_text = await _run_react_loop(
                system_prompt=system_prompt,
                user_message=user_message,
                tools=run_tools,
                harness_context=ctx,
                emit_delta=ctx.emit_delta,
            )
        except Exception as exc:
            if not _is_transient_model_error(exc):
                raise
            logger.warning("React subagent using degraded deterministic output", exc_info=True)
            if ctx.emit_delta is not None:
                await ctx.emit_delta(
                    "thinking",
                    "Model provider is temporarily unavailable; using deterministic workspace context output.",
                )
            final_text = _build_degraded_react_text(ctx, exc)

        output = _parse_output(final_text, config)

        return SubagentResult(
            output=output,
            tool_calls=tool_records,
            token_usage=None,
        )


async def _run_react_loop(
    system_prompt: str,
    user_message: str,
    tools: list[str] | None = None,
    harness_context: SubagentContext | None = None,
    emit_delta: Callable[[str, str], Awaitable[None]] | None = None,
) -> str:
    """Run the MiMo ReAct loop (or plain model invoke if no tools).

    When no tools are available, uses a bounded direct ``model.ainvoke()`` call.

    Returns the final text content of the assistant's last message.
    """
    model = create_chat_model(
        _react_model_id(harness_context),
        thinking_enabled=True,
        request_timeout=_react_agent_timeout_seconds(harness_context),
        max_retries=0,
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ]

    if tools:
        resolved_tools = _resolve_tools(tools, harness_context)
        if not resolved_tools:
            requested = ", ".join(str(tool).strip() for tool in tools if str(tool).strip())
            raise RuntimeError(
                "React tools were requested but no registered tool callables are available"
                f": {requested}"
            )

        from langgraph.prebuilt import create_react_agent

        agent = create_react_agent(
            model=model,
            tools=resolved_tools,
            prompt=system_prompt,
            pre_model_hook=_react_pre_model_hook,
        )
        agent_config = {
            "recursion_limit": _react_recursion_limit(harness_context),
        }
        try:
            result = await asyncio.wait_for(
                agent.ainvoke(
                    {"messages": [HumanMessage(content=user_message)]},
                    config=agent_config,
                ),
                timeout=_react_agent_timeout_seconds(harness_context),
            )
        except TimeoutError as exc:
            timeout_seconds = _react_agent_timeout_seconds(harness_context)
            raise RuntimeError(
                f"React agent timed out after {timeout_seconds:.0f}s"
            ) from exc
        # Extract last AI message content
        msgs = result.get("messages", [])
        for msg in reversed(msgs):
            if hasattr(msg, "content") and msg.content:
                for usage_message in msgs:
                    record_token_usage(usage_message)
                return msg.content
        return ""

    # No tools -- stream the response and emit thinking deltas
    try:
        return await asyncio.wait_for(
            _run_direct_model_call(
                model=model,
                messages=messages,
                emit_delta=emit_delta,
            ),
            timeout=_react_agent_timeout_seconds(harness_context),
        )
    except TimeoutError as exc:
        timeout_seconds = _react_agent_timeout_seconds(harness_context)
        raise RuntimeError(
            f"React direct model timed out after {timeout_seconds:.0f}s"
        ) from exc


async def _run_direct_model_call(
    *,
    model: Any,
    messages: list[BaseMessage],
    emit_delta: Callable[[str, str], Awaitable[None]] | None = None,
) -> str:
    """Run a bounded plain model call for no-tool subagents."""

    if emit_delta is not None:
        await emit_delta("thinking", "正在整理上下文并生成结构化结果。")

    message = await asyncio.to_thread(model.invoke, messages)
    usage = extract_message_usage(message)
    if usage is not None:
        record_token_usage(usage)
    else:
        record_token_usage(message)
    return _message_content_text(getattr(message, "content", ""))


def _message_content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
        return "".join(parts)
    return str(content or "")


def _should_run_direct_with_upstream_evidence(
    ctx: SubagentContext,
    config: dict[str, Any],
) -> bool:
    """Use direct model synthesis when a skill declares evidence-first execution."""

    strategy = _execution_strategy_config(config)
    if not ctx.tools:
        return False
    mode = strategy.get("mode")
    if mode == "direct":
        return True
    if mode != "direct_when_upstream_evidence":
        return False
    min_items = _positive_int(strategy.get("min_evidence_items"), default=1)
    return _upstream_evidence_count(ctx) >= min_items


def _execution_strategy_config(config: dict[str, Any]) -> dict[str, Any]:
    extensions = config.get("extensions")
    if not isinstance(extensions, dict):
        return {}
    strategy = extensions.get("execution_strategy")
    return dict(strategy) if isinstance(strategy, dict) else {}


def _upstream_evidence_count(ctx: SubagentContext) -> int:
    inputs = ctx.inputs if isinstance(ctx.inputs, dict) else {}
    total = 0
    for section_name in ("upstream_context", "team_blackboard"):
        section = inputs.get(section_name)
        if isinstance(section, dict):
            total += _evidence_items_count(section.get("evidence_items"))
    if isinstance(ctx.team_context, dict):
        total += _evidence_items_count(ctx.team_context.get("evidence_items"))
    return total


def _evidence_items_count(value: Any) -> int:
    if isinstance(value, list):
        return len([item for item in value if isinstance(item, dict) and item])
    return 0


def _positive_int(value: Any, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(1, parsed)


def _react_agent_timeout_seconds(ctx: SubagentContext | None) -> float:
    """Resolve a bounded wall-clock timeout for tool-backed ReAct subagents."""

    configured = None
    if ctx is not None:
        capability_policy = ctx.capability_policy if isinstance(ctx.capability_policy, dict) else {}
        limits = capability_policy.get("limits")
        if isinstance(limits, dict):
            configured = limits.get("react_timeout_seconds") or limits.get("timeout_seconds")
        if configured is None:
            sandbox_policy = capability_policy.get("sandbox_policy")
            if isinstance(sandbox_policy, dict):
                configured = sandbox_policy.get("react_timeout_seconds")
                resource_limits = sandbox_policy.get("resource_limits")
                if configured is None and isinstance(resource_limits, dict):
                    configured = resource_limits.get("react_timeout_seconds")
        if configured is None and ctx.skill is not None:
            skill_config = getattr(ctx.skill, "config", None)
            if isinstance(skill_config, dict):
                configured = skill_config.get("react_timeout_seconds")
    try:
        value = float(configured) if configured is not None else DEFAULT_REACT_AGENT_TIMEOUT_SECONDS
    except (TypeError, ValueError):
        value = DEFAULT_REACT_AGENT_TIMEOUT_SECONDS
    return max(10.0, min(value, float(LLMSettings.AGENT_TIMEOUT)))


def _react_recursion_limit(ctx: SubagentContext | None) -> int:
    """Keep tool-backed ReAct graphs from spinning through long empty loops."""

    configured = None
    if ctx is not None:
        capability_policy = ctx.capability_policy if isinstance(ctx.capability_policy, dict) else {}
        sandbox_policy = capability_policy.get("sandbox_policy")
        if isinstance(sandbox_policy, dict):
            configured = sandbox_policy.get("max_iterations")
        if configured is None and ctx.skill is not None:
            skill_config = getattr(ctx.skill, "config", None)
            if isinstance(skill_config, dict):
                configured = skill_config.get("max_iterations")
    try:
        max_iterations = int(configured) if configured is not None else 4
    except (TypeError, ValueError):
        max_iterations = 4
    return max(4, min(DEFAULT_REACT_RECURSION_LIMIT, max_iterations * 2 + 2))


def _resolve_tools(tool_names: list[str], harness_context: SubagentContext | None = None) -> list:
    """Resolve tool names to callables.

    Callers that request tools must receive an explicit failure instead of a
    plain-LLM execution when no harness-backed callable can be resolved.
    """
    if harness_context is None:
        return []
    from src.agents.harness.langchain_adapter import build_langchain_tools

    return build_langchain_tools(harness_context, tool_names)


def _is_transient_model_error(exc: Exception) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    text = str(exc).lower()
    return any(
        marker in text
        for marker in (
            "500",
            "502",
            "503",
            "504",
            "bad gateway",
            "gateway timeout",
            "service unavailable",
            "timeout",
            "timed out",
        )
    )


def _latex_escape(value: Any) -> str:
    text = str(value or "")
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in text)


def _library_sources(inputs: dict[str, Any]) -> list[dict[str, Any]]:
    library_context = inputs.get("library_context")
    if not isinstance(library_context, dict):
        return []
    sources = library_context.get("citable_sources")
    if not isinstance(sources, list):
        return []
    result: list[dict[str, Any]] = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        citation_key = str(source.get("citation_key") or "").strip()
        if citation_key:
            result.append(source)
    return result


def _citation_key(source: dict[str, Any]) -> str:
    return str(source.get("citation_key") or "").strip()


def _build_degraded_manuscript(ctx: SubagentContext, exc: Exception) -> str:
    inputs = dict(ctx.inputs or {})
    sources = _library_sources(inputs)
    keys = [_citation_key(source) for source in sources[:8] if _citation_key(source)]
    topic = (
        str(inputs.get("topic") or "").strip()
        or str(inputs.get("raw_message") or "").strip()
        or "Federated Fine-Tuning of Large Language Models"
    )
    escaped_topic = _latex_escape(topic[:180])
    first = keys[0] if keys else ""
    second = keys[1] if len(keys) > 1 else first
    third = keys[2] if len(keys) > 2 else second
    source_lines = []
    for source in sources[:8]:
        title = _latex_escape(source.get("title") or _citation_key(source))
        key = _citation_key(source)
        year = source.get("year") or "n.d."
        source_lines.append(f"  \\item \\cite{{{key}}} {title} ({year}).")
    if not source_lines:
        source_lines.append("  \\item Library context was unavailable; citations must be checked before submission.")

    cite_intro = f"\\cite{{{first}}}" if first else "NEEDS_SOURCE"
    cite_related = f"\\cite{{{second}}}" if second else cite_intro
    cite_method = f"\\cite{{{third}}}" if third else cite_related

    return "\n".join(
        [
            r"\documentclass[UTF8]{ctexart}",
            r"\usepackage[a4paper,margin=1in]{geometry}",
            r"\usepackage{hyperref}",
            r"\usepackage{booktabs}",
            r"\title{Federated Fine-Tuning of Large Language Models with Parameter-Efficient Adaptation}",
            r"\author{Wenjin Research Workspace}",
            r"\date{\today}",
            r"\begin{document}",
            r"\maketitle",
            r"\begin{abstract}",
            f"This draft studies {escaped_topic}. It positions federated fine-tuning as a privacy-preserving path for adapting large language models across distributed clients, with low-rank adapters used to reduce communication and client resource requirements. Claims are intentionally conservative and must be strengthened with experiments before submission.",
            r"\end{abstract}",
            r"\section{Introduction}",
            f"Large language models increasingly require task- and domain-specific adaptation, but centralizing user data creates privacy, governance, and deployment barriers. Federated learning provides a natural alternative by keeping raw data on clients while coordinating model updates. Recent Library sources such as {cite_intro} indicate that parameter-efficient adapters can make this setting more practical for large models.",
            r"\section{Related Work}",
            "The literature can be grouped into federated instruction tuning, LoRA or adapter-based federated learning, communication-efficient aggregation, and privacy-preserving personalization. The Library currently contains the following citable sources:",
            r"\begin{itemize}",
            *source_lines,
            r"\end{itemize}",
            f"Work represented by {cite_related} motivates the need to connect personalization quality, communication cost, and privacy guarantees in one evaluation protocol.",
            r"\section{Method Overview}",
            f"We propose a federated adapter fine-tuning framework in which each client trains a local LoRA or adapter module while the server aggregates only parameter-efficient updates. The design separates the frozen backbone from trainable adapters, tracks client heterogeneity, and records communication volume per round. This section should be expanded with formal notation and algorithmic pseudocode. The method discussion should be checked against {cite_method}.",
            r"\section{Experimental Plan}",
            r"The empirical package should compare centralized fine-tuning, local-only adapters, federated full-parameter tuning where feasible, and federated LoRA/adapters. Required metrics include task quality, personalization lift, communication bytes, client memory footprint, privacy leakage probes, and robustness under non-IID splits. No numeric result is asserted in this draft until sandbox experiments are executed.",
            r"\section{Expected Contributions}",
            r"\begin{enumerate}",
            r"  \item A unified problem formulation for cross-device federated LLM fine-tuning with parameter-efficient adapters.",
            r"  \item A communication-aware aggregation protocol for heterogeneous LoRA or adapter updates.",
            r"  \item A reproducible benchmark plan covering quality, personalization, communication, and privacy-risk dimensions.",
            r"\end{enumerate}",
            r"\section{Limitations}",
            r"This draft does not yet contain executed experiments, statistical tests, or ablation results. All performance claims must remain marked as planned work until the sandbox produces reproducible artifacts.",
            r"\section{Conclusion}",
            r"Federated parameter-efficient fine-tuning is a promising route for privacy-preserving LLM personalization. The next step is to execute the experimental plan and replace TODO-level claims with verified evidence.",
            r"\bibliographystyle{plain}",
            r"\bibliography{refs}",
            r"\end{document}",
        ]
    )


def _build_degraded_react_text(ctx: SubagentContext, exc: Exception) -> str:
    skill_prompt = str(getattr(ctx.skill, "prompt", "") or "").lower()
    task_focus = str((ctx.inputs or {}).get("task_focus") or "").lower()
    if "manuscript writer" in skill_prompt or "写作" in task_focus or "draft" in task_focus:
        return _build_degraded_manuscript(ctx, exc)

    sources = _library_sources(dict(ctx.inputs or {}))
    source_summary = "\n".join(
        f"- {_citation_key(source)}: {source.get('title') or 'Untitled source'}"
        for source in sources[:8]
    )
    if not source_summary:
        source_summary = "- No Library sources were available in this node input."
    return (
        "Degraded deterministic node output.\n\n"
        "The configured model provider returned a transient error, so Wenjin "
        "preserved execution continuity using structured workspace context.\n\n"
        f"Provider error: {str(exc)[:300]}\n\n"
        "Available citation context:\n"
        f"{source_summary}\n\n"
        "Quality note: this output is conservative and should be refined when "
        "the model provider is available."
    )
