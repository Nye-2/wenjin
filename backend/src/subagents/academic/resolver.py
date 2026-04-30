"""Academic agent configuration resolver."""

import logging
from collections.abc import Mapping, Sequence
from typing import Any

from .errors import InvalidToolError, UnknownSubagentTypeError
from .registry import SubagentConfig, get_subagent_config

logger = logging.getLogger(__name__)

_RETIRED_ACADEMIC_SEARCH_TOOLS = {
    "web_search",
    "arxiv_search",
    "crossref_search",
    "openalex_search",
}


class AcademicAgentResolver:
    """Resolves academic agent configuration based on type and requested tools."""

    def __init__(self, sandbox_tools: Mapping[str, Any] | Sequence[Any]):
        """Initialize the resolver.

        Args:
            sandbox_tools: Mapping or sequence of available tools.
        """
        self._sandbox_tools = self._normalize_tools(sandbox_tools)
        self._tool_categories = {
            "search": [
                "list_workspace_reference_outline",
                "search_workspace_references",
                "read_workspace_reference_section",
            ],
            "file": [
                "read_file",
                "list_workspace_reference_outline",
                "search_workspace_references",
                "read_workspace_reference_section",
            ],
            "code": ["python_exec", "data_analysis"],
        }

    @staticmethod
    def _normalize_tools(
        sandbox_tools: Mapping[str, Any] | Sequence[Any],
    ) -> dict[str, Any]:
        """Normalize tool inputs into a name-to-tool mapping."""
        if isinstance(sandbox_tools, Mapping):
            return dict(sandbox_tools)

        normalized: dict[str, Any] = {}
        for tool in sandbox_tools:
            tool_name = getattr(tool, "name", None)
            if not tool_name:
                continue
            normalized[str(tool_name)] = tool
        return normalized

    def resolve_config(
        self,
        subagent_type: str,
        requested_tools: list[str] | None = None
    ) -> SubagentConfig:
        """Resolve agent configuration with merged tools.

        Args:
            subagent_type: Type from registry (scout, writer, synthesizer, analyst)
            requested_tools: Optional override tools

        Returns:
            SubagentConfig with merged tools

        Raises:
            UnknownSubagentTypeError: If subagent_type is not recognized.
            InvalidToolError: If all requested tools are invalid.
        """
        # Get base config from registry (raises ValueError if unknown)
        try:
            base_config = get_subagent_config(
                subagent_type,
                apply_runtime_overrides=True,
            )
        except ValueError as exc:
            raise UnknownSubagentTypeError(subagent_type) from exc

        # Merge tools: requested > default > base
        if requested_tools is not None:
            tools = self._validate_tools(requested_tools)
        else:
            tools = self._merge_default_tools(base_config.tools)

        return base_config.copy_with(tools=tools)

    def _validate_tools(self, tool_names: list[str]) -> list[str]:
        """Validate and return only available tools.

        Args:
            tool_names: List of tool names to validate.

        Returns:
            List of valid tool names.

        Raises:
            InvalidToolError: If no valid tools are found.
        """
        valid_tools = []
        invalid_tools = []

        for name in tool_names:
            if name in _RETIRED_ACADEMIC_SEARCH_TOOLS:
                invalid_tools.append(name)
            elif name in self._sandbox_tools:
                valid_tools.append(name)
            else:
                invalid_tools.append(name)

        if invalid_tools:
            logger.warning(f"Requested tools not available: {invalid_tools}")

        if not valid_tools:
            raise InvalidToolError(tool_names[0], list(self._sandbox_tools.keys()))

        return valid_tools

    def _merge_default_tools(self, base_tools: list[str]) -> list[str]:
        """Merge base tools with all available sandbox tools.

        Args:
            base_tools: Base tool list from subagent config.

        Returns:
            Merged list of all available tools.
        """
        merged = {
            tool_name
            for tool_name in base_tools
            if tool_name not in _RETIRED_ACADEMIC_SEARCH_TOOLS
        }
        merged.update(
            tool_name
            for tool_name in self._sandbox_tools.keys()
            if tool_name not in _RETIRED_ACADEMIC_SEARCH_TOOLS
        )
        return list(merged)
