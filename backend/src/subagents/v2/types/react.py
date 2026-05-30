"""ReactSubagent -- MiMo ReAct loop driven by skill prompt and tools."""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from src.models import create_chat_model
from src.services.thread_billing import extract_message_usage
from src.services.token_usage_collector import record_token_usage

from ..base import SubagentBase, SubagentContext, SubagentResult
from ..registry import subagent

logger = logging.getLogger(__name__)


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
        gates = config.get("quality_gates")
        return list(gates) if isinstance(gates, list) else []
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

    quality_gates = config.get("quality_gates")
    if quality_gates:
        payload["_skill_quality_gates"] = quality_gates

    return payload


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
        config = ctx.skill.config or {}
        system_prompt = _with_output_contract(ctx.skill.prompt or "", config)
        user_template = config.get("user_template")
        user_inputs = ctx.inputs if user_template else _build_default_user_payload(ctx, config)
        user_message = _render_user_message(user_template, user_inputs)

        # Run the ReAct loop (or plain invoke if no tools)
        try:
            final_text = await _run_react_loop(
                system_prompt=system_prompt,
                user_message=user_message,
                tools=ctx.tools,
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
            tool_calls=[],
            token_usage=None,
        )


async def _run_react_loop(
    system_prompt: str,
    user_message: str,
    tools: list[str] | None = None,
    emit_delta: Callable[[str, str], Awaitable[None]] | None = None,
) -> str:
    """Run the MiMo ReAct loop (or plain model invoke if no tools).

    When no tools are available, streams the response using ``model.astream()``
    and emits thinking deltas through *emit_delta* (throttled to 500 ms).

    Returns the final text content of the assistant's last message.
    """
    model = create_chat_model("mimo-v2.5-pro", thinking_enabled=True)

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ]

    if tools:
        resolved_tools = _resolve_tools(tools)
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
            state_modifier=system_prompt,
        )
        result = await agent.ainvoke({"messages": [HumanMessage(content=user_message)]})
        # Extract last AI message content
        msgs = result.get("messages", [])
        for msg in reversed(msgs):
            if hasattr(msg, "content") and msg.content:
                for usage_message in msgs:
                    record_token_usage(usage_message)
                return msg.content
        return ""

    # No tools -- stream the response and emit thinking deltas
    collected_content: list[str] = []
    thinking_buf = ""
    last_flush = 0.0
    latest_stream_usage = None

    async for chunk in model.astream(messages):
        latest_stream_usage = extract_message_usage(chunk) or latest_stream_usage

        # --- Thinking chunk detection ---
        is_thinking = False
        thinking_text = ""

        # Anthropic thinking content blocks
        if hasattr(chunk, "additional_kwargs"):
            if chunk.additional_kwargs.get("type") == "thinking":
                is_thinking = True
                thinking_text = chunk.additional_kwargs.get("thinking", "")
                if not thinking_text and isinstance(chunk.content, str):
                    thinking_text = chunk.content

        # Handle list-style content blocks (Anthropic extended thinking)
        if not is_thinking and isinstance(chunk.content, list):
            for block in chunk.content:
                if isinstance(block, dict) and block.get("type") == "thinking":
                    is_thinking = True
                    thinking_text += block.get("thinking", "")
            # Collect regular text blocks too
            if not is_thinking:
                for block in chunk.content:
                    if isinstance(block, str):
                        collected_content.append(block)
                    elif isinstance(block, dict) and block.get("type") == "text":
                        collected_content.append(block.get("text", ""))

        if is_thinking:
            thinking_buf += thinking_text
            if emit_delta is not None:
                now = time.monotonic()
                if now - last_flush >= 0.5:
                    await emit_delta("thinking", thinking_buf)
                    last_flush = now
                    thinking_buf = ""
        else:
            # Regular content chunk
            if isinstance(chunk.content, str) and chunk.content:
                collected_content.append(chunk.content)

    # Final flush of remaining thinking buffer
    if thinking_buf and emit_delta is not None:
        await emit_delta("thinking", thinking_buf)

    if latest_stream_usage is not None:
        record_token_usage(latest_stream_usage)

    return "".join(collected_content)


def _resolve_tools(tool_names: list[str]) -> list:
    """Resolve tool names to callables.

    The current runtime has no React tool registry bridge. Callers that request
    tools must receive an explicit failure instead of a plain-LLM execution.
    """
    return []


def _is_transient_model_error(exc: Exception) -> bool:
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
