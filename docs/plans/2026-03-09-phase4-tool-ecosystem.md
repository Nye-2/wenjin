# Phase 4: Tool Ecosystem Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add MCP integration framework, academic tools, sandbox environment, and frontend API adapters.

**Architecture:**
- MCP (Model Context Protocol) integration for external tool access
- Academic MCP tools: arXiv, PubMed, DOI resolvers
- Sandbox execution environment for safe code execution
- Frontend API adapters for Next.js integration

**Tech Stack:** MCP SDK, arxiv API, pubmed API, doi.org API, Docker (optional)

---

## Pre-requisites

Before starting, verify Phase 3 is complete:

```bash
cd /home/cjz/academiagpt-v2/backend
PYTHONPATH=. uv run pytest -x -q 2>&1 | tail -5
```

Expected: `972 passed`

---

### Task 1: MCP Integration Framework

**Files:**
- Create: `backend/src/mcp/__init__.py`
- Create: `backend/src/mcp/client.py`
- Create: `backend/src/mcp/manager.py`
- Create: `backend/tests/mcp/test_client.py`

**Step 1: Write the failing test**

```python
# tests/mcp/test_client.py
import pytest
from src.mcp.client import MCPClient, MCPServerConfig


class TestMCPClient:
    def test_create_config(self):
        """Should create MCP server configuration."""
        config = MCPServerConfig(
            name="test-server",
            command="python",
            args=["-m", "test_server"],
        )
        assert config.name == "test-server"
        assert config.command == "python"

    @pytest.mark.asyncio
    async def test_client_initialize(self):
        """Client should initialize with config."""
        client = MCPClient()
        assert client is not None

    def test_list_tools(self):
        """Should list available tools from config."""
        from src.mcp.manager import MCPManager
        manager = MCPManager()
        # Should return empty list if no servers configured
        tools = manager.list_tools()
        assert isinstance(tools, list)
```

**Step 2-5: Implement and test**

Create basic MCP integration:
- `MCPServerConfig`: Configuration dataclass
- `MCPClient`: Client for connecting to MCP servers
- `MCPManager`: Manager for multiple MCP connections

**Step 6: Commit**

```bash
git add backend/src/mcp/ backend/tests/mcp/
git commit -m "feat: add MCP integration framework"
```

---

### Task 2: Academic MCP Tools

**Files:**
- Create: `backend/src/mcp/tools/arxiv.py`
- Create: `backend/src/mcp/tools/pubmed.py`
- Create: `backend/src/mcp/tools/doi.py`
- Create: `backend/tests/mcp/test_academic_tools.py`

**Step 1: Write the failing test**

```python
# tests/mcp/test_academic_tools.py
import pytest
from src.mcp.tools.arxiv import ArxivTool
from src.mcp.tools.pubmed import PubMedTool
from src.mcp.tools.doi import DOITool


class TestArxivTool:
    def test_tool_creation(self):
        """ArxivTool should be created with correct name."""
        tool = ArxivTool()
        assert tool.name == "arxiv_search"

    @pytest.mark.asyncio
    async def test_search_returns_results(self):
        """Search should return paper results."""
        tool = ArxivTool()
        # Mock or use test query
        results = await tool.search("machine learning", max_results=5)
        assert isinstance(results, list)


class TestPubMedTool:
    def test_tool_creation(self):
        """PubMedTool should be created with correct name."""
        tool = PubMedTool()
        assert tool.name == "pubmed_search"


class TestDOITool:
    def test_tool_creation(self):
        """DOITool should be created with correct name."""
        tool = DOITool()
        assert tool.name == "doi_resolve"

    @pytest.mark.asyncio
    async def test_resolve_doi(self):
        """Should resolve DOI to metadata."""
        tool = DOITool()
        # Test with a known DOI
        metadata = await tool.resolve("10.1038/nature12373")
        assert metadata is not None
```

**Step 2-5: Implement and test**

Create academic tools:
- `ArxivTool`: Search arXiv papers
- `PubMedTool`: Search PubMed papers
- `DOITool`: Resolve DOI to metadata

**Step 6: Commit**

```bash
git add backend/src/mcp/tools/ backend/tests/mcp/test_academic_tools.py
git commit -m "feat: add academic MCP tools (arxiv, pubmed, doi)"
```

---

### Task 3: Sandbox Execution Environment

**Files:**
- Create: `backend/src/sandbox/__init__.py`
- Create: `backend/src/sandbox/executor.py`
- Create: `backend/tests/sandbox/test_executor.py`

**Step 1: Write the failing test**

