"""Tests for academic agent error classes."""

import pytest
from src.subagents.academic.errors import (
    AcademicAgentError,
    UnknownSubagentTypeError,
    InvalidToolError,
)


class TestAcademicAgentError:
    """Tests for base AcademicAgentError."""

    def test_base_exception_is_exception(self):
        """Test that AcademicAgentError is an Exception."""
        assert issubclass(AcademicAgentError, Exception)

    def test_can_raise_and_catch(self):
        """Test that error can be raised and caught."""
        with pytest.raises(AcademicAgentError):
            raise AcademicAgentError("Test error")


class TestUnknownSubagentTypeError:
    """Tests for UnknownSubagentTypeError."""

    def test_creates_with_subagent_type(self):
        """Test error creation with subagent_type."""
        error = UnknownSubagentTypeError("researcher")
        assert error.subagent_type == "researcher"

    def test_message_contains_type(self):
        """Test that message contains the invalid type."""
        error = UnknownSubagentTypeError("researcher")
        assert "researcher" in str(error)
        assert "scout" in str(error)  # Should list valid types

    def test_is_subclass_of_academic_agent_error(self):
        """Test that it's a subclass of AcademicAgentError."""
        assert issubclass(UnknownSubagentTypeError, AcademicAgentError)


class TestInvalidToolError:
    """Tests for InvalidToolError."""

    def test_creates_with_tool_name(self):
        """Test error creation with tool_name."""
        error = InvalidToolError("bad_tool", ["tool1", "tool2"])
        assert error.tool_name == "bad_tool"

    def test_stores_available_tools(self):
        """Test that available_tools is stored."""
        error = InvalidToolError("bad_tool", ["tool1", "tool2"])
        assert error.available_tools == ["tool1", "tool2"]

    def test_message_contains_tool_name(self):
        """Test that message contains the invalid tool name."""
        error = InvalidToolError("bad_tool", ["tool1", "tool2"])
        assert "bad_tool" in str(error)

    def test_is_subclass_of_academic_agent_error(self):
        """Test that it's a subclass of AcademicAgentError."""
        assert issubclass(InvalidToolError, AcademicAgentError)


class TestInvalidToolErrorIsSubclass:
    """Additional tests for InvalidToolError."""

    def test_is_subclass_of_academic_agent_error(self):
        """Test that InvalidToolError is a subclass of AcademicAgentError."""
        assert issubclass(InvalidToolError, AcademicAgentError)
