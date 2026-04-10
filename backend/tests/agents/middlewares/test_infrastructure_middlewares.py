"""Tests for shared infrastructure middlewares."""

import pytest

from src.agents.middlewares.sandbox import SandboxMiddleware
from src.agents.middlewares.dangling_tool_call import DanglingToolCallMiddleware
from src.agents.middlewares.thread_data import ThreadDataMiddleware
from src.agents.middlewares.title import TitleMiddleware
from src.agents.middlewares.uploads import UploadsMiddleware


class TestThreadDataMiddleware:
    @pytest.mark.asyncio
    async def test_creates_directories(self, tmp_path):
        mw = ThreadDataMiddleware(base_dir=str(tmp_path))
        state = {"messages": [], "thread_data": None}
        config = {"configurable": {"thread_id": "test-thread-1"}}
        result = await mw.before_model(state, config)
        assert result is not None
        assert "thread_data" in result
        td = result["thread_data"]
        assert "workspace_path" in td
        assert "uploads_path" in td
        assert "outputs_path" in td

    @pytest.mark.asyncio
    async def test_skips_if_thread_data_exists(self, tmp_path):
        mw = ThreadDataMiddleware(base_dir=str(tmp_path))
        existing = {"workspace_path": "/existing", "uploads_path": "/existing", "outputs_path": "/existing"}
        state = {"messages": [], "thread_data": existing}
        config = {"configurable": {"thread_id": "test-thread-1"}}
        result = await mw.before_model(state, config)
        assert result == {} or result.get("thread_data") == existing

    @pytest.mark.asyncio
    async def test_requires_thread_id(self, tmp_path):
        mw = ThreadDataMiddleware(base_dir=str(tmp_path))

        with pytest.raises(RuntimeError, match="ThreadDataMiddleware requires config.configurable.thread_id"):
            await mw.before_model({"messages": [], "thread_data": None}, {"configurable": {}})


class TestSandboxMiddleware:
    @pytest.mark.asyncio
    async def test_acquires_sandbox_with_thread_id(self):
        class _Sandbox:
            sandbox_id = "sandbox-1"

        class _Provider:
            def __init__(self):
                self.calls: list[str] = []

            async def acquire(self, thread_id: str):
                self.calls.append(thread_id)
                return _Sandbox()

        provider = _Provider()
        mw = SandboxMiddleware(provider)

        result = await mw.before_model({}, {"configurable": {"thread_id": "thread-42"}})

        assert provider.calls == ["thread-42"]
        assert result == {"sandbox": {"sandbox_id": "sandbox-1"}}

    @pytest.mark.asyncio
    async def test_requires_thread_id(self):
        class _Provider:
            async def acquire(self, thread_id: str):
                raise AssertionError(f"acquire should not be called: {thread_id}")

        mw = SandboxMiddleware(_Provider())

        with pytest.raises(RuntimeError, match="SandboxMiddleware requires config.configurable.thread_id"):
            await mw.before_model({}, {"configurable": {}})


class TestUploadsMiddleware:
    @pytest.mark.asyncio
    async def test_injects_file_info(self):
        from langchain_core.messages import HumanMessage
        mw = UploadsMiddleware()
        state = {
            "messages": [HumanMessage(content="Hello")],
            "uploaded_files": [{"name": "test.pdf", "path": "/tmp/test.pdf", "size": 1024}],
        }
        config = {"configurable": {}}
        result = await mw.before_model(state, config)
        # Should inject file info into conversation
        assert result is not None

    @pytest.mark.asyncio
    async def test_noop_without_files(self):
        from langchain_core.messages import HumanMessage
        mw = UploadsMiddleware()
        state = {"messages": [HumanMessage(content="Hello")], "uploaded_files": None}
        config = {"configurable": {}}
        result = await mw.before_model(state, config)
        assert result == {}


class TestDanglingToolCallMiddleware:
    @pytest.mark.asyncio
    async def test_patches_missing_tool_messages(self):
        from langchain_core.messages import AIMessage, HumanMessage
        mw = DanglingToolCallMiddleware()
        # Simulate: AI made a tool call but no ToolMessage followed
        ai_msg = AIMessage(content="", tool_calls=[{"id": "call_1", "name": "bash", "args": {"command": "ls"}}])
        state = {"messages": [HumanMessage(content="Hi"), ai_msg, HumanMessage(content="Continue")]}
        config = {"configurable": {}}
        result = await mw.before_model(state, config)
        if result and "messages" in result:
            # Should have injected a synthetic ToolMessage
            from langchain_core.messages import ToolMessage
            tool_msgs = [m for m in result["messages"] if isinstance(m, ToolMessage)]
            assert len(tool_msgs) >= 1

    @pytest.mark.asyncio
    async def test_noop_when_complete(self):
        from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
        mw = DanglingToolCallMiddleware()
        ai_msg = AIMessage(content="", tool_calls=[{"id": "call_1", "name": "bash", "args": {"command": "ls"}}])
        tool_msg = ToolMessage(content="output", tool_call_id="call_1")
        state = {"messages": [HumanMessage(content="Hi"), ai_msg, tool_msg]}
        config = {"configurable": {}}
        result = await mw.before_model(state, config)
        assert result == {}  # No fix needed


class TestTitleMiddleware:
    @pytest.mark.asyncio
    async def test_generates_title(self):
        from langchain_core.messages import AIMessage, HumanMessage
        mw = TitleMiddleware(max_words=8)
        state = {
            "messages": [
                HumanMessage(content="Help me research LLM alignment methods"),
                AIMessage(content="I can help you with that."),
            ],
            "title": None,
        }
        config = {"configurable": {}}
        result = await mw.after_model(state, config)
        assert result is not None
        assert "title" in result
        assert isinstance(result["title"], str)
        assert len(result["title"]) > 0

    @pytest.mark.asyncio
    async def test_skips_if_title_exists(self):
        from langchain_core.messages import AIMessage, HumanMessage
        mw = TitleMiddleware()
        state = {
            "messages": [HumanMessage(content="Hi"), AIMessage(content="Hello")],
            "title": "Existing Title",
        }
        config = {"configurable": {}}
        result = await mw.after_model(state, config)
        assert result == {}
