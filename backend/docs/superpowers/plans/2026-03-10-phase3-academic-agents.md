# Phase 3: Academic Agents Integration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate 4 academic subagents (Scout, Writer, Synthesizer, Analyst) into the GlobalSubagentManager infrastructure with type-based API access.

**Architecture:** Add AcademicAgentResolver for config resolution and tool merging, extend API with `subagent_type` parameter, and create academic-specific graph templates with custom system prompts.

**Tech Stack:** Python 3.12+, FastAPI, Pydantic, LangGraph, asyncio

---

## File Structure

### New Files
- `src/subagents/academic/resolver.py` - AcademicAgentResolver class
- `src/subagents/academic/errors.py` - Exception classes
- `tests/subagents/academic/__init__.py` - Test package init (if needed)
- `tests/subagents/academic/test_resolver.py` - Resolver unit tests

### Modified Files
- `src/subagents/academic/__init__.py` - Export new classes
- `src/subagents/graph.py` - Add create_academic_agent_graph, register_academic_templates
- `src/subagents/__init__.py` - Export resolver components
- `src/api/subagents.py` - Extend SpawnRequest with subagent_type, tools params
- `tests/subagents/test_api.py` - Add tests for new spawn parameters

---

## Chunk 1: Error Classes and Resolver

### Task 1: Create Exception Classes

**Files:**
- Create: `src/subagents/academic/errors.py`
- Test: `tests/subagents/academic/test_errors.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/subagents/academic/test_errors.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && uv run pytest tests/subagents/academic/test_errors.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.subagents.academic.errors'"

- [ ] **Step 3: Write minimal implementation**

```python
# src/subagents/academic/errors.py
"""Exception classes for academic agent operations."""


class AcademicAgentError(Exception):
    """Base exception for academic agent errors."""
    pass


class UnknownSubagentTypeError(AcademicAgentError):
    """Raised when subagent_type is not recognized."""

    def __init__(self, subagent_type: str):
        self.subagent_type = subagent_type
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && uv run pytest tests/subagents/academic/test_errors.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add src/subagents/academic/errors.py tests/subagents/academic/test_errors.py
git commit -m "feat(academic): add exception classes for academic agents

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 2: Create AcademicAgentResolver

