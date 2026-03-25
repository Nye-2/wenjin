"""Tests for sandbox-backed built-in tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.sandbox.providers.local import LocalSandboxProvider
from src.tools.builtins.bash import bash_tool
from src.tools.builtins.file_ops import (
    ls_tool,
    read_file_tool,
    str_replace_tool,
    write_file_tool,
)


@pytest.mark.asyncio
async def test_read_file_tool_rejects_host_absolute_paths(tmp_path):
    provider = LocalSandboxProvider(base_dir=str(tmp_path))
    sandbox = await provider.acquire("thread-1")

    with patch(
        "src.tools.builtins.file_ops.resolve_runtime_sandbox",
        AsyncMock(return_value=sandbox),
    ):
        result = await read_file_tool.coroutine(
            file_path="/etc/hosts",
            state={"messages": []},
            config={"configurable": {"thread_id": "thread-1"}},
        )

    assert "Error reading file:" in result
    assert "/etc/hosts" in result


@pytest.mark.asyncio
async def test_file_tools_use_thread_workspace(tmp_path):
    provider = LocalSandboxProvider(base_dir=str(tmp_path))
    sandbox = await provider.acquire("thread-1")
    runtime_state = {"messages": []}
    runtime_config = {"configurable": {"thread_id": "thread-1"}}

    with patch(
        "src.tools.builtins.file_ops.resolve_runtime_sandbox",
        AsyncMock(return_value=sandbox),
    ):
        write_result = await write_file_tool.coroutine(
            file_path="notes.txt",
            content="alpha\nbeta\n",
            state=runtime_state,
            config=runtime_config,
        )
        read_result = await read_file_tool.coroutine(
            file_path="notes.txt",
            state=runtime_state,
            config=runtime_config,
        )
        replace_result = await str_replace_tool.coroutine(
            file_path="notes.txt",
            old_str="beta",
            new_str="gamma",
            state=runtime_state,
            config=runtime_config,
        )
        ls_result = await ls_tool.coroutine(
            path=".",
            state=runtime_state,
            config=runtime_config,
        )

    expected_path = tmp_path / "thread-1" / "user-data" / "workspace" / "notes.txt"
    assert write_result == "Successfully wrote to /mnt/user-data/workspace/notes.txt"
    assert "alpha" in read_result
    assert "beta" in read_result
    assert replace_result == "Replaced 1 occurrence(s) in /mnt/user-data/workspace/notes.txt"
    assert "notes.txt" in ls_result
    assert expected_path.read_text() == "alpha\ngamma\n"


@pytest.mark.asyncio
async def test_bash_tool_executes_inside_thread_workspace(tmp_path):
    provider = LocalSandboxProvider(base_dir=str(tmp_path))
    sandbox = await provider.acquire("thread-1")

    with patch(
        "src.tools.builtins.bash.resolve_runtime_sandbox",
        AsyncMock(return_value=sandbox),
    ):
        result = await bash_tool.coroutine(
            command="pwd",
            state={"messages": []},
            config={"configurable": {"thread_id": "thread-1"}},
        )

    assert str(tmp_path / "thread-1" / "user-data" / "workspace") in result


@pytest.mark.asyncio
async def test_bash_tool_rejects_host_absolute_paths(tmp_path):
    provider = LocalSandboxProvider(base_dir=str(tmp_path))
    sandbox = await provider.acquire("thread-1")

    with patch(
        "src.tools.builtins.bash.resolve_runtime_sandbox",
        AsyncMock(return_value=sandbox),
    ):
        result = await bash_tool.coroutine(
            command="cat /etc/hosts",
            state={"messages": []},
            config={"configurable": {"thread_id": "thread-1"}},
        )

    assert "outside sandbox" in result


@pytest.mark.asyncio
async def test_bash_tool_rejects_relative_escape_paths(tmp_path):
    provider = LocalSandboxProvider(base_dir=str(tmp_path))
    sandbox = await provider.acquire("thread-1")
    (tmp_path / "secret.txt").write_text("host-secret", encoding="utf-8")

    with patch(
        "src.tools.builtins.bash.resolve_runtime_sandbox",
        AsyncMock(return_value=sandbox),
    ):
        result = await bash_tool.coroutine(
            command="cat ../../../secret.txt",
            state={"messages": []},
            config={"configurable": {"thread_id": "thread-1"}},
        )

    assert "outside sandbox" in result
