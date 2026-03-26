"""Integration-style tests for subagent execution runtime wiring."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

from src.agents.middlewares.execution import ExecutionMiddleware
from src.execution.types import ExecutionResult, ExecutionStatus
from src.subagents.graph import create_default_subagent_graph
from src.tools.execution import compile_latex_tool


class ToolBindableFakeMessagesListChatModel(FakeMessagesListChatModel):
    """Fake chat model that behaves like a tool-bindable chat model."""

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        return self


@pytest.mark.asyncio
async def test_subagent_graph_executes_compile_tool_via_execution_middleware():
    llm = ToolBindableFakeMessagesListChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "compile_latex_tool",
                        "args": {
                            "latex_source": (
                                "\\documentclass{article}\\begin{document}Hi\\end{document}"
                            ),
                            "compiler": "xelatex",
                        },
                        "id": "call-1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="compiled"),
        ]
    )
    execution_service = MagicMock()
    execution_service.execute = AsyncMock(
        return_value=ExecutionResult(
            status=ExecutionStatus.SUCCESS,
            sandbox_path="/mnt/user-data/execution/latex_compile/run-1/main.pdf",
            metadata={"page_count": 1},
        )
    )

    with patch(
        "src.subagents.graph.build_subagent_tool_middlewares",
        return_value=[ExecutionMiddleware(execution_service)],
    ):
        graph = create_default_subagent_graph(llm, [compile_latex_tool])
        result = await graph.ainvoke(
            {"messages": [("human", "Compile this document")]},
            config={"configurable": {"thread_id": "thread-1"}},
        )

    execution_service.execute.assert_awaited_once()
    assert result["messages"][-1].content == "compiled"