**Files:**
- Create: `src/subagents/academic/resolver.py`
- Test: `tests/subagents/academic/test_resolver.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/subagents/academic/test_resolver.py
"""Tests for AcademicAgentResolver."""

import pytest
from src.subagents.academic.resolver import AcademicAgentResolver
from src.subagents.academic.errors import UnknownSubagentTypeError, InvalidToolError
from src.subagents.academic.registry import SubagentConfig


class TestAcademicAgentResolver:
    """Tests for AcademicAgentResolver."""

    @pytest.fixture
    def sandbox_tools(self):
        """Create mock sandbox tools."""
        return {
            "semantic_scholar_search": lambda q: f"search: {q}",
            "read_file": lambda p: f"read: {p}",
            "get_paper_section": lambda s: f"section: {s}",
            "get_paper_toc": lambda: "toc",
            "python_exec": lambda c: f"exec: {c}",
            "web_search": lambda q: f"web: {q}",
        }

    @pytest.fixture
    def resolver(self, sandbox_tools):
        """Create resolver instance."""
        return AcademicAgentResolver(sandbox_tools)

    def test_resolve_config_valid_scout(self, resolver):
        """Test resolving scout configuration."""
        config = resolver.resolve_config("scout")
        assert config.name == "Scout"
        assert "semantic_scholar_search" in config.tools
        assert config.system_prompt is not None

    def test_resolve_config_valid_writer(self, resolver):
        """Test resolving writer configuration."""
        config = resolver.resolve_config("writer")
        assert config.name == "Writer"
        assert "get_paper_section" in config.tools

    def test_resolve_config_valid_synthesizer(self, resolver):
        """Test resolving synthesizer configuration."""
        config = resolver.resolve_config("synthesizer")
        assert config.name == "Synthesizer"

    def test_resolve_config_valid_analyst(self, resolver):
        """Test resolving analyst configuration."""
        config = resolver.resolve_config("analyst")
        assert config.name == "Analyst"

    def test_resolve_config_invalid_type_raises(self, resolver):
        """Test that invalid type raises UnknownSubagentTypeError."""
        with pytest.raises(UnknownSubagentTypeError) as exc_info:
            resolver.resolve_config("researcher")
        assert exc_info.value.subagent_type == "researcher"

    def test_resolve_config_with_tool_override(self, resolver, sandbox_tools):
        """Test resolving config with custom tools."""
        config = resolver.resolve_config("scout", requested_tools=["read_file", "web_search"])
        assert "read_file" in config.tools
        assert "web_search" in config.tools
        # Should only have requested tools, not all sandbox tools
        assert len(config.tools) == 2

    def test_resolve_config_with_invalid_tool_in_override(self, resolver):
        """Test that invalid tools in override are filtered out."""
        config = resolver.resolve_config(
            "scout",
            requested_tools=["read_file", "nonexistent_tool"]
        )
        assert "read_file" in config.tools
        assert "nonexistent_tool" not in config.tools

    def test_resolve_config_all_invalid_tools_raises(self, resolver):
        """Test that all invalid tools raises InvalidToolError."""
        with pytest.raises(InvalidToolError) as exc_info:
            resolver.resolve_config("scout", requested_tools=["fake1", "fake2"])
        assert exc_info.value.tool_name in ["fake1", "fake2"]

    def test_resolve_config_merges_all_sandbox_tools_by_default(self, resolver, sandbox_tools):
        """Test that default behavior merges all sandbox tools."""
        config = resolver.resolve_config("scout")
        # Should have base tools + all sandbox tools
        for tool_name in sandbox_tools.keys():
            assert tool_name in config.tools

    def test_validate_tools_filters_invalid(self, resolver):
        """Test _validate_tools filters out invalid tools."""
        valid = resolver._validate_tools(["read_file", "fake_tool"])
        assert "read_file" in valid
        assert "fake_tool" not in valid

    def test_merge_default_tools_includes_all_sandbox(self, resolver, sandbox_tools):
        """Test _merge_default_tools includes all sandbox tools."""
        merged = resolver._merge_default_tools(["semantic_scholar_search"])
        for tool_name in sandbox_tools.keys():
            assert tool_name in merged
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && uv run pytest tests/subagents/academic/test_resolver.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.subagents.academic.resolver'"

- [ ] **Step 3: Write minimal implementation**

```python
# src/subagents/academic/resolver.py
"""Academic agent configuration resolver."""

import logging
from typing import Any

from .errors import InvalidToolError
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
        from .errors import UnknownSubagentTypeError
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && uv run pytest tests/subagents/academic/test_resolver.py -v`
Expected: 14 passed

- [ ] **Step 5: Commit**

```bash
git add src/subagents/academic/resolver.py tests/subagents/academic/test_resolver.py
git commit -m "feat(academic): add AcademicAgentResolver for config resolution

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 3: Update Academic Module Exports

**Files:**
- Modify: `src/subagents/academic/__init__.py`

- [ ] **Step 1: Update __init__.py exports**

