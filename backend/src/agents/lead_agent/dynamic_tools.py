"""Dynamic tool node helpers for runtime-refreshable tool registries."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections.abc import Callable, Coroutine, Sequence
from typing import Any, Literal, TypeAlias, TypeVar, cast

logger = logging.getLogger(__name__)

from langchain_core.messages import AnyMessage, ToolCall, ToolMessage
from langchain_core.runnables import RunnableConfig
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

from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState, create_thread_state

ToolLoader = Callable[[], Sequence[BaseTool]]
ToolNodeInputType: TypeAlias = Literal["list", "dict", "tool_calls"]
ToolRunOutput: TypeAlias = ToolMessage | Command[Any]
T = TypeVar("T")


def _coerce_json_object(value: object) -> dict[str, Any]:
    """Normalize arbitrary tool payloads into dict form."""
    return dict(value) if isinstance(value, dict) else {}


class DynamicToolNode(ToolNode):
    """Tool node that refreshes its tool registry before each invocation."""

    def __init__(
        self,
        tool_loader: ToolLoader,
        *,
        name: str = "tools",
        middlewares: Sequence[Middleware] | None = None,
        tags: list[str] | None = None,
        handle_tool_errors: bool | str | Callable[..., str] | tuple[type[Exception], ...] = True,
        messages_key: str = "messages",
        refresh_interval: float = 60.0,
    ) -> None:
        self._tool_loader = tool_loader
        self._refresh_lock = threading.RLock()
        self._middlewares = list(middlewares or [])
        self._refresh_interval = refresh_interval
        self._last_refresh: float = 0.0
        self._last_tool_names: frozenset[str] = frozenset()
        initial_tools = list(tool_loader())
        super().__init__(
            initial_tools,
            name=name,
            tags=tags,
            handle_tool_errors=handle_tool_errors,
            messages_key=messages_key,
        )
        # Record the initial load so _refresh_tools respects the TTL from construction
        self._last_tool_names = frozenset(t.name for t in initial_tools)
        self._last_refresh = time.monotonic()

    def list_available_tools(self) -> list[BaseTool]:
        """Return the latest tool registry snapshot."""
        self._refresh_tools()
        return list(self.tools_by_name.values())

    def _refresh_tools(self) -> None:
        with self._refresh_lock:
            now = time.monotonic()
            if now - self._last_refresh < self._refresh_interval:
                return  # Within TTL: skip full reload
            tools = list(self._tool_loader())
            new_names = frozenset(tool.name for tool in tools)
            if new_names == self._last_tool_names and self._last_refresh > 0:
                self._last_refresh = now  # Reset TTL without rebuilding
                return
            # Rebuild tool maps
            self.tools_by_name = {tool.name: tool for tool in tools}
            self.tool_to_state_args = {
                tool.name: _get_state_args(tool)
                for tool in tools
            }
            self.tool_to_store_arg = {
                tool.name: _get_store_arg(tool)
                for tool in tools
            }
            self._last_tool_names = new_names
            self._last_refresh = now

    def invalidate_tool_cache(self) -> None:
        """Force a full tool reload on the next invocation (e.g. after MCP reconnect)."""
        with self._refresh_lock:
            self._last_refresh = 0.0

    @staticmethod
    def _run_coroutine_sync(coroutine: Coroutine[Any, Any, T]) -> T:
        """Run an async middleware hook from a synchronous tool path."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coroutine)

        logger.warning(
            "DynamicToolNode._run_coroutine_sync: called inside a running event loop. "
            "Spawning a daemon thread to avoid nested-loop deadlock. "
            "This is safe for stateless middleware but may fail if the coroutine "
            "uses thread-local DB sessions. Prefer ainvoke() over invoke()."
        )

        result_box: list[Any] = []
        error_box: list[BaseException] = []

        def _runner() -> None:
            try:
                result_box.append(asyncio.run(coroutine))
            except BaseException as exc:  # noqa: BLE001
                error_box.append(exc)

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        thread.join(timeout=30.0)
        if thread.is_alive():
            raise TimeoutError(
                "DynamicToolNode._run_coroutine_sync: thread did not complete within 30 s"
            )

        if error_box:
            raise error_box[0]
        if not result_box:
            raise RuntimeError(
                "DynamicToolNode._run_coroutine_sync: thread completed but produced no result"
            )
        return cast(T, result_box[0])

    def _build_tool_config(
        self,
        config: RunnableConfig | None,
        *,
        tool_call_id: str,
    ) -> RunnableConfig:
        """Create a per-tool-call config so middleware state does not collide."""
        tool_config = dict(config or {})
        configurable = _coerce_json_object(tool_config.get("configurable", {}))
        configurable["tool_call_id"] = tool_call_id
        tool_config["configurable"] = configurable
        return cast(RunnableConfig, tool_config)

    def _build_state(self, input: Any) -> ThreadState:
        """Best-effort conversion from ToolNode input to ThreadState."""
        if isinstance(input, dict):
            return create_thread_state(input)
        if isinstance(input, list):
            return create_thread_state(messages=cast(list[AnyMessage], input))
        if hasattr(input, "model_dump"):
            payload = input.model_dump()
            if isinstance(payload, dict):
                return create_thread_state(payload)
        messages = getattr(input, self.messages_key, None)
        if isinstance(messages, list):
            return create_thread_state(messages=cast(list[AnyMessage], messages))
        return create_thread_state()

    async def _apply_before_tool(
        self,
        *,
        state: ThreadState,
        config: RunnableConfig,
        call: ToolCall,
    ) -> ToolCall:
        updated_call = dict(call)
        tool_name = str(updated_call["name"])
        tool_args = _coerce_json_object(updated_call.get("args") or {})

        for middleware in self._middlewares:
            try:
                tool_name, tool_args = await middleware.before_tool(
                    state,
                    config,
                    tool_name,
                    tool_args,
                )
            except Exception:
                logger.exception(
                    "Middleware %s.before_tool failed for tool %s, skipping",
                    type(middleware).__name__,
                    tool_name,
                )

        updated_call["name"] = tool_name
        updated_call["args"] = tool_args
        return cast(ToolCall, updated_call)

    async def _apply_after_tool(
        self,
        *,
        state: ThreadState,
        config: RunnableConfig,
        call: ToolCall,
        response: Any,
    ) -> Any:
        result: Any = response.content if isinstance(response, ToolMessage) else response
        for middleware in self._middlewares:
            try:
                result = await middleware.after_tool(
                    state,
                    config,
                    str(call["name"]),
                    result,
                )
            except Exception:
                logger.exception(
                    "Middleware %s.after_tool failed for tool %s, skipping",
                    type(middleware).__name__,
                    str(call["name"]),
                )

        if isinstance(result, (ToolMessage, Command)):
            return result

        if isinstance(response, ToolMessage):
            response.content = cast(str | list[Any], msg_content_output(result))
            return response

        return ToolMessage(
            content=cast(str | list[Any], msg_content_output(result)),
            name=str(call["name"]),
            tool_call_id=str(call["id"]),
        )

    def _coerce_tool_error_message(
        self,
        *,
        call: ToolCall,
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

    def _func(
        self,
        input: Any,
        config: RunnableConfig,
        *,
        store: Any = None,
    ) -> Any:
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
        return self._combine_tool_outputs(cast(list[ToolMessage], outputs), input_type)

    async def _afunc(
        self,
        input: Any,
        config: RunnableConfig,
        *,
        store: Any = None,
    ) -> Any:
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
        return self._combine_tool_outputs(cast(list[ToolMessage], outputs), input_type)

    def _run_one_with_middlewares(
        self,
        *,
        call: ToolCall,
        input_type: ToolNodeInputType,
        config: RunnableConfig,
        state: ThreadState,
    ) -> ToolRunOutput:
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
            return cast(
                ToolRunOutput,
                self._validate_tool_command(response, updated_call, input_type),
            )
        if isinstance(response, ToolMessage):
            response.content = cast(str | list[Any], msg_content_output(response.content))
            return response
        raise TypeError(
            f"Tool {updated_call['name']} returned unexpected type: {type(response)}"
        )

    async def _arun_one_with_middlewares(
        self,
        *,
        call: ToolCall,
        input_type: ToolNodeInputType,
        config: RunnableConfig,
        state: ThreadState,
    ) -> ToolRunOutput:
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
            return cast(
                ToolRunOutput,
                self._validate_tool_command(response, updated_call, input_type),
            )
        if isinstance(response, ToolMessage):
            response.content = cast(str | list[Any], msg_content_output(response.content))
            return response
        raise TypeError(
            f"Tool {updated_call['name']} returned unexpected type: {type(response)}"
        )
