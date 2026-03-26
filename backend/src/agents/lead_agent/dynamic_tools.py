"""Dynamic tool node helpers for runtime-refreshable tool registries."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable, Sequence
from typing import Any, cast

from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool
from langgraph.errors import GraphBubbleUp
from langgraph.prebuilt.tool_node import (
    ToolNode,
    _get_state_args,
    _get_store_arg,
    _handle_tool_error,
    _infer_handled_types,
    msg_content_output,
)
from langgraph.types import Command

from src.agents.thread_state import ThreadState

ToolLoader = Callable[[], Sequence[BaseTool]]


class DynamicToolNode(ToolNode):
    """Tool node that refreshes its tool registry before each invocation."""

    def __init__(
        self,
        tool_loader: ToolLoader,
        *,
        name: str = "tools",
        middlewares: Sequence[Any] | None = None,
        tags: list[str] | None = None,
        handle_tool_errors: bool | str | Callable[..., str] | tuple[type[Exception], ...] = True,
        messages_key: str = "messages",
    ) -> None:
        self._tool_loader = tool_loader
        self._refresh_lock = threading.RLock()
        self._middlewares = list(middlewares or [])
        super().__init__(
            list(tool_loader()),
            name=name,
            tags=tags,
            handle_tool_errors=handle_tool_errors,
            messages_key=messages_key,
        )

    def list_available_tools(self) -> list[BaseTool]:
        """Return the latest tool registry snapshot."""
        self._refresh_tools()
        return list(self.tools_by_name.values())

    def _refresh_tools(self) -> None:
        with self._refresh_lock:
            tools = list(self._tool_loader())
            self.tools_by_name = {tool.name: tool for tool in tools}
            self.tool_to_state_args = {
                tool.name: _get_state_args(tool)
                for tool in tools
            }
            self.tool_to_store_arg = {
                tool.name: _get_store_arg(tool)
                for tool in tools
            }

    @staticmethod
    def _run_coroutine_sync(coroutine):
        """Run an async middleware hook from a synchronous tool path."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coroutine)

        result: dict[str, Any] = {}
        error: dict[str, BaseException] = {}

        def _runner() -> None:
            try:
                result["value"] = asyncio.run(coroutine)
            except BaseException as exc:  # noqa: BLE001
                error["value"] = exc

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        thread.join()

        if "value" in error:
            raise error["value"]
        return result.get("value")

    def _build_tool_config(self, config: Any, *, tool_call_id: str) -> Any:
        """Create a per-tool-call config so middleware state does not collide."""
        tool_config = dict(config or {})
        configurable = dict(tool_config.get("configurable", {}))
        configurable["tool_call_id"] = tool_call_id
        tool_config["configurable"] = configurable
        return tool_config

    def _build_state(self, input: Any) -> ThreadState:
        """Best-effort conversion from ToolNode input to ThreadState."""
        if isinstance(input, dict):
            return ThreadState(**input)
        if isinstance(input, list):
            return ThreadState(messages=input)
        if hasattr(input, "model_dump"):
            payload = input.model_dump()
            if isinstance(payload, dict):
                return ThreadState(**payload)
        messages = getattr(input, self.messages_key, None)
        if isinstance(messages, list):
            return ThreadState(messages=messages)
        return ThreadState(messages=[])

    async def _apply_before_tool(
        self,
        *,
        state: ThreadState,
        config: Any,
        call: dict[str, Any],
    ) -> dict[str, Any]:
        updated_call = dict(call)
        tool_name = str(updated_call["name"])
        tool_args = dict(updated_call.get("args") or {})

        for middleware in self._middlewares:
            tool_name, tool_args = await middleware.before_tool(
                state,
                config,
                tool_name,
                tool_args,
            )

        updated_call["name"] = tool_name
        updated_call["args"] = tool_args
        return updated_call

    async def _apply_after_tool(
        self,
        *,
        state: ThreadState,
        config: Any,
        call: dict[str, Any],
        response: Any,
    ) -> Any:
        result: Any = response.content if isinstance(response, ToolMessage) else response
        for middleware in self._middlewares:
            result = await middleware.after_tool(
                state,
                config,
                str(call["name"]),
                result,
            )

        if isinstance(result, (ToolMessage, Command)):
            return result

        if isinstance(response, ToolMessage):
            response.content = cast(str | list, msg_content_output(result))
            return response

        return ToolMessage(
            content=cast(str | list, msg_content_output(result)),
            name=str(call["name"]),
            tool_call_id=str(call["id"]),
        )

    def _coerce_tool_error_message(
        self,
        *,
        call: dict[str, Any],
        error: Exception,
    ) -> ToolMessage:
        if isinstance(self.handle_tool_errors, tuple):
            handled_types: tuple[type[Exception], ...] = self.handle_tool_errors
        elif callable(self.handle_tool_errors):
            handled_types = _infer_handled_types(self.handle_tool_errors)
        else:
            handled_types = (Exception,)

        if not self.handle_tool_errors or not isinstance(error, handled_types):
            raise error

        content = _handle_tool_error(error, flag=self.handle_tool_errors)
        return ToolMessage(
            content=content,
            name=str(call["name"]),
            tool_call_id=str(call["id"]),
            status="error",
        )

    def _func(self, input: Any, config, *, store=None) -> Any:
        self._refresh_tools()
        tool_calls, input_type = self._parse_input(input, store)
        state = self._build_state(input)
        outputs = [
            self._run_one_with_middlewares(
                call=call,
                input_type=input_type,
                config=self._build_tool_config(config, tool_call_id=str(call["id"])),
                state=state,
            )
            for call in tool_calls
        ]
        return self._combine_tool_outputs(outputs, input_type)

    async def _afunc(self, input: Any, config, *, store=None) -> Any:
        self._refresh_tools()
        tool_calls, input_type = self._parse_input(input, store)
        state = self._build_state(input)
        outputs = await asyncio.gather(
            *(
                self._arun_one_with_middlewares(
                    call=call,
                    input_type=input_type,
                    config=self._build_tool_config(config, tool_call_id=str(call["id"])),
                    state=state,
                )
                for call in tool_calls
            )
        )
        return self._combine_tool_outputs(outputs, input_type)

    def _run_one_with_middlewares(
        self,
        *,
        call: dict[str, Any],
        input_type: str,
        config: Any,
        state: ThreadState,
    ) -> ToolMessage:
        if invalid_tool_message := self._validate_tool_call(call):
            return invalid_tool_message

        try:
            updated_call = self._run_coroutine_sync(
                self._apply_before_tool(
                    state=state,
                    config=config,
                    call=call,
                )
            )
            if invalid_tool_message := self._validate_tool_call(updated_call):
                return invalid_tool_message
            call_args = {**updated_call, **{"type": "tool_call"}}
            response = self.tools_by_name[updated_call["name"]].invoke(call_args, config)
        except GraphBubbleUp as exc:
            raise exc
        except Exception as exc:  # noqa: BLE001
            return self._coerce_tool_error_message(call=call, error=exc)

        response = self._run_coroutine_sync(
            self._apply_after_tool(
                state=state,
                config=config,
                call=updated_call,
                response=response,
            )
        )

        if isinstance(response, Command):
            return self._validate_tool_command(response, updated_call, input_type)
        if isinstance(response, ToolMessage):
            response.content = cast(str | list, msg_content_output(response.content))
            return response
        raise TypeError(
            f"Tool {updated_call['name']} returned unexpected type: {type(response)}"
        )

    async def _arun_one_with_middlewares(
        self,
        *,
        call: dict[str, Any],
        input_type: str,
        config: Any,
        state: ThreadState,
    ) -> ToolMessage:
        if invalid_tool_message := self._validate_tool_call(call):
            return invalid_tool_message

        try:
            updated_call = await self._apply_before_tool(
                state=state,
                config=config,
                call=call,
            )
            if invalid_tool_message := self._validate_tool_call(updated_call):
                return invalid_tool_message
            call_args = {**updated_call, **{"type": "tool_call"}}
            response = await self.tools_by_name[updated_call["name"]].ainvoke(call_args, config)
        except GraphBubbleUp as exc:
            raise exc
        except Exception as exc:  # noqa: BLE001
            return self._coerce_tool_error_message(call=call, error=exc)

        response = await self._apply_after_tool(
            state=state,
            config=config,
            call=updated_call,
            response=response,
        )

        if isinstance(response, Command):
            return self._validate_tool_command(response, updated_call, input_type)
        if isinstance(response, ToolMessage):
            response.content = cast(str | list, msg_content_output(response.content))
            return response
        raise TypeError(
            f"Tool {updated_call['name']} returned unexpected type: {type(response)}"
        )