```python
# tests/sandbox/test_executor.py
import pytest
from src.sandbox.executor import SandboxExecutor, SandboxConfig


class TestSandboxExecutor:
    def test_create_config(self):
        """Should create sandbox configuration."""
        config = SandboxConfig(
            timeout=30,
            max_memory_mb=512,
        )
        assert config.timeout == 30

    @pytest.mark.asyncio
    async def test_execute_simple_code(self):
        """Should execute simple Python code."""
        executor = SandboxExecutor()
        result = await executor.execute("print('hello')")
        assert result.success
        assert "hello" in result.output

    @pytest.mark.asyncio
    async def test_timeout_enforcement(self):
        """Should enforce timeout on long-running code."""
        executor = SandboxExecutor(SandboxConfig(timeout=1))
        result = await executor.execute("import time; time.sleep(10)")
        assert not result.success
        assert "timeout" in result.error.lower()

    @pytest.mark.asyncio
    async def test_restricted_operations(self):
        """Should block dangerous operations."""
        executor = SandboxExecutor()
        result = await executor.execute("import os; os.system('rm -rf /')")
        assert not result.success
```

**Step 2-5: Implement and test**

Create sandbox executor:
- Basic Python code execution with restricted builtins
- Timeout enforcement
- Memory limits (optional)
- Safe file operations

**Step 6: Commit**

```bash
git add backend/src/sandbox/ backend/tests/sandbox/
git commit -m "feat: add sandbox execution environment"
```

---

### Task 4: Frontend API Adapters

**Files:**
- Create: `backend/src/gateway/adapters/skill_adapter.py`
- Create: `backend/src/gateway/adapters/workspace_adapter.py`
- Modify: `backend/src/gateway/routers/academic.py`
- Create: `backend/tests/gateway/test_adapters.py`

**Step 1: Write the failing test**

```python
# tests/gateway/test_adapters.py
import pytest
from src.gateway.adapters.skill_adapter import SkillAdapter
from src.gateway.adapters.workspace_adapter import WorkspaceAdapter


class TestSkillAdapter:
    @pytest.mark.asyncio
    async def test_list_skills(self):
        """Should list available skills."""
        adapter = SkillAdapter()
        skills = await adapter.list_skills()
        assert isinstance(skills, list)
        assert len(skills) >= 8  # At least 8 academic skills

    @pytest.mark.asyncio
    async def test_execute_skill(self):
        """Should execute a skill and return result."""
        adapter = SkillAdapter()
        result = await adapter.execute_skill(
            skill_name="deep-research",
            workspace_id="test",
            query="test query",
        )
        assert result is not None


class TestWorkspaceAdapter:
    @pytest.mark.asyncio
    async def test_list_workspaces(self):
        """Should list workspaces."""
        adapter = WorkspaceAdapter()
        workspaces = await adapter.list_workspaces(user_id="test")
        assert isinstance(workspaces, list)
```

**Step 2-5: Implement and test**

Create adapters:
- `SkillAdapter`: Bridge between frontend and skill execution
- `WorkspaceAdapter`: Bridge between frontend and workspace management
- Update API routes to use adapters

**Step 6: Commit**

```bash
git add backend/src/gateway/adapters/ backend/tests/gateway/test_adapters.py
git commit -m "feat: add frontend API adapters"
```

---

### Task 5: Integration Test - Tool Chain

**Files:**
- Create: `backend/tests/integration/test_tool_chain.py`

**Step 1: Write integration test**

```python
# tests/integration/test_tool_chain.py
"""Integration tests for tool chain execution."""

import pytest


class TestToolChainIntegration:
    @pytest.mark.asyncio
    async def test_mcp_tool_in_skill(self):
        """Skills should be able to use MCP tools."""
        # Test skill can call arxiv tool
        ...

    @pytest.mark.asyncio
    async def test_sandbox_in_skill(self):
        """Skills should be able to use sandbox for code execution."""
        # Test skill can execute code in sandbox
        ...

    @pytest.mark.asyncio
    async def test_full_tool_chain(self):
        """Complete tool chain should work end-to-end."""
        # Test: arxiv search -> sandbox analysis -> paper generation
        ...
```

**Step 2-3: Run tests and commit**

---

### Task 6: Final Verification

**Step 1: Run full test suite**

```bash
cd /home/cjz/academiagpt-v2/backend
PYTHONPATH=. uv run pytest -v 2>&1 | tail -20
```

**Step 2: Verify Phase 4 imports**

```python
from src.mcp.client import MCPClient
from src.mcp.tools.arxiv import ArxivTool
from src.sandbox.executor import SandboxExecutor
from src.gateway.adapters.skill_adapter import SkillAdapter
print("Phase 4 imports successful!")
```

**Step 3: Commit phase summary**

```bash
git add -A
git commit -m "docs: Phase 4 Tool Ecosystem complete

- MCP integration framework
- Academic tools (arxiv, pubmed, doi)
- Sandbox execution environment
- Frontend API adapters"
```

---

## Post-Phase 4 Checklist

- [ ] All tests pass
- [ ] MCP tools can be called from skills
- [ ] Sandbox executes code safely
- [ ] Frontend adapters work with Next.js

## What's Next: Phase 5

Phase 5 (Frontend Optimization) will use the ui-ux-pro-max skill to optimize the Next.js frontend.