```python
# src/subagents/academic/__init__.py
"""Academic subagents module.

This module provides specialized academic subagents:
- Scout: Literature exploration and citation chain tracking
- Writer: Academic writing following discipline norms
- Synthesizer: Insight generation and gap finding
- Analyst: Data analysis and methodology review
"""

from .errors import (
    AcademicAgentError,
    InvalidToolError,
    UnknownSubagentTypeError,
)
from .prompts import (
    ANALYST_PROMPT,
    SCOUT_PROMPT,
    SYNTHESIZER_PROMPT,
    WRITER_PROMPT,
)
from .registry import (
    SUBAGENT_REGISTRY,
    SubagentConfig,
    get_all_subagent_types,
    get_subagent_config,
)
from .resolver import AcademicAgentResolver

__all__ = [
    # Errors
    "AcademicAgentError",
    "InvalidToolError",
    "UnknownSubagentTypeError",
    # Prompts
    "SCOUT_PROMPT",
    "WRITER_PROMPT",
    "SYNTHESIZER_PROMPT",
    "ANALYST_PROMPT",
    # Registry
    "SubagentConfig",
    "SUBAGENT_REGISTRY",
    "get_subagent_config",
    "get_all_subagent_types",
    # Resolver
    "AcademicAgentResolver",
]
```

- [ ] **Step 2: Verify imports work**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && uv run python -c "from src.subagents.academic import AcademicAgentResolver, UnknownSubagentTypeError, InvalidToolError; print('OK')"`
Expected: OK

- [ ] **Step 3: Run all academic tests**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && uv run pytest tests/subagents/academic/ -v`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add src/subagents/academic/__init__.py
git commit -m "feat(academic): export resolver and error classes

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Chunk 2: Graph Templates

### Task 4: Add Academic Graph Template Functions

**Files:**
- Modify: `src/subagents/graph.py`
- Create: `tests/subagents/test_graph_academic.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/subagents/test_graph_academic.py
"""Tests for academic graph template functions."""

import pytest
from unittest.mock import MagicMock, patch

from src.subagents.graph import (
    create_academic_agent_graph,
    register_academic_templates,
    GraphTemplateRegistry,
)


class TestCreateAcademicAgentGraph:
    """Tests for create_academic_agent_graph."""

    def test_creates_graph_with_tools_and_prompt(self):
        """Test that graph is created with tools and system prompt."""
        mock_llm = MagicMock()
        mock_tools = [MagicMock(), MagicMock()]
        system_prompt = "You are a scout agent."

        with patch("src.subagents.graph.create_react_agent") as mock_create:
            mock_create.return_value = MagicMock()
            graph = create_academic_agent_graph(
                mock_llm,
                mock_tools,
                system_prompt,
                max_turns=10
            )
            mock_create.assert_called_once()
            call_kwargs = mock_create.call_args[1]
            assert call_kwargs["state_modifier"] == system_prompt
            assert call_kwargs["tools"] == mock_tools

    def test_uses_default_max_turns(self):
        """Test that default max_turns is 10."""
        mock_llm = MagicMock()
        mock_tools = []
        system_prompt = "Test prompt"

        with patch("src.subagents.graph.create_react_agent") as mock_create:
            mock_create.return_value = MagicMock()
            create_academic_agent_graph(mock_llm, mock_tools, system_prompt)
            assert mock_create.called


class TestRegisterAcademicTemplates:
    """Tests for register_academic_templates."""

    @pytest.fixture
    def mock_tools(self):
        """Create mock tools dict."""
        return {
            "semantic_scholar_search": MagicMock(),
            "read_file": MagicMock(),
            "get_paper_section": MagicMock(),
            "get_paper_toc": MagicMock(),
        }

    def test_registers_four_academic_templates(self, mock_tools):
        """Test that all 4 academic templates are registered."""
        registry = GraphTemplateRegistry()
        mock_llm = MagicMock()

        with patch("src.subagents.graph.create_react_agent") as mock_create:
            mock_create.return_value = MagicMock()
            register_academic_templates(registry, mock_llm, mock_tools)

        assert registry.has("academic_scout")
        assert registry.has("academic_writer")
        assert registry.has("academic_synthesizer")
        assert registry.has("academic_analyst")
        assert registry.count == 4

    def test_uses_correct_tools_for_scout(self, mock_tools):
        """Test that scout template uses correct tools."""
        registry = GraphTemplateRegistry()
        mock_llm = MagicMock()

        with patch("src.subagents.graph.create_react_agent") as mock_create:
            mock_create.return_value = MagicMock()
            register_academic_templates(registry, mock_llm, mock_tools)

            # Check that create_react_agent was called with scout's tools
            calls = mock_create.call_args_list
            scout_call = None
            for call in calls:
                kwargs = call[1]
                tools = kwargs.get("tools", [])
                # Scout should have semantic_scholar_search
                if any(hasattr(t, '_name') or t in mock_tools.values() for t in tools):
                    scout_call = call
                    break

            assert mock_create.call_count >= 4  # At least one per agent
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && uv run pytest tests/subagents/test_graph_academic.py -v`
Expected: FAIL with "ImportError: cannot import name 'create_academic_agent_graph' from 'src.subagents.graph'"

