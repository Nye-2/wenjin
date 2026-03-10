"""Test all sandbox module exports."""

import pytest
from src.sandbox import (
    # Core
    Sandbox,
    CommandResult,
    FileInfo,
    # Exceptions
    SandboxError,
    SandboxNotFoundError,
    SandboxRuntimeError,
    SandboxTimeoutError,
    # Path management
    VirtualPathMapper,
    # Sandbox providers
    LocalSandbox,
    LocalSandboxProvider,
    # Tools
    create_sandbox_tools,
)


def test_core_exports():
    """Test that core classes are exported."""
    assert Sandbox is not None
    assert CommandResult is not None
    assert FileInfo is not None


def test_exception_exports():
    """Test that exception classes are exported."""
    assert SandboxError is not None
    assert SandboxNotFoundError is not None
    assert SandboxRuntimeError is not None
    assert SandboxTimeoutError is not None


def test_path_mapper_export():
    """Test that VirtualPathMapper is exported."""
    assert VirtualPathMapper is not None

    # Test basic functionality
    mapper = VirtualPathMapper("/tmp/sandbox")
    assert mapper.base_dir == "/tmp/sandbox"

    # Test path conversion
    physical = mapper.to_physical("/mnt/user-data/workspace", "thread1")
    assert "workspace" in physical

    virtual = mapper.to_virtual("/tmp/sandbox/thread1/workspace", "thread1")
    assert virtual == "/mnt/user-data/workspace"


def test_local_sandbox_export():
    """Test that LocalSandbox is exported."""
    assert LocalSandbox is not None

    # Test basic initialization
    path_mappings = {
        "/mnt/user-data/workspace": "/tmp/test/workspace",
        "/mnt/user-data/uploads": "/tmp/test/uploads",
    }
    sandbox = LocalSandbox("test-thread", path_mappings)
    assert sandbox.sandbox_id == "test-thread"
    assert sandbox.path_mappings == path_mappings


def test_local_sandbox_provider_export():
    """Test that LocalSandboxProvider is exported."""
    assert LocalSandboxProvider is not None

    # Test basic initialization
    provider = LocalSandboxProvider("/tmp/sandbox")
    assert provider.base_dir == "/tmp/sandbox"
    assert provider._sandboxes == {}


def test_create_sandbox_tools_export():
    """Test that create_sandbox_tools is exported."""
    assert create_sandbox_tools is not None

    # Test that it returns a list
    tools = create_sandbox_tools()
    assert isinstance(tools, list)
    assert len(tools) > 0

    # Test that all tools are the expected types
    from src.sandbox.tools import bash, read_file, write_file, str_replace, list_dir

    expected_tools = [bash, read_file, write_file, str_replace, list_dir]
    assert len(tools) == len(expected_tools)

    # Check that all tools are in the returned list
    for tool in expected_tools:
        assert tool in tools


def test_sandbox_instantiation():
    """Test that we can instantiate the main sandbox class."""
    # This is a basic test to ensure the interface can be imported
    # LocalSandbox is the concrete implementation we're testing here
    path_mappings = {
        "/mnt/user-data/workspace": "/tmp/test",
    }
    sandbox = LocalSandbox("test", path_mappings)

    # Test that it's a proper Sandbox instance
    assert isinstance(sandbox, Sandbox)
    assert hasattr(sandbox, 'execute_command')
    assert hasattr(sandbox, 'read_file')
    assert hasattr(sandbox, 'write_file')
    assert hasattr(sandbox, 'list_dir')


def test_command_result_creation():
    """Test that CommandResult can be created."""
    result = CommandResult(
        stdout="test output",
        stderr="",
        exit_code=0,
        timed_out=False,
    )

    assert result.stdout == "test output"
    assert result.stderr == ""
    assert result.exit_code == 0
    assert result.timed_out is False


def test_file_info_creation():
    """Test that FileInfo can be created."""
    file_info = FileInfo(
        name="test.txt",
        path="/mnt/user-data/workspace/test.txt",
        is_dir=False,
        size=1024,
    )

    assert file_info.name == "test.txt"
    assert file_info.path == "/mnt/user-data/workspace/test.txt"
    assert file_info.is_dir is False
    assert file_info.size == 1024


if __name__ == "__main__":
    pytest.main([__file__, "-v"])