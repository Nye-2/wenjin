"""Exception classes for academic agent operations."""


class AcademicAgentError(Exception):
    """Base exception for academic agent errors."""
    pass


class UnknownSubagentTypeError(AcademicAgentError):
    """Raised when subagent_type is not recognized."""

    def __init__(self, subagent_type: str):
        self.subagent_type = subagent_type
        try:
            from .registry import get_all_subagent_types

            valid_types = get_all_subagent_types()
        except Exception:
            valid_types = ["scout", "writer", "synthesizer", "analyst"]
        super().__init__(
            f"Unknown subagent type: {subagent_type}. "
            f"Valid types: {', '.join(valid_types)}"
        )


class InvalidToolError(AcademicAgentError):
    """Raised when a requested tool is not available."""

    def __init__(self, tool_name: str, available_tools: list[str]):
        self.tool_name = tool_name
        self.available_tools = available_tools
        super().__init__(
            f"Tool '{tool_name}' not available. "
            f"Available tools: {', '.join(available_tools)}"
        )