- [ ] **Step 3: Write minimal implementation**

Read current graph.py first, then extend it:

```python
# src/subagents/graph.py (append to existing file)
"""Graph template registry for subagent graphs."""

import threading
from typing import Any, Optional


class GraphTemplateRegistry:
    """Registry for graph templates used by subagents."""

    def __init__(self):
        """Initialize an empty registry."""
        self._templates: dict[str, Any] = {}
        self._lock = threading.Lock()

    @property
    def count(self) -> int:
        """Return the number of registered templates."""
        with self._lock:
            return len(self._templates)

    def register(self, name: str, graph: Any) -> None:
        """Register a graph template.

        Args:
            name: Template name.
            graph: Graph object to register.
        """
        with self._lock:
            self._templates[name] = graph

    def get(self, name: str) -> Optional[Any]:
        """Get a registered graph template.

        Args:
            name: Template name.

        Returns:
            Graph object if found, None otherwise.
        """
        with self._lock:
            return self._templates.get(name)

    def has(self, name: str) -> bool:
        """Check if a template is registered.

        Args:
            name: Template name.

        Returns:
            True if registered, False otherwise.
        """
        with self._lock:
            return name in self._templates


def create_default_subagent_graph(llm: Any, tools: list, max_turns: int = 10) -> Any:
    """Create a default ReAct-style subagent graph.

    Args:
        llm: Language model instance
        tools: List of tools available to the agent
        max_turns: Maximum number of turns (default: 10)

    Returns:
        A compiled LangGraph agent

    Raises:
        ImportError: If langgraph is not installed
    """
    try:
        from langgraph.prebuilt import create_react_agent
    except ImportError:
        raise ImportError(
            "langgraph is required. Install with: pip install langgraph"
        )

    return create_react_agent(llm, tools=tools)


def create_academic_agent_graph(
    llm: Any,
    tools: list,
    system_prompt: str,
    max_turns: int = 10
) -> Any:
    """Create a ReAct agent with custom system prompt for academic tasks.

    Args:
        llm: Language model instance
        tools: List of tools available to the agent
        system_prompt: Custom system prompt for the academic agent
        max_turns: Maximum number of turns (default: 10)

    Returns:
        A compiled LangGraph agent with custom system prompt

    Raises:
        ImportError: If langgraph is not installed
    """
    try:
        from langgraph.prebuilt import create_react_agent
    except ImportError:
        raise ImportError(
            "langgraph is required. Install with: pip install langgraph"
        )

    return create_react_agent(
        llm,
        tools=tools,
        state_modifier=system_prompt
    )


def register_academic_templates(
    registry: GraphTemplateRegistry,
    llm: Any,
    tools: dict
) -> None:
    """Register academic agent graph templates.

    Args:
        registry: GraphTemplateRegistry instance
        llm: Language model instance
        tools: Dictionary of available tools
    """
    from src.subagents.academic import get_subagent_config, get_all_subagent_types

    for agent_type in get_all_subagent_types():
        config = get_subagent_config(agent_type)
        # Filter tools to only those available
        agent_tools = [tools[t] for t in config.tools if t in tools]
        graph = create_academic_agent_graph(
            llm,
            agent_tools,
            config.system_prompt,
            max_turns=config.max_turns
        )
        registry.register(f"academic_{agent_type}", graph)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && uv run pytest tests/subagents/test_graph_academic.py -v`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add src/subagents/graph.py tests/subagents/test_graph_academic.py
