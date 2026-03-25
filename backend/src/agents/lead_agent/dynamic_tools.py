"""Dynamic tool node helpers for runtime-refreshable tool registries."""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from typing import Any

from langchain_core.tools import BaseTool
from langgraph.prebuilt.tool_node import ToolNode, _get_state_args, _get_store_arg

ToolLoader = Callable[[], Sequence[BaseTool]]


class DynamicToolNode(ToolNode):
    """Tool node that refreshes its tool registry before each invocation."""

    def __init__(
        self,
        tool_loader: ToolLoader,
        *,
        name: str = "tools",
        tags: list[str] | None = None,
        handle_tool_errors: bool | str | Callable[..., str] | tuple[type[Exception], ...] = True,
        messages_key: str = "messages",
    ) -> None:
        self._tool_loader = tool_loader
        self._refresh_lock = threading.RLock()
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

    def _func(self, input: Any, config, *, store=None) -> Any:
        self._refresh_tools()
        return super()._func(input, config, store=store)

    async def _afunc(self, input: Any, config, *, store=None) -> Any:
        self._refresh_tools()
        return await super()._afunc(input, config, store=store)
