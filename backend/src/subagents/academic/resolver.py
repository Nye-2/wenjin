"""Academic agent configuration resolver."""

import logging
from typing import Any

from .errors import InvalidToolError, UnknownSubagentTypeError
from .registry import SubagentConfig, get_subagent_config


logger = logging.getLogger(__name__)


class AcademicAgentResolver:
    """Resolves academic agent configuration based on type and requested tools."""

    def __init__(self, sandbox_tools: dict[str, Any]):
        """Initialize the resolver.

        Args:
            sandbox_tools: Dictionary of available sandbox tools.
        """
        self._sandbox_tools = sandbox_tools
        self._tool_categories = {
            "search": ["semantic_scholar_search", "web_search", "arxiv_search"],
            "file": ["read_file", "get_paper_section", "get_paper_toc"],
            "code": ["python_exec", "data_analysis"],
        }

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
            base_config = get_subagent_config(subagent_type)
        except ValueError:
            raise UnknownSubagentTypeError(subagent_type)

        # Merge tools: requested > default > base
        if requested_tools is not None:
            tools = self._validate_tools(requested_tools)
        else:
            tools = self._merge_default_tools(base_config.tools)

        return SubagentConfig(
            name=base_config.name,
            description=base_config.description,
            system_prompt=base_config.system_prompt,
            tools=tools,
            max_turns=base_config.max_turns,
        )

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
            if name in self._sandbox_tools:
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
        merged = set(base_tools)
        merged.update(self._sandbox_tools.keys())
        return list(merged)