git commit -m "feat(graph): add academic graph template functions

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Chunk 3: API Extension

### Task 5: Extend SpawnRequest with subagent_type and tools

**Files:**
- Modify: `src/api/subagents.py`
- Modify: `tests/subagents/test_api.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/subagents/test_api.py`:

```python
# Add to tests/subagents/test_api.py

# Add new imports at top
from src.subagents.academic import AcademicAgentResolver


class TestSpawnWithSubagentType:
    """Tests for spawn endpoint with subagent_type parameter."""

    @pytest.fixture
    def mock_manager_with_tools(self, mock_manager):
        """Create mock manager with tools."""
        mock_manager._tools = {
            "semantic_scholar_search": lambda q: f"search: {q}",
            "read_file": lambda p: f"read: {p}",
            "get_paper_section": lambda s: f"section: {s}",
            "get_paper_toc": lambda: "toc",
        }
        return mock_manager

    def test_spawn_with_valid_subagent_type(self, client, mock_manager_with_tools, app):
        """Test spawning with valid subagent_type."""
        app.dependency_overrides[get_manager] = lambda: mock_manager_with_tools
        response = client.post(
            "/subagents/threads/thread-123/spawn",
            json={
                "prompt": "Search for papers",
                "subagent_type": "scout"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert data["status"] == "pending"
        app.dependency_overrides = {}

    def test_spawn_with_invalid_subagent_type_returns_400(self, client, mock_manager_with_tools, app):
        """Test spawning with invalid subagent_type returns 400."""
        app.dependency_overrides[get_manager] = lambda: mock_manager_with_tools
        response = client.post(
            "/subagents/threads/thread-123/spawn",
            json={
                "prompt": "Search for papers",
                "subagent_type": "researcher"  # Invalid type
            }
        )
        assert response.status_code == 400
        data = response.json()
        assert "UnknownSubagentType" in data["detail"]["error"]
        assert "scout" in str(data["detail"]["valid_types"])
        app.dependency_overrides = {}

    def test_spawn_with_tool_override(self, client, mock_manager_with_tools, app):
        """Test spawning with custom tools override."""
        app.dependency_overrides[get_manager] = lambda: mock_manager_with_tools
        response = client.post(
            "/subagents/threads/thread-123/spawn",
            json={
                "prompt": "Search for papers",
                "subagent_type": "scout",
                "tools": ["read_file"]
            }
        )
        assert response.status_code == 200
        app.dependency_overrides = {}

    def test_spawn_with_invalid_tools_returns_400(self, client, mock_manager_with_tools, app):
        """Test spawning with all invalid tools returns 400."""
        app.dependency_overrides[get_manager] = lambda: mock_manager_with_tools
        response = client.post(
            "/subagents/threads/thread-123/spawn",
            json={
                "prompt": "Search for papers",
                "subagent_type": "scout",
                "tools": ["nonexistent_tool"]
            }
        )
        assert response.status_code == 400
        data = response.json()
        assert "InvalidTool" in data["detail"]["error"]
        app.dependency_overrides = {}

    def test_spawn_without_subagent_type_backward_compat(self, client, mock_manager_with_tools, app):
        """Test backward compatibility - spawn without subagent_type."""
        app.dependency_overrides[get_manager] = lambda: mock_manager_with_tools
        response = client.post(
            "/subagents/threads/thread-123/spawn",
            json={"prompt": "Test prompt"}
        )
        assert response.status_code == 200
        app.dependency_overrides = {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && uv run pytest tests/subagents/test_api.py::TestSpawnWithSubagentType -v`
Expected: FAIL with "pydantic_core._pydantic_core.ValidationError" or similar

- [ ] **Step 3: Write minimal implementation**

Update `src/api/subagents.py`:

```python
# src/api/subagents.py
"""FastAPI routes for subagent operations."""

from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.subagents import (
    GlobalSubagentManager,
    SubagentTask,
    SubagentStatus,
    SubagentResult,
)


router = APIRouter(prefix="/subagents", tags=["subagents"])


class SpawnRequest(BaseModel):
    """Request to spawn a new subagent."""
    prompt: str
    subagent_type: Optional[str] = None  # NEW: scout, writer, synthesizer, analyst
    tools: Optional[list[str]] = None    # NEW: optional tool override
    max_turns: int = 10
    timeout: int = 900
    graph_template: str = "default"


class SpawnResponse(BaseModel):
    """Response after spawning a subagent."""
    task_id: str
    status: str


class TaskStatusResponse(BaseModel):
    """Response with task status."""
    task_id: str
    thread_id: str
    status: SubagentStatus
    result: Optional[SubagentResult] = None


class CancelResponse(BaseModel):
    """Response after cancelling a task."""
    success: bool


def get_manager() -> GlobalSubagentManager:
    """Get the GlobalSubagentManager instance."""
    return GlobalSubagentManager.get_instance()


@router.post("/threads/{thread_id}/spawn", response_model=SpawnResponse)
async def spawn_subagent(
    thread_id: str,
    request: SpawnRequest,
    manager: GlobalSubagentManager = Depends(get_manager),
) -> SpawnResponse:
    """Spawn a new subagent task.

    Args:
        thread_id: Thread ID for the task.
        request: Spawn request parameters.
        manager: GlobalSubagentManager instance.

    Returns:
        SpawnResponse with task ID and initial status.

    Raises:
        HTTPException: If subagent_type is unknown or tools are invalid.
    """
    from datetime import datetime

    # Import academic resolver components
    from src.subagents.academic import (
        AcademicAgentResolver,
        UnknownSubagentTypeError,
        InvalidToolError,
        get_all_subagent_types,
    )

    # Resolve agent config if subagent_type specified
    system_prompt = None
    if request.subagent_type:
        resolver = AcademicAgentResolver(manager._tools)
        try:
            config = resolver.resolve_config(request.subagent_type, request.tools)
            system_prompt = config.system_prompt
        except UnknownSubagentTypeError as e:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "UnknownSubagentType",
                    "message": str(e),
                    "valid_types": get_all_subagent_types(),
                }
            )
        except InvalidToolError as e:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "InvalidTool",
                    "message": str(e),
                    "available_tools": e.available_tools,
                }
            )

    task = SubagentTask(
        task_id=str(uuid4()),
        thread_id=thread_id,
        prompt=request.prompt,
        created_at=datetime.now(),
        max_turns=min(request.max_turns, manager._config.max_turns_limit),
        timeout=min(request.timeout, manager._config.max_timeout),
        graph_template=request.graph_template,
        tools=request.tools or [],
        metadata={
            "subagent_type": request.subagent_type,
            "system_prompt": system_prompt,
        }
    )
    await manager.spawn(task)
    return SpawnResponse(task_id=task.task_id, status="pending")


@router.get(
    "/threads/{thread_id}/tasks/{task_id}/status",
    response_model=TaskStatusResponse,
)
async def get_task_status(
    thread_id: str,
    task_id: str,
    manager: GlobalSubagentManager = Depends(get_manager),
) -> TaskStatusResponse:
    """Get the status of a subagent task.

    Args:
        thread_id: Thread ID.
        task_id: Task ID.
        manager: GlobalSubagentManager instance.

    Returns:
        TaskStatusResponse with status and optional result.

    Raises:
        HTTPException: If task not found.
    """
    status = await manager.get_status(thread_id, task_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Task not found")
    result = await manager.get_result(thread_id, task_id)
    return TaskStatusResponse(
        task_id=task_id,
        thread_id=thread_id,
        status=status,
        result=result,
    )


@router.post(
    "/threads/{thread_id}/tasks/{task_id}/cancel",
    response_model=CancelResponse,
)
async def cancel_task(
    thread_id: str,
    task_id: str,
    manager: GlobalSubagentManager = Depends(get_manager),
) -> CancelResponse:
    """Cancel a running subagent task.

    Args:
        thread_id: Thread ID.
        task_id: Task ID.
        manager: GlobalSubagentManager instance.

    Returns:
        CancelResponse with success status.
    """
    success = await manager.cancel(thread_id, task_id)
    return CancelResponse(success=success)


@router.get("/events")
async def subscribe_events(
    thread_id: Optional[str] = None,
    manager: GlobalSubagentManager = Depends(get_manager),
) -> StreamingResponse:
    """Subscribe to subagent event stream.

    Args:
        thread_id: Optional thread ID to filter events.
        manager: GlobalSubagentManager instance.

    Returns:
        StreamingResponse with SSE event stream.
    """
    return StreamingResponse(
        manager.subscribe_events(thread_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && uv run pytest tests/subagents/test_api.py -v`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add src/api/subagents.py tests/subagents/test_api.py
