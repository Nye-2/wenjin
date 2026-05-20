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

    if kind == "document":
        return {"markdown": final_text}

    if kind == "json":
        try:
            parsed = json.loads(final_text)
            if isinstance(parsed, dict):
                return parsed
            return {"text": final_text}
        except (json.JSONDecodeError, TypeError):
            return {"text": final_text}

    # Default: plain text
    return {"text": final_text}


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
        system_prompt = ctx.skill.prompt or ""
        config = ctx.skill.config or {}
        user_template = config.get("user_template")
        user_message = _render_user_message(user_template, ctx.inputs)

        # Run the ReAct loop (or plain invoke if no tools)
        final_text = await _run_react_loop(
            system_prompt=system_prompt,
            user_message=user_message,
            tools=ctx.tools,
            emit_delta=ctx.emit_delta,
        )

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
        # Resolve tool callables by name and build a ReAct agent
        from langgraph.prebuilt import create_react_agent

        # TODO: resolve actual tool callables from tool names when tool registry is ready
        # For now, plain model invoke is used when tools list is empty after resolution
        resolved_tools = _resolve_tools(tools)
        if resolved_tools:
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
                    return msg.content
            return ""

    # No tools -- stream the response and emit thinking deltas
    collected_content: list[str] = []
    thinking_buf = ""
    last_flush = 0.0

    async for chunk in model.astream(messages):
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

    return "".join(collected_content)


def _resolve_tools(tool_names: list[str]) -> list:
    """Resolve tool names to callables.

    Placeholder -- returns an empty list until the tool registry is wired up.
    """
    # TODO: integrate with tool registry
    return []