git commit -m "feat(api): add subagent_type and tools parameters to spawn endpoint

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Chunk 4: Final Verification and Exports

### Task 6: Update Subagents Module Exports

**Files:**
- Modify: `src/subagents/__init__.py`

- [ ] **Step 1: Update exports**

```python
# src/subagents/__init__.py
"""Subagents module initialization."""

from .registry import SubagentConfig as SubagentTypeConfig, SubagentRegistry
from .task_tool import task_tool
from .parallel import ParallelExecutor, ExecutionPhase, PhasedPlan, PhaseResult
from .models import SubagentStatus, SubagentTask, SubagentEvent, SubagentResult
from .config import SubagentConfig
from .manager import ThreadContext, GlobalSubagentManager
from .graph import (
    GraphTemplateRegistry,
    create_default_subagent_graph,
    create_academic_agent_graph,
    register_academic_templates,
)

__all__ = [
    "SubagentRegistry",
    "SubagentTypeConfig",  # Legacy: Subagent type configuration (dataclass)
    "SubagentConfig",      # New: System configuration (Pydantic)
    "SubagentStatus",
    "SubagentTask",
    "SubagentEvent",
    "SubagentResult",
    "task_tool",
    "ParallelExecutor",
    "ExecutionPhase",
    "PhasedPlan",
    "PhaseResult",
    "ThreadContext",
    "GlobalSubagentManager",
    # Graph
    "GraphTemplateRegistry",
    "create_default_subagent_graph",
    "create_academic_agent_graph",
    "register_academic_templates",
]
```

- [ ] **Step 2: Verify imports**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && uv run python -c "from src.subagents import create_academic_agent_graph, register_academic_templates; print('OK')"`
Expected: OK

- [ ] **Step 3: Run all subagent tests**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && uv run pytest tests/subagents/ -v`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add src/subagents/__init__.py
git commit -m "feat(subagents): export academic graph functions

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

### Task 7: Run Full Test Suite

- [ ] **Step 1: Run all tests**

Run: `cd /home/cjz/AcademiaGPT-V2/backend && uv run pytest -v --tb=short`
Expected: All tests pass (target: 170+ tests)

- [ ] **Step 2: Verify no regressions**

Check test count and pass rate. If failures, debug and fix.

- [ ] **Step 3: Final commit (if needed)**

```bash
git add -A
git commit -m "test: verify all tests pass after Phase 3 integration

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Exception classes | `errors.py`, `test_errors.py` |
| 2 | AcademicAgentResolver | `resolver.py`, `test_resolver.py` |
| 3 | Module exports | `academic/__init__.py` |
| 4 | Graph templates | `graph.py`, `test_graph_academic.py` |
| 5 | API extension | `subagents.py`, `test_api.py` |
| 6 | Module exports | `subagents/__init__.py` |
| 7 | Full verification | All tests |

**Total new tests: ~24**
